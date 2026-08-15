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
from main import (
    ReflectionHandler,
    ThreadingHTTPServer,
    format_reflection_event,
    format_voice_event,
)
from service import ReflectionService


class ReflectionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = ReflectionDatabase(Path(self.temp_dir.name) / "api.sqlite3")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ReflectionHandler)
        self.server.service = ReflectionService(self.database)
        self.server.voice_transcriber = None
        self.server.api_token = "test-token"
        self.reflection_events = []
        self.server.reflection_event_callback = self.reflection_events.append
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

    def test_dashboard_endpoint_returns_knowledge_summary(self) -> None:
        started = self.request("/api/reflections/start", {"force_new": True})
        session_id = started["session"]["id"]
        self.request(
            f"/api/reflections/{session_id}/messages",
            {"content": "检索练习会强化记忆。"},
        )
        self.request(f"/api/reflections/{session_id}/finish", {})
        self.request(f"/api/reflections/{session_id}/confirm", {})

        dashboard = self.request("/api/dashboard")

        self.assertEqual(dashboard["knowledge_count"], 1)
        self.assertEqual(len(dashboard["recent"]), 1)
        self.assertEqual(dashboard["health"], {"growing": 1, "stable": 0, "due": 1})

    def test_reflection_prompts_endpoint_uses_real_open_questions(self) -> None:
        started = self.request("/api/reflections/start", {"force_new": True})
        session_id = started["session"]["id"]
        self.request(
            f"/api/reflections/{session_id}/messages",
            {"content": "注意力会动态聚合信息，但我还不理解为什么需要缩放。"},
        )
        draft = self.request(f"/api/reflections/{session_id}/finish", {})
        edited = {
            **draft["knowledge_draft"],
            "title": "注意力机制",
            "open_questions": ["为什么点积结果需要缩放？"],
        }
        self.request(f"/api/reflections/{session_id}/draft", {"content": edited})
        self.request(f"/api/reflections/{session_id}/confirm", {})

        prompts = self.request("/api/reflection-prompts?limit=8")

        self.assertEqual(prompts["total"], 1)
        self.assertEqual(prompts["items"][0]["prompt"], "为什么点积结果需要缩放？")
        self.assertEqual(prompts["items"][0]["reason_code"], "open_question")

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

    def test_obsidian_prompt_starts_pet_session_then_accepts_rating(self) -> None:
        started = self.request("/api/reflections/start", {"force_new": True})
        session_id = started["session"]["id"]
        self.request(f"/api/reflections/{session_id}/messages", {"content": "检索练习强化记忆。"})
        draft = self.request(f"/api/reflections/{session_id}/finish", {})
        draft["knowledge_draft"]["open_questions"] = ["为什么主动提取更有效？"]
        self.request(f"/api/reflections/{session_id}/draft", {"content": draft["knowledge_draft"]})
        self.request(f"/api/reflections/{session_id}/confirm", {})
        prompt = self.request("/api/reflection-prompts?limit=8")["items"][0]

        task = self.request(f"/api/reflection-prompts/{prompt['id']}/start", {})
        task_id = task["session"]["id"]
        self.assertEqual(task["messages"][0]["content"], prompt["prompt"])
        self.assertEqual(self.reflection_events[0]["type"], "review-task-started")
        self.assertEqual(self.reflection_events[0]["session_id"], task_id)

        self.request(f"/api/reflections/{task_id}/messages", {"content": "因为提取本身会强化路径。"})
        self.request(f"/api/reflections/{task_id}/finish", {})
        self.request(f"/api/reflections/{task_id}/confirm", {})
        rated = self.request(
            f"/api/reflections/{task_id}/rate",
            {"rating": "easy", "independent_recall": True},
        )
        self.assertEqual(rated["knowledge_state"]["stability_days"], 7.0)
        self.assertTrue(rated["event"]["independent_recall"])

    def test_review_start_endpoint_returns_a_friendly_empty_state(self) -> None:
        result = self.request("/api/reviews/start", {})

        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "no_due_prompt")

    def test_reflection_event_pipe_is_ascii_and_round_trips_chinese(self) -> None:
        line = format_reflection_event({"type": "review-task-started", "title": "注意力机制"})
        line.encode("ascii")
        payload = json.loads(line.removeprefix("LIORA_REFLECTION_EVENT "))
        self.assertEqual(payload["title"], "注意力机制")

    def test_intelligence_endpoints_return_structured_empty_results(self) -> None:
        self.assertEqual(self.request("/api/changesets?status=pending")["items"], [])
        self.assertEqual(self.request("/api/relations")["items"], [])
        granularity = self.request("/api/granularity")
        self.assertEqual(granularity["items"], [])
        self.assertEqual(granularity["hierarchy"], [])
        answer = self.request("/api/knowledge/ask", {"question": "当前知识库里有什么？"})
        self.assertEqual(answer["provider"], "local")
        self.assertEqual(answer["evidence"], [])

    def test_relation_decisions_endpoint_archives_confirm_and_reject_actions(self) -> None:
        self.database.replace_discovered_relations([{
            "source_id": "source", "target_id": "target", "kind": "typed_path",
            "category": "knowledge", "label": "causal_continuation",
            "confidence": 0.92, "reason": "A → B → C", "status": "candidate",
            "evidence": {
                "source_excerpt": "A 导致 B", "target_excerpt": "B 导致 C",
                "bridge": "B", "path": [{"evidence": "A 导致 B"}, {"evidence": "B 导致 C"}],
                "learning_payoff": "连接两段因果链。", "failure_conditions": ["条件不同则不成立。"],
            },
            "features": {"canonical_key": "source-target-causal", "direction": ["source", "target"]},
            "pipeline_version": "learning-engine-v4",
        }])
        relation_id = self.database.list_relations("candidate")[0]["id"]

        self.request(
            f"/api/relations/{relation_id}/confirm",
            {"reason_code": "learning_value_confirmed"},
        )
        decisions = self.request("/api/relation-decisions?limit=10")

        self.assertEqual(decisions["total"], 1)
        self.assertEqual(decisions["items"][0]["action"], "confirmed")
        self.assertEqual(decisions["items"][0]["evidence"]["bridge"], "B")

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
