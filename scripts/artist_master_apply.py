#!/usr/bin/env python3
"""Aplica complementos verificados sobre los shards del maestro.

Es la UNICA pieza del ciclo que escribe en pipelines/config/artists, asi que su
contrato es deliberadamente estrecho: **solo rellena huecos**. Si el campo ya
tiene valor, no lo toca — ni para "corregirlo". Corregir un dato curado es una
decision humana y se hace editando el YAML a mano.

Existe porque hay complementos que no se pueden aplicar uno a uno: marcar
``death_status: living`` en 333 fichas con evidencia de Wikidata es mecanico y
verificable, pero inviable a mano. Lo que sigue siendo manual es *decidir* que
esos complementos son correctos: este script se ejecuta sobre la salida ya
revisada de ``artist_master_promote.py --completions``.

Uso desde la raiz del repo::

    python scripts/artist_master_promote.py --completions      # revisar primero
    python scripts/artist_master_apply.py --field death_status --dry-run
    python scripts/artist_master_apply.py --field death_status
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SHARD_DIR = ROOT / "pipelines" / "config" / "artists"
NON_SHARDS = frozenset({"_countries.yaml", "_lot_author_fixes.yaml"})

# Campos que este script puede escribir. Lista cerrada a proposito: no debe
# poder tocar aliases ni display_name, que son afirmaciones de identidad.
WRITABLE_FIELDS = frozenset(
    {"country_birth", "birth_year", "death_year", "death_status", "nationalities"}
)


def _load_promoter():
    spec = importlib.util.spec_from_file_location(
        "artist_master_promote", ROOT / "scripts" / "artist_master_promote.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _quote_iso(value: Any) -> Any:
    """Marca los codigos ISO para que el volcado los deje entrecomillados.

    YAML 1.1 lee NO (Noruega), ON, OFF e YES sin comillas como booleanos: sin
    esto, un artista noruego acabaria con country_birth: False y Noruega
    desapareceria de la tabla sin que nadie lo note.
    """
    return str(value)


def apply_completions(
    completions: Iterable[Mapping[str, Any]],
    *,
    shard_dir: Path = SHARD_DIR,
    fields: frozenset[str] | None = None,
    dry_run: bool = False,
) -> int:
    """Rellena huecos en los shards. Devuelve cuantas fichas cambiaron.

    Nunca sobrescribe: si el campo ya tiene valor, la ficha se deja como esta.
    """
    allowed = (fields or WRITABLE_FIELDS) & WRITABLE_FIELDS
    wanted: dict[str, dict[str, Any]] = {}
    for item in completions:
        artist_id = item.get("artist_id")
        item_fields = item.get("fields") or {}
        if not artist_id:
            continue
        usable = {k: v for k, v in item_fields.items() if k in allowed}
        if usable:
            wanted[str(artist_id)] = usable

    if not wanted:
        return 0

    changed = 0
    for shard in sorted(shard_dir.glob("*.yaml")):
        if shard.name in NON_SHARDS:
            continue
        text = shard.read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        entries = data.get("artists")
        if not isinstance(entries, list):
            continue

        touched = False
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            pending = wanted.get(str(entry.get("artist_id") or ""))
            if not pending:
                continue
            for field, value in pending.items():
                # El guardado es por "esta vacio", no por truthiness: un 0 no
                # aparece aqui, pero la regla debe leerse sin ambiguedad.
                if entry.get(field) is not None:
                    continue
                entry[field] = _quote_iso(value) if field == "country_birth" else value
                touched = True
                changed += 1

        if touched and not dry_run:
            tmp = shard.with_suffix(".yaml.tmp")
            with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
                yaml.safe_dump(
                    data,
                    handle,
                    allow_unicode=True,
                    sort_keys=False,
                    default_flow_style=False,
                    width=110,
                )
            tmp.replace(shard)

    return changed


def merge_new_entries(
    entries: Iterable[Mapping[str, Any]],
    *,
    shard_dir: Path = SHARD_DIR,
    dry_run: bool = False,
) -> int:
    """Anade fichas nuevas al shard de su inicial. Devuelve cuantas entraron.

    Nunca reemplaza: si el ``artist_id`` ya existe, o si alguno de sus alias ya
    pertenece a otro artista, la ficha se salta. Lo curado a mano siempre gana,
    y la regla 3 del maestro (un alias, un solo artista) se respeta aqui en vez
    de dejar que ``load_master()`` falle despues.
    """
    from pipelines.shared.artist_key import artist_fold

    existing_ids: set[str] = set()
    claimed_folds: set[str] = set()
    shards: dict[str, dict[str, Any]] = {}

    for shard in sorted(shard_dir.glob("*.yaml")):
        if shard.name in NON_SHARDS:
            continue
        data = yaml.safe_load(shard.read_text(encoding="utf-8")) or {}
        if not isinstance(data.get("artists"), list):
            data["artists"] = []
        shards[shard.name] = data
        for entry in data["artists"]:
            if not isinstance(entry, dict):
                continue
            existing_ids.add(str(entry.get("artist_id") or ""))
            for alias in [entry.get("display_name"), *(entry.get("aliases") or [])]:
                fold = artist_fold(str(alias)) if alias else None
                if fold:
                    claimed_folds.add(fold)

    added = 0
    touched: set[str] = set()
    for entry in entries:
        artist_id = str(entry.get("artist_id") or "")
        if not artist_id or artist_id in existing_ids:
            continue
        aliases = [str(a) for a in (entry.get("aliases") or []) if a]
        folds = {f for f in (artist_fold(a) for a in aliases) if f}
        if folds & claimed_folds:
            continue

        initial = artist_id[:1].lower()
        name = f"{initial}.yaml" if "a" <= initial <= "z" else "_misc.yaml"
        data = shards.setdefault(name, {"artists": []})
        if not isinstance(data.get("artists"), list):
            data["artists"] = []

        # death_year: null no aporta y ensucia el diff; se omiten los vacios.
        clean = {k: v for k, v in entry.items() if v is not None and v != []}
        data["artists"].append(clean)
        data["artists"].sort(key=lambda e: str(e.get("artist_id") or ""))
        existing_ids.add(artist_id)
        claimed_folds |= folds
        touched.add(name)
        added += 1

    if not dry_run:
        for name in sorted(touched):
            path = shard_dir / name
            tmp = path.with_suffix(".yaml.tmp")
            with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
                yaml.safe_dump(
                    shards[name],
                    handle,
                    allow_unicode=True,
                    sort_keys=False,
                    default_flow_style=False,
                    width=110,
                )
            tmp.replace(path)

    return added


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Aplica en los shards los complementos que produce "
            "artist_master_promote.py --completions. Solo rellena huecos."
        )
    )
    parser.add_argument(
        "--field",
        action="append",
        dest="fields",
        help="Campo a aplicar; repetible. Por defecto, todos los permitidos.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Cuenta lo que cambiaria sin escribir nada.",
    )
    parser.add_argument(
        "--merge-new",
        action="store_true",
        help="Anade tambien las fichas NUEVAS al shard de su inicial.",
    )
    args = parser.parse_args(argv)

    promote = _load_promoter()
    if not promote.DEFAULT_INPUT.exists():
        print(f"No existe el diario: {promote.DEFAULT_INPUT}", file=sys.stderr)
        return 2

    completions = promote.build_completions(promote._iter_jsonl(promote.DEFAULT_INPUT))
    fields = frozenset(args.fields) if args.fields else None

    counts: Counter[str] = Counter()
    for item in completions:
        for field in item["fields"]:
            if not fields or field in fields:
                counts[field] += 1

    changed = apply_completions(
        completions, fields=fields, dry_run=args.dry_run
    )

    sys.stdout.reconfigure(encoding="utf-8")

    if args.merge_new:
        entries, _ = promote.build_entries(
            promote._iter_jsonl(promote.DEFAULT_INPUT)
        )
        added = merge_new_entries(entries, dry_run=args.dry_run)
        verbo_alta = "se anadirian" if args.dry_run else "anadidas"
        print(f"--- Fichas nuevas {verbo_alta}: {added} de {len(entries)} propuestas ---")

    verbo = "se aplicarian" if args.dry_run else "aplicados"
    print(f"--- Complementos {verbo}: {changed} ---")
    for field, count in counts.most_common():
        print(f"  {field}: {count} propuestos")
    if args.dry_run:
        print("  (dry-run: no se ha escrito nada)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
