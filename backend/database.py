import sqlite3
import threading
import uuid
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ReflectionDatabase:
    def __init__(self, database_path: Path):
        self._database_path = Path(database_path)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA busy_timeout = 3000")
        self._create_schema()

    def _create_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS reflection_sessions (
                    id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL CHECK (status IN ('active', 'completed')),
                    summary TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS reflection_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('assistant', 'user')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES reflection_sessions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_reflection_messages_session
                ON reflection_messages(session_id, id);

                CREATE TABLE IF NOT EXISTS knowledge_items (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    current_revision_id INTEGER
                );

                CREATE TABLE IF NOT EXISTS knowledge_revisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    knowledge_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    content_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(knowledge_id, version),
                    FOREIGN KEY (knowledge_id) REFERENCES knowledge_items(id) ON DELETE CASCADE,
                    FOREIGN KEY (session_id) REFERENCES reflection_sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS knowledge_drafts (
                    session_id TEXT PRIMARY KEY,
                    knowledge_id TEXT,
                    content_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES reflection_sessions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_knowledge_revisions_item
                ON knowledge_revisions(knowledge_id, version DESC);

                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    id TEXT PRIMARY KEY,
                    relative_path TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    content_json TEXT NOT NULL,
                    file_mtime_ns INTEGER NOT NULL,
                    file_size INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    source TEXT NOT NULL,
                    indexed_at TEXT NOT NULL,
                    deleted_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_knowledge_documents_updated
                ON knowledge_documents(deleted_at, updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_knowledge_documents_hash
                ON knowledge_documents(content_hash);
                """
            )
            session_columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(reflection_sessions)").fetchall()
            }
            if "knowledge_id" not in session_columns:
                self._connection.execute(
                    "ALTER TABLE reflection_sessions ADD COLUMN knowledge_id TEXT"
                )
            document_columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(knowledge_documents)").fetchall()
            }
            document_migrations = {
                "folder": "ALTER TABLE knowledge_documents ADD COLUMN folder TEXT NOT NULL DEFAULT ''",
                "tags_json": "ALTER TABLE knowledge_documents ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]'",
                "search_text": "ALTER TABLE knowledge_documents ADD COLUMN search_text TEXT NOT NULL DEFAULT ''",
            }
            for column, statement in document_migrations.items():
                if column not in document_columns:
                    self._connection.execute(statement)
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_knowledge_documents_folder
                ON knowledge_documents(deleted_at, folder)
                """
            )
            self._connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_documents_fts USING fts5(
                    document_id UNINDEXED,
                    title,
                    body,
                    relative_path,
                    tags,
                    tokenize='trigram'
                )
                """
            )
            self._connection.execute(
                """
                DELETE FROM knowledge_documents_fts
                WHERE document_id NOT IN (
                    SELECT id FROM knowledge_documents WHERE deleted_at IS NULL
                )
                """
            )

    def create_session(self, knowledge_id: str | None = None) -> dict:
        session = {
            "id": str(uuid.uuid4()),
            "started_at": utc_now(),
            "completed_at": None,
            "status": "active",
            "summary": "",
            "knowledge_id": knowledge_id,
        }
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO reflection_sessions
                    (id, started_at, completed_at, status, summary, knowledge_id)
                VALUES
                    (:id, :started_at, :completed_at, :status, :summary, :knowledge_id)
                """,
                session,
            )
        return session

    def get_session(self, session_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM reflection_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_active_session(self) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM reflection_sessions
                WHERE status = 'active'
                ORDER BY started_at DESC
                LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else None

    def add_message(self, session_id: str, role: str, content: str) -> dict:
        created_at = utc_now()
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO reflection_messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, created_at),
            )
        return {
            "id": cursor.lastrowid,
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": created_at,
        }

    def get_messages(self, session_id: str) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, session_id, role, content, created_at
                FROM reflection_messages
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def complete_session(self, session_id: str, summary: str) -> dict:
        completed_at = utc_now()
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE reflection_sessions
                SET status = 'completed', completed_at = ?, summary = ?
                WHERE id = ?
                """,
                (completed_at, summary, session_id),
            )
        return self.get_session(session_id)

    def list_sessions(self, limit: int = 20) -> list[dict]:
        safe_limit = min(max(limit, 1), 100)
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT
                    s.*,
                    COUNT(m.id) AS message_count
                FROM reflection_sessions s
                LEFT JOIN reflection_messages m ON m.session_id = s.id
                GROUP BY s.id
                ORDER BY s.started_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_knowledge_draft(
        self, session_id: str, content: dict, knowledge_id: str | None = None
    ) -> dict:
        created_at = utc_now()
        encoded = json.dumps(content, ensure_ascii=False)
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO knowledge_drafts (session_id, knowledge_id, content_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    knowledge_id = excluded.knowledge_id,
                    content_json = excluded.content_json,
                    created_at = excluded.created_at
                """,
                (session_id, knowledge_id, encoded, created_at),
            )
        return {
            "session_id": session_id,
            "knowledge_id": knowledge_id,
            "content": content,
            "created_at": created_at,
        }

    def get_knowledge_draft(self, session_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM knowledge_drafts WHERE session_id = ?", (session_id,)
            ).fetchone()
        if not row:
            return None
        value = dict(row)
        value["content"] = json.loads(value.pop("content_json"))
        return value

    def discard_knowledge_draft(self, session_id: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM knowledge_drafts WHERE session_id = ?", (session_id,)
            )

    def discard_session(self, session_id: str) -> dict:
        with self._lock, self._connection:
            session = self._connection.execute(
                "SELECT * FROM reflection_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not session:
                raise LookupError("没有找到这次反思记录。")
            if session["status"] != "active":
                raise ValueError("已经完成的反思不能放弃。")
            self._connection.execute(
                "DELETE FROM reflection_sessions WHERE id = ?", (session_id,)
            )
        return dict(session)

    def confirm_knowledge_draft(
        self,
        session_id: str,
        knowledge_id_override: str | None = None,
        version_override: int | None = None,
    ) -> dict:
        with self._lock, self._connection:
            draft = self._connection.execute(
                "SELECT * FROM knowledge_drafts WHERE session_id = ?", (session_id,)
            ).fetchone()
            session = self._connection.execute(
                "SELECT * FROM reflection_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not draft or not session:
                raise LookupError("没有找到待确认的知识整理结果。")

            content = json.loads(draft["content_json"])
            knowledge_id = knowledge_id_override or draft["knowledge_id"] or session["knowledge_id"]
            now = utc_now()
            if knowledge_id:
                item = self._connection.execute(
                    "SELECT id FROM knowledge_items WHERE id = ?", (knowledge_id,)
                ).fetchone()
                if not item:
                    self._connection.execute(
                        """
                        INSERT INTO knowledge_items (id, title, created_at, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (knowledge_id, content["title"], now, now),
                    )
            else:
                knowledge_id = str(uuid.uuid4())
                self._connection.execute(
                    """
                    INSERT INTO knowledge_items (id, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (knowledge_id, content["title"], now, now),
                )

            version = version_override or self._connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM knowledge_revisions WHERE knowledge_id = ?",
                (knowledge_id,),
            ).fetchone()[0]
            cursor = self._connection.execute(
                """
                INSERT INTO knowledge_revisions
                    (knowledge_id, session_id, version, content_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (knowledge_id, session_id, version, draft["content_json"], now),
            )
            self._connection.execute(
                """
                UPDATE knowledge_items
                SET title = ?, updated_at = ?, current_revision_id = ?
                WHERE id = ?
                """,
                (content["title"], now, cursor.lastrowid, knowledge_id),
            )
            self._connection.execute(
                """
                UPDATE reflection_sessions
                SET status = 'completed', completed_at = ?, summary = ?, knowledge_id = ?
                WHERE id = ?
                """,
                (now, content["core_insight"], knowledge_id, session_id),
            )
            self._connection.execute(
                "DELETE FROM knowledge_drafts WHERE session_id = ?", (session_id,)
            )
            self._connection.execute(
                "DELETE FROM reflection_messages WHERE session_id = ?", (session_id,)
            )
        return self.get_knowledge(knowledge_id)

    def get_knowledge(self, knowledge_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT i.*, r.version, r.content_json, r.created_at AS revision_created_at
                FROM knowledge_items i
                JOIN knowledge_revisions r ON r.id = i.current_revision_id
                WHERE i.id = ?
                """,
                (knowledge_id,),
            ).fetchone()
        return self._knowledge_payload(row) if row else None

    def list_knowledge(self, limit: int = 20) -> list[dict]:
        safe_limit = min(max(limit, 1), 100)
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT i.*, r.version, r.content_json, r.created_at AS revision_created_at
                FROM knowledge_items i
                JOIN knowledge_revisions r ON r.id = i.current_revision_id
                ORDER BY i.updated_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [self._knowledge_payload(row) for row in rows]

    def list_all_knowledge(self) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT i.*, r.version, r.content_json, r.created_at AS revision_created_at
                FROM knowledge_items i
                JOIN knowledge_revisions r ON r.id = i.current_revision_id
                ORDER BY i.updated_at DESC
                """
            ).fetchall()
        return [self._knowledge_payload(row) for row in rows]

    def upsert_knowledge_document(self, item: dict) -> None:
        encoded = json.dumps(item["content"], ensure_ascii=False)
        tags = [str(value).strip() for value in item.get("tags", []) if str(value).strip()]
        tags_json = json.dumps(tags, ensure_ascii=False)
        tags_text = " ".join(tags)
        with self._lock, self._connection:
            old_path = self._connection.execute(
                "SELECT id FROM knowledge_documents WHERE relative_path = ? AND id != ?",
                (item["relative_path"], item["id"]),
            ).fetchone()
            if old_path:
                self._connection.execute(
                    "DELETE FROM knowledge_documents WHERE id = ?", (old_path["id"],)
                )
                self._connection.execute(
                    "DELETE FROM knowledge_documents_fts WHERE document_id = ?", (old_path["id"],)
                )
            self._connection.execute(
                """
                INSERT INTO knowledge_documents (
                    id, relative_path, title, created_at, updated_at, version,
                    content_json, file_mtime_ns, file_size, content_hash,
                    source, indexed_at, folder, tags_json, search_text, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(id) DO UPDATE SET
                    relative_path = excluded.relative_path,
                    title = excluded.title,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    version = excluded.version,
                    content_json = excluded.content_json,
                    file_mtime_ns = excluded.file_mtime_ns,
                    file_size = excluded.file_size,
                    content_hash = excluded.content_hash,
                    source = excluded.source,
                    indexed_at = excluded.indexed_at,
                    folder = excluded.folder,
                    tags_json = excluded.tags_json,
                    search_text = excluded.search_text,
                    deleted_at = NULL
                """,
                (
                    item["id"],
                    item["relative_path"],
                    item["title"],
                    item["created_at"],
                    item["updated_at"],
                    int(item.get("version") or 1),
                    encoded,
                    int(item["file_mtime_ns"]),
                    int(item["file_size"]),
                    item["content_hash"],
                    item["source"],
                    item["indexed_at"],
                    item.get("folder", ""),
                    tags_json,
                    item.get("search_text", item["title"]),
                ),
            )
            self._connection.execute(
                "DELETE FROM knowledge_documents_fts WHERE document_id = ?", (item["id"],)
            )
            self._connection.execute(
                """
                INSERT INTO knowledge_documents_fts
                    (document_id, title, body, relative_path, tags)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    item["id"],
                    item["title"],
                    item.get("search_text", item["title"]),
                    item["relative_path"],
                    tags_text,
                ),
            )

    def get_knowledge_document(self, knowledge_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM knowledge_documents WHERE id = ? AND deleted_at IS NULL",
                (knowledge_id,),
            ).fetchone()
        return self._document_payload(row) if row else None

    def list_knowledge_documents(self, limit: int = 20) -> list[dict]:
        safe_limit = min(max(limit, 1), 1000)
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM knowledge_documents
                WHERE deleted_at IS NULL
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [self._document_payload(row) for row in rows]

    @staticmethod
    def _fts_expression(query: str) -> str:
        terms = [term for term in re.split(r"\s+", query.strip()) if term]
        return " AND ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)

    @staticmethod
    def _like_pattern(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    def search_knowledge_documents(
        self,
        query: str = "",
        folder: str = "",
        tag: str = "",
        sort: str = "relevance",
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        query = str(query or "").strip()[:200]
        folder = str(folder or "").strip()
        tag = str(tag or "").strip().lstrip("#")
        sort = sort if sort in {"relevance", "updated", "title"} else "relevance"
        safe_limit = min(max(int(limit), 1), 50)
        safe_offset = max(int(offset), 0)
        query_terms = [term for term in re.split(r"\s+", query) if term]
        use_fts = bool(query_terms) and all(len(term) >= 3 for term in query_terms)

        where = ["d.deleted_at IS NULL"]
        params: list = []
        if folder:
            where.append("d.folder = ?")
            params.append("" if folder == "." else folder)
        if tag:
            where.append(
                "EXISTS (SELECT 1 FROM json_each(d.tags_json) WHERE json_each.value = ?)"
            )
            params.append(tag)

        if use_fts:
            where.insert(0, "knowledge_documents_fts MATCH ?")
            params.insert(0, self._fts_expression(query))
            source = """
                knowledge_documents_fts
                JOIN knowledge_documents d
                    ON d.id = knowledge_documents_fts.document_id
            """
            rank = "bm25(knowledge_documents_fts, 0.0, 8.0, 1.0, 2.5, 5.0)"
            snippet = "snippet(knowledge_documents_fts, 2, '', '', ' … ', 24)"
        else:
            source = "knowledge_documents d"
            rank = "0.0"
            snippet = "substr(d.search_text, 1, 180)"
            if query:
                for term in re.split(r"\s+", query):
                    if not term:
                        continue
                    pattern = self._like_pattern(term)
                    where.append(
                        "(d.title LIKE ? ESCAPE '\\' OR d.search_text LIKE ? ESCAPE '\\' "
                        "OR d.relative_path LIKE ? ESCAPE '\\' OR d.tags_json LIKE ? ESCAPE '\\')"
                    )
                    params.extend([pattern, pattern, pattern, pattern])

        where_sql = " AND ".join(where)
        if sort == "title":
            order_sql = "d.title COLLATE NOCASE ASC, d.updated_at DESC"
        elif sort == "updated" or not query:
            order_sql = "d.updated_at DESC, d.title COLLATE NOCASE ASC"
        else:
            order_sql = f"{rank} ASC, d.updated_at DESC"

        with self._lock:
            total = int(
                self._connection.execute(
                    f"SELECT COUNT(*) FROM {source} WHERE {where_sql}", params
                ).fetchone()[0]
            )
            rows = self._connection.execute(
                f"""
                SELECT d.*, {rank} AS search_rank, {snippet} AS snippet
                FROM {source}
                WHERE {where_sql}
                ORDER BY {order_sql}
                LIMIT ? OFFSET ?
                """,
                [*params, safe_limit, safe_offset],
            ).fetchall()
        return {
            "items": [self._document_payload(row) for row in rows],
            "total": total,
            "limit": safe_limit,
            "offset": safe_offset,
            "has_more": safe_offset + len(rows) < total,
        }

    def knowledge_facets(self) -> dict:
        with self._lock:
            folders = self._connection.execute(
                """
                SELECT folder, COUNT(*) AS count
                FROM knowledge_documents
                WHERE deleted_at IS NULL
                GROUP BY folder
                ORDER BY folder COLLATE NOCASE ASC
                """
            ).fetchall()
            tags = self._connection.execute(
                """
                SELECT json_each.value AS tag, COUNT(*) AS count
                FROM knowledge_documents AS d, json_each(d.tags_json)
                WHERE d.deleted_at IS NULL AND json_each.value != ''
                GROUP BY json_each.value
                ORDER BY json_each.value COLLATE NOCASE ASC
                """
            ).fetchall()
        return {
            "folders": [dict(row) for row in folders],
            "tags": [dict(row) for row in tags],
        }

    def all_knowledge_documents(self) -> list[dict]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM knowledge_documents").fetchall()
        return [self._document_payload(row) for row in rows]

    def count_knowledge_documents(self) -> int:
        with self._lock:
            return int(
                self._connection.execute(
                    "SELECT COUNT(*) FROM knowledge_documents WHERE deleted_at IS NULL"
                ).fetchone()[0]
            )

    def find_missing_document_by_hash(
        self, content_hash: str, active_paths: set[str]
    ) -> dict | None:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM knowledge_documents WHERE content_hash = ?",
                (content_hash,),
            ).fetchall()
        for row in rows:
            if row["relative_path"] not in active_paths:
                return self._document_payload(row)
        return None

    def mark_missing_knowledge_documents(self, active_paths: set[str]) -> int:
        now = utc_now()
        with self._lock, self._connection:
            rows = self._connection.execute(
                "SELECT relative_path FROM knowledge_documents WHERE deleted_at IS NULL"
            ).fetchall()
            missing = [row["relative_path"] for row in rows if row["relative_path"] not in active_paths]
            self._connection.executemany(
                "UPDATE knowledge_documents SET deleted_at = ? WHERE relative_path = ?",
                [(now, path) for path in missing],
            )
            if missing:
                placeholders = ",".join("?" for _ in missing)
                ids = self._connection.execute(
                    f"SELECT id FROM knowledge_documents WHERE relative_path IN ({placeholders})",
                    missing,
                ).fetchall()
                self._connection.executemany(
                    "DELETE FROM knowledge_documents_fts WHERE document_id = ?",
                    [(row["id"],) for row in ids],
                )
        return len(missing)

    def backup(self, destination: Path) -> None:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(destination)
            try:
                self._connection.backup(target)
            finally:
                target.close()

    @staticmethod
    def _document_payload(row: sqlite3.Row) -> dict:
        value = dict(row)
        value["content"] = json.loads(value.pop("content_json"))
        value["tags"] = json.loads(value.pop("tags_json", "[]") or "[]")
        value["search_indexed"] = bool(value.pop("search_text", ""))
        value["managed"] = value.get("source") == "liora"
        return value

    @staticmethod
    def _knowledge_payload(row: sqlite3.Row) -> dict:
        value = dict(row)
        value["content"] = json.loads(value.pop("content_json"))
        return value

    def close(self) -> None:
        with self._lock:
            self._connection.close()
