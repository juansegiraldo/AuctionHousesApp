#!/usr/bin/env python3
"""Compatibility wrapper for the new Bogota house module."""

from scraping.houses.bogota_auctions.test_info_url import (
    test_derived_url,
    test_historic_index,
    test_scrape_has_info_url,
)

__all__ = ["test_derived_url", "test_historic_index", "test_scrape_has_info_url"]
