"""Segunda opinion de Jev (TypeSafe) sobre el default "autor" de attribution_type().

Las reglas de artist_key.attribution_type() son precisas cuando devuelven
escuela/circulo/anonimo/no_autor, pero terminan en `return "autor"`: un
"Collar de perlas" que no esta en _OBJECT_NAMES entra en el ranking como
pintor. Hasta ahora eso se tapaba ampliando stop-lists a mano.

Jev SOLO se consulta para lotes que las reglas dan como "autor" y que NO estan
en el maestro curado (artist_resolution == "fold_only"). Solo puede QUITAR un
nombre del ranking, nunca anadirlo, y nunca escribe identidad ni pais.

La respuesta se guarda en pipelines/config/attribution_jev.jsonl, versionada en
git e indexada por artist_fold. Silver se construye leyendo SOLO esa cache, asi
que es reproducible y funciona offline: la red solo sirve para rellenar folds
nuevos, y sin clave o sin red el pipeline sigue con reglas + cache.

Validado el 2026-10-12 (scripts/jev_attribution_eval.py, 603 folds): con
confianza >= 0,90 acierta el 98,9 % de los no-autor que ya clasifican las
reglas y ninguno se cuela como "autor".
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

import orjson

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "pipelines" / "config" / "attribution_jev.jsonl"
JEV_ENV = ROOT.parent / "JEV_v0" / ".env"

# Por debajo, la etiqueta de Jev NO se aplica: el lote sigue "autor" y se cuenta
# en quality_flags como attribution_low_conf. 0,95 era mas conservador; entre
# 0,90 y 0,95 los 10 casos del eval eran todos correctos.
THRESHOLD = 0.90
BATCH_SIZE = 200
WORKERS = 8

INSTRUCTIONS = (
    "This is the 'artist' field of an auction lot, plus some lot context. "
    "What kind of authorship does the artist field declare?"
)
# En ingles con ejemplos reales del dataset: lo que separa dos opciones
# parecidas es el ejemplo. 'desconocido' es la salida de "no lo se".
CRITERIA = {
    "autor": "A specific, identifiable individual artist or maker (a person's name, possibly with biography), e.g. 'Antonio Burgos Fraile', 'BOTERO, FERNANDO (1932 - 2023)'.",
    "escuela": "A school or regional/period style, not a person, e.g. 'Escuela española S. XIX', 'Escuela Quiteña'.",
    "circulo": "Circle of an artist: 'Círculo de ...', 'Circle of ...'.",
    "taller": "Workshop/studio of an artist: 'Taller de ...', 'Workshop of ...'.",
    "seguidor": "Follower or manner of an artist: 'Seguidor de ...', 'Manera de ...', 'Estilo de ...'.",
    "copia": "A copy after an artist: 'Copia de ...', 'Después de ...', 'After ...'.",
    "atribuido": "Attributed to an artist, not certain: 'Atribuido a ...', '(atrib.)'.",
    "anonimo": "Explicitly anonymous or unsigned: 'Anónimo', 'Sin firma', 'Anonymous'.",
    "no_autor": "Not a person at all: an object or object type ('Collar de perlas', 'Florero', 'Cartel'), a work title, a book field, a lot description, a group of items, a place or a brand.",
    "desconocido": "Cannot tell from the information given.",
}


def load_api_key() -> Optional[str]:
    """TYPESAFE_API_KEY del entorno, de un .env local o de ../JEV_v0/.env.

    En ../JEV_v0/.env la variable se llama 'type_safe ' (con espacio), asi que
    se aceptan los dos nombres. Nunca se imprime.
    """
    if os.environ.get("TYPESAFE_API_KEY"):
        return os.environ["TYPESAFE_API_KEY"]
    for path in (ROOT / ".env", JEV_ENV):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() in ("TYPESAFE_API_KEY", "type_safe"):
                return value.strip().strip("'\"") or None
    return None


def lot_state(row: Dict[str, Any]) -> Dict[str, Any]:
    """El state que ve Jev: el nombre y el contexto del lote."""
    state = {"artist_name": row.get("artist_name") or ""}
    # En Duran el titulo solo vive en description ('"Paisaje". Oleo sobre...').
    title = row.get("lot_title") or (row.get("description") or "")[:200]
    if title:
        state["titulo"] = title
    if row.get("medium"):
        state["tecnica"] = row["medium"]
    state["casa"] = row.get("auction_house_name") or row.get("house_slug")
    return state


def ask(client, state: Dict[str, Any]):
    """Una llamada a Jev. Devuelve la SystemOneResponse completa."""
    from typesafe_sdk import Choice

    return client.system_one(state=state, questions={
        "attribution": Choice(instructions=INSTRUCTIONS, criteria=CRITERIA),
    })


def load_cache(path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    path = path or CACHE
    if not path.exists():
        return {}
    return {
        entry["fold"]: entry
        for entry in map(orjson.loads, path.read_bytes().splitlines())
    }


def _write_cache(cache: Dict[str, Dict[str, Any]]) -> None:
    # Ordenado por fold: un re-run solo anade lineas y el diff de git se lee.
    tmp = CACHE.with_suffix(".jsonl.tmp")
    with tmp.open("wb") as fh:
        for fold in sorted(cache):
            fh.write(orjson.dumps(cache[fold], option=orjson.OPT_APPEND_NEWLINE))
    os.replace(tmp, CACHE)


def fetch_missing(states: Dict[str, Dict[str, Any]], cache: Dict[str, Dict[str, Any]],
                  client=None) -> int:
    """Consulta a Jev los folds que faltan en la cache y la reescribe. Nunca lanza.

    Sin clave, sin SDK o sin red, devuelve 0 y el pipeline sigue con lo que
    haya en cache: un fold sin entrada se queda como lo dejaron las reglas.
    """
    todo = sorted(f for f in states if f not in cache)
    if not todo:
        return 0
    try:
        from typesafe_sdk import (TypeSafeAPIConnectionError, TypeSafeAuthenticationError,
                                  TypeSafeClient, TypeSafeError)
    except ImportError:
        print(f"  [jev] typesafe-sdk no instalada: {len(todo):,} folds sin consultar")
        return 0
    owned = client is None
    if owned:
        key = load_api_key()
        if not key:
            print(f"  [jev] sin TYPESAFE_API_KEY: {len(todo):,} folds sin consultar")
            return 0
        client = TypeSafeClient(api_key=key, timeout=30.0)

    today = date.today().isoformat()
    fatal: list[str] = []

    def one(fold):
        if fatal:
            return None
        try:
            r = ask(client, states[fold])
        except (TypeSafeAPIConnectionError, TypeSafeAuthenticationError) as exc:
            # Sin red o con la clave mal, fallarian los 8.000: se corta aqui.
            fatal.append(type(exc).__name__)
            return None
        except TypeSafeError:
            return None
        a = r.answers["attribution"]
        return {"fold": fold, "label": a.choice, "confidence": round(a.confidence, 4),
                "model": r.model, "date": today}

    added = 0
    try:
        with ThreadPoolExecutor(WORKERS) as pool:
            # Por lotes, guardando la cache tras cada uno: si algo corta la
            # ejecucion a la mitad, lo ya pagado no se pierde.
            for i in range(0, len(todo), BATCH_SIZE):
                for entry in pool.map(one, todo[i:i + BATCH_SIZE]):
                    if entry:
                        cache[entry["fold"]] = entry
                        added += 1
                _write_cache(cache)
                if fatal:
                    break
    finally:
        if owned:
            client.close()
    if fatal:
        print(f"  [jev] cortado por {fatal[0]}: sigue con reglas + cache")
    print(f"  [jev] {added:,} folds nuevos en cache ({len(todo) - added:,} sin respuesta)")
    return added


def apply(resolved: Dict[str, Any], cache: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Aplica la etiqueta de Jev a un lote ya resuelto por las reglas.

    Solo toca 'autor' fuera del maestro, y solo con confianza >= THRESHOLD.
    artist_id y pais ya son None en un fold_only: Jev no los rellena nunca.
    """
    if resolved.get("artist_resolution") != "fold_only":
        return resolved
    entry = cache.get(resolved.get("artist_fold"))
    if not entry or entry["label"] == "autor" or entry["confidence"] < THRESHOLD:
        return resolved
    return {**resolved, "attribution_type": entry["label"],
            "artist_resolution": "not_an_author"}


def is_low_conf(resolved: Dict[str, Any], cache: Dict[str, Dict[str, Any]]) -> bool:
    """Jev duda de que sea un autor, pero no lo bastante para cambiarlo."""
    if resolved.get("artist_resolution") != "fold_only":
        return False
    entry = cache.get(resolved.get("artist_fold"))
    return bool(entry) and entry["label"] != "autor" and entry["confidence"] < THRESHOLD
