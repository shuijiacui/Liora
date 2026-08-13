# Liora Knowledge for Obsidian

Liora Knowledge 为 Obsidian 注册一个 `Liora Home` 页面，并把知识问题接到 Liora 的主动复述流程：

- 当前数据源与连接状态；
- Knowledge Object 总数和未解决问题数；
- 最近更新的五个 Markdown 文件；
- 知识文件中的“尚待探索”问题；
- 点击卡片后在 Obsidian 中打开对应文件；
- 从问题卡片唤起桌宠完成复述，并按结果安排下一次出现时间。

0.4.0 完成阶段 B 与阶段 C：

- 从 Knowledge Object 的“尚待探索”生成有证据的小问题；
- 每张卡片使用包含 Liora 的动态人格标题；
- “Liora，换一个”会把当前问题移到队列后面；
- “Liora，先放一放”会把当前问题冷却三天；
- “讲给Liora听”创建复述任务，并交给桌宠独立的“回顾”气泡；
- Liora 空闲时自动打开回顾，正在处理其他内容时用角标等待，不打断当前流程；
- 知识确认后用四档手感更新下一次出现时间；
- 只保存结构化 Learning Event 和 Knowledge State，确认后仍删除原始对话；
- 支持“Liora为什么问这个？”；
- 支持打开问题对应的知识文件；
- Knowledge Engine 离线时退回 Vault 本地只读视图，涉及调度与唤起的动作会明确提示断线。

当前源码继续实现阶段 D 至 G：

- 自动提取 Claim、检索候选，并判断 CREATE / UPDATE，避免明显重复知识；
- 低风险改动自动完成，不确定或结构性改动进入 ChangeSet 审核，可拒绝和回滚；
- 本地语义检索、Hard / Soft Connection、跨知识提问和知识问答；
- 可解释的 Split / Merge 候选、Parent / Child 与多尺度知识结构。

## 开发

不要在正式 Vault 中开发插件。先创建一个专用测试 Vault，然后在本目录运行：

```powershell
npm install
npm run check
```

把以下文件与角色资源复制到测试 Vault：

```text
<测试 Vault>/.obsidian/plugins/liora-knowledge/
├── main.js
├── manifest.json
├── styles.css
└── assets/
    ├── idle.png
    ├── asking.png
    ├── happy.png
    ├── running.png
    ├── greeting.png
    ├── celebrating.png
    └── home-banner.png
```

然后在 Obsidian 的“设置 → 第三方插件”中启用 `Liora Knowledge`。点击左侧脑形图标，或者从命令面板执行“Liora Knowledge: 打开知识首页”。

开发时可以执行 `npm run dev` 持续编译。修改 `manifest.json` 后需要重新启动 Obsidian；普通代码修改后重新加载插件即可。

## 数据源

插件会优先读取 Liora 发布在本机用户数据目录中的临时连接信息，自动连接正在运行的 Knowledge Engine。Liora 没有运行时，插件直接通过 Obsidian API 读取当前 Vault。

也可以在插件设置中填写本机 Knowledge Engine 地址和 `X-Liora-Token`。两项均填写并连接成功后，首页会读取现有 `/health` 和 `/api/knowledge` 接口；连接失败时自动退回 Vault 只读模式。

当前 Vault 中的每一篇 Markdown 都是知识对象。`type`、`source` 和 `liora_id` 只描述知识身份与来源，不再作为是否纳入管理的资格判断。
