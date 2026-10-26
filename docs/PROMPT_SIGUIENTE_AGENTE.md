# Prompt para el siguiente agente

Pega todo lo que hay debajo de la línea como primer mensaje de una sesión nueva en
`AuctionHousesApp/`. Escrito el 2026-10-26, al cerrar la sesión que añadió Morton Subastas.

---

Vas a continuar el trabajo en `AuctionHousesApp`, un pipeline de datos (scraping → bronze → silver →
gold) que alimenta una app móvil estática en `data/gold/app/`. La app la lee la pareja del dueño del
repo desde el móvil. El dueño escribe en español y prefiere explicaciones cortas, con un ejemplo
concreto, sin jerga.

**Antes de tocar nada, lee `CLAUDE.md` entero.** Recoge cada trampa que ya costó un error. Si vas a
tocar el maestro de artistas, lee también `docs/PLAN_MAESTRO_ARTISTAS.md` y
`pipelines/config/artists/README.md`.

## Qué se hizo en la sesión anterior (rama `feat/morton-subastas`)

- **Casa nueva: Morton Subastas (Ciudad de México, MXN)**, solo sus 57 subastas de arte de las 803
  que tiene (12.838 lotes, 2021→2026). Está en `scraping/houses/morton_subastas/`, y su `README.md`
  explica cada trampa: precios detrás de login sacados del JSON-LD, que un `Discontinued` con precio
  NO es una venta, mojibake real, fechas en hora de CDMX y registros reciclados con títulos de coche.
- **FX:** peso mexicano desde el BCE (`scripts/fx_fetch_history.py`, `fx_history.yaml` hasta 2026-10).
- **App:** color fijo por casa (`HOUSE_SERIES`; antes salía del puesto en ventas y Morton repintaba a
  las demás). Las fichas de artista ahora van por `artist_key`, no por posición, y `cards.json`/`lots.json`
  se piden con `?v=<huella>`. El fallo era que "tocar Tamayo abría a Obregón".
- **Maestro de artistas:** 58 fichas nuevas, 6 alias por inversión de coma y el país de Rodolfo
  Morales. Los artistas sin país del top 200 bajaron de 68 a 4, cada ficha con su fuente en `notes`.
- **Bogotá:** el parser del texto alt cortaba los nombres en el de pila ("Fernando" por Fernando
  Botero). Está arreglado en `scraping/parsers.py` y, para los datos ya cargados, en
  `pipelines/silver/artist_resolve._full_bogota_name()`.
- **Categorías:** "Con documento" ya no convierte una obra en `books_documents`.

Cifras de referencia al cerrar (si cambian sin motivo, algo se rompió):

| Casa | Lotes | Vendidos | Ingreso EUR |
|---|---|---|---|
| duran_subastas | 47.383 | 21.949 | 27.154.575,00 |
| morton_subastas | 12.838 | 4.742 | 23.434.298,54 |
| bogota_auctions | 10.437 | 10.395 | 8.011.261,34 |
| zorrilla_subastas | 11.168 | 6.942 | 3.919.315,22 |
| lefebre_subastas | 3.858 | 1.600 | 2.756.837,90 |
| **Total** | **85.684** | **45.628** | **65.276.288,00** |

`python -m pytest` → 963 en verde. Maestro: 3.582 artistas, 0 problemas de validación.

Los datos (`data/**`, `scraping/**/output/*.jsonl`) están en `.gitignore`: existen solo en esta
máquina. Si faltan, Morton se rehace con
`python -m scraping.houses.morton_subastas.run_historic --workers 6 --auction-timeout 7200`, que
tarda una hora. Después corre `python scripts/verify_morton_scrape.py` y `.\scripts\run_all.ps1`.

## Tareas pendientes, por prioridad

### 1. Silver se queda con la copia MÁS ANTIGUA de cada lote (lo más importante)

`pipelines/silver/build_silver.py` recorre las particiones de Bronze en orden de carpeta (la más
antigua primero) y gana la primera fila de cada `dedupe_key`. `pipelines/bronze/ingest.py` copia en
cada corrida TODO el output actual a la partición de hoy. Resultado: un re-scrape o un arreglo del
parser **no llega** a los lotes que ya existían. Hoy 9.099 lotes de Bogotá salen de la copia del
2026-03-07.

El arreglo natural es que gane la partición MÁS NUEVA, pero **no lo apliques a ciegas**. Medido el
2026-10-25 comparando la copia más antigua con la más nueva de cada lote:

- Bogotá, Durán, Lefebre y Morton: sin diferencias en `artist_name`, `price_sold`, `status`,
  `lot_title`, `auction_start_date` y `price_estimate_min`.
- **Zorrilla: 1.018 lotes** que en la copia del 2026-08-01 traen artista (p. ej. "Eduardo Mac
  Entyre") vienen **sin artista** en la más nueva.

Hay que averiguar por qué el output actual de Zorrilla perdió esos artistas. ¿Un re-scrape con un
parser anterior a `_artist_from_description()`? ¿Una corrida con `--quick` antes de que
`_lot_from_preview` copiara los campos descriptivos? Arréglalo en el origen y solo después cambia el
orden de Silver, con un test. Cuando esté hecho, `_full_bogota_name()` en `artist_resolve.py` deja de
hacer falta y se puede quitar, si un test demuestra que Botero sigue en el puesto 1.

Comprobación obligatoria antes y después: el ingreso total no se mueve, o la diferencia se explica
lote a lote.

### 2. Volver a publicar la app

`data/gold/app/` (`index.html`, `cards.json`, `lots.json`) cambió mucho y **no se ha vuelto a
publicar**. La URL que usa la pareja del dueño sigue enseñando la versión sin Morton. Busca el
Artifact existente con la herramienta Artifact (`action: list`), léelo y publica encima en la misma
URL, con los dos JSON como ficheros de apoyo. No crees uno nuevo: la pareja perdería el enlace.

### 3. Los 4 huecos que quedan en el top 200 (y el borde)

Robert Henri (un lote de Durán con una fecha de muerte que no cuadra), Guillermo Gómez Mayorga y
Raymundo Martínez (sin segunda fuente independiente) y **Myra Landau**, que entró por el borde (#200).
Usa el método de `docs/PLAN_MAESTRO_ARTISTAS.md` §2.4: `resolve_artist` primero, una fuente por ficha
con la URL en `notes`, y el hueco antes que un país inventado. Cada alta mueve el borde: no persigas
el puesto 200 indefinidamente.

### 4. Menores

- Durán tiene 2 lotes con artista "Juan Antonio" (el nombre viene así de su ficha, no es el fallo de
  Bogotá).
- En `ESTADO.md` sigue la viñeta antigua "Acentos corruptos", que contradice a CLAUDE.md (era la
  consola). Bórrala o reescríbela.
- Las "Subastas de los Sábados" de Morton (115) mezclan arte con muebles. Si el dueño quiere más
  volumen de Morton, hay que decidir con él si se filtra por lote. No es una tarea técnica.

## Trampas de entorno que costaron tiempo

- **Windows**: los scripts que imprimen nombres necesitan `sys.stdout.reconfigure(encoding="utf-8")`,
  o revientan con `UnicodeEncodeError`.
- `run_all.ps1 *> fichero.log` escribe UTF-8 con BOM. Léelo con `decode("utf-8-sig")`, no como UTF-16.
- **TLS**: Python en esta máquina no tiene la raíz Sectigo E46 del BCE. `fx_fetch_history.py` ya usa
  `certifi`. Haz lo mismo si añades descargas.
- **Wikidata** devuelve 429 si encadenas consultas: deja 1-1,5 s entre llamadas.
- Los tests van **al final** de `run_all.ps1`, nunca con Gold a medio reconstruir.
- Bronze es inmutable: los arreglos sobre datos ya cargados van en Silver (ver tarea 1).
