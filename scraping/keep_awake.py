#!/usr/bin/env python3
"""Compatibility wrapper for the new Bogota house module."""

from scraping.houses.bogota_auctions.keep_awake import main

__all__ = ["main"]


if __name__ == "__main__":
    main()
