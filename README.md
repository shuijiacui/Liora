# Liora

<p align="center">
  <img src="assets/character/idle.png" width="180" alt="Liora 桌面角色">
</p>

<p align="center">
  <strong>让知识从你每天说过的话里，慢慢长出来。</strong>
</p>

<p align="center">
  一个通过追问、解释与共同修改，陪你构建个人知识库的桌面 AI 伙伴。
</p>

<p align="center">
  <a href="https://github.com/shuijiacui/Liora/releases/latest"><strong>下载 Windows 最新版</strong></a>
  ·
  <a href="#五步完成一次知识沉淀">使用指南</a>
  ·
  <a href="#从源码运行">从源码运行</a>
</p>

> Liora 生成的不是对话记录或聊天摘要，而是一份脱离对话也能独立阅读、复习和继续完善的完整知识文件。

Liora 会安静地待在桌面上。你可以从一个刚学会的概念、一段没有想通的问题，或今天值得记住的经历开始。它通常用一个自然的问题帮助你说清自己的理解；当你拿不准、记不清或可能理解有误时，它也会先给出必要的解释、纠正或查证，而不是机械地继续追问。

对话结束后，Liora 会围绕真正的知识主题补充核心原理、完整推理、例子、边界与延伸。保存前，你既可以亲自编辑每一部分，也可以告诉 Liora 应该怎样修改，直到它成为一份你愿意长期保留的知识文件。

项目目前处于积极开发的原型阶段，主要面向 Windows 桌面；同时提供适配通用 Linux 小屏设备的运行模式。

## 一分钟看懂 Liora

```text
说出正在思考的内容
        ↓
Liora 追问；必要时解释、纠正或联网查证
        ↓
围绕核心主题生成完整知识文件
        ↓
自己编辑，或提出意见让 Liora 再次修改
        ↓
确认后保存到本地知识库或 Obsidian
```

它和普通聊天助手的区别在于：

| 普通聊天或自动摘要 | Liora |
|---|---|
| 重点是尽快回答问题 | 重点是帮助你形成自己的理解 |
| 将对话压缩成一份记录 | 从对话识别主题，再构建独立知识文件 |
| 生成后通常只能接受或重来 | 可以逐项手动编辑，也可以用修改意见反复协作 |
| 一直追问，或直接给出长篇答案 | 能追问，也会在你拿不准时提供恰到好处的帮助 |
| 内容留在单次聊天中 | 确认后进入可搜索、可修订的长期知识库 |

<details>
<summary><strong>展开：用五张图了解 Liora</strong></summary>

<p align="center">
  <img src="Liora01.png" width="48%" alt="让知识从每天说过的话里慢慢长出来">
  <img src="Liora02.png" width="48%" alt="桌面唤醒与每日节奏">
</p>
<p align="center">
  <img src="Liora03.png" width="48%" alt="从对话构建核心理解与逻辑链">
  <img src="Liora04.png" width="48%" alt="将知识保存到 Obsidian">
</p>
<p align="center">
  <img src="Liora05.png" width="48%" alt="让知识库顺着人的认知过程自然生长">
</p>

</details>

## 五步完成一次知识沉淀

### 1. 开始一轮思考

点击桌面角色，或把鼠标移到角色上并选择“反思”。输入文字，也可以点击“开始说”，用最长一分钟的语音表达。

不用先整理好措辞。可以直接从一句很模糊的话开始，例如：

> 我大概知道 Attention 是什么，但总觉得自己没有真正说清楚。

### 2. 和 Liora 一起把问题想清楚

Liora 默认会提出当前最值得回答的一个问题，帮助你回忆、解释和连接已有知识。但追问不是硬性规则：

- 你说“我不确定”或直接询问事实时，它会先提供简短辅助。
- 发现明显概念混淆时，它会温和纠正错误前提。
- 涉及最新信息、精确数据或你明确要求搜索时，可以联网查证。
- 无需达到固定对话轮数，你决定什么时候已经聊得够了。

### 3. 点击“生成知识文件”

Liora 不会简单复述你们刚才说了什么，而会以对话揭示的主题和认知缺口为线索，构建一份完整草稿。知识文件可以包含：

- 核心理解
- 关键要点
- 原理与推理
- 例子与反例
- 延伸理解
- 边界与常见误区
- 与其他知识的联系
- 尚待探索的问题
- 最有价值的下一步
- 联网查证时使用的参考资料

没有价值的部分不会为了凑格式而强行填满；无法可靠确认的内容会留在“尚待探索”，而不是被写成确定结论。

### 4. 把草稿改成真正属于你的知识

草稿不是最终答案。点击“编辑与修改”后有两种方式：

1. **直接编辑**：逐项修改标题、核心理解、推理过程、例子、边界等内容，然后点击“保存修改”。
2. **请 Liora 修改**：写下具体意见，或使用“讲透原理”“补充例子”“核实事实”“精简表达”等快捷建议。

例如可以这样说：

> 展开第二步的推理，保留我对图书管理员的类比，再联网确认动态卷积与多头注意力的区别。

Liora 会以当前草稿为主要编辑对象，尽量保留你已经手动改好的表达。你也可以点击“继续聊聊”补充新的理解，再重新构建文件。

### 5. 确认并保存

- **这样保存**：确认当前草稿，写入长期知识记录。
- **这次不保存**：清除本轮草稿和对话，不污染知识库。
- **知识**：搜索已经确认的内容，或选择一条旧知识继续思考；再次确认后会保存为同一条知识的新版本。

## 当你拿不准时，Liora 会怎样帮助

Liora 的目标不是只做“提问机器”，也不是替你完成全部思考。它会根据当前表达选择三种方式：

| 情况 | Liora 的回应方式 |
|---|---|
| 你正在形成自己的理解 | 提出一个最有价值的自然追问 |
| 你不确定、记不清或直接询问事实 | 先给出必要的简短解释，再继续推进 |
| 涉及最新、精确或可能变化的信息 | 配置 Tavily 后搜索查证，并在知识文件中保留来源 |

联网并非每次对话都会发生。Liora 只发送当前问题所需的短查询，不发送整段反思记录；搜索不可用时会明确说明，并退回模型已有知识，不会假装已经查证。

## 其他主要能力

### 可生长的个人知识库

- 使用 SQLite 保存反思状态、草稿、已确认知识和修订版本。
- 支持中文全文搜索，以及按文件夹、标签和更新时间筛选。
- 可以从已有知识继续思考，而不是每次创建互不相关的新笔记。
- 可连接 Obsidian Vault，以 Markdown 作为长期主数据。
- 未完成的反思和待确认草稿可在重新打开 Liora 后恢复。

### 本地语音与桌面角色

- 使用 Vosk 在本地识别中英文唤醒词 “Hi Liora”。
- 使用 faster-whisper 在本地转写中文、英文和中英混说。
- 录音由“开始说 / 说完了”明确控制，唤醒后不会擅自录制正文。
- 音频只在内存中短暂存在，转写后释放，不生成录音文件。
- 透明、无边框、始终置顶，支持拖动、位置记忆、托盘和开机启动。
- 提供反思、知识和天气三个轻量入口，以及可关闭的晚间反思提醒。

## 安装 Windows 版

1. 打开 [Releases](https://github.com/shuijiacui/Liora/releases/latest)，下载 `Liora-Setup-0.2.2-x64.exe`。
2. 运行安装程序，按提示选择安装位置。
3. 当前安装包没有商业代码签名。如果 Windows SmartScreen 显示“未知发布者”，请确认文件来自本仓库的 Release 页面后再决定是否继续。

Liora 在没有云端 API Key 时仍可启动，并使用本地降级策略。要使用更完整的 AI 追问、知识构建和修改能力，请在下面的位置创建 `.env` 文件：

```text
%APPDATA%\liora-desktop-companion\.env
```

最小配置：

```dotenv
DEEPSEEK_API_KEY=你的_API_Key
```

保存后从系统托盘完全退出 Liora，再重新打开。

### 可选：启用联网查证

在同一个 `.env` 文件中加入：

```dotenv
TAVILY_API_KEY=你的_API_Key
TAVILY_BASE_URL=https://api.tavily.com
TAVILY_TIMEOUT_SECONDS=15
TAVILY_MAX_RESULTS=4
```

联网查证默认关闭。只有配置 Tavily Key 后，且用户明确要求搜索，或当前内容涉及最新信息、精确数据和明显不确定性时，Liora 才会尝试搜索。

## 连接 Obsidian

Liora 采用 **Markdown 主数据 + SQLite 运行状态与索引** 的存储方式：

1. 在系统托盘菜单中选择“连接 Obsidian 知识库…”。
2. 选择一个 Vault 的根目录。
3. 首次连接只扫描 Markdown 并建立本地索引，不会修改已有笔记。
4. 之后确认的新知识会原子写入 `00 Inbox/Liora/`。
5. 如需导出原有 SQLite 知识，选择“迁移 SQLite 知识到 Obsidian…”；Liora 会先创建一致性备份。

普通 Obsidian 笔记保持只读。只有当你明确选择一条知识继续完善，并再次确认时，Liora 才会更新由它管理的内容。

知识搜索使用 SQLite FTS5 trigram 索引标题、正文、路径和标签，支持中文连续文本。索引可以随时重建，Markdown 始终是连接 Obsidian 后的主数据。

## 隐私与数据

| 数据 | 保存或处理位置 |
|---|---|
| 唤醒词与语音转写 | 本机 Vosk / faster-whisper；不生成音频文件 |
| 临时反思与知识草稿 | Electron 用户数据目录中的 SQLite |
| 已确认知识 | SQLite，或连接后的 Obsidian Vault |
| DeepSeek / Tavily API Key | 本地 `.env`；不进入安装包、前端或 Git |
| 联网查证查询 | 仅在配置 Tavily 后发送当前问题所需的短查询 |
| 天气位置 | 本机保存缩减精度后的坐标，不发送给 DeepSeek |

Windows 默认数据目录：

```text
%APPDATA%\liora-desktop-companion\
```

重新安装或覆盖升级不会主动删除这里的知识、设置与窗口状态。

## 从源码运行

### 环境要求

- Node.js 22.12 或更高版本
- Python 3.10 或更高版本
- Windows、macOS 或 Linux；当前桌面安装包主要在 Windows 上验证

### 安装依赖和本地语音模型

```powershell
npm.cmd install
python -m pip install -r backend\requirements.txt
python scripts\setup-voice-model.py
python scripts\setup-wake-models.py
```

语音模型首次下载需要数百 MB，之后会从项目的 `.models` 目录读取。可以设置 `LIORA_WHISPER_MODEL=base`，使用体积更小但准确率较低的听写模型。

复制 `.env.example` 为 `.env`，至少填写：

```dotenv
DEEPSEEK_API_KEY=你的_API_Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=30
```

启动桌面模式：

```powershell
npm.cmd start
```

### Linux 小屏设备模式

在电脑上以 800×480 窗口预览：

```powershell
npm.cmd run dev:device
```

在 Linux 小屏设备中全屏启动：

```bash
npm run start:device
```

设备模式目前是可运行的软件原型。麦克风、功耗、散热、GPIO 和自动恢复仍需结合具体硬件验证，详见[硬件模式说明](docs/device-mode.md)。

## 开发与验证

运行 Electron / Node.js 测试：

```powershell
npm.cmd test
```

运行 Python 后端测试：

```powershell
python -m unittest discover -s backend\tests -v
```

只运行语音相关测试：

```powershell
npm.cmd run test:voice
```

生成 Windows 安装包和配置安装版的详细说明见[打包文档](docs/packaging.md)。

## 技术结构

```text
Electron 桌面 / Linux 小屏界面
              │
              ├── 文字交互与知识编辑
              ├── Vosk 离线唤醒
              └── faster-whisper 本地转写
              │
              ▼
       Python Reflection Service
              │
              ├── DeepSeek / 本地降级策略
              ├── 可选 Tavily 联网查证
              ├── 反思与完整知识文件构建
              └── SQLite 状态与全文索引
                          │
                          └── Obsidian Markdown
```

```text
assets/character/  角色状态素材
backend/           Python 反思服务、知识构建、SQLite、语音与测试
docs/              设备模式和打包说明
scripts/           启动、模型下载和打包脚本
src/               Electron 主进程、界面和共享业务规则
tests/             Electron 侧业务与语音生命周期测试
```

## Roadmap

- [x] 桌面角色、反思对话与本地知识存储
- [x] 中英文离线唤醒与本地语音转写
- [x] 完整知识文件生成、直接编辑与 AI 定向修改
- [x] 必要解释、纠错与可选联网查证
- [x] 知识版本修订和 Obsidian 连接
- [x] 桌面与 Linux 小屏双运行模式
- [ ] 语义检索与知识之间的自动关联
- [ ] 基于长期记录的复习提醒
- [ ] 个人认知模型与成长轨迹
- [ ] 在具体小屏硬件上完成语音、功耗和稳定性验证

## 参与项目

欢迎提交 Issue、改进建议和用于非商业目的的 Pull Request。较大的功能改动建议先发起 Issue，说明使用场景和设计方向。

提交代码前请确保：

- 没有提交 `.env`、API Key、数据库或本地模型
- Node.js 与 Python 测试通过
- 新增行为包含相应测试或验证说明
- 贡献内容可以按照本项目许可证用于非商业目的

## 许可证与非商业使用

Liora 采用 [PolyForm Noncommercial License 1.0.0](LICENSE)。

你可以出于个人学习、研究、实验和其他非商业目的阅读、运行、修改和分享本项目。未经单独书面授权，不得将 Liora 或其修改版本用于商业目的。

由于许可证限制商业使用，Liora 是一个 **source-available（源码可见）项目**，而不是符合 OSI 定义的开源软件。该许可证不构成对 Liora 名称、标识或品牌身份的商标授权。
