$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "请先运行 scripts\setup.ps1"
}

& $pythonPath -m pip install "pyinstaller>=6.10,<7"
& $pythonPath -m PyInstaller --noconfirm --clean (Join-Path $projectRoot "packaging\word_voice.spec")

$result = Join-Path $projectRoot "dist\WordPdfVoice\WordPdfVoice.exe"
if (-not (Test-Path -LiteralPath $result)) {
    throw "打包失败：未找到 $result"
}

& $pythonPath (Join-Path $projectRoot "scripts\verify_portable.py") --exe $result
if ($LASTEXITCODE -ne 0) {
    throw "打包失败：便携版真实发音验证未通过"
}

Write-Host "打包完成：$result"

