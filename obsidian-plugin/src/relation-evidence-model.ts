export interface RelationEvidence {
  sourceExcerpt: string;
  targetExcerpt: string;
  sourceSection?: string;
  targetSection?: string;
  bridge?: string;
  patternId?: string;
  patternLabel?: string;
  path?: Array<Record<string, unknown>>;
  learningPayoff?: string;
  failureConditions?: string[];
  verification?: string;
  basis: "explicit" | "typed_path" | "semantic" | "cognitive" | "analogy";
}

export function normalizeRelationEvidence(value: unknown): RelationEvidence | undefined {
  if (!value || typeof value !== "object") return undefined;
  const raw = value as Record<string, unknown>;
  const basisValue = String(raw.basis ?? "semantic");
  const basis = (["explicit", "typed_path", "semantic", "cognitive", "analogy"].includes(basisValue)
    ? basisValue : "semantic") as RelationEvidence["basis"];
  const failures = raw.failureConditions ?? raw.failure_conditions;
  return {
    sourceExcerpt: String(raw.sourceExcerpt ?? raw.source_excerpt ?? ""),
    targetExcerpt: String(raw.targetExcerpt ?? raw.target_excerpt ?? ""),
    sourceSection: String(raw.sourceSection ?? raw.source_section ?? "") || undefined,
    targetSection: String(raw.targetSection ?? raw.target_section ?? "") || undefined,
    bridge: String(raw.bridge ?? "") || undefined,
    patternId: String(raw.patternId ?? raw.pattern_id ?? "") || undefined,
    patternLabel: String(raw.patternLabel ?? raw.pattern_label ?? "") || undefined,
    path: Array.isArray(raw.path) ? raw.path.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") : undefined,
    learningPayoff: String(raw.learningPayoff ?? raw.learning_payoff ?? "") || undefined,
    failureConditions: Array.isArray(failures) ? failures.map(String).filter(Boolean) : undefined,
    verification: String(raw.verification ?? "") || undefined,
    basis
  };
}

const TEMPLATE_LINES = new Set([
  "核心理解", "核心洞察", "关键要点", "关键概念", "原理与推理", "工作机制",
  "逻辑链", "例子与反例", "示例", "延伸理解", "知识延伸", "边界与误区",
  "适用边界", "知识联系", "对比与联系", "尚待探索", "仍待确认", "开放问题",
  "下一步", "参考资料", "来源", "暂无", "无", "待补充", "待整理"
]);

function cleanMarkdown(value: string): string {
  return value
    .replace(/<!--[^]*?-->/gu, " ")
    .replace(/^#{1,6}\s+/u, "")
    .replace(/^\s*(?:[-*+] |\d+[.)]\s+)/u, "")
    .replace(/!?(?:\[([^\]]*)\])\([^)]*\)/gu, "$1")
    .replace(/\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]/gu, (_match, path: string, alias?: string) => alias || path)
    .replace(/[*_`~>|]/gu, "")
    .replace(/\s+/gu, " ")
    .trim();
}

export function markdownPassages(markdown: string): string[] {
  const body = String(markdown || "")
    .replace(/^---\s*[\s\S]*?\s---\s*/u, "")
    .replace(/<!--[^]*?-->/gu, " ");
  const passages: string[] = [];
  for (const block of body.split(/\n\s*\n|\r?\n(?=\s*(?:[-*+] |\d+[.)]\s+|#{1,6}\s+))/u)) {
    const value = cleanMarkdown(block);
    if (value.length < 8 || TEMPLATE_LINES.has(value)) continue;
    const excerpt = value.slice(0, 280);
    if (!passages.includes(excerpt)) passages.push(excerpt);
    if (passages.length >= 24) break;
  }
  return passages;
}

function tokens(value: string): Set<string> {
  const normalized = value.toLocaleLowerCase().replace(/\s+/gu, "");
  const result = new Set(normalized.match(/[a-z0-9_+#.-]{2,}/gu) ?? []);
  const chinese = normalized.replace(/[^\u3400-\u9fff]/gu, "");
  for (let index = 0; index < chinese.length - 1; index += 1) result.add(chinese.slice(index, index + 2));
  return result;
}

function similarity(left: string, right: string): number {
  const leftTokens = tokens(left);
  const rightTokens = tokens(right);
  if (!leftTokens.size || !rightTokens.size) return 0;
  let shared = 0;
  for (const token of leftTokens) if (rightTokens.has(token)) shared += 1;
  return shared / Math.sqrt(leftTokens.size * rightTokens.size);
}

export function buildRelationEvidence(
  sourceMarkdown: string,
  targetMarkdown: string,
  sourceTitle = "",
  targetTitle = ""
): RelationEvidence | null {
  const sourcePassages = markdownPassages(sourceMarkdown);
  const targetPassages = markdownPassages(targetMarkdown);
  if (!sourcePassages.length || !targetPassages.length) return null;

  const explicitSource = sourcePassages.find((passage) => targetTitle.length >= 2 && passage.includes(targetTitle));
  const explicitTarget = targetPassages.find((passage) => sourceTitle.length >= 2 && passage.includes(sourceTitle));
  if (explicitSource || explicitTarget) {
    return {
      sourceExcerpt: explicitSource ?? sourcePassages[0],
      targetExcerpt: explicitTarget ?? targetPassages[0],
      basis: "explicit"
    };
  }

  let best = { sourceExcerpt: sourcePassages[0], targetExcerpt: targetPassages[0], score: -1 };
  for (const sourceExcerpt of sourcePassages.slice(0, 14)) {
    for (const targetExcerpt of targetPassages.slice(0, 14)) {
      const score = similarity(sourceExcerpt, targetExcerpt);
      if (score > best.score) best = { sourceExcerpt, targetExcerpt, score };
    }
  }
  return { sourceExcerpt: best.sourceExcerpt, targetExcerpt: best.targetExcerpt, basis: "semantic" };
}
