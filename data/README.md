# Data Layers (Medallion)

This project uses a Medallion-style data layout:

- `data/bronze/`: immutable landed raw JSONL per house
- `data/silver/`: normalized and deduplicated records
- `data/gold/`: analytics-ready facts, dimensions, and aggregates
- `data/enrichments/`: outputs from enrichment jobs

Local data files are gitignored by default.
