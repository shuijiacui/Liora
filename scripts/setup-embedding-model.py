import argparse
from pathlib import Path

from huggingface_hub import snapshot_download


DEFAULT_REPOSITORY = "onnx-community/bge-small-zh-v1.5-ONNX"


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Liora's local semantic embedding model")
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--output", default=".models/embeddings/bge-small-zh-v1.5")
    args = parser.parse_args()

    destination = Path(args.output).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    location = snapshot_download(
        repo_id=args.repository,
        local_dir=destination,
        allow_patterns=[
            "config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "onnx/model_quantized.onnx",
            "onnx/model_quantized.onnx_data",
        ],
    )
    print(f"Liora semantic embedding model ready: {location}")


if __name__ == "__main__":
    main()
