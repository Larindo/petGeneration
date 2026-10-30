$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Run Setup-DahliaPet.ps1 first.'
}
Start-Process -FilePath $pythonPath -ArgumentList @('-m', 'pet.character_studio') -WorkingDirectory $projectRoot -WindowStyle Hidden
