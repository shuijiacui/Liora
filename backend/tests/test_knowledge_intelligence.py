import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from database import ReflectionDatabase
from knowledge_intelligence import (
    align_knowledge,
    build_knowledge_chunks,
    content_diff,
    discover_relations,
    extract_cognitive_profile,
    granularity_candidates,
    semantic_candidates,
    semantic_clean,
)
from service import ReflectionService


class FakeSemanticEmbedding:
    available = True
    using_semantic_model = True
    model_name = "test-semantic-v1"

    def prepare(self):
        return True

    def status(self):
        return {"available": True, "loaded": True, "model": self.model_name}

    def embed_document(self, text):
        lowered = str(text).casefold()
        if "bfs" in lowered or "广度优先" in lowered or "按层" in lowered:
            return [1.0, 0.0, 0.0]
        if "队列" in lowered:
            return [0.8, 0.2, 0.0]
        return [0.0, 0.0, 1.0]

    def embed_query(self, text):
        return self.embed_document(text)

    def embed_documents(self, texts):
        return [self.embed_document(text) for text in texts]


def content(title: str, core: str, points: list[str] | None = None) -> dict:
    return {
        "title": title,
        "core_insight": core,
        "key_points": points or [core],
        "logic_chain": [],
        "examples": [],
        "extensions": [],
        "boundaries": [],
        "connections": [],
        "open_questions": [],
        "next_step": "",
        "sources": [],
    }


class KnowledgeIntelligenceUnitTests(unittest.TestCase):
    def test_exact_title_alignment_updates_instead_of_creating_duplicate(self) -> None:
        documents = [{"id": "bfs", "title": "BFS", "content": content("BFS", "广度优先搜索使用队列。") }]
        result = align_knowledge(content("BFS", "广度优先搜索按层遍历。"), documents)
        self.assertEqual(result["action"], "update")
        self.assertEqual(result["target_id"], "bfs")
        self.assertEqual(result["decision_basis"], "exact_title")
        self.assertGreaterEqual(result["confidence"], 0.98)

    def test_semantic_search_and_relations_work_across_documents(self) -> None:
        documents = [
            {"id": "bfs", "title": "BFS", "content": content("BFS", "队列实现按层图搜索，适合无权最短路。")},
            {"id": "queue", "title": "队列", "content": content("队列", "先进先出的线性结构，可以支持广度优先遍历。")},
            {"id": "hash", "title": "哈希表", "content": content("哈希表", "通过哈希函数定位键值。")},
        ]
        matches = semantic_candidates("图的按层遍历为什么需要先进先出", documents, 3)
        self.assertTrue({"bfs", "queue"}.issubset({item["knowledge_id"] for item in matches}))
        relations = discover_relations(documents)
        self.assertTrue(any({item["source_id"], item["target_id"]} == {"bfs", "queue"} for item in relations))

    def test_liora_template_scaffolding_is_not_relation_evidence(self) -> None:
        first = content(
            "咖啡烘焙",
            "<!-- liora:begin -->\n## 核心理解\n浅烘焙突出果酸和花香。\n## 尚待探索\n待补充\n<!-- liora:end -->",
        )
        second = content(
            "民法时效",
            "<!loria-begin->\n## 核心理解\n诉讼时效影响请求权的司法保护。\n## 尚待探索\n待补充\n<!loria-end->",
        )
        self.assertNotIn("liora", semantic_clean(first["core_insight"]).casefold())
        self.assertNotIn("loria", semantic_clean(second["core_insight"]).casefold())
        relations = discover_relations([
            {"id": "coffee", "title": "咖啡烘焙", "content": first},
            {"id": "law", "title": "民法时效", "content": second},
        ])
        self.assertEqual(relations, [])

    def test_canonical_chunks_never_contain_liora_scaffolding(self) -> None:
        value = content(
            "递归",
            "<!-- liora:begin -->\n## 核心理解\n递归把问题分解为更小的子问题。\n<!-- liora:end -->",
        )
        chunks = build_knowledge_chunks(value, "recursion")
        self.assertTrue(chunks)
        self.assertTrue(all("liora" not in item["text"].casefold() for item in chunks))
        self.assertTrue(all("核心理解" not in item["text"] for item in chunks))

    def test_whole_document_dense_similarity_cannot_bypass_chunk_evidence(self) -> None:
        documents = [
            {
                "id": "coffee", "title": "咖啡", "content": content("咖啡", "浅烘焙突出果酸。"),
                "embedding": [1.0, 0.0],
                "chunks": [{"id": "coffee-1", "text": "浅烘焙突出果酸。", "section": "core_insight", "embedding": [1.0, 0.0]}],
                "cognitive_profile": {"patterns": []},
            },
            {
                "id": "law", "title": "民法", "content": content("民法", "诉讼时效影响请求权保护。"),
                "embedding": [1.0, 0.0],
                "chunks": [{"id": "law-1", "text": "诉讼时效影响请求权保护。", "section": "core_insight", "embedding": [0.0, 1.0]}],
                "cognitive_profile": {"patterns": []},
            },
        ]
        self.assertEqual(discover_relations(documents, semantic_model=True), [])

    def test_shared_reasoning_pattern_creates_separate_cognitive_relation(self) -> None:
        planning = content("项目规划", "把大型项目分解为可独立推进的工作单元。")
        merge_sort = content("归并排序", "把数组分解为子数组，分别处理后再合并。")
        documents = [
            {"id": "planning", "title": "项目规划", "content": planning, "cognitive_profile": extract_cognitive_profile(planning)},
            {"id": "merge", "title": "归并排序", "content": merge_sort, "cognitive_profile": extract_cognitive_profile(merge_sort)},
        ]
        relations = discover_relations(documents)
        cognitive = next(item for item in relations if item["category"] == "cognitive")
        self.assertEqual(cognitive["evidence"]["pattern_id"], "decomposition")
        self.assertIn("分解", cognitive["evidence"]["source_excerpt"])
        self.assertIn("分解", cognitive["evidence"]["target_excerpt"])

    def test_relation_storage_round_trips_evidence_and_compact_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = ReflectionDatabase(Path(directory) / "liora.sqlite3")
            try:
                relation = {
                    "source_id": "a", "target_id": "b", "kind": "cognitive",
                    "category": "cognitive", "label": "shares_reasoning_pattern:abstraction",
                    "confidence": 0.81, "reason": "共同使用抽象。", "status": "candidate",
                    "evidence": {"source_excerpt": "忽略细节建立模型。", "target_excerpt": "抽象出统一表示。", "basis": "cognitive"},
                    "features": {"pattern_id": "abstraction"}, "pipeline_version": "knowledge-graph-v3",
                }
                database.replace_discovered_relations([relation])
                stored = database.list_relations("candidate")[0]
                self.assertEqual(stored["evidence"]["basis"], "cognitive")
                self.assertEqual(stored["features"]["pattern_id"], "abstraction")
                database.replace_knowledge_chunks(
                    [{"id": "chunk", "knowledge_id": "a", "fingerprint": "fp", "section": "core_insight", "ordinal": 0, "text": "正文证据", "embedding": [0.25, -0.5]}],
                    "test-model",
                )
                vector = database.list_knowledge_chunks()["chunk"]["embedding"]
                self.assertAlmostEqual(vector[0], 0.25, places=3)
                self.assertAlmostEqual(vector[1], -0.5, places=3)
            finally:
                database.close()

    def test_refresh_removes_stale_candidates_but_preserves_user_decisions(self) -> None:
        now = "2026-08-13T12:00:00+00:00"
        with tempfile.TemporaryDirectory() as directory:
            database = ReflectionDatabase(Path(directory) / "liora.sqlite3")
            try:
                with database._lock, database._connection:
                    database._connection.executemany(
                        """
                        INSERT INTO knowledge_relations
                            (id, source_id, target_id, kind, label, confidence, reason, status, created_at, updated_at)
                        VALUES (?, ?, ?, 'soft', 'semantic_similarity', 0.5, 'old', ?, ?, ?)
                        """,
                        [
                            ("candidate", "a", "b", "candidate", now, now),
                            ("confirmed", "c", "d", "confirmed", now, now),
                            ("rejected", "e", "f", "rejected", now, now),
                        ],
                    )
                database.replace_discovered_relations([])
                statuses = {item["id"]: item["status"] for item in database.list_relations()}
                self.assertNotIn("candidate", statuses)
                self.assertEqual(statuses["confirmed"], "confirmed")
                self.assertEqual(statuses["rejected"], "rejected")
            finally:
                database.close()

    def test_refresh_removes_stale_granularity_candidates_but_preserves_user_decisions(self) -> None:
        now = "2026-08-13T12:00:00+00:00"
        with tempfile.TemporaryDirectory() as directory:
            database = ReflectionDatabase(Path(directory) / "liora.sqlite3")
            try:
                with database._lock, database._connection:
                    database._connection.executemany(
                        """
                        INSERT INTO granularity_candidates
                            (id, signature, kind, source_ids_json, score, reasons_json,
                             proposal_json, status, created_at, updated_at)
                        VALUES (?, ?, 'split', '["copilot"]', 0.8, '{}', '{}', ?, ?, ?)
                        """,
                        [
                            ("candidate", "candidate", "candidate", now, now),
                            ("rejected", "rejected", "rejected", now, now),
                        ],
                    )
                database.replace_granularity_candidates([])
                self.assertEqual(
                    [item["id"] for item in database.list_granularity_candidates("candidate")],
                    [],
                )
                self.assertEqual(
                    [item["id"] for item in database.list_granularity_candidates("rejected")],
                    ["rejected"],
                )
            finally:
                database.close()

    def test_diff_and_granularity_are_explainable(self) -> None:
        before = content("Attention", "动态聚合信息。")
        after = {**before, "core_insight": "根据输入关系动态聚合信息。"}
        self.assertEqual(content_diff(before, after)[0]["field"], "core_insight")
        rich = content(
            "Attention",
            "注意力是一组动态聚合机制。",
            ["QKV 表示", "缩放点积", "注意力掩码", "多头表示", "信息路由"],
        )
        candidates = granularity_candidates(
            [{"id": "attention", "title": "Attention", "content": rich}], []
        )
        self.assertTrue(any(item["kind"] == "split" for item in candidates))
        split = next(item for item in candidates if item["kind"] == "split")
        self.assertIn("semantic_separation", split["reasons"])
        self.assertEqual(split["proposal"]["strategy"], "copy_then_link")
        self.assertTrue(split["proposal"]["reversible"])
        self.assertTrue(all(child["source_excerpts"] for child in split["proposal"]["children"]))


class KnowledgeChangeSetFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.vault_path = root / "Vault"
        self.vault_path.mkdir()
        self.database = ReflectionDatabase(root / "data" / "liora.sqlite3")
        self.service = ReflectionService(
            self.database,
            vault_path=self.vault_path,
            data_dir=root / "data",
        )

    def tearDown(self) -> None:
        self.database.close()
        self.temporary.cleanup()

    def _draft(self, title: str, core: str) -> str:
        started = self.service.start(force_new=True)
        session_id = started["session"]["id"]
        self.service.reply(session_id, core)
        draft = self.service.finish(session_id)["knowledge_draft"]
        self.service.update_draft(session_id, {**draft, "title": title, "core_insight": core})
        return session_id

    def test_low_risk_create_is_applied_and_can_be_rolled_back(self) -> None:
        session_id = self._draft("BFS", "BFS 使用队列进行按层遍历，并避免重复访问节点。")
        result = self.service.confirm(session_id)
        self.assertFalse(result["review_required"])
        self.assertEqual(result["changeset"]["status"], "applied")
        path = self.vault_path / result["knowledge"]["relative_path"]
        self.assertTrue(path.exists())

        rolled_back = self.service.rollback_changeset(result["changeset"]["id"])
        self.assertEqual(rolled_back["status"], "rolled_back")
        self.assertFalse(path.exists())

    def test_exact_title_update_reuses_existing_knowledge(self) -> None:
        first = self.service.confirm(self._draft("BFS", "BFS 使用队列按层遍历。"))
        second = self.service.confirm(self._draft("BFS", "BFS 还需要 visited 集合避免重复访问。"))
        self.assertEqual(first["knowledge"]["id"], second["knowledge"]["id"])
        self.assertEqual(second["changeset"]["action"], "update")
        self.assertEqual(len(self.service.knowledge_list(limit=10)["items"]), 1)

    def test_semantic_only_update_waits_for_review_without_touching_markdown(self) -> None:
        first = self.service.confirm(
            self._draft("广度优先搜索", "广度优先搜索使用队列按层遍历图节点，并记录已经访问的节点。")
        )
        original_path = self.vault_path / first["knowledge"]["relative_path"]
        original = original_path.read_text(encoding="utf-8")
        session_id = self._draft(
            "BFS 的队列机制",
            "广度优先搜索使用队列按层遍历图节点，并记录已经访问的节点。",
        )
        result = self.service.confirm(session_id)
        self.assertTrue(result["review_required"])
        self.assertEqual(result["changeset"]["status"], "pending")
        self.assertEqual(original_path.read_text(encoding="utf-8"), original)

    def test_confident_independent_create_is_applied_after_adjudication(self) -> None:
        self.service.confirm(
            self._draft("BFS", "BFS 使用队列按层遍历图节点。")
        )
        session_id = self._draft(
            "线性结构",
            "线性结构用有序的前驱和后继关系组织元素。",
        )
        adjudicated = {
            "action": "create",
            "decision_basis": "deepseek_adjudication",
            "target_id": None,
            "target_title": None,
            "confidence": 0.95,
            "reason": "与候选只共享领域术语，应创建独立知识。",
            "candidates": [{"knowledge_id": "bfs", "score": 0.53}],
            "thresholds": {"related": 0.3},
            "adjudication": {
                "decision": "CREATE",
                "confidence": 0.95,
                "conflicts": [],
                "needs_human_review": False,
            },
        }
        with patch.object(
            self.service,
            "_judge_ambiguous_alignment",
            return_value=adjudicated,
        ):
            result = self.service.confirm(session_id)

        self.assertFalse(result["review_required"])
        self.assertEqual(result["changeset"]["status"], "applied")
        self.assertTrue((self.vault_path / result["knowledge"]["relative_path"]).exists())

    def test_adjudicated_update_still_waits_for_review(self) -> None:
        alignment = {
            "action": "update",
            "decision_basis": "deepseek_adjudication",
            "target_id": "bfs",
            "adjudication": {
                "decision": "UPDATE",
                "confidence": 0.98,
                "conflicts": [],
                "needs_human_review": False,
            },
        }
        self.assertTrue(
            self.service._alignment_requires_review(alignment, None, locally_ambiguous=True)
        )

    def test_adjudicated_create_with_conflicts_still_waits_for_review(self) -> None:
        alignment = {
            "action": "create",
            "decision_basis": "deepseek_adjudication",
            "target_id": None,
            "adjudication": {
                "decision": "CREATE",
                "confidence": 0.96,
                "conflicts": ["与现有定义存在冲突"],
                "needs_human_review": False,
            },
        }
        self.assertTrue(
            self.service._alignment_requires_review(alignment, None, locally_ambiguous=True)
        )

    def test_cross_knowledge_question_returns_evidence(self) -> None:
        self.service.confirm(self._draft("BFS", "BFS 使用队列按层搜索无权图的最短路径。"))
        answer = self.service.knowledge_answer("无权图最短路径为什么使用队列？")
        self.assertTrue(answer["evidence"])
        self.assertEqual(answer["evidence"][0]["title"], "BFS")

    def test_service_uses_semantic_engine_and_reports_its_status(self) -> None:
        service = ReflectionService(
            self.database,
            vault_path=self.vault_path,
            data_dir=Path(self.temporary.name) / "data",
            embedding_engine=FakeSemanticEmbedding(),
        )
        started = service.start(force_new=True)
        session_id = started["session"]["id"]
        service.reply(session_id, "BFS 使用队列按层遍历图节点。")
        draft = service.finish(session_id)["knowledge_draft"]
        service.update_draft(
            session_id,
            {**draft, "title": "BFS", "core_insight": "BFS 使用队列按层遍历图节点。"},
        )
        service.confirm(session_id)
        result = service.semantic_search("广度优先搜索", 3)
        self.assertEqual(result["items"][0]["title"], "BFS")
        self.assertEqual(result["embedding"]["model"], "test-semantic-v1")


if __name__ == "__main__":
    unittest.main()
