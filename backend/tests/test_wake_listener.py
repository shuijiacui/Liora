import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from wake_listener import (
    encoded_audio_event,
    is_wake_phrase,
    normalize,
    result_confidence,
)


class WakeListenerTests(unittest.TestCase):
    def test_matches_english_and_chinese_wake_variants(self) -> None:
        self.assertTrue(is_wake_phrase("hi laura", ("hi laura",)))
        self.assertTrue(is_wake_phrase("hi lee aura", ("hi lee aura",)))
        self.assertTrue(is_wake_phrase("hey lia ora", ("hey lia ora",)))
        self.assertTrue(is_wake_phrase("嗨 莉 奥 拉", ("嗨莉奥拉",)))
        self.assertFalse(is_wake_phrase("today is sunny", ("hi liora",)))

    def test_normalizes_spacing_and_averages_word_confidence(self) -> None:
        self.assertEqual(normalize("Hi, Li Ora!"), "hiliora")
        self.assertEqual(
            result_confidence({"result": [{"conf": 0.8}, {"conf": 0.6}]}),
            0.7,
        )

    def test_command_audio_stays_in_memory_and_round_trips(self) -> None:
        event = encoded_audio_event([b"\x01\x02", b"\x03\x04"], 16_000, "session", "follow-up")
        self.assertEqual(event["type"], "command-audio")
        self.assertEqual(event["session_id"], "session")
        self.assertEqual(event["encoding"], "pcm_s16le")
        self.assertEqual(event["audio"], "AQIDBA==")


if __name__ == "__main__":
    unittest.main()
