"""Panel "Madrid 3D" en la barra lateral del visor 3D (tecla N).

Se guarda dentro del .blend y se registra al abrirlo si se permite la ejecución de scripts.
Todo lo que hace es cambiar propiedades del objeto CONTROL y mover la cámara.
"""
import json

import bpy
import mathutils

ESTACIONES = ["Primavera", "Verano", "Otoño", "Invierno"]
CAPAS = [("picos", "Picos"), ("pueblos", "Madrid y pueblos"), ("rios", "Ríos"),
         ("embalses", "Embalses"), ("limite", "Límite de la Comunidad"), ("entorno", "Terreno vecino")]


def control():
    return bpy.data.objects.get("CONTROL")


def refrescar(context):
    c = control()
    if c:
        c.update_tag()
    for o in bpy.data.objects:
        if o.animation_data and o.animation_data.drivers:
            o.update_tag()
    context.view_layer.update()


class MADRID_OT_estacion(bpy.types.Operator):
    bl_idname = "madrid.estacion"
    bl_label = "Estación"
    bl_description = "Cambiar la estación (colores, nieve, sol y cielo)"
    valor: bpy.props.IntProperty()

    def execute(self, context):
        control()["estacion"] = self.valor
        refrescar(context)
        return {"FINISHED"}


class MADRID_OT_vista(bpy.types.Operator):
    bl_idname = "madrid.vista"
    bl_label = "Vista"
    bl_description = "Llevar la cámara a esta vista"
    indice: bpy.props.IntProperty()

    def execute(self, context):
        c = control()
        v = json.loads(c["vistas_json"])[self.indice]
        e = float(c["exageracion"])
        cam = context.scene.camera
        ox, oy, oz = v["obj"]
        cx, cy, cz = v["cam"]
        objetivo = mathutils.Vector((ox, oy, oz * e))
        pos = mathutils.Vector((cx, cy, max(cz, oz) * e + v["h"]))
        cam.location = pos
        cam.rotation_euler = (objetivo - pos).to_track_quat("-Z", "Y").to_euler()
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_perspective = "CAMERA"
                area.spaces.active.lock_camera = True
        refrescar(context)
        return {"FINISHED"}


class MADRID_PT_panel(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Madrid 3D"
    bl_label = "Comunidad de Madrid"

    def draw(self, context):
        c = control()
        lay = self.layout
        if c is None:
            lay.label(text="Falta el objeto CONTROL")
            return
        lay.label(text="Estación")
        fila = lay.row(align=True)
        for i, n in enumerate(ESTACIONES):
            fila.operator("madrid.estacion", text=n, depress=int(c["estacion"]) == i).valor = i
        lay.separator()
        lay.prop(c, '["exageracion"]', text="Exageración del relieve", slider=True)
        lay.separator()
        lay.label(text="Capas")
        col = lay.column(align=True)
        for k, n in CAPAS:
            col.prop(c, f'["{k}"]', text=n)
        lay.separator()
        lay.label(text="Vistas")
        col = lay.column(align=True)
        for i, v in enumerate(json.loads(c["vistas_json"])):
            col.operator("madrid.vista", text=v["nombre"]).indice = i
        lay.separator()
        lay.operator("render.render", text="Sacar foto de esta vista (F12)", icon="RENDER_STILL")


CLASES = (MADRID_OT_estacion, MADRID_OT_vista, MADRID_PT_panel)


def register():
    for k in CLASES:
        try:
            bpy.utils.register_class(k)
        except ValueError:
            bpy.utils.unregister_class(k)
            bpy.utils.register_class(k)


register()
