# Scaling Checklist

## Add a new auction house

1. Create `scraping/houses/<house_slug>/`.
2. Implement house parser and runners.
3. Set default output to `scraping/houses/<house_slug>/output/`.
4. Add entry in `scraping/houses/registry.json`.
5. Run Bronze ingest and verify house partition appears in `data/bronze/<house_slug>/`.

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
