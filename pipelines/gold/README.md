# Gold layer

Analytics-ready facts and aggregates. Built from Silver by `build_gold.py`. Consumed only by `pipelines/analytics/report_gold.py` (and any future analytics or semantic consumers).

## Artefacts

### agg_house_metrics.jsonl

One row per auction house.

| Field             | Type    | Description                          |
|-------------------|---------|--------------------------------------|
| house_slug        | string  | House identifier                     |
| lots_offered      | int     | Total lots                           |
| lots_sold         | int     | Lots with price_sold                 |
| sell_through_rate | float   | lots_sold / lots_offered (0–1)        |
| revenue           | float   | Sum of price_sold (EUR)              |
| avg_sold_price    | float?  | revenue / lots_sold, or null if none |

### agg_auction_metrics.jsonl

One row per auction (house + auction_id).

| Field          | Type   | Description                    |
|----------------|--------|--------------------------------|
| house_slug     | string | House identifier               |
| auction_id     | string | Auction identifier             |
| auction_title  | string?| From silver lot                |
| lots           | int    | Lots in auction                |
| sold           | int    | Lots sold                      |
| sell_through_pct| float | (sold / lots) * 100            |
| revenue_eur    | float  | Sum of price_sold for auction  |

## Future extensions

Gold can be extended with more artefacts (e.g. semantic rollups, embedding summaries, category aggregates) without changing Bronze or Silver. Document new artefacts here and have `report_gold.py` (or other consumers) read them from `data/gold/`.
