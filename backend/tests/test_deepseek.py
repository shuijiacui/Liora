import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from config import DeepSeekSettings
from deepseek_client import DeepSeekClient


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


class DeepSeekClientTests(unittest.TestCase):
    def test_dotenv_configuration_and_request_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            (root / ".env").write_text(
                "DEEPSEEK_API_KEY=test-secret\nDEEPSEEK_MODEL=deepseek-v4-flash\n",
                encoding="utf-8",
            )
            settings = DeepSeekSettings.from_project(root)
            client = DeepSeekClient(settings)
            response = FakeResponse(
                {"choices": [{"message": {"role": "assistant", "content": "这个理解和你以前学过的什么最相似？"}}]}
            )

            with patch("deepseek_client.urlopen", return_value=response) as mocked_urlopen:
                result = client.generate_follow_up(
                    [
                        {"role": "assistant", "content": "今天学到了什么？"},
                        {"role": "user", "content": "我理解了注意力机制。"},
                    ],
                    1,
                )

            self.assertIn("什么最相似", result)
            request = mocked_urlopen.call_args.args[0]
            body = json.loads(request.data.decode("utf-8"))
            self.assertEqual(request.full_url, "https://api.deepseek.com/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer test-secret")
            self.assertEqual(body["model"], "deepseek-v4-flash")
            self.assertEqual(body["thinking"], {"type": "disabled"})
            self.assertEqual(body["messages"][-1]["content"], "我理解了注意力机制。")

    def test_organize_knowledge_parses_structured_json(self) -> None:
        settings = DeepSeekSettings(
            api_key="test-secret",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
            timeout_seconds=5,
        )
        client = DeepSeekClient(settings)
        organized = {
            "title": "注意力理解",
            "core_insight": "权重会随当前输入变化。",
            "logic_chain": ["读取当前输入", "计算相关性", "形成动态权重"],
            "open_questions": ["不同头如何分工？"],
            "next_step": "用一个小例子手算权重。",
        }
        response = FakeResponse(
            {"choices": [{"message": {"role": "assistant", "content": json.dumps(organized, ensure_ascii=False)}}]}
        )

        with patch("deepseek_client.urlopen", return_value=response):
            result = client.organize_knowledge(
                [{"role": "user", "content": "我理解了注意力权重。"}]
            )

        self.assertEqual(result, organized)


if __name__ == "__main__":
    unittest.main()
