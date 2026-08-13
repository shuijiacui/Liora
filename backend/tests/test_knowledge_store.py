import sys
import tempfile
import unittest
import json
import sqlite3
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from database import ReflectionDatabase
from knowledge_store import KnowledgeVault, parse_markdown, render_knowledge_markdown
from service import ReflectionService


class KnowledgeVaultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.vault_path = root / "Vault"
        self.vault_path.mkdir()
        self.database = ReflectionDatabase(root / "data" / "liora.sqlite3")
        self.vault = KnowledgeVault(self.database, self.vault_path, root / "backups")

    def tearDown(self) -> None:
        self.database.close()
        self.temporary.cleanup()

    def test_rich_knowledge_sections_and_sources_round_trip_through_markdown(self) -> None:
        content = {
            "title": "动态注意力",
            "core_insight": "参数固定不等于运行时权重固定。",
            "key_points": ["输入参与权重计算"],
            "logic_chain": ["读取输入", "计算相关性", "形成权重"],
            "examples": ["同一词在不同句子中关注不同位置"],
            "extensions": ["可以和动态卷积做有限类比"],
            "boundaries": ["推理时模型参数不会重新训练"],
            "connections": ["与内容寻址有关"],
            "open_questions": ["不同注意力头如何分工"],
            "next_step": "手算一个小例子。",
            "sources": [
                {
                    "title": "Reference",
                    "url": "https://example.com/reference",
                    "summary": "An explanatory source.",
                }
            ],
        }
        markdown = render_knowledge_markdown(
            {
                "id": "knowledge-id",
                "title": content["title"],
                "created_at": "2026-08-10T00:00:00+00:00",
                "updated_at": "2026-08-10T00:00:00+00:00",
                "version": 1,
                "content": content,
            }
        )
        parsed = parse_markdown(markdown, "fallback")

        self.assertIn("## 延伸理解", markdown)
        self.assertEqual(parsed["content"]["extensions"], content["extensions"])
        self.assertEqual(parsed["content"]["sources"], content["sources"])
        self.assertEqual(parsed["object_type"], "knowledge")

    def test_malformed_historical_liora_markers_are_metadata_not_content(self) -> None:
        parsed = parse_markdown(
            "# 手写标题\n\n<!loria-begin->\n# Liora 整理：真正标题\n\n## 核心理解\n\n真正的知识内容。\n<!loria-end->\n",
            "fallback",
        )
        self.assertEqual(parsed["title"], "真正标题")
        self.assertEqual(parsed["content"]["core_insight"], "真正的知识内容。")
        self.assertNotIn("loria", parsed["content"]["core_insight"].casefold())

    def test_every_markdown_is_a_knowledge_object_without_requiring_markers(self) -> None:
        ordinary = parse_markdown("# 普通笔记\n\n只是随手记录。", "fallback")
        explicit = parse_markdown(
            "---\ntype: concept\n---\n# 注意力\n\n## 尚待探索\n\n- 为什么需要缩放？\n",
            "fallback",
        )
        managed = parse_markdown(
            "# 外部笔记\n\n<!-- liora:begin -->\n## 核心理解\n\n由 Liora 管理。\n<!-- liora:end -->\n",
            "fallback",
        )

        self.assertEqual(ordinary["object_type"], "knowledge")
        self.assertEqual(explicit["object_type"], "concept")
        self.assertEqual(managed["object_type"], "knowledge")

    def test_scan_is_read_only_incremental_and_tracks_a_rename(self) -> None:
        note = self.vault_path / "Notes" / "Attention.md"
        note.parent.mkdir()
        original = "# Attention\n\n权重由当前输入决定。\n"
        note.write_text(original, encoding="utf-8")

        first = self.vault.scan()
        item = self.database.list_knowledge_documents()[0]
        self.assertEqual(first["indexed"], 1)
        self.assertEqual(note.read_text(encoding="utf-8"), original)
        self.assertIn("权重由当前输入决定", item["content"]["core_insight"])

        second = self.vault.scan()
        self.assertEqual(second["unchanged"], 1)

        cached = self.vault.scan(allow_cached=True)
        self.assertTrue(cached["cached"])

        rebuilt = self.vault.rebuild_index()
        self.assertEqual(rebuilt["updated"], 1)

        moved = note.with_name("Dynamic attention.md")
        note.rename(moved)
        renamed = self.vault.scan()
        after = self.database.list_knowledge_documents()[0]
        self.assertEqual(renamed["active"], 1)
        self.assertEqual(after["id"], item["id"])
        self.assertEqual(after["relative_path"], "Notes/Dynamic attention.md")

    def test_migration_is_idempotent_and_creates_a_consistent_backup(self) -> None:
        service = ReflectionService(self.database)
        started = service.start(force_new=True)
        service.reply(started["session"]["id"], "Retrieval practice improves memory.")
        service.finish(started["session"]["id"])
        legacy = service.confirm(started["session"]["id"])["knowledge"]

        first = self.vault.migrate_legacy()
        second = self.vault.migrate_legacy()

        self.assertEqual(first["migrated"], 1)
        self.assertTrue(Path(first["backup_path"]).is_file())
        self.assertEqual(second["migrated"], 0)
        self.assertEqual(second["skipped"], 1)
        files = list((self.vault_path / "00 Inbox" / "Liora").glob("*.md"))
        self.assertEqual(len(files), 1)
        self.assertIn(legacy["id"], files[0].read_text(encoding="utf-8"))

    def test_confirm_writes_markdown_before_completing_the_session(self) -> None:
        service = ReflectionService(
            self.database,
            vault_path=self.vault_path,
            data_dir=Path(self.temporary.name) / "data",
        )
        started = service.start(force_new=True)
        session_id = started["session"]["id"]
        service.reply(session_id, "A file should be the durable knowledge record.")
        service.finish(session_id)
        completed = service.confirm(session_id)

        document = completed["knowledge"]
        markdown = self.vault_path / Path(document["relative_path"])
        self.assertTrue(markdown.is_file())
        self.assertIn("source: liora", markdown.read_text(encoding="utf-8"))
        self.assertEqual(completed["session"]["status"], "completed")
        self.assertEqual(service.knowledge_get(document["id"])["item"]["id"], document["id"])

    def test_extending_an_obsidian_note_preserves_manual_content(self) -> None:
        note = self.vault_path / "Manual.md"
        manual = "# 手工笔记\n\n这部分由用户维护。\n"
        note.write_text(manual, encoding="utf-8")
        self.vault.scan()
        existing = self.database.list_knowledge_documents()[0]

        service = ReflectionService(
            self.database,
            vault_path=self.vault_path,
            data_dir=Path(self.temporary.name) / "data",
        )
        started = service.start(force_new=True, knowledge_id=existing["id"])
        service.reply(started["session"]["id"], "这是通过 Liora 增加的理解。")
        service.finish(started["session"]["id"])
        service.confirm(started["session"]["id"])

        updated = note.read_text(encoding="utf-8")
        self.assertIn("这部分由用户维护。", updated)
        self.assertIn("<!-- liora:begin -->", updated)
        self.assertIn("liora_id:", updated)

    def test_updating_a_liora_note_preserves_content_outside_the_managed_block(self) -> None:
        service = ReflectionService(
            self.database,
            vault_path=self.vault_path,
            data_dir=Path(self.temporary.name) / "data",
        )
        first = service.start(force_new=True)
        service.reply(first["session"]["id"], "Original insight.")
        service.finish(first["session"]["id"])
        knowledge = service.confirm(first["session"]["id"])["knowledge"]
        note = self.vault_path / Path(knowledge["relative_path"])
        note.write_text(note.read_text(encoding="utf-8") + "\n用户补充：不要覆盖这一行。\n", encoding="utf-8")

        continued = service.start(force_new=True, knowledge_id=knowledge["id"])
        service.reply(continued["session"]["id"], "A newer insight.")
        service.finish(continued["session"]["id"])
        service.confirm(continued["session"]["id"])

        updated = note.read_text(encoding="utf-8")
        self.assertIn("用户补充：不要覆盖这一行。", updated)
        self.assertEqual(updated.count("<!-- liora:begin -->"), 1)

    def test_search_supports_chinese_rank_filters_tags_and_pagination(self) -> None:
        notes = self.vault_path / "Notes"
        projects = self.vault_path / "Projects"
        notes.mkdir()
        projects.mkdir()
        (notes / "Attention.md").write_text(
            "---\ntags: [学习, AI]\n---\n# 注意力机制\n\n注意力会根据当前输入动态分配权重。\n",
            encoding="utf-8",
        )
        (projects / "Retrieval.md").write_text(
            "---\ntags:\n  - 学习\n  - 记忆\n---\n# 检索练习\n\n检索练习能够强化长期记忆。 #复习\n",
            encoding="utf-8",
        )
        (self.vault_path / "Weather.md").write_text(
            "# 天气记录\n\n今天有阵雨。\n",
            encoding="utf-8",
        )
        service = ReflectionService(
            self.database,
            vault_path=self.vault_path,
            data_dir=Path(self.temporary.name) / "data",
        )

        chinese = service.knowledge_list(query="检索练习", limit=10)
        self.assertEqual(chinese["total"], 1)
        self.assertEqual(chinese["items"][0]["title"], "检索练习")
        self.assertIn("长期记忆", chinese["items"][0]["snippet"])

        short = service.knowledge_list(query="记忆", limit=10)
        self.assertEqual(short["total"], 1)
        tagged = service.knowledge_list(tag="学习", limit=10)
        self.assertEqual(tagged["total"], 2)
        folder = service.knowledge_list(folder="Projects", limit=10)
        self.assertEqual(folder["total"], 1)
        self.assertIn("复习", folder["items"][0]["tags"])
        self.assertIn({"folder": "Projects", "count": 1}, folder["facets"]["folders"])

        first_page = service.knowledge_list(sort="title", limit=2)
        self.assertEqual(first_page["total"], 3)
        self.assertTrue(first_page["has_more"])
        second_page = service.knowledge_list(sort="title", limit=2, offset=2)
        self.assertEqual(len(second_page["items"]), 1)
        self.assertFalse(second_page["has_more"])
        unusual = service.knowledge_list(query='" OR *', limit=10)
        self.assertEqual(unusual["total"], 0)

    def test_dashboard_counts_every_markdown_and_collects_questions(self) -> None:
        (self.vault_path / "普通笔记.md").write_text("# 普通笔记\n\n也应计入 Dashboard。\n", encoding="utf-8")
        (self.vault_path / "注意力.md").write_text(
            "---\nid: KO-ATTENTION\ntype: concept\ntitle: 注意力机制\n---\n"
            "# 注意力机制\n\n## 核心理解\n\n根据输入动态计算权重。\n\n"
            "## 尚待探索\n\n- 为什么要除以根号 dk？\n",
            encoding="utf-8",
        )
        service = ReflectionService(
            self.database,
            vault_path=self.vault_path,
            data_dir=Path(self.temporary.name) / "data",
        )

        dashboard = service.dashboard()

        self.assertEqual(dashboard["knowledge_count"], 2)
        self.assertNotIn("unclassified_count", dashboard)
        self.assertEqual(dashboard["open_question_count"], 1)
        self.assertEqual(
            {item["title"] for item in dashboard["recent"]},
            {"普通笔记", "注意力机制"},
        )
        self.assertEqual(dashboard["open_questions"][0]["question"], "为什么要除以根号 dk？")

        prompts = service.reflection_prompts()
        self.assertEqual(prompts["total"], 1)
        self.assertEqual(prompts["items"][0]["kind"], "knowledge_gap")
        self.assertEqual(prompts["items"][0]["prompt"], "为什么要除以根号 dk？")
        self.assertEqual(prompts["items"][0]["reason_code"], "open_question")
        self.assertIn("Liora没有额外猜测", prompts["items"][0]["reason"])

    def test_existing_document_index_schema_is_upgraded_without_data_loss(self) -> None:
        root = Path(self.temporary.name)
        database_path = root / "legacy.sqlite3"
        connection = sqlite3.connect(database_path)
        connection.execute(
            """
            CREATE TABLE knowledge_documents (
                id TEXT PRIMARY KEY,
                relative_path TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                content_json TEXT NOT NULL,
                file_mtime_ns INTEGER NOT NULL,
                file_size INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                source TEXT NOT NULL,
                indexed_at TEXT NOT NULL,
                deleted_at TEXT
            )
            """
        )
        content = {
            "title": "旧索引",
            "core_insight": "升级时不应丢失内容。",
            "logic_chain": [],
            "open_questions": [],
            "next_step": "",
        }
        connection.execute(
            """
            INSERT INTO knowledge_documents VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                "legacy-id",
                "Archive/Legacy.md",
                "旧索引",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
                1,
                json.dumps(content, ensure_ascii=False),
                1,
                10,
                "hash",
                "obsidian",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        connection.commit()
        connection.close()

        upgraded = ReflectionDatabase(database_path)
        try:
            item = upgraded.list_knowledge_documents()[0]
            self.assertEqual(item["title"], "旧索引")
            self.assertEqual(item["object_type"], "knowledge")
            self.assertFalse(item["search_indexed"])
            upgraded.upsert_knowledge_document(
                {
                    **item,
                    "folder": "Archive",
                    "tags": ["迁移"],
                    "search_text": "旧索引\n升级时不应丢失内容。",
                }
            )
            result = upgraded.search_knowledge_documents(query="不应丢失", limit=10)
            self.assertEqual(result["total"], 1)
            self.assertEqual(result["items"][0]["id"], "legacy-id")
        finally:
            upgraded.close()


if __name__ == "__main__":
    unittest.main()
