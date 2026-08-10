import json
import base64
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from database import ReflectionDatabase
from main import ReflectionHandler, ThreadingHTTPServer, format_voice_event
from service import ReflectionService


class ReflectionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = ReflectionDatabase(Path(self.temp_dir.name) / "api.sqlite3")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ReflectionHandler)
        self.server.service = ReflectionService(self.database)
        self.server.voice_transcriber = None
        self.server.api_token = "test-token"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.database.close()
        self.temp_dir.cleanup()

    def request(self, path: str, payload: dict | None = None, token: str = "test-token") -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method="POST" if payload is not None else "GET",
            headers={"X-Liora-Token": token, "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_full_http_reflection_flow(self) -> None:
        started = self.request("/api/reflections/start", {"force_new": False})
        session_id = started["session"]["id"]
        response = None
        for content in ("今天学了注意力机制。", "它会按输入改变权重。", "记住权重来自当前输入。"):
            response = self.request(f"/api/reflections/{session_id}/messages", {"content": content})
        self.assertFalse(response["complete"])

        draft = self.request(f"/api/reflections/{session_id}/finish", {})
        self.assertTrue(draft["awaiting_confirmation"])
        edited_content = {
            **draft["knowledge_draft"],
            "title": "注意力机制知识",
            "core_insight": "注意力的运行时权重由当前输入之间的关系动态决定。",
        }
        edited = self.request(
            f"/api/reflections/{session_id}/draft",
            {"content": edited_content},
        )
        self.assertEqual(edited["knowledge_draft"]["title"], "注意力机制知识")
        completed = self.request(f"/api/reflections/{session_id}/confirm", {})
        self.assertTrue(completed["complete"])

        knowledge = self.request("/api/knowledge?limit=10")
        self.assertEqual(knowledge["items"][0]["id"], completed["knowledge"]["id"])

        searched = self.request(f"/api/knowledge?q={quote('注意力')}&limit=10&offset=0")
        self.assertEqual(searched["total"], 1)
        self.assertEqual(searched["items"][0]["id"], completed["knowledge"]["id"])

        history = self.request("/api/reflections?limit=10")
        self.assertEqual(history["sessions"][0]["id"], session_id)

    def test_api_rejects_missing_token(self) -> None:
        with self.assertRaises(HTTPError) as context:
            self.request("/health", token="wrong-token")
        self.assertEqual(context.exception.code, 401)

    def test_discard_endpoint_removes_the_draft_without_creating_knowledge(self) -> None:
        started = self.request("/api/reflections/start", {"force_new": True})
        session_id = started["session"]["id"]
        self.request(
            f"/api/reflections/{session_id}/messages",
            {"content": "这次内容不需要保存。"},
        )
        self.request(f"/api/reflections/{session_id}/finish", {})

        discarded = self.request(f"/api/reflections/{session_id}/discard", {})

        self.assertTrue(discarded["discarded"])
        self.assertEqual(self.request("/api/knowledge?limit=10")["items"], [])

    def test_voice_event_pipe_is_ascii_and_round_trips_chinese(self) -> None:
        line = format_voice_event({"type": "voice-transcript", "text": "今天学习了注意力机制"})
        line.encode("ascii")
        payload = json.loads(line.removeprefix("LIORA_VOICE_EVENT "))
        self.assertEqual(payload["text"], "今天学习了注意力机制")

    def test_command_audio_is_transcribed_in_memory(self) -> None:
        calls = []

        class Transcriber:
            @staticmethod
            def transcribe_pcm16(audio: bytes, sample_rate: int) -> dict:
                calls.append((audio, sample_rate))
                return {"text": "今天天气怎么样", "confidence": 0.91}

        self.server.voice_transcriber = Transcriber()
        result = self.request(
            "/api/voice/command-transcript",
            {
                "encoding": "pcm_s16le",
                "sample_rate": 16_000,
                "audio": base64.b64encode(b"\x01\x02\x03\x04").decode("ascii"),
            },
        )
        self.assertEqual(result["text"], "今天天气怎么样")
        self.assertEqual(calls, [(b"\x01\x02\x03\x04", 16_000)])


if __name__ == "__main__":
    unittest.main()
