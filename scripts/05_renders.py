"""Renders de control desde las vistas guardadas.

Uso:  blender -b blender/madrid3d.blend --enable-autoexec --python scripts/05_renders.py -- [vistas] [estaciones] [ancho]
  vistas: índices separados por coma (por defecto 0,1,2)
  estaciones: 0 primavera, 1 verano, 2 otoño, 3 invierno (por defecto 3)
"""
import json
import sys
from pathlib import Path

import bpy
import mathutils

RAIZ = Path(bpy.data.filepath).resolve().parent.parent
OUT = RAIZ / "renders"
NOMBRES_EST = ["primavera", "verano", "otono", "invierno"]

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
vistas_sel = [int(x) for x in (args[0] if len(args) > 0 else "0,1,2").split(",")]
est_sel = [int(x) for x in (args[1] if len(args) > 1 else "3").split(",")]
ancho = int(args[2]) if len(args) > 2 else 1280
exag = float(args[3]) if len(args) > 3 else None

escena = bpy.context.scene
ctrl = bpy.data.objects["CONTROL"]
cam = escena.camera
vistas = json.loads(ctrl["vistas_json"])
escena.render.resolution_x = ancho
escena.render.resolution_y = int(ancho * 9 / 16)
escena.render.image_settings.file_format = "JPEG"
escena.render.image_settings.quality = 90
if exag:
    ctrl["exageracion"] = exag


def a_vista(v, e):
    ox, oy, oz = v["obj"]
    cx, cy, cz = v["cam"]
    objetivo = mathutils.Vector((ox, oy, oz * e))
    pos = mathutils.Vector((cx, cy, max(cz, oz) * e + v["h"]))
    cam.location = pos
    cam.rotation_euler = (objetivo - pos).to_track_quat("-Z", "Y").to_euler()


for s in est_sel:
    ctrl["estacion"] = s
    for i in vistas_sel:
        v = vistas[i]
        a_vista(v, float(ctrl["exageracion"]))
        escena.frame_set(1)
        bpy.context.view_layer.update()
        nombre = v["nombre"].lower().replace(" ", "_")
        destino = OUT / f"r_{i}_{nombre}_{NOMBRES_EST[s]}.jpg"
        escena.render.filepath = str(destino)
        bpy.ops.render.render(write_still=True)
        print("RENDER", destino.name)
