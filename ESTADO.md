# Estado del proyecto

Actualizado: 2026-10-25

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

Ejecuta en orden: bronce → plata → enriquecimientos → oro → informe, y termina con las
puertas de calidad. Las etapas se lanzan como **módulos** (`python -m pipelines...`)
porque importan de `pipelines.shared`.

Tests:

```powershell
python -m pytest        # 941 pasan
```

## Las cifras hoy

| Casa | País | Lotes | Vendidos | Tasa | Ingresos (nativa) | ≈ EUR |
|---|---|---|---|---|---|---|
| duran_subastas | España | 47.383 | 21.949 | 46,3% | 27.154.575 EUR | 27,15 M € |
| morton_subastas | México | 12.838 | 4.742 | 36,9% | 481.195.909 MXN | 23,43 M € |
| bogota_auctions | Colombia | 10.437 | 10.395 | 99,6% | 35.245.120.000 COP | 8,01 M € |
| zorrilla_subastas | Uruguay | 11.168 | 6.942 | 62,2% | 4.365.109 USD | 3,92 M € |
| lefebre_subastas | Colombia | 3.858 | 1.600 | 41,5% | 12.361.725.000 COP | 2,76 M € |
| **Total** | | **85.684** | **45.628** | — | — | **65,28 M €** |

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
- **Acentos corruptos** en títulos y nombres de artista (`Álvaro` → `\udc81lvaro`): problema
  de codificación en el scraping. Se avisa en el informe pero no está corregido; arreglarlo
  bien exige re-scrapear o una pasada de reparación sobre bronce.
- **~~Bogotá cortaba nombres de artista al nombre de pila~~ — arreglado el 2026-10-25.** "Fernando"
  por Fernando Botero, "Edgar" por Edgar Negret: el parser confundía el apellido con el país. Botero
  recupera *La plegaria* y vuelve al puesto 1.
- **Plata se queda con la copia MÁS ANTIGUA de cada lote** que hay en bronce. Por eso un arreglo del
  scraper no llega solo a los lotes que ya existían, y el de Bogotá se aplica al construir plata.
  Cambiar el orden es el arreglo de verdad, pero hoy cambiaría 1.018 lotes de Zorrilla que hay que
  revisar antes. Detalle en CLAUDE.md.
- **Morton trae los acentos rotos en su propia web** (títulos de 2021-2023), a diferencia de Bogotá
  y Durán, donde era la consola. El parser de Morton los repara al leer.
- **`subasta-541-marzo-2107`**: errata en la web de Durán (2107 en vez de 2017). El extractor
  de año la rechaza en vez de inventarse un año, así que esos 315 lotes caen en `unknown`.
- Quedan copias legacy de los scripts en la raíz de `scraping/` junto a la estructura nueva
  `scraping/houses/`.
- Bronce tiene ahora dos particiones con contenido solapado (marzo y agosto). Es seguro: la
  capa plata deduplica por `lot_url`.

## La decisión pendiente

El informe ya es fiable. Ábrelo y decide:

- **¿Me basta?** → listo. Programa el pipeline y el HTML es el producto.
- **¿Quiero filtrar y buscar?** → Streamlit o Evidence sobre `data/gold/*.jsonl`. Sin base
  de datos ni API.
- **¿Quiero que otros lo consulten en vivo?** → entonces sí, restaurar el backend desde
  `765841b`, pero reconstruido sobre este pipeline, no sobre los supuestos viejos.
