# Ficheros descartados — NO devolver a `output/`

Estos dos JSONL son **restos de corridas de prueba**, no datos.

| Fichero | Filas | Qué tiene |
|---|---|---|
| `2245_test.jsonl` | 127 | catálogo sin detalle |
| `test_info_url.jsonl` | 173 | catálogo sin detalle |

## Por qué están fuera de `output/`

Son corridas que **nunca bajaron la página de detalle del lote**, así que las 300
filas traen `auction_start_date`, `artist_name`, `artist_raw`, `medium`,
`provenance`, `dimensions` y `price_estimate_max` a `None`.

Silver deduplica por `lot_url` y **gana el primero que aterriza**, de modo que
mientras estuvieron en `output/` pisaban a los ficheros buenos: 67 lotes de la
subasta 2245 entraban mutilados aunque
`grabados-y-multiples-artes-decorativas-y-diseno_2245-001.jsonl` tiene los 127
completos al lado. Se detectó porque esos lotes salían como los 52
`fallback_static` de la capa FX.

No aportan **ni una sola** `lot_url` que no esté ya en los ficheros buenos.

## Doble red

1. `pipelines/bronze/ingest.py` ignora cualquier fichero con `test` como
   **segmento** del nombre (`is_ingestable()`), así que aunque volvieran a
   `output/` no entrarían.
2. Están aquí, fuera de `output/`, que es el directorio que lee el registro.

Se conservan en vez de borrarse por si hicieran falta para depurar el scraper.
Ver la entrada de *Known issues* en `CLAUDE.md`.
