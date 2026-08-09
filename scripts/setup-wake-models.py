import argparse
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path


MODELS = {
    "en-us": (
        "vosk-model-small-en-us-0.15",
        "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
    ),
    "cn": (
        "vosk-model-small-cn-0.22",
        "https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip",
    ),
}


def install_model(target_root: Path, key: str, force: bool) -> None:
    folder_name, url = MODELS[key]
    destination = target_root / key
    if destination.exists() and not force:
        print(f"Liora wake model already exists: {destination}")
        return

    target_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="liora-vosk-") as temporary:
        archive = Path(temporary) / f"{folder_name}.zip"
        print(f"Downloading {key} wake model from {url}")
        urllib.request.urlretrieve(url, archive)
        with zipfile.ZipFile(archive) as package:
            package.extractall(temporary)
        extracted = Path(temporary) / folder_name
        if not extracted.exists():
            raise RuntimeError(f"Downloaded archive did not contain {folder_name}")
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(extracted), str(destination))
        print(f"Liora wake model is ready: {destination}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Liora's bilingual Vosk wake models")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    target_root = project_root / ".models" / "vosk"
    for key in MODELS:
        install_model(target_root, key, args.force)


if __name__ == "__main__":
    main()
