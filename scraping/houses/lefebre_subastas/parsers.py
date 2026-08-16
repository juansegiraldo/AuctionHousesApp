"""Parsers de Lefebre Subastas, sobre el API JSON de Auction Mobility.

La web es una SPA de Angular: bajarla con curl devuelve "no hay subastas
anteriores" y parece que no hay dato. Es falso — el contenido se rellena en
cliente. Pero NO hace falta navegador headless, porque hay dos seams:

1. El listado de subastas viene RENDERIZADO EN SERVIDOR dentro del blob
   `viewVars` del HTML de /auctions/past (igual que el window.__data de
   Zorrilla). La pagina 1 solo trae 20 de 29: hay que pedir ?page=2.
2. Los lotes salen del proxy AJAX del propio sitio, sin autenticacion:
       GET /ajax/lots/<codigo>?limit=100
   El backend directo (production4-server.auctionmobility.com/v1/...) devuelve
   401 con cualquier cabecera que se pruebe, incluida la amRegistrationKey que
   la propia pagina publica. Hay que pasar por el proxy.

Este modulo lee JSON, no DOM. Las funciones aceptan dict (lo que devuelve el
fetcher) o str (lo que pasan los tests), como el _page_html() de Zorrilla.

Comprobacion que da confianza al dato: la suma de sold_price de los lotes cuadra
EXACTAMENTE con el total_hammer_price que declara el resumen de la subasta. Se
cumplio en 14 de 14 subastas el 2026-08-16.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional
from urllib.parse import urlsplit

from scraping.common.models import AuctionMeta

# split_title() ya resuelve el bloque 'ARTISTA (1907-1992) / Titulo / Tecnica /
# Medidas:' en sus dos formatos (saltos de linea y espacios). Es el mismo texto
# que trae el API, asi que se reutiliza en vez de reescribirlo.
from scraping.houses.lefebre_subastas.from_excel import _BIO_RE, split_title

HOUSE_SLUG = "lefebre_subastas"
HOUSE_NAME = "Lefebre Subastas"
BASE_URL = "https://auction.lefebresubastas.com"
CURRENCY = "COP"

HISTORIC_URL = f"{BASE_URL}/auctions/past"

# Cuantos lotes pedir por pagina. El API acepta hasta 100; por encima ignora el
# limite y devuelve 100 igual.
PAGE_SIZE = 100

# Las 11 subastas cuyo dato viene del Excel curado (from_excel.py). NO se
# scrapean, por dos motivos y el segundo pesa mas que el primero:
#
# 1. Sus lot_url son 'excel://lefebre_subastas/...' sinteticas. Las del scraper
#    son https://. No colisionan, asi que Silver -que deduplica por
#    'house_slug|lot_url'- contaria cada lote DOS veces.
# 2. La web trae 890 lotes mas en esas 11 subastas, y no son dato que falte: son
#    mobiliario, joyeria, cuberterias, vajillas y obra anonima ('Escuela
#    Quitena') que el curador descarto A PROPOSITO. Medido lote a lote el
#    2026-08-16: el 93,4% de los 1.037 lotes que guardo tiene parentesis
#    biografico, frente al 0,9% de los 890 que descarto. Eso no sale de un
#    descarte por prisa; es un criterio aplicado a conciencia (quedarse con el
#    arte de artista atribuido). Traerlos convertiria una base de arte en un
#    catalogo generalista y romperia las metricas por artista.
#
# Si algun dia se quiere el dato completo de la casa, es una decision de
# producto: habria que borrar los excel:// en el mismo movimiento.
EXCEL_ONLY_AUCTIONS = {
    "4-2PS1ML",  # subasta-18
    "4-3DH3Q1",  # subasta-19
    "4-43DSCZ",  # subasta-20
    "4-4Z5007",  # subasta-21
    "4-5Z5J1Y",  # subasta-22
    "4-705B9J",  # subasta-23
    "4-7QTI5H",  # subasta-24
    "4-8Z5HCN",  # subasta-25
    "4-9VIOKS",  # subasta-26
    "4-6RD96A",  # subasta-barranquilla
    "4-544EZR",  # subasta-de-prueba-17-de-febrero-de-2022
}

_VIEWVARS_RE = re.compile(r"viewVars\s*=\s*(\{.*?\});", re.S)

# Codigo de subasta de Auction Mobility: '4-DLG0WK', '4-L2X0QX'.
_AUCTION_CODE_RE = re.compile(r"\d+-[A-Z0-9]+", re.IGNORECASE)


def _payload(page: Any) -> dict:
    """dict o str -> dict. El fetcher devuelve dict; los tests pasan str."""
    if isinstance(page, dict):
        return page
    if isinstance(page, (bytes, bytearray)):
        return json.loads(page.decode("utf-8", "replace"))
    if isinstance(page, str):
        return json.loads(page)
    # scrapling: el HTML real esta en .html_content, no en str(page)
    content = getattr(page, "html_content", None)
    return json.loads(str(content if content is not None else page))


def _html(page: Any) -> str:
    if isinstance(page, str):
        return page
    if isinstance(page, (bytes, bytearray)):
        return page.decode("utf-8", "replace")
    content = getattr(page, "html_content", None)
    return str(content if content is not None else page)


def _int_or_none(value: Any) -> Optional[int]:
    """'1500000.00' -> 1500000. Devuelve None para 0, vacio o no numerico.

    OJO: el valor llega como cadena con decimales, asi que hay que pasar por
    float antes de int. Limpiar los separadores a mano multiplicaria por 100
    (es el mismo bug que _to_int() evita en from_excel.py, alli x10).
    """
    if value is None or value == "":
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def artist_from_title(title: Optional[str]) -> tuple[Optional[str], Optional[int], Optional[int]]:
    """(artista, nacimiento, muerte) SOLO si hay parentesis biografico.

    Lefebre es una casa generalista: ademas de arte vende joyeria, relojes,
    mobiliario y vinilos. Coger "la primera linea" como nombre de artista
    fabricaria pintores llamados 'Solitario de Diamante', 'Anillo Tiffany's en
    oro blanco' o 'DURA DURAN' — el mismo defecto que _OBJECT_NAMES filtra para
    Bogota ('Cartel' con 85 lotes, 'Collar', 'Florero').

    Por eso el nombre solo se acepta cuando va seguido del parentesis con
    fechas, que es lo unico que distingue de forma fiable a una persona de un
    objeto. En las 14 subastas nuevas eso deja 1.149 de 2.054 lotes con artista
    y 905 sin el; esos 905 entran igual al pipeline, pero con artist_name a
    None. El bloque crudo se guarda en description, asi que nada se pierde.

    No es una heuristica inventada aqui: es la misma regla que el curador aplico
    a mano en el Excel de 2024 (93,4% de lo guardado con parentesis, frente al
    0,9% de lo descartado).
    """
    if not title:
        return None, None, None
    bio = _BIO_RE.search(title)
    if not bio:
        return None, None, None
    name = title[: bio.start()].strip(" ,;\n\t")
    if not name:
        return None, None, None
    years = re.findall(r"\d{4}", bio.group(0))
    birth = int(years[0]) if years else None
    death = int(years[1]) if len(years) > 1 else None
    return name, birth, death


def _auction_id_from_url(url: str) -> str:
    """URL de subasta -> slug. '/auctions/4-DLG0WK/subasta-30' -> 'subasta-30'.

    Se usa el SLUG y no el codigo (4-DLG0WK) porque run_historic_cli nombra el
    fichero de salida con esto. Las 4 subastas que ya vinieron del Excel se
    llaman subasta-27..30.jsonl; si aqui devolvieramos el codigo, el scraper
    crearia 4-DLG0WK.jsonl al lado y Bronze copiaria los dos: el mismo dato dos
    veces, con lot_url identicos, y el resume no volveria a saltarselo nunca.
    """
    path = urlsplit(url).path.rstrip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3 and parts[0] == "auctions":
        return parts[2]
    return parts[-1] if parts else url


def auction_code_from_url(url: str) -> Optional[str]:
    """'/auctions/4-DLG0WK/subasta-30' -> '4-DLG0WK' (el id del API).

    Se exige la forma '<n>-<ALFANUM>' y no se acepta cualquier segmento: si no,
    '/auctions/past' devolveria 'past' y el fetcher lo reescribiria a
    '/ajax/lots/past', rompiendo el descubrimiento del historico.
    """
    parts = [p for p in urlsplit(url).path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "auctions" and _AUCTION_CODE_RE.fullmatch(parts[1]):
        return parts[1]
    return None


def lots_url(auction_code: str, limit: int = PAGE_SIZE) -> str:
    return f"{BASE_URL}/ajax/lots/{auction_code}?limit={limit}"


def next_page_url(raw_next: Optional[str], auction_code: str) -> Optional[str]:
    """Reescribe el next_page del API al proxy del sitio.

    query_info.next_page apunta a production4-server.auctionmobility.com, que
    responde 401 sin credenciales. La query (n=, o=) si vale: se conserva y se
    cuelga del /ajax/lots del sitio, que no pide auth.
    """
    if not raw_next:
        return None
    query = urlsplit(raw_next).query
    base = f"{BASE_URL}/ajax/lots/{auction_code}"
    return f"{base}?{query}" if query else base


def get_auction_title_from_page(page: Any) -> Optional[str]:
    """El titulo viaja dentro de cada lote, en el objeto 'auction' anidado."""
    rows = _payload(page).get("result_page") or []
    for row in rows:
        auction = row.get("auction") or {}
        if auction.get("title"):
            return auction["title"]
    return None


def get_auction_start_date_from_page(page: Any) -> Optional[str]:
    """Hook opcional del framework: '2024-05-31T00:00:00Z' -> '2024-05-31'.

    Se normaliza a ISO corto porque extract_year() lee los 4 primeros
    caracteres y asi devuelve ('2024', 'iso') en vez de marcarlo como inferido.
    """
    rows = _payload(page).get("result_page") or []
    for row in rows:
        start = (row.get("auction") or {}).get("time_start")
        if start:
            return start[:10]
    return None


def parse_auction_page(page: Any, meta: Any = None) -> list[dict]:
    """Pagina del catalogo JSON -> lista de previews de lote.

    El payload del catalogo ya trae precio, estado, titulo, numero e imagen, asi
    que no hace falta bajar el detalle de cada lote (ver parse_lot_page).
    """
    previews = []
    for row in _payload(page).get("result_page") or []:
        detail = row.get("_detail_url")
        if not detail:
            continue

        # DOBLE BARRA A PROPOSITO: _detail_url ya empieza por '/', asi que esto
        # produce '...com//lots/view/...'. Es exactamente la forma con la que se
        # guardaron los 674 lotes que ya estan en Silver (verificado: 89/89 en
        # subasta-30). Un urljoin() "correcto" daria barra simple, no casaria
        # con nada de lo ingerido y duplicaria cada lote re-scrapeado.
        lot_url = f"{BASE_URL}//{detail.lstrip('/')}"

        title_block = row.get("title")
        lot_title, medium, dimensions = split_title(title_block)
        artist, birth, death = artist_from_title(title_block)

        # 'sold' es lo unico que significa vendido. 'expired' es no vendido y
        # 'active' en una subasta ya cerrada es un lote que no se remato: darle
        # EN CURSO inflaria la tasa de venta de la casa.
        sold = row.get("status") == "sold"
        price_sold = _int_or_none(row.get("sold_price")) if sold else None

        descripcion = "\n".join(
            part for part in (title_block, row.get("truncated_description")) if part
        ) or None

        previews.append(
            {
                "lot_url": lot_url,
                "lot_number": row.get("lot_number"),
                "lot_title": lot_title,
                "price_sold": price_sold,
                # La casa no publica estimate_low/high (vienen null en todos los
                # lotes medidos): el precio de salida es lo unico que hay, igual
                # que en el Excel.
                "price_estimate_min": _int_or_none(row.get("starting_price")),
                "price_estimate_max": _int_or_none(row.get("estimate_high")),
                "status": "VENDIDO" if price_sold is not None else "NO VENDIDO",
                "artist_name": artist,
                "artist_birth_year": birth,
                "artist_death_year": death,
                # Diagnostico unicamente, y aqui ni eso: la web no publica pais.
                # El pais real lo fija el maestro de artistas, nunca la casa.
                "artist_country": None,
                "artist_raw": (title_block or "")[:60] or None,
                "description": descripcion,
                "medium": medium,
                "dimensions": dimensions,
                "image_url": row.get("cover_thumbnail"),
                "category": None,
            }
        )
    return previews


def parse_lot_page(page: Any, meta: Any = None) -> dict:
    """No se usa: el catalogo ya lo trae todo.

    /ajax/lot/<row_id> devuelve {'response': ..., 'responseCode': ...} sin
    ningun campo util (comprobado el 2026-08-16), y el payload del catalogo ya
    incluye precio, estado, titulo, numero de lote e imagen. Bajar una pagina
    por lote solo anadiria 2.000 peticiones para nada. Se corre con --quick.
    """
    return {}


def _view_vars(page: Any) -> dict:
    match = _VIEWVARS_RE.search(_html(page))
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}


def raw_auction_count(page: Any) -> int:
    """Subastas que trae la pagina ANTES de excluir las del Excel.

    La paginacion se para con esto y no con el resultado ya filtrado: la pagina
    2 es casi toda del Excel y devuelve 0 utiles, pero eso no significa que se
    haya acabado el listado.
    """
    view_vars = _view_vars(page)
    return sum(
        len((view_vars.get(key) or {}).get("result_page") or [])
        for key in ("auctions", "upcomingAuctions")
    )


def parse_historic_page(page: Any) -> list[AuctionMeta]:
    """HTML de /auctions/past -> AuctionMeta, saltando las del Excel.

    El listado no esta en el DOM sino en el blob viewVars que el servidor
    incrusta en el HTML. Se leen las pasadas y las proximas.
    """
    view_vars = _view_vars(page)
    auctions: list[AuctionMeta] = []
    for key in ("auctions", "upcomingAuctions"):
        for row in (view_vars.get(key) or {}).get("result_page") or []:
            code = row.get("row_id")
            if not code or code in EXCEL_ONLY_AUCTIONS:
                continue
            slug = row.get("_slug") or code
            detail = row.get("_detail_url") or f"/auctions/{code}/{slug}"
            start = row.get("time_start")
            auctions.append(
                AuctionMeta(
                    auction_id=slug,
                    auction_title=row.get("title") or slug,
                    auction_start_date=start[:10] if start else None,
                    auction_house_name=HOUSE_NAME,
                    auction_url=f"{BASE_URL}{detail}",
                    auction_image_url=row.get("cover_thumbnail"),
                )
            )
    return auctions
