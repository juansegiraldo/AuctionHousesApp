#!/usr/bin/env python3
"""Genera pipelines/config/world_110m.json: el contorno de cada pais ya proyectado.

MANUAL y raro, como scripts/fx_fetch_history.py: baja Natural Earth una vez y
deja el resultado versionado en git. Los pipelines nunca tocan la red, y la app
no puede cargar una libreria de mapas ni un TopoJSON de un CDN: la CSP de un
Artifact bloquea todo host externo. Asi que la geometria viaja dentro del repo
como paths SVG listos para pintar.

Decisiones:
  - Natural Earth 110m (dominio publico). A esa escala un pais pequenio sigue
    siendo tocable en un movil y el fichero queda en ~100 KB.
  - ISO_A2_EH y no ISO_A2: en ISO_A2 Francia y Noruega valen "-99" (por sus
    territorios de ultramar), y saldrian grises con ventas millonarias.
  - Proyeccion Equal Earth: de areas iguales, que es lo honesto en un mapa de
    coropletas (Mercator infla Europa y encoge America Latina, justo los dos
    mercados de este proyecto).
  - Sin Antartida: no vende arte y ocupa un tercio del alto.

Uso:
    python -m scripts.build_world_map
"""

from __future__ import annotations

import json
import math
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "pipelines" / "config" / "world_110m.json"
SOURCE = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/"
          "geojson/ne_110m_admin_0_countries.geojson")

WIDTH = 1000.0
A1, A2, A3, A4 = 1.340264, -0.081106, 0.000893, 0.003796
M = math.sqrt(3) / 2


def equal_earth(lon: float, lat: float) -> tuple[float, float]:
    lam, phi = math.radians(lon), math.radians(lat)
    t = math.asin(M * math.sin(phi))
    t2, t6 = t * t, t ** 6
    x = 2 * math.sqrt(3) * lam * math.cos(t) / (3 * (9 * A4 * t6 * t2 + 7 * A3 * t6 + 3 * A2 * t2 + A1))
    y = t * (A1 + A2 * t2 + A3 * t6 + A4 * t6 * t2)
    return x, y


X_MAX = equal_earth(180, 0)[0]
SCALE = WIDTH / (2 * X_MAX)


def project(lon: float, lat: float) -> tuple[float, float]:
    x, y = equal_earth(lon, lat)
    return (x + X_MAX) * SCALE, -y * SCALE


def ring_path(ring: list[list[float]]) -> tuple[str, float, tuple[float, float, float, float]]:
    """Path relativo a 1 decimal: la mitad de bytes que absoluto, y un decimal
    basta para el zoom de Europa (~4x) sin dientes de sierra."""
    pts = [project(lon, lat) for lon, lat in ring]
    out, prev = [], None
    for x, y in pts:
        x, y = round(x, 1), round(y, 1)
        if prev is None:
            out.append(f"M{x:g} {y:g}")
        else:
            dx, dy = round(x - prev[0], 1), round(y - prev[1], 1)
            if dx == 0 and dy == 0:
                continue
            out.append(f"l{dx:g} {dy:g}")
        prev = (x, y)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    # Area por la formula del cordon: decide cual es el poligono principal.
    area = abs(sum(pts[i][0] * pts[i - 1][1] - pts[i - 1][0] * pts[i][1] for i in range(len(pts)))) / 2
    return "".join(out) + "z", area, (min(xs), min(ys), max(xs), max(ys))


def main() -> None:
    with urllib.request.urlopen(SOURCE, timeout=60) as r:
        data = json.load(r)

    countries, top = {}, math.inf
    bottom = -math.inf
    for f in data["features"]:
        p = f["properties"]
        code = p.get("ISO_A2_EH")
        if not code or code == "-99" or code == "AQ":
            continue
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        d, best = [], (0.0, None)
        for poly in polys:
            for k, ring in enumerate(poly):
                path, area, bbox = ring_path(ring)
                d.append(path)
                top, bottom = min(top, bbox[1]), max(bottom, bbox[3])
                if k == 0 and area > best[0]:
                    best = (area, bbox)
        bx = best[1]
        # El centro va al poligono mayor, no al de todo el pais: el de Francia
        # caeria en el Atlantico por la Guayana, y el toque "mas cercano" fallaria.
        countries[code] = {
            "name": p.get("NAME_ES") or p.get("NAME"),
            "d": "".join(d),
            "c": [round((bx[0] + bx[2]) / 2, 1), round((bx[1] + bx[3]) / 2, 1)],
        }

    out = {
        "source": SOURCE,
        "projection": "Equal Earth",
        "viewBox": [0, round(top - 4, 1), WIDTH, round(bottom - top + 8, 1)],
        "countries": countries,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"[world] {OUT}  {len(countries)} paises, {OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
