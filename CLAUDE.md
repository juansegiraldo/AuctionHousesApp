# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python data pipeline that scrapes Latin American / Spanish auction houses and refines the
results through a Medallion (bronze → silver → gold) architecture for analytics. There is no
running web service or database in the current tree — it is a batch scrape-and-transform project
producing JSONL files plus an HTML analytics report.

**The HTML report *is* the frontend.** `data/gold/analytics_report.html` is the product; there
is nothing to serve. Users looking for a UI should open that file.

> Note on git status: the tracked `backend/` (FastAPI), `frontend/` (Next.js), `database/`, and
> root `docker-compose.yml` / `Makefile` files show as **deleted** — the project was rebuilt
> around the scraping + pipelines layout and those legacy files no longer exist on disk. They
> remain recoverable from commit `765841b`. Work against the `scraping/`, `pipelines/`,
> `semantic_layer/`, and `data/` directories; ignore the old full-stack files unless explicitly
> asked to restore them. [ESTADO.md](ESTADO.md) documents this in Spanish for the repo owner.

## Setup & commands

All Python commands run **from the repo root**. `pyproject.toml` sets `pythonpath = ["."]`,
`testpaths = ["tests"]`, and `-p no:postgresql` (a leftover `pytest-postgresql` plugin from the
deleted backend crashes collection on `psycopg`/libpq import — do not remove that flag unless
the plugin is uninstalled). Targets Python 3.13.

There is **no top-level `requirements.txt`** (the legacy one was removed). The scraper deps live in
[scraping/requirements.txt](scraping/requirements.txt) — `scrapling[fetchers]`, `pydantic>=2.0`,
`orjson>=3.11`. The code additionally imports `requests` (Duran AJAX session), `pyyaml`
(`pipelines/config`), and `pytest` for tests.

```powershell
python -m venv venv; venv\Scripts\activate
pip install -r scraping/requirements.txt
pip install requests pyyaml pytest
```

Run tests (56 pass, 1 skipped):

```powershell
python -m pytest                          # full suite
python -m pytest tests/pipelines/         # pipeline + quality-gate tests
python -m pytest tests/scraping/duran_subastas/test_parse_lot_page.py::test_name
```

**Everything runs as a module** (`python -m`), scrapers and pipeline stages alike — the stages
now import from `pipelines.shared`, so file-path invocation breaks:

```powershell
python -m scraping.houses.duran_subastas.run_historic --list-only
python -m scraping.houses.bogota_auctions.run_auction_list --file urls.txt

.\scripts\run_all.ps1                     # whole pipeline in the correct order

python -m pipelines.bronze.ingest
python -m pipelines.silver.build_silver
python -m pipelines.enrichments.currency_normalize   # also: artist_canonicalize, category_tag
python -m pipelines.gold.build_gold
python -m pipelines.analytics.report_gold            # writes data/gold/analytics_report.{json,html}
```

`quality_gates.py` is the exception — still a file path, and it takes arguments:

```powershell
python pipelines/silver/quality_gates.py --house-slug duran_subastas
```

## Architecture

Two layers connected by the `data/` directory and the **house registry**.

### 1. Scraping (`scraping/`) — one subpackage per auction house

- `scraping/common/models.py` — shared Pydantic schema for **all** houses: `AuctionMeta` and
  `LotItem`. The schema is intentionally **Dublin Core (DCMI)–compatible** (fields annotated with
  `dcterms:*` mappings) and prices are integers in the house's own currency, which differs per
  house (`COP` for Bogotá, `EUR` for Duran — the model defaults to `COP`, so each house sets
  `currency` explicitly when building `LotItem`s). Changing this schema affects every house and
  every downstream pipeline stage.
- `scraping/houses/<slug>/` — each house has `parsers.py` (HTML → models) plus three runners with
  the **same interface across houses**: `run_one_auction.py`, `run_auction_list.py`,
  `run_historic.py`. Runners write JSONL into the house's own `output/` directory.
- `scraping/houses/registry.json` — the source of truth mapping `slug → module → output_dir`.
  `pipelines/bronze/ingest.py` reads this to discover what to land. **Adding a house means adding
  a registry entry**, not editing the pipeline.
- House runners share patterns: retry-with-backoff (`--max-retries`, `--timeout`), resume by
  skipping auctions whose output file already exists, per-auction JSON checkpoints under
  `output/checkpoints/`, test limits (`--max-auctions`, `--max-lots-per-auction`), and optional
  thread-pool parallelism (`--workers`; >16 risks HTTP 419 rate limiting).
- Duran discovers lots via an **AJAX endpoint**, not the static page. Its `historic_all_lots.jsonl`
  is a superset of the per-auction files (40,442 lots, 2014→2026) and is safe to re-ingest —
  Silver dedupes on `lot_url`.
- `scraping/` root still holds the original single-house (Bogotá) scripts — the `houses/` layout
  is the current structure; prefer it for new work.

### 2. Pipelines (`pipelines/`) — Medallion transform over `data/`

Data flows one direction through `data/`, and each stage reads the previous layer only:

1. **bronze** (`bronze/ingest.py`): copies each registered house's `output/*.jsonl` into
   `data/bronze/<slug>/ingestion_date=YYYY-MM-DD/`. Immutable raw landing.
2. **silver** (`silver/build_silver.py`): reads all bronze JSONL, calls
   `pipelines.shared.schema.normalize_lot` (adds `house_slug`, `ingested_at`, `source_file`, and a
   `dedupe_key = "<house>|<lot_url>"`), dedupes on that key, and emits `data/silver/lots.jsonl`
   plus a derived `data/silver/auctions.jsonl`. `auction_index.jsonl` files are skipped here.
3. **enrichments** (`enrichments/*.py`): optional, independent jobs keyed by `dedupe_key`
   (currency normalize, artist canonicalize, category tag, embeddings stub) → `data/enrichments/`.
4. **gold** (`gold/build_gold.py`): aggregates silver into analytics facts
   (`agg_house_metrics`, `agg_lots_by_year`, …) plus `quality_flags.jsonl` in `data/gold/`.
5. **quality_gates** (`silver/quality_gates.py`): coverage report (% with price/artist/image/url)
   over silver, optionally per house. Reports by default; `--fail-on-violation` exits non-zero
   for CI. `--allowed-categories` must match the **English** tags emitted by `category_tag.py`
   (`painting`, `prints`, …) — the old Spanish defaults matched nothing and flagged 100% of rows.
6. **analytics** (`analytics/report_gold.py`): renders the Gold layer to JSON + HTML. Reads Gold
   only — never bronze/silver.

Run the whole chain with `.\scripts\run_all.ps1`. Running stages piecemeal is how the layers
previously drifted out of sync (enrichments built in March over a Silver rebuilt in May).
The Duran "massive run" runbook lives in [docs/SCALING_CHECKLIST.md](docs/SCALING_CHECKLIST.md).

### Data rules that hold up every Gold figure

These are load-bearing. Breaking one silently corrupts the report:

- **Never sum prices across houses.** Each house quotes in its own currency (`COP` for Bogotá,
  `EUR` for Duran). Gold emits `revenue_native` + `currency` (exact) alongside `revenue_eur`
  (approximate). Any cross-house total must sum `revenue_eur`. Conversion goes through
  `pipelines/shared/fx.py`, whose rates live in `pipelines/config/fx.yaml` — the single source
  of truth, read by both Gold and the currency enrichment. `to_eur()` returns `None` for an
  unknown currency, never `1.0`, so a missing rate stays visible instead of masquerading as euros.
- **Year extraction is house-specific**, so always use `pipelines.shared.schema.extract_year()`.
  Bogotá stores ISO (`2024-06-07T19:00`); Duran stores Spanish text (`"Julio 2014"`) and
  sometimes only encodes the year in `auction_id`. It returns `(year, method)` so the report can
  say when a year was *inferred* rather than read.
- **"Sold" means explicit status when the house publishes it** — use
  `pipelines.shared.schema.is_sold()`. Falling back to "has a price" is only valid where status
  is absent.
- **Sell-through is not comparable across houses.** Bogotá reads ~99% because its site publishes
  almost exclusively sold lots (~1,764 lot numbers missing from otherwise contiguous sequences);
  Duran publishes `NO VENDIDO` too and reads ~46%. This is a source-data property, not a bug —
  surface it as a warning, never "fix" it by computation.
- `quality_flags.jsonl` carries these caveats into the report's warnings panel. When adding a
  caveat, emit a flag there rather than hardcoding text in the HTML.

### 3. Semantic layer (`semantic_layer/`) — code-first business definitions

`sources.yaml` (which Gold/Silver/enrichment datasets exist), `dimensions.yaml`, and
`metrics.yaml` (KPI expressions like `sell_through_rate`, `revenue_native` / `revenue_eur`).
Intended to be consumed by BI tools / future analytics endpoints — it's metadata, not executed
by the pipelines. Because nothing executes it, it can silently drift from the pipeline: when you
change how a metric is computed in `build_gold.py`, update `metrics.yaml` in the same edit.

## Conventions

- **All data outputs are gitignored** (`data/bronze|silver|gold|enrichments/*`, every
  `scraping/**/output/*.jsonl`, and checkpoints). Only `.gitkeep` files are tracked. Don't commit
  scrape results.
- JSONL is the interchange format everywhere; writes use `orjson` with `OPT_APPEND_NEWLINE`.
- Tests use HTML **fixtures** under `tests/scraping/<house>/fixtures/` so parser tests run offline;
  prefer adding a fixture over hitting the live site.
- Adding a house or enrichment is registry/config driven — see
  [docs/SCALING_CHECKLIST.md](docs/SCALING_CHECKLIST.md) and [scraping/README.md](scraping/README.md).
- Comments in pipeline code are written in Spanish (the repo owner's language) and explain *why*
  a rule exists, usually citing the bug it prevents. Match that when editing those files.

## Known issues

Don't rediscover these; they're documented in [ESTADO.md](ESTADO.md) too:

- **`scraping/houses/bogota_auctions/parsers.py` never extracts `status`** — a regression from the
  refactor. The legacy [scraping/parsers.py](scraping/parsers.py) still does, and its final
  `if not status and price_sold: status = "VENDIDO"` is where Bogotá's inferred status comes from.
  Current Bogotá status data was produced by the legacy scraper.
- **Mojibake in scraped text**: `Álvaro` surfaces as `\udc81lvaro` in `artist_name`/`lot_title`.
  Encoding issue at scrape time; surviving into Silver. Flagged in the report, not fixed — a real
  fix means re-scraping or a repair pass over Bronze.
- **`subasta-541-marzo-2107`** is a typo on Duran's own site (2107 for 2017). `extract_year()`
  only accepts `19xx`/`20xx`, so those 315 lots land in `unknown` rather than a fabricated year.
- Bronze holds overlapping partitions (March and August ingests). Safe — Silver dedupes on
  `lot_url` — but it roughly doubles Bronze disk usage.
- Legacy single-house scripts still sit at the `scraping/` root beside the current
  `scraping/houses/` layout.
