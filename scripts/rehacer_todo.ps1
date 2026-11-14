# Regenera todo desde data/ (no vuelve a descargar). Uso: powershell -File scripts\rehacer_todo.ps1
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$blender = if ($env:BLENDER) { $env:BLENDER } else { "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" }  # o definir $env:BLENDER
Set-Location "$raiz\scripts"
python -W ignore 02_procesar.py
python 03_texturas.py
Set-Location $raiz
& $blender -b --factory-startup --python scripts\04_escena.py
& $blender -b blender\madrid3d.blend --enable-autoexec --python scripts\05_renders.py -- 0,1,2,3,4,5,6,7 3 1280
& $blender -b blender\madrid3d.blend --enable-autoexec --python scripts\05_renders.py -- 0,1,6 0,1,2 1280
python scripts\06_web.py
"FIN $(Get-Date)"
