# Estado del proyecto

Actualizado: 2026-11-13

## Qué es esto (y qué no es)

Un **pipeline de datos por lotes**: scrapea casas de subastas y refina los resultados por
capas (bronce → plata → oro) hasta producir un **informe HTML**.

**No hay backend, ni API, ni frontend web.** Si buscas eso y no lo encuentras, no te has
vuelto loco: se borraron del disco. No están perdidos — viven en git:

```powershell
git show 765841b --stat              # ver qué había
git checkout 765841b -- backend/     # recuperarlo si algún día hace falta
```

Se borraron `backend/` (FastAPI), `frontend/` (Next.js), `database/`, `docker-compose.yml`
y `Makefile`. El proyecto se reconstruyó alrededor del scraping y los pipelines.

## Dónde está el "front"

Aquí:

```powershell
python -m http.server -d data\gold\app    # y abre http://localhost:8000
```

Esa carpeta **es** la interfaz: una app pensada para el móvil (`index.html` + `lots.json` +
`cards.json`) que se regenera con el pipeline. Hay que servirla, no abrirla con doble clic:
las fichas y el detalle de lotes se cargan con `fetch`, que el navegador bloquea en `file://`.
Se publica tal cual como Artifact de Claude o en Vercel (`vercel deploy data/gold/app`).
El antiguo `analytics_report.html` (Plotly) se retiró: dos renderers del mismo dato acababan
diciendo cosas distintas.

## Cómo regenerar todo

Un solo comando, desde la raíz del repo:

```powershell
.\scripts\run_all.ps1
```

Ejecuta en orden: bronce → copia a Supabase → plata → control de volumen → enriquecimientos
→ oro → informe, y termina con las puertas de calidad, que ahora **detienen la corrida** si
una casa no las pasa. Las etapas se lanzan como **módulos** (`python -m pipelines...`)
porque importan de `pipelines.shared`. Cada corrida deja su log en `logs/`.

Tests:

```powershell
python -m pytest        # 985 pasan
```

## Dónde están los datos (y cómo recuperarlos)

Desde el 2026-11-13 los lotes ya no viven solo en este disco. Hay tres copias:

1. **Este disco**: la copia de trabajo (`scraping/houses/*/output/` y `data/`).
2. **Supabase**, tabla `auction.raw_lots` del proyecto de entrenamiento: cada versión de cada
   lote tal como salió del scraper. 90.089 lotes. **Nadie puede borrar ni modificar ahí**, ni
   siquiera el pipeline: solo se añade.
3. **Supabase Storage**, bucket privado `auction-archive`: lo que no es lote y no se puede
   volver a generar (el Excel de Lefebre y la investigación de artistas).

Si se pierde el disco:

```powershell
python -m scripts.db_restore --out .     # baja todo lo scrapeado desde Supabase
.\scripts\run_all.ps1                    # reconstruye plata, oro y la app
```

Para comprobar que la copia sirve, sin tocar nada (tarda 2 minutos; pasó el 2026-11-13 con
cero diferencias en los 90.089 lotes):

```powershell
python -m scripts.db_restore --out C:\Temp\prueba --check
```

Supabase está en el **plan gratuito**: no hace copias de seguridad por su cuenta y pausa el
proyecto tras 7 días sin actividad (hoy lo mantiene despierto la sincronización de Garmin).
Por eso existen las tres copias. Tras guardar algo irreemplazable nuevo, lanza
`python -m scripts.archive_to_storage`.

**Supabase no es un backend.** La app sigue siendo estática y no consulta la base.

## Qué pasa ahora cuando algo falla

Antes estos fallos pasaban en silencio; ahora cortan la corrida y lo dicen:

- **Un scrape cortado a medias** deja un fichero `.part` y se repite en la siguiente corrida.
  Antes quedaba un fichero incompleto que se daba por bueno para siempre.
- **Un re-scrape que trae menos datos que el anterior** (falló la página de detalle y solo
  quedó el catálogo) detiene la carga si afecta a más del 1 % de una casa.
- **Plata con menos lotes de una casa que Supabase** detiene la corrida: algo se perdió.
- **Falta un fichero intermedio**: error con el nombre del fichero y la etapa que lo genera.
  Antes salía una app con 0 lotes o con todo clasificado como "other".
- **Sin conexión**: la copia a Supabase avisa, queda pendiente y el resto sigue.

## Las cifras hoy

| Casa | País | Lotes | Vendidos | Tasa | Ingresos (nativa) | ≈ EUR |
|---|---|---|---|---|---|---|
| duran_subastas | España | 51.788 | 23.908 | 46,2% | 29.180.695 EUR | 29,18 M € |
| morton_subastas | México | 12.838 | 4.742 | 36,9% | 481.195.909 MXN | 23,43 M € |
| bogota_auctions | Colombia | 10.437 | 10.395 | 99,6% | 35.245.120.000 COP | 8,01 M € |
| zorrilla_subastas | Uruguay | 11.168 | 6.942 | 62,2% | 4.365.109 USD | 3,92 M € |
| lefebre_subastas | Colombia | 3.858 | 1.600 | 41,5% | 12.361.725.000 COP | 2,76 M € |
| **Total** | | **90.089** | **47.587** | — | — | **67,30 M €** |

Cobertura temporal: 2014 → 2026. De Morton solo están sus **57 subastas de arte** (de 803: el
resto son camiones, coches, vinos y joyas); ver `scraping/houses/morton_subastas/README.md`.

### Qué es aproximado (léelo antes de citar una cifra)

1. **La conversión a EUR.** Tasa media del MES de cada subasta (`pipelines/config/fx_history.yaml`:
   BCE para USD y MXN, TRM para COP). Sirve para comparar casas entre sí; **no** para valoración
   contable.
2. **La tasa de venta NO es comparable entre casas.** Bogotá da 99,4% porque su web
   publica casi solo lotes vendidos (faltan ~1.764 números de lote de las secuencias).
   Durán, Zorrilla, Lefebre y Morton publican también los no vendidos (46%, 62%, 42% y 37%) y sí
   son comparables entre sí. Comparar cualquiera de ellas con Bogotá es un error.
3. **1.133 lotes de Bogotá no traen estado explícito**: se infiere "vendido" por tener precio.
4. **1.202 lotes en subastas sin fecha en el título** quedan agrupados como `unknown`.
5. **2.672 lotes de Durán son tienda online** (venta directa permanente), no subastas: no
   tienen fecha por naturaleza y quedan fuera de la serie temporal.

Todo esto aparece también en el panel de avisos del propio informe.

## Deuda técnica conocida

- **~~El parser nuevo de Bogotá no extrae `status`~~ — era falso (comprobado 2026-10-12).**
  `scraping/houses/bogota_auctions/parsers.py` es un `import *` del legacy, así que extrae
  `status` igual. El fallo real era otro: `import *` no reexporta los nombres con `_`, y los tres
  runners de Bogotá morían con `ImportError`. Arreglado y cubierto por un test.
- **~~Acentos corruptos~~ — era la consola de Windows, no los datos** (comprobado 2026-08-01). En
  plata no hay ni un carácter roto: `Álvaro Barrios` está bien guardado y la app lo pinta bien. Lo
  que parecía corrupto era la consola sin UTF-8. La excepción es Morton (ver más abajo).
- **~~Bogotá cortaba nombres de artista al nombre de pila~~ — arreglado el 2026-10-25.** "Fernando"
  por Fernando Botero, "Edgar" por Edgar Negret: el parser confundía el apellido con el país. Botero
  recupera *La plegaria* y vuelve al puesto 1.
- **~~Plata se queda con la copia MÁS ANTIGUA de cada lote~~ — arreglado el 2026-10-26.** Ahora gana
  la copia más nueva, así que un arreglo del scraper sí llega a los lotes ya cargados. Cambiarlo no
  movió ni un dato en los 85.684 lotes. Los 1.018 lotes de Zorrilla que daban miedo no dependían del
  orden: salían de un fichero resumen (`historic_all_lots.jsonl`) que quedó desfasado. Ese fichero
  ahora se lee el último.
- **A Zorrilla le falta ~11% de sus lotes.** El scraper no pedía la última página de casi ningún
  catálogo (la subasta "Uruguayan Art" tiene 149 lotes y llegaron 144). El fallo está arreglado en
  el código, pero hoy no se puede volver a bajar: LiveAuctioneers cambió su web y bloquea el robot.
  Hasta entonces las cifras de Zorrilla se quedan cortas.
- **Morton trae los acentos rotos en su propia web** (títulos de 2021-2023), a diferencia de Bogotá
  y Durán, donde era la consola. El parser de Morton los repara al leer.
- **`subasta-541-marzo-2107`**: errata en la web de Durán (2107 en vez de 2017). El extractor
  de año la rechaza en vez de inventarse un año, así que esos 315 lotes caen en `unknown`.
- Quedan copias legacy de los scripts en la raíz de `scraping/` junto a la estructura nueva
  `scraping/houses/`.
- Bronce guarda una copia completa por cada día de ingesta (39 particiones entre las cinco casas, ~1,4 GB). Es
  seguro —plata deduplica por `lot_url`— pero ya es redundante: Supabase tiene todas las
  versiones. Se pueden borrar las particiones viejas dejando las dos últimas de cada casa.
- **No hay tabla consultable en Supabase** (solo el registro crudo). Se dejó fuera a propósito:
  ocuparía ~150 MB más de un plan de 500 MB y hoy nada la usaría.

## La decisión pendiente

El informe ya es fiable. Ábrelo y decide:

- **¿Me basta?** → listo. Programa el pipeline y el HTML es el producto.
- **¿Quiero filtrar y buscar?** → Streamlit o Evidence sobre `data/gold/*.jsonl`. Sin base
  de datos ni API.
- **¿Quiero que otros lo consulten en vivo?** → entonces sí, restaurar el backend desde
  `765841b`, pero reconstruido sobre este pipeline, no sobre los supuestos viejos.
