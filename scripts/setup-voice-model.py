import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path


MODEL_REPOSITORY = "https://www.modelscope.cn/iic/SenseVoiceSmall-onnx.git"
MODEL_REVISION = "0dd101a91bcf61c26dd778ddf634d8989afe22e3"
MODEL_SHA256 = "21dc965f689a78d1604717bf561e40d5a236087c85a95584567835750549e822"
MODEL_FILES = ("model_quant.onnx", "tokens.json", "am.mvn", "config.yaml", "README.md")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_is_ready(model_dir: Path) -> bool:
    return all((model_dir / name).is_file() for name in MODEL_FILES) and sha256(
        model_dir / "model_quant.onnx"
    ) == MODEL_SHA256


def run(*args: str, cwd: Path | None = None) -> None:
    try:
        subprocess.run(args, cwd=cwd, check=True)
    except FileNotFoundError as error:
        raise SystemExit("未找到 Git。请先安装 Git for Windows（包含 Git LFS）。") from error
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"SenseVoice 模型下载失败（退出码 {error.returncode}）。") from error


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    models_root = project_root / ".models"
    model_dir = models_root / "sensevoice"
    if model_is_ready(model_dir):
        print(f"Liora SenseVoice model is already ready: {model_dir}")
        return

    models_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sensevoice-download-", dir=models_root) as temporary:
        checkout = Path(temporary) / "repository"
        run("git", "clone", "--depth", "1", MODEL_REPOSITORY, str(checkout))
        revision = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=checkout,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if revision != MODEL_REVISION:
            print(f"提示：官方模型仓库已更新（当前 {revision[:12]}）。继续校验固定 INT8 权重。")

        model_path = checkout / "model_quant.onnx"
        if not model_path.is_file() or sha256(model_path) != MODEL_SHA256:
            raise SystemExit(
                "下载到的 SenseVoice 权重不完整或校验失败。请确认 Git LFS 已安装后重试。"
            )

        model_dir.mkdir(parents=True, exist_ok=True)
        for name in MODEL_FILES:
            source = checkout / name
            if not source.is_file():
                raise SystemExit(f"官方模型仓库缺少必要文件：{name}")
            pending = model_dir / f"{name}.part"
            shutil.copyfile(source, pending)
            pending.replace(model_dir / name)

    print(f"Liora SenseVoice INT8 model is ready: {model_dir}")


if __name__ == "__main__":
    main()
