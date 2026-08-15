import gc
import os
import queue
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

import numpy as np
from opencc import OpenCC


class VoiceTranscriber:
    def __init__(self, model_root: Path, emit: Callable[[dict], None]):
        self._model_root = model_root
        self._simplifier = OpenCC("tw2sp")
        self._emit = emit
        self._model = None
        self._unload_timer: threading.Timer | None = None
        self._idle_unload_seconds = self._bounded_int_env("LIORA_VOICE_IDLE_SECONDS", 180, 30, 3600)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._discard = False
        self._lock = threading.RLock()
        self._transcription_lock = threading.Lock()
        self._state = "idle"
        self._error = ""

    def status(self) -> dict:
        with self._lock:
            return {"state": self._state, "error": self._error, "model": "sensevoice-small-int8"}

    def start(self) -> dict:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self.status()
            self._stop_event.clear()
            self._discard = False
            self._error = ""
            self._set_state("loading" if self._model is None else "preparing")
            self._thread = threading.Thread(target=self._run, name="liora-sensevoice", daemon=True)
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
        from sensevoice_runtime import SenseVoiceRuntime

        try:
            self._model = SenseVoiceRuntime(self._model_root)
        except Exception as error:
            raise RuntimeError(
                "本地语音模型未安装或无法读取，请运行 python scripts/setup-voice-model.py。"
            ) from error
        return self._model

    def _schedule_model_unload(self) -> None:
        with self._lock:
            if self._unload_timer is not None:
                self._unload_timer.cancel()
            self._unload_timer = threading.Timer(self._idle_unload_seconds, self._unload_model)
            self._unload_timer.daemon = True
            self._unload_timer.start()

    def _unload_model(self) -> None:
        with self._transcription_lock:
            with self._lock:
                self._model = None
                self._unload_timer = None
        gc.collect()

    def close(self) -> None:
        with self._lock:
            if self._unload_timer is not None:
                self._unload_timer.cancel()
                self._unload_timer = None
        with self._transcription_lock:
            self._model = None
        gc.collect()

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
            audio = self._resample_audio(audio, sample_rate, 16_000)
        return self._transcribe_audio(audio)

    def _transcribe_audio(self, audio: np.ndarray) -> dict:
        if len(audio) < 1600:
            raise ValueError("没有检测到可转写的语音。")
        results: list[dict] = []
        try:
            with self._transcription_lock:
                model = self._load_model()
                for chunk in self._segment_audio(np.asarray(audio, dtype=np.float32)):
                    result = model.transcribe(chunk, language="auto", use_itn=True)
                    if str(result.get("text") or "").strip():
                        results.append(result)
        finally:
            self._schedule_model_unload()

        text = self._join_transcript_parts([str(result["text"]).strip() for result in results])
        text = self._simplifier.convert(text)
        text = text.replace("怎幺", "怎么").strip()
        if not text:
            raise ValueError("听到了声音，但没有识别出清晰文字。")

        weights = [max(1, int(result.get("token_count") or len(str(result["text"])))) for result in results]
        total_weight = max(1, sum(weights))
        confidence = sum(float(result.get("confidence") or 0.0) * weight for result, weight in zip(results, weights)) / total_weight
        language_weights: dict[str, int] = {}
        for result, weight in zip(results, weights):
            language = str(result.get("language") or "unknown")
            language_weights[language] = language_weights.get(language, 0) + weight
        language = max(language_weights, key=language_weights.get) if language_weights else "unknown"
        selected = [
            (result, weight)
            for result, weight in zip(results, weights)
            if str(result.get("language") or "unknown") == language
        ]
        language_probability = (
            sum(float(result.get("language_probability") or 0.0) * weight for result, weight in selected)
            / max(1, sum(weight for _result, weight in selected))
        )
        return {
            "text": text,
            "language": language,
            "language_probability": round(language_probability, 4),
            "confidence": round(confidence, 4),
        }

    @staticmethod
    def _join_transcript_parts(parts: list[str]) -> str:
        text = ""
        for part in parts:
            if not part:
                continue
            needs_space = bool(
                text
                and not text[-1].isspace()
                and not part[0].isspace()
                and text[-1].isascii()
                and part[0].isascii()
                and (text[-1].isalnum() or text[-1] in ".,!?;:")
                and part[0].isalnum()
            )
            text += (" " if needs_space else "") + part
        return text

    @staticmethod
    def _segment_audio(audio: np.ndarray) -> list[np.ndarray]:
        sample_rate = 16_000
        maximum = 28 * sample_rate
        if len(audio) <= maximum:
            return [audio]

        target = 22 * sample_rate
        minimum = 8 * sample_rate
        search_radius = 4 * sample_rate
        energy_window = 800
        energy_step = 320
        chunks: list[np.ndarray] = []
        cursor = 0
        while len(audio) - cursor > maximum:
            latest = min(cursor + maximum, len(audio) - minimum)
            desired = min(cursor + target, latest)
            search_start = max(cursor + minimum, desired - search_radius)
            search_end = min(latest, desired + search_radius)
            candidates = range(search_start, max(search_start + 1, search_end), energy_step)
            cut = min(
                candidates,
                key=lambda index: float(
                    np.mean(np.square(audio[index : index + energy_window]), dtype=np.float64)
                ),
            )
            cut = max(cursor + minimum, min(cut, latest))
            chunks.append(audio[cursor:cut])
            cursor = cut
        if len(audio) - cursor >= 1600:
            chunks.append(audio[cursor:])
        return chunks

    @staticmethod
    def _resample_audio(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
        if source_rate == target_rate:
            return np.asarray(audio, dtype=np.float32)
        output_length = max(1, round(len(audio) * target_rate / source_rate))
        output = np.empty(output_length, dtype=np.float32)
        scale = np.float32(source_rate / target_rate)
        block_size = 65_536
        for start in range(0, output_length, block_size):
            end = min(output_length, start + block_size)
            positions = np.arange(start, end, dtype=np.float32) * scale
            left = positions.astype(np.int64)
            np.minimum(left, len(audio) - 1, out=left)
            right = np.minimum(left + 1, len(audio) - 1)
            fraction = positions - left
            output[start:end] = audio[left] * (1.0 - fraction) + audio[right] * fraction
        return output

    def _record_utterance(self) -> np.ndarray | None:
        import sounddevice as sd

        model_sample_rate = 16_000
        audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=24)

        def callback(indata, _frames, _time_info, status) -> None:
            if status:
                self._emit({"type": "voice-warning", "message": str(status)})
            chunk = np.asarray(indata[:, 0], dtype=np.float32).copy()
            try:
                audio_queue.put_nowait(chunk)
            except queue.Full:
                try:
                    audio_queue.get_nowait()
                    audio_queue.put_nowait(chunk)
                except (queue.Empty, queue.Full):
                    pass

        calibration: list[float] = []
        pre_roll: deque[np.ndarray] = deque(maxlen=10)
        recorded: list[np.ndarray] = []
        speech_started = False
        loud_blocks = 0
        listening_emitted = False
        started_at = time.monotonic()

        stream = None
        sample_rate = 0
        failures: list[str] = []
        for device_index in self._input_device_candidates(sd):
            device = sd.query_devices(device_index)
            default_sample_rate = int(round(float(device.get("default_samplerate") or 44_100)))
            for candidate_rate in dict.fromkeys((model_sample_rate, default_sample_rate)):
                sample_rate = candidate_rate
                try:
                    stream = sd.InputStream(
                        device=device_index,
                        samplerate=sample_rate,
                        channels=1,
                        dtype="float32",
                        blocksize=max(1, sample_rate // 10),
                        callback=callback,
                    )
                    stream.start()
                    break
                except Exception as error:
                    failures.append(f"{device.get('name', device_index)}@{sample_rate}Hz: {error}")
                    if stream is not None:
                        stream.close()
                    stream = None
            if stream is not None:
                break

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
                    continue

                recorded.append(chunk)
                # Pauses are part of natural reflection. Recording ends only when
                # the user stops it or the one-minute safety limit is reached.
        finally:
            stream.stop()
            stream.close()

        if not recorded:
            return None
        audio = np.concatenate(recorded).astype(np.float32, copy=False)
        if sample_rate == model_sample_rate:
            return audio
        return self._resample_audio(audio, sample_rate, model_sample_rate)

    @staticmethod
    def _bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(os.getenv(name, str(default)))
        except ValueError:
            value = default
        return max(minimum, min(maximum, value))

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
