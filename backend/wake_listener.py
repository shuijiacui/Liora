import argparse
import audioop
import base64
import json
import queue
import signal
import threading
import time
import uuid
from collections import deque
from pathlib import Path


ENGLISH_PHRASES = (
    "hi liora",
    "hey liora",
    "hi leora",
    "hey leora",
    "hi laura",
    "hey laura",
    "hi lora",
    "hey lora",
    "hi lee aura",
    "hey lee aura",
    "hi lia ora",
    "hey lia ora",
)
ENGLISH_GRAMMAR = (
    "hi laura",
    "hey laura",
    "hi lora",
    "hey lora",
    "hi lee aura",
    "hey lee aura",
    "hi lia ora",
    "hey lia ora",
)
CHINESE_PHRASES = (
    "嗨莉奥拉",
    "嗨丽奥拉",
    "嗨里奥拉",
    "海莉奥拉",
    "海丽奥拉",
    "海里奥拉",
)
CHINESE_GRAMMAR = (
    "嗨 丽 奥 拉",
    "嗨 里 奥 拉",
    "海 丽 奥 拉",
    "海 里 奥 拉",
)

COMMAND_WINDOW_SECONDS = 7.0
MAX_UTTERANCE_BLOCKS = 28
SPEECH_START_RMS = 350
SPEECH_END_RMS = 250


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")), flush=True)


def normalize(text: str) -> str:
    return "".join(character.lower() for character in str(text) if character.isalnum())


def is_wake_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    value = normalize(text)
    return any(normalize(phrase) in value for phrase in phrases)


def result_confidence(payload: dict) -> float:
    words = payload.get("result") or []
    values = [float(item.get("conf", 0)) for item in words if item.get("conf") is not None]
    return round(sum(values) / len(values), 4) if values else 0.75


def create_recognizer(model_path: Path, sample_rate: int, grammar_phrases: tuple[str, ...]):
    from vosk import KaldiRecognizer, Model

    model = Model(str(model_path))
    grammar = json.dumps([*grammar_phrases, "[unk]"], ensure_ascii=False)
    recognizer = KaldiRecognizer(model, sample_rate, grammar)
    recognizer.SetWords(True)
    return model, recognizer


def input_device_candidates(sounddevice) -> list[int | None]:
    devices = list(sounddevice.query_devices())
    try:
        default_index = int(sounddevice.default.device[0])
    except (TypeError, ValueError, IndexError):
        default_index = -1
    candidates = [default_index] if 0 <= default_index < len(devices) else []
    candidates.extend(
        index
        for index, device in enumerate(devices)
        if int(device.get("max_input_channels", 0)) > 0 and index != default_index
    )
    return candidates or [None]


def encoded_audio_event(
    audio_chunks: list[bytes],
    sample_rate: int,
    session_id: str,
    phase: str,
) -> dict:
    audio = b"".join(audio_chunks)
    return {
        "type": "command-audio",
        "session_id": session_id,
        "phase": phase,
        "sample_rate": sample_rate,
        "encoding": "pcm_s16le",
        "audio": base64.b64encode(audio).decode("ascii"),
        "duration_ms": round(len(audio) / (sample_rate * 2) * 1000),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Liora offline bilingual wake-word listener")
    parser.add_argument("--models-dir", required=True)
    parser.add_argument("--mode", default="wake")
    args = parser.parse_args()

    models_dir = Path(args.models_dir)
    english_path = models_dir / "en-us"
    chinese_path = models_dir / "cn"
    missing = [str(path) for path in (english_path, chinese_path) if not path.exists()]
    if missing:
        emit({
            "type": "error",
            "message": "缺少 Vosk 中英文唤醒模型，请运行 python scripts/setup-wake-models.py。",
            "missing": missing,
        })
        raise SystemExit(2)

    try:
        import sounddevice as sd
        from vosk import SetLogLevel

        SetLogLevel(-1)
        sample_rate = 16_000
        english_model, english = create_recognizer(english_path, sample_rate, ENGLISH_GRAMMAR)
        chinese_model, chinese = create_recognizer(chinese_path, sample_rate, CHINESE_GRAMMAR)
        _models = (english_model, chinese_model)
        recognizers = (
            ("en-US", "Vosk small English", ENGLISH_PHRASES, english),
            ("zh-CN", "Vosk small Chinese", CHINESE_PHRASES, chinese),
        )

        audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=24)
        stop_event = threading.Event()

        def stop_listener(*_args) -> None:
            stop_event.set()

        signal.signal(signal.SIGINT, stop_listener)
        signal.signal(signal.SIGTERM, stop_listener)

        def callback(indata, _frames, _time_info, status) -> None:
            if status:
                emit({"type": "warning", "message": str(status)})
            try:
                audio_queue.put_nowait(bytes(indata))
            except queue.Full:
                try:
                    audio_queue.get_nowait()
                    audio_queue.put_nowait(bytes(indata))
                except queue.Empty:
                    pass

        stream = None
        failures = []
        for device_index in input_device_candidates(sd):
            try:
                stream = sd.RawInputStream(
                    device=device_index,
                    samplerate=sample_rate,
                    blocksize=4_000,
                    channels=1,
                    dtype="int16",
                    callback=callback,
                )
                stream.start()
                break
            except Exception as error:
                failures.append(str(error))
                if stream is not None:
                    stream.close()
                stream = None
        if stream is None:
            raise RuntimeError("无法打开麦克风：" + "; ".join(failures[-3:]))

        emit({
            "type": "ready",
            "mode": args.mode,
            "recognizers": [
                {"culture": culture, "description": description}
                for culture, description, _phrases, _recognizer in recognizers
            ],
        })

        audio_history: deque[bytes] = deque(maxlen=MAX_UTTERANCE_BLOCKS)
        command_pre_roll: deque[bytes] = deque(maxlen=2)
        command_chunks: list[bytes] = []
        command_speech_started = False
        command_loud_blocks = 0
        command_silence_blocks = 0
        active_session_id = ""
        active_wake_culture = ""
        wake_utterance_sent = False
        awaiting_command_until = 0.0
        last_wake_at = 0.0

        def reset_command_capture() -> None:
            nonlocal command_speech_started, command_loud_blocks, command_silence_blocks
            command_pre_roll.clear()
            command_chunks.clear()
            command_speech_started = False
            command_loud_blocks = 0
            command_silence_blocks = 0

        try:
            while not stop_event.is_set():
                try:
                    audio = audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                now = time.monotonic()
                if active_session_id and wake_utterance_sent:
                    rms = audioop.rms(audio, 2)
                    command_pre_roll.append(audio)
                    if not command_speech_started:
                        command_loud_blocks = command_loud_blocks + 1 if rms >= SPEECH_START_RMS else 0
                        if command_loud_blocks >= 2:
                            command_speech_started = True
                            command_chunks.extend(command_pre_roll)
                    else:
                        command_chunks.append(audio)
                        command_silence_blocks = command_silence_blocks + 1 if rms < SPEECH_END_RMS else 0

                    command_finished = command_speech_started and command_silence_blocks >= 3
                    command_expired = now >= awaiting_command_until
                    if command_finished or command_expired:
                        if command_speech_started and len(command_chunks) >= 2:
                            emit(encoded_audio_event(
                                command_chunks,
                                sample_rate,
                                active_session_id,
                                "follow-up",
                            ))
                        elif command_expired:
                            emit({"type": "command-timeout", "session_id": active_session_id})
                        active_session_id = ""
                        active_wake_culture = ""
                        wake_utterance_sent = False
                        awaiting_command_until = 0.0
                        reset_command_capture()

                audio_history.append(audio)
                completed_results = []
                wake_results = []
                for culture, description, phrases, recognizer in recognizers:
                    completed = recognizer.AcceptWaveform(audio)
                    payload = json.loads(recognizer.Result() if completed else recognizer.PartialResult())
                    text = str(payload.get("text" if completed else "partial", "")).strip()
                    result = (culture, description, phrases, payload, text, completed)
                    if completed:
                        completed_results.append(result)
                    if text and is_wake_phrase(text, phrases):
                        wake_results.append(result)

                if not active_session_id and wake_results and now - last_wake_at >= 2.5:
                    culture, description, _phrases, payload, text, _completed = max(
                        wake_results,
                        key=lambda item: result_confidence(item[3]),
                    )
                    last_wake_at = now
                    active_session_id = str(uuid.uuid4())
                    active_wake_culture = culture
                    wake_utterance_sent = False
                    awaiting_command_until = now + COMMAND_WINDOW_SECONDS
                    reset_command_capture()
                    emit({
                        "type": "recognized",
                        "text": text,
                        "confidence": result_confidence(payload),
                        "grammar": f"liora-wake:{culture}",
                        "culture": culture,
                        "recognizer": description,
                        "session_id": active_session_id,
                    })

                wake_utterance_completed = any(
                    result[0] == active_wake_culture
                    for result in completed_results
                )
                if active_session_id and not wake_utterance_sent and wake_utterance_completed:
                    emit(encoded_audio_event(
                        list(audio_history),
                        sample_rate,
                        active_session_id,
                        "wake-utterance",
                    ))
                    wake_utterance_sent = True
                    awaiting_command_until = now + COMMAND_WINDOW_SECONDS
                    reset_command_capture()
                    audio_history.clear()
                elif completed_results and not active_session_id:
                    audio_history.clear()
        finally:
            stream.stop()
            stream.close()
    except Exception as error:
        emit({"type": "error", "message": f"本地双语唤醒启动失败：{error}"})
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
