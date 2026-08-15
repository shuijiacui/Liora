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
            "core_insight": "参数在训练后固定，但注意力分布仍会随当前输入变化。",
            "key_points": ["参数与运行时权重不是同一概念", "输入决定当前注意力分布"],
            "logic_chain": ["读取当前输入", "计算相关性", "形成动态权重"],
            "examples": ["同一个词在不同句子中会关注不同上下文。"],
            "extensions": ["这种动态性可以用于建立与动态卷积的有限类比。"],
            "boundaries": ["不能说模型参数会在每次推理时重新训练。"],
            "connections": ["与动态卷积都具有输入相关的计算行为。"],
            "open_questions": ["不同头如何分工？"],
            "next_step": "用一个小例子手算权重。",
            "sources": [],
        }
        response = FakeResponse(
            {"choices": [{"message": {"role": "assistant", "content": json.dumps(organized, ensure_ascii=False)}}]}
        )

        with patch("deepseek_client.urlopen", return_value=response):
            result = client.organize_knowledge(
                [{"role": "user", "content": "我理解了注意力权重。"}]
            )

        self.assertEqual(result, organized)

    def test_revise_knowledge_uses_current_draft_and_instruction(self) -> None:
        settings = DeepSeekSettings(
            api_key="test-secret",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
            timeout_seconds=5,
        )
        client = DeepSeekClient(settings)
        current = {
            "title": "注意力理解",
            "core_insight": "注意力权重随输入变化。",
            "key_points": ["权重是动态的"],
            "logic_chain": ["输入", "权重"],
            "examples": [],
            "extensions": [],
            "boundaries": [],
            "connections": [],
            "open_questions": [],
            "next_step": "",
            "sources": [],
        }
        revised = {**current, "examples": ["同一个词在不同上下文中得到不同权重。"]}
        response = FakeResponse(
            {"choices": [{"message": {"role": "assistant", "content": json.dumps(revised, ensure_ascii=False)}}]}
        )

        with patch("deepseek_client.urlopen", return_value=response) as mocked_urlopen:
            result = client.revise_knowledge([], current, "增加一个例子")

        self.assertEqual(result["examples"], revised["examples"])
        body = json.loads(mocked_urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertIn("增加一个例子", body["messages"][-1]["content"])

    def test_alignment_judge_is_constrained_to_retrieved_candidates(self) -> None:
        settings = DeepSeekSettings(
            api_key="test-secret",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
            timeout_seconds=5,
        )
        client = DeepSeekClient(settings)
        response = FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "decision": "UPDATE",
                                    "target_id": "bfs",
                                    "relationship": "same mechanism",
                                    "conflicts": [],
                                    "reason": "两者解释同一个 BFS 层序扩展机制。",
                                    "confidence": 0.86,
                                    "needs_human_review": True,
                                },
                                ensure_ascii=False,
                            ),
                        }
                    }
                ]
            }
        )
        with patch("deepseek_client.urlopen", return_value=response):
            result = client.judge_alignment(
                {"title": "BFS 的层序扩展", "core_insight": "使用队列逐层访问。"},
                [{"knowledge_id": "bfs", "title": "广度优先搜索", "score": 0.54}],
            )
        self.assertEqual(result["decision"], "UPDATE")
        self.assertEqual(result["target_id"], "bfs")

        invalid = FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {"decision": "UPDATE", "target_id": "invented"}
                            ),
                        }
                    }
                ]
            }
        )
        with patch("deepseek_client.urlopen", return_value=invalid):
            with self.assertRaises(Exception):
                client.judge_alignment(
                    {"title": "BFS"},
                    [{"knowledge_id": "bfs", "title": "广度优先搜索", "score": 0.54}],
                )

    def test_cognitive_profile_keeps_only_schema_bound_verbatim_evidence(self) -> None:
        settings = DeepSeekSettings(
            api_key="test-secret",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            timeout_seconds=5,
        )
        client = DeepSeekClient(settings)
        response = FakeResponse(
            {
                "choices": [{"message": {"role": "assistant", "content": json.dumps({
                    "patterns": [
                        {"id": "decomposition", "description": "拆成独立工作单元", "evidence": "把大型项目分解为可独立推进的工作单元。", "section": "core_insight", "confidence": 0.91},
                        {"id": "worldview", "description": "模型自由联想", "evidence": "把大型项目分解为可独立推进的工作单元。", "section": "core_insight", "confidence": 0.99},
                        {"id": "abstraction", "description": "没有原文支持", "evidence": "这是模型改写而不是原句。", "section": "core_insight", "confidence": 0.95},
                    ],
                    "problem_structure": "把整体任务转化为可独立处理的局部任务",
                }, ensure_ascii=False)}}]
            }
        )
        with patch("deepseek_client.urlopen", return_value=response):
            result = client.analyze_cognitive_profile(
                "项目规划",
                [{"section": "core_insight", "text": "把大型项目分解为可独立推进的工作单元。"}],
            )
        self.assertEqual([item["id"] for item in result["patterns"]], ["decomposition"])
        self.assertEqual(result["patterns"][0]["evidence"], "把大型项目分解为可独立推进的工作单元。")


if __name__ == "__main__":
    unittest.main()
