"""Tests de pipelines/shared/artist_master.py.

Cubren las dos garantias que sostienen el maestro: que nunca inventa un pais y
que un alias solo puede pertenecer a un artista. Ademas valida el maestro REAL
del repo, que es lo que impide que se pudra como paso con houses.yaml.
"""

import textwrap

import pytest
import yaml

from pipelines.shared import artist_master
from pipelines.shared.artist_master import (
    RESOLUTION_FOLD_ONLY,
    RESOLUTION_MASTER,
    RESOLUTION_NOT_AUTHOR,
    RESOLUTION_UNRESOLVED,
)

REAL_ARTISTS_DIR = artist_master.ARTISTS_DIR

COUNTRIES_YAML = textwrap.dedent(
    """
    countries:
      CO: {es: Colombia, demonym_es: colombiano}
      ES: {es: España, demonym_es: español}
      GB: {es: Reino Unido, demonym_es: británico}
      MX: {es: México, demonym_es: mexicano}
    aliases:
      colombia: CO
      bogota: CO
      espana: ES
      inglaterra: GB
      reino unido: GB
      mexico: MX
    """
)


@pytest.fixture
def master_dir(tmp_path, monkeypatch):
    """Redirige el maestro a un arbol temporal y limpia los caches."""
    d = tmp_path / "artists"
    d.mkdir(parents=True, exist_ok=True)
    (d / "_countries.yaml").write_text(COUNTRIES_YAML, encoding="utf-8")
    monkeypatch.setattr(artist_master, "ARTISTS_DIR", d)
    artist_master.reset_caches()
    yield d
    artist_master.reset_caches()


def _write_shard(directory, name, artists):
    path = directory / name
    path.write_text(
        yaml.safe_dump({"artists": artists}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    artist_master.reset_caches()
    return path


def _obregon(**overrides):
    entry = {
        "artist_id": "alejandro_obregon",
        "display_name": "Alejandro Obregón",
        "country_birth": "ES",
        "nationalities": ["CO", "ES"],
        "attribution_type": "autor",
        "source": "manual",
        "confidence": "high",
        "aliases": ["Alejandro Obregón", "OBREGÓN, ALEJANDRO"],
    }
    entry.update(overrides)
    return entry


# --------------------------------------------------------------------------
# Integridad del maestro
# --------------------------------------------------------------------------

def test_empty_master_loads_without_error(master_dir):
    """Shards vacios es el estado de entrega: debe cargar, no fallar."""
    _write_shard(master_dir, "a.yaml", [])
    assert artist_master.load_master() == {}


def test_missing_directory_loads_without_error(tmp_path, monkeypatch):
    monkeypatch.setattr(artist_master, "ARTISTS_DIR", tmp_path / "no-existe")
    artist_master.reset_caches()
    assert artist_master.load_master() == {}
    artist_master.reset_caches()


def test_duplicate_artist_id_across_shards_raises(master_dir):
    """Un artist_id repetido rompe la identidad: falla al cargar, ruidosamente."""
    _write_shard(master_dir, "a.yaml", [_obregon()])
    _write_shard(master_dir, "b.yaml", [_obregon(aliases=["Otro Nombre"])])
    with pytest.raises(ValueError, match="artist_id duplicado"):
        artist_master.load_master()


def test_duplicate_alias_across_shards_raises(master_dir):
    """Un nombre crudo solo puede pertenecer a una persona."""
    _write_shard(master_dir, "a.yaml", [_obregon()])
    _write_shard(
        master_dir,
        "b.yaml",
        [
            _obregon(
                artist_id="beatriz_gonzalez",
                display_name="Beatriz González",
                aliases=["Alejandro Obregón"],  # ya lo reclama alejandro_obregon
            )
        ],
    )
    with pytest.raises(ValueError, match="alias duplicado"):
        artist_master.resolve_artist("Alejandro Obregón")


def test_entry_without_artist_id_raises(master_dir):
    _write_shard(master_dir, "a.yaml", [{"display_name": "Sin Id"}])
    with pytest.raises(ValueError, match="sin artist_id"):
        artist_master.load_master()


# --------------------------------------------------------------------------
# Nunca inventar un pais
# --------------------------------------------------------------------------

def test_unknown_artist_returns_null_country_not_a_guess(master_dir):
    """Un artista fuera del maestro no recibe pais. Ni el de la casa, ni ninguno.

    Es la regla de to_eur(), que devuelve None en vez de 1.0: un dato que falta
    debe verse, no disfrazarse.
    """
    _write_shard(master_dir, "a.yaml", [])
    got = artist_master.resolve_artist("Fernando Botero")
    assert got["artist_resolution"] == RESOLUTION_FOLD_ONLY
    assert got["artist_country_birth"] is None
    assert got["artist_nationalities"] == []
    assert got["artist_id"] is None
    assert got["artist_fold"] == "fernando botero"


def test_resolved_artist_gets_country_from_master(master_dir):
    _write_shard(master_dir, "a.yaml", [_obregon()])
    got = artist_master.resolve_artist("OBREGÓN, ALEJANDRO")
    assert got["artist_resolution"] == RESOLUTION_MASTER
    assert got["artist_id"] == "alejandro_obregon"
    assert got["artist_display_name"] == "Alejandro Obregón"
    assert got["artist_country_birth"] == "ES"
    assert set(got["artist_nationalities"]) == {"CO", "ES"}


def test_nationalities_includes_country_birth(master_dir):
    """Si el curador olvida repetir el pais de nacimiento, se anade igual."""
    _write_shard(master_dir, "a.yaml", [_obregon(nationalities=["CO"])])
    got = artist_master.resolve_artist("Alejandro Obregón")
    assert "ES" in got["artist_nationalities"]
    assert "CO" in got["artist_nationalities"]


def test_non_authors_never_get_identity(master_dir):
    _write_shard(master_dir, "a.yaml", [])
    for name in ["Escuela Española S. XVII", "Anónimo", "Colonia: 10 obras"]:
        got = artist_master.resolve_artist(name)
        assert got["artist_resolution"] == RESOLUTION_NOT_AUTHOR
        assert got["artist_id"] is None
        assert got["artist_country_birth"] is None


def test_furniture_looks_like_an_author_but_gets_no_country(master_dir):
    """"Sillas de bar" es indistinguible de un nombre propio, y da igual.

    Ninguna regla determinista puede separar un mueble de una persona cuando no
    hay marca lexica: por eso el maestro es curado. Lo que si garantiza el
    sistema es que, al no estar en el maestro, no recibe pais ni artist_id, y
    que MIN_LOTS_FOR_ARTIST_RANK lo deja fuera del ranking.
    """
    _write_shard(master_dir, "a.yaml", [])
    got = artist_master.resolve_artist("Sillas de bar")
    assert got["artist_resolution"] == RESOLUTION_FOLD_ONLY
    assert got["artist_id"] is None
    assert got["artist_country_birth"] is None


def test_empty_name_is_unresolved(master_dir):
    _write_shard(master_dir, "a.yaml", [])
    for name in [None, "", "   "]:
        got = artist_master.resolve_artist(name)
        assert got["artist_resolution"] == RESOLUTION_UNRESOLVED
        assert got["artist_fold"] is None


def test_resolution_always_has_the_same_shape(master_dir):
    """Todos los lotes de Silver deben acabar con las mismas 7 claves."""
    _write_shard(master_dir, "a.yaml", [_obregon()])
    expected = {
        "artist_id",
        "artist_fold",
        "artist_display_name",
        "attribution_type",
        "artist_country_birth",
        "artist_nationalities",
        "artist_resolution",
    }
    for name in ["Alejandro Obregón", "Fernando Botero", "Escuela Española", None]:
        assert set(artist_master.resolve_artist(name)) == expected


# --------------------------------------------------------------------------
# Normalizacion de paises
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("Colombia", "CO"),
        ("colombia", "CO"),
        ("España", "ES"),
        ("Espana", "ES"),
        # Henry Moore aparece en los datos con las dos formas: mismo pais.
        ("Inglaterra", "GB"),
        ("Reino Unido", "GB"),
        # Ciudad donde deberia ir el pais: 69 lotes con "Bogotá".
        ("Bogotá", "CO"),
        ("México", "MX"),
        ("CO", "CO"),  # ya viene como ISO
        # Desconocido: None, no se cuela tal cual.
        ("Frobnia", None),
        ("", None),
        (None, None),
    ],
)
def test_country_normalization(master_dir, text, expected):
    assert artist_master.normalize_country(text) == expected


def test_yaml_boolean_country_codes_survive_loading(tmp_path, monkeypatch):
    """NO (Noruega) no puede acabar siendo el booleano False.

    YAML 1.1 lee NO, ON, OFF y YES sin comillas como booleanos. En la primera
    version de _countries.yaml, "NO: {es: Noruega}" cargaba con la clave False y
    Noruega desaparecia de la tabla; el alias "noruega: NO" apuntaba a False.
    """
    d = tmp_path / "artists"
    d.mkdir(parents=True, exist_ok=True)
    (d / "_countries.yaml").write_text(
        textwrap.dedent(
            """
            countries:
              NO: {es: Noruega, demonym_es: noruego}
            aliases:
              noruega: NO
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(artist_master, "ARTISTS_DIR", d)
    artist_master.reset_caches()
    try:
        assert artist_master.normalize_country("Noruega") == "NO"
        assert artist_master.country_es("NO") == "Noruega"
    finally:
        artist_master.reset_caches()


def test_validate_catches_unquoted_boolean_country(master_dir):
    """Un country_birth sin comillas (NO -> False) tiene que saltar.

    El guardado era "if birth and ...", y False es falsy: la corrupcion pasaba
    de largo por el unico control que existe para detectarla, y el artista
    perdia el pais sin un solo error en toda la cadena.
    """
    _write_shard(
        master_dir,
        "e.yaml",
        [
            {
                "artist_id": "edvard_munch",
                "display_name": "Edvard Munch",
                "country_birth": False,   # lo que YAML hace con un NO sin comillas
                "nationalities": [False],
                "attribution_type": "autor",
                "source": "manual",
                "confidence": "high",
                "aliases": ["Edvard Munch"],
            }
        ],
    )
    problems = artist_master.validate_master()
    assert any("booleano" in p for p in problems), problems


def test_country_es_display_name(master_dir):
    assert artist_master.country_es("CO") == "Colombia"
    assert artist_master.country_es("GB") == "Reino Unido"
    assert artist_master.country_es("XX") is None
    assert artist_master.country_es(None) is None


# --------------------------------------------------------------------------
# El maestro REAL del repo
# --------------------------------------------------------------------------

def test_every_shard_entry_validates():
    """Valida pipelines/config/artists/ tal como esta en el repo.

    Este es el test que impide que el maestro se pudra: houses.yaml quedo
    obsoleto justamente porque nada lo leia ni lo comprobaba.
    """
    artist_master.reset_caches()
    try:
        problems = artist_master.validate_master()
    finally:
        artist_master.reset_caches()
    assert problems == [], "\n".join(problems)


def test_real_countries_table_is_loadable():
    """Los alias del repo deben apuntar a paises declarados."""
    artist_master.reset_caches()
    try:
        data = artist_master.load_countries()
        assert data["countries"], "_countries.yaml no declara ningun pais"
        unknown = sorted(
            {code for code in data["aliases"].values() if code not in data["countries"]}
        )
        assert unknown == [], f"alias apuntando a paises no declarados: {unknown}"
    finally:
        artist_master.reset_caches()


# --------------------------------------------------------------------------
# Alias por inversion de coma: revisados a mano, no automaticos
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "comma_form,expected_id",
    [
        ("ALCALDE, JUAN", "juan_alcalde"),
        ("ALCAÍN, ALFREDO", "alfredo_alcain"),
        ("ALCORLO, MANUEL", "manuel_alcorlo"),
        ("MIRÓ FERRÁ, JOAN", "joan_miro"),
        ("González, Beatriz", "beatriz_gonzalez"),
        ("GUTIÉRREZ SOLANA, JOSÉ", "jose_gutierrez_solana"),
    ],
)
def test_comma_inverted_aliases_resolve_to_the_same_artist(comma_form, expected_id):
    """La casa publica el mismo artista de dos formas: "APELLIDO, Nombre" y directa.

    El fold NO invierte por su cuenta a proposito, asi que estas uniones viven
    como alias explicitos en el maestro. Sin ellos el artista sale dos veces en
    el ranking y la mitad de sus lotes se queda sin pais.

    Se comprueba contra el maestro REAL del repo, no contra un fixture: lo que
    se quiere fijar es que esos alias sigan estando en los shards.
    """
    artist_master.reset_caches()
    try:
        resolved = artist_master.resolve_artist(comma_form)
    finally:
        artist_master.reset_caches()
    assert resolved["artist_id"] == expected_id
    assert resolved["artist_resolution"] == RESOLUTION_MASTER


def test_garcia_marquez_is_still_not_merged():
    """El contraejemplo que justifica que la inversion se revise a mano.

    "García Márquez, Gabriel" son 55 lotes de LIBROS: el escritor, no un pintor.
    Invertir por regla automatica lo habria fusionado con un pintor homonimo.
    """
    artist_master.reset_caches()
    try:
        resolved = artist_master.resolve_artist("García Márquez, Gabriel")
    finally:
        artist_master.reset_caches()
    assert resolved["artist_resolution"] != RESOLUTION_MASTER
    assert resolved["artist_country_birth"] is None


# --------------------------------------------------------------------------
# Pais de NACIMIENTO, no el de mercado
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name,country_birth",
    [
        # Todos venden en Duran (mercado espaniol) pero NACIERON fuera. Es el
        # error que HOUSE_COUNTRY habria cometido: usar el pais de la casa.
        ("Carlos Sáenz de Tejada", "MA"),      # Tanger
        ("Théophile Alexandre Steinlen", "CH"),  # Lausana; trabajo en Paris
        ("José Pinazo Martínez", "IT"),        # Roma, de familia valenciana
        ("Joan Gardy Artigas", "FR"),          # Boulogne-Billancourt
        ("Arturo Peyrot", "IT"),               # Roma; murio en Madrid
        ("Grete Stern", "DE"),                 # Elberfeld; emigro a Argentina
        ("José Pedro Croft", "PT"),
        ("Nelson Domínguez", "CU"),
    ],
)
def test_birth_country_is_not_the_market_country(name, country_birth):
    """El pais es donde NACIO el artista, no donde se subasta su obra."""
    artist_master.reset_caches()
    try:
        resolved = artist_master.resolve_artist(name)
    finally:
        artist_master.reset_caches()
    assert resolved["artist_country_birth"] == country_birth


@pytest.mark.parametrize(
    "name",
    ["Miguel Zelada", "Carlos Villalva", "Antonio Posada", "Pietro Psaier"],
)
def test_unverifiable_artists_keep_no_country(name):
    """Investigados sin resultado concluyente: se quedan SIN pais.

    Es la regla del README y la razon de que el informe publique la cobertura
    real. Un pais a ojo aqui no se distinguiria luego de uno documentado.
    """
    artist_master.reset_caches()
    try:
        resolved = artist_master.resolve_artist(name)
    finally:
        artist_master.reset_caches()
    assert resolved["artist_country_birth"] is None


# --------------------------------------------------------------------------
# Seudonimos de una sola palabra
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "pseudonym,country_birth",
    [
        ("Jano", "ES"),        # Francisco Fernandez-Zarza Perez
        ("Marola", "ES"),      # Manuel Rodriguez Lana
        ("Serny", "ES"),       # Ricardo Summers Ysern
        ("Monir", "IR"),       # Monir Shahroudy Farmanfarmaian
        ("Rembrandt", "NL"),
        ("Durero", "DE"),      # forma castellanizada de Albrecht Durer
        ("Guinovart", "ES"),   # alias corto de josep_guinovart, no otra entrada
    ],
)
def test_single_word_pseudonyms_resolve(pseudonym, country_birth):
    """Un solo apellido o seudonimo tambien identifica a una persona.

    El fold no puede resolverlos por su cuenta: hace falta que alguien decida
    que "Serny" es Ricardo Summers. Por eso viven como alias del maestro.
    """
    artist_master.reset_caches()
    try:
        resolved = artist_master.resolve_artist(pseudonym)
    finally:
        artist_master.reset_caches()
    assert resolved["artist_resolution"] == RESOLUTION_MASTER
    assert resolved["artist_country_birth"] == country_birth


def test_ambiguous_surname_is_left_unresolved():
    """"*Mingorance" son 10 lotes que podrian ser de dos personas distintas.

    El maestro tiene a Manuel Mingorance Acien (1937-2011) y las fuentes traen
    ademas a Juan Eugenio Mingorance Navas (1906-1979). Los lotes no llevan anio
    con el que desempatar, asi que se quedan sin pais: es el caso "Francisco
    Toledo" que justifica que el maestro se clave en alias y no en el fold.
    """
    artist_master.reset_caches()
    try:
        resolved = artist_master.resolve_artist("*Mingorance")
    finally:
        artist_master.reset_caches()
    assert resolved["artist_country_birth"] is None


def test_format_life_years_shapes():
    """Un artista sin fecha de muerte NO es un artista vivo.

    El maestro no distingue "sigue vivo" de "no consta la fecha", asi que la
    forma "1954-" queda prohibida: afirmaria algo que el dato no sostiene.
    """
    assert artist_master.format_life_years(1920, 1992) == "1920-1992"
    assert artist_master.format_life_years(1954, None) == "n. 1954"
    assert artist_master.format_life_years(None, 2008) == "m. 2008"
    assert artist_master.format_life_years(None, None) is None


def test_artist_years_never_invents_a_date():
    """Misma disciplina que country_birth: fuera del maestro, None.

    Un artista en fold_only no tiene artist_id, y artist_raw viene truncado a 60
    caracteres, asi que no hay de donde sacar la fecha sin inventarla.
    """
    artist_master.reset_caches()
    try:
        assert artist_master.artist_years(None) == {
            "birth_year": None,
            "death_year": None,
        }
        assert artist_master.artist_years("no_existe_este_id") == {
            "birth_year": None,
            "death_year": None,
        }
    finally:
        artist_master.reset_caches()
