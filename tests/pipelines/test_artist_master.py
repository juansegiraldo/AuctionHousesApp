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


def test_norwegian_demonym_resolves_to_norway(tmp_path, monkeypatch):
    """Un alias que vale NO devuelve Noruega, con comillas y sin ellas.

    YAML 1.1 lee NO sin comillas como el booleano False, asi que 'norwegian: NO'
    llega al loader como False. Aqui no rompe nada porque _iso() lo convierte de
    vuelta a "NO" — esa coercion es la que sostiene el caso, no las comillas del
    fichero. Se prueban las dos formas para que quitar la coercion falle, que es
    lo unico que puede volver a borrar Noruega de la tabla.
    """
    for literal in ('"NO"', "NO"):
        d = tmp_path / f"artists_{len(literal)}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "_countries.yaml").write_text(
            textwrap.dedent(
                f"""
                countries:
                  "NO": {{es: Noruega, demonym_es: noruego}}
                aliases:
                  norwegian: {literal}
                """
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(artist_master, "ARTISTS_DIR", d)
        artist_master.reset_caches()
        try:
            got = artist_master.normalize_country("Norwegian")
            assert got == "NO", f"con 'norwegian: {literal}' llego {got!r}"
            assert got is not False
            assert artist_master.country_es(got) == "Noruega"
        finally:
            artist_master.reset_caches()


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


@pytest.mark.parametrize(
    "text,expected",
    [
        # Gentilicios y nombres en ingles. Llegan de agregadores y de fichas de
        # Duran escritas en ingles, y se contaban como unmapped_country_values
        # aunque 'spanish' y 'uruguayan' ya estuvieran mapeados desde el principio.
        ("Argentinean", "AR"),
        ("Japanese", "JP"),
        ("Philippine", "PH"),
        ("Hungarian", "HU"),
        ("Czech", "CZ"),
        ("Norwegian", "NO"),
        # Holanda es la region y no el estado, pero la ficha la usa como el pais,
        # igual que 'Inglaterra' -> GB.
        ("The Netherlands", "NL"),
        ("Holland", "NL"),
        # Paises en espaniol que faltaban en la tabla.
        ("Turquía", "TR"),
        ("Bielorrusia", "BY"),
        ("República Checa", "CZ"),
        # Ciudad y region donde deberia ir el pais, como el caso de Bogota.
        ("Viena", "AT"),
        ("Catalan", "ES"),
        ("escuela sevillana", "ES"),
        # Un siglo no es un pais: se queda en None a proposito, para que siga
        # contando como unmapped en vez de inventarse una procedencia.
        ("19th century", None),
        ("18th century", None),
        ("Europa", None),
    ],
)
def test_real_table_maps_the_values_silver_actually_writes(text, expected):
    """Contra el _countries.yaml del repo, no contra el fixture reducido.

    Los casos de test_country_normalization usan una tabla de cuatro paises, asi
    que no dicen nada sobre lo que Silver escribe de verdad en artist_country.
    Estos valores salieron de contar unmapped_country_values sobre los 64.567
    lotes reales.
    """
    artist_master.reset_caches()
    try:
        assert artist_master.normalize_country(text) == expected
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


def test_beatriz_gonzalez_birth_year_is_1932_not_1938():
    """1932, aunque el alias de la casa y el Reina Sofia digan 1938.

    El error de 1938 esta vivo en dos fuentes que normalmente serian buenas:
    el propio alias de Bogota ("Beatriz González (Colombia, 1938)") y la ficha
    de exposicion del Museo Reina Sofia. Lo desempata la aritmetica del
    obituario: murio el 09-01-2026 A LOS 93, y con 1938 tendria 87.

    Se fija en un test porque el dato equivocado va a volver: esta en el alias
    que entra por el scraper en cada ingesta.
    """
    artist_master.reset_caches()
    try:
        years = artist_master.artist_years("beatriz_gonzalez")
    finally:
        artist_master.reset_caches()
    assert years == {"birth_year": 1932, "death_year": 2026}


@pytest.mark.parametrize(
    "name,country,nationalities",
    [
        # Cuatro fichas que TENIAN un pais equivocado, no un hueco. Se detectaron
        # comparando el maestro contra fuentes publicas y son los cuatro sabores
        # del mismo error: dar por nacional del mercado a quien nacio fuera.
        #
        # El apellido no es el pais: Hoffmann figuraba como DE por sonar aleman
        # y nacio en Barranquilla.
        ("Marlene Hoffmann", "CO", ["CO"]),
        # Vender en Madrid no es haber nacido en Madrid: los tres venden en
        # Duran y ninguno nacio en Espania.
        ("Guillermo Muñoz Vera", "CL", ["ES", "CL"]),
        ("Pedro Sandoval", "VE", ["ES", "VE"]),
        ("Darío Basso", "VE", ["ES", "VE"]),
    ],
)
def test_corrected_birth_countries(name, country, nationalities):
    """El pais de NACIMIENTO manda, aunque el mercado diga otra cosa.

    nationalities conserva la del mercado en primer lugar (regla 4 del README):
    el dato de mercado no se pierde, se coloca donde corresponde.
    """
    artist_master.reset_caches()
    try:
        resolved = artist_master.resolve_artist(name)
    finally:
        artist_master.reset_caches()
    assert resolved["artist_country_birth"] == country
    assert resolved["artist_nationalities"] == nationalities


@pytest.mark.parametrize(
    "name,country,birth",
    [
        # Estaban en la lista de "no verificables" y una segunda vuelta de
        # investigacion SI los encontro, en fuentes institucionales (coleccion
        # de Afundacion y ArteInformado). Se fijan para que no vuelvan a
        # perderse: "no encontrado" es un estado del que se puede salir, y
        # confundirlo con "no existe" congela la cobertura del informe.
        ("Miguel Zelada", "ES", 1942),
        ("Antonio Posada", "ES", 1952),
    ],
)
def test_second_pass_resolved_these(name, country, birth):
    artist_master.reset_caches()
    try:
        resolved = artist_master.resolve_artist(name)
        years = artist_master.artist_years(resolved["artist_id"])
    finally:
        artist_master.reset_caches()
    assert resolved["artist_country_birth"] == country
    assert years["birth_year"] == birth


def test_mitsuo_miura_is_the_living_painter_not_the_cinematographer():
    """Miura es el pintor de Iwate (1946), no el homonimo director de foto.

    Hay un Mitsuo Miura (1902-1956) director de fotografia japones. Son dos
    personas: el de los 93 lotes de Duran nacio en 1946, reside en Espania
    desde 1966 y esta VIVO, asi que no puede llevar death_year.
    """
    artist_master.reset_caches()
    try:
        years = artist_master.artist_years("mitsuo_miura")
    finally:
        artist_master.reset_caches()
    assert years["birth_year"] == 1946
    assert years["death_year"] is None


@pytest.mark.parametrize(
    "name",
    [
        "Carlos Villalva",
        # Psaier es el caso mas fuerte de la lista y por eso sigue aqui: no es
        # que falten sus datos, es que el mundo del arte discute que la PERSONA
        # existiera (se sospecha una identidad fabricada por marchantes). Se le
        # dio de alta con "IT, 1936-2004" en una tanda de investigacion y se
        # revirtio: poner pais y fechas a alguien de existencia discutida es
        # justamente inventar identidad, no documentarla.
        "Pietro Psaier",
    ],
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


def test_excel_epoch_year_is_not_a_birth_date():
    """1905 en una ficha de FINALL.xlsx puede ser el epoch, no un nacimiento.

    Julia Acunia Guillen llevaba birth_year 1905 y salia viva con 121 anios. Su
    unico lote no trae anio en el catalogo, asi que el 1905 solo existia en la
    hoja: es el mismo artefacto que ya dejo 4 fichas con fechas imposibles.
    Se retira en vez de sustituirlo por una estimacion.

    El contraejemplo va en el mismo test a proposito: el 1918 de Leonor Alarcon
    SI lo confirma el catalogo ("Leonor Alarcon Colombia, 1918"), asi que se
    queda. La diferencia no es la antiguedad, es que haya una segunda fuente.
    """
    artist_master.reset_caches()
    try:
        julia = artist_master.artist_years("julia_acuna_guillen")
        leonor = artist_master.artist_years("leonor_alarcon")
    finally:
        artist_master.reset_caches()
    assert julia["birth_year"] is None
    assert leonor["birth_year"] == 1918


def test_luis_alberto_acuna_is_one_artist_not_two():
    """Una sola ficha: entraba dos veces, con dos anios de muerte distintos.

    "Luis Alberto Acuna" (catalogo de Bogota) y "Luis Alberto Acuna Tapias"
    (hoja FINALL) son la misma persona, y sus 19 lotes salian partidos en dos
    filas del ranking. Murio en 1993: el alias de la casa y la DESCRIPCION de
    Wikidata dicen 1994, pero el claim P570 de Wikidata y Wikipedia ES dicen
    1993.
    """
    artist_master.reset_caches()
    try:
        assert "luis_alberto_acuna_tapias" not in artist_master.load_master()
        for name in ("Luis Alberto Acuña", "LUIS ALBERTO ACUÑA TAPIAS"):
            resolved = artist_master.resolve_artist(name)
            assert resolved["artist_id"] == "luis_alberto_acuna"
        years = artist_master.artist_years("luis_alberto_acuna")
    finally:
        artist_master.reset_caches()
    assert years == {"birth_year": 1904, "death_year": 1993}


def test_implausible_age_is_flagged_not_published_as_alive():
    """Pasados los 105 anios, "sin fecha de muerte" es un hueco, no una vida larga.

    El informe llego a publicar a Fidolo Gonzalez Camargo (1883-1942) como si
    tuviera 96 anios porque su ficha decia 1930, y a Julia Acunia Guillen con
    121. La regla de no inventar una muerte sigue intacta: no se rellena
    death_year, solo se deja de AFIRMAR que la persona vive.
    """
    f = artist_master.format_life_years
    # Sin anio de referencia se comporta como siempre (compatibilidad).
    assert f(1905, None) == "n. 1905"
    # Con el anio en curso, una edad imposible se marca.
    assert f(1905, None, 2026) == "n. 1905 (?)"
    assert f(1883, None, 2026) == "n. 1883 (?)"
    # Justo por debajo del umbral no se toca: hay artistas centenarios reales.
    assert f(1930, None, 2026) == "n. 1930"
    # Y si consta la muerte, la edad da igual: el dato esta completo.
    assert f(1883, 1942, 2026) == "1883-1942"


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


def test_juan_romero_does_not_publish_a_false_death_year():
    """El catálogo antiguo decía 1996, pero el artista estaba activo en 2023."""
    artist_master.reset_caches()
    try:
        years = artist_master.artist_years("juan_romero")
    finally:
        artist_master.reset_caches()
    assert years == {"birth_year": 1932, "death_year": None}


def test_jose_catala_omits_the_disputed_birth_year():
    """Las fuentes secundarias discrepan entre 1958 y 1959."""
    artist_master.reset_caches()
    try:
        resolved = artist_master.resolve_artist("CATALÁ , JOSÉ")
        years = artist_master.artist_years("jose_catala")
    finally:
        artist_master.reset_caches()
    assert resolved["artist_id"] == "jose_catala"
    assert resolved["artist_country_birth"] == "ES"
    assert years == {"birth_year": None, "death_year": None}


def test_jorge_damiani_uses_birth_country_and_real_death_year():
    """El MNAV fija Nervi, Italia (1931), y Montevideo (2017)."""
    artist_master.reset_caches()
    try:
        resolved = artist_master.resolve_artist("Jorge DAMIANI")
        years = artist_master.artist_years("jorge_damiani")
    finally:
        artist_master.reset_caches()
    assert resolved["artist_country_birth"] == "IT"
    assert set(resolved["artist_nationalities"]) == {"IT", "UY"}
    assert years == {"birth_year": 1931, "death_year": 2017}


def test_santiago_cardenas_short_and_full_names_are_one_living_artist():
    """El sufijo Arroyo no crea otro ID y 2006 no era una muerte."""
    artist_master.reset_caches()
    try:
        short = artist_master.resolve_artist("Santiago Cárdenas")
        full = artist_master.resolve_artist("SANTIAGO CARDENAS ARROYO")
        years = artist_master.artist_years("santiago_cardenas")
        master = artist_master.load_master()
    finally:
        artist_master.reset_caches()
    assert short["artist_id"] == full["artist_id"] == "santiago_cardenas"
    assert "santiago_cardenas_arroyo" not in master
    assert years == {"birth_year": 1937, "death_year": None}


def test_giuseppe_maraschini_house_typo_resolves():
    artist_master.reset_caches()
    try:
        resolved = artist_master.resolve_artist("Guiseppe MARASCHINI")
        years = artist_master.artist_years("giuseppe_maraschini")
    finally:
        artist_master.reset_caches()
    assert resolved["artist_id"] == "giuseppe_maraschini"
    assert resolved["artist_country_birth"] == "IT"
    assert years == {"birth_year": 1839, "death_year": 1903}
