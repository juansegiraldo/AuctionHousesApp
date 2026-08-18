# Maestro de artistas

Fuente unica de la identidad del artista y de su pais. Curado a mano y
versionado en git — por eso vive aqui y no en `data/`, que esta entero en
`.gitignore`.

Lo lee `pipelines/shared/artist_master.py`, que a su vez usa
`pipelines/silver/artist_resolve.py`. Mismo patron que `pipelines/config/fx.yaml`.

## Estado actual (2026-08-16)

**1.088 artistas poblados**, que resuelven **21.037 lotes con pais (32,6% del
total, 49,7% de los lotes con autor)**, repartidos en **46 paises**. En el
ranking, **1.053 de 9.885 artistas (10,7%) cubren el 84,47% del ingreso
atribuido a artistas** (25.231.853,12 de 29.870.550,04 EUR), equivalente al
**67,15% del ingreso total de subastas**. Las dos coberturas se publican juntas:
la primera mide trabajo pendiente y la segunda, su importancia economica.

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
    source: manual                    # manual | llm | parsed
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
