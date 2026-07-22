$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Run scripts\setup.ps1 first."
}

& $pythonPath (Join-Path $projectRoot "scripts\verify_version.py")
if ($LASTEXITCODE -ne 0) {
    throw "Build failed: version metadata is inconsistent."
}

& $pythonPath -m pip install "pyinstaller>=6.10,<7"
& $pythonPath -m PyInstaller --noconfirm --clean (Join-Path $projectRoot "packaging\word_voice.spec")

$result = Join-Path $projectRoot "dist\WordPdfVoice-v0.6.1\WordPdfVoice-v0.6.1.exe"
if (-not (Test-Path -LiteralPath $result)) {
    throw "Build failed: missing $result"
}

& $pythonPath (Join-Path $projectRoot "scripts\verify_portable.py") --exe $result
if ($LASTEXITCODE -ne 0) {
    throw "Build failed: portable TTS verification did not pass."
}

Write-Host "Build complete: $result"

