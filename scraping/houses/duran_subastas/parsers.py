"""
Parser utilities for Duran Arte y Subastas.

The site renders parts of listing pages dynamically, so these parsers favor
resilient regex extraction from raw HTML with multi-pattern fallbacks.
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Any
from urllib.parse import urljoin

from scraping.common.models import AuctionMeta

BASE_URL = "https://www.duran-subastas.com"
TARGET_CATEGORIES = {"obra_grafica", "pintura"}

_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
_SUBASTA_RE = re.compile(r"/es/subasta/[^\"'\s<>]+", re.IGNORECASE)
_LOTE_RE = re.compile(r"/es/(?:lote|articulo|subasta-lote)/[^\"'\s<>]+", re.IGNORECASE)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TAG_CONTENT_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?P<name>[^"\']+)["\'][^>]+content=["\'](?P<content>[^"\']*)["\']',
    re.IGNORECASE,
)
_PRICE_RE = re.compile(r"(?:€\s*([\d\.\,]+)|([\d\.\,]+)\s*€|EUR\s*([\d\.\,]+)|([\d\.\,]+)\s*EUR)", re.IGNORECASE)
_LOT_NUM_RE = re.compile(r"(?:lote|lot)\s*:?\s*#?\s*(\d+)", re.IGNORECASE)
_URL_LOT_NUM_RE = re.compile(r"/(\d+)-(\d+)(?:\?.*)?$")
_AJAX_URL_RE = re.compile(r'var\s+url_lots\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_INFINITE_FORM_RE = re.compile(
    r'<form[^>]+id=["\']infiniteScrollForm["\'][^>]*>(.*?)</form>',
    re.IGNORECASE | re.DOTALL,
)
_INPUT_RE = re.compile(r'<input[^>]+name=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE)
_CATEGORY_BADGE_RE = re.compile(
    r'<div[^>]*class=["\']cat["\'][^>]*>\s*Categorias\s*</div>.*?<span[^>]*class=["\']badge["\'][^>]*>(.*?)</span>',
    re.IGNORECASE | re.DOTALL,
)
_LOT_CARD_RE = re.compile(r'<div[^>]*class=["\'][^"\']*square[^"\']*["\'][^>]*>.*?</div>\s*</div>', re.IGNORECASE | re.DOTALL)
_A_TAG_RE = re.compile(r"<a[^>]+>", re.IGNORECASE)
_IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")
_DETAIL_ROW_RE = re.compile(
    r'<div[^>]*class=["\'][^"\']*col-xs-4[^"\']*pb-2[^"\']*["\'][^>]*>(?P<label>.*?)</div>\s*'
    r'<div[^>]*class=["\'][^"\']*col-xs-8[^"\']*pb-2[^"\']*["\'][^>]*>(?P<value>.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)
_DESCRIPTION_BLOCK_RE = re.compile(
    r"Lote\s*:\s*\d+\s*(?P<body>.+?)\s*Bibliograf[ií]a\s*:",
    re.IGNORECASE | re.DOTALL,
)
_BREADCRUMB_AUCTION_RE = re.compile(
    r'<a[^>]+href=["\'](?P<href>[^"\']*/es/subasta/[^"\']+)["\'][^>]*>\s*'
    r"<span[^>]*itemprop=[\"']name[\"'][^>]*>(?P<title>.*?)</span>",
    re.IGNORECASE | re.DOTALL,
)
_REFERENCIA_FICHA_RE = re.compile(
    r'<div[^>]*class=["\'][^"\']*referencia-ficha[^"\']*["\'][^>]*>.*?</div>',
    re.IGNORECASE | re.DOTALL,
)

_SPANISH_MONTHS = {
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
}


def _page_html(page: Any) -> str:
    if isinstance(page, str):
        return page
    for attr in ("html_content", "body", "text"):
        value = getattr(page, attr, None)
        if value:
            return str(value)
    return str(page)


def _page_url(page: Any) -> str | None:
    if isinstance(page, str):
        return None
    value = getattr(page, "url", None)
    return str(value) if value else None


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(html.unescape(value).replace("\xa0", " ").split()).strip()


def _strip_tags(raw_html: str) -> str:
    return _clean_text(re.sub(r"<[^>]+>", " ", raw_html))


def _normalize_for_match(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text).strip().lower()


def normalize_category(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _normalize_for_match(value)
    if "obra grafica" in normalized:
        return "obra_grafica"
    if "pintura" in normalized:
        return "pintura"
    return None


def _abs_url(url: str) -> str:
    return urljoin(BASE_URL, url)


def _extract_meta_map(raw_html: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for match in _TAG_CONTENT_RE.finditer(raw_html):
        key = _clean_text(match.group("name")).lower()
        val = _clean_text(match.group("content"))
        if key and val:
            meta[key] = val
    return meta


def _meta_value(raw_html: str, key: str) -> str | None:
    # More tolerant fallback when malformed meta attributes break strict parsing.
    key_pat = re.escape(key)
    patterns = [
        re.compile(
            rf'<meta[^>]+(?:property|name)\s*=\s*" {key_pat} "[^>]+content\s*=\s*"([^"]*)"',
            re.IGNORECASE | re.VERBOSE | re.DOTALL,
        ),
        re.compile(
            rf"<meta[^>]+(?:property|name)\s*=\s*' {key_pat} '[^>]+content\s*=\s*\"([^\"]*)\"",
            re.IGNORECASE | re.VERBOSE | re.DOTALL,
        ),
        re.compile(
            rf'<meta[^>]+(?:property|name)\s*=\s*" {key_pat} "[^>]+content\s*=\s*\'([^\']*)\'',
            re.IGNORECASE | re.VERBOSE | re.DOTALL,
        ),
    ]
    for pattern in patterns:
        match = pattern.search(raw_html)
        if match:
            value = _clean_text(match.group(1))
            if value:
                return value
    return None


def _extract_title(raw_html: str) -> str:
    match = _TITLE_RE.search(raw_html)
    return _strip_tags(match.group(1)) if match else ""


def _auction_id_from_url(url: str) -> str:
    return (url.rstrip("/").split("/")[-1] or url).split("?")[0]


def _extract_subasta_urls(raw_html: str) -> list[str]:
    urls = {_abs_url(m.group(0)) for m in _SUBASTA_RE.finditer(raw_html)}
    return sorted(url for url in urls if "/es/subasta/" in url and ("_001" in url or "-001" in url))


def _extract_lot_urls(raw_html: str) -> list[str]:
    urls = {_abs_url(m.group(0)) for m in _LOTE_RE.finditer(raw_html)}
    return sorted(urls)


def _extract_input_value(input_tag: str) -> str:
    value_match = re.search(r'value=["\']([^"\']*)["\']', input_tag, flags=re.IGNORECASE)
    return html.unescape(value_match.group(1)) if value_match else ""


def extract_infinite_scroll_config(page: Any) -> tuple[str | None, dict[str, str]]:
    raw_html = _page_html(page)
    ajax_match = _AJAX_URL_RE.search(raw_html)
    ajax_url = _abs_url(ajax_match.group(1)) if ajax_match else None

    payload: dict[str, str] = {}
    form_match = _INFINITE_FORM_RE.search(raw_html)
    if form_match:
        form_html = form_match.group(1)
        for input_match in _INPUT_RE.finditer(form_html):
            input_tag = input_match.group(0)
            payload[input_match.group(1)] = _extract_input_value(input_tag)

    return ajax_url, payload


def category_from_filter_payload(payload: dict[str, str] | None) -> str | None:
    if not payload:
        return None
    # Known category IDs currently used by Duran's listing filters.
    category_id = (payload.get("category") or "").strip()
    if category_id == "614":
        return "obra_grafica"
    if category_id == "23":
        return "pintura"
    return None


def parse_historic_page(page: Any) -> list[AuctionMeta]:
    raw_html = _page_html(page)
    auction_urls = _extract_subasta_urls(raw_html)
    auctions: list[AuctionMeta] = []
    for auction_url in auction_urls:
        auction_id = _auction_id_from_url(auction_url)
        auctions.append(
            AuctionMeta(
                auction_id=auction_id,
                auction_title=auction_id.replace("-", " "),
                auction_url=auction_url,
                auction_house_name="Duran Arte y Subastas",
            )
        )
    return auctions


def parse_auction_page(page: Any, auction_meta: AuctionMeta | None = None) -> list[dict]:
    raw_html = _page_html(page)
    previews: list[dict] = []
    lot_urls = _extract_lot_urls(raw_html)
    if lot_urls:
        for lot_url in lot_urls:
            previews.append(
                {
                    "lot_url": lot_url,
                    "lot_number": lot_number_from_text(lot_url),
                    "lot_title": None,
                    "lot_year": None,
                    "price_estimate_min": None,
                    "price_estimate_max": None,
                    "price_sold": None,
                    "status": None,
                    "thumbnail_url": None,
                    "category": category_from_text(lot_url),
                }
            )
        return previews

    seen_urls: set[str] = set()
    for card_match in _LOT_CARD_RE.finditer(raw_html):
        card_html = card_match.group(0)
        href_match = re.search(
            r'href=["\']([^"\']*?/es/(?:subasta-lote|lote|articulo)/[^"\']+)["\']',
            card_html,
            flags=re.IGNORECASE,
        )
        if not href_match:
            continue
        lot_url = _abs_url(href_match.group(1))
        if lot_url in seen_urls:
            continue
        seen_urls.add(lot_url)
        lot_title = None
        a_tag_match = _A_TAG_RE.search(card_html)
        if a_tag_match:
            title_match = re.search(r'title=["\']([^"\']+)["\']', a_tag_match.group(0), flags=re.IGNORECASE)
            if title_match:
                lot_title = _clean_text(title_match.group(1)) or None

        thumbnail_url = None
        img_match = _IMG_SRC_RE.search(card_html)
        if img_match:
            thumbnail_url = _abs_url(img_match.group(1))
        estimate_min, estimate_max = _parse_prices(card_html)

        previews.append(
            {
                "lot_url": lot_url,
                "lot_number": lot_number_from_text(card_html) or lot_number_from_text(lot_url),
                "lot_title": lot_title,
                "lot_year": None,
                "price_estimate_min": estimate_min,
                "price_estimate_max": estimate_max,
                "price_sold": None,
                "status": _status_from_text(card_html),
                "thumbnail_url": thumbnail_url,
                "category": category_from_text(card_html) or category_from_text(lot_title) or category_from_text(lot_url),
            }
        )
    return previews


def category_from_text(value: str | None) -> str | None:
    return normalize_category(value)


def lot_number_from_text(value: str | None) -> int | None:
    if not value:
        return None
    m = _LOT_NUM_RE.search(value)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    if value:
        tail_match = _URL_LOT_NUM_RE.search(value)
        if tail_match:
            try:
                return int(tail_match.group(2))
            except ValueError:
                return None
    return None


def _extract_badge_category(raw_html: str) -> str | None:
    match = _CATEGORY_BADGE_RE.search(raw_html)
    if not match:
        return None
    badge_text = _strip_tags(match.group(1))
    return normalize_category(badge_text)


def _parse_prices(raw_html: str) -> tuple[int | None, int | None]:
    prices = []
    for match in _PRICE_RE.finditer(raw_html):
        amount = next((g for g in match.groups() if g), None)
        if not amount:
            continue
        value = amount.replace(".", "").replace(",", ".")
        try:
            prices.append(float(value))
        except ValueError:
            continue
    if not prices:
        return None, None
    if len(prices) == 1:
        return int(prices[0]), None
    return int(min(prices)), int(max(prices))


def _to_eur_int(amount_text: str | None) -> int | None:
    if not amount_text:
        return None
    value = amount_text.replace(".", "").replace(",", ".").strip()
    try:
        return int(float(value))
    except ValueError:
        return None


def _extract_price_by_label(raw_html: str, label: str) -> int | None:
    plain = _strip_tags(raw_html)
    pattern = re.compile(rf"{re.escape(label)}\s*([\d\.\,]+)\s*(?:€|EUR)", re.IGNORECASE)
    match = pattern.search(plain)
    if not match:
        return None
    return _to_eur_int(match.group(1))


def _status_from_text(raw_html: str) -> str | None:
    text = _normalize_for_match(_strip_tags(raw_html))
    if "no vendido" in text or "desierto" in text:
        return "NO VENDIDO"
    if "vendido por" in text or "adjudicado" in text or "remate" in text:
        return "VENDIDO"
    if "en curso" in text or "presencial" in text or "online" in text:
        return "EN CURSO"
    return None


def _infer_artist_from_title(title: str | None) -> tuple[str | None, str | None]:
    if not title:
        return None, None
    parts = [p.strip() for p in title.split(".", 1)]
    if len(parts) < 2 or not parts[0]:
        return None, None
    artist = parts[0]
    if len(artist) > 80:
        return None, None
    return artist, artist


def _infer_year(*values: str | None) -> str | None:
    for value in values:
        if not value:
            continue
        m = _YEAR_RE.search(value)
        if m:
            return m.group(1)
    return None


def _extract_spanish_month_year(value: str | None) -> str | None:
    if not value:
        return None
    text = _normalize_for_match(value)
    m = re.search(r"\b([a-z]+)\s+(20\d{2}|19\d{2})\b", text)
    if not m:
        return None
    month = m.group(1)
    if month not in _SPANISH_MONTHS:
        return None
    return f"{month.capitalize()} {m.group(2)}"


def _extract_breadcrumb_auction(raw_html: str) -> tuple[str | None, str | None, str | None]:
    match = _BREADCRUMB_AUCTION_RE.search(raw_html)
    if not match:
        return None, None, None
    auction_url = _abs_url(match.group("href"))
    auction_title = _clean_text(_strip_tags(match.group("title"))) or None
    auction_start_date = _extract_spanish_month_year(auction_title)
    return auction_url, auction_title, auction_start_date


def get_auction_start_date_from_page(page: Any) -> str | None:
    raw_html = _page_html(page)
    _, breadcrumb_title, breadcrumb_start_date = _extract_breadcrumb_auction(raw_html)
    if breadcrumb_start_date:
        return breadcrumb_start_date
    page_title = _extract_title(raw_html)
    if page_title:
        return _extract_spanish_month_year(page_title)
    if breadcrumb_title:
        return _extract_spanish_month_year(breadcrumb_title)
    return None


def _extract_lot_number_from_reference(raw_html: str) -> int | None:
    match = _REFERENCIA_FICHA_RE.search(raw_html)
    if not match:
        return None
    return lot_number_from_text(_strip_tags(match.group(0)))


def _parse_artist_years(artist_raw: str | None) -> tuple[int | None, int | None]:
    if not artist_raw:
        return None, None
    match = re.search(r"\((\d{4})\s*-\s*(\d{4}|\?)\)", artist_raw)
    if not match:
        return None, None
    birth = int(match.group(1))
    death_text = match.group(2)
    death = int(death_text) if death_text.isdigit() else None
    return birth, death


def _extract_detail_fields(raw_html: str) -> dict[str, str]:
    details: dict[str, str] = {}
    for match in _DETAIL_ROW_RE.finditer(raw_html):
        label = _normalize_for_match(_strip_tags(match.group("label")))
        value = _clean_text(_strip_tags(match.group("value")))
        if label and value:
            details[label] = value
    return details


def _extract_main_description(raw_html: str) -> str | None:
    plain = _strip_tags(raw_html)
    match = _DESCRIPTION_BLOCK_RE.search(plain)
    if not match:
        return None
    body = _clean_text(match.group("body"))
    return body or None


def parse_lot_page(page: Any, auction_meta: AuctionMeta | None = None) -> dict:
    raw_html = _page_html(page)
    current_url = _page_url(page)
    meta = _extract_meta_map(raw_html)
    strict_og_title = meta.get("og:title")
    strict_og_description = meta.get("og:description")
    title_candidates = [
        strict_og_title,
        _meta_value(raw_html, "og:title"),
        _extract_title(raw_html),
    ]
    title = max((t for t in title_candidates if t), key=lambda v: len(_clean_text(v)), default="")
    description = (
        strict_og_description
        or _meta_value(raw_html, "og:description")
        or meta.get("description")
        or _meta_value(raw_html, "description")
        or ""
    )
    image_url = meta.get("og:image")
    price_start = _extract_price_by_label(raw_html, "Precio salida")
    price_sold = _extract_price_by_label(raw_html, "Vendido por")
    estimate_min, estimate_max = _parse_prices(raw_html)
    if price_start is not None:
        estimate_min, estimate_max = price_start, price_start
    category = (
        normalize_category(meta.get("article:section"))
        or _extract_badge_category(raw_html)
        or category_from_text(title)
        or category_from_text(description)
    )
    artist_name, artist_raw = _infer_artist_from_title(title)
    lot_year = _infer_year(title, description)
    details = _extract_detail_fields(raw_html)
    detail_title = details.get("titulo")
    if detail_title:
        title = detail_title
    main_description = _extract_main_description(raw_html)
    if (not description or len(_clean_text(description)) < 20) and main_description:
        description = main_description
    artist_from_detail = details.get("autor")
    if artist_from_detail and not artist_raw:
        artist_raw = artist_from_detail
    if artist_from_detail and not artist_name:
        artist_name = artist_from_detail.split("(")[0].strip()
    if not lot_year:
        lot_year = _infer_year(details.get("titulo"), artist_from_detail)
    artist_birth_year, artist_death_year = _parse_artist_years(artist_from_detail or artist_raw)
    lot_number = (
        _extract_lot_number_from_reference(raw_html)
        or lot_number_from_text(title)
        or lot_number_from_text(description)
        or lot_number_from_text(current_url)
    )
    provenance = details.get("procedencia")
    dimensions = details.get("medidas")
    medium = details.get("tecnica pintura") or details.get("tecnica")
    auction_url_from_breadcrumb, auction_title_from_breadcrumb, auction_start_from_breadcrumb = _extract_breadcrumb_auction(raw_html)

    result = {
        "lot_url": current_url,
        "lot_title": _clean_text(title) or None,
        "description": _clean_text(description) or None,
        "image_url": image_url,
        "price_estimate_min": estimate_min,
        "price_estimate_max": estimate_max,
        "price_sold": price_sold,
        "lot_number": lot_number,
        "lot_year": lot_year,
        "category": category,
        "currency": "EUR",
        "artist_name": artist_name,
        "artist_birth_year": artist_birth_year,
        "artist_death_year": artist_death_year,
        "artist_raw": artist_raw,
        "medium": medium,
        "dimensions": dimensions,
        "provenance": provenance,
        "status": _status_from_text(raw_html),
    }

    if auction_meta:
        result.setdefault("auction_id", auction_meta.auction_id)
        result.setdefault("auction_title", auction_meta.auction_title)
        result.setdefault("auction_start_date", auction_meta.auction_start_date)
        result.setdefault("auction_end_date", auction_meta.auction_end_date)
        result.setdefault("auction_house_name", auction_meta.auction_house_name)
        result.setdefault("auction_url", auction_meta.auction_url)
        result.setdefault("auction_info_url", auction_meta.auction_info_url)
    else:
        if auction_url_from_breadcrumb:
            result.setdefault("auction_url", auction_url_from_breadcrumb)
            result.setdefault("auction_id", _auction_id_from_url(auction_url_from_breadcrumb))
        if auction_title_from_breadcrumb:
            result.setdefault("auction_title", auction_title_from_breadcrumb)
        if auction_start_from_breadcrumb:
            result.setdefault("auction_start_date", auction_start_from_breadcrumb)

    return result


def get_auction_page_urls(page: Any, base_auction_url: str) -> list[str]:
    raw_html = _page_html(page)
    links = {_abs_url(url) for url in _HREF_RE.findall(raw_html)}
    page_links = {base_auction_url.split("?")[0]}
    for link in links:
        if "page=" in link or "order=" in link or "actual=" in link:
            page_links.add(link)
    return sorted(page_links)


def get_auction_title_from_page(page: Any) -> str:
    raw_html = _page_html(page)
    return _extract_title(raw_html)

