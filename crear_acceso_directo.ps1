$ErrorActionPreference = "Stop"

$projectDir = $PSScriptRoot
$pythonw = Join-Path $projectDir ".venv\Scripts\pythonw.exe"
$main = Join-Path $projectDir "main.py"
$icon = Join-Path $projectDir "assets\robot-assistant.ico"

foreach ($requiredFile in @($pythonw, $main, $icon)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "No se encuentra el archivo necesario: $requiredFile"
    }
}

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Robot Asistente.lnk"
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = '"' + $main + '"'
$shortcut.WorkingDirectory = $projectDir
$shortcut.IconLocation = $icon + ",0"
$shortcut.Description = "Robot Asistente con IA"
$shortcut.Save()

Write-Output "Acceso directo actualizado: $shortcutPath"
