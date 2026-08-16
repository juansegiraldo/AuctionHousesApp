"""Fixture Excel minimo para los tests de Lefebre.

Se construye el .xlsx en tiempo de test en vez de versionar un binario: el
fichero real (FINALL.xlsx, 1,8 MB) tiene datos de dos casas y no cabe como
fixture. Aqui van solo los casos que importan, incluidos los raros.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from openpyxl import Workbook

COLUMNS = [
    "Title", "Order", "Starting Price", "Sold For", "Auction Name",
    "Casa de Subasta", "URL Subasta", "URL Lote", "Título_Clean",
    "Starting Price_Clean", "Sold For_Clean", "Artista_Raw", "Artista_Clean",
    "Pais_Clean", "Nacimiento_Clean", "Muerte_Clean", "Auction_Date",
]


def _row(**kwargs):
    return [kwargs.get(column) for column in COLUMNS]


@pytest.fixture
def excel_path(tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "FINAL"
    sheet.append(COLUMNS)

    # --- Subasta 29: numeracion real (1..3) y URL de lote real ---
    # Los numeros van como float a proposito: es lo que openpyxl devuelve al
    # leer celdas numericas, y es donde se colo el bug del x10.
    for order in (1, 2, 3):
        sheet.append(_row(
            Title=f"ARTISTA {order} (1930-1990)\nObra {order}, 1975\n"
                  f"Oleo sobre lienzo\nMedidas: 50 x 70 cm",
            Order=float(order),
            **{"Auction Name": "Subastas 29",
               "Casa de Subasta": "Lefebre",
               "URL Subasta": "Subastas 29",
               "URL Lote": f"https://auction.lefebresubastas.com//lots/view/{order}",
               "Starting Price_Clean": 1000000.0,
               # El '0' de las subastas nuevas = NO vendido.
               "Sold For_Clean": 2000000.0 if order < 3 else 0,
               "Artista_Clean": f"ARTISTA {order}",
               "Pais_Clean": "Colombia",
               "Nacimiento_Clean": 1930,
               "Muerte_Clean": 1990,
               "Auction_Date": "13/03/2024"},
        ))

    # --- Subasta 18: sin URL, Order = nº de fila, 'Pasado' = NO vendido ---
    # Ademas las dos ultimas son el caso de titulo duplicado con Order distinto:
    # lotes distintos de verdad, no duplicados a deduplicar.
    for order in (4968, 4969):
        sheet.append(_row(
            Title="PEDRO RUIZ (1957)\n S/T, 2020\n Tinta sobre papel\n Medidas: 30 x 40 cm",
            Order=float(order),
            **{"Auction Name": "Subasta 18",
               "Casa de Subasta": "Lefebre",
               "URL Subasta": "Subasta 18",
               "Starting Price_Clean": 1250000.0,
               "Sold For_Clean": "Pasado",
               "Artista_Clean": "PEDRO RUIZ",
               "Pais_Clean": "Colombia",
               "Nacimiento_Clean": 1957,
               "Muerte_Clean": "Vive",
               # datetime real, no texto: la hoja mezcla los dos formatos.
               "Auction_Date": datetime(2021, 6, 24)},
        ))

    # 'Pendiente' en el precio de salida -> None, no 0.
    sheet.append(_row(
        Title="ANONIMO\n S/T, sf.\n Acuarela",
        Order=4970,
        **{"Auction Name": "Subasta 18",
           "Casa de Subasta": "Lefebre",
           "URL Subasta": "Subasta 18",
           "Starting Price_Clean": "Pendiente",
           "Sold For_Clean": "Pendiente",
           "Pais_Clean": "#N/D",
           "Auction_Date": datetime(2021, 6, 24)},
    ))

    # --- Fila de Bogota: NO debe emitirse (ya entra por su scraper) ---
    sheet.append(_row(
        Title="85   -  Centro de mesa Warhol",
        Order=1965,
        **{"Auction Name": "GRABADOS - MULTIPLES",
           "Casa de Subasta": "Bogota Auctions",
           "URL Subasta": "https://www.bogotaauctions.com/es/subasta/1",
           "Starting Price_Clean": 150000,
           "Sold For_Clean": 200000,
           "Auction_Date": "28/09/2021"},
    ))

    path = tmp_path / "fixture.xlsx"
    workbook.save(path)
    return path
