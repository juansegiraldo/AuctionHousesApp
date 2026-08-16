# Scaling Checklist

## Add a new auction house

**Hito 0 primero: comprobar que la fuente publica lo que necesitas.** Antes de escribir
código, baja la página histórica con el fetcher que vayas a usar y confirma que hay
**precio de remate numérico**. Zorrilla costó dos intentos por saltarse esto: su sitio
propio lista 70 subastas que están todas vacías, y una fixture capturada sin render JS
(`auction_page.html`) quedó inservible. Si no hay precios, cambia de fuente — no de parser.

Casas nuevas: usar el framework `scraping/common/` (las legacy `bogota_auctions` y
`duran_subastas` siguen con código propio duplicado; no migrarlas).
`zorrilla_subastas` es el ejemplo de referencia.

1. Crear `scraping/houses/<slug>/` con `__init__.py`.
2. `parsers.py` con las 5 funciones de `House.REQUIRED_PARSER_FUNCS`
   (`_auction_id_from_url`, `parse_historic_page`, `parse_auction_page`, `parse_lot_page`,
   `get_auction_title_from_page`) + opcional `get_auction_start_date_from_page`.
   Tests primero, sobre fixtures HTML en `tests/scraping/<slug>/fixtures/`.
3. `house.py` con un `HOUSE = House(...)`: elegir la estrategia de `discovery.py`
   (`html_pagination_discovery` o `ajax_infinite_scroll_discovery`) y el `fetcher`
   (`default_fetcher`, `stealthy_fetcher`, o uno propio si hace falta `network_idle`).
4. Los 3 runners como shims de ~15 líneas que llaman a `run_*_cli(globals())`. Deben exponer
   `HOUSE`, `DEFAULT_OUTPUT_DIR`, `scrape_auction` y, en historic, `fetch_historic`.
5. Salida por defecto a `scraping/houses/<slug>/output/`.
6. Añadir entrada en `scraping/houses/registry.json` (Bronze no necesita cambios de código).
7. Si la moneda es nueva, **añadir la tasa a `pipelines/config/fx.yaml`** — sin eso `to_eur()`
   devuelve `None` y la casa desaparece de los totales cross-house.
8. Correr Bronze ingest y verificar `data/bronze/<slug>/`.

## Add an enrichment pipeline

1. Add script under `pipelines/enrichments/`.
2. Produce output keyed by `dedupe_key`.
3. Register source in `semantic_layer/sources.yaml`.
4. Update `semantic_layer/dimensions.yaml` or `metrics.yaml` if needed.

## Add a semantic metric

1. Define metric expression in `semantic_layer/metrics.yaml`.
2. Verify source dataset exists in Silver/Gold.
3. Add BI/dashboard mappings.

## Standard run order

1. Scrape per house.
2. `python pipelines/bronze/ingest.py`
3. `python pipelines/silver/build_silver.py`
4. Run selected enrichments.
5. `python pipelines/gold/build_gold.py`

## Duran (#2) massive runbook

### Historic full run (focus categories only)

```powershell
python -m scraping.houses.duran_subastas.run_historic --max-retries 3 --timeout 25 --delay 1.5
```

### Incremental resume run

```powershell
python -m scraping.houses.duran_subastas.run_historic --start-from 652 --max-retries 3 --timeout 25
```

### Backfill sample run

```powershell
python -m scraping.houses.duran_subastas.run_historic --max-auctions 10 --max-lots-per-auction 100
```

### Post-run checklist

1. `python pipelines/bronze/ingest.py`
2. `python pipelines/silver/build_silver.py`
3. `python pipelines/enrichments/currency_normalize.py`
4. `python pipelines/enrichments/artist_canonicalize.py`
5. `python pipelines/enrichments/category_tag.py`
6. `python pipelines/enrichments/embeddings.py`
7. `python pipelines/gold/build_gold.py`
8. `python pipelines/silver/quality_gates.py --house-slug duran_subastas`

## Zorrilla (#3) massive runbook

Fuente: **LiveAuctioneers**, no el sitio propio (ver
[scraping/houses/zorrilla_subastas/README.md](../scraping/houses/zorrilla_subastas/README.md)).
45 catálogos, ~12.500 lotes, 2019-2023, en USD.

```powershell
python -m scraping.houses.zorrilla_subastas.run_historic --list-only
python -m scraping.houses.zorrilla_subastas.run_historic --quick --workers 4
```

**Siempre `--quick`**: el payload del catálogo ya trae precio, estimaciones, estado y título,
así que el fetch de detalle por lote no aporta nada y serían ~12.500 cargas de navegador.

El fetcher es un navegador headless (~10-40 s por página, ~11 páginas por catálogo), así que
el run completo va en decenas de minutos. Resume por fichero existente: relanzar el mismo
comando continúa donde se quedó.

### Post-run

Igual que Durán, pero con `--house-slug zorrilla_subastas` en el paso 8. Verificar además que
`data/gold/quality_flags.jsonl` incluye `currency_normalized_at_source` (salvedad USD/UYU).
