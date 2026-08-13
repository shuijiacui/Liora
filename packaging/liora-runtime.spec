from pathlib import Path

from PyInstaller.utils.hooks import collect_all


project_root = Path(SPECPATH).parent
backend_dir = project_root / "backend"

datas = []
binaries = []
hiddenimports = []

for package in (
    "av",
    "ctranslate2",
    "faster_whisper",
    "opencc",
    "sounddevice",
    "tokenizers",
    "onnxruntime",
    "vosk",
    "_sounddevice_data",
):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

hiddenimports += ["huggingface_hub", "onnxruntime"]

a = Analysis(
    [str(backend_dir / "runtime_entry.py")],
    pathex=[str(backend_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "catboost",
        "keras",
        "lightgbm",
        "llvmlite",
        "matplotlib",
        "numba",
        "IPython",
        "jedi",
        "pandas",
        "PIL",
        "scipy",
        "sklearn",
        "tensorflow",
        "torch",
        "xgboost",
        "zmq",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="liora-runtime",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="liora-runtime",
)
