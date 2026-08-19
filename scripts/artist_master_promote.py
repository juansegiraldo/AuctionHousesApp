#!/usr/bin/env python3
"""Convierte la evidencia de Wikidata en altas revisables del maestro.

Es la ultima pieza del ciclo que empieza en pipelines/gold/build_artist_master.py
(que marca los huecos) y sigue en scripts/artist_master_web_research.py (que los
investiga sin promover nada). Aqui se decide que evidencia es lo bastante firme
para escribirse como ficha del maestro.

La disciplina es la del README de pipelines/config/artists: un hueco es un
resultado correcto, un pais equivocado es una corrupcion silenciosa que nadie
detecta leyendo el informe. Por eso el promotor prefiere no promover:

  - solo entra ``status=matched``. Un ``ambiguous`` es un homonimo sin resolver
    (Chillida padre e hijo, dos Antonio Saura), y desempatarlo por popularidad
    es justo el error que el investigador evita a proposito.
  - el pais sale del lugar de NACIMIENTO (P19) resuelto a su pais (P17), nunca
    del pais de la casa de subastas. Saenz de Tejada nacio en Tanger y vende en
    Madrid; hay un test en el repo que prohibe usar HOUSE_COUNTRY.
  - un lugar cuyo pais no queda en uno solo NO elige: Minsk declara catorce
    P17 (Rus de Kiev, Imperio ruso, URSS, Ucrania...) porque Wikidata registra
    los estados historicos. Se filtra a los que tienen ISO vigente (P297) y, si
    aun asi queda mas de uno, se deja el hueco.
  - una ocupacion no artistica no entra. Es el caso Garcia Marquez: 55 lotes de
    libros no convierten a un escritor en pintor.
  - nunca se pisa lo curado a mano, y un alias solo puede pertenecer a un
    artista (regla 3 del maestro).

Escribe a stdout o a un fichero, NUNCA dentro de pipelines/config/artists: el
YAML que sale se revisa y se pega a mano, igual que artist_master_propose.py.

Uso desde la raiz del repo::

    python scripts/artist_master_promote.py --shard a --out candidatos_a.yaml
    python scripts/artist_master_promote.py --report
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.shared.artist_key import artist_fold, attribution_type
from pipelines.shared.artist_master import (
    MAX_PLAUSIBLE_AGE,
    load_master,
    normalize_country,
)

DEFAULT_INPUT = ROOT / "data" / "enrichments" / "artist_web_research.jsonl"

# Ocupaciones de Wikidata que sostienen una ficha de artista plastico. Es una
# lista cerrada a proposito: el repo ya decidio no filtrar por la forma del
# nombre, y una regla generica sobre la ocupacion tendria el mismo defecto.
# Un escritor con lotes de libros (Garcia Marquez) no debe entrar como pintor.
ARTISTIC_OCCUPATIONS = frozenset(
    {
        "Q1028181",   # pintor
        "Q483501",    # artista
        "Q1281618",   # escultor
        "Q15296811",  # dibujante
        "Q644687",    # ilustrador
        "Q1925963",   # artista grafico
        "Q11569986",  # grabador
        "Q3391743",   # artista visual
        "Q33231",     # fotografo
        "Q16947657",  # litografo
        "Q5322166",   # disenador
        "Q329439",    # grabador (segunda forma usada en el corpus)
        "Q2707485",   # escenografo
        "Q3658608",   # caricaturista
        "Q42973",     # arquitecto
        "Q10373653",  # acuarelista
        "Q7541856",   # ceramista
        "Q18074503",  # artista de instalaciones
        "Q715301",    # historietista
        "Q10694573",  # artista textil
        "Q10732476",  # muralista
        "Q1935740",   # orfebre
    }
)

# Paises con codigo ISO que ya no existen: ISO los conserva, pero publicar a un
# artista como nacido en "SU" seria un dato muerto en el informe.
HISTORICAL_ISO = frozenset({"SU", "YU", "CS", "DD", "ZR", "AN"})

# Distancia maxima, en anios, entre el nacimiento que publica la casa y el que
# devuelve Wikidata antes de sospechar que son DOS PERSONAS.
#
# Es la trampa que documenta docs/PLAN_MAESTRO_ARTISTAS.md: buscar "Ricardo
# Canals" devuelve un representante de futbolistas nacido en 1970, no al pintor
# de 1876. El umbral tolera el desacuerdo normal entre fuentes (Antonio
# Palacios: 1874 en Wikipedia, 1876 en la ficha de Duran) y corta cuando la
# diferencia ya no es un error de registro sino otra persona.
MAX_BIRTH_YEAR_DRIFT = 15

# Distancia a partir de la cual el anio del catalogo ya no es un desacuerdo
# entre fuentes sino una ficha equivocada.
MAX_CATALOG_YEAR_DRIFT = 25

# Identidades que el repo declara NO verificables, con test propio en
# tests/pipelines/test_artist_master.py. Tener ficha en Wikidata acredita que
# la ficha existe, no que la persona sea real: de Pietro Psaier se sospecha una
# identidad fabricada por marchantes para vender obra atribuida a Warhol. Ya se
# dio de alta y se revirtio dos veces, asi que la decision vive en codigo.
DISPUTED_IDENTITIES = frozenset({"pietro psaier", "carlos villalva"})


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    """Lee el diario tolerando lineas rotas.

    Se abre en BINARIO y se decodifica linea a linea: en modo texto, un byte
    invalido lanza UnicodeDecodeError al iterar el fichero, o sea *antes* del
    try, y tumba la promocion entera por una sola linea que un proceso
    interrumpido dejo a medias. Es el mismo fallo que ya inutilizo la cache.
    """
    with path.open("rb") as handle:
        for raw in handle:
            if not raw.strip():
                continue
            try:
                value = json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                # El diario es append-only y reanudable: una linea truncada por
                # una interrupcion se ignora, no aborta la promocion.
                continue
            if isinstance(value, dict):
                yield value


def _plausible_year(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year if 500 <= year <= date.today().year else None


def country_from_places(
    places: Iterable[Mapping[str, Any]],
    place_countries: Mapping[str, str] | None = None,
) -> str | None:
    """Lugares de nacimiento -> un unico pais ISO, o None.

    Dos caminos, ninguno inventa: el mapa ``place_countries`` (P17 de Wikidata
    filtrado a paises vigentes) y, como respaldo, la tabla ``_countries.yaml``
    que ya resuelve las ciudades grandes. Si los lugares apuntan a mas de un
    pais, devuelve None: un artista nacido en un sitio no puede tener dos
    paises de nacimiento, asi que la discrepancia es una senal de duda.
    """
    codes: set[str] = set()
    for place in places or []:
        if not isinstance(place, Mapping):
            continue
        qid = place.get("id")
        code = None
        if place_countries and isinstance(qid, str):
            code = place_countries.get(qid)
        # El investigador ya resolvio el P17 vigente del lugar; es la via que
        # cubre las ciudades que _countries.yaml no conoce.
        if not code:
            iso = place.get("country_iso")
            if isinstance(iso, str) and iso.strip():
                code = iso.strip().upper()
        if not code:
            code = normalize_country(place.get("label"))
        if code and code not in HISTORICAL_ISO:
            codes.add(code)
    return next(iter(codes)) if len(codes) == 1 else None


def occupation_verdict(occupations: Iterable[Mapping[str, Any]]) -> str:
    """"artistic" | "non_artistic" | "unknown".

    La distincion que importa: **no declarar ocupacion no es evidencia en
    contra**. Costus (el duo de la Movida) y Jose Sancha son pintores reales
    cuya ficha de Wikidata no trae P106; descartarlos por ausencia de dato
    seria borrar en silencio, que es justo lo que prohibe la regla 1. Un
    futbolista homonimo, en cambio, si es evidencia y se rechaza.
    """
    items = [item for item in occupations or [] if isinstance(item, Mapping)]
    if not items:
        return "unknown"
    if any(item.get("id") in ARTISTIC_OCCUPATIONS for item in items):
        return "artistic"
    return "non_artistic"



def _is_latin(text: str) -> bool:
    """True si el texto se escribe en alfabeto latino.

    El display_name se PUBLICA en el informe y lo compara el fold contra el
    catalogo, asi que un label en otro alfabeto no sirve: Wikidata devolvio
    "بابلو بيكاسو" como label de Picasso, y esa ficha habria entrado como un
    artista nuevo teniendo ya "pablo_picasso" en el maestro.
    """
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    return all("LATIN" in unicodedata.name(ch, "") for ch in letters)


def _artist_id(result: Mapping[str, Any]) -> str:
    for key in ("research_key", "artist_key"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().replace(" ", "_")
    return "sin_id"


def _aliases(result: Mapping[str, Any]) -> list[str]:
    """Todas las grafias del catalogo, para que ningun lote quede fuera."""
    names: list[str] = []
    for value in [result.get("display_name"), *(result.get("aliases") or [])]:
        if isinstance(value, str) and value.strip() and value.strip() not in names:
            names.append(value.strip())
    return names



def _catalog_birth_year(result: Mapping[str, Any]) -> int | None:
    """Anio de nacimiento que publica la casa, venga donde venga."""
    direct = result.get("candidate_birth_year")
    if direct is not None:
        return _plausible_year(direct)
    context = result.get("master_context")
    if isinstance(context, Mapping):
        return _plausible_year(context.get("candidate_birth_year"))
    return None


def _disambiguate_by_catalog_year(result: Mapping[str, Any]) -> dict[str, Any] | None:
    """Un ambiguous con un unico candidato que casa el anio de la casa.

    Devuelve el registro convertido en ``matched`` sobre ese candidato, o None
    si no hay desempate limpio. La ficha resultante nunca llega a ``high``: es
    un homonimo resuelto por concordancia, no una identidad sin dudas.
    """
    year = _catalog_birth_year(result)
    if not year:
        return None
    candidates = result.get("candidates")
    if not isinstance(candidates, list):
        return None
    hits = [
        c
        for c in candidates
        if isinstance(c, Mapping)
        and _plausible_year((c.get("proposal") or {}).get("birth_year")) == year
    ]
    if len(hits) != 1:
        return None
    match = dict(hits[0])
    resolved = dict(result)
    resolved["status"] = "matched"
    resolved["match"] = match
    resolved["_disambiguated_by_catalog_year"] = year
    return resolved



def _display_name(
    proposal: Mapping[str, Any], result: Mapping[str, Any], artist_id: str
) -> str:
    """El label de Wikidata gana salvo que no sea latino; ahi manda el catalogo."""
    proposed = str(proposal.get("display_name") or "").strip()
    catalog = str(result.get("display_name") or "").strip()
    if proposed and _is_latin(proposed):
        return proposed
    return catalog or proposed or artist_id



# El catalogo tiene que INSISTIR para contradecir al maestro: un lote suelto
# puede llevar una errata del scraper, varios ya son la ficha de la casa.
MIN_LOTS_TO_CHALLENGE_MASTER = 2


def catalog_year_conflicts(
    master: Mapping[str, Any],
    dimension_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Fichas cuyo birth_year contradice al que publica la casa.

    Un hueco es un resultado correcto, pero un anio EQUIVOCADO se publica en
    el informe y no lo detecta nadie leyendolo. La carga del Excel curado dejo
    40 de estas: Nirma Zarate figuraba como n.1969 cuando sus 13 lotes dicen
    1936-1999, y el texto crudo lo confirma.

    NO corrige nada: devuelve la lista para revisar a mano, que es la misma
    disciplina del resto del ciclo.
    """
    out: list[dict[str, Any]] = []
    for row in dimension_rows:
        artist_id = row.get("artist_id")
        entry = master.get(artist_id) if artist_id else None
        if not isinstance(entry, Mapping):
            continue
        master_year = _plausible_year(entry.get("birth_year"))
        if not master_year:
            continue
        evidence = (row.get("evidence") or {}).get("birth_year") or []
        # Solo cuenta el valor DOMINANTE del catalogo. Antonio Barrera tiene 62
        # lotes diciendo 1948 (como el maestro) y 7 diciendo 1889: quedarse con
        # el discrepante mas votado ignorando la mayoria daba un falso positivo,
        # porque esa minoria es ruido de un homonimo o de otra ficha.
        votes = [
            (value, item.get("count") or 0)
            for item in evidence
            if isinstance(item, Mapping)
            and (value := _plausible_year(item.get("value")))
        ]
        best = None
        if votes:
            top_value, top_count = max(votes, key=lambda v: v[1])
            if (
                top_count >= MIN_LOTS_TO_CHALLENGE_MASTER
                and abs(top_value - master_year) > MAX_CATALOG_YEAR_DRIFT
            ):
                best = (top_value, top_count)
        if best:
            out.append(
                {
                    "artist_id": artist_id,
                    "display_name": entry.get("display_name"),
                    "master_birth_year": master_year,
                    "catalog_birth_year": best[0],
                    "lots": best[1],
                    "source": entry.get("source"),
                }
            )
    out.sort(key=lambda item: -item["lots"])
    return out


def build_entries(
    results: Iterable[Mapping[str, Any]],
    *,
    master: Mapping[str, Any] | None = None,
    place_countries: Mapping[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Evidencia -> (fichas promovidas, descartes con su motivo).

    Devuelve los descartes en vez de tragarselos porque el motivo es el
    resultado util: dice si falta investigacion, si hay un homonimo o si el
    nombre nunca fue una persona.
    """
    master = load_master() if master is None else master
    known_ids = set(master)
    # Se guardan por separado: los folds del maestro dicen "ya existe" y los de
    # esta tanda dicen "otra ficha nueva ya reclamo el nombre".
    master_folds: set[str] = set()
    for entry in master.values():
        if not isinstance(entry, Mapping):
            continue
        for alias in [entry.get("display_name"), *(entry.get("aliases") or [])]:
            fold = artist_fold(str(alias)) if alias else None
            if fold:
                master_folds.add(fold)
    claimed: set[str] = set(master_folds)

    entries: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    # wikidata_id -> ficha ya promovida. Dos grafias del catalogo pueden tener
    # folds distintos ("Ouka Leele" y "Ouka Lele") y ser la misma persona; si
    # Wikidata las resuelve al mismo QID, la identidad la afirma la fuente y se
    # fusionan en una ficha con las dos grafias como alias. Sin esto la artista
    # rankearia partida y la mitad de sus lotes se quedaria sin pais.
    by_wikidata: dict[str, dict[str, Any]] = {}

    def skip(result: Mapping[str, Any], reason: str) -> None:
        skipped.append(
            {
                "artist_id": _artist_id(result),
                "display_name": result.get("display_name"),
                "reason": reason,
                "lots_observed": result.get("lots_observed"),
                "source_url": result.get("source_url"),
            }
        )

    for result in results:
        status = str(result.get("status") or "unknown")
        if status == "ambiguous":
            # Wikidata no desempata homonimos por popularidad, y hace bien.
            # Pero la CASA publica el anio de nacimiento, y si solo uno de los
            # candidatos lo cumple, son dos fuentes independientes concordando
            # y la ambiguedad desaparece. Si casan dos, o ninguno, se queda sin
            # resolver: el desempate tiene que ser unico para valer.
            resolved = _disambiguate_by_catalog_year(result)
            if resolved is None:
                skip(result, "status_ambiguous")
                continue
            result = resolved
            status = "matched"
        elif status != "matched":
            skip(result, f"status_{status}")
            continue

        artist_id = _artist_id(result)
        if artist_id in known_ids or result.get("artist_id"):
            skip(result, "already_in_master")
            continue

        aliases = _aliases(result)
        # Red de seguridad: los objetos y escuelas ya se filtran aguas arriba,
        # pero una ficha cuyo nombre no es de autor no puede resolver un lote.
        if not aliases or not any(attribution_type(a) == "autor" for a in aliases):
            skip(result, "not_an_author")
            continue

        # Decision documentada del repo: la identidad esta en disputa y se
        # queda sin pais ni fechas aunque Wikidata tenga ficha.
        if any(artist_fold(a) in DISPUTED_IDENTITIES for a in aliases):
            skip(result, "identity_disputed")
            continue

        match_value = result.get("match")
        proposed_display = ""
        if isinstance(match_value, Mapping):
            proposal_value = match_value.get("proposal")
            if isinstance(proposal_value, Mapping):
                proposed_display = str(proposal_value.get("display_name") or "")

        # El display_name que devuelve Wikidata entra en la comparacion, no solo
        # los alias del catalogo. El maestro ya tenia a Steinlen como
        # "Théophile Alexandre Steinlen" y el catalogo lo publica invertido:
        # folds distintos, asi que sin esto se creaba un artista duplicado que
        # rompe load_master() al arrancar (regla 3).
        folds = {f for f in (artist_fold(a) for a in aliases) if f}
        display_fold = artist_fold(proposed_display) if proposed_display else None
        if display_fold:
            folds.add(display_fold)

        # La fusion por QID va ANTES del choque de alias: dos grafias de la
        # misma persona no son un conflicto, son alias de una sola ficha.
        qid = (
            str(match_value.get("wikidata_id") or "")
            if isinstance(match_value, Mapping)
            else ""
        )
        existing = by_wikidata.get(qid) if qid else None
        if existing is not None:
            for alias in aliases:
                if alias not in existing["aliases"]:
                    existing["aliases"].append(alias)
            claimed |= folds
            continue

        # Chocar con el maestro y chocar con otra ficha de esta misma tanda son
        # cosas distintas: la primera dice "ya existe, quiza falte un alias".
        if folds & master_folds:
            skip(result, "already_in_master")
            continue
        if folds & claimed:
            skip(result, "alias_already_claimed")
            continue

        # Un nombre de UNA palabra que solo casa con un ALIAS de Wikidata (no
        # con su label) no acredita identidad. El catalogo publica "Ángeles" y
        # Wikidata lista "Angeles" como alias de Peter Angelis, pintor flamenco:
        # el match es real y la conclusion, falsa. Con el label si vale, que es
        # el caso de Ceesepe o Balet.
        if isinstance(match_value, Mapping) and all(
            len(alias.split()) == 1 for alias in aliases
        ):
            # Se compara contra los alias DEL CATALOGO, no contra `folds`: ahi
            # ya se metio el display_name propuesto por Wikidata y la condicion
            # no dispararia nunca.
            catalog_folds = {f for f in (artist_fold(a) for a in aliases) if f}
            label_fold = artist_fold(str(match_value.get("label") or ""))
            if label_fold and label_fold not in catalog_folds:
                skip(result, "one_word_alias_only_match")
                continue

        match = result.get("match")
        proposal = match.get("proposal") if isinstance(match, Mapping) else None
        if not isinstance(proposal, Mapping):
            skip(result, "no_proposal")
            continue

        verdict = occupation_verdict(proposal.get("occupations"))
        if verdict == "non_artistic":
            skip(result, "no_artistic_occupation")
            continue

        country = country_from_places(proposal.get("birth_places"), place_countries)
        birth = _plausible_year(proposal.get("birth_year"))
        death = _plausible_year(proposal.get("death_year"))
        # Una muerte anterior al nacimiento invalida el par entero: no se sabe
        # cual de los dos esta mal, asi que no se publica ninguno.
        if birth and death and death <= birth:
            birth = death = None

        # El catalogo de la casa es el desempate contra el homonimo: si su anio
        # de nacimiento se aleja demasiado del de Wikidata, lo mas probable es
        # que sean dos personas distintas y no un dato corregido.
        # El investigador guarda el dato del catalogo dentro de master_context;
        # se acepta tambien en el nivel superior para tolerar diarios antiguos.
        context = result.get("master_context")
        # Nacido hace mas de MAX_PLAUSIBLE_AGE y sin fecha de muerte: no es un
        # supercentenario, es una ficha incompleta. El anio de nacimiento es
        # bueno y se conserva, pero no se puede publicar "n. 1853" a secas
        # porque el informe lo escribe como si siguiera vivo. Es el bug que
        # publico a Fidolo Gonzalez Camargo con 96 anios.
        implausibly_old = bool(
            birth and not death and date.today().year - birth > MAX_PLAUSIBLE_AGE
        )

        catalog_birth = _plausible_year(
            result.get("candidate_birth_year")
            if result.get("candidate_birth_year") is not None
            else (context.get("candidate_birth_year") if isinstance(context, Mapping) else None)
        )
        if birth and catalog_birth and abs(birth - catalog_birth) > MAX_BIRTH_YEAR_DRIFT:
            skip(result, "birth_year_conflicts_with_catalog")
            continue

        source_url = ""
        if isinstance(match, Mapping):
            source_url = str(match.get("source_url") or "")
        lots = result.get("lots_observed")
        note_parts = []
        if lots:
            note_parts.append(f"{lots} lotes")
        note_parts.append("Identidad verificada en Wikidata por match exacto de nombre")
        disambiguated = result.get("_disambiguated_by_catalog_year")
        if disambiguated:
            note_parts.append(
                "habia varios homonimos y se desempato porque solo uno nacio en "
                f"{disambiguated}, el anio que publica la casa"
            )
        if verdict == "unknown":
            note_parts.append(
                "Wikidata no declara ocupacion: confirmar que es artista antes de fijar"
            )
        if implausibly_old:
            note_parts.append(
                "sin fecha de muerte y nacido hace mas de "
                f"{MAX_PLAUSIBLE_AGE} anios: falta el dato, no esta vivo"
            )
        if not country:
            note_parts.append("sin pais de nacimiento resoluble: pendiente de verificar")
        if source_url:
            note_parts.append(f"Fuente: {source_url}")

        entry = {
                "artist_id": artist_id,
                "display_name": _display_name(proposal, result, artist_id),
                "country_birth": country,
                "nationalities": [country] if country else [],
                "birth_year": birth,
                "death_year": death,
                "attribution_type": "autor",
                "source": "wikidata",
                # Sin pais la ficha sigue siendo util (identidad y fechas), pero
                # se marca low para que la siguiente tanda la vuelva a mirar.
                "confidence": (
                    "medium"
                    if disambiguated and country and birth
                    else "high"
                    if country and birth and verdict == "artistic" and not implausibly_old
                    else "low"
                ),
                # Se emite explicito en None para que quien revise vea que el
                # hueco esta sin resolver, en vez de que la clave falte.
                "death_status": None,
                "aliases": aliases,
                "notes": ". ".join(note_parts),
        }
        entries.append(entry)
        if qid:
            by_wikidata[qid] = entry
        claimed |= folds
        known_ids.add(artist_id)

    return entries, skipped


def build_completions(
    results: Iterable[Mapping[str, Any]],
    *,
    master: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Huecos de fichas YA curadas que la evidencia puede cerrar.

    Son complementos, no altas: la ficha existe y solo le falta un campo. Se
    emiten para revisar a mano — este script nunca escribe en los shards.

    Nunca se propone un ``death_year`` para quien esta declarado ``living``:
    eso no es un hueco sino una afirmacion del curador, y pisarla publicaria
    como muerto a alguien vivo. Es el mismo cuidado que ya obligo a poner
    "n. 1954" en vez de "1954-" en el informe.
    """
    master = load_master() if master is None else master
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    for result in results:
        if result.get("status") != "matched":
            continue
        artist_id = result.get("artist_id")
        entry = master.get(artist_id) if artist_id else None
        if not isinstance(entry, Mapping) or artist_id in seen:
            continue

        # Las identidades en disputa tampoco se complementan: el hueco de
        # Pietro Psaier es deliberado y una tanda de complementos volvio a
        # rellenarle el pais el 2026-08-18, tercera reincidencia del mismo caso.
        names = [entry.get("display_name"), *(entry.get("aliases") or [])]
        if any(artist_fold(str(n)) in DISPUTED_IDENTITIES for n in names if n):
            continue

        match_value = result.get("match")
        proposal = match_value.get("proposal") if isinstance(match_value, Mapping) else None
        if not isinstance(proposal, Mapping):
            continue
        if occupation_verdict(proposal.get("occupations")) == "non_artistic":
            continue

        # Un hueco que el curador dejo A PROPOSITO no es un hueco que rellenar.
        # Sebastian de Llanos y Valdes lleva escrito "Se omiten los anios por
        # discrepancia": proponer fechas ahi contradice a quien ya miro el caso.
        notes = str(entry.get("notes") or "").lower()
        deliberate_gap = any(
            marker in notes
            for marker in ("se omite", "discrepanc", "sin verificar", "no verificable")
        )

        fields: dict[str, Any] = {}
        if not entry.get("country_birth"):
            country = country_from_places(proposal.get("birth_places"))
            if country:
                fields["country_birth"] = country

        birth = _plausible_year(proposal.get("birth_year"))
        death = _plausible_year(proposal.get("death_year"))
        existing_birth = _plausible_year(entry.get("birth_year"))

        # El desempate contra el homonimo tambien aplica aqui: si la ficha ya
        # tiene un nacimiento y Wikidata da otro muy distinto, no es la misma
        # persona y no se complementa nada.
        if existing_birth and birth and abs(existing_birth - birth) > MAX_BIRTH_YEAR_DRIFT:
            continue
        if birth and not existing_birth:
            fields["birth_year"] = birth
        if (
            death
            and not entry.get("death_year")
            and entry.get("death_status") not in ("living", "not_applicable")
        ):
            fields["death_year"] = death

        # Wikidata tiene ficha y NO publica fecha de muerte: es evidencia de que
        # la persona vive, y convierte un hueco ambiguo en un dato afirmado. Sin
        # death_status, "n. 1954" no distingue "sigue vivo" de "falta el dato".
        #
        # El limite de edad es la cautela que ya existe en el informe: pasados
        # MAX_PLAUSIBLE_AGE anios lo probable no es un supercentenario sino una
        # ficha incompleta, y ahi el hueco se queda visible.
        birth_for_age = existing_birth or birth
        if (
            not death
            and not entry.get("death_year")
            and not entry.get("death_status")
            and birth_for_age
            and date.today().year - birth_for_age <= MAX_PLAUSIBLE_AGE
        ):
            fields["death_status"] = "living"

        if not fields or deliberate_gap:
            continue
        seen.add(str(artist_id))
        out.append(
            {
                "artist_id": artist_id,
                "display_name": entry.get("display_name") or artist_id,
                "fields": fields,
                "source_url": str(
                    match_value.get("source_url") if isinstance(match_value, Mapping) else ""
                ),
            }
        )
    return out


def _yaml_str(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def render_shard(entries: list[dict[str, Any]]) -> str:
    """Fichas -> YAML listo para revisar y pegar en el shard que toque."""
    lines = [
        "# Generado por scripts/artist_master_promote.py a partir de la",
        "# investigacion en Wikidata. REVISAR ANTES DE PEGAR:",
        "#   - comprobar que el homonimo es el que vende en las casas",
        "#   - las fichas confidence: low no tienen pais y siguen pendientes",
        "",
        "artists:",
    ]
    for entry in entries:
        lines.append(f"  - artist_id: {entry['artist_id']}")
        lines.append(f"    display_name: {_yaml_str(entry['display_name'])}")
        # Los codigos van SIEMPRE entrecomillados: YAML 1.1 lee NO (Noruega)
        # como el booleano False y Noruega desaparecia de la tabla en silencio.
        country = entry["country_birth"]
        lines.append(
            f'    country_birth: "{country}"' if country else "    country_birth: null"
        )
        nationalities = entry["nationalities"]
        lines.append(
            "    nationalities: [" + ", ".join(f'"{c}"' for c in nationalities) + "]"
            if nationalities
            else "    nationalities: []"
        )
        if entry["birth_year"]:
            lines.append(f"    birth_year: {entry['birth_year']}")
        if entry["death_year"]:
            lines.append(f"    death_year: {entry['death_year']}")
        lines.append("    attribution_type: autor")
        lines.append(f"    source: {entry['source']}")
        lines.append(f"    confidence: {entry['confidence']}")
        lines.append("    aliases:")
        for alias in entry["aliases"]:
            lines.append(f"      - {_yaml_str(alias)}")
        lines.append(f"    notes: {_yaml_str(entry['notes'])}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Promueve a fichas del maestro la evidencia Wikidata inequivoca. "
            "Escribe YAML para revisar; nunca toca pipelines/config/artists."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--shard", help="Solo los artist_id que empiezan por esta letra.")
    parser.add_argument("--limit", type=int, help="Corta a las N primeras fichas.")
    parser.add_argument("--out", type=Path, help="Fichero de salida (por defecto stdout).")
    parser.add_argument(
        "--report",
        action="store_true",
        help="Resume promovidos y motivos de descarte en vez de emitir YAML.",
    )
    parser.add_argument(
        "--year-conflicts",
        action="store_true",
        help="Lista fichas cuyo birth_year contradice al catalogo de la casa.",
    )
    parser.add_argument(
        "--completions",
        action="store_true",
        help="Lista huecos de fichas YA curadas que la evidencia puede cerrar.",
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(
            f"No existe el diario de investigacion: {args.input}\n"
            "Ejecuta antes python scripts/artist_master_web_research.py",
            file=sys.stderr,
        )
        return 2

    if args.year_conflicts:
        sys.stdout.reconfigure(encoding="utf-8")
        dim = ROOT / "data" / "gold" / "dim_artist_master.jsonl"
        rows = _iter_jsonl(dim) if dim.exists() else []
        conflicts = catalog_year_conflicts(load_master(), rows)
        print(f"--- Fichas con anio en conflicto con el catalogo: {len(conflicts)} ---")
        for item in conflicts:
            print(
                f"  {item['artist_id']:<34} maestro n.{item['master_birth_year']}"
                f"  catalogo n.{item['catalog_birth_year']} ({item['lots']} lotes)"
            )
        return 0

    if args.completions:
        sys.stdout.reconfigure(encoding="utf-8")
        completions = build_completions(_iter_jsonl(args.input))
        print(f"--- Complementos para fichas ya curadas: {len(completions)} ---")
        counts: Counter[str] = Counter()
        for item in completions:
            counts.update(item["fields"].keys())
            campos = ", ".join(f"{k}={v}" for k, v in sorted(item["fields"].items()))
            print(f"  {item['artist_id']:<34} {campos}")
            print(f"      {item['source_url']}")
        print(f"  campos: {dict(counts)}")
        return 0

    entries, skipped = build_entries(_iter_jsonl(args.input))

    if args.shard:
        prefix = args.shard.lower()
        entries = [e for e in entries if e["artist_id"].lower().startswith(prefix)]
    if args.limit:
        entries = entries[: args.limit]

    sys.stdout.reconfigure(encoding="utf-8")

    if args.report:
        reasons = Counter(item["reason"] for item in skipped)
        with_country = sum(1 for e in entries if e["country_birth"])
        with_birth = sum(1 for e in entries if e["birth_year"])
        print("--- Promocion de evidencia Wikidata ---")
        print(f"  fichas promovibles      : {len(entries)}")
        print(f"    con pais de nacimiento: {with_country}")
        print(f"    con anio de nacimiento: {with_birth}")
        print(f"  descartadas             : {len(skipped)}")
        for reason, count in reasons.most_common():
            print(f"    {reason:<26}: {count}")
        return 0

    text = render_shard(entries)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"{len(entries)} fichas escritas en {args.out}")
    else:
        print(text)
    print(f"# {len(entries)} promovidas, {len(skipped)} descartadas", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
