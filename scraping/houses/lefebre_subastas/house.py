"""Definicion de la casa Lefebre Subastas para el framework scraping/common/.

Lefebre es la unica casa con DOS fuentes conviviendo en el mismo output/:

  - from_excel.py  -> 11 subastas (18-26, Barranquilla, prueba), 1.037 lotes,
                      curadas a mano en 2024. Se conservan tal cual.
  - este scraper   -> el resto, desde el API de Auction Mobility.

Bronze copia *.jsonl del directorio sin importar quien los escribio, asi que las
dos fuentes conviven sin que el pipeline note la diferencia.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

import requests

from scraping.common.house import House
from scraping.houses.lefebre_subastas import parsers

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = ROOT / "scraping" / "houses" / "lefebre_subastas" / "output"

# Tope duro de paginas por subasta. La mayor vista tiene 255 lotes (3 paginas de
# 100); 40 deja margen de sobra y evita un bucle infinito si el API empezara a
# devolver un next_page que se apunta a si mismo.
MAX_PAGES = 40

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    # El proxy /ajax/ del sitio responde JSON con esta cabecera; sin ella puede
    # devolver el HTML de la SPA.
    "X-Requested-With": "XMLHttpRequest",
}


def lefebre_fetcher(url: str, timeout_seconds: float) -> Any:
    """Fetcher propio: aqui la fuente es JSON, no HTML.

    No se usa default_fetcher (scrapling) porque no hay DOM que consultar, ni
    stealthy_fetcher porque no hace falta navegador: el proxy /ajax/ del sitio
    sirve el dato sin auth y sin render. Devuelve dict cuando la respuesta es
    JSON y str cuando es HTML (el historico), y los parsers aceptan las dos.

    TRADUCCION CLAVE: el engine arranca con `fetch(auction_url)`, y esa URL es
    la de la ficha publica (/auctions/4-XXXX/slug), que es la SPA de Angular y
    no trae ni un lote. Aqui se reescribe al catalogo JSON antes de pedirla, de
    modo que el `first_page` que recibe discover() ya es la pagina 1 del
    catalogo. Sin esto, parse_auction_page revienta al intentar leer HTML como
    JSON y ademas default_build_meta se quedaria sin titulo ni fecha.
    """
    code = parsers.auction_code_from_url(url)
    if code and "/ajax/" not in url:
        url = parsers.lots_url(code)

    response = requests.get(url, headers=_HEADERS, timeout=timeout_seconds)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "")
    if "json" in content_type.lower():
        return response.json()
    text = response.text
    # El proxy /ajax/ a veces devuelve JSON con Content-Type text/plain.
    stripped = text.lstrip()
    if stripped[:1] in "{[":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


def paginated_json_discovery(
    first_page: Any,
    meta: Any,
    *,
    fetch,
    post=None,
    get_session=None,
    delay: float = 0.0,
    max_lots: Optional[int] = None,
    max_retries: int = 2,
    timeout_seconds: float = 30.0,
    log=None,
) -> list[dict]:
    """Recorre el catalogo siguiendo query_info.next_page.

    No encaja ninguna de las dos estrategias de common/discovery.py:
    html_pagination_discovery espera URLs de pagina en el DOM, y
    ajax_infinite_scroll_discovery espera un POST con token de formulario. Aqui
    la paginacion es un cursor (n=, o=) dentro del propio JSON.

    El engine vuelve a deduplicar por lot_url, pero se deduplica tambien aqui
    para poder cortar por max_lots con un conteo real.
    """
    auction_url = getattr(meta, "auction_url", "") or ""
    code = parsers.auction_code_from_url(auction_url)

    previews: list[dict] = []
    seen: set[str] = set()
    page: Any = first_page

    for page_number in range(1, MAX_PAGES + 1):
        payload = parsers._payload(page)
        nuevos = 0
        for preview in parsers.parse_auction_page(page, meta):
            url = preview.get("lot_url")
            if not url or url in seen:
                continue
            seen.add(url)
            previews.append(preview)
            nuevos += 1
            if max_lots is not None and len(previews) >= max_lots:
                return previews[:max_lots]

        if log:
            log("catalog_page", auction_id=getattr(meta, "auction_id", None),
                page=page_number, new=nuevos, total=len(previews))

        raw_next = (payload.get("query_info") or {}).get("next_page")
        siguiente = parsers.next_page_url(raw_next, code) if code else None
        # Sin next_page se acabo. Si ademas una pagina no aporta nada nuevo,
        # se corta igualmente para no quedarse girando sobre el mismo cursor.
        if not siguiente or nuevos == 0:
            break

        if delay:
            time.sleep(delay)
        # OJO: el `fetch` que inyecta el engine toma SOLO la url (ya lleva
        # dentro el timeout y los reintentos). Pasarle timeout_seconds revienta
        # con TypeError, y solo se nota en subastas de mas de una pagina.
        page = fetch(siguiente)

    return previews


HOUSE = House(
    slug="lefebre_subastas",
    name=parsers.HOUSE_NAME,
    currency=parsers.CURRENCY,  # COP, explicito: el modelo asume COP pero no hay que confiar en el default
    base_url=parsers.BASE_URL,
    historic_url=parsers.HISTORIC_URL,
    output_dir=DEFAULT_OUTPUT_DIR,
    parsers=parsers,
    discover=paginated_json_discovery,
    fetcher=lefebre_fetcher,
    # API JSON: ni render ni navegador, asi que se puede ir mas rapido que
    # Zorrilla (0.5/120s) y no hace falta el timeout largo de Playwright.
    default_delay=0.4,
    historic_delay=0.8,
    default_retries=2,
    default_timeout=30.0,
)
