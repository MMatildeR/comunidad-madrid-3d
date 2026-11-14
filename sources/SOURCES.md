# Fuentes

Consultadas el 13/11/2026.

| Fuente | URL | Licencia | Qué aporta | Local |
|---|---|---|---|---|
| MDT 25 m, IGN (WCS INSPIRE, cobertura `Elevacion25830_25`) | https://servicios.idee.es/wcs-inspire/mdt | CC BY 4.0, © Instituto Geográfico Nacional | Relieve, 25 m, alturas enteras en m, EPSG:25830 | `sources/mdt/mdt25_{x}_{y}.tif` (56 teselas de 20 km) |
| CORINE Land Cover vía WMS del IGN (`LC.LandCoverSurfaces`) | https://servicios.idee.es/wms-inspire/ocupacion-suelo | CLC: Copernicus (uso libre con atribución) | Cobertura del suelo; se reconstruye la clase desde la paleta estándar CLC | `sources/clc/clc_{x}_{y}.png` |
| OpenStreetMap vía Overpass | https://overpass-api.de | ODbL, © colaboradores de OpenStreetMap | Límite autonómico (rel. 349055), ríos, embalses, picos, núcleos | `sources/osm/*.json` |

## Notas

- CLC se obtiene como imagen renderizada (WMS), no como dato vectorial. La clase se reconstruye por el color más cercano de la paleta estándar. Los bordes con antialias pueden caer en una clase vecina; a 25 m no se nota.
- Área del límite OSM reproyectado: 8.023,5 km² (oficial: 8.028 km²).
- Patones no figura como `place=village` en el área. No se rotula.
