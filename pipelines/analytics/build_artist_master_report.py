#!/usr/bin/env python3
"""Panel de seguimiento del maestro de artistas: data/gold/artist_master_report.html.

Responde a una pregunta que el informe principal no hace: no "cuanto se vendio"
sino "como va la curacion de identidades". El ciclo que vigila es el que empieza
en pipelines/gold/build_artist_master.py (marca los huecos), sigue en
scripts/artist_master_web_research.py (los investiga sin promover) y termina en
scripts/artist_master_promote.py (decide que evidencia es lo bastante firme).

Es un LECTOR PURO. El agente de investigacion escribe en
data/enrichments/artist_web_research.jsonl mientras esto corre, asi que aqui no
se abre nada en modo escritura salvo el propio informe y el diario de snapshots.
Nunca toca los shards YAML ni la cola de revision.

Dos disciplinas heredadas del README de pipelines/config/artists:

  - un revenue que no cruza es un HUECO, nunca un cero. Un 0 en la tabla diria
    "no vendio nada", que es falso; el hueco dice "no lo se", que es cierto.
  - matched no es promovible. La cifra que importa del loop no es cuantos
    encontro sino cuantos puede promover sin decidir por su cuenta un homonimo.

Los graficos son SVG generado aqui, sin libreria de cliente, por la misma razon
que build_fx_report.py: un Artifact de Claude bloquea todo host externo.

Ejecutar como modulo desde la raiz:
    python -m pipelines.analytics.build_artist_master_report
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "data" / "gold"
COVERAGE = GOLD / "artist_master_coverage.json"
DIM_ARTISTS = GOLD / "dim_artist_master.jsonl"
ARTIST_METRICS = GOLD / "agg_artist_metrics.jsonl"
RESEARCH = ROOT / "data" / "enrichments" / "artist_web_research.jsonl"
REVIEW_MANIFEST = ROOT / "pipelines" / "config" / "artist_review" / "_manifest.json"
SNAPSHOTS = GOLD / "artist_master_snapshots.jsonl"
OUTPUT = GOLD / "artist_master_report.html"

# Cuantas filas de impacto se publican. La cola real son >11k: la tabla existe
# para ver si el loop trabaja la cola valiosa, no para listarla entera.
TOP_IMPACT = 40

STATUS_ORDER = ("matched", "ambiguous", "not_found", "error")
STATUS_ES = {
    "matched": "con match",
    "ambiguous": "ambiguo",
    "not_found": "sin resultado",
    "error": "error",
}


# ---------------------------------------------------------------- lectura


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Lee un JSONL tolerando la ultima linea a medio escribir.

    El diario del investigador es append-only y se lee EN CALIENTE: si el
    agente esta a mitad de un write, la ultima linea no parsea todavia. Eso no
    puede tumbar el informe.
    """
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    # Se lee en BINARIO y se decodifica por linea: en modo texto, un byte
    # invalido lanza UnicodeDecodeError al ITERAR el fichero, o sea antes
    # del try, y tumbaba el informe entero por una linea que una corrida
    # solapada dejo partida. Mismo fallo que ya mordio en la cache HTTP y
    # en el promotor.
    with path.open("rb") as fh:
        for raw in fh:
            if not raw.strip():
                continue
            try:
                rows.append(json.loads(raw.decode("utf-8")))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def load_snapshots(path: Path = SNAPSHOTS) -> list[dict[str, Any]]:
    return _read_jsonl(path)


def append_snapshot(path: Path, row: Mapping[str, Any]) -> None:
    """Anade una fila al diario. Append-only: nunca reescribe el historico."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- calculo


def _revenue_index(metrics: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    """Indexa revenue por fold.

    agg_artist_metrics agrupa por ``artist_id or artist_fold``, asi que la
    clave de cruce es esa y no el nombre crudo: en cuanto una casa cambia una
    tilde, el nombre deja de casar y el fold sigue casando.
    """
    index: dict[str, float] = {}
    for row in metrics:
        key = row.get("artist_key") or row.get("artist_id")
        revenue = row.get("revenue_eur")
        if key and revenue is not None:
            index[key] = float(revenue)
    return index


def _impact_rows(
    candidates: Iterable[Mapping[str, Any]],
    revenue_index: Mapping[str, float],
) -> list[dict[str, Any]]:
    """Ordena los candidatos por lotes que desbloquean.

    El revenue se queda en ``None`` cuando el fold no cruza. Es la misma regla
    que to_eur() devolviendo None en vez de 1.0: un hueco visible, no un cero
    que se lee como un hecho.
    """
    rows = []
    for cand in candidates:
        key = cand.get("artist_key") or cand.get("artist_id") or ""
        rows.append(
            {
                "artist_key": key,
                "display_name": cand.get("display_name") or key,
                "lots_observed": cand.get("lots_observed") or 0,
                "curation_status": cand.get("curation_status"),
                "houses": list(cand.get("houses") or []),
                "revenue_eur": revenue_index.get(key),
                "sample_lot_url": (cand.get("sample_lot_urls") or [None])[0],
            }
        )
    rows.sort(key=lambda r: (r["lots_observed"], r["revenue_eur"] or 0), reverse=True)
    return rows


def _crossed_count(rows: Iterable[Mapping[str, Any]]) -> int:
    """Cuantas filas de impacto tienen revenue cruzado.

    Existe porque el top por lotes engana: los candidatos con MAS lotes son
    justo los que no cruzan. agg_artist_metrics solo agrega lo vendido, y Duran
    oferta mucho que no vende, asi que un artista con 380 lotes ofertados puede
    no aparecer. Sin este contador la tabla parece rota cuando es correcta.
    """
    return sum(1 for r in rows if r.get("revenue_eur") is not None)


def _by_revenue(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Los candidatos que SI cruzan, por dinero desbloqueado."""
    crossed = [dict(r) for r in rows if r.get("revenue_eur") is not None]
    crossed.sort(key=lambda r: r["revenue_eur"], reverse=True)
    return crossed


def _evidence_counts(research: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Cuenta el diario del investigador.

    ``auto_promote`` se cuenta aparte de ``matched`` a proposito: un match con
    revision pendiente es trabajo hecho pero no cobrado, y confundirlos es
    creerse mas avanzado de lo que se esta.
    """
    status: dict[str, int] = {}
    auto_promote = 0
    review_required = 0
    for row in research:
        key = str(row.get("status") or "unknown")
        status[key] = status.get(key, 0) + 1
        if row.get("auto_promote"):
            auto_promote += 1
        if row.get("review_required"):
            review_required += 1
    return {
        "status": status,
        "auto_promote": auto_promote,
        "review_required": review_required,
        "total": sum(status.values()),
    }


# Ocupaciones de Wikidata que sostienen un hallazgo presentable. Es la misma
# disciplina que artist_master_promote.py: sin este filtro se cuelan homonimos
# ("Damian Diaz, futbolista", "Francisco Rodriguez Martin, futbolista") que son
# otra persona con el mismo nombre. Presumir de esos seria presumir de error.
_ART_WORDS = (
    "pintor", "pintora", "artista", "escultor", "escultora", "grabador",
    "grabadora", "dibujante", "ilustrador", "ilustradora", "fotograf",
    "ceramista", "acuarelista", "muralista", "orfebre", "arquitect",
    "diseñador", "diseñadora", "litograf", "cartelista", "miniaturista",
)


def _is_artist(occupations: Iterable[str]) -> bool:
    import unicodedata

    for occ in occupations:
        flat = unicodedata.normalize("NFKD", str(occ).lower())
        flat = "".join(c for c in flat if not unicodedata.combining(c))
        if any(w.replace("ñ", "n").replace("ó", "o") in flat for w in _ART_WORDS):
            return True
    return False


def _findings(research: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Los artistas cuyo pais NO teniamos y ahora si.

    Es la cosecha del trabajo, y es lo que faltaba en el panel: un contador de
    'matched' no ensena a nadie que hemos identificado a Casimiro Sainz. Solo
    entran ocupaciones artisticas, por la razon de _ART_WORDS.
    """
    out = []
    for row in research:
        if row.get("status") != "matched":
            continue
        if (row.get("master_context") or {}).get("country_birth"):
            continue
        claims = (row.get("match") or {}).get("claims", {})
        country = next(
            (c.get("country_iso") for c in claims.get("P19", []) if c.get("country_iso")),
            None,
        )
        if not country:
            continue
        occupations = [c.get("label") or "" for c in claims.get("P106", [])]
        if not _is_artist(occupations):
            continue
        born = next((str(c.get("time", ""))[1:5] for c in claims.get("P569", [])), "")
        qid = row.get("wikidata_id")
        out.append(
            {
                "name": row.get("display_name") or row.get("artist_key"),
                "country": country,
                "occupation": occupations[0] if occupations else "",
                "born": born,
                "lots": int((row.get("priority_metrics") or {}).get("lots") or 0),
                "url": f"https://www.wikidata.org/wiki/{qid}" if qid else "",
            }
        )
    out.sort(key=lambda r: r["lots"], reverse=True)
    return out


def _promotable(research: Iterable[Mapping[str, Any]]) -> int:
    """Fichas que el promotor aceptaria hoy.

    NO cuenta ``auto_promote``: el investigador lo escribe como literal ``False``
    en TODAS sus filas (lineas 816-817 de artist_master_web_research.py), asi que
    leer ese campo daba "0 promovibles" mientras el promotor reportaba 819. Un
    literal no es un juicio.

    La condicion es la del promotor: ``matched`` (nunca ``ambiguous``, que es un
    homonimo sin resolver), ocupacion artistica, pais deducible del lugar de
    nacimiento, y que no este ya en el maestro.

    Delega en ``scripts.artist_master_promote.build_entries``: es LA autoridad
    sobre que se promueve, y reimplementar su criterio aqui daba otra cifra
    (627 frente a 826) porque el resuelve paises via _countries.yaml y fusiona
    alias del maestro. Dos respuestas a la misma pregunta es peor que una.

    Si el promotor no se puede importar, se cae a ``_findings`` en vez de
    reventar: el panel es un lector y no debe morir por una dependencia.
    """
    rows = list(research)
    try:
        from scripts.artist_master_promote import build_entries

        entries, _ = build_entries(iter(rows))
        return len(entries)
    except Exception:
        return len(_findings(rows))


def _health(rate: float | None, error_pct: float) -> dict[str, str]:
    """Semaforo. Traduce ritmo y errores a algo que se lee sin interpretar."""
    if rate is None:
        return {"level": "unknown", "label": "Sin medir",
                "note": "Hace falta una segunda medicion para saber el ritmo."}
    if rate <= 0:
        return {"level": "bad", "label": "Parado",
                "note": "No se han buscado artistas nuevos desde la ultima medicion."}
    if error_pct >= 15.0:
        return {"level": "warn", "label": "Con incidencias",
                "note": "Avanza, pero Wikidata esta rechazando muchas consultas."}
    return {"level": "ok", "label": "En marcha",
            "note": "Buscando artistas con normalidad."}


def _error_digest(research: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Agrupa los errores por tipo y guarda los nombres para reintentarlos.

    Los errores observados son de RED (``URLError: getaddrinfo failed`` tras 4
    intentos), no de rate limiting. La distincion importa: un fallo de DNS se
    reintenta con ``--retry-errors`` y se recupera entero; si nos estuvieran
    frenando, reintentar mas rapido lo empeoraria. Por eso se muestra el TIPO y
    el mensaje, no solo el numero.
    """
    rows = []
    by_type: dict[str, int] = {}
    for row in research:
        if row.get("status") != "error":
            continue
        err = row.get("error") or {}
        etype = str(err.get("type") or "unknown")
        by_type[etype] = by_type.get(etype, 0) + 1
        rows.append(
            {
                "display_name": row.get("display_name") or row.get("artist_key"),
                "artist_key": row.get("artist_key"),
                "type": etype,
                "message": err.get("message") or "",
                "lots": (row.get("priority_metrics") or {}).get("lots"),
            }
        )
    rows.sort(key=lambda r: r["lots"] or 0, reverse=True)
    return {"total": len(rows), "by_type": by_type, "rows": rows}


def _rate(snapshots: list[Mapping[str, Any]]) -> float | None:
    """Filas investigadas por hora entre el primer y el ultimo snapshot.

    Devuelve None con una sola medicion o sin tiempo transcurrido: un 0 se
    leeria como "atascado", que es una afirmacion distinta de "no lo se".
    """
    if len(snapshots) < 2:
        return None
    first, last = snapshots[0], snapshots[-1]
    try:
        t0 = datetime.fromisoformat(str(first.get("stamped_at")))
        t1 = datetime.fromisoformat(str(last.get("stamped_at")))
    except (TypeError, ValueError):
        return None
    hours = (t1 - t0).total_seconds() / 3600.0
    if hours <= 0:
        return None
    delta = (last.get("researched") or 0) - (first.get("researched") or 0)
    return delta / hours


def _eta_hours(pending: Any, rate: float | None) -> float | None:
    """Horas para vaciar la cola al ritmo medido."""
    if not rate or rate <= 0 or not pending:
        return None
    return float(pending) / rate


def _fmt_eta(hours: float | None) -> str:
    if hours is None:
        return "&mdash;"
    if hours < 48:
        return f"{hours:.0f} h"
    days = hours / 24.0
    if days < 90:
        return f"{days:.0f} dias"
    return f"{days / 30.44:.0f} meses"


def _snapshot_row(
    coverage: Mapping[str, Any],
    evidence: Mapping[str, Any],
    stamped_at: str,
) -> dict[str, Any]:
    """Congela los contadores del momento para dibujar la curva de avance."""
    status = evidence.get("status", {})
    curation = coverage.get("curation_status_counts", {})
    disposition = coverage.get("disposition_counts", {})
    return {
        "stamped_at": stamped_at,
        "author_folds": coverage.get("author_folds"),
        "curated_master_rows": coverage.get("curated_master_rows"),
        "pending_identity_rows": coverage.get("pending_identity_rows"),
        "needs_web": curation.get("needs_web"),
        "verified": curation.get("verified"),
        "master_disposition": disposition.get("master"),
        "researched": evidence.get("total", 0),
        "matched": status.get("matched", 0),
        "ambiguous": status.get("ambiguous", 0),
        "not_found": status.get("not_found", 0),
        "error": status.get("error", 0),
        "auto_promote": evidence.get("auto_promote", 0),
        "review_required": evidence.get("review_required", 0),
    }


# ---------------------------------------------------------------- formato


def _num(value: Any) -> str:
    if value is None:
        return "&mdash;"
    return f"{int(value):,}".replace(",", ".")


def _eur(value: Any) -> str:
    """Un hueco se pinta como hueco. Nunca como 0 &euro;."""
    if value is None:
        return '<span class="gap" title="Sin cruce en agg_artist_metrics">sin dato</span>'
    return f"{int(value):,}".replace(",", ".") + "&nbsp;&euro;"


def _pct(part: Any, whole: Any) -> str:
    if not whole:
        return "&mdash;"
    return f"{100.0 * (part or 0) / whole:.1f}%".replace(".", ",")


# ---------------------------------------------------------------- graficos

def _gauge(pct: float) -> str:
    """Arco de progreso con la cifra dentro.

    Un solo numero protagonista: la guia de dataviz pide hero number, no
    grafico, cuando el dato es un titular unico. El arco es semicircular
    (mas legible de un vistazo que un donut) y la cifra va en el centro.
    """
    import math

    pct = max(0.0, min(100.0, pct))
    r, cx, cy = 130.0, 160.0, 150.0
    ang = math.pi * (1.0 - pct / 100.0)
    ex, ey = cx + r * math.cos(ang), cy - r * math.sin(ang)
    large = 1 if pct > 50 else 0
    return f"""<svg viewBox="0 0 320 170" class="gauge" role="img"
 aria-label="Progreso: {pct:.0f} por ciento de los artistas ya revisados">
<path d="M{cx - r},{cy} A{r},{r} 0 1 1 {cx + r},{cy}" class="gt"/>
<path d="M{cx - r},{cy} A{r},{r} 0 {large} 1 {ex:.1f},{ey:.1f}" class="gv"/>
<text x="{cx}" y="{cy - 22}" class="gn" text-anchor="middle">{pct:.0f}%</text>
<text x="{cx}" y="{cy + 4}" class="gl" text-anchor="middle">revisados</text>
</svg>"""


def _finding_cards(found: list[dict[str, Any]], limit: int = 12) -> str:
    if not found:
        return '<p class="empty">Todavía no hay hallazgos que enseñar.</p>'
    cards = []
    for f in found[:limit]:
        flag = _flag(f["country"])
        name = f["name"]
        if f["url"]:
            name = f'<a href="{f["url"]}" target="_blank" rel="noopener">{name}</a>'
        vida = f' &middot; n. {f["born"]}' if f["born"] else ""
        cards.append(
            f'<li><span class="fg">{flag}</span>'
            f'<span class="fn">{name}</span>'
            f'<span class="fm">{f["occupation"]}{vida}</span>'
            f'<span class="fl">{f["lots"]} obras</span></li>'
        )
    return f'<ul class="finds">{"".join(cards)}</ul>'


def _flag(iso: str) -> str:
    """Bandera emoji desde el ISO-2. Es decoracion; el codigo va al lado."""
    if not iso or len(iso) != 2:
        return "&#127988;"
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso.upper())


SPARK_W, SPARK_H = 320.0, 64.0


def _spark(values: list[float], cls: str = "acc") -> str:
    """Curva de avance con el punto final marcado."""
    if len(values) < 2:
        return '<p class="empty">Una sola medición todavía: la curva aparece en la próxima ejecución.</p>'
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    pts = [
        (
            i * SPARK_W / (len(values) - 1),
            SPARK_H - 6 - (v - lo) * (SPARK_H - 14) / span,
        )
        for i, v in enumerate(values)
    ]
    path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{path} L{SPARK_W:.1f},{SPARK_H:.1f} L0,{SPARK_H:.1f} Z"
    ex, ey = pts[-1]
    return (
        f'<svg viewBox="0 0 {SPARK_W:.0f} {SPARK_H:.0f}" class="spark {cls}" role="img" '
        f'aria-label="Evolucion: de {values[0]:.0f} a {values[-1]:.0f}">'
        f'<path d="{area}" class="sf"/><path d="{path}" class="sl"/>'
        f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="3.2" class="sd"/></svg>'
    )


def _stack(counts: Mapping[str, int]) -> str:
    """Barra apilada de estados de la investigacion."""
    total = sum(counts.values()) or 1
    out, x = [], 0.0
    for key in STATUS_ORDER:
        n = counts.get(key, 0)
        if not n:
            continue
        w = 100.0 * n / total
        out.append(
            f'<span class="seg s-{key}" style="width:{w:.2f}%" '
            f'title="{STATUS_ES[key]}: {n}"></span>'
        )
        x += w
    return f'<div class="stack">{"".join(out)}</div>'


def _legend(counts: Mapping[str, int]) -> str:
    total = sum(counts.values()) or 1
    items = []
    for key in STATUS_ORDER:
        n = counts.get(key, 0)
        if not n:
            continue
        items.append(
            f'<li><span class="dot s-{key}"></span><b>{_num(n)}</b> '
            f'<span class="lab">{STATUS_ES[key]}</span> '
            f'<span class="sub">{_pct(n, total)}</span></li>'
        )
    return f'<ul class="legend">{"".join(items)}</ul>'


def _error_panel(errors: Mapping[str, Any]) -> str:
    """Los errores, con su causa y el comando que los recupera."""
    if not errors.get("total"):
        return '<div class="panel"><p class="ok-note">Sin errores en el diario.</p></div>'
    types = ", ".join(f"{k} &times;{v}" for k, v in errors["by_type"].items())
    items = "".join(
        f'<li><b>{r["display_name"]}</b>'
        f'<span class="sub">{_num(r["lots"]) if r["lots"] else "&mdash;"} lotes</span>'
        f'<span class="msg">{r["message"][:120]}</span></li>'
        for r in errors["rows"][:12]
    )
    return f"""<div class="panel">
    <p class="sub" style="margin:0 0 12px">{types}</p>
    <ul class="errs">{items}</ul>
    <p class="note-block" style="margin-top:16px">Son fallos de <b>red</b>
    (<code>getaddrinfo failed</code> tras 4 intentos), no de rate limiting: el
    investigador perdió DNS y se rindió en esas filas. Se recuperan enteras sin
    reinvestigar nada más &mdash;
    <code>python scripts/artist_master_web_research.py --retry-errors</code>.</p>
    </div>"""


def _impact_table(rows: list[dict[str, Any]]) -> str:
    body = []
    for r in rows[:TOP_IMPACT]:
        name = r["display_name"]
        if r["sample_lot_url"]:
            name = f'<a href="{r["sample_lot_url"]}" target="_blank" rel="noopener">{name}</a>'
        houses = ", ".join(h.replace("_subastas", "").replace("_auctions", "") for h in r["houses"])
        body.append(
            f'<tr><td class="nm">{name}</td>'
            f'<td class="n">{_num(r["lots_observed"])}</td>'
            f'<td class="n">{_eur(r["revenue_eur"])}</td>'
            f'<td class="ho">{houses}</td></tr>'
        )
    return (
        '<table class="impact"><thead><tr><th>Candidato</th><th class="n">Lotes</th>'
        '<th class="n">Revenue cruzado</th><th>Casas</th></tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table>'
    )


# ---------------------------------------------------------------- render


def render(
    coverage: Mapping[str, Any],
    evidence: Mapping[str, Any],
    impact: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    manifest: Mapping[str, Any],
    generated_at: str,
    errors: Mapping[str, Any] | None = None,
    last_write: str = "&mdash;",
    research_rows: list[dict[str, Any]] | None = None,
) -> str:
    errors = errors or {"total": 0, "by_type": {}, "rows": []}
    research_rows = research_rows or []
    status = evidence.get("status", {})
    researched = evidence.get("total", 0)
    pending = coverage.get("pending_identity_rows") or 0
    author_folds = coverage.get("author_folds") or 0
    curated = coverage.get("curated_master_rows") or 0
    auto = evidence.get("auto_promote", 0)

    crossed = _crossed_count(impact)
    by_revenue = _by_revenue(impact)
    total_pending_revenue = sum(r["revenue_eur"] for r in by_revenue) or None

    rate = _rate(snapshots)
    rate_txt = f"{rate:.0f}" if rate is not None else "&mdash;"
    eta = _eta_hours(pending - researched, rate)

    found = _findings(research_rows)
    promotable = _promotable(research_rows)
    error_pct = 100.0 * (errors.get("total") or 0) / (researched or 1)
    health = _health(rate, error_pct)

    if eta is None:
        eta_sentence = (
            "Aun no se puede estimar cuando acaba: hace falta otra medicion."
            if rate is None else "Ahora mismo no avanza, asi que no hay fecha estimada."
        )
    else:
        eta_sentence = (
            f"Al ritmo actual ({rate:.0f} nombres por hora) quedan unas "
            f"<b>{_fmt_eta(eta)}</b> de trabajo."
        )

    spark_researched = _spark([float(s.get("researched") or 0) for s in snapshots])
    spark_master = _spark([float(s.get("curated_master_rows") or 0) for s in snapshots], "ok")

    shards = manifest.get("shards", {})
    shard_bars = "".join(
        f'<li><span class="sh">{k}</span>'
        f'<span class="bar"><i style="width:{100.0 * v / max(shards.values()):.1f}%"></i></span>'
        f'<span class="n">{_num(v)}</span></li>'
        for k, v in sorted(shards.items())
    )

    return f"""<title>Maestro de Artistas</title>
<style>
:root {{
  --paper:#EFEBE3; --ink:#1B1A17; --muted:#6B6558; --rule:#D9D2C5; --card:#F7F4EE;
  --ok:#2F6B4F; --warn:#B07A2A; --bad:#9B3B2F; --dim:#8A8375; --acc:#B07A2A;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --paper:#16150F; --ink:#EDE8DC; --muted:#9C9484; --rule:#302C22; --card:#1E1C15;
    --ok:#6FB58C; --warn:#D9A85A; --bad:#D2705F; --dim:#7A7365; --acc:#D9A85A;
  }}
}}
:root[data-theme="dark"] {{
  --paper:#16150F; --ink:#EDE8DC; --muted:#9C9484; --rule:#302C22; --card:#1E1C15;
  --ok:#6FB58C; --warn:#D9A85A; --bad:#D2705F; --dim:#7A7365; --acc:#D9A85A;
}}
* {{ box-sizing:border-box; }}
body {{
  background:var(--paper); color:var(--ink); margin:0;
  font:16px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
  font-variant-numeric:tabular-nums;
}}
.wrap {{ max-width:1080px; margin:0 auto; padding:48px 24px 80px; display:flex; flex-direction:column; gap:44px; }}
h1 {{ font:600 34px/1.15 ui-serif,Georgia,"Times New Roman",serif; margin:0; letter-spacing:-.01em; text-wrap:balance; }}
h2 {{ font:600 13px/1.3 ui-sans-serif,sans-serif; text-transform:uppercase; letter-spacing:.09em;
     color:var(--muted); margin:0 0 16px; }}
.sub {{ color:var(--muted); font-size:13px; }}
header .sub {{ margin-top:8px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:14px; }}
.kpi {{ background:var(--card); border:1px solid var(--rule); border-radius:3px; padding:18px 18px 16px;
        display:flex; flex-direction:column; gap:4px; }}
.kpi b {{ font:600 30px/1 ui-serif,Georgia,serif; }}
.kpi .lab {{ font-size:12px; text-transform:uppercase; letter-spacing:.07em; color:var(--muted); }}
.kpi .note {{ font-size:12px; color:var(--dim); }}
.stack {{ display:flex; height:12px; border-radius:2px; overflow:hidden; border:1px solid var(--rule); }}
.seg {{ display:block; }}
.s-matched {{ background:var(--ok); }} .s-ambiguous {{ background:var(--warn); }}
.s-not_found {{ background:var(--dim); }} .s-error {{ background:var(--bad); }}
.legend {{ list-style:none; padding:0; margin:14px 0 0; display:flex; flex-wrap:wrap; gap:18px; font-size:13px; }}
.legend .lab {{ color:var(--muted); }}
.dot {{ width:9px; height:9px; border-radius:50%; display:inline-block; margin-right:7px; }}
.spark {{ width:100%; height:64px; display:block; }}
.sf {{ fill:var(--acc); opacity:.13; }} .sl {{ fill:none; stroke:var(--acc); stroke-width:1.8; }}
.sd {{ fill:var(--acc); }}
.spark.ok .sl {{ stroke:var(--ok); }} .spark.ok .sf {{ fill:var(--ok); }} .spark.ok .sd {{ fill:var(--ok); }}
.two {{ display:grid; grid-template-columns:1fr 1fr; gap:26px; }}
@media (max-width:720px) {{ .two {{ grid-template-columns:1fr; }} }}
.panel {{ background:var(--card); border:1px solid var(--rule); border-radius:3px; padding:20px; }}
.panel h2 {{ margin-bottom:12px; }}
.tw {{ overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th {{ text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.07em;
      color:var(--muted); font-weight:600; padding:0 10px 9px; border-bottom:1px solid var(--rule); }}
td {{ padding:9px 10px; border-bottom:1px solid var(--rule); }}
td.n, th.n {{ text-align:right; }}
td.nm a {{ color:var(--ink); text-decoration:none; border-bottom:1px solid var(--rule); }}
td.nm a:hover {{ border-color:var(--acc); }}
td.ho {{ color:var(--muted); font-size:12.5px; }}
.gap {{ color:var(--dim); font-style:italic; }}
.shards {{ list-style:none; padding:0; margin:0; display:grid;
           grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:7px 20px; font-size:13px; }}
.shards li {{ display:flex; align-items:center; gap:9px; }}
.sh {{ width:14px; color:var(--muted); text-transform:uppercase; font-size:11px; }}
.bar {{ flex:1; height:6px; background:var(--rule); border-radius:2px; overflow:hidden; }}
.bar i {{ display:block; height:100%; background:var(--acc); opacity:.6; }}
.note-block {{ font-size:13px; color:var(--muted); border-left:2px solid var(--rule); padding-left:14px; }}
.empty {{ color:var(--dim); font-size:13px; font-style:italic; margin:8px 0 0; }}
a:focus-visible, [tabindex]:focus-visible {{ outline:2px solid var(--acc); outline-offset:2px; }}
footer {{ color:var(--dim); font-size:12px; border-top:1px solid var(--rule); padding-top:18px; }}
.hrow {{ display:flex; align-items:flex-start; justify-content:space-between; gap:20px; flex-wrap:wrap; }}
.refresh {{ font:600 12px/1 ui-sans-serif,sans-serif; text-transform:uppercase; letter-spacing:.08em;
  color:var(--ink); background:var(--card); border:1px solid var(--rule); border-radius:3px;
  padding:11px 18px; cursor:pointer; flex:none; }}
.refresh:hover {{ border-color:var(--acc); color:var(--acc); }}
.refresh[data-busy] {{ opacity:.5; cursor:progress; }}
.stamp {{ color:var(--acc); }}
.hero {{ display:grid; grid-template-columns:340px 1fr; gap:34px; align-items:center; }}
@media (max-width:760px) {{ .hero {{ grid-template-columns:1fr; }} }}
.gauge {{ width:100%; max-width:340px; height:auto; display:block; }}
.gt {{ fill:none; stroke:var(--rule); stroke-width:22; stroke-linecap:round; }}
.gv {{ fill:none; stroke:var(--acc); stroke-width:22; stroke-linecap:round; }}
.gn {{ fill:var(--ink); font:600 54px/1 ui-serif,Georgia,serif; }}
.gl {{ fill:var(--muted); font:500 13px/1 ui-sans-serif,sans-serif;
       text-transform:uppercase; letter-spacing:.1em; }}
.hero-cap {{ text-align:center; color:var(--muted); font-size:13px; margin:2px 0 0; }}
.lead {{ font-size:17px; line-height:1.6; margin:0 0 18px; }}
.status {{ display:flex; gap:13px; align-items:flex-start; padding:14px 16px;
  border:1px solid var(--rule); border-radius:3px; background:var(--card); }}
.status div {{ display:flex; flex-direction:column; gap:2px; }}
.status b {{ font-size:15px; }}
.status span {{ font-size:13px; color:var(--muted); }}
.sdot {{ width:11px; height:11px; border-radius:50%; margin-top:5px; flex:none; }}
.s-ok .sdot {{ background:var(--ok); }} .s-warn .sdot {{ background:var(--warn); }}
.s-bad .sdot {{ background:var(--bad); }} .s-unknown .sdot {{ background:var(--dim); }}
.s-ok b {{ color:var(--ok); }} .s-warn b {{ color:var(--warn); }} .s-bad b {{ color:var(--bad); }}
.eta {{ font-size:14px; color:var(--muted); margin:16px 0 0; }}
.finds {{ list-style:none; padding:0; margin:0; display:grid;
  grid-template-columns:repeat(auto-fill,minmax(250px,1fr)); gap:14px 22px; }}
.finds li {{ display:grid; grid-template-columns:auto 1fr; gap:2px 11px;
  align-items:baseline; padding-bottom:12px; border-bottom:1px solid var(--rule); }}
.fg {{ grid-row:span 2; font-size:22px; line-height:1; }}
.fn {{ font-weight:600; font-size:15px; }}
.fn a {{ color:var(--ink); text-decoration:none; border-bottom:1px solid var(--rule); }}
.fn a:hover {{ border-color:var(--acc); }}
.fm {{ font-size:12.5px; color:var(--muted); grid-column:2; }}
.fl {{ font-size:12px; color:var(--dim); grid-column:2; }}
.split {{ border:0; border-top:1px solid var(--rule); margin:8px 0 -30px; }}
.tech-note {{ font-size:12px; text-transform:uppercase; letter-spacing:.09em;
  color:var(--dim); margin:0 0 -24px; }}
.errs {{ list-style:none; padding:0; margin:0; display:flex; flex-direction:column; gap:9px; font-size:13.5px; }}
.errs li {{ display:flex; gap:12px; align-items:baseline; flex-wrap:wrap;
  padding-bottom:9px; border-bottom:1px solid var(--rule); }}
.errs .sub {{ color:var(--muted); font-size:12px; flex:none; }}
.errs .msg {{ color:var(--bad); font-size:12px; font-family:ui-monospace,monospace; }}
.ok-note {{ color:var(--ok); font-size:13px; margin:0; }}
code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.92em;
  background:var(--rule); padding:1px 5px; border-radius:2px; }}
@media (prefers-reduced-motion:reduce) {{ * {{ transition:none !important; }} }}
</style>
<div class="wrap">

<header>
  <div class="hrow">
    <div>
      <h1>Maestro de artistas</h1>
      <p class="sub">Seguimiento del ciclo de curación &middot;
         <b class="stamp">medición {len(snapshots)}</b> &middot; {generated_at}
         &middot; diario escrito {last_write}</p>
    </div>
    <button id="rf" type="button" class="refresh">Refrescar</button>
  </div>
</header>

<section class="hero">
  <div class="hero-g">
    {_gauge(100.0 * researched / (pending or 1))}
    <p class="hero-cap">{_num(researched)} de {_num(pending)} nombres</p>
  </div>
  <div class="hero-t">
    <p class="lead">Estamos repasando <b>{_num(pending)} nombres</b> que aparecen en los
    catálogos de subastas para averiguar <b>quién es cada artista y de qué país es</b>.
    Muchos son variantes del mismo pintor o cosas que ni siquiera son personas.</p>
    <div class="status s-{health["level"]}">
      <span class="sdot"></span>
      <div><b>{health["label"]}</b><span>{health["note"]}</span></div>
    </div>
    <p class="eta">{eta_sentence}</p>
  </div>
</section>

<section>
  <h2>Lo que llevamos encontrado</h2>
  <p class="sub" style="margin:-8px 0 16px">
    <b>{_num(len(found))} artistas</b> identificados con su país de nacimiento, que antes
    no lo tenían. Estos son los que más obras tienen en los catálogos:</p>
  <div class="panel">{_finding_cards(found)}</div>
</section>

<section>
  <h2>Las cifras, explicadas</h2>
  <div class="grid">
    <div class="kpi"><span class="lab">Nombres por repasar</span><b>{_num(pending)}</b>
      <span class="note">Todos los que salen en los catálogos y aún no sabemos quién son.</span></div>
    <div class="kpi"><span class="lab">Ya repasados</span><b>{_num(researched)}</b>
      <span class="note">Buscados uno a uno en Wikidata, la enciclopedia libre.</span></div>
    <div class="kpi"><span class="lab">Artistas con país nuevo</span><b>{_num(len(found))}</b>
      <span class="note">El fruto: gente que ahora sabemos de dónde es.</span></div>
    <div class="kpi"><span class="lab">Fichas definitivas</span><b>{_num(curated)}</b>
      <span class="note">Las que ya están revisadas a mano y son oficiales.</span></div>
  </div>
  <p class="note-block" style="margin-top:18px">Repasar no es lo mismo que dar por bueno.
  El ordenador propone, pero <b>una persona revisa antes de que la ficha sea oficial</b>:
  hay pintores distintos que se llaman igual, y equivocarse ahí ensucia el archivo entero.
  Por eso las <i>fichas definitivas</i> suben más despacio que los <i>repasados</i>.
  Ahora mismo hay <b>{_num(promotable)} fichas ya listas</b> esperando ese último visto bueno.</p>
</section>

<hr class="split"/>
<p class="tech-note">A partir de aquí, el detalle técnico del proceso.</p>

<section class="two">
  <div>
    <h2>Ritmo de investigación</h2>
    {spark_researched}
    <p class="sub">Filas escritas por el investigador, medición a medición.</p>
  </div>
  <div>
    <h2>Fichas en el maestro</h2>
    {spark_master}
    <p class="sub">Lo único que cuenta como avance real: identidad curada.</p>
  </div>
</section>

<section>
  <h2>Calidad de la evidencia</h2>
  <div class="panel">
    {_stack(status)}
    {_legend(status)}
    <div class="grid" style="margin-top:22px">
      <div class="kpi"><span class="lab">Listas para promover</span><b>{_num(promotable)}</b>
        <span class="note">{_pct(promotable, researched)} de lo investigado</span></div>
      <div class="kpi"><span class="lab">Sin identidad firme</span><b>{_num(researched - promotable)}</b>
        <span class="note">homónimos, sin resultado o ya en el maestro</span></div>
      <div class="kpi"><span class="lab">Conflicto de evidencia</span><b>{_num(coverage.get("rows_with_evidence_conflict"))}</b>
        <span class="note">catálogo contra catálogo</span></div>
      <div class="kpi"><span class="lab">Posible alias existente</span><b>{_num(coverage.get("rows_with_possible_master_match"))}</b>
        <span class="note">quizá ya están en el maestro</span></div>
    </div>
    <p class="note-block" style="margin-top:22px">Un <b>match no es una promoción</b>. Solo
    <code>status=matched</code> sin ambigüedad entra; un homónimo sin resolver
    (Chillida padre e hijo, dos Antonio Saura) se queda fuera a propósito, porque
    desempatarlo por popularidad es exactamente el error que el investigador evita.
    <br/><br/>El contador de arriba aplica esa misma regla &mdash; <b>no</b> lee el campo
    <code>auto_promote</code> del diario, que es un literal <code>False</code> en todas
    las filas y hacía leer &laquo;0 promovibles&raquo; con {_num(promotable)} esperando.
    Contrástalo con <code>python scripts/artist_master_promote.py --report</code>.</p>
  </div>
</section>

<section>
  <h2>Impacto en el ranking</h2>
  <div class="grid" style="margin-bottom:20px">
    <div class="kpi"><span class="lab">Candidatos</span><b>{_num(len(impact))}</b>
      <span class="note">pendientes de identidad</span></div>
    <div class="kpi"><span class="lab">Con revenue cruzado</span><b>{_num(crossed)}</b>
      <span class="note">{_pct(crossed, len(impact))} de los candidatos</span></div>
    <div class="kpi"><span class="lab">Dinero en cola</span><b>{_eur(total_pending_revenue)}</b>
      <span class="note">de lo que sí cruza</span></div>
  </div>

  <div class="two">
    <div class="panel tw">
      <h2>Por dinero desbloqueado</h2>
      {_impact_table(by_revenue)}
    </div>
    <div class="panel tw">
      <h2>Por lotes observados</h2>
      {_impact_table(impact)}
    </div>
  </div>

  <p class="note-block" style="margin-top:18px">Las dos tablas no coinciden, y esa es la
  información. <code>agg_artist_metrics</code> solo agrega lo <b>vendido</b>: Durán oferta
  mucho que no vende, así que los candidatos con más lotes ofertados suelen mostrar
  <span class="gap">sin dato</span>. El cruce va por <i>fold</i>, nunca por nombre crudo, y un
  hueco se pinta como hueco &mdash; un 0&nbsp;&euro; diría &laquo;no vendió nada&raquo;, que es
  falso.</p>
</section>

<section>
  <h2>Salud del loop</h2>
  <div class="grid" style="margin-bottom:20px">
    <div class="kpi"><span class="lab">Ritmo medido</span><b>{rate_txt}</b>
      <span class="note">filas por hora</span></div>
    <div class="kpi"><span class="lab">Vaciar la cola</span><b>{_fmt_eta(eta)}</b>
      <span class="note">al ritmo actual</span></div>
    <div class="kpi"><span class="lab">Errores</span><b>{_num(errors["total"])}</b>
      <span class="note">{_pct(errors["total"], researched)} de lo investigado</span></div>
    <div class="kpi"><span class="lab">Última escritura</span><b>{last_write}</b>
      <span class="note">del diario del investigador</span></div>
  </div>
  {_error_panel(errors)}
</section>

<section>
  <h2>Cola por shard</h2>
  <div class="panel"><ul class="shards">{shard_bars}</ul></div>
</section>

<footer>
  Lector puro sobre <code>data/gold</code> y <code>data/enrichments</code>.
  No promueve, no escribe en los shards YAML ni en la cola de revisión.
  Histórico en <code>data/gold/artist_master_snapshots.jsonl</code>.
  Para tomar una medición nueva:
  <code>python -m pipelines.analytics.build_artist_master_report</code>.
</footer>

</div>
<script>
// location.reload() a secas sirve la copia CACHEADA: en el Artifact publicado
// repintaba exactamente lo mismo y parecia que el panel estaba muerto. Se anade
// un parametro que cambia en cada clic para forzar una peticion nueva.
//
// Aun asi el boton solo trae el HTML que ya existe. Generar una MEDICION nueva
// es cosa del script de Python -- una pagina no puede lanzar un proceso, y
// fingir que si con un spinner seria mentira.
(function () {{
  var b = document.getElementById("rf");
  if (!b) return;
  b.addEventListener("click", function () {{
    b.setAttribute("data-busy", "1");
    b.textContent = "Recargando";
    var u = new URL(location.href);
    u.searchParams.set("t", Date.now().toString(36));
    location.replace(u.toString());
  }});
}})();
</script>
"""


def main() -> None:
    coverage = _read_json(COVERAGE)
    research = _read_jsonl(RESEARCH)
    manifest = _read_json(REVIEW_MANIFEST)
    evidence = _evidence_counts(research)

    revenue_index = _revenue_index(_read_jsonl(ARTIST_METRICS))
    candidates = [
        row
        for row in _read_jsonl(DIM_ARTISTS)
        if row.get("curation_status") in {"needs_web", "ambiguous", "needs_review"}
    ]
    impact = _impact_rows(candidates, revenue_index)

    errors = _error_digest(research)

    # Última escritura del diario: si el loop se paro, esto lo delata antes que
    # cualquier contador.
    last_write = "&mdash;"
    if RESEARCH.exists():
        last_write = datetime.fromtimestamp(RESEARCH.stat().st_mtime).strftime("%H:%M")

    stamped_at = datetime.now().isoformat(timespec="seconds")
    append_snapshot(SNAPSHOTS, _snapshot_row(coverage, evidence, stamped_at))
    snapshots = load_snapshots(SNAPSHOTS)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        render(
            coverage, evidence, impact, snapshots, manifest, stamped_at,
            errors=errors, last_write=last_write, research_rows=research,
        ),
        encoding="utf-8",
    )
    rate = _rate(snapshots)
    print(f"OK  {OUTPUT}")
    print(f"    investigados={evidence['total']} listas_para_promover={_promotable(research)}")
    print(f"    errores={errors['total']} ritmo={rate:.0f}/h" if rate else
          f"    errores={errors['total']} ritmo=sin medir")
    print(f"    snapshots={len(snapshots)}")


if __name__ == "__main__":
    main()
