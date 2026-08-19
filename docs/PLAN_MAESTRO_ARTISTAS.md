# Plan de mejora del maestro de artistas

Para quien recoja este trabajo. Escrito el 2026-08-16, despues de dos tandas
(commits `0888851` y `703fecf`) que cerraron los 20 huecos sin pais del top 200.

Este documento tiene dos partes: **lo que salio mal** (para que no se repita) y
**el trabajo pendiente ordenado por lo que rinde**. Lee la primera antes de
tocar nada; la mitad de los errores de la ultima tanda fueron por no leer.

---

## 1. Errores de la tanda anterior, y como evitarlos

Cuatro fallos reales. Ninguno es teorico: los cuatro costaron rehacer trabajo.

### 1.1. Verificar "uno a uno" no es delegar 18 fichas en bloque

Se pidio verificar los artistas uno a uno y se lanzo un subagente con los 18 de
golpe. Las fuentes salieron bien, pero eso fue suerte del muestreo, no metodo:
solo 2 de 18 se comprobaron a mano contra la fuente primaria.

**Regla para la proxima tanda:** cada ficha nueva se abre en su fuente y se cita
la URL concreta en `notes`. Si una ficha no se ha mirado, no entra. Es
preferible una tanda de 20 verificadas que una de 140 a medias — el maestro es
la fuente de verdad del pais, y un pais equivocado no lo detecta nadie leyendo
el informe.

**Trampa concreta que ya mordio:** buscar "Ricardo Canals" en Wikipedia devuelve
un representante de futbolistas uruguayo nacido en 1970. El pintor es Ricard
Canals i Llambi (1876-1931). **Contrasta siempre las fechas de la ficha de la
casa con las de la fuente antes de dar por bueno un homonimo.**

### 1.2. Leer las reglas ANTES de escribir, no despues de fallar

Tres errores evitables, todos por escribir antes de mirar:

| Error | Que paso | Como se evita |
|---|---|---|
| Alias-titulo | Se metio `'"Vendedoras de frutas"'` como alias de Alcala Galiano. El README **ya prohibe** eso: un alias afirma identidad, un titulo no identifica a nadie | Leer `pipelines/config/artists/README.md` entero |
| Duplicado | Se dio de alta `andres_de_santamaria` cuando ya existia `andres_de_santa_maria`. Salto la regla 3 al cargar | `grep -i "<apellido>" pipelines/config/artists/*.yaml` **antes** de crear la entrada |
| `strip_biography` | `BOTERO, FERNANDO (1932 - 2023)` pliega a `botero fernando 1932 2023` y no casa con el alias `BOTERO, FERNANDO`. `artist_fold()` NO recorta la biografia | Comprobar el fold antes de asumir que un alias casa |

**Comando de comprobacion previa obligatorio** para cada nombre que vayas a dar
de alta:

```powershell
python -c "import sys; sys.stdout.reconfigure(encoding='utf-8'); from pipelines.shared.artist_master import resolve_artist; print(resolve_artist('EL NOMBRE CRUDO'))"
```

Si devuelve un `artist_id`, el artista **ya esta**: lo que falta es un alias, no
una entrada nueva. Eso es media hora de trabajo frente a una alta duplicada que
rompe la carga.

### 1.3. El parche del `lot_url` es deuda, no solucion

`_lot_author_fixes.yaml` repara 14 lotes a mano. La causa real sigue viva y esta
descrita en la seccion 2.1: **arreglala antes de ampliar el fichero**. Cada
entrada nueva ahi es trabajo que el arreglo de raiz haria innecesario.

### 1.4. No confundir "cobertura de artistas" con "cobertura del informe"

Se reporto "9,7% de los artistas del ranking" y esa cifra, sola, es engañosa en
la direccion de hacer parecer el trabajo peor de lo que es. Los numeros reales:

| Metrica | Valor |
|---|---|
| Artistas del ranking con pais | 958 de 9.793 (9,8%) |
| **Ingreso cubierto por esos artistas** | **78,4%** |
| Lotes con pais | 20.515 de 64.567 (31,8%) |

El ranking tiene cola larguisima: **97 artistas hacen el 50% del ingreso y 517
hacen el 80%**. Usa siempre las dos cifras juntas — la de artistas para saber
cuanto falta, la de ingreso para saber cuanto importa.

---

## 2. Trabajo pendiente, por lo que rinde

Medido sobre `data/gold/agg_artist_metrics.jsonl` del 2026-08-16.

### 2.1. PRIMERO: arreglar el parser de Duran (causa raiz)

**Esto va antes que cualquier alta en el maestro.** Mientras no se haga, cada
tanda de investigacion arrastra ruido que no es investigable.

En [`scraping/houses/duran_subastas/parsers.py`](../scraping/houses/duran_subastas/parsers.py):

```python
# Linea ~505: la conjetura se calcula primero
artist_name, artist_raw = _infer_artist_from_title(title)
...
# Linea ~515: y el dato BUENO solo se usa si la conjetura fallo
artist_from_detail = details.get("autor")
if artist_from_detail and not artist_raw:      # <-- precedencia invertida
    artist_raw = artist_from_detail
```

`_infer_artist_from_title()` corta el titulo por el primer punto. Para un lote
publicado como `"Madre Superiora". Oleo sobre lienzo. 130 x 99...` el "artista"
que sale es el **titulo de la obra**. Son **721 lotes en 452 variantes**.

**El arreglo:** invertir la precedencia — el campo `autor` de la ficha de
detalle gana siempre; la conjetura del titulo es el respaldo. Luego re-scrapear
Duran y rehacer la cadena.

Pasos:

1. Invertir la precedencia en `parsers.py`.
2. Test con fixture del lote `504-154` (el Botero) comprobando que sale
   `BOTERO, FERNANDO (1932 - 2023)` y no `"Madre Superiora"`.
3. Re-scrape de Duran (ver [docs/SCALING_CHECKLIST.md](SCALING_CHECKLIST.md)).
4. Rehacer bronze -> silver -> artist_resolve -> gold -> insights.
5. **Vaciar `_lot_author_fixes.yaml`** dejando solo la cabecera explicativa, y
   comprobar que el Botero sigue con 33 lotes y 731.590 EUR. Si el numero
   cuadra sin el fichero, el parche ya no hace falta.
6. `_QUOTED_TITLE_RE` en `artist_key.py` **se queda** como red de seguridad.

Rendimiento: recupera hasta 721 lotes con su autor real, sin investigar nada.

### 2.2. SEGUNDO: separar el ruido de los huecos reales

En el top 1000 hay **461 filas sin pais**, y una parte **no son artistas**:

| Ejemplo | Que es |
|---|---|
| `Carta de Gonzalo Jimenez de Quesada al Rey Carlos V` | un documento |
| `Pair of Chinese Guangxu period vases` | porcelana |
| `Manuscritos sobre esclavitud siglo XVIII-XIX` | un lote documental |
| `Reloj de pared estilo Luis XV, de Patek Philippe` | un reloj |
| `Real Academia de la Lengua` | una institucion |

**Cuidado, y es la parte dificil:** una heuristica por longitud o palabras clave
sobre-detecta. `Ricardo de Madrazo y Garreta`, `Francisco de Paula Mendoza y
Moreno` y `Jose Marcelo Contreras y Muñoz` son nombres largos de pintores
**reales**. Una regla automatica los borraria en silencio, que es el fallo peor
— el mismo razonamiento por el que los autores de libros se dejaron entrar
(ver README, "Lo que se decidio NO filtrar").

**Como hacerlo bien:** clasificar a mano los ~40 sospechosos del top 1000,
meter los confirmados en una **lista cerrada** en `artist_key.py` (junto a
`_OBJECT_NAMES` y `_NON_ARTIST_AUTHORS`) y **no** escribir una regla generica.
Si en el futuro se quiere una regla, que sea sobre una señal determinista del
scraper, nunca sobre la forma del nombre.

Rendimiento: limpia el ranking y evita que la siguiente tanda pierda tiempo
investigando jarrones.

### 2.3. TERCERO: los 66 alias por inversion de coma (gratis)

De los 461 huecos del top 1000, **66 llevan coma** (`ZUMETA, JOSÉ LUIS`,
`ORTIZ DE ELGEA, CARMELO`). Muchos apuntan a artistas que **ya estan** en el
maestro sin ese alias. Es la tanda de mejor relacion esfuerzo/resultado:
cero investigacion, solo comprobar que no se fusionan dos personas distintas.

```powershell
python scripts/artist_master_propose.py --min-lots 1 --show-inversions
```

`--show-inversions` es justo lo que hace falta aqui: lista las formas
`Apellido, Nombre` con su inversion propuesta. `artist_fold()` **no** invierte
por su cuenta a proposito, asi que sin el alias explicito el artista rankea dos
veces con la mitad de sus lotes sin pais.

**Ojo con un sesgo del script:** `_known_folds()` (linea 153) salta los folds
que el maestro ya cubre. Como `ZUMETA, JOSÉ LUIS` y `José Luis Zumeta` tienen
folds **distintos**, la forma con coma si aparece — pero si alguna variante ya
esta aliasada, sus hermanas quedan ocultas. Para ver la lista completa, parchea
`_known_folds()` para que devuelva `set()`.

Para cada candidato, **verifica que el año de nacimiento no se contradiga**
antes de fusionar. El contraejemplo que justifica revisarlos a mano es
`García Márquez, Gabriel`: 55 lotes de libros del escritor, no un pintor. La
tanda anterior de 93 alias dio 0 conflictos revisandolos asi.

### 2.4. CUARTO: investigar del puesto 200 al 500

**Aqui esta el volumen que importa.** Los tramos:

| Tramo | Huecos sin pais | Ingreso acumulado del tramo |
|---|---|---|
| top 200 | **0** (hecho) | 64,3% |
| top 500 | 119 | 79,5% |
| top 1000 | 461 | 88,3% |
| top 2000 | 1.260 | 94,3% |

Los **119 huecos del top 500** son el objetivo: valen mas que los 7.800
artistas restantes juntos. Despues, el top 1000 con rendimiento ya decreciente.

**No sigas mas alla del top 2000.** El 62,6% de los nombres aparece una sola
vez y el 5,7% del ingreso que queda no paga el esfuerzo.

Metodo por ficha, en este orden:

1. `resolve_artist('<nombre crudo>')` — ¿ya esta? Entonces es alias, no alta.
2. `grep -i` en los shards por el apellido — ¿hay variante o homonimo?
3. Fuente primaria (Prado, museo nacional, Wikidata) y **URL en `notes`**.
4. Contrasta las fechas con las de la ficha de la casa. Si discrepan, gana la
   fuente y **se anota la discrepancia** (como se hizo con Antonio Palacios:
   1874 en Wikipedia frente a 1876 en la ficha de Duran).
5. Si no se verifica: **se deja sin pais**. Un hueco es un resultado correcto;
   un pais inventado es corrupcion silenciosa. De las 176 fichas de la tercera
   tanda, 36 se quedaron sin pais a proposito.

### 2.5. QUINTO: cerrar la deriva del semantic layer

`semantic_layer/metrics.yaml` no lo ejecuta nadie, asi que se pudre en silencio
— ya se encontraron dos derivas al añadir el maestro. Si tocas como se calcula
algo en `build_insights.py`, **actualiza el YAML en la misma edicion**.

---

## 3. Comprobaciones antes de dar una tanda por buena

```powershell
python -m pipelines.gold.build_artist_master --write-review-queue
python -m pipelines.silver.artist_resolve
python -m pipelines.gold.build_gold
python -m pipelines.gold.build_insights
python -m pipelines.analytics.report_gold
python pipelines/silver/quality_gates.py --house-slug duran_subastas
python -m pytest -q                                    # 654 en verde hoy
```

**El orden importa y los tests van al FINAL.** Con Gold a medio reconstruir,
`report_gold` reventaba con un `TypeError` en `render_html` y caian 11 tests de
`test_render_html.py`; no era un bug del informe sino agregados de dos
generaciones mezclados. Completada la cadena en orden, los 654 pasan. Es la
misma razon por la que el CLAUDE.md insiste en `run_all.ps1` en vez de correr
etapas sueltas.

Y contrasta que **el ingreso total no se mueve**. Dar de alta artistas
reatribuye lotes; nunca crea ni destruye ingreso. Si esa cifra cambia por una
tanda del maestro, algo se rompio.

**La cifra de referencia caduca cuando se re-scrapea una casa, y hay que
comprobarlo antes de dar la alarma.** El 2026-08-17 el total leia
**37.145.061,77 EUR** frente a los **37.575.775,80** que decia este plan, y la
diferencia **no era del maestro**: Zorrilla habia pasado de 3.437 a **11.168
lotes** en un re-scrape posterior, asi que el corpus ya no era el mismo. Como se
descarto que fuera un fallo, en este orden:

1. `artist_resolve.py` **no toca precios** — `grep -n "price\|revenue" ` sobre
   el fichero sale vacio. Una tanda de artistas no puede mover el ingreso.
2. Lefebre seguia cuadrando **exactamente** con su cifra pinchada en CLAUDE.md
   (12.361.725.000 COP, 1.600 vendidos), asi que el pipeline no corrompia importes.
3. Las tasas de `fx_history.yaml` y `fx.yaml` no tenian cambios locales.
4. La suma nativa de Zorrilla cuadraba con su agregado (4.365.109 USD).

Referencia vigente al 2026-08-17, con Zorrilla ya ampliada:

| Casa | Lotes | Vendidos | Ingreso EUR |
|---|---|---|---|
| duran_subastas | 40.442 | 18.624 | 23.450.015,00 |
| bogota_auctions | 9.099 | 9.059 | 7.018.893,65 |
| zorrilla_subastas | 11.168 | 6.942 | 3.919.315,22 |
| lefebre_subastas | 3.858 | 1.600 | 2.756.837,90 |
| **Total** | **64.567** | | **37.145.061,77** |

Metricas a reportar al cerrar (las dos, no solo la primera):

- artistas del ranking con pais / total
- **porcentaje del ingreso que cubren**

---

## 3.bis. Estado al cerrar la sesion del 2026-08-19, y por donde seguir

**3.524 artistas** en el maestro; **86,8% con pais**, **78,9% completas**
(pais + nacimiento + muerte-o-`living`). Ingreso cubierto **89,90%**.

Las **743 fichas incompletas** que quedan, clasificadas por CAUSA -- que es lo
que dice si merece la pena seguir:

| Causa | Fichas |
|---|---|
| **Sin investigar todavia** | **724** |
| Ya investigadas sin exito (queda escrito en `notes`) | 10 |
| Hueco deliberado documentado (discrepancia, duo, identidad en disputa) | 9 |

**Ojo con la lectura facil:** que la via AUTOMATICA este agotada no significa que
las 724 no tengan fuente. Lo medido es esto:

- de **16.049 nombres consultados** en Wikidata, el 63,8% no da identidad
  utilizable, y de **490 fichas incompletas con match** solo UNA aporto un dato
  seguro (las otras 17 candidatas eran muertes anteriores al nacimiento, paises
  ambiguos o `SU` como pais vigente);
- pero de **63 fichas investigadas A MANO**, la mayoria SI se resolvio con fuente
  institucional. Buscar una por una funciona; lo que no funciona es automatizarlo.

### Por donde empezar la proxima tanda

1. **El tramo nacido antes de 1920 sin muerte (~24 fichas).** Es el mas rentable
   con diferencia: son artistas historicos con ficha en museos nacionales, no la
   cola de pintores locales. En esta sesion se cerraron ahi Henri Rousseau,
   Jeronimo Jacinto de Espinosa, Carle Vernet, Coco Madrazo y Adam Willaerts.
2. **Los 10 conflictos de anio** (`--year-conflicts`): son datos EQUIVOCADOS
   publicandose hoy, y eso pesa mas que un hueco.
3. **La cola de pais**, por volumen de lotes. Rinde 1-2 fichas por ronda de
   busqueda y varias no existen en ninguna fuente.

### Ritmo real, para dimensionar

Una ficha exige buscar, contrastar fuentes que a menudo se contradicen (Agelvis
sale venezolano en unas y colombiano en la fuente academica; Salinas Teruel tiene
tres anios de muerte distintos) y a veces una segunda consulta para verificar si
la persona vive. **1-4 fichas por ronda**, con la URL citada en `notes`.

## 4. Lo que NO hay que hacer

Reglas que ya costaron un bug. Estan en el README con mas detalle.

- **No inventes un pais.** Sin certeza, `country_birth: null` y `confidence: low`.
- **No uses el pais de la casa como nacionalidad.** Hay un test que lo prohibe.
  Bogota ha vendido 46 artistas españoles, 26 alemanes y 25 panameños.
- **No claves el maestro en el fold.** `Francisco Toledo` son dos personas
  distintas con el mismo fold. Con alias se separan; con fold, jamas.
- **No metas un titulo de obra como alias.** Si el lote llego mal parseado, va
  por `lot_url` — o mejor, arregla el parser (seccion 2.1).
- **No filtres por la forma del nombre.** Borrar un pintor real no se ve en el
  informe; dejar entrar un jarron, si.
- **Quota `NO` en YAML.** `NO:` (Noruega) parsea como booleano `False` en
  YAML 1.1. Hay un test que lo fija.
