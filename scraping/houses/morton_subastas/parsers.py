"""Parsers de Morton Subastas (Ciudad de Mexico) via su web de pujas.

FUENTE: live.mortonsubastas.com, la web de pujas de la casa, montada sobre la
plataforma Bidsquare (las imagenes salen de s1.img.bidsquare.com). La web de
marketing (mortonsubastas.com, Webflow) solo enlaza ahi. Todo es HTML servido
por el servidor: no hace falta navegador headless ni API privada.

POR QUE LA FICHA DE CADA LOTE Y NO SOLO EL CATALOGO:
En las subastas anteriores a 2024 la tarjeta del catalogo dice "Login for Price"
(data-lot_price_display_level="0"): ni precio ni estado. Pero la ficha del lote
publica, sin login, un JSON-LD `Product` con `offers.price` y
`offers.availability`. Es el mismo caso que Zorrilla con "See Sold Price": el
dato esta en el HTML publico, solo que no en la parte visible.

TRAMPA DEL JSON-LD: un lote NO vendido ("Discontinued") TAMBIEN trae precio, y
no es una venta: es la salida, siempre por debajo de la estimacion baja.
Verificado 2026-10-25 contra la etiqueta visible en 20 lotes de 2024-2025:
`SoldOut` coincide peso a peso con "Sold for"; `Discontinued` es "Unsold" en los
20. Solo `SoldOut` cuenta como precio de venta. La ficha aclara "Sold Price
excludes BP": es precio de martillo, sin prima del comprador, como en las demas
casas.

MOJIBAKE REAL (no de consola): los titulos de 2021-2023 vienen con las tildes
rotas EN EL HTML de la casa ("Sin tÃ­tulo", a veces doble: "HERNÃƒÂNDEZ"). En
el mismo catalogo conviven titulos sanos y rotos, asi que se repara texto a
texto y tramo a tramo. La `description` del JSON-LD llega limpia; el `name`, no.

FECHAS: el listado pinta la hora en la zona de quien mira ("01:00AM BST") y el
JSON-LD en zonas de EE. UU. ("17:00:00 CDT"). Todo se pasa a la hora de Ciudad
de Mexico, que es donde ocurre la subasta: leida tal cual, una subasta de las
19:00 del dia 31 cae en el mes siguiente y se convierte con otra tasa.
"""

from __future__ import annotations

import datetime
import html
import json
import math
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from zoneinfo import ZoneInfo

from scrapling.parser import Selector

from scraping.common.models import AuctionMeta

HOUSE_NAME = "Morton Subastas"
BASE_URL = "https://live.mortonsubastas.com"
HISTORIC_URL = f"{BASE_URL}/en/auctions/past"

# El catalogo admite ?limit=24|48|72|96|120; con 120 una subasta tipica (~220
# lotes) son 2 paginas en vez de 5.
LOTS_PER_PAGE = 120

MEXICO_CITY = ZoneInfo("America/Mexico_City")


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------

def _page_html(page: Any) -> str:
    """Normaliza lo que devuelve el fetcher a str.

    Con scrapling, str(page) devuelve solo "<200 url>"; el HTML real esta en
    .html_content. Los tests pasan el HTML como str directamente.
    """
    if isinstance(page, str):
        return page
    content = getattr(page, "html_content", None)
    if content is not None:
        return str(content)
    return str(page)


def _selector(page: Any) -> Selector:
    return Selector(_page_html(page))


def _fold(text: str) -> str:
    """Minusculas sin acentos, para comparar titulos y lugares."""
    nfkd = unicodedata.normalize("NFKD", text or "").casefold()
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def _mojibake_bytes(text: str) -> bytes:
    """Deshace el decode erroneo: cp1252 donde existe el caracter, latin-1 donde
    no (0x81, 0x8D, 0x8F, 0x90 y 0x9D no existen en cp1252 y el decode original
    los dejo como caracteres de control: "Á" doble-codificada lleva un \\x81)."""
    out = bytearray()
    for ch in text:
        try:
            out += ch.encode("cp1252")
        except UnicodeEncodeError:
            if ord(ch) > 0xFF:
                raise
            out.append(ord(ch))
    return bytes(out)


def _undo_once(text: str) -> str:
    try:
        return _mojibake_bytes(text).decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


_NON_ASCII_RUN = re.compile(r"[^\x00-\x7f]+")


def fix_mojibake(text: Optional[str]) -> Optional[str]:
    """Repara tildes doble o triplemente codificadas, dejando intacto lo sano.

    Primero el texto entero; si no decodifica (mezcla de tramos sanos y rotos,
    como "ARÉVALO, Sin tÃ­tulo"), tramo no-ASCII a tramo: una letra sana sola
    ("É" = 0xC9) no es UTF-8 valido y se queda como estaba, igual que "Ã" de
    verdad en "SÃO PAULO" o un espacio duro.
    """
    if not text:
        return text
    for _ in range(3):
        fixed = _undo_once(text)
        if fixed == text:
            fixed = _NON_ASCII_RUN.sub(lambda m: _undo_once(m.group(0)), text)
        if fixed == text:
            break
        text = fixed
    return text


def _spanish_half(title: Optional[str]) -> Optional[str]:
    """En 2021 los titulos eran bilingues: "ES ... | EN ...". Se queda el espanol;
    el ingles duplica el texto y confundiria la categorizacion."""
    if not title:
        return title
    return title.split(" | ")[0].strip() or None


def _clean_description(text: Optional[str]) -> Optional[str]:
    """Descripcion del JSON-LD, legible. html.unescape porque el JSON-LD a veces
    trae entidades HTML escapadas dentro ("M&eacute;xico", "&Oacute;leo"): 251
    descripciones de la primera corrida, y dejaban paises como "Per&uacute;"."""
    if not text:
        return None
    lines = [" ".join(line.split()) for line in fix_mojibake(html.unescape(text)).splitlines()]
    joined = "\n".join(line for line in lines if line)
    return joined or None


def _money(value: Any) -> Optional[int]:
    """'210000.00' -> 210000. Decimal y no float: un importe no se redondea."""
    if value is None:
        return None
    try:
        number = int(Decimal(str(value).replace(",", "")))
    except (InvalidOperation, ValueError):
        return None
    return number if number > 0 else None


def _lot_number(text: Optional[str]) -> Optional[int]:
    match = re.search(r"\d+", text or "")
    return int(match.group(0)) if match else None


# ---------------------------------------------------------------------------
# Fechas
# ---------------------------------------------------------------------------

# Solo las zonas que se han visto en la fuente (BST en el listado; EST/EDT y
# CST/CDT en el JSON-LD) y sus vecinas. Una zona desconocida devuelve None:
# mejor sin fecha que con una corrida un dia.
_TZ_OFFSETS = {
    "UTC": 0, "GMT": 0, "BST": 1, "CET": 1, "CEST": 2,
    "EST": -5, "EDT": -4, "CST": -6, "CDT": -5,
    "MST": -7, "MDT": -6, "PST": -8, "PDT": -7,
}
_MONTHS_EN = {
    m: i for i, m in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1
    )
}
_LISTING_DATE = re.compile(
    r"^(?P<mon>[A-Za-z]{3})\w* (?P<day>\d{1,2}), (?P<year>\d{4}) "
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*(?P<ampm>AM|PM)$",
    re.I,
)
_PLAIN_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$")


def mexico_city_iso(text: Optional[str]) -> Optional[str]:
    """Fecha de la fuente -> ISO en hora de Ciudad de Mexico, o None.

    Acepta los tres formatos vistos:
      "Sep 25, 2026 01:00AM BST"        (listado de subastas pasadas)
      "2021-08-26 17:00:00 CDT"         (JSON-LD Event.startDate)
      "2026-08-27T20:00:00-04:00 EDT"   (JSON-LD Offer.availabilityEnds)
    """
    if not text:
        return None
    match = re.match(r"^\s*(.*?)\s+([A-Z]{2,5})\s*$", text)
    if not match:
        return None
    body, zone = match.group(1), match.group(2)
    if zone not in _TZ_OFFSETS:
        return None
    tz = datetime.timezone(datetime.timedelta(hours=_TZ_OFFSETS[zone]))

    moment: Optional[datetime.datetime] = None
    if re.search(r"T\d{2}:\d{2}(:\d{2})?[+-]\d{2}:\d{2}$", body):
        moment = datetime.datetime.fromisoformat(body)
    elif plain := _PLAIN_DATE.match(body):
        y, mo, d, h, mi, s = (int(x or 0) for x in plain.groups())
        moment = datetime.datetime(y, mo, d, h, mi, s, tzinfo=tz)
    elif listing := _LISTING_DATE.match(body):
        month = _MONTHS_EN.get(listing.group("mon").lower()[:3])
        if month is None:
            return None
        hour = int(listing.group("hour")) % 12 + (12 if listing.group("ampm").upper() == "PM" else 0)
        moment = datetime.datetime(
            int(listing.group("year")), month, int(listing.group("day")),
            hour, int(listing.group("minute")), tzinfo=tz,
        )
    if moment is None:
        return None
    return moment.astimezone(MEXICO_CITY).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Que subastas son de arte
# ---------------------------------------------------------------------------

# Morton subasta de todo: de 803 subastas pasadas, 158 son flotillas de camiones
# y coches, 115 "Subastas de los Sabados" mezcladas, y el resto vinos, joyas,
# libros, antiguedades y mobiliario. Se quedan solo las de arte (57), con el
# mismo criterio que la curacion de Lefebre: arte con artista, no un catalogo
# generalista. Se decide por el titulo de la subasta, sobre texto plegado.
_ART_INCLUDE = re.compile(
    r"\barte (?:mexicano|moderno|contemporaneo|latinoamericano)"
    r"|\bartistas\b|obra grafica|pintura|escultura|grandes maestros|maestro impresor"
    r"|\bruptura\b"  # "Ecos de la Ruptura": la generacion de la Ruptura, pintura mexicana
    r"|graphic work|\bprints?\b|painting|sculpture|mexican art|latin american art"
    r"|modern and contemporary art"
)
# "Arte" en el titulo no basta: "Artes Decorativas | Explora el Arte Pop",
# "Arte y Vid" (arte con vinos), "Venta directa" (precio fijo, no remate) y
# los catalogos de antiguedades o libros que incluyen algun cuadro.
_ART_EXCLUDE = re.compile(
    r"venta directa|decorativ|libro|book|vino|wine|joy|jewel|antig|antique|mobiliario|furniture"
)


def is_art_auction(title: Optional[str]) -> bool:
    folded = _fold(title or "")
    return bool(_ART_INCLUDE.search(folded)) and not _ART_EXCLUDE.search(folded)


# ---------------------------------------------------------------------------
# Artista
# ---------------------------------------------------------------------------

# Entidades federativas: Morton escribe el lugar de nacimiento de un mexicano
# como "(Ciudad, Estado, anio - ...)" y solo pone el pais a los extranjeros
# ("(Argentina, 1928 - ...)", "(Pensilvania, EE. UU., 1928 - ...)").
_MEXICAN_STATES = {
    "aguascalientes", "baja california", "baja california sur", "campeche",
    "chiapas", "chihuahua", "coahuila", "coahuila de zaragoza", "colima",
    "durango", "guanajuato", "guerrero", "hidalgo", "jalisco", "michoacan",
    "michoacan de ocampo", "morelos", "nayarit", "nuevo leon", "oaxaca", "puebla",
    "queretaro", "quintana roo", "san luis potosi", "sinaloa", "sonora", "tabasco",
    "tamaulipas", "tlaxcala", "veracruz", "yucatan", "zacatecas",
}
_MEXICO_PLACES = _MEXICAN_STATES | {
    "mexico", "estado de mexico", "ciudad de mexico", "cdmx", "distrito federal",
    "df", "d.f.", "d. f.",
    # Capitales que la casa escribe solas, sin estado detras.
    "monterrey", "guadalajara", "oaxaca de juarez",
}

# Particulas que van en minuscula dentro de un nombre ("Fernando de Szyszlo").
# "le" NO: Julio Le Parc.
_PARTICLES = {"de", "del", "la", "las", "los", "y", "da", "di", "van", "von"}
_ROMAN = re.compile(r"^[IVXLC]{2,}\.?$")


def _is_upper_word(word: str) -> bool:
    return any(ch.isalpha() for ch in word) and not any(ch.islower() for ch in word)


def _keeps_dot(core: str) -> bool:
    """El punto de una inicial ("M. C. ESCHER"), de "JR." o de un tratamiento
    ("DR. LAKRA", "MR. BRAINWASH") no cierra el nombre. Sin los tratamientos,
    Dr. Lakra, Dr. Atl, Mr. Brainwash y Mr. Doodle se quedaban sin autor."""
    return (len(core) == 1 and core.isalpha()) or core in {"JR", "SR", "DR", "MR", "MRS", "MS"}


# Lo que la ficha pone delante del autor: "Diseñado por FRANCISCO TOLEDO",
# "Firmada HERARI" (la casa nombra al autor por su firma) o una coma suelta
# (", LUIS NISHIZAWA"). Las palabras van en (?i:) y la mayuscula del nombre no:
# "Firmado y fechado" no es un prefijo de autor.
_LEAD_PREFIX = re.compile(
    r"^[\s,;.:]*(?:(?i:dise[ñn]ad[oa]|dise[ñn]o)\s+(?i:por|de)\s+"
    r"|(?i:firmad[oa])\s+(?=[A-ZÁÉÍÓÚÑÜ]{2}))?"
)
# Carpetas colectivas: la descripcion empieza por el primero de los artistas, y
# atribuirle la carpeta entera seria inventar autoria. attribution_type las
# marca como anonimo.
_COLLECTIVE_LEAD = re.compile(r"^(varios (?:autores|artistas)|an[oó]nimo)\b", re.I)
_QUOTES_OPEN = ('"', "“", "«")
_BIO_FIELDS = ("artist_birth_year", "artist_death_year", "artist_country")


def _display_word(word: str, first: bool) -> str:
    if _ROMAN.match(word):
        return word
    lower = word.lower()
    if not first and lower in _PARTICLES:
        return lower
    # Capitaliza cada tramo de letras: "o'higgins" -> "O'Higgins".
    return re.sub(r"[^\W\d_]+", lambda m: m.group(0).capitalize(), lower)


def _display_name(words: list[str]) -> str:
    """"FERNANDO DE SZYSZLO" -> "Fernando de Szyszlo". La casa escribe al autor
    en MAYUSCULAS; sin esto el ranking de la app grita."""
    return " ".join(_display_word(w, i == 0) for i, w in enumerate(words))


def _year(text: str) -> Optional[int]:
    """Anio al final de un tramo de la biografia. Fuera de rango -> None: la casa
    tiene erratas ("1055" por 1955) y un anio falso es peor que ninguno."""
    match = re.search(r"(\d{3,4})\s*\??\s*$", text)
    if not match:
        return None
    year = int(match.group(1))
    return year if 1300 <= year <= 2030 else None


def _place(text: str) -> str:
    return re.sub(r"(?:,?\s*(?:ca\.?\s*)?\d{3,4}\s*\??)\s*$", "", text).strip(" ,")


def _country_from_place(place: str) -> Optional[str]:
    """Pais segun la convencion de la casa: un estado mexicano es Mexico; si no,
    el ultimo tramo tal cual lo escribe la casa ("EE. UU.", "Colombia").

    Va a artist_country, el texto libre de la casa: solo diagnostico. NUNCA
    escribe artist_country_birth, que sale del maestro de artistas.
    """
    if not place:
        return None
    last = place.split(",")[-1].strip(" ;")
    # el punto se ignora al comparar ("Guerrero.") pero se conserva al devolver
    # el texto de la casa: "EE. UU." lo lleva por derecho.
    folded = _fold(last.rstrip("."))
    # "(Siglo XX)" o un anio suelto no son un lugar: sin pais, no "Siglo XX".
    if not any(ch.isalpha() for ch in last) or "siglo" in folded:
        return None
    if folded in _MEXICO_PLACES:
        return "México"
    # "Chilpancingo Guerrero", "Victoria de Durango": acaba en un estado. Solo
    # estados: "Nuevo Mexico" / "New Mexico" acaban en "mexico" y son EE. UU.
    if any(folded.endswith(" " + state) for state in _MEXICAN_STATES):
        return "México"
    return last


# Guion entre nacimiento y muerte: con espacio a algun lado ("1940 - Oaxaca") o
# pegado detras de un anio ("1928-2014", "1932-Ciudad de México"). Un guion
# pegado entre letras es parte de un topónimo ("Saint-Denis") y no parte.
_BIO_DASH = re.compile(r"\s+[-–]\s*|\s*[-–]\s+|(?<=\d)[-–](?=\w)")


def _biography(text: str) -> dict:
    """"(Juchitán, Oaxaca, 1940 - Oaxaca, Oaxaca, 2019)" -> anios y pais."""
    parts = _BIO_DASH.split(text.strip()[1:-1], maxsplit=1)
    birth = parts[0]
    death = parts[1] if len(parts) > 1 else ""
    out: dict = {}
    birth_year = _year(birth)
    if birth_year:
        out["artist_birth_year"] = birth_year
    death_year = _year(death) if death else None
    if death_year:
        out["artist_death_year"] = death_year
    country = _country_from_place(_place(birth))
    if country:
        out["artist_country"] = country
    return out


def artist_from_text(text: Optional[str]) -> dict:
    """Autor desde el titulo o la descripcion del lote. {} si no hay autor claro.

    La convencion de la casa es el autor en MAYUSCULAS al principio, cerrado por
    punto (desde 2024) o coma (antes), a veces con la biografia entre parentesis
    detras. Una entrada que empieza en minusculas ("Lote de tres grabados") no
    es un autor y no se inventa uno.
    """
    if not text:
        return {}
    text = _LEAD_PREFIX.sub("", " ".join(text.split()), count=1)
    # Separador pegado ("JAVIER MARÍN,Torso", "PENHOS,31/August", '"SEBASTIAN".Sin'):
    # sin el espacio el token entero tiene minusculas y el nombre se cortaba
    # en "Javier". El punto solo antes de letra, para no partir "40.5".
    text = re.sub(r"([,;])(?=\S)", r"\1 ", text)
    text = re.sub(r"\.(?=[^\W\d_])", ". ", text)
    collective = _COLLECTIVE_LEAD.match(text)
    if collective:
        return {"artist_name": _display_name(collective.group(1).split()), "artist_raw": collective.group(1)}
    words: list[str] = []
    consumed = 0
    in_alias = False
    for token in text.split(" "):
        # Apodo entre comillas: se salta entero y el nombre sigue detras
        # ('GEORGINA "GOGY" FARÍAS' -> Georgina Farías; 'GERARDO MURILLO "DR. ATL"'
        # -> Gerardo Murillo). Cortar en la comilla dejaba "Georgina" de artista.
        if in_alias or token.startswith(_QUOTES_OPEN):
            consumed += len(token) + 1
            closed = re.search(r"[\"”»][.,;:]?$", token[1:] if not in_alias else token)
            in_alias = not closed
            if closed and token.endswith((",", ";", ":", ".")):
                break
            continue
        if token.startswith("("):
            break
        core = token.rstrip(".,;:")
        if not core or not _is_upper_word(core):
            if not core:  # "FRIEDEBERG ." / "GOERITZ ,": el separador suelto cierra
                consumed += len(token) + 1
            break
        consumed += len(token) + 1
        words.append(core + ("." if token.endswith(".") and _keeps_dot(core) else ""))
        if token.endswith((",", ";", ":")):
            break
        if token.endswith(".") and not _keeps_dot(core):
            break

    letters = sum(ch.isalpha() for w in words for ch in w)
    if letters < 3:
        return {}

    lead = " ".join(words)
    out: dict = {"artist_name": _display_name(words), "artist_raw": lead}
    rest = text[consumed:].lstrip()
    if rest.startswith("("):
        depth = 0
        for idx, ch in enumerate(rest):
            depth += ch == "("
            depth -= ch == ")"
            if depth == 0:
                bio = rest[: idx + 1]
                out.update(_biography(bio))
                out["artist_raw"] = f"{lead} {bio}"
                break
    return out


# ---------------------------------------------------------------------------
# JSON-LD
# ---------------------------------------------------------------------------

def _jsonld(page: Any, kind: str) -> dict:
    """Primer bloque JSON-LD de tipo `kind` ("Event" en la subasta, "Product" en
    el lote). strict=False: algunas descripciones traen saltos de linea crudos."""
    for node in _selector(page).css('script[type="application/ld+json"]'):
        try:
            data = json.loads(node.text or "", strict=False)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("@type") == kind:
            return data
    return {}


# ---------------------------------------------------------------------------
# Funciones exigidas por House.REQUIRED_PARSER_FUNCS
# ---------------------------------------------------------------------------

def _auction_id_from_url(auction_url: str) -> str:
    """.../auctions/morton-subastas/subasta-de-arte-latinoamericano-17078[/catalog?...] -> "17078".

    El id numerico y no el slug: los titulos se repiten ("Subasta de Arte
    Moderno y Contemporaneo" hay 15) y el runner nombra el fichero con esto.
    """
    match = re.search(r"/auctions/[^/]+/[^/?#]*?-(\d+)(?=[/?#]|$)", auction_url or "")
    if match:
        return match.group(1)
    return (auction_url or "").rstrip("/").split("/")[-1].split("?")[0]


def _event_url(url: str) -> str:
    return re.sub(r"/catalog.*$", "", url.split("?")[0]).rstrip("/")


def get_auction_title_from_page(page: Any) -> Optional[str]:
    name = _jsonld(page, "Event").get("name")
    return fix_mojibake(str(name)).strip() if name else None


def get_auction_start_date_from_page(page: Any) -> Optional[str]:
    """Hook opcional que default_build_meta llama via hasattr."""
    return mexico_city_iso(_jsonld(page, "Event").get("startDate"))


def parse_historic_page(page: Any) -> list[AuctionMeta]:
    """Una pagina de /en/auctions/past -> una AuctionMeta por subasta (de arte o no:
    el filtro es de run_historic, para que el listado se pueda auditar entero)."""
    auctions: list[AuctionMeta] = []
    seen: set[str] = set()
    for item in _selector(page).css("li[id^='st-']"):
        link = item.css(".list-top h1 a")
        if not link:
            continue
        url = link[0].attrib.get("href") or ""
        auction_id = _auction_id_from_url(url)
        if not auction_id or auction_id in seen:
            continue
        seen.add(auction_id)
        start = None
        for span in item.css(".list-top span"):
            label = (span.text or "").strip()
            if label.startswith("Start:"):
                start = mexico_city_iso(label[len("Start:"):].strip())
                break
        auctions.append(
            AuctionMeta(
                auction_id=auction_id,
                auction_title=fix_mojibake(link[0].text.strip()) or f"morton-{auction_id}",
                auction_start_date=start,
                auction_url=url,
                auction_house_name=HOUSE_NAME,
            )
        )
    return auctions


def get_page_urls(first_page: Any, base_auction_url: str) -> list[str]:
    """Todas las paginas del catalogo a 120 lotes, derivadas del total.

    Una pagina fuera de rango NO viene vacia: Bidsquare devuelve la ultima otra
    vez. Por eso el numero sale de "N Results" y no de paginar hasta vaciar.
    """
    match = re.search(r"(\d[\d,]*)\s+Results", _page_html(first_page))
    if not match:
        return []
    total = int(match.group(1).replace(",", ""))
    base = _event_url(base_auction_url)
    pages = math.ceil(total / LOTS_PER_PAGE)
    return [f"{base}/catalog?limit={LOTS_PER_PAGE}&page={n}" for n in range(1, pages + 1)]


def _exchange(node_list: Any) -> dict:
    """Atributo data-exchange (JSON con los importes en MXN) del primer nodo."""
    if not node_list:
        return {}
    try:
        return json.loads(node_list[0].attrib.get("data-exchange") or "{}")
    except ValueError:
        return {}


def parse_auction_page(page: Any, meta: Optional[AuctionMeta] = None) -> list[dict]:
    """Un preview por tarjeta de lote del catalogo.

    Con precio visible (2024+) ya trae estado e importe. Detras de login (antes
    de 2024) el estado queda en None, no "no vendido": la ficha del lote lo
    completa. Los importes salen de data-exchange, no del texto "MXN$18,000".
    """
    auction_id = _auction_id_from_url(meta.auction_url) if meta else None
    previews: list[dict] = []
    for card in _selector(page).css("div.gtm-visible_item[data-item_id]"):
        if auction_id and card.attrib.get("data-event_id") != auction_id:
            continue
        link = card.css(".lot_title a")
        if not link:
            continue
        raw_title = fix_mojibake(link[0].get_all_text().strip())
        title = _spanish_half(raw_title)

        estimate = _exchange(card.css(".estimate_amount"))
        label_nodes = card.css("span[id^='lbl_']")
        label = (label_nodes[0].text or "").strip().lower() if label_nodes else ""
        status, price = None, None
        if label.startswith("sold"):
            status = "VENDIDO"
            price = _money(_exchange(card.css(".converted_curr")).get("amount"))
        elif label == "unsold":
            status = "NO VENDIDO"

        image = next(
            (img.attrib.get("src") for img in card.css(".catalog_img img")
             if "/item/" in (img.attrib.get("src") or "")),
            None,
        )
        num_nodes = card.css(".lot_Num")
        preview = {
            "lot_url": link[0].attrib.get("href"),
            "lot_number": _lot_number(num_nodes[0].text if num_nodes else None),
            "lot_title": title,
            "price_estimate_min": _money(estimate.get("low_est")),
            "price_estimate_max": _money(estimate.get("high_est")),
            "price_sold": price,
            "status": status,
            "image_url": image,
            "category": None,
        }
        preview.update(artist_from_text(title))
        previews.append(preview)
    return previews


def parse_lot_page(page: Any, meta: Optional[AuctionMeta] = None) -> dict:
    """Ficha del lote -> precio y estado reales (JSON-LD), descripcion y biografia.

    Es la unica fuente de precio para las subastas anteriores a 2024. El nombre
    sale del titulo, que lo cierra con punto o coma; la biografia, de las dos
    primeras lineas de la descripcion ("JULIO LE PARC" / "(Argentina, 1928 -
    ..."). En la descripcion el nombre va solo en su linea, sin separador, asi
    que leerlo de ahi pegaria un titulo en mayusculas al nombre.
    """
    product = _jsonld(page, "Product")
    if not product:
        return {}
    title = _spanish_half(fix_mojibake(html.unescape(str(product.get("name") or ""))).strip())
    description = _clean_description(product.get("description"))

    offers = product.get("offers") or {}
    availability = str(offers.get("availability") or "").rstrip("/").split("/")[-1]
    status, price = None, None
    if availability == "SoldOut":
        status, price = "VENDIDO", _money(offers.get("price"))
    elif availability == "Discontinued":
        # offers.price aqui es la SALIDA, no una venta: ver docstring del modulo
        status = "NO VENDIDO"

    lot_number = re.search(r">\s*Lot\s+(\d+)[A-Z]?\s*<", _page_html(page))
    detail: dict = {
        "lot_number": int(lot_number.group(1)) if lot_number else None,
        "lot_title": title,
        "description": description,
        "price_sold": price,
        "status": status,
        "image_url": product.get("image"),
    }
    detail["lot_title"] = lot_title_for(title, description)
    detail.update(artist_for_lot(detail["lot_title"], description))
    return detail


def lot_title_for(title: Optional[str], description: Optional[str]) -> Optional[str]:
    """Titulo del lote; rehecho desde la descripcion si no nombra a ningun autor.

    Morton recicla registros: en la subasta 20912 (Arte Latinoamericano,
    2025-11) 51 lotes heredaron el titulo de un lote de flotilla ("Camioneta
    Chevrolet Tornado 2009", hasta en la URL), mientras descripcion, precio y
    estimacion son de la obra (Beloff, Merida, Toledo...). Un titulo sin autor
    con una descripcion que si lo tiene no describe la obra: se rehace con
    nombre, titulo, firma y tecnica, sin la biografia.
    """
    if not description or artist_from_text(title):
        return title
    lines = [line for line in description.splitlines() if line.strip()]
    if not lines or not artist_from_text(" ".join(lines[:2])):
        return title
    name = re.sub(r"\s*\([^()]*\)", "", lines[0]).strip()  # biografia pegada al nombre
    rest = [line for line in lines[1:] if not line.startswith("(")]
    return ". ".join(part.rstrip(". ") for part in [name] + rest[:3])


def artist_for_lot(title: Optional[str], description: Optional[str]) -> dict:
    """Autor de un lote a partir de su titulo y su descripcion ya limpios.

    Funcion aparte de parse_lot_page para poder recalcular el autor sobre lotes
    ya descargados (title y description se guardan en el JSONL) sin volver a
    pedir 12.838 fichas cuando cambia una regla.
    """
    artist = artist_from_text(title)
    from_description = (
        artist_from_text(" ".join(description.splitlines()[:2])) if description else {}
    )
    if not artist or not from_description:
        return artist or from_description
    name = _fold(artist["artist_name"])
    same_person = _fold(from_description["artist_name"]) == name or (
        # seudonimo del titulo dentro de la primera linea: 'GERARDO MURILLO "DR. ATL"'
        name in _fold(description.splitlines()[0])
    )
    bio = {k: v for k, v in from_description.items() if k in _BIO_FIELDS}
    if same_person and bio:
        # la descripcion AÑADE anios, pais y texto crudo; nunca borra los que ya
        # traia el titulo (2021: titulo con biografia, descripcion en ingles sin
        # ella). El nombre sigue siendo el del titulo.
        return {**artist, **bio, "artist_raw": from_description["artist_raw"]}
    return artist
