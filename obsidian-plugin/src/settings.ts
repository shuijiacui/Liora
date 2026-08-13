import { App, PluginSettingTab, Setting } from "obsidian";
import type LioraKnowledgePlugin from "./main";

export class LioraSettingTab extends PluginSettingTab {
  constructor(app: App, private readonly plugin: LioraKnowledgePlugin) {
    super(app, plugin);
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.createEl("h2", { text: "Liora Knowledge" });
    containerEl.createEl("p", {
      text: "不填写连接信息时，插件会自动发现正在运行的 Liora；断线时仍会以只读方式展示当前 Vault。"
    });

    new Setting(containerEl)
      .setName("Knowledge Engine 地址")
      .setDesc("高级选项。通常留空即可自动发现 Liora；插件只允许连接本机地址。")
      .addText((text) => text
        .setPlaceholder("http://127.0.0.1:43117")
        .setValue(this.plugin.settings.engineUrl)
        .onChange(async (value) => {
          this.plugin.settings.engineUrl = value.trim();
          await this.plugin.saveSettings();
        }));

    new Setting(containerEl)
      .setName("本地访问令牌")
      .setDesc("高级选项。与手动地址配套使用，不是模型 API Key。")
      .addText((text) => {
        text.inputEl.type = "password";
        text
          .setPlaceholder("X-Liora-Token")
          .setValue(this.plugin.settings.accessToken)
          .onChange(async (value) => {
            this.plugin.settings.accessToken = value.trim();
            await this.plugin.saveSettings();
          });
      });
  }
}
