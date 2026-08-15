import { ItemView, Notice, setIcon, WorkspaceLeaf } from "obsidian";
import type LioraKnowledgePlugin from "./main";
import type { ChangeSet, GranularityCandidate, KnowledgeRelation, RelationDecision } from "./knowledge-service";
import { KnowledgeScopeModal } from "./knowledge-scope-modal";
import { buildChangeSetReview } from "./changeset-review-model";

export const LIORA_MANAGER_VIEW = "liora-knowledge-manager";

type ManagerTab = "review" | "relations" | "structure" | "history";
type ActionTone = "primary" | "quiet" | "danger";

const RELATION_LABELS: Record<string, string> = {
  conceptual_overlap: "共享核心概念",
  explains: "解释关系",
  example_of: "原理与实例",
  applies_to: "原理与应用",
  contrasts_with: "对比关系",
  prerequisite_of: "前置关系",
  duplicates: "内容高度重合",
  explicit_reference: "正文明确引用",
  causal_continuation: "因果链衔接"
};

function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "（空）";
  if (Array.isArray(value)) return value.map((item) => typeof item === "string" ? `• ${item}` : JSON.stringify(item)).join("\n");
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function iconButton(parent: HTMLElement, icon: string, label: string): HTMLButtonElement {
  const button = parent.createEl("button", { cls: "liora-icon-button", attr: { title: label, "aria-label": label } });
  setIcon(button, icon);
  return button;
}

export class LioraManagerView extends ItemView {
  private activeTab: ManagerTab = "review";
  private resizeObserver: ResizeObserver | null = null;

  constructor(leaf: WorkspaceLeaf, private readonly plugin: LioraKnowledgePlugin) {
    super(leaf);
  }

  getViewType(): string { return LIORA_MANAGER_VIEW; }
  getDisplayText(): string { return "Liora 管理台"; }
  getIcon(): string { return "library-big"; }

  async onOpen(): Promise<void> {
    this.containerEl.addClass("liora-manager-host");
    this.resizeObserver = new ResizeObserver(([entry]) => {
      const width = entry?.contentRect.width ?? this.contentEl.clientWidth;
      const height = entry?.contentRect.height ?? this.contentEl.clientHeight;
      this.contentEl.toggleClass("is-compact", width < 900);
      this.contentEl.toggleClass("is-narrow", width < 760);
      this.contentEl.toggleClass("is-short", height < 720);
    });
    this.resizeObserver.observe(this.contentEl);
    await this.render();
  }

  async onClose(): Promise<void> {
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.containerEl.removeClass("liora-manager-host");
  }

  async render(): Promise<void> {
    const root = this.contentEl;
    root.empty();
    root.addClass("liora-manager");
    const canvas = root.createDiv({ cls: "liora-manager__canvas" });
    this.renderHeader(canvas);
    const loading = canvas.createDiv({ cls: "liora-manager__loading", text: "Liora 正在巡视知识花园…" });
    const service = this.plugin.createKnowledgeService();
    try {
      const [changes, appliedChanges, relations, relationDecisions, granularity] = await Promise.all([
        service.loadChangeSets(), service.loadChangeSets("applied"), service.loadRelations(),
        service.loadRelationDecisions(), service.loadGranularityData()
      ]);
      loading.remove();
      this.renderDashboard(canvas, changes, appliedChanges, relations, relationDecisions, granularity.items, granularity.hierarchy);
    } catch (error) {
      loading.setText(error instanceof Error ? error.message : "Liora 管理台暂时打不开。");
      loading.addClass("liora-manager__error");
    }
  }

  private renderHeader(root: HTMLElement): void {
    const header = root.createEl("header", { cls: "liora-manager__topbar" });
    const brand = header.createDiv({ cls: "liora-brand" });
    brand.createDiv({ cls: "liora-brand__mark", text: "L" });
    const brandCopy = brand.createDiv();
    brandCopy.createDiv({ cls: "liora-brand__name", text: "LIORA" });
    brandCopy.createDiv({ cls: "liora-brand__caption", text: "你的知识小屋" });
    const copy = header.createDiv({ cls: "liora-manager__title" });
    copy.createDiv({ cls: "liora-manager__eyebrow", text: "KNOWLEDGE GARDEN" });
    copy.createEl("h1", { text: "知识管理台" });
    const tools = header.createDiv({ cls: "liora-manager__tools" });
    const home = iconButton(tools, "home", "返回 Liora Home");
    home.addEventListener("click", () => void this.plugin.activateHome());
    const scope = iconButton(tools, "list-tree", "确认知识管理范围");
    scope.addEventListener("click", () => new KnowledgeScopeModal(this.plugin).open());
    const refresh = iconButton(tools, "refresh-cw", "重新检查知识库");
    refresh.addEventListener("click", () => void this.render());
  }

  private renderDashboard(
    root: HTMLElement,
    changes: ChangeSet[],
    appliedChanges: ChangeSet[],
    relations: KnowledgeRelation[],
    relationDecisions: RelationDecision[],
    granularity: GranularityCandidate[],
    hierarchy: Array<{ parent: { title: string; path: string }; child: { title: string; path: string } }>
  ): void {
    const candidates = relations.filter((item) => item.status === "candidate").length;
    const banner = root.createDiv({
      cls: "liora-manager-banner",
      attr: { role: "img", "aria-label": "Liora 与知识花园的城市旅程" }
    });
    banner.style.setProperty("--liora-manager-banner-image", `url("${this.plugin.assetResource("manager-banner.png")}")`);
    const stage = root.createDiv({ cls: "liora-manager__workspace" });
    const navigation = stage.createEl("nav", { cls: "liora-manager__overview", attr: { "aria-label": "管理台工作区" } });
    const main = stage.createEl("main", { cls: "liora-manager__main" });
    const side = stage.createEl("aside", { cls: "liora-manager__side" });
    const tabs: Array<{ id: ManagerTab; label: string; note: string; icon: string; count: number }> = [
      { id: "review", label: "待你确认", note: "有风险的改动", icon: "inbox", count: changes.length },
      { id: "relations", label: "新关联", note: "等待判断的线索", icon: "waypoints", count: candidates },
      { id: "structure", label: "知识结构", note: "粒度与层级", icon: "network", count: granularity.length + hierarchy.length },
      { id: "history", label: "照料记录", note: "变更与关联决策", icon: "history", count: appliedChanges.length + relationDecisions.length }
    ];

    const buttons = new Map<ManagerTab, HTMLButtonElement>();
    const renderActive = (): void => {
      for (const [id, button] of buttons) {
        const active = id === this.activeTab;
        button.toggleClass("is-active", active);
        button.setAttr("aria-current", active ? "page" : "false");
      }
      main.empty();
      if (this.activeTab === "review") this.renderChanges(main, changes);
      if (this.activeTab === "relations") this.renderRelations(main, relations);
      if (this.activeTab === "structure") {
        this.renderGranularity(main, granularity);
        this.renderHierarchy(main, hierarchy);
      }
      if (this.activeTab === "history") this.renderCareLog(main, appliedChanges, relationDecisions);
    };

    for (const tab of tabs) {
      const button = navigation.createEl("button", { cls: "liora-manager-stat", attr: { type: "button" } });
      const icon = button.createSpan({ cls: "liora-manager-stat__icon" });
      setIcon(icon, tab.icon);
      const text = button.createSpan({ cls: "liora-manager-stat__copy" });
      text.createSpan({ cls: "liora-manager-stat__label", text: tab.label });
      text.createSpan({ cls: "liora-manager-stat__note", text: tab.note });
      button.createSpan({ cls: "liora-manager-stat__count", text: String(tab.count) });
      button.addEventListener("click", () => {
        this.activeTab = tab.id;
        renderActive();
      });
      buttons.set(tab.id, button);
    }
    this.renderAsk(side);
    renderActive();
  }

  private renderAppliedChanges(root: HTMLElement, items: ChangeSet[]): void {
    const section = this.section(root, "CARE LOG", "最近照料过的知识", items.length, "这里保留最近十次已应用的改变，你可以随时检查或撤回。");
    if (!items.length) return void section.createDiv({ cls: "liora-manager-empty", text: "Liora 还没有应用过知识变更。" });
    const list = section.createDiv({ cls: "liora-manager-list liora-manager-list--history" });
    for (const item of items.slice(0, 10)) {
      const card = list.createDiv({ cls: "liora-manager-card is-history" });
      card.createDiv({ cls: "liora-manager-card__badge", text: "已应用" });
      card.createEl("h3", { text: item.title });
      card.createEl("p", { text: item.reason });
      this.actions(card, [["撤回这次改动", async () => this.plugin.createKnowledgeService().rollbackChangeSet(item.id), "danger"]]);
    }
  }

  private section(root: HTMLElement, eyebrow: string, title: string, count: number | null, description?: string): HTMLElement {
    const section = root.createEl("section", { cls: "liora-manager__section" });
    const header = section.createDiv({ cls: "liora-manager__section-header" });
    const copy = header.createDiv();
    copy.createDiv({ cls: "liora-manager__section-kicker", text: eyebrow });
    const titleRow = copy.createDiv({ cls: "liora-manager__section-title" });
    titleRow.createEl("h2", { text: title });
    if (count !== null) titleRow.createSpan({ text: `${count} 条` });
    if (description) header.createEl("p", { text: description });
    return section;
  }

  private renderChanges(root: HTMLElement, items: ChangeSet[]): void {
    const section = this.section(root, "REVIEW QUEUE", "需要你决定的变化", items.length, "Liora 只把不确定的部分留给你，展开后可以查看变更前后。");
    if (!items.length) return void section.createDiv({ cls: "liora-manager-empty is-celebrate", text: "今天很安静，没有需要你决定的变更。" });
    const list = section.createDiv({ cls: "liora-manager-list" });
    for (const item of items) {
      const review = buildChangeSetReview(item);
      const card = list.createDiv({ cls: "liora-manager-card is-review" });
      card.createDiv({ cls: `liora-manager-card__badge is-${item.action}`, text: item.action === "create" ? "新知识" : "内容调整" });
      card.createEl("h3", { text: item.title });
      card.createEl("p", { text: item.reason });
      const details = card.createEl("details");
      details.createEl("summary", { text: review.summary });
      for (const change of review.fields) {
        const row = details.createDiv({ cls: `liora-diff is-${review.mode}` });
        row.createEl("strong", { text: change.label });
        if (review.mode === "update") {
          const before = row.createDiv({ cls: "liora-diff__version" });
          before.createDiv({ cls: "liora-diff__label", text: "原内容" });
          before.createEl("pre", { cls: "liora-diff__before", text: display(change.before) });
        }
        const after = row.createDiv({ cls: "liora-diff__version" });
        after.createDiv({ cls: "liora-diff__label", text: review.mode === "create" ? "拟写入" : "调整后" });
        after.createEl("pre", { cls: "liora-diff__after", text: display(change.after) });
      }
      this.actions(card, [
        [review.mode === "create" ? "创建这篇知识" : "确认这样改", async () => this.plugin.createKnowledgeService().applyChangeSet(item.id), "primary"],
        [review.mode === "create" ? "暂不创建" : "暂时不改", async () => this.plugin.createKnowledgeService().rejectChangeSet(item.id), "quiet"]
      ]);
    }
  }

  private renderCareLog(root: HTMLElement, changes: ChangeSet[], decisions: RelationDecision[]): void {
    const section = this.section(
      root, "CARE LOG", "最近的照料决定", changes.length + decisions.length,
      "建立、忽略或重新考虑关联后，卡片会从待确认区移到这里，并保留当时的证据快照。"
    );
    if (!changes.length && !decisions.length) {
      return void section.createDiv({ cls: "liora-manager-empty", text: "Liora 还没有记录知识变更或关联决定。" });
    }
    if (decisions.length) {
      const list = section.createDiv({ cls: "liora-manager-list liora-manager-list--history" });
      const actionLabels = { confirmed: "已建立关联", rejected: "已忽略", restored: "已放回待确认" } as const;
      for (const item of decisions.slice(0, 30)) {
        const card = list.createDiv({ cls: "liora-manager-card is-history is-relation" });
        card.createDiv({ cls: "liora-manager-card__badge", text: actionLabels[item.action] ?? item.action });
        card.createEl("h3", { text: `${item.source.title || "未知知识"} → ${item.target.title || "未知知识"}` });
        card.createEl("p", { text: item.learning_payoff || item.evidence?.learningPayoff || "已保留当时的关系证据。" });
        if (item.evidence?.sourceExcerpt && item.evidence?.targetExcerpt) {
          const details = card.createEl("details");
          details.createEl("summary", { text: "查看当时的双侧证据" });
          details.createEl("blockquote", { text: item.evidence.sourceExcerpt });
          details.createEl("blockquote", { text: item.evidence.targetExcerpt });
        }
        if (item.action !== "restored") this.actions(card, [[
          "重新放回待确认", async () => this.plugin.createKnowledgeService().updateRelation(item.relation_id, "restore"), "quiet"
        ]]);
      }
    }
    if (changes.length) this.renderAppliedChanges(root, changes);
  }

  private renderAsk(root: HTMLElement): void {
    const section = this.section(root, "ASK THE GARDEN", "从整个知识库中找联系", null, "适合寻找跨笔记联系，不会直接修改你的内容。");
    section.addClass("liora-manager__section--ask");
    const form = section.createEl("form", { cls: "liora-manager-ask" });
    const input = form.createEl("textarea", { attr: { placeholder: "例如：复杂度和 BFS 之间有什么联系？", maxlength: "500", rows: "3" } });
    const submit = form.createEl("button", { attr: { type: "submit" } });
    submit.createSpan({ text: "问问 Liora" });
    setIcon(submit.createSpan(), "arrow-up-right");
    const answer = section.createDiv({ cls: "liora-manager-ask__answer", attr: { "aria-live": "polite" } });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const question = input.value.trim();
      if (!question) return;
      answer.setText("Liora 正在翻知识库…");
      void this.plugin.createKnowledgeService().askKnowledge(question).then((result) => {
        answer.empty();
        answer.createEl("p", { text: result.answer });
        if (result.evidence.length) answer.createDiv({ cls: "liora-manager-ask__evidence-label", text: "相关知识" });
        for (const evidence of result.evidence) {
          const button = answer.createEl("button", { cls: "liora-evidence", text: `${evidence.title} · ${Math.round(evidence.score * 100)}%` });
          button.addEventListener("click", () => void this.plugin.createKnowledgeService().openKnowledge(evidence.path));
        }
      }).catch((error) => answer.setText(error instanceof Error ? error.message : "Liora 暂时答不上来。"));
    });
  }

  private renderRelations(root: HTMLElement, items: KnowledgeRelation[]): void {
    const strict = items.filter((item) => item.status === "candidate" && ["typed_path", "hard"].includes(item.kind));
    const section = this.section(
      root, "HIGH-VALUE CONNECTIONS", "值得你判断的新关联", strict.length,
      "这里只出现能组成有效路径的关系：双侧原文、连接中介、学习收益和失效条件必须同时存在。相似或思维标签本身不会成为建议。"
    );
    if (!strict.length) return void section.createDiv({ cls: "liora-manager-empty", text: "目前没有通过严格门槛的新关联；少而可信比凑数更重要。" });
    const list = section.createDiv({ cls: "liora-manager-list liora-manager-list--relations" });
    for (const item of strict.slice(0, 8)) this.renderRelationCard(list, { ...item, category: "knowledge" });
  }

  private renderRelationCard(list: HTMLElement, item: KnowledgeRelation): void {
    const card = list.createDiv({ cls: "liora-manager-card is-relation is-knowledge" });
    const relationLabel = RELATION_LABELS[item.label ?? ""] ?? "知识路径";
    const badges = card.createDiv({ cls: "liora-manager-card__badges" });
    badges.createDiv({ cls: "liora-manager-card__badge is-knowledge", text: "知识路径" });
    badges.createDiv({ cls: "liora-manager-card__relation-type", text: relationLabel });
    const relation = card.createDiv({ cls: "liora-manager-card__relation" });
    const sourceTitle = relation.createEl("button", { text: item.source.title || "未知知识", attr: { title: "打开来源知识" } });
    const linkIcon = relation.createSpan();
    setIcon(linkIcon, "arrow-left-right");
    const targetTitle = relation.createEl("button", { text: item.target.title || "未知知识", attr: { title: "打开目标知识" } });
    if (item.source.relative_path) sourceTitle.addEventListener("click", () => void this.plugin.createKnowledgeService().openKnowledge(item.source.relative_path ?? ""));
    else sourceTitle.disabled = true;
    if (item.target.relative_path) targetTitle.addEventListener("click", () => void this.plugin.createKnowledgeService().openKnowledge(item.target.relative_path ?? ""));
    else targetTitle.disabled = true;
    card.createEl("p", { text: item.reason });
    if (item.evidence?.sourceExcerpt && item.evidence?.targetExcerpt) {
      const evidence = card.createDiv({ cls: "liora-relation-evidence" });
      const source = evidence.createDiv({ cls: "liora-relation-evidence__passage" });
      source.createDiv({ cls: "liora-relation-evidence__label", text: `${item.evidence.sourceSection ? `${item.evidence.sourceSection} · ` : ""}《${item.source.title || "来源知识"}》` });
      source.createEl("blockquote", { text: item.evidence.sourceExcerpt });
      const bridge = evidence.createDiv({ cls: "liora-relation-evidence__bridge" });
      setIcon(bridge.createSpan(), item.evidence.basis === "explicit" ? "link" : "route");
      bridge.createSpan({ text: item.evidence.bridge || (item.evidence.basis === "explicit" ? "正文明确指向" : "正文片段相互支持") });
      const target = evidence.createDiv({ cls: "liora-relation-evidence__passage" });
      target.createDiv({ cls: "liora-relation-evidence__label", text: `${item.evidence.targetSection ? `${item.evidence.targetSection} · ` : ""}《${item.target.title || "目标知识"}》` });
      target.createEl("blockquote", { text: item.evidence.targetExcerpt });
      if (item.evidence.learningPayoff) {
        const payoff = card.createDiv({ cls: "liora-relation-evidence__missing" });
        payoff.createEl("strong", { text: "为什么值得看：" });
        payoff.createSpan({ text: item.evidence.learningPayoff });
      }
      if (item.evidence.failureConditions?.length) {
        const failures = card.createEl("details");
        failures.createEl("summary", { text: "这条关联什么时候不成立？" });
        const failureList = failures.createEl("ul");
        for (const condition of item.evidence.failureConditions) failureList.createEl("li", { text: condition });
      }
    } else {
      card.createDiv({ cls: "liora-relation-evidence__missing", text: "这条线索缺少双侧正文证据，Liora 不会建议确认它。" });
    }
    const confidence = Math.round(item.confidence * 100);
    const meter = card.createDiv({ cls: "liora-confidence" });
    meter.createSpan({ text: `路径证据 ${confidence}%` });
    const track = meter.createDiv();
    const fill = track.createDiv();
    fill.style.width = `${confidence}%`;
    const confirmLabel = "建立这条关联";
    if (item.status === "candidate" && item.evidence?.sourceExcerpt && item.evidence?.targetExcerpt) this.actions(card, [
      [confirmLabel, async () => this.plugin.createKnowledgeService().updateRelation(item.id, "confirm", "learning_value_confirmed"), "primary"],
      ["忽略这条线索", async () => this.plugin.createKnowledgeService().updateRelation(item.id, "reject", "not_useful_now"), "quiet"]
    ]);
  }

  private renderGranularity(root: HTMLElement, items: GranularityCandidate[]): void {
    const section = this.section(root, "KNOWLEDGE SHAPE", "知识粒度建议", items.length, "拆分让知识更聚焦，合并让同一主题不再散落。结构调整前 Liora 会等你确认。");
    if (!items.length) return void section.createDiv({ cls: "liora-manager-empty", text: "现在的知识粒度看起来正合适。" });
    const list = section.createDiv({ cls: "liora-manager-list liora-manager-list--structure" });
    for (const item of items) {
      const card = list.createDiv({ cls: "liora-manager-card is-structure" });
      card.createDiv({ cls: "liora-manager-card__badge", text: item.kind === "split" ? "建议拆分" : "建议合并" });
      card.createEl("h3", { text: item.sources.map((source) => source.title).join(" + ") });
      const proposal = item.proposal as {
        rationale?: string;
        strategy?: string;
        parent_after?: { note?: string; retains?: string[] };
        children?: Array<{ title?: string; purpose?: string; diagnostic_question?: string; source_excerpts?: string[] }>;
        migration_steps?: string[];
        failure_conditions?: string[];
        reversible?: boolean;
      };
      card.createEl("p", { text: proposal.rationale || (item.kind === "split" ? "这篇知识包含多个可独立检索的主题。" : "两篇知识高度重合。") });
      if (item.kind === "split" && proposal.children?.length) {
        const details = card.createEl("details");
        details.createEl("summary", { text: `预览如何拆成 ${proposal.children.length} 篇` });
        for (const [index, child] of proposal.children.entries()) {
          const childPlan = details.createDiv({ cls: "liora-diff is-create" });
          childPlan.createEl("strong", { text: `${index + 1}. ${child.title || "未命名子知识"}` });
          childPlan.createEl("p", { text: child.purpose || "形成可单独检索的知识单元。" });
          if (child.diagnostic_question) childPlan.createEl("p", { text: `拆分后的检查问题：${child.diagnostic_question}` });
          const excerpts = child.source_excerpts ?? [];
          if (excerpts.length) childPlan.createEl("pre", { text: excerpts.map((excerpt) => `• ${excerpt}`).join("\n") });
        }
        if (proposal.migration_steps?.length) {
          details.createEl("h4", { text: "执行步骤" });
          const steps = details.createEl("ol");
          for (const step of proposal.migration_steps) steps.createEl("li", { text: step });
        }
        if (proposal.failure_conditions?.length) {
          details.createEl("h4", { text: "不应拆分的情况" });
          const failures = details.createEl("ul");
          for (const condition of proposal.failure_conditions) failures.createEl("li", { text: condition });
        }
        if (proposal.parent_after?.note) details.createEl("p", { text: `安全策略：${proposal.parent_after.note}` });
      }
      this.actions(card, [
        [item.kind === "split" ? "确认拆分" : "确认合并", async () => this.plugin.createKnowledgeService().updateGranularity(item.id, "apply"), "primary"],
        ["保持现在这样", async () => this.plugin.createKnowledgeService().updateGranularity(item.id, "reject"), "quiet"]
      ]);
    }
  }

  private renderHierarchy(root: HTMLElement, items: Array<{ parent: { title: string; path: string }; child: { title: string; path: string } }>): void {
    const section = this.section(root, "KNOWLEDGE TREE", "知识层级", items.length, "从主题到细节，查看知识之间的父子脉络。点击名称可以打开原笔记。");
    section.addClass("liora-manager__section--tree");
    if (!items.length) return void section.createDiv({ cls: "liora-manager-empty", text: "还没有形成 Parent / Child 知识树。" });
    const tree = section.createDiv({ cls: "liora-hierarchy" });
    for (const edge of items) {
      const row = tree.createDiv({ cls: "liora-hierarchy__row" });
      const parent = row.createEl("button", { text: edge.parent.title });
      const arrow = row.createSpan();
      setIcon(arrow, "arrow-right");
      const child = row.createEl("button", { text: edge.child.title });
      parent.addEventListener("click", () => void this.plugin.createKnowledgeService().openKnowledge(edge.parent.path));
      child.addEventListener("click", () => void this.plugin.createKnowledgeService().openKnowledge(edge.child.path));
    }
  }

  private actions(card: HTMLElement, actions: Array<[string, () => Promise<void>, ActionTone?]>): void {
    const row = card.createDiv({ cls: "liora-manager-card__actions" });
    for (const [label, action, tone = "quiet"] of actions) {
      const button = row.createEl("button", { cls: `is-${tone}`, text: label });
      button.addEventListener("click", () => {
        button.disabled = true;
        void action().then(async () => {
          new Notice(`${label}，Liora 记住啦。`);
          await this.render();
        }).catch((error) => {
          button.disabled = false;
          new Notice(error instanceof Error ? error.message : "Liora 暂时没处理成功。", 6000);
        });
      });
    }
  }
}
