"""Procesa sources/ -> data/.

Salidas (malla común: 25 m, EPSG:25830, norte arriba, origen arriba-izquierda en X_MIN, Y_MAX):
  data/mdt.npy        float32  altitud (m)
  data/mascara.npy    bool     dentro de la Comunidad de Madrid
  data/suelo.npy      uint8    clase de suelo agrupada (ver CLASES)
  data/capas.json     ríos, embalses, picos, núcleos, límite (coordenadas UTM)
  data/meta.json      malla, offset y fuentes
"""
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import LineString, MultiPolygon, Polygon, mapping
from shapely.ops import linemerge, polygonize, transform, unary_union

from utm import lonlat_to_utm30

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "sources"
DATA = RAIZ / "data"

X_MIN, X_MAX = 360_000, 500_000
Y_MIN, Y_MAX = 4_410_000, 4_570_000
RES = 25
TESELA = 20_000
W = (X_MAX - X_MIN) // RES
H = (Y_MAX - Y_MIN) // RES

# --- Suelo: CORINE -> grupos -------------------------------------------------
CLASES = ["fuera", "urbano", "suelo_desnudo", "cereal", "regadio", "olivar_vina",
          "prados", "mosaico_cultivos", "dehesa", "frondosas", "coniferas", "mixto",
          "pastizal", "matorral", "roca", "agua"]
PALETA_CLC = {  # código CLC: (R,G,B, grupo)
    111: (230, 0, 77, 1), 112: (255, 0, 0, 1), 121: (204, 77, 242, 1), 122: (204, 0, 0, 1),
    123: (230, 204, 204, 1), 124: (230, 204, 230, 1), 131: (166, 0, 204, 2), 132: (166, 77, 0, 2),
    133: (255, 77, 255, 2), 141: (255, 166, 255, 1), 142: (255, 230, 255, 1),
    211: (255, 255, 168, 3), 212: (255, 255, 0, 4), 213: (230, 230, 0, 4),
    221: (230, 128, 0, 5), 222: (242, 166, 77, 5), 223: (230, 166, 0, 5),
    231: (230, 230, 77, 6), 241: (255, 230, 166, 7), 242: (255, 230, 77, 7),
    243: (230, 204, 77, 7), 244: (242, 204, 166, 8),
    311: (128, 255, 0, 9), 312: (0, 166, 0, 10), 313: (77, 255, 0, 11),
    321: (204, 242, 77, 12), 322: (166, 255, 128, 13), 323: (166, 230, 77, 13), 324: (166, 242, 0, 13),
    331: (230, 230, 230, 14), 332: (204, 204, 204, 14), 333: (204, 255, 204, 14), 334: (0, 0, 0, 14),
    335: (166, 230, 204, 14),
    411: (166, 166, 255, 15), 412: (77, 77, 255, 15), 511: (0, 204, 242, 15), 512: (128, 242, 230, 15),
}


def fila(y):
    return int(round((Y_MAX - y) / RES))


def col(x):
    return int(round((x - X_MIN) / RES))


def mosaico_mdt():
    mdt = np.full((H, W), np.nan, dtype=np.float32)
    for f in sorted((SRC / "mdt").glob("mdt25_*.tif")):
        _, x0, y0 = f.stem.split("_")
        a = np.array(Image.open(f)).astype(np.float32)
        r0, c0 = fila(int(y0) + TESELA), col(int(x0))
        mdt[r0:r0 + a.shape[0], c0:c0 + a.shape[1]] = a
    mdt[(mdt < -100) | (mdt > 5000)] = np.nan
    print("MDT", mdt.shape, np.nanmin(mdt), np.nanmax(mdt), "nan:", int(np.isnan(mdt).sum()))
    return mdt


def mosaico_suelo():
    cods = list(PALETA_CLC.values())
    pal = np.array([c[:3] for c in cods], dtype=np.int32)
    grupos = np.array([c[3] for c in cods], dtype=np.uint8)
    suelo = np.zeros((H, W), dtype=np.uint8)
    for f in sorted((SRC / "clc").glob("clc_*.png")):
        _, x0, y0 = f.stem.split("_")
        im = Image.open(f).convert("RGBA")
        a = np.array(im).astype(np.int32)
        rgb, alfa = a[..., :3], a[..., 3]
        # Colores únicos -> grupo más cercano (rápido: pocos miles de colores).
        clave = rgb[..., 0] * 65536 + rgb[..., 1] * 256 + rgb[..., 2]
        unicos, inv = np.unique(clave, return_inverse=True)
        u = np.stack([unicos // 65536, (unicos // 256) % 256, unicos % 256], axis=1)
        d = ((u[:, None, :] - pal[None, :, :]) ** 2).sum(-1)
        g = grupos[d.argmin(1)]
        g[(u == 255).all(1)] = 0  # fondo blanco
        t = g[inv].reshape(clave.shape)
        t[alfa < 128] = 0
        r0, c0 = fila(int(y0) + TESELA), col(int(x0))
        suelo[r0:r0 + t.shape[0], c0:c0 + t.shape[1]] = t
    return suelo


def a_utm(geom):
    return transform(lambda x, y, z=None: lonlat_to_utm30(x, y), geom)


def limite():
    rel = json.loads((SRC / "osm" / "limite.json").read_text(encoding="utf-8"))["elements"][0]
    lineas = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
              for m in rel["members"] if m["type"] == "way" and m.get("role") == "outer"]
    polys = list(polygonize(linemerge(lineas)))
    geom = unary_union(polys)
    return a_utm(geom)


def mascara(poli):
    im = Image.new("L", (W, H), 0)
    dib = ImageDraw.Draw(im)
    geoms = poli.geoms if isinstance(poli, MultiPolygon) else [poli]
    for g in geoms:
        anillo = [((x - X_MIN) / RES, (Y_MAX - y) / RES) for x, y in g.exterior.coords]
        dib.polygon(anillo, fill=1)
        for h in g.interiors:
            dib.polygon([((x - X_MIN) / RES, (Y_MAX - y) / RES) for x, y in h.coords], fill=0)
    return np.array(im, dtype=bool)


def num(s):
    m = re.match(r"[-\d.,]+", str(s).strip())
    return float(m.group(0).replace(",", ".")) if m else None


# Selección curada: lo que un madrileño reconoce. Nombres tal como están en OSM.
PICOS = {
    "Peñalara": None, "Cabeza de Hierro Mayor": None, "Alto de las Guarramillas (Bola del Mundo)": "Bola del Mundo",
    "La Maliciosa": None, "La Najarra": None, "Montón de Trigo": None, "Pico del Lobo": None,
    "Peña del Yelmo": "La Pedriza (Yelmo)", "Abantos": "Monte Abantos", "Cueva Valiente": None,
    "Cerro de San Pedro": None, "Cerro de la Escusa": None, "Tres Provincias - Cebollera Vieja": "Cebollera Vieja",
    "Peñacabra": None, "Almenara": None,
}
NUCLEOS = [
    "Madrid", "Alcalá de Henares", "Aranjuez", "Móstoles", "Getafe", "Alcobendas", "Torrejón de Ardoz",
    "Collado Villalba", "Colmenar Viejo", "San Lorenzo de El Escorial", "Navalcarnero", "Arganda del Rey",
    "Chinchón", "Buitrago del Lozoya", "Rascafría", "Manzanares el Real", "Cercedilla", "Navacerrada",
    "Guadarrama", "Somosierra", "Torrelaguna", "Patones", "San Martín de Valdeiglesias", "Robledo de Chavela",
    "Villarejo de Salvanés", "Colmenar de Oreja", "Tres Cantos", "Miraflores de la Sierra", "Montejo de la Sierra",
    "Cadalso de los Vidrios", "Villa del Prado", "Fuenlabrada", "Leganés", "Alcorcón", "Parla", "Pozuelo de Alarcón",
    "Majadahonda", "Las Rozas de Madrid", "Boadilla del Monte", "Valdemoro", "Pinto", "Rivas-Vaciamadrid",
    "Coslada", "San Sebastián de los Reyes", "Galapagar", "Torrelodones", "El Escorial", "Lozoya",
]
RIOS = ["Tajo", "Jarama", "Manzanares", "Henares", "Lozoya", "Guadarrama", "Alberche", "Tajuña",
        "Guadalix", "Perales", "Cofio", "Aulencia", "Tajuña"]


def capas(poli):
    osm = lambda n: json.loads((SRC / "osm" / f"{n}.json").read_text(encoding="utf-8"))["elements"]
    dentro = poli.buffer(1500)

    # Ríos: unir tramos con el mismo nombre, recortar, simplificar.
    tramos = {}
    for e in osm("rios"):
        n = e.get("tags", {}).get("name", "")
        base = re.sub(r"^(Río|Rio|río)\s+", "", n)
        if base in RIOS and "geometry" in e:
            tramos.setdefault(base, []).append(a_utm(LineString([(p["lon"], p["lat"]) for p in e["geometry"]])))
    rios = []
    for n, ls in tramos.items():
        g = linemerge(unary_union(ls)).intersection(dentro).simplify(40)
        partes = getattr(g, "geoms", [g])
        rios.append({"nombre": n, "lineas": [list(p.coords) for p in partes if p.length > 500]})

    # Embalses: polígonos > 0,3 km².
    embalses = []
    for e in osm("embalses"):
        tags = e.get("tags", {})
        if e["type"] == "way" and "geometry" in e:
            anillos = [[(p["lon"], p["lat"]) for p in e["geometry"]]]
        elif e["type"] == "relation":
            ls = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
                  for m in e["members"] if m.get("role") == "outer" and "geometry" in m]
            anillos = [list(p.exterior.coords) for p in polygonize(linemerge(ls))] if ls else []
        else:
            continue
        for a in anillos:
            if len(a) < 4:
                continue
            p = a_utm(Polygon(a)).buffer(0)
            if p.area > 300_000 and p.intersects(poli):
                embalses.append({"nombre": tags.get("name", ""), "area": p.area,
                                 "anillo": list(p.simplify(15).exterior.coords)})

    # Montón de Trigo / Cerro Pelado repetidos en OSM: quedarse con el más alto.
    porn = {}
    for e in osm("picos"):
        n = e["tags"]["name"]
        if n in PICOS:
            ele = num(e["tags"].get("ele")) or 0
            if n not in porn or ele > porn[n][0]:
                x, y = lonlat_to_utm30(e["lon"], e["lat"])
                porn[n] = (ele, float(x), float(y))
    picos = [{"nombre": PICOS[n] or n, "ele": v[0], "x": v[1], "y": v[2]} for n, v in porn.items()]

    nucleos = []
    vistos = set()
    for e in osm("nucleos"):
        n = e["tags"].get("name")
        if n in NUCLEOS and n not in vistos:
            vistos.add(n)
            x, y = lonlat_to_utm30(e["lon"], e["lat"])
            nucleos.append({"nombre": n, "tipo": e["tags"]["place"], "pob": num(e["tags"].get("population")),
                            "x": float(x), "y": float(y)})
    faltan = sorted(set(NUCLEOS) - vistos)
    if faltan:
        print("Núcleos no encontrados en OSM:", faltan)
    falt_p = sorted(set(PICOS) - set(porn))
    if falt_p:
        print("Picos no encontrados en OSM:", falt_p)

    geoms = poli.geoms if isinstance(poli, MultiPolygon) else [poli]
    lim = [list(g.simplify(20).exterior.coords) for g in geoms]
    return {"rios": rios, "embalses": embalses, "picos": picos, "nucleos": nucleos, "limite": lim}


def main():
    DATA.mkdir(exist_ok=True)
    mdt = mosaico_mdt()
    poli = limite()
    print("Área Comunidad (km²):", round(poli.area / 1e6, 1), "(oficial: 8.028)")
    m = mascara(poli)
    suelo = mosaico_suelo()
    np.save(DATA / "mdt.npy", mdt)
    np.save(DATA / "mascara.npy", m)
    np.save(DATA / "suelo.npy", suelo)
    c = capas(poli)
    (DATA / "capas.json").write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    hist = np.bincount(suelo[m], minlength=len(CLASES)) / m.sum()
    print("Suelo dentro de la CM:", {CLASES[i]: round(float(v) * 100, 1) for i, v in enumerate(hist) if v > 0.001})
    print("Ríos:", [r["nombre"] for r in c["rios"]], "| embalses:", len(c["embalses"]),
          "| picos:", len(c["picos"]), "| núcleos:", len(c["nucleos"]))
    meta = {"crs": "EPSG:25830", "res_m": RES, "x_min": X_MIN, "y_max": Y_MAX, "ancho": W, "alto": H,
            "clases_suelo": CLASES}
    (DATA / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
