# Tasas FX históricas (COP/USD/EUR) — Implementation Plan

> **EJECUTADO el 2026-08-16.** Las 8 tareas están completas y commiteadas. Tres cosas salieron
> distintas de lo planeado y quedan anotadas aquí para que nadie las "arregle" de vuelta:
>
> 1. **El efecto es mucho menor de lo previsto, y el diseño se equivocaba en el porqué.** El
>    documento de diseño esperaba +62% en las ventas de Bogotá de 2014. **Bogotá no tiene lotes
>    de 2014**: sus datos empiezan en 2019, y los lotes de 2014 son de Durán, que es EUR y no
>    convierte. Los totales por casa se mueven sólo −2% a −4%. El mecanismo sí funciona: un
>    importe COP convierte a **1,61×** la tasa estática en 2014-01, y dentro de la ventana real
>    de Bogotá (2019→2026) hay un **spread de 1,27×** entre el mes más fuerte y el más débil.
> 2. **EUR tuvo que cortocircuitar antes del histórico.** Sin eso, un lote de Durán sin fecha
>    parseable se marcaba `fallback_static`, y son 40.442 lotes: habrían dominado el contador de
>    fallback del informe con lotes que no son aproximados en absoluto. Hay un test que lo fija.
> 3. **El flag `fx_static_timeseries` (warn) pasó a `fx_timeseries` (info).** Avisaba de que
>    comparar años no era válido por usar una tasa única — justo lo que esto arregla. Dejarlo
>    habría contradicho al flag nuevo en el mismo panel.
>
> Extra fuera de plan: `pipelines/analytics/build_fx_report.py` → `data/gold/fx_report.html`,
> el panel de la capa FX. Suite: **533 tests en verde** (la base eran 488, no los 201 que cita
> este plan).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir los importes a EUR usando la tasa del mes de la subasta en vez de una única tasa de hoy, que hoy infravalora ~62% las ventas de Bogotá de 2014.

**Architecture:** Un script manual descarga series diarias del BCE (EUR/USD) y de la TRM oficial colombiana (USD/COP), las agrega a media mensual y las escribe en `pipelines/config/fx_history.yaml`, versionado en git. `pipelines/shared/fx.py` sigue siendo el único punto de lectura de tasas y gana `to_eur_at(amount, currency, when)`, que devuelve `(importe, method)`. Los pipelines extraen el mes de la subasta con una función nueva `extract_month()` y guardan el método usado por lote.

**Tech Stack:** Python 3.13, `pyyaml`, `urllib.request` (stdlib, sin dependencias nuevas), `pytest`, `orjson`.

## Global Constraints

- Todos los comandos se ejecutan **desde la raíz del repo**. Todo se invoca como módulo (`python -m ...`), no por ruta de fichero.
- **Los comentarios y docstrings del código de pipelines van en español** (convención del repo) y explican *por qué* existe la regla, citando el bug que evitan.
- **Los tests nunca tocan la red.** El script de descarga se testea sólo en el parseo, con fixtures guardadas.
- `pipelines/shared/fx.py` es el **único punto de lectura** de tasas. Ningún otro módulo puede leer `fx.yaml` ni `fx_history.yaml` directamente.
- **Moneda desconocida devuelve `None`, nunca 1.0 ni tasa estática.** El fallback es sólo por *fecha* ausente.
- **EUR nunca consulta el histórico**: tasa 1.0 en cualquier mes.
- `data/**` está gitignored: nunca commitear resultados de pipeline. `pipelines/config/fx_history.yaml` **sí** se commitea (está fuera de `data/`).
- Los 201 tests existentes deben seguir pasando. `to_eur()`, `rate_for()` y `fx_as_of()` conservan su firma actual.

## File Structure

| Fichero | Responsabilidad |
|---|---|
| `scripts/fx_fetch_history.py` (crear) | Descarga BCE + TRM, agrega a mensual, escribe el YAML. Manual, fuera de `run_all.ps1`. |
| `pipelines/config/fx_history.yaml` (crear, commitear) | Tasas mensuales 2013-01 → hoy para USD y COP. |
| `pipelines/shared/fx.py` (modificar) | Añade `to_eur_at()`, `rate_for_month()`, `fx_history_range()`. Conserva lo existente. |
| `pipelines/shared/schema.py` (modificar) | Añade `extract_month()`, hermana de `extract_year()`. |
| `pipelines/gold/build_gold.py` (modificar) | Usa `to_eur_at()`; cuenta métodos; emite el flag `fx_historical`. |
| `pipelines/gold/build_insights.py` (modificar) | Usa `to_eur_at()`. |
| `pipelines/enrichments/currency_normalize.py` (modificar) | Usa `to_eur_at()`; `fx_source` por lote. |
| `pipelines/silver/quality_gates.py` (modificar) | Métrica `fx_historical_coverage`, informativa. |
| `pipelines/analytics/render_html.py`, `build_artifact.py` (modificar) | Textos: "tasa del mes de subasta". |
| `semantic_layer/metrics.yaml` (modificar) | `fx_rate_to_eur(currency, auction_month)`. |
| `tests/pipelines/test_fx_history.py` (crear) | Tests de `to_eur_at` y del fallback. |
| `tests/pipelines/test_extract_month.py` (crear) | Tests de `extract_month`. |
| `tests/scripts/test_fx_fetch_parse.py` (crear) | Parseo de fixtures BCE/TRM, sin red. |

**Orden de tareas:** 1 (schema) → 2 (script descarga) → 3 (datos reales) → 4 (fx.py) → 5 (gold) → 6 (insights+enrichment) → 7 (gates+informe+semantic) → 8 (rerun).

---

### Task 1: `extract_month()` en schema.py

Hermana de `extract_year()`. Es independiente de todo lo demás: se hace primero para que las tareas siguientes puedan consumirla.

**Files:**
- Modify: `pipelines/shared/schema.py` (añadir tras `extract_year`, línea 54)
- Test: `tests/pipelines/test_extract_month.py` (crear)

**Interfaces:**
- Consumes: nada.
- Produces: `extract_month(auction_start_date: Optional[str], auction_id: Optional[str] = None) -> Tuple[Optional[str], str]`. Devuelve `("YYYY-MM", method)` con method en `{"iso", "text", "auction_id", "unknown"}`, o `(None, "unknown")`.

- [x] **Step 1: Escribir los tests que fallan**

Crear `tests/pipelines/test_extract_month.py`:

```python
"""Tests de extract_month: cada casa guarda la fecha en un formato distinto."""

from pipelines.shared.schema import extract_month


def test_iso_date_bogota():
    # Bogota y Zorrilla guardan ISO con dia exacto.
    assert extract_month("2022-03-03T20:00") == ("2022-03", "iso")


def test_iso_date_with_timezone_zorrilla():
    assert extract_month("2019-05-10T20:00:00+00:00") == ("2019-05", "iso")


def test_spanish_text_duran():
    # Duran solo publica mes y anio, en texto libre y en espaniol.
    assert extract_month("Enero 2014") == ("2014-01", "text")
    assert extract_month("Julio 2014") == ("2014-07", "text")
    assert extract_month("Diciembre 2020") == ("2020-12", "text")


def test_spanish_text_is_accent_and_case_insensitive():
    # "Marzo", "marzo" y "MARZO" son la misma cosa.
    assert extract_month("marzo 2015") == ("2015-03", "text")
    assert extract_month("MARZO 2015") == ("2015-03", "text")


def test_falls_back_to_auction_id():
    # Ultimo recurso: el slug lleva mes y anio.
    assert extract_month(None, "subasta-504-enero-2014_504-001") == ("2014-01", "auction_id")


def test_auction_id_only_used_when_date_unusable():
    # Si la fecha sirve, el slug no se mira.
    assert extract_month("2021-06-01T19:00", "subasta-504-enero-2014_504-001") == (
        "2021-06",
        "iso",
    )


def test_typo_year_2107_is_not_accepted():
    # subasta-541-marzo-2107 es un typo de la propia web de Duran (2107 por
    # 2017). extract_year solo acepta 19xx/20xx; extract_month hace lo mismo,
    # para no fabricar un mes que no existe.
    assert extract_month(None, "subasta-541-marzo-2107") == (None, "unknown")


def test_no_date_no_id():
    assert extract_month(None) == (None, "unknown")
    assert extract_month("") == (None, "unknown")


def test_unparseable_text():
    assert extract_month("tienda-online") == (None, "unknown")


def test_month_without_year_is_unknown():
    # Un mes suelto no basta: sin anio no hay clave "YYYY-MM".
    assert extract_month("Enero") == (None, "unknown")
```

- [x] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `python -m pytest tests/pipelines/test_extract_month.py -v`
Expected: FAIL con `ImportError: cannot import name 'extract_month'`

- [x] **Step 3: Implementar `extract_month`**

En `pipelines/shared/schema.py`, añadir junto a `_YEAR_RE` (línea 13):

```python
# Duran escribe el mes en texto y en espaniol ("Julio 2014"). El anio se acepta
# solo como 19xx/20xx, igual que en extract_year: la propia web de Duran tiene
# el typo "subasta-541-marzo-2107", y preferimos un mes desconocido a uno
# fabricado.
_MONTHS_ES = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "setiembre": "09", "octubre": "10",
    "noviembre": "11", "diciembre": "12",
}
_MONTH_TEXT_RE = re.compile(
    r"(" + "|".join(_MONTHS_ES) + r")[\s\-_]+((?:19|20)\d{2})",
    re.IGNORECASE,
)
_ISO_MONTH_RE = re.compile(r"^((?:19|20)\d{2})-(0[1-9]|1[0-2])")
```

Y tras `extract_year()` (línea 54):

```python
def extract_month(
    auction_start_date: Optional[str],
    auction_id: Optional[str] = None,
) -> Tuple[Optional[str], str]:
    """Extrae el mes de una subasta como "YYYY-MM".

    Devuelve (month, method) con method en:
      "iso"        -> fecha ISO estandar (Bogota, Zorrilla)
      "text"       -> texto en espaniol, p.ej. "Julio 2014" (Duran)
      "auction_id" -> inferido del slug, p.ej. "subasta-504-enero-2014_504-001"
      "unknown"    -> no hay mes recuperable; el llamante decide el fallback

    Es la hermana de extract_year(). Existe porque la conversion a EUR usa la
    tasa del mes de la subasta: aplicar la tasa de hoy a un lote de 2014
    infravalora ~62% las ventas en COP.
    """
    date_str = auction_start_date or ""

    # 1. ISO: "2022-03-03T20:00" -> "2022-03".
    match = _ISO_MONTH_RE.match(date_str)
    if match:
        return f"{match.group(1)}-{match.group(2)}", "iso"

    # 2. Texto libre en espaniol ("Julio 2014").
    match = _MONTH_TEXT_RE.search(date_str)
    if match:
        return f"{match.group(2)}-{_MONTHS_ES[match.group(1).lower()]}", "text"

    # 3. Ultimo recurso: el slug de la subasta.
    if auction_id:
        match = _MONTH_TEXT_RE.search(auction_id)
        if match:
            return f"{match.group(2)}-{_MONTHS_ES[match.group(1).lower()]}", "auction_id"

    return None, "unknown"
```

- [x] **Step 4: Ejecutar los tests para verificar que pasan**

Run: `python -m pytest tests/pipelines/test_extract_month.py -v`
Expected: PASS (11 tests)

- [x] **Step 5: Verificar que no se rompió nada**

Run: `python -m pytest -q`
Expected: 201 tests previos + 11 nuevos, todos PASS

- [x] **Step 6: Commit**

```bash
git add pipelines/shared/schema.py tests/pipelines/test_extract_month.py
git commit -m "feat(schema): extract_month() para la tasa FX del mes de subasta"
```

---

### Task 2: script de descarga (parseo, sin red)

Se construye el script con sus parsers testeables **antes** de descargar nada. Los tests usan fixtures guardadas, nunca la red.

**Files:**
- Create: `scripts/fx_fetch_history.py`
- Create: `tests/scripts/test_fx_fetch_parse.py`
- Create: `tests/scripts/fixtures/ecb_sample.csv`
- Create: `tests/scripts/fixtures/trm_sample.json`

**Interfaces:**
- Consumes: nada.
- Produces: `parse_ecb_csv(text: str) -> dict[str, float]` (fecha ISO → EUR/USD), `parse_trm_json(text: str) -> dict[str, float]` (fecha ISO → COP por USD), `monthly_average(daily: dict[str, float]) -> dict[str, float]` ("YYYY-MM" → media), `build_rates(eurusd_monthly, trm_monthly) -> dict[str, dict[str, float]]` con claves `"USD"` y `"COP"`.

- [x] **Step 1: Crear las fixtures**

`tests/scripts/fixtures/ecb_sample.csv` — recorte real de la API del BCE (cabecera + 3 observaciones de dos meses distintos):

```csv
KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE,OBS_STATUS
EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2014-01-02,1.3670,A
EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2014-01-03,1.3592,A
EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2014-02-03,1.3488,A
```

`tests/scripts/fixtures/trm_sample.json` — recorte real de datos.gov.co:

```json
[{"valor":"1938.89","unidad":"COP","vigenciadesde":"2014-01-02T00:00:00.000","vigenciahasta":"2014-01-03T00:00:00.000"}
,{"valor":"1936.92","unidad":"COP","vigenciadesde":"2014-01-03T00:00:00.000","vigenciahasta":"2014-01-07T00:00:00.000"}
,{"valor":"1970.00","unidad":"COP","vigenciadesde":"2014-02-03T00:00:00.000","vigenciahasta":"2014-02-03T00:00:00.000"}]
```

- [x] **Step 2: Escribir los tests que fallan**

Crear `tests/scripts/test_fx_fetch_parse.py`:

```python
"""Tests del parseo de fx_fetch_history. NUNCA tocan la red: usan fixtures.

El script se ejecuta a mano y rara vez; lo que hay que blindar es que lo
descargado se interprete bien, no que la API responda.
"""

from pathlib import Path

from scripts.fx_fetch_history import (
    build_rates,
    monthly_average,
    parse_ecb_csv,
    parse_trm_json,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_ecb_csv():
    text = (FIXTURES / "ecb_sample.csv").read_text(encoding="utf-8")
    daily = parse_ecb_csv(text)
    assert daily["2014-01-02"] == 1.3670
    assert daily["2014-01-03"] == 1.3592
    assert len(daily) == 3


def test_parse_ecb_csv_skips_header():
    text = (FIXTURES / "ecb_sample.csv").read_text(encoding="utf-8")
    assert "TIME_PERIOD" not in parse_ecb_csv(text)


def test_parse_trm_json():
    text = (FIXTURES / "trm_sample.json").read_text(encoding="utf-8")
    daily = parse_trm_json(text)
    assert daily["2014-01-02"] == 1938.89
    assert daily["2014-02-03"] == 1970.00
    assert len(daily) == 3


def test_monthly_average():
    daily = {"2014-01-02": 1.0, "2014-01-03": 2.0, "2014-02-03": 5.0}
    monthly = monthly_average(daily)
    assert monthly["2014-01"] == 1.5
    assert monthly["2014-02"] == 5.0


def test_monthly_average_empty():
    assert monthly_average({}) == {}


def test_build_rates_usd_is_inverse_of_eurusd():
    # El BCE publica EUR->USD (cuantos USD vale 1 EUR). Nosotros guardamos
    # USD->EUR, que es el inverso.
    rates = build_rates({"2014-01": 1.36}, {})
    assert rates["USD"]["2014-01"] == round(1 / 1.36, 8)


def test_build_rates_cop_bridges_through_usd():
    # COP->EUR = (1/TRM) x (1/EURUSD). El BCE no publica COP, de ahi el puente.
    rates = build_rates({"2014-01": 1.36}, {"2014-01": 1938.0})
    expected = round((1 / 1938.0) * (1 / 1.36), 10)
    assert rates["COP"]["2014-01"] == expected


def test_build_rates_skips_month_missing_from_either_source():
    # Sin las dos series no se puede componer COP: mejor omitir el mes que
    # inventarlo. Es la misma disciplina que to_eur() devolviendo None.
    rates = build_rates({"2014-01": 1.36}, {"2014-02": 1938.0})
    assert "2014-02" not in rates["COP"]
    assert "2014-01" not in rates["COP"]
```

- [x] **Step 3: Ejecutar los tests para verificar que fallan**

Run: `python -m pytest tests/scripts/test_fx_fetch_parse.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'scripts.fx_fetch_history'`

- [x] **Step 4: Crear `scripts/__init__.py` si no existe**

```bash
python -c "import pathlib; p=pathlib.Path('scripts/__init__.py'); p.exists() or p.write_text('')"
```

- [x] **Step 5: Implementar el script**

Crear `scripts/fx_fetch_history.py`:

```python
#!/usr/bin/env python3
"""Descarga el historico de tasas y escribe pipelines/config/fx_history.yaml.

Se ejecuta A MANO y rara vez. NO forma parte de run_all.ps1: los pipelines no
tocan la red, leen siempre el YAML versionado en git.

Dos fuentes, porque el BCE NO publica el peso colombiano (la serie
D.COP.EUR.SP00.A devuelve 404). El puente es:

    COP->EUR = (1 / TRM_COP_USD) x (1 / EURUSD_BCE)

usando en cada lado la fuente canonica de esa moneda.

Ejecutar desde la raiz:  python -m scripts.fx_fetch_history
"""

from __future__ import annotations

import json
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "pipelines" / "config" / "fx_history.yaml"

# Un anio de margen antes del primer lote (2014) para que ningun mes real
# quede fuera de rango.
START = "2013-01-01"

ECB_URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
    "?startPeriod={start}&format=csvdata"
)
TRM_URL = (
    "https://www.datos.gov.co/resource/32sa-8pi3.json"
    "?$limit=50000&$where=vigenciadesde>='{start}T00:00:00'"
    "&$order=vigenciadesde%20ASC"
)
# Sin User-Agent el BCE responde 403.
HEADERS = {"User-Agent": "AuctionHousesApp/1.0 (fx history fetch)"}


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8")


def parse_ecb_csv(text: str) -> Dict[str, float]:
    """CSV del BCE -> {fecha ISO: EUR/USD}. TIME_PERIOD y OBS_VALUE son las
    columnas 7 y 8 (indices 6 y 7)."""
    daily: Dict[str, float] = {}
    for line in text.splitlines():
        parts = line.split(",")
        if len(parts) < 8 or parts[6] == "TIME_PERIOD":
            continue
        try:
            daily[parts[6]] = float(parts[7])
        except ValueError:
            # Dias sin cotizacion (festivos) vienen vacios: se omiten.
            continue
    return daily


def parse_trm_json(text: str) -> Dict[str, float]:
    """JSON de datos.gov.co -> {fecha ISO: COP por USD}."""
    daily: Dict[str, float] = {}
    for row in json.loads(text):
        date = (row.get("vigenciadesde") or "")[:10]
        try:
            daily[date] = float(row["valor"])
        except (KeyError, TypeError, ValueError):
            continue
    return daily


def monthly_average(daily: Dict[str, float]) -> Dict[str, float]:
    """Media mensual. Es la granularidad mas fina que soportan las tres casas:
    Duran solo publica mes y anio ("Enero 2014")."""
    buckets: Dict[str, list] = defaultdict(list)
    for date, value in daily.items():
        buckets[date[:7]].append(value)
    return {month: sum(vals) / len(vals) for month, vals in sorted(buckets.items())}


def build_rates(
    eurusd_monthly: Dict[str, float],
    trm_monthly: Dict[str, float],
) -> Dict[str, Dict[str, float]]:
    """Compone las tasas hacia EUR.

    Un mes que falte en cualquiera de las dos series se omite en COP en vez de
    rellenarse: la misma disciplina que to_eur() devolviendo None.
    """
    usd = {m: round(1 / v, 8) for m, v in eurusd_monthly.items() if v}
    cop = {
        m: round((1 / trm) * (1 / eurusd_monthly[m]), 10)
        for m, trm in trm_monthly.items()
        if trm and eurusd_monthly.get(m)
    }
    return {"USD": usd, "COP": cop}


def render_yaml(rates: Dict[str, Dict[str, float]], generated_at: str) -> str:
    lines = [
        "# Tasas de cambio MENSUALES hacia EUR. Generado por",
        "# scripts/fx_fetch_history.py -- no editar a mano.",
        "#",
        "# El BCE no publica COP (D.COP.EUR.SP00.A da 404), asi que el peso se",
        "# compone puenteando por el dolar: COP->EUR = (1/TRM) x (1/EURUSD).",
        "#",
        "# Lo lee unicamente pipelines/shared/fx.py.",
        "",
        "base_currency: EUR",
        f'generated_at: "{generated_at}"',
        "sources:",
        '  USD: "ECB SDW EXR D.USD.EUR.SP00.A (media mensual)"',
        '  COP: "TRM Superfinanciera datos.gov.co 32sa-8pi3 x ECB EUR/USD (media mensual)"',
        "rates_to_eur:",
    ]
    for currency in ("USD", "COP"):
        lines.append(f"  {currency}:")
        for month, rate in sorted(rates[currency].items()):
            lines.append(f'    "{month}": {rate}')
    return "\n".join(lines) + "\n"


def main() -> None:
    import datetime

    print(f"[fx] descargando BCE EUR/USD desde {START} ...")
    eurusd = monthly_average(parse_ecb_csv(_fetch(ECB_URL.format(start=START))))
    print(f"[fx]   {len(eurusd)} meses")

    print(f"[fx] descargando TRM COP/USD desde {START} ...")
    trm = monthly_average(parse_trm_json(_fetch(TRM_URL.format(start=START))))
    print(f"[fx]   {len(trm)} meses")

    rates = build_rates(eurusd, trm)
    generated_at = datetime.date.today().isoformat()
    OUTPUT.write_text(render_yaml(rates, generated_at), encoding="utf-8")
    print(f"[fx] escrito {OUTPUT}")
    print(f"[fx]   USD: {len(rates['USD'])} meses | COP: {len(rates['COP'])} meses")


if __name__ == "__main__":
    main()
```

- [x] **Step 6: Ejecutar los tests para verificar que pasan**

Run: `python -m pytest tests/scripts/test_fx_fetch_parse.py -v`
Expected: PASS (8 tests)

- [x] **Step 7: Commit**

```bash
git add scripts/fx_fetch_history.py scripts/__init__.py tests/scripts/
git commit -m "feat(fx): script de descarga del historico BCE + TRM (parseo testeado)"
```

---

### Task 3: descargar los datos reales y commitear el YAML

Única tarea que toca la red. Requiere conexión.

**Files:**
- Create: `pipelines/config/fx_history.yaml` (generado, se commitea)

**Interfaces:**
- Consumes: `scripts.fx_fetch_history.main()` de la Task 2.
- Produces: `pipelines/config/fx_history.yaml` con `rates_to_eur.USD` y `rates_to_eur.COP`, claves `"YYYY-MM"` de 2013-01 al mes actual.

- [x] **Step 1: Ejecutar la descarga**

Run: `python -m scripts.fx_fetch_history`
Expected: escribe el fichero e imprime ~163 meses en USD y ~163 en COP.

- [x] **Step 2: Verificar el contenido a ojo**

```bash
python -c "
import yaml
d = yaml.safe_load(open('pipelines/config/fx_history.yaml', encoding='utf-8'))
cop = d['rates_to_eur']['COP']; usd = d['rates_to_eur']['USD']
print('meses COP:', len(cop), '| USD:', len(usd))
print('COP 2014-01:', cop['2014-01'], '-> 1 EUR =', round(1/cop['2014-01']), 'COP')
print('COP 2026-07:', cop['2026-07'], '-> 1 EUR =', round(1/cop['2026-07']), 'COP')
print('ratio 2014 vs hoy:', round(cop['2014-01']/0.000232, 2))
"
```

Expected: 1 EUR ≈ 2.650 COP en 2014-01 y ≈ 3.500 COP hoy; ratio ≈ **1,6**. Si el ratio no está entre 1,4 y 1,8, **parar**: algo va mal en la composición.

- [x] **Step 3: Verificar que no hay huecos en el rango con datos**

```bash
python -c "
import yaml
d = yaml.safe_load(open('pipelines/config/fx_history.yaml', encoding='utf-8'))
for cur in ('USD','COP'):
    ms = sorted(d['rates_to_eur'][cur])
    gaps = [m for m in ms if d['rates_to_eur'][cur][m] is None]
    print(cur, ms[0], '->', ms[-1], '| nulos:', len(gaps))
"
```

Expected: rango 2013-01 → mes actual, 0 nulos.

- [x] **Step 4: Commit**

```bash
git add pipelines/config/fx_history.yaml
git commit -m "data(fx): historico mensual COP/USD/EUR 2013-2026 (BCE + TRM)"
```

---

### Task 4: `to_eur_at()` en fx.py

El corazón del cambio. `fx.py` sigue siendo el único punto de lectura de tasas.

**Files:**
- Modify: `pipelines/shared/fx.py`
- Test: `tests/pipelines/test_fx_history.py` (crear)

**Interfaces:**
- Consumes: `pipelines/config/fx_history.yaml` de la Task 3.
- Produces:
  - `to_eur_at(amount: Optional[float], currency: Optional[str], when: Optional[str]) -> Tuple[Optional[float], str]` — method en `{"monthly", "fallback_static", "unavailable"}`.
  - `rate_for_month(currency: Optional[str], when: Optional[str]) -> Optional[float]`
  - `fx_history_range() -> Tuple[Optional[str], Optional[str]]`
  - `fx_note(fallback_lots: Optional[int] = None) -> str` (firma ampliada, compatible)
- `to_eur()`, `rate_for()`, `fx_as_of()` **sin cambios**.

- [x] **Step 1: Escribir los tests que fallan**

Crear `tests/pipelines/test_fx_history.py`:

```python
"""Tests de la conversion con tasa historica mensual.

Fijan el bug que arregla esta feature: aplicar la tasa de hoy a un lote de
2014 infravalora ~62% las ventas en COP.
"""

import pytest

from pipelines.shared.fx import (
    fx_history_range,
    rate_for_month,
    to_eur,
    to_eur_at,
)


def test_monthly_rate_differs_from_static():
    # El test de regresion del bug. En 2014 el COP valia mucho mas frente al
    # EUR que hoy, asi que el mismo importe convierte a bastante mas.
    historico, method = to_eur_at(10_000_000, "COP", "2014-01")
    estatico = to_eur(10_000_000, "COP")
    assert method == "monthly"
    assert historico > estatico * 1.4


def test_eur_never_converts():
    # Duran ya viene en EUR: tasa 1.0 en cualquier mes, sin mirar el historico.
    for month in ("2014-01", "2026-07", None):
        assert to_eur_at(1000, "EUR", month) == (1000.0, "monthly")


def test_missing_month_falls_back_to_static():
    # Decision del propietario: todo lote convierte siempre. El fallback queda
    # contado en quality_flags, no invisible.
    importe, method = to_eur_at(10_000_000, "COP", None)
    assert method == "fallback_static"
    assert importe == to_eur(10_000_000, "COP")


def test_unknown_currency_returns_none_not_fallback():
    # El fallback es por FECHA ausente, no por MONEDA ausente. Una moneda sin
    # tasa sigue devolviendo None, nunca 1.0 ni la tasa estatica.
    assert to_eur_at(100, "XYZ", "2014-01") == (None, "unavailable")
    assert to_eur_at(100, "XYZ", None) == (None, "unavailable")
    assert to_eur_at(100, None, "2014-01") == (None, "unavailable")


def test_none_amount_returns_none():
    assert to_eur_at(None, "COP", "2014-01")[0] is None


def test_month_before_range_clamps_to_earliest():
    # Un mes fuera de rango cae al mes mas cercano DENTRO del historico, no a
    # la tasa estatica: sigue siendo un dato real.
    first, _ = fx_history_range()
    importe, method = to_eur_at(1_000_000, "COP", "1990-01")
    assert method == "monthly"
    assert importe == to_eur_at(1_000_000, "COP", first)[0]


def test_month_after_range_clamps_to_latest():
    _, last = fx_history_range()
    importe, method = to_eur_at(1_000_000, "COP", "2099-12")
    assert method == "monthly"
    assert importe == to_eur_at(1_000_000, "COP", last)[0]


def test_rate_for_month_usd():
    rate = rate_for_month("USD", "2014-01")
    assert rate is not None
    # 1 EUR valia ~1,36 USD en enero de 2014 -> 1 USD ~ 0,73 EUR.
    assert 0.70 < rate < 0.78


def test_rate_for_month_is_case_insensitive():
    assert rate_for_month("cop", "2014-01") == rate_for_month("COP", "2014-01")


def test_history_range_covers_data():
    first, last = fx_history_range()
    assert first <= "2014-01"   # el primer lote es de enero de 2014
    assert last >= "2026-01"


def test_legacy_to_eur_unchanged():
    # No se rompe lo existente: to_eur sigue siendo el camino del fallback.
    assert to_eur(1000, "EUR") == 1000.0
    assert to_eur(100, "XYZ") is None
```

- [x] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `python -m pytest tests/pipelines/test_fx_history.py -v`
Expected: FAIL con `ImportError: cannot import name 'to_eur_at'`

- [x] **Step 3: Implementar en `pipelines/shared/fx.py`**

Añadir tras `FX_CONFIG` (línea 19):

```python
FX_HISTORY = ROOT / "pipelines" / "config" / "fx_history.yaml"
```

Añadir tras `load_fx()` (línea 26):

```python
@lru_cache(maxsize=1)
def load_fx_history() -> Dict[str, Any]:
    """Carga fx_history.yaml (cacheado). Lo genera scripts/fx_fetch_history.py."""
    with open(FX_HISTORY, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


@lru_cache(maxsize=1)
def _history_months() -> Dict[str, list]:
    """Meses disponibles por moneda, ordenados. Cacheado para no reordenar en
    cada lote (son 60.709)."""
    rates = load_fx_history().get("rates_to_eur", {})
    return {cur: sorted(months) for cur, months in rates.items()}


def fx_history_range() -> tuple[Optional[str], Optional[str]]:
    """Primer y ultimo mes cubiertos por el historico."""
    months = _history_months().get("USD") or []
    return (months[0], months[-1]) if months else (None, None)


def rate_for_month(currency: Optional[str], when: Optional[str]) -> Optional[float]:
    """Tasa hacia EUR para una moneda en un mes "YYYY-MM".

    EUR no consulta el historico: siempre 1.0.

    Un mes fuera de rango se sujeta al mes mas cercano disponible (no a la tasa
    estatica): sigue siendo un dato real de mercado.
    """
    if not currency or not when:
        return None
    cur = currency.upper()
    if cur == "EUR":
        return 1.0
    months = _history_months().get(cur)
    if not months:
        return None
    key = when if when in set(months) else (months[0] if when < months[0] else months[-1])
    return load_fx_history()["rates_to_eur"][cur].get(key)


def to_eur_at(
    amount: Optional[float],
    currency: Optional[str],
    when: Optional[str],
) -> tuple[Optional[float], str]:
    """Convierte a EUR con la tasa del mes de la subasta.

    Devuelve (importe, method) con method en:
      "monthly"          -> tasa del mes (o del mes mas cercano del historico)
      "fallback_static"  -> sin mes utilizable: tasa estatica de fx.yaml
      "unavailable"      -> moneda sin tasa: importe None

    El fallback es por FECHA ausente, NO por moneda ausente: una moneda
    desconocida sigue devolviendo None, nunca 1.0. Son dos fallos distintos y
    solo uno tiene respuesta razonable.

    Devolver el metodo junto al importe es el patron de extract_year(), para
    que el informe pueda contar cuantos lotes usaron el fallback.
    """
    if rate_for(currency) is None and (not currency or currency.upper() != "EUR"):
        return None, "unavailable"
    if amount is None:
        return None, "monthly" if when else "fallback_static"

    rate = rate_for_month(currency, when)
    if rate is not None:
        return round(float(amount) * rate, 2), "monthly"

    return to_eur(amount, currency), "fallback_static"
```

Y reemplazar `fx_note()` (líneas 50-56) por:

```python
def fx_note(fallback_lots: Optional[int] = None) -> str:
    """Texto de descargo para mostrar en el informe."""
    first, last = fx_history_range()
    note = (
        f"Conversion a EUR con la tasa media del MES de cada subasta "
        f"({first} a {last}). Fuentes: BCE (EUR/USD) y TRM de la "
        "Superfinanciera de Colombia (USD/COP). "
        "Sirve para comparar casas entre si, no para valoracion contable."
    )
    if fallback_lots:
        note += (
            f" {fallback_lots:,} lotes sin fecha utilizable se convirtieron con "
            f"la tasa estatica de {fx_as_of()}."
        )
    return note
```

- [x] **Step 4: Ejecutar los tests para verificar que pasan**

Run: `python -m pytest tests/pipelines/test_fx_history.py tests/pipelines/test_fx.py -v`
Expected: PASS. Ojo: `test_fx.py::test_note_mentions_as_of` puede fallar si asertaba que `fx_as_of()` sale en la nota. Actualizarlo para asertar sobre el nuevo texto:

```python
def test_note_describes_monthly_conversion():
    note = fx_note()
    assert "MES" in note or "mes" in note


def test_note_mentions_fallback_count_when_given():
    assert "1,234" in fx_note(1234)
    assert fx_as_of() in fx_note(1234)
```

- [x] **Step 5: Verificar la suite completa**

Run: `python -m pytest -q`
Expected: todo PASS

- [x] **Step 6: Commit**

```bash
git add pipelines/shared/fx.py tests/pipelines/test_fx_history.py tests/pipelines/test_fx.py
git commit -m "feat(fx): to_eur_at() convierte con la tasa del mes de subasta"
```

---

### Task 5: integrar en build_gold.py

**Files:**
- Modify: `pipelines/gold/build_gold.py:29` (import), `:110-118` (conversión), `:180` (`fx_rate_used`), `:250-257` (flags)

**Interfaces:**
- Consumes: `to_eur_at()` (Task 4), `extract_month()` (Task 1), `fx_note(fallback_lots)` (Task 4).
- Produces: `agg_house_metrics.jsonl` con `fx_method_counts: dict[str, int]` y `fx_fallback_lots: int`; `quality_flags.jsonl` con un flag `code: "fx_historical"`.

- [x] **Step 1: Actualizar el import (línea 29)**

```python
from pipelines.shared.fx import fx_as_of, fx_note, rate_for, to_eur, to_eur_at
```

Y en el import de schema, añadir `extract_month`:

```python
from pipelines.shared.schema import extract_month, extract_year, is_sold
```

(Comprobar la línea exacta del import de `schema` con `grep -n "from pipelines.shared.schema" pipelines/gold/build_gold.py`.)

- [x] **Step 2: Añadir el acumulador de métodos**

Junto a `unconvertible` (línea 96):

```python
    # Cuantos lotes se convirtieron con tasa del mes y cuantos cayeron al
    # fallback estatico. Se publica en quality_flags: el fallback existe, pero
    # queda contado, no invisible.
    fx_methods: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
```

- [x] **Step 3: Sustituir la conversión (líneas 115-118)**

Reemplazar:

```python
        # Importe convertido: None si la moneda no esta en fx.yaml.
        price_eur = to_eur(price, currency) if sold else None
        if sold and price is not None and price_eur is None:
            unconvertible[str(currency)] += 1
```

por:

```python
        # Importe convertido con la tasa del MES de la subasta. Con la tasa de
        # hoy, un lote COP de 2014 salia ~62% barato.
        month, _month_method = extract_month(row.get("auction_start_date"), aid_raw)
        if sold:
            price_eur, fx_method = to_eur_at(price, currency, month)
        else:
            price_eur, fx_method = None, "monthly"
        if sold and price is not None:
            fx_methods[house][fx_method] += 1
            if price_eur is None:
                unconvertible[str(currency)] += 1
```

- [x] **Step 4: Sustituir `fx_rate_used` (línea 180)**

Reemplazar `"fx_rate_used": rate_for(currency),` por:

```python
                # Ya no hay una unica tasa por moneda: se aplica la del mes de
                # cada subasta. Se publica el recuento de metodos en su lugar.
                "fx_method_counts": dict(fx_methods.get(house, {})),
                "fx_fallback_lots": fx_methods.get(house, {}).get("fallback_static", 0),
                "fx_rate_static": rate_for(currency),
```

- [x] **Step 5: Actualizar el flag de quality (líneas 250-257)**

Reemplazar el bloque `flags = [...]` por:

```python
    total_fallback = sum(m.get("fallback_static", 0) for m in fx_methods.values())
    flags = [
        {
            "level": "info",
            "code": "fx_historical",
            "message": fx_note(total_fallback),
            "fx_as_of": fx_as_of(),
            "fx_fallback_lots": total_fallback,
        }
    ]
```

- [x] **Step 6: Ejecutar Gold y verificar el efecto**

Run: `python -m pipelines.gold.build_gold`

```bash
python -c "
import json
for l in open('data/gold/agg_house_metrics.jsonl', encoding='utf-8'):
    r = json.loads(l)
    print(r['house_slug'], r['currency'], 'EUR:', r['revenue_eur'], r.get('fx_method_counts'))
"
```

Expected: `bogota_auctions` debe tener un `revenue_eur` **claramente mayor** que antes del cambio (sus lotes son de 2018-2024, con COP más fuerte). `fx_method_counts` mayoritariamente `monthly`.

- [x] **Step 7: Verificar la suite**

Run: `python -m pytest -q`
Expected: todo PASS

- [x] **Step 8: Commit**

```bash
git add pipelines/gold/build_gold.py
git commit -m "feat(gold): revenue_eur con la tasa del mes de cada subasta"
```

---

### Task 6: integrar en build_insights.py y currency_normalize.py

Los dos consumidores restantes de `to_eur()`.

**Files:**
- Modify: `pipelines/gold/build_insights.py:30` (import), `:183` (conversión)
- Modify: `pipelines/enrichments/currency_normalize.py:16,25,39-49`

**Interfaces:**
- Consumes: `to_eur_at()` (Task 4), `extract_month()` (Task 1).
- Produces: `currency_normalized.jsonl` con `fx_source` por lote (`"monthly_2014-01"` / `"static_2026-08-01"`).

- [x] **Step 1: `build_insights.py` — actualizar imports**

Línea 30: `from pipelines.shared.fx import to_eur` → `from pipelines.shared.fx import to_eur_at`

Añadir `extract_month` al import de `pipelines.shared.schema` (comprobar la línea con grep).

- [x] **Step 2: `build_insights.py` — sustituir la conversión (líneas 181-183)**

Reemplazar:

```python
            # to_eur devuelve None si la moneda no tiene tasa: no lo tratamos
            # como euros, se queda fuera de los agregados monetarios.
            eur = to_eur(price, currency) if (sold and price) else None
```

por:

```python
            # Tasa del mes de la subasta: agg_artist_metrics compara artistas
            # ENTRE casas, y con la tasa de hoy un artista vendido en Bogota en
            # 2014 salia ~62% mas barato de lo que realmente se vendio.
            # to_eur_at devuelve None si la moneda no tiene tasa: no lo
            # tratamos como euros, se queda fuera de los agregados monetarios.
            if sold and price:
                month, _ = extract_month(r.get("auction_start_date"), r.get("auction_id") or "")
                eur, _fx_method = to_eur_at(price, currency, month)
            else:
                eur = None
```

- [x] **Step 3: `currency_normalize.py` — reescribir el cuerpo**

Línea 16: `from pipelines.shared.fx import fx_as_of, to_eur` → `from pipelines.shared.fx import fx_as_of, to_eur_at`

Añadir: `from pipelines.shared.schema import extract_month`

Reemplazar la línea 25 (`fx_source = ...`) y el bloque 37-50 por:

```python
            row = json.loads(line)
            currency = row.get("currency")
            price_sold = row.get("price_sold")
            # Tasa del mes de la subasta, no la de hoy.
            month, _ = extract_month(
                row.get("auction_start_date"), row.get("auction_id") or ""
            )
            price_sold_eur, fx_method = to_eur_at(price_sold, currency, month)
            if price_sold is not None and price_sold_eur is None:
                missing_rate += 1
            if fx_method == "fallback_static":
                fallback += 1

            payload = {
                "dedupe_key": row.get("dedupe_key"),
                "currency": currency,
                "price_sold_eur": price_sold_eur,
                "price_estimate_min_eur": to_eur_at(
                    row.get("price_estimate_min"), currency, month
                )[0],
                "price_estimate_max_eur": to_eur_at(
                    row.get("price_estimate_max"), currency, month
                )[0],
                "fx_source": (
                    f"monthly_{month}" if fx_method == "monthly" and month
                    else f"static_{fx_as_of()}"
                ),
            }
```

Declarar `fallback = 0` junto a `missing_rate = 0` (línea 27), y añadir al final, tras el aviso de `missing_rate`:

```python
    if fallback:
        print(f"[enrichment] {fallback:,} lotes sin fecha usable -> tasa estatica")
```

- [x] **Step 4: Ejecutar ambos y verificar**

```bash
python -m pipelines.enrichments.currency_normalize
python -m pipelines.gold.build_insights
python -c "
import json, collections
c = collections.Counter()
for l in open('data/enrichments/currency_normalized.jsonl', encoding='utf-8'):
    c[json.loads(l)['fx_source'].split('_')[0]] += 1
print(c)
"
```

Expected: mayoría `monthly`, minoría `static`.

- [x] **Step 5: Verificar la suite**

Run: `python -m pytest -q`
Expected: todo PASS

- [x] **Step 6: Commit**

```bash
git add pipelines/gold/build_insights.py pipelines/enrichments/currency_normalize.py
git commit -m "feat(pipelines): insights y currency_normalize con tasa mensual"
```

---

### Task 7: quality gate, textos del informe y semantic layer

Cierra la trazabilidad: el fallback se ve en el informe y la definición de la métrica no queda desincronizada.

**Files:**
- Modify: `pipelines/silver/quality_gates.py`
- Modify: `pipelines/analytics/render_html.py:119`
- Modify: `pipelines/analytics/build_artifact.py:407`
- Modify: `semantic_layer/metrics.yaml:30`

**Interfaces:**
- Consumes: `extract_month()` (Task 1), `quality_flags.jsonl` con `code: "fx_historical"` (Task 5).
- Produces: métrica `fx_historical_coverage` en el informe de quality gates.

- [x] **Step 1: Añadir la métrica a `quality_gates.py`**

Localizar dónde se calculan las métricas por casa (`grep -n "artist_resolution_rate" pipelines/silver/quality_gates.py`) y añadir junto a ellas, siguiendo el patrón existente:

```python
    # Cobertura de tasa historica: % de lotes cuya fecha permite elegir la
    # tasa del mes. Informativa por defecto, como las de artistas: los lotes
    # sin fecha caen a la tasa estatica, no se pierden.
    with_month = sum(
        1 for r in rows if extract_month(r.get("auction_start_date"), r.get("auction_id") or "")[0]
    )
    metrics["fx_historical_coverage"] = round(with_month / len(rows), 4) if rows else 0.0
```

Añadir `extract_month` al import de `pipelines.shared.schema` en ese fichero.

- [x] **Step 2: Actualizar los textos del informe**

`pipelines/analytics/render_html.py:119` — reemplazar:

```python
            "note": f"Convertido a EUR · tasa {fx_as_of()}",
```

por:

```python
            "note": "Convertido a EUR · tasa del mes de subasta",
```

`pipelines/analytics/build_artifact.py:407` — reemplazar:

```python
         f"Convertido a EUR - tasa {fx_as_of()}", True),
```

por:

```python
         "Convertido a EUR - tasa del mes de subasta", True),
```

Las líneas 1418 y 960 (que llaman a `fx_note()`) **no se tocan**: ya recogen el texto nuevo automáticamente.

Si `fx_as_of` queda sin usar en alguno de los dos ficheros, quitarlo del import.

- [x] **Step 3: Actualizar `semantic_layer/metrics.yaml:30`**

Reemplazar:

```yaml
    expression: sum(price_sold * fx_rate_to_eur(currency))
```

por:

```yaml
    expression: sum(price_sold * fx_rate_to_eur(currency, auction_month))
```

Y añadir a la descripción de esa métrica (o crearla si no la hay):

```yaml
    notes: >
      La tasa es la media del mes de la subasta, no la de hoy. Los lotes sin
      fecha usable caen a la tasa estatica y se cuentan en quality_flags.
```

- [x] **Step 4: Ejecutar quality gates**

Run: `python pipelines/silver/quality_gates.py`
Expected: aparece `fx_historical_coverage` en el informe, sin fallo.

- [x] **Step 5: Verificar la suite**

Run: `python -m pytest -q`
Expected: todo PASS

- [x] **Step 6: Commit**

```bash
git add pipelines/silver/quality_gates.py pipelines/analytics/render_html.py pipelines/analytics/build_artifact.py semantic_layer/metrics.yaml
git commit -m "feat(quality,report): cobertura FX historica y textos del informe"
```

---

### Task 8: rerun completo y verificación final

**PASO NO REVERSIBLE SIN COSTE.** Reescribe `data/gold/` y `data/enrichments/`, incluido `analytics_report.html`, que es el producto. Es reproducible (basta reejecutar), pero el informe anterior se pierde salvo que se guarde copia.

**Files:**
- Modify: `data/gold/**`, `data/enrichments/**` (gitignored, no se commitean)
- Modify: `CLAUDE.md` (documentar la feature)

**Interfaces:**
- Consumes: todas las tareas anteriores.
- Produces: informe regenerado con importes EUR correctos.

- [x] **Step 1: Guardar copia del informe actual antes de sobrescribirlo**

```bash
cp data/gold/analytics_report.html data/gold/analytics_report.PRE-FX.html
python -c "
import json
tot = {}
for l in open('data/gold/agg_house_metrics.jsonl', encoding='utf-8'):
    r = json.loads(l); tot[r['house_slug']] = r['revenue_eur']
json.dump(tot, open('data/gold/_pre_fx_revenue.json','w'), indent=2)
print('guardado:', tot)
"
```

- [x] **Step 2: Rerun completo**

Run: `.\scripts\run_all.ps1`

Expected: termina sin error. Es un rerun **completo**, no por etapas: ejecutar las etapas sueltas es como se desincronizaron antes las capas (enrichments de marzo sobre un Silver de mayo).

- [x] **Step 3: Comparar antes/después**

```bash
python -c "
import json
pre = json.load(open('data/gold/_pre_fx_revenue.json'))
for l in open('data/gold/agg_house_metrics.jsonl', encoding='utf-8'):
    r = json.loads(l); h = r['house_slug']
    a, b = pre.get(h, 0), r['revenue_eur']
    print(f'{h:22} {a:>16,.0f} -> {b:>16,.0f}  ({b/a if a else 0:.2f}x)')
"
```

Expected: `duran_subastas` ≈ 1,00x (es EUR, no debe moverse). `bogota_auctions` y `zorrilla_subastas` cambian. **Si Durán se mueve, hay un bug**: EUR nunca debe convertirse.

- [x] **Step 4: Verificar el informe**

Abrir `data/gold/analytics_report.html` y comprobar:
- El panel de avisos dice "tasa media del MES de cada subasta" y cita BCE + TRM.
- Si hubo lotes en fallback, aparece el recuento.
- Las tarjetas dicen "tasa del mes de subasta".

- [x] **Step 5: Limpiar los ficheros temporales de comparación**

```bash
rm data/gold/_pre_fx_revenue.json
```

Dejar `analytics_report.PRE-FX.html` hasta que el usuario confirme que el informe nuevo está bien.

- [x] **Step 6: Documentar en CLAUDE.md**

En la sección "Data rules that hold up every Gold figure", reemplazar la parte de la regla de moneda que describe la tasa estática por:

```markdown
- **Never sum prices across houses.** Each house quotes in its own currency (`COP` for Bogotá,
  `EUR` for Duran, `USD` for Zorrilla). Gold emits `revenue_native` + `currency` (exact) alongside
  `revenue_eur`. Any cross-house total must sum `revenue_eur`. Conversion goes through
  `pipelines/shared/fx.py` — the single source of truth, read by both Gold and the currency
  enrichment. **It uses the monthly rate of the auction's month**, not a single current rate:
  the COP went from ~2,650 to ~3,500 per EUR between 2014 and 2026, so a flat rate undervalued
  Bogotá's 2014 sales by ~62%. Rates live in `pipelines/config/fx_history.yaml`, generated by
  `python -m scripts.fx_fetch_history` (manual, not part of `run_all.ps1` — pipelines never hit
  the network). Two sources because **the ECB does not publish COP** (`D.COP.EUR.SP00.A` → 404):
  ECB for EUR/USD, Colombia's official TRM for USD/COP, bridged as
  `COP→EUR = (1/TRM) × (1/EURUSD)`. `to_eur_at()` returns `(amount, method)`; a lot with no usable
  date falls back to the static `fx.yaml` rate and is **counted** in `quality_flags` — the fallback
  is visible, not silent. An unknown *currency* still returns `None`, never `1.0`: that fallback is
  for a missing date only.
```

- [x] **Step 7: Verificación final**

Run: `python -m pytest -q`
Expected: 201 tests previos + ~30 nuevos, todos PASS.

- [x] **Step 8: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: tasa FX del mes de subasta en las reglas de datos"
```

---

## Criterios de aceptación

1. `pipelines/config/fx_history.yaml` existe y está versionado, cubriendo 2013-01 → mes actual para COP y USD.
2. Un lote COP de 2014 convierte a ~1,6× lo que daba la tasa estática (Task 4, Step 4).
3. `agg_house_metrics.jsonl` lleva `fx_method_counts` y `fx_fallback_lots`; el recuento de fallback aparece en `quality_flags.jsonl` y en el informe HTML.
4. Durán (EUR) **no cambia** su `revenue_eur` tras el rerun.
5. `python -m pytest` verde y pipeline completo re-ejecutado con `run_all.ps1`.
