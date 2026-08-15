import { Plugin, WorkspaceLeaf } from "obsidian";
import { KnowledgeService, LioraSettings } from "./knowledge-service";
import { LIORA_HOME_VIEW, LioraHomeView } from "./home-view";
import { LIORA_MANAGER_VIEW, LioraManagerView } from "./manager-view";
import { LioraSettingTab } from "./settings";
import type { LioraMemo } from "./memo-model";
import { normalizeMemos } from "./memo-model";

const DEFAULT_SETTINGS: LioraSettings = {
  engineUrl: "",
  accessToken: "",
  memos: [],
  includedFolders: [],
  excludedFolders: []
};

export default class LioraKnowledgePlugin extends Plugin {
  settings: LioraSettings = DEFAULT_SETTINGS;

  async onload(): Promise<void> {
    await this.loadSettings();
    this.registerView(LIORA_HOME_VIEW, (leaf) => new LioraHomeView(leaf, this));
    this.registerView(LIORA_MANAGER_VIEW, (leaf) => new LioraManagerView(leaf, this));
    this.addRibbonIcon("home", "打开 Liora Home", () => void this.activateHome());
    this.addCommand({
      id: "open-liora-home",
      name: "打开知识首页",
      callback: () => void this.activateHome()
    });
    this.addCommand({
      id: "open-liora-manager",
      name: "打开 Liora 管理台",
      callback: () => void this.activateManager()
    });
    this.addSettingTab(new LioraSettingTab(this.app, this));
  }

  async onunload(): Promise<void> {
    this.app.workspace.detachLeavesOfType(LIORA_HOME_VIEW);
    this.app.workspace.detachLeavesOfType(LIORA_MANAGER_VIEW);
  }

  createKnowledgeService(): KnowledgeService {
    return new KnowledgeService(this.app, this.settings);
  }

  characterResource(state: "idle" | "asking" | "happy" | "running" | "greeting" | "celebrating"): string {
    return this.assetResource(`${state}.png`);
  }

  assetResource(filename: string): string {
    const pluginDir = this.manifest.dir ?? `${this.app.vault.configDir}/plugins/${this.manifest.id}`;
    return this.app.vault.adapter.getResourcePath(`${pluginDir}/assets/${filename}`);
  }

  async activateHome(): Promise<void> {
    const existing = this.app.workspace.getLeavesOfType(LIORA_HOME_VIEW)[0];
    let leaf: WorkspaceLeaf;
    if (existing) {
      leaf = existing;
    } else {
      leaf = this.app.workspace.getLeaf("tab");
      await leaf.setViewState({ type: LIORA_HOME_VIEW, active: true });
    }
    await this.app.workspace.revealLeaf(leaf);
  }

  async activateManager(): Promise<void> {
    const existing = this.app.workspace.getLeavesOfType(LIORA_MANAGER_VIEW)[0];
    const leaf = existing ?? this.app.workspace.getLeaf("tab");
    if (!existing) await leaf.setViewState({ type: LIORA_MANAGER_VIEW, active: true });
    await this.app.workspace.revealLeaf(leaf);
  }

  async loadSettings(): Promise<void> {
    const stored = await this.loadData() as Partial<LioraSettings> | null;
    this.settings = {
      ...DEFAULT_SETTINGS,
      ...(stored ?? {}),
      memos: normalizeMemos(stored?.memos),
      includedFolders: Array.isArray(stored?.includedFolders) ? stored.includedFolders.map(String) : [],
      excludedFolders: Array.isArray(stored?.excludedFolders) ? stored.excludedFolders.map(String) : []
    };
  }

  async addMemo(memo: LioraMemo): Promise<void> {
    this.settings.memos = [...this.settings.memos, memo];
    await this.saveData(this.settings);
  }

  async toggleMemo(id: string): Promise<void> {
    this.settings.memos = this.settings.memos.map((memo) =>
      memo.id === id ? { ...memo, done: !memo.done } : memo);
    await this.saveData(this.settings);
  }

  async deleteMemo(id: string): Promise<void> {
    this.settings.memos = this.settings.memos.filter((memo) => memo.id !== id);
    await this.saveData(this.settings);
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
    const view = this.app.workspace.getLeavesOfType(LIORA_HOME_VIEW)[0]?.view;
    if (view instanceof LioraHomeView) await view.render();
  }

  async saveKnowledgeScope(includedFolders: string[], excludedFolders: string[]): Promise<void> {
    this.settings.includedFolders = includedFolders;
    this.settings.excludedFolders = excludedFolders;
    await this.saveSettings();
  }
}
