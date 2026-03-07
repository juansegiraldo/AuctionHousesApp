"""
Pure extraction functions for Bogotá Auctions pages.

Each function receives a Scrapling response/page object and returns
either model instances or raw dicts.  No network calls happen here,
making the logic easy to test with saved HTML fixtures.
"""

from __future__ import annotations

import html as html_mod
import re
from typing import Any
from urllib.parse import urljoin

from scraping.common.models import AuctionMeta, LotItem

BASE_URL = "https://www.bogotaauctions.com"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COP_RE = re.compile(r"COP\s*\$?\s*([\d.]+)")
_ESTIMATE_RE = re.compile(
    r"COP\s*\$\s*([\d.]+)\s*[-–]\s*\$\s*([\d.]+)"
)
_ESTIMATE_PLAIN_RE = re.compile(
    r"(?:Estimado|estimado):\s*\$?\s*([\d.]+)\s*[-–]\s*\$?\s*([\d.]+)",
    re.IGNORECASE,
)
# Country + dates in parentheses: "(Colombia, 1945)" or "(Colombia, 1945 - 2020)"
_ARTIST_COUNTRY_PAREN_RE = re.compile(
    r"\(([A-ZÁ-Úa-zá-úñ]+(?:\s+[A-ZÁ-Úa-zá-úñ]+)*),\s*(\d{4})(?:\s*[-–]\s*(\d{4}))?\)"
)
_DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
_DIMENSIONS_RE = re.compile(r"(\d[\d,\.]*\s*x\s*\d[\d,\.]*\s*(?:x\s*\d[\d,\.]*\s*)?cm)", re.IGNORECASE)
_LOT_NUM_RE = re.compile(r"^(\d+)\s*-\s*")
_LOT_YEAR_RE = re.compile(
    r",\s*"
    r"("
    r"(?:ca\.?\s*|c\.\s*|circa\s+)?\d{4}"      # year with optional ca./circa prefix
    r"(?:\s*[-–]\s*\d{4})?"                      # optional range like 1950-1960
    r"|[Ss]in\s+[Ff]echa"                        # "Sin Fecha"
    r"|[Ss]\.?\s*[Ff]\.?"                        # "S.F." / "s.f."
    r")\s*$"
)
_ARTIST_LINE_RE = re.compile(
    r"^(.+?)(?:\s*<br>\s*|\n\s*)([A-ZÁ-Ú][a-zá-ú]+(?:[\s,]+\w+)*),\s*(\d{4})\s*[-–]\s*(\d{4})?",
    re.UNICODE,
)


def _parse_cop(text: str) -> int | None:
    """Extract integer COP amount from text like 'COP 1.200.000' or 'COP  6.000.000'."""
    text = text.replace("\xa0", " ").strip()
    m = _COP_RE.search(text)
    if m:
        raw = m.group(1).replace(".", "")
        try:
            return int(raw)
        except ValueError:
            return None
    return None


def _parse_date(dd_mm_yyyy: str) -> str | None:
    """Convert DD-MM-YYYY to ISO-8601 YYYY-MM-DD."""
    m = _DATE_RE.match(dd_mm_yyyy.strip())
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


def _parse_time(text: str) -> str:
    """Extract HH:MM from text like '17:00 h'."""
    m = re.search(r"(\d{1,2}:\d{2})", text)
    return m.group(1) if m else ""


def _abs_url(href: str) -> str:
    if href and not href.startswith("http"):
        return urljoin(BASE_URL, href)
    return href


def _auction_id_from_url(url: str) -> str:
    """Extract auction ID/slug from a URL like '.../subasta/slug_2583-001'."""
    parts = url.rstrip("/").split("/")
    return parts[-1] if parts else url


def _info_url_from_auction_url(auction_url: str) -> str | None:
    """
    Derive the INFO page URL from an auction URL.
    .../es/subasta/slug_2583-001 -> .../es/info-subasta/2583-slug
    .../es/subasta/slug_2685B-001 -> .../es/info-subasta/2685B-slug
    """
    if not auction_url or "/es/subasta/" not in auction_url:
        return None
    base = BASE_URL.rstrip("/")
    if auction_url.startswith("http"):
        base = auction_url.split("/es/")[0]
    segment = auction_url.rstrip("/").split("/")[-1]
    if "_" not in segment:
        return None
    # slug_id e.g. "libros-documentos-y-grabados-antiguos-virtual_2685B-001"
    parts = segment.split("_", 1)
    if len(parts) != 2:
        return None
    slug, id_part = parts
    # id_part "2685B-001" -> "2685B"; "2583-001" -> "2583"
    id_for_info = id_part.split("-")[0] if "-" in id_part else id_part
    return f"{base}/es/info-subasta/{id_for_info}-{slug}"



def _clean_text(text: str | None) -> str:
    """Strip whitespace and normalize."""
    if not text:
        return ""
    return " ".join(text.split()).strip()


def _extract_lot_year(title: str) -> str | None:
    """
    Extract the work's year from a title like:
      'León Cano. Vista de París, 1930'  ->  '1930'
      'Fernando Botero. Sin título, ca. 1950'  ->  'ca. 1950'
      'Anónimo. Retrato, Sin Fecha'  ->  'Sin Fecha'
      '[Vista de París], 1930'  ->  '1930'
    """
    m = _LOT_YEAR_RE.search(title)
    if m:
        year = m.group(1).strip()
        if re.match(r"[Ss]\.?\s*[Ff]\.?$", year) or re.match(r"[Ss]in\s+[Ff]echa$", year):
            return "Sin Fecha"
        return year
    return None


def _unescape_json_html(s: str) -> str:
    """Unescape JSON-encoded HTML: \\\" -> \", unicode escapes, etc."""
    s = s.replace('\\"', '"').replace("\\n", "\n").replace("\\/", "/")
    s = s.encode("utf-8").decode("unicode_escape", errors="replace")
    return s


def _html_to_text(html_str: str) -> str:
    """Minimal HTML to text: strip tags, decode entities."""
    text = re.sub(r"<br\s*/?>", "\n", html_str, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_mod.unescape(text)
    text = text.replace("\xa0", " ")
    return text.strip()


# ---------------------------------------------------------------------------
# Historic page parser
# ---------------------------------------------------------------------------

def parse_historic_page(page: Any) -> list[AuctionMeta]:
    """
    Parse the historic auctions listing page.
    Returns a list of AuctionMeta, one per auction card.
    """
    cards = page.css(".auctions-auction-card")
    auctions: list[AuctionMeta] = []

    for card in cards:
        title_el = card.css(".auction-card_title")
        title = _clean_text(title_el[0].text) if title_el else ""

        ver_lotes = card.css("a.auction-card__button_principal")
        auction_url = ""
        if ver_lotes:
            auction_url = _abs_url(ver_lotes[0].attrib.get("href", ""))

        info_link = card.css("a.auction-card__button_secondary")
        info_url = _abs_url(info_link[0].attrib.get("href", "")) if info_link else None

        img = card.css("img")
        img_url = None
        for i in img:
            src = i.attrib.get("src", "")
            if src and "logo" not in src and "base64" not in src:
                img_url = _abs_url(src)
                break

        # Dates: look at .auctions-init-dates inside .auction-card__dates, then anywhere in card
        date_blocks = card.css(".auction-card__dates .auctions-init-dates") or card.css(".auctions-init-dates")
        start_date = None
        end_date = None
        start_time = ""
        end_time = ""

        for block in date_blocks:
            ps = block.css("p.m-0")
            label = _clean_text(ps[0].text) if len(ps) > 0 else ""
            date_text = _clean_text(ps[1].text) if len(ps) > 1 else ""
            time_el = block.css("small")
            time_text = _clean_text(time_el[0].text) if time_el else ""

            parsed_date = _parse_date(date_text)
            label_lower = label.lower().strip()
            if parsed_date and ("inicio" in label_lower or label_lower == "start"):
                start_date = parsed_date
                start_time = _parse_time(time_text)
            elif parsed_date and ("cierre" in label_lower or label_lower == "end" or label_lower == "cierre"):
                end_date = parsed_date
                end_time = _parse_time(time_text)

        # Fallback: find any p.m-0 with "Inicio" / "Start" followed by DD-MM-YYYY, and optional small for time
        if not start_date:
            all_ps = card.css("p.m-0")
            for idx, p in enumerate(all_ps):
                txt = _clean_text(p.text)
                if ("inicio" in txt.lower() or txt.strip().lower() == "start") and idx + 1 < len(all_ps):
                    next_text = _clean_text(all_ps[idx + 1].text)
                    start_date = _parse_date(next_text)
                    if start_date:
                        # try to get time from same block (next sibling small after the date p)
                        parent = all_ps[idx + 1].parent
                        if parent:
                            smalls = parent.css("small")
                            if smalls:
                                start_time = _parse_time(_clean_text(smalls[0].text))
                    break
                if ("cierre" in txt.lower() or txt.strip().lower() == "end") and idx + 1 < len(all_ps):
                    next_text = _clean_text(all_ps[idx + 1].text)
                    end_date = _parse_date(next_text)
                    if end_date:
                        parent = all_ps[idx + 1].parent
                        if parent:
                            smalls = parent.css("small")
                            if smalls:
                                end_time = _parse_time(_clean_text(smalls[0].text))
                    break

        if start_date and start_time:
            start_date = f"{start_date}T{start_time}"
        if end_date and end_time:
            end_date = f"{end_date}T{end_time}"

        auction_id = _auction_id_from_url(auction_url)

        auctions.append(
            AuctionMeta(
                auction_id=auction_id,
                auction_title=title,
                auction_start_date=start_date,
                auction_end_date=end_date,
                auction_url=auction_url,
                auction_info_url=info_url,
                auction_image_url=img_url,
            )
        )

    return auctions


# ---------------------------------------------------------------------------
# Auction page parser (lot listing)
# ---------------------------------------------------------------------------

def parse_auction_page(page: Any, auction_meta: AuctionMeta | None = None) -> list[dict]:
    """
    Parse a single page of an auction's lot listing.

    Returns a list of dicts with lot preview data:
      lot_url, lot_number, lot_title, price_estimate_min, price_estimate_max, price_sold, status, thumbnail_url
    """
    items = page.css(".item_lot")
    lots: list[dict] = []

    for item in items:
        # .item_lot is typically wrapped inside an <a> tag
        parent_a = item.parent
        if parent_a and parent_a.tag == "a" and "/es/lote/" in (parent_a.attrib.get("href", "")):
            lot_url = _abs_url(parent_a.attrib.get("href", ""))
        else:
            lot_link = item.css("a[href*='/es/lote/']")
            if not lot_link:
                continue
            lot_url = _abs_url(lot_link[0].attrib.get("href", ""))

        title_el = item.css("span.seo_h4")
        raw_title = _clean_text(title_el[0].text) if title_el else ""

        lot_number = None
        lot_title = raw_title
        nm = _LOT_NUM_RE.match(raw_title)
        if nm:
            lot_number = int(nm.group(1))
            lot_title = raw_title[nm.end():].strip()

        price_els = item.css("span.salida-price")
        price_estimate_min = None
        price_estimate_max = None
        price_sold = None
        for pel in price_els:
            cls = pel.attrib.get("class", "")
            txt = _clean_text(pel.text)
            if "soldGrid" in cls:
                price_sold = _parse_cop(txt)
            else:
                em = _ESTIMATE_RE.search(txt)
                if em:
                    try:
                        price_estimate_min = int(em.group(1).replace(".", ""))
                        price_estimate_max = int(em.group(2).replace(".", ""))
                    except ValueError:
                        pass
                elif price_estimate_min is None:
                    price_estimate_min = _parse_cop(txt)

        # RightlabelGrid is a sibling of .item_lot inside the parent <a> tag
        status = None
        parent_a = item.parent
        if parent_a and parent_a.tag == "a":
            sold_label = parent_a.css(".RightlabelGrid")
            if sold_label:
                status_text = _clean_text(sold_label[0].text)
                if "VENDIDO" in status_text.upper():
                    status = "VENDIDO"
        if not status and price_sold:
            status = "VENDIDO"

        img = item.css("img")
        thumb = None
        for i in img:
            src = i.attrib.get("src", "")
            if src and "/img/thumbs/" in src:
                thumb = _abs_url(src)
                break

        lot_year = _extract_lot_year(lot_title) if lot_title else None

        lots.append(
            {
                "lot_url": lot_url,
                "lot_number": lot_number,
                "lot_title": lot_title,
                "lot_year": lot_year,
                "price_estimate_min": price_estimate_min,
                "price_estimate_max": price_estimate_max,
                "price_sold": price_sold,
                "status": status,
                "thumbnail_url": thumb,
            }
        )

    return lots


def get_auction_page_urls(page: Any, base_auction_url: str) -> list[str]:
    """
    Extract all pagination URLs from an auction page.
    Returns a deduplicated list including the base URL.
    """
    urls = {base_auction_url.split("?")[0]}
    for link in page.css(".pagination a"):
        href = link.attrib.get("href", "")
        if href:
            urls.add(_abs_url(href))
    return sorted(urls)


def get_auction_title_from_page(page: Any) -> str:
    """Extract auction title from h1 on an auction page."""
    h1 = page.css("h1")
    if h1:
        return _clean_text(h1[0].text)
    return ""


# ---------------------------------------------------------------------------
# Lot detail page parser
# ---------------------------------------------------------------------------

def parse_lot_page(page: Any, auction_meta: AuctionMeta | None = None) -> dict:
    """
    Parse a single lot detail page.

    Returns a dict with all extractable fields for a LotItem.
    """
    result: dict[str, Any] = {}

    # --- Lot title from span.description (first one) ---
    desc_spans = page.css("span.description")
    if desc_spans:
        title_text = _clean_text(desc_spans[0].text)
        result["lot_title"] = title_text
        year = _extract_lot_year(title_text)
        if year:
            result["lot_year"] = year
    if len(desc_spans) > 1:
        result["artist_name"] = _clean_text(desc_spans[1].text)

    # --- Main image ---
    main_img = page.css(".item_content_img_single img")
    for img in main_img:
        src = img.attrib.get("src", "")
        if src and "/img/thumbs/" in src:
            result["image_url"] = _abs_url(src)
            alt = img.attrib.get("alt", "")
            if alt:
                result["artist_raw"] = _clean_text(alt)
                _parse_artist_from_alt(alt, result)
            break

    # --- Status ---
    retired = page.css(".retired")
    if retired:
        result["status"] = _clean_text(retired[0].text)

    # --- Sold price ---
    pre_price = page.css(".pre-price")
    if pre_price:
        price_text = _clean_text(pre_price[0].text)
        result["price_sold"] = _parse_cop(price_text)

    # --- Auction URL ---
    auction_link = page.css('a[href*="/es/subasta/"]')
    if auction_link:
        result["auction_url"] = _abs_url(auction_link[0].attrib.get("href", ""))

    # --- Extract rich data from embedded JSON (desc_hces1) ---
    _parse_embedded_json(page, result)

    # --- Merge auction meta if provided ---
    if auction_meta:
        result.setdefault("auction_id", auction_meta.auction_id)
        result.setdefault("auction_title", auction_meta.auction_title)
        result.setdefault("auction_start_date", auction_meta.auction_start_date)
        result.setdefault("auction_end_date", auction_meta.auction_end_date)
        result.setdefault("auction_house_name", auction_meta.auction_house_name)
        result.setdefault("auction_url", auction_meta.auction_url)
        result.setdefault("auction_info_url", auction_meta.auction_info_url)

    return result


def _parse_artist_from_alt(alt: str, result: dict) -> None:
    """
    Parse artist info from image alt text like:
      'Fernando Botero Colombia, 1932 - 2023 : Sin título'
    The alt text may have the artist name run together with country
    (no separator), e.g. "Fernando BoteroColombia, 1932 - 2023".
    """
    # Split on " : " to separate artist info from title
    parts = alt.split(" : ")
    if len(parts) < 2:
        return

    artist_part = parts[0].strip()
    # Alt text often has no space between name and country:
    #   "Fernando BoteroColombia, 1932 - 2023"
    #   "Gastón LelargeFrancia, 1861 - 1890"
    # We split at the boundary where a lowercase letter precedes a capital letter + comma + year.
    m = re.match(
        r"(.+?)([A-ZÁ-Ú][a-zá-úñ]+(?:\s+[A-ZÁ-Ú][a-zá-úñ]+)*),\s*(\d{4})\s*[-–]\s*(\d{4})?",
        artist_part,
    )
    if m:
        name = m.group(1).strip().rstrip(",").strip()
        country = m.group(2).strip()
        # If the name ends without a space before country, it was concatenated
        # Only set country from alt if it looks reasonable (not part of the name)
        result.setdefault("artist_name", name)
        try:
            result.setdefault("artist_birth_year", int(m.group(3)))
        except (ValueError, TypeError):
            pass
        if m.group(4):
            try:
                result.setdefault("artist_death_year", int(m.group(4)))
            except (ValueError, TypeError):
                pass


def _parse_embedded_json(page: Any, result: dict) -> None:
    """
    Extract and parse the desc_hces1 HTML from the embedded auction_info JSON.

    This contains the richest structured data: artist, technique, dimensions,
    provenance, and estimate range.
    """
    for script in page.css("script"):
        txt = script.text or ""
        if "auction_info" not in txt:
            continue

        # Use regex to extract the desc_hces1 value up to the next field boundary
        idx = txt.find('"desc_hces1":"')
        if idx < 0:
            break

        m = re.search(r'"desc_hces1":"(.*?)(?:","|\"\})', txt[idx:], re.DOTALL)
        if not m:
            break

        raw_html = m.group(1)
        # Unescape JS/JSON encoding: \\" -> ", \/ -> /, \\uXXXX -> char
        desc_html = raw_html.replace('\\"', '"').replace("\\\\", "\\").replace("\\/", "/")
        desc_html = re.sub(
            r"\\u([0-9a-fA-F]{4})",
            lambda x: chr(int(x.group(1), 16)),
            desc_html,
        )
        desc_text = _html_to_text(desc_html)

        if desc_text:
            result.setdefault("description", desc_text)

        _parse_description_fields(desc_text, result)

        # Extract lot ref number from JSON
        ref_match = re.search(r'"ref_asigl1":"(\d+)"', txt)
        if ref_match:
            result.setdefault("lot_number", int(ref_match.group(1)))

        break


def _parse_description_fields(desc_text: str, result: dict) -> None:
    """
    Parse structured fields from the description text block.

    Typical format:
        Fernando Botero
        Colombia, 1932 - 2023

        Sin título, 1956
        Óleo sobre tela
        130 x 90 cm
        ...
        Provenance: ...
        COP $150.000.000 - $300.000.000
    """
    lines = [ln.strip() for ln in desc_text.split("\n") if ln.strip()]

    if not lines:
        return

    # First line is often the artist name
    if lines and not result.get("artist_name"):
        result["artist_name"] = lines[0]

    # Look for country + dates line: "Colombia, 1932 - 2023" or "(Colombia, 1945)"
    country_line_idx = None
    for i, line in enumerate(lines[1:4], 1):
        m = re.match(
            r"([A-ZÁ-Ú][a-zá-ú]+(?:\s+[A-ZÁ-Ú][a-zá-ú]+)*),\s*(\d{4})\s*[-–]\s*(\d{4})?",
            line,
        )
        if m:
            result.setdefault("artist_country", m.group(1))
            try:
                result.setdefault("artist_birth_year", int(m.group(2)))
            except (ValueError, TypeError):
                pass
            if m.group(3):
                try:
                    result.setdefault("artist_death_year", int(m.group(3)))
                except (ValueError, TypeError):
                    pass
            country_line_idx = i
            break
        # Format "(Colombia, 1945)" or "(Colombia, 1945 - 2020)"
        pm = _ARTIST_COUNTRY_PAREN_RE.search(line)
        if pm:
            result.setdefault("artist_country", pm.group(1))
            try:
                result.setdefault("artist_birth_year", int(pm.group(2)))
            except (ValueError, TypeError):
                pass
            if pm.group(3):
                try:
                    result.setdefault("artist_death_year", int(pm.group(3)))
                except (ValueError, TypeError):
                    pass
            country_line_idx = i
            break

    # Work title line (after artist country): "[Vista de París], 1930"
    # Extract lot_year from it
    if country_line_idx is not None:
        for line in lines[country_line_idx + 1 : country_line_idx + 3]:
            year = _extract_lot_year(line)
            if year:
                result.setdefault("lot_year", year)
                break

    # Dimensions
    for line in lines:
        dm = _DIMENSIONS_RE.search(line)
        if dm:
            result.setdefault("dimensions", dm.group(1))
            break

    # Medium/technique: line containing keywords
    medium_keywords = [
        "óleo", "oleo", "acuarela", "acrílico", "acrilico", "tinta",
        "lápiz", "lapiz", "grabado", "litografía", "litografia",
        "serigrafía", "serigrafia", "técnica mixta", "tecnica mixta",
        "pastel", "gouache", "temple", "collage", "escultura",
        "bronce", "madera", "cerámica", "ceramica", "papel",
        "fotografía", "fotografia", "impresión", "impresion",
    ]
    for line in lines:
        lower = line.lower()
        if any(kw in lower for kw in medium_keywords):
            if not _DIMENSIONS_RE.match(line) and "COP" not in line:
                result.setdefault("medium", line)
                break

    # Provenance
    for i, line in enumerate(lines):
        lower = line.lower()
        if lower.startswith("provenance:") or lower.startswith("procedencia:"):
            prov = line.split(":", 1)[1].strip()
            result.setdefault("provenance", prov)
            break
        if "colección privada" in lower or "colecci" in lower.replace("ó", "o"):
            result.setdefault("provenance", line)

    # Estimate range: COP $X - $Y or "Estimado: $X - $Y"
    for line in lines:
        em = _ESTIMATE_RE.search(line)
        if em:
            try:
                result.setdefault("price_estimate_min", int(em.group(1).replace(".", "")))
                result.setdefault("price_estimate_max", int(em.group(2).replace(".", "")))
            except ValueError:
                pass
            break
    if not result.get("price_estimate_min") and not result.get("price_estimate_max"):
        for line in lines:
            em = _ESTIMATE_PLAIN_RE.search(line)
            if em:
                try:
                    result.setdefault("price_estimate_min", int(em.group(1).replace(".", "")))
                    result.setdefault("price_estimate_max", int(em.group(2).replace(".", "")))
                except ValueError:
                    pass
                break

    # "Precio salida" in the description is typically the low estimate
    for line in lines:
        if "precio salida" in line.lower():
            val = _parse_cop(line)
            if val:
                result.setdefault("price_estimate_min", val)
