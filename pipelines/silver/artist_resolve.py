#!/usr/bin/env python3
"""Etapa de Silver: resuelve identidad, tipo de autoria y pais del artista.

Se ejecuta despues de build_silver.py y reescribe data/silver/lots.jsonl
anadiendo 7 campos a CADA lote. Es el punto unico donde se limpia el artista,
para que Gold, la puerta de calidad y el informe partan todos del mismo dato.

Por que aqui y no en un enrichment: los enrichments son opcionales e
independientes, y quality_gates.py solo lee Silver, asi que no podria medir la
cobertura. Ademas un fichero lateral repetiria el error de
artist_canonicalized.jsonl: 10 MB que no consume nadie. Y no va dentro de
normalize_lot() porque esa funcion es un passthrough puro sin I/O al que se
llama 52.978 veces.

Campos anadidos (siempre presentes, aunque valgan null, como los otros 31):
    artist_id              id del maestro, o None
    artist_fold            clave de agrupacion deterministica
    artist_display_name    nombre para mostrar
    attribution_type       autor | escuela | circulo | taller | seguidor |
                           copia | atribuido | anonimo | no_autor | desconocido
    artist_country_birth   ISO alpha-2, o None
    artist_nationalities   lista de ISO alpha-2 (puede estar vacia)
    artist_resolution      master | fold_only | not_an_author | unresolved

REGLA DE DISENO: un artista sin entrada en el maestro devuelve
artist_country_birth None, nunca un pais inventado ni el pais de la casa de
subastas. Es el mismo principio que to_eur(), que devuelve None en vez de 1.0.
El atajo "lote de Bogota => artista colombiano" ya seria falso hoy para 46
artistas espanioles, 26 alemanes y 25 panamenios presentes en los datos.

Cuando el texto libre de Silver contradiga al maestro, GANA EL MAESTRO y la
discrepancia se cuenta y se informa. Ni primer-valor-gana (el bug que tenia
build_insights.py) ni votacion por mayoria: los datos crudos de Alejandro
Obregon dicen "Espania" 17 veces y "Colombia" 3, y la respuesta correcta no es
ninguna de las dos por separado, es country_birth=ES + nationalities=[CO, ES].

La escritura es a fichero temporal + reemplazo atomico: un fallo a media
escritura no puede dejar Silver corrupto.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict

from pipelines.shared.artist_master import (
    load_lot_author_fixes,
    normalize_country,
    resolve_artist,
)

ROOT = Path(__file__).resolve().parents[2]
SILVER_LOTS = ROOT / "data" / "silver" / "lots.jsonl"

RESOLUTION_FIELDS = (
    "artist_id",
    "artist_fold",
    "artist_display_name",
    "attribution_type",
    "artist_country_birth",
    "artist_nationalities",
    "artist_resolution",
)


def resolve_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Devuelve el lote con los 7 campos de artista anadidos.

    Idempotente: volver a pasarlo sobre una fila ya resuelta da el mismo
    resultado, porque siempre se recalcula desde artist_name.
    """
    resolved = dict(row)

    # Compatibilidad con el antiguo parche por lot_url. El mapa de produccion
    # esta vacio desde que el parser de Duran prioriza el campo Autor; no se debe
    # ampliar para datos nuevos.
    name = row.get("artist_name")
    lot_url = row.get("lot_url")
    if lot_url:
        name = load_lot_author_fixes().get(lot_url, name)

    artist = resolve_artist(name)

    # Lefebre mezcla ocasionalmente nombre y titulo en lineas consecutivas. No
    # se acepta la primera linea por su forma: la casa es generalista y eso
    # fabricaria autores a partir de joyas, monedas o vinilos. Solo si el bloque
    # completo queda sin maestro se prueban sus prefijos, de mayor a menor, y se
    # acepta exclusivamente uno que YA sea un alias exacto del maestro. Asi
    # ``SANTIAGO CARDENAS\nBlack Tie`` recupera al pintor sin convertir el titulo
    # en alias; los prefijos desconocidos permanecen sin pais.
    if (
        row.get("house_slug") == "lefebre_subastas"
        and artist["artist_resolution"] == "fold_only"
        and isinstance(name, str)
        and "\n" in name
    ):
        lines = [line.strip() for line in name.splitlines() if line.strip()]
        for end in range(len(lines) - 1, 0, -1):
            candidate = " ".join(lines[:end])
            candidate_artist = resolve_artist(candidate)
            if candidate_artist["artist_resolution"] == "master":
                name = candidate
                artist = candidate_artist
                break

    resolved.update(artist)

    # El display name cae al nombre crudo cuando el artista no esta en el
    # maestro, para que el informe siga mostrando algo legible.
    if resolved["artist_display_name"] is None:
        raw = (name or "").strip()
        resolved["artist_display_name"] = raw or None

    return resolved


def main() -> None:
    if not SILVER_LOTS.exists():
        raise FileNotFoundError(
            f"Silver no encontrado: {SILVER_LOTS}. "
            "Ejecuta primero python -m pipelines.silver.build_silver"
        )

    tmp_path = SILVER_LOTS.with_suffix(".jsonl.tmp")
    stats = Counter()
    countries_seen = Counter()
    unmapped_country_values = Counter()
    conflicts = 0

    with open(SILVER_LOTS, encoding="utf-8") as source, open(
        tmp_path, "w", encoding="utf-8"
    ) as target:
        for line in source:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            resolved = resolve_row(row)

            stats["lots"] += 1
            stats[resolved["artist_resolution"]] += 1
            stats[f"attr_{resolved['attribution_type']}"] += 1

            if resolved["artist_country_birth"]:
                stats["with_country"] += 1
                countries_seen[resolved["artist_country_birth"]] += 1

            # El texto libre de la casa se usa SOLO para diagnostico: alimenta
            # unmapped_country_values (que evita que _countries.yaml se pudra)
            # y cuenta discrepancias con el maestro. Nunca escribe el pais.
            raw_country = row.get("artist_country")
            if raw_country:
                mapped = normalize_country(raw_country)
                if mapped is None:
                    unmapped_country_values[str(raw_country).strip()] += 1
                elif (
                    resolved["artist_country_birth"]
                    and mapped != resolved["artist_country_birth"]
                    and mapped not in resolved["artist_nationalities"]
                ):
                    conflicts += 1

            target.write(json.dumps(resolved, ensure_ascii=False) + "\n")

    # Reemplazo atomico: si algo peta arriba, lots.jsonl sigue intacto.
    os.replace(tmp_path, SILVER_LOTS)

    total = stats["lots"] or 1
    authors = stats["attr_autor"] or 0
    print("--- Silver: resolucion de artistas ---")
    print(f"  lotes: {stats['lots']:,}")
    print(f"  autores (attribution_type=autor): {authors:,} ({authors / total:.1%})")
    print(f"  resueltos con maestro: {stats['master']:,}")
    print(f"  solo fold (sin maestro): {stats['fold_only']:,}")
    print(f"  no son autor: {stats['not_an_author']:,}")
    print(f"  sin nombre: {stats['unresolved']:,}")
    print(f"  con pais: {stats['with_country']:,} ({stats['with_country'] / total:.1%})")

    if unmapped_country_values:
        # Este es el bucle de realimentacion que mantiene viva la tabla de
        # paises: sin el, _countries.yaml envejece en silencio.
        print(f"  paises sin mapear en _countries.yaml: {len(unmapped_country_values)}")
        for value, count in unmapped_country_values.most_common(10):
            print(f"    {value!r}: {count:,} lotes")
    if conflicts:
        print(f"  discrepancias casa vs maestro (gana el maestro): {conflicts:,}")
    if not stats["master"]:
        print(
            "  AVISO: el maestro esta vacio, asi que ningun lote tiene pais. "
            "Ver pipelines/config/artists/README.md para poblarlo."
        )

    print(f"[silver] wrote: {SILVER_LOTS}")


if __name__ == "__main__":
    main()
