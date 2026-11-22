"""Reglas de category_tag.classify().

El fallo que motivo estos tests: "documento" mandaba a books_documents cualquier
obra que viene CON un documento (certificado, constancia). En Morton eran 220
lotes, entre ellos un dibujo de Diego Rivera y esculturas de Javier Marin.
"""
import pytest

from pipelines.enrichments.category_tag import classify


@pytest.mark.parametrize("text, category", [
    ("DIEGO RIVERA, Mujer y mula, Firmado y fechado 48, Lápiz de grafito sobre papel. Con documento", "other"),
    ("JAVIER MARÍN, Maqueta Caballo II, Bronce y resina 1/4. Con documento de Galería Kin", "decorative_arts"),
    ("FANNY RABEL, La copa del olvido. Con copia de documento del artista", "other"),
    ("GERARDO MURILLO, Montaña con árbol, Esténcil s/papel, con documentos", "other"),
])
def test_artwork_that_comes_with_a_document_is_not_a_document(text, category):
    assert classify(text) == category


@pytest.mark.parametrize("text", [
    "VARIOS AUTORES, Rufino Tamayo. Catálogo Razonado de Obra Gráfica. Libro",
    # Lefebre: "con documentos" es parte del titulo del libro, no un certificado.
    # El certificado siempre abre clausula ("... papel. Con documento").
    "José Asunción Silva: ensayo biográfico con documentos inéditos",
    # Bogota, folleto de 1831: abre clausula, pero le sigue un adjetivo.
    "Esposicion que el Señor Pedro Murgueitio presenta... Con documentos importantes",
    "Documento firmado por Benito Juárez, 1867",
    "Lote de 12 postales de la Ciudad de México",
])
def test_real_books_and_documents_still_are(text):
    assert classify(text) == "books_documents"


def test_earlier_categories_keep_priority():
    # Un oleo con certificado sigue siendo pintura (painting va primero).
    assert classify("Óleo sobre tela. Con documento de autenticidad") == "painting"
