import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from semantic_embedding import SemanticEmbeddingEngine


class SemanticEmbeddingEngineTests(unittest.TestCase):
    def test_missing_model_falls_back_without_network_or_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"LIORA_EMBEDDING_MODEL_DIR": directory}, clear=False
        ):
            engine = SemanticEmbeddingEngine(Path(directory))
            vector = engine.embed_document("广度优先搜索按层遍历")
            self.assertEqual(len(vector), 384)
            self.assertFalse(engine.using_semantic_model)
            self.assertEqual(engine.status()["model"], "liora-local-ngram-v1")

    def test_model_is_never_downloaded_implicitly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            engine = SemanticEmbeddingEngine(Path(directory))
            engine.embed_query("测试查询")
            self.assertFalse((Path(directory) / "embeddings").exists())

    def test_release_drops_runtime_objects_and_allows_lazy_reload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            engine = SemanticEmbeddingEngine(Path(directory))
            engine._session = object()
            engine._tokenizer = object()
            engine._attempted = True

            engine.release()

            self.assertFalse(engine.using_semantic_model)
            self.assertIsNone(engine._tokenizer)
            self.assertFalse(engine._attempted)
            self.assertEqual(engine.status()["idle_release_seconds"], 300)
