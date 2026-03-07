# Pipelines

Pipeline stages are designed around Medallion architecture:

1. `bronze/ingest.py` - land raw house JSONL into `data/bronze/`
2. `silver/build_silver.py` - normalize and dedupe into `data/silver/`
3. `enrichments/*.py` - optional enrichment outputs
4. `gold/build_gold.py` - analytics-ready aggregates into `data/gold/`
5. `silver/quality_gates.py` - house-level quality validation for massive runs

## Typical execution

```powershell
python pipelines/bronze/ingest.py
python pipelines/silver/build_silver.py
python pipelines/enrichments/currency_normalize.py
python pipelines/gold/build_gold.py
python pipelines/silver/quality_gates.py --house-slug duran_subastas
```
