import { App, requestUrl, TFile } from "obsidian";
import {
  buildDashboardUrl,
  buildReflectionPromptActionUrl,
  buildReflectionPromptsUrl,
  DashboardData,
  DashboardItem,
  DashboardQuestion,
  extractOpenQuestions,
  normalizeEngineDashboard,
  normalizeEngineUrl
} from "./dashboard-model";
import { discoverConnection } from "./connection-discovery";
import {
  normalizeReflectionPrompts,
  promptsFromDashboardQuestions,
  ReflectionPrompt
} from "./question-card-model";
import type { LioraMemo } from "./memo-model";
import { buildRelationEvidence, type RelationEvidence } from "./relation-evidence-model";
import { comparableVaultPath, vaultPathCandidates } from "./vault-path-model";

export interface LioraSettings {
  engineUrl: string;
  accessToken: string;
  memos: LioraMemo[];
}

export interface PromptActionResult {
  ok: boolean;
  message: string;
}

export interface ChangeSet {
  id: string;
  action: "create" | "update";
  status: string;
  risk: string;
  title: string;
  reason: string;
  diff: Array<{ field: string; before: unknown; after: unknown }>;
  alignment?: { confidence?: number; candidates?: Array<{ title: string; score: number }> };
}

export interface KnowledgeRelation {
  id: string;
  kind: "hard" | "soft";
  confidence: number;
  reason: string;
  status: string;
  source: { id?: string; title?: string; relative_path?: string };
  target: { id?: string; title?: string; relative_path?: string };
  evidence?: RelationEvidence;
}

export interface GranularityCandidate {
  id: string;
  kind: "split" | "merge";
  score: number;
  reasons: Record<string, number>;
  proposal: Record<string, unknown>;
  sources: Array<{ id: string; title: string; path: string }>;
}

export interface KnowledgeHierarchy {
  parent: { id: string; title: string; path: string };
  child: { id: string; title: string; path: string };
}

export interface GranularityData {
  items: GranularityCandidate[];
  hierarchy: KnowledgeHierarchy[];
}

export interface KnowledgeAnswer {
  answer: string;
  evidence: Array<{ knowledge_id: string; title: string; path: string; score: number; excerpt: string }>;
}

export class KnowledgeService {
  constructor(
    private readonly app: App,
    private readonly settings: LioraSettings
  ) {}

  async loadDashboard(): Promise<DashboardData> {
    const configured = this.settings.engineUrl.trim() && this.settings.accessToken.trim()
      ? { engineUrl: this.settings.engineUrl, accessToken: this.settings.accessToken }
      : discoverConnection();
    if (configured) {
      try {
        return await this.loadFromEngine(configured.engineUrl, configured.accessToken);
      } catch (error) {
        const message = error instanceof Error ? error.message : "无法连接 Knowledge Engine。";
        return await this.loadFromVault(`Knowledge Engine 暂时不可用，已显示 Vault 本地数据。${message}`);
      }
    }
    return await this.loadFromVault("当前使用 Obsidian Vault 只读模式。启动 Liora 后会自动连接 Knowledge Engine。");
  }

  async loadReflectionPrompts(dashboard?: DashboardData): Promise<ReflectionPrompt[]> {
    const configured = this.settings.engineUrl.trim() && this.settings.accessToken.trim()
      ? { engineUrl: this.settings.engineUrl, accessToken: this.settings.accessToken }
      : discoverConnection();
    if (configured) {
      try {
        const baseUrl = normalizeEngineUrl(configured.engineUrl);
        const response = await requestUrl({
          url: buildReflectionPromptsUrl(baseUrl),
          method: "GET",
          headers: { "X-Liora-Token": configured.accessToken.trim() },
          throw: false
        });
        if (response.status === 200) return normalizeReflectionPrompts(response.json);
      } catch {
        // The dashboard's Vault-derived questions remain a safe read-only fallback.
      }
    }
    const source = dashboard ?? await this.loadDashboard();
    return promptsFromDashboardQuestions(source.openQuestions);
  }

  async startReflectionPrompt(promptId: string): Promise<PromptActionResult> {
    return this.postPromptAction(promptId, "start", {});
  }

  async skipReflectionPrompt(promptId: string): Promise<PromptActionResult> {
    return this.postPromptAction(promptId, "skip", {});
  }

  async snoozeReflectionPrompt(promptId: string, days = 3): Promise<PromptActionResult> {
    return this.postPromptAction(promptId, "snooze", { days });
  }

  private connection(): { engineUrl: string; accessToken: string } | null {
    return this.settings.engineUrl.trim() && this.settings.accessToken.trim()
      ? { engineUrl: this.settings.engineUrl, accessToken: this.settings.accessToken }
      : discoverConnection();
  }

  private async engineRequest(path: string, method = "GET", body?: Record<string, unknown>): Promise<unknown> {
    const configured = this.connection();
    if (!configured) throw new Error("Liora都断掉线咯，管理功能需要先启动 Liora。");
    const response = await requestUrl({
      url: `${normalizeEngineUrl(configured.engineUrl)}${path}`,
      method,
      headers: {
        "X-Liora-Token": configured.accessToken.trim(),
        "Content-Type": "application/json"
      },
      body: body ? JSON.stringify(body) : undefined,
      throw: false
    });
    const payload = response.json as { error?: unknown } | undefined;
    if (response.status !== 200) {
      throw new Error(typeof payload?.error === "string" ? payload.error : `Liora连接返回 HTTP ${response.status}。`);
    }
    return payload;
  }

  async loadChangeSets(status = "pending"): Promise<ChangeSet[]> {
    const payload = await this.engineRequest(`/api/changesets?status=${encodeURIComponent(status)}&limit=30`) as { items?: ChangeSet[] };
    return Array.isArray(payload.items) ? payload.items : [];
  }

  async applyChangeSet(id: string): Promise<void> {
    await this.engineRequest(`/api/changesets/${encodeURIComponent(id)}/apply`, "POST", {});
  }

  async rejectChangeSet(id: string): Promise<void> {
    await this.engineRequest(`/api/changesets/${encodeURIComponent(id)}/reject`, "POST", {});
  }

  async rollbackChangeSet(id: string): Promise<void> {
    await this.engineRequest(`/api/changesets/${encodeURIComponent(id)}/rollback`, "POST", {});
  }

  async loadRelations(): Promise<KnowledgeRelation[]> {
    const payload = await this.engineRequest("/api/relations?limit=100") as { items?: KnowledgeRelation[] };
    if (!Array.isArray(payload.items)) return [];
    const markdown = new Map<string, Promise<string>>();
    const read = (path: string): Promise<string> => {
      if (!markdown.has(path)) {
        const file = this.resolveKnowledgeFile(path);
        markdown.set(path, file ? this.app.vault.cachedRead(file) : Promise.resolve(""));
      }
      return markdown.get(path) ?? Promise.resolve("");
    };
    return await Promise.all(payload.items.map(async (item) => {
      if (item.evidence?.sourceExcerpt && item.evidence?.targetExcerpt) return item;
      const sourcePath = item.source?.relative_path ?? "";
      const targetPath = item.target?.relative_path ?? "";
      if (!sourcePath || !targetPath) return item;
      const [sourceMarkdown, targetMarkdown] = await Promise.all([read(sourcePath), read(targetPath)]);
      const evidence = buildRelationEvidence(
        sourceMarkdown,
        targetMarkdown,
        item.source?.title ?? "",
        item.target?.title ?? ""
      );
      return evidence ? { ...item, evidence } : item;
    }));
  }

  async updateRelation(id: string, action: "confirm" | "reject"): Promise<void> {
    await this.engineRequest(`/api/relations/${encodeURIComponent(id)}/${action}`, "POST", {});
  }

  async loadGranularity(): Promise<GranularityCandidate[]> {
    return (await this.loadGranularityData()).items;
  }

  async loadGranularityData(): Promise<GranularityData> {
    const payload = await this.engineRequest("/api/granularity?status=candidate&limit=40") as Partial<GranularityData>;
    return {
      items: Array.isArray(payload.items) ? payload.items : [],
      hierarchy: Array.isArray(payload.hierarchy) ? payload.hierarchy : []
    };
  }

  async updateGranularity(id: string, action: "apply" | "reject"): Promise<void> {
    await this.engineRequest(`/api/granularity/${encodeURIComponent(id)}/${action}`, "POST", {});
  }

  async askKnowledge(question: string): Promise<KnowledgeAnswer> {
    return await this.engineRequest("/api/knowledge/ask", "POST", { question }) as KnowledgeAnswer;
  }

  private async postPromptAction(
    promptId: string,
    action: "start" | "skip" | "snooze",
    body: Record<string, unknown>
  ): Promise<PromptActionResult> {
    const configured = this.settings.engineUrl.trim() && this.settings.accessToken.trim()
      ? { engineUrl: this.settings.engineUrl, accessToken: this.settings.accessToken }
      : discoverConnection();
    if (!configured) {
      return { ok: false, message: "Liora都断掉线咯，先启动源码版 Liora 再试一次。" };
    }
    try {
      const baseUrl = normalizeEngineUrl(configured.engineUrl);
      const response = await requestUrl({
        url: buildReflectionPromptActionUrl(baseUrl, promptId, action),
        method: "POST",
        headers: {
          "X-Liora-Token": configured.accessToken.trim(),
          "Content-Type": "application/json"
        },
        body: JSON.stringify(body),
        throw: false
      });
      const payload = response.json as { error?: unknown } | undefined;
      if (response.status === 200) {
        const messages = {
          start: "Liora收到这个小问题啦；正忙时会先挂在“回顾”气泡上。",
          skip: "Liora先换一个小问号。",
          snooze: "Liora先把它放回三天后。"
        };
        return { ok: true, message: messages[action] };
      }
      return {
        ok: false,
        message: typeof payload?.error === "string" ? payload.error : `Liora连接返回 HTTP ${response.status}。`
      };
    } catch (error) {
      return {
        ok: false,
        message: error instanceof Error ? error.message : "Liora暂时接不到这个小问题。"
      };
    }
  }

  private async loadFromEngine(engineUrl: string, accessToken: string): Promise<DashboardData> {
    const baseUrl = normalizeEngineUrl(engineUrl);
    const headers = { "X-Liora-Token": accessToken.trim() };
    const health = await requestUrl({ url: `${baseUrl}/health`, method: "GET", headers, throw: false });
    if (health.status !== 200) {
      throw new Error(`连接返回 HTTP ${health.status}。`);
    }
    const dashboard = await requestUrl({
      url: buildDashboardUrl(baseUrl),
      method: "GET",
      headers,
      throw: false
    });
    if (dashboard.status !== 200) {
      throw new Error(`知识首页返回 HTTP ${dashboard.status}。`);
    }
    const normalized = normalizeEngineDashboard(dashboard.json);
    const healthPayload = health.json as {
      embedding?: { model?: unknown; available?: unknown; loaded?: unknown; provider?: unknown };
    };
    const rawEmbedding = healthPayload.embedding;
    const embedding = rawEmbedding ? {
      model: String(rawEmbedding.model || ""),
      available: Boolean(rawEmbedding.available),
      loaded: Boolean(rawEmbedding.loaded),
      provider: String(rawEmbedding.provider || "")
    } : undefined;
    return { source: "engine", engineConnected: true, embedding, ...normalized };
  }

  private async loadFromVault(notice: string): Promise<DashboardData> {
    // This plugin is installed in a dedicated Liora Vault, so every Markdown
    // file is already a knowledge object. Metadata describes it but does not
    // decide whether it is admitted into knowledge management.
    const files = this.app.vault.getMarkdownFiles();
    const sorted = [...files].sort((left, right) => right.stat.mtime - left.stat.mtime);
    const recent = sorted.slice(0, 5).map((file): DashboardItem => {
      const cache = this.app.metadataCache.getFileCache(file);
      const frontmatterTitle = cache?.frontmatter?.title;
      return {
        id: String(cache?.frontmatter?.id ?? cache?.frontmatter?.liora_id ?? ""),
        title: typeof frontmatterTitle === "string" && frontmatterTitle.trim()
          ? frontmatterTitle.trim()
          : file.basename,
        path: file.path,
        updatedAt: new Date(file.stat.mtime).toISOString(),
        summary: ""
      };
    });
    const openQuestions: DashboardQuestion[] = [];
    for (const file of sorted) {
      if (openQuestions.length >= 5) break;
      const text = await this.app.vault.cachedRead(file);
      for (const question of extractOpenQuestions(text)) {
        const item = recent.find((candidate) => candidate.path === file.path);
        openQuestions.push({
          knowledgeId: item?.id ?? "",
          title: item?.title ?? file.basename,
          path: file.path,
          question
        });
        if (openQuestions.length >= 5) break;
      }
    }
    return {
      source: "vault",
      engineConnected: false,
      total: files.length,
      recent,
      openQuestionCount: openQuestions.length,
      openQuestions,
      health: { growing: 0, stable: 0, due: 0 },
      notice
    };
  }

  async openKnowledge(path: string): Promise<boolean> {
    const target = this.resolveKnowledgeFile(path);
    if (!target) return false;
    await this.app.workspace.getLeaf("tab").openFile(target);
    return true;
  }

  private resolveKnowledgeFile(path: string): TFile | null {
    const adapter = this.app.vault.adapter as typeof this.app.vault.adapter & { getBasePath?: () => string };
    const basePath = adapter.getBasePath?.() ?? "";
    const candidates = vaultPathCandidates(path, basePath);
    for (const candidate of candidates) {
      const target = this.app.vault.getAbstractFileByPath(candidate);
      if (target instanceof TFile) return target;
    }

    const files = this.app.vault.getMarkdownFiles();
    const comparableInput = comparableVaultPath(path);
    for (const file of files) {
      const comparableFile = comparableVaultPath(file.path);
      if (comparableInput === comparableFile || comparableInput.endsWith(`/${comparableFile}`)) return file;
    }

    const linkPath = candidates[0]?.replace(/\.md$/iu, "") ?? "";
    const linked = linkPath ? this.app.metadataCache.getFirstLinkpathDest(linkPath, "") : null;
    if (linked instanceof TFile) return linked;

    const name = comparableInput.split("/").pop()?.replace(/\.md$/iu, "") ?? "";
    const byName = files.filter((file) => file.basename.toLocaleLowerCase() === name);
    return byName.length === 1 ? byName[0] : null;
  }
}
