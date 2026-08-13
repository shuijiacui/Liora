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

SEMANTIC_PIPELINE_VERSION = "semantic-clean-v2"
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


def discover_relations(documents: list[dict], semantic_model: bool = False) -> list[dict]:
    relations: dict[tuple[str, str], dict] = {}
    vectors = {
        item["id"]: item.get("embedding")
        or embed_text(knowledge_text(item.get("content") or {}, item.get("title") or ""))
        for item in documents
    }
    titles = {
        clean_text(item.get("title")): item
        for item in documents
        if clean_text(item.get("title"))
    }
    for source in documents:
        source_id = source["id"]
        raw = knowledge_text(source.get("content") or {}, source.get("title") or "")
        links = {clean_text(value) for value in re.findall(r"\[\[([^]|#]+)", raw)}
        connection_text = "\n".join((source.get("content") or {}).get("connections") or [])
        for title_key, target in titles.items():
            if target["id"] == source_id:
                continue
            mentioned = title_key in links or (
                len(title_key) >= 2 and title_key in clean_text(connection_text)
            )
            if mentioned:
                key = tuple(sorted((source_id, target["id"])))
                relations[key] = {
                    "source_id": source_id,
                    "target_id": target["id"],
                    "kind": "hard",
                    "label": "explicit_reference",
                    "confidence": 1.0,
                    "reason": f"《{source.get('title')}》明确提到了《{target.get('title')}》。",
                    "status": "confirmed",
                }
    for index, source in enumerate(documents):
        for target in documents[index + 1 :]:
            key = tuple(sorted((source["id"], target["id"])))
            if key in relations:
                continue
            source_relation_text = relation_text(source.get("content") or {})
            target_relation_text = relation_text(target.get("content") or {})
            source_tokens = set(_tokens(source_relation_text))
            target_tokens = set(_tokens(target_relation_text))
            # Titles and Liora's template structure are not evidence. Both
            # documents need substantive body content before a soft relation
            # can be proposed.
            if len(source_tokens) < 6 or len(target_tokens) < 6:
                continue
            score = cosine(vectors[source["id"]], vectors[target["id"]])
            evidence_overlap = lexical_overlap(source_relation_text, target_relation_text)
            source_title = clean_text(source.get("title"))
            target_title = clean_text(target.get("title"))
            title_evidence = (
                len(target_title) >= 2 and target_title in clean_text(source_relation_text)
            ) or (
                len(source_title) >= 2 and source_title in clean_text(target_relation_text)
            )
            soft_threshold = 0.36 if semantic_model else 0.12
            duplicate_ceiling = 0.82 if semantic_model else 0.88
            evidence_floor = 0.015 if semantic_model else 0.025
            high_semantic_evidence = semantic_model and score >= 0.58
            if (
                soft_threshold <= score < duplicate_ceiling
                and (title_evidence or evidence_overlap >= evidence_floor or high_semantic_evidence)
            ):
                relations[key] = {
                    "source_id": source["id"],
                    "target_id": target["id"],
                    "kind": "soft",
                    "label": "semantic_similarity",
                    "confidence": round(score, 4),
                    "reason": "两条知识的正文存在可核对的语义交集，但尚未明确建立关系。",
                    "status": "candidate",
                }
    return list(relations.values())


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
    candidates = []
    relation_counts = Counter()
    for relation in relations:
        relation_counts[relation["source_id"]] += 1
        relation_counts[relation["target_id"]] += 1
    for item in documents:
        content = item.get("content") or {}
        claims = extract_claims(content)
        if len(claims) < 4:
            continue
        vectors = [(document_embedder or embed_text)(claim["text"]) for claim in claims]
        similarities = [
            cosine(vectors[left], vectors[right])
            for left in range(len(vectors))
            for right in range(left + 1, len(vectors))
        ]
        separation = 1 - max(sum(similarities) / max(len(similarities), 1), 0)
        size_pressure = min(len(knowledge_text(content)) / 5000, 1)
        retrieval_independence = min(len(claims) / 12, 1)
        relation_divergence = min(relation_counts[item["id"]] / 8, 1)
        score = (
            0.45 * separation
            + 0.25 * retrieval_independence
            + 0.15 * relation_divergence
            + 0.15 * size_pressure
        )
        if score >= 0.48:
            proposed = [
                {"title": claim["text"][:42].rstrip("。.!?！？"), "seed": claim["text"]}
                for claim in claims
                if claim["kind"] in {"key_points", "extensions", "connections"}
            ][:4]
            if len(proposed) >= 2:
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
                        "proposal": {"parent_id": item["id"], "children": proposed},
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
            merge_threshold = 0.78 if semantic_model else 0.72
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
    return candidates[:40]
