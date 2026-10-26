# Morton Subastas (Ciudad de México)

Quinta casa del pipeline y la primera mexicana. Segunda sobre el framework
`scraping/common/`, copiada de Zorrilla: `parsers.py` + `house.py` + 3 shims.

Morton (antes Galerías Louis C. Morton) subasta desde 1988 en Monte Athos 179, Lomas de
Chapultepec, y es la referencia del mercado mexicano: la prensa sigue sus ventas de Toledo,
Tamayo, Remedios Varo o Botero. Moneda: **pesos mexicanos (MXN)**.

## Cifras (scrape del 2026-10-25)

| | |
|---|---|
| Subastas de arte | 57 (2021-06 → 2026-09), las 57 verificadas contra su "N Results" |
| Lotes | 12.838 |
| Vendidos | 4.742 (36,9%) |
| Martillo | 481.195.909 MXN ≈ 23,43 M€ (tasa del mes de cada subasta) |
| Volumen con país de nacimiento (maestro) | 84,3% |

Contraste con prensa: el Botero de la Subasta de Arte Latinoamericano sale aquí a **7.000.000 MXN**
de martillo; Milenio publicó 8,6 millones, que es el martillo más la prima del comprador (×1,23).

## Fuente

`live.mortonsubastas.com`, la web de pujas de la casa, montada sobre **Bidsquare** (las
imágenes salen de `s1.img.bidsquare.com`). La web de marketing, `mortonsubastas.com`
(Webflow), solo enlaza ahí. Todo es HTML servido por el servidor: basta el fetcher plano,
sin navegador headless ni API privada.

| Página | Qué se lee |
|---|---|
| `/en/auctions/past?page=N` | listado de subastas pasadas (24 por página, 34 páginas) |
| `/en/auctions/morton-subastas/<slug>-<id>` | JSON-LD `Event`: título y fecha |
| `…/<id>/catalog?limit=120&page=N` | tarjetas de lote: título, estimación, a veces precio |
| `/en/online-auctions/morton-subastas/<slug>-<id>` | JSON-LD `Product`: precio, estado, descripción con biografía |

## Cobertura: solo arte, 57 de 803 subastas

Morton vende de todo. De las 803 subastas pasadas (marzo 2020 → octubre 2026), 158 son
flotillas de camiones y coches (Bimbo, "Multimarcas"), 115 "Subastas de los Sábados"
mezcladas, y el resto vinos, joyas, libros, antigüedades y mobiliario francés. Se quedan
**solo las 57 de arte (2021 → 2026)**, con el mismo criterio que la curación de Lefebre:
arte con artista, no un catálogo generalista.

`parsers.is_art_auction()` decide por el título: entra lo que dice arte mexicano / moderno /
contemporáneo / latinoamericano, artistas, obra gráfica, pintura, escultura (y sus versiones
en inglés de 2021-2022); sale lo que además dice decorativas, libros, antigüedades, vino,
joyas, mobiliario o "venta directa". Casos frontera que la regla deja **fuera** a propósito:
"Subasta de Artes Decorativas | Explora el Arte Pop", "Arte y Vid" (arte con vinos),
"Venta directa | Rufino Tamayo" (precio fijo, no remate) y "Subasta de Fotografía y Libros".
Un test fija el 57 sobre los 803 títulos reales (`fixtures/past_titles.json`).

Gold emite el aviso `source_is_art_subset`: el volumen de Morton en la app es el de su arte,
no el de la casa.

## Precio: la ficha del lote, no el catálogo

**Antes de 2024 el catálogo no muestra precio**: la tarjeta dice "Login for Price"
(`data-lot_price_display_level="0"`). Pero la ficha del lote publica sin login un JSON-LD
`Product` con `offers.price` y `offers.availability` — el mismo caso que Zorrilla con "See
Sold Price". Por eso Morton se corre **sin `--quick`**: ~12.500 fichas.

**Trampa: un lote no vendido también trae precio.** Verificado el 2026-10-25 contra la
etiqueta visible en 20 lotes de 2024-2025:

| `availability` | etiqueta visible | `offers.price` |
|---|---|---|
| `SoldOut` | "Sold for MXN$…" | **igual peso a peso** al precio visible (20/20) |
| `Discontinued` | "Unsold" | la **salida**, siempre por debajo de la estimación baja |

Solo `SoldOut` cuenta como venta. La ficha aclara "Sold Price excludes BP": es **precio de
martillo**, sin prima del comprador, como en las demás casas.

Morton publica los no vendidos, así que su tasa de venta es comparable con la de Durán,
Zorrilla y Lefebre (no con la de Bogotá).

## Mojibake real, no de consola

A diferencia del resto del repo (donde el "mojibake" resultó ser la consola de Windows),
**aquí está en el HTML de la casa**: los títulos de 2021-2023 vienen como "Sin tÃ­tulo", a
veces doblemente codificados ("HERNÃƒÂ\x81NDEZ"). En un mismo catálogo conviven títulos
sanos y rotos. `fix_mojibake()` repara texto a texto y, si el texto mezcla ambos, tramo a
tramo; no toca "SÃO PAULO" ni un espacio duro. La `description` del JSON-LD llega limpia;
el `name`, no.

## Fechas en hora de Ciudad de México

El listado pinta la hora en la zona de quien mira ("Sep 25, 2026 01:00AM BST") y el JSON-LD
en zonas de EE. UU. ("2021-08-26 17:00:00 CDT"). `mexico_city_iso()` lo pasa todo a
`America/Mexico_City`, que es donde ocurre la subasta: la de Arte Mexicano de 2026 fue el
**24** de septiembre a las 18:00, no el 25. En un día 31 el error cambiaría el mes y, con
él, la tasa de cambio. Una zona desconocida da `None`, nunca una fecha corrida. Necesita el
paquete `tzdata` en Windows.

## Artista

La casa escribe al autor **en MAYÚSCULAS al principio**, cerrado por coma (hasta 2023) o
punto (desde 2024); en 2021 el título era bilingüe ("ES … | EN …") y se queda la mitad en
español. Un texto que empieza en minúsculas no tiene autor y no se inventa uno.

La descripción de la ficha trae la biografía en la segunda línea:
`JULIO LE PARC` / `(Argentina, 1928 - Francia, 2026)`. De ahí salen los años y
`artist_country`. A los mexicanos la casa les pone **ciudad y estado sin país**
("(Juchitán, Oaxaca, 1940 - …)"), así que un estado mexicano se lee como `México`; a los
extranjeros, el país tal cual ("EE. UU.", "Colombia"). Es el texto libre de la casa:
**solo diagnóstico**, nunca escribe `artist_country_birth`, que sale del maestro.

Años fuera de 1300-2030 se descartan (errata real: "1055" por 1955).

Casos reales que fija un test cada uno:

| Texto de la casa | Sin la regla | Con la regla |
|---|---|---|
| `JAVIER MARÍN,Torso de mujer` | Javier | Javier Marín (85 lotes con separador pegado) |
| `GEORGINA "GOGY" FARÍAS` | Georgina | Georgina Farías (apodo saltado) |
| `DR. LAKRA`, `MR. BRAINWASH` | sin autor | Dr. Lakra, Mr. Brainwash |
| `Diseñado por FRANCISCO TOLEDO`, `Firmada HERARI` | sin autor | Francisco Toledo, Herari |
| `Varios autores, Cinco Grabadores…` | el primer grabador de la descripción | Varios Autores (anónimo) |
| título `DR. ATL`, descripción `GERARDO MURILLO "DR. ATL" (…, 1875 - …)` | sin fechas | Dr. Atl con la biografía |

## Registros reciclados

En la subasta 20912 (Arte Latinoamericano, 2025-11) **51 lotes heredaron el título de un lote de
flotilla** — "Camioneta Chevrolet Tornado 2009", "Automovil Nissan Tsuru 2011", hasta en la URL —
mientras descripción, precio y estimación son de la obra (Beloff, Mérida, Toledo, Siqueiros).
`lot_title_for()` rehace el título desde la descripción cuando el título no nombra a ningún autor y
la descripción sí.

## Recalcular sin re-scrapear

`parse_lot_page()` delega en `lot_title_for()` y `artist_for_lot()`, que solo necesitan el título y
la descripción ya guardados en el JSONL. Si cambia una regla de autor, se pueden recalcular los
12.838 lotes sobre `output/` sin volver a pedir las fichas (una hora).

## Ejecutar

```powershell
python -m scraping.houses.morton_subastas.run_historic --list-only   # las 57
python -m scraping.houses.morton_subastas.run_historic --workers 6 --auction-timeout 7200
python scripts/verify_morton_scrape.py                               # lotes vs "N Results"
```

Una página fuera de rango **no viene vacía**: Bidsquare repite la última. Por eso el número
de páginas sale de "N Results" (catálogo) o de "no hay subastas nuevas" (listado), nunca de
paginar hasta vaciar.

El runner abre el fichero de la subasta al empezar: una corrida cortada deja ficheros a
medias que la siguiente **salta** por resume. Bórralos antes de relanzar, o pasa
`verify_morton_scrape.py`, que los detecta.
