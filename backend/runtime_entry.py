import sys

from main import main as backend_main
from wake_listener import main as wake_listener_main


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: liora-runtime <backend|wake> [arguments]")
    mode = sys.argv.pop(1).strip().lower()
    if mode == "backend":
        backend_main()
        return
    if mode == "wake":
        wake_listener_main()
        return
    raise SystemExit(f"unknown Liora runtime mode: {mode}")


if __name__ == "__main__":
    main()
