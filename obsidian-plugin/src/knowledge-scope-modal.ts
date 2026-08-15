import { Modal, Notice, setIcon } from "obsidian";
import type LioraKnowledgePlugin from "./main";
import { isManagedKnowledgePath } from "./knowledge-path-filter";
import {
  applyFolderDecision,
  collectKnowledgeFolders,
  folderDecision,
  type ScopeDecision
} from "./knowledge-scope-model";

export class KnowledgeScopeModal extends Modal {
  private included: string[] = [];
  private excluded: string[] = [];

  constructor(private readonly plugin: LioraKnowledgePlugin) {
    super(plugin.app);
    this.included = [...plugin.settings.includedFolders];
    this.excluded = [...plugin.settings.excludedFolders];
  }

  async onOpen(): Promise<void> {
    this.modalEl.addClass("liora-scope-modal");
    this.render(true);
    try {
      const scope = await this.plugin.createKnowledgeService().loadKnowledgeScope();
      this.included = scope.includedFolders;
      this.excluded = scope.excludedFolders;
      await this.plugin.saveKnowledgeScope(this.included, this.excluded);
      this.render(false);
    } catch {
      this.render(false, "Liora 当前未连接，显示的是上次保存的范围；连接后才能应用到知识索引。");
    }
  }

  private render(loading = false, notice = ""): void {
    const root = this.contentEl;
    root.empty();
    const header = root.createDiv({ cls: "liora-scope__header" });
    const mark = header.createSpan({ cls: "liora-scope__mark" });
    setIcon(mark, "list-tree");
    const copy = header.createDiv();
    copy.createDiv({ cls: "liora-scope__eyebrow", text: "KNOWLEDGE SCOPE" });
    copy.createEl("h2", { text: "哪些内容交给 Liora 管理" });
    root.createEl("p", {
      cls: "liora-scope__intro",
      text: "普通文件夹默认纳入；Copilot 与 Templates 默认排除。子文件夹会继承父级决定，也可以单独覆盖。"
    });
    if (loading) {
      root.createDiv({ cls: "liora-scope__notice", text: "正在读取当前管理范围…" });
      return;
    }
    if (notice) root.createDiv({ cls: "liora-scope__notice is-warning", text: notice });

    const markdownPaths = this.app.vault.getMarkdownFiles().map((file) => file.path);
    const folders = collectKnowledgeFolders(markdownPaths);
    const list = root.createDiv({ cls: "liora-scope__list" });
    if (!folders.length) list.createDiv({ cls: "liora-scope__empty", text: "Vault 里还没有可确认的文件夹。" });
    for (const folder of folders) this.renderFolder(list, folder);

    const footer = root.createDiv({ cls: "liora-scope__footer" });
    footer.createEl("p", { text: "保存后会立即重建索引；被排除的内容不会参与搜索、统计、关联或回顾。" });
    const cancel = footer.createEl("button", { cls: "mod-muted", text: "取消", attr: { type: "button" } });
    cancel.addEventListener("click", () => this.close());
    const save = footer.createEl("button", { cls: "mod-cta", text: "保存并重建索引", attr: { type: "button" } });
    save.addEventListener("click", () => void this.save(save));
  }

  private renderFolder(list: HTMLElement, folder: string): void {
    const row = list.createDiv({ cls: "liora-scope-row" });
    row.style.setProperty("--liora-scope-depth", String(Math.max(0, folder.split("/").length - 1)));
    const icon = row.createSpan({ cls: "liora-scope-row__icon" });
    setIcon(icon, "folder");
    const copy = row.createDiv({ cls: "liora-scope-row__copy" });
    copy.createEl("strong", { text: folder.split("/").pop() ?? folder });
    copy.createEl("small", { text: folder });
    const decision = folderDecision(folder, this.included, this.excluded);
    const effective = isManagedKnowledgePath(`${folder}/placeholder.md`, this.included, this.excluded);
    const state = row.createSpan({
      cls: `liora-scope-row__state ${effective ? "is-managed" : "is-excluded"}`,
      text: effective ? "当前纳入" : "当前排除"
    });
    const select = row.createEl("select", { attr: { "aria-label": `${folder} 的知识管理范围` } });
    select.createEl("option", { value: "inherit", text: "跟随默认或父级" });
    select.createEl("option", { value: "include", text: "纳入管理" });
    select.createEl("option", { value: "exclude", text: "不纳入管理" });
    select.value = decision;
    select.addEventListener("change", () => {
      const next = applyFolderDecision(folder, select.value as ScopeDecision, this.included, this.excluded);
      this.included = next.included;
      this.excluded = next.excluded;
      this.render(false);
    });
  }

  private async save(button: HTMLButtonElement): Promise<void> {
    button.disabled = true;
    try {
      await this.plugin.createKnowledgeService().saveKnowledgeScope({
        includedFolders: this.included,
        excludedFolders: this.excluded
      });
      await this.plugin.saveKnowledgeScope(this.included, this.excluded);
      new Notice("知识管理范围已保存，索引也重新整理好了。");
      this.close();
    } catch (error) {
      button.disabled = false;
      new Notice(error instanceof Error ? error.message : "暂时无法保存知识管理范围。", 6000);
    }
  }
}
