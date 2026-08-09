import os
import queue
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

# The user's Conda NumPy and the CTranslate2 wheel bundle separate copies of
# Intel OpenMP. This process only runs one small CPU transcription at a time.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import numpy as np
from opencc import OpenCC


class VoiceTranscriber:
    def __init__(self, model_root: Path, emit: Callable[[dict], None]):
        self._model_root = model_root
        self._model_name = os.getenv("LIORA_WHISPER_MODEL", "small").strip() or "small"
        self._simplifier = OpenCC("tw2sp")
        self._emit = emit
        self._model = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._discard = False
        self._lock = threading.RLock()
        self._transcription_lock = threading.Lock()
        self._state = "idle"
        self._error = ""

    def status(self) -> dict:
        with self._lock:
            return {"state": self._state, "error": self._error, "model": f"faster-whisper-{self._model_name}"}

    def start(self) -> dict:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self.status()
            self._stop_event.clear()
            self._discard = False
            self._error = ""
            self._set_state("loading" if self._model is None else "preparing")
            self._thread = threading.Thread(target=self._run, name="liora-whisper", daemon=True)
            self._thread.start()
        return self.status()

    def stop(self, discard: bool = False) -> dict:
        with self._lock:
            self._discard = self._discard or discard
            self._stop_event.set()
        return self.status()

    def _set_state(self, state: str, error: str = "") -> None:
        with self._lock:
            self._state = state
            self._error = error
        self._emit({"type": "voice-status", **self.status()})

    def _load_model(self):
        if self._model is not None:
            return self._model
        from faster_whisper import WhisperModel

        try:
            self._model = WhisperModel(
                self._model_name,
                device="cpu",
                compute_type="int8",
                cpu_threads=max(2, min(4, os.cpu_count() or 2)),
                download_root=str(self._model_root),
                local_files_only=True,
            )
        except Exception as error:
            raise RuntimeError(
                "本地语音模型未安装或无法读取，请运行 python scripts/setup-voice-model.py。"
            ) from error
        return self._model

    def _run(self) -> None:
        try:
            audio = self._record_utterance()
            if self._discard:
                self._set_state("idle")
                return
            if audio is None or len(audio) < 1600:
                self._set_state("error", "没有检测到可转写的语音。")
                return

            self._set_state("transcribing")
            try:
                transcript = self._transcribe_audio(audio)
            except ValueError as error:
                self._set_state("error", str(error))
                return
            self._emit({"type": "voice-transcript", **transcript})
            self._set_state("idle")
        except Exception as error:
            self._set_state("error", f"本地语音转写失败：{error}")
        finally:
            with self._lock:
                self._thread = None
                self._stop_event.clear()
                self._discard = False

    def transcribe_pcm16(self, audio_bytes: bytes, sample_rate: int) -> dict:
        if sample_rate < 8_000 or sample_rate > 48_000:
            raise ValueError("语音采样率无效。")
        if not audio_bytes or len(audio_bytes) % 2:
            raise ValueError("没有收到可转写的语音。")
        if len(audio_bytes) > sample_rate * 2 * 12:
            raise ValueError("语音指令超过十二秒，请说得更简短一些。")
        audio = np.frombuffer(audio_bytes, dtype="<i2").astype(np.float32) / 32768.0
        if sample_rate != 16_000:
            output_length = max(1, round(len(audio) * 16_000 / sample_rate))
            source_positions = np.arange(len(audio), dtype=np.float64)
            target_positions = np.arange(output_length, dtype=np.float64) * sample_rate / 16_000
            audio = np.interp(target_positions, source_positions, audio).astype(np.float32)
        return self._transcribe_audio(audio)

    def _transcribe_audio(self, audio: np.ndarray) -> dict:
        if len(audio) < 1600:
            raise ValueError("没有检测到可转写的语音。")
        with self._transcription_lock:
            model = self._load_model()
            segments, info = model.transcribe(
                audio,
                language=None,
                multilingual=True,
                language_detection_threshold=0.5,
                language_detection_segments=2,
                beam_size=5,
                best_of=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
                condition_on_previous_text=False,
                temperature=0,
                no_speech_threshold=0.6,
                log_prob_threshold=-1.0,
            )
            accepted_segments = [
                segment
                for segment in segments
                if segment.no_speech_prob < 0.7 and segment.avg_logprob >= -1.5
            ]
        text = self._simplifier.convert("".join(segment.text for segment in accepted_segments))
        text = text.replace("怎幺", "怎么").strip()
        if not text:
            raise ValueError("听到了声音，但没有识别出清晰文字。")
        confidence_values = [
            float(np.exp(min(0.0, float(segment.avg_logprob))))
            for segment in accepted_segments
        ]
        confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
        return {
            "text": text,
            "language": info.language,
            "language_probability": round(float(info.language_probability), 4),
            "confidence": round(confidence, 4),
        }

    def _record_utterance(self) -> np.ndarray | None:
        import sounddevice as sd

        whisper_sample_rate = 16_000
        audio_queue: queue.Queue[np.ndarray] = queue.Queue()

        def callback(indata, _frames, _time_info, status) -> None:
            if status:
                self._emit({"type": "voice-warning", "message": str(status)})
            audio_queue.put(np.mean(indata, axis=1, dtype=np.float32))

        calibration: list[float] = []
        pre_roll: deque[np.ndarray] = deque(maxlen=10)
        recorded: list[np.ndarray] = []
        speech_started = False
        silence_blocks = 0
        loud_blocks = 0
        listening_emitted = False
        started_at = time.monotonic()

        stream = None
        sample_rate = 0
        failures: list[str] = []
        for device_index in self._input_device_candidates(sd):
            device = sd.query_devices(device_index)
            sample_rate = int(round(float(device.get("default_samplerate") or 44_100)))
            channels = min(2, int(device.get("max_input_channels") or 1))
            try:
                stream = sd.InputStream(
                    device=device_index,
                    samplerate=sample_rate,
                    channels=channels,
                    dtype="float32",
                    blocksize=max(1, sample_rate // 10),
                    callback=callback,
                )
                stream.start()
                break
            except Exception as error:
                failures.append(f"{device.get('name', device_index)}: {error}")
                if stream is not None:
                    stream.close()
                stream = None

        if stream is None:
            details = "; ".join(failures[-3:])
            raise RuntimeError(f"无法打开麦克风。{details}")

        try:
            while time.monotonic() - started_at < 60:
                if self._stop_event.is_set():
                    break
                try:
                    chunk = audio_queue.get(timeout=0.25)
                except queue.Empty:
                    continue

                rms = float(np.sqrt(np.mean(np.square(chunk), dtype=np.float64)))
                elapsed = time.monotonic() - started_at
                if elapsed < 0.8:
                    calibration.append(rms)
                    pre_roll.append(chunk)
                    continue

                if not listening_emitted:
                    self._set_state("listening")
                    listening_emitted = True

                noise_floor = float(np.percentile(calibration, 25)) if calibration else 0.001
                speech_threshold = min(max(noise_floor * 2.0, noise_floor + 0.008, 0.008), 0.035)

                if not speech_started:
                    pre_roll.append(chunk)
                    if rms >= speech_threshold:
                        loud_blocks += 1
                    else:
                        loud_blocks = 0
                    if loud_blocks >= 3:
                        speech_started = True
                        recorded.extend(pre_roll)
                        silence_blocks = 0
                    continue

                recorded.append(chunk)
                if rms < max(noise_floor * 1.5, speech_threshold * 0.75):
                    silence_blocks += 1
                else:
                    silence_blocks = 0
                # Pauses are part of natural reflection. Recording ends only when
                # the user stops it or the one-minute safety limit is reached.
        finally:
            stream.stop()
            stream.close()

        if not recorded:
            return None
        audio = np.concatenate(recorded).astype(np.float32, copy=False)
        if sample_rate == whisper_sample_rate:
            return audio

        output_length = max(1, round(len(audio) * whisper_sample_rate / sample_rate))
        source_positions = np.arange(len(audio), dtype=np.float64)
        target_positions = np.arange(output_length, dtype=np.float64) * sample_rate / whisper_sample_rate
        return np.interp(target_positions, source_positions, audio).astype(np.float32)

    @staticmethod
    def _input_device_candidates(sd) -> list[int]:
        devices = list(sd.query_devices())
        host_apis = list(sd.query_hostapis())
        try:
            default_index = int(sd.default.device[0])
        except (TypeError, ValueError, IndexError):
            default_index = -1

        default_name = ""
        if 0 <= default_index < len(devices):
            default_name = str(devices[default_index].get("name", "")).split("(", 1)[0].strip().lower()

        def score(item: tuple[int, dict]) -> tuple[int, int, int]:
            index, device = item
            name = str(device.get("name", "")).lower()
            host_name = str(host_apis[int(device.get("hostapi", 0))].get("name", "")).lower()
            same_microphone = bool(default_name and default_name in name)
            looks_like_microphone = any(word in name for word in ("麦克风", "microphone", "mic array", " mic"))
            host_rank = 0 if "wdm-ks" in host_name else 1 if "wasapi" in host_name else 2
            return (0 if same_microphone else 1 if looks_like_microphone else 2, host_rank, index)

        usable = [
            (index, device)
            for index, device in enumerate(devices)
            if int(device.get("max_input_channels", 0)) > 0
        ]
        ordered = [index for index, _device in sorted(usable, key=score)]
        if default_index in ordered:
            ordered.remove(default_index)
            ordered.insert(0, default_index)
        return ordered
