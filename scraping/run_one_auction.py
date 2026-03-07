#!/usr/bin/env python3
"""Compatibility wrapper for the new Bogota house module."""

from scraping.houses.bogota_auctions.run_one_auction import main, scrape_auction

__all__ = ["main", "scrape_auction"]


if __name__ == "__main__":
    main()
