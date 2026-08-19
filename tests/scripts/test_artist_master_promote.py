"""Pruebas del promotor de evidencia Wikidata al maestro de artistas.

El promotor es la unica pieza que convierte el diario de investigacion en
altas del YAML curado, asi que aqui se fijan las reglas que impiden que la
prisa por llegar al 100% meta basura en el maestro:

  - solo se promueve status=matched; ambiguous/not_found/error nunca
  - el pais sale del lugar de NACIMIENTO (P19), nunca de la casa ni del mercado
  - un lugar que no resuelve a ISO no inventa pais: se queda el hueco
  - una ocupacion que no es artistica no entra (escritores, futbolistas)
  - nunca se pisa un valor ya curado a mano
  - la URL de Wikidata queda en notes, que es la convencion de evidencia
"""

import importlib.util
import json
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "artist_master_promote",
    ROOT / "scripts" / "artist_master_promote.py",
)
promote = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(promote)


def _place(qid, label):
    return {"id": qid, "label": label, "source_url": f"https://www.wikidata.org/wiki/{qid}"}


def _result(**updates):
    """Un registro matched tipico del diario de investigacion."""
    result = {
        "status": "matched",
        "research_key": "juan_perez",
        "artist_key": "juan_perez",
        "artist_id": None,
        "display_name": "Juan Pérez",
        "aliases": ["Juan Pérez", "PÉREZ, JUAN"],
        "wikidata_id": "Q123",
        "source_url": "https://www.wikidata.org/wiki/Q123",
        "lots_observed": 12,
        "match": {
            "wikidata_id": "Q123",
            "source_url": "https://www.wikidata.org/wiki/Q123",
            "label": "Juan Pérez",
            "matched_names": ["Juan Pérez"],
            "proposal": {
                "display_name": "Juan Pérez",
                "birth_year": 1920,
                "death_year": 1992,
                "birth_places": [_place("Q1492", "Barcelona")],
                "occupations": [_place("Q1028181", "pintor")],
            },
        },
    }
    result.update(updates)
    return result


# --- Lo que se promueve -------------------------------------------------


def test_matched_human_painter_becomes_a_complete_entry():
    entries, _ = promote.build_entries([_result()])

    assert len(entries) == 1
    entry = entries[0]
    assert entry["artist_id"] == "juan_perez"
    assert entry["display_name"] == "Juan Pérez"
    assert entry["country_birth"] == "ES"
    assert entry["birth_year"] == 1920
    assert entry["death_year"] == 1992
    # "wikidata", no "llm": la identidad la afirma una fuente comprobable y la
    # ficha lleva su QID, asi que se puede auditar. Un "llm" la confundiria con
    # una conjetura de modelo, que es lo que el maestro no admite.
    assert entry["source"] == "wikidata"
    # La evidencia concreta debe viajar con la ficha, no quedarse en el diario.
    assert "https://www.wikidata.org/wiki/Q123" in entry["notes"]


def test_aliases_keep_every_catalog_spelling_so_no_lot_is_left_behind():
    entries, _ = promote.build_entries([_result()])

    aliases = entries[0]["aliases"]
    assert "Juan Pérez" in aliases
    assert "PÉREZ, JUAN" in aliases


# --- Lo que NO se promueve ----------------------------------------------


@pytest.mark.parametrize("status", ["ambiguous", "not_found", "error"])
def test_only_matched_results_are_promoted(status):
    entries, skipped = promote.build_entries([_result(status=status)])

    assert entries == []
    assert skipped[0]["reason"] == f"status_{status}"


def test_a_birthplace_that_does_not_resolve_to_iso_leaves_the_country_empty():
    """Un lugar desconocido deja hueco; jamas se cae al pais de la casa."""
    result = _result()
    result["match"]["proposal"]["birth_places"] = [_place("Q999", "Lugar Inventado")]

    entries, _ = promote.build_entries([result])

    assert entries[0]["country_birth"] is None
    assert entries[0]["nationalities"] == []
    # Un pais que falta debe verse: la ficha baja de confianza, no se rellena.
    assert entries[0]["confidence"] == "low"


def test_two_birthplaces_in_different_countries_do_not_pick_one():
    result = _result()
    result["match"]["proposal"]["birth_places"] = [
        _place("Q1492", "Barcelona"),
        _place("Q90", "París"),
    ]

    entries, _ = promote.build_entries([result])

    assert entries[0]["country_birth"] is None


def test_the_country_resolved_by_the_researcher_is_used_for_unknown_cities():
    """Lausana no esta en _countries.yaml, pero el P17 ya vino resuelto."""
    result = _result()
    place = _place("Q807", "Lausana")
    place["country_iso"] = "CH"
    result["match"]["proposal"]["birth_places"] = [place]

    entries, _ = promote.build_entries([result])

    assert entries[0]["country_birth"] == "CH"


def test_a_writer_is_not_promoted_as_an_artist():
    """El caso Garcia Marquez: 55 lotes de libros no hacen un pintor."""
    result = _result()
    result["match"]["proposal"]["occupations"] = [_place("Q36180", "escritor")]

    entries, skipped = promote.build_entries([result])

    assert entries == []
    assert skipped[0]["reason"] == "no_artistic_occupation"


def test_no_declared_occupation_is_not_evidence_against_being_an_artist():
    """Costus y José Sancha son pintores reales sin P106 en Wikidata.

    Rechazarlos por AUSENCIA de dato es descartar en silencio, justo lo que la
    regla 1 prohibe. Entran, pero con confidence low para que se revisen.
    """
    result = _result()
    result["match"]["proposal"]["occupations"] = []

    entries, _ = promote.build_entries([result])

    assert len(entries) == 1
    assert entries[0]["confidence"] == "low"
    assert "ocupacion" in entries[0]["notes"].lower()


def test_a_declared_non_artistic_occupation_still_rejects():
    """Un futbolista homonimo SI es evidencia en contra, y se descarta."""
    result = _result()
    result["match"]["proposal"]["occupations"] = [_place("Q937857", "futbolista")]

    entries, skipped = promote.build_entries([result])

    assert entries == []
    assert skipped[0]["reason"] == "no_artistic_occupation"


def _ambiguous(**updates):
    """Dos homonimos humanos con el mismo nombre, distinto anio."""
    result = _result(status="ambiguous")
    result.pop("match", None)
    result["candidates"] = [
        {
            "wikidata_id": "Q1",
            "source_url": "https://www.wikidata.org/wiki/Q1",
            "label": "Juan Pérez",
            "matched_names": ["Juan Pérez"],
            "proposal": {
                "display_name": "Juan Pérez",
                "birth_year": 1920,
                "death_year": 1992,
                "birth_places": [_place("Q1492", "Barcelona")],
                "occupations": [_place("Q1028181", "pintor")],
            },
        },
        {
            "wikidata_id": "Q2",
            "source_url": "https://www.wikidata.org/wiki/Q2",
            "label": "Juan Pérez",
            "matched_names": ["Juan Pérez"],
            "proposal": {
                "display_name": "Juan Pérez",
                "birth_year": 1855,
                "death_year": 1910,
                "birth_places": [_place("Q90", "París")],
                "occupations": [_place("Q1028181", "pintor")],
            },
        },
    ]
    result.update(updates)
    return result


def test_the_catalog_birth_year_breaks_a_two_way_ambiguity():
    """Dos homonimos y la casa publica el anio: eso desempata.

    No es una conjetura: son dos fuentes independientes concordando. El
    catalogo dice 1920 y solo uno de los dos candidatos nacio en 1920.
    """
    result = _ambiguous()
    result["master_context"] = {"candidate_birth_year": 1920}

    entries, _ = promote.build_entries([result], master={})

    assert len(entries) == 1
    assert entries[0]["birth_year"] == 1920
    assert entries[0]["country_birth"] == "ES"
    # Nunca "high": el desempate es solido pero sigue siendo un homonimo.
    assert entries[0]["confidence"] == "medium"
    assert "desempat" in entries[0]["notes"].lower()


def test_an_ambiguity_the_catalog_cannot_break_stays_out():
    """Si el anio del catalogo no casa con ninguno, sigue sin resolver."""
    result = _ambiguous()
    result["master_context"] = {"candidate_birth_year": 1700}

    entries, skipped = promote.build_entries([result], master={})

    assert entries == []
    assert skipped[0]["reason"] == "status_ambiguous"


def test_an_ambiguity_matching_two_candidates_stays_out():
    """Dos candidatos con el mismo anio no se desempatan por fecha."""
    result = _ambiguous()
    result["candidates"][1]["proposal"]["birth_year"] = 1920
    result["master_context"] = {"candidate_birth_year": 1920}

    entries, skipped = promote.build_entries([result], master={})

    assert entries == []
    assert skipped[0]["reason"] == "status_ambiguous"


def test_an_ambiguity_without_a_catalog_year_stays_out():
    """Sin dato de la casa no hay desempate posible."""
    result = _ambiguous()

    entries, skipped = promote.build_entries([result], master={})

    assert entries == []
    assert skipped[0]["reason"] == "status_ambiguous"


def test_a_non_latin_wikidata_label_does_not_become_the_display_name():
    """Wikidata devolvio 'بابلو بيكاسو' como label de Picasso.

    El display_name es lo que se PUBLICA en el informe y lo que la casa
    escribe en su catalogo, asi que un label en otro alfabeto no puede
    ganarle al nombre del catalogo. Ademas parte la ficha: 'picasso' habria
    entrado como artista nuevo teniendo ya 'pablo_picasso'.
    """
    result = _result(display_name="Pablo Picasso", aliases=["Pablo Picasso"])
    result["match"]["label"] = "Pablo Picasso"
    result["match"]["proposal"]["display_name"] = "بابلو بيكاسو"

    entries, _ = promote.build_entries([result], master={})

    assert entries[0]["display_name"] == "Pablo Picasso"


def test_a_latin_wikidata_label_still_wins_over_the_catalog_form():
    """El label de Wikidata suele estar mejor escrito que el del catalogo."""
    result = _result(display_name="PEREZ, JUAN", aliases=["PEREZ, JUAN"])
    result["match"]["proposal"]["display_name"] = "Juan Pérez"

    entries, _ = promote.build_entries([result], master={})

    assert entries[0]["display_name"] == "Juan Pérez"


def test_an_identity_the_repo_declares_unverifiable_is_never_promoted():
    """Pietro Psaier: existe la ficha de Wikidata, se discute la PERSONA.

    Se sospecha una identidad fabricada por marchantes. Ya se dio de alta y se
    revirtio dos veces, asi que el promotor tiene que conocer la decision: un
    match exacto acredita que hay ficha, no que la identidad sea real.
    """
    result = _result(
        research_key="pietro_psaier",
        artist_key="pietro_psaier",
        display_name="Pietro Psaier",
        aliases=["Pietro Psaier"],
    )

    entries, skipped = promote.build_entries([result], master={})

    assert entries == []
    assert skipped[0]["reason"] == "identity_disputed"


def test_a_one_word_catalog_name_needs_more_than_a_wikidata_alias():
    """El catalogo publica 'Ángeles' y Wikidata lo casa con 'Peter Angelis'.

    El match es real — Wikidata lista 'Angeles' como alias del pintor flamenco —
    pero la conclusion es falsa: en un catalogo espaniol 'Ángeles' es un
    apellido. Un nombre de UNA palabra que solo casa con un ALIAS (no con el
    label) no acredita identidad.
    """
    result = _result(
        research_key="angeles",
        artist_key="angeles",
        display_name="Ángeles",
        aliases=["Ángeles"],
    )
    result["match"]["label"] = "Peter Angelis"
    result["match"]["matched_names"] = ["Angeles"]
    result["match"]["proposal"]["display_name"] = "Peter Angelis"

    entries, skipped = promote.build_entries([result], master={})

    assert entries == []
    assert skipped[0]["reason"] == "one_word_alias_only_match"


def test_a_one_word_name_matching_the_label_itself_is_kept():
    """'Ceesepe' o 'Balet' casan con el LABEL: eso si es la persona."""
    result = _result(
        research_key="balet",
        artist_key="balet",
        display_name="Balet",
        aliases=["Balet"],
    )
    result["match"]["label"] = "Balet"
    result["match"]["matched_names"] = ["Balet"]
    result["match"]["proposal"]["display_name"] = "Jan Balet"

    entries, _ = promote.build_entries([result], master={})

    assert len(entries) == 1


def test_an_implausibly_old_new_entry_is_not_published_as_alive():
    """Manuel Fernandez Carpio: n. 1853 y sin muerte serian 173 anios.

    La guarda de edad ya existia para los COMPLEMENTOS pero no para las altas
    nuevas, asi que la ficha entraba con confidence high y sin death_status, y
    el informe la escribe "n. 1853", que el lector lee como persona viva. Es el
    bug que publico a Fidolo Gonzalez Camargo con 96 anios.
    """
    result = _result()
    result["match"]["proposal"]["birth_year"] = 1853
    result["match"]["proposal"]["death_year"] = None

    entries, _ = promote.build_entries([result], master={})

    assert len(entries) == 1
    entry = entries[0]
    # El anio de nacimiento es un dato bueno y se conserva; lo que no se puede
    # afirmar es que siga vivo, asi que la ficha baja de confianza y lo avisa.
    assert entry["birth_year"] == 1853
    assert entry["death_status"] is None
    assert entry["confidence"] == "low"
    assert "muerte" in entry["notes"].lower()


def test_a_recent_birth_without_death_stays_high_confidence():
    """Un artista de 1966 sin fecha de muerte simplemente esta vivo."""
    result = _result()
    result["match"]["proposal"]["birth_year"] = 1966
    result["match"]["proposal"]["death_year"] = None

    entries, _ = promote.build_entries([result], master={})

    assert entries[0]["confidence"] == "high"


def test_a_birth_year_far_from_the_catalog_is_a_probable_homonym():
    """La trampa Ricardo Canals: el catalogo y Wikidata deben concordar.

    'André Eugène' llega del catalogo con 1856 y Wikidata devuelve 1959: un
    siglo de diferencia significa que es OTRA persona, no un dato mejorado.
    """
    result = _result(candidate_birth_year=1856)
    result["match"]["proposal"]["birth_year"] = 1959
    result["match"]["proposal"]["death_year"] = None

    entries, skipped = promote.build_entries([result])

    assert entries == []
    assert skipped[0]["reason"] == "birth_year_conflicts_with_catalog"


def test_a_small_date_discrepancy_survives_because_sources_disagree():
    """Antonio Palacios: 1874 en Wikipedia y 1876 en la ficha de Duran.

    Las discrepancias pequenias son normales entre fuentes y no indican un
    homonimo; la ficha entra y la fuente gana, como ya se hizo a mano.
    """
    result = _result(candidate_birth_year=1918)
    result["match"]["proposal"]["birth_year"] = 1920

    entries, skipped = promote.build_entries([result])

    assert len(entries) == 1
    assert entries[0]["birth_year"] == 1920


def test_a_display_name_already_in_the_master_is_not_promoted_again():
    """El caso Steinlen: la ficha ya existe con el nombre en otro orden.

    El promotor comparaba el artist_id y los alias del catalogo, pero el
    display_name que devuelve Wikidata ('Théophile Alexandre Steinlen') tiene
    fold distinto de la forma invertida del catalogo, asi que no chocaba y se
    creaba un artista duplicado que rompe load_master() entero.
    """
    result = _result(
        research_key="alexandre_theophile_steinlen",
        artist_key="alexandre_theophile_steinlen",
        display_name="Alexandre Théophile Steinlen",
        aliases=["Alexandre Théophile Steinlen"],
    )
    result["match"]["proposal"]["display_name"] = "Théophile Alexandre Steinlen"
    master = {
        "theophile_alexandre_steinlen": {
            "artist_id": "theophile_alexandre_steinlen",
            "display_name": "Théophile Alexandre Steinlen",
            "aliases": ["Théophile Alexandre Steinlen"],
        }
    }

    entries, skipped = promote.build_entries([result], master=master)

    assert entries == []
    assert skipped[0]["reason"] == "already_in_master"


def test_an_entry_already_curated_by_hand_is_never_overwritten():
    result = _result(artist_id="juan_perez")
    master = {"juan_perez": {"artist_id": "juan_perez", "country_birth": "CO"}}

    entries, skipped = promote.build_entries([result], master=master)

    assert entries == []
    assert skipped[0]["reason"] == "already_in_master"


def test_implausible_years_are_dropped_instead_of_published():
    result = _result()
    result["match"]["proposal"]["birth_year"] = 1990
    result["match"]["proposal"]["death_year"] = 1920

    entries, _ = promote.build_entries([result])

    assert entries[0]["birth_year"] is None
    assert entries[0]["death_year"] is None


def test_a_name_that_is_not_an_author_never_becomes_an_entry():
    """Objetos y escuelas ya se filtran aguas arriba; aqui es la red de seguridad."""
    result = _result(
        research_key="escuela_espanola_s_xix",
        display_name="ESCUELA ESPAÑOLA S. XIX",
        aliases=["ESCUELA ESPAÑOLA S. XIX"],
    )

    entries, skipped = promote.build_entries([result])

    assert entries == []
    assert skipped[0]["reason"] == "not_an_author"


# --- Integridad del YAML generado ---------------------------------------


def test_completions_report_only_fields_the_master_is_missing():
    """Una ficha ya curada puede tener huecos que la evidencia cierra.

    Se emiten como COMPLEMENTOS para revisar, nunca como altas ni como
    escritura automatica: el maestro se edita a mano.
    """
    result = _result(artist_id="juan_perez")
    master = {
        "juan_perez": {
            "artist_id": "juan_perez",
            "display_name": "Juan Pérez",
            "aliases": ["Juan Pérez"],
            "country_birth": "ES",   # ya lo tiene: no debe proponerse
            "birth_year": None,      # hueco
            "death_year": None,      # hueco
        }
    }

    completions = promote.build_completions([result], master=master)

    assert len(completions) == 1
    assert completions[0]["artist_id"] == "juan_perez"
    assert completions[0]["fields"] == {"birth_year": 1920, "death_year": 1992}
    assert "https://www.wikidata.org/wiki/Q123" in completions[0]["source_url"]


def test_wikidata_without_a_death_date_confirms_a_living_artist():
    """Una ficha de Wikidata sin P570 es evidencia de que la persona vive.

    Sin death_status, "n. 1954" se lee como hueco y no se sabe si falta el dato
    o si el artista sigue vivo. Marcarlo cierra la ficha de verdad.
    """
    result = _result(artist_id="juan_perez")
    result["match"]["proposal"]["birth_year"] = 1954
    result["match"]["proposal"]["death_year"] = None
    master = {
        "juan_perez": {
            "artist_id": "juan_perez",
            "display_name": "Juan Pérez",
            "aliases": ["Juan Pérez"],
            "country_birth": "ES",
            "birth_year": 1954,
            "death_year": None,
        }
    }

    completions = promote.build_completions([result], master=master)

    assert completions[0]["fields"] == {"death_status": "living"}


def test_an_implausibly_old_artist_is_not_declared_living():
    """Nacido en 1850 y sin muerte no esta vivo: falta el dato.

    Es el bug que ya publico a Fidolo Gonzalez Camargo con 96 anios y a Julia
    Acunia Guillen con 121. Ahi el hueco se queda visible.
    """
    result = _result(artist_id="juan_perez")
    result["match"]["proposal"]["birth_year"] = 1850
    result["match"]["proposal"]["death_year"] = None
    master = {
        "juan_perez": {
            "artist_id": "juan_perez",
            "display_name": "Juan Pérez",
            "aliases": ["Juan Pérez"],
            "country_birth": "ES",
            "birth_year": 1850,
            "death_year": None,
        }
    }

    completions = promote.build_completions([result], master=master)

    assert completions == []


def test_a_gap_the_curator_left_on_purpose_is_not_proposed_again():
    """Sebastián de Llanos y Valdés: 'Se omiten los anios por discrepancia'.

    El hueco es una DECISION documentada en notes, no un olvido. Proponer
    fechas ahi contradice a la persona que ya miro el caso.
    """
    result = _result(artist_id="juan_perez")
    master = {
        "juan_perez": {
            "artist_id": "juan_perez",
            "display_name": "Juan Pérez",
            "aliases": ["Juan Pérez"],
            "country_birth": "ES",
            "birth_year": None,
            "death_year": None,
            "notes": "3 lotes | nacido en Sevilla. Se omiten los anios por discrepancia entre fuentes.",
        }
    }

    completions = promote.build_completions([result], master=master)

    assert completions == []


def test_a_living_artist_is_never_given_a_death_year():
    """death_status living es una afirmacion; no se pisa con un hueco ajeno."""
    result = _result(artist_id="juan_perez")
    master = {
        "juan_perez": {
            "artist_id": "juan_perez",
            "display_name": "Juan Pérez",
            "aliases": ["Juan Pérez"],
            "country_birth": "ES",
            "birth_year": 1920,
            "death_year": None,
            "death_status": "living",
        }
    }

    completions = promote.build_completions([result], master=master)

    assert completions == []


def test_two_spellings_matching_the_same_wikidata_id_become_one_entry():
    """'Ouka Leele' y 'Ouka Lele' son la misma persona en el catalogo de Duran.

    Sus folds difieren por la doble ele, asi que llegan como dos filas, pero
    Wikidata las resuelve al mismo Q440610. Promoverlas por separado dejaria a
    la artista rankeando partida y con la mitad de sus lotes sin pais, que es
    justo lo que la lista de alias existe para evitar.
    """
    first = _result(
        research_key="ouka_leele", artist_key="ouka_leele",
        display_name="Ouka Leele", aliases=["Ouka Leele"],
    )
    second = _result(
        research_key="ouka_lele", artist_key="ouka_lele",
        display_name="Ouka Lele", aliases=["Ouka Lele"],
    )

    # master={} aisla la regla: con el maestro real esta artista ya existe y el
    # descarte por already_in_master taparia lo que se quiere comprobar.
    entries, _ = promote.build_entries([first, second], master={})

    assert len(entries) == 1
    # Las dos grafias del catalogo deben resolver contra la unica ficha.
    assert set(entries[0]["aliases"]) == {"Ouka Leele", "Ouka Lele"}


def test_two_results_claiming_the_same_alias_only_promote_once():
    """Regla 3 del maestro: un alias solo puede pertenecer a un artista.

    Son dos QID distintos (dos personas para Wikidata) que reclaman el mismo
    nombre: ahi no se fusiona, se descarta el segundo. Es el caso
    'Francisco Toledo', dos pintores reales con el mismo fold.
    """
    first = _result()
    second = _result(research_key="juan_perez_dup", artist_key="juan_perez_dup")
    second["match"] = {**second["match"], "wikidata_id": "Q999"}

    entries, skipped = promote.build_entries([first, second])

    assert len(entries) == 1
    assert skipped[0]["reason"] == "alias_already_claimed"


def test_rendered_yaml_quotes_country_codes_so_norway_survives():
    """NO sin comillas parsea como booleano False y Noruega desaparecia."""
    result = _result()
    result["match"]["proposal"]["birth_places"] = [_place("Q585", "Oslo")]

    # Oslo no esta en _countries.yaml: el pais sale del P17 de Wikidata, que es
    # el camino real para las ciudades que la tabla no cubre.
    entries, _ = promote.build_entries([result], place_countries={"Q585": "NO"})
    text = promote.render_shard(entries)
    parsed = yaml.safe_load(text)

    assert entries[0]["country_birth"] == "NO"
    assert parsed["artists"][0]["country_birth"] == "NO"
    assert parsed["artists"][0]["country_birth"] is not False


def test_a_corrupted_journal_line_does_not_abort_the_promotion(tmp_path):
    """Una linea con bytes invalidos tumbaba la promocion entera.

    El diario es append-only: un proceso interrumpido a mitad de escritura deja
    una linea rota, y leer en modo texto lanza UnicodeDecodeError al iterar,
    antes del try. Mismo fallo que ya inutilizo la cache HTTP.
    """
    path = tmp_path / "journal.jsonl"
    good = json.dumps(_result(), ensure_ascii=False)
    with path.open("wb") as handle:
        handle.write(good.encode("utf-8") + b"\n")
        handle.write(b"\xb3 basura binaria\n")

    rows = list(promote._iter_jsonl(path))

    assert len(rows) == 1
    assert rows[0]["research_key"] == "juan_perez"


def test_a_place_country_map_rescues_entries_researched_before_the_p17_hop():
    """265 fichas se investigaron antes de que existiera el salto P19->P17.

    Sus lugares llegan sin country_iso ('Florencia', None) y _countries.yaml
    no conoce esas ciudades, asi que la ficha se quedaba sin pais teniendo el
    dato a un salto de distancia. El mapa se pasa aparte para no reinvestigar.
    """
    result = _result()
    result["match"]["proposal"]["birth_places"] = [_place("Q2044", "Florencia")]

    entries, _ = promote.build_entries(
        [result], master={}, place_countries={"Q2044": "IT"}
    )

    assert entries[0]["country_birth"] == "IT"
