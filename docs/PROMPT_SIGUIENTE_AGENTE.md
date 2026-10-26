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

## Hecho en la sesión del 2026-10-26 (tareas 1-3 de la versión anterior de este prompt)

- **Silver ahora se queda con la copia MÁS NUEVA** de cada lote, y dentro de una partición lee
  `historic_all_lots.jsonl` el último. Cambiarlo no movió ningún campo en los 85.684 lotes. Los
  1.018 lotes de Zorrilla "sin artista" no dependían de la partición: salían de un
  `historic_all_lots.jsonl` que se concatenó antes de re-scrapear 13 subastas. Hay tests para las
  dos reglas. `_full_bogota_name()` **sigue haciendo falta**, porque el output de Bogotá aún dice
  `Fernando` (sus subastas antiguas nunca se re-scrapearon).
- **A Zorrilla le falta ~11% de sus lotes**: `LOTS_PER_PAGE` valía 28 y cada página aporta 24. El
  código está arreglado y tiene test, pero **no se ha re-scrapeado**: LiveAuctioneers ya no incrusta
  `window.__data` y bloquea con Incapsula a la segunda petición. Ver CLAUDE.md, "Known issues".
- **Maestro: 3.584 artistas** (+Robert Henri, +Myra Landau). En el top 200 quedan 2 huecos
  deliberados, Gómez Mayorga y Raymundo Martínez: solo hay páginas de galerías como fuente.
- **App publicada** con Morton en la misma URL: https://claude.ai/artifact/9vJLvbfstaWdA3638vqAF1
  (versión 3).

Las cifras de la tabla de arriba no cambiaron: 65.276.288,00 EUR, 45.628 vendidos. `pytest`: 965.

## Tareas pendientes, por prioridad

### 1. Adaptar el scraper de Zorrilla a la LiveAuctioneers de hoy (decidirlo con el dueño)

Es lo que recupera el ~11% que falta (~1.300 lotes). Exige otra fuente de datos (la página ya no
trae `window.__data`; la de la casa trae JSON-LD `SaleEvent` sin número de lotes) y pasar el
bloqueo de Incapsula. Es un proyecto, no un parche: pregunta antes de empezar. Cuando funcione,
añade un `scripts/verify_zorrilla_scrape.py` como el de Morton, que compare con `lotsListed`.

### 2. Descargas CSV dentro del Artifact (opcional)

El visor de Artifacts bloquea las descargas por `blob:`. Hoy la app cae a abrir el CSV en otra
pestaña o copiarlo al portapapeles. Se arreglaría declarando la capacidad `downloads` y usando
`window.claude.downloads.save(...)` **solo si existe**: la misma carpeta tiene que seguir sirviendo
en Vercel sin cambios.

### 3. Menores

- Durán tiene 2 lotes con artista "Juan Antonio": es la misma obra ofrecida dos veces, Durán la
  publica sin apellido y la venta no trae precio. No es investigable ni mueve un euro. Déjalo.
- Las "Subastas de los Sábados" de Morton (115) mezclan arte con muebles. Si el dueño quiere más
  volumen de Morton, hay que decidir con él si se filtra por lote. No es una tarea técnica.
- Re-scrapear las subastas antiguas de Bogotá con el parser arreglado permitiría quitar
  `_full_bogota_name()` (con un test que demuestre que Botero sigue el #1).

## Trampas de entorno que costaron tiempo

- **Windows**: los scripts que imprimen nombres necesitan `sys.stdout.reconfigure(encoding="utf-8")`,
  o revientan con `UnicodeEncodeError`.
- `run_all.ps1 *> fichero.log` escribe UTF-8 con BOM. Léelo con `decode("utf-8-sig")`, no como UTF-16.
- **TLS**: Python en esta máquina no tiene la raíz Sectigo E46 del BCE. `fx_fetch_history.py` ya usa
  `certifi`. Haz lo mismo si añades descargas.
- **Wikidata** devuelve 429 si encadenas consultas: deja 1-1,5 s entre llamadas.
- Los tests van **al final** de `run_all.ps1`, nunca con Gold a medio reconstruir.
- Bronze es inmutable: los arreglos sobre datos ya cargados van en Silver (ver tarea 1).
