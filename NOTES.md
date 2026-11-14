# Madrid en relieve: notas

## Cómo se usa

- Abrir `blender/madrid3d.blend` con Blender 5.2. Si aparece el aviso de ejecución automática de scripts, pulsar **Allow Execution**. Así se activa el panel **Madrid 3D** de la barra lateral (tecla N).
- Sin permitir scripts todo sigue funcionando desde las propiedades del objeto `CONTROL` (pestaña Object › Custom Properties): `exageracion`, `estacion` (0 primavera, 1 verano, 2 otoño, 3 invierno) y las capas.
- La vista 3D sigue la cámara (Lock Camera to View): al navegar se mueve la cámara y los rótulos la siguen. F12 renderiza lo que se ve.
- Visor web: `web/visor/` (se puede servir con GitHub Pages).

## Regenerar

`scripts/01_descargar.py` (una vez) y luego `scripts/rehacer_todo.ps1`.

## Decisiones

- Unidades de Blender: 1 unidad = 1 km. Origen local: UTM 30N (430000, 4490000), cota 300 m. La exageración escala Z alrededor de esa cota.
- Malla de la Comunidad a 50 m (3,2 M vértices). Entorno a 200 m, atenuado, que baja y se funde en 14 km con un plano de fondo.
- Ríos y límite van pintados en máscaras sobre el terreno, no como objetos 3D: así siguen al relieve con cualquier exageración.
- Neblina: mezcla según la distancia a la cámara. Se debilita con la altura de la cámara y cubre del todo hacia el horizonte.
- Rótulos: un ancla por rótulo. Marca y texto escalan con la distancia (tamaño constante en pantalla). Los menores se ocultan a más de 45 km.

- Tipografías (elegidas por Matilde el 13 y 14/11/2026): Chonburi para los picos, MADRID y los títulos; Atkinson Hyperlegible para los pueblos (negrita) y el texto (regular). Domine se probó y se descartó el 14/11. Las dos son de Google Fonts, con licencia OFL, y están en `fonts/`. En Blender van empaquetadas en el `.blend`.

## [ESTIMADO]

- Los colores por estación salen de reglas, no de imágenes reales de cada estación. La base es la clase CORINE. Las frondosas se separan por altitud: por debajo de unos 950 m se tratan como encinar (perenne) y por encima como rebollar (caduco). Por encima de 1.700 m el pastizal pasa a cervunal y por encima de 1.500 m hay piornal en flor (primavera).
- Cota de nieve por estación: invierno 1.450 m, primavera 1.950 m (neveros), otoño 2.150 m (primeras nevadas), verano sin nieve. La cota se ajusta por orientación (más nieve en las laderas norte), por pendiente (nada en paredes) y por dosel (el pinar se ve oscuro).
- Nivel de los embalses: percentil 15 del MDT en su orilla, más 2 m.

## Abierto

- Si la vista 3D de Blender va lenta, subir `PASO_CM` a 3 (75 m) en `scripts/04_escena.py`.
- Patones sin rótulo (no está en OSM como núcleo dentro del área).
