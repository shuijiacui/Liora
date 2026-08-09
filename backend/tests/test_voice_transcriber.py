import sys
import unittest
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from voice_transcriber import VoiceTranscriber


class FakeSoundDevice:
    class default:
        device = (1, 3)

    devices = [
        {"name": "Stereo Mix", "hostapi": 0, "max_input_channels": 2},
        {"name": "Microphone Array (Realtek)", "hostapi": 0, "max_input_channels": 2},
        {"name": "Microphone Array (Realtek HD)", "hostapi": 1, "max_input_channels": 2},
        {"name": "Speakers", "hostapi": 1, "max_input_channels": 0},
    ]

    @classmethod
    def query_devices(cls):
        return cls.devices

    @staticmethod
    def query_hostapis():
        return [{"name": "MME"}, {"name": "Windows WDM-KS"}]


class VoiceTranscriberTests(unittest.TestCase):
    def test_prefers_default_then_matching_wdm_microphone(self) -> None:
        candidates = VoiceTranscriber._input_device_candidates(FakeSoundDevice)
        self.assertEqual(candidates[:2], [1, 2])
        self.assertNotIn(3, candidates)

    def test_initial_status_is_idle_and_local(self) -> None:
        transcriber = VoiceTranscriber(Path(".models"), lambda _event: None)
        status = transcriber.status()
        self.assertEqual(status["state"], "idle")
        self.assertTrue(status["model"].startswith("faster-whisper-"))

    def test_transcript_is_converted_to_simplified_chinese(self) -> None:
        transcriber = VoiceTranscriber(Path(".models"), lambda _event: None)
        converted = transcriber._simplifier.convert("今天學習了注意力機制和軟體設計")
        self.assertEqual(converted, "今天学习了注意力机制和软件设计")

    def test_simplification_keeps_english_and_converts_mixed_text(self) -> None:
        transcriber = VoiceTranscriber(Path(".models"), lambda _event: None)
        converted = transcriber._simplifier.convert("I learned attention 機制 with Python today")
        self.assertEqual(converted, "I learned attention 机制 with Python today")

    def test_transcription_uses_automatic_multilingual_detection(self) -> None:
        events = []

        class Segment:
            text = "I learned attention 機制"
            no_speech_prob = 0.1
            avg_logprob = -0.2

        class Info:
            language = "en"
            language_probability = 0.92

        class Model:
            options = None

            def transcribe(self, _audio, **options):
                self.options = options
                return iter([Segment()]), Info()

        model = Model()
        transcriber = VoiceTranscriber(Path(".models"), events.append)
        transcriber._model = model
        transcriber._record_utterance = lambda: np.ones(3200, dtype=np.float32)
        transcriber._run()

        self.assertIsNone(model.options["language"])
        self.assertTrue(model.options["multilingual"])
        transcript = next(event for event in events if event["type"] == "voice-transcript")
        self.assertEqual(transcript["text"], "I learned attention 机制")
        self.assertGreater(transcript["confidence"], 0.7)

    def test_transcribes_in_memory_pcm_without_opening_the_microphone(self) -> None:
        class Segment:
            text = " 今天天气怎么样"
            no_speech_prob = 0.05
            avg_logprob = -0.1

        class Info:
            language = "zh"
            language_probability = 0.96

        class Model:
            def transcribe(self, _audio, **_options):
                return iter([Segment()]), Info()

        transcriber = VoiceTranscriber(Path(".models"), lambda _event: None)
        transcriber._model = Model()
        pcm = (np.ones(3200, dtype=np.int16) * 1000).tobytes()
        result = transcriber.transcribe_pcm16(pcm, 16_000)
        self.assertEqual(result["text"], "今天天气怎么样")
        self.assertGreater(result["confidence"], 0.8)


if __name__ == "__main__":
    unittest.main()
