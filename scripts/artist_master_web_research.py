#!/usr/bin/env python3
"""Investiga, sin promover, los huecos del maestro de artistas en Wikidata.

Esta herramienta es deliberadamente independiente del pipeline. Lee la
dimensión materializada en Gold y escribe un diario de evidencia en
``data/enrichments``. Nunca modifica los shards YAML ni el JSONL de entrada.

El criterio de match es conservador: al menos un label/alias de Wikidata debe
ser exactamente igual bajo ``artist_fold`` a un nombre del maestro, y la
entidad debe declarar ``instance of (P31) human (Q5)``. Dos o más humanos que
cumplan el criterio producen ``ambiguous``; no se desempata por popularidad ni
por ocupación.

Uso desde la raíz del repositorio::

    python scripts/artist_master_web_research.py --limit 100 --sleep 0.25

La salida y la caché HTTP son JSONL append-only, por lo que una ejecución se
puede reanudar sin perder resultados ya escritos ni repetir consultas exitosas.
Los registros con ``status=error`` solo se reintentan con ``--retry-errors``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.shared.artist_key import artist_fold


DEFAULT_INPUT = ROOT / "data" / "gold" / "dim_artist_master.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "enrichments" / "artist_web_research.jsonl"
DEFAULT_CACHE = (
    ROOT / "data" / "enrichments" / "artist_web_research_cache.jsonl"
)

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY_URL = "https://www.wikidata.org/wiki/{qid}"
USER_AGENT = (
    "AuctionHousesApp-ArtistResearchBot/1.0 "
    "(https://github.com/juansegiraldo/AuctionHousesApp; artist research)"
)
MAX_SEARCH_RESULTS_PER_LANGUAGE = 500

# Espera ante maxlag. Wikidata pide reintentar "tras al menos 5 segundos"; se
# aplica un factor sobre el lag declarado porque el servidor sigue retrasado
# justo despues de anunciarlo.
MIN_MAXLAG_WAIT = 5.0
MAXLAG_WAIT_FACTOR = 2.0

HUMAN_QID = "Q5"
RECORDED_PROPERTIES = ("P569", "P570", "P19", "P106")
_QID_RE = re.compile(r"^Q[1-9]\d*$")
_WIKIDATA_TIME_RE = re.compile(r"^([+-])(\d+)-")

_LOTS_KEYS = (
    "lots_observed",
    "lots_offered",
    "lots",
    "lot_count",
    "lots_count",
    "total_lots",
)
_REVENUE_KEYS = (
    "revenue_eur",
    "total_revenue_eur",
    "revenue",
    "total_revenue",
)

JsonObject = dict[str, Any]
SleepFn = Callable[[float], None]
OpenFn = Callable[..., Any]


class WikidataAPIError(RuntimeError):
    """Respuesta inválida o error no recuperable de la API."""


class TransientWikidataError(WikidataAPIError):
    """Error de Wikidata que sí admite reintento."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def utc_now() -> str:
    """Timestamp UTC estable y legible para los diarios JSONL."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _json_line(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def iter_jsonl(path: Path, *, tolerate_bad_lines: bool = False) -> Iterator[JsonObject]:
    """Lee objetos JSONL; el input es estricto y los diarios reanudables no.

    Una interrupción durante un append puede dejar una última línea truncada.
    Para caché/salida se avisa y se ignora; para la dimensión de entrada se
    levanta un error con número de línea para no investigar datos corruptos.

    Se lee en BINARIO y se decodifica línea a línea a propósito: abriendo el
    fichero en modo texto, un byte inválido lanza UnicodeDecodeError al iterar,
    es decir *antes* de entrar en el try, y ni siquiera tolerate_bad_lines lo
    atrapaba. Un proceso interrumpido a mitad de escritura dejó así una caché
    de 17.511 líneas inservible por UNA línea rota.
    """

    with path.open("rb") as handle:
        for line_number, raw_bytes in enumerate(handle, start=1):
            if not raw_bytes.strip():
                continue
            try:
                text = raw_bytes.decode("utf-8").strip()
                if not text:
                    continue
                value = json.loads(text)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                if tolerate_bad_lines:
                    print(
                        f"Aviso: se ignora JSONL inválido en {path}:{line_number}: {exc}",
                        file=sys.stderr,
                    )
                    continue
                raise ValueError(f"JSONL inválido en {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                if tolerate_bad_lines:
                    print(
                        f"Aviso: se ignora valor no-objeto en {path}:{line_number}",
                        file=sys.stderr,
                    )
                    continue
                raise ValueError(
                    f"Se esperaba un objeto JSON en {path}:{line_number}"
                )
            yield value


def append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    """Añade y fuerza a disco un registro completo de reanudación."""

    path.parent.mkdir(parents=True, exist_ok=True)
    needs_separator = False
    if path.exists() and path.stat().st_size:
        with path.open("rb") as existing:
            existing.seek(-1, 2)
            needs_separator = existing.read(1) not in {b"\n", b"\r"}
    # El registro y su salto de linea van en UN SOLO write. Con dos writes, dos
    # procesos escribiendo el mismo diario a la vez se cuelan entre ambos y
    # parten los registros: la corrida solapada del 2026-08-18 dejo 71 lineas
    # cortadas a media URL. Un unico write no da atomicidad formal, pero a este
    # tamanio de linea el entrelazado deja de ocurrir en la practica.
    payload = _json_line(value) + "\n"
    if needs_separator:
        # Si una interrupcion dejo la ultima linea a medias, no se pega el
        # siguiente objeto a ella: la linea rota se podra ignorar al reanudar.
        payload = "\n" + payload
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()


class JsonlResponseCache:
    """Caché append-only de respuestas API, indexada por URL canónica."""

    def __init__(self, path: Path | None):
        self.path = path
        self._responses: dict[str, JsonObject] = {}
        if path is not None and path.exists():
            for row in iter_jsonl(path, tolerate_bad_lines=True):
                key = row.get("cache_key")
                response = row.get("response")
                if isinstance(key, str) and isinstance(response, dict):
                    self._responses[key] = response

    @staticmethod
    def key_for(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def get(self, url: str) -> JsonObject | None:
        return self._responses.get(self.key_for(url))

    def put(self, url: str, response: JsonObject) -> None:
        key = self.key_for(url)
        self._responses[key] = response
        if self.path is not None:
            append_jsonl(
                self.path,
                {
                    "cache_key": key,
                    "fetched_at": utc_now(),
                    "request_url": url,
                    "response": response,
                },
            )


def _retry_after_seconds(exc: urllib.error.HTTPError) -> float | None:
    value = exc.headers.get("Retry-After") if exc.headers else None
    if value and value.strip().isdigit():
        return min(120.0, float(value.strip()))
    return None


def _api_error(payload: Mapping[str, Any]) -> WikidataAPIError | None:
    error = payload.get("error")
    if not isinstance(error, Mapping):
        return None
    code = str(error.get("code") or "unknown")
    message = str(error.get("info") or error.get("message") or "error de API")
    text = f"Wikidata API {code}: {message}"
    if code in {"maxlag", "ratelimited", "readonly", "internal_api_error"}:
        lag = error.get("lag")
        try:
            retry_after = float(lag) if lag is not None else None
        except (TypeError, ValueError):
            retry_after = None
        # El lag declarado es cuanto lleva retrasado el servidor AHORA, no
        # cuanto tardara en recuperarse: esperar justo eso reintenta demasiado
        # pronto y agota los intentos mientras el cluster sigue laggeado. En la
        # corrida real se perdieron asi 24 fichas, entre ellas Picasso,
        # Cruz-Diez y Grete Stern. Se espera con margen sobre el lag.
        if retry_after is not None:
            retry_after = max(MIN_MAXLAG_WAIT, retry_after * MAXLAG_WAIT_FACTOR)
        return TransientWikidataError(text, retry_after=retry_after)
    return WikidataAPIError(text)


def fetch_json_with_retry(
    url: str,
    *,
    timeout: float,
    retries: int,
    backoff: float,
    opener: OpenFn = urllib.request.urlopen,
    sleep_fn: SleepFn = time.sleep,
    user_agent: str = USER_AGENT,
) -> JsonObject:
    """GET JSON con timeout, User-Agent y backoff exponencial.

    ``retries`` es el número de intentos adicionales al primero. Solo se
    reintentan 429/5xx, fallos de transporte, timeouts, JSON truncado y errores
    transitorios declarados por la propia API.
    """

    if timeout <= 0:
        raise ValueError("timeout debe ser mayor que cero")
    if retries < 0:
        raise ValueError("retries no puede ser negativo")
    if backoff < 0:
        raise ValueError("backoff no puede ser negativo")

    for attempt in range(retries + 1):
        retry_after: float | None = None
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": user_agent, "Accept": "application/json"},
            )
            with opener(request, timeout=timeout) as response:
                body = response.read()
            payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, dict):
                raise WikidataAPIError("Wikidata devolvió JSON que no es un objeto")
            api_exc = _api_error(payload)
            if api_exc:
                raise api_exc
            return payload
        except urllib.error.HTTPError as exc:
            if exc.code != 429 and not 500 <= exc.code < 600:
                raise WikidataAPIError(f"Wikidata HTTP {exc.code}") from exc
            retry_after = _retry_after_seconds(exc)
            caught: BaseException = exc
        except TransientWikidataError as exc:
            retry_after = exc.retry_after
            caught = exc
        except (
            urllib.error.URLError,
            TimeoutError,
            socket.timeout,
            ConnectionError,
            OSError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as exc:
            caught = exc
        except WikidataAPIError:
            raise

        if attempt >= retries:
            raise WikidataAPIError(
                f"Wikidata falló tras {attempt + 1} intentos: "
                f"{type(caught).__name__}: {caught}"
            ) from caught
        delay = retry_after if retry_after is not None else backoff * (2**attempt)
        sleep_fn(min(120.0, max(0.0, delay)))

    raise AssertionError("bucle de reintentos inalcanzable")


class WikidataClient:
    """Cliente pequeño de la Action API oficial de Wikidata."""

    def __init__(
        self,
        *,
        cache: JsonlResponseCache,
        timeout: float = 20.0,
        retries: int = 3,
        backoff: float = 1.0,
        request_sleep: float = 0.25,
        search_languages: Sequence[str] = ("es", "en"),
        opener: OpenFn = urllib.request.urlopen,
        sleep_fn: SleepFn = time.sleep,
    ):
        if request_sleep < 0:
            raise ValueError("sleep no puede ser negativo")
        self.cache = cache
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.request_sleep = request_sleep
        self.search_languages = tuple(search_languages)
        self.opener = opener
        self.sleep_fn = sleep_fn

    def call(self, **params: Any) -> JsonObject:
        full_params = {
            "format": "json",
            "formatversion": 2,
            # maxlag alto a proposito: esto es lectura por lotes, no una
            # escritura interactiva. Con maxlag=5 el cluster rebotaba las
            # consultas en cuanto se retrasaba unos segundos y se perdieron
            # 135 fichas por ese motivo, entre ellas Picasso y Cruz-Diez.
            # Wikimedia recomienda un valor asi para trabajo no interactivo.
            "maxlag": 20,
            **params,
        }
        query = urllib.parse.urlencode(sorted(full_params.items()), doseq=True)
        url = f"{WIKIDATA_API}?{query}"
        cached = self.cache.get(url)
        if cached is not None:
            return cached
        payload = fetch_json_with_retry(
            url,
            timeout=self.timeout,
            retries=self.retries,
            backoff=self.backoff,
            opener=self.opener,
            sleep_fn=self.sleep_fn,
        )
        self.cache.put(url, payload)
        if self.request_sleep:
            self.sleep_fn(self.request_sleep)
        return payload

    def search(self, name: str) -> list[str]:
        """Busca items en español/inglés; el match exacto se valida después.

        Se consumen las páginas de ``search-continue`` para no declarar un
        match único cuando hay otro homónimo después de los primeros 50. Una
        consulta con más de 500 resultados por idioma se considera demasiado
        amplia y se registra como error, nunca como match inseguro.
        """

        qids: list[str] = []
        seen: set[str] = set()
        for language in self.search_languages:
            offset = 0
            retrieved = 0
            while True:
                params: JsonObject = {
                    "action": "wbsearchentities",
                    "search": name,
                    "language": language,
                    "uselang": language,
                    "type": "item",
                    "limit": 50,
                }
                if offset:
                    params["continue"] = offset
                payload = self.call(**params)
                results = payload.get("search")
                if not isinstance(results, list):
                    raise WikidataAPIError(
                        "wbsearchentities no devolvió una lista search"
                    )
                retrieved += len(results)
                for result in results:
                    qid = result.get("id") if isinstance(result, Mapping) else None
                    if (
                        isinstance(qid, str)
                        and _QID_RE.fullmatch(qid)
                        and qid not in seen
                    ):
                        seen.add(qid)
                        qids.append(qid)

                continuation = payload.get("search-continue")
                if continuation is None:
                    break
                if retrieved >= MAX_SEARCH_RESULTS_PER_LANGUAGE:
                    raise WikidataAPIError(
                        f"Búsqueda demasiado amplia para {name!r} en {language}: "
                        f">={MAX_SEARCH_RESULTS_PER_LANGUAGE} resultados"
                    )
                try:
                    next_offset = int(continuation)
                except (TypeError, ValueError) as exc:
                    raise WikidataAPIError(
                        "wbsearchentities devolvió search-continue inválido"
                    ) from exc
                if next_offset <= offset:
                    raise WikidataAPIError(
                        "wbsearchentities no avanzó su search-continue"
                    )
                offset = next_offset
        return qids

    def get_entities(
        self,
        qids: Iterable[str],
        *,
        props: Sequence[str] = ("labels", "aliases", "claims"),
    ) -> dict[str, JsonObject]:
        """Descarga entidades en lotes de 50, el máximo seguro de la API."""

        unique = sorted({qid for qid in qids if _QID_RE.fullmatch(qid)})
        entities: dict[str, JsonObject] = {}
        for start in range(0, len(unique), 50):
            batch = unique[start : start + 50]
            payload = self.call(
                action="wbgetentities",
                ids="|".join(batch),
                props="|".join(props),
                redirects="yes",
            )
            raw_entities = payload.get("entities")
            if isinstance(raw_entities, Mapping):
                iterator = raw_entities.items()
            elif isinstance(raw_entities, list):
                iterator = (
                    (str(entity.get("id")), entity)
                    for entity in raw_entities
                    if isinstance(entity, Mapping)
                )
            else:
                raise WikidataAPIError("wbgetentities no devolvió entities")
            for qid, entity in iterator:
                if isinstance(entity, dict) and not entity.get("missing"):
                    canonical_id = entity.get("id")
                    key = canonical_id if isinstance(canonical_id, str) else str(qid)
                    entities[key] = entity
                    # La forma v1 usa el QID solicitado como key aunque ``id``
                    # ya sea el destino canónico de un redirect.
                    entities[str(qid)] = entity

            redirects = payload.get("redirects")
            if isinstance(redirects, list):
                for redirect in redirects:
                    if not isinstance(redirect, Mapping):
                        continue
                    old = redirect.get("from")
                    new = redirect.get("to")
                    if isinstance(old, str) and isinstance(new, str) and new in entities:
                        entities[old] = entities[new]
        return entities


def _text_values(bucket: Any) -> list[str]:
    values: list[str] = []
    if not isinstance(bucket, Mapping):
        return values
    for language_values in bucket.values():
        if isinstance(language_values, Mapping):
            language_values = [language_values]
        if not isinstance(language_values, list):
            continue
        for item in language_values:
            value = item.get("value") if isinstance(item, Mapping) else None
            if isinstance(value, str) and value.strip():
                values.append(value.strip())
    return values


def entity_names(entity: Mapping[str, Any]) -> list[str]:
    """Todos los labels y aliases de una entidad, sin perder idiomas."""

    names = _text_values(entity.get("labels")) + _text_values(entity.get("aliases"))
    return list(dict.fromkeys(names))


def _statement_values(
    entity: Mapping[str, Any], prop: str, *, include_deprecated: bool = False
) -> list[Any]:
    claims = entity.get("claims")
    statements = claims.get(prop) if isinstance(claims, Mapping) else None
    if not isinstance(statements, list):
        return []
    values: list[Any] = []
    for statement in statements:
        if not isinstance(statement, Mapping):
            continue
        if not include_deprecated and statement.get("rank") == "deprecated":
            continue
        snak = statement.get("mainsnak")
        if not isinstance(snak, Mapping) or snak.get("snaktype") not in (None, "value"):
            continue
        datavalue = snak.get("datavalue")
        if isinstance(datavalue, Mapping) and "value" in datavalue:
            values.append(datavalue["value"])
    return values


def _item_ids(entity: Mapping[str, Any], prop: str) -> list[str]:
    qids: list[str] = []
    for value in _statement_values(entity, prop):
        qid = value.get("id") if isinstance(value, Mapping) else None
        if isinstance(qid, str) and _QID_RE.fullmatch(qid) and qid not in qids:
            qids.append(qid)
    return qids


def is_human(entity: Mapping[str, Any]) -> bool:
    return HUMAN_QID in _item_ids(entity, "P31")


def _preferred_label(entity: Mapping[str, Any], fallback: str) -> str:
    labels = entity.get("labels")
    if isinstance(labels, Mapping):
        for language in ("es", "en"):
            item = labels.get(language)
            value = item.get("value") if isinstance(item, Mapping) else None
            if isinstance(value, str) and value.strip():
                return value.strip()
    names = _text_values(labels)
    return names[0] if names else fallback


def _source_names(row: Mapping[str, Any]) -> list[dict[str, str]]:
    raw_names: list[Any] = [
        row.get("display_name"),
        row.get("artist_name"),
        row.get("name"),
    ]
    aliases = row.get("aliases")
    if isinstance(aliases, list):
        raw_names.extend(aliases)

    names: list[dict[str, str]] = []
    seen_values: set[str] = set()
    for raw in raw_names:
        if not isinstance(raw, str) or not raw.strip():
            continue
        value = raw.strip()
        fold = artist_fold(value)
        # Dos grafías pueden compartir fold pero producir resultados de
        # búsqueda distintos; se consultan ambas y se valida luego por fold.
        value_key = value.casefold()
        if fold and value_key not in seen_values:
            seen_values.add(value_key)
            names.append({"value": value, "fold": fold})
    return names


def _research_key(row: Mapping[str, Any]) -> str:
    for key in ("artist_key", "artist_id"):
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    names = _source_names(row)
    return names[0]["fold"] if names else "invalid-artist"


def input_fingerprint(row: Mapping[str, Any]) -> str:
    """Firma solo lo que puede cambiar la investigación o sus huecos."""

    material = {
        "research_key": _research_key(row),
        "names": sorted(
            (name["fold"], name["value"].casefold())
            for name in _source_names(row)
        ),
        "country_birth": row.get("country_birth"),
        "birth_year": row.get("birth_year"),
        "death_year": row.get("death_year"),
        "candidate_country_birth": row.get("candidate_country_birth"),
        "candidate_birth_year": row.get("candidate_birth_year"),
        "candidate_death_year": row.get("candidate_death_year"),
        "missing_fields": row.get("missing_fields"),
    }
    encoded = json.dumps(
        material, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def _first_metric(row: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    containers: list[Mapping[str, Any]] = [row]
    for nested_key in ("metrics", "observed_metrics", "stats"):
        nested = row.get(nested_key)
        if isinstance(nested, Mapping):
            containers.append(nested)
    for container in containers:
        for key in keys:
            number = _number(container.get(key))
            if number is not None:
                return number
    return None


def prioritized_research_rows(rows: Iterable[JsonObject]) -> list[JsonObject]:
    """Filtra el flag booleano y prioriza lots, luego revenue, establemente."""

    selected = [row for row in rows if row.get("needs_web_research") is True]

    def key(item: tuple[int, JsonObject]) -> tuple[Any, ...]:
        index, row = item
        lots = _first_metric(row, _LOTS_KEYS)
        revenue = _first_metric(row, _REVENUE_KEYS)
        return (
            lots is None,
            -(lots or 0.0),
            revenue is None,
            -(revenue or 0.0),
            index,
        )

    return [row for _, row in sorted(enumerate(selected), key=key)]


def _search_url(name: str) -> str:
    return "https://www.wikidata.org/w/index.php?" + urllib.parse.urlencode(
        {"search": name, "title": "Special:Search", "ns0": 1}
    )


def _time_claims(entity: Mapping[str, Any], prop: str) -> list[JsonObject]:
    claims: list[JsonObject] = []
    for value in _statement_values(entity, prop):
        if not isinstance(value, Mapping) or not isinstance(value.get("time"), str):
            continue
        claim: JsonObject = {"time": value["time"]}
        if isinstance(value.get("precision"), int):
            claim["precision"] = value["precision"]
        if isinstance(value.get("calendarmodel"), str):
            claim["calendar_model"] = value["calendarmodel"]
        if claim not in claims:
            claims.append(claim)
    return claims


def _linked_claims(
    entity: Mapping[str, Any],
    prop: str,
    related: Mapping[str, Mapping[str, Any]],
) -> list[JsonObject]:
    claims: list[JsonObject] = []
    for qid in _item_ids(entity, prop):
        linked = related.get(qid, {})
        claim: JsonObject = {
            "id": qid,
            "label": _preferred_label(linked, qid),
            "source_url": WIKIDATA_ENTITY_URL.format(qid=qid),
        }
        # Para el lugar de nacimiento se anota tambien su pais actual: la tabla
        # _countries.yaml solo cubre ciudades grandes, y sin esto un artista
        # nacido en Oslo o Lausana se quedaria sin pais pese a estar el dato.
        if prop == "P19":
            iso = _current_country_iso(linked, related)
            if iso:
                claim["country_iso"] = iso
        claims.append(claim)
    return claims


def _current_country_iso(
    place: Mapping[str, Any],
    related: Mapping[str, Mapping[str, Any]],
) -> str | None:
    """Pais VIGENTE de un lugar, via P17 filtrado por codigo ISO (P297).

    Wikidata lista en P17 todos los estados que gobernaron el sitio: Minsk
    declara catorce, del Rus de Kiev a Ucrania. Quedarse con el primero
    publicaria un pais desaparecido, asi que solo cuentan los que tienen ISO
    3166-1 hoy. Si aun asi queda mas de uno, devuelve None: la duda se ve.
    """
    codes: set[str] = set()
    fallback: set[str] = set()
    for qid in _item_ids(place, "P17"):
        country = related.get(qid)
        if not isinstance(country, Mapping):
            continue
        for value in _statement_values(country, "P297"):
            if isinstance(value, str) and value.strip():
                codes.add(value.strip().upper())
        # Respaldo: Wikidata marca el P297 "NL" de Paises Bajos como
        # deprecated, y descartarlo dejaba sin pais a Haarlem, La Haya y
        # Amsterdam, es decir a todos los pintores neerlandeses. Un codigo
        # deprecated es peor que uno vigente pero mucho mejor que ninguno.
        # Solo se mira si el pais no aporto ningun codigo normal, para no
        # reintroducir la URSS por la puerta de atras.
        if not codes:
            for value in _statement_values(country, "P297", include_deprecated=True):
                if isinstance(value, str) and value.strip():
                    fallback.add(value.strip().upper())
    chosen = codes or fallback
    return next(iter(chosen)) if len(chosen) == 1 else None


def _year_from_claim(claim: Mapping[str, Any]) -> int | None:
    precision = claim.get("precision")
    # Precision 9 = año; valores más precisos también fijan el año.
    if not isinstance(precision, int) or precision < 9:
        return None
    raw = claim.get("time")
    match = _WIKIDATA_TIME_RE.match(raw) if isinstance(raw, str) else None
    if not match:
        return None
    year = int(match.group(2))
    return -year if match.group(1) == "-" else year


def _single_year(claims: Sequence[Mapping[str, Any]]) -> int | None:
    years = {_year_from_claim(claim) for claim in claims}
    years.discard(None)
    return next(iter(years)) if len(years) == 1 else None


def _entity_evidence(
    qid: str,
    entity: Mapping[str, Any],
    source_folds: set[str],
    related: Mapping[str, Mapping[str, Any]],
) -> JsonObject:
    matched_names = []
    matched_folds: set[str] = set()
    for name in entity_names(entity):
        fold = artist_fold(name)
        if fold and fold in source_folds:
            matched_names.append(name)
            matched_folds.add(fold)

    claims = {
        "P569": _time_claims(entity, "P569"),
        "P570": _time_claims(entity, "P570"),
        "P19": _linked_claims(entity, "P19", related),
        "P106": _linked_claims(entity, "P106", related),
    }
    proposal: JsonObject = {
        "display_name": _preferred_label(entity, qid),
        "birth_places": claims["P19"],
        "occupations": claims["P106"],
    }
    birth_year = _single_year(claims["P569"])
    death_year = _single_year(claims["P570"])
    if birth_year is not None:
        proposal["birth_year"] = birth_year
    if death_year is not None:
        proposal["death_year"] = death_year

    return {
        "wikidata_id": qid,
        "source_url": WIKIDATA_ENTITY_URL.format(qid=qid),
        "label": _preferred_label(entity, qid),
        "human_q5": True,
        "matched_names": list(dict.fromkeys(matched_names)),
        "matched_folds": sorted(matched_folds),
        "claims": claims,
        "proposal": proposal,
    }


def _base_result(row: Mapping[str, Any], names: list[dict[str, str]]) -> JsonObject:
    return {
        "schema_version": 1,
        "researched_at": utc_now(),
        "research_key": _research_key(row),
        "input_fingerprint": input_fingerprint(row),
        "artist_key": row.get("artist_key"),
        "artist_id": row.get("artist_id"),
        "display_name": row.get("display_name"),
        "aliases": row.get("aliases") if isinstance(row.get("aliases"), list) else [],
        "curation_status": row.get("curation_status"),
        "entity_type": row.get("entity_type"),
        "houses": row.get("houses") if isinstance(row.get("houses"), list) else [],
        "quality_flags": (
            row.get("quality_flags")
            if isinstance(row.get("quality_flags"), list)
            else []
        ),
        "missing_fields": (
            row.get("missing_fields")
            if isinstance(row.get("missing_fields"), list)
            else []
        ),
        "master_context": {
            key: row.get(key)
            for key in (
                "country_birth",
                "birth_year",
                "death_year",
                "candidate_country_birth",
                "candidate_birth_year",
                "candidate_death_year",
            )
            if row.get(key) is not None
        },
        "priority_metrics": {
            "lots": _first_metric(row, _LOTS_KEYS),
            "revenue": _first_metric(row, _REVENUE_KEYS),
        },
        "source_names": names,
        "source": "wikidata",
        "match_policy": "artist_fold_exact+P31_Q5",
        "review_required": True,
        "auto_promote": False,
    }


def research_artist(row: Mapping[str, Any], client: Any) -> JsonObject:
    """Investiga una fila. El cliente se inyecta para pruebas sin red."""

    names = _source_names(row)
    base = _base_result(row, names)
    if not names:
        return {
            **base,
            "status": "error",
            "source_url": WIKIDATA_API,
            "error": {
                "type": "invalid_input",
                "message": "No hay display_name/alias válido bajo artist_fold",
            },
        }

    source_folds = {name["fold"] for name in names}
    candidate_qids: list[str] = []
    try:
        for name in names:
            for qid in client.search(name["value"]):
                if qid not in candidate_qids:
                    candidate_qids.append(qid)
        entities = client.get_entities(candidate_qids)

        accepted: list[tuple[str, JsonObject]] = []
        accepted_qids: set[str] = set()
        rejected: list[JsonObject] = []
        for qid in candidate_qids:
            entity = entities.get(qid)
            if not isinstance(entity, Mapping):
                continue
            matching_names = [
                name
                for name in entity_names(entity)
                if (fold := artist_fold(name)) and fold in source_folds
            ]
            if not matching_names:
                continue
            if not is_human(entity):
                rejected.append(
                    {
                        "wikidata_id": qid,
                        "source_url": WIKIDATA_ENTITY_URL.format(qid=qid),
                        "matched_names": list(dict.fromkeys(matching_names)),
                        "reason": "not_q5_human",
                    }
                )
                continue
            canonical_qid = entity.get("id")
            if not isinstance(canonical_qid, str) or not _QID_RE.fullmatch(canonical_qid):
                canonical_qid = qid
            if canonical_qid not in accepted_qids:
                accepted_qids.add(canonical_qid)
                accepted.append((canonical_qid, dict(entity)))

        related_qids: set[str] = set()
        for _, entity in accepted:
            related_qids.update(_item_ids(entity, "P19"))
            related_qids.update(_item_ids(entity, "P106"))
        # Se piden con claims, no solo labels, porque del lugar de nacimiento
        # hace falta su P17 para resolver el pais.
        related = (
            client.get_entities(related_qids, props=("labels", "claims"))
            if related_qids
            else {}
        )
        # Segundo salto: los paises que declaran esos lugares, para leer su
        # P297 y descartar los estados historicos sin ISO vigente.
        country_qids: set[str] = set()
        for place in related.values():
            if isinstance(place, Mapping):
                country_qids.update(_item_ids(place, "P17"))
        country_qids -= set(related)
        if country_qids:
            related = {
                **related,
                **client.get_entities(country_qids, props=("labels", "claims")),
            }
        evidence = [
            _entity_evidence(qid, entity, source_folds, related)
            for qid, entity in accepted
        ]

        if len(evidence) == 1:
            match = evidence[0]
            return {
                **base,
                "status": "matched",
                "source_url": match["source_url"],
                "wikidata_id": match["wikidata_id"],
                "match": match,
                "rejected_candidates": rejected,
            }
        search_url = _search_url(names[0]["value"])
        if len(evidence) > 1:
            return {
                **base,
                "status": "ambiguous",
                "source_url": search_url,
                "candidates": evidence,
                "rejected_candidates": rejected,
            }
        return {
            **base,
            "status": "not_found",
            "source_url": search_url,
            "rejected_candidates": rejected,
        }
    except Exception as exc:  # aislamiento por artista; la corrida debe continuar
        return {
            **base,
            "status": "error",
            "source_url": WIKIDATA_API,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc)[:500],
            },
        }


def completed_fingerprints(
    output_path: Path, *, retry_errors: bool = False
) -> set[str]:
    if not output_path.exists():
        return set()
    latest_status: dict[str, str] = {}
    for row in iter_jsonl(output_path, tolerate_bad_lines=True):
        fingerprint = row.get("input_fingerprint")
        status = row.get("status")
        if (
            isinstance(fingerprint, str)
            and status in {"matched", "ambiguous", "not_found", "error"}
        ):
            latest_status[fingerprint] = status
    return {
        fingerprint
        for fingerprint, status in latest_status.items()
        if not (retry_errors and status == "error")
    }


def run_research(
    *,
    input_path: Path,
    output_path: Path,
    client: Any,
    limit: int | None = None,
    retry_errors: bool = False,
) -> Counter[str]:
    """Procesa candidatos pendientes y devuelve conteos por estado."""

    if not input_path.exists():
        raise FileNotFoundError(f"No existe la dimensión de entrada: {input_path}")
    if input_path.resolve() == output_path.resolve():
        raise ValueError("input y output deben ser ficheros distintos")
    if limit is not None and limit < 0:
        raise ValueError("limit no puede ser negativo")

    done = completed_fingerprints(output_path, retry_errors=retry_errors)
    rows = prioritized_research_rows(iter_jsonl(input_path))
    pending_all: list[JsonObject] = []
    seen_pending: set[str] = set()
    already_completed = 0
    duplicates_skipped = 0
    for row in rows:
        fingerprint = input_fingerprint(row)
        if fingerprint in done:
            already_completed += 1
        elif fingerprint in seen_pending:
            duplicates_skipped += 1
        else:
            seen_pending.add(fingerprint)
            pending_all.append(row)
    pending = pending_all
    if limit is not None:
        pending = pending[:limit]

    counts: Counter[str] = Counter()
    for row in pending:
        result = research_artist(row, client)
        append_jsonl(output_path, result)
        counts[str(result["status"])] += 1
        print(
            f"{result['status']:>10}  {result['research_key']}  "
            f"{result.get('display_name') or ''}"
        )
    counts["selected"] = len(rows)
    counts["already_completed"] = already_completed
    counts["duplicates_skipped"] = duplicates_skipped
    counts["deferred_by_limit"] = len(pending_all) - len(pending)
    counts["processed"] = len(pending)
    return counts


def _non_negative_int(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("debe ser >= 0")
    return value


def _non_negative_float(text: str) -> float:
    value = float(text)
    if value < 0:
        raise argparse.ArgumentTypeError("debe ser >= 0")
    return value


def _positive_float(text: str) -> float:
    value = float(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("debe ser > 0")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Investiga en Wikidata los artistas marcados needs_web_research. "
            "Solo escribe propuestas para revisión; nunca modifica el maestro."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument(
        "--limit",
        type=_non_negative_int,
        help="Máximo de artistas pendientes a procesar (0 no procesa ninguno).",
    )
    parser.add_argument(
        "--sleep",
        type=_non_negative_float,
        default=0.25,
        help="Pausa en segundos después de cada consulta HTTP no cacheada.",
    )
    parser.add_argument("--timeout", type=_positive_float, default=20.0)
    parser.add_argument(
        "--retries",
        type=_non_negative_int,
        default=3,
        help="Reintentos adicionales por consulta (por defecto 3).",
    )
    parser.add_argument("--backoff", type=_non_negative_float, default=1.0)
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="Reprocesa fingerprints cuyo último resultado fue error.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    resolved = {args.input.resolve(), args.output.resolve(), args.cache.resolve()}
    if len(resolved) != 3:
        raise SystemExit("--input, --output y --cache deben ser ficheros distintos")

    cache = JsonlResponseCache(args.cache)
    client = WikidataClient(
        cache=cache,
        timeout=args.timeout,
        retries=args.retries,
        backoff=args.backoff,
        request_sleep=args.sleep,
    )
    try:
        counts = run_research(
            input_path=args.input,
            output_path=args.output,
            client=client,
            limit=args.limit,
            retry_errors=args.retry_errors,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(
        "Resumen: "
        + ", ".join(
            f"{key}={counts[key]}"
            for key in ("processed", "matched", "ambiguous", "not_found", "error")
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
