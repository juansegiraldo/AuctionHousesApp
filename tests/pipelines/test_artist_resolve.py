"""Tests de pipelines/silver/artist_resolve.py.

La etapa reescribe data/silver/lots.jsonl, asi que lo que se protege aqui es
que no pierda lotes, que no invente paises y que se pueda volver a ejecutar sin
que el resultado derive.
"""

import json
import textwrap

import pytest
import yaml

from pipelines.shared import artist_master
from pipelines.silver import artist_resolve

COUNTRIES_YAML = textwrap.dedent(
    """
    countries:
      CO: {es: Colombia, demonym_es: colombiano}
      ES: {es: España, demonym_es: español}
    aliases:
      colombia: CO
      espana: ES
    """
)


def _lot(**kw):
    base = {
        "dedupe_key": "duran_subastas|u",
        "lot_url": "u",
        "house_slug": "duran_subastas",
        "currency": "EUR",
        "status": "VENDIDO",
        "price_sold": 100,
        "artist_name": "Fernando Botero",
        "artist_country": None,
    }
    base.update(kw)
    return base


def _write(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@pytest.fixture
def silver(tmp_path, monkeypatch):
    """Silver temporal + maestro temporal vacio."""
    lots = tmp_path / "data" / "silver" / "lots.jsonl"
    lots.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(artist_resolve, "SILVER_LOTS", lots)

    master = tmp_path / "artists"
    master.mkdir(parents=True, exist_ok=True)
    (master / "_countries.yaml").write_text(COUNTRIES_YAML, encoding="utf-8")
    (master / "a.yaml").write_text("artists: []\n", encoding="utf-8")
    monkeypatch.setattr(artist_master, "ARTISTS_DIR", master)
    artist_master.reset_caches()
    yield lots, master
    artist_master.reset_caches()


def _seed_master(master_dir, artists):
    (master_dir / "a.yaml").write_text(
        yaml.safe_dump({"artists": artists}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    artist_master.reset_caches()


# --------------------------------------------------------------------------
# Forma e integridad
# --------------------------------------------------------------------------

def test_all_lots_get_all_fields(silver):
    """Todos los lotes salen con los 7 campos, incluidos los que no tienen artista.

    Zorrilla son 3.437 lotes de joyeria sin artist_name en ninguno: si la etapa
    solo anadiera campos cuando hay artista, Silver dejaria de tener una forma
    unica y Gold tendria que usar .get() por todas partes.
    """
    lots, _ = silver
    _write(
        lots,
        [
            _lot(lot_url="a", dedupe_key="a"),
            _lot(lot_url="b", dedupe_key="b", artist_name=None,
                 house_slug="zorrilla_subastas", lot_title="9K RED GOLD PENDANT."),
            _lot(lot_url="c", dedupe_key="c", artist_name="Escuela Española S. XVII"),
        ],
    )
    artist_resolve.main()
    rows = _read(lots)
    assert len(rows) == 3
    for row in rows:
        for field in artist_resolve.RESOLUTION_FIELDS:
            assert field in row, f"falta {field} en {row['dedupe_key']}"


def test_no_lot_is_dropped(silver):
    lots, _ = silver
    rows = [_lot(lot_url=f"x{i}", dedupe_key=f"x{i}") for i in range(25)]
    _write(lots, rows)
    artist_resolve.main()
    assert len(_read(lots)) == 25


def test_idempotent(silver):
    """Dos pasadas dan un fichero identico byte a byte.

    run_all.ps1 se re-ejecuta a menudo; si la etapa no fuera idempotente, cada
    pasada iria acumulando cambios sobre Silver.
    """
    lots, _ = silver
    _write(
        lots,
        [
            _lot(lot_url="a", dedupe_key="a"),
            _lot(lot_url="b", dedupe_key="b", artist_name="Anónimo"),
        ],
    )
    artist_resolve.main()
    first = lots.read_bytes()
    artist_resolve.main()
    assert lots.read_bytes() == first


def test_missing_master_file_does_not_crash(silver, monkeypatch, tmp_path):
    """Sin maestro, todo autor cae a fold_only y la etapa termina bien."""
    lots, _ = silver
    monkeypatch.setattr(artist_master, "ARTISTS_DIR", tmp_path / "no-existe")
    artist_master.reset_caches()
    _write(lots, [_lot(lot_url="a", dedupe_key="a")])
    artist_resolve.main()
    row = _read(lots)[0]
    assert row["artist_resolution"] == "fold_only"
    assert row["artist_country_birth"] is None


def test_missing_silver_raises_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(artist_resolve, "SILVER_LOTS", tmp_path / "no-existe.jsonl")
    with pytest.raises(FileNotFoundError, match="build_silver"):
        artist_resolve.main()


# --------------------------------------------------------------------------
# Nunca inventar un pais
# --------------------------------------------------------------------------

def test_house_country_is_never_used_as_artist_country(silver):
    """El pais de la casa NO es el pais del artista.

    Es el test mas importante del conjunto. render_html.py tiene un
    HOUSE_COUNTRY (bogota_auctions -> Colombia) que es donde OCURRE la subasta.
    Usarlo como nacionalidad ya seria falso hoy para los 46 artistas espanioles,
    26 alemanes y 25 panamenios que Bogota ha vendido.
    """
    lots, _ = silver
    _write(
        lots,
        [
            _lot(lot_url="a", dedupe_key="a", house_slug="bogota_auctions",
                 artist_name="Artista Desconocido Del Maestro"),
            _lot(lot_url="b", dedupe_key="b", house_slug="duran_subastas",
                 artist_name="Otro Artista Sin Maestro"),
        ],
    )
    artist_resolve.main()
    for row in _read(lots):
        assert row["artist_country_birth"] is None
        assert row["artist_nationalities"] == []


def test_raw_country_alone_does_not_grant_a_country(silver):
    """artist_country de la casa es diagnostico, no fuente de verdad.

    Solo el maestro concede pais. El texto libre sirve para detectar valores sin
    mapear y discrepancias, no para escribir artist_country_birth.
    """
    lots, _ = silver
    _write(
        lots,
        [_lot(lot_url="a", dedupe_key="a", artist_name="Sin Ficha En Maestro",
              artist_country="Colombia")],
    )
    artist_resolve.main()
    row = _read(lots)[0]
    assert row["artist_resolution"] == "fold_only"
    assert row["artist_country_birth"] is None


def test_master_beats_conflicting_silver_free_text(silver):
    """El caso Alejandro Obregon: gana el maestro, no la mayoria del texto crudo.

    Los datos reales dicen "Espania" 17 veces y "Colombia" 3. Una votacion por
    mayoria daria "Espania" con toda confianza, y seria una respuesta pobre:
    nacio en Barcelona pero el mercado lo trata como colombiano. La forma
    correcta es country_birth=ES + nationalities=[CO, ES].
    """
    lots, master = silver
    _seed_master(
        master,
        [
            {
                "artist_id": "alejandro_obregon",
                "display_name": "Alejandro Obregón",
                "country_birth": "ES",
                "nationalities": ["CO", "ES"],
                "attribution_type": "autor",
                "source": "manual",
                "confidence": "high",
                "aliases": ["Alejandro Obregón"],
            }
        ],
    )
    _write(
        lots,
        [
            _lot(lot_url="a", dedupe_key="a", artist_name="Alejandro Obregón",
                 artist_country="España"),
            _lot(lot_url="b", dedupe_key="b", artist_name="Alejandro Obregón",
                 artist_country="Colombia"),
        ],
    )
    artist_resolve.main()
    for row in _read(lots):
        assert row["artist_resolution"] == "master"
        assert row["artist_id"] == "alejandro_obregon"
        assert row["artist_country_birth"] == "ES"
        assert set(row["artist_nationalities"]) == {"CO", "ES"}


def test_variants_share_one_fold(silver):
    """Las grafias de un mismo artista se agrupan aunque no haya maestro."""
    lots, _ = silver
    _write(
        lots,
        [
            _lot(lot_url="a", dedupe_key="a", artist_name="Agustín Úbeda"),
            _lot(lot_url="b", dedupe_key="b", artist_name="Agustin Ubeda"),
            _lot(lot_url="c", dedupe_key="c", artist_name="AGUSTÍN ÚBEDA"),
        ],
    )
    artist_resolve.main()
    assert len({row["artist_fold"] for row in _read(lots)}) == 1


def test_attribution_type_is_written_for_non_authors(silver):
    lots, _ = silver
    _write(
        lots,
        [
            _lot(lot_url="a", dedupe_key="a", artist_name="Escuela Española S. XVII"),
            _lot(lot_url="b", dedupe_key="b", artist_name="Anónimo"),
            _lot(lot_url="c", dedupe_key="c", artist_name="Fernando Botero"),
            _lot(lot_url="d", dedupe_key="d", artist_name=None),
        ],
    )
    artist_resolve.main()
    got = {row["dedupe_key"]: row["attribution_type"] for row in _read(lots)}
    assert got == {
        "a": "escuela",
        "b": "anonimo",
        "c": "autor",
        "d": "desconocido",
    }


def test_original_fields_are_preserved(silver):
    """La etapa anade, no reemplaza: los 31 campos originales siguen ahi."""
    lots, _ = silver
    original = _lot(lot_url="a", dedupe_key="a", artist_country="Colombia")
    _write(lots, [original])
    artist_resolve.main()
    row = _read(lots)[0]
    for key, value in original.items():
        assert row[key] == value
