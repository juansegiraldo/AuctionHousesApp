"""Valida Jev (TypeSafe) como clasificador de attribution_type ANTES de integrarlo.

Paso 1 del plan: no toca el pipeline. Compara Jev con las reglas de
pipelines/shared/artist_key.attribution_type() sobre una muestra de Silver:

  - ~300 folds que las reglas clasifican como NO-"autor": ahi las reglas son
    precisas, asi que sirven de ground truth -> matriz de confusion.
  - ~300 folds "autor" que NO estan en el maestro curado (fold_only): ahi esta
    el agujero del default ("Collar de perlas" sale "autor"). Se listan los que
    Jev reclasifica para revisarlos a ojo; aqui no hay ground truth.

Las respuestas se guardan en data/gold/jev_attribution_eval.jsonl (gitignored)
y se reutilizan al relanzar: solo se paga por los folds que faltan.

    python -m scripts.jev_attribution_eval
    python -m scripts.jev_attribution_eval --per-class 50 --autor 300 --workers 8
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import orjson

from pipelines.shared.artist_key import ATTRIBUTION_TYPES
from pipelines.shared.attribution_jev import ask, load_api_key, lot_state
from pipelines.silver.artist_resolve import resolve_row

ROOT = Path(__file__).resolve().parents[1]
SILVER = ROOT / "data" / "silver" / "lots.jsonl"
OUT = ROOT / "data" / "gold" / "jev_attribution_eval.jsonl"

# $ por millon de tokens de entrada (la salida no se cobra).
PRICE_PER_M_INPUT = 0.04


def build_folds() -> dict[str, dict]:
    """fold -> {attribution, resolution, n_lots, state} con el lote mas representativo."""
    names: dict[str, Counter] = defaultdict(Counter)
    info: dict[str, dict] = {}
    with SILVER.open("rb") as fh:
        for line in fh:
            # Las reglas se recalculan aqui: Silver ya lleva las etiquetas de
            # Jev aplicadas, y medir a Jev contra si mismo no valida nada.
            lot = resolve_row(orjson.loads(line))
            fold = lot.get("artist_fold")
            if not fold:
                continue
            names[fold][lot.get("artist_name") or ""] += 1
            entry = info.setdefault(fold, {
                "attribution": lot["attribution_type"],
                "resolution": lot["artist_resolution"],
                "n_lots": 0,
                "lot": lot,
            })
            entry["n_lots"] += 1
            # Preferimos un lote con titulo/tecnica: es el contexto que ve Jev.
            if not (entry["lot"].get("lot_title") or entry["lot"].get("medium")):
                entry["lot"] = lot
    for fold, entry in info.items():
        lot = entry.pop("lot")
        state = lot_state({**lot, "artist_name": names[fold].most_common(1)[0][0]})
        entry["state"] = state
    return info


def sample(folds: dict[str, dict], per_class: int, n_autor: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    by_class: dict[str, list[str]] = defaultdict(list)
    for fold, entry in sorted(folds.items()):
        if entry["attribution"] != "autor":
            by_class[entry["attribution"]].append(fold)
    picked = []
    # Tope por clase: sin el, 'no_autor' (1.327 folds) se come la muestra y
    # 'copia' (3) o 'taller' (10) ni aparecen en la matriz.
    for fold_list in by_class.values():
        picked += rng.sample(fold_list, min(per_class, len(fold_list)))
    autor = sorted(f for f, e in folds.items()
                   if e["attribution"] == "autor" and e["resolution"] == "fold_only")
    picked += rng.sample(autor, min(n_autor, len(autor)))
    return picked


def classify(client, fold: str, state: dict) -> dict:
    from typesafe_sdk import TypeSafeError

    t0 = time.perf_counter()
    try:
        r = ask(client, state)
    except TypeSafeError as exc:
        return {"fold": fold, "error": type(exc).__name__}
    a = r.answers["attribution"]
    return {
        "fold": fold,
        "label": a.choice,
        "confidence": a.confidence,
        "probabilities": a.probabilities,
        "model": r.model,
        "input_tokens": r.usage.input_tokens,
        "latency_s": round(time.perf_counter() - t0, 3),
    }


def report(folds: dict, results: dict, sample_folds: list[str], wall_s: float) -> None:
    rows = [results[f] for f in sample_folds if f in results and "label" in results[f]]
    errors = [f for f in sample_folds if "error" in results.get(f, {"error": 1})]
    gt = [r for r in rows if folds[r["fold"]]["attribution"] != "autor"]
    au = [r for r in rows if folds[r["fold"]]["attribution"] == "autor"]

    print(f"\n== Muestra: {len(gt)} no-autor + {len(au)} autor fold_only "
          f"({len(errors)} errores)")

    # Matriz de confusion: filas = reglas, columnas = Jev.
    print("\n== No-autor: reglas (filas) vs Jev (columnas)")
    cols = [t for t in ATTRIBUTION_TYPES if any(r["label"] == t for r in gt)]
    print(f"{'reglas':>12} " + " ".join(f"{c[:9]:>9}" for c in cols) + "   n   acc")
    for t in ATTRIBUTION_TYPES:
        sub = [r for r in gt if folds[r["fold"]]["attribution"] == t]
        if not sub:
            continue
        c = Counter(r["label"] for r in sub)
        hit = c[t] / len(sub)
        print(f"{t:>12} " + " ".join(f"{c[x]:>9}" for x in cols) + f" {len(sub):>4} {hit:5.0%}")
    for thr in (0.0, 0.8, 0.95):
        s = [r for r in gt if r["confidence"] >= thr]
        ok = sum(r["label"] == folds[r["fold"]]["attribution"] for r in s)
        # 'autor' es el error caro: un no-autor que entraria en el ranking.
        leak = sum(r["label"] == "autor" for r in s)
        print(f"  conf>={thr:.2f}: cobertura {len(s)}/{len(gt)}, acierto "
              f"{ok / max(len(s), 1):.1%}, se cuelan como 'autor' {leak}")

    print("\n== Autor fold_only: etiquetas de Jev")
    c = Counter(r["label"] for r in au)
    print("  " + ", ".join(f"{k} {v}" for k, v in c.most_common()))
    for thr in (0.8, 0.95):
        n = sum(r["label"] != "autor" and r["confidence"] >= thr for r in au)
        print(f"  reclasificados con conf>={thr:.2f}: {n}")

    print("\n== Autor fold_only que Jev reclasifica (para revisar a ojo)")
    print(f"{'conf':>5} {'jev':>11} {'lotes':>5}  artist_name | titulo")
    for r in sorted((r for r in au if r["label"] != "autor"),
                    key=lambda r: -r["confidence"]):
        st = folds[r["fold"]]["state"]
        title = (st.get("titulo") or "")[:60].replace("\n", " ")
        print(f"{r['confidence']:5.2f} {r['label']:>11} {folds[r['fold']]['n_lots']:>5}  "
              f"{st['artist_name'][:45]} | {title}")

    tokens = sum(r["input_tokens"] for r in rows)
    lat = sorted(r["latency_s"] for r in rows)
    print(f"\n== Coste y tiempo")
    print(f"  modelo: {sorted({r['model'] for r in rows})}")
    print(f"  tokens de entrada: {tokens:,} ({tokens / max(len(rows), 1):.0f}/fold)")
    print(f"  coste: ${tokens * PRICE_PER_M_INPUT / 1e6:.4f} "
          f"(a ${PRICE_PER_M_INPUT}/M); los 8.845 fold_only costarian "
          f"~${tokens / max(len(rows), 1) * 8845 * PRICE_PER_M_INPUT / 1e6:.4f}")
    if lat:
        print(f"  latencia por llamada: p50 {lat[len(lat) // 2]:.2f}s, "
              f"p95 {lat[int(len(lat) * 0.95)]:.2f}s; reloj de esta ejecucion {wall_s:.1f}s")


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--per-class", type=int, default=50)
    ap.add_argument("--autor", type=int, default=300)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    folds = build_folds()
    sample_folds = sample(folds, args.per_class, args.autor, args.seed)

    results: dict[str, dict] = {}
    if OUT.exists():
        for line in OUT.read_bytes().splitlines():
            r = orjson.loads(line)
            if "label" in r:
                results[r["fold"]] = r
    todo = [f for f in sample_folds if f not in results]
    print(f"{len(sample_folds)} folds en la muestra, {len(todo)} por consultar")

    t0 = time.perf_counter()
    if todo:
        key = load_api_key()
        if not key:
            print("Falta TYPESAFE_API_KEY (entorno, .env o ../JEV_v0/.env)")
            return 1
        from typesafe_sdk import TypeSafeClient

        OUT.parent.mkdir(parents=True, exist_ok=True)
        with TypeSafeClient(api_key=key) as client, OUT.open("ab") as fh, \
                ThreadPoolExecutor(args.workers) as pool:
            for r in pool.map(lambda f: classify(client, f, folds[f]["state"]), todo):
                results[r["fold"]] = r
                if "label" in r:
                    fh.write(orjson.dumps(r, option=orjson.OPT_APPEND_NEWLINE))
    report(folds, results, sample_folds, time.perf_counter() - t0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
