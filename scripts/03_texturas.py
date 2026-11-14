"""Genera las texturas de color (albedo) por estación a partir de data/.

Salidas en data/texturas/:
  albedo_{primavera,verano,otono,invierno}.jpg   25 m/píxel, malla completa
  mascara.png                                    blanco = Comunidad de Madrid
y vistas previas con sombreado en renders/previa_*.jpg.

Todo lo de color y nieve es [ESTIMADO] por reglas (ver NOTES.md): clase de suelo CORINE
+ altitud + orientación + pendiente + ruido; no es una imagen real de cada estación.
"""
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.spatial import cKDTree

RAIZ = Path(__file__).resolve().parent.parent
DATA = RAIZ / "data"
OUT = DATA / "texturas"
RENDERS = RAIZ / "renders"
RES = 25
rng = np.random.default_rng(1561)  # año en que la Corte se fija en Madrid

ESTACIONES = ["primavera", "verano", "otono", "invierno"]

# Colores sRGB por clase y estación (prim, ver, oto, inv). Tonos de foto aérea, no de mapa.
C = {
    "urbano":        [(152, 142, 134)] * 4,
    "suelo_desnudo": [(178, 162, 138)] * 4,
    "cereal":        [(106, 130, 64), (194, 166, 108), (148, 122, 94), (124, 128, 84)],
    "regadio":       [(90, 122, 58), (98, 128, 62), (132, 122, 84), (122, 116, 88)],
    "olivar_vina":   [(128, 126, 88), (150, 132, 98), (140, 120, 90), (130, 120, 96)],
    "prados":        [(100, 128, 64), (164, 148, 96), (118, 126, 72), (108, 116, 74)],
    "dehesa":        [(124, 136, 74), (182, 156, 106), (148, 140, 92), (124, 128, 84)],
    "encinar":       [(78, 88, 56), (74, 82, 54), (76, 84, 56), (74, 82, 58)],
    "rebollar":      [(94, 120, 56), (72, 96, 46), (136, 104, 72), (124, 108, 94)],
    "coniferas":     [(46, 64, 46), (44, 60, 44), (46, 62, 46), (42, 56, 46)],
    "pastizal":      [(118, 134, 74), (174, 150, 100), (146, 136, 92), (130, 126, 92)],
    "cervunal":      [(112, 132, 72), (146, 142, 92), (134, 128, 86), (124, 120, 92)],
    "matorral":      [(106, 112, 68), (116, 108, 78), (106, 96, 72), (96, 92, 72)],
    "piorno_flor":   [(164, 154, 82), (116, 108, 78), (106, 96, 72), (96, 92, 72)],
    "roca":          [(128, 124, 118)] * 4,
    "agua":          [(38, 62, 78), (44, 70, 72), (40, 64, 76), (38, 60, 76)],
}
NIEVE = np.array([238, 242, 248], dtype=np.float32)
CLASES = ["fuera", "urbano", "suelo_desnudo", "cereal", "regadio", "olivar_vina", "prados",
          "mosaico_cultivos", "dehesa", "frondosas", "coniferas", "mixto", "pastizal",
          "matorral", "roca", "agua"]


def ruido(shape, escala_px, octavas=4):
    """Ruido fractal suave en [-1, 1]."""
    total = np.zeros(shape, np.float32)
    amp, norm = 1.0, 0.0
    for o in range(octavas):
        e = max(2, escala_px // (2 ** o))
        peq = rng.standard_normal((shape[0] // e + 3, shape[1] // e + 3)).astype(np.float32)
        z = ndimage.zoom(peq, e, order=3)[: shape[0], : shape[1]]
        total += amp * z
        norm += amp
        amp *= 0.5
    total /= norm
    return np.clip(total / (total.std() * 2.5 + 1e-6), -1, 1)


def parcelas(shape, tam_px):
    """Teselación tipo Voronoi: id de parcela por píxel (parcelario agrícola)."""
    n = int(shape[0] * shape[1] / tam_px**2)
    sem = rng.uniform([0, 0], shape, size=(n, 2))
    yy, xx = np.mgrid[0: shape[0], 0: shape[1]]
    # Distorsión leve para que los lindes no sean rectos.
    d = 2.5
    pts = np.stack([(yy + d * ruido(shape, 6, 2)).ravel(), (xx + d * ruido(shape, 6, 2)).ravel()], 1)
    _, ids = cKDTree(sem).query(pts, workers=-1)
    return ids.reshape(shape), n


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    mdt = np.load(DATA / "mdt.npy")
    suelo = np.load(DATA / "suelo.npy")
    mascara = np.load(DATA / "mascara.npy")
    H, W = mdt.shape
    print("derivados...")
    gy, gx = np.gradient(ndimage.gaussian_filter(mdt, 1.0), RES)
    pendiente = np.degrees(np.arctan(np.hypot(gx, gy)))
    norte = -gy / (np.hypot(gx, gy) + 1e-6)  # +1 ladera mirando al norte (fila crece hacia el sur)
    norte = np.where(np.hypot(gx, gy) < 0.02, 0, norte)
    vaguada = mdt - ndimage.uniform_filter(mdt, 15)  # <0 en fondos de valle/canchales

    print("ruido y parcelas...")
    r_grande = ruido((H, W), 400)
    r_medio = ruido((H, W), 60)
    r_fino = rng.standard_normal((H, W)).astype(np.float32)
    ids, n_parc = parcelas((H, W), 14)  # ~350 m
    estado_parc = rng.uniform(0, 1, n_parc).astype(np.float32)[ids]
    tono_parc = rng.normal(0, 1, n_parc).astype(np.float32)[ids]

    # Reclasificación fina: frondosas por altitud, pastizal alto, piornal en flor, mosaicos.
    nombre = np.array(CLASES)[suelo]
    nombre = np.where(nombre == "frondosas", np.where(mdt < 950 + 80 * r_grande, "encinar", "rebollar"), nombre)
    nombre = np.where(nombre == "mixto", np.where(r_medio > 0, "coniferas", np.where(mdt < 950, "encinar", "rebollar")), nombre)
    nombre = np.where((nombre == "pastizal") & (mdt > 1700), "cervunal", nombre)
    nombre = np.where((nombre == "matorral") & (mdt > 1500) & (r_medio > 0.35), "piorno_flor", nombre)
    nombre = np.where(nombre == "mosaico_cultivos",
                      np.where(estado_parc < 0.45, "cereal", np.where(estado_parc < 0.75, "prados", "olivar_vina")), nombre)
    nombre = np.where(nombre == "fuera", "pastizal", nombre)

    luz = np.array([-1.0, 1.0, 1.6]); luz /= np.linalg.norm(luz)
    nrm = np.stack([-gx, gy, np.ones_like(gx)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    sombreado = np.clip(nrm @ luz, 0, 1) ** 0.9

    for k, est in enumerate(ESTACIONES):
        print("estación", est)
        col = np.zeros((H, W, 3), np.float32)
        for cls, tonos in C.items():
            m = nombre == cls
            if m.any():
                col[m] = tonos[k]
        # Variación por parcela en cultivos: rastrojo/labrado/verde según estación.
        cult = np.isin(nombre, ["cereal", "regadio", "prados", "olivar_vina"])
        if est == "verano":
            alt = np.array([150, 120, 88], np.float32)  # labrado temprano
        elif est == "otono":
            alt = np.array([118, 128, 70], np.float32)  # siembra brotando
        elif est == "primavera":
            alt = np.array([150, 132, 92], np.float32)  # barbecho
        else:
            alt = np.array([146, 118, 92], np.float32)  # labrado
        cambio = cult & (estado_parc > 0.72)
        col[cambio] = alt
        col[cult] *= (1 + 0.07 * tono_parc[cult])[:, None]
        # Tejido urbano: hormigón, tejados, asfalto y arbolado, variando por manzana.
        urb = nombre == "urbano"
        if urb.any():
            mezcla = np.array([(164, 158, 150), (170, 128, 106), (108, 106, 104), (88, 104, 70)], np.float32)
            u = r_fino[urb]
            idx = np.where(u < -0.6, 2, np.where(u < 0.25, 0, np.where(u < 1.1, 1, 3)))
            col[urb] = mezcla[idx] * (1 + 0.06 * tono_parc[urb])[:, None]
        # Dehesa: punteado de encinas sobre pasto.
        arbol = (nombre == "dehesa") & (r_fino > 0.9)
        col[arbol] = C["encinar"][k]
        # Textura de dosel en bosques.
        bosque = np.isin(nombre, ["encinar", "rebollar", "coniferas"])
        col[bosque] *= (1 + 0.10 * np.clip(r_fino[bosque], -2, 2))[:, None]
        # Variación general a escala de paisaje.
        col *= (1 + 0.06 * r_grande + 0.04 * r_medio)[..., None]
        # Roca aflorando en pendientes fuertes de la sierra (granito, gneis).
        roca = np.clip((pendiente - 28) / 12, 0, 1) * np.clip((mdt - 1300) / 300, 0, 1)
        col = col * (1 - roca[..., None]) + np.array(C["roca"][k], np.float32) * roca[..., None]

        # Nieve.
        if est != "verano":
            cota, ancho, sol = {"invierno": (1450, 260, 160), "primavera": (1950, 180, 220),
                                "otono": (2150, 120, 120)}[est]
            linea = cota + 120 * r_grande - sol * norte - (60 if est == "primavera" else 0) * np.clip(-vaguada / 8, -1, 1)
            nieve = np.clip((mdt - linea) / ancho + 0.5, 0, 1)
            if est == "primavera":
                nieve *= np.clip((r_medio + 0.2) * 2.5, 0, 1)  # neveros a parches
            nieve *= 1 - 0.75 * np.clip((pendiente - 32) / 15, 0, 1)  # la nieve no se agarra en paredes
            # Bajo dosel: el pinar se ve oscuro sobre la nieve; el rebollar sin hoja deja ver más suelo.
            dosel = np.where(nombre == "coniferas", 0.12, np.where(nombre == "rebollar", 0.6,
                             np.where(nombre == "encinar", 0.3, 1.0)))
            nieve *= dosel
            col = col * (1 - nieve[..., None]) + NIEVE * nieve[..., None]

        col = np.clip(col, 0, 255).astype(np.uint8)
        Image.fromarray(col).save(OUT / f"albedo_{est}.jpg", quality=92)

        # Vista previa 2D con sombreado (solo para revisar; no se usa en Blender).
        prev = col.astype(np.float32) * (0.35 + 0.75 * sombreado[..., None])
        prev[~mascara] = prev[~mascara] * 0.35 + 235 * 0.65
        img = Image.fromarray(np.clip(prev, 0, 255).astype(np.uint8)).resize((W // 4, H // 4), Image.LANCZOS)
        RENDERS.mkdir(exist_ok=True)
        img.save(RENDERS / f"previa_{est}.jpg", quality=88)

    Image.fromarray((mascara * 255).astype(np.uint8)).save(OUT / "mascara.png")
    mascaras_lineas(H, W)
    print("listo")


def mascaras_lineas(H, W, ss=2):
    """Ríos y límite como máscaras con antialias (se encienden y apagan en el material)."""
    import json
    from PIL import ImageDraw
    capas = json.loads((DATA / "capas.json").read_text(encoding="utf-8"))
    x_min, y_max = 360_000, 4_570_000
    px = lambda c: [((x - x_min) / RES * ss, (y_max - y) / RES * ss) for x, y in c]
    mayores = {"Tajo", "Jarama", "Alberche", "Henares"}
    im = Image.new("L", (W * ss, H * ss), 0)
    d = ImageDraw.Draw(im)
    for r in capas["rios"]:
        for linea in r["lineas"]:
            d.line(px(linea), fill=255, width=(3 if r["nombre"] in mayores else 2) * ss, joint="curve")
    im.resize((W, H), Image.LANCZOS).save(OUT / "rios.png")
    im = Image.new("L", (W * ss, H * ss), 0)
    d = ImageDraw.Draw(im)
    for anillo in capas["limite"]:
        d.line(px(anillo), fill=255, width=4 * ss, joint="curve")
    im.resize((W, H), Image.LANCZOS).save(OUT / "limite.png")


if __name__ == "__main__":
    main()
