# Release local de Robot Asistente — mientras la CI de GitHub Actions esté sin créditos.
# Uso:
#   powershell -ExecutionPolicy Bypass -File .\tools\release.ps1             # build + zip verificado
#   powershell -ExecutionPolicy Bypass -File .\tools\release.ps1 -Publicar   # además publica la release
param([switch]$Publicar)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

# 1. El zip debe salir exactamente de lo que está en git.
$pendiente = git status --porcelain
if ($pendiente) { Write-Host "❌ Hay cambios sin commitear:"; $pendiente; exit 1 }

# 2. Tests antes de empaquetar.
$env:QT_QPA_PLATFORM = "offscreen"
$env:PYGAME_HIDE_SUPPORT_PROMPT = "1"
.\.venv\Scripts\python.exe -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { Write-Host "❌ Los tests fallan: no se empaqueta."; exit 1 }

# 3. Build y zip (igual que hacía la CI).
.\build_exe.bat
if ($LASTEXITCODE -ne 0) { exit 1 }
Compress-Archive -Path 'dist\RobotAsistente\*' -DestinationPath 'RobotAsistente-win64.zip' -Force

# 4. El .env con las claves nunca viaja en el zip.
$contenido = .\.venv\Scripts\python.exe -m zipfile -l RobotAsistente-win64.zip
if ($contenido | Where-Object { $_ -match '[\\/]\.env\s' }) {
    Write-Host "❌ El zip contiene un .env: NO se publica. Revisa robot.spec."
    exit 1
}
Write-Host "✅ Zip verificado sin .env:" (Get-Item RobotAsistente-win64.zip).Length / 1MB "MB"

# 5. Publicación opcional: tag + release con las notas de RELEASE_NOTES.md.
if ($Publicar) {
    $version = (Select-String -Path core\version.py -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
    $tag = "v$version"
    git tag -f $tag
    git push origin $tag
    gh release create $tag --title "$tag" --notes-file RELEASE_NOTES.md RobotAsistente-win64.zip
    Write-Host "✅ Release publicada: $tag"
}
