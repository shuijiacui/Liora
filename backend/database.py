import sqlite3
import threading
import uuid
import json
import math
import re
import struct
from datetime import datetime, timedelta, timezone
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
                    summary TEXT NOT NULL DEFAULT '',
                    knowledge_id TEXT,
                    session_type TEXT NOT NULL DEFAULT 'reflection',
                    prompt_id TEXT,
                    prompt_kind TEXT,
                    prompt_text TEXT,
                    prompt_reason TEXT,
                    target_kc_ids_json TEXT NOT NULL DEFAULT '[]',
                    rubric_json TEXT NOT NULL DEFAULT '{}'
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
                    object_type TEXT NOT NULL DEFAULT '',
                    indexed_at TEXT NOT NULL,
                    deleted_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_knowledge_documents_updated
                ON knowledge_documents(deleted_at, updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_knowledge_documents_hash
                ON knowledge_documents(content_hash);

                CREATE TABLE IF NOT EXISTS knowledge_states (
                    knowledge_id TEXT PRIMARY KEY,
                    last_reflected_at TEXT,
                    next_entry_at TEXT,
                    reflection_count INTEGER NOT NULL DEFAULT 0,
                    last_rating TEXT,
                    difficulty REAL NOT NULL DEFAULT 0.5,
                    stability_days REAL NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_knowledge_states_due
                ON knowledge_states(next_entry_at);

                CREATE TABLE IF NOT EXISTS reflection_prompt_states (
                    prompt_id TEXT PRIMARY KEY,
                    knowledge_id TEXT NOT NULL,
                    last_skipped_at TEXT,
                    last_started_at TEXT,
                    snoozed_until TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS learning_events (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL UNIQUE,
                    knowledge_id TEXT NOT NULL,
                    prompt_id TEXT NOT NULL,
                    prompt_kind TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    independent_recall INTEGER,
                    hint_count INTEGER,
                    misconception_count INTEGER,
                    knowledge_changed INTEGER NOT NULL DEFAULT 1,
                    occurred_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES reflection_sessions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_learning_events_knowledge
                ON learning_events(knowledge_id, occurred_at DESC);

                CREATE TABLE IF NOT EXISTS knowledge_changesets (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    action TEXT NOT NULL,
                    target_id TEXT,
                    target_path TEXT,
                    status TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    title TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    alignment_json TEXT NOT NULL DEFAULT '{}',
                    before_json TEXT,
                    after_json TEXT NOT NULL,
                    diff_json TEXT NOT NULL DEFAULT '[]',
                    before_markdown TEXT,
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    applied_at TEXT,
                    rolled_back_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_knowledge_changesets_status
                ON knowledge_changesets(status, created_at DESC);

                CREATE TABLE IF NOT EXISTS knowledge_embeddings (
                    knowledge_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    model TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    vector_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alignment_judgments (
                    signature TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS knowledge_relations (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    label TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'knowledge',
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    features_json TEXT NOT NULL DEFAULT '{}',
                    pipeline_version TEXT NOT NULL DEFAULT 'legacy',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(source_id, target_id, label)
                );

                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id TEXT PRIMARY KEY,
                    knowledge_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    section TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    model TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    vector_blob BLOB NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_knowledge
                ON knowledge_chunks(knowledge_id, section, ordinal);

                CREATE TABLE IF NOT EXISTS knowledge_cognitive_profiles (
                    knowledge_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    model TEXT NOT NULL,
                    profile_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_knowledge_relations_status
                ON knowledge_relations(status, kind, confidence DESC);

                CREATE TABLE IF NOT EXISTS knowledge_claims (
                    id TEXT PRIMARY KEY,
                    knowledge_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    claim_type TEXT NOT NULL,
                    subject TEXT NOT NULL DEFAULT '',
                    predicate TEXT NOT NULL DEFAULT '',
                    object_text TEXT NOT NULL DEFAULT '',
                    mechanism TEXT NOT NULL DEFAULT '',
                    conditions_json TEXT NOT NULL DEFAULT '[]',
                    polarity TEXT NOT NULL DEFAULT 'positive',
                    section TEXT NOT NULL,
                    section_label TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    evidence TEXT NOT NULL,
                    start_offset INTEGER NOT NULL DEFAULT -1,
                    end_offset INTEGER NOT NULL DEFAULT -1,
                    model TEXT NOT NULL,
                    pipeline_version TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_knowledge_claims_document
                ON knowledge_claims(knowledge_id, section, ordinal);

                CREATE TABLE IF NOT EXISTS knowledge_components (
                    id TEXT PRIMARY KEY,
                    knowledge_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    question TEXT NOT NULL,
                    claim_ids_json TEXT NOT NULL DEFAULT '[]',
                    prerequisite_ids_json TEXT NOT NULL DEFAULT '[]',
                    fingerprint TEXT NOT NULL,
                    model TEXT NOT NULL,
                    pipeline_version TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_knowledge_components_document
                ON knowledge_components(knowledge_id, ordinal);

                CREATE TABLE IF NOT EXISTS kc_states (
                    kc_id TEXT PRIMARY KEY,
                    mastery REAL NOT NULL DEFAULT 0.35,
                    uncertainty REAL NOT NULL DEFAULT 0.75,
                    stability_days REAL NOT NULL DEFAULT 0,
                    retrievability REAL NOT NULL DEFAULT 0,
                    transfer_level REAL NOT NULL DEFAULT 0,
                    misconceptions_json TEXT NOT NULL DEFAULT '[]',
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    last_evidence_type TEXT,
                    last_evidence_at TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kc_evidence (
                    id TEXT PRIMARY KEY,
                    kc_id TEXT NOT NULL,
                    session_id TEXT,
                    evidence_type TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    independent_recall INTEGER,
                    hint_count INTEGER NOT NULL DEFAULT 0,
                    misconceptions_json TEXT NOT NULL DEFAULT '[]',
                    state_before_json TEXT NOT NULL DEFAULT '{}',
                    state_after_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_kc_evidence_component
                ON kc_evidence(kc_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS insight_paths (
                    id TEXT PRIMARY KEY,
                    canonical_key TEXT NOT NULL UNIQUE,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    path_json TEXT NOT NULL,
                    learning_payoff TEXT NOT NULL,
                    failure_conditions_json TEXT NOT NULL DEFAULT '[]',
                    verification TEXT NOT NULL,
                    score REAL NOT NULL,
                    pipeline_version TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS relation_decisions (
                    id TEXT PRIMARY KEY,
                    relation_id TEXT NOT NULL,
                    canonical_key TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reason_code TEXT NOT NULL DEFAULT '',
                    source_snapshot_json TEXT NOT NULL DEFAULT '{}',
                    target_snapshot_json TEXT NOT NULL DEFAULT '{}',
                    path_snapshot_json TEXT NOT NULL DEFAULT '{}',
                    learning_payoff TEXT NOT NULL DEFAULT '',
                    pipeline_version TEXT NOT NULL,
                    decided_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_relation_decisions_recent
                ON relation_decisions(decided_at DESC);

                CREATE INDEX IF NOT EXISTS idx_relation_decisions_canonical
                ON relation_decisions(canonical_key, decided_at DESC);

                CREATE TABLE IF NOT EXISTS recommendation_feedback (
                    id TEXT PRIMARY KEY,
                    recommendation_id TEXT NOT NULL,
                    feedback_scope TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ai_usage_events (
                    id TEXT PRIMARY KEY,
                    purpose TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    prompt_cache_hit_tokens INTEGER NOT NULL DEFAULT 0,
                    prompt_cache_miss_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS granularity_candidates (
                    id TEXT PRIMARY KEY,
                    signature TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL,
                    source_ids_json TEXT NOT NULL,
                    score REAL NOT NULL,
                    reasons_json TEXT NOT NULL,
                    proposal_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_granularity_candidates_status
                ON granularity_candidates(status, score DESC);

                CREATE TABLE IF NOT EXISTS knowledge_hierarchy (
                    parent_id TEXT NOT NULL,
                    child_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(parent_id, child_id)
                );
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
            session_migrations = {
                "session_type": (
                    "ALTER TABLE reflection_sessions ADD COLUMN "
                    "session_type TEXT NOT NULL DEFAULT 'reflection'"
                ),
                "prompt_id": "ALTER TABLE reflection_sessions ADD COLUMN prompt_id TEXT",
                "prompt_kind": "ALTER TABLE reflection_sessions ADD COLUMN prompt_kind TEXT",
                "prompt_text": "ALTER TABLE reflection_sessions ADD COLUMN prompt_text TEXT",
                "prompt_reason": "ALTER TABLE reflection_sessions ADD COLUMN prompt_reason TEXT",
                "target_kc_ids_json": "ALTER TABLE reflection_sessions ADD COLUMN target_kc_ids_json TEXT NOT NULL DEFAULT '[]'",
                "rubric_json": "ALTER TABLE reflection_sessions ADD COLUMN rubric_json TEXT NOT NULL DEFAULT '{}'",
            }
            for column, statement in session_migrations.items():
                if column not in session_columns:
                    self._connection.execute(statement)
            self._connection.execute(
                "UPDATE reflection_sessions SET session_type = 'review' "
                "WHERE prompt_id IS NOT NULL AND prompt_id != ''"
            )
            document_columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(knowledge_documents)").fetchall()
            }
            document_migrations = {
                "folder": "ALTER TABLE knowledge_documents ADD COLUMN folder TEXT NOT NULL DEFAULT ''",
                "tags_json": "ALTER TABLE knowledge_documents ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]'",
                "search_text": "ALTER TABLE knowledge_documents ADD COLUMN search_text TEXT NOT NULL DEFAULT ''",
                "object_type": "ALTER TABLE knowledge_documents ADD COLUMN object_type TEXT NOT NULL DEFAULT ''",
            }
            for column, statement in document_migrations.items():
                if column not in document_columns:
                    self._connection.execute(statement)
            relation_columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(knowledge_relations)").fetchall()
            }
            relation_migrations = {
                "category": "ALTER TABLE knowledge_relations ADD COLUMN category TEXT NOT NULL DEFAULT 'knowledge'",
                "evidence_json": "ALTER TABLE knowledge_relations ADD COLUMN evidence_json TEXT NOT NULL DEFAULT '{}'",
                "features_json": "ALTER TABLE knowledge_relations ADD COLUMN features_json TEXT NOT NULL DEFAULT '{}'",
                "pipeline_version": "ALTER TABLE knowledge_relations ADD COLUMN pipeline_version TEXT NOT NULL DEFAULT 'legacy'",
            }
            for column, statement in relation_migrations.items():
                if column not in relation_columns:
                    self._connection.execute(statement)
            learning_event_columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(learning_events)").fetchall()
            }
            learning_event_migrations = {
                "target_kc_ids_json": "ALTER TABLE learning_events ADD COLUMN target_kc_ids_json TEXT NOT NULL DEFAULT '[]'",
                "outcome": "ALTER TABLE learning_events ADD COLUMN outcome TEXT NOT NULL DEFAULT ''",
                "misconceptions_json": "ALTER TABLE learning_events ADD COLUMN misconceptions_json TEXT NOT NULL DEFAULT '[]'",
            }
            for column, statement in learning_event_migrations.items():
                if column not in learning_event_columns:
                    self._connection.execute(statement)
            # The Vault boundary defines knowledge membership. Upgrade notes
            # indexed by earlier versions, which treated frontmatter markers as
            # a Knowledge Object admission check.
            self._connection.execute(
                "UPDATE knowledge_documents SET object_type = 'knowledge' "
                "WHERE object_type = '' OR object_type = 'note'"
            )
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

    def create_session(
        self,
        knowledge_id: str | None = None,
        prompt: dict | None = None,
        session_type: str = "reflection",
    ) -> dict:
        prompt = prompt or {}
        normalized_type = str(session_type or "reflection").strip().lower()
        if normalized_type not in {"reflection", "review"}:
            raise ValueError("不支持的会话类型。")
        session = {
            "id": str(uuid.uuid4()),
            "started_at": utc_now(),
            "completed_at": None,
            "status": "active",
            "summary": "",
            "knowledge_id": knowledge_id,
            "session_type": normalized_type,
            "prompt_id": prompt.get("id"),
            "prompt_kind": prompt.get("kind"),
            "prompt_text": prompt.get("prompt"),
            "prompt_reason": prompt.get("reason"),
            "target_kc_ids_json": json.dumps(prompt.get("target_kc_ids") or [], ensure_ascii=False),
            "rubric_json": json.dumps(prompt.get("rubric") or {}, ensure_ascii=False),
        }
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO reflection_sessions
                    (id, started_at, completed_at, status, summary, knowledge_id,
                     session_type, prompt_id, prompt_kind, prompt_text, prompt_reason,
                     target_kc_ids_json, rubric_json)
                VALUES
                    (:id, :started_at, :completed_at, :status, :summary, :knowledge_id,
                     :session_type, :prompt_id, :prompt_kind, :prompt_text, :prompt_reason,
                     :target_kc_ids_json, :rubric_json)
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

    def get_active_session(self, session_type: str | None = None) -> dict | None:
        with self._lock:
            if session_type:
                row = self._connection.execute(
                    """
                    SELECT * FROM reflection_sessions
                    WHERE status = 'active' AND session_type = ?
                    ORDER BY started_at DESC
                    LIMIT 1
                    """,
                    (session_type,),
                ).fetchone()
            else:
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

    def complete_session_after_changeset(
        self,
        session_id: str,
        knowledge_id: str | None,
        summary: str,
    ) -> dict:
        now = utc_now()
        with self._lock, self._connection:
            session = self._connection.execute(
                "SELECT * FROM reflection_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not session:
                raise LookupError("没有找到这次反思记录。")
            self._connection.execute(
                """
                UPDATE reflection_sessions
                SET status = 'completed', completed_at = ?, summary = ?, knowledge_id = ?
                WHERE id = ?
                """,
                (now, summary, knowledge_id, session_id),
            )
            self._connection.execute(
                "DELETE FROM knowledge_drafts WHERE session_id = ?", (session_id,)
            )
            self._connection.execute(
                "DELETE FROM reflection_messages WHERE session_id = ?", (session_id,)
            )
        return self.get_session(session_id)

    def discard_session(self, session_id: str) -> dict:
        with self._lock, self._connection:
            session = self._connection.execute(
                "SELECT * FROM reflection_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not session:
                raise LookupError("没有找到这次反思记录。")
            if session["status"] != "active":
                raise ValueError("已经完成的反思不能放弃。")
            if session["prompt_id"]:
                self._connection.execute(
                    "UPDATE reflection_prompt_states SET snoozed_until = NULL, updated_at = ? WHERE prompt_id = ?",
                    (utc_now(), session["prompt_id"]),
                )
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
                    source, object_type, indexed_at, folder, tags_json, search_text, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
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
                    object_type = excluded.object_type,
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
                    item.get("object_type", "knowledge"),
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

    def knowledge_dashboard(self, recent_limit: int = 5, question_limit: int = 5) -> dict:
        safe_recent_limit = min(max(int(recent_limit), 1), 20)
        safe_question_limit = min(max(int(question_limit), 1), 20)
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM knowledge_documents
                WHERE deleted_at IS NULL
                ORDER BY updated_at DESC, title COLLATE NOCASE ASC
                """
            ).fetchall()

        items = [self._document_payload(row) for row in rows]
        recent = [
            {
                "id": item["id"],
                "title": item["title"],
                "path": item["relative_path"],
                "updated_at": item["updated_at"],
                "summary": str(item.get("content", {}).get("core_insight") or "")[:240],
                "object_type": item.get("object_type") or "knowledge",
            }
            for item in items[:safe_recent_limit]
        ]
        open_questions = []
        for item in items:
            for question in item.get("content", {}).get("open_questions", []):
                value = str(question).strip()
                if not value:
                    continue
                open_questions.append(
                    {
                        "knowledge_id": item["id"],
                        "title": item["title"],
                        "path": item["relative_path"],
                        "question": value,
                    }
                )
                if len(open_questions) >= safe_question_limit:
                    break
            if len(open_questions) >= safe_question_limit:
                break

        health = self.knowledge_health([item["id"] for item in items])
        return {
            "knowledge_count": len(items),
            "open_question_count": sum(
                len(item.get("content", {}).get("open_questions", [])) for item in items
            ),
            "recent": recent,
            "open_questions": open_questions,
            "health": health,
        }

    def knowledge_prompt_candidates(self, limit: int = 8) -> list[dict]:
        safe_limit = min(max(int(limit), 1), 20)
        now = utc_now()
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM knowledge_documents
                WHERE deleted_at IS NULL
                ORDER BY updated_at DESC, title COLLATE NOCASE ASC
                """
            ).fetchall()
            prompt_states = {
                row["prompt_id"]: dict(row)
                for row in self._connection.execute(
                    "SELECT * FROM reflection_prompt_states"
                ).fetchall()
            }
            knowledge_states = {
                row["knowledge_id"]: dict(row)
                for row in self._connection.execute(
                    "SELECT * FROM knowledge_states"
                ).fetchall()
            }

        candidates = []
        for row in rows:
            item = self._document_payload(row)
            context = str(item.get("content", {}).get("core_insight") or "").strip()[:240]
            for question in item.get("content", {}).get("open_questions", []):
                prompt = str(question).strip()
                if not prompt:
                    continue
                prompt_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"liora:knowledge-gap:{item['id']}:{prompt}",
                    )
                )
                prompt_state = prompt_states.get(prompt_id, {})
                knowledge_state = knowledge_states.get(item["id"], {})
                snoozed_until = prompt_state.get("snoozed_until")
                next_entry_at = knowledge_state.get("next_entry_at")
                if snoozed_until and snoozed_until > now:
                    continue
                if next_entry_at and next_entry_at > now:
                    continue
                candidates.append(
                    {
                        "id": prompt_id,
                        "kind": "knowledge_gap",
                        "knowledge_id": item["id"],
                        "title": item["title"],
                        "path": item["relative_path"],
                        "context": context,
                        "prompt": prompt,
                        "reason_code": "open_question",
                        "reason": (
                            f"这个问题来自《{item['title']}》的“尚待探索”。"
                            "Liora没有额外猜测你的掌握程度。"
                        ),
                        "schedule": {
                            "reflection_count": int(knowledge_state.get("reflection_count") or 0),
                            "last_rating": knowledge_state.get("last_rating"),
                            "next_entry_at": next_entry_at,
                            "difficulty": float(knowledge_state.get("difficulty") or 0.5),
                            "stability_days": float(knowledge_state.get("stability_days") or 0),
                            "retrievability": self._retrievability(knowledge_state),
                        },
                        "_last_skipped_at": prompt_state.get("last_skipped_at") or "",
                    }
                )
        candidates.sort(
            key=lambda candidate: (
                bool(candidate["_last_skipped_at"]),
                candidate["_last_skipped_at"],
            )
        )
        for candidate in candidates:
            candidate.pop("_last_skipped_at", None)
        return candidates[:safe_limit]

    def schedule_prompt_candidates(self, candidates: list[dict], limit: int = 8) -> list[dict]:
        safe_limit = min(max(int(limit), 1), 20)
        now = utc_now()
        with self._lock:
            prompt_states = {
                row["prompt_id"]: dict(row)
                for row in self._connection.execute("SELECT * FROM reflection_prompt_states").fetchall()
            }
            knowledge_states = {
                row["knowledge_id"]: dict(row)
                for row in self._connection.execute("SELECT * FROM knowledge_states").fetchall()
            }
        scheduled = []
        for candidate in candidates:
            prompt_state = prompt_states.get(candidate["id"], {})
            knowledge_state = knowledge_states.get(candidate["knowledge_id"], {})
            snoozed_until = prompt_state.get("snoozed_until")
            next_entry_at = knowledge_state.get("next_entry_at")
            if snoozed_until and snoozed_until > now:
                continue
            if next_entry_at and next_entry_at > now:
                continue
            scheduled.append({
                **candidate,
                "schedule": {
                    "reflection_count": int(knowledge_state.get("reflection_count") or 0),
                    "last_rating": knowledge_state.get("last_rating"),
                    "next_entry_at": next_entry_at,
                    "difficulty": float(knowledge_state.get("difficulty") or 0.5),
                    "stability_days": float(knowledge_state.get("stability_days") or 0),
                    "retrievability": self._retrievability(knowledge_state),
                },
                "_last_skipped_at": prompt_state.get("last_skipped_at") or "",
            })
        scheduled.sort(key=lambda item: (bool(item["_last_skipped_at"]), item["_last_skipped_at"]))
        for item in scheduled:
            item.pop("_last_skipped_at", None)
        return scheduled[:safe_limit]

    def mark_prompt_skipped(self, prompt_id: str, knowledge_id: str) -> dict:
        now = utc_now()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO reflection_prompt_states
                    (prompt_id, knowledge_id, last_skipped_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(prompt_id) DO UPDATE SET
                    knowledge_id = excluded.knowledge_id,
                    last_skipped_at = excluded.last_skipped_at,
                    updated_at = excluded.updated_at
                """,
                (prompt_id, knowledge_id, now, now),
            )
        return {"prompt_id": prompt_id, "skipped_at": now}

    def snooze_prompt(self, prompt_id: str, knowledge_id: str, days: int = 3) -> dict:
        now = datetime.now(timezone.utc)
        until = (now + timedelta(days=min(max(int(days), 1), 30))).isoformat(timespec="seconds")
        now_text = now.isoformat(timespec="seconds")
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO reflection_prompt_states
                    (prompt_id, knowledge_id, snoozed_until, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(prompt_id) DO UPDATE SET
                    knowledge_id = excluded.knowledge_id,
                    snoozed_until = excluded.snoozed_until,
                    updated_at = excluded.updated_at
                """,
                (prompt_id, knowledge_id, until, now_text),
            )
        return {"prompt_id": prompt_id, "snoozed_until": until}

    def mark_prompt_started(self, prompt_id: str, knowledge_id: str) -> None:
        now = datetime.now(timezone.utc)
        # Keep the same card from resurfacing while its reflection is unfinished.
        until = (now + timedelta(days=1)).isoformat(timespec="seconds")
        now_text = now.isoformat(timespec="seconds")
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO reflection_prompt_states
                    (prompt_id, knowledge_id, last_started_at, snoozed_until, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(prompt_id) DO UPDATE SET
                    knowledge_id = excluded.knowledge_id,
                    last_started_at = excluded.last_started_at,
                    snoozed_until = excluded.snoozed_until,
                    updated_at = excluded.updated_at
                """,
                (prompt_id, knowledge_id, now_text, until, now_text),
            )

    def record_learning_event(
        self,
        session_id: str,
        rating: str,
        independent_recall: bool | None = None,
        hint_count: int | None = None,
        misconception_count: int | None = None,
        outcome: str | None = None,
        misconceptions: list[str] | None = None,
    ) -> dict:
        normalized = str(rating or "").strip().lower()
        if normalized not in {"again", "hard", "good", "easy"}:
            raise ValueError("复述结果必须是 again、hard、good 或 easy。")
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT * FROM learning_events WHERE session_id = ?", (session_id,)
            ).fetchone()
            if existing:
                event = self._learning_event_payload(existing)
                state = self._connection.execute(
                    "SELECT * FROM knowledge_states WHERE knowledge_id = ?",
                    (event["knowledge_id"],),
                ).fetchone()
                return {
                    **event,
                    "knowledge_state": self._knowledge_state_payload(state) if state else None,
                }
            session = self._connection.execute(
                "SELECT * FROM reflection_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not session:
                raise LookupError("没有找到这次复述。")
            if session["status"] != "completed":
                raise ValueError("请先确认知识整理结果，再评价这次复述。")
            if not session["prompt_id"] or not session["knowledge_id"]:
                raise ValueError("这次不是由知识问题发起的复述，不需要安排复习。")

            state = self._connection.execute(
                "SELECT * FROM knowledge_states WHERE knowledge_id = ?",
                (session["knowledge_id"],),
            ).fetchone()
            previous_stability = float(state["stability_days"] or 0) if state else 0.0
            previous_difficulty = float(state["difficulty"] or 0.5) if state else 0.5
            first_intervals = {"again": 1 / 6, "hard": 1.0, "good": 3.0, "easy": 7.0}
            if previous_stability <= 0:
                stability = first_intervals[normalized]
            else:
                factors = {"again": 0.5, "hard": 1.2, "good": 2.0, "easy": 3.0}
                floors = {"again": 1 / 6, "hard": 1.0, "good": 3.0, "easy": 7.0}
                stability = max(floors[normalized], previous_stability * factors[normalized])
            stability = min(stability, 365.0)
            difficulty_delta = {"again": 0.10, "hard": 0.05, "good": -0.04, "easy": -0.08}
            difficulty = min(max(previous_difficulty + difficulty_delta[normalized], 0.05), 0.95)
            occurred = datetime.now(timezone.utc)
            occurred_text = occurred.isoformat(timespec="seconds")
            next_entry = (occurred + timedelta(days=stability)).isoformat(timespec="seconds")
            count = int(state["reflection_count"] or 0) + 1 if state else 1
            target_kc_ids = json.loads(session["target_kc_ids_json"] or "[]")
            normalized_outcome = str(outcome or "").strip().lower()
            if normalized_outcome not in {"correct", "partial", "incorrect", "unknown"}:
                normalized_outcome = {
                    "easy": "correct", "good": "correct", "hard": "partial", "again": "incorrect"
                }[normalized]
            normalized_misconceptions = [
                " ".join(str(item or "").split()).strip()[:160]
                for item in (misconceptions or [])[:12]
                if " ".join(str(item or "").split()).strip()
            ]
            event = {
                "id": str(uuid.uuid4()),
                "session_id": session_id,
                "knowledge_id": session["knowledge_id"],
                "prompt_id": session["prompt_id"],
                "prompt_kind": session["prompt_kind"] or "knowledge_gap",
                "rating": normalized,
                "independent_recall": None if independent_recall is None else int(independent_recall),
                "hint_count": None if hint_count is None else max(int(hint_count), 0),
                "misconception_count": (
                    None if misconception_count is None else max(int(misconception_count), 0)
                ),
                "knowledge_changed": 1,
                "occurred_at": occurred_text,
                "target_kc_ids_json": json.dumps(target_kc_ids, ensure_ascii=False),
                "outcome": normalized_outcome,
                "misconceptions_json": json.dumps(normalized_misconceptions, ensure_ascii=False),
            }
            self._connection.execute(
                """
                INSERT INTO learning_events
                    (id, session_id, knowledge_id, prompt_id, prompt_kind, rating,
                     independent_recall, hint_count, misconception_count,
                     knowledge_changed, occurred_at, target_kc_ids_json,
                     outcome, misconceptions_json)
                VALUES
                    (:id, :session_id, :knowledge_id, :prompt_id, :prompt_kind, :rating,
                     :independent_recall, :hint_count, :misconception_count,
                     :knowledge_changed, :occurred_at, :target_kc_ids_json,
                     :outcome, :misconceptions_json)
                """,
                event,
            )
            self._connection.execute(
                """
                INSERT INTO knowledge_states
                    (knowledge_id, last_reflected_at, next_entry_at, reflection_count,
                     last_rating, difficulty, stability_days, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(knowledge_id) DO UPDATE SET
                    last_reflected_at = excluded.last_reflected_at,
                    next_entry_at = excluded.next_entry_at,
                    reflection_count = excluded.reflection_count,
                    last_rating = excluded.last_rating,
                    difficulty = excluded.difficulty,
                    stability_days = excluded.stability_days,
                    updated_at = excluded.updated_at
                """,
                (
                    session["knowledge_id"], occurred_text, next_entry, count,
                    normalized, difficulty, stability, occurred_text,
                ),
            )
            self._connection.execute(
                "UPDATE reflection_prompt_states SET snoozed_until = NULL, updated_at = ? WHERE prompt_id = ?",
                (occurred_text, session["prompt_id"]),
            )
        return {
            **self._learning_event_payload(event),
            "knowledge_state": self._knowledge_state_payload({
                "knowledge_id": session["knowledge_id"],
                "last_reflected_at": occurred_text,
                "next_entry_at": next_entry,
                "reflection_count": count,
                "last_rating": normalized,
                "difficulty": difficulty,
                "stability_days": stability,
            }),
        }

    def knowledge_health(self, knowledge_ids: list[str]) -> dict:
        if not knowledge_ids:
            return {"growing": 0, "stable": 0, "due": 0}
        now = utc_now()
        with self._lock:
            states = {
                row["knowledge_id"]: dict(row)
                for row in self._connection.execute("SELECT * FROM knowledge_states").fetchall()
            }
        growing = 0
        stable = 0
        due = 0
        for knowledge_id in knowledge_ids:
            state = states.get(knowledge_id)
            if not state or int(state.get("reflection_count") or 0) < 3:
                growing += 1
            else:
                stable += 1
            if not state or not state.get("next_entry_at") or state["next_entry_at"] <= now:
                due += 1
        return {"growing": growing, "stable": stable, "due": due}

    def create_changeset(self, value: dict) -> dict:
        now = utc_now()
        changeset = {
            "id": value.get("id") or str(uuid.uuid4()),
            "session_id": value.get("session_id"),
            "action": value["action"],
            "target_id": value.get("target_id"),
            "target_path": value.get("target_path"),
            "status": value.get("status") or "pending",
            "risk": value.get("risk") or "review",
            "title": value.get("title") or "未命名变更",
            "reason": value.get("reason") or "",
            "alignment_json": json.dumps(value.get("alignment") or {}, ensure_ascii=False),
            "before_json": (
                json.dumps(value["before"], ensure_ascii=False)
                if value.get("before") is not None
                else None
            ),
            "after_json": json.dumps(value.get("after") or {}, ensure_ascii=False),
            "diff_json": json.dumps(value.get("diff") or [], ensure_ascii=False),
            "before_markdown": value.get("before_markdown"),
            "result_json": None,
            "created_at": now,
            "resolved_at": None,
            "applied_at": None,
            "rolled_back_at": None,
        }
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO knowledge_changesets (
                    id, session_id, action, target_id, target_path, status, risk,
                    title, reason, alignment_json, before_json, after_json,
                    diff_json, before_markdown, result_json, created_at,
                    resolved_at, applied_at, rolled_back_at
                ) VALUES (
                    :id, :session_id, :action, :target_id, :target_path, :status, :risk,
                    :title, :reason, :alignment_json, :before_json, :after_json,
                    :diff_json, :before_markdown, :result_json, :created_at,
                    :resolved_at, :applied_at, :rolled_back_at
                )
                """,
                changeset,
            )
        return self.get_changeset(changeset["id"])

    def get_changeset(self, changeset_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM knowledge_changesets WHERE id = ?", (changeset_id,)
            ).fetchone()
        return self._changeset_payload(row) if row else None

    def list_changesets(self, status: str = "pending", limit: int = 30) -> list[dict]:
        safe_limit = min(max(int(limit), 1), 100)
        normalized = str(status or "").strip().lower()
        with self._lock:
            if normalized in {"pending", "applied", "rejected", "rolled_back"}:
                rows = self._connection.execute(
                    """
                    SELECT * FROM knowledge_changesets
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (normalized, safe_limit),
                ).fetchall()
            else:
                rows = self._connection.execute(
                    "SELECT * FROM knowledge_changesets ORDER BY created_at DESC LIMIT ?",
                    (safe_limit,),
                ).fetchall()
        return [self._changeset_payload(row) for row in rows]

    def resolve_changeset(
        self,
        changeset_id: str,
        status: str,
        result: dict | None = None,
    ) -> dict:
        if status not in {"applied", "rejected", "rolled_back"}:
            raise ValueError("不支持的 ChangeSet 状态。")
        now = utc_now()
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT * FROM knowledge_changesets WHERE id = ?", (changeset_id,)
            ).fetchone()
            if not row:
                raise LookupError("没有找到这条知识变更。")
            self._connection.execute(
                """
                UPDATE knowledge_changesets
                SET status = ?, result_json = ?, resolved_at = ?,
                    applied_at = CASE WHEN ? = 'applied' THEN ? ELSE applied_at END,
                    rolled_back_at = CASE WHEN ? = 'rolled_back' THEN ? ELSE rolled_back_at END
                WHERE id = ?
                """,
                (
                    status,
                    json.dumps(result or {}, ensure_ascii=False),
                    now,
                    status,
                    now,
                    status,
                    now,
                    changeset_id,
                ),
            )
        return self.get_changeset(changeset_id)

    def upsert_embedding(
        self,
        knowledge_id: str,
        fingerprint: str,
        vector: list[float],
        model: str = "liora-local-ngram-v1",
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO knowledge_embeddings
                    (knowledge_id, fingerprint, model, dimensions, vector_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(knowledge_id) DO UPDATE SET
                    fingerprint = excluded.fingerprint,
                    model = excluded.model,
                    dimensions = excluded.dimensions,
                    vector_json = excluded.vector_json,
                    updated_at = excluded.updated_at
                """,
                (
                    knowledge_id,
                    fingerprint,
                    model,
                    len(vector),
                    json.dumps(vector),
                    utc_now(),
                ),
            )

    def list_embeddings(self) -> dict[str, dict]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM knowledge_embeddings").fetchall()
        return {
            row["knowledge_id"]: {
                **dict(row),
                "vector": json.loads(row["vector_json"]),
            }
            for row in rows
        }

    @staticmethod
    def _pack_half_vector(vector: list[float]) -> bytes:
        return struct.pack(f"<{len(vector)}e", *vector) if vector else b""

    @staticmethod
    def _unpack_half_vector(value: bytes, dimensions: int) -> list[float]:
        if not value or dimensions <= 0:
            return []
        return [float(item) for item in struct.unpack(f"<{dimensions}e", value)]

    def list_knowledge_chunks(self) -> dict[str, dict]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM knowledge_chunks ORDER BY knowledge_id, section, ordinal"
            ).fetchall()
        result = {}
        for row in rows:
            item = dict(row)
            vector_blob = item.pop("vector_blob")
            item["embedding"] = self._unpack_half_vector(
                vector_blob, int(item["dimensions"])
            )
            result[row["id"]] = item
        return result

    def replace_knowledge_chunks(self, chunks: list[dict], model: str) -> None:
        now = utc_now()
        active_ids = {str(item["id"]) for item in chunks}
        with self._lock, self._connection:
            existing_ids = {
                row["id"] for row in self._connection.execute("SELECT id FROM knowledge_chunks").fetchall()
            }
            stale = existing_ids - active_ids
            if stale:
                self._connection.executemany(
                    "DELETE FROM knowledge_chunks WHERE id = ?",
                    [(item,) for item in stale],
                )
            self._connection.executemany(
                """
                INSERT INTO knowledge_chunks (
                    id, knowledge_id, fingerprint, section, ordinal, text,
                    model, dimensions, vector_blob, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    knowledge_id = excluded.knowledge_id,
                    fingerprint = excluded.fingerprint,
                    section = excluded.section,
                    ordinal = excluded.ordinal,
                    text = excluded.text,
                    model = excluded.model,
                    dimensions = excluded.dimensions,
                    vector_blob = excluded.vector_blob,
                    updated_at = excluded.updated_at
                """,
                [
                    (
                        item["id"], item["knowledge_id"], item["fingerprint"],
                        item["section"], int(item["ordinal"]), item["text"], model,
                        len(item.get("embedding") or []),
                        self._pack_half_vector(item.get("embedding") or []), now,
                    )
                    for item in chunks
                ],
            )

    def list_cognitive_profiles(self) -> dict[str, dict]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM knowledge_cognitive_profiles"
            ).fetchall()
        return {
            row["knowledge_id"]: {
                **dict(row),
                "profile": json.loads(row["profile_json"]),
            }
            for row in rows
        }

    def upsert_cognitive_profile(
        self, knowledge_id: str, fingerprint: str, model: str, profile: dict
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO knowledge_cognitive_profiles
                    (knowledge_id, fingerprint, model, profile_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(knowledge_id) DO UPDATE SET
                    fingerprint = excluded.fingerprint,
                    model = excluded.model,
                    profile_json = excluded.profile_json,
                    updated_at = excluded.updated_at
                """,
                (
                    knowledge_id,
                    fingerprint,
                    model,
                    json.dumps(profile, ensure_ascii=False),
                    utc_now(),
                ),
            )

    def count_cognitive_profiles_since(self, moment: str, model_prefix: str = "deepseek:") -> int:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT COUNT(*) FROM knowledge_cognitive_profiles
                WHERE updated_at >= ? AND model LIKE ?
                """,
                (moment, f"{model_prefix}%"),
            ).fetchone()
        return int(row[0])

    def replace_grounded_structure(
        self, knowledge_id: str, claims: list[dict], components: list[dict]
    ) -> None:
        """Replace derived claims/components while retaining stable KC states."""

        now = utc_now()
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM knowledge_claims WHERE knowledge_id = ?", (knowledge_id,)
            )
            self._connection.execute(
                "DELETE FROM knowledge_components WHERE knowledge_id = ?", (knowledge_id,)
            )
            self._connection.executemany(
                """
                INSERT INTO knowledge_claims (
                    id, knowledge_id, fingerprint, claim_type, subject, predicate,
                    object_text, mechanism, conditions_json, polarity, section,
                    section_label, ordinal, evidence, start_offset, end_offset,
                    model, pipeline_version, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item["id"], knowledge_id, item["fingerprint"], item["claim_type"],
                        item.get("subject", ""), item.get("predicate", ""),
                        item.get("object", ""), item.get("mechanism", ""),
                        json.dumps(item.get("conditions") or [], ensure_ascii=False),
                        item.get("polarity", "positive"), item["section"],
                        item.get("section_label", item["section"]), int(item.get("ordinal") or 0),
                        item["evidence"], int(item.get("start_offset", -1)),
                        int(item.get("end_offset", -1)), item.get("model", "local"),
                        item.get("pipeline_version", "learning-engine-v4"), now,
                    )
                    for item in claims
                ],
            )
            self._connection.executemany(
                """
                INSERT INTO knowledge_components (
                    id, knowledge_id, title, question, claim_ids_json,
                    prerequisite_ids_json, fingerprint, model, pipeline_version,
                    ordinal, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item["id"], knowledge_id, item["title"], item["question"],
                        json.dumps(item.get("claim_ids") or [], ensure_ascii=False),
                        json.dumps(item.get("prerequisite_ids") or [], ensure_ascii=False),
                        item["fingerprint"], item.get("model", "local"),
                        item.get("pipeline_version", "learning-engine-v4"),
                        int(item.get("ordinal") or 0), now,
                    )
                    for item in components
                ],
            )

    def list_grounded_claims(self) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM knowledge_claims ORDER BY knowledge_id, section, ordinal"
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["object"] = item.pop("object_text", "")
            item["conditions"] = json.loads(item.pop("conditions_json", "[]") or "[]")
            result.append(item)
        return result

    def list_knowledge_components(self, knowledge_id: str | None = None) -> list[dict]:
        with self._lock:
            if knowledge_id:
                rows = self._connection.execute(
                    "SELECT * FROM knowledge_components WHERE knowledge_id = ? ORDER BY ordinal",
                    (knowledge_id,),
                ).fetchall()
            else:
                rows = self._connection.execute(
                    "SELECT * FROM knowledge_components ORDER BY knowledge_id, ordinal"
                ).fetchall()
            states = {
                row["kc_id"]: dict(row)
                for row in self._connection.execute("SELECT * FROM kc_states").fetchall()
            }
        result = []
        for row in rows:
            item = dict(row)
            item["claim_ids"] = json.loads(item.pop("claim_ids_json", "[]") or "[]")
            item["prerequisite_ids"] = json.loads(
                item.pop("prerequisite_ids_json", "[]") or "[]"
            )
            state = states.get(item["id"])
            if state:
                state["misconceptions"] = json.loads(
                    state.pop("misconceptions_json", "[]") or "[]"
                )
            item["state"] = state
            result.append(item)
        return result

    def get_kc_state(self, kc_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM kc_states WHERE kc_id = ?", (kc_id,)
            ).fetchone()
        if not row:
            return None
        value = dict(row)
        value["misconceptions"] = json.loads(
            value.pop("misconceptions_json", "[]") or "[]"
        )
        return value

    def record_kc_evidence(
        self, kc_id: str, session_id: str | None, evidence: dict,
        before: dict, after: dict,
    ) -> dict:
        event_id = str(uuid.uuid4())
        now = utc_now()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO kc_evidence (
                    id, kc_id, session_id, evidence_type, outcome,
                    independent_recall, hint_count, misconceptions_json,
                    state_before_json, state_after_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id, kc_id, session_id, evidence.get("evidence_type", "recall"),
                    evidence.get("outcome", "unknown"),
                    None if evidence.get("independent_recall") is None else int(bool(evidence.get("independent_recall"))),
                    max(int(evidence.get("hint_count") or 0), 0),
                    json.dumps(evidence.get("misconceptions") or [], ensure_ascii=False),
                    json.dumps(before or {}, ensure_ascii=False),
                    json.dumps(after or {}, ensure_ascii=False), now,
                ),
            )
            self._connection.execute(
                """
                INSERT INTO kc_states (
                    kc_id, mastery, uncertainty, stability_days, retrievability,
                    transfer_level, misconceptions_json, evidence_count,
                    last_evidence_type, last_evidence_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(kc_id) DO UPDATE SET
                    mastery = excluded.mastery,
                    uncertainty = excluded.uncertainty,
                    stability_days = excluded.stability_days,
                    retrievability = excluded.retrievability,
                    transfer_level = excluded.transfer_level,
                    misconceptions_json = excluded.misconceptions_json,
                    evidence_count = excluded.evidence_count,
                    last_evidence_type = excluded.last_evidence_type,
                    last_evidence_at = excluded.last_evidence_at,
                    updated_at = excluded.updated_at
                """,
                (
                    kc_id, float(after.get("mastery") or 0.35),
                    float(after.get("uncertainty") or 0.75),
                    float(after.get("stability_days") or 0),
                    float(after.get("retrievability") or 0),
                    float(after.get("transfer_level") or 0),
                    json.dumps(after.get("misconceptions") or [], ensure_ascii=False),
                    int(after.get("evidence_count") or 0),
                    after.get("last_evidence_type"), after.get("last_evidence_at"), now,
                ),
            )
        return {"id": event_id, "kc_id": kc_id, "created_at": now, "state": after}

    def record_ai_usage(self, purpose: str, model: str, usage: dict | None) -> None:
        usage = usage or {}
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO ai_usage_events (
                    id, purpose, model, prompt_tokens, prompt_cache_hit_tokens,
                    prompt_cache_miss_tokens, completion_tokens, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()), purpose, model,
                    int(usage.get("prompt_tokens") or 0),
                    int(usage.get("prompt_cache_hit_tokens") or 0),
                    int(usage.get("prompt_cache_miss_tokens") or 0),
                    int(usage.get("completion_tokens") or 0), utc_now(),
                ),
            )

    def ai_usage_since(self, moment: str) -> dict:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                       COALESCE(SUM(prompt_cache_hit_tokens), 0) AS prompt_cache_hit_tokens,
                       COALESCE(SUM(prompt_cache_miss_tokens), 0) AS prompt_cache_miss_tokens,
                       COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                       COUNT(*) AS calls
                FROM ai_usage_events WHERE created_at >= ?
                """,
                (moment,),
            ).fetchone()
        return dict(row)

    def record_recommendation_feedback(
        self, recommendation_id: str, feedback_scope: str, reason_code: str,
        details: str = "",
    ) -> dict:
        item = {
            "id": str(uuid.uuid4()),
            "recommendation_id": str(recommendation_id or "")[:160],
            "feedback_scope": str(feedback_scope or "prompt")[:40],
            "reason_code": str(reason_code or "unknown")[:80],
            "details": str(details or "")[:1000],
            "created_at": utc_now(),
        }
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO recommendation_feedback (
                    id, recommendation_id, feedback_scope, reason_code, details, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                tuple(item[key] for key in (
                    "id", "recommendation_id", "feedback_scope", "reason_code", "details", "created_at"
                )),
            )
        return item

    def get_alignment_judgment(self, signature: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT result_json FROM alignment_judgments WHERE signature = ?",
                (signature,),
            ).fetchone()
        return json.loads(row["result_json"]) if row else None

    def save_alignment_judgment(self, signature: str, model: str, result: dict) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO alignment_judgments (signature, model, result_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(signature) DO UPDATE SET
                    model = excluded.model,
                    result_json = excluded.result_json,
                    created_at = excluded.created_at
                """,
                (signature, model, json.dumps(result, ensure_ascii=False), utc_now()),
            )

    def count_alignment_judgments_since(self, moment: str) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) FROM alignment_judgments WHERE created_at >= ?",
                (moment,),
            ).fetchone()
        return int(row[0])

    def replace_discovered_relations(self, relations: list[dict]) -> None:
        now = utc_now()
        with self._lock, self._connection:
            # Candidates are derived data. Rebuild them from scratch so a
            # cleaner algorithm removes historical false positives. Preserve
            # confirmed/rejected decisions made by the user.
            self._connection.execute(
                "DELETE FROM knowledge_relations WHERE status = 'candidate'"
            )
            latest_actions: dict[str, str] = {}
            for row in self._connection.execute(
                "SELECT canonical_key, action FROM relation_decisions ORDER BY decided_at DESC"
            ).fetchall():
                latest_actions.setdefault(row["canonical_key"], row["action"])
            rejected_keys = {
                key for key, action in latest_actions.items() if action == "rejected"
            }
            self._connection.execute("DELETE FROM insight_paths")
            for relation in relations:
                features = relation.get("features") or {}
                canonical_key = str(features.get("canonical_key") or "")
                if relation.get("status") == "candidate" and canonical_key in rejected_keys:
                    continue
                left, right = sorted((relation["source_id"], relation["target_id"]))
                relation_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"liora:relation:{left}:{right}:{relation['label']}",
                    )
                )
                self._connection.execute(
                    """
                    INSERT INTO knowledge_relations (
                        id, source_id, target_id, kind, label, confidence,
                        reason, status, created_at, updated_at, category,
                        evidence_json, features_json, pipeline_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id, target_id, label) DO UPDATE SET
                        kind = excluded.kind,
                        category = excluded.category,
                        confidence = excluded.confidence,
                        reason = excluded.reason,
                        evidence_json = excluded.evidence_json,
                        features_json = excluded.features_json,
                        pipeline_version = excluded.pipeline_version,
                        status = CASE
                            WHEN knowledge_relations.status IN ('confirmed', 'rejected')
                            THEN knowledge_relations.status
                            ELSE excluded.status
                        END,
                        updated_at = excluded.updated_at
                    """,
                    (
                        relation_id,
                        left,
                        right,
                        relation["kind"],
                        relation["label"],
                        float(relation["confidence"]),
                        relation["reason"],
                        relation["status"],
                        now,
                        now,
                        relation.get("category", "knowledge"),
                        json.dumps(relation.get("evidence") or {}, ensure_ascii=False),
                        json.dumps(relation.get("features") or {}, ensure_ascii=False),
                        relation.get("pipeline_version", "legacy"),
                    ),
                )
                evidence = relation.get("evidence") or {}
                path = evidence.get("path")
                if canonical_key and isinstance(path, list) and path:
                    self._connection.execute(
                        """
                        INSERT INTO insight_paths (
                            id, canonical_key, source_id, target_id, relation_type,
                            path_json, learning_payoff, failure_conditions_json,
                            verification, score, pipeline_version, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(canonical_key) DO UPDATE SET
                            path_json = excluded.path_json,
                            learning_payoff = excluded.learning_payoff,
                            failure_conditions_json = excluded.failure_conditions_json,
                            verification = excluded.verification,
                            score = excluded.score,
                            pipeline_version = excluded.pipeline_version,
                            updated_at = excluded.updated_at
                        """,
                        (
                            str(uuid.uuid5(uuid.NAMESPACE_URL, f"liora:path:{canonical_key}")),
                            canonical_key, left, right, relation["label"],
                            json.dumps(path, ensure_ascii=False),
                            str(evidence.get("learning_payoff") or relation.get("reason") or ""),
                            json.dumps(evidence.get("failure_conditions") or [], ensure_ascii=False),
                            str(evidence.get("verification") or "unverified"),
                            float(relation.get("confidence") or 0),
                            relation.get("pipeline_version", "legacy"), now,
                        ),
                    )

    def list_relations(self, status: str = "", limit: int = 100) -> list[dict]:
        safe_limit = min(max(int(limit), 1), 300)
        with self._lock:
            if status:
                rows = self._connection.execute(
                    """
                    SELECT * FROM knowledge_relations WHERE status = ?
                    ORDER BY confidence DESC LIMIT ?
                    """,
                    (status, safe_limit),
                ).fetchall()
            else:
                rows = self._connection.execute(
                    "SELECT * FROM knowledge_relations ORDER BY confidence DESC LIMIT ?",
                    (safe_limit,),
                ).fetchall()
        return [self._relation_payload(row) for row in rows]

    def set_relation_status(self, relation_id: str, status: str) -> dict:
        if status not in {"candidate", "confirmed", "rejected"}:
            raise ValueError("不支持的关系状态。")
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE knowledge_relations SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), relation_id),
            )
            row = self._connection.execute(
                "SELECT * FROM knowledge_relations WHERE id = ?", (relation_id,)
            ).fetchone()
        if not row:
            raise LookupError("没有找到这条知识关系。")
        return self._relation_payload(row)

    def resolve_relation(
        self,
        relation_id: str,
        status: str,
        reason_code: str = "",
        source_snapshot: dict | None = None,
        target_snapshot: dict | None = None,
    ) -> dict:
        if status not in {"confirmed", "rejected", "candidate"}:
            raise ValueError("不支持的关系状态。")
        now = utc_now()
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT * FROM knowledge_relations WHERE id = ?", (relation_id,)
            ).fetchone()
            if not row:
                raise LookupError("没有找到这条知识关系。")
            relation = self._relation_payload(row)
            self._connection.execute(
                "UPDATE knowledge_relations SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, relation_id),
            )
            features = relation.get("features") or {}
            evidence = relation.get("evidence") or {}
            canonical_key = str(
                features.get("canonical_key")
                or uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"liora:relation-decision:{relation['source_id']}:{relation['target_id']}:{relation['label']}",
                )
            )
            decision_action = status if status in {"confirmed", "rejected"} else "restored"
            if status in {"confirmed", "rejected", "candidate"}:
                self._connection.execute(
                    """
                    INSERT INTO relation_decisions (
                        id, relation_id, canonical_key, action, reason_code,
                        source_snapshot_json, target_snapshot_json,
                        path_snapshot_json, learning_payoff, pipeline_version,
                        decided_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()), relation_id, canonical_key, decision_action,
                        str(reason_code or "")[:80],
                        json.dumps(source_snapshot or {}, ensure_ascii=False),
                        json.dumps(target_snapshot or {}, ensure_ascii=False),
                        json.dumps(evidence, ensure_ascii=False),
                        str(evidence.get("learning_payoff") or relation.get("reason") or "")[:1200],
                        relation.get("pipeline_version", "legacy"), now,
                    ),
                )
            updated = self._connection.execute(
                "SELECT * FROM knowledge_relations WHERE id = ?", (relation_id,)
            ).fetchone()
        return self._relation_payload(updated)

    def list_relation_decisions(self, limit: int = 100) -> list[dict]:
        safe_limit = min(max(int(limit), 1), 300)
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM relation_decisions ORDER BY decided_at DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["source"] = json.loads(item.pop("source_snapshot_json", "{}") or "{}")
            item["target"] = json.loads(item.pop("target_snapshot_json", "{}") or "{}")
            item["evidence"] = json.loads(item.pop("path_snapshot_json", "{}") or "{}")
            result.append(item)
        return result

    def replace_granularity_candidates(self, candidates: list[dict]) -> None:
        now = utc_now()
        with self._lock, self._connection:
            # Granularity suggestions are derived from the current active
            # knowledge scope. Rebuild pending candidates from scratch so
            # excluded or deleted notes cannot survive as stale suggestions.
            # Preserve explicit user decisions (rejected/confirmed/applied).
            self._connection.execute(
                "DELETE FROM granularity_candidates WHERE status = 'candidate'"
            )
            for candidate in candidates:
                signature = json.dumps(
                    [candidate["kind"], sorted(candidate["source_ids"])],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                candidate_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"liora:granularity:{signature}"))
                self._connection.execute(
                    """
                    INSERT INTO granularity_candidates (
                        id, signature, kind, source_ids_json, score, reasons_json,
                        proposal_json, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'candidate', ?, ?)
                    ON CONFLICT(signature) DO UPDATE SET
                        score = excluded.score,
                        reasons_json = excluded.reasons_json,
                        proposal_json = excluded.proposal_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        candidate_id,
                        signature,
                        candidate["kind"],
                        json.dumps(candidate["source_ids"], ensure_ascii=False),
                        float(candidate["score"]),
                        json.dumps(candidate["reasons"], ensure_ascii=False),
                        json.dumps(candidate["proposal"], ensure_ascii=False),
                        now,
                        now,
                    ),
                )

    def list_granularity_candidates(self, status: str = "candidate", limit: int = 40) -> list[dict]:
        safe_limit = min(max(int(limit), 1), 100)
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM granularity_candidates
                WHERE status = ?
                ORDER BY score DESC LIMIT ?
                """,
                (status, safe_limit),
            ).fetchall()
        return [self._granularity_payload(row) for row in rows]

    def set_granularity_status(self, candidate_id: str, status: str) -> dict:
        if status not in {"candidate", "confirmed", "rejected", "applied"}:
            raise ValueError("不支持的粒度候选状态。")
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE granularity_candidates SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), candidate_id),
            )
            row = self._connection.execute(
                "SELECT * FROM granularity_candidates WHERE id = ?", (candidate_id,)
            ).fetchone()
        if not row:
            raise LookupError("没有找到这条粒度建议。")
        return self._granularity_payload(row)

    def add_hierarchy(self, parent_id: str, child_id: str, source: str = "review") -> None:
        if parent_id == child_id:
            raise ValueError("知识对象不能成为自己的子对象。")
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO knowledge_hierarchy
                    (parent_id, child_id, source, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (parent_id, child_id, source, utc_now()),
            )

    def list_hierarchy(self) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM knowledge_hierarchy ORDER BY created_at"
            ).fetchall()
        return [dict(row) for row in rows]

    def remove_knowledge_intelligence(self, knowledge_id: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM knowledge_embeddings WHERE knowledge_id = ?", (knowledge_id,)
            )
            self._connection.execute(
                "DELETE FROM knowledge_relations WHERE source_id = ? OR target_id = ?",
                (knowledge_id, knowledge_id),
            )
            self._connection.execute(
                "DELETE FROM knowledge_hierarchy WHERE parent_id = ? OR child_id = ?",
                (knowledge_id, knowledge_id),
            )
            component_ids = [
                row["id"]
                for row in self._connection.execute(
                    "SELECT id FROM knowledge_components WHERE knowledge_id = ?",
                    (knowledge_id,),
                ).fetchall()
            ]
            self._connection.execute(
                "DELETE FROM knowledge_claims WHERE knowledge_id = ?", (knowledge_id,)
            )
            self._connection.execute(
                "DELETE FROM knowledge_components WHERE knowledge_id = ?", (knowledge_id,)
            )
            if component_ids:
                self._connection.executemany(
                    "DELETE FROM kc_states WHERE kc_id = ?",
                    [(item,) for item in component_ids],
                )
                self._connection.executemany(
                    "DELETE FROM kc_evidence WHERE kc_id = ?",
                    [(item,) for item in component_ids],
                )
            self._connection.execute(
                "DELETE FROM insight_paths WHERE source_id = ? OR target_id = ?",
                (knowledge_id, knowledge_id),
            )

    @staticmethod
    def _learning_event_payload(row: sqlite3.Row | dict) -> dict:
        value = dict(row)
        for key in ("independent_recall", "knowledge_changed"):
            if value.get(key) is not None:
                value[key] = bool(value[key])
        value["target_kc_ids"] = json.loads(
            value.pop("target_kc_ids_json", "[]") or "[]"
        )
        value["misconceptions"] = json.loads(
            value.pop("misconceptions_json", "[]") or "[]"
        )
        return value

    @staticmethod
    def _changeset_payload(row: sqlite3.Row | dict) -> dict:
        value = dict(row)
        for stored, public in (
            ("alignment_json", "alignment"),
            ("before_json", "before"),
            ("after_json", "after"),
            ("diff_json", "diff"),
            ("result_json", "result"),
        ):
            raw = value.pop(stored, None)
            value[public] = json.loads(raw) if raw else None
        return value

    @staticmethod
    def _granularity_payload(row: sqlite3.Row | dict) -> dict:
        value = dict(row)
        value["source_ids"] = json.loads(value.pop("source_ids_json"))
        value["reasons"] = json.loads(value.pop("reasons_json"))
        value["proposal"] = json.loads(value.pop("proposal_json"))
        return value

    @staticmethod
    def _retrievability(state: dict) -> float:
        last_reflected = state.get("last_reflected_at")
        stability = float(state.get("stability_days") or 0)
        if not last_reflected or stability <= 0:
            return 0.0
        try:
            moment = datetime.fromisoformat(str(last_reflected))
            elapsed_days = max((datetime.now(timezone.utc) - moment).total_seconds() / 86400, 0)
        except (TypeError, ValueError):
            return 0.0
        return round(math.exp(-elapsed_days / stability), 4)

    @classmethod
    def _knowledge_state_payload(cls, row: sqlite3.Row | dict) -> dict:
        value = dict(row)
        value["retrievability"] = cls._retrievability(value)
        return value

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
    def _relation_payload(row: sqlite3.Row) -> dict:
        value = dict(row)
        value["category"] = value.get("category") or "knowledge"
        value["evidence"] = json.loads(value.pop("evidence_json", "{}") or "{}")
        value["features"] = json.loads(value.pop("features_json", "{}") or "{}")
        return value

    @staticmethod
    def _knowledge_payload(row: sqlite3.Row) -> dict:
        value = dict(row)
        value["content"] = json.loads(value.pop("content_json"))
        return value

    def close(self) -> None:
        with self._lock:
            self._connection.close()
