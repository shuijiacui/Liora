import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import WebSearchSettings


class WebSearchError(RuntimeError):
    pass


class WebSearchClient:
    def __init__(self, settings: WebSearchSettings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return self.settings.configured

    def search(self, query: str) -> list[dict]:
        value = " ".join(str(query or "").split()).strip()[:500]
        if not value:
            return []
        if not self.configured:
            raise WebSearchError("联网查证尚未配置。")

        payload = {
            "query": value,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
            "max_results": self.settings.max_results,
        }
        request = Request(
            f"{self.settings.base_url}/search",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Liora-Knowledge-Companion/0.3",
            },
        )
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise WebSearchError(f"联网查证请求失败（HTTP {error.code}）。") from error
        except (URLError, socket.timeout, TimeoutError) as error:
            raise WebSearchError("联网查证连接或响应超时。") from error
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise WebSearchError("联网查证返回了无法读取的数据。") from error

        sources = []
        for item in result.get("results", []):
            title = str(item.get("title") or "").strip()[:200]
            url = str(item.get("url") or "").strip()[:1000]
            snippet = " ".join(str(item.get("content") or "").split()).strip()[:1200]
            if title and url:
                sources.append({"title": title, "url": url, "summary": snippet})
        return sources[: self.settings.max_results]
