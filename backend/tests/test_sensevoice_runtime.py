import sys
import unittest
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sensevoice_runtime import SenseVoiceRuntime


class FakeSession:
    def __init__(self, logits: np.ndarray):
        self.logits = logits
        self.inputs = None

    def run(self, _outputs, inputs):
        self.inputs = inputs
        return self.logits[None, :, :], np.asarray([len(self.logits)], dtype=np.int32)


class SenseVoiceRuntimeTests(unittest.TestCase):
    def test_greedy_ctc_decodes_text_tags_and_confidence(self) -> None:
        runtime = SenseVoiceRuntime.__new__(SenseVoiceRuntime)
        runtime._tokens = ["<unk>", "▁hello", "world", "<|zh|>"]
        runtime._special_token_start = 3
        runtime._language_tokens = {3: "zh"}
        runtime._extract_features = lambda _audio: np.ones((5, 560), dtype=np.float32)
        logits = np.full((5, 4), -4.0, dtype=np.float32)
        for frame, token in enumerate((3, 1, 1, 0, 2)):
            logits[frame, token] = 5.0
        runtime._session = FakeSession(logits)

        result = runtime.transcribe(np.ones(3200, dtype=np.float32))

        self.assertEqual(result["text"], "helloworld")
        self.assertEqual(result["language"], "zh")
        self.assertEqual(result["token_count"], 2)
        self.assertGreater(result["confidence"], 0.99)
        self.assertEqual(runtime._session.inputs["language"].tolist(), [0])
        self.assertEqual(runtime._session.inputs["textnorm"].tolist(), [14])


if __name__ == "__main__":
    unittest.main()
