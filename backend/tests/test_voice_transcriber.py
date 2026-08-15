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
        self.assertEqual(status["model"], "sensevoice-small-int8")

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

        class Model:
            options = None

            def transcribe(self, _audio, **options):
                self.options = options
                return {
                    "text": "I learned attention 機制",
                    "language": "en",
                    "language_probability": 0.92,
                    "confidence": 0.84,
                    "token_count": 5,
                }

        model = Model()
        transcriber = VoiceTranscriber(Path(".models"), events.append)
        transcriber._model = model
        transcriber._schedule_model_unload = lambda: None
        transcriber._record_utterance = lambda: np.ones(3200, dtype=np.float32)
        transcriber._run()

        self.assertEqual(model.options["language"], "auto")
        self.assertTrue(model.options["use_itn"])
        transcript = next(event for event in events if event["type"] == "voice-transcript")
        self.assertEqual(transcript["text"], "I learned attention 机制")
        self.assertGreater(transcript["confidence"], 0.7)

    def test_transcribes_in_memory_pcm_without_opening_the_microphone(self) -> None:
        class Model:
            def transcribe(self, _audio, **_options):
                return {
                    "text": " 今天天气怎么样",
                    "language": "zh",
                    "language_probability": 0.96,
                    "confidence": 0.9,
                    "token_count": 7,
                }

        transcriber = VoiceTranscriber(Path(".models"), lambda _event: None)
        transcriber._model = Model()
        transcriber._schedule_model_unload = lambda: None
        pcm = (np.ones(3200, dtype=np.int16) * 1000).tobytes()
        result = transcriber.transcribe_pcm16(pcm, 16_000)
        self.assertEqual(result["text"], "今天天气怎么样")
        self.assertGreater(result["confidence"], 0.8)

    def test_long_audio_is_split_without_exceeding_model_limit(self) -> None:
        audio = np.ones(60 * 16_000, dtype=np.float32)
        audio[20 * 16_000 : 20 * 16_000 + 1600] = 0
        audio[42 * 16_000 : 42 * 16_000 + 1600] = 0
        chunks = VoiceTranscriber._segment_audio(audio)
        self.assertGreaterEqual(len(chunks), 3)
        self.assertEqual(sum(map(len, chunks)), len(audio))
        self.assertLessEqual(max(map(len, chunks)), 28 * 16_000)

    def test_resampling_is_float32_and_memory_bounded_output(self) -> None:
        source = np.linspace(-1, 1, 48_000, dtype=np.float32)
        result = VoiceTranscriber._resample_audio(source, 48_000, 16_000)
        self.assertEqual(result.dtype, np.float32)
        self.assertEqual(len(result), 16_000)
        self.assertAlmostEqual(float(result[0]), -1.0, places=5)


if __name__ == "__main__":
    unittest.main()
