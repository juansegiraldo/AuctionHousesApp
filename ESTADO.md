# Estado del proyecto

Actualizado: 2026-08-01

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
python -m pytest        # 56 pasan, 1 se salta
```

## Las cifras hoy

| Casa | Lotes | Vendidos | Tasa | Ingresos (nativa) | ≈ EUR |
|---|---|---|---|---|---|
| duran_subastas | 40.442 | 18.624 | 46,1% | 23.450.015 EUR | 23,45 M € |
| bogota_auctions | 9.099 | 9.045 | 99,4% | 31.215.260.000 COP | 7,24 M € |
| **Total** | **49.541** | **27.669** | — | — | **30,69 M €** |

Cobertura temporal: 2014 → 2026.

### Qué es aproximado (léelo antes de citar una cifra)

1. **La conversión a EUR.** Tasa estática de `pipelines/config/fx.yaml`, no histórica por
   fecha. Sirve para comparar casas entre sí; **no** para valoración contable. Los datos
   abarcan 2014-2026 y el COP se movió mucho en ese periodo.
2. **La tasa de venta NO es comparable entre casas.** Bogotá da 99,4% porque su web
   publica casi solo lotes vendidos (faltan ~1.764 números de lote de las secuencias).
   Durán publica también los `NO VENDIDO`, y por eso da 46,1%. Comparar ambas es un error.
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
