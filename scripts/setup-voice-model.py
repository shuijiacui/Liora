import argparse
from pathlib import Path

from huggingface_hub import snapshot_download


MODEL_REPOSITORIES = {
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Liora's local speech model")
    parser.add_argument("--model", choices=MODEL_REPOSITORIES, default="small")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    model_root = project_root / ".models" / "faster-whisper"
    location = snapshot_download(
        MODEL_REPOSITORIES[args.model],
        cache_dir=model_root,
    )
    print(f"Liora voice model is ready: {location}")


if __name__ == "__main__":
    main()
