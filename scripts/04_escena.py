"""Construye la escena de Blender: blender/madrid3d.blend

Uso:  blender -b --factory-startup --python scripts/04_escena.py

Unidades: 1 unidad de Blender = 1 km. Origen local = UTM (430000, 4490000), cota 300 m.
  x_local = (X - 430000)/1000 ; y_local = (Y - 4490000)/1000 ; z_local = (Z - 300)/1000 * exageración
Todo lo interactivo cuelga de las propiedades del objeto "CONTROL" vía drivers de expresión simple
(funcionan aunque Blender tenga desactivada la ejecución automática de scripts).
"""
import json
import math
from pathlib import Path

import bpy
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
DATA = RAIZ / "data"
TEX = DATA / "texturas"
SALIDA = RAIZ / "blender" / "madrid3d.blend"

X_MIN, Y_MAX, RES = 360_000, 4_570_000, 25
X0, Y0, Z0 = 430_000, 4_490_000, 300.0
PASO_CM = 2        # 50 m
PASO_ENTORNO = 8   # 200 m
BASE_M = 180.0     # cota del zócalo de la pieza
ANCHO_FUNDIDO = 14.0                 # km en los que el entorno se funde con el fondo
COLOR_FONDO = (0.30, 0.31, 0.30)     # lineal; mismo color en el plano de fondo y el borde del entorno
# Rótulos que se ven siempre; el resto aparece al acercarse (km a la cámara).
SIEMPRE = {"Peñalara", "La Maliciosa", "Pico del Lobo", "La Pedriza (Yelmo)", "Monte Abantos",
           "Madrid", "Alcalá de Henares", "Aranjuez", "San Lorenzo de El Escorial", "Buitrago del Lozoya",
           "Collado Villalba", "Colmenar Viejo", "Navalcarnero", "Chinchón",
           "Manzanares el Real", "San Martín de Valdeiglesias", "Torrelaguna", "Villarejo de Salvanés"}
DIST_ROTULO = 45.0

mdt = np.load(DATA / "mdt.npy")
mascara = np.load(DATA / "mascara.npy")
capas = json.loads((DATA / "capas.json").read_text(encoding="utf-8"))
H, W = mdt.shape

ESTACIONES = ["Primavera", "Verano", "Otoño", "Invierno"]


# --------------------------------------------------------------------------- utilidades
def loc(x, y):
    return (x - X0) / 1000.0, (y - Y0) / 1000.0


def zb(z_m):
    return (z_m - Z0) / 1000.0


def cota(x, y, radio_px=0):
    r = int(round((Y_MAX - y) / RES)); c = int(round((x - X_MIN) / RES))
    r = min(max(r, 0), H - 1); c = min(max(c, 0), W - 1)
    if radio_px:
        return float(mdt[max(r - radio_px, 0): r + radio_px + 1, max(c - radio_px, 0): c + radio_px + 1].max())
    return float(mdt[r, c])


def driver(owner, path, expr, variables, index=None):
    fc = owner.driver_add(path) if index is None else owner.driver_add(path, index)
    d = fc.driver
    d.type = "SCRIPTED"
    for nombre, tipo, a, b in variables:
        v = d.variables.new()
        v.name = nombre
        if tipo == "prop":
            v.type = "SINGLE_PROP"
            v.targets[0].id_type = "OBJECT"
            v.targets[0].id = a
            v.targets[0].data_path = b
        elif tipo == "locz":
            v.type = "TRANSFORMS"
            v.targets[0].id = a
            v.targets[0].transform_type = "LOC_Z"
            v.targets[0].transform_space = "WORLD_SPACE"
        elif tipo == "dist":
            v.type = "LOC_DIFF"
            v.targets[0].id = a
            v.targets[1].id = b
    d.expression = expr
    return fc


def por_estacion(valores):
    """Expresión por tramos: valores[i] cuando s == i."""
    return "(" + "+".join(f"{v}*(s=={i})" for i, v in enumerate(valores)) + ")"


def limpiar():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for col in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.curves, bpy.data.lights,
                bpy.data.cameras, bpy.data.worlds):
        for b in list(col):
            col.remove(b)


def coleccion(nombre, padre=None):
    c = bpy.data.collections.new(nombre)
    (padre or bpy.context.scene.collection).children.link(c)
    return c


def malla_desde_arrays(nombre, verts, caras, uv=None, liso=True):
    me = bpy.data.meshes.new(nombre)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    n_lados = caras.shape[1]
    me.loops.add(caras.size)
    me.loops.foreach_set("vertex_index", caras.astype(np.int32).ravel())
    me.polygons.add(len(caras))
    me.polygons.foreach_set("loop_start", np.arange(0, caras.size, n_lados, dtype=np.int32))
    me.update(calc_edges=True)
    if uv is not None:
        capa = me.uv_layers.new(name="UVMap")
        capa.data.foreach_set("uv", uv.astype(np.float32).ravel())
    if liso:
        me.shade_smooth()
    return me


# --------------------------------------------------------------------------- terreno
def rejilla(paso, celdas, dz=0.0):
    zs = mdt[::paso, ::paso]
    R, C = zs.shape
    celdas = celdas[: R - 1, : C - 1]
    rr, cc = np.nonzero(celdas)
    usado = np.zeros((R, C), bool)
    for dr, dc in ((0, 0), (1, 0), (1, 1), (0, 1)):
        usado[rr + dr, cc + dc] = True
    vid = -np.ones((R, C), np.int64)
    vid[usado] = np.arange(usado.sum())
    vr, vc = np.nonzero(usado)
    xw = X_MIN + vc * paso * RES + RES / 2
    yw = Y_MAX - vr * paso * RES - RES / 2
    verts = np.stack([(xw - X0) / 1000, (yw - Y0) / 1000, (zs[vr, vc] - Z0) / 1000 + dz], 1)
    caras = np.stack([vid[rr, cc], vid[rr + 1, cc], vid[rr + 1, cc + 1], vid[rr, cc + 1]], 1)
    uv_v = np.stack([(xw - X_MIN) / (W * RES), 1 - (Y_MAX - yw) / (H * RES)], 1)
    uv = uv_v[caras.ravel()]
    return verts, caras, uv, vid, zs


def terreno_cm():
    paso = PASO_CM
    zs_shape = mdt[::paso, ::paso].shape
    centros = mascara[paso // 2:: paso, paso // 2:: paso][: zs_shape[0] - 1, : zs_shape[1] - 1]
    verts, caras, uv, vid, zs = rejilla(paso, centros)
    me = malla_desde_arrays("Terreno_CM", verts, caras, uv)
    print("Terreno CM:", len(verts), "vértices")

    # Canto de la pieza (paredes hasta el zócalo).
    inc = np.zeros((centros.shape[0] + 2, centros.shape[1] + 2), bool)
    inc[1:-1, 1:-1] = centros
    c0 = inc[1:-1, 1:-1]
    lados = {  # vecino ausente -> arista (P -> Q) en sentido antihorario de la celda
        "izq": (~inc[1:-1, :-2], (0, 0), (1, 0)),
        "abajo": (~inc[2:, 1:-1], (1, 0), (1, 1)),
        "der": (~inc[1:-1, 2:], (1, 1), (0, 1)),
        "arriba": (~inc[:-2, 1:-1], (0, 1), (0, 0)),
    }
    pts_p, pts_q = [], []
    for vecino, p, q in lados.values():
        rr, cc = np.nonzero(c0 & vecino)
        pts_p.append(np.stack([rr + p[0], cc + p[1]], 1))
        pts_q.append(np.stack([rr + q[0], cc + q[1]], 1))
    P = np.concatenate(pts_p); Q = np.concatenate(pts_q)

    def xyz(rc, base=False):
        xw = X_MIN + rc[:, 1] * paso * RES + RES / 2
        yw = Y_MAX - rc[:, 0] * paso * RES - RES / 2
        z = np.full(len(rc), zb(BASE_M)) if base else (zs[rc[:, 0], rc[:, 1]] - Z0) / 1000
        return np.stack([(xw - X0) / 1000, (yw - Y0) / 1000, z], 1)

    n = len(P)
    vw = np.concatenate([xyz(P), xyz(P, True), xyz(Q, True), xyz(Q)])
    fw = np.stack([np.arange(n), np.arange(n) + n, np.arange(n) + 2 * n, np.arange(n) + 3 * n], 1)
    canto = malla_desde_arrays("Canto_CM", vw, fw, liso=False)
    return me, canto


def terreno_entorno():
    paso = PASO_ENTORNO
    R, C = mdt[::paso, ::paso].shape
    m = mascara[: (R - 1) * paso, : (C - 1) * paso].reshape(R - 1, paso, C - 1, paso).mean((1, 3))
    verts, caras, uv, _, _ = rejilla(paso, m < 0.98, dz=-0.012)
    # Hacia los bordes del recuadro el terreno baja al zócalo y se funde con el plano de fondo.
    x0l, x1l = (X_MIN - X0) / 1000, (X_MIN + W * RES - X0) / 1000
    y0l, y1l = (Y_MAX - H * RES - Y0) / 1000, (Y_MAX - Y0) / 1000
    borde = np.minimum.reduce([verts[:, 0] - x0l, x1l - verts[:, 0], verts[:, 1] - y0l, y1l - verts[:, 1]])
    t = np.clip(borde / ANCHO_FUNDIDO, 0, 1)
    t = t * t * (3 - 2 * t)
    verts[:, 2] = zb(BASE_M) + (verts[:, 2] - zb(BASE_M)) * t
    print("Terreno entorno:", len(verts), "vértices")
    return malla_desde_arrays("Terreno_entorno", verts, caras, uv)


# --------------------------------------------------------------------------- materiales
def imagen(nombre, color=True):
    im = bpy.data.images.load(str(TEX / nombre), check_existing=True)
    im.colorspace_settings.name = "sRGB" if color else "Non-Color"
    return im


def material_terreno(nombre, ctrl, entorno=False):
    mat = bpy.data.materials.new(nombre)
    nt = mat.node_tree
    N = nt.nodes; L = nt.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial"); out.location = (1500, 0)
    bsdf = N.new("ShaderNodeBsdfPrincipled"); bsdf.location = (900, 0)
    bsdf.inputs["Roughness"].default_value = 0.93
    bsdf.inputs["Specular IOR Level"].default_value = 0.25
    uvn = N.new("ShaderNodeTexCoord"); uvn.location = (-1200, 0)

    s = N.new("ShaderNodeValue"); s.name = s.label = "estacion"; s.location = (-900, 500)
    driver(nt, 'nodes["estacion"].outputs[0].default_value', "s", [("s", "prop", ctrl, '["estacion"]')])

    texs = []
    for i, e in enumerate(["primavera", "verano", "otono", "invierno"]):
        t = N.new("ShaderNodeTexImage"); t.location = (-900, 250 - 280 * i)
        t.image = imagen(f"albedo_{e}.jpg"); t.interpolation = "Cubic"
        L.new(uvn.outputs["UV"], t.inputs["Vector"])
        texs.append(t)
    previo = texs[0].outputs["Color"]
    for i in range(1, 4):
        resta = N.new("ShaderNodeMath"); resta.operation = "SUBTRACT"; resta.use_clamp = True
        resta.location = (-600, 500 - 120 * i)
        L.new(s.outputs[0], resta.inputs[0]); resta.inputs[1].default_value = i - 1
        mix = N.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.location = (-350 + 150 * i, 200 - 80 * i)
        L.new(resta.outputs[0], mix.inputs["Factor"])
        L.new(previo, mix.inputs["A"]); L.new(texs[i].outputs["Color"], mix.inputs["B"])
        previo = mix.outputs["Result"]

    # Capas pintadas sobre el terreno: ríos y límite (se encienden/apagan).
    for capa, color, prop, x in (("rios.png", (0.035, 0.09, 0.13, 1), "rios", 250),
                                  ("limite.png", (0.42, 0.06, 0.09, 1), "limite", 450)):
        t = N.new("ShaderNodeTexImage"); t.image = imagen(capa, color=False); t.location = (x - 300, -900)
        L.new(uvn.outputs["UV"], t.inputs["Vector"])
        v = N.new("ShaderNodeValue"); v.name = v.label = prop; v.location = (x - 300, -1150)
        driver(nt, f'nodes["{prop}"].outputs[0].default_value', "v", [("v", "prop", ctrl, f'["{prop}"]')])
        mul = N.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.location = (x, -950)
        L.new(t.outputs["Color"], mul.inputs[0]); L.new(v.outputs[0], mul.inputs[1])
        mix = N.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.location = (x + 150, -300)
        L.new(mul.outputs[0], mix.inputs["Factor"]); L.new(previo, mix.inputs["A"])
        mix.inputs["B"].default_value = color
        previo = mix.outputs["Result"]

    if entorno:  # fuera de la Comunidad: desaturado y aclarado
        hs = N.new("ShaderNodeHueSaturation"); hs.location = (650, 250)
        hs.inputs["Saturation"].default_value = 0.45
        L.new(previo, hs.inputs["Color"])
        mix = N.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.location = (750, 300)
        mix.inputs["Factor"].default_value = 0.42
        mix.inputs["B"].default_value = (0.62, 0.64, 0.64, 1)
        L.new(hs.outputs["Color"], mix.inputs["A"])
        previo = mix.outputs["Result"]
        # Fundido al color del fondo cerca de los bordes (mismo ancho que el descenso de la malla).
        sep = N.new("ShaderNodeSeparateXYZ"); sep.location = (450, 600)
        L.new(uvn.outputs["UV"], sep.inputs[0])
        bordes = []
        for eje, escala in (("X", W * RES / 1000), ("Y", H * RES / 1000)):
            a = N.new("ShaderNodeMath"); a.operation = "PINGPONG"; a.inputs[1].default_value = 0.5
            L.new(sep.outputs[eje], a.inputs[0])
            b = N.new("ShaderNodeMath"); b.operation = "MULTIPLY"; b.inputs[1].default_value = escala
            L.new(a.outputs[0], b.inputs[0])
            bordes.append(b)
        mn = N.new("ShaderNodeMath"); mn.operation = "MINIMUM"; mn.location = (600, 600)
        L.new(bordes[0].outputs[0], mn.inputs[0]); L.new(bordes[1].outputs[0], mn.inputs[1])
        rng_ = N.new("ShaderNodeMapRange"); rng_.location = (750, 600)
        rng_.interpolation_type = "SMOOTHSTEP"
        rng_.inputs["From Min"].default_value = 0.0
        rng_.inputs["From Max"].default_value = ANCHO_FUNDIDO
        rng_.inputs["To Min"].default_value = 1.0
        rng_.inputs["To Max"].default_value = 0.0
        L.new(mn.outputs[0], rng_.inputs["Value"])
        mix2 = N.new("ShaderNodeMix"); mix2.data_type = "RGBA"; mix2.location = (850, 350)
        L.new(rng_.outputs[0], mix2.inputs["Factor"]); L.new(previo, mix2.inputs["A"])
        mix2.inputs["B"].default_value = (*COLOR_FONDO, 1)
        previo = mix2.outputs["Result"]
    L.new(previo, bsdf.inputs["Base Color"])
    neblina(mat, bsdf, out, ctrl)
    return mat


def neblina(mat, bsdf, out, ctrl):
    """Perspectiva aérea: mezcla con un color de neblina según distancia a la cámara (km)."""
    nt = mat.node_tree
    N = nt.nodes; L = nt.links
    cam = N.new("ShaderNodeCameraData"); cam.location = (500, -600)
    k = N.new("ShaderNodeMath"); k.operation = "MULTIPLY"; k.location = (700, -600)
    k.inputs[1].default_value = -1 / 160.0
    L.new(cam.outputs["View Distance"], k.inputs[0])
    ex = N.new("ShaderNodeMath"); ex.operation = "EXPONENT"; ex.location = (850, -600)
    L.new(k.outputs[0], ex.inputs[0])
    inv = N.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.location = (1000, -600)
    inv.inputs[0].default_value = 1.0
    L.new(ex.outputs[0], inv.inputs[1])
    # Cuanto más alta la cámara, menos aire atraviesa la mirada hacia abajo: menos neblina cercana.
    alt = N.new("ShaderNodeValue"); alt.name = alt.label = "neblina_cercana"; alt.location = (1000, -450)
    driver(nt, 'nodes["neblina_cercana"].outputs[0].default_value', "0.45*exp(-h/14)",
           [("h", "locz", CAMARA, None)])
    fuerza = N.new("ShaderNodeMath"); fuerza.operation = "MULTIPLY"; fuerza.location = (1150, -600)
    L.new(alt.outputs[0], fuerza.inputs[1])
    L.new(inv.outputs[0], fuerza.inputs[0])
    # Lejos (el fondo hacia el horizonte) la neblina llega a cubrir del todo: sin corte con el cielo.
    lejos = N.new("ShaderNodeMapRange"); lejos.location = (1000, -800)
    lejos.interpolation_type = "SMOOTHSTEP"
    lejos.inputs["From Min"].default_value = 130.0
    lejos.inputs["From Max"].default_value = 450.0
    L.new(cam.outputs["View Distance"], lejos.inputs["Value"])
    total = N.new("ShaderNodeMath"); total.operation = "MAXIMUM"; total.location = (1200, -750)
    L.new(fuerza.outputs[0], total.inputs[0]); L.new(lejos.outputs[0], total.inputs[1])
    fuerza = total
    neb = N.new("ShaderNodeRGB"); neb.name = neb.label = "neblina"; neb.location = (1000, -350)
    tonos = [(0.62, 0.70, 0.80), (0.74, 0.74, 0.72), (0.72, 0.68, 0.62), (0.66, 0.74, 0.86)]
    for i in range(3):
        driver(nt, 'nodes["neblina"].outputs[0].default_value', por_estacion([t[i] for t in tonos]),
               [("s", "prop", ctrl, '["estacion"]')], index=i)
    emi = N.new("ShaderNodeEmission"); emi.location = (1150, -250)
    brillo = N.new("ShaderNodeMath"); brillo.operation = "MULTIPLY_ADD"; brillo.location = (1000, -950)
    L.new(lejos.outputs[0], brillo.inputs[0])
    brillo.inputs[1].default_value = 1.6   # hacia el horizonte, tan clara como el cielo
    brillo.inputs[2].default_value = 1.25
    L.new(brillo.outputs[0], emi.inputs["Strength"])
    L.new(neb.outputs[0], emi.inputs["Color"])
    ms = N.new("ShaderNodeMixShader"); ms.location = (1300, 0)
    L.new(fuerza.outputs[0], ms.inputs[0]); L.new(bsdf.outputs[0], ms.inputs[1]); L.new(emi.outputs[0], ms.inputs[2])
    L.new(ms.outputs[0], out.inputs["Surface"])


def material_simple(nombre, color, rough=0.8, emision=0.0, ior=None):
    mat = bpy.data.materials.new(nombre)
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    if ior:
        b.inputs["IOR"].default_value = ior
    if emision:
        b.inputs["Emission Color"].default_value = (*color, 1)
        b.inputs["Emission Strength"].default_value = emision
    return mat


# --------------------------------------------------------------------------- escena
def main():
    global CAMARA
    limpiar()
    escena = bpy.context.scene
    # Cámara (única: los rótulos la miran y la neblina depende de su altura).
    cam_data = bpy.data.cameras.new("Cámara")
    cam_data.lens = 35; cam_data.clip_start = 0.02; cam_data.clip_end = 2500
    CAMARA = bpy.data.objects.new("Cámara", cam_data)
    escena.collection.objects.link(CAMARA)
    escena.camera = CAMARA
    escena.unit_settings.system = "METRIC"
    escena.unit_settings.scale_length = 1000.0  # 1 unidad = 1 km
    escena.unit_settings.length_unit = "KILOMETERS"

    c_terreno = coleccion("Terreno")
    c_agua = coleccion("Agua")
    c_rot = coleccion("Rótulos")
    c_picos = coleccion("Picos", c_rot)
    c_pueblos = coleccion("Pueblos", c_rot)
    c_vistas = coleccion("Vistas")

    # Control central.
    ctrl = bpy.data.objects.new("CONTROL", None)
    ctrl.empty_display_type = "SPHERE"; ctrl.empty_display_size = 0.5
    ctrl.location = (0, 0, -5)
    escena.collection.objects.link(ctrl)
    props = {
        "exageracion": (2.0, 1.0, 4.0, "Exageración vertical del relieve (1 = escala real)"),
        "estacion": (3, 0, 3, "0 primavera · 1 verano · 2 otoño · 3 invierno"),
        "picos": (True, None, None, "Mostrar nombres de picos"),
        "pueblos": (True, None, None, "Mostrar Madrid y pueblos"),
        "rios": (True, None, None, "Mostrar ríos"),
        "embalses": (True, None, None, "Mostrar embalses"),
        "limite": (True, None, None, "Mostrar el límite de la Comunidad"),
        "entorno": (True, None, None, "Mostrar el terreno de fuera de la Comunidad"),
    }
    for k, (v, lo, hi, desc) in props.items():
        ctrl[k] = v
        ui = ctrl.id_properties_ui(k)
        if lo is not None:
            ui.update(min=lo, max=hi, soft_min=lo, soft_max=hi, description=desc)
        else:
            ui.update(description=desc)
    E = [("e", "prop", ctrl, '["exageracion"]')]

    def escalar_z(obj):
        driver(obj, "scale", "e", E, index=2)

    def visible_si(obj, prop, invertir=False):
        expr = "v>0.5" if invertir else "v<0.5"
        for p in ("hide_viewport", "hide_render"):
            driver(obj, p, expr, [("v", "prop", ctrl, f'["{prop}"]')])

    # Terreno.
    me_cm, me_canto = terreno_cm()
    t_cm = bpy.data.objects.new("Terreno_CM", me_cm)
    t_cm.data.materials.append(material_terreno("Terreno", ctrl))
    canto = bpy.data.objects.new("Canto_CM", me_canto)
    canto.data.materials.append(material_simple("Canto", (0.16, 0.13, 0.11), 0.95))
    me_ent = terreno_entorno()
    t_ent = bpy.data.objects.new("Terreno_entorno", me_ent)
    t_ent.data.materials.append(material_terreno("Terreno_entorno", ctrl, entorno=True))
    for o in (t_cm, canto, t_ent):
        c_terreno.objects.link(o)
        escalar_z(o)
    visible_si(t_ent, "entorno")
    visible_si(canto, "entorno", invertir=True)

    # Plano de fondo hasta el horizonte (evita el borde del recuadro).
    zf = zb(BASE_M) - 0.013
    me_f = malla_desde_arrays("Fondo", np.array([[-1500, -1500, zf], [1500, -1500, zf], [1500, 1500, zf],
                                                [-1500, 1500, zf]]), np.array([[0, 1, 2, 3]]), liso=False)
    fondo = bpy.data.objects.new("Fondo", me_f)
    m_fondo = material_simple("Fondo", COLOR_FONDO, 0.95)
    m_fondo.node_tree.nodes["Principled BSDF"].inputs["Specular IOR Level"].default_value = 0.25
    neblina(m_fondo, m_fondo.node_tree.nodes["Principled BSDF"], m_fondo.node_tree.nodes["Material Output"], ctrl)
    fondo.data.materials.append(m_fondo)
    c_terreno.objects.link(fondo)
    escalar_z(fondo)
    visible_si(fondo, "entorno")

    # Embalses.
    mat_agua = material_simple("Agua embalses", (0.02, 0.045, 0.06), 0.06, ior=1.33)
    for e in capas["embalses"]:
        anillo = np.array(e["anillo"][:-1])
        nivel = float(np.percentile([cota(x, y) for x, y in anillo], 15)) + 2.0
        verts = np.array([[*loc(x, y), zb(nivel)] for x, y in anillo])
        me = malla_desde_arrays("Embalse " + e["nombre"], verts, np.arange(len(verts))[None, :], liso=False)
        o = bpy.data.objects.new("Embalse " + (e["nombre"] or "sin nombre"), me)
        o.data.materials.append(mat_agua)
        c_agua.objects.link(o)
        escalar_z(o)
        visible_si(o, "embalses")

    cam = CAMARA

    # Rótulos.
    f_pico = bpy.data.fonts.load(str(RAIZ / "fonts" / "Chonburi-Regular.ttf"))
    f_pueblo = bpy.data.fonts.load(str(RAIZ / "fonts" / "AtkinsonHyperlegible-Bold.ttf"))
    f_madrid = bpy.data.fonts.load(str(RAIZ / "fonts" / "Chonburi-Regular.ttf"))
    m_texto = material_simple("Rótulo", (1, 1, 1), 1.0, emision=1.6)
    m_sombra = material_simple("Rótulo sombra", (0.0, 0.0, 0.0), 1.0)
    m_pico = material_simple("Marca pico", (0.05, 0.05, 0.05), 0.6)
    m_pueblo = material_simple("Marca pueblo", (0.95, 0.95, 0.92), 0.6, emision=0.8)

    import bmesh
    esferas = {}
    for capa_, mat_ in (("picos", m_pico), ("pueblos", m_pueblo)):
        esfera = bpy.data.meshes.new("marca_" + capa_)
        bm = bmesh.new(); bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0); bm.to_mesh(esfera); bm.free()
        esfera.materials.append(mat_)
        esferas[capa_] = esfera

    def rotulo(nombre, texto, x, y, z_m, coleccion_, fuente, tam, mat_marca, capa, espaciado=1.0):
        lx, ly = loc(x, y)
        ancla = bpy.data.objects.new("· " + nombre, None)
        ancla.empty_display_size = 0.2
        ancla.location = (lx, ly, 0)
        coleccion_.objects.link(ancla)
        driver(ancla, "location", f"{zb(z_m):.5f}*e", E, index=2)
        marca = bpy.data.objects.new(nombre + " (marca)", esferas[capa])
        marca.parent = ancla
        coleccion_.objects.link(marca)
        D = [("d", "dist", ancla, cam)]
        for i in range(3):
            driver(marca, "scale", "d*0.0028", D, index=i)
        cu = bpy.data.curves.new(nombre, "FONT")
        cu.body = texto; cu.font = fuente; cu.align_x = "CENTER"; cu.align_y = "BOTTOM"
        cu.space_character = espaciado
        txt = bpy.data.objects.new(nombre, cu)
        txt.parent = ancla
        txt.data.materials.append(m_texto)
        coleccion_.objects.link(txt)
        for i in range(3):
            driver(txt, "scale", f"d*{tam}", D, index=i)
        driver(txt, "location", "d*0.012", D, index=2)
        con = txt.constraints.new("TRACK_TO")
        con.target = cam; con.track_axis = "TRACK_Z"; con.up_axis = "UP_Y"
        sombra = bpy.data.objects.new(nombre + " (sombra)", cu.copy())
        sombra.data.materials.clear(); sombra.data.materials.append(m_sombra)
        sombra.parent = txt
        sombra.location = (0.035, -0.035, -0.02)
        coleccion_.objects.link(sombra)
        expr = "v<0.5" if nombre in SIEMPRE else f"v<0.5 or d>{DIST_ROTULO}"
        for o in (marca, txt, sombra):
            o.visible_shadow = False
            for p in ("hide_viewport", "hide_render"):
                driver(o, p, expr, [("v", "prop", ctrl, f'["{capa}"]')] + D)

    for p in capas["picos"]:
        z = cota(p["x"], p["y"], radio_px=2)
        ele = int(round(p["ele"] or z))
        texto = f"{p['nombre']}  {ele:,}".replace(",", ".")
        rotulo(p["nombre"], texto, p["x"], p["y"], z, c_picos, f_pico, 0.0135, m_pico, "picos")
    for n in capas["nucleos"]:
        z = cota(n["x"], n["y"])
        pob = n["pob"] or 0
        if n["nombre"] == "Madrid":
            rotulo("Madrid", "MADRID", n["x"], n["y"], z, c_pueblos, f_madrid, 0.025, m_pueblo, "pueblos", 1.15)
        else:
            tam = 0.0145 if pob > 100_000 else 0.0115
            rotulo(n["nombre"], n["nombre"], n["x"], n["y"], z, c_pueblos, f_pueblo, tam, m_pueblo, "pueblos")

    # Sol y cielo según estación.
    sol_data = bpy.data.lights.new("Sol", "SUN")
    sol_data.angle = math.radians(1.2)
    sol = bpy.data.objects.new("Sol", sol_data)
    escena.collection.objects.link(sol)
    S = [("s", "prop", ctrl, '["estacion"]')]
    elev = [42, 60, 30, 19]
    azim = [195, 210, 200, 205]
    driver(sol, "rotation_euler", f"(90-{por_estacion(elev)})*0.0174533", S, index=0)
    driver(sol, "rotation_euler", f"(180-{por_estacion(azim)})*0.0174533", S, index=2)
    driver(sol_data, "energy", por_estacion([4.2, 4.6, 3.8, 3.4]), S)
    colores = [(1.0, 0.96, 0.9), (1.0, 0.97, 0.93), (1.0, 0.86, 0.7), (1.0, 0.84, 0.68)]
    for i in range(3):
        driver(sol_data, "color", por_estacion([c[i] for c in colores]), S, index=i)

    mundo = bpy.data.worlds.new("Cielo")
    escena.world = mundo
    wn = mundo.node_tree.nodes; wl = mundo.node_tree.links
    wn.clear()
    cielo = wn.new("ShaderNodeTexSky"); cielo.name = "cielo"
    cielo.sky_type = "MULTIPLE_SCATTERING"; cielo.sun_disc = False
    cielo.altitude = 600
    fondo = wn.new("ShaderNodeBackground"); fondo.name = "fondo"
    fondo.inputs["Strength"].default_value = 0.26
    salida = wn.new("ShaderNodeOutputWorld")
    wl.new(cielo.outputs[0], fondo.inputs[0]); wl.new(fondo.outputs[0], salida.inputs[0])
    driver(mundo.node_tree, 'nodes["cielo"].sun_elevation', f"{por_estacion(elev)}*0.0174533", S)
    driver(mundo.node_tree, 'nodes["cielo"].sun_rotation', f"(90+{por_estacion(azim)})*0.0174533", S)
    driver(mundo.node_tree, 'nodes["cielo"].aerosol_density', por_estacion([1.0, 1.8, 1.4, 0.7]), S)

    # Vistas guardadas: (nombre, objetivo lon/lat, desplazamiento cámara km (este, norte), altura sobre suelo km)
    from utm import lonlat_to_utm30
    vistas_def = [
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
    for nombre, (lon, lat), (dx, dy), h in vistas_def:
        tx, ty = lonlat_to_utm30(lon, lat)
        cx, cy = tx + dx * 1000, ty + dy * 1000
        vistas.append({"nombre": nombre, "obj": [*loc(tx, ty), zb(cota(tx, ty))],
                       "cam": [*loc(cx, cy), zb(cota(cx, cy, 8))], "h": h})
        em = bpy.data.objects.new("Vista · " + nombre, None)
        em.location = (*loc(cx, cy), zb(cota(cx, cy, 8)) * 2 + h)
        em.empty_display_type = "CONE"; em.empty_display_size = 0.6
        c_vistas.objects.link(em)
    ctrl["vistas_json"] = json.dumps(vistas, ensure_ascii=False)
    c_vistas.hide_viewport = True
    c_vistas.hide_render = True

    # Cámara inicial: vista general con exageración 2.
    v = vistas[0]
    aplicar_vista(cam, v, 2.0)

    # Render.
    escena.render.engine = "BLENDER_EEVEE"
    escena.render.resolution_x, escena.render.resolution_y = 1920, 1080
    escena.eevee.use_raytracing = True
    escena.eevee.use_shadows = True
    escena.view_settings.view_transform = "AgX"
    try:
        escena.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    escena.view_settings.exposure = -0.2
    escena.render.film_transparent = False

    # Panel lateral (requiere permitir scripts al abrir el archivo).
    txt = bpy.data.texts.new("madrid3d_panel.py")
    txt.from_string((RAIZ / "scripts" / "panel_madrid3d.py").read_text(encoding="utf-8"))
    txt.use_module = True

    configurar_pantalla()

    for f in bpy.data.fonts:
        if f.filepath and f.filepath != "<builtin>" and not f.packed_file:
            f.pack()
    SALIDA.parent.mkdir(exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(SALIDA), relative_remap=True)
    print("Guardado", SALIDA)


def aplicar_vista(cam, v, e):
    import mathutils
    ox, oy, oz = v["obj"]
    cx, cy, cz = v["cam"]
    objetivo = mathutils.Vector((ox, oy, oz * e))
    pos = mathutils.Vector((cx, cy, max(cz, oz) * e + v["h"]))
    cam.location = pos
    cam.rotation_euler = (objetivo - pos).to_track_quat("-Z", "Y").to_euler()


def configurar_pantalla():
    """Vista 3D del Layout: mirar por la cámara, cámara pegada a la navegación, sombreado material."""
    for pantalla in bpy.data.screens:
        for area in pantalla.areas:
            if area.type != "VIEW_3D":
                continue
            for sp in area.spaces:
                if sp.type == "VIEW_3D":
                    sp.clip_start = 0.01
                    sp.clip_end = 3000
                    sp.lock_camera = True
                    sp.shading.type = "MATERIAL"
                    sp.overlay.show_floor = False
                    sp.overlay.show_axis_x = sp.overlay.show_axis_y = False
                    sp.overlay.show_relationship_lines = False
                    sp.overlay.show_extras = False
                    sp.show_region_ui = True
                    if sp.region_3d:
                        sp.region_3d.view_perspective = "CAMERA"


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(RAIZ / "scripts"))
    main()
