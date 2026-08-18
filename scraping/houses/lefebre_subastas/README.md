# Lefebre Subastas

**La única casa con dos fuentes conviviendo**, y no por descuido: cada una cubre un
periodo que la otra no puede.

| Fuente | Subastas | Lotes | Periodo |
|---|---|---|---|
| `from_excel.py` — hoja curada a mano en 2024 | 11 (18–26, Barranquilla, prueba) | 1.037 | 2021 → 2023 |
| `parsers.py` + runners — API de Auction Mobility | 19 (27–38, Pereira ×2, Barranquilla ×3, Libros, Seriados) | 2.821 | 2023 → 2026 |

**3.858 lotes · 30 subastas · 2021–2026 · COP.** Las dos escriben `*.jsonl` en el mismo
`output/`, y a partir de ahí Lefebre es indistinguible del resto del pipeline: Bronze solo
copia `*.jsonl` del `output_dir` y **nunca importa el módulo de la casa** — ese es el
resquicio por el que entra una fuente que no es un scraper.

```powershell
# Fuente 1: el Excel. Se ejecuta a mano y una sola vez (ya está hecho).
python -m scraping.houses.lefebre_subastas.from_excel --excel FINALL.xlsx

# Fuente 2: el scraper. Baja solo lo que falta; el resume salta lo ya descargado.
python -m scraping.houses.lefebre_subastas.run_historic --list-only
python -m scraping.houses.lefebre_subastas.run_historic --quick

# Verifica cualquier scrape contra el total que declara la propia casa.
python scripts/verify_lefebre_scrape.py
```

## Por qué NO se re-scrapean las 11 del Excel

La web tiene esas 11 subastas con **890 lotes más**. Parece que falta casi la mitad del
dato. **No es así, y traerlos sería un error:**

| | Lotes | Con paréntesis biográfico |
|---|---|---|
| **Guardados** en el Excel | 1.037 | **969 (93,4%)** |
| **Descartados** | 890 | **8 (0,9%)** |

Un descarte por prisa sería aleatorio y los dos porcentajes se parecerían. Un 93% frente a
un 1% solo sale de un criterio aplicado a conciencia: *quedarse con el arte de artista
atribuido*. De los 890 descartados, el **51% es mobiliario, joyería y objetos decorativos**
(cuberterías Christofle, vajillas Rosenthal, jarrones Lalique, sillas Versace, espejos,
baúles, brújulas) y un 5% más son obras anónimas (`Escuela Quiteña`, `Escuela colonial`).
De los 1.037 guardados, solo el 1% es mobiliario.

Lefebre es una casa **generalista**; el Excel es su **subconjunto de arte**. Scrapear esas
11 subastas no recupera dato perdido: mete 890 lotes de mobiliario en una base curada como
base de arte y rompe las métricas por artista. Por eso están en
`parsers.EXCEL_ONLY_AUCTIONS`, con un test que lo fija.

Los 8 descartados con fecha tampoco son olvidos claros: dos son **libros** sobre Vásquez de
Arce (no obra suya), uno es una **silla de 1940** cuyo "(1940)" es la fecha del mueble, dos
son Escuela Quiteña con fecha de época. Solo **dos Camilo Sanín** (subastas 24 y 26) parecen
omisiones genuinas, y ninguno se vendió.

## La fuente del Excel

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

---

# El scraper (subastas 27 → 38 y siguientes)

## La web parece vacía, pero no lo está

`auction.lefebresubastas.com` corre sobre **Auction Mobility**, una SPA de Angular. Bajar
`/auctions/past` con `curl` devuelve *"no hay subastas anteriores"* y parece que no hay
nada que scrapear — la misma trampa que Zorrilla. El contenido se rellena en cliente.

**No hace falta navegador headless.** Hay dos resquicios:

1. El listado de subastas viene **renderizado en servidor** dentro del blob `viewVars` del
   propio HTML (igual que el `window.__data` de Zorrilla). Ojo: la página 1 solo trae 20 de
   las 29 pasadas, hay que pedir `?page=2`.
2. Los lotes salen del **proxy AJAX del propio sitio, sin autenticación**:

   ```
   GET /ajax/lots/<codigo>?limit=100
   ```

El backend directo (`production4-server.auctionmobility.com/v1/...`) devuelve **401** con
cualquier cabecera que se pruebe, incluida la `amRegistrationKey` que la propia página
publica. Hay que pasar por el proxy — y por eso `next_page_url()` reescribe el `next_page`
que trae el JSON, que apunta al backend con 401.

## El oráculo de verificación

El resumen de cada subasta publica `total_hammer_price` y `sold_lot_count`. La suma de los
precios de los lotes **cuadra exactamente** con eso: comprobado en **19/19 subastas**. Es
un oráculo gratis que detecta paginación incompleta, lotes perdidos por un timeout y
errores de conversión de precio, sin depender de ninguna fuente externa:

```powershell
python scripts/verify_lefebre_scrape.py
```

## Tres trampas

**1. El `lot_url` lleva doble barra, y es a propósito.** Los 674 lotes que ya estaban en
Silver se guardaron como `https://auction.lefebresubastas.com//lots/view/...`, que es lo
que sale de `BASE_URL + "/" + _detail_url` (el `_detail_url` ya empieza por `/`). Reproduce
**89/89** las URLs existentes de subasta-30. Un `urljoin()` "correcto" daría barra simple,
no casaría con nada de lo ingerido y **Silver duplicaría cada lote re-scrapeado**. Hay un
test que lo fija.

**2. El `auction_id` es el slug, no el código.** `run_historic_cli` nombra el fichero de
salida con `_auction_id_from_url()`. Devolver `4-DLG0WK` en vez de `subasta-30` crearía un
`4-DLG0WK.jsonl` al lado del que dejó el Excel: el mismo dato en dos ficheros, con
`lot_url` idénticos, y el resume no volvería a saltárselo nunca.

**3. El fetcher traduce la URL de la subasta al catálogo.** El engine arranca con
`fetch(auction_url)`, y esa URL es la ficha pública (la SPA), que no trae ni un lote.
`lefebre_fetcher` la reescribe a `/ajax/lots/<codigo>` antes de pedirla. Por eso
`auction_code_from_url()` exige la forma `4-XXXXXX` y no acepta cualquier segmento: si no,
`/auctions/past` se leería como código `past` y rompería el descubrimiento del histórico.

## Solo hay artista si hay paréntesis biográfico

Lefebre ya no vende solo arte: hay **joyería, relojes, mobiliario y vinilos**. Con la
heurística "la primera línea es el artista" salen pintores llamados `Solitario de Diamante`,
`Anillo Tiffany's en oro blanco` o `DURA DURAN` — el mismo defecto que `_OBJECT_NAMES`
filtra para Bogotá (`Cartel` con 85 lotes, `Collar`, `Florero`).

`artist_from_title()` **solo acepta el nombre cuando va seguido del paréntesis con fechas**.
De los 2.821 lotes scrapeados, 1.564 (55%) tienen artista y 1.257 no. Esos 1.257 **entran
igual al pipeline** con `artist_name` a `None`: así se conserva la facturación real de la
casa sin contaminar el ranking de artistas, y es filtrable después sin re-scrapear. El
bloque crudo se guarda en `description`, así que nada se pierde.

`subasta-de-libros-y-vinilos` (162 lotes) queda entera sin artista, que es lo correcto: son
discos, no cuadros.

**Esta regla no es una heurística inventada: es la que el curador aplicó a mano en 2024**
(93,4% de lo guardado con paréntesis frente al 0,9% de lo descartado). La única diferencia
es que en 2024 el no-arte se descartaba y aquí entra sin artista.

## Trampa del resume tras un timeout

Heredada del framework y documentada también en Zorrilla: el resume salta las subastas cuyo
`.jsonl` ya existe, pero una subasta que expira **deja un fichero parcial**. Al relanzar, el
resume lo da por completo y esos lotes se pierden en silencio. Tras un `auction_timeout`,
**borrar el `.jsonl` y el checkpoint de esa subasta** antes de relanzar.

`verify_lefebre_scrape.py` detecta justo eso: un fichero parcial no cuadra con el
`total_hammer_price` de la casa.

## Re-scrapear una subasta ya descargada

El resume va por existencia de fichero y no hay flag para forzarlo (añadirlo tocaría el CLI
compartido de las cuatro casas). Para rehacer una subasta, se borra su fichero y se relanza:

```powershell
Remove-Item scraping\houses\lefebre_subastas\output\subasta-38.jsonl
Remove-Item scraping\houses\lefebre_subastas\output\checkpoints\subasta-38.json
python -m scraping.houses.lefebre_subastas.run_historic --quick
```

Así se re-scrapearon 27/28/29/30, que venían del Excel sin imágenes ni número de lote. Sus
importes no cambiaron (subasta-30 sigue en 864.800.000 COP) y ganaron los dos campos.

## Por qué `--quick` siempre

El payload del catálogo ya trae precio, estado, título, número de lote e imagen, y
`/ajax/lot/<row_id>` devuelve `{response, responseCode}` sin ningún campo útil. Bajar una
página por lote añadiría ~2.800 peticiones para nada. `parse_lot_page()` devuelve `{}` a
propósito.
