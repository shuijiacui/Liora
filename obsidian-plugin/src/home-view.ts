import { ItemView, Modal, Notice, setIcon, WorkspaceLeaf } from "obsidian";
import type LioraKnowledgePlugin from "./main";
import type { DashboardData, DashboardItem } from "./dashboard-model";
import type { ReflectionPrompt } from "./question-card-model";
import { voiceFor } from "./question-card-model";
import type { LioraMemo } from "./memo-model";
import { localDateKey, memosForDate, weekAround } from "./memo-model";

export const LIORA_HOME_VIEW = "liora-knowledge-home";

interface AppWithCommands {
  commands: { executeCommandById(id: string): boolean };
}

function formatDate(value: string): string {
  if (!value) return "刚刚";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "最近";
  return new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" }).format(parsed);
}

function iconButton(parent: HTMLElement, icon: string, label: string, cls = ""): HTMLButtonElement {
  const button = parent.createEl("button", {
    cls: `liora-icon-button ${cls}`.trim(),
    attr: { "aria-label": label, title: label }
  });
  setIcon(button, icon);
  return button;
}

class MemoModal extends Modal {
  constructor(
    private readonly plugin: LioraKnowledgePlugin,
    private readonly date: string,
    private readonly onSaved: () => void
  ) {
    super(plugin.app);
  }

  onOpen(): void {
    this.modalEl.addClass("liora-memo-modal");
    const { contentEl } = this;
    contentEl.createDiv({ cls: "liora-memo-modal__eyebrow", text: "A NOTE FOR LATER" });
    contentEl.createEl("h2", { text: "写给之后的自己" });
    contentEl.createEl("p", { text: "简单记下一件事，到那天我会把它放回桌面。" });

    const form = contentEl.createEl("form", { cls: "liora-memo-form" });
    const text = form.createEl("textarea", {
      attr: { placeholder: "例如：晚上重新看一遍 Attention 的边界条件", maxlength: "160", rows: "3" }
    });
    const fields = form.createDiv({ cls: "liora-memo-form__fields" });
    const dateLabel = fields.createEl("label");
    dateLabel.createSpan({ text: "日期" });
    const dateInput = dateLabel.createEl("input", { attr: { type: "date", value: this.date } });
    const timeLabel = fields.createEl("label");
    timeLabel.createSpan({ text: "时间（可不填）" });
    const timeInput = timeLabel.createEl("input", { attr: { type: "time" } });
    const actions = form.createDiv({ cls: "liora-memo-form__actions" });
    const cancel = actions.createEl("button", { text: "取消", attr: { type: "button" } });
    const save = actions.createEl("button", { cls: "mod-cta", text: "交给 Liora", attr: { type: "submit" } });
    cancel.addEventListener("click", () => this.close());
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const value = text.value.trim();
      if (!value || !dateInput.value) return void new Notice("先写下一件想记住的事吧。");
      save.disabled = true;
      await this.plugin.addMemo({
        id: `memo-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        text: value,
        date: dateInput.value,
        time: timeInput.value,
        done: false,
        createdAt: new Date().toISOString()
      });
      new Notice("好，我替你把这张小纸条收好了。");
      this.close();
      this.onSaved();
    });
    window.setTimeout(() => text.focus(), 0);
  }

  onClose(): void {
    this.contentEl.empty();
  }
}

export class LioraHomeView extends ItemView {
  private promptIndex = 0;
  private promptVariation = 0;
  private reasonVisible = false;
  private selectedDate = localDateKey(new Date());
  private dashboard: DashboardData | null = null;
  private prompts: ReflectionPrompt[] = [];
  private resizeObserver: ResizeObserver | null = null;

  constructor(leaf: WorkspaceLeaf, private readonly plugin: LioraKnowledgePlugin) {
    super(leaf);
  }

  getViewType(): string { return LIORA_HOME_VIEW; }
  getDisplayText(): string { return "Liora Home"; }
  getIcon(): string { return "home"; }

  async onOpen(): Promise<void> {
    this.containerEl.addClass("liora-home-host");
    this.resizeObserver = new ResizeObserver(([entry]) => {
      const width = entry?.contentRect.width ?? this.contentEl.clientWidth;
      const height = entry?.contentRect.height ?? this.contentEl.clientHeight;
      this.contentEl.toggleClass("is-compact", width < 780);
      this.contentEl.toggleClass("is-narrow", width < 540);
      this.contentEl.toggleClass("is-short", height < 760);
      this.contentEl.toggleClass("is-very-short", height < 620);
    });
    this.resizeObserver.observe(this.contentEl);
    await this.render();
  }

  async onClose(): Promise<void> {
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.containerEl.removeClass("liora-home-host");
  }

  async render(): Promise<void> {
    const root = this.contentEl;
    root.empty();
    root.addClass("liora-home");
    const loading = root.createDiv({ cls: "liora-home__loading", text: "Liora 正在把书桌收拾好…" });
    try {
      const service = this.plugin.createKnowledgeService();
      this.dashboard = await service.loadDashboard();
      this.prompts = await service.loadReflectionPrompts(this.dashboard);
      root.empty();
      this.renderHome(root, this.dashboard, this.prompts);
    } catch (error) {
      loading.setText(error instanceof Error ? error.message : "Liora 暂时打不开书房。");
      loading.addClass("liora-home__error");
    }
  }

  private renderHome(root: HTMLElement, data: DashboardData, prompts: ReflectionPrompt[]): void {
    root.toggleClass("is-offline", !data.engineConnected);
    const canvas = root.createDiv({ cls: "liora-home__canvas" });
    const topbar = canvas.createDiv({ cls: "liora-home__topbar" });
    const brand = topbar.createDiv({ cls: "liora-brand" });
    brand.createDiv({ cls: "liora-brand__mark", text: "L" });
    const brandCopy = brand.createDiv();
    brandCopy.createDiv({ cls: "liora-brand__name", text: "LIORA" });
    brandCopy.createDiv({ cls: "liora-brand__caption", text: "你的知识小屋" });
    const topActions = topbar.createDiv({ cls: "liora-home__top-actions" });
    const status = topActions.createDiv({ cls: "liora-connection" });
    status.createSpan({ cls: "liora-connection__dot" });
    const engineLabel = data.embedding?.loaded
      ? "已连接 · 本地语义"
      : data.engineConnected
        ? "已连接 · 兼容检索"
        : "Vault 模式";
    const statusText = status.createSpan({ text: engineLabel });
    if (data.embedding?.model) statusText.setAttr("title", data.embedding.model);
    const refresh = iconButton(topActions, "refresh-cw", "刷新首页");
    refresh.addEventListener("click", () => {
      this.promptIndex = 0;
      this.promptVariation = 0;
      this.reasonVisible = false;
      void this.render();
    });
    const settings = iconButton(topActions, "settings-2", "插件设置");
    settings.addEventListener("click", () => {
      (this.plugin.app as unknown as AppWithCommands).commands.executeCommandById("app:open-settings");
    });
    this.renderTopNavigation(topbar);

    const columns = canvas.createDiv({ cls: "liora-home__columns" });
    const main = columns.createEl("main", { cls: "liora-home__main" });
    const banner = main.createDiv({ cls: "liora-home-banner", attr: { role: "img", "aria-label": "Liora 的知识花园" } });
    banner.style.setProperty("--liora-banner-image", `url("${this.plugin.assetResource("home-banner.png")}")`);
    this.renderDialogue(main, prompts);

    const side = columns.createEl("aside", { cls: "liora-home__calendar-column" });
    this.renderDayPanel(side, data);
  }

  private renderTopNavigation(topbar: HTMLElement): void {
    const navigation = topbar.createEl("nav", { cls: "liora-top-nav", attr: { "aria-label": "Liora 常用功能" } });
    const actions = [
      { icon: "sticky-note", label: "随手记", run: () => new MemoModal(this.plugin, this.selectedDate, () => void this.render()).open() },
      { icon: "message-circle-question", label: "问知识库", run: () => this.focusAsk() },
      { icon: "search", label: "搜索", run: () => (this.plugin.app as unknown as AppWithCommands).commands.executeCommandById("global-search:open") },
      { icon: "file-plus-2", label: "新建笔记", run: () => (this.plugin.app as unknown as AppWithCommands).commands.executeCommandById("file-explorer:new-file") },
      { icon: "library-big", label: "知识管理", run: () => void this.plugin.activateManager() }
    ];
    for (const action of actions) {
      const button = navigation.createEl("button", { attr: { title: action.label } });
      setIcon(button.createSpan(), action.icon);
      button.createSpan({ text: action.label });
      button.addEventListener("click", action.run);
    }
  }

  private renderDialogue(parent: HTMLElement, prompts: ReflectionPrompt[]): void {
    const section = parent.createEl("section", { cls: "liora-dialogue" });
    const heading = section.createDiv({ cls: "liora-dialogue__heading" });
    const copy = heading.createDiv();
    copy.createDiv({ cls: "liora-section-kicker", text: "A QUIET CONVERSATION" });
    copy.createEl("h2", { text: "与 Liora 一起想一想" });
    heading.createSpan({ text: "一边回想，一边寻找" });
    const body = section.createDiv({ cls: "liora-dialogue__body" });
    const recall = body.createDiv({ cls: "liora-dialogue__recall" });
    const recallLabel = recall.createDiv({ cls: "liora-dialogue__direction" });
    setIcon(recallLabel.createSpan(), "message-circle-heart");
    recallLabel.createSpan({ text: "Liora 问你" });
    this.renderPrompt(recall, prompts);
    const ask = body.createDiv({ cls: "liora-dialogue__ask" });
    const askLabel = ask.createDiv({ cls: "liora-dialogue__direction" });
    setIcon(askLabel.createSpan(), "book-open-text");
    askLabel.createSpan({ text: "你问知识库" });
    this.renderAsk(ask);
  }

  private renderPrompt(parent: HTMLElement, prompts: ReflectionPrompt[]): HTMLElement {
    const area = parent.createDiv({ cls: "liora-reflection" });
    if (!prompts.length) {
      area.createDiv({ cls: "liora-reflection__kicker", text: "TODAY · ALL CLEAR" });
      area.createEl("h2", { text: "今天没有一定要回答的问题。" });
      area.createEl("p", { text: "可以随手记下一点新想法，或者去翻翻最近的知识。" });
      return area;
    }
    const safeIndex = ((this.promptIndex % prompts.length) + prompts.length) % prompts.length;
    const prompt = prompts[safeIndex];
    const voice = voiceFor(prompt.id, this.promptVariation);
    const promptVoice = prompt.kind === "diagnostic"
      ? { eyebrow: "Liora 想确认一小块掌握情况", primaryAction: "开始 3 分钟诊断" }
      : prompt.kind === "transfer_check"
        ? { eyebrow: "Liora 想看看这项知识能否迁移", primaryAction: "开始迁移检验" }
        : voice;
    area.createDiv({ cls: "liora-reflection__kicker", text: promptVoice.eyebrow });
    area.createDiv({ cls: "liora-reflection__topic", text: prompt.title });
    area.createEl("p", { cls: "liora-reflection__question", text: prompt.prompt });
    if (this.reasonVisible) {
      const reason = area.createDiv({ cls: "liora-reflection__reason" });
      setIcon(reason.createSpan(), "lightbulb");
      reason.createSpan({ text: prompt.reason });
    }
    const actions = area.createDiv({ cls: "liora-reflection__actions" });
    const primary = actions.createEl("button", { cls: "liora-button-primary", text: promptVoice.primaryAction });
    primary.addEventListener("click", async () => {
      primary.disabled = true;
      const result = await this.plugin.createKnowledgeService().startReflectionPrompt(prompt.id);
      new Notice(result.message, result.ok ? 3000 : 5000);
      primary.disabled = false;
    });
    const next = actions.createEl("button", { cls: "liora-button-secondary", text: "换一个" });
    next.addEventListener("click", async () => {
      if (prompts.length > 1) {
        const result = await this.plugin.createKnowledgeService().skipReflectionPrompt(prompt.id);
        if (!result.ok) new Notice(result.message, 4000);
        this.promptIndex = (safeIndex + 1) % prompts.length;
      }
      this.promptVariation += 1;
      this.reasonVisible = false;
      area.empty();
      this.renderPromptInto(area, prompts);
    });
    const details = actions.createDiv({ cls: "liora-reflection__links" });
    const reason = details.createEl("button", { text: this.reasonVisible ? "收起线索" : "为什么问这个？" });
    reason.addEventListener("click", () => {
      this.reasonVisible = !this.reasonVisible;
      area.empty();
      this.renderPromptInto(area, prompts);
    });
    const open = details.createEl("button", { text: "查看原知识" });
    open.addEventListener("click", async () => {
      const opened = prompt.path ? await this.plugin.createKnowledgeService().openKnowledge(prompt.path) : false;
      if (!opened) new Notice(`找不到这段知识：${prompt.path || prompt.title}`);
    });
    const snooze = details.createEl("button", { text: "三天后再问" });
    snooze.addEventListener("click", async () => {
      const result = await this.plugin.createKnowledgeService().snoozeReflectionPrompt(prompt.id, 3);
      new Notice(result.message, result.ok ? 3000 : 5000);
      if (result.ok) {
        this.prompts = prompts.filter((item) => item.id !== prompt.id);
        area.empty();
        this.renderPromptInto(area, this.prompts);
      }
    });
    return area;
  }

  private renderPromptInto(area: HTMLElement, prompts: ReflectionPrompt[]): void {
    const parent = area.parentElement;
    if (!parent) return;
    const next = area.nextSibling;
    area.remove();
    const replacement = this.renderPrompt(parent, prompts);
    if (next) parent.insertBefore(replacement, next);
  }

  private renderDayPanel(parent: HTMLElement, data: DashboardData): void {
    const panel = parent.createEl("aside", { cls: "liora-day" });
    this.renderDayPanelContent(panel, data);
  }

  private renderDayPanelContent(panel: HTMLElement, data: DashboardData): void {
    panel.createDiv({ cls: "liora-day__eyebrow", text: "THIS WEEK" });
    const selected = new Date(`${this.selectedDate}T12:00:00`);
    panel.createEl("h2", {
      text: new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", weekday: "long" }).format(selected)
    });
    const week = panel.createDiv({ cls: "liora-week" });
    for (const day of weekAround(selected)) {
      const key = localDateKey(day);
      const button = week.createEl("button", { cls: key === this.selectedDate ? "is-selected" : "" });
      button.createSpan({ text: "一二三四五六日"[(day.getDay() + 6) % 7] });
      button.createEl("strong", { text: String(day.getDate()) });
      if (this.plugin.settings.memos.some((memo) => memo.date === key && !memo.done)) {
        button.createEl("i", { cls: "liora-week__dot" });
      }
      button.addEventListener("click", () => {
        this.selectedDate = key;
        panel.empty();
        this.renderDayPanelContent(panel, data);
      });
    }
    this.renderMemos(panel);
    this.renderRecent(panel, data, true);
  }

  private renderMemos(panel: HTMLElement): void {
    const heading = panel.createDiv({ cls: "liora-memo-heading" });
    heading.createEl("h3", { text: "这天的小纸条" });
    const add = iconButton(heading, "plus", "添加备忘", "liora-memo-add");
    add.createSpan({ text: "添加" });
    add.addEventListener("click", () => new MemoModal(this.plugin, this.selectedDate, () => void this.render()).open());
    const list = panel.createDiv({ cls: "liora-memos" });
    const memos = memosForDate(this.plugin.settings.memos, this.selectedDate);
    if (!memos.length) {
      const empty = list.createDiv({ cls: "liora-memos__empty" });
      empty.createDiv({ text: "这天还没有纸条" });
      empty.createSpan({ text: "有事情想记住时，就交给我吧。" });
      return;
    }
    for (const memo of memos) this.renderMemo(list, memo);
  }

  private renderMemo(parent: HTMLElement, memo: LioraMemo): void {
    const row = parent.createDiv({ cls: memo.done ? "liora-memo is-done" : "liora-memo" });
    const check = row.createEl("button", { cls: "liora-memo__check", attr: { "aria-label": memo.done ? "标记未完成" : "标记完成" } });
    setIcon(check, memo.done ? "check" : "circle");
    check.addEventListener("click", async () => {
      await this.plugin.toggleMemo(memo.id);
      void this.render();
    });
    const copy = row.createDiv({ cls: "liora-memo__copy" });
    copy.createSpan({ cls: "liora-memo__time", text: memo.time || "随时" });
    copy.createDiv({ text: memo.text });
    const remove = iconButton(row, "x", "删除备忘", "liora-memo__delete");
    remove.addEventListener("click", async () => {
      await this.plugin.deleteMemo(memo.id);
      void this.render();
    });
  }

  private renderAsk(parent: HTMLElement): void {
    const section = parent.createEl("section", { cls: "liora-ask-home" });
    section.createEl("h3", { text: "问问我的知识库" });
    section.createEl("p", { text: "从过往笔记中寻找答案，并附上参考来源。" });
    const form = section.createEl("form");
    const input = form.createEl("input", {
      cls: "liora-ask-home__input",
      attr: { type: "text", placeholder: "例如：我以前如何理解 Attention？", maxlength: "500" }
    });
    const submit = iconButton(form, "arrow-up", "发送");
    const answer = section.createDiv({ cls: "liora-ask-home__answer" });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const question = input.value.trim();
      if (!question) return;
      submit.disabled = true;
      answer.setText("Liora 正在沿着知识线索找一找…");
      try {
        const result = await this.plugin.createKnowledgeService().askKnowledge(question);
        answer.empty();
        answer.createEl("p", { text: result.answer });
        for (const evidence of result.evidence ?? []) {
          const link = answer.createEl("button", { text: `${evidence.title} · ${Math.round(evidence.score * 100)}%` });
          link.addEventListener("click", () => void this.plugin.createKnowledgeService().openKnowledge(evidence.path));
        }
      } catch (error) {
        answer.setText(error instanceof Error ? error.message : "暂时没有找到答案。");
      } finally {
        submit.disabled = false;
      }
    });
  }

  private focusAsk(): void {
    const input = this.contentEl.querySelector<HTMLInputElement>(".liora-ask-home__input");
    input?.scrollIntoView({ behavior: "smooth", block: "center" });
    input?.focus();
  }

  private renderRecent(root: HTMLElement, data: DashboardData, rail = false): void {
    const section = root.createEl("section", { cls: rail ? "liora-recent liora-recent--rail" : "liora-recent" });
    const heading = section.createDiv({ cls: "liora-recent__heading" });
    const copy = heading.createDiv();
    copy.createDiv({ cls: "liora-section-kicker", text: "RECENT MEMORIES" });
    copy.createEl("h2", { text: "最近的知识" });
    heading.createSpan({ text: `${data.recent.length} 段` });
    if (!data.recent.length) {
      section.createDiv({ cls: "liora-recent__empty", text: "把 Markdown 放进 Vault 后，我会从这里开始认识你的知识。" });
      return;
    }
    const list = section.createDiv({ cls: "liora-recent__list" });
    for (const item of data.recent) this.renderKnowledgeRow(list, item);
  }

  private renderKnowledgeRow(parent: HTMLElement, item: DashboardItem): void {
    const button = parent.createEl("button", { cls: "liora-knowledge-row" });
    const ornament = button.createSpan({ cls: "liora-knowledge-row__ornament" });
    setIcon(ornament, "sparkle");
    const content = button.createDiv({ cls: "liora-knowledge-row__content" });
    content.createEl("h3", { text: item.title });
    if (item.summary) content.createEl("p", { text: item.summary });
    content.createSpan({ text: item.path });
    const meta = button.createDiv({ cls: "liora-knowledge-row__meta" });
    meta.createSpan({ text: formatDate(item.updatedAt) });
    setIcon(meta.createSpan(), "arrow-up-right");
    button.addEventListener("click", async () => {
      if (!await this.plugin.createKnowledgeService().openKnowledge(item.path)) {
        new Notice(`找不到这段知识：${item.path}`);
      }
    });
  }
}
