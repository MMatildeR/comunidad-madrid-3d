"""Exporta los recursos del visor web a web/visor/datos/.

  altura.png        relieve a 100 m, codificado en R*256+G (decímetros)
  {estacion}.jpg    color por estación a 50 m, con el entorno atenuado y fundido en los bordes
  rios.png, limite.png  capas transparentes a 50 m
  capas.json        rótulos, embalses, metadatos (coordenadas locales en km)
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

RAIZ = Path(__file__).resolve().parent.parent
DATA = RAIZ / "data"
TEX = DATA / "texturas"
OUT = RAIZ / "web" / "visor" / "datos"

X_MIN, Y_MAX, RES = 360_000, 4_570_000, 25
X0, Y0 = 430_000, 4_490_000
PASO_H = 4    # 100 m
PASO_T = 2    # 50 m
FUNDIDO_KM = 14.0
FONDO = np.array([150, 152, 150], np.float32)  # sRGB aprox. del color de fondo


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    mdt = np.load(DATA / "mdt.npy")
    mascara = np.load(DATA / "mascara.npy")
    H, W = mdt.shape

    # Relieve.
    h = ndimage.uniform_filter(mdt, PASO_H)[PASO_H // 2:: PASO_H, PASO_H // 2:: PASO_H]
    dm = np.clip(np.round(h * 10), 0, 65535).astype(np.uint32)
    rgb = np.stack([(dm >> 8) & 255, dm & 255, np.zeros_like(dm)], -1).astype(np.uint8)
    Image.fromarray(rgb).save(OUT / "altura.png", optimize=True)
    hh, hw = h.shape

    # Peso del entorno: 1 dentro de la CM, atenuado fuera, fundido al fondo en los bordes.
    th, tw = H // PASO_T, W // PASO_T
    m = np.array(Image.fromarray(mascara.astype(np.uint8) * 255).resize((tw, th), Image.BILINEAR),
                 np.float32) / 255
    yy, xx = np.mgrid[0:th, 0:tw]
    borde_km = np.minimum.reduce([xx, tw - 1 - xx, yy, th - 1 - yy]) * PASO_T * RES / 1000
    t = np.clip(borde_km / FUNDIDO_KM, 0, 1)
    t = t * t * (3 - 2 * t)

    for est in ["primavera", "verano", "otono", "invierno"]:
        im = Image.open(TEX / f"albedo_{est}.jpg").resize((tw, th), Image.LANCZOS)
        a = np.asarray(im, np.float32)
        gris = a.mean(-1, keepdims=True)
        fuera = (gris + (a - gris) * 0.45) * 0.58 + np.array([200, 204, 204]) * 0.42
        a = a * m[..., None] + fuera * (1 - m[..., None])
        a = a * t[..., None] + FONDO * (1 - t[..., None])
        Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(OUT / f"{est}.jpg", quality=86, optimize=True)

    for capa, color in (("rios", (24, 62, 92)), ("limite", (128, 22, 34))):
        g = np.asarray(Image.open(TEX / f"{capa}.png").resize((tw, th), Image.LANCZOS), np.float32)
        alfa = np.clip(g * (1.6 if capa == "rios" else 1.2), 0, 255).astype(np.uint8)
        rgba = np.zeros((th, tw, 4), np.uint8)
        rgba[..., :3] = color
        rgba[..., 3] = alfa
        Image.fromarray(rgba, "RGBA").save(OUT / f"{capa}.png", optimize=True)

    capas = json.loads((DATA / "capas.json").read_text(encoding="utf-8"))

    def cota(x, y, r=0):
        f = int(round((Y_MAX - y) / RES)); c = int(round((x - X_MIN) / RES))
        return float(mdt[max(f - r, 0): f + r + 1, max(c - r, 0): c + r + 1].max())

    siempre = {"Peñalara", "La Maliciosa", "Pico del Lobo", "La Pedriza (Yelmo)", "Monte Abantos",
               "Madrid", "Alcalá de Henares", "Aranjuez", "San Lorenzo de El Escorial", "Buitrago del Lozoya",
               "Collado Villalba", "Colmenar Viejo", "Navalcarnero", "Chinchón",
               "Manzanares el Real", "San Martín de Valdeiglesias", "Torrelaguna", "Villarejo de Salvanés"}
    rotulos = []
    for p in capas["picos"]:
        z = cota(p["x"], p["y"], 2)
        rotulos.append({"tipo": "pico", "nombre": p["nombre"], "ele": int(round(p["ele"] or z)),
                        "x": (p["x"] - X0) / 1000, "y": (p["y"] - Y0) / 1000, "z": z,
                        "siempre": p["nombre"] in siempre})
    for n in capas["nucleos"]:
        rotulos.append({"tipo": "capital" if n["nombre"] == "Madrid" else ("ciudad" if (n["pob"] or 0) > 100_000 else "pueblo"),
                        "nombre": n["nombre"], "x": (n["x"] - X0) / 1000, "y": (n["y"] - Y0) / 1000,
                        "z": cota(n["x"], n["y"]), "siempre": n["nombre"] in siempre})
    embalses = []
    for e in capas["embalses"]:
        an = e["anillo"][:-1]
        nivel = float(np.percentile([cota(x, y) for x, y in an], 15)) + 2
        embalses.append({"nombre": e["nombre"], "nivel": nivel,
                         "anillo": [[round((x - X0) / 1000, 4), round((y - Y0) / 1000, 4)] for x, y in an]})
    from utm import lonlat_to_utm30
    vistas_def = [  # mismas que en Blender: objetivo (lon, lat), cámara desplazada (km E, km N), altura (km)
        ("Vista general", (-3.70, 40.58), (18, -70), 95),
        ("Guadarrama", (-3.98, 40.785), (14, -26), 7),
        ("Peñalara", (-3.956, 40.850), (7, -13), 3.2),
        ("La Pedriza", (-3.871, 40.759), (2, -9), 2.0),
        ("Valle del Lozoya", (-3.85, 40.90), (-16, -14), 5.5),
        ("Sierra Norte", (-3.50, 41.08), (12, -22), 7),
        ("Madrid desde la sierra", (-3.70, 40.42), (-23.6, 40.6), 0.5),
        ("Madrid ciudad", (-3.70, 40.42), (6, -14), 6),
    ]
    vistas = []
    for nombre, (lon, lat), (dx, dy), hkm in vistas_def:
        tx, ty = (float(v) for v in lonlat_to_utm30(lon, lat))
        cx, cy = tx + dx * 1000, ty + dy * 1000
        vistas.append({"nombre": nombre,
                       "objetivo": [(tx - X0) / 1000, (ty - Y0) / 1000, cota(tx, ty)],
                       "camara": [(cx - X0) / 1000, (cy - Y0) / 1000, cota(cx, cy, 8)], "h": hkm})
    meta = {
        "ancho_km": W * RES / 1000, "alto_km": H * RES / 1000,
        "centro_km": [(X_MIN + W * RES / 2 - X0) / 1000, (Y_MAX - H * RES / 2 - Y0) / 1000],
        "altura_px": [hw, hh], "z_ref_m": 300,
    }
    (OUT / "capas.json").write_text(json.dumps({"meta": meta, "rotulos": rotulos, "embalses": embalses, "vistas": vistas},
                                               ensure_ascii=False), encoding="utf-8")
    for f in sorted(OUT.iterdir()):
        print(f.name, round(f.stat().st_size / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
