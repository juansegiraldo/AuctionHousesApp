# AuctionHousesApp

Pipeline de datos que scrapea casas de subastas latinoamericanas y españolas, y refina los
resultados por capas (bronce → plata → oro) hasta producir un **informe HTML de analítica**.

**No es una aplicación web.** No hay servidor que arrancar, ni API, ni base de datos. El
producto final es un fichero HTML que abres en el navegador. Si buscas el `backend/` o el
`frontend/`, lee [ESTADO.md](ESTADO.md).

## Empezar

```powershell
python -m venv venv; venv\Scripts\activate
pip install -r scraping/requirements.txt
pip install requests pyyaml pytest

.\scripts\run_all.ps1                    # reconstruye todo el pipeline
start data\gold\analytics_report.html    # abre el informe
```

Todos los comandos se ejecutan **desde la raíz del repo**. Requiere Python 3.13.

## El informe

`data/gold/analytics_report.html` es la interfaz: KPIs, treemap de ingresos por casa y
subasta, gráficos por año, tablas de detalle y un **panel de avisos de calidad** que declara
qué cifras son aproximadas y por qué.

Cifras actuales (2014-2026):

| Casa | Lotes | Vendidos | Tasa | Ingresos (nativa) | ≈ EUR |
|---|---|---|---|---|---|
| duran_subastas | 40.442 | 18.624 | 46,1% | 23.450.015 EUR | 23,45 M € |
| bogota_auctions | 9.099 | 9.045 | 99,4% | 31.215.260.000 COP | 7,24 M € |
| **Total** | **49.541** | **27.669** | — | **—** | **30,69 M €** |

> **Dos salvedades importantes.** Cada casa cotiza en su propia moneda: los totales en EUR
> usan una tasa **estática y aproximada** ([pipelines/config/fx.yaml](pipelines/config/fx.yaml)),
> válida para comparar casas pero no para valoración contable. Y la **tasa de venta no es
> comparable entre casas**: Bogotá publica casi solo lotes vendidos, Durán publica también
> los no vendidos. El informe avisa de ambas cosas.

## Comandos

```powershell
python -m pytest                         # 56 tests
.\scripts\run_all.ps1                    # pipeline completo, en orden

# Etapas sueltas (como módulos: importan de pipelines.shared)
python -m pipelines.bronze.ingest
python -m pipelines.silver.build_silver
python -m pipelines.enrichments.currency_normalize
python -m pipelines.gold.build_gold
python -m pipelines.analytics.report_gold

# Puertas de calidad (informan; con --fail-on-violation abortan)
python pipelines/silver/quality_gates.py --house-slug duran_subastas

# Scrapers (también como módulos)
python -m scraping.houses.duran_subastas.run_historic --list-only
python -m scraping.houses.bogota_auctions.run_auction_list --file urls.txt
```

## Estructura

```
scraping/          Un subpaquete por casa + framework común (scraping/common/)
  houses/
    registry.json  Fuente de verdad: slug → módulo → carpeta de salida
pipelines/         Transformación medallion sobre data/
  bronze/          Aterrizaje crudo, inmutable
  silver/          Normaliza + deduplica por lot_url
  enrichments/     Trabajos independientes por dedupe_key
  gold/            Agregados analíticos + avisos de calidad
  analytics/       Renderiza el informe (solo lee gold)
  shared/          fx.py (monedas), schema.py (año, vendido)
  config/          houses.yaml, fx.yaml
semantic_layer/    Definiciones de negocio en YAML (metadatos, no se ejecutan)
data/              Salidas del pipeline — todo gitignored
tests/             56 tests; los de parsers usan fixtures HTML offline
```

## Documentación

- [ESTADO.md](ESTADO.md) — qué existe, qué se borró y dónde está, salvedades de los datos,
  deuda técnica conocida.
- [CLAUDE.md](CLAUDE.md) — guía de arquitectura para trabajar en el repo.
- [docs/SCALING_CHECKLIST.md](docs/SCALING_CHECKLIST.md) — añadir casas y ejecuciones masivas.
- [scraping/README.md](scraping/README.md) — detalle de los scrapers.

## Añadir una casa de subastas

Es una operación de registro, no de código de pipeline: creas
`scraping/houses/<slug>/` con `parsers.py` y los tres runners de interfaz común, y añades
la entrada en `scraping/houses/registry.json`. El pipeline la descubre sola. Detalle en
[docs/SCALING_CHECKLIST.md](docs/SCALING_CHECKLIST.md).
