"""Learning-value-first intelligence for Liora's knowledge engine.

This module deliberately separates grounded extraction, candidate recall and
relationship validation.  It never turns raw similarity or a shared thinking
style into a visible recommendation.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from datetime import datetime, timezone

from knowledge_intelligence import clean_text, cosine, semantic_clean


PIPELINE_VERSION = "learning-engine-v4"
CLAIM_SCHEMA_VERSION = "grounded-claims-v1"

SECTION_LABELS = {
    "core_insight": "核心理解",
    "key_points": "关键要点",
    "logic_chain": "推理过程",
    "examples": "例子",
    "extensions": "延伸理解",
    "boundaries": "适用边界",
    "connections": "知识连接",
    "open_questions": "尚待探索",
    "next_step": "下一步",
}

NOISE = {
    "因此", "所以", "因为", "由于", "导致", "从而", "可以", "可能", "需要",
    "这个", "这种", "一个", "一种", "进行", "通过", "以及", "或者", "并且",
}

CAUSAL_PATTERNS = (
    re.compile(r"^(.{2,160}?)(?:会|将|可能)?(?:导致|造成|引发|使得|促使)(.{2,180})$"),
    re.compile(r"^(.{2,160}?)(?:因此|所以|从而)(.{2,180})$"),
    re.compile(r"^(?:因为|由于)(.{2,160}?)[，,；;](?:所以|因此|从而)?(.{2,180})$"),
)

PREREQUISITE_PATTERNS = (
    re.compile(r"^(.{2,120}?)(?:是|构成)(.{2,120}?)(?:的)?(?:前提|基础|先决条件)$"),
    re.compile(r"^(?:理解|掌握|使用)(.{2,120}?)(?:需要|依赖|要求)(.{2,120})$"),
)


def _fingerprint(*parts: object, size: int = 32) -> str:
    return hashlib.sha256("\n".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()[:size]


def _normalized(value: object) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", clean_text(value))


def _meaningful_terms(value: object) -> set[str]:
    text = semantic_clean(value)
    terms = {
        term.casefold()
        for term in re.findall(r"[A-Za-z][A-Za-z0-9_+.-]{2,}|[\u4e00-\u9fff]{2,10}", text)
        if term.casefold() not in NOISE
    }
    return terms


def _proposition_match(left: object, right: object) -> float:
    """Return a conservative bridge-equivalence score.

    This is a hard path gate, not semantic recall.  It intentionally prefers
    missing a bridge to joining two merely related propositions.
    """

    a, b = _normalized(left), _normalized(right)
    if len(a) < 4 or len(b) < 4:
        return 0.0
    if a in b or b in a:
        return round(min(len(a), len(b)) / max(len(a), len(b)), 4)
    left_terms, right_terms = _meaningful_terms(left), _meaningful_terms(right)
    if not left_terms or not right_terms:
        return 0.0
    overlap = left_terms & right_terms
    if not overlap:
        return 0.0
    coverage = len(overlap) / min(len(left_terms), len(right_terms))
    return round(coverage, 4) if coverage >= 0.75 else 0.0


def _parse_causal(text: str) -> tuple[str, str] | None:
    value = semantic_clean(text).strip("。.!！?？ ")
    arrow = re.split(r"\s*(?:→|->|⇒|=>)\s*", value)
    if len(arrow) == 2 and min(map(len, arrow)) >= 2:
        return arrow[0].strip(), arrow[1].strip()
    for pattern in CAUSAL_PATTERNS:
        match = pattern.match(value)
        if match:
            cause, effect = (part.strip("，,；;。 ") for part in match.groups())
            if min(len(cause), len(effect)) >= 2:
                return cause, effect
    return None


def _parse_prerequisite(text: str) -> tuple[str, str] | None:
    value = semantic_clean(text).strip("。.!！?？ ")
    for index, pattern in enumerate(PREREQUISITE_PATTERNS):
        match = pattern.match(value)
        if not match:
            continue
        first, second = (part.strip("，,；;。 ") for part in match.groups())
        # Pattern 1: prerequisite first, target second. Pattern 2 reverses it.
        return (first, second) if index == 0 else (second, first)
    return None


def _iter_grounded_sections(content: dict) -> list[tuple[str, int, str]]:
    rows: list[tuple[str, int, str]] = []
    for section in SECTION_LABELS:
        raw = content.get(section)
        values = raw if isinstance(raw, list) else [raw] if raw else []
        for ordinal, item in enumerate(values):
            value = semantic_clean(item)
            if len(clean_text(value)) >= 8:
                rows.append((section, ordinal, value[:1200]))
    return rows


def extract_grounded_structure(content: dict, knowledge_id: str, title: str = "") -> dict:
    """Extract conservative claims and knowledge components from canonical content.

    Every returned item is copied from a canonical field and therefore remains
    source grounded even when DeepSeek is unavailable.
    """

    claims: list[dict] = []
    section_claims: dict[str, list[str]] = defaultdict(list)
    for section, ordinal, evidence in _iter_grounded_sections(content):
        causal = _parse_causal(evidence)
        prerequisite = _parse_prerequisite(evidence)
        claim_type = {
            "boundaries": "boundary",
            "examples": "example",
            "open_questions": "question",
            "next_step": "method",
            "connections": "connection",
            "logic_chain": "reasoning_step",
        }.get(section, "assertion")
        subject = predicate = object_value = ""
        if causal:
            claim_type = "causal"
            subject, object_value = causal
            predicate = "causes"
        elif prerequisite:
            claim_type = "prerequisite"
            subject, object_value = prerequisite
            predicate = "prerequisite_of"
        claim_id = _fingerprint(knowledge_id, section, ordinal, evidence)
        claim = {
            "id": claim_id,
            "knowledge_id": knowledge_id,
            "claim_type": claim_type,
            "subject": subject,
            "predicate": predicate,
            "object": object_value,
            "mechanism": evidence if section == "logic_chain" else "",
            "conditions": [evidence] if section == "boundaries" else [],
            "polarity": "negative" if re.search(r"不|无|不能|并非|避免|失效", evidence) else "positive",
            "section": section,
            "section_label": SECTION_LABELS[section],
            "ordinal": ordinal,
            "evidence": evidence,
            "start_offset": -1,
            "end_offset": -1,
            "fingerprint": _fingerprint(CLAIM_SCHEMA_VERSION, evidence, claim_type),
            "model": "local-grounded-rules-v1",
            "pipeline_version": PIPELINE_VERSION,
        }
        claims.append(claim)
        section_claims[section].append(claim_id)

    components: list[dict] = []
    component_seeds: list[tuple[str, str, list[str]]] = []
    for ordinal, question in enumerate(content.get("open_questions") or []):
        value = semantic_clean(question)
        if value:
            component_seeds.append((value[:72], value[:240], section_claims.get("open_questions", [])[ordinal:ordinal + 1]))
    key_claim_ids = section_claims.get("key_points", [])
    for ordinal, point in enumerate(content.get("key_points") or []):
        value = semantic_clean(point)
        if value:
            short = value[:64].rstrip("。.!！?？")
            component_seeds.append((short, f"如何准确解释：{short}？", key_claim_ids[ordinal:ordinal + 1]))
    if not component_seeds and claims:
        central = semantic_clean(title or content.get("title") or "这项知识")[:72]
        component_seeds.append((central, f"如何准确理解{central}？", [claim["id"] for claim in claims[:6]]))

    seen_questions: set[str] = set()
    for ordinal, (component_title, question, claim_ids) in enumerate(component_seeds[:12]):
        normalized_question = _normalized(question)
        if not normalized_question or normalized_question in seen_questions:
            continue
        seen_questions.add(normalized_question)
        component_id = _fingerprint(knowledge_id, "kc", normalized_question)
        components.append({
            "id": component_id,
            "knowledge_id": knowledge_id,
            "title": component_title,
            "question": question,
            "claim_ids": claim_ids,
            "prerequisite_ids": [],
            "fingerprint": _fingerprint(CLAIM_SCHEMA_VERSION, normalized_question, *claim_ids),
            "model": "local-grounded-rules-v1",
            "pipeline_version": PIPELINE_VERSION,
            "ordinal": ordinal,
        })
    return {"claims": claims[:64], "components": components[:12], "pipeline_version": PIPELINE_VERSION}


def merge_ai_structure(local: dict, ai: dict, chunks: list[dict], knowledge_id: str) -> dict:
    """Merge only AI claims whose evidence is an exact supplied source span."""

    source_texts = [(str(chunk.get("section") or ""), semantic_clean(chunk.get("text"))) for chunk in chunks]
    claims = list(local.get("claims") or [])
    known = {claim["fingerprint"] for claim in claims}
    for raw in ai.get("claims") if isinstance(ai.get("claims"), list) else []:
        if not isinstance(raw, dict):
            continue
        evidence = semantic_clean(raw.get("evidence"))
        matched = next(((section, text) for section, text in source_texts if evidence and evidence in text), None)
        claim_type = str(raw.get("type") or "").strip().lower()
        if not matched or claim_type not in {
            "assertion", "definition", "causal", "prerequisite", "boundary", "method",
            "example", "contradiction", "question", "reasoning_step", "connection",
        }:
            continue
        fingerprint = _fingerprint(CLAIM_SCHEMA_VERSION, evidence, claim_type)
        if fingerprint in known:
            continue
        known.add(fingerprint)
        claims.append({
            "id": _fingerprint(knowledge_id, matched[0], evidence),
            "knowledge_id": knowledge_id,
            "claim_type": claim_type,
            "subject": semantic_clean(raw.get("subject"))[:240],
            "predicate": semantic_clean(raw.get("predicate"))[:80],
            "object": semantic_clean(raw.get("object"))[:240],
            "mechanism": semantic_clean(raw.get("mechanism"))[:500],
            "conditions": [semantic_clean(item)[:300] for item in (raw.get("conditions") or [])[:6] if semantic_clean(item)],
            "polarity": "negative" if str(raw.get("polarity") or "").lower() == "negative" else "positive",
            "section": matched[0],
            "section_label": SECTION_LABELS.get(matched[0], matched[0] or "正文"),
            "ordinal": len(claims),
            "evidence": evidence[:1200],
            "start_offset": -1,
            "end_offset": -1,
            "fingerprint": fingerprint,
            "model": str(ai.get("model") or "deepseek-grounded-v1"),
            "pipeline_version": PIPELINE_VERSION,
        })

    components = list(local.get("components") or [])
    questions = {clean_text(item.get("question")) for item in components}
    for raw in ai.get("components") if isinstance(ai.get("components"), list) else []:
        if not isinstance(raw, dict):
            continue
        question = semantic_clean(raw.get("question"))[:300]
        component_title = semantic_clean(raw.get("title"))[:100]
        if len(clean_text(question)) < 6 or clean_text(question) in questions:
            continue
        claim_ids = [str(item) for item in (raw.get("claim_ids") or []) if str(item) in {claim["id"] for claim in claims}]
        if not claim_ids:
            continue
        questions.add(clean_text(question))
        components.append({
            "id": _fingerprint(knowledge_id, "kc", clean_text(question)),
            "knowledge_id": knowledge_id,
            "title": component_title or question[:72],
            "question": question,
            "claim_ids": claim_ids[:12],
            "prerequisite_ids": [],
            "fingerprint": _fingerprint(CLAIM_SCHEMA_VERSION, clean_text(question), *claim_ids),
            "model": str(ai.get("model") or "deepseek-grounded-v1"),
            "pipeline_version": PIPELINE_VERSION,
            "ordinal": len(components),
        })
    return {"claims": claims[:64], "components": components[:12], "pipeline_version": PIPELINE_VERSION}


def _relation_record(source: dict, target: dict, relation_type: str, path: list[dict], bridge: str,
                     payoff: str, failure_conditions: list[str], confidence: float) -> dict:
    left, right = sorted((source["id"], target["id"]))
    source_step, target_step = path[0], path[-1]
    evidence = {
        "source_excerpt": source_step["evidence"][:500],
        "target_excerpt": target_step["evidence"][:500],
        "source_section": source_step.get("section_label", "正文"),
        "target_section": target_step.get("section_label", "正文"),
        "basis": "typed_path",
        "bridge": bridge,
        "path": path,
        "learning_payoff": payoff,
        "failure_conditions": failure_conditions,
        "verification": "deterministic-strict",
    }
    return {
        # Preserve path direction for display.  Only the canonical key is
        # order-independent; swapping ids here would attach excerpts to the
        # wrong note whenever UUID ordering differs from causal direction.
        "source_id": source["id"],
        "target_id": target["id"],
        "kind": "typed_path",
        "category": "knowledge",
        "label": relation_type,
        "confidence": round(min(max(confidence, 0.0), 1.0), 4),
        "reason": payoff,
        "status": "candidate",
        "evidence": evidence,
        "features": {
            "path_length": len(path),
            "hard_gates_passed": True,
            "canonical_key": _fingerprint(left, right, relation_type, bridge),
            "direction": [source["id"], target["id"]],
        },
        "pipeline_version": PIPELINE_VERSION,
    }


def discover_strict_relations(documents: list[dict], document_similarity_floor: float = 0.18) -> list[dict]:
    """Discover only explicit references and strictly composable causal paths."""

    results: list[dict] = []
    titles = {clean_text(item.get("title")): item for item in documents if clean_text(item.get("title"))}
    # Explicit references are user-authored and therefore confirmed hard edges.
    for source in documents:
        connection_text = "\n".join((source.get("content") or {}).get("connections") or [])
        links = {clean_text(value) for value in re.findall(r"\[\[([^]|#]+)", connection_text)}
        for title_key, target in titles.items():
            if source["id"] == target["id"] or title_key not in links:
                continue
            excerpt = next((item for item in (source.get("claims") or []) if title_key in clean_text(item.get("evidence"))), None)
            target_claim = next(iter(target.get("claims") or []), None)
            if not excerpt or not target_claim:
                continue
            record = _relation_record(
                source, target, "explicit_reference", [excerpt, target_claim],
                "正文明确引用", "用户明确写出了这条知识连接。", [], 1.0,
            )
            record["kind"] = "hard"
            record["status"] = "confirmed"
            record["evidence"]["basis"] = "explicit"
            results.append(record)

    causal_by_note = {
        item["id"]: [claim for claim in (item.get("claims") or []) if claim.get("claim_type") == "causal" and claim.get("subject") and claim.get("object")]
        for item in documents
    }
    for index, source in enumerate(documents):
        for target in documents[index + 1:]:
            if source.get("embedding") and target.get("embedding"):
                if cosine(source["embedding"], target["embedding"]) < document_similarity_floor:
                    continue
            best: tuple[float, dict, dict, bool] | None = None
            for left in causal_by_note.get(source["id"], []):
                for right in causal_by_note.get(target["id"], []):
                    forward = _proposition_match(left.get("object"), right.get("subject"))
                    reverse = _proposition_match(right.get("object"), left.get("subject"))
                    candidate = (forward, left, right, True) if forward >= reverse else (reverse, right, left, False)
                    if candidate[0] >= 0.75 and (best is None or candidate[0] > best[0]):
                        best = candidate
            if not best:
                continue
            bridge_score, first, second, forward = best
            if first.get("polarity") != second.get("polarity"):
                continue
            bridge = first["object"]
            payoff = f"《{source.get('title')}》与《{target.get('title')}》能衔接为：{first['subject']} → {bridge} → {second['object']}。"
            failures = ["若两篇笔记讨论的条件、时间尺度或对象层级不同，这条链不成立。"]
            path_source, path_target = (source, target) if forward else (target, source)
            payoff = (
                f"《{path_source.get('title')}》与《{path_target.get('title')}》能衔接为："
                f"{first['subject']} → {bridge} → {second['object']}。"
            )
            record = _relation_record(
                path_source, path_target, "causal_continuation", [first, second], bridge,
                payoff, failures, 0.78 + 0.18 * bridge_score,
            )
            results.append(record)

    # Keep the queue intentionally small: at most one candidate per source and
    # never more than eight unresolved insights for a refresh.
    confirmed = [item for item in results if item["status"] == "confirmed"]
    candidates = sorted(
        (item for item in results if item["status"] == "candidate"),
        key=lambda item: (-item["confidence"], item["label"]),
    )
    selected: list[dict] = []
    used_sources: set[str] = set()
    for item in candidates:
        direction = item.get("features", {}).get("direction") or [item["source_id"]]
        anchor = direction[0]
        if anchor in used_sources:
            continue
        used_sources.add(anchor)
        selected.append(item)
        if len(selected) >= 8:
            break
    return [*confirmed, *selected]


def component_state_label(state: dict | None) -> str:
    if not state or int(state.get("evidence_count") or 0) == 0:
        return "unknown"
    mastery = float(state.get("mastery") or 0.0)
    uncertainty = float(state.get("uncertainty") or 1.0)
    return "mastered" if mastery >= 0.78 and uncertainty <= 0.35 else "uncertain"


def update_component_state(previous: dict | None, evidence: dict) -> dict:
    """Transparent Bayesian-style KC update without a resident KT model."""

    previous = previous or {}
    mastery = float(previous.get("mastery") or 0.35)
    uncertainty = float(previous.get("uncertainty") or 0.75)
    stability = float(previous.get("stability_days") or 0.0)
    transfer = float(previous.get("transfer_level") or 0.0)
    kind = str(evidence.get("evidence_type") or "recall")
    outcome = str(evidence.get("outcome") or "unknown")
    independent = evidence.get("independent_recall")
    hints = max(int(evidence.get("hint_count") or 0), 0)
    misconceptions = [semantic_clean(item)[:160] for item in (evidence.get("misconceptions") or []) if semantic_clean(item)]

    gains = {
        "correct": 0.16,
        "partial": 0.05,
        "incorrect": -0.18,
        "unknown": 0.0,
    }
    delta = gains.get(outcome, 0.0)
    if independent is True:
        delta += 0.08
    if hints:
        delta -= min(0.03 * hints, 0.12)
    if misconceptions:
        delta -= min(0.04 * len(misconceptions), 0.12)
    if kind == "transfer" and outcome == "correct":
        transfer = min(1.0, transfer + 0.2 + (0.08 if independent else 0.0))
    mastery = min(max(mastery + delta, 0.02), 0.98)
    uncertainty = min(max(uncertainty - (0.12 if outcome != "unknown" else 0.0) + (0.05 if outcome == "partial" else 0.0), 0.08), 0.95)
    stability = max(1 / 6, stability * (1.8 if outcome == "correct" else 0.7) if stability else (3.0 if outcome == "correct" else 0.5))
    existing_misconceptions = list(previous.get("misconceptions") or [])
    merged_misconceptions = list(dict.fromkeys([*existing_misconceptions, *misconceptions]))[-12:]
    return {
        "mastery": round(mastery, 4),
        "uncertainty": round(uncertainty, 4),
        "stability_days": round(min(stability, 365.0), 4),
        "retrievability": round(math.exp(-1 / max(stability, 1 / 6)), 4),
        "transfer_level": round(transfer, 4),
        "misconceptions": merged_misconceptions,
        "evidence_count": int(previous.get("evidence_count") or 0) + 1,
        "last_evidence_type": kind,
        "last_evidence_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def diagnostic_value(component: dict, state: dict | None, goal_relevance: float = 0.5) -> float:
    state = state or {}
    uncertainty = float(state.get("uncertainty") or 0.85)
    mastery = float(state.get("mastery") or 0.35)
    entropy_proxy = 4 * mastery * (1 - mastery)
    return round(0.55 * uncertainty + 0.25 * entropy_proxy + 0.20 * min(max(goal_relevance, 0), 1), 4)
