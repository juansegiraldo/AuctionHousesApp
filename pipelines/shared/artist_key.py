"""Clave canonica y tipo de autoria para nombres de artista.

Funciones puras, sin I/O. Es el unico sitio donde se decide como se pliega un
nombre y que tipo de autoria declara la casa, para que Silver y Gold no puedan
divergir (mismo principio que pipelines/shared/fx.py con las tasas).

Bug que corrige este modulo:
    pipelines/enrichments/artist_canonicalize.py hacia
        re.sub(r"[^a-z0-9\\s]", "", nombre.lower())
    sin normalizacion Unicode, asi que los acentos se BORRABAN en vez de
    plegarse: "Joan Miro'" -> "joan mir", "A'lvaro Barrios" -> "lvaro barrios".
    Solo colapsaba 15.199 nombres crudos a 14.727. Con NFKD baja a ~14.207 y,
    sobre todo, une las 4 grafias de "Agustin Ubeda" (368 lotes que hoy salen
    partidos en 4 filas del ranking).

Regla de diseno: el fold AGRUPA, no identifica. "Francisco Toledo" son dos
personas reales distintas y comparten fold. Por eso el maestro de artistas se
clava en alias explicitos (ver pipelines/shared/artist_master.py) y el fold solo
sirve para agregar y para PROPONER alias. El fold nunca concede un pais.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

# Tipos de autoria posibles. Solo "autor" entra en el ranking de artistas.
ATTRIBUTION_TYPES = (
    "autor",
    "escuela",
    "circulo",
    "taller",
    "seguidor",
    "copia",
    "atribuido",
    "anonimo",
    "no_autor",
    "desconocido",
)

# Un nombre plegado de <= 3 caracteres no identifica a nadie. En los datos reales
# son 64 nombres ("J", "S", "*A", "s.a") que arrastran 785 lotes.
MIN_FOLD_LENGTH = 4

# Un "nombre" de mas de 60 caracteres no es un nombre: son 430 casos donde el
# scraper metio un parrafo entero (titulos de libro, descripciones de cartel).
MAX_NAME_LENGTH = 60

# Prefijos sobre el FOLD (ya sin acentos), por eso no hace falta duplicar
# "circulo de"/"ci'rculo de" como pasaba en ARTIST_NOISE_PREFIXES.
_PREFIX_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("escuela", ("escuela ",)),
    ("taller", ("taller de", "taller del")),
    ("circulo", ("circulo de", "circulo del")),
    ("seguidor", ("seguidor de", "maestro de", "escuela de")),
    ("copia", ("copia de", "segun ", "a la manera de")),
    ("atribuido", ("atrib", "attrib")),
)

# Ficha bibliografica de Bogota: el scraper metio en artist_name el campo
# "Ciudad" de la ficha del libro ("Ciudad Bogotá", "Ciudad Paris"), a veces con
# la ficha entera detras ("Ciudad Bogotá Editorial Imprenta de la Luz Piezas 1
# Tamaño Octavo mayor..."). Son 144 lotes en 28 variantes, todas 'Ciudad' mas un
# toponimo.
#
# No basta el prefijo "ciudad ": "Ciudad Real, Antonio" es un apellido espaniol
# legitimo, y la coma delata la forma "Apellido, Nombre" de una persona.
#
# Pero la ficha tambien escribe "Ciudad Bogotá, Colombia" y "Ciudad Cádiz,
# España", que llevan coma y NO son personas. Lo que las separa es lo que va
# detras: un pais o una ciudad conocidos, no un nombre de pila. Por eso se
# admite la coma solo cuando la cola esta en esta lista cerrada.
#
# Se comprueba sobre el nombre ORIGINAL porque artist_fold() quita la puntuacion.
_CITY_TAIL = (
    "colombia|espana|españa|suiza|francia|italia|alemania|inglaterra|"
    "reino unido|mexico|méxico|argentina|cuba|peru|perú|chile|uruguay|"
    "venezuela|ecuador|brasil|portugal|holanda|belgica|bélgica|"
    "paris|parís|madrid|barcelona|bogota|bogotá|londres|roma"
)
_CITY_FIELD_RE = re.compile(
    rf"^\s*ciudad\s+(?:[^,]*|[^,]*,\s*(?:{_CITY_TAIL})\s*\.?)$",
    re.IGNORECASE,
)

# Marcas de obra sin autor identificable, en cualquier posicion del fold.
_ANONYMOUS_MARKERS = (
    "anonimo",
    "anonima",
    "vv aa",
    "vvaa",
    "varios autores",
    "autor desconocido",
    "sin firma",
)

# El nombre ES el tipo de objeto o el titulo generico de la obra: el scraper
# metio ahi la descripcion del lote. Se comparan por IGUALDAD con el fold
# completo, nunca por prefijo ni por 'contiene': hay artistas reales apellidados
# Marina, Rivera o Prado, y "Paisaje de Toledo" como titulo no convierte en ruido
# a quien lo firma. En los datos reales son 467 lotes en 32 terminos, y hoy
# entran en el ranking de artistas como si fueran autores.
#   artist_name='Collar'  lot_title='Collar, década de 1990'   (Bogota, joyeria)
#   artist_name='Cartel'  lot_title='Cartel ...'               (Duran, carteles)
_OBJECT_NAMES = frozenset(
    {
        # Joyeria y moda (Bogota).
        "collar", "cinturon", "vestido", "pendientes", "anillo", "pulsera",
        "broche", "reloj", "sortija", "abrigo", "bolso", "chaqueta", "aretes",
        # Mobiliario y artes decorativas.
        "consola", "alfombra", "alfombra persa", "tapiz", "silla", "mesa",
        "mesa de centro", "bandeja", "copa", "espejo", "jarron", "plato",
        "caja", "lampara", "florero",
        # Titulos genericos usados como nombre de artista.
        "cartel", "sin titulo", "paisaje", "bodegon", "composicion", "desnudo",
        "marina", "retrato", "abstracto", "maternidad", "fotografia",
        "escultura", "busto", "figura",
    }
)

# Parentesis biografico final: "Ever Astudillo (Colombia, 1948 - 2015)".
# Se recorta ANTES de mirar si hay digitos, porque si no 552 nombres que si son
# artistas caerian en no_autor y perderiamos justo los que llevan el pais dentro.
_TRAILING_PAREN_RE = re.compile(r"\s*\([^()]*\)\s*$")

# Variante de Bogota sin parentesis: "Edgar Negret - Colombia, 1920-2012."
_TRAILING_DASH_BIO_RE = re.compile(r"\s*[-–]\s*[^-–]*\d{4}[^-–]*\.?\s*$")

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_DIGIT_RE = re.compile(r"\d")


def _strip_accents(text: str) -> str:
    """Pliega acentos a su letra base via NFKD (o' -> o, a` -> a)."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def strip_biography(name: str) -> str:
    """Quita el parentesis/guion biografico final de un nombre.

    "Ever Astudillo (Colombia, 1948 - 2015)" -> "Ever Astudillo"
    "Edgar Negret - Colombia, 1920-2012."    -> "Edgar Negret"

    Se aplica en bucle porque hay nombres con dos parentesis encadenados.
    """
    previous = None
    current = name.strip()
    while previous != current:
        previous = current
        current = _TRAILING_PAREN_RE.sub("", current).strip()
        current = _TRAILING_DASH_BIO_RE.sub("", current).strip()
    return current


def artist_fold(name: Optional[str]) -> Optional[str]:
    """Clave de agrupacion deterministica para un nombre de artista.

    Pasos, en este orden y cada uno justificado por los datos reales:
      1. NFKD + descarte de combinantes -> "Miro'"/"Tapies`" pliegan bien.
         AQUI muere el bug de artist_canonicalize.py.
      2. casefold() -> fusiona los 681 nombres en MAYUSCULAS.
      3. Todo lo que no sea [a-z0-9] pasa a espacio y se colapsa -> une
         "Garcia-Ochoa" con "Garcia Ochoa" y los 32 nombres con doble espacio.
      4. None si queda vacio o demasiado corto para identificar a nadie.

    NO invierte "Apellido, Nombre": ver propose_inversion(), que es una
    sugerencia sujeta a revision humana, no una regla automatica.

    Devuelve None cuando no hay clave utilizable, nunca una cadena vacia.
    """
    if not name:
        return None
    folded = _strip_accents(name).casefold()
    folded = _NON_ALNUM_RE.sub(" ", folded).strip()
    if len(folded) < MIN_FOLD_LENGTH:
        return None
    return folded


def attribution_type(name: Optional[str]) -> str:
    """Clasifica QUE tipo de autoria declara la casa para este nombre.

    Se calcula una sola vez en Silver (pipelines/silver/artist_resolve.py) y
    sustituye a is_noise_artist() de build_insights.py, que hacia un match de
    prefijo sobre el nombre en minusculas SIN plegar acentos: por eso la lista
    tenia que llevar "circulo de" y "ci'rculo de" por separado y cualquier
    variante acentuada nueva se colaba en el ranking.

    Solo "autor" entra en el ranking de artistas. En los datos reales unos 9.400
    lotes NO son de un autor identificable (6.214 de "Escuela *", 308 anonimos,
    mas muebles y titulos de libro que el scraper metio en artist_name).
    """
    if not name or not name.strip():
        return "desconocido"

    raw = name.strip()

    # El parentesis biografico se recorta antes de cualquier heuristica de
    # longitud o digitos: "Ever Astudillo (Colombia, 1948 - 2015)" es un autor.
    core = strip_biography(raw)
    fold = artist_fold(core)

    if fold is None:
        # Nombres de una o dos letras ("J", "*A", "s.a"): 785 lotes.
        return "no_autor"

    for label, prefixes in _PREFIX_RULES:
        if any(fold.startswith(prefix) for prefix in prefixes):
            return label

    if any(marker in fold for marker in _ANONYMOUS_MARKERS):
        return "anonimo"

    # Igualdad exacta contra el fold entero: "Collar" es ruido, "Ana Collar" no.
    if fold in _OBJECT_NAMES:
        return "no_autor"

    # Campo "Ciudad" de la ficha del libro, no una persona.
    if _CITY_FIELD_RE.match(core):
        return "no_autor"

    # Ya sin biografia, un digito restante delata un titulo o un lote agrupado
    # ("Colonia: 10 obras", "11 Postales Transporte y Hoteles").
    if _DIGIT_RE.search(core):
        return "no_autor"

    # Parrafos enteros en el campo de artista.
    if len(core) > MAX_NAME_LENGTH:
        return "no_autor"

    return "autor"


def propose_inversion(name: Optional[str]) -> Optional[str]:
    """Propone la forma directa de un "Apellido, Nombre". Solo para revision.

    "GARCIA OCHOA, LUIS" -> "Luis Garcia Ochoa" (fold: "luis garcia ochoa")

    En los datos hay 3.085 nombres con coma y 281 de ellos colisionan con un
    artista ya existente: fusionarlos vale cientos de lotes. Pero NO se hace
    automaticamente ni entra en artist_fold(), porque "Garcia Marquez, Gabriel"
    (51 lotes) es un escritor en lotes de libros, no un pintor. Esto alimenta a
    scripts/artist_master_propose.py; la decision la toma una persona.

    Devuelve None si el nombre no tiene exactamente una coma util.
    """
    if not name:
        return None
    core = strip_biography(name.strip())
    parts = [p.strip() for p in core.split(",")]
    if len(parts) != 2 or not all(parts):
        return None
    surname, given = parts
    return artist_fold(f"{given} {surname}")
