import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from config import WebSearchSettings
from web_search import WebSearchClient


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self) -> bytes:
        return json.dumps(
            {
                "results": [
                    {
                        "title": "Official documentation",
                        "url": "https://example.com/docs",
                        "content": "A verified explanation.",
                    }
                ]
            }
        ).encode("utf-8")


class WebSearchClientTests(unittest.TestCase):
    def test_search_uses_bearer_auth_and_normalizes_sources(self) -> None:
        client = WebSearchClient(
            WebSearchSettings(
                api_key="tvly-test",
                base_url="https://api.tavily.com",
                timeout_seconds=5,
                max_results=4,
            )
        )
        with patch("web_search.urlopen", return_value=FakeResponse()) as mocked_urlopen:
            sources = client.search("current specification")

        self.assertEqual(sources[0]["title"], "Official documentation")
        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(request.headers["Authorization"], "Bearer tvly-test")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertFalse(payload["include_raw_content"])
        self.assertEqual(payload["max_results"], 4)


if __name__ == "__main__":
    unittest.main()
