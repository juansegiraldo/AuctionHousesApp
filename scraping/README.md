# Scraping Workspace

Multi-house scraper workspace for auction houses.  
Each house lives under `scraping/houses/<house_slug>/`, with shared models in `scraping/common/`.

## Structure

```text
scraping/
  common/
    models.py
  houses/
    registry.json
    bogota_auctions/
      parsers.py
      run_one_auction.py
      run_auction_list.py
      run_historic.py
      output/
```

## Run a house scraper

Use module execution from repo root:

```powershell
python -m scraping.houses.bogota_auctions.run_one_auction "<AUCTION_URL>"
python -m scraping.houses.bogota_auctions.run_auction_list --file urls.txt
python -m scraping.houses.bogota_auctions.run_historic
```

## Add a new auction house

1. Create `scraping/houses/<new_slug>/`.
2. Add house-specific `parsers.py`.
3. Add `run_one_auction.py`, `run_auction_list.py`, and `run_historic.py`.
4. Set the house output directory to `scraping/houses/<new_slug>/output/`.
5. Register it in `scraping/houses/registry.json`.
6. Reuse shared schema from `scraping.common.models`.

## Output policy

- House outputs are written under `scraping/houses/<slug>/output/`.
- Legacy `scraping/output/` can be backed up with `scripts/preflight_backup_outputs.ps1`.
- Output JSONL is ignored by git via `.gitignore`.
