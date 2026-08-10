import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path) -> None:
    """Load a small .env file without adding a runtime dependency."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


@dataclass(frozen=True)
class DeepSeekSettings:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float

    @property
    def configured(self) -> bool:
        return bool(self.api_key.strip())

    @classmethod
    def from_project(cls, project_root: Path) -> "DeepSeekSettings":
        load_dotenv(project_root / ".env")
        timeout_text = os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "30")
        try:
            timeout = min(max(float(timeout_text), 5.0), 120.0)
        except ValueError:
            timeout = 30.0

        return cls(
            api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash").strip() or "deepseek-v4-flash",
            timeout_seconds=timeout,
        )


@dataclass(frozen=True)
class WebSearchSettings:
    api_key: str
    base_url: str
    timeout_seconds: float
    max_results: int

    @property
    def configured(self) -> bool:
        return bool(self.api_key.strip())

    @classmethod
    def from_project(cls, project_root: Path) -> "WebSearchSettings":
        load_dotenv(project_root / ".env")
        try:
            timeout = min(max(float(os.getenv("TAVILY_TIMEOUT_SECONDS", "15")), 5.0), 60.0)
        except ValueError:
            timeout = 15.0
        try:
            maximum = min(max(int(os.getenv("TAVILY_MAX_RESULTS", "4")), 1), 8)
        except ValueError:
            maximum = 4
        return cls(
            api_key=os.getenv("TAVILY_API_KEY", "").strip(),
            base_url=os.getenv("TAVILY_BASE_URL", "https://api.tavily.com").rstrip("/"),
            timeout_seconds=timeout,
            max_results=maximum,
        )
