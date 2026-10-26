#!/usr/bin/env python3
"""Example enrichment: assign simple category tags from text rules."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SILVER_LOTS = ROOT / "data" / "silver" / "lots.jsonl"
OUTPUT = ROOT / "data" / "enrichments" / "category_tags.jsonl"


RULES = {
    "painting": ["oleo", "óleo", "acrilico", "acrílico", "acuarela", "gouache"],
    "prints": ["grabado", "litografia", "litografía", "serigrafia", "serigrafía"],
    "books_documents": ["libro", "documento", "postales"],
    "decorative_arts": ["bronce", "madera", "ceramica", "cerámica", "design", "decorativas"],
}


# "Con documento", "con documentos de Galeria Kin", "Con copia de documento": la
# obra viene CON un certificado, no ES un documento. Sin quitarlo, "documento"
# mandaba a books_documents 125 lotes de Morton (un dibujo de Diego Rivera,
# esculturas de Javier Marin) que no son libros ni papeles. Dos condiciones,
# porque los libros tambien dicen "con documentos":
#   - abre clausula (inicio, tras punto, coma o salto): "ensayo biografico con
#     documentos ineditos" (Lefebre) es el titulo de un libro;
#   - detras viene "de/del/y/firmado", fin de texto o el campo siguiente en
#     MAYUSCULAS (el autor de la descripcion), nunca un adjetivo en minuscula:
#     "Con documentos importantes" es el subtitulo de un folleto de 1831.
# Por eso se aplica sobre el texto original, antes de pasar a minusculas.
_COMES_WITH_DOCUMENT = re.compile(
    r"(?:^|[.,;\n])\s*(?i:con)\b[^.,;\n]{0,40}?\b(?i:documentos?)\b"
    r"(?=\s*(?:$|[.,;:\n(]|(?i:de|del|y|firmad[oa]s?|informativo)\b|[A-ZÁÉÍÓÚÑ]))"
)


def classify(text: str) -> str:
    lower = _COMES_WITH_DOCUMENT.sub(" ", text).lower()
    for category, keywords in RULES.items():
        if any(keyword in lower for keyword in keywords):
            return category
    return "other"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(SILVER_LOTS, encoding="utf-8") as source, open(OUTPUT, "w", encoding="utf-8") as target:
        for line in source:
            row = json.loads(line)
            text = " ".join(filter(None, [row.get("lot_title"), row.get("description"), row.get("medium")]))
            payload = {
                "dedupe_key": row.get("dedupe_key"),
                "category": classify(text),
            }
            target.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(f"[enrichment] wrote: {OUTPUT}")


if __name__ == "__main__":
    main()
