export interface EngineKnowledgeItem {
  id?: unknown;
  title?: unknown;
  relative_path?: unknown;
  updated_at?: unknown;
  snippet?: unknown;
  content?: { core_insight?: unknown } | null;
}

export interface EngineQuestionItem {
  knowledge_id?: unknown;
  title?: unknown;
  path?: unknown;
  question?: unknown;
}

export interface EngineDashboardPayload {
  knowledge_count?: unknown;
  open_question_count?: unknown;
  recent?: unknown;
  open_questions?: unknown;
  health?: unknown;
}

export interface DashboardItem {
  id: string;
  title: string;
  path: string;
  updatedAt: string;
  summary: string;
}

export interface DashboardData {
  source: "engine" | "vault";
  engineConnected: boolean;
  total: number;
  openQuestionCount: number;
  recent: DashboardItem[];
  openQuestions: DashboardQuestion[];
  health: DashboardHealth;
  notice?: string;
  embedding?: {
    model: string;
    available: boolean;
    loaded: boolean;
    provider: string;
  };
}

export interface DashboardQuestion {
  knowledgeId: string;
  title: string;
  path: string;
  question: string;
}

export interface DashboardHealth {
  growing: number;
  stable: number;
  due: number;
}

function clean(value: unknown, maximum = 500): string {
  return typeof value === "string" ? value.trim().slice(0, maximum) : "";
}

const QUESTION_HEADINGS = new Set([
  "尚待探索",
  "仍待确认",
  "还想继续弄清",
  "开放问题",
  "open questions"
]);

export function extractOpenQuestions(markdown: string): string[] {
  const questions: string[] = [];
  let collecting = false;
  for (const line of String(markdown || "").split(/\r?\n/u)) {
    const heading = line.match(/^#{1,6}\s+(.+?)\s*$/u);
    if (heading) {
      collecting = QUESTION_HEADINGS.has(heading[1].trim().toLowerCase());
      continue;
    }
    if (!collecting) continue;
    const question = line.replace(/^\s*(?:[-*+] |\d+[.)]\s+)/u, "").trim();
    if (question) questions.push(question);
  }
  return questions;
}

export function normalizeEngineUrl(value: string): string {
  const raw = value.trim();
  if (!raw) return "";

  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error("Knowledge Engine 地址格式不正确。");
  }

  const isLoopback = ["127.0.0.1", "localhost", "::1"].includes(parsed.hostname);
  if (!isLoopback || !["http:", "https:"].includes(parsed.protocol)) {
    throw new Error("第一版只允许连接本机 Knowledge Engine。");
  }
  parsed.pathname = parsed.pathname.replace(/\/+$/, "");
  parsed.search = "";
  parsed.hash = "";
  return parsed.toString().replace(/\/$/, "");
}

export function buildDashboardUrl(baseUrl: string): string {
  return `${normalizeEngineUrl(baseUrl)}/api/dashboard`;
}

export function buildReflectionPromptsUrl(baseUrl: string, limit = 8): string {
  const safeLimit = Math.min(Math.max(Math.trunc(limit) || 8, 1), 20);
  return `${normalizeEngineUrl(baseUrl)}/api/reflection-prompts?limit=${safeLimit}`;
}

export function buildReflectionPromptActionUrl(
  baseUrl: string,
  promptId: string,
  action: "start" | "skip" | "snooze"
): string {
  const id = String(promptId || "").trim();
  if (!id) throw new Error("缺少复述问题 ID。");
  return `${normalizeEngineUrl(baseUrl)}/api/reflection-prompts/${encodeURIComponent(id)}/${action}`;
}

function nonNegativeInteger(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? Math.trunc(parsed) : 0;
}

export function normalizeEngineDashboard(
  payload: EngineDashboardPayload
): Pick<DashboardData, "total" | "openQuestionCount" | "recent" | "openQuestions" | "health"> {
  const values = Array.isArray(payload.recent) ? payload.recent : [];
  const recent = values.slice(0, 5).flatMap((raw): DashboardItem[] => {
    if (!raw || typeof raw !== "object") return [];
    const item = raw as EngineKnowledgeItem;
    const path = clean((item as EngineKnowledgeItem & { path?: unknown }).path ?? item.relative_path);
    if (!path) return [];
    const title = clean(item.title, 160) || path.split("/").pop()?.replace(/\.md$/i, "") || "未命名知识";
    const snippet = clean(item.snippet, 240);
    const coreInsight = clean(item.content?.core_insight, 240);
    return [{
      id: clean(item.id, 100),
      title,
      path,
      updatedAt: clean(item.updated_at, 80),
      summary: snippet || coreInsight
    }];
  });

  const questionValues = Array.isArray(payload.open_questions) ? payload.open_questions : [];
  const openQuestions = questionValues.slice(0, 5).flatMap((raw): DashboardQuestion[] => {
    if (!raw || typeof raw !== "object") return [];
    const item = raw as EngineQuestionItem;
    const question = clean(item.question, 500);
    if (!question) return [];
    return [{
      knowledgeId: clean(item.knowledge_id, 100),
      title: clean(item.title, 160) || "未命名知识",
      path: clean(item.path),
      question
    }];
  });
  const rawHealth = payload.health && typeof payload.health === "object"
    ? payload.health as Record<string, unknown>
    : {};
  return {
    total: nonNegativeInteger(payload.knowledge_count),
    openQuestionCount: nonNegativeInteger(payload.open_question_count),
    recent,
    openQuestions,
    health: {
      growing: nonNegativeInteger(rawHealth.growing),
      stable: nonNegativeInteger(rawHealth.stable),
      due: nonNegativeInteger(rawHealth.due)
    }
  };
}
