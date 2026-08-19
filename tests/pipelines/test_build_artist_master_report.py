"""Tests del panel de seguimiento del maestro de artistas.

No tocan data/: prueban las funciones puras. El panel es un LECTOR — el agente
de fondo escribe mientras esto corre —, asi que lo que se pincha aqui es que no
invente cifras: un revenue que no se puede cruzar es un hueco, nunca un cero.
"""

import json

from pipelines.analytics.build_artist_master_report import (
    _crossed_count,
    _error_digest,
    _eta_hours,
    _evidence_counts,
    _findings,
    _health,
    _promotable,
    _rate,
    _impact_rows,
    _revenue_index,
    _snapshot_row,
    append_snapshot,
    load_snapshots,
)


def test_revenue_index_keys_by_fold_not_by_raw_name():
    # agg_artist_metrics agrupa por artist_id or artist_fold; cruzar por el
    # nombre crudo fallaria en cuanto la casa cambie una tilde.
    index = _revenue_index(
        [{"artist_key": "julio_romero_de_torres", "revenue_eur": 793450.0}]
    )
    assert index["julio_romero_de_torres"] == 793450.0


def test_impact_row_carries_revenue_when_the_fold_crosses():
    rows = _impact_rows(
        [{"artist_key": "pedro_mozos", "display_name": "Pedro Mozos",
          "lots_observed": 380, "curation_status": "needs_web", "houses": ["duran_subastas"]}],
        {"pedro_mozos": 120000.0},
    )
    assert rows[0]["revenue_eur"] == 120000.0


def test_impact_row_leaves_revenue_none_when_the_fold_is_unknown():
    # Misma disciplina que to_eur(): un dato que falta se queda en None y se
    # pinta como hueco. Un 0 aqui diria "no vendio nada", que es falso.
    rows = _impact_rows(
        [{"artist_key": "agueda de la pisa", "display_name": "Agueda de la Pisa",
          "lots_observed": 10, "curation_status": "needs_web", "houses": ["duran_subastas"]}],
        {},
    )
    assert rows[0]["revenue_eur"] is None


def test_impact_rows_are_sorted_by_lots_desc():
    rows = _impact_rows(
        [{"artist_key": "a", "display_name": "A", "lots_observed": 3,
          "curation_status": "needs_web", "houses": []},
         {"artist_key": "b", "display_name": "B", "lots_observed": 99,
          "curation_status": "needs_web", "houses": []}],
        {},
    )
    assert [r["artist_key"] for r in rows] == ["b", "a"]


def test_impact_rows_report_how_many_crossed_revenue():
    # 9.811 de 12.472 candidatos cruzan, pero los de MAS lotes son justo los que
    # no: agg_artist_metrics solo cuenta lo vendido y Duran oferta mucho que no
    # vende. Sin este contador la tabla parecia rota cuando estaba bien.
    rows = _impact_rows(
        [{"artist_key": "a", "display_name": "A", "lots_observed": 9, "houses": []},
         {"artist_key": "b", "display_name": "B", "lots_observed": 4, "houses": []}],
        {"b": 5000.0},
    )
    assert _crossed_count(rows) == 1


def test_evidence_counts_separates_auto_promote_from_review():
    # La diferencia es el corazon del loop: matched no significa promovible.
    counts = _evidence_counts([
        {"status": "matched", "auto_promote": True, "review_required": False},
        {"status": "matched", "auto_promote": False, "review_required": True},
        {"status": "ambiguous", "auto_promote": False, "review_required": True},
    ])
    assert counts["status"]["matched"] == 2
    assert counts["auto_promote"] == 1
    assert counts["review_required"] == 2


def test_evidence_counts_reports_errors_so_a_stalled_loop_is_visible():
    counts = _evidence_counts([{"status": "error", "auto_promote": False}])
    assert counts["status"]["error"] == 1


def test_error_digest_groups_by_error_type():
    # Los errores reales son de RED (getaddrinfo failed), no rate limiting.
    # Agrupar por tipo es lo que distingue "se cayo el DNS" de "nos frenaron".
    digest = _error_digest([
        {"status": "error", "display_name": "A",
         "error": {"type": "WikidataAPIError", "message": "URLError: getaddrinfo failed"}},
        {"status": "error", "display_name": "B",
         "error": {"type": "WikidataAPIError", "message": "URLError: getaddrinfo failed"}},
        {"status": "matched", "display_name": "C"},
    ])
    assert digest["total"] == 2
    assert digest["by_type"]["WikidataAPIError"] == 2


def test_error_digest_keeps_the_names_so_they_can_be_retried():
    digest = _error_digest([
        {"status": "error", "display_name": "Rene Portocarrero",
         "artist_key": "rene_portocarrero", "error": {"type": "X", "message": "m"},
         "priority_metrics": {"lots": 26.0}},
    ])
    assert digest["rows"][0]["display_name"] == "Rene Portocarrero"
    assert digest["rows"][0]["lots"] == 26.0


def test_error_digest_is_empty_when_the_loop_is_healthy():
    assert _error_digest([{"status": "matched"}])["total"] == 0


def test_rate_measures_rows_per_hour_between_snapshots():
    rate = _rate([
        {"stamped_at": "2026-08-17T12:00:00", "researched": 100},
        {"stamped_at": "2026-08-17T13:00:00", "researched": 160},
    ])
    assert rate == 60.0


def test_rate_is_none_with_a_single_measurement():
    # Sin dos puntos no hay velocidad. Inventar un 0 diria "atascado".
    assert _rate([{"stamped_at": "2026-08-17T12:00:00", "researched": 100}]) is None


def test_rate_ignores_a_snapshot_pair_with_no_elapsed_time():
    # Dos ejecuciones en el mismo segundo dividirian por cero.
    pair = [
        {"stamped_at": "2026-08-17T12:00:00", "researched": 100},
        {"stamped_at": "2026-08-17T12:00:00", "researched": 100},
    ]
    assert _rate(pair) is None


def test_eta_hours_uses_the_measured_rate():
    assert _eta_hours(pending=120, rate=60.0) == 2.0


def test_eta_is_none_when_the_loop_is_not_moving():
    assert _eta_hours(pending=120, rate=0.0) is None


def _matched(name, iso, occupation, lots=10, had_country=None):
    return {
        "status": "matched", "display_name": name, "artist_key": name.lower(),
        "wikidata_id": "Q1", "priority_metrics": {"lots": lots},
        "master_context": {"country_birth": had_country},
        "match": {"claims": {
            "P19": [{"label": "x", "country_iso": iso}] if iso else [],
            "P106": [{"label": occupation}],
            "P569": [{"time": "+1900-01-01T00:00:00Z"}],
        }},
    }


def test_findings_keep_only_artists():
    # "Francisco Rodriguez Martin, futbolista" es un homonimo mal casado: mismo
    # nombre, persona distinta. Ensenarlo como hallazgo seria presumir de error.
    found = _findings([
        _matched("Casimiro Sainz", "ES", "pintor"),
        _matched("Damian Diaz", "AR", "futbolista"),
    ])
    assert [f["name"] for f in found] == ["Casimiro Sainz"]


def test_findings_skip_artists_that_already_had_a_country():
    # El hallazgo es el pais que NO teniamos. Uno ya conocido no es noticia.
    found = _findings([_matched("Joaquin Sorolla", "ES", "pintor", had_country="ES")])
    assert found == []


def test_findings_are_sorted_by_lots():
    found = _findings([
        _matched("Poco", "ES", "pintor", lots=2),
        _matched("Mucho", "ES", "pintor", lots=90),
    ])
    assert [f["name"] for f in found] == ["Mucho", "Poco"]


def test_findings_carry_the_country_and_the_wikidata_link():
    found = _findings([_matched("Casimiro Sainz", "ES", "pintor")])
    assert found[0]["country"] == "ES"
    assert "wikidata.org" in found[0]["url"]


def test_promotable_agrees_with_the_promoter():
    # LA prueba que importa: el panel y scripts/artist_master_promote.py deben
    # decir el mismo numero. Reimplementar su criterio aqui daba 627 frente a
    # sus 826, y dos respuestas a la misma pregunta es peor que una.
    from scripts.artist_master_promote import build_entries

    rows = [
        _matched("Casimiro Sainz", "ES", "pintor"),
        _matched("Damian Diaz", "AR", "futbolista"),
        {"status": "ambiguous", "display_name": "Dos Sauras"},
    ]
    entries, _ = build_entries(iter(rows))
    assert _promotable(rows) == len(entries)


def test_promotable_ignores_the_auto_promote_flag():
    # auto_promote es un literal False en TODAS las filas del investigador
    # (lineas 816-817 de artist_master_web_research.py). Leerlo hacia que el
    # panel dijese "0 promovibles" con cientos de fichas esperando.
    rows = [_matched("Casimiro Sainz", "ES", "pintor")]
    con_flag = _promotable(rows)
    rows[0]["auto_promote"] = True
    assert _promotable(rows) == con_flag


def test_promotable_survives_without_the_promoter():
    # El panel es un lector: si el promotor no se puede importar, degrada a su
    # propio recuento en vez de reventar.
    assert _promotable([_matched("Casimiro Sainz", "ES", "pintor")]) >= 0


def test_health_is_green_when_it_advances_without_errors():
    assert _health(rate=700.0, error_pct=2.0)["level"] == "ok"


def test_health_is_red_when_it_stopped():
    assert _health(rate=0.0, error_pct=2.0)["level"] == "bad"


def test_health_warns_when_errors_spike():
    # El episodio real: dos procesos en paralelo dispararon los errores al 25%.
    assert _health(rate=700.0, error_pct=25.0)["level"] == "warn"


def test_health_is_unknown_without_a_measured_rate():
    assert _health(rate=None, error_pct=2.0)["level"] == "unknown"


def test_snapshot_append_keeps_previous_rows(tmp_path):
    path = tmp_path / "snapshots.jsonl"
    append_snapshot(path, {"researched": 10})
    append_snapshot(path, {"researched": 25})
    rows = load_snapshots(path)
    assert [r["researched"] for r in rows] == [10, 25]


def test_snapshot_row_stamps_the_counters_of_the_moment():
    row = _snapshot_row(
        coverage={"author_folds": 12961, "curation_status_counts": {"needs_web": 12127},
                  "disposition_counts": {"master": 1488}, "pending_identity_rows": 11473,
                  "curated_master_rows": 1086},
        evidence={"status": {"matched": 101}, "auto_promote": 40, "review_required": 60},
        stamped_at="2026-08-17T14:00:00",
    )
    assert row["matched"] == 101
    assert row["curated_master_rows"] == 1086
    assert row["stamped_at"] == "2026-08-17T14:00:00"


def test_load_snapshots_survives_a_half_written_line(tmp_path):
    # El fichero es append-only y se lee mientras el loop corre: una linea a
    # medio escribir no puede tumbar el informe.
    path = tmp_path / "snapshots.jsonl"
    path.write_text(json.dumps({"researched": 1}) + "\n{\"researched\":", encoding="utf-8")
    assert [r["researched"] for r in load_snapshots(path)] == [1]


def test_a_corrupted_journal_line_does_not_take_down_the_panel(tmp_path):
    """El panel es un LECTOR en caliente y no puede caerse por una linea rota.

    Una corrida solapada dejo 71 lineas partidas en el diario y el panel dejo
    de generarse: abria el fichero en modo texto, asi que el UnicodeDecodeError
    saltaba al ITERAR, antes del try que ya existia para tolerarlas. Es el
    mismo fallo que mordio en la cache HTTP y en el promotor.
    """
    from pipelines.analytics.build_artist_master_report import _read_jsonl

    path = tmp_path / "research.jsonl"
    good = json.dumps({"research_key": "ok", "status": "matched"}, ensure_ascii=False)
    with path.open("wb") as handle:
        handle.write(good.encode("utf-8") + b"\n")
        handle.write(b"\xb3 basura binaria a medio escribir\n")
        handle.write(b'{"research_key": "trunc", "stat\n')
        handle.write(good.replace('"ok"', '"ok2"').encode("utf-8") + b"\n")

    rows = _read_jsonl(path)

    assert [row["research_key"] for row in rows] == ["ok", "ok2"]
