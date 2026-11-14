"""Dibuja los límites entre municipios de la Comunidad de Madrid como textura del visor.

Salida: web/visor/datos/municipios.png (2800 x 3200 px, transparente).

Fuente: recintos municipales del IGN, en la versión simplificada del paquete npm
es-atlas (es/municipalities.json). Se dibujan solo los tramos que separan dos
municipios madrileños; el contorno de la Comunidad sale de limite.png.

Proyección del visor: ETRS89 / UTM 30N (EPSG:25830), centro en 430000, 4490000;
140 x 160 km a 20 px por km.

Uso, desde la carpeta scripts/:
    npm pack es-atlas
    tar xzf es-atlas-*.tgz
    python limites_municipales.py

Requiere: numpy, pillow, pyproj.
"""
import json
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from pyproj import Transformer

TOPOJSON = Path("package/es/municipalities.json")
SALIDA = Path(__file__).resolve().parent.parent / "web" / "visor" / "datos" / "municipios.png"

E0, N0 = 430000, 4490000          # centro del visor en UTM 30N (m)
ANCHO_KM, ALTO_KM, PX_KM = 140, 160, 20
W, H = ANCHO_KM * PX_KM, ALTO_KM * PX_KM
SS = 3                            # sobremuestreo para suavizar el trazo
TRAZO, HUECO, GROSOR = 10 * SS, 6 * SS, int(1.9 * SS)
COLOR = (96, 17, 26, 150)         # granate oscuro, semitransparente


def cargar_arcos(t):
    sx, sy = t["transform"]["scale"]
    tx, ty = t["transform"]["translate"]
    arcos = []
    for a in t["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in a:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcos.append(pts)
    return arcos


def main():
    t = json.loads(TOPOJSON.read_text(encoding="utf8"))
    arcos = cargar_arcos(t)
    madrid = [g for g in t["objects"]["municipalities"]["geometries"] if g["id"].startswith("28")]

    # Un arco usado por dos municipios madrileños es un límite interior.
    uso = Counter()
    for g in madrid:
        poligonos = [g["arcs"]] if g["type"] == "Polygon" else g["arcs"]
        for p in poligonos:
            for anillo in p:
                for i in anillo:
                    uso[i if i >= 0 else ~i] += 1
    interiores = [i for i, n in uso.items() if n >= 2]
    print(f"{len(madrid)} municipios, {len(interiores)} tramos interiores")

    tr = Transformer.from_crs(4326, 25830, always_xy=True)
    im = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i in interiores:
        e, n = tr.transform(*np.array(arcos[i]).T)
        px = ((e - E0) / 1000 + ANCHO_KM / 2) * PX_KM * SS
        py = (ALTO_KM / 2 - (n - N0) / 1000) * PX_KM * SS
        pts = np.c_[px, py]
        # Raya discontinua que sigue el arco de punta a punta.
        largos = np.hypot(*np.diff(pts, axis=0).T)
        s = np.r_[0, np.cumsum(largos)]
        pos = 0.0
        while pos < s[-1]:
            a, b = pos, min(pos + TRAZO, s[-1])
            tramo = np.r_[a, s[(s > a) & (s < b)], b]
            xs = np.interp(tramo, s, pts[:, 0])
            ys = np.interp(tramo, s, pts[:, 1])
            d.line(list(zip(xs, ys)), fill=COLOR, width=GROSOR, joint="curve")
            pos += TRAZO + HUECO

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    im.resize((W, H), Image.LANCZOS).save(SALIDA, optimize=True)
    print(f"Guardado en {SALIDA}")


if __name__ == "__main__":
    main()
