# Pipelines

Pipeline stages are designed around Medallion architecture:

1. `bronze/ingest.py` - land raw house JSONL into `data/bronze/`
2. `silver/build_silver.py` - normalize and dedupe into `data/silver/`
3. `enrichments/*.py` - optional enrichment outputs
4. `gold/build_gold.py` - analytics-ready aggregates into `data/gold/`
5. `silver/quality_gates.py` - house-level quality validation for massive runs
6. `analytics/report_gold.py` - report from Gold only (no bronze/silver); writes `data/gold/analytics_report.json` and `analytics_report.html`

## Typical execution

```powershell
python pipelines/bronze/ingest.py
python pipelines/silver/build_silver.py
python pipelines/enrichments/currency_normalize.py
python pipelines/gold/build_gold.py
python pipelines/silver/quality_gates.py --house-slug duran_subastas
python pipelines/analytics/report_gold.py
```

After building Gold, run the analytics report to see metrics from the Gold layer (house and auction aggregates). Open `data/gold/analytics_report.html` in a browser to view the report.

## Bronze/Silver contract

Bronze preserves raw scraper artifacts, including per-house metadata files such as `auction_index.jsonl`. Silver `lots.jsonl` is lot-grain only: `silver/build_silver.py` reads records with a non-empty `lot_url`, skips non-lot artifacts, and dedupes by `house_slug|lot_url`.
