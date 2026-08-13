import type { DashboardQuestion } from "./dashboard-model";

export interface ReflectionPrompt {
  id: string;
  kind: "knowledge_gap";
  knowledgeId: string;
  title: string;
  path: string;
  context: string;
  prompt: string;
  reasonCode: "open_question";
  reason: string;
}

export interface QuestionVoice {
  eyebrow: string;
  primaryAction: string;
}

export const QUESTION_VOICES: ReadonlyArray<QuestionVoice> = [
  { eyebrow: "Liora突然想到一个小问题", primaryAction: "讲给Liora听" },
  { eyebrow: "Liora脑袋里冒出个问号", primaryAction: "告诉Liora我的想法" },
  { eyebrow: "Liora觉得这里少了一小块", primaryAction: "和Liora一起想" },
  { eyebrow: "Liora在这里卡住啦", primaryAction: "我来解释" },
  { eyebrow: "Liora想听你再讲一点", primaryAction: "说给Liora听" },
  { eyebrow: "Liora又开始好奇啦", primaryAction: "接着想想" }
];

function clean(value: unknown, maximum = 500): string {
  return typeof value === "string" ? value.trim().slice(0, maximum) : "";
}

function stableNumber(value: string): number {
  let hash = 2166136261;
  for (const character of value) {
    hash ^= character.codePointAt(0) ?? 0;
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

export function voiceFor(promptId: string, variation = 0): QuestionVoice {
  const index = (stableNumber(promptId) + Math.max(Math.trunc(variation), 0)) % QUESTION_VOICES.length;
  return QUESTION_VOICES[index];
}

export function normalizeReflectionPrompts(payload: unknown): ReflectionPrompt[] {
  if (!payload || typeof payload !== "object") return [];
  const rawItems = (payload as { items?: unknown }).items;
  if (!Array.isArray(rawItems)) return [];
  return rawItems.slice(0, 20).flatMap((raw): ReflectionPrompt[] => {
    if (!raw || typeof raw !== "object") return [];
    const item = raw as Record<string, unknown>;
    const id = clean(item.id, 120);
    const prompt = clean(item.prompt);
    const title = clean(item.title, 160) || "未命名知识";
    if (!id || !prompt || item.kind !== "knowledge_gap" || item.reason_code !== "open_question") return [];
    return [{
      id,
      kind: "knowledge_gap",
      knowledgeId: clean(item.knowledge_id, 120),
      title,
      path: clean(item.path),
      context: clean(item.context, 240),
      prompt,
      reasonCode: "open_question",
      reason: clean(item.reason, 500) || `这个问题来自《${title}》的“尚待探索”。`
    }];
  });
}

export function promptsFromDashboardQuestions(questions: DashboardQuestion[]): ReflectionPrompt[] {
  return questions.map((item, index) => ({
    id: item.knowledgeId
      ? `vault:${item.knowledgeId}:${index}:${item.question}`
      : `vault:${item.path}:${index}:${item.question}`,
    kind: "knowledge_gap",
    knowledgeId: item.knowledgeId,
    title: item.title,
    path: item.path,
    context: "",
    prompt: item.question,
    reasonCode: "open_question",
    reason: `这个问题来自《${item.title}》的“尚待探索”。Liora没有额外猜测你的掌握程度。`
  }));
}
