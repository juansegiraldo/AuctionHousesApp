# Maestro de artistas

Fuente unica de la identidad del artista y de su pais. Curado a mano y
versionado en git — por eso vive aqui y no en `data/`, que esta entero en
`.gitignore`.

Lo lee `pipelines/shared/artist_master.py`, que a su vez usa
`pipelines/silver/artist_resolve.py`. Mismo patron que `pipelines/config/fx.yaml`.

## Estado actual (2026-08-18)

**3.524 artistas poblados**, que resuelven **26.034 lotes con pais (61,8% de los
lotes que tienen autor)**. En el ranking, **2.386 de 9.769 artistas (24,4%)
cubren el 89,79% del ingreso atribuido a artistas**. Las dos coberturas se
publican juntas: la primera mide trabajo pendiente y la segunda, su importancia
economica.

Completitud de las fichas: **85,5% con pais**, **72,1% completas** (pais +
nacimiento + muerte-o-`living`).

La cobertura **exhaustiva** es aparte y va al 100%: los **12.893 folds de autor**
del corpus estan todos contabilizados y clasificados por
`pipelines/gold/build_artist_master.py`. Un fold en `needs_web` es un hueco
visible con su flag puesto, no un olvido — ver "El ciclo de cobertura
exhaustiva" mas abajo.

Este es el historial de tandas, de mejor a peor fuente:

| Tanda | Altas | Lotes que aporta | Fuente |
|---|---|---|---|
| Hoja `Artistas` de `FINALL.xlsx` | 303 | +927 | curaduria manual (la de Lefebre) |
| Alias por inversion de coma | 93 alias | +228 | ninguna: union de variantes ya presentes |
| Investigacion en fuentes publicas | 140 | +2.050 | Wikipedia, Wikidata, Prado, Reina Sofia, MACBA, Artnet |
| Seudonimos de una palabra | 6 + 1 alias | +104 | Wikidata, Wikipedia |
| Huecos del top 200 por valor | 15 + 3 alias | +19 filas del top 200 | Prado, National Gallery, Wikidata, Banrepcultural, Bilbao Museoa |
| Parser `Autor` de Duran + reproceso dirigido | - | 710 autores recuperados de 721 lotes objetivo | ficha de detalle de la propia casa |
| Plan top 500 del 2026-08-16 | 96 altas, alias y 1 ID duplicado consolidado (neto +95) | +522 lotes con pais frente al snapshot; 495/500 del top con pais | museos, archivos, catalogos institucionales y ficha de la casa |
| Ciclo automatico Wikidata del 2026-08-18/19 | 2.221 altas + 450 `death_status` + 68 falsos autores retirados | +4.578 lotes con pais | Wikidata (P19->P17->P297), 16.049 nombres consultados, promocion revisada ficha a ficha |

### La tanda del top 200: bajar el corte a 1 lote cambia que hay que investigar

Con `MIN_LOTS_FOR_ARTIST_RANK = 1` entran al ranking artistas de un solo lote, y
el top 200 por ingresos se llena de nombres carisimos con **una** venta que antes
no llegaban al corte. De los 20 huecos que aparecieron:

- **2 no eran artistas**, sino el titulo de la obra (ver abajo).
- **3 ya estaban en el maestro** y solo les faltaba el alias: `Oswaldo Guaysamín`
  (errata de Duran, sin la segunda "a"), `Salvatore Mangione (Salvo)` y
  `ANDRES DE SANTAMARIA` (Lefebre escribe el apellido junto y sin tildes).
  Cero investigacion, tres artistas que rankeaban partidos.
- **15 se investigaron** y los 15 se verificaron con fuente concreta.

Lo que rindio, otra vez, no fue rellenar huecos sino **corregir lo obvio**:

| Artista | Se diria | Nacio en | Por que importa |
|---|---|---|---|
| Andres de Santa Maria | Belgica (murio en Bruselas) | `CO`, Bogota | Se formo y murio en Europa; es colombiano de nacimiento |
| Justiniano Asuncion | Espania (vende en Duran) | `PH`, Manila | Filipinas espaniolas: mercado espaniol, pintor filipino |
| Francisco Oller | Espania o EEUU | `PR`, Bayamon | ISO **si** codifica Puerto Rico; no hay que forzar `ES` ni `US` |
| Jan Anthonisz van Ravesteyn | Flandes | `NL`, La Haya | Es neerlandes del norte, no flamenco |
| Marten van Valckenborch | Belgica moderna | `BE`, Lovaina | Paises Bajos espanioles; el estado belga no existia |
| Paja Jovanovic | Austria (murio en Viena) | `RS`, Vrsac | Imperio austriaco entonces, Serbia hoy |

Dos entradas quedaron en `confidence: medium` a proposito: **Tamara de Lempicka**
(el nacimiento se disputa a tres bandas — Varsovia, San Petersburgo o Moscu segun
la fuente; `PL` es consenso, no hecho) y **Juan de Juanes**, donde la ficha de la
casa da 1523 y el consenso academico es c.1503-1505, sin partida posible porque
los libros bautismales de Fuente la Higuera empiezan en 1535.

Y tres alias se dejaron **sin** fusionar aunque el fold invitaba:
`Seguidor de Juan de Arellano` (obra de seguidor, como `Despues de Pablo
Picasso`), `Cesar del Valle` frente a `Evaristo Valle`, y
`Navas Sanz de Santamaria, Pablo` frente a Andres de Santa Maria.

La tercera tanda ataco los artistas con mas lotes que seguian sin resolver, casi
todos pintores espanioles del XIX-XX de Duran. De **176 fichas investigadas se
verificaron 140 y se descartaron 36**: esas 36 se quedan sin pais a proposito.

### Seudonimos: un solo nombre tambien es una persona

`Jano`, `Marola`, `Serny`, `Monir`, `Rembrandt`, `Durero` y `Guinovart` parecian
ruido de una sola palabra y son artistas con seudonimo o forma corta:

| En el catalogo | Quien es | Nace en |
|---|---|---|
| `Jano` | Francisco Fernandez-Zarza Perez, cartelista | `ES` |
| `Marola` | Manuel Rodriguez Lana, de Gijon | `ES` |
| `Serny` | Ricardo Summers Ysern | `ES` |
| `Monir` | Monir Shahroudy Farmanfarmaian | `IR` |
| `Durero` | Albrecht Durer, en su forma castellanizada | `DE` |
| `Guinovart` | alias corto de `josep_guinovart`, **no** una entrada nueva | `ES` |

El `birth_year` del propio dato de subasta confirmo cada uno (Jano 1922, Marola
1905, Serny 1908, Durero 1471, Rembrandt 1606, Guinovart 1927).

**`*Mingorance` se quedo fuera a proposito.** El maestro ya tiene a Manuel
Mingorance Acien (1937-2011) y las fuentes traen ademas a Juan Eugenio Mingorance
Navas (1906-1979): dos personas. Sus 10 lotes no llevan anio con el que
desempatar, asi que siguen sin pais. Es el caso "Francisco Toledo" del que habla
la regla 2, y hay un test que lo fija.

El resto queda en `artist_resolution: fold_only` sin pais, y el informe publica la
cobertura real en vez de aparentar que esta completo.

Para seguir poblando: `python scripts/artist_master_propose.py --min-lots 3` y
revisar por shard. La curva de cobertura tiene rendimientos decrecientes fuertes
a partir de ~2.000 artistas (el 62,6% de los nombres aparece una sola vez).

### El pais es el de NACIMIENTO, y ahi esta el valor de investigar

Lo que mas rinde de buscar en fuentes reales no es rellenar huecos, es corregir
lo que una heuristica habria dado por obvio. Todos estos venden en Duran, mercado
espaniol, y ninguno nacio en Espania:

| Artista | Nace en | Detalle |
|---|---|---|
| Carlos Saenz de Tejada | `MA` | Tanger |
| Theophile A. Steinlen | `CH` | Lausana; toda su obra es de Paris |
| Jose Pinazo Martinez | `IT` | Roma, con el padre becado; familia valenciana |
| Joan Gardy Artigas | `FR` | Boulogne-Billancourt; ceramista de familia catalana |
| Arturo Peyrot | `IT` | Roma; murio en Madrid |
| Grete Stern | `DE` | Elberfeld; se la asocia a Argentina, donde emigro |

Hay un test (`test_birth_country_is_not_the_market_country`) que los fija. Es la
misma regla que prohibe usar `HOUSE_COUNTRY` como nacionalidad.

### Lo que hubo que corregir de la hoja curada

Una fuente curada a mano tampoco entra tal cual. Al cargar esas 303:

- **29 artistas sin pais se descartaron** (`Pais_Clean: Unknown`) en vez de darlos
  de alta vacios. Un artista que falta se puede anadir; uno dado de alta sin pais
  ensucia el maestro y ya no lo propone el script.
- **Los duos y colectivos van sin fechas.** `Fernando Pareja y Leidy Chavez` trae
  1979 y 1984 en la hoja: son los dos NACIMIENTOS, no un nacimiento y una muerte.
  Darlos por buenos habria publicado a una artista viva como muerta en 1984. Se
  detectan por ` y `, `&` o `/` en el nombre y se les quitan las fechas, no el pais.
- **4 fichas traian fechas imposibles** (muerte <= nacimiento) porque el serial de
  Excel se convirtio en 1904/1905, su epoch. Se descarta la fecha, se conserva el pais.
- **`display_name` no se copia de la hoja**, que esta entera en MAYUSCULAS. Se toma
  la variante bien capitalizada que ya usa alguna casa (262 de 303) y solo si no
  existe se capitaliza, respetando particulas (`de`, `del`, `y`) e iniciales sueltas.

### Los alias por inversion: 228 lotes sin investigar nada

93 variantes tipo `ALCALDE, JUAN` apuntaban a artistas que **ya estaban** en el
maestro (`juan_alcalde`), solo que sin ese alias. El fold no invierte por su
cuenta a proposito, asi que hasta anadirlos el artista salia dos veces en el
ranking y la mitad de sus lotes se quedaba sin pais. Entre ellos
`MIRÓ FERRÁ, JOAN` -> Joan Miro y `GOYA Y LUCIENTES, FRANCISCO DE` -> Goya.

Se revisaron uno a uno comprobando que el anio de nacimiento no se contradijera
(0 conflictos). **`García Márquez, Gabriel` sigue sin fusionarse**: son 55 lotes
de libros del escritor, y es el contraejemplo que justifica que esto se revise a
mano en vez de aplicarse por regla. Hay un test para cada cosa.

### Lo que NO es un artista

El scraper metio el tipo de objeto en `artist_name` en 467 lotes, y contaban como
autores: `Cartel` (85 lotes) rankeaba por delante de artistas reales, junto a
`Collar`, `Cinturón`, `Florero` o `"Paisaje"`. Se filtran en
`pipelines/shared/artist_key.py` (`_OBJECT_NAMES`), que es donde vive esa
clasificacion, no en el maestro.

La comparacion es **por igualdad con el fold entero**, nunca por `contiene`: hay
artistas reales apellidados Rivera, Marina, Mesa o Prado, y un `in` los habria
borrado del ranking en silencio. Un test lo fija.

Lo mismo pasa con el campo **`Ciudad` de la ficha bibliografica** de Bogota:
`Ciudad Bogotá` era el segundo "artista" con mas lotes de todo el dataset (144
lotes en 28 variantes). Ahi la regla si va por prefijo, porque a veces arrastra
la ficha entera detras (`Ciudad Bogotá Editorial Imprenta de la Luz Piezas 1...`),
pero con dos cautelas que costaron dos iteraciones:

- **`Ciudad Real, Antonio` es un apellido espaniol**, asi que la coma excluye.
- ...salvo que detras venga un pais o ciudad conocidos (`Ciudad Cádiz, España`),
  que son 4 lotes que si son ficha. De ahi la lista cerrada `_CITY_TAIL`.

### El titulo de la obra en el campo del artista: 721 lotes

Duran publica el lote como `"Madre Superiora". Oleo sobre lienzo. 130 x 99...` y
`_infer_artist_from_title()` (en `scraping/houses/duran_subastas/parsers.py`)
**corta por el primer punto** y se queda con el titulo entrecomillado como
artista. Son **721 lotes en 452 variantes**, y no es ruido barato:

- `"Madre Superiora"` rankeaba **el puesto 39 del top 200 con 120.000 EUR** — y
  es un **Botero**: la ficha de detalle dice `BOTERO, FERNANDO (1932 - 2023)` y
  la descripcion cita un certificado firmado por el propio Botero.
- `"Vendedoras de frutas"` (40.000 EUR) es de **Alvaro Alcala Galiano**, que
  ademas estaba en la misma lista de huecos con su nombre bien escrito: el mismo
  artista rankeaba dos veces, una de ellas bajo el titulo de su cuadro.

Se filtra en `pipelines/shared/artist_key.py` (`_QUOTED_TITLE_RE`), donde vive
esa clasificacion, no en el maestro: un titulo de obra **no puede ser un alias**,
porque el alias afirma identidad y aqui lo unico cierto es que ese texto *no* es
una persona.

**La regla exige que TODO el nombre sea el entrecomillado, no que empiece por
comilla.** Hay 29 lotes tipo `"Au merite" art nouveau. Henri Louis Levasseur`,
`"Marina" Segrelles` o `"Retrato femenino" Juan Cardona` donde el artista real
va **detras** del titulo; un match por prefijo los habria borrado. Es la misma
cautela que la coma de `_CITY_FIELD_RE` con `Ciudad Real, Antonio`. Hay un test
para cada mitad de la regla.

**El parche por `lot_url` ya esta retirado.** El parser de Duran prioriza ahora
el campo `autor` de la ficha y el output crudo fue regenerado. El fichero
[`_lot_author_fixes.yaml`](_lot_author_fixes.yaml) se conserva vacio como punto
de compatibilidad para `load_lot_author_fixes()`; no se deben anadir excepciones
ni convertir titulos de obras en aliases del maestro.

El reproceso fue dirigido a los **721 lotes** afectados: **710** devolvieron un
`Autor` real y **11** fichas validas no publicaban autor. Tras reconstruir toda
la cadena, Fernando Botero conserva **36 lotes ofrecidos, 33 vendidos y
731.589,80 EUR**; el lote 504-154 llega a Silver como `BOTERO, FERNANDO`, no
como `"Madre Superiora"`. El ingreso total del corpus sigue exactamente en
**37.575.775,80 EUR**.

### Cierre del top 500

Despues de limpiar 34 nombres que eran objetos/documentos, incorporar las
inversiones de coma seguras e investigar cada candidato con fuente concreta,
**495 de las 500 primeras filas tienen pais**. Los cinco huecos restantes son
deliberados: Jose Taviel de Andrade no tiene lugar de nacimiento verificable;
Juan de la Abadia "El Viejo" y Juan I de la Abadia no permiten fijar pais de
nacimiento con seguridad; Garcia Marquez, Gabriel y Duran y Diaz, Joaquin (ed.)
siguen la politica documentada de no borrar autores/editoriales mediante una
heuristica de forma. Un hueco verificable es preferible a un pais inventado.

### Lo que se decidio NO filtrar

**Los autores de libros se quedan.** 2.528 lotes tienen el patron
`Autor : Titulo` en `artist_raw` con el nombre invertido, y entre ellos estan
Garcia Marquez (55), Bolivar (19) o Humboldt (14), que no son pintores. Pero el
mismo patron lo cumplen **Antonio Caro, Beatriz Gonzalez y Ana Mercedes Hoyos**,
que si lo son.

Se probaron dos senales para separarlos y ninguna aguanta: `medium` esta vacio en
los escritores pero es estadistico, no determinista; y `category_tag` clasifica a
Humboldt como `prints` por los grabados de sus libros. Sin senal fiable, filtrar
habria borrado artistas reales, que es peor que dejar entrar a unos escritores.

## El ciclo de cobertura exhaustiva

El maestro curado (~1.086 fichas) nunca va a cubrir por si solo los 12.961 folds
de autor del corpus, y fingir lo contrario era el riesgo real. El ciclo separa
**contabilizar** de **afirmar**, que son dos cosas distintas:

| Paso | Que hace | Que NO hace |
|---|---|---|
| `python -m pipelines.gold.build_artist_master --write-review-queue` | Clasifica **el 100%** de los folds de autor en `verified` / `needs_web` / `needs_review` / `ambiguous` y escribe la cola en `pipelines/config/artist_review/` | No promueve texto de catalogo a identidad |
| `python scripts/artist_master_web_research.py` | Busca en Wikidata cada fold marcado `needs_web_research` y escribe un diario de evidencia con `auto_promote: false` | No toca los shards YAML |
| `python scripts/artist_master_promote.py --report` | Convierte en fichas YAML **solo** la evidencia inequivoca, para revisar y pegar | No escribe en `pipelines/config/artists/` |

Asi el "100%" significa **contabilizado y clasificado**, no "promovido sin
pruebas". Un fold en `needs_web` es un hueco visible con su flag puesto, que es
exactamente lo que la regla 1 pide.

### Por que el promotor descarta tanto, y por que eso es el resultado

Sobre las primeras 108 fichas investigadas el promotor propuso **0 altas**: 47
descartes por `already_in_master` (la cola prioriza por volumen de lotes, y los
artistas de mas lotes ya estaban curados a mano), 24 por `status_ambiguous` y 5
por `status_not_found`. No es un fallo del promotor: es la prueba de que el
maestro ya cubre la cabeza de la distribucion y que lo que queda es cola larga.

Los motivos de descarte son la parte util del informe:

| Motivo | Que significa |
|---|---|
| `already_in_master` | Ya curado a mano; el promotor jamas pisa una ficha existente |
| `status_ambiguous` | Dos o mas humanos con el mismo nombre exacto. **No se desempata por popularidad** — es el caso `Francisco Toledo`, dos personas reales |
| `no_artistic_occupation` | Wikidata lo documenta como escritor, futbolista, politico... Es el caso `García Márquez, Gabriel`, el nombre nº1 por lotes entre los no curados: 55 lotes de libros no hacen un pintor |
| `not_an_author` | Red de seguridad: el nombre es un objeto o una escuela |
| `alias_already_claimed` | Regla 3: un alias solo puede pertenecer a un artista |

### La fusion la afirma Wikidata, no el promotor

Dos grafias del catalogo pueden tener folds distintos y ser la misma persona:
Duran vende **`Ouka Leele` (12 lotes) y `Ouka Lele` (11 lotes)**, que difieren
solo en la doble ele. Llegan como dos filas de la dimension y Wikidata resuelve
las dos al mismo `Q440610`.

El promotor las fusiona **por `wikidata_id`, no por parecido del nombre**: ahi
la identidad la afirma la fuente, que es la unica base admisible segun la regla
2. Sin esa fusion la artista rankearia partida y la mitad de sus lotes se
quedaria sin pais — el mismo defecto que arreglan los alias por inversion.

Cuidado con la asimetria que esto destapa: `Ouka Leele` **ya estaba** en el
maestro con pais `ES`, pero `Ouka Lele` no resolvia. No es un alta, es un alias
que falta, que es la tanda de mejor relacion esfuerzo/resultado. Dos QID
distintos que reclaman el mismo nombre **no** se fusionan: son el caso
`Francisco Toledo`, dos pintores reales.

### `_countries.yaml` crece cuando aparece un pais nuevo, y la puerta avisa

Una tanda dio de alta a Gary Tricker con `NZ` y `validate_master()` fallo:
Nueva Zelanda no estaba en la tabla. **Ese fallo es el sistema funcionando**, no
un estorbo — es el bucle de retroalimentacion que el README describe para que
`_countries.yaml` no se pudra como paso con `houses.yaml`.

Al anadir un pais hay que tocar las tres partes: el codigo en `countries:` (con
`es` y `demonym_es`) y sus alias en espaniol e ingles, para que
`normalize_country()` resuelva tanto "Nueva Zelanda" como "New Zealand".

### Paises Bajos no tenia pais: el `P297` deprecated

Un caso que costo encontrar y explica un hueco entero del maestro. El salto
P19 -> P17 -> P297 descarta las declaraciones marcadas `deprecated`, que es lo
correcto en general. Pero **Wikidata marca como deprecated el `P297: NL` de los
Paises Bajos** (`Q55`), asi que Haarlem, La Haya, Amsterdam y Delft se quedaban
sin pais... y con ellos **todos los pintores neerlandeses del corpus**:
Adriaen van Ostade, Egbert van der Poel, Ary Scheffer, Mathias Withoos.

Ahora el codigo deprecated se usa **solo como respaldo**, cuando el pais no
aporta ninguno normal. El orden importa: si se aceptara siempre, Minsk volveria
a tener `SU` compitiendo con `BY` y se reintroducirian los estados historicos
por la puerta de atras. Hay un test para cada mitad.

Recupero **18 fichas** de golpe. La leccion util: cuando un hueco afecta a un
pais entero y no a artistas sueltos, la causa esta en la tabla de paises o en la
forma de leerla, no en los artistas.

### Un nombre de UNA palabra que solo casa con un ALIAS no acredita identidad

El catalogo publica **`Ángeles`** y Wikidata lo caso con **Peter Angelis**,
pintor flamenco de 1685: el match es tecnicamente correcto (Wikidata lista
`Angeles` como alias suyo) y la conclusion, falsa — en un catalogo espaniol
`Ángeles` es un apellido.

La guarda exige que un nombre de una sola palabra case con el **label**, no solo
con un alias. Descarto **32 fichas**, y la lista deja claro por que hacia falta:
`Shakspeare` → William Shakespeare, `ANDELU` → Händel, `Londres` → Albert
Londres, `Alexanco` → un futbolista, `Arvizu` → el bajista de Korn.

**No es una regla que se pueda aplicar sola.** Entre esas 32 hay tambien
`Besler` → Basilius Besler, `Blaeu` → Joan Blaeu, `Cavanilles` y `Cirlot`, que
si son la persona. Por eso van a revision manual en vez de descartarse para
siempre: son 32 casos, un volumen que una persona puede juzgar.

### Los duplicados no siempre rompen la carga, y esos son los peligrosos

`load_master()` falla ruidosamente cuando dos fichas comparten alias (regla 3),
pero **dos fichas de la misma persona con nombres distintos no chocan**: cargan
bien, parten los lotes del artista en dos filas del ranking y pueden publicar
dos fechas de nacimiento diferentes.

Un barrido por **mismas fechas + un nombre contenido en el otro** encontro 16,
entre ellos **Salvador Dali** (`salvador_dali` / `salvador_dali_i_domenech`) y
**Jesus Rafael Soto**. Tambien `Palazuelo` / `Pablo Palazuelo`, que una tanda
automatica creo el mismo dia.

Al consolidar gana **la ficha curada a mano**; la absorbida aporta sus alias y
solo rellena los campos que la otra no tenia. La discrepancia de fechas se anota
en `notes`, no se resuelve sola (Palazuelo: 1915 en Wikidata, 1916 en la ficha).

El barrido tiene falsos positivos obvios (`Alberto Dura` / `Alberto Magnelli`
solo comparten fechas), asi que **se revisa a mano**; la heuristica sirve para
encontrar candidatos, no para fusionar.

### Cuando parar: los tramos rentables se agotan, la cola no

La curva de rendimiento medida sobre 8.053 fichas investigadas, contando **solo
candidatos que siguen pendientes** (las ya integradas cambian de clave y, si se
cuentan, inflan artificialmente el tramo de 1 lote hasta un 74% imposible):

| Lotes del candidato | Investigados | Match | Pendientes hoy |
|---|---|---|---|
| 10 o mas | 816 | **58%** | **1** |
| 5 a 9 | 1.219 | 26% | **0** |
| 2 a 4 | 3.341 | 17% | 175 |
| 1 solo lote | 853 | 22% | **6.599** |

**Los tramos que rentaban estan agotados.** De los 6.775 candidatos que quedan,
**6.599 (97%) aparecen en un solo lote**: cada match añade un lote al corpus, y
mas de dos tercios devuelven `not_found` porque no existen en ninguna fuente
enciclopedica.

Seguir no esta prohibido — la cola se puede vaciar entera y el ciclo es
reanudable — pero hay que saber que a partir de aqui **se compra cobertura del
maestro, no cobertura del informe**. La cifra que importa (el ingreso cubierto,
87,57%) ya casi no se mueve con estas fichas.

### Tener ficha en Wikidata no acredita que la persona exista

**Pietro Psaier** es el caso que mejor delimita lo que un match automatico puede
afirmar. Wikidata tiene ficha (`Q3904190`) y el nombre casa exacto, asi que el
promotor le dio `IT, 1936-2004`. Pero el mundo del arte **discute que la persona
existiera**: se sospecha una identidad fabricada por marchantes para vender obra
atribuida a Warhol.

Ya se habia dado de alta y revertido antes; el ciclo automatico repitio el
mismo error el 2026-08-18. Lo detecto
`test_unverifiable_artists_keep_no_country`, que existia precisamente para eso.

La leccion es la frontera del metodo: **un match exacto acredita que la ficha
existe, no que la identidad sea real**. Por eso la decision vive ahora en codigo
(`DISPUTED_IDENTITIES` en el promotor) ademas de en el test — una decision
documentada solo en `notes` no protege contra una tanda automatica que crea
fichas nuevas.

### `death_status`: el hueco que no era un hueco

La meta pide pais **y fechas de nacimiento y muerte**, y el ano de muerte se
quedaba en el 66,9%. Pero la mayor parte de ese "hueco" no era dato ausente:
eran **artistas vivos**. Sin `death_status`, una ficha con `birth_year` y sin
`death_year` no distingue "sigue vivo" de "falta el dato", y el maestro solo
tenia el campo en el **0,5%** de las entradas.

De las 597 fichas con nacimiento y sin muerte:

| | |
|---|---|
| menores de 90 anios (casi seguro vivos) | 501 |
| entre 90 y 105 (dudoso) | 61 |
| **mayores de 105: ahi SI falta el dato** | **35** |

Una ficha de Wikidata que no publica `P570` es evidencia de que la persona vive,
y eso convierte el hueco en un dato afirmado. **334 fichas** quedaron marcadas
`living`, y la completitud (pais + nacimiento + muerte-o-vivo) subio del
**60,1% al 73,4%**.

Los mayores de `MAX_PLAUSIBLE_AGE` **no se marcan**: ahi lo probable no es un
supercentenario sino una ficha incompleta. Es la misma cautela que ya obligaba a
escribir "n. 1905 (?)" en el informe despues de publicar a Fidolo Gonzalez
Camargo con 96 anios y a Julia Acunia Guillen con 121.

### `artist_master_apply.py`: la unica pieza que escribe en los shards

Marcar 334 fichas a mano no es viable, asi que hay un aplicador — con un
contrato deliberadamente estrecho:

- **solo rellena huecos**: si el campo tiene valor, no lo toca ni para corregirlo
- **lista cerrada de campos** (`WRITABLE_FIELDS`): no puede tocar `aliases` ni
  `display_name`, que son afirmaciones de identidad
- `--dry-run` cuenta sin escribir; se ejecuta sobre la salida ya revisada de
  `--completions`

```powershell
python scripts/artist_master_promote.py --completions          # revisar
python scripts/artist_master_apply.py --field death_status --dry-run
python scripts/artist_master_apply.py --field death_status
```

Los shards **no llevan comentarios**, por eso `yaml.safe_dump` puede reescribir
el fichero entero sin perder informacion. Si alguna vez se anaden comentarios,
este script hay que rehacerlo con un editor que los preserve.

### Complementos: cerrar huecos de fichas que YA existen

Las fichas del maestro tambien se investigan, y `already_in_master` las
descartaba en bloque sin usar su evidencia. `--completions` lista los huecos que
la evidencia puede cerrar, para revisarlos y editarlos a mano.

Rinde poco y eso es buena senial: de **843 fichas matched ya curadas**, solo 14
tenian un hueco rellenable y **2 sobrevivieron a las guardas**. El maestro
curado esta mas completo de lo que parecia.

Las tres guardas, y las tres nacen de un caso real del propio maestro:

| Guarda | Caso |
|---|---|
| `death_status: living` nunca recibe `death_year` | publicar como muerto a alguien vivo es el peor error del informe |
| Un nacimiento muy distinto al de la ficha **no complementa** | es el homonimo otra vez; se reutiliza `MAX_BIRTH_YEAR_DRIFT` |
| Un hueco **deliberado** no se rellena | Sebastian de Llanos y Valdes lleva escrito *"Se omiten los anios por discrepancia"*: el hueco es una decision documentada, no un olvido |

Esa ultima guarda es la que mas importa: filtro de 5 complementos a 2, y los 3
que quito contradecian a una persona que ya habia mirado el caso. Se detecta por
marcadores en `notes` (`se omite`, `discrepanc`, `sin verificar`,
`no verificable`).

### El duplicado que rompe el maestro entero: comparar tambien el display_name

Pegar fichas del promotor creo un `alexandre_theophile_steinlen` en `a.yaml`
cuando `theophile_alexandre_steinlen` **ya existia** en `t.yaml` con los mismos
datos (CH, 1859-1923). `load_master()` dejo de cargar y **36 tests cayeron a la
vez**: la regla 3 haciendo su trabajo, fallando pronto y ruidosamente.

El fallo estaba en el promotor: comparaba el `artist_id` y los alias del
catalogo, pero el catalogo publica el nombre **invertido** y el `display_name`
que devuelve Wikidata tiene fold distinto, asi que no chocaba con nada. Ahora el
`display_name` propuesto entra en la comparacion, y chocar con el maestro se
reporta como `already_in_master` (ya existe, quiza falte un alias) en vez de
como conflicto entre fichas nuevas.

**Antes de pegar una tanda, ejecutar siempre:**

```powershell
python -c "import sys; sys.path.insert(0,'.'); from pipelines.shared import artist_master as am; am.reset_caches(); print(len(am.load_master()), 'artistas,', len(am.validate_master()), 'problemas')"
```

### El catalogo de la casa es el desempate contra el homonimo

Un match exacto de nombre **no** garantiza que sea la misma persona. Contrastando
el anio de nacimiento que publica la casa con el de Wikidata aparecieron **27
discrepancias**, y las grandes son homonimos, no datos corregidos:

| Nombre | Catalogo | Wikidata |
|---|---|---|
| André Eugène | 1856 | **1959** |
| Federico Avrial | 1807 | 1870 |
| Julio Nieto | 1929 | 1964 |
| Antonio Molina Torres | 1917 | 1895 |

Es la trampa que documenta `docs/PLAN_MAESTRO_ARTISTAS.md`: buscar "Ricardo
Canals" devuelve un representante de futbolistas nacido en 1970, no al pintor de
1876. `MAX_BIRTH_YEAR_DRIFT` (15 anios) descarta esas fichas y tolera el
desacuerdo normal entre fuentes — Antonio Palacios es 1874 en Wikipedia y 1876
en la ficha de Duran, y esa si entra.

**Ojo al leer el diario:** el dato del catalogo viaja dentro de
`master_context`, no en el nivel superior. Leerlo del sitio equivocado devuelve
`None` y desactiva la guarda entera sin que falle nada.

### "Sin ocupacion declarada" no es evidencia de no ser artista

El filtro de ocupacion es lo que impide que un homonimo entre como pintor, y
sobre datos reales acierta: rechaza al **futbolista** Javier Sagarzazu, a un
exegeta, a una modista y a un actor, todos homonimos de nombres del catalogo.

Pero la primera version rechazaba tambien a **Costus** (el duo de pintores de la
Movida) y a **Jose Sancha**, y por un motivo distinto: su ficha de Wikidata **no
declara P106**. Descartar por *ausencia* de dato es borrar en silencio — la
regla 1 otra vez. Ahora hay tres veredictos:

| Veredicto | Que se hace |
|---|---|
| `artistic` | entra; puede llegar a `confidence: high` |
| `non_artistic` | se descarta (el futbolista) |
| `unknown` (sin P106) | **entra con `confidence: low`** y una nota pidiendo confirmar |

El arreglo recupero 37 fichas (los rechazos por ocupacion bajaron de 139 a 102)
y subio las promovibles de 566 a 589.

**La lista de QID se derivo del corpus, no de memoria.** Las primeras conjeturas
estaban mal: el corpus usa `Q1925963` para *artista grafico* y `Q329439` como
segunda forma de *grabador*, y `Q18074503` es *artista de instalaciones*, no
cartelista. Faltaban ademas `Q10373653` (acuarelista) y `Q715301`
(historietista). Si se amplia, sacar los QID de las ocupaciones que aparecen de
verdad en `artist_web_research.jsonl`.

### La limpieza de la cola: 68 falsos autores fuera en dos pasadas

Sobre los 412 nombres que Wikidata marca como no-humanos se hicieron **dos
pasadas revisadas a mano**, y el reparto final por tipo:

| Tipo | Ejemplos | Donde vive el filtro |
|---|---|---|
| Prendas y mobiliario | `Blazer`, `Hielera`, `Biombo`, `Bargueno`, `Cajonera` | `_OBJECT_NAMES` |
| Tecnicas y campos de ficha | `Oleo sobre lienzo`, `Obra grafica`, `Litografia`, `Varios` | `_OBJECT_NAMES` |
| Titulos genericos de obra | `Desnudo femenino`, `Nino Jesus`, `Cabeza de mujer` | `_OBJECT_NAMES` |
| Instituciones y publicaciones | `Banco de la Republica`, `Avianca`, `Museo del Prado`, `El Tiempo` | `_NON_ARTIST_AUTHORS` |

**Efecto medido:** los folds de autor bajaron de **12.961 a 12.893** (68 falsos
retirados) y la cobertura sobre lotes con autor subio del 59,8% al **60,2%** sin
investigar ni inventar un solo dato — solo dejando de contar como artistas
cosas que no lo son.

Las dos listas se mantienen separadas a proposito: `_OBJECT_NAMES` son cosas,
`_NON_ARTIST_AUTHORS` son entidades que **si** publicaron el documento del lote
(el Banco de la Republica emitio los billetes, `El Tiempo` el periodico). La
segunda documenta una decision editorial distinta.

**Lo que NO se filtro, y es la mitad importante del trabajo:** de los 160
candidatos revisados, la mayoria eran autores reales que la senial marcaba mal
— `CHILLIDA, EDUARDO`, `VASARELY, VICTOR`, `PALENCIA, BENJAMIN`,
`PALAZUELO, PABLO`, `HOGARTH, WILLIAM`, `MERCATOR, GERHARD`, `Equipo Realidad`,
`Estampa Popular`. Hay un test que fija que los 17 sobrevivan.

### 40 fichas con el anio EQUIVOCADO, y por que importan mas que un hueco

Un hueco es un resultado correcto; un anio equivocado se publica en el informe
y **nadie lo detecta leyendolo**. La carga del Excel curado dejo 40 fichas donde
el catalogo insiste en otra fecha, y el texto crudo le da la razon a la casa:

| Ficha | Maestro | Catalogo | Lotes |
|---|---|---|---|
| `alejandro_sanchez` | n.1945 | **n.1981** | 59 |
| `alberto_riano` | n.1920 | **1958-2006** | 34 |
| `nirma_zarate` | n.1969 | **1936-1999** | 13 |
| `maria_villa` | n.1972 | **1909-1991** | 6 |

`python scripts/artist_master_promote.py --year-conflicts` las lista. **No
corrige nada**: cada una se verifica a mano contra fuente antes de tocarla, la
misma disciplina del resto del ciclo.

El umbral (`MAX_CATALOG_YEAR_DRIFT`, 25 anios) distingue el error de dato del
desacuerdo normal entre fuentes — Antonio Palacios es 1874 en Wikipedia y 1876
en la ficha de Duran, y eso no es un conflicto. Y el catalogo tiene que
**insistir** (`MIN_LOTS_TO_CHALLENGE_MASTER`): un lote suelto puede llevar una
errata del scraper, varios ya son la ficha de la casa.

**Ojo con la lectura ingenua de la evidencia:** el primer analisis leyo esos
anios como fechas de MUERTE y salieron artistas muertos a los 11 y 19 anios.
Eran nacimientos, y el maestro era el que estaba mal.

### El anio de la casa desempata al homonimo que Wikidata deja abierto

Wikidata no elige entre dos homonimos, y hace bien. Pero **la casa publica el
anio de nacimiento**, y si de los candidatos solo uno lo cumple, la ambiguedad
desaparece: son dos fuentes independientes concordando, no una conjetura.

De **1.531 fichas `ambiguous`, 488 se desempatan asi** y aportaron 191 altas —
James Northcote, Ricardo Macarron, Esteban Vicente. El desempate exige un
**unico** candidato coincidente: si casan dos, o ninguno, la ficha se queda sin
resolver.

Entran con `confidence: medium`, nunca `high`: un homonimo resuelto por
concordancia no es una identidad sin dudas, y la nota deja escrito el anio que
sirvio de desempate.

**Trampa que aparecio aqui:** Wikidata devolvio `بابلو بيكاسو` como label de
Picasso y `Рихард Линднер` como el de Lindner. El `display_name` se PUBLICA en
el informe y lo compara el fold contra el catalogo, asi que un label en otro
alfabeto no puede ganar: `picasso` habria entrado como artista nuevo teniendo ya
`pablo_picasso`. Si el label no es latino, manda el nombre del catalogo.

### La senial determinista que SI sirve, y por que no se aplica sola

El repo prohibe filtrar por la forma del nombre, pero Wikidata da una senial
que no depende de como se escriba: si un nombre casa **exacto** con una entidad
que **no es humana** (`P31 != Q5`), el investigador lo registra en
`rejected_candidates` con `reason: not_q5_human`. Son **412 nombres unicos**.

Esa senial encuentra basura real — `Blazer`, `Blusa`, `Hielera`, `Gargantilla`,
`Mesa de comedor`, `Lentes de sol` — pero **aplicarla en bloque habria borrado a
Chillida**:

| Marcado no-humano | Que es en realidad |
|---|---|
| `CHILLIDA, EDUARDO` | el escultor; casa con una entidad de su obra |
| `VASARELY, VICTOR`, `PALENCIA, BENJAMÍN` | pintores de primera fila |
| `CALLOT, JACQUES`, `ORTELIUS, ABRAHAM`, `SEUTTER, MATTHAUS` | grabadores y cartografos: el nombre casa con su ATLAS, no con la persona |
| `Equipo Realidad`, `Los Carpinteros` | colectivos artisticos reales |

Por eso los 18 objetos entraron **uno a uno** en `_OBJECT_NAMES`, revisados a
mano, y hay un test que fija las dos mitades: que las prendas se filtren y que
Chillida, Vasarely, Callot y Equipo Realidad **sobrevivan**.

Un primer cribado util: los nombres que el maestro **ya reconoce** son falsos
positivos por definicion (asi salieron `Equipo Cronica`, `Serny` y
`Los Carpinteros`). El resto se mira a ojo.

### El ruido de la cola NO se filtra por la forma del nombre

La cola de investigacion consulta terminos que no son personas — `GRABADO`,
`Lámpara de escritorio`, `Coche bar`, `Diseño original`, `SCADTA` (una
aerolinea), `Davivienda` (un banco) — y la tentacion es escribir una regla que
los descarte antes de gastar la consulta. **No se hace**, por la misma razon que
los autores de libros se dejaron entrar.

De los 11.473 candidatos sin identidad, 783 son de **una sola palabra**, y esa
lista mezcla las dos poblaciones sin separacion posible por forma:

| Son artistas reales | Es ruido |
|---|---|
| `Anzo`, `Ceesepe`, `Doré`, `Costus`, `KAWS`, `Picasso` | `Blazer`, `Blusa`, `Hielera`, `AA.VV.`, `Barcelona` |

Una regla por longitud o por palabra clave borraria a Ceesepe y KAWS **en
silencio**, que es el fallo peor: un artista borrado no se ve en el informe, un
jarron que entra si. El coste del ruido es acotado (consultas gastadas, y el
resultado es `not_found`); el de borrar un artista real es irreversible.

Si algun dia se filtra, que sea sobre una **senal determinista del scraper**
(el campo del que salio el texto), nunca sobre el aspecto del nombre.

### Nunca dos corridas a la vez sobre el mismo diario

La noche del 2026-08-18 se lanzo un lote cuando el anterior aun no habia
terminado y ambos escribieron `artist_web_research.jsonl` a la vez. Resultado:
**71 lineas partidas a media URL**, todas concentradas entre la 8.970 y la
11.204 — justo el tramo solapado. Se perdieron ~36 fichas de 13.049; el resto
sobrevivio y esas se reinvestigan solas al reanudar.

La causa estaba en `append_jsonl`: el registro y su salto de linea iban en **dos
`write()` distintos**, y el otro proceso se colaba entre ambos. Ahora van en uno
solo. No es atomicidad formal, pero a este tamanio de linea el entrelazado deja
de ocurrir; hay un test que fija que sea un unico `write`.

**Aun asi, la regla operativa es no solapar corridas**: el diario es reanudable,
asi que encadenar lotes no cuesta nada y evita el problema de raiz. Antes de
lanzar uno nuevo, comprobar que no queda ningun `python` vivo.

### La cache HTTP crece hasta llenar el disco, y es desechable

`artist_web_research_cache.jsonl` guarda la respuesta **completa** de
`wbgetentities`, que trae todos los idiomas de cada entidad: llego a **2,6 GB
con 5.000 fichas investigadas** en un disco que estaba al 92%. Solo evita
repetir consultas ya hechas, asi que se puede borrar sin perder nada — el
resultado real es el diario `artist_web_research.jsonl`, que ocupa 11 MB.

Si una corrida se corta a mitad de escritura, la cache queda con una linea de
bytes invalidos. Eso **mataba la corrida siguiente**: `iter_jsonl` abria el
fichero en modo texto y el `UnicodeDecodeError` saltaba al iterar, antes del
`try`, de modo que ni `tolerate_bad_lines` lo atrapaba. Ahora se lee en binario
y se decodifica por linea, con un test para cada mitad.

**Antes de una corrida larga, comprobar el espacio libre y considerar borrar la
cache.**

### Reintentos: el `maxlag` de Wikidata se llevaba fichas de primera fila

En la corrida real **26 fichas se marcaron `error`**, 24 de ellas por `maxlag`,
y no eran nombres menores: **Picasso, Cruz-Diez, Portocarrero, Grete Stern y
Mariscal**. El motivo es sutil: el `lag` que declara el servidor es cuanto lleva
retrasado **ahora**, no cuanto tardara en recuperarse, asi que esperar
exactamente esa cifra reintentaba mientras el cluster seguia laggeado y agotaba
los intentos en segundos.

Se espera con margen (`MAXLAG_WAIT_FACTOR`) y nunca menos de `MIN_MAXLAG_WAIT`,
que es lo que la propia API pide. Los `error` se reprocesan con
`--retry-errors`; el diario guarda el ultimo estado de cada fingerprint, asi que
reanudar no repite lo ya resuelto.

### El techo de la investigacion automatica: Wikidata no conoce la cola larga

Medido sobre el segmento **no curado** de la cola (los 11.473 folds sin
identidad), la tasa de match cae a **3 de 12 (25%)** frente al **65%** de la
cabeza ya curada. La causa no es la calidad de la busqueda:

Se probo la hipotesis obvia — que los nombres en forma invertida
(`MARTINEZ TERRON,VICTORIANO`) fallaban por la coma — buscando ademas su
inversion. **No los rescata:** Martinez Terron y Guijarro Gutierrez siguen
`not_found` porque no estan en Wikidata, y `Serrano, Eduardo` o `Pérez, Felipe`
pasan a `ambiguous`, que tampoco promueve. La inversion por coma sirve para
**fusionar variantes de artistas que ya estan en el maestro** (esa tanda dio
+228 lotes), no para descubrir gente nueva.

La distribucion explica el techo:

| Lotes del candidato | Candidatos |
|---|---|
| 10 o mas | 50 |
| 5 a 9 | 781 |
| 2 a 4 | 3.299 |
| **1 solo lote** | **7.343 (64%)** |

Son pintores locales que vendieron una vez y que ninguna fuente enciclopedica
documenta. **Ese hueco no se cierra con mas busqueda automatica**, y forzarlo
inventando paises seria exactamente la corrupcion silenciosa que prohibe la
regla 1. Lo correcto es que sigan contabilizados en `needs_web` con su flag.

### El pais sale del lugar de nacimiento, resuelto en dos saltos

Wikidata publica el **lugar** (P19), no el pais, y `_countries.yaml` solo conoce
las ciudades grandes: `Barcelona` resuelve, `Oslo`, `Lausana` y `Manila` no. El
investigador da dos saltos — lugar → `P17` (pais) → `P297` (codigo ISO) — y ahi
hay una trampa que costo verificarla contra la API real:

**P17 lista todos los estados que gobernaron el sitio.** Oslo declara cuatro
(incluida la union con Suecia y el reino de Dinamarca y Noruega) y **Minsk
declara catorce**, del Rus de Kiev al Imperio ruso. Quedarse con el primero
publicaria un pais desaparecido. Por eso solo cuentan los que tienen ISO vigente
(`P297`), y si aun asi queda mas de uno se deja el hueco. `HISTORICAL_ISO` en el
promotor descarta ademas `SU`, `YU`, `CS` y compania, que ISO si conserva.

Verificado contra la API real con los dos casos que el repo ya documenta como
dificiles: Steinlen → Lausana → `CH` (no Francia, donde hizo toda su obra) y
Monir → Qazvin → `IR`.

## Ficheros

| Fichero | Que es |
|---|---|
| `_countries.yaml` | Tabla de normalizacion de paises a ISO 3166-1 alpha-2. **Poblada.** |
| `a.yaml` … `z.yaml` | Un shard por inicial del `artist_id`. Poblados salvo `q` y `x`. |
| `_misc.yaml` | Iniciales no latinas y casos raros. |

El sharding no es cosmetico: un lote de altas toca un solo fichero (~150
entradas) y el diff se puede revisar. Un fichero unico de 16.000 lineas convierte
cada regeneracion en un diff que nadie mira — que es exactamente como
`pipelines/config/houses.yaml` se quedo obsoleto.

## Forma de una entrada

```yaml
artists:
  - artist_id: alejandro_obregon      # unico en TODO el maestro; da la inicial del shard
    display_name: Alejandro Obregón   # como se muestra en el informe
    country_birth: ES                 # ISO alpha-2. Donde NACIO.
    nationalities: [CO, ES]           # todas las que tenga; la de mercado primero
    birth_year: 1920
    death_year: 1992
    attribution_type: autor
    source: manual                    # manual | llm | parsed | wikidata
    confidence: high                  # high | medium | low
    aliases:                          # nombres crudos tal cual salen de las casas
      - Alejandro Obregón
      - "OBREGÓN, ALEJANDRO"
      - Alejandro Obregon Roses
    notes: "Nacido en Barcelona, obra y mercado colombianos."
```

## Reglas

1. **Nunca se inventa un pais.** Si no hay certeza, `country_birth: null` y
   `confidence: low`. Es la misma regla que `to_eur()`, que devuelve `None` en vez
   de `1.0`: un dato que falta debe verse, no disfrazarse. Un artista sin pais es
   un resultado correcto; un pais equivocado es una corrupcion silenciosa que
   nadie detectara leyendo el informe.

2. **Los alias son una decision humana, no una heuristica.** El maestro se clava
   en alias explicitos y no en el fold automatico porque hay 86 nombres con
   fechas de nacimiento en conflicto: `Francisco Toledo` son **dos personas
   reales distintas** con el mismo fold. Con alias se pueden separar; clavado en
   el fold, ese error seria irreparable por construccion.

3. **Un alias solo puede pertenecer a un artista.** `load_master()` lanza al
   cargar si detecta un `artist_id` o un alias duplicado entre shards. Falla
   pronto y ruidosamente, nunca a mitad de proceso.

4. **`nationalities` incluye `country_birth`** cuando este se conoce, y se ordena
   poniendo primero la nacionalidad con la que opera el mercado. Obregon nacio en
   Barcelona (`ES`) pero el mercado lo trata como colombiano, de ahi `[CO, ES]`.

5. **Los codigos deben existir en `_countries.yaml`.** El test
   `test_every_shard_entry_validates` carga el maestro real y lo comprueba, para
   que no se pudra.

## Poblar el maestro

`python scripts/artist_master_propose.py --help` genera candidatos a partir de
Silver (parentesis biograficos, `artist_country`, inversiones por coma) con forma
de YAML, para revisar y pegar en el shard que toque. Nunca escribe aqui por su
cuenta.
