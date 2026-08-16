"""Parsers de Zorrilla Subastas (Montevideo, UY) via LiveAuctioneers.

POR QUE ESTA FUENTE Y NO zorrilla.com.uy:
El sitio propio de la casa despublica los lotes despues de cada remate: las 70 subastas
de /subastas-anteriores/ devuelven "No se encontraron resultados" (verificado 2026-08-01
con navegador real, no es falta de JS). Solo sobrevive /venta-directa/, que son precios
fijos, no precios de remate. LiveAuctioneers si conserva el historico completo
(45 catalogos, 2019-2023) CON precio de remate y sin login.

POR QUE JSON Y NO CSS/DOM:
LiveAuctioneers es React; el precio no esta en el DOM inicial (la UI muestra
"See Sold Price"). Pero la pagina embebe `window.__data = {...}` con el registro
completo de cada lote, incluido `salePrice`. Leer ese JSON es mas estable que
perseguir clases de React que cambian en cada despliegue.

MONEDA: LiveAuctioneers normaliza a USD en origen (`currency: "USD"` en los 45
catalogos). El remate original pudo cotizarse en UYU; ese dato NO existe en esta
fuente. Ver el quality_flag emitido en gold para la salvedad.
"""

from __future__ import annotations

import datetime
import json
import re
from typing import Any, Optional

from scraping.common.models import AuctionMeta

HOUSE_NAME = "Zorrilla Subastas"
SELLER_ID = 6727
BASE_URL = "https://www.liveauctioneers.com"

# LiveAuctioneers pinta 28 lotes por pagina en /catalog/<id>/?page=N
LOTS_PER_PAGE = 28


# ---------------------------------------------------------------------------
# Acceso al JSON embebido
# ---------------------------------------------------------------------------

def extract_page_data(page: Any) -> dict:
    """Devuelve el objeto `window.__data` de la pagina, o {} si no esta.

    Usa raw_decode en vez de una regex con `};`: el payload tiene llaves anidadas y
    cualquier regex no-greedy corta a mitad (probado: "Extra data" en json.loads).
    """
    html = _page_html(page)
    idx = html.find("window.__data")
    if idx == -1:
        return {}
    start = html.find("{", idx)
    if start == -1:
        return {}
    blob = html[start:]
    # el payload trae `undefined` literal, que no es JSON valido
    blob = re.sub(r"\bundefined\b", "null", blob)
    try:
        obj, _end = json.JSONDecoder().raw_decode(blob)
    except ValueError:
        return {}
    return obj if isinstance(obj, dict) else {}


def _page_html(page: Any) -> str:
    """Normaliza lo que devuelve el fetcher a str.

    OJO: con scrapling, str(page) devuelve solo "<200 url>"; el HTML real esta en
    .html_content. Los tests pasan el HTML como str directamente.
    """
    if isinstance(page, str):
        return page
    content = getattr(page, "html_content", None)
    if content is not None:
        return str(content)
    return str(page)


def _items(data: dict) -> dict:
    return (data.get("itemSummary") or {}).get("byId") or {}


def _catalogs(data: dict) -> dict:
    return (data.get("catalog") or {}).get("byId") or {}


def _iso_from_epoch(ts: Any) -> Optional[str]:
    """epoch UTC -> ISO. LiveAuctioneers da timestamps, asi que no hay que
    interpretar texto en espanol como en Duran ("Julio 2014")."""
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat()


def _int_or_none(value: Any) -> Optional[int]:
    """0 no es un precio: LiveAuctioneers usa 0 como 'sin dato'."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


# ---------------------------------------------------------------------------
# Funciones exigidas por House.REQUIRED_PARSER_FUNCS
# ---------------------------------------------------------------------------

def _auction_id_from_url(auction_url: str) -> str:
    """https://www.liveauctioneers.com/catalog/214514/?page=2 -> "214514"."""
    match = re.search(r"/catalog/(\d+)", auction_url or "")
    if match:
        return match.group(1)
    return (auction_url or "").rstrip("/").split("/")[-1].split("?")[0]


def get_auction_title_from_page(page: Any) -> Optional[str]:
    data = extract_page_data(page)
    for catalog in _catalogs(data).values():
        title = catalog.get("title")
        if title:
            return str(title)
    for item in _items(data).values():
        title = item.get("catalogTitle")
        if title:
            return str(title)
    return None


def get_auction_start_date_from_page(page: Any) -> Optional[str]:
    """Hook opcional que default_build_meta llama via hasattr."""
    data = extract_page_data(page)
    for catalog in _catalogs(data).values():
        iso = _iso_from_epoch(catalog.get("saleStartTs"))
        if iso:
            return iso
    for item in _items(data).values():
        iso = _iso_from_epoch(item.get("saleStartTs"))
        if iso:
            return iso
    return None


def parse_auction_page(page: Any, meta: Optional[AuctionMeta] = None) -> list[dict]:
    """Un preview por lote del catalogo, ya con precio de remate.

    Devuelve todos los campos que el engine necesita, para poder correr con --quick
    (skip_lot_detail) y evitar 12.500 fetchs de detalle: el payload del catalogo ya
    trae titulo, precio, estimaciones y estado.
    """
    data = extract_page_data(page)
    catalog_id = _auction_id_from_url(meta.auction_url) if meta else None

    previews: list[dict] = []
    for item in _items(data).values():
        # La pagina incluye "Similar Items" de OTRAS casas; filtrarlos o
        # contaminariamos el catalogo con lotes ajenos.
        if int(item.get("sellerId") or 0) != SELLER_ID:
            continue
        if catalog_id and str(item.get("catalogId")) != str(catalog_id):
            continue

        item_id = item.get("itemId")
        if not item_id:
            continue

        slug = item.get("slug") or ""
        lot_url = f"{BASE_URL}/item/{item_id}"
        if slug:
            lot_url = f"{lot_url}_{slug}"

        is_sold = bool(item.get("isSold"))
        description = (item.get("shortDescription") or "").strip() or None
        preview = {
            "lot_url": lot_url,
            "lot_number": _lot_number(item.get("lotNumber")),
            "lot_title": (item.get("title") or "").strip() or None,
            "price_sold": _int_or_none(item.get("salePrice")) if is_sold else None,
            "price_estimate_min": _int_or_none(item.get("lowBidEstimate")),
            "price_estimate_max": _int_or_none(item.get("highBidEstimate")),
            # el estado es explicito en el payload -> no lo inferimos de "tiene precio"
            "status": "VENDIDO" if is_sold else "NO VENDIDO",
            "description": description,
            "image_url": _image_url(item),
            "category": None,
        }
        preview.update(_artist_from_description(description))
        previews.append(preview)

    previews.sort(key=lambda p: (p["lot_number"] is None, p["lot_number"] or 0))
    return previews


# LiveAuctioneers no publica campo de artista, pero la descripcion sigue un
# patron muy regular en los catalogos de arte:
#   'SOLARI, Luis Alberto (Uruguayan school, 1918-1993). Color engraving. "..."'
# De ahi salen artista, escuela/nacionalidad y años. Sin esto, Zorrilla se queda
# fuera del ranking de artistas pese a tener el dato delante.
_ARTIST_RE = re.compile(
    r"^\s*(?P<name>[A-ZÁÉÍÓÚÑÜ][^.(]{2,60}?)\s*"
    r"\(\s*(?P<school>[^,)]*?)\s*(?:school|escuela)?\s*,?\s*"
    r"(?P<birth>1[6-9]\d{2}|20\d{2})?\s*[-–]?\s*(?P<death>1[6-9]\d{2}|20\d{2})?\s*\)",
    re.I,
)

# Las descripciones en espanol empiezan por el TIPO DE OBJETO, no por el autor:
#   "Cuadro de José Gurvich (1927-1974)"  -> el artista es Gurvich, no "Cuadro de..."
# Sin quitar este prefijo, el ranking se llena de entradas como
# "Cuadro de Eduardo Mac Entyre".
_OBJETO_PREFIJO = re.compile(
    r"^(?:cuadro|dibujo|pintura|obra|escultura|grabado|litografia|litografía|"
    r"acuarela|oleo|óleo|serigrafia|serigrafía|painting|drawing|print|sculpture)\s+"
    r"(?:de|by|of)\s+",
    re.I,
)

# Prefijos que NO son el autor (mismos criterios que build_insights).
_NON_AUTHOR = re.compile(
    r"^(attributed to|circle of|school of|follower of|after|manner of|"
    r"atribuido|escuela|taller|seguidor|copia)\b",
    re.I,
)


def _artist_from_description(description: Optional[str]) -> dict:
    """Extrae artista/años/pais de la descripcion. {} si no hay patron claro."""
    if not description:
        return {}
    match = _ARTIST_RE.search(description)
    if not match:
        return {}

    school_raw = (match.group("school") or "").strip()
    tiene_anios = bool(match.group("birth") or match.group("death"))
    # Un parentesis sin anios NI escuela no identifica a un autor: en joyeria es
    # una medida ("Collar de 3 hilos de perlas (8.7 mm diametro promedio)").
    if not tiene_anios and not re.search(r"school|escuela|[a-z]{4,}", school_raw, re.I):
        return {}
    if re.search(r"\d\s*(mm|cm|kg|k\b|quilat|carat)", school_raw, re.I):
        return {}

    name = " ".join((match.group("name") or "").split()).strip(" .,")
    name = _OBJETO_PREFIJO.sub("", name).strip(" .,")
    if not name or len(name) < 3 or _NON_AUTHOR.match(name):
        return {}
    # "18th century", "Anonymous European"... no son personas
    if re.match(r"^(anonymous|anonimo|anónimo|\d)", name, re.I):
        return {}
    # "SOLARI, Luis Alberto" -> "Luis Alberto SOLARI" (orden natural)
    if "," in name:
        apellido, _, nombre = name.partition(",")
        nombre = nombre.strip()
        if nombre:
            name = f"{nombre} {apellido.strip()}"

    out: dict = {"artist_name": name, "artist_raw": match.group(0).strip()}
    for campo, clave in (("birth", "artist_birth_year"), ("death", "artist_death_year")):
        valor = match.group(campo)
        if valor:
            out[clave] = int(valor)
    school = (match.group("school") or "").strip()
    if school and len(school) < 40:
        out["artist_country"] = school
    return out


def _image_url(item: dict) -> Optional[str]:
    """URL de la foto principal del lote.

    El payload no trae la URL montada: da `photos` (lista de indices) e
    `imageVersion` (cache-buster). El CDN de LiveAuctioneers las combina en
    <itemId>_<n>_x.jpg. Sin esto, image_url quedaba vacio en los 11.166 lotes.
    """
    photos = item.get("photos") or []
    item_id = item.get("itemId")
    seller_id = item.get("sellerId")
    catalog_id = item.get("catalogId")
    if not (photos and item_id and seller_id and catalog_id):
        return None
    # Formato verificado contra el HTML real de la fixture, no deducido:
    # https://p1.liveauctioneers.com/6727/214514/109860982_1_x.jpg
    return (
        f"https://p1.liveauctioneers.com/{seller_id}/{catalog_id}/"
        f"{item_id}_{photos[0]}_x.jpg"
    )


def _lot_number(raw: Any) -> Optional[int]:
    """lotNumber viene como "0462" (str con ceros) y a veces con sufijo tipo "12A"."""
    if raw is None:
        return None
    match = re.search(r"\d+", str(raw))
    return int(match.group(0)) if match else None


def parse_lot_page(page: Any, meta: Optional[AuctionMeta] = None) -> dict:
    """Detalle de un lote suelto.

    Normalmente NO se usa: el catalogo ya trae todo y se corre con --quick. Existe
    porque House.REQUIRED_PARSER_FUNCS lo exige y para runs de un solo lote.
    """
    data = extract_page_data(page)
    for item in _items(data).values():
        if int(item.get("sellerId") or 0) != SELLER_ID:
            continue
        is_sold = bool(item.get("isSold"))
        return {
            "lot_number": _lot_number(item.get("lotNumber")),
            "lot_title": (item.get("title") or "").strip() or None,
            "price_sold": _int_or_none(item.get("salePrice")) if is_sold else None,
            "price_estimate_min": _int_or_none(item.get("lowBidEstimate")),
            "price_estimate_max": _int_or_none(item.get("highBidEstimate")),
            "status": "VENDIDO" if is_sold else "NO VENDIDO",
            "description": (item.get("shortDescription") or "").strip() or None,
            "image_url": _image_url(item),
            "currency": item.get("currency") or "USD",
        }
    return {}


def parse_historic_page(page: Any) -> list[AuctionMeta]:
    """Pagina de la casa -> una AuctionMeta por catalogo historico."""
    data = extract_page_data(page)
    auctions: list[AuctionMeta] = []
    seen: set[str] = set()

    for catalog_id, catalog in _catalogs(data).items():
        cid = str(catalog_id)
        if cid in seen:
            continue
        seen.add(cid)
        auctions.append(
            AuctionMeta(
                auction_id=cid,
                auction_title=str(catalog.get("title") or f"catalog-{cid}"),
                auction_start_date=_iso_from_epoch(catalog.get("saleStartTs")),
                auction_url=f"{BASE_URL}/catalog/{cid}/",
                auction_house_name=HOUSE_NAME,
            )
        )

    auctions.sort(key=lambda a: a.auction_start_date or "")
    return auctions


# ---------------------------------------------------------------------------
# Paginacion (para html_pagination_discovery)
# ---------------------------------------------------------------------------

def get_page_urls(first_page: Any, base_auction_url: str) -> list[str]:
    """Todas las paginas del catalogo, derivadas de lotsListed.

    La pagina 1 solo trae 28 de los ~300 lotes; sin esto perderiamos el 90%.
    """
    data = extract_page_data(first_page)
    total = 0
    for catalog in _catalogs(data).values():
        total = max(total, int(catalog.get("lotsListed") or 0))
    if not total:
        for item in _items(data).values():
            total = max(total, int(item.get("lotsListed") or 0))
    if not total:
        return []

    base = base_auction_url.split("?")[0].rstrip("/")
    pages = (total + LOTS_PER_PAGE - 1) // LOTS_PER_PAGE
    return [f"{base}/?page={n}" for n in range(1, pages + 1)]
