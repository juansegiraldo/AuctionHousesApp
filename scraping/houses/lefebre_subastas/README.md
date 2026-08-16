# Lefebre Subastas

**La única casa que no se scrapea.** Su dato no está en ninguna web: viene de una hoja
de cálculo curada a mano en 2024 (`FINALL.xlsx`, hoja `FINAL`), así que este directorio
tiene un conversor en vez de un scraper.

```powershell
python -m scraping.houses.lefebre_subastas.from_excel --excel FINALL.xlsx
```

Se ejecuta **a mano y una sola vez**, igual que un scraper: `run_all.ps1` empieza en
Bronze, sobre el JSONL ya escrito. A partir de ahí Lefebre es indistinguible del resto,
porque `pipelines/bronze/ingest.py` solo copia los `*.jsonl` del `output_dir` y nunca
importa el módulo de la casa.

**1.711 lotes · 15 subastas · 2021–2024 · COP · 806 vendidos (47,1%) · ≈1,34 M EUR.**

## La fuente

La hoja `FINAL` mezcla dos casas en 5.784 filas. Se filtra por
`Casa de Subasta == 'Lefebre'` y **las 4.073 filas de Bogotá se descartan**: esa casa ya
entra por su propio scraper y mezclarlas duplicaría el dato.

## Mapeo de columnas

| `LotItem` | Columna | Nota |
|---|---|---|
| `auction_id` | slug de `Auction Name` | `subasta-29`, `subasta-barranquilla` |
| `auction_title` | `Auction Name` | |
| `auction_url` | `URL Subasta` si es URL | en Lefebre trae el nombre, no una URL → `excel://…` |
| `auction_start_date` | `Auction_Date` → ISO | mezcla `dd/mm/YYYY` y datetime |
| `lot_url` | `URL Lote` o URI sintética | ver abajo |
| `lot_number` | `Order`, solo si es real | ver abajo |
| `lot_title`, `medium`, `dimensions` | parseo de `Title` | `Técnica`/`Tamaño` están vacías en las 1.711 filas |
| `description` | `Title` completo | |
| `price_estimate_min` | `Starting Price_Clean` | `Pendiente` → `None` |
| `price_estimate_max` | — | la hoja no tiene precio máximo |
| `price_sold` | `Sold For_Clean` si es > 0 | |
| `status` | derivado | `VENDIDO` / `NO VENDIDO` |
| `currency` | fijo `COP` | |
| `artist_name` / `artist_raw` | `Artista_Clean` / `Artista_Raw` | |
| `artist_birth_year` / `artist_death_year` | `Nacimiento_Clean` / `Muerte_Clean` | `Vive` → `None` |
| `artist_country` | `Pais_Clean` | **solo diagnóstico**, ver abajo |

## Cuatro trampas de esta fuente

Cada una tiene un test que la fija en `tests/scraping/lefebre_subastas/`.

**1. `Pasado` y `0` significan lo mismo: NO vendido.** No es una diferencia semántica
sino de convención por subasta — las 27/28/29/30 escriben `0`, las anteriores `Pasado`.
Tratar el `0` como un remate de cero, o `Pasado` como "sin dato", invertiría la tasa de
venta de la casa.

**2. `Order` no es el número de lote.** Solo lo es en las 4 subastas que además traen
URL (1..N contiguo). En las 11 antiguas es el **número de fila de la hoja** (~4074–5110).
Volcarlo fabricaría huecos enormes de secuencia, y `build_gold.py` lee esos huecos para
estimar si la casa publica los no vendidos: saldría un aviso inventado. Por eso ahí
`lot_number` se queda a `None`, y se emite el flag `partial_lot_numbers`.

**3. Solo 674 de 1.711 filas tienen URL de lote.** Silver descarta toda fila sin
`lot_url` y deduplica por `house_slug|lot_url`, así que hace falta un identificador único
**y estable entre ejecuciones** (si cambiara, cada ingesta duplicaría los lotes). Sin URL
se usa `excel://lefebre_subastas/<slug-subasta>/<Order>`: el par `(Auction Name, Order)`
no colisiona en ninguna de las 1.711 filas.

Nota: hay 16 pares con el mismo título dentro de la misma subasta que son **obras
distintas de verdad** (mismo artista, remates diferentes: Matta 3.000.000 vs 3.400.000).
Se separan por `Order` y no se deduplican.

**4. El bloque `Title` viene en dos formatos.** Las 11 subastas antiguas lo traen con
saltos de línea; las 4 nuevas (678 lotes) con **espacios**, y a veces sin separación
ninguna. Partir solo por líneas dejaba esos lotes sin título y hundía la cobertura al
60%. Se corta por dos marcas presentes en ambos formatos: el paréntesis biográfico
(`(1907-1992)`) y `Medidas:`.

## El país es solo diagnóstico

`Pais_Clean` cubre 1.396 lotes — casi el doble de los 734 que resuelve hoy el maestro de
artistas. Aun así **no fija el país del artista**: se escribe en `artist_country`, que
alimenta `unmapped_country_values` y el contador de conflictos, y nada más.

La regla del repo es que `artist_country_birth` sale **solo** del maestro
(`pipelines/config/artists/`), nunca del texto libre de una casa. La forma legítima de
aprovechar esta curaduría es proponer altas al maestro con
`scripts/artist_master_propose.py`, revisadas a mano — no volcarla en el lote.

La hoja `Artistas` del Excel (423 artistas con país, nacimiento y muerte) es exactamente
el input de ese proceso. De los 441 artistas distintos de Lefebre, 68 ya estaban en el
maestro y 369 son candidatos.

## Lo que se descarta a propósito

`Se cuenta?`, `Aplica ARR?`, `Vivo?`, `Muerto hace cuanto?` y `Foto?` son el análisis de
**derecho de participación (ARR)** de la hoja original, no hechos de la subasta. Meterlas
en `LotItem` mezclaría dos modelos distintos.
