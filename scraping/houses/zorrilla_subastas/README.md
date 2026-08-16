# Zorrilla Subastas (Montevideo, Uruguay)

Tercera casa del pipeline y **primer consumidor real del framework `scraping/common/`**:
aquí no hay código de orquestación, retry, resume ni escritura JSONL — todo eso lo pone el
engine compartido. La casa son `parsers.py` + `house.py` + 3 shims de ~15 líneas.

## Por qué la fuente es LiveAuctioneers y no zorrilla.com.uy

El sitio propio **despublica los lotes después de cada remate** (verificado 2026-08-01 con
navegador real, no es falta de JS):

| Ruta | Resultado |
|---|---|
| `zorrilla.com.uy/subastas-anteriores/` | 200 OK, lista 70 subastas |
| cada subasta histórica | **"No se encontraron resultados", 0 lotes** |
| `/subastas/venta-directa/` | 51 productos, precio fijo (no de remate) |

`StealthyFetcher` sí vence el 403 de Cloudflare del sitio propio, pero eso no sirve de nada:
el dato no está publicado. LiveAuctioneers conserva el histórico completo **con precio de
remate y sin login**.

También se evaluó **Castells** (la casa #1 de Uruguay, fundada 1835): con render JS sí lista
sus remates, pero el HTML no contiene ningún importe y la navegación es por postback GeneXus
con URLs encriptadas. Descartada.

## Cómo se extraen los datos

LiveAuctioneers es React y la UI muestra "See Sold Price" en lugar del número, pero la página
embebe **`window.__data`** con el registro completo de cada lote, `salePrice` incluido.

Se lee ese JSON en vez del DOM porque es más estable que las clases de React. Para extraerlo
se usa `json.JSONDecoder().raw_decode`, **no** una regex terminada en `};`: el payload tiene
llaves anidadas y cualquier regex no-greedy corta a mitad (`Extra data` en `json.loads`).

Mapeo al modelo común:

| `window.__data` | `LotItem` |
|---|---|
| `salePrice` (si `isSold`) | `price_sold` |
| `lowBidEstimate` / `highBidEstimate` | `price_estimate_min` / `_max` |
| `isSold` | `status` = `VENDIDO` / `NO VENDIDO` |
| `lotNumber` (`"0462"`) | `lot_number` (int) |
| `saleStartTs` (epoch) | `auction_start_date` (ISO) |

## Volumen

**45 catálogos, ~12.500 lotes, 2019-05 → 2023-08.** Incluye arte uruguayo
(«Uruguayan Art», «Uruguayan & international painting», «China Zorrilla Auction»), platería
gaucha, militaria, joyería y numismática.

## Comandos

```powershell
python -m scraping.houses.zorrilla_subastas.run_historic --list-only
python -m scraping.houses.zorrilla_subastas.run_historic --quick --workers 4
python -m scraping.houses.zorrilla_subastas.run_one_auction "https://www.liveauctioneers.com/catalog/214514/" --quick
```

**Usar siempre `--quick`.** El payload del catálogo ya trae precio, estimaciones, estado y
título, así que el fetch de detalle por lote no aporta nada y serían ~12.500 cargas de
navegador headless.

**El run completo tarda ~1,5 h y hay que dejarlo terminar.** Cada página tarda 10-40 s
(navegador headless) y son ~11 páginas por catálogo × 45 catálogos. Lanzarlo con un timeout
corto lo mata a media faena: el proceso muere **sin traceback**, con el log cortado en seco,
lo que parece un fallo del scraper y no lo es. Si un run termina antes de tiempo y no hay
`auction_failed` en el log ni checkpoints `failed`, sospecha del timeout del lanzador antes
que del código.

`--workers 1` es la configuración estable. Con varios workers aparece algún
`Page.goto: Page crashed` en catálogos grandes (167977 = MILITARIA, 467 lotes); esa página
descargada de forma aislada devuelve 200 y sus 27 lotes sin problema —con y sin
`network_idle`—, así que es contención entre navegadores, no un problema de la fuente.

> **Trampa del resume tras un timeout.** El resume salta las subastas cuyo `.jsonl` ya existe,
> pero una subasta que expira **deja un fichero parcial** (167977 quedó con 384 de 467 lotes).
> Al relanzar, el resume lo da por completo y esos lotes se pierden en silencio. Tras un
> `auction_timeout`, **borrar el `.jsonl` y el checkpoint de esa subasta** antes de relanzar:
>
> ```powershell
> python -c "import json,glob; [print(json.load(open(f))['auction_id']) for f in glob.glob('scraping/houses/zorrilla_subastas/output/checkpoints/*.json') if json.load(open(f))['status']=='failed']"
> ```

## El artista sale de la descripción, no de un campo

LiveAuctioneers **no publica campo de artista**: `title` es la descripción del objeto
("9K RED GOLD PENDANT"). Pero en los catálogos de arte la descripción sigue un patrón fijo
del que `_artist_from_description()` saca nombre, años y escuela:

```
SOLARI, Luis Alberto (Uruguayan school, 1918-1993). Color engraving. "Mr. John Wafflen."
Cuadro de José Gurvich (1927-1974). Óleo sobre tela. "Puerto con barco."
```

Dos trampas que costó ver, ambas cubiertas por tests:

- Las descripciones **en español** empiezan por el tipo de objeto, no por el autor. Sin quitar
  ese prefijo el ranking se llena de entradas como *"Cuadro de Eduardo Mac Entyre"*.
- En joyería el paréntesis es una **medida**, no una biografía: *"Collar de 3 hilos de perlas
  (8.7 mm diámetro promedio)"*. Por eso se exige que el paréntesis traiga años o escuela.

Extrae artista en ~39% de los lotes de arte. `artist_country` es solo diagnóstico:
**el país lo pone el maestro** (`pipelines/config/artists/`), nunca el scraper — regla del
repo, no un descuido. Por eso hubo que añadir los artistas uruguayos al maestro; sin eso
quedaban sin país aunque la casa lo publicase.

## Trampas conocidas

- **`--quick` no es "modo rápido incompleto" aquí.** En las otras casas se salta datos; en
  ésta no, porque el detalle ya viene en el listado.
- **La página de la casa está paginada**: la 1 solo trae 24 de los 45 catálogos. `fetch_historic`
  recorre `?page=N` hasta que no aparecen nuevos. Sin eso se pierde todo 2019-2020.
- **Cada página de catálogo repite ~3 lotes promocionados.** No es un bug; el engine deduplica
  por `lot_url`.
- **La página incluye "Similar Items" de otras casas.** `parse_auction_page` filtra por
  `sellerId == 6727`; sin ese filtro se cuelan lotes ajenos en el catálogo.
- **`str(page)` devuelve solo `"<200 url>"`** con scrapling. El HTML real está en
  `page.html_content` (lo maneja `_page_html`).
- **Moneda:** LiveAuctioneers normaliza a **USD** en origen. La casa opera en Montevideo y pudo
  rematar en UYU, pero ese importe no existe en la fuente. Gold emite el flag
  `currency_normalized_at_source` para que nadie lea esos USD como moneda de martillo.
- **Solo 13 de los 45 catálogos son de arte.** El resto es joyería, militaria, platería gaucha,
  numismática y mobiliario. Si vuelves a scrapear para enriquecer datos, filtra primero: son
  2.641 lotes en vez de 11.166 (**76% menos trabajo**). Los de arte son los que llevan
  "Uruguayan Art", "painting", "Decorative Arts" o "JEWELRY & ART" en el título del catálogo.
- **`--quick` descartaba `description` hasta 2026-08-01.** `_lot_from_preview` en
  `scraping/common/runner.py` copiaba solo precio/estado/título, así que un listado que ya trae
  la descripción la perdía entera. Corregido para copiar también `description`, `artist_*`,
  `medium`, `dimensions` y `provenance`. Si ves lotes sin descripción, son de antes del fix.
