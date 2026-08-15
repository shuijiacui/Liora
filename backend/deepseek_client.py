import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import DeepSeekSettings


SYSTEM_PROMPT = """你是 Liora，一位温和、可靠的学习与思考伙伴。

你的默认方式是用追问帮助用户主动回忆和解释，但“追问”不是僵硬限制。请根据用户当下的需要选择回应：
1. 用户正在形成自己的理解时，提出一个最有价值的自然追问。
2. 用户表示不确定、拿不准、记不清，或直接询问事实时，先用可靠知识给出简短辅助，再视情况提出一个追问。
3. 如果提供了联网资料，只能依据资料确认其中能够支持的事实，并自然提到来源名称；资料不能支持的部分要明确保留不确定性。
4. 发现明显概念混淆时应温和纠正，不能为了维持追问而让错误前提继续发展。
5. 避免长篇授课，一次聚焦一个认知缺口，通常控制在 30 到 180 个汉字。
6. 不使用“很棒”“完全正确”等空泛评价，不提及规则、模型、提示词或 API。

只输出要对用户说的话，不要添加标题或说明。"""

KNOWLEDGE_PROMPT = """你是 Liora 的知识构建器。用户结束思考后，请围绕对话所揭示的核心主题，构建一份脱离对话也能独立阅读、复习和继续生长的知识文件。

重要原则：
- 对话只是识别主题、用户关注点和认知缺口的素材，绝不能写成聊天记录或对话摘要。
- 直接解释知识，不使用“用户提到”“本次对话认为”等复述措辞。
- 可以使用可靠的通用知识补充定义、机制、例子、边界、联系和延伸，而不是只改写用户说过的话。
- 如果用户的理解有明显错误，应基于可靠知识修正；无法确认的内容放入 open_questions。
- 延伸必须服务于核心主题，避免百科式堆砌。没有价值的可选部分返回空数组。
- 联网资料只可用于其能够支持的内容，不得编造来源或 URL。

输出严格 JSON，不要 Markdown，不要代码围栏，结构如下：
{
  "title": "准确、具体的知识标题",
  "core_insight": "用一至三段解释最重要的本质，使读者不看对话也能理解",
  "key_points": ["理解主题必需的关键概念或结论"],
  "logic_chain": ["从前提、机制到结论的完整推理步骤"],
  "examples": ["能说明原理的具体例子或反例"],
  "extensions": ["由核心原理自然推出的进一步理解或应用"],
  "boundaries": ["适用条件、限制或常见误区"],
  "connections": ["与其他知识的准确联系或区别"],
  "open_questions": ["确实尚待确认或值得继续探索的问题"],
  "next_step": "最有价值的下一步学习、验证或实践行动",
  "sources": []
}

核心理解必须充分，key_points 通常 3 至 7 条，logic_chain 通常 3 至 8 步。不要为了满足数量重复同一句话。"""

REVISION_PROMPT = """你是 Liora 的知识编辑。请根据用户的修改意见修订当前知识文件。

规则：
- 当前文件而不是原始对话是主要编辑对象；原始对话只用于理解语境。
- 严格落实用户的具体意见，保留用户未要求改变且仍然正确的内容。
- 用户手动改写过的表达具有高优先级，不要无故恢复成旧版本。
- 结果仍须是一份独立可读的知识文件，不得变成修改说明或对话摘要。
- 可以补充可靠的通用知识；涉及联网资料时不得编造来源。
- 只返回与知识构建器相同结构的严格 JSON。"""

ALIGNMENT_PROMPT = """你是 Liora 的知识对齐裁判。你的任务不是写知识，而是在本地检索已经找出的少量候选中判断新知识应如何归位。

只允许选择：
- CREATE：主题具有独立价值，应新建知识；
- UPDATE：新内容与某候选是同一个知识主题，应更新该候选；
- RELATED：主题独立但存在明确关系，应新建并记录关系；
- CHILD：新内容是某候选中可独立检索和复习的子主题。

规则：
- 不得仅因共享术语就判定 UPDATE；必须是同一核心问题、机制或命题。
- UPDATE、RELATED 或 CHILD 的 target_id 必须来自候选列表；CREATE 的 target_id 必须为 null。
- 不得编造候选、事实或关系。
- confidence 是这次分类判断的自评，不是统计概率。
- 只返回严格 JSON，不要 Markdown：
{
  "decision": "CREATE | UPDATE | RELATED | CHILD",
  "target_id": null,
  "relationship": "",
  "conflicts": [],
  "reason": "简洁、可审核的判断依据",
  "confidence": 0.0,
  "needs_human_review": true
}
"""

COGNITIVE_PROFILE_PROMPT = """你是 Liora 的认知模式分析器。请判断一篇知识中实际使用了哪些思考动作，而不是判断它讨论什么主题。

只允许使用这些模式 ID：
- decomposition：分解问题
- abstraction：抽象与建模
- classification：分类与分层
- causal_reasoning：因果推理
- comparison：对比与排除
- hypothesis_test：假设与验证
- local_to_global：局部到整体
- iteration：递归与迭代
- tradeoff：权衡与优化
- boundary：边界分析
- analogy：类比迁移
- feedback：反馈修正

严格规则：
- 每个模式必须附带输入原文中的连续原句，不能概括或改写 evidence。
- 内容仅仅有列表、标题或 Liora 模板，不代表使用了某种思维方式。
- 没有足够证据时 patterns 返回空数组；不要为了丰富结果而联想。
- problem_structure 只描述问题如何被处理，不复述主题；无法判断时返回空字符串。
- 只返回严格 JSON，不要 Markdown：
{
  "patterns": [
    {"id": "decomposition", "description": "如何体现该思考动作", "evidence": "输入中的连续原句", "section": "logic_chain", "confidence": 0.0}
  ],
  "problem_structure": ""
}
"""

LEARNING_STRUCTURE_PROMPT = """你是 Liora 的知识命题抽取器。请从输入片段中抽取可用于学习诊断和严格路径推理的命题。

只允许类型：assertion、definition、causal、prerequisite、boundary、method、example、contradiction、question、reasoning_step、connection。

严格规则：
- evidence 必须是输入某一片段中的连续原文，不能概括、拼接或改写；
- causal 必须给出明确 subject（原因）、object（结果），mechanism 只填原文明确说明的机制；
- prerequisite 必须给出前置 subject 和目标 object；
- conditions 只保留原文明示的条件；
- 不因为出现“因为、所以、导致”等词就强行抽取完整因果链；
- 不抽取思维风格、主题标签、模板标题或格式标记；
- 没有足够证据时 claims 返回空数组；
- 每篇最多 24 条，只返回严格 JSON：
{
  "claims": [
    {
      "type": "causal",
      "subject": "",
      "predicate": "causes",
      "object": "",
      "mechanism": "",
      "conditions": [],
      "polarity": "positive | negative",
      "evidence": "输入中的连续原文"
    }
  ],
  "components": []
}
"""

PATH_VERIFIER_PROMPT = """你是 Liora 的学习路径反向审查器。输入中的候选已经过本地召回，但你必须主动寻找拒绝理由。

逐条检查：
1. 前一步输出是否真的等价或蕴含后一步输入；
2. 是否存在方向反转、极性冲突、时间/范围/层级/适用条件不兼容；
3. 是否依赖没有写出的关键前提；
4. 是否只是主题相似、共同词语、共同表达方式或明显重复；
5. 组合后是否产生具体的新解释、预测、决策边界或行动；
6. 这条解释是否泛化到大量无关文本；若是则拒绝。

只能使用输入证据，不得补充外部事实。允许全部拒绝。返回严格 JSON：
{
  "decisions": [
    {
      "canonical_key": "",
      "decision": "PASS | REJECT",
      "reason_code": "valid | broken_bridge | missing_premise | wrong_direction | incompatible_scope | obvious | generic | ungrounded",
      "reason": "",
      "learning_payoff": "",
      "failure_conditions": []
    }
  ]
}
"""

COGNITIVE_PATTERN_IDS = {
    "decomposition", "abstraction", "classification", "causal_reasoning",
    "comparison", "hypothesis_test", "local_to_global", "iteration",
    "tradeoff", "boundary", "analogy", "feedback",
}


class DeepSeekError(RuntimeError):
    pass


class DeepSeekClient:
    def __init__(self, settings: DeepSeekSettings):
        self.settings = settings
        self.last_usage: dict = {}

    @property
    def configured(self) -> bool:
        return self.settings.configured

    def generate_follow_up(
        self,
        conversation: list[dict],
        turn_number: int,
        sources: list[dict] | None = None,
    ) -> str:
        if not self.configured:
            raise DeepSeekError("DeepSeek API Key 尚未配置。")

        research = self._research_context(sources or [])
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "system",
                "content": (
                    f"这是用户本次反思的第 {turn_number} 次回答。请结合完整上下文判断是追问，"
                    "还是先提供必要的解释或确认。" + research
                ),
            },
            *[
                {"role": item["role"], "content": item["content"]}
                for item in conversation[-12:]
                if item.get("role") in {"assistant", "user"} and item.get("content")
            ],
        ]
        content = self._request(messages, temperature=0.55, max_tokens=320)
        return self._clean_response(content)

    def organize_knowledge(
        self,
        conversation: list[dict],
        existing: dict | None = None,
        sources: list[dict] | None = None,
    ) -> dict:
        if not self.configured:
            raise DeepSeekError("DeepSeek API Key 尚未配置。")
        context = ""
        if existing:
            context = (
                "\n这是用户正在继续完善的已有知识，请把新感悟与它连成新的完整逻辑：\n"
                + json.dumps(existing.get("content", existing), ensure_ascii=False)
            )
        source_pool = [*(existing or {}).get("content", {}).get("sources", []), *(sources or [])]
        messages = [
            {
                "role": "system",
                "content": KNOWLEDGE_PROMPT + context + self._research_context(sources or []),
            },
            *[
                {"role": item["role"], "content": item["content"]}
                for item in conversation
                if item.get("role") in {"assistant", "user"} and item.get("content")
            ],
            {"role": "user", "content": "请以对话为知识线索，构建一份完整知识文件，并只返回指定 JSON。"},
        ]
        raw = self._request(messages, temperature=0.25, max_tokens=3200)
        result = self._parse_json(raw)
        normalized = self.normalize_knowledge(result)
        normalized["sources"] = self._normalize_sources(source_pool)
        return normalized

    def revise_knowledge(
        self,
        conversation: list[dict],
        current: dict,
        instruction: str,
        sources: list[dict] | None = None,
    ) -> dict:
        if not self.configured:
            raise DeepSeekError("DeepSeek API Key 尚未配置。")
        messages = [
            {
                "role": "system",
                "content": REVISION_PROMPT + self._research_context(sources or []),
            },
            {
                "role": "user",
                "content": "原始对话：\n" + json.dumps(conversation, ensure_ascii=False),
            },
            {
                "role": "user",
                "content": "当前知识文件：\n" + json.dumps(current, ensure_ascii=False),
            },
            {"role": "user", "content": f"修改意见：{instruction.strip()}"},
        ]
        raw = self._request(messages, temperature=0.2, max_tokens=3200)
        result = self._parse_json(raw)
        normalized = self.normalize_knowledge(result)
        normalized["sources"] = self._normalize_sources(
            [*current.get("sources", []), *(sources or [])]
        )
        return normalized

    def judge_alignment(self, draft: dict, candidates: list[dict]) -> dict:
        if not self.configured:
            raise DeepSeekError("DeepSeek API Key 尚未配置。")
        compact_candidates = [
            {
                "id": str(item.get("knowledge_id") or ""),
                "title": str(item.get("title") or "")[:120],
                "score": float(item.get("score") or 0),
                "core_insight": str(
                    item.get("core_insight") or item.get("snippet") or ""
                )[:1200],
                "key_points": [
                    str(value)[:400] for value in (item.get("key_points") or [])[:5]
                ],
            }
            for item in candidates[:3]
            if item.get("knowledge_id")
        ]
        messages = [
            {"role": "system", "content": ALIGNMENT_PROMPT},
            {
                "role": "user",
                "content": "待对齐的新知识：\n" + json.dumps(draft, ensure_ascii=False),
            },
            {
                "role": "user",
                "content": "本地检索候选：\n"
                + json.dumps(compact_candidates, ensure_ascii=False),
            },
        ]
        raw = self._request(messages, temperature=0.0, max_tokens=700)
        value = self._parse_json(raw)
        decision = str(value.get("decision") or "").strip().upper()
        if decision not in {"CREATE", "UPDATE", "RELATED", "CHILD"}:
            raise DeepSeekError("DeepSeek 返回了无效的知识对齐结论。")
        candidate_ids = {item["id"] for item in compact_candidates}
        target_id = str(value.get("target_id") or "").strip() or None
        if decision in {"UPDATE", "RELATED", "CHILD"} and target_id not in candidate_ids:
            raise DeepSeekError("DeepSeek 选择了候选列表之外的知识。")
        if decision == "CREATE":
            target_id = None
        try:
            confidence = min(max(float(value.get("confidence") or 0), 0.0), 1.0)
        except (TypeError, ValueError):
            confidence = 0.0
        conflicts = value.get("conflicts")
        return {
            "decision": decision,
            "target_id": target_id,
            "relationship": str(value.get("relationship") or "").strip()[:500],
            "conflicts": [str(item).strip()[:500] for item in conflicts[:8]]
            if isinstance(conflicts, list)
            else [],
            "reason": str(value.get("reason") or "").strip()[:1200],
            "confidence": round(confidence, 4),
            "needs_human_review": bool(value.get("needs_human_review", True)),
        }

    def analyze_cognitive_profile(self, title: str, chunks: list[dict]) -> dict:
        if not self.configured:
            raise DeepSeekError("DeepSeek API Key 尚未配置。")
        compact_chunks = [
            {
                "section": str(item.get("section") or "")[:80],
                "text": str(item.get("text") or "")[:500],
            }
            for item in chunks[:36]
            if str(item.get("text") or "").strip()
        ]
        messages = [
            {"role": "system", "content": COGNITIVE_PROFILE_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {"title": str(title or "")[:120], "chunks": compact_chunks},
                    ensure_ascii=False,
                ),
            },
        ]
        raw = self._request(messages, temperature=0.0, max_tokens=1200)
        value = self._parse_json(raw)
        raw_patterns = value.get("patterns")
        patterns = []
        for item in raw_patterns if isinstance(raw_patterns, list) else []:
            if not isinstance(item, dict):
                continue
            pattern_id = str(item.get("id") or "").strip()
            evidence = " ".join(str(item.get("evidence") or "").split()).strip()
            if pattern_id not in COGNITIVE_PATTERN_IDS or len(evidence) < 8:
                continue
            matched_chunk = next(
                (
                    chunk
                    for chunk in compact_chunks
                    if evidence in " ".join(chunk["text"].split())
                ),
                None,
            )
            if not matched_chunk:
                continue
            try:
                confidence = min(max(float(item.get("confidence") or 0), 0.0), 1.0)
            except (TypeError, ValueError):
                confidence = 0.0
            if confidence < 0.58:
                continue
            patterns.append(
                {
                    "id": pattern_id,
                    "description": str(item.get("description") or "").strip()[:500],
                    "evidence": evidence[:360],
                    "section": matched_chunk["section"],
                    "confidence": round(confidence, 4),
                }
            )
        seen = set()
        unique = []
        for item in patterns:
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            unique.append(item)
        return {
            "patterns": unique[:6],
            "problem_structure": str(value.get("problem_structure") or "").strip()[:600],
            "provider": "deepseek-schema-evidence",
        }

    def analyze_learning_structure(self, title: str, chunks: list[dict]) -> dict:
        if not self.configured:
            raise DeepSeekError("DeepSeek API Key 尚未配置。")
        compact_chunks = [
            {
                "section": str(item.get("section") or "")[:80],
                "text": str(item.get("text") or "")[:450],
            }
            for item in chunks[:20]
            if str(item.get("text") or "").strip()
        ]
        messages = [
            {"role": "system", "content": LEARNING_STRUCTURE_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {"title": str(title or "")[:120], "chunks": compact_chunks},
                    ensure_ascii=False,
                ),
            },
        ]
        raw = self._request(messages, temperature=0.0, max_tokens=1000)
        value = self._parse_json(raw)
        claims = value.get("claims")
        return {
            "claims": claims[:24] if isinstance(claims, list) else [],
            "components": [],
            "model": f"deepseek:{self.settings.model}:grounded-claims-v1",
        }

    def verify_learning_paths(self, candidates: list[dict]) -> dict[str, dict]:
        if not self.configured:
            raise DeepSeekError("DeepSeek API Key 尚未配置。")
        compact = []
        for item in candidates[:3]:
            evidence = item.get("evidence") or {}
            key = str((item.get("features") or {}).get("canonical_key") or "")
            if not key:
                continue
            compact.append({
                "canonical_key": key,
                "relation_type": str(item.get("label") or "")[:80],
                "source_excerpt": str(evidence.get("source_excerpt") or "")[:500],
                "target_excerpt": str(evidence.get("target_excerpt") or "")[:500],
                "bridge": str(evidence.get("bridge") or "")[:240],
                "proposed_payoff": str(evidence.get("learning_payoff") or item.get("reason") or "")[:600],
                "failure_conditions": [str(value)[:300] for value in (evidence.get("failure_conditions") or [])[:5]],
            })
        if not compact:
            return {}
        raw = self._request(
            [
                {"role": "system", "content": PATH_VERIFIER_PROMPT},
                {"role": "user", "content": json.dumps({"candidates": compact}, ensure_ascii=False)},
            ],
            temperature=0.0,
            max_tokens=700,
        )
        value = self._parse_json(raw)
        allowed = {item["canonical_key"] for item in compact}
        decisions: dict[str, dict] = {}
        for item in value.get("decisions") if isinstance(value.get("decisions"), list) else []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("canonical_key") or "")
            decision = str(item.get("decision") or "").upper()
            if key not in allowed or decision not in {"PASS", "REJECT"}:
                continue
            decisions[key] = {
                "decision": decision,
                "reason_code": str(item.get("reason_code") or "")[:80],
                "reason": str(item.get("reason") or "")[:800],
                "learning_payoff": str(item.get("learning_payoff") or "")[:800],
                "failure_conditions": [
                    str(condition)[:300]
                    for condition in (item.get("failure_conditions") or [])[:6]
                ],
            }
        return decisions

    @staticmethod
    def _parse_json(raw: str) -> dict:
        try:
            value = raw.strip()
            if value.startswith("```"):
                value = value.split("\n", 1)[-1].rsplit("```", 1)[0]
            return json.loads(value)
        except (json.JSONDecodeError, TypeError) as error:
            raise DeepSeekError("DeepSeek 返回的知识整理格式无效。") from error

    def _request(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
        self.last_usage = {}
        payload = {
            "model": self.settings.model,
            "messages": messages,
            "thinking": {"type": "disabled"},
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        raw_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{self.settings.base_url}/chat/completions",
            data=raw_body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Liora-Reflection-Companion/0.2",
            },
        )

        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = self._http_error_detail(error)
            raise DeepSeekError(f"DeepSeek 请求失败（HTTP {error.code}）：{detail}") from error
        except (URLError, socket.timeout, TimeoutError) as error:
            raise DeepSeekError("DeepSeek 网络连接或响应超时。") from error
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise DeepSeekError("DeepSeek 返回了无法读取的数据。") from error

        try:
            content = result["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError, AttributeError) as error:
            raise DeepSeekError("DeepSeek 返回结果中没有可用的回复。") from error
        if not content:
            raise DeepSeekError("DeepSeek 返回了空回复。")
        usage = result.get("usage") if isinstance(result, dict) else {}
        prompt_details = usage.get("prompt_tokens_details") if isinstance(usage, dict) else {}
        self.last_usage = {
            "prompt_tokens": int((usage or {}).get("prompt_tokens") or 0),
            "prompt_cache_hit_tokens": int(
                (usage or {}).get("prompt_cache_hit_tokens")
                or (prompt_details or {}).get("cached_tokens")
                or 0
            ),
            "prompt_cache_miss_tokens": int(
                (usage or {}).get("prompt_cache_miss_tokens") or 0
            ),
            "completion_tokens": int((usage or {}).get("completion_tokens") or 0),
        }
        return content

    @staticmethod
    def normalize_knowledge(value: dict) -> dict:
        if not isinstance(value, dict):
            raise DeepSeekError("DeepSeek 返回的知识整理格式无效。")
        title = str(value.get("title", "")).strip()[:80]
        core = str(value.get("core_insight", "")).strip()[:3000]

        def string_list(name: str, limit: int = 8, item_limit: int = 800) -> list[str]:
            raw_items = value.get(name, [])
            if isinstance(raw_items, str):
                raw_items = raw_items.splitlines()
            if not isinstance(raw_items, list):
                return []
            return [str(item).strip()[:item_limit] for item in raw_items if str(item).strip()][:limit]

        result = {
            "title": title,
            "core_insight": core,
            "key_points": string_list("key_points", 8),
            "logic_chain": string_list("logic_chain", 8),
            "examples": string_list("examples", 6, 1200),
            "extensions": string_list("extensions", 8, 1200),
            "boundaries": string_list("boundaries", 8),
            "connections": string_list("connections", 8),
            "open_questions": string_list("open_questions", 6),
            "next_step": str(value.get("next_step", "")).strip()[:1200],
            "sources": DeepSeekClient._normalize_sources(value.get("sources", [])),
        }
        if not title or not core or not (result["key_points"] or result["logic_chain"]):
            raise DeepSeekError("DeepSeek 返回的知识整理缺少必要内容。")
        return result

    @staticmethod
    def _normalize_sources(sources: list[dict] | object) -> list[dict]:
        if not isinstance(sources, list):
            return []
        normalized = []
        seen = set()
        for item in sources:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()[:200]
            url = str(item.get("url") or "").strip()[:1000]
            summary = " ".join(str(item.get("summary") or "").split()).strip()[:1200]
            if not title or not url or url in seen:
                continue
            seen.add(url)
            normalized.append({"title": title, "url": url, "summary": summary})
        return normalized[:8]

    @staticmethod
    def _research_context(sources: list[dict]) -> str:
        normalized = DeepSeekClient._normalize_sources(sources)
        if not normalized:
            return ""
        return (
            "\n\n以下是本次联网查证得到的资料。只使用这些资料能够支持的事实，并保留来源名称：\n"
            + json.dumps(normalized, ensure_ascii=False)
        )

    @staticmethod
    def _clean_response(content: str) -> str:
        value = content.strip().strip('"“”')
        if len(value) > 600:
            value = value[:600].rstrip() + "…"
        return value

    @staticmethod
    def _http_error_detail(error: HTTPError) -> str:
        try:
            payload = json.loads(error.read().decode("utf-8"))
            message = payload.get("error", {}).get("message")
            if message:
                return str(message)[:200]
        except Exception:
            pass
        return "请检查 Key、模型名称、余额或服务状态。"
