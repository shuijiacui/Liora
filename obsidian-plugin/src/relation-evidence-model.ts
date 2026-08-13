export interface RelationEvidence {
  sourceExcerpt: string;
  targetExcerpt: string;
  basis: "explicit" | "semantic";
}

function cleanMarkdown(value: string): string {
  return value
    .replace(/^#{1,6}\s+/u, "")
    .replace(/^\s*(?:[-*+] |\d+[.)]\s+)/u, "")
    .replace(/!?(?:\[([^\]]*)\])\([^)]*\)/gu, "$1")
    .replace(/\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]/gu, (_match, path: string, alias?: string) => alias || path)
    .replace(/[*_`~>|]/gu, "")
    .replace(/\s+/gu, " ")
    .trim();
}

export function markdownPassages(markdown: string): string[] {
  const body = String(markdown || "").replace(/^---\s*[\s\S]*?\s---\s*/u, "");
  const passages: string[] = [];
  for (const block of body.split(/\n\s*\n|\r?\n(?=\s*(?:[-*+] |\d+[.)]\s+|#{1,6}\s+))/u)) {
    const value = cleanMarkdown(block);
    if (value.length < 8) continue;
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
