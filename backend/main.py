import argparse
import base64
import json
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from config import DeepSeekSettings, WebSearchSettings
from database import ReflectionDatabase
from deepseek_client import DeepSeekClient
from service import ReflectionService
from voice_transcriber import VoiceTranscriber
from web_search import WebSearchClient


def format_voice_event(payload: dict) -> str:
    return f"LIORA_VOICE_EVENT {json.dumps(payload, ensure_ascii=True)}"


class ReflectionHandler(BaseHTTPRequestHandler):
    server_version = "LioraReflection/0.1"

    def do_GET(self) -> None:
        route = urlparse(self.path)
        if not self._authorized():
            return self._json(401, {"error": "unauthorized"})
        try:
            if route.path == "/health":
                return self._json(200, {"ok": True, **self.server.service.status()})
            if route.path == "/api/reflections":
                query = parse_qs(route.query)
                limit = int(query.get("limit", ["20"])[0])
                return self._json(200, self.server.service.history(limit))
            if route.path == "/api/knowledge":
                query = parse_qs(route.query)
                limit = int(query.get("limit", ["20"])[0])
                offset = int(query.get("offset", ["0"])[0])
                return self._json(
                    200,
                    self.server.service.knowledge_list(
                        limit=limit,
                        offset=offset,
                        query=query.get("q", [""])[0],
                        folder=query.get("folder", [""])[0],
                        tag=query.get("tag", [""])[0],
                        sort=query.get("sort", ["relevance"])[0],
                    ),
                )
            if route.path.startswith("/api/knowledge/"):
                knowledge_id = route.path.removeprefix("/api/knowledge/")
                return self._json(200, self.server.service.knowledge_get(knowledge_id))
            if route.path == "/api/storage":
                return self._json(200, self.server.service.storage_status())
            if route.path == "/api/voice/status":
                return self._json(200, self.server.voice_transcriber.status())
            return self._json(404, {"error": "not_found"})
        except (ValueError, LookupError) as error:
            return self._json(400, {"error": str(error)})

    def do_POST(self) -> None:
        if not self._authorized():
            return self._json(401, {"error": "unauthorized"})

        try:
            route = urlparse(self.path).path
            maximum = 1_048_576 if route == "/api/voice/command-transcript" else 16_384
            if route.endswith(("/draft", "/revise")):
                maximum = 131_072
            body = self._read_json(maximum)
            if route == "/api/reflections/start":
                return self._json(
                    200,
                    self.server.service.start(
                        bool(body.get("force_new")),
                        str(body.get("knowledge_id") or "") or None,
                    ),
                )
            if route == "/api/voice/start":
                return self._json(200, self.server.voice_transcriber.start())
            if route == "/api/voice/stop":
                return self._json(200, self.server.voice_transcriber.stop(discard=False))
            if route == "/api/voice/cancel":
                return self._json(200, self.server.voice_transcriber.stop(discard=True))
            if route == "/api/voice/command-transcript":
                if body.get("encoding") != "pcm_s16le":
                    raise ValueError("不支持的语音编码。")
                try:
                    audio = base64.b64decode(str(body.get("audio") or ""), validate=True)
                except (ValueError, TypeError) as error:
                    raise ValueError("语音数据无法读取。") from error
                return self._json(
                    200,
                    self.server.voice_transcriber.transcribe_pcm16(
                        audio,
                        int(body.get("sample_rate") or 0),
                    ),
                )
            if route == "/api/storage/configure":
                vault_path = str(body.get("vault_path") or "").strip()
                if not vault_path:
                    raise ValueError("请选择 Obsidian Vault。")
                return self._json(200, self.server.service.configure_vault(vault_path))
            if route == "/api/storage/scan":
                return self._json(200, self.server.service.scan_vault())
            if route == "/api/storage/rebuild":
                return self._json(200, self.server.service.rebuild_vault_index())
            if route == "/api/storage/migrate":
                return self._json(200, self.server.service.migrate_legacy_knowledge())

            parts = [part for part in route.split("/") if part]
            if len(parts) == 4 and parts[:2] == ["api", "reflections"]:
                session_id, action = parts[2], parts[3]
                if action == "messages":
                    return self._json(200, self.server.service.reply(session_id, str(body.get("content", ""))))
                if action == "finish":
                    return self._json(200, self.server.service.finish(session_id))
                if action == "draft":
                    return self._json(
                        200,
                        self.server.service.update_draft(session_id, body.get("content") or {}),
                    )
                if action == "revise":
                    return self._json(
                        200,
                        self.server.service.revise_draft(
                            session_id,
                            str(body.get("instruction") or ""),
                            body.get("content") if isinstance(body.get("content"), dict) else None,
                        ),
                    )
                if action == "confirm":
                    return self._json(200, self.server.service.confirm(session_id))
                if action == "discard":
                    return self._json(200, self.server.service.discard(session_id))

            return self._json(404, {"error": "not_found"})
        except (ValueError, LookupError) as error:
            return self._json(400, {"error": str(error)})
        except Exception as error:
            print(f"LIORA_BACKEND_ERROR {error}", flush=True)
            return self._json(500, {"error": "后端暂时遇到问题，请稍后重试。"})

    def _authorized(self) -> bool:
        return self.headers.get("X-Liora-Token") == self.server.api_token

    def _read_json(self, maximum_length: int = 16_384) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > maximum_length:
            raise ValueError("请求内容过长。")
        raw = self.rfile.read(length) if length else b"{}"
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("请求格式不正确。")
        return value

    def _json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Liora reflection backend")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--port", type=int, default=43117)
    parser.add_argument("--token", required=True)
    parser.add_argument("--vault-path")
    parser.add_argument("--models-dir")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    database = ReflectionDatabase(Path(args.data_dir) / "liora.sqlite3")
    settings = DeepSeekSettings.from_project(project_root)
    search_settings = WebSearchSettings.from_project(project_root)
    service = ReflectionService(
        database,
        DeepSeekClient(settings),
        search_client=WebSearchClient(search_settings),
        vault_path=Path(args.vault_path) if args.vault_path else None,
        data_dir=Path(args.data_dir),
    )
    def emit_voice_event(payload: dict) -> None:
        # Keep the process pipe ASCII-only. Electron decodes the JSON escapes,
        # avoiding Windows code-page differences that corrupt Chinese text.
        print(format_voice_event(payload), flush=True)

    models_dir = Path(args.models_dir) if args.models_dir else project_root / ".models"
    voice_transcriber = VoiceTranscriber(models_dir / "faster-whisper", emit_voice_event)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), ReflectionHandler)
    server.service = service
    server.voice_transcriber = voice_transcriber
    server.api_token = args.token

    def stop_server(*_) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop_server)
    signal.signal(signal.SIGINT, stop_server)
    print(
        f"LIORA_BACKEND_READY {args.port} provider={service.status()['provider']} model={service.status()['model']}",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        voice_transcriber.stop(discard=True)
        database.close()
        server.server_close()


if __name__ == "__main__":
    main()
