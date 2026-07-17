$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $projectRoot ".venv"
$pythonPath = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv $venvPath
}

& $pythonPath -m pip install --upgrade pip
& $pythonPath -m pip install -e $projectRoot
& $pythonPath (Join-Path $PSScriptRoot "setup_models.py")

Write-Host "准备完成。运行："
Write-Host "  $pythonPath $PSScriptRoot\run_app.py"

