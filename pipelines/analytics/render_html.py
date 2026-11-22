#!/usr/bin/env python3
"""Piezas compartidas de la capa de presentacion.

Aqui vivia el informe con Plotly (analytics_report.html). Se retiro al quedarse
la app de build_artifact.py como unico renderer: dos renderers del mismo dato
divergian (uno decia "las tres casas" con cuatro). Quedan solo las tablas y
funciones que la app importa, en el mismo modulo para no mover los imports.
"""

from __future__ import annotations

# Nombres legibles: los slugs son claves tecnicas, no etiquetas de interfaz.
HOUSE_LABELS = {
    "bogota_auctions": "Bogotá Auctions",
    "duran_subastas": "Durán Subastas",
    "zorrilla_subastas": "Zorrilla Subastas",
    "lefebre_subastas": "Lefebre Subastas",
    "morton_subastas": "Morton Subastas",
}
# Donde OCURRE la subasta. NO es la nacionalidad del artista: esa sale del
# maestro (pipelines/config/artists/) via artist_country_birth. Usar esta tabla
# como nacionalidad ya seria falso hoy para los 46 artistas espanioles, 26
# alemanes y 25 panamenios que ha vendido Bogota.
HOUSE_COUNTRY = {
    "bogota_auctions": "Colombia",
    "duran_subastas": "España",
    "zorrilla_subastas": "Uruguay",
    "lefebre_subastas": "Colombia",
    "morton_subastas": "México",
}
MONTH_LABELS = {
    "01": "Ene", "02": "Feb", "03": "Mar", "04": "Abr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Ago",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dic",
}


def _rank_selection(artists: list[dict], limit: int) -> list[dict]:
    """Top `limit` global MAS el top `limit` de cada pais.

    El corte global solo dejaba 41 colombianos de 258, asi que el desplegable
    prometia un filtro que no podia cumplir: el filtrado es JS sobre el DOM y
    no puede traer filas que no se hayan renderizado.

    Alcanzar 200 colombianos por corte global exigiria pintar 2.383 filas; por
    pais salen ~1.400 y ademas cada pais queda completo hasta su propio tope.
    Se conserva el orden global para que la columna de posicion siga leyendose
    de mayor a menor volumen.
    """
    keep: set[int] = set(range(min(limit, len(artists))))
    per_country: dict[str, int] = {}
    for i, a in enumerate(artists):
        code = a.get("country_birth")
        if not code:
            continue
        seen = per_country.get(code, 0)
        if seen < limit:
            per_country[code] = seen + 1
            keep.add(i)
    return [a for i, a in enumerate(artists) if i in keep]



LOT_DETAIL_COLUMNS = (
    "artist_name", "country", "house_slug", "auction_id", "auction_start_date",
    "lot_number", "lot_title", "status", "sold", "price_sold", "currency",
    "price_sold_eur", "lot_url",
    # Va al FINAL a proposito: anadirla en medio moveria los indices de las
    # columnas ya existentes y habria que tocar los dos lotLine() a la vez.
    # Es la clave real de cruce ficha-lotes; el fold del nombre agrupa a dos
    # personas distintas que se llaman igual (los dos Francisco Toledo).
    "artist_key",
)


def pack_lot_details(details: list[dict]) -> dict:
    """Empaqueta el detalle lote a lote para embeberlo en el HTML.

    Son 13.733 filas: como JSON de objetos ocupan ~4 MB porque repiten el nombre
    de la clave y el del artista en cada una. Aqui van como filas posicionales y
    los valores que se repiten (artista, pais, casa, subasta, moneda, estado)
    como indices a un diccionario. Baja a menos de 1 MB sin perder un dato.
    """
    if not details:
        return {"cols": list(LOT_DETAIL_COLUMNS), "dict": {}, "rows": []}

    # Columnas de baja cardinalidad: merece la pena indexarlas. artist_key entra
    # aqui porque hay ~1.500 claves para 22.888 filas: repetirla en cada fila
    # costaria mas que el diccionario entero.
    indexed = ("artist_name", "country", "house_slug", "auction_id", "status",
               "currency", "artist_key")
    tables: dict[str, list] = {c: [] for c in indexed}
    lookup: dict[str, dict] = {c: {} for c in indexed}

    rows = []
    for d in details:
        row = []
        for col in LOT_DETAIL_COLUMNS:
            value = d.get(col)
            if col in indexed:
                if value not in lookup[col]:
                    lookup[col][value] = len(tables[col])
                    tables[col].append(value)
                row.append(lookup[col][value])
            elif col == "sold":
                row.append(1 if value else 0)
            else:
                row.append(value)
        rows.append(row)

    return {"cols": list(LOT_DETAIL_COLUMNS), "dict": tables, "rows": rows}
