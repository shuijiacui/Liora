import sys
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


if __name__ == "__main__":
    unittest.main()
