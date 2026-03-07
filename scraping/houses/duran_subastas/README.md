# Duran Arte y Subastas scraper

Scraper masivo para Durán con foco en categorías:

- `obra_grafica`
- `pintura`

## Comandos

```powershell
python -m scraping.houses.duran_subastas.run_historic --list-only
python -m scraping.houses.duran_subastas.run_historic --max-auctions 3 --max-lots-per-auction 50
python -m scraping.houses.duran_subastas.run_one_auction "https://www.duran-subastas.com/es/subasta/subasta-652-enero-2026_652-001"
```

## Controles masivos

- retries con backoff: `--max-retries`
- timeout por request: `--timeout`
- resume por archivos existentes
- checkpoints por subasta en `output/checkpoints/`
- límites de prueba: `--max-auctions`, `--max-lots-per-auction`

