"""Maestro de artistas: identidad, pais de nacimiento y nacionalidades.

El maestro vive en pipelines/config/artists/ (YAML curado, versionado en git).
Este modulo es el unico punto de lectura, para que Silver, Gold y el informe no
puedan divergir. Mismo patron que pipelines/shared/fx.py con las tasas de cambio.

Regla de diseno: un artista que no esta en el maestro devuelve country_birth
None, nunca un pais inventado ni el pais de la casa de subastas. Es el mismo
principio que to_eur(), que devuelve None en vez de 1.0: un dato que falta debe
verse, no disfrazarse.

Ojo con el atajo tentador: render_html.py tiene un HOUSE_COUNTRY que es donde
OCURRE la subasta, no de donde es el artista. "Lote de Bogota => artista
colombiano" ya seria falso hoy para 46 artistas espanioles, 26 alemanes y 25
paameienios presentes en los datos.

Por que el maestro se clava en alias explicitos y no en el fold automatico: hay
86 nombres con fechas de nacimiento en conflicto y "Francisco Toledo" son dos
personas reales distintas que comparten fold. Con alias se pueden separar; con
el fold como clave, ese error seria irreparable por construccion.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from pipelines.shared.artist_key import artist_fold, attribution_type, strip_biography

ROOT = Path(__file__).resolve().parents[2]
ARTISTS_DIR = ROOT / "pipelines" / "config" / "artists"

# Nombre del fichero de paises, no su ruta: se resuelve contra ARTISTS_DIR en
# cada lectura para que los tests puedan redirigir el directorio entero con un
# solo monkeypatch.
COUNTRIES_FILENAME = "_countries.yaml"

# Punto de compatibilidad del antiguo parche por lot_url. El parser de Duran ya
# prioriza el campo Autor y el mapa esta deliberadamente vacio. No es un shard:
# no lleva `artists:` y se salta igual que la tabla de paises.
LOT_AUTHOR_FIXES_FILENAME = "_lot_author_fixes.yaml"

# Ficheros de pipelines/config/artists/ que NO son shards de artistas.
_NON_SHARD_FILENAMES = frozenset({COUNTRIES_FILENAME, LOT_AUTHOR_FIXES_FILENAME})

VALID_SOURCES = ("manual", "llm", "parsed")
VALID_CONFIDENCE = ("high", "medium", "low")

# Estados posibles de resolucion de un lote.
RESOLUTION_MASTER = "master"          # alias encontrado en el maestro
RESOLUTION_FOLD_ONLY = "fold_only"    # es autor, pero no esta en el maestro
RESOLUTION_NOT_AUTHOR = "not_an_author"  # escuela, anonimo, mueble...
RESOLUTION_UNRESOLVED = "unresolved"  # sin nombre utilizable


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _iso(value: Any) -> str:
    """Codigo ISO como texto en mayusculas.

    YAML 1.1 lee NO, ON, OFF y YES sin comillas como booleanos, asi que
    "NO: Noruega" llegaba aqui como la clave False y Noruega desaparecia de la
    tabla. Se normaliza a "NO"/"ON"/... en vez de dejar pasar un bool.
    """
    if value is True:
        return "YES"
    if value is False:
        return "NO"
    return str(value).strip().upper()


@lru_cache(maxsize=1)
def load_countries() -> Dict[str, Any]:
    """Carga _countries.yaml (cacheado: se lee una sola vez por proceso)."""
    data = _load_yaml(ARTISTS_DIR / COUNTRIES_FILENAME)
    return {
        "countries": {
            _iso(code): entry for code, entry in (data.get("countries") or {}).items()
        },
        # Las claves de alias se pliegan para que "Panamá" y "panama" entren igual.
        "aliases": {
            artist_fold(str(k)) or str(k).strip().casefold(): _iso(v)
            for k, v in (data.get("aliases") or {}).items()
        },
    }


@lru_cache(maxsize=1)
def load_master() -> Dict[str, Dict[str, Any]]:
    """Fusiona todos los shards de pipelines/config/artists/ en artist_id -> entrada.

    Lanza ValueError si hay un artist_id duplicado entre shards. Es la garantia
    de integridad que impide que dos curadores asignen el mismo nombre a dos
    artistas distintos: falla al cargar, ruidosamente, no a mitad de stream.

    Un directorio ausente o con los shards vacios devuelve {} sin fallar: es el
    estado de entrega mientras el maestro no se ha poblado.
    """
    master: Dict[str, Dict[str, Any]] = {}
    if not ARTISTS_DIR.exists():
        return master

    for shard in sorted(ARTISTS_DIR.glob("*.yaml")):
        if shard.name in _NON_SHARD_FILENAMES:
            continue
        for entry in _load_yaml(shard).get("artists") or []:
            artist_id = (entry or {}).get("artist_id")
            if not artist_id:
                raise ValueError(f"{shard.name}: hay una entrada sin artist_id")
            if artist_id in master:
                raise ValueError(
                    f"artist_id duplicado '{artist_id}': esta en "
                    f"{master[artist_id]['_shard']} y en {shard.name}"
                )
            record = dict(entry)
            record["_shard"] = shard.name
            master[artist_id] = record
    return master


@lru_cache(maxsize=1)
def load_lot_author_fixes() -> Dict[str, str]:
    """Carga el mapa legado lot_url -> autor; en produccion debe estar vacio.

    Se conserva para compatibilidad con datos/configuraciones antiguas. Las
    reparaciones nuevas deben hacerse en el parser y reprocesando el output, no
    ampliando este mapa ni convirtiendo titulos en aliases del maestro.
    """
    data = _load_yaml(ARTISTS_DIR / LOT_AUTHOR_FIXES_FILENAME)
    fixes = data.get("lot_authors") or {}
    return {
        str(url): strip_biography(str(author))
        for url, author in fixes.items()
        if url and author
    }


@lru_cache(maxsize=1)
def _alias_index() -> Dict[str, str]:
    """artist_fold(alias) -> artist_id.

    Lanza si dos artistas reclaman el mismo alias: un nombre crudo solo puede
    pertenecer a una persona.
    """
    index: Dict[str, str] = {}
    for artist_id, entry in load_master().items():
        # El display_name tambien resuelve, aunque no se repita en aliases.
        candidates = list(entry.get("aliases") or [])
        if entry.get("display_name"):
            candidates.append(entry["display_name"])
        for alias in candidates:
            fold = artist_fold(str(alias))
            if not fold:
                continue
            owner = index.get(fold)
            if owner and owner != artist_id:
                raise ValueError(
                    f"alias duplicado '{alias}' (fold '{fold}'): lo reclaman "
                    f"'{owner}' y '{artist_id}'"
                )
            index[fold] = artist_id
    return index


def normalize_country(text: Optional[str]) -> Optional[str]:
    """Texto libre de pais -> codigo ISO alpha-2, o None si no se reconoce.

    "Bogotá" -> "CO", "Inglaterra" -> "GB", "Reino Unido" -> "GB".
    Un valor no reconocido devuelve None en vez de colarse tal cual: asi la
    puerta de calidad lo cuenta en unmapped_country_values y la tabla de alias
    puede crecer, en vez de que _countries.yaml se pudra en silencio.
    """
    if not text:
        return None
    raw = str(text).strip()
    if not raw:
        return None
    # Ya viene como codigo ISO valido.
    if len(raw) == 2 and raw.upper() in load_countries()["countries"]:
        return raw.upper()
    fold = artist_fold(raw) or raw.casefold()
    return load_countries()["aliases"].get(fold)


def country_es(code: Optional[str]) -> Optional[str]:
    """Codigo ISO -> nombre en espaniol para mostrar. None si no se conoce."""
    if not code:
        return None
    entry = load_countries()["countries"].get(str(code).upper())
    return entry.get("es") if entry else None


def demonym_es(code: Optional[str]) -> Optional[str]:
    """Codigo ISO -> gentilicio en espaniol ("ES" -> "espaniol"). None si falta.

    El dato ya estaba en _countries.yaml para los 42 paises pero no tenia
    getter, asi que el informe no podia escribir "pintor colombiano" y se
    limitaba a poner el nombre del pais al lado de las fechas.
    """
    if not code:
        return None
    entry = load_countries()["countries"].get(str(code).upper())
    return entry.get("demonym_es") if entry else None


def artist_years(artist_id: Optional[str]) -> Dict[str, Any]:
    """artist_id -> anios de nacimiento y muerte del maestro.

    Se lee aqui y no en resolve_artist a proposito: las 7 claves que este
    devuelve se escriben en los 62.420 lotes de Silver, y los anios son un dato
    por ARTISTA, no por lote. El ranking ya agrupa por artist_id, asi que los
    pide una sola vez por artista al serializar.

    Nunca se infiere una fecha: un artista fuera del maestro, o dentro pero sin
    fecha, devuelve None en los dos campos. Misma disciplina que country_birth
    (ver README de pipelines/config/artists).
    """
    empty = {"birth_year": None, "death_year": None}
    if not artist_id:
        return empty
    entry = load_master().get(artist_id)
    if not entry:
        return empty
    return {
        "birth_year": entry.get("birth_year"),
        "death_year": entry.get("death_year"),
    }


# Edad por encima de la cual "sin fecha de muerte" ya no se puede leer como
# "vivo": es que falta el dato. El informe llego a publicar a Fidolo Gonzalez
# Camargo (n. 1883, m. 1942) como si tuviera 96 anios porque su ficha decia
# 1930, y a Julia Acunia Guillen con 121. Un supercentenario es posible pero
# rarisimo; una ficha incompleta es lo normal, asi que se dice lo segundo.
MAX_PLAUSIBLE_AGE = 105


def format_life_years(
    birth: Optional[int],
    death: Optional[int],
    this_year: Optional[int] = None,
) -> Optional[str]:
    """(1920, 1992) -> "1920-1992"; (1954, None) -> "n. 1954"; sin datos -> None.

    Un artista vivo y uno sin fecha de muerte registrada son indistinguibles en
    el maestro, asi que se usa "n." (nacido) en vez de "1954-" : esa forma
    afirmaria que sigue vivo, y el dato no da para tanto.

    Pasado MAX_PLAUSIBLE_AGE ni siquiera "n." se sostiene, porque el lector lo
    lee como una persona viva: ahi se marca "n. 1905 (?)" para que el hueco se
    vea como hueco. No se inventa una muerte, que es la regla de siempre; se
    deja de afirmar implicitamente algo que casi seguro es falso.
    """
    if birth and death:
        return f"{birth}-{death}"
    if birth:
        if this_year and this_year - int(birth) > MAX_PLAUSIBLE_AGE:
            return f"n. {birth} (?)"
        return f"n. {birth}"
    if death:
        return f"m. {death}"
    return None


def _empty_resolution(resolution: str, fold: Optional[str], attribution: str) -> Dict[str, Any]:
    return {
        "artist_id": None,
        "artist_fold": fold,
        "artist_display_name": None,
        "attribution_type": attribution,
        "artist_country_birth": None,
        "artist_nationalities": [],
        "artist_resolution": resolution,
    }


def resolve_artist(name: Optional[str]) -> Dict[str, Any]:
    """Resuelve un nombre crudo a identidad y pais. Nunca lanza, nunca inventa.

    Devuelve siempre un dict con las mismas 7 claves, para que todos los lotes
    de Silver tengan la misma forma (incluidos los 3.437 de Zorrilla, que es una
    casa de joyeria y no trae artista en ningun lote).

    artist_resolution dice de donde sale cada cosa:
      "master"        -> alias encontrado; el pais sale SOLO del maestro
      "fold_only"     -> es autor pero no esta en el maestro: sin pais
      "not_an_author" -> escuela / anonimo / mueble: sin identidad ni pais
      "unresolved"    -> sin nombre utilizable
    """
    attribution = attribution_type(name)

    if attribution == "desconocido":
        return _empty_resolution(RESOLUTION_UNRESOLVED, None, attribution)

    fold = artist_fold(name)

    if attribution != "autor":
        return _empty_resolution(RESOLUTION_NOT_AUTHOR, fold, attribution)

    artist_id = _alias_index().get(fold) if fold else None
    if not artist_id:
        return _empty_resolution(RESOLUTION_FOLD_ONLY, fold, attribution)

    entry = load_master()[artist_id]
    country_birth = normalize_country(entry.get("country_birth"))
    nationalities = [
        code
        for code in (
            normalize_country(n) for n in (entry.get("nationalities") or [])
        )
        if code
    ]
    # La de nacimiento siempre esta entre las nacionalidades si se conoce.
    if country_birth and country_birth not in nationalities:
        nationalities.append(country_birth)

    return {
        "artist_id": artist_id,
        "artist_fold": fold,
        "artist_display_name": entry.get("display_name") or (name or "").strip(),
        "attribution_type": entry.get("attribution_type") or attribution,
        "artist_country_birth": country_birth,
        "artist_nationalities": nationalities,
        "artist_resolution": RESOLUTION_MASTER,
    }


def validate_master() -> List[str]:
    """Comprueba el maestro y devuelve la lista de problemas encontrados.

    Se usa desde los tests y desde scripts/artist_master_propose.py. Devuelve
    mensajes en vez de lanzar para poder informar de todos los fallos de golpe.
    """
    problems: List[str] = []
    countries = load_countries()["countries"]

    for artist_id, entry in load_master().items():
        shard = entry.get("_shard", "?")
        where = f"{shard}:{artist_id}"

        if not entry.get("display_name"):
            problems.append(f"{where}: falta display_name")

        source = entry.get("source")
        if source not in VALID_SOURCES:
            problems.append(f"{where}: source '{source}' no esta en {VALID_SOURCES}")

        confidence = entry.get("confidence")
        if confidence not in VALID_CONFIDENCE:
            problems.append(
                f"{where}: confidence '{confidence}' no esta en {VALID_CONFIDENCE}"
            )

        # Ojo con el guardado por truthiness: un country_birth escrito como NO
        # sin comillas llega aqui como el booleano False, que es falsy. Con un
        # "if birth:" la corrupcion pasaba de largo justo por el unico control
        # que existe para detectarla. Se compara contra None explicitamente.
        birth = entry.get("country_birth")
        if birth is not None and _iso(birth) not in countries:
            problems.append(f"{where}: country_birth '{birth}' no esta en _countries.yaml")
        if isinstance(birth, bool):
            problems.append(
                f"{where}: country_birth llego como booleano: falta entrecomillar "
                f'el codigo en el YAML (usar "NO", no NO)'
            )

        for nat in entry.get("nationalities") or []:
            if _iso(nat) not in countries:
                problems.append(f"{where}: nacionalidad '{nat}' no esta en _countries.yaml")
            if isinstance(nat, bool):
                problems.append(
                    f"{where}: nacionalidad llego como booleano: falta entrecomillar "
                    f'el codigo en el YAML (usar "NO", no NO)'
                )

        if not entry.get("aliases"):
            problems.append(f"{where}: sin aliases, no resolvera ningun lote")

        # El shard debe corresponder con la inicial del artist_id, para que un
        # lote de altas toque un solo fichero.
        expected = f"{artist_id[0].lower()}.yaml"
        if shard not in (expected, "_misc.yaml"):
            problems.append(f"{where}: deberia vivir en {expected} o en _misc.yaml")

    return problems


def reset_caches() -> None:
    """Limpia los caches. Solo para tests que cambian ARTISTS_DIR."""
    load_countries.cache_clear()
    load_master.cache_clear()
    load_lot_author_fixes.cache_clear()
    _alias_index.cache_clear()
