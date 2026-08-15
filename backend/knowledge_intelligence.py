import hashlib
import math
import re
from collections import Counter
from typing import Callable


CONTENT_KEYS = (
    "core_insight",
    "key_points",
    "logic_chain",
    "examples",
    "extensions",
    "boundaries",
    "connections",
    "open_questions",
    "next_step",
    "sources",
)

RELATION_KEYS = (
    "core_insight",
    "key_points",
    "logic_chain",
    "examples",
    "extensions",
    "boundaries",
    "connections",
)

SEMANTIC_PIPELINE_VERSION = "knowledge-graph-v3"
LIORA_MARKER_PATTERN = re.compile(
    r"<!(?:--)?\s*(?:liora|loria)\s*[:_-]?\s*(?:begin|end)\s*(?:--|-)?\s*>",
    re.IGNORECASE,
)
GENERIC_TEMPLATE_LINES = {
    "核心理解",
    "核心洞察",
    "关键要点",
    "关键概念",
    "原理与推理",
    "工作机制",
    "逻辑链",
    "例子与反例",
    "示例",
    "延伸理解",
    "知识延伸",
    "边界与误区",
    "适用边界",
    "知识联系",
    "对比与联系",
    "尚待探索",
    "仍待确认",
    "开放问题",
    "下一步",
    "参考资料",
    "来源",
    "暂无",
    "无",
    "待补充",
    "待整理",
}
GENERIC_TEMPLATE_KEYS = {item.casefold() for item in GENERIC_TEMPLATE_LINES}

SECTION_LABELS = {
    "core_insight": "核心理解",
    "key_points": "关键要点",
    "logic_chain": "原理与推理",
    "examples": "例子与反例",
    "extensions": "延伸理解",
    "boundaries": "边界与误区",
    "connections": "知识联系",
}

# A deliberately small, auditable cognitive ontology. These signals are only
# the offline fallback; a configured LLM may infer the same schema from less
# explicit prose, but every result still has to quote the source text.
COGNITIVE_PATTERNS = {
    "decomposition": ("分解问题", r"分解|拆分|划分|子问题|分治"),
    "abstraction": ("抽象与建模", r"抽象|建模|一般化|统一表示|忽略.{0,8}细节"),
    "classification": ("分类与分层", r"分类|归类|分层|层次|类别"),
    "causal_reasoning": ("因果推理", r"因为|由于|导致|因此|从而|因果"),
    "comparison": ("对比与排除", r"对比|相比|区别|反之|而不是|排除"),
    "hypothesis_test": ("假设与验证", r"假设|验证|检验|证伪|实验"),
    "local_to_global": ("局部到整体", r"局部.{0,12}整体|自底向上|逐层|组合.{0,8}整体"),
    "iteration": ("递归与迭代", r"递归|迭代|循环|反复"),
    "tradeoff": ("权衡与优化", r"权衡|取舍|优化|复杂度|效率|成本|空间换时间"),
    "boundary": ("边界分析", r"边界|前提|条件|限制|例外|不变量"),
    "analogy": ("类比迁移", r"类比|类似于|映射|对应关系"),
    "feedback": ("反馈修正", r"反馈|校正|纠偏|闭环|动态调整"),
}

COGNITIVE_AFFINITIES = {
    frozenset(("decomposition", "local_to_global")): "从拆解局部到重组整体",
    frozenset(("abstraction", "analogy")): "通过抽象结构完成跨域迁移",
    frozenset(("iteration", "feedback")): "在重复过程中依据反馈修正",
    frozenset(("comparison", "boundary")): "通过对比和边界澄清问题",
    frozenset(("hypothesis_test", "causal_reasoning")): "用验证过程检查因果解释",
}


def semantic_clean(value: object) -> str:
    """Remove Liora scaffolding without discarding user knowledge."""
    text = LIORA_MARKER_PATTERN.sub(" ", str(value or ""))
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"^\s*#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*Liora\s*整理\s*[：:]\s*", "", text, flags=re.IGNORECASE)
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"^\s*(?:[-*+] |\d+[.)]\s+)", "", raw).strip()
        if not line or line.casefold() in GENERIC_TEMPLATE_KEYS:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def clean_text(value: object) -> str:
    return " ".join(semantic_clean(value).casefold().split())


def knowledge_text(content: dict, title: str = "") -> str:
    values = [semantic_clean(title or content.get("title") or "")]
    for key in CONTENT_KEYS:
        raw = content.get(key)
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    values.extend(semantic_clean(value) for value in item.values())
                else:
                    values.append(semantic_clean(item))
        elif raw:
            values.append(semantic_clean(raw))
    return "\n".join(value for value in values if value.strip())


def relation_text(content: dict) -> str:
    values = []
    for key in RELATION_KEYS:
        raw = content.get(key)
        if isinstance(raw, list):
            values.extend(semantic_clean(item) for item in raw)
        elif raw:
            values.append(semantic_clean(raw))
    return "\n".join(value for value in values if value.strip())


def _split_semantic_passage(text: str, limit: int = 360) -> list[str]:
    value = semantic_clean(text)
    if not value:
        return []
    units = [
        unit.strip()
        for unit in re.split(r"\n+|(?<=[。！？.!?；;])\s*", value)
        if unit.strip()
    ]
    chunks: list[str] = []
    buffer = ""
    for unit in units:
        if len(unit) > limit:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.extend(unit[index : index + limit] for index in range(0, len(unit), limit))
        elif buffer and len(buffer) + len(unit) + 1 > limit:
            chunks.append(buffer)
            buffer = unit
        else:
            buffer = f"{buffer}\n{unit}".strip()
    if buffer:
        chunks.append(buffer)
    return [item for item in chunks if len(clean_text(item)) >= 8]


def build_knowledge_chunks(content: dict, knowledge_id: str = "") -> list[dict]:
    """Create compact, structure-aware evidence chunks from canonical content."""
    chunks: list[dict] = []
    for key in RELATION_KEYS:
        raw = content.get(key)
        values = raw if isinstance(raw, list) else [raw] if raw else []
        ordinal = 0
        for item in values:
            for text in _split_semantic_passage(str(item or "")):
                fingerprint = hashlib.sha256(
                    f"{SEMANTIC_PIPELINE_VERSION}\n{key}\n{text}".encode("utf-8")
                ).hexdigest()
                chunk_id = hashlib.sha256(
                    f"{knowledge_id}\n{key}\n{ordinal}".encode("utf-8")
                ).hexdigest()[:32]
                chunks.append(
                    {
                        "id": chunk_id,
                        "knowledge_id": knowledge_id,
                        "section": key,
                        "section_label": SECTION_LABELS.get(key, key),
                        "ordinal": ordinal,
                        "text": text,
                        "fingerprint": fingerprint,
                    }
                )
                ordinal += 1
    return chunks[:64]


def extract_cognitive_profile(content: dict) -> dict:
    """Infer only explicitly evidenced thinking patterns for offline use."""
    chunks = build_knowledge_chunks(content)
    patterns = []
    for pattern_id, (label, signal) in COGNITIVE_PATTERNS.items():
        match = next((chunk for chunk in chunks if re.search(signal, chunk["text"])), None)
        if not match:
            continue
        patterns.append(
            {
                "id": pattern_id,
                "label": label,
                "description": f"这段内容体现了“{label}”的思考动作。",
                "evidence": match["text"][:360],
                "section": match["section"],
                "confidence": 0.68,
            }
        )
    return {
        "patterns": patterns[:6],
        "problem_structure": "",
        "provider": "local-evidence-rules",
        "pipeline_version": SEMANTIC_PIPELINE_VERSION,
    }


def extract_claims(content: dict) -> list[dict]:
    claims: list[dict] = []
    core = str(content.get("core_insight") or "").strip()
    for paragraph in re.split(r"\n+|(?<=[。！？.!?])\s+", core):
        value = paragraph.strip()
        if len(value) >= 8:
            claims.append({"kind": "core", "text": value[:800]})
    for key in (
        "key_points",
        "logic_chain",
        "examples",
        "extensions",
        "boundaries",
        "connections",
        "open_questions",
    ):
        for item in content.get(key) or []:
            value = str(item).strip()
            if value:
                claims.append({"kind": key, "text": value[:800]})
    seen = set()
    unique = []
    for claim in claims:
        identity = clean_text(claim["text"])
        if identity and identity not in seen:
            seen.add(identity)
            unique.append(claim)
    return unique[:48]


def _tokens(text: str) -> list[str]:
    value = clean_text(text)
    words = re.findall(r"[a-z0-9_+#.-]{2,}|[\u3400-\u9fff]", value)
    compact = re.sub(r"\s+", "", value)
    grams = [compact[index : index + 2] for index in range(max(len(compact) - 1, 0))]
    return [*words, *grams]


def embed_text(text: str, dimensions: int = 384) -> list[float]:
    counts: Counter[int] = Counter()
    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        number = int.from_bytes(digest, "big")
        index = number % dimensions
        counts[index] += -1 if number & 1 else 1
    vector = [float(counts.get(index, 0)) for index in range(dimensions)]
    norm = math.sqrt(sum(value * value for value in vector))
    return [round(value / norm, 7) for value in vector] if norm else vector


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return max(min(sum(a * b for a, b in zip(left, right)), 1.0), -1.0)


def lexical_overlap(left: str, right: str) -> float:
    left_tokens = set(_tokens(left))
    right_tokens = set(_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def content_fingerprint(content: dict, title: str = "") -> str:
    payload = f"{SEMANTIC_PIPELINE_VERSION}\n{knowledge_text(content, title)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def semantic_candidates(
    query: str,
    documents: list[dict],
    limit: int = 8,
    exclude_ids: set[str] | None = None,
    query_embedder: Callable[[str], list[float]] | None = None,
    document_embedder: Callable[[str], list[float]] | None = None,
    semantic_model: bool = False,
) -> list[dict]:
    query_vector = (query_embedder or embed_text)(query)
    excluded = exclude_ids or set()
    candidates = []
    for item in documents:
        if item.get("id") in excluded:
            continue
        vector = item.get("embedding") or (document_embedder or embed_text)(
            knowledge_text(item.get("content") or {}, item.get("title") or "")
        )
        dense_score = cosine(query_vector, vector)
        if dense_score <= 0:
            continue
        document_text = knowledge_text(item.get("content") or {}, item.get("title") or "")
        lexical_score = lexical_overlap(query, document_text)
        # Dense retrieval provides semantic recall. A small lexical signal gives
        # deterministic reranking and protects exact terminology without
        # overwhelming paraphrases. The legacy hash vector already encodes
        # lexical overlap, so it keeps its historical score distribution.
        score = (
            0.88 * dense_score + 0.12 * lexical_score
            if semantic_model
            else dense_score
        )
        candidates.append(
            {
                "knowledge_id": item["id"],
                "title": item.get("title") or "未命名知识",
                "path": item.get("relative_path") or item.get("path") or "",
                "score": round(score, 4),
                "dense_score": round(dense_score, 4),
                "lexical_score": round(lexical_score, 4),
                "snippet": str((item.get("content") or {}).get("core_insight") or "")[:240],
            }
        )
    candidates.sort(key=lambda item: (-item["score"], item["title"].casefold()))
    return candidates[: max(1, min(int(limit), 30))]


def align_knowledge(
    draft: dict,
    documents: list[dict],
    explicit_target_id: str | None = None,
    document_embedder: Callable[[str], list[float]] | None = None,
    semantic_model: bool = False,
) -> dict:
    claims = extract_claims(draft)
    candidates = semantic_candidates(
        knowledge_text(draft),
        documents,
        6,
        query_embedder=document_embedder,
        document_embedder=document_embedder,
        semantic_model=semantic_model,
    )
    by_id = {item.get("id"): item for item in documents}
    title_key = re.sub(r"\W+", "", clean_text(draft.get("title")))
    exact = next(
        (
            item
            for item in documents
            if title_key
            and re.sub(r"\W+", "", clean_text(item.get("title"))) == title_key
        ),
        None,
    )
    target = by_id.get(explicit_target_id) if explicit_target_id else None
    reason = "没有发现足够接近的已有知识，建议创建新的知识对象。"
    confidence = 0.72
    action = "create"
    decision_basis = "novel"
    # BGE cosine scores have a different distribution from the legacy hash
    # vectors. These are conservative provisional gates: semantic matches are
    # recalled early, while only very close pairs may become UPDATE candidates.
    # DeepSeek/human review still decides every semantic-only structural change.
    update_threshold = 0.62 if semantic_model else 0.58
    related_threshold = 0.30 if semantic_model else 0.42
    if target:
        action = "update"
        decision_basis = "explicit"
        confidence = 1.0
        reason = "这次复述从已有知识继续，沿用原知识对象。"
    elif exact:
        target = exact
        action = "update"
        decision_basis = "exact_title"
        confidence = 0.98
        reason = "标题与已有知识完全一致，为避免重复，建议更新原对象。"
    elif candidates and candidates[0]["score"] >= update_threshold:
        target = by_id.get(candidates[0]["knowledge_id"])
        action = "update"
        decision_basis = "semantic"
        confidence = candidates[0]["score"]
        reason = "核心表达与已有知识高度相近，为避免重复，建议合入原对象。"
    elif candidates and candidates[0]["score"] >= related_threshold:
        confidence = round(1 - candidates[0]["score"] * 0.45, 4)
        reason = "发现相关知识，但主题仍有独立价值；创建建议需要在差异审核中确认。"
    return {
        "action": action,
        "decision_basis": decision_basis,
        "target_id": target.get("id") if target else None,
        "target_title": target.get("title") if target else None,
        "confidence": round(float(confidence), 4),
        "reason": reason,
        "claims": claims,
        "candidates": candidates,
        "thresholds": {
            "update": update_threshold,
            "related": related_threshold,
            "profile": "bge-zh-v1.5-provisional" if semantic_model else "ngram-v1",
        },
    }


def content_diff(before: dict | None, after: dict) -> list[dict]:
    before = before or {}
    changes = []
    for key in ("title", *CONTENT_KEYS):
        old = before.get(key)
        new = after.get(key)
        if old != new:
            changes.append({"field": key, "before": old, "after": new})
    return changes


def _relation_label(source_chunk: dict, target_chunk: dict, score: float) -> tuple[str, str]:
    joined = clean_text(f"{source_chunk['text']}\n{target_chunk['text']}")
    if score >= 0.88:
        return "duplicates", "内容高度重合"
    if re.search(r"对比|相比|区别|反之|相反|而不是", joined):
        return "contrasts_with", "形成对比"
    if re.search(r"前置|基础|依赖|先理解", joined):
        return "prerequisite_of", "存在前置关系"
    if source_chunk.get("section") == "examples" or target_chunk.get("section") == "examples":
        return "example_of", "原理与实例互相对应"
    if re.search(r"应用|用于|适用于|实践", joined):
        return "applies_to", "原理与应用互相对应"
    if source_chunk.get("section") == "logic_chain" or target_chunk.get("section") == "logic_chain":
        return "explains", "存在解释关系"
    return "conceptual_overlap", "共享核心概念"


def _ordered_evidence(source: dict, target: dict, evidence: dict) -> tuple[str, str, dict]:
    if source["id"] <= target["id"]:
        return source["id"], target["id"], evidence
    swapped = dict(evidence)
    swapped["source_excerpt"], swapped["target_excerpt"] = (
        evidence.get("target_excerpt", ""),
        evidence.get("source_excerpt", ""),
    )
    swapped["source_section"], swapped["target_section"] = (
        evidence.get("target_section", ""),
        evidence.get("source_section", ""),
    )
    return target["id"], source["id"], swapped


def _relation_record(
    source: dict,
    target: dict,
    *,
    kind: str,
    category: str,
    label: str,
    confidence: float,
    reason: str,
    status: str,
    evidence: dict,
    features: dict | None = None,
) -> dict:
    source_id, target_id, ordered_evidence = _ordered_evidence(source, target, evidence)
    return {
        "source_id": source_id,
        "target_id": target_id,
        "kind": kind,
        "category": category,
        "label": label,
        "confidence": round(min(max(float(confidence), 0.0), 1.0), 4),
        "reason": reason,
        "status": status,
        "evidence": ordered_evidence,
        "features": features or {},
        "pipeline_version": SEMANTIC_PIPELINE_VERSION,
    }


def _document_chunks(item: dict) -> list[dict]:
    chunks = item.get("chunks") or build_knowledge_chunks(item.get("content") or {}, item["id"])
    result = []
    for chunk in chunks:
        text = semantic_clean(chunk.get("text"))
        if len(clean_text(text)) < 8:
            continue
        result.append({**chunk, "text": text, "embedding": chunk.get("embedding") or embed_text(text)})
    return result


def _best_chunk_matches(source_chunks: list[dict], target_chunks: list[dict]) -> list[dict]:
    matches = []
    for source in source_chunks:
        for target in target_chunks:
            dense = cosine(source["embedding"], target["embedding"])
            lexical = lexical_overlap(source["text"], target["text"])
            matches.append(
                {
                    "source": source,
                    "target": target,
                    "dense": dense,
                    "lexical": lexical,
                    "score": 0.88 * dense + 0.12 * min(lexical * 4, 1),
                }
            )
    matches.sort(key=lambda item: (-item["score"], -item["lexical"]))
    return matches


def discover_relations(documents: list[dict], semantic_model: bool = False) -> list[dict]:
    """Discover typed, evidence-backed content and cognitive connections.

    Whole-document similarity is recall only. A candidate is emitted only when
    canonical chunks or two cognitive profiles provide evidence on both sides.
    """
    relations: dict[tuple[str, str, str], dict] = {}
    vectors = {
        item["id"]: item.get("embedding")
        or embed_text(knowledge_text(item.get("content") or {}, item.get("title") or ""))
        for item in documents
    }
    chunks = {item["id"]: _document_chunks(item) for item in documents}
    titles = {
        clean_text(item.get("title")): item
        for item in documents
        if clean_text(item.get("title"))
    }

    for source in documents:
        source_id = source["id"]
        connection_text = "\n".join((source.get("content") or {}).get("connections") or [])
        links = {clean_text(value) for value in re.findall(r"\[\[([^]|#]+)", connection_text)}
        for title_key, target in titles.items():
            if target["id"] == source_id:
                continue
            mentioned = title_key in links or (
                len(title_key) >= 2 and title_key in clean_text(connection_text)
            )
            if not mentioned:
                continue
            source_evidence = next(
                (item for item in chunks[source_id] if title_key in clean_text(item["text"])),
                chunks[source_id][0] if chunks[source_id] else None,
            )
            target_evidence = chunks[target["id"]][0] if chunks[target["id"]] else None
            if not source_evidence or not target_evidence:
                continue
            evidence = {
                "source_excerpt": source_evidence["text"][:360],
                "target_excerpt": target_evidence["text"][:360],
                "source_section": source_evidence.get("section_label", "正文"),
                "target_section": target_evidence.get("section_label", "正文"),
                "basis": "explicit",
                "bridge": "正文明确指向另一条知识",
            }
            record = _relation_record(
                source,
                target,
                kind="hard",
                category="knowledge",
                label="explicit_reference",
                confidence=1.0,
                reason=f"《{source.get('title')}》明确提到了《{target.get('title')}》。",
                status="confirmed",
                evidence=evidence,
                features={"direction": [source_id, target["id"]]},
            )
            relations[(record["source_id"], record["target_id"], record["label"])] = record

    recall_threshold = 0.32 if semantic_model else 0.10
    strong_chunk_threshold = 0.64 if semantic_model else 0.12
    supporting_chunk_threshold = 0.50 if semantic_model else 0.08
    lexical_floor = 0.025
    for index, source in enumerate(documents):
        for target in documents[index + 1 :]:
            source_chunks = chunks[source["id"]]
            target_chunks = chunks[target["id"]]
            if not source_chunks or not target_chunks:
                continue
            document_score = cosine(vectors[source["id"]], vectors[target["id"]])
            if document_score < recall_threshold:
                continue
            matches = _best_chunk_matches(source_chunks, target_chunks)
            if not matches:
                continue
            best = matches[0]
            independent = []
            used_source: set[str] = set()
            used_target: set[str] = set()
            for match in matches:
                source_key = match["source"]["id"]
                target_key = match["target"]["id"]
                if match["dense"] < supporting_chunk_threshold:
                    continue
                if source_key in used_source or target_key in used_target:
                    continue
                independent.append(match)
                used_source.add(source_key)
                used_target.add(target_key)
                if len(independent) == 2:
                    break
            has_evidence = (
                best["lexical"] >= lexical_floor
                or best["dense"] >= strong_chunk_threshold
                or len(independent) >= 2
            )
            if not has_evidence:
                continue
            label, bridge = _relation_label(best["source"], best["target"], best["dense"])
            confidence = 0.28 * document_score + 0.58 * best["dense"] + 0.14 * min(best["lexical"] * 4, 1)
            evidence = {
                "source_excerpt": best["source"]["text"][:360],
                "target_excerpt": best["target"]["text"][:360],
                "source_section": best["source"].get("section_label", "正文"),
                "target_section": best["target"].get("section_label", "正文"),
                "basis": "semantic",
                "bridge": bridge,
            }
            record = _relation_record(
                source,
                target,
                kind="typed",
                category="knowledge",
                label=label,
                confidence=confidence,
                reason=f"两侧正文片段{bridge}；相似度仅用于召回，不作为关系本身。",
                status="candidate",
                evidence=evidence,
                features={
                    "document_dense": round(document_score, 4),
                    "chunk_dense": round(best["dense"], 4),
                    "lexical_overlap": round(best["lexical"], 4),
                    "independent_matches": len(independent),
                },
            )
            relations[(record["source_id"], record["target_id"], record["label"])] = record

    # Cognitive connections are a separate graph. Matching pattern identifiers
    # provide the schema constraint; verbatim excerpts provide provenance.
    for index, source in enumerate(documents):
        source_patterns = {
            item.get("id"): item
            for item in (source.get("cognitive_profile") or {}).get("patterns", [])
            if item.get("id") in COGNITIVE_PATTERNS and semantic_clean(item.get("evidence"))
        }
        if not source_patterns:
            continue
        for target in documents[index + 1 :]:
            target_patterns = {
                item.get("id"): item
                for item in (target.get("cognitive_profile") or {}).get("patterns", [])
                if item.get("id") in COGNITIVE_PATTERNS and semantic_clean(item.get("evidence"))
            }
            shared = sorted(set(source_patterns) & set(target_patterns))
            if shared:
                pattern_id = max(
                    shared,
                    key=lambda key: min(
                        float(source_patterns[key].get("confidence") or 0),
                        float(target_patterns[key].get("confidence") or 0),
                    ),
                )
                left_pattern = source_patterns[pattern_id]
                right_pattern = target_patterns[pattern_id]
                label = COGNITIVE_PATTERNS[pattern_id][0]
                confidence = min(
                    float(left_pattern.get("confidence") or 0),
                    float(right_pattern.get("confidence") or 0),
                )
                evidence = {
                    "source_excerpt": semantic_clean(left_pattern["evidence"])[:360],
                    "target_excerpt": semantic_clean(right_pattern["evidence"])[:360],
                    "source_section": SECTION_LABELS.get(left_pattern.get("section"), "正文"),
                    "target_section": SECTION_LABELS.get(right_pattern.get("section"), "正文"),
                    "basis": "cognitive",
                    "bridge": f"共同采用：{label}",
                    "pattern_id": pattern_id,
                    "pattern_label": label,
                }
                record = _relation_record(
                    source,
                    target,
                    kind="cognitive",
                    category="cognitive",
                    label=f"shares_reasoning_pattern:{pattern_id}",
                    confidence=confidence,
                    reason=f"两篇知识讨论的对象可以不同，但都体现了“{label}”的思考动作。",
                    status="candidate",
                    evidence=evidence,
                    features={"pattern_id": pattern_id, "shared_patterns": shared},
                )
                relations[(record["source_id"], record["target_id"], record["label"])] = record
                continue

            affinity = next(
                (
                    (left_id, right_id, description)
                    for pair, description in COGNITIVE_AFFINITIES.items()
                    for left_id in source_patterns
                    for right_id in target_patterns
                    if frozenset((left_id, right_id)) == pair
                ),
                None,
            )
            if not affinity:
                continue
            left_id, right_id, description = affinity
            left_pattern = source_patterns[left_id]
            right_pattern = target_patterns[right_id]
            evidence = {
                "source_excerpt": semantic_clean(left_pattern["evidence"])[:360],
                "target_excerpt": semantic_clean(right_pattern["evidence"])[:360],
                "source_section": SECTION_LABELS.get(left_pattern.get("section"), "正文"),
                "target_section": SECTION_LABELS.get(right_pattern.get("section"), "正文"),
                "basis": "analogy",
                "bridge": description,
            }
            record = _relation_record(
                source,
                target,
                kind="inspiration",
                category="inspiration",
                label=f"analogical_bridge:{left_id}:{right_id}",
                confidence=0.56,
                reason=f"这是一条探索性连接：{description}。它不是事实关系，确认后才会保留。",
                status="candidate",
                evidence=evidence,
                features={"source_pattern": left_id, "target_pattern": right_id},
            )
            relations[(record["source_id"], record["target_id"], record["label"])] = record
    return sorted(
        relations.values(),
        key=lambda item: (item["status"] != "candidate", -item["confidence"], item["label"]),
    )


def answer_from_documents(question: str, documents: list[dict]) -> dict:
    candidates = semantic_candidates(question, documents, 5)
    by_id = {item["id"]: item for item in documents}
    evidence = []
    for candidate in candidates[:3]:
        item = by_id[candidate["knowledge_id"]]
        content = item.get("content") or {}
        excerpt = str(content.get("core_insight") or "").strip()
        if excerpt:
            evidence.append({**candidate, "excerpt": excerpt[:500]})
    if not evidence or evidence[0]["score"] < 0.12:
        answer = "Liora暂时没有在当前知识库里找到足够相关的依据。"
    else:
        answer = "\n\n".join(
            f"《{item['title']}》：{item['excerpt']}" for item in evidence
        )
    return {"question": question, "answer": answer, "evidence": evidence, "provider": "local"}


def granularity_candidates(
    documents: list[dict],
    relations: list[dict],
    document_embedder: Callable[[str], list[float]] | None = None,
    semantic_model: bool = False,
) -> list[dict]:
    """Return a small queue of reversible, evidence-backed structure plans.

    A score alone is not actionable.  Every split therefore includes the
    destination notes, copied source passages, field-level migration mapping,
    retained parent role and failure conditions.  Applying a plan copies
    content into children and keeps the parent intact, so the operation is
    reversible from Obsidian history.
    """
    candidates = []
    relation_counts = Counter()
    for relation in relations:
        relation_counts[relation["source_id"]] += 1
        relation_counts[relation["target_id"]] += 1
    for item in documents:
        content = item.get("content") or {}
        claims = [
            claim for claim in extract_claims(content)
            if claim["kind"] in {"key_points", "logic_chain", "examples", "extensions", "boundaries"}
        ]
        if len(claims) < 5:
            continue
        vectors = [(document_embedder or embed_text)(claim["text"]) for claim in claims]
        similarities = [
            cosine(vectors[left], vectors[right])
            for left in range(len(vectors))
            for right in range(left + 1, len(vectors))
        ]
        separation = 1 - max(sum(similarities) / max(len(similarities), 1), 0)
        size_pressure = min(len(knowledge_text(content)) / 5000, 1)
        retrieval_independence = min(len(claims) / 10, 1)
        relation_divergence = min(relation_counts[item["id"]] / 8, 1)
        score = (
            0.45 * separation
            + 0.25 * retrieval_independence
            + 0.15 * relation_divergence
            + 0.15 * size_pressure
        )
        if score >= 0.55:
            # Farthest-first seeds keep the proposal interpretable and cheap.
            seed_indexes = [0]
            while len(seed_indexes) < (3 if len(claims) >= 9 else 2):
                candidate_index, distance = max(
                    (
                        (index, min(1 - cosine(vectors[index], vectors[seed]) for seed in seed_indexes))
                        for index in range(len(claims)) if index not in seed_indexes
                    ),
                    key=lambda pair: pair[1],
                    default=(-1, 0),
                )
                if candidate_index < 0 or distance < 0.36:
                    break
                seed_indexes.append(candidate_index)
            groups: list[list[dict]] = [[] for _ in seed_indexes]
            for claim, vector in zip(claims, vectors):
                group_index = max(
                    range(len(seed_indexes)),
                    key=lambda index: cosine(vector, vectors[seed_indexes[index]]),
                )
                groups[group_index].append(claim)
            groups = [group for group in groups if group]
            proposed = []
            for group in groups:
                anchor = next((claim for claim in group if claim["kind"] == "key_points"), group[0])
                title = anchor["text"][:42].rstrip("。.!?！？")
                field_map: dict[str, list[str]] = {}
                for claim in group:
                    field_map.setdefault(claim["kind"], []).append(claim["text"])
                child_content = {
                    "title": title,
                    "core_insight": anchor["text"],
                    "key_points": field_map.get("key_points") or [anchor["text"]],
                    "logic_chain": field_map.get("logic_chain") or [],
                    "examples": field_map.get("examples") or [],
                    "extensions": field_map.get("extensions") or [],
                    "boundaries": field_map.get("boundaries") or [],
                    "connections": [f"上位知识：{item.get('title') or '原知识'}"],
                    "open_questions": [],
                    "next_step": f"尝试独立解释“{title}”，并补充一个适用边界。",
                    "sources": [],
                }
                proposed.append({
                    "title": title,
                    "purpose": f"把围绕“{title}”的论点收束成可单独检索和回顾的知识单元。",
                    "diagnostic_question": f"不查看原文时，你能解释“{title}”及其适用边界吗？",
                    "seed": anchor["text"],
                    "source_excerpts": [claim["text"] for claim in group],
                    "moved_sections": field_map,
                    "content": child_content,
                })
            if len(proposed) >= 2 and all(child["source_excerpts"] for child in proposed):
                candidates.append(
                    {
                        "kind": "split",
                        "source_ids": [item["id"]],
                        "score": round(score, 4),
                        "reasons": {
                            "semantic_separation": round(separation, 4),
                            "retrieval_independence": round(retrieval_independence, 4),
                            "relation_divergence": round(relation_divergence, 4),
                            "size_pressure": round(size_pressure, 4),
                        },
                        "proposal": {
                            "parent_id": item["id"],
                            "strategy": "copy_then_link",
                            "rationale": (
                                f"当前笔记含 {len(claims)} 个可独立检索的论点，至少形成 "
                                f"{len(proposed)} 个语义簇；拆开后每个子知识都能单独提问和复习。"
                            ),
                            "parent_after": {
                                "title": item.get("title") or "原知识",
                                "retains": ["核心理解", "原始全文", "子知识索引"],
                                "note": "首次执行不删除原文，只创建子知识并建立父子链接。",
                            },
                            "children": proposed,
                            "migration_steps": [
                                "创建下列子知识并复制对应原文片段",
                                "为每个子知识加入返回上位知识的链接",
                                "在数据库记录 Parent / Child 层级",
                                "保留原笔记全文，确认无误后再由你手动精简",
                            ],
                            "failure_conditions": [
                                "这些论点必须经常一起解释，拆开反而丢失上下文",
                                "子知识无法形成独立问题或独立检索意图",
                            ],
                            "reversible": True,
                        },
                    }
                )
    vectors = {
        item["id"]: item.get("embedding")
        or (document_embedder or embed_text)(
            knowledge_text(item.get("content") or {}, item.get("title") or "")
        )
        for item in documents
    }
    for index, source in enumerate(documents):
        for target in documents[index + 1 :]:
            score = cosine(vectors[source["id"]], vectors[target["id"]])
            merge_threshold = 0.90 if semantic_model else 0.86
            if score >= merge_threshold:
                candidates.append(
                    {
                        "kind": "merge",
                        "source_ids": [source["id"], target["id"]],
                        "score": round(score, 4),
                        "reasons": {"semantic_overlap": round(score, 4)},
                        "proposal": {
                            "title": source.get("title") or target.get("title"),
                            "keep_parent_summary": True,
                        },
                    }
                )
    candidates.sort(key=lambda item: (-item["score"], item["kind"]))
    # Precision beats volume: at most six structure decisions per refresh.
    return candidates[:6]
