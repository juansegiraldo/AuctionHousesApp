#!/usr/bin/env python3
"""Compatibility wrapper for the new Bogota house module."""

from scraping.houses.bogota_auctions.run_auction_list import main

__all__ = ["main"]


if __name__ == "__main__":
    main()
