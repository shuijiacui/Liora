import threading
import uuid
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from database import ReflectionDatabase, utc_now
from deepseek_client import DeepSeekClient, DeepSeekError
from knowledge_intelligence import (
    align_knowledge,
    build_knowledge_chunks,
    content_diff,
    content_fingerprint,
    granularity_candidates,
    knowledge_text,
    semantic_candidates,
)
from learning_intelligence import (
    PIPELINE_VERSION as LEARNING_PIPELINE_VERSION,
    component_state_label,
    diagnostic_value,
    discover_strict_relations,
    extract_grounded_structure,
    merge_ai_structure,
    update_component_state,
)
from knowledge_store import KnowledgeVault
from reflection_agent import START_PROMPT, follow_up, make_knowledge_draft
from semantic_embedding import SemanticEmbeddingEngine
from web_search import WebSearchClient, WebSearchError


WEB_SEARCH_HINTS = (
    "联网", "搜索", "查一下", "查证", "核实", "最新", "目前", "现在", "版本",
    "政策", "法规", "价格", "数据", "统计", "论文", "研究", "是否正确", "准确吗",
    "是不是", "不确定", "拿不准", "记不清",
)
EXPLICIT_WEB_HINTS = ("联网", "搜索", "查一下", "查证", "核实")
AUTO_APPLY_CREATE_CONFIDENCE = 0.85


class ReflectionService:
    def __init__(
        self,
        database: ReflectionDatabase,
        llm_client: DeepSeekClient | None = None,
        search_client: WebSearchClient | None = None,
        vault_path: Path | None = None,
        data_dir: Path | None = None,
        models_dir: Path | None = None,
        embedding_engine: SemanticEmbeddingEngine | None = None,
    ):
        self._database = database
        self._llm_client = llm_client
        self._search_client = search_client
        self._data_dir = Path(data_dir) if data_dir else Path.cwd()
        self._review_lock = threading.RLock()
        self._intelligence_lock = threading.RLock()
        self._embedding = embedding_engine or SemanticEmbeddingEngine(models_dir)
        self._vault: KnowledgeVault | None = None
        if vault_path:
            self.configure_vault(vault_path)

    def status(self) -> dict:
        configured = bool(self._llm_client and self._llm_client.configured)
        judge_limit = self._alignment_daily_limit()
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat(timespec="seconds")
        usage = self._database.ai_usage_since(today)
        input_limit, output_limit = self._ai_token_limits()
        return {
            "provider": "deepseek" if configured else "local",
            "model": self._llm_client.settings.model if configured else "local-reflection-agent",
            "configured": configured,
            "web_search": bool(self._search_client and self._search_client.configured),
            "storage": self.storage_status(),
            "embedding": self._embedding.status(),
            "alignment_judge": {
                "mode": str(os.getenv("LIORA_ALIGNMENT_JUDGE", "balanced")).strip().lower(),
                "daily_limit": judge_limit,
                "calls_today": self._database.count_alignment_judgments_since(today),
            },
            "learning_engine": {
                "pipeline_version": LEARNING_PIPELINE_VERSION,
                "mode": "grounded-deepseek" if configured else "strict-local-only",
                "input_token_limit": input_limit,
                "output_token_limit": output_limit,
                "usage_today": usage,
            },
        }

    @staticmethod
    def _alignment_daily_limit() -> int:
        try:
            value = int(os.getenv("LIORA_ALIGNMENT_DAILY_LIMIT", "20"))
        except ValueError:
            value = 20
        return min(max(value, 0), 100)

    @staticmethod
    def _ai_token_limits() -> tuple[int, int]:
        try:
            input_limit = int(os.getenv("LIORA_AI_DAILY_INPUT_TOKENS", "60000"))
        except ValueError:
            input_limit = 60000
        try:
            output_limit = int(os.getenv("LIORA_AI_DAILY_OUTPUT_TOKENS", "15000"))
        except ValueError:
            output_limit = 15000
        return min(max(input_limit, 0), 2_000_000), min(max(output_limit, 0), 500_000)

    def _ai_budget_available(self) -> bool:
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat(timespec="seconds")
        usage = self._database.ai_usage_since(today)
        input_limit, output_limit = self._ai_token_limits()
        return (
            input_limit > 0
            and output_limit > 0
            and int(usage.get("prompt_tokens") or 0) < input_limit
            and int(usage.get("completion_tokens") or 0) < output_limit
        )

    def _record_last_ai_usage(self, purpose: str) -> None:
        if not self._llm_client:
            return
        settings = getattr(self._llm_client, "settings", None)
        self._database.record_ai_usage(
            purpose,
            str(getattr(settings, "model", "configured-llm")),
            getattr(self._llm_client, "last_usage", {}) or {},
        )

    def configure_vault(self, vault_path: Path | str) -> dict:
        vault = KnowledgeVault(
            self._database,
            Path(vault_path),
            self._data_dir / "backups",
            self._data_dir / "knowledge-scope.json",
        )
        scan = vault.scan()
        self._vault = vault
        self.refresh_intelligence(scan_vault=False)
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

    def update_vault_scope(self, included_folders, excluded_folders) -> dict:
        if self._vault is None:
            raise ValueError("请先选择 Obsidian Vault。")
        result = self._vault.set_scope(included_folders, excluded_folders)
        self.refresh_intelligence(scan_vault=False)
        return {"storage": self._vault.status(), **result}

    def migrate_legacy_knowledge(self) -> dict:
        if self._vault is None:
            raise ValueError("请先选择 Obsidian Vault。")
        report = self._vault.migrate_legacy()
        return {"storage": self._vault.status(), "migration": report}

    def dashboard(self) -> dict:
        if self._vault:
            scan = self._vault.scan(allow_cached=True)
            return {
                **self._database.knowledge_dashboard(),
                "storage": self._vault.status(),
                "scan": scan,
            }

        items = self._database.list_all_knowledge()
        recent = [
            {
                "id": item["id"],
                "title": item["title"],
                "path": item.get("relative_path", ""),
                "updated_at": item["updated_at"],
                "summary": str(item.get("content", {}).get("core_insight") or "")[:240],
                "object_type": "knowledge",
            }
            for item in items[:5]
        ]
        questions = []
        for item in items:
            for question in item.get("content", {}).get("open_questions", []):
                value = str(question).strip()
                if value:
                    questions.append(
                        {
                            "knowledge_id": item["id"],
                            "title": item["title"],
                            "path": "",
                            "question": value,
                        }
                    )
                if len(questions) >= 5:
                    break
            if len(questions) >= 5:
                break
        return {
            "knowledge_count": len(items),
            "open_question_count": sum(
                len(item.get("content", {}).get("open_questions", [])) for item in items
            ),
            "recent": recent,
            "open_questions": questions,
            "health": self._database.knowledge_health([item["id"] for item in items]),
            "storage": self.storage_status(),
        }

    def reflection_prompts(self, limit: int = 8) -> dict:
        safe_limit = min(max(int(limit), 1), 20)
        if self._vault:
            self._vault.scan(allow_cached=True)
            documents = self._database.list_knowledge_documents(1000)
            candidates = self._database.knowledge_prompt_candidates(20)
        else:
            documents = self._database.list_all_knowledge()
            candidates = []
            for item in documents:
                context = str(item.get("content", {}).get("core_insight") or "").strip()[:240]
                for question in item.get("content", {}).get("open_questions", []):
                    prompt = str(question).strip()
                    if not prompt:
                        continue
                    candidates.append({
                        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"liora:knowledge-gap:{item['id']}:{prompt}")),
                        "kind": "open_question",
                        "knowledge_id": item["id"],
                        "title": item["title"],
                        "path": "",
                        "context": context,
                        "prompt": prompt,
                        "reason_code": "open_question",
                        "reason": f"这个问题来自《{item['title']}》的“尚待探索”。",
                        "priority": 0.72,
                    })

        by_id = {item["id"]: item for item in documents}
        for candidate in candidates:
            candidate["kind"] = "open_question"
            candidate["priority"] = max(float(candidate.get("priority") or 0), 0.72)
            candidate.setdefault("target_kc_ids", [])
            candidate.setdefault("rubric", {})

        for component in self._database.list_knowledge_components():
            document = by_id.get(component["knowledge_id"])
            if not document:
                continue
            state = component.get("state") or {}
            state_label = component_state_label(state)
            if state_label == "mastered" and float(state.get("transfer_level") or 0) >= 0.65:
                continue
            value = diagnostic_value(component, state, goal_relevance=0.6)
            if value < 0.58:
                continue
            prompt_kind = (
                "transfer_check"
                if float(state.get("mastery") or 0) >= 0.72
                and float(state.get("transfer_level") or 0) < 0.5
                else "diagnostic"
            )
            candidates.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"liora:{prompt_kind}:{component['id']}:{component['fingerprint']}")),
                "kind": prompt_kind,
                "knowledge_id": component["knowledge_id"],
                "title": document.get("title") or component["title"],
                "path": document.get("relative_path") or "",
                "context": str((document.get("content") or {}).get("core_insight") or "")[:240],
                "prompt": component["question"],
                "reason_code": "kc_uncertainty" if prompt_kind == "diagnostic" else "transfer_gap",
                "reason": (
                    f"Liora 还不能确定你是否掌握“{component['title']}”，用一个短问题确认。"
                    if prompt_kind == "diagnostic"
                    else f"“{component['title']}”的基础理解较稳定，现在检查能否迁移使用。"
                ),
                "target_kc_ids": [component["id"]],
                "rubric": {"evidence_claim_ids": component.get("claim_ids") or []},
                "priority": value,
                "learner_state": {
                    "label": state_label,
                    "mastery": float(state.get("mastery") or 0.35),
                    "uncertainty": float(state.get("uncertainty") or 0.75),
                    "transfer_level": float(state.get("transfer_level") or 0),
                },
            })

        scheduled = self._database.schedule_prompt_candidates(candidates, 20)
        scheduled.sort(key=lambda item: (-float(item.get("priority") or 0), item.get("title") or ""))
        selected = scheduled[:safe_limit]
        return {"items": selected, "total": len(selected), "source": "adaptive_review"}

    def _get_knowledge(self, knowledge_id: str) -> dict | None:
        if self._vault:
            return self._database.get_knowledge_document(knowledge_id)
        return self._database.get_knowledge(knowledge_id)

    def _find_prompt(self, prompt_id: str) -> dict:
        prompt_id = str(prompt_id or "").strip()
        if not prompt_id:
            raise ValueError("没有收到要复述的问题。")
        for prompt in self.reflection_prompts(20)["items"]:
            if prompt["id"] == prompt_id:
                return prompt
        raise LookupError("这个问题已经不在当前复述队列里了，请让 Liora 再翻翻。")

    def start_prompt(self, prompt_id: str) -> dict:
        with self._review_lock:
            prompt_id = str(prompt_id or "").strip()
            active = self._database.get_active_session("review")
            if active:
                if active.get("prompt_id") == prompt_id:
                    return self._payload(active["id"], resumed=True)
                has_user_content = any(
                    message["role"] == "user"
                    for message in self._database.get_messages(active["id"])
                )
                has_draft = self._database.get_knowledge_draft(active["id"]) is not None
                if has_user_content or has_draft:
                    raise ValueError(
                        "Liora正在听上一段回顾。请先在桌宠的“回顾”里完成，"
                        "或点“先放一放”。"
                    )
                # An assistant-only review contains no user contribution and can
                # safely yield to the newly selected Obsidian question.
                self._database.discard_session(active["id"])
            prompt = self._find_prompt(prompt_id)
            payload = self.start(
                force_new=True,
                knowledge_id=prompt["knowledge_id"],
                prompt=prompt,
                session_type="review",
            )
            self._database.mark_prompt_started(prompt["id"], prompt["knowledge_id"])
            self._database.record_recommendation_feedback(
                prompt["id"], "learning_prompt", "started", str(prompt.get("kind") or "")
            )
            payload["started_from_obsidian"] = True
            payload["prompt"] = prompt
            return payload

    def start_review(self) -> dict:
        with self._review_lock:
            active = self._database.get_active_session("review")
            if active:
                payload = self._payload(active["id"], resumed=True)
                draft = self._database.get_knowledge_draft(active["id"])
                if draft:
                    payload["awaiting_confirmation"] = True
                    payload["knowledge_draft"] = draft["content"]
                return payload
            prompts = self.reflection_prompts(1)["items"]
            if not prompts:
                return {
                    "available": False,
                    "reason": "no_due_prompt",
                    "message": "Liora暂时没有找到该回顾的小问题。",
                }
            return self.start_prompt(prompts[0]["id"])

    def defer_review(self, session_id: str, days: int = 3) -> dict:
        with self._review_lock:
            session = self._require_active_session(session_id)
            if session.get("session_type") != "review" or not session.get("prompt_id"):
                raise ValueError("只有知识回顾可以先放一放。")
            discarded = self._database.discard_session(session_id)
            snoozed = self._database.snooze_prompt(
                discarded["prompt_id"], discarded["knowledge_id"], days
            )
            return {"deferred": True, "session_id": session_id, **snoozed}

    def skip_prompt(self, prompt_id: str) -> dict:
        prompt = self._find_prompt(prompt_id)
        self._database.record_recommendation_feedback(
            prompt["id"], "learning_prompt", "skipped", str(prompt.get("kind") or "")
        )
        return {"skipped": True, **self._database.mark_prompt_skipped(
            prompt["id"], prompt["knowledge_id"]
        )}

    def snooze_prompt(self, prompt_id: str, days: int = 3) -> dict:
        prompt = self._find_prompt(prompt_id)
        self._database.record_recommendation_feedback(
            prompt["id"], "learning_prompt", "snoozed", f"{days} days; {prompt.get('kind') or ''}"
        )
        return {"snoozed": True, **self._database.snooze_prompt(
            prompt["id"], prompt["knowledge_id"], days
        )}

    def rate_reflection(
        self,
        session_id: str,
        rating: str,
        independent_recall: bool | None = None,
        hint_count: int | None = None,
        misconception_count: int | None = None,
        outcome: str | None = None,
        misconceptions: list[str] | None = None,
    ) -> dict:
        event = self._database.record_learning_event(
            session_id,
            rating,
            independent_recall,
            hint_count,
            misconception_count,
            outcome,
            misconceptions,
        )
        evidence_type = {
            "transfer_check": "transfer",
            "boundary_check": "boundary",
            "prerequisite_check": "prerequisite",
            "diagnostic": "diagnostic",
            "open_question": "exploration",
        }.get(str(event.get("prompt_kind") or ""), "recall")
        component_states = []
        for kc_id in event.get("target_kc_ids") or []:
            previous = self._database.get_kc_state(kc_id) or {}
            evidence = {
                "evidence_type": evidence_type,
                "outcome": event.get("outcome") or "unknown",
                "independent_recall": independent_recall,
                "hint_count": hint_count,
                "misconceptions": event.get("misconceptions") or [],
            }
            updated = update_component_state(previous, evidence)
            component_states.append(
                self._database.record_kc_evidence(kc_id, session_id, evidence, previous, updated)
            )
        self._database.record_recommendation_feedback(
            event.get("prompt_id") or session_id,
            "learning_prompt",
            f"completed_{event.get('outcome') or 'unknown'}",
            str(event.get("prompt_kind") or ""),
        )
        return {
            "recorded": True,
            "event": event,
            "knowledge_state": event["knowledge_state"],
            "component_states": component_states,
        }

    def start(
        self,
        force_new: bool = False,
        knowledge_id: str | None = None,
        prompt: dict | None = None,
        session_type: str = "reflection",
    ) -> dict:
        existing_knowledge = None
        if knowledge_id:
            if self._vault:
                self._vault.scan()
            existing_knowledge = self._get_knowledge(knowledge_id)
            if existing_knowledge is None:
                raise LookupError("没有找到要继续完善的知识记录。")
        session = (
            None
            if force_new or knowledge_id
            else self._database.get_active_session(session_type)
        )
        resumed = session is not None

        if session is None:
            session = self._database.create_session(
                knowledge_id=knowledge_id,
                prompt=prompt,
                session_type=session_type,
            )
            opening_prompt = (
                str(prompt.get("prompt"))
                if prompt
                else f"关于“{existing_knowledge['title']}”，你又有了什么新的感悟？"
                if existing_knowledge
                else START_PROMPT
            )
            self._database.add_message(session["id"], "assistant", opening_prompt)

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
        sources, search_notice = self._search_sources(content)
        if self._llm_client and self._llm_client.configured:
            try:
                assistant_message = (
                    self._llm_client.generate_follow_up(messages, len(user_messages), sources)
                    if sources
                    else self._llm_client.generate_follow_up(messages, len(user_messages))
                )
                provider = "deepseek"
            except DeepSeekError as error:
                print(f"LIORA_DEEPSEEK_FALLBACK {error}", flush=True)
                assistant_message = follow_up(content, len(user_messages))
                provider = "local-fallback"
                notice = "DeepSeek 暂时不可用，已使用本地反思策略继续。"
        else:
            assistant_message = follow_up(content, len(user_messages))
            provider = "local"
        if search_notice and any(word in content for word in EXPLICIT_WEB_HINTS):
            assistant_message = f"我目前没能联网查证。基于已有知识，{assistant_message}"
        notice = self._join_notices(notice, search_notice)
        self._database.add_message(session_id, "assistant", assistant_message)
        payload = self._payload(session_id, provider=provider, notice=notice)
        payload["web_sources"] = sources
        payload["web_used"] = bool(sources)
        return payload

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
        search_text = self._knowledge_search_text(user_messages)
        sources, search_notice = self._search_sources(search_text)
        if self._llm_client and self._llm_client.configured:
            try:
                draft_content = (
                    self._llm_client.organize_knowledge(messages, existing, sources)
                    if sources
                    else self._llm_client.organize_knowledge(messages, existing)
                )
                provider = "deepseek"
            except DeepSeekError as error:
                print(f"LIORA_DEEPSEEK_FALLBACK {error}", flush=True)
                draft_content = make_knowledge_draft(user_messages, existing)
                provider = "local-fallback"
                notice = "DeepSeek 暂时不可用，已使用本地方式整理。"
        else:
            draft_content = make_knowledge_draft(user_messages, existing)
            provider = "local"
        notice = self._join_notices(notice, search_notice)
        draft = self._database.save_knowledge_draft(
            session_id, draft_content, session.get("knowledge_id")
        )
        payload = self._payload(session_id, complete=False, provider=provider, notice=notice)
        payload["awaiting_confirmation"] = True
        payload["knowledge_draft"] = draft["content"]
        payload["web_used"] = bool(sources)
        return payload

    def update_draft(self, session_id: str, content: dict) -> dict:
        session = self._require_active_session(session_id)
        existing_draft = self._database.get_knowledge_draft(session_id)
        if existing_draft is None:
            raise LookupError("没有找到待修改的知识草稿。")
        try:
            normalized = DeepSeekClient.normalize_knowledge(content)
        except DeepSeekError as error:
            raise ValueError(str(error)) from error
        draft = self._database.save_knowledge_draft(
            session_id,
            normalized,
            existing_draft.get("knowledge_id") or session.get("knowledge_id"),
        )
        payload = self._payload(session_id, complete=False)
        payload["awaiting_confirmation"] = True
        payload["knowledge_draft"] = draft["content"]
        return payload

    def revise_draft(self, session_id: str, instruction: str, content: dict | None = None) -> dict:
        session = self._require_active_session(session_id)
        instruction = " ".join(str(instruction or "").split()).strip()
        if not instruction:
            raise ValueError("请先写下希望 Liora 如何修改。")
        if len(instruction) > 1200:
            raise ValueError("修改意见请控制在 1200 字以内。")
        stored = self._database.get_knowledge_draft(session_id)
        if stored is None:
            raise LookupError("没有找到待修改的知识草稿。")
        if not self._llm_client or not self._llm_client.configured:
            raise ValueError("请先配置 DeepSeek，才能让 Liora 按意见修改。")
        try:
            current = DeepSeekClient.normalize_knowledge(content or stored["content"])
        except DeepSeekError as error:
            raise ValueError(str(error)) from error

        sources, search_notice = self._search_sources(f"{current['title']} {instruction}")
        messages = self._database.get_messages(session_id)
        try:
            revised = self._llm_client.revise_knowledge(messages, current, instruction, sources)
        except DeepSeekError as error:
            raise ValueError(f"暂时无法按意见修改：{error}") from error
        draft = self._database.save_knowledge_draft(
            session_id,
            revised,
            stored.get("knowledge_id") or session.get("knowledge_id"),
        )
        payload = self._payload(session_id, complete=False, provider="deepseek", notice=search_notice)
        payload["awaiting_confirmation"] = True
        payload["knowledge_draft"] = draft["content"]
        payload["web_used"] = bool(sources)
        return payload

    def confirm(self, session_id: str) -> dict:
        session = self._require_active_session(session_id)
        if self._vault:
            draft = self._database.get_knowledge_draft(session_id)
            if draft is None:
                raise LookupError("没有找到待确认的知识整理结果。")
            self._vault.scan()
            documents = self._database.list_knowledge_documents(1000)
            explicit_target = draft.get("knowledge_id") or session.get("knowledge_id")
            if self._embedding.available:
                self.refresh_intelligence(scan_vault=False)
                stored_embeddings = self._database.list_embeddings()
                documents = [
                    {
                        **item,
                        "embedding": (stored_embeddings.get(item["id"]) or {}).get("vector", []),
                    }
                    for item in documents
                ]
            semantic_model = self._embedding.using_semantic_model
            alignment = align_knowledge(
                draft["content"],
                documents,
                explicit_target,
                document_embedder=self._embedding.embed_document,
                semantic_model=semantic_model,
            )
            alignment = self._judge_ambiguous_alignment(
                draft["content"], alignment, documents, explicit_target
            )
            existing = self._get_knowledge(alignment.get("target_id"))
            content = self._merge_knowledge_content(existing, draft["content"])
            knowledge_id = existing["id"] if existing else str(uuid.uuid4())
            target_path = existing.get("relative_path") if existing else None
            before_markdown = self._vault.read_markdown(target_path) if target_path else None
            top_score = (
                alignment["candidates"][0]["score"] if alignment.get("candidates") else 0
            )
            thresholds = alignment.get("thresholds") or {}
            related_threshold = float(thresholds.get("related") or 0.42)
            ambiguous = (
                not explicit_target
                and (
                    (alignment["action"] == "create" and top_score >= related_threshold)
                    or (
                        alignment["action"] == "update"
                        and alignment.get("decision_basis") == "semantic"
                    )
                )
            )
            risk = (
                "review"
                if self._alignment_requires_review(alignment, explicit_target, ambiguous)
                else "low"
            )
            changeset = self._database.create_changeset(
                {
                    "session_id": session_id,
                    "action": alignment["action"],
                    "target_id": knowledge_id,
                    "target_path": target_path,
                    "status": "pending",
                    "risk": risk,
                    "title": content["title"],
                    "reason": alignment["reason"],
                    "alignment": alignment,
                    "before": existing.get("content") if existing else None,
                    "after": content,
                    "diff": content_diff(existing.get("content") if existing else None, content),
                    "before_markdown": before_markdown,
                }
            )
            if risk == "low":
                changeset = self.apply_changeset(changeset["id"], complete_session=False)
                knowledge = changeset["result"]["knowledge"]
            else:
                knowledge = {
                    "id": knowledge_id,
                    "title": content["title"],
                    "content": content,
                    "pending": True,
                }
            self._database.complete_session_after_changeset(
                session_id,
                knowledge_id,
                content["core_insight"],
            )
        else:
            knowledge = self._database.confirm_knowledge_draft(session_id)
        payload = self._payload(session_id, complete=True)
        payload["knowledge"] = knowledge
        if self._vault:
            payload["changeset"] = changeset
            payload["review_required"] = changeset["status"] == "pending"
        return payload

    @staticmethod
    def _alignment_requires_review(
        alignment: dict,
        explicit_target: str | None,
        locally_ambiguous: bool,
    ) -> bool:
        if explicit_target or alignment.get("decision_basis") == "exact_title":
            return False

        adjudication = alignment.get("adjudication")
        if not isinstance(adjudication, dict):
            return locally_ambiguous

        try:
            confidence = float(adjudication.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        conflicts = adjudication.get("conflicts")
        has_conflicts = isinstance(conflicts, list) and bool(conflicts)
        is_plain_create = (
            alignment.get("action") == "create"
            and adjudication.get("decision") == "CREATE"
            and not alignment.get("parent_id")
            and not alignment.get("related_target_id")
        )
        confident_independent_create = (
            is_plain_create
            and confidence >= AUTO_APPLY_CREATE_CONFIDENCE
            and not adjudication.get("needs_human_review", True)
            and not has_conflicts
        )
        return not confident_independent_create

    @staticmethod
    def _merge_knowledge_content(existing: dict | None, draft: dict) -> dict:
        if not existing:
            return draft
        before = existing.get("content") or {}
        merged = {**before, **draft}
        for key in (
            "key_points", "logic_chain", "examples", "extensions", "boundaries",
            "connections", "open_questions", "sources",
        ):
            values = []
            seen = set()
            for item in [*(before.get(key) or []), *(draft.get(key) or [])]:
                identity = str(item).casefold().strip()
                if identity and identity not in seen:
                    seen.add(identity)
                    values.append(item)
            merged[key] = values[:8]
        return merged

    def _judge_ambiguous_alignment(
        self,
        draft: dict,
        alignment: dict,
        documents: list[dict],
        explicit_target: str | None,
    ) -> dict:
        mode = str(os.getenv("LIORA_ALIGNMENT_JUDGE", "balanced")).strip().lower()
        if mode in {"off", "local", "disabled", "0", "false"}:
            return alignment
        if explicit_target or alignment.get("decision_basis") == "exact_title":
            return alignment
        candidates = alignment.get("candidates") or []
        if not candidates or not self._llm_client or not self._llm_client.configured:
            return alignment
        thresholds = alignment.get("thresholds") or {}
        related_threshold = float(thresholds.get("related") or 0.42)
        top_score = float(candidates[0].get("score") or 0)
        second_score = float(candidates[1].get("score") or 0) if len(candidates) > 1 else 0
        ambiguous = (
            top_score >= related_threshold
            or (top_score >= max(related_threshold - 0.05, 0) and top_score - second_score < 0.04)
        )
        if not ambiguous:
            return alignment

        by_id = {item["id"]: item for item in documents}
        enriched = []
        for candidate in candidates[:3]:
            item = by_id.get(candidate.get("knowledge_id")) or {}
            content = item.get("content") or {}
            enriched.append(
                {
                    **candidate,
                    "core_insight": content.get("core_insight") or candidate.get("snippet") or "",
                    "key_points": content.get("key_points") or [],
                }
            )
        signature_data = {
            "draft": content_fingerprint(draft),
            "candidates": [
                [item.get("knowledge_id"), item.get("score"), by_id.get(item.get("knowledge_id"), {}).get("version")]
                for item in enriched
            ],
            "model": self._llm_client.settings.model,
            "schema": 1,
        }
        signature = hashlib.sha256(
            json.dumps(signature_data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        cached = self._database.get_alignment_judgment(signature)
        if not cached:
            today = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat(timespec="seconds")
            limit = self._alignment_daily_limit()
            used = self._database.count_alignment_judgments_since(today)
            if limit == 0 or used >= limit:
                return {
                    **alignment,
                    "adjudication_error": "DeepSeek 知识对齐今日调用上限已到，已保留本地建议并等待人工审核。",
                    "adjudication_provider": "daily-limit-local-kept",
                }
        try:
            judgment = cached or self._llm_client.judge_alignment(draft, enriched)
            if not cached:
                self._database.save_alignment_judgment(
                    signature, self._llm_client.settings.model, judgment
                )
        except DeepSeekError as error:
            return {
                **alignment,
                "adjudication_error": str(error),
                "adjudication_provider": "deepseek-failed-local-kept",
            }

        decision = judgment["decision"]
        target_id = judgment.get("target_id")
        resolved = {**alignment}
        resolved["local_decision"] = {
            "action": alignment.get("action"),
            "decision_basis": alignment.get("decision_basis"),
            "target_id": alignment.get("target_id"),
            "reason": alignment.get("reason"),
        }
        resolved["adjudication"] = {
            **judgment,
            "provider": "deepseek-cache" if cached else "deepseek",
            "signature": signature,
        }
        resolved["reason"] = judgment.get("reason") or alignment.get("reason")
        resolved["confidence"] = judgment.get("confidence", alignment.get("confidence"))
        resolved["decision_basis"] = "deepseek_adjudication"
        if decision == "UPDATE":
            target = by_id.get(target_id)
            if target:
                resolved["action"] = "update"
                resolved["target_id"] = target_id
                resolved["target_title"] = target.get("title")
        else:
            resolved["action"] = "create"
            resolved["target_id"] = None
            resolved["target_title"] = None
            if decision == "CHILD":
                resolved["parent_id"] = target_id
            if decision == "RELATED":
                resolved["related_target_id"] = target_id
        return resolved

    def changesets(self, status: str = "pending", limit: int = 30) -> dict:
        items = self._database.list_changesets(status, limit)
        return {"items": items, "total": len(items)}

    def apply_changeset(self, changeset_id: str, complete_session: bool = True) -> dict:
        if not self._vault:
            raise ValueError("请先连接 Obsidian Vault。")
        changeset = self._database.get_changeset(changeset_id)
        if not changeset:
            raise LookupError("没有找到这条知识变更。")
        if changeset["status"] == "applied":
            return changeset
        if changeset["status"] != "pending":
            raise ValueError("这条知识变更已经处理过了。")
        existing = self._get_knowledge(changeset.get("target_id"))
        now = utc_now()
        proposed = {
            "id": changeset["target_id"] or str(uuid.uuid4()),
            "title": changeset["after"]["title"],
            "created_at": existing["created_at"] if existing else now,
            "updated_at": now,
            "version": int(existing.get("version") or 0) + 1 if existing else 1,
            "content": changeset["after"],
        }
        knowledge = self._vault.write(proposed)
        alignment = changeset.get("alignment") or {}
        adjudication = alignment.get("adjudication") or {}
        if alignment.get("parent_id"):
            self._database.add_hierarchy(
                alignment["parent_id"], knowledge["id"], "deepseek_alignment"
            )
        if alignment.get("related_target_id"):
            self._database.replace_discovered_relations(
                [
                    {
                        "source_id": knowledge["id"],
                        "target_id": alignment["related_target_id"],
                        "kind": "soft",
                        "label": "deepseek_related",
                        "confidence": float(adjudication.get("confidence") or 0.5),
                        "reason": adjudication.get("reason")
                        or "Liora 在知识对齐审核中确认了这两条知识的关系。",
                        "status": "confirmed",
                    }
                ]
            )
        resolved = self._database.resolve_changeset(
            changeset_id, "applied", {"knowledge": knowledge}
        )
        if complete_session and changeset.get("session_id"):
            session = self._database.get_session(changeset["session_id"])
            if session and session["status"] == "active":
                self._database.complete_session_after_changeset(
                    session["id"], knowledge["id"], changeset["after"].get("core_insight", "")
                )
        self.refresh_intelligence(scan_vault=False)
        return resolved

    def reject_changeset(self, changeset_id: str) -> dict:
        changeset = self._database.get_changeset(changeset_id)
        if not changeset:
            raise LookupError("没有找到这条知识变更。")
        if changeset["status"] != "pending":
            raise ValueError("这条知识变更已经处理过了。")
        return self._database.resolve_changeset(changeset_id, "rejected")

    def rollback_changeset(self, changeset_id: str) -> dict:
        if not self._vault:
            raise ValueError("请先连接 Obsidian Vault。")
        changeset = self._database.get_changeset(changeset_id)
        if not changeset:
            raise LookupError("没有找到这条知识变更。")
        if changeset["status"] != "applied":
            raise ValueError("只有已经应用的变更可以回滚。")
        result = changeset.get("result") or {}
        knowledge = result.get("knowledge") or {}
        relative_path = knowledge.get("relative_path") or changeset.get("target_path")
        if not relative_path:
            raise ValueError("这条变更缺少可回滚的文件路径。")
        if changeset.get("before_markdown") is not None:
            self._vault.restore_markdown(relative_path, changeset["before_markdown"])
        else:
            self._vault.delete_created(relative_path)
            if knowledge.get("id") or changeset.get("target_id"):
                self._database.remove_knowledge_intelligence(
                    knowledge.get("id") or changeset["target_id"]
                )
        resolved = self._database.resolve_changeset(changeset_id, "rolled_back")
        self.refresh_intelligence(scan_vault=False)
        return resolved

    def refresh_intelligence(self, scan_vault: bool = True) -> dict:
        with self._intelligence_lock:
            return self._refresh_intelligence_locked(scan_vault)

    def _refresh_intelligence_locked(self, scan_vault: bool = True) -> dict:
        if self._vault and scan_vault:
            self._vault.scan(allow_cached=True)
        documents = (
            self._database.list_knowledge_documents(1000)
            if self._vault
            else self._database.list_all_knowledge()
        )
        self._embedding.prepare()
        cached = self._database.list_embeddings()
        enriched = []
        embedding_model = self._embedding.model_name
        changed = []
        for item in documents:
            fingerprint = content_fingerprint(item.get("content") or {}, item.get("title") or "")
            stored = cached.get(item["id"])
            if (
                stored
                and stored["fingerprint"] == fingerprint
                and stored.get("model") == embedding_model
            ):
                enriched.append({**item, "embedding": stored["vector"]})
            else:
                changed.append((item, fingerprint))
        if changed:
            vectors = self._embedding.embed_documents(
                [knowledge_text(item.get("content") or {}, item.get("title") or "") for item, _ in changed]
            )
            embedding_model = self._embedding.model_name
            for (item, fingerprint), vector in zip(changed, vectors):
                self._database.upsert_embedding(
                    item["id"], fingerprint, vector, model=embedding_model
                )
                enriched.append({**item, "embedding": vector})
        semantic_model = self._embedding.using_semantic_model

        cached_chunks = self._database.list_knowledge_chunks()
        all_chunks = []
        changed_chunks = []
        for item in enriched:
            for chunk in build_knowledge_chunks(item.get("content") or {}, item["id"]):
                stored = cached_chunks.get(chunk["id"])
                if (
                    stored
                    and stored.get("fingerprint") == chunk["fingerprint"]
                    and stored.get("model") == embedding_model
                ):
                    all_chunks.append({**chunk, "embedding": stored["embedding"]})
                else:
                    changed_chunks.append(chunk)
        if changed_chunks:
            chunk_vectors = self._embedding.embed_documents(
                [item["text"] for item in changed_chunks]
            )
            all_chunks.extend(
                {**item, "embedding": vector}
                for item, vector in zip(changed_chunks, chunk_vectors)
            )
        self._database.replace_knowledge_chunks(all_chunks, embedding_model)
        chunks_by_knowledge: dict[str, list[dict]] = {}
        for chunk in all_chunks:
            chunks_by_knowledge.setdefault(chunk["knowledge_id"], []).append(chunk)

        structure_cache = self._database.list_cognitive_profiles()
        configured_llm = bool(self._llm_client and self._llm_client.configured)
        structure_model = (
            f"deepseek:{self._llm_client.settings.model}:grounded-claims-v1"
            if configured_llm
            else "local-grounded-rules-v1"
        )
        structured = []
        deep_structures = 0
        for item in enriched:
            fingerprint = content_fingerprint(item.get("content") or {}, item.get("title") or "")
            stored = structure_cache.get(item["id"])
            stored_structure = (stored or {}).get("profile") or {}
            cache_valid = bool(
                stored
                and stored.get("fingerprint") == fingerprint
                and stored_structure.get("pipeline_version") == LEARNING_PIPELINE_VERSION
            )
            if cache_valid:
                structure = stored_structure
            else:
                structure = extract_grounded_structure(
                    item.get("content") or {}, item["id"], item.get("title") or ""
                )
                used_model = "local-grounded-rules-v1"
                if (
                    configured_llm
                    and chunks_by_knowledge.get(item["id"])
                    and self._ai_budget_available()
                    and hasattr(self._llm_client, "analyze_learning_structure")
                ):
                    try:
                        ai_structure = self._llm_client.analyze_learning_structure(
                            item.get("title") or "",
                            chunks_by_knowledge.get(item["id"], []),
                        )
                        self._record_last_ai_usage("grounded-structure")
                        structure = merge_ai_structure(
                            structure,
                            ai_structure,
                            chunks_by_knowledge.get(item["id"], []),
                            item["id"],
                        )
                        used_model = structure_model
                        deep_structures += 1
                    except DeepSeekError:
                        pass
                structure["pipeline_version"] = LEARNING_PIPELINE_VERSION
                self._database.upsert_cognitive_profile(
                    item["id"], fingerprint, used_model, structure
                )
            self._database.replace_grounded_structure(
                item["id"], structure.get("claims") or [], structure.get("components") or []
            )
            structured.append({
                **item,
                "chunks": chunks_by_knowledge.get(item["id"], []),
                "claims": structure.get("claims") or [],
                "components": structure.get("components") or [],
            })

        relations = discover_strict_relations(structured)
        pending = [item for item in relations if item.get("status") == "candidate"][:3]
        if (
            pending
            and configured_llm
            and self._ai_budget_available()
            and hasattr(self._llm_client, "verify_learning_paths")
        ):
            signature = hashlib.sha256(
                json.dumps(pending, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            cached_decisions = self._database.get_alignment_judgment(f"path:{signature}")
            try:
                decisions = cached_decisions or self._llm_client.verify_learning_paths(pending)
                if not cached_decisions:
                    self._record_last_ai_usage("path-verification")
                    self._database.save_alignment_judgment(
                        f"path:{signature}", self._llm_client.settings.model, decisions
                    )
                verified = []
                for relation in relations:
                    if relation.get("status") != "candidate":
                        verified.append(relation)
                        continue
                    key = str((relation.get("features") or {}).get("canonical_key") or "")
                    decision = decisions.get(key) if isinstance(decisions, dict) else None
                    if not decision or decision.get("decision") != "PASS":
                        continue
                    evidence = relation.get("evidence") or {}
                    evidence["verification"] = "deepseek-cache" if cached_decisions else "deepseek"
                    evidence["verifier_reason"] = decision.get("reason") or ""
                    if decision.get("learning_payoff"):
                        evidence["learning_payoff"] = decision["learning_payoff"]
                        relation["reason"] = decision["learning_payoff"]
                    if decision.get("failure_conditions"):
                        evidence["failure_conditions"] = decision["failure_conditions"]
                    relation["evidence"] = evidence
                    verified.append(relation)
                relations = verified
            except DeepSeekError:
                # Deterministic-strict paths remain eligible; no regex or broad
                # cognitive fallback is introduced when the verifier is down.
                pass
        self._database.replace_discovered_relations(relations)
        granular = granularity_candidates(
            structured,
            relations,
            document_embedder=self._embedding.embed_document,
            semantic_model=semantic_model,
        )
        self._database.replace_granularity_candidates(granular)
        return {
            "knowledge_count": len(documents),
            "embedding_count": len(enriched),
            "chunk_count": len(all_chunks),
            "knowledge_component_count": sum(len(item.get("components") or []) for item in structured),
            "grounded_claim_count": sum(len(item.get("claims") or []) for item in structured),
            "deep_structures_created": deep_structures,
            "relation_count": len(relations),
            "granularity_candidate_count": len(granular),
            "embedding": self._embedding.status(),
        }

    def semantic_search(self, query: str, limit: int = 10) -> dict:
        query = " ".join(str(query or "").split()).strip()
        if not query:
            raise ValueError("请先输入要检索的内容。")
        self.refresh_intelligence()
        documents = self._database.list_knowledge_documents(1000) if self._vault else self._database.list_all_knowledge()
        embeddings = self._database.list_embeddings()
        items = [
            {**item, "embedding": (embeddings.get(item["id"]) or {}).get("vector", [])}
            for item in documents
        ]
        matches = semantic_candidates(
            query,
            items,
            limit,
            query_embedder=self._embedding.embed_query,
            document_embedder=self._embedding.embed_document,
            semantic_model=self._embedding.using_semantic_model,
        )
        return {
            "query": query,
            "items": matches,
            "total": len(matches),
            "embedding": self._embedding.status(),
        }

    def knowledge_answer(self, question: str) -> dict:
        question = " ".join(str(question or "").split()).strip()
        if not question:
            raise ValueError("请先告诉 Liora 你想问什么。")
        self.refresh_intelligence()
        documents = self._database.list_knowledge_documents(1000) if self._vault else self._database.list_all_knowledge()
        embeddings = self._database.list_embeddings()
        items = [
            {**item, "embedding": (embeddings.get(item["id"]) or {}).get("vector", [])}
            for item in documents
        ]
        candidates = semantic_candidates(
            question,
            items,
            5,
            query_embedder=self._embedding.embed_query,
            document_embedder=self._embedding.embed_document,
            semantic_model=self._embedding.using_semantic_model,
        )
        by_id = {item["id"]: item for item in items}
        evidence = []
        for candidate in candidates[:3]:
            item = by_id[candidate["knowledge_id"]]
            excerpt = str((item.get("content") or {}).get("core_insight") or "").strip()
            if excerpt:
                evidence.append({**candidate, "excerpt": excerpt[:500]})
        minimum = 0.28 if self._embedding.using_semantic_model else 0.12
        answer = (
            "Liora 暂时没有在当前知识库里找到足够相关的依据。"
            if not evidence or evidence[0]["score"] < minimum
            else "\n\n".join(f"《{item['title']}》：{item['excerpt']}" for item in evidence)
        )
        return {
            "question": question,
            "answer": answer,
            "evidence": evidence,
            "provider": "local",
            "embedding": self._embedding.status(),
        }

    def relations(self, status: str = "", limit: int = 100) -> dict:
        self.refresh_intelligence()
        documents = {
            item["id"]: item
            for item in (self._database.list_knowledge_documents(1000) if self._vault else self._database.list_all_knowledge())
        }
        items = [
            item
            for item in self._database.list_relations(status, 300)
            if item["source_id"] in documents and item["target_id"] in documents
        ][:min(max(int(limit), 1), 300)]
        for item in items:
            direction = (item.get("features") or {}).get("direction") or [item["source_id"], item["target_id"]]
            source_id, target_id = direction[:2] if len(direction) >= 2 else (item["source_id"], item["target_id"])
            item["source"] = {key: documents.get(source_id, {}).get(key) for key in ("id", "title", "relative_path")}
            item["target"] = {key: documents.get(target_id, {}).get(key) for key in ("id", "title", "relative_path")}
        return {"items": items, "total": len(items)}

    def update_relation(
        self, relation_id: str, status: str, reason_code: str = ""
    ) -> dict:
        documents = {
            item["id"]: item
            for item in (
                self._database.list_knowledge_documents(1000)
                if self._vault
                else self._database.list_all_knowledge()
            )
        }
        relation = next(
            (item for item in self._database.list_relations("", 300) if item["id"] == relation_id),
            None,
        )
        if not relation:
            raise LookupError("没有找到这条知识关系。")
        direction = (relation.get("features") or {}).get("direction") or [relation["source_id"], relation["target_id"]]
        source_id, target_id = direction[:2] if len(direction) >= 2 else (relation["source_id"], relation["target_id"])
        source = documents.get(source_id) or {}
        target = documents.get(target_id) or {}
        snapshot_keys = ("id", "title", "relative_path")
        return self._database.resolve_relation(
            relation_id,
            status,
            reason_code,
            {key: source.get(key) for key in snapshot_keys},
            {key: target.get(key) for key in snapshot_keys},
        )

    def relation_decisions(self, limit: int = 100) -> dict:
        items = self._database.list_relation_decisions(limit)
        return {"items": items, "total": len(items)}

    def granularity(self, status: str = "candidate", limit: int = 40) -> dict:
        self.refresh_intelligence()
        documents = {
            item["id"]: item
            for item in (self._database.list_knowledge_documents(1000) if self._vault else self._database.list_all_knowledge())
        }
        items = [
            item
            for item in self._database.list_granularity_candidates(status, 100)
            if item["source_ids"] and all(source_id in documents for source_id in item["source_ids"])
        ][:min(max(int(limit), 1), 100)]
        for item in items:
            item["sources"] = [
                {
                    "id": source_id,
                    "title": documents.get(source_id, {}).get("title") or "未知知识",
                    "path": documents.get(source_id, {}).get("relative_path") or "",
                }
                for source_id in item["source_ids"]
            ]
        hierarchy = [
            edge for edge in self._database.list_hierarchy()
            if edge["parent_id"] in documents and edge["child_id"] in documents
        ]
        for edge in hierarchy:
            edge["parent"] = {
                "id": edge["parent_id"],
                "title": documents.get(edge["parent_id"], {}).get("title") or "未知知识",
                "path": documents.get(edge["parent_id"], {}).get("relative_path") or "",
            }
            edge["child"] = {
                "id": edge["child_id"],
                "title": documents.get(edge["child_id"], {}).get("title") or "未知知识",
                "path": documents.get(edge["child_id"], {}).get("relative_path") or "",
            }
        return {"items": items, "total": len(items), "hierarchy": hierarchy}

    def reject_granularity(self, candidate_id: str) -> dict:
        return self._database.set_granularity_status(candidate_id, "rejected")

    def apply_granularity(self, candidate_id: str) -> dict:
        if not self._vault:
            raise ValueError("请先连接 Obsidian Vault。")
        candidate = next(
            (
                item
                for item in self._database.list_granularity_candidates("candidate", 100)
                if item["id"] == candidate_id
            ),
            None,
        )
        if not candidate:
            raise LookupError("没有找到这条待确认的粒度建议。")
        if candidate["kind"] == "merge":
            # A merge approval records the structural decision without deleting
            # either source. Destructive consolidation remains a future step.
            return self._database.set_granularity_status(candidate_id, "confirmed")
        parent_id = candidate["source_ids"][0]
        parent = self._get_knowledge(parent_id)
        if not parent:
            raise LookupError("没有找到要拆分的上位知识。")
        created = []
        for child in candidate["proposal"].get("children", [])[:4]:
            title = str(child.get("title") or "").strip()[:80]
            seed = str(child.get("seed") or "").strip()
            if not title or not seed:
                continue
            child_id = str(
                uuid.uuid5(uuid.NAMESPACE_URL, f"liora:child:{parent_id}:{title.casefold()}")
            )
            existing = self._get_knowledge(child_id)
            now = utc_now()
            planned_content = child.get("content") if isinstance(child.get("content"), dict) else {}
            proposed = {
                "id": child_id,
                "title": title,
                "created_at": existing["created_at"] if existing else now,
                "updated_at": now,
                "version": int(existing.get("version") or 0) + 1 if existing else 1,
                "content": {
                    "title": title,
                    "core_insight": str(planned_content.get("core_insight") or seed),
                    "key_points": list(planned_content.get("key_points") or [seed]),
                    "logic_chain": list(planned_content.get("logic_chain") or []),
                    "examples": list(planned_content.get("examples") or []),
                    "extensions": list(planned_content.get("extensions") or []),
                    "boundaries": list(planned_content.get("boundaries") or []),
                    "connections": list(planned_content.get("connections") or [f"上位知识：{parent['title']}"]),
                    "open_questions": list(planned_content.get("open_questions") or []),
                    "next_step": str(planned_content.get("next_step") or "继续通过复述补全这个子知识。"),
                    "sources": list(planned_content.get("sources") or []),
                },
            }
            knowledge = self._vault.write(proposed)
            self._database.add_hierarchy(parent_id, knowledge["id"], "split")
            created.append(knowledge)
        resolved = self._database.set_granularity_status(candidate_id, "applied")
        self.refresh_intelligence(scan_vault=False)
        return {**resolved, "created": created, "parent": parent}

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
                        *item.get("content", {}).get("key_points", []),
                        *item.get("content", {}).get("logic_chain", []),
                        *item.get("content", {}).get("examples", []),
                        *item.get("content", {}).get("extensions", []),
                        *item.get("content", {}).get("boundaries", []),
                        *item.get("content", {}).get("connections", []),
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

    def _search_sources(self, text: str) -> tuple[list[dict], str | None]:
        value = " ".join(str(text or "").split()).strip()
        if not value or not any(word in value for word in WEB_SEARCH_HINTS):
            return [], None
        if not self._search_client or not self._search_client.configured:
            if any(word in value for word in EXPLICIT_WEB_HINTS):
                return [], "联网查证尚未配置，已使用模型已有知识继续。"
            return [], None
        try:
            return self._search_client.search(value[:500]), None
        except WebSearchError as error:
            return [], f"联网查证暂时不可用：{error}"

    @staticmethod
    def _knowledge_search_text(user_messages: list[str]) -> str:
        relevant = [
            message for message in user_messages
            if any(word in message for word in WEB_SEARCH_HINTS)
        ]
        return (relevant[-1] if relevant else "").strip()

    @staticmethod
    def _join_notices(first: str | None, second: str | None) -> str | None:
        values = [value for value in (first, second) if value]
        return "；".join(values) if values else None

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
