from pathlib import Path

from PyInstaller.utils.hooks import collect_all


project_root = Path(SPECPATH).parent
app_name = "WordPdfVoice-v0.3.0"
datas = []
binaries = []
hiddenimports = []

for package in (
    "kokoro_onnx",
    "espeakng_loader",
    "phonemizer",
    "language_tags",
    "pdfplumber",
    "genanki",
    "soundfile",
):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

for filename in ("kokoro-v1.0.int8.onnx", "voices-v1.0.bin"):
    model_path = project_root / "models" / filename
    if not model_path.is_file():
        raise FileNotFoundError(f"Missing model file: {model_path}")
    datas.append((str(model_path), "models"))

ui_assets = project_root / "assets" / "ui"
for asset_path in ui_assets.glob("*.png"):
    datas.append((str(asset_path), "assets/ui"))

a = Analysis(
    [str(project_root / "scripts" / "run_app.py")],
    pathex=[str(project_root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "IPython", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=app_name,
)

