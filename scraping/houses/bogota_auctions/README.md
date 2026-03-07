# Bogota Auctions scraper

This house package contains the scraper implementation for Bogota Auctions.

## Run from repo root

```powershell
python -m scraping.houses.bogota_auctions.run_one_auction "<AUCTION_URL>"
python -m scraping.houses.bogota_auctions.run_auction_list --file urls.txt
python -m scraping.houses.bogota_auctions.run_historic
```

## Output location

Default output files are written to:

`scraping/houses/bogota_auctions/output/`

The scripts still accept `--output` if you want a custom path.
