#!/usr/bin/env python3
"""Audita un lote de fichas ANTES de pegarlo en el maestro.

Existe por lo que paso al pegar el shard A. La comprobacion previa dijo "0
colisiones" y habia dos, porque comparaba alias contra alias mientras el loader
indexa TAMBIEN el display_name. Una de ellas, Antonio Reyna Manescau, habria
entrado como italiano: Wikidata da el pais por el lugar de FALLECIMIENTO (Roma)
y el pintor nacio en Coin, Malaga. La otra, Steinlen, era la misma persona con
el nombre invertido en dos shards distintos.

Ninguno de los dos casos lo detecta el promotor, porque el promotor mira su
propio lote y no el maestro ya cargado. Este script cierra ese hueco.

No decide nada: SENALA. Lo que encuentra se mira a mano, que es justo donde
aparecieron los dos errores de hoy.

Uso desde la raiz del repo::

    python scripts/artist_master_audit.py --shard b
    python scripts/artist_master_audit.py --file candidatos_b.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.shared.artist_key import artist_fold
from pipelines.shared.artist_master import load_master


def _folds_of(entry: Mapping[str, Any]) -> list[str]:
    """Todos los folds con los que una ficha reclama identidad.

    Incluye el display_name ademas de los aliases: es exactamente lo que hace
    _alias_index() en el loader, y mirar solo los aliases fue el fallo que dejo
    pasar las dos colisiones del shard A.
    """
    out = []
    for name in [entry.get("display_name"), *(entry.get("aliases") or [])]:
        if name:
            fold = artist_fold(str(name))
            if fold:
                out.append(fold)
    return out


def find_clashes(
    entries: Iterable[Mapping[str, Any]],
    master: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Fichas que reclaman un fold que ya pertenece a otra.

    Comprueba contra el maestro Y dentro del propio lote: dos fichas nuevas
    pueden chocar entre si sin que el maestro sepa nada todavia.
    """
    master = load_master() if master is None else master
    owner: dict[str, str] = {}
    for aid, entry in master.items():
        for fold in _folds_of(entry):
            owner.setdefault(fold, aid)

    clashes = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        aid = entry.get("artist_id") or "?"
        for fold in _folds_of(entry):
            prev = owner.get(fold)
            if prev is not None and prev != aid:
                key = (aid, fold)
                if key not in seen:
                    seen.add(key)
                    clashes.append(
                        {
                            "artist_id": aid,
                            "display_name": entry.get("display_name"),
                            "fold": fold,
                            "owner": prev,
                        }
                    )
            else:
                # Se registra siempre que el fold quede libre, para que la
                # SIGUIENTE ficha del lote choque contra esta. Sin esto, dos
                # fichas nuevas con el mismo nombre pasaban las dos.
                owner[fold] = aid
    return clashes


def find_country_conflicts(
    entries: Iterable[Mapping[str, Any]],
    master: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Fichas que proponen un pais distinto del ya curado a mano.

    El caso Reyna Manescau. El maestro gana siempre (lo dice el CLAUDE.md), pero
    la discrepancia hay que verla: a veces la curada es la que esta mal.
    """
    master = load_master() if master is None else master
    by_fold: dict[str, Mapping[str, Any]] = {}
    for entry in master.values():
        for fold in _folds_of(entry):
            by_fold.setdefault(fold, entry)

    out = []
    for entry in entries:
        proposed = entry.get("country_birth")
        if not proposed:
            continue
        for fold in _folds_of(entry):
            curated = (by_fold.get(fold) or {}).get("country_birth")
            if curated and curated != proposed:
                out.append(
                    {
                        "artist_id": entry.get("artist_id"),
                        "display_name": entry.get("display_name"),
                        "curated": curated,
                        "proposed": proposed,
                    }
                )
                break
    return out


def flag_suspicious(entries: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Fichas que piden una mirada humana, con el motivo.

    Nada de esto es un error por si mismo: un nombre de una palabra puede ser
    ruido (el caso _OBJECT_NAMES) o un pseudonimo real (Castelao, Alvar, Serny).
    Por eso se senala en vez de descartarse.
    """
    out = []
    for entry in entries:
        name = str(entry.get("display_name") or "")
        if name and len(name.split()) == 1:
            out.append(
                {
                    "artist_id": entry.get("artist_id"),
                    "display_name": name,
                    "reason": "nombre_de_una_palabra",
                }
            )
        if not entry.get("country_birth"):
            out.append(
                {
                    "artist_id": entry.get("artist_id"),
                    "display_name": name,
                    "reason": "sin_pais",
                }
            )
    return out


def _load_entries(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get("artists") or [])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audita un lote de fichas antes de pegarlo en el maestro."
    )
    parser.add_argument("--file", type=Path, help="YAML de candidatos a auditar.")
    parser.add_argument("--shard", help="Genera el lote de esta letra y lo audita.")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    if args.file:
        entries = _load_entries(args.file)
        origen = str(args.file)
    elif args.shard:
        from scripts.artist_master_promote import build_entries, _iter_jsonl, DEFAULT_INPUT

        todas, _ = build_entries(_iter_jsonl(DEFAULT_INPUT))
        pref = args.shard.lower()
        entries = [e for e in todas if e["artist_id"].lower().startswith(pref)]
        origen = f"shard {pref}"
    else:
        parser.error("hace falta --file o --shard")

    clashes = find_clashes(entries)
    conflicts = find_country_conflicts(entries)
    suspicious = flag_suspicious(entries)

    print(f"--- Auditoria de {origen}: {len(entries)} fichas ---")
    print(f"  colisiones de alias    : {len(clashes)}")
    for c in clashes:
        print(f"      {c['display_name']!r} choca con '{c['owner']}' (fold: {c['fold']})")
    print(f"  conflictos de pais     : {len(conflicts)}")
    for c in conflicts:
        print(f"      {c['display_name']}: curado {c['curated']} vs propuesto {c['proposed']}")

    una = [s for s in suspicious if s["reason"] == "nombre_de_una_palabra"]
    sinp = [s for s in suspicious if s["reason"] == "sin_pais"]
    print(f"  nombres de una palabra : {len(una)}   (revisar: ruido o pseudonimo)")
    for s in una[:12]:
        print(f"      {s['display_name']}")
    print(f"  sin pais               : {len(sinp)}   (entran como confidence low)")

    bloqueantes = len(clashes) + len(conflicts)
    print()
    if bloqueantes:
        print(f"REVISAR A MANO antes de pegar: {bloqueantes} casos.")
    else:
        print("Sin colisiones ni conflictos: el lote se puede pegar.")
    return 1 if bloqueantes else 0


if __name__ == "__main__":
    raise SystemExit(main())
