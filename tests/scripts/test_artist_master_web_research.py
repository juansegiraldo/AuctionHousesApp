"""Pruebas sin red de scripts/artist_master_web_research.py."""

import importlib.util
import json
import urllib.error
import urllib.parse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "artist_master_web_research",
    ROOT / "scripts" / "artist_master_web_research.py",
)
research = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(research)


def _item_statement(qid):
    return {
        "rank": "normal",
        "mainsnak": {
            "snaktype": "value",
            "datavalue": {"value": {"entity-type": "item", "id": qid}},
        },
    }


def _time_statement(value, precision=11):
    return {
        "rank": "normal",
        "mainsnak": {
            "snaktype": "value",
            "datavalue": {
                "value": {
                    "time": value,
                    "precision": precision,
                    "calendarmodel": "http://www.wikidata.org/entity/Q1985727",
                }
            },
        },
    }


def _entity(qid, label, *, human=True, aliases=(), claims=None):
    entity_claims = dict(claims or {})
    entity_claims.setdefault("P31", [_item_statement("Q5" if human else "Q43229")])
    return {
        "id": qid,
        "labels": {"es": {"language": "es", "value": label}},
        "aliases": {
            "es": [
                {"language": "es", "value": alias}
                for alias in aliases
            ]
        },
        "claims": entity_claims,
    }


class FakeClient:
    def __init__(self, searches, entities):
        self.searches = searches
        self.entities = entities
        self.search_calls = []
        self.entity_calls = []

    def search(self, name):
        self.search_calls.append(name)
        value = self.searches.get(name, [])
        if isinstance(value, Exception):
            raise value
        return list(value)

    def get_entities(self, qids, *, props=("labels", "aliases", "claims")):
        qids = list(qids)
        self.entity_calls.append((set(qids), tuple(props)))
        return {qid: self.entities[qid] for qid in qids if qid in self.entities}


def _row(**updates):
    row = {
        "artist_key": "artist:fernando_botero",
        "artist_id": "fernando_botero",
        "display_name": "Fernándo Botero",
        "aliases": ["F. Botero"],
        "needs_web_research": True,
        "lots_observed": 30,
        "missing_fields": ["birth_year", "death_year", "country_birth"],
    }
    row.update(updates)
    return row


def test_only_flagged_rows_are_prioritized_by_lots_then_revenue():
    rows = [
        _row(artist_key="none", display_name="No Flag", needs_web_research=False),
        _row(artist_key="revenue-low", display_name="Revenue Low", lots_observed=None,
             revenue_eur=10),
        _row(artist_key="lots-2-low", display_name="Lots 2 Low", lots_observed=2,
             revenue_eur=10),
        _row(artist_key="lots-2-high", display_name="Lots 2 High", lots_observed=2,
             revenue_eur=100),
        _row(artist_key="revenue-high", display_name="Revenue High", lots_observed=None,
             revenue_eur=999),
    ]

    got = research.prioritized_research_rows(rows)

    assert [row["artist_key"] for row in got] == [
        "lots-2-high",
        "lots-2-low",
        "revenue-high",
        "revenue-low",
    ]


def test_exact_folded_human_match_records_required_claims_and_proposal():
    artist = _entity(
        "Q123",
        "Fernando Botero",
        aliases=("Botero",),
        claims={
            "P569": [_time_statement("+1932-04-19T00:00:00Z")],
            "P570": [_time_statement("+2023-09-15T00:00:00Z")],
            "P19": [_item_statement("Q65")],
            "P106": [_item_statement("Q1028181")],
        },
    )
    place = _entity("Q65", "Medellín", claims={})
    occupation = _entity("Q1028181", "pintor", claims={})
    client = FakeClient(
        {"Fernándo Botero": ["Q123"], "F. Botero": []},
        {"Q123": artist, "Q65": place, "Q1028181": occupation},
    )

    result = research.research_artist(_row(), client)

    assert result["status"] == "matched"
    assert result["wikidata_id"] == "Q123"
    assert result["source_url"] == "https://www.wikidata.org/wiki/Q123"
    assert result["review_required"] is True
    assert result["auto_promote"] is False
    assert result["match_policy"] == "artist_fold_exact+P31_Q5"
    assert result["match"]["human_q5"] is True
    assert set(result["match"]["claims"]) == {"P569", "P570", "P19", "P106"}
    assert result["match"]["claims"]["P19"][0]["label"] == "Medellín"
    assert result["match"]["claims"]["P106"][0]["id"] == "Q1028181"
    assert result["match"]["proposal"]["birth_year"] == 1932
    assert result["match"]["proposal"]["death_year"] == 2023
    # La tilde distinta sigue siendo igualdad exacta bajo el artist_fold canónico.
    assert "Fernando Botero" in result["match"]["matched_names"]


def test_same_fold_spelling_variants_are_both_searched():
    row = _row(
        display_name="Fernándo Botero",
        aliases=["Fernando Botero"],
    )
    client = FakeClient(
        {"Fernándo Botero": [], "Fernando Botero": ["Q123"]},
        {"Q123": _entity("Q123", "Fernando Botero")},
    )

    result = research.research_artist(row, client)

    assert result["status"] == "matched"
    assert client.search_calls == ["Fernándo Botero", "Fernando Botero"]


def test_two_exact_human_matches_are_ambiguous_without_occupation_tiebreak():
    first = _entity(
        "Q1",
        "Francisco Toledo",
        claims={"P106": [_item_statement("Q1028181")]},
    )
    second = _entity(
        "Q2",
        "Francisco Toledo",
        claims={"P106": [_item_statement("Q49757")]},
    )
    entities = {
        "Q1": first,
        "Q2": second,
        "Q1028181": _entity("Q1028181", "pintor"),
        "Q49757": _entity("Q49757", "poeta"),
    }
    row = _row(
        artist_key="artist:francisco_toledo",
        display_name="Francisco Toledo",
        aliases=[],
    )
    client = FakeClient({"Francisco Toledo": ["Q1", "Q2"]}, entities)

    result = research.research_artist(row, client)

    assert result["status"] == "ambiguous"
    assert {candidate["wikidata_id"] for candidate in result["candidates"]} == {
        "Q1",
        "Q2",
    }
    assert all(set(candidate["claims"]) == set(research.RECORDED_PROPERTIES)
               for candidate in result["candidates"])


def test_exact_nonhuman_is_rejected_and_reported_as_not_found():
    entity = _entity("Q9", "Taller Azul", human=False)
    row = _row(display_name="Taller Azul", aliases=[])
    client = FakeClient({"Taller Azul": ["Q9"]}, {"Q9": entity})

    result = research.research_artist(row, client)

    assert result["status"] == "not_found"
    assert result["rejected_candidates"] == [
        {
            "wikidata_id": "Q9",
            "source_url": "https://www.wikidata.org/wiki/Q9",
            "matched_names": ["Taller Azul"],
            "reason": "not_q5_human",
        }
    ]


def test_similar_but_not_exact_name_is_not_accepted():
    entity = _entity("Q7", "María Pérez García")
    row = _row(display_name="María Pérez", aliases=[])
    client = FakeClient({"María Pérez": ["Q7"]}, {"Q7": entity})

    result = research.research_artist(row, client)

    assert result["status"] == "not_found"
    assert result["rejected_candidates"] == []


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_http_fetch_sets_user_agent_timeout_and_retries_with_backoff():
    calls = []
    sleeps = []

    def opener(request, timeout):
        calls.append((request, timeout))
        if len(calls) == 1:
            raise urllib.error.URLError("temporary")
        return FakeResponse({"search": []})

    got = research.fetch_json_with_retry(
        "https://www.wikidata.org/w/api.php?action=test",
        timeout=7,
        retries=2,
        backoff=0.5,
        opener=opener,
        sleep_fn=sleeps.append,
    )

    assert got == {"search": []}
    assert len(calls) == 2
    assert calls[0][1] == 7
    assert calls[0][0].get_header("User-agent") == research.USER_AGENT
    assert sleeps == [0.5]


def test_jsonl_http_cache_avoids_a_second_network_call(tmp_path):
    calls = []
    sleeps = []

    def opener(_request, timeout):
        calls.append(timeout)
        return FakeResponse({"search": [{"id": "Q1"}]})

    cache_path = tmp_path / "cache.jsonl"
    client = research.WikidataClient(
        cache=research.JsonlResponseCache(cache_path),
        opener=opener,
        sleep_fn=sleeps.append,
        request_sleep=0.2,
        search_languages=("es",),
    )

    assert client.search("Nombre") == ["Q1"]
    assert client.search("Nombre") == ["Q1"]

    assert len(calls) == 1
    assert sleeps == [0.2]
    cache_rows = list(research.iter_jsonl(cache_path))
    assert len(cache_rows) == 1
    assert cache_rows[0]["request_url"].startswith(research.WIKIDATA_API)


def test_search_follows_continuation_so_later_homonyms_are_not_hidden():
    calls = []

    def opener(request, timeout):
        assert timeout == 20.0
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
        calls.append(query)
        if "continue" not in query:
            return FakeResponse(
                {"search": [{"id": "Q1"}], "search-continue": 1}
            )
        return FakeResponse({"search": [{"id": "Q2"}]})

    client = research.WikidataClient(
        cache=research.JsonlResponseCache(None),
        opener=opener,
        request_sleep=0,
        search_languages=("es",),
    )

    assert client.search("Nombre Común") == ["Q1", "Q2"]
    assert len(calls) == 2
    assert calls[1]["continue"] == ["1"]


def test_run_is_append_only_resumable_and_limit_applies_after_resume(tmp_path):
    input_path = tmp_path / "master.jsonl"
    output_path = tmp_path / "research.jsonl"
    done_row = _row(
        artist_key="done",
        display_name="Artista Hecho",
        aliases=[],
        lots_observed=100,
    )
    next_row = _row(
        artist_key="next",
        display_name="Artista Siguiente",
        aliases=[],
        lots_observed=50,
    )
    last_row = _row(
        artist_key="last",
        display_name="Artista Final",
        aliases=[],
        lots_observed=1,
    )
    with input_path.open("w", encoding="utf-8") as handle:
        for row in (last_row, done_row, next_row):
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    research.append_jsonl(
        output_path,
        {
            "input_fingerprint": research.input_fingerprint(done_row),
            "status": "not_found",
        },
    )
    client = FakeClient({"Artista Siguiente": []}, {})

    counts = research.run_research(
        input_path=input_path,
        output_path=output_path,
        client=client,
        limit=1,
    )

    assert counts["processed"] == 1
    assert client.search_calls == ["Artista Siguiente"]
    rows = list(research.iter_jsonl(output_path))
    assert len(rows) == 2
    assert rows[-1]["research_key"] == "next"
    # Segunda corrida: done y next se saltan; se procesa el siguiente pendiente.
    client2 = FakeClient({"Artista Final": []}, {})
    research.run_research(
        input_path=input_path,
        output_path=output_path,
        client=client2,
        limit=1,
    )
    assert client2.search_calls == ["Artista Final"]


def test_retry_errors_uses_the_latest_status_for_each_fingerprint(tmp_path):
    output_path = tmp_path / "research.jsonl"
    research.append_jsonl(
        output_path,
        {"input_fingerprint": "eventually-ok", "status": "error"},
    )
    research.append_jsonl(
        output_path,
        {"input_fingerprint": "eventually-ok", "status": "matched"},
    )
    research.append_jsonl(
        output_path,
        {"input_fingerprint": "latest-error", "status": "matched"},
    )
    research.append_jsonl(
        output_path,
        {"input_fingerprint": "latest-error", "status": "error"},
    )

    assert research.completed_fingerprints(
        output_path, retry_errors=True
    ) == {"eventually-ok"}


def test_append_after_a_truncated_line_preserves_the_new_resume_record(tmp_path):
    output_path = tmp_path / "research.jsonl"
    output_path.write_text('{"status": "mat', encoding="utf-8")

    research.append_jsonl(
        output_path,
        {"input_fingerprint": "safe", "status": "matched"},
    )

    rows = list(research.iter_jsonl(output_path, tolerate_bad_lines=True))
    assert rows == [{"input_fingerprint": "safe", "status": "matched"}]


def test_client_failure_becomes_error_evidence_instead_of_stopping_run():
    client = FakeClient(
        {"Fernándo Botero": research.WikidataAPIError("offline")},
        {},
    )

    result = research.research_artist(_row(aliases=[]), client)

    assert result["status"] == "error"
    assert result["source_url"] == research.WIKIDATA_API
    assert result["error"]["type"] == "WikidataAPIError"
    assert "offline" in result["error"]["message"]


def _iso_statement(code):
    return {
        "rank": "normal",
        "mainsnak": {
            "snaktype": "value",
            "datavalue": {"value": code},
        },
    }


def test_birth_place_records_the_country_so_small_towns_resolve():
    """Oslo no esta en _countries.yaml; su pais sale del P17 de Wikidata."""
    artist = _entity(
        "Q123",
        "Fernando Botero",
        claims={"P19": [_item_statement("Q585")], "P106": [_item_statement("Q1028181")]},
    )
    oslo = _entity("Q585", "Oslo", human=False, claims={"P17": [_item_statement("Q20")]})
    noruega = _entity("Q20", "Noruega", human=False, claims={"P297": [_iso_statement("NO")]})
    client = FakeClient(
        {"Fernándo Botero": ["Q123"], "F. Botero": []},
        {"Q123": artist, "Q585": oslo, "Q20": noruega, "Q1028181": _entity("Q1028181", "pintor", human=False)},
    )

    result = research.research_artist(_row(), client)

    assert result["match"]["proposal"]["birth_places"][0]["country_iso"] == "NO"


def test_a_city_with_historical_states_does_not_pick_a_dead_country():
    """Minsk declara Rus de Kiev, Imperio ruso, URSS... Solo cuenta el vigente."""
    artist = _entity(
        "Q123",
        "Fernando Botero",
        claims={"P19": [_item_statement("Q1899")], "P106": [_item_statement("Q1028181")]},
    )
    minsk = _entity(
        "Q1899",
        "Minsk",
        human=False,
        claims={"P17": [_item_statement("Q34266"), _item_statement("Q184")]},
    )
    imperio = _entity("Q34266", "Imperio ruso", human=False, claims={})
    bielorrusia = _entity("Q184", "Bielorrusia", human=False, claims={"P297": [_iso_statement("BY")]})
    client = FakeClient(
        {"Fernándo Botero": ["Q123"], "F. Botero": []},
        {
            "Q123": artist,
            "Q1899": minsk,
            "Q34266": imperio,
            "Q184": bielorrusia,
            "Q1028181": _entity("Q1028181", "pintor", human=False),
        },
    )

    result = research.research_artist(_row(), client)

    # El imperio no tiene ISO vigente: no compite con Bielorrusia.
    assert result["match"]["proposal"]["birth_places"][0]["country_iso"] == "BY"


def _maxlag_body(seconds):
    return {
        "error": {
            "code": "maxlag",
            "info": f"Waiting for wdqs1013: {seconds} seconds lagged.",
            "lag": seconds,
        }
    }


def test_maxlag_waits_the_minimum_wikidata_asks_for():
    """Un lag de 6s agotaba los 4 intentos en segundos y perdia la ficha.

    Picasso, Cruz-Diez y Grete Stern se marcaron 'error' asi en la corrida
    real: el servidor seguia laggeado cuando se acababan los reintentos.
    """
    sleeps = []
    calls = []

    def opener(request, timeout):
        calls.append(request)
        if len(calls) <= 2:
            return FakeResponse(_maxlag_body(6.1))
        return FakeResponse({"search": []})

    got = research.fetch_json_with_retry(
        "https://www.wikidata.org/w/api.php?action=test",
        timeout=7,
        retries=3,
        backoff=0.5,
        opener=opener,
        sleep_fn=sleeps.append,
    )

    assert got == {"search": []}
    # Se espera CON MARGEN sobre el lag: esperar justo el lag declarado
    # reintentaba mientras el cluster seguia retrasado.
    assert all(delay >= 6.1 * research.MAXLAG_WAIT_FACTOR for delay in sleeps)


def test_a_tiny_declared_lag_still_waits_the_minimum():
    """Un lag de 0.2s no justifica martillear al servidor que pide calma."""
    sleeps = []
    calls = []

    def opener(request, timeout):
        calls.append(request)
        if len(calls) == 1:
            return FakeResponse(_maxlag_body(0.2))
        return FakeResponse({"search": []})

    research.fetch_json_with_retry(
        "https://www.wikidata.org/w/api.php?action=test",
        timeout=7,
        retries=2,
        backoff=0.5,
        opener=opener,
        sleep_fn=sleeps.append,
    )

    assert sleeps == [research.MIN_MAXLAG_WAIT]


def test_a_cache_line_with_invalid_utf8_is_skipped_not_fatal(tmp_path):
    """Un corte a mitad de escritura dejaba la cache inservible.

    iter_jsonl toleraba JSON invalido pero el UnicodeDecodeError se lanzaba al
    iterar las lineas, antes de que el try lo pudiera atrapar, y la corrida
    siguiente moria al construir la cache.
    """
    path = tmp_path / "cache.jsonl"
    good = json.dumps({"cache_key": "k", "response": {"ok": True}}, ensure_ascii=False)
    with path.open("wb") as handle:
        handle.write(good.encode("utf-8") + b"\n")
        handle.write(b"\xd0\x28 truncado\n")
        handle.write(good.replace('"k"', '"k2"').encode("utf-8") + b"\n")

    rows = list(research.iter_jsonl(path, tolerate_bad_lines=True))

    assert [row["cache_key"] for row in rows] == ["k", "k2"]


def test_the_response_cache_survives_a_corrupted_line(tmp_path):
    path = tmp_path / "cache.jsonl"
    with path.open("wb") as handle:
        handle.write(b"\xff\xfe roto\n")

    cache = research.JsonlResponseCache(path)

    assert cache.get("https://example.invalid") is None


def _iso_statement_ranked(code, rank="normal"):
    return {
        "rank": rank,
        "mainsnak": {"snaktype": "value", "datavalue": {"value": code}},
    }


def test_a_deprecated_iso_code_is_used_when_there_is_no_other():
    """Wikidata marca el P297 'NL' de Paises Bajos como deprecated.

    Descartarlo dejaba a Haarlem, La Haya y Amsterdam sin pais, y con ellos a
    todos los pintores neerlandeses. Un codigo deprecated es peor que uno
    normal, pero infinitamente mejor que ningun codigo.
    """
    place = _entity("Q9920", "Haarlem", human=False, claims={"P17": [_item_statement("Q55")]})
    country = _entity(
        "Q55", "Países Bajos", human=False,
        claims={"P297": [_iso_statement_ranked("NL", rank="deprecated")]},
    )

    got = research._current_country_iso(place, {"Q55": country})

    assert got == "NL"


def test_a_normal_iso_code_wins_over_a_deprecated_one():
    """Si hay codigo vigente, el deprecated no compite: seria reintroducir
    estados historicos como la URSS por la puerta de atras."""
    place = _entity(
        "Q1899", "Minsk", human=False,
        claims={"P17": [_item_statement("Q184"), _item_statement("Q15180")]},
    )
    vigente = _entity("Q184", "Bielorrusia", human=False,
                      claims={"P297": [_iso_statement_ranked("BY")]})
    historico = _entity("Q15180", "URSS", human=False,
                        claims={"P297": [_iso_statement_ranked("SU", rank="deprecated")]})

    got = research._current_country_iso(place, {"Q184": vigente, "Q15180": historico})

    assert got == "BY"


def test_each_record_is_written_in_a_single_call(tmp_path, monkeypatch):
    """Dos procesos a la vez entrelazaban lineas y partian registros.

    La corrida de la noche del 2026-08-18 solapo dos lotes sobre el mismo
    diario y dejo 71 lineas partidas a media URL. Con el salto de linea dentro
    del mismo write, un registro no se puede cortar por la mitad.
    """
    path = tmp_path / "journal.jsonl"
    writes = []

    real_open = Path.open

    class SpyHandle:
        def __init__(self, inner):
            self.inner = inner

        def write(self, text):
            writes.append(text)
            return self.inner.write(text)

        def __getattr__(self, name):
            return getattr(self.inner, name)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.inner.__exit__(*args)

    def fake_open(self, *args, **kwargs):
        handle = real_open(self, *args, **kwargs)
        if "a" in (args[0] if args else kwargs.get("mode", "")):
            return SpyHandle(handle.__enter__())
        return handle

    monkeypatch.setattr(Path, "open", fake_open)
    research.append_jsonl(path, {"research_key": "x", "status": "matched"})

    assert len(writes) == 1
    assert writes[0].endswith("\n")
