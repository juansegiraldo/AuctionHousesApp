#!/usr/bin/env python3
"""Genera candidatos para el maestro de artistas a partir de Silver.

Herramienta de apoyo, NO una etapa del pipeline: escribe a stdout (o al fichero
que se le indique) para que una persona revise y pegue en el shard que toque.
Nunca escribe dentro de pipelines/config/artists/.

Uso (desde la raiz del repo):

    python scripts/artist_master_propose.py --min-lots 10
    python scripts/artist_master_propose.py --shard a --out candidatos_a.yaml
    python scripts/artist_master_propose.py --min-lots 5 --show-inversions

Que extrae de los datos:
  - el parentesis biografico del propio nombre ("Ever Astudillo (Colombia, 1948
    - 2015)"): 552 nombres distintos lo llevan
  - artist_raw, con el mismo formato pero truncado a 60 caracteres
  - artist_country cuando la casa lo publica (solo Bogota, 2% de los lotes)
  - anios de nacimiento/muerte, que son el desempate cuando dos personas
    comparten nombre (el caso "Francisco Toledo")
  - inversiones por coma ("GARCIA OCHOA, LUIS") que colisionan con un nombre ya
    presente: 281 casos de alto valor, pero SIEMPRE como sugerencia, porque
    "Garcia Marquez, Gabriel" es un escritor en lotes de libros

Lo que sale NO tiene pais salvo que los datos lo dijeran. Rellenar country_birth
y nationalities es la parte que hace una persona (o un LLM revisado por una
persona), siguiendo la regla del README: ante la duda, null y confidence: low.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.shared.artist_key import artist_fold, attribution_type, propose_inversion
from pipelines.shared.artist_master import load_master, normalize_country

SILVER_LOTS = ROOT / "data" / "silver" / "lots.jsonl"

# "(Colombia, 1948 - 2015)" / "(Colombia, 1948)" / "(1927 - 2021)"
_PAREN_RE = re.compile(r"\(([^()]*)\)")
_YEARS_RE = re.compile(r"\b(1[5-9]\d{2}|20\d{2})\b")


def parse_biography(text: str | None) -> dict:
    """Saca pais y anios del parentesis biografico. Devuelve {} si no hay nada."""
    if not text:
        return {}
    out: dict = {}
    for chunk in _PAREN_RE.findall(text):
        years = _YEARS_RE.findall(chunk)
        if years:
            out.setdefault("birth_year", int(years[0]))
            if len(years) > 1:
                out.setdefault("death_year", int(years[1]))
        # La parte no numerica suele ser el pais (o la ciudad).
        head = re.split(r"[,;]", chunk)[0].strip()
        if head and not _YEARS_RE.search(head):
            code = normalize_country(head)
            if code:
                out.setdefault("country_birth", code)
    return out


def collect(min_lots: int) -> list[dict]:
    """Agrupa Silver por fold y devuelve candidatos ordenados por volumen."""
    if not SILVER_LOTS.exists():
        raise SystemExit(
            f"Silver no encontrado: {SILVER_LOTS}. "
            "Ejecuta antes python -m pipelines.silver.build_silver"
        )

    groups: dict[str, dict] = defaultdict(
        lambda: {
            "lots": 0,
            "names": Counter(),
            "houses": set(),
            "countries": Counter(),
            "birth": Counter(),
            "death": Counter(),
        }
    )

    with open(SILVER_LOTS, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            name = (row.get("artist_name") or "").strip()
            if not name or attribution_type(name) != "autor":
                continue
            fold = artist_fold(name)
            if not fold:
                continue

            g = groups[fold]
            g["lots"] += 1
            g["names"][name] += 1
            if row.get("house_slug"):
                g["houses"].add(row["house_slug"])

            # El pais que publica la casa, normalizado a ISO.
            code = normalize_country(row.get("artist_country"))
            if code:
                g["countries"][code] += 1
            # Y el que venga dentro del propio nombre o de artist_raw.
            for source in (name, row.get("artist_raw")):
                bio = parse_biography(source)
                if bio.get("country_birth"):
                    g["countries"][bio["country_birth"]] += 1
                if bio.get("birth_year"):
                    g["birth"][bio["birth_year"]] += 1
                if bio.get("death_year"):
                    g["death"][bio["death_year"]] += 1

            if row.get("artist_birth_year"):
                g["birth"][row["artist_birth_year"]] += 1
            if row.get("artist_death_year"):
                g["death"][row["artist_death_year"]] += 1

    known_folds = _known_folds()
    out = []
    for fold, g in groups.items():
        if g["lots"] < min_lots or fold in known_folds:
            continue
        display = g["names"].most_common(1)[0][0]
        out.append(
            {
                "fold": fold,
                "artist_id": fold.replace(" ", "_"),
                "display_name": display,
                "lots": g["lots"],
                "houses": sorted(g["houses"]),
                "aliases": [n for n, _ in g["names"].most_common()],
                "countries": g["countries"],
                "birth": g["birth"],
                "death": g["death"],
            }
        )
    out.sort(key=lambda c: -c["lots"])
    return out


def _known_folds() -> set[str]:
    """Folds ya cubiertos por el maestro: no hace falta volver a proponerlos."""
    known = set()
    for entry in load_master().values():
        for alias in list(entry.get("aliases") or []) + [entry.get("display_name")]:
            fold = artist_fold(str(alias)) if alias else None
            if fold:
                known.add(fold)
    return known


def _single(counter: Counter):
    """Valor unico si no hay discrepancia; None si esta vacio o en conflicto."""
    if not counter:
        return None
    if len(counter) == 1:
        return next(iter(counter))
    return None


def to_yaml(candidates: list[dict], show_inversions: bool) -> str:
    lines = [
        "# Candidatos generados por scripts/artist_master_propose.py",
        "# REVISAR ANTES DE PEGAR. Reglas en pipelines/config/artists/README.md:",
        "#   - ante la duda, country_birth: null y confidence: low. Nunca inventar.",
        "#   - los alias son una decision humana: comprobar que no mezclan a dos",
        "#     personas distintas (ver los avisos CONFLICTO de abajo).",
        "",
        "artists:",
    ]
    for c in candidates:
        country = _single(c["countries"])
        birth = _single(c["birth"])
        death = _single(c["death"])
        confidence = "medium" if country else "low"

        lines.append(f"  - artist_id: {c['artist_id']}")
        lines.append(f"    display_name: {json.dumps(c['display_name'], ensure_ascii=False)}")
        # Los codigos van SIEMPRE entrecomillados: YAML 1.1 lee NO (Noruega),
        # ON, OFF e YES sin comillas como booleanos, y un artista noruego
        # acabaria con country_birth: False sin que nadie lo note.
        lines.append(
            f'    country_birth: "{country}"' if country
            else "    country_birth: null   # RELLENAR o dejar null"
        )
        lines.append(
            f'    nationalities: ["{country}"]' if country else "    nationalities: []"
        )
        if birth:
            lines.append(f"    birth_year: {birth}")
        if death:
            lines.append(f"    death_year: {death}")
        lines.append("    attribution_type: autor")
        lines.append("    source: parsed")
        lines.append(f"    confidence: {confidence}")
        lines.append("    aliases:")
        for alias in c["aliases"]:
            lines.append(f"      - {json.dumps(alias, ensure_ascii=False)}")

        notes = [f"{c['lots']} lotes", "casas: " + ", ".join(c["houses"])]
        if len(c["countries"]) > 1:
            notes.append(
                "CONFLICTO paises: "
                + ", ".join(f"{k}x{v}" for k, v in c["countries"].most_common())
            )
        if len(c["birth"]) > 1:
            notes.append(
                "CONFLICTO nacimiento: "
                + ", ".join(f"{k}x{v}" for k, v in c["birth"].most_common())
                + " (puede que sean DOS personas distintas)"
            )
        if show_inversions:
            for alias in c["aliases"]:
                inverted = propose_inversion(alias)
                if inverted and inverted != c["fold"]:
                    notes.append(f"posible inversion: {alias!r} -> {inverted!r}")
        lines.append(f"    notes: {json.dumps(' | '.join(notes), ensure_ascii=False)}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Propone entradas del maestro de artistas a partir de Silver."
    )
    parser.add_argument(
        "--min-lots",
        type=int,
        default=10,
        help="Solo artistas con al menos N lotes (por defecto 10). "
        "Referencia: >=10 son ~765 artistas, >=5 son ~1.760.",
    )
    parser.add_argument(
        "--shard",
        help="Solo los artistas cuyo artist_id empieza por esta letra.",
    )
    parser.add_argument("--limit", type=int, help="Corta a los N primeros por volumen.")
    parser.add_argument("--out", type=Path, help="Fichero de salida (por defecto stdout).")
    parser.add_argument(
        "--show-inversions",
        action="store_true",
        help="Anota inversiones por coma como sugerencia para revisar.",
    )
    args = parser.parse_args()

    candidates = collect(args.min_lots)
    if args.shard:
        prefix = args.shard.lower()
        candidates = [c for c in candidates if c["artist_id"].startswith(prefix)]
    if args.limit:
        candidates = candidates[: args.limit]

    text = to_yaml(candidates, args.show_inversions)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"{len(candidates)} candidatos escritos en {args.out}")
    else:
        # El repo tiene un problema conocido imprimiendo UTF-8 en la consola de
        # Windows: se reconfigura aqui, no se toca el dato.
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
        print(f"# {len(candidates)} candidatos", file=sys.stderr)


if __name__ == "__main__":
    main()
