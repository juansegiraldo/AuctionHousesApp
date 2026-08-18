"""Tests de la ingesta a Bronze.

El bug que fijan: Bronze copiaba *.jsonl a ciegas, asi que los ficheros de
prueba que quedaron en el output de Bogota (2245_test.jsonl, test_info_url.jsonl)
entraban como si fueran datos reales. Eran corridas de catalogo que NUNCA
bajaron la pagina de detalle: 300 filas sin fecha, sin artista, sin medium ni
procedencia. Silver dedupe por lot_url y el primero gana, asi que pisaban al
fichero bueno y dejaban 67 lotes mutilados -- los mismos 52 vendidos que caian
al fallback estatico de FX.
"""

import json

from pipelines.bronze.ingest import is_ingestable


def test_test_fixtures_are_not_ingestable():
    # Los dos ficheros reales que causaron el bug.
    assert not is_ingestable("2245_test.jsonl")
    assert not is_ingestable("test_info_url.jsonl")


def test_real_auction_files_are_ingestable():
    # El nombre normal de una subasta: slug + codigo.
    assert is_ingestable("grabados-y-multiples-artes-decorativas-y-diseno_2245-001.jsonl")
    assert is_ingestable("arte-colombiano-y-latinoamericano_2033-001.jsonl")
    assert is_ingestable("historic_all_lots.jsonl")


def test_a_real_slug_containing_test_still_ingests():
    # "test" como subcadena no basta: una subasta podria llamarse asi. Solo se
    # descarta cuando es un segmento propio del nombre.
    assert is_ingestable("arte-contest-2024_2100-001.jsonl")
    assert is_ingestable("protesta-social_2101-001.jsonl")


def test_full_variant_is_ingestable():
    # 2245_full.jsonl es redundante (subconjunto del bueno) pero NO esta
    # mutilado: no se filtra, porque filtrarlo por nombre seria adivinar.
    assert is_ingestable("2245_full.jsonl")


def test_non_jsonl_is_not_ingestable():
    assert not is_ingestable("checkpoints.json")
    assert not is_ingestable("notas.txt")
