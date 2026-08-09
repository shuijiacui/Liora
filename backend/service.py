import uuid
from pathlib import Path

from database import ReflectionDatabase, utc_now
from deepseek_client import DeepSeekClient, DeepSeekError
from knowledge_store import KnowledgeVault
from reflection_agent import START_PROMPT, follow_up, make_knowledge_draft


class ReflectionService:
    def __init__(
        self,
        database: ReflectionDatabase,
        llm_client: DeepSeekClient | None = None,
        vault_path: Path | None = None,
        data_dir: Path | None = None,
    ):
        self._database = database
        self._llm_client = llm_client
        self._data_dir = Path(data_dir) if data_dir else Path.cwd()
        self._vault: KnowledgeVault | None = None
        if vault_path:
            self.configure_vault(vault_path)

    def status(self) -> dict:
        configured = bool(self._llm_client and self._llm_client.configured)
        return {
            "provider": "deepseek" if configured else "local",
            "model": self._llm_client.settings.model if configured else "local-reflection-agent",
            "configured": configured,
            "storage": self.storage_status(),
        }

    def configure_vault(self, vault_path: Path | str) -> dict:
        vault = KnowledgeVault(
            self._database,
            Path(vault_path),
            self._data_dir / "backups",
        )
        scan = vault.scan()
        self._vault = vault
        return {**vault.status(), "scan": scan}

    def storage_status(self) -> dict:
        if self._vault is None:
            return {"configured": False, "vault_path": None, "indexed_count": 0}
        return self._vault.status()

    def scan_vault(self) -> dict:
        if self._vault is None:
            raise ValueError("请先选择 Obsidian Vault。")
        return {"storage": self._vault.status(), "scan": self._vault.scan()}

    def rebuild_vault_index(self) -> dict:
        if self._vault is None:
            raise ValueError("请先选择 Obsidian Vault。")
        return {"storage": self._vault.status(), "scan": self._vault.rebuild_index()}

    def migrate_legacy_knowledge(self) -> dict:
        if self._vault is None:
            raise ValueError("请先选择 Obsidian Vault。")
        report = self._vault.migrate_legacy()
        return {"storage": self._vault.status(), "migration": report}

    def _get_knowledge(self, knowledge_id: str) -> dict | None:
        if self._vault:
            return self._database.get_knowledge_document(knowledge_id)
        return self._database.get_knowledge(knowledge_id)

    def start(self, force_new: bool = False, knowledge_id: str | None = None) -> dict:
        existing_knowledge = None
        if knowledge_id:
            if self._vault:
                self._vault.scan()
            existing_knowledge = self._get_knowledge(knowledge_id)
            if existing_knowledge is None:
                raise LookupError("没有找到要继续完善的知识记录。")
        session = None if force_new or knowledge_id else self._database.get_active_session()
        resumed = session is not None

        if session is None:
            session = self._database.create_session(knowledge_id=knowledge_id)
            prompt = (
                f"关于“{existing_knowledge['title']}”，你又有了什么新的感悟？"
                if existing_knowledge
                else START_PROMPT
            )
            self._database.add_message(session["id"], "assistant", prompt)

        payload = self._payload(session["id"], resumed=resumed)
        draft = self._database.get_knowledge_draft(session["id"])
        if draft:
            payload["awaiting_confirmation"] = True
            payload["knowledge_draft"] = draft["content"]
        return payload

    def reply(self, session_id: str, content: str) -> dict:
        content = content.strip()
        if not content:
            raise ValueError("写下一点内容后再发送吧。")
        if len(content) > 2000:
            raise ValueError("单条内容请控制在 2000 字以内。")

        session = self._require_active_session(session_id)
        self._database.discard_knowledge_draft(session_id)
        self._database.add_message(session_id, "user", content)
        messages = self._database.get_messages(session_id)
        user_messages = [item["content"] for item in messages if item["role"] == "user"]

        provider = None
        notice = None
        if self._llm_client and self._llm_client.configured:
            try:
                assistant_message = self._llm_client.generate_follow_up(messages, len(user_messages))
                provider = "deepseek"
            except DeepSeekError as error:
                print(f"LIORA_DEEPSEEK_FALLBACK {error}", flush=True)
                assistant_message = follow_up(content, len(user_messages))
                provider = "local-fallback"
                notice = "DeepSeek 暂时不可用，已使用本地反思策略继续。"
        else:
            assistant_message = follow_up(content, len(user_messages))
            provider = "local"
        self._database.add_message(session_id, "assistant", assistant_message)
        return self._payload(session_id, provider=provider, notice=notice)

    def finish(self, session_id: str) -> dict:
        session = self._require_active_session(session_id)
        messages = self._database.get_messages(session_id)
        user_messages = [item["content"] for item in messages if item["role"] == "user"]
        if not user_messages:
            raise ValueError("至少说下一点内容后再整理吧。")
        existing = (
            self._get_knowledge(session.get("knowledge_id"))
            if session.get("knowledge_id")
            else None
        )
        provider = None
        notice = None
        if self._llm_client and self._llm_client.configured:
            try:
                draft_content = self._llm_client.organize_knowledge(messages, existing)
                provider = "deepseek"
            except DeepSeekError as error:
                print(f"LIORA_DEEPSEEK_FALLBACK {error}", flush=True)
                draft_content = make_knowledge_draft(user_messages, existing)
                provider = "local-fallback"
                notice = "DeepSeek 暂时不可用，已使用本地方式整理。"
        else:
            draft_content = make_knowledge_draft(user_messages, existing)
            provider = "local"
        draft = self._database.save_knowledge_draft(
            session_id, draft_content, session.get("knowledge_id")
        )
        payload = self._payload(session_id, complete=False, provider=provider, notice=notice)
        payload["awaiting_confirmation"] = True
        payload["knowledge_draft"] = draft["content"]
        return payload

    def confirm(self, session_id: str) -> dict:
        session = self._require_active_session(session_id)
        if self._vault:
            draft = self._database.get_knowledge_draft(session_id)
            if draft is None:
                raise LookupError("没有找到待确认的知识整理结果。")
            existing = self._get_knowledge(draft.get("knowledge_id") or session.get("knowledge_id"))
            knowledge_id = existing["id"] if existing else str(uuid.uuid4())
            version = int(existing.get("version") or 0) + 1 if existing else 1
            now = utc_now()
            proposed = {
                "id": knowledge_id,
                "title": draft["content"]["title"],
                "created_at": existing["created_at"] if existing else now,
                "updated_at": now,
                "version": version,
                "content": draft["content"],
            }
            knowledge = self._vault.write(proposed)
            self._database.confirm_knowledge_draft(
                session_id,
                knowledge_id_override=knowledge_id,
                version_override=version,
            )
        else:
            knowledge = self._database.confirm_knowledge_draft(session_id)
        payload = self._payload(session_id, complete=True)
        payload["knowledge"] = knowledge
        return payload

    def discard(self, session_id: str) -> dict:
        session = self._require_active_session(session_id)
        if self._database.get_knowledge_draft(session_id) is None:
            raise LookupError("没有找到可以放弃的知识草稿。")
        self._database.discard_session(session_id)
        return {
            "discarded": True,
            "session_id": session_id,
            "knowledge_id": session.get("knowledge_id"),
        }

    def knowledge_list(
        self,
        limit: int = 20,
        offset: int = 0,
        query: str = "",
        folder: str = "",
        tag: str = "",
        sort: str = "relevance",
    ) -> dict:
        if self._vault:
            scan = self._vault.scan(allow_cached=True)
            result = self._database.search_knowledge_documents(
                query=query,
                folder=folder,
                tag=tag,
                sort=sort,
                limit=limit,
                offset=offset,
            )
            return {**result, "facets": self._database.knowledge_facets(), "scan": scan}

        safe_limit = min(max(int(limit), 1), 50)
        safe_offset = max(int(offset), 0)
        normalized_query = str(query or "").strip().casefold()
        items = self._database.list_all_knowledge()
        if normalized_query:
            items = [
                item
                for item in items
                if normalized_query
                in "\n".join(
                    [
                        item.get("title", ""),
                        item.get("content", {}).get("core_insight", ""),
                        *item.get("content", {}).get("logic_chain", []),
                        *item.get("content", {}).get("open_questions", []),
                        item.get("content", {}).get("next_step", ""),
                    ]
                ).casefold()
            ]
        if sort == "title":
            items.sort(key=lambda item: item.get("title", "").casefold())
        total = len(items)
        page = items[safe_offset : safe_offset + safe_limit]
        for item in page:
            item["folder"] = ""
            item["tags"] = []
            item["snippet"] = item.get("content", {}).get("core_insight", "")[:180]
        return {
            "items": page,
            "total": total,
            "limit": safe_limit,
            "offset": safe_offset,
            "has_more": safe_offset + len(page) < total,
            "facets": {"folders": [], "tags": []},
        }

    def knowledge_get(self, knowledge_id: str) -> dict:
        if self._vault:
            self._vault.scan()
        item = self._get_knowledge(knowledge_id)
        if item is None:
            raise LookupError("没有找到这条知识记录。")
        return {"item": item}

    def history(self, limit: int = 20) -> dict:
        return {"sessions": self._database.list_sessions(limit)}

    def _require_active_session(self, session_id: str) -> dict:
        session = self._database.get_session(session_id)
        if session is None:
            raise LookupError("没有找到这次反思记录。")
        if session["status"] != "active":
            raise ValueError("这次反思已经完成，可以开始新的一次。")
        return session

    def _payload(
        self,
        session_id: str,
        resumed: bool = False,
        complete: bool | None = None,
        provider: str | None = None,
        notice: str | None = None,
    ) -> dict:
        session = self._database.get_session(session_id)
        status = self.status()
        return {
            "session": session,
            "messages": self._database.get_messages(session_id),
            "resumed": resumed,
            "complete": session["status"] == "completed" if complete is None else complete,
            "provider": provider or status["provider"],
            "model": status["model"],
            "notice": notice,
        }
