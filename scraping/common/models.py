"""
Shared Pydantic data models for auction lot scraping.

Schema is designed to be Dublin Core (DCMI Terms) compatible.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AuctionMeta(BaseModel):
    """Metadata for a single auction event."""

    auction_id: str = Field(..., description="Slug/ID extracted from the auction URL")
    auction_title: str = Field(..., description="Title of the auction (dcterms:title)")
    auction_start_date: Optional[str] = Field(None, description="ISO-8601 start date (dcterms:date)")
    auction_end_date: Optional[str] = Field(None, description="ISO-8601 end date if available")
    auction_house_name: str = Field(default="Bogota Auctions", description="dcterms:publisher")
    auction_url: str = Field(..., description="Canonical URL of the auction listing (dcterms:identifier)")
    auction_info_url: Optional[str] = Field(None, description="INFO page URL")
    auction_image_url: Optional[str] = Field(None, description="Thumbnail image of the auction")


class LotItem(BaseModel):
    """Full record for a single auction lot."""

    auction_id: str
    auction_title: str
    auction_start_date: Optional[str] = None
    auction_end_date: Optional[str] = None
    auction_house_name: str = "Bogota Auctions"
    auction_url: str
    auction_info_url: Optional[str] = None

    lot_number: Optional[int] = None
    lot_url: str = Field(..., description="Canonical URL of the lot (dcterms:identifier)")
    lot_title: Optional[str] = Field(None, description="Display title: 'Artist. Title, year' (dcterms:title)")
    lot_year: Optional[str] = Field(None, description="Year of the work, e.g. '1930', 'ca. 1950', 'Sin Fecha' (dcterms:created)")
    image_url: Optional[str] = Field(None, description="Primary image URL")

    price_estimate_min: Optional[int] = Field(None, description="Low estimate (COP integer)")
    price_estimate_max: Optional[int] = Field(None, description="High estimate (COP integer)")
    price_sold: Optional[int] = Field(None, description="Hammer price if sold (COP integer)")
    currency: str = "COP"

    artist_name: Optional[str] = Field(None, description="dcterms:creator")
    artist_birth_year: Optional[int] = Field(None, description="Artist birth year, e.g. 1867")
    artist_death_year: Optional[int] = Field(None, description="Artist death year, e.g. 1930")
    artist_country: Optional[str] = Field(None, description="dcterms:spatial")
    artist_raw: Optional[str] = Field(None, description="Unstructured artist line from alt/description")

    description: Optional[str] = Field(None, description="Full text description (dcterms:description)")
    medium: Optional[str] = Field(None, description="Technique/material (dcterms:medium)")
    dimensions: Optional[str] = Field(None, description="Physical dimensions (dcterms:extent)")
    provenance: Optional[str] = Field(None, description="Ownership history (dcterms:provenance)")

    status: Optional[str] = Field(None, description="VENDIDO / NO VENDIDO / EN CURSO")

    scraped_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds") + "Z"
    )
