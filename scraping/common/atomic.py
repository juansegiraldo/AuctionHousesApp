"""Escritura atomica: el fichero final solo aparece si se escribio entero."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator


@contextmanager
def atomic_write(path: Path | str, mode: str = "wb", **kwargs) -> Iterator[IO]:
    """Escribe en `<path>.part` y lo renombra a `path` solo al terminar bien.

    Por que existe: los runners abrian el fichero final vacio ANTES de bajar el
    primer lote, y el resume da por hecha cualquier subasta cuyo fichero existe.
    Un timeout o un Ctrl-C dejaba un fichero a medias que no se volvia a scrapear
    nunca. Si el bloque lanza, queda el `.part` (util para depurar) y el fichero
    final anterior, si lo habia, sigue intacto. El `.part` no casa con `*.jsonl`,
    asi que ni el resume ni Bronze lo ven.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    with open(tmp, mode, **kwargs) as handle:
        yield handle
    os.replace(tmp, path)
