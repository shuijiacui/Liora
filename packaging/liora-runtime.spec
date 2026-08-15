from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all


project_root = Path(SPECPATH).parent
backend_dir = project_root / "backend"

datas = []
binaries = []
hiddenimports = []

# The packaging venv is created from a Conda interpreter. PyInstaller does not
# recognize that parent environment through the venv and otherwise omits DLLs
# required by Python's own stdlib extensions (sqlite3, expat, bz2, lzma, ffi).
conda_library_bin = Path(sys.base_prefix) / "Library" / "bin"
for dll_name in ("ffi.dll", "libbz2.dll", "libexpat.dll", "liblzma.dll", "sqlite3.dll"):
    dll_path = conda_library_bin / dll_name
    if dll_path.is_file():
        binaries.append((str(dll_path), "."))

for package in (
    "kaldi_native_fbank",
    "opencc",
    "sounddevice",
    "tokenizers",
    "vosk",
    "_sounddevice_data",
):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

hiddenimports += ["kaldi_native_fbank", "onnxruntime"]

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
