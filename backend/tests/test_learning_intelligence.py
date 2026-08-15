import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from database import ReflectionDatabase
from learning_intelligence import (
    discover_strict_relations,
    extract_grounded_structure,
    update_component_state,
)


def note(note_id: str, title: str, logic: list[str], key_points: list[str] | None = None) -> dict:
    content = {
        "title": title,
        "core_insight": key_points[0] if key_points else "",
        "key_points": key_points or [],
        "logic_chain": logic,
        "examples": [],
        "extensions": [],
        "boundaries": [],
        "connections": [],
        "open_questions": [],
        "next_step": "",
    }
    structure = extract_grounded_structure(content, note_id, title)
    return {"id": note_id, "title": title, "content": content, **structure}


class LearningIntelligenceTests(unittest.TestCase):
    def test_grounded_claims_drop_liora_markers_and_keep_exact_evidence(self) -> None:
        content = {
            "key_points": ["<!-- liora:begin -->", "检索练习能够强化提取路径。"],
            "logic_chain": [], "examples": [], "extensions": [], "boundaries": [],
            "connections": [], "open_questions": [], "next_step": "",
        }
        result = extract_grounded_structure(content, "retrieval", "检索练习")
        evidence = [item["evidence"] for item in result["claims"]]
        self.assertEqual(evidence, ["检索练习能够强化提取路径。"])
        self.assertTrue(result["components"])

    def test_only_composable_causal_chains_become_visible_relations(self) -> None:
        source = note("z-source", "反馈学习", ["持续反馈导致误差校正"], ["反馈用于修正偏差"])
        target = note("a-target", "稳定策略", ["误差校正导致策略稳定"], ["稳定来自持续校正"])
        unrelated = note("other", "解释文本", [], ["因为作者给出了解释，所以这句话看起来有因果语气"])

        relations = discover_strict_relations([source, target, unrelated])

        self.assertEqual(len(relations), 1)
        relation = relations[0]
        self.assertEqual(relation["label"], "causal_continuation")
        self.assertEqual(relation["features"]["direction"], ["z-source", "a-target"])
        self.assertEqual(relation["evidence"]["bridge"], "误差校正")
        self.assertIn("不成立", relation["evidence"]["failure_conditions"][0])

    def test_kc_state_uses_outcomes_hints_transfer_and_misconceptions(self) -> None:
        first = update_component_state(None, {
            "evidence_type": "diagnostic", "outcome": "partial",
            "independent_recall": False, "hint_count": 1,
            "misconceptions": ["把相关当成因果"],
        })
        transferred = update_component_state(first, {
            "evidence_type": "transfer", "outcome": "correct",
            "independent_recall": True, "hint_count": 0, "misconceptions": [],
        })
        self.assertGreater(transferred["mastery"], first["mastery"])
        self.assertGreater(transferred["transfer_level"], 0)
        self.assertEqual(transferred["evidence_count"], 2)
        self.assertIn("把相关当成因果", transferred["misconceptions"])

    def test_relation_decision_archives_evidence_and_suppresses_rejected_recall(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = ReflectionDatabase(Path(directory) / "learning.sqlite3")
            try:
                relation = discover_strict_relations([
                    note("left", "反馈", ["反馈导致误差校正"]),
                    note("right", "策略", ["误差校正导致策略稳定"]),
                ])[0]
                database.replace_discovered_relations([relation])
                stored = database.list_relations("candidate")[0]
                database.resolve_relation(
                    stored["id"], "rejected", "not_useful_now",
                    {"id": "left", "title": "反馈"},
                    {"id": "right", "title": "策略"},
                )
                decision = database.list_relation_decisions()[0]
                self.assertEqual(decision["action"], "rejected")
                self.assertEqual(decision["reason_code"], "not_useful_now")
                self.assertEqual(decision["evidence"]["bridge"], "误差校正")

                database.replace_discovered_relations([relation])
                self.assertEqual(database.list_relations("candidate"), [])
            finally:
                database.close()


if __name__ == "__main__":
    unittest.main()
