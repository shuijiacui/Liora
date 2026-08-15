"""Lean SenseVoice-Small INT8 ONNX inference for Liora.

The feature extraction and greedy CTC decoding follow the open-source FunASR
ONNX runtime (Apache-2.0).  Keeping the small adapter here avoids importing the
full FunASR/PyTorch audio stack into Liora's long-lived backend process.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import numpy as np


LANGUAGE_INPUTS = {
    "auto": 0,
    "zh": 3,
    "en": 4,
    "yue": 7,
    "ja": 11,
    "ko": 12,
    "nospeech": 13,
}
TEXT_NORM_INPUTS = {True: 14, False: 15}


class SenseVoiceRuntime:
    """Single-session, batch-one SenseVoice-Small CPU runtime."""

    sample_rate = 16_000

    def __init__(self, model_dir: Path, cpu_threads: int | None = None):
        self.model_dir = Path(model_dir)
        required = ("model_quant.onnx", "tokens.json", "am.mvn")
        missing = [name for name in required if not (self.model_dir / name).is_file()]
        if missing:
            raise FileNotFoundError(
                f"SenseVoice 模型不完整（缺少 {', '.join(missing)}），"
                "请运行 python scripts/setup-voice-model.py。"
            )

        with (self.model_dir / "tokens.json").open("r", encoding="utf-8") as handle:
            self._tokens: list[str] = json.load(handle)
        self._special_token_start = next(
            (index for index, token in enumerate(self._tokens) if token.startswith("<|")),
            len(self._tokens),
        )
        self._language_tokens = {
            index: token[2:-2]
            for index, token in enumerate(self._tokens)
            if token.startswith("<|")
            and token.endswith("|>")
            and token[2:-2] in {"zh", "en", "zh/en", "en/zh", "yue", "ja", "ko", "nospeech"}
        }
        self._cmvn = self._load_cmvn(self.model_dir / "am.mvn")

        import kaldi_native_fbank as knf
        import onnxruntime as ort

        self._knf = knf
        self._fbank_options = self._create_fbank_options(knf)
        threads = cpu_threads or _bounded_int_env(
            "LIORA_VOICE_THREADS", max(2, min(4, os.cpu_count() or 2)), 1, 8
        )
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        # The process is mostly idle. Avoid retaining an arena sized for the
        # largest dictation and accept a small allocation cost per request.
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        options.log_severity_level = 3
        self._session = ort.InferenceSession(
            str(self.model_dir / "model_quant.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )

    @staticmethod
    def _create_fbank_options(knf):
        options = knf.FbankOptions()
        options.frame_opts.samp_freq = 16_000
        options.frame_opts.dither = 1.0
        options.frame_opts.window_type = "hamming"
        options.frame_opts.frame_shift_ms = 10.0
        options.frame_opts.frame_length_ms = 25.0
        options.frame_opts.snip_edges = True
        options.mel_opts.num_bins = 80
        options.mel_opts.debug_mel = False
        options.energy_floor = 0
        return options

    @staticmethod
    def _load_cmvn(path: Path) -> np.ndarray:
        means: list[str] = []
        scales: list[str] = []
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines[:-1]):
            parts = line.split()
            if not parts:
                continue
            values = lines[index + 1].split()
            if len(values) < 5 or values[0] != "<LearnRateCoef>":
                continue
            if parts[0] == "<AddShift>":
                means = values[3:-1]
            elif parts[0] == "<Rescale>":
                scales = values[3:-1]
        if not means or len(means) != len(scales):
            raise ValueError("SenseVoice 的 am.mvn 无法解析。")
        return np.asarray([means, scales], dtype=np.float32)

    def _extract_features(self, audio: np.ndarray) -> np.ndarray:
        waveform = np.ascontiguousarray(audio, dtype=np.float32)
        if waveform.ndim != 1:
            waveform = waveform.reshape(-1)
        waveform = np.clip(waveform, -1.0, 1.0)

        fbank = self._knf.OnlineFbank(self._fbank_options)
        scaled = waveform * np.float32(32768.0)
        fbank.accept_waveform(self.sample_rate, scaled.tolist())
        frame_count = fbank.num_frames_ready
        if frame_count <= 0:
            raise ValueError("没有检测到足够长的语音。")
        features = np.empty((frame_count, 80), dtype=np.float32)
        for index in range(frame_count):
            features[index] = fbank.get_frame(index)

        # Low-frame-rate stacking from SenseVoice's frontend_conf: m=7, n=6.
        lfr_m, lfr_n = 7, 6
        output_frames = int(math.ceil(frame_count / lfr_n))
        left_padding = (lfr_m - 1) // 2
        padded = np.pad(features, ((left_padding, 0), (0, 0)), mode="edge")
        indices = (
            np.arange(output_frames, dtype=np.int32)[:, None] * lfr_n
            + np.arange(lfr_m, dtype=np.int32)[None, :]
        )
        np.minimum(indices, padded.shape[0] - 1, out=indices)
        stacked = padded[indices].reshape(output_frames, lfr_m * 80)
        stacked += self._cmvn[0, : stacked.shape[1]]
        stacked *= self._cmvn[1, : stacked.shape[1]]
        return np.ascontiguousarray(stacked, dtype=np.float32)

    @staticmethod
    def _probability(logits: np.ndarray, token_id: int) -> float:
        maximum = float(np.max(logits))
        shifted = np.asarray(logits, dtype=np.float32) - np.float32(maximum)
        np.exp(shifted, out=shifted)
        denominator = float(np.sum(shifted, dtype=np.float64))
        if denominator <= 0:
            return 0.0
        return float(math.exp(float(logits[token_id]) - maximum) / denominator)

    def transcribe(
        self,
        audio: np.ndarray,
        *,
        language: str = "auto",
        use_itn: bool = True,
    ) -> dict:
        language_key = str(language or "auto").lower()
        if language_key not in LANGUAGE_INPUTS:
            raise ValueError(f"SenseVoice 不支持语言参数：{language}")

        features = self._extract_features(audio)
        outputs = self._session.run(
            ["ctc_logits", "encoder_out_lens"],
            {
                "speech": features[None, :, :],
                "speech_lengths": np.asarray([features.shape[0]], dtype=np.int32),
                "language": np.asarray([LANGUAGE_INPUTS[language_key]], dtype=np.int32),
                "textnorm": np.asarray([TEXT_NORM_INPUTS[bool(use_itn)]], dtype=np.int32),
            },
        )
        logits = outputs[0][0]
        output_length = min(int(np.asarray(outputs[1]).reshape(-1)[0]), logits.shape[0])
        logits = logits[:output_length]
        best_ids = np.argmax(logits, axis=1)

        collapsed: list[tuple[int, int]] = []
        previous = -1
        for frame_index, raw_token_id in enumerate(best_ids):
            token_id = int(raw_token_id)
            if token_id == previous:
                continue
            previous = token_id
            if token_id != 0:
                collapsed.append((frame_index, token_id))

        detected_language = ""
        language_probability = 0.0
        pieces: list[str] = []
        token_probabilities: list[float] = []
        for frame_index, token_id in collapsed:
            if token_id in self._language_tokens and not detected_language:
                detected_language = self._language_tokens[token_id]
                language_probability = self._probability(logits[frame_index], token_id)
            if token_id >= self._special_token_start:
                continue
            pieces.append(self._tokens[token_id])
            token_probabilities.append(self._probability(logits[frame_index], token_id))

        text = "".join(pieces).replace("▁", " ").strip()
        confidence = (
            math.exp(
                sum(math.log(max(probability, 1e-8)) for probability in token_probabilities)
                / len(token_probabilities)
            )
            if token_probabilities
            else 0.0
        )
        if detected_language in {"zh/en", "en/zh"}:
            detected_language = "zh"
        if not detected_language:
            detected_language = language_key if language_key != "auto" else "unknown"

        return {
            "text": text,
            "language": detected_language,
            "language_probability": float(language_probability),
            "confidence": float(confidence),
            "token_count": len(token_probabilities),
        }


def _bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))
