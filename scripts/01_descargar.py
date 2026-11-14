"""Descarga las fuentes crudas a sources/.

- MDT 25 m del IGN (WCS INSPIRE, EPSG:25830), en teselas de 20 km.
- Capas de OpenStreetMap (Overpass): límite autonómico, ríos, embalses, picos, núcleos.

Uso:  python scripts/01_descargar.py
Es idempotente: no vuelve a bajar lo que ya existe.
"""
import json
import time
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
MDT_DIR = RAIZ / "sources" / "mdt"
OSM_DIR = RAIZ / "sources" / "osm"

# Recuadro de trabajo (EPSG:25830) que cubre la Comunidad con margen.
X_MIN, X_MAX = 360_000, 500_000
Y_MIN, Y_MAX = 4_410_000, 4_570_000
TESELA = 20_000

WCS = ("https://servicios.idee.es/wcs-inspire/mdt?SERVICE=WCS&VERSION=2.0.1"
       "&REQUEST=GetCoverage&COVERAGEID=Elevacion25830_25"
       "&SUBSET=x({x0},{x1})&SUBSET=y({y0},{y1})&FORMAT=image/tiff")

OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter"]
AREA = 'area["boundary"="administrative"]["admin_level"="4"]["name"="Comunidad de Madrid"]->.cm;'
CONSULTAS = {
    "limite": '[out:json][timeout:180];rel["boundary"="administrative"]["admin_level"="4"]["name"="Comunidad de Madrid"];out geom;',
    "rios": f'[out:json][timeout:180];{AREA}way["waterway"="river"](area.cm);out geom tags;',
    "embalses": f'[out:json][timeout:180];{AREA}(way["water"="reservoir"](area.cm);rel["water"="reservoir"](area.cm););out geom;',
    # Picos por recuadro (no por área): varias cumbres caen sobre la raya con Segovia/Ávila.
    "picos": '[out:json][timeout:180];node["natural"="peak"]["name"](39.85,-4.65,41.20,-3.00);out;',
    "nucleos": f'[out:json][timeout:180];{AREA}node["place"~"^(city|town|village)$"](area.cm);out;',
}

CABECERA = {"User-Agent": "comunidad-madrid-3d/0.1 (proyecto personal de visualizacion)"}


def descargar_mdt():
    MDT_DIR.mkdir(parents=True, exist_ok=True)
    for x0 in range(X_MIN, X_MAX, TESELA):
        for y0 in range(Y_MIN, Y_MAX, TESELA):
            destino = MDT_DIR / f"mdt25_{x0}_{y0}.tif"
            if destino.exists():
                continue
            url = WCS.format(x0=x0, x1=x0 + TESELA, y0=y0, y1=y0 + TESELA)
            for intento in range(4):
                try:
                    r = requests.get(url, headers=CABECERA, timeout=120)
                    r.raise_for_status()
                    if not r.content.startswith((b"II", b"MM")):
                        raise ValueError(r.text[:200])
                    destino.write_bytes(r.content)
                    print("ok", destino.name)
                    break
                except Exception as exc:  # reintento simple
                    print("reintento", destino.name, exc)
                    time.sleep(5 * (intento + 1))


def descargar_osm():
    OSM_DIR.mkdir(parents=True, exist_ok=True)
    for nombre, q in CONSULTAS.items():
        destino = OSM_DIR / f"{nombre}.json"
        if destino.exists():
            continue
        datos = None
        for intento in range(6):
            servidor = OVERPASS[intento % len(OVERPASS)]
            try:
                r = requests.post(servidor, data={"data": q}, headers=CABECERA, timeout=300)
                r.raise_for_status()
                datos = r.json()
                break
            except Exception as exc:
                print("reintento", nombre, servidor, exc)
                time.sleep(10)
        if datos is None:
            raise RuntimeError(f"Overpass no respondió para {nombre}")
        destino.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        print("ok", nombre, len(datos["elements"]), "elementos")
        time.sleep(3)


CLC_DIR = RAIZ / "sources" / "clc"
WMS_CLC = ("https://servicios.idee.es/wms-inspire/ocupacion-suelo?SERVICE=WMS&VERSION=1.3.0"
           "&REQUEST=GetMap&LAYERS=LC.LandCoverSurfaces&STYLES=&CRS=EPSG:25830"
           "&BBOX={x0},{y0},{x1},{y1}&WIDTH={px}&HEIGHT={px}&FORMAT=image/png")
CLC_RES = 25  # m/píxel, misma malla que el MDT


def descargar_clc():
    """CORINE Land Cover renderizado por el WMS del IGN (paleta estándar CLC)."""
    CLC_DIR.mkdir(parents=True, exist_ok=True)
    px = TESELA // CLC_RES
    for x0 in range(X_MIN, X_MAX, TESELA):
        for y0 in range(Y_MIN, Y_MAX, TESELA):
            destino = CLC_DIR / f"clc_{x0}_{y0}.png"
            if destino.exists():
                continue
            url = WMS_CLC.format(x0=x0, y0=y0, x1=x0 + TESELA, y1=y0 + TESELA, px=px)
            for intento in range(4):
                try:
                    r = requests.get(url, headers=CABECERA, timeout=120)
                    r.raise_for_status()
                    if not r.content.startswith(b"\x89PNG"):
                        raise ValueError(r.text[:200])
                    destino.write_bytes(r.content)
                    print("ok", destino.name)
                    break
                except Exception as exc:
                    print("reintento", destino.name, exc)
                    time.sleep(5 * (intento + 1))


if __name__ == "__main__":
    descargar_mdt()
    descargar_clc()
    descargar_osm()
