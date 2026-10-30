$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$env:PYTHONUTF8 = '1'
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
    }
    & '.\.venv\Scripts\python.exe' -m pip install -r requirements-studio.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
} finally {
    Pop-Location
}
