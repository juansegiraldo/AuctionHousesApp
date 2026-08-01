# Diseño: tasas de cambio históricas (COP / USD / EUR)

Fecha: 2026-08-01
Estado: aprobado, pendiente de plan de implementación

## Problema

Toda conversión a EUR usa hoy una **tasa estática única** (`pipelines/config/fx.yaml`,
`as_of: 2026-08-01`) aplicada a lotes de 2014 a 2026. Es justo el periodo en el que el peso
colombiano se devaluó de forma masiva:

- TRM oficial COP/USD: **1.938,89** el 2014-01-03 → **3.144,14** el 2026-08-01.
- La tasa actual **infravalora ~62%** las ventas de Bogotá de 2014.

Afecta a los 9.032 lotes COP de Bogotá y a los 11.168 lotes USD de Zorrilla. Los 40.442 de
Durán son EUR y no dependen de la tasa. El error no es cosmético: `agg_artist_metrics` y
`agg_country_metrics` comparan artistas *entre casas*, así que un artista vendido en Bogotá en
2014 aparece hoy un 62% más barato de lo que realmente se vendió.

## Alcance

Convertir a EUR usando la tasa del **mes de la subasta** en lugar de la tasa de hoy, con las
tasas históricas versionadas en git y sin que los pipelines toquen la red.

Fuera de alcance: cambiar `revenue_native` (sigue siendo exacto en moneda de la casa), tocar el
scraping, o modificar la regla de "nunca sumes precios entre casas sin pasar por EUR".

## Decisiones tomadas

| Decisión | Elección | Motivo |
|---|---|---|
| Fuente | Ficheros descargados y versionados en git | Reproducible y offline, como `fx.yaml` y `config/artists/` |
| Granularidad | **Mensual** | Es la granularidad más fina que las tres casas soportan de forma homogénea |
| Fecha no utilizable | **Fallback a la tasa estática actual**, contado en `quality_flags` | Decisión del propietario del repo: todo lote convierte siempre |

### Sobre el fallback (opción elegida frente a devolver `None`)

Un total en EUR mezclará importes bien convertidos con importes a tasa de 2026 sin que el número
lo delate. Se mitiga guardando `fx_method` **por lote** y publicando el recuento en
`quality_flags.jsonl` y en el informe: el fallback existe, pero queda contado, no invisible.

El impacto real es marginal — los lotes sin mes recuperable son mayoritariamente de Durán, que
es EUR (tasa 1.0 en cualquier caso).

**Ojo — el fallback es sólo por fecha ausente, no por moneda ausente.** Una moneda desconocida
sigue devolviendo `None`, nunca 1.0 ni tasa estática. Son dos fallos distintos y sólo uno tiene
respuesta razonable.

## Por qué dos fuentes

El BCE publica EUR→USD diario desde 1999, pero **no publica COP** (la serie
`D.COP.EUR.SP00.A` devuelve 404 — el peso colombiano no está en su lista de referencia).
Verificado el 2026-08-01.

El puente es `COP → USD` (TRM oficial de Colombia) y `USD → EUR` (BCE), usando en cada lado la
fuente canónica de esa moneda:

```
COP→EUR = (1 / TRM_COP_USD) × (1 / EURUSD_BCE)
```

## 1. Adquisición de datos

Script nuevo `scripts/fx_fetch_history.py`, ejecutado **a mano y rara vez**. No forma parte de
`scripts/run_all.ps1`: el pipeline nunca toca la red, lee siempre el fichero versionado.

- **EUR→USD**: `https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A`
  (`format=csvdata`, diaria). Requiere cabecera `User-Agent`.
- **USD→COP**: `https://www.datos.gov.co/resource/32sa-8pi3.json` (TRM Superfinanciera, diaria).
  El campo `vigenciadesde`/`vigenciahasta` cubre fines de semana con un solo registro.

Agrega ambas series a **media mensual**, compone COP→EUR, y escribe
`pipelines/config/fx_history.yaml`. Rango: **2013-01** (un año de margen antes del primer lote)
hasta el mes en curso. ~163 meses × 2 monedas.

```yaml
base_currency: EUR
generated_at: "2026-08-01"
sources:
  USD: "ECB SDW EXR D.USD.EUR.SP00.A (media mensual)"
  COP: "TRM Superfinanciera datos.gov.co 32sa-8pi3 x ECB EUR/USD (media mensual)"
rates_to_eur:
  USD:
    "2014-01": 0.7350
    "2014-02": 0.7326
  COP:
    "2014-01": 0.000379
    "2014-02": 0.000372
```

## 2. Módulo `pipelines/shared/fx.py`

Sigue siendo el **único punto de lectura** de tasas. Se le añade la dimensión temporal sin
romper lo existente:

```python
def to_eur_at(amount, currency, when) -> tuple[float | None, str]:
    """Convierte a EUR usando la tasa del mes de `when` ("YYYY-MM").

    Devuelve (importe, method) donde method es:
      "monthly"          -> tasa del mes exacto de la subasta
      "fallback_static"  -> sin fecha utilizable: tasa estatica de fx.yaml
      "unavailable"      -> moneda desconocida: importe None
    """
```

Devolver el método junto al importe es el mismo patrón que `extract_year()`, que devuelve
`(year, method)` para que el informe pueda avisar cuándo un dato fue inferido.

`to_eur()`, `rate_for()` y `fx_as_of()` **conservan su firma actual** y pasan a ser el camino
del fallback. No se borran: mantiene verdes los tests de `tests/pipelines/test_fx.py` y evita
tocar código que no lo necesita.

Reglas que el módulo respeta:

- **Moneda desconocida → `None`**, nunca 1.0 ni fallback estático.
- **EUR nunca se convierte**: tasa 1.0 en todos los meses, sin consultar el histórico.
- **Mes fuera de rango** (anterior a 2013-01 o posterior al último publicado) cae al mes más
  cercano disponible *dentro del histórico*, no a la tasa estática — sigue siendo un dato real.
  Se marca como `monthly`.
- Carga cacheada con `lru_cache`, como `load_fx()`.

## 3. Extracción del mes de subasta

Función nueva en `pipelines/shared/schema.py`, hermana de `extract_year()`:

```python
def extract_month(auction_start_date, auction_id=None) -> tuple[str | None, str]:
    """Devuelve ("YYYY-MM", method) o (None, "unknown")."""
```

Tres estrategias en orden, el patrón de `extract_year()`:

1. **ISO** — `"2022-03-03T20:00"` → `"2022-03"` (Bogotá, Zorrilla).
2. **Texto español** — `"Enero 2014"` → `"2014-01"`, con tabla de los 12 meses (Durán).
3. **`auction_id`** — `"subasta-504-enero-2014_504-001"` lleva mes y año en el slug.

Si ninguna funciona → `(None, "unknown")` y el llamante cae al fallback estático. El typo
`subasta-541-marzo-2107` no da un año válido (`extract_year` sólo acepta `19xx`/`20xx`), así que
esos 315 lotes caen al fallback — coherente con lo que ya hace `extract_year()` con ellos.

## 4. Integración en los pipelines

Los tres puntos que hoy llaman `to_eur()` pasan a `to_eur_at()` y guardan el método:

- **`pipelines/gold/build_gold.py:116`** — el lote ya tiene `auction_start_date` y `auction_id`
  a mano. Los agregados por casa ganan `fx_method_counts` y `fx_fallback_lots`. El
  `fx_rate_used` de la línea 180, hoy constante por moneda, pasa a ser el rango de tasas
  efectivamente aplicadas.
- **`pipelines/gold/build_insights.py:183`** — misma sustitución. Es donde más se nota, porque
  `agg_artist_metrics` compara artistas entre casas.
- **`pipelines/enrichments/currency_normalize.py:39-48`** — convierte precio y ambas
  estimaciones. Su `fx_source`, hoy `static_fx_2026-08-01`, pasa a ser por lote
  (`monthly_2014-01` / `static_2026-08-01`).
- **`pipelines/silver/quality_gates.py`** — nueva métrica `fx_historical_coverage` (% de lotes
  convertidos con tasa del mes). Informativa por defecto, como las de artistas, no bloqueante.

**Orden y consistencia**: `run_all.ps1` no cambia de orden. Pero como esto reescribe importes en
EUR en Gold y en enrichments, hace falta **rerun completo desde Gold**, no por partes — es el
escenario de drift que documenta CLAUDE.md (enrichments de marzo sobre un Silver de mayo).

## 5. Informe

- `fx_note()` deja de decir "tasa estática de 2026-08-01": explica la conversión mensual, cita
  las dos fuentes (BCE + TRM) y dice **cuántos lotes cayeron al fallback**.
- El panel de avisos de `render_html.py:1418` y `build_artifact.py:960` lo recoge desde
  `quality_flags.jsonl`, sin texto hardcodeado — la convención que ya sigue el repo.
- La etiqueta "Convertido a EUR · tasa {fecha}" (`render_html.py:119`,
  `build_artifact.py:407`) pasa a "Convertido a EUR · tasa del mes de subasta".

## 6. Semantic layer

`semantic_layer/metrics.yaml:30` declara hoy `sum(price_sold * fx_rate_to_eur(currency))`. Pasa
a `fx_rate_to_eur(currency, auction_month)`. Es metadata y no se ejecuta, pero CLAUDE.md pide
actualizarla **en la misma edición** que cambia el cálculo, porque ya se ha desincronizado dos
veces.

## 7. Tests

Todos offline, con un `fx_history.yaml` de fixture. Ninguno toca la red.

- `to_eur_at` con mes exacto, mes fuera de rango (→ mes más cercano, método `monthly`), fecha
  `None` (→ `fallback_static`), moneda desconocida (→ `None`, **no** fallback).
- `extract_month` en los tres formatos + el typo `2107` + `auction_start_date` nulo.
- **Test de regresión del bug**: un lote COP de 2014 debe convertir a ~1,6× lo que daba la tasa
  estática. Es el que fija que el arreglo funciona.
- Test de que EUR nunca consulta el histórico (tasa 1.0 en cualquier mes).
- El script de descarga se testea sólo en el **parseo** de respuestas guardadas como fixture
  (una del BCE en CSV, una de la TRM en JSON), nunca contra la red.

## Criterios de aceptación

1. `pipelines/config/fx_history.yaml` existe, versionado, cubriendo 2013-01 → mes actual para
   COP y USD.
2. Un lote COP de Bogotá de 2014 convierte a ~1,6× su valor actual en `revenue_eur`.
3. Todo lote tiene `fx_method`; el recuento de `fallback_static` aparece en `quality_flags.jsonl`
   y en el informe HTML.
4. Los 201 tests existentes siguen pasando, más los nuevos.
5. `python -m pytest` verde y pipeline completo re-ejecutado desde Gold.
