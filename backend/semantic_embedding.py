import math
import os
import threading
import gc
from pathlib import Path

from knowledge_intelligence import embed_text


DEFAULT_MODEL_ID = "onnx-community/bge-small-zh-v1.5-ONNX"
DEFAULT_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


class SemanticEmbeddingEngine:
    """Lazy ONNX sentence embeddings with a deterministic local fallback.

    The model is never downloaded implicitly. This keeps startup predictable and
    makes API/network use an explicit setup action. If the model or runtime is
    unavailable, every caller continues to work with the original hashed n-gram
    vectors and can expose the degraded status to the UI.
    """

    def __init__(self, models_dir: Path | None = None):
        root = Path(models_dir or Path.cwd() / ".models")
        override = str(os.getenv("LIORA_EMBEDDING_MODEL_DIR", "")).strip()
        self.model_dir = (
            Path(override).expanduser()
            if override
            else root / "embeddings" / "bge-small-zh-v1.5"
        )
        self.model_id = str(
            os.getenv("LIORA_EMBEDDING_MODEL_ID", DEFAULT_MODEL_ID)
        ).strip() or DEFAULT_MODEL_ID
        self.query_instruction = str(
            os.getenv("LIORA_EMBEDDING_QUERY_INSTRUCTION", DEFAULT_QUERY_INSTRUCTION)
        )
        self.max_length = self._bounded_int("LIORA_EMBEDDING_MAX_LENGTH", 512, 64, 512)
        self.batch_size = self._bounded_int("LIORA_EMBEDDING_BATCH_SIZE", 8, 1, 32)
        self.idle_seconds = self._bounded_int("LIORA_EMBEDDING_IDLE_SECONDS", 300, 30, 3600)
        self._lock = threading.RLock()
        self._session = None
        self._tokenizer = None
        self._attempted = False
        self._error: str | None = None
        self._idle_timer: threading.Timer | None = None
        self._idle_generation = 0

    @staticmethod
    def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(os.getenv(name, str(default)))
        except ValueError:
            value = default
        return min(max(value, minimum), maximum)

    @property
    def onnx_path(self) -> Path:
        preferred = self.model_dir / "onnx" / "model_quantized.onnx"
        if preferred.exists():
            return preferred
        return self.model_dir / "model_quantized.onnx"

    @property
    def tokenizer_path(self) -> Path:
        return self.model_dir / "tokenizer.json"

    @property
    def available(self) -> bool:
        return self.onnx_path.is_file() and self.tokenizer_path.is_file()

    @property
    def using_semantic_model(self) -> bool:
        return self._session is not None

    @property
    def model_name(self) -> str:
        return (
            "bge-small-zh-v1.5-onnx-int8"
            if self.available and self._error is None
            else "liora-local-ngram-v1"
        )

    def status(self) -> dict:
        return {
            "provider": "onnx-local" if self.using_semantic_model else "local-fallback",
            "model": self.model_name,
            "model_id": self.model_id,
            "model_dir": str(self.model_dir),
            "available": self.available,
            "loaded": self.using_semantic_model,
            "dimensions": 512 if self.model_name.startswith("bge-") else 384,
            "idle_release_seconds": self.idle_seconds,
            "error": self._error,
        }

    def embed_document(self, text: str) -> list[float]:
        return self._embed(str(text or ""), is_query=False)

    def embed_query(self, text: str) -> list[float]:
        return self._embed(str(text or ""), is_query=True)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed_many([str(text or "") for text in texts], is_query=False)

    def prepare(self) -> bool:
        """Load the local model without embedding text.

        Services call this before consulting the cache so a restarted process
        never combines cached 512-dimensional BGE vectors with 384-dimensional
        fallback query vectors.
        """
        loaded = self._ensure_loaded()
        if loaded:
            self._schedule_idle_release()
        return loaded

    def _embed(self, text: str, is_query: bool) -> list[float]:
        return self._embed_many([text], is_query=is_query)[0]

    def _embed_many(self, texts: list[str], is_query: bool) -> list[list[float]]:
        if not texts:
            return []
        if not self._ensure_loaded():
            return [embed_text(text) for text in texts]
        prepared = [
            f"{self.query_instruction}{text}" if is_query and text.strip() else text
            for text in texts
        ]
        vectors: list[list[float]] = []
        try:
            with self._lock:
                for start in range(0, len(prepared), self.batch_size):
                    vectors.extend(self._run_batch(prepared[start : start + self.batch_size]))
            self._schedule_idle_release()
            return vectors
        except Exception as error:
            # A broken or incompatible local model must never take down the
            # knowledge engine. Keep the reason visible and degrade atomically.
            with self._lock:
                self._error = f"{type(error).__name__}: {str(error)[:240]}"
                self._session = None
                self._tokenizer = None
                self._cancel_idle_release_locked()
            return [embed_text(text) for text in texts]

    def release(self) -> None:
        """Release ONNX/tokenizer memory while keeping cached vectors usable."""
        with self._lock:
            self._cancel_idle_release_locked()
            self._session = None
            self._tokenizer = None
            # A deliberate idle release may load again on the next query.
            self._attempted = False
        gc.collect()

    def _cancel_idle_release_locked(self) -> None:
        if self._idle_timer is not None:
            self._idle_timer.cancel()
            self._idle_timer = None

    def _schedule_idle_release(self) -> None:
        with self._lock:
            if self._session is None:
                return
            self._cancel_idle_release_locked()
            self._idle_generation += 1
            generation = self._idle_generation
            timer = threading.Timer(
                self.idle_seconds, self._release_if_idle, args=(generation,)
            )
            timer.daemon = True
            self._idle_timer = timer
            timer.start()

    def _release_if_idle(self, generation: int) -> None:
        with self._lock:
            if generation != self._idle_generation:
                return
            self._cancel_idle_release_locked()
            self._session = None
            self._tokenizer = None
            self._attempted = False
        gc.collect()

    def _ensure_loaded(self) -> bool:
        with self._lock:
            if self._session is not None and self._tokenizer is not None:
                return True
            if self._attempted or not self.available:
                return False
            self._attempted = True
            try:
                import onnxruntime as ort
                from tokenizers import Tokenizer

                tokenizer = Tokenizer.from_file(str(self.tokenizer_path))
                tokenizer.enable_truncation(max_length=self.max_length)
                tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
                options = ort.SessionOptions()
                options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                session = ort.InferenceSession(
                    str(self.onnx_path),
                    sess_options=options,
                    providers=["CPUExecutionProvider"],
                )
                self._tokenizer = tokenizer
                self._session = session
                return True
            except Exception as error:
                self._error = f"{type(error).__name__}: {str(error)[:240]}"
                return False

    def _run_batch(self, texts: list[str]) -> list[list[float]]:
        import numpy as np

        encodings = self._tokenizer.encode_batch(texts)
        input_ids = np.asarray([item.ids for item in encodings], dtype=np.int64)
        attention_mask = np.asarray(
            [item.attention_mask for item in encodings], dtype=np.int64
        )
        type_ids = np.asarray([item.type_ids for item in encodings], dtype=np.int64)
        available_inputs = {item.name for item in self._session.get_inputs()}
        feed = {}
        if "input_ids" in available_inputs:
            feed["input_ids"] = input_ids
        if "attention_mask" in available_inputs:
            feed["attention_mask"] = attention_mask
        if "token_type_ids" in available_inputs:
            feed["token_type_ids"] = type_ids
        outputs = self._session.run(None, feed)
        hidden = np.asarray(outputs[0], dtype=np.float32)
        pooled = hidden[:, 0, :] if hidden.ndim == 3 else hidden
        normalized = []
        for row in pooled:
            norm = math.sqrt(float(np.dot(row, row)))
            normalized.append(
                [round(float(value) / norm, 7) for value in row]
                if norm
                else [0.0 for _ in row]
            )
        return normalized
