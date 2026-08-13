import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from database import ReflectionDatabase
from deepseek_client import DeepSeekError
from service import ReflectionService


class FailingDeepSeekClient:
    configured = True
    settings = SimpleNamespace(model="deepseek-v4-flash")

    def generate_follow_up(self, _conversation, _turn_number):
        raise DeepSeekError("simulated outage")

    def organize_knowledge(self, _conversation, _existing):
        raise DeepSeekError("simulated outage")


class EditingDeepSeekClient:
    configured = True
    settings = SimpleNamespace(model="deepseek-v4-flash")

    def revise_knowledge(self, _conversation, current, instruction, _sources):
        return {**current, "extensions": [instruction]}


class ReflectionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = ReflectionDatabase(Path(self.temp_dir.name) / "test.sqlite3")
        self.service = ReflectionService(self.database)

    def tearDown(self) -> None:
        self.database.close()
        self.temp_dir.cleanup()

    def test_session_is_resumed_and_does_not_auto_complete(self) -> None:
        started = self.service.start()
        resumed = self.service.start()
        self.assertEqual(started["session"]["id"], resumed["session"]["id"])
        self.assertTrue(resumed["resumed"])

        session_id = started["session"]["id"]
        for content in ("I learned about attention.", "Weights depend on input.", "That is the key idea."):
            response = self.service.reply(session_id, content)

        self.assertFalse(response["complete"])
        self.assertEqual(response["session"]["status"], "active")
        self.assertEqual(len(response["messages"]), 7)

    def test_finish_requires_confirmation_then_persists_knowledge(self) -> None:
        started = self.service.start(force_new=True)
        session_id = started["session"]["id"]
        self.service.reply(session_id, "Retrieval practice improves memory.")

        draft = self.service.finish(session_id)
        self.assertFalse(draft["complete"])
        self.assertTrue(draft["awaiting_confirmation"])
        self.assertEqual(draft["session"]["status"], "active")
        self.assertIn("Retrieval practice", draft["knowledge_draft"]["core_insight"])

        completed = self.service.confirm(session_id)
        self.assertTrue(completed["complete"])
        self.assertEqual(completed["session"]["status"], "completed")
        self.assertEqual(len(completed["messages"]), 0)
        self.assertEqual(len(self.service.knowledge_list()["items"]), 1)

    def test_existing_knowledge_can_receive_a_new_revision(self) -> None:
        first = self.service.start(force_new=True)
        self.service.reply(first["session"]["id"], "The first insight.")
        self.service.finish(first["session"]["id"])
        knowledge = self.service.confirm(first["session"]["id"])["knowledge"]

        continued = self.service.start(force_new=True, knowledge_id=knowledge["id"])
        self.service.reply(continued["session"]["id"], "A related new insight.")
        self.service.finish(continued["session"]["id"])
        revised = self.service.confirm(continued["session"]["id"])["knowledge"]

        self.assertEqual(revised["id"], knowledge["id"])
        self.assertEqual(revised["version"], 2)

    def test_unconfirmed_draft_is_resumed_and_replaced_after_more_dialogue(self) -> None:
        started = self.service.start(force_new=True)
        session_id = started["session"]["id"]
        self.service.reply(session_id, "An early thought.")
        first_draft = self.service.finish(session_id)

        resumed = self.service.start()
        self.assertTrue(resumed["awaiting_confirmation"])
        self.assertEqual(resumed["knowledge_draft"], first_draft["knowledge_draft"])

        self.service.reply(session_id, "A clearer later thought.")
        refreshed = self.service.start()
        self.assertNotIn("awaiting_confirmation", refreshed)

    def test_user_can_discard_a_draft_without_saving_knowledge(self) -> None:
        started = self.service.start(force_new=True)
        session_id = started["session"]["id"]
        self.service.reply(session_id, "This thought does not need to be saved.")
        self.service.finish(session_id)

        discarded = self.service.discard(session_id)

        self.assertTrue(discarded["discarded"])
        self.assertIsNone(self.database.get_session(session_id))
        self.assertEqual(self.database.get_messages(session_id), [])
        self.assertIsNone(self.database.get_knowledge_draft(session_id))
        self.assertEqual(self.service.knowledge_list()["items"], [])

    def test_user_can_edit_the_draft_before_confirming(self) -> None:
        started = self.service.start(force_new=True)
        session_id = started["session"]["id"]
        self.service.reply(session_id, "An early thought.")
        draft = self.service.finish(session_id)["knowledge_draft"]
        edited = {
            **draft,
            "title": "A clearer title",
            "core_insight": "A manually clarified explanation.",
            "key_points": ["The user's edited key point."],
        }

        updated = self.service.update_draft(session_id, edited)
        completed = self.service.confirm(session_id)

        self.assertEqual(updated["knowledge_draft"]["title"], "A clearer title")
        self.assertEqual(completed["knowledge"]["content"]["core_insight"], edited["core_insight"])

    def test_ai_revision_uses_the_current_edited_draft(self) -> None:
        service = ReflectionService(self.database, EditingDeepSeekClient())
        started = service.start(force_new=True)
        session_id = started["session"]["id"]
        service._database.add_message(session_id, "user", "A knowledge seed.")
        draft = {
            "title": "Seed",
            "core_insight": "A complete seed explanation.",
            "key_points": ["One point"],
            "logic_chain": [],
            "examples": [],
            "extensions": [],
            "boundaries": [],
            "connections": [],
            "open_questions": [],
            "next_step": "",
            "sources": [],
        }
        self.database.save_knowledge_draft(session_id, draft)

        revised = service.revise_draft(session_id, "加入迁移应用", draft)

        self.assertEqual(revised["knowledge_draft"]["extensions"], ["加入迁移应用"])

    def test_discarding_an_extension_keeps_existing_knowledge_unchanged(self) -> None:
        first = self.service.start(force_new=True)
        self.service.reply(first["session"]["id"], "The original insight.")
        self.service.finish(first["session"]["id"])
        knowledge = self.service.confirm(first["session"]["id"])["knowledge"]

        extension = self.service.start(force_new=True, knowledge_id=knowledge["id"])
        self.service.reply(extension["session"]["id"], "An extension I may discard.")
        self.service.finish(extension["session"]["id"])
        self.service.discard(extension["session"]["id"])

        unchanged = self.service.knowledge_get(knowledge["id"])["item"]
        self.assertEqual(unchanged["version"], 1)
        self.assertEqual(unchanged["content"], knowledge["content"])

    def test_deepseek_failure_falls_back_without_losing_message(self) -> None:
        service = ReflectionService(self.database, FailingDeepSeekClient())
        started = service.start(force_new=True)
        response = service.reply(started["session"]["id"], "I learned about attention.")

        self.assertEqual(response["provider"], "local-fallback")
        self.assertEqual(response["messages"][-2]["role"], "user")
        self.assertEqual(response["messages"][-1]["role"], "assistant")

    def _knowledge_with_question(self) -> tuple[dict, dict]:
        started = self.service.start(force_new=True)
        session_id = started["session"]["id"]
        self.service.reply(session_id, "Retrieval practice strengthens memory.")
        draft = self.service.finish(session_id)["knowledge_draft"]
        edited = {
            **draft,
            "title": "Retrieval practice",
            "open_questions": ["Why does effort improve later recall?"],
        }
        self.service.update_draft(session_id, edited)
        knowledge = self.service.confirm(session_id)["knowledge"]
        prompt = self.service.reflection_prompts(8)["items"][0]
        return knowledge, prompt

    def test_prompt_session_uses_exact_question_and_records_structured_event(self) -> None:
        knowledge, prompt = self._knowledge_with_question()

        started = self.service.start_prompt(prompt["id"])
        session_id = started["session"]["id"]
        self.assertEqual(started["messages"][0]["content"], prompt["prompt"])
        self.assertEqual(started["session"]["prompt_id"], prompt["id"])
        self.assertEqual(started["session"]["session_type"], "review")

        self.service.reply(session_id, "Effort makes retrieval pathways easier to use later.")
        self.service.finish(session_id)
        confirmed = self.service.confirm(session_id)
        self.assertEqual(confirmed["messages"], [])

        rated = self.service.rate_reflection(session_id, "good", True)
        state = rated["knowledge_state"]
        self.assertEqual(state["knowledge_id"], knowledge["id"])
        self.assertEqual(state["reflection_count"], 1)
        self.assertEqual(state["stability_days"], 3.0)
        self.assertTrue(rated["event"]["independent_recall"])
        self.assertEqual(self.database.get_messages(session_id), [])
        self.assertEqual(self.service.reflection_prompts(8)["items"], [])
        repeated = self.service.rate_reflection(session_id, "good", True)
        self.assertEqual(repeated["event"]["id"], rated["event"]["id"])
        self.assertEqual(repeated["knowledge_state"]["reflection_count"], 1)

    def test_skip_rotates_and_snooze_removes_prompt_from_queue(self) -> None:
        _, prompt = self._knowledge_with_question()
        skipped = self.service.skip_prompt(prompt["id"])
        self.assertTrue(skipped["skipped"])
        self.assertEqual(self.service.reflection_prompts(8)["items"][0]["id"], prompt["id"])

        snoozed = self.service.snooze_prompt(prompt["id"], 3)
        self.assertTrue(snoozed["snoozed"])
        self.assertEqual(self.service.reflection_prompts(8)["items"], [])

    def test_discarded_prompt_session_returns_question_to_queue(self) -> None:
        _, prompt = self._knowledge_with_question()
        task = self.service.start_prompt(prompt["id"])
        session_id = task["session"]["id"]
        self.service.reply(session_id, "I want to discard this attempt.")
        self.service.finish(session_id)
        self.service.discard(session_id)

        self.assertEqual(self.service.reflection_prompts(8)["items"][0]["id"], prompt["id"])

    def test_review_can_be_deferred_without_saving_dialogue(self) -> None:
        _, prompt = self._knowledge_with_question()
        task = self.service.start_prompt(prompt["id"])
        session_id = task["session"]["id"]
        self.service.reply(session_id, "This attempt should wait.")

        result = self.service.defer_review(session_id, 3)

        self.assertTrue(result["deferred"])
        self.assertIsNone(self.database.get_session(session_id))
        self.assertEqual(self.database.get_messages(session_id), [])
        self.assertEqual(self.service.reflection_prompts(8)["items"], [])

    def test_review_coexists_with_an_abandoned_reflection_session(self) -> None:
        _, prompt = self._knowledge_with_question()
        empty = self.service.start(force_new=True)

        task = self.service.start_prompt(prompt["id"])

        self.assertIsNotNone(self.database.get_session(empty["session"]["id"]))
        self.assertEqual(task["session"]["prompt_id"], prompt["id"])

    def test_review_coexists_with_a_reflection_that_has_user_content(self) -> None:
        _, prompt = self._knowledge_with_question()
        active = self.service.start(force_new=True)
        self.service.reply(active["session"]["id"], "This explanation is unfinished.")

        review = self.service.start_prompt(prompt["id"])

        self.assertIsNotNone(self.database.get_session(active["session"]["id"]))
        self.assertEqual(review["session"]["session_type"], "review")

    def test_review_button_resumes_only_the_review_channel(self) -> None:
        _, prompt = self._knowledge_with_question()
        reflection = self.service.start(force_new=True)
        review = self.service.start_prompt(prompt["id"])

        resumed = self.service.start_review()

        self.assertEqual(resumed["session"]["id"], review["session"]["id"])
        self.assertNotEqual(resumed["session"]["id"], reflection["session"]["id"])
        self.assertTrue(resumed["resumed"])

    def test_reflection_button_resumes_only_the_reflection_channel(self) -> None:
        _, prompt = self._knowledge_with_question()
        reflection = self.service.start(force_new=True)
        self.service.start_prompt(prompt["id"])

        resumed = self.service.start()

        self.assertEqual(resumed["session"]["id"], reflection["session"]["id"])
        self.assertEqual(resumed["session"]["session_type"], "reflection")
        self.assertTrue(resumed["resumed"])

    def test_review_button_has_a_friendly_empty_state(self) -> None:
        result = self.service.start_review()

        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "no_due_prompt")

    def test_legacy_sessions_gain_channel_types_idempotently(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy.sqlite3"
        connection = sqlite3.connect(legacy_path)
        connection.execute(
            """
            CREATE TABLE reflection_sessions (
                id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                knowledge_id TEXT,
                prompt_id TEXT,
                prompt_kind TEXT,
                prompt_text TEXT,
                prompt_reason TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO reflection_sessions VALUES (?, ?, NULL, 'active', '', NULL, NULL, NULL, NULL, NULL)",
            ("old-reflection", "2026-01-01T00:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO reflection_sessions VALUES (?, ?, NULL, 'active', '', 'K-1', 'P-1', 'knowledge_gap', 'Q', 'R')",
            ("old-review", "2026-01-02T00:00:00+00:00"),
        )
        connection.commit()
        connection.close()

        first = ReflectionDatabase(legacy_path)
        self.assertEqual(first.get_session("old-reflection")["session_type"], "reflection")
        self.assertEqual(first.get_session("old-review")["session_type"], "review")
        first.close()
        second = ReflectionDatabase(legacy_path)
        self.assertEqual(second.get_session("old-review")["session_type"], "review")
        second.close()


if __name__ == "__main__":
    unittest.main()
