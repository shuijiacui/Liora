# Liora

<p align="center">
  <img src="assets/character/idle.png" width="180" alt="Liora 桌面角色">
</p>

<p align="center">
  <strong>让个人知识不只被保存，而是持续被理解、整理与照料。</strong>
</p>

<p align="center">
  Liora 是一位本地优先的个人知识管理员：负责知识沉淀、对齐、关联、审核与回顾；桌面角色只是她与你相遇的方式。
</p>

<p align="center">
  <a href="https://github.com/shuijiacui/Liora/releases/latest"><strong>下载 Windows 版</strong></a>
  ·
  <a href="#第一次使用应该选择哪条路线">选择安装方式</a>
  ·
  <a href="#从源码运行桌面端">从源码运行</a>
  ·
  <a href="#安装-obsidian-插件">安装 Obsidian 插件</a>
</p>

> 当前版本：Liora 桌面端 `0.2.4`，Obsidian 插件 `0.6.0`。项目仍处于积极开发的原型阶段，主要在 Windows 10/11 x64 上开发和验证。

如果你刚看到这个仓库，不需要先了解 Electron、Python、Embedding 或 Obsidian 插件。先记住一句话：

> Liora 不是一个附带知识库功能的桌宠，而是运行在个人设备上的知识管理系统。她把零散思考转化为可维护的知识对象，并持续照料它们之间的结构、关系、版本与回顾节奏。

桌面上的角色是 Liora 最自然的交互入口：你可以向她复述刚学会的概念、尚未想清楚的问题或值得留下的经验。真正位于产品核心的，是本地 Knowledge Engine。它负责把表达整理成独立知识，判断应该新建、更新还是建立联系，维护检索与认知状态，并在适当的时候把知识重新带回你的注意力。

连接 Obsidian 后，Markdown 是可阅读、可迁移的长期主数据；SQLite 承担索引、向量、审核、关系、回顾与回滚等运行状态。Liora 不接管你的决定：不确定的变更会提供证据和差异，经过你确认后才写入。她更像一位长期、克制而可靠的个人知识数据库管理员，而不是替你思考或擅自重构资料的自治 Agent。

### Liora 管理的不只是文件

| 管理对象 | Liora 负责什么 |
| --- | --- |
| 新的想法 | 通过追问、解释与修订，把口语化思考沉淀为可独立阅读的知识 |
| 已有知识 | 判断 CREATE / UPDATE / RELATED / CHILD，减少重复和错误覆盖 |
| 知识关系 | 发现显式引用与语义关联，同时展示可核对的原文证据 |
| 知识结构 | 提出 Split / Merge 与 Parent / Child 建议，保持合适的知识粒度 |
| 知识版本 | 生成 ChangeSet、字段差异和回滚信息，把最终决定留给用户 |
| 认知状态 | 从开放问题和历史反馈安排回顾，让知识在需要时重新出现 |
| 数据边界 | 本地保存主数据与索引，只在明确环节使用外部模型或联网查证 |

## 目录

- [第一次使用应该选择哪条路线](#第一次使用应该选择哪条路线)
- [Liora 由哪几个部分组成](#liora-由哪几个部分组成)
- [主要功能](#主要功能)
- [安装 Windows 版](#安装-windows-版)
- [完成第一次知识沉淀](#完成第一次知识沉淀)
- [连接 Obsidian Vault](#连接-obsidian-vault)
- [安装 Obsidian 插件](#安装-obsidian-插件)
- [从源码运行桌面端](#从源码运行桌面端)
- [配置说明](#配置说明)
- [测试与验证](#测试与验证)
- [构建 Windows 安装包](#构建-windows-安装包)
- [常见问题](#常见问题)
- [项目结构](#项目结构)
- [隐私、数据和许可证](#隐私数据和许可证)

## 第一次使用应该选择哪条路线

根据你的目的选择一条即可，不需要把所有步骤都做一遍。

| 你的目的 | 推荐路线 | 需要编程环境吗 |
| --- | --- | --- |
| 只想体验 Liora 的反思与知识管理 | 下载 Windows 安装包 | 不需要 |
| 想同时使用漂亮的 Obsidian Home 和知识管理台 | 先安装桌面端，再单独安装 Obsidian 插件 | 插件当前需要 Node.js 构建一次 |
| 想阅读代码、修改功能或参与开发 | 从源码运行桌面端，再按需部署插件 | 需要 Node.js、Python 和 Git |
| 只想看 Vault，不运行 Liora 桌面端 | 单独安装 Obsidian 插件 | 可以浏览本地 Markdown，但智能维护功能不可用 |

最省事的体验顺序是：

```text
安装 Liora 桌面端
  → 配置 DeepSeek Key（可选但推荐）
  → 从托盘连接一个 Obsidian Vault
  → 完成一次反思并保存知识
  → 再安装 Obsidian 插件查看 Home 与管理台
```

## Liora 由哪几个部分组成

这个仓库里有三个互相协作、但可以独立理解的部分：

| 部分 | 它是什么 | 是否包含在 Windows 安装包中 |
| --- | --- | --- |
| Liora 桌面界面 | 具有人格感的自然入口，承载复述、对话、确认、语音、天气与提醒 | 是 |
| Knowledge Engine | 产品核心；负责知识稿、索引、对齐、关联、审核、结构、回顾和运行状态 | 是，安装版自带独立运行时 |
| Liora Knowledge 插件 | Obsidian 中的知识 Home、日历备忘、管理台、证据与决策界面 | 否，需要单独安装到 Vault |

因此有两个常见但容易混淆的事实：

1. 修改 `obsidian-plugin/` 不会自动改变已经安装的桌面端，也不会让桌面安装包变大；插件需要重新构建并复制到 Vault。
2. 修改 `backend/` 会影响 Knowledge Engine。重新打包桌面端后，新安装包会包含这些后端改动；已经生成的旧安装包不会自动更新。

整体连接方式如下：

```text
Liora 桌面端
    │ 启动并管理
    ▼
本地 Knowledge Engine（仅监听 127.0.0.1，使用随机令牌）
    │                       ▲
    │ 读写 Markdown         │ 本机 API
    ▼                       │
Obsidian Vault ◀──── Liora Knowledge 插件
```

Obsidian 插件不会直接调用 DeepSeek，也不会把整个 Vault 发给模型。它连接的是本机 Knowledge Engine；桌面端退出后，插件会退回 `VAULT ONLY` 只读模式。

## 主要功能

Liora 的能力围绕一条完整的知识生命周期组织，而不是一组彼此孤立的 AI 功能：

```text
捕捉想法 → 澄清理解 → 形成知识 → 对齐旧知识
         → 审核写入 → 发现关系 → 调整结构 → 安排回顾
```

### 从复述生成真正可读的知识

- 从一个模糊想法开始，不要求你先整理好措辞。
- Liora 会追问当前最值得想清楚的问题。
- 当你不确定、记错或询问事实时，它可以先解释或纠正。
- 对话结束后生成结构化知识稿，而不是聊天摘要。
- 支持直接编辑，也支持告诉 Liora“补充例子”“讲透原理”“精简表达”后重新修订。
- 最终知识可以包含核心理解、关键要点、推理链、例子、边界、联系、开放问题和来源。

### 本地优先的 Knowledge Engine

- 连接 Obsidian 后，以 Vault 中的 Markdown 作为长期主数据。
- 使用 SQLite 保存索引、向量、审核状态、回顾状态和回滚数据。
- 使用本地 `bge-small-zh-v1.5` ONNX INT8 模型完成中文语义检索。
- 判断新知识应该 CREATE、UPDATE、RELATED 还是 CHILD。
- 不确定或结构性改动进入 ChangeSet，确认后才写入 Markdown。
- 发现 Hard / Soft Connection，并为新关联展示可核对的两侧原文。
- 已过滤 `<!-- liora:begin -->`、历史错误 `loria` 标记和通用模板标题带来的伪关联。
- 提供 Split / Merge 候选和 Parent / Child 多尺度结构；真正破坏性的自动合并目前不会执行。

### Obsidian Home 与知识管理台

- 温暖、低饱和、适配 Obsidian 窗格的 Liora Home。
- 顶部常用入口、知识横幅、回顾问题和“问问我的知识库”。
- 周历和按日期保存的简单备忘纸条。
- 最近知识列表，点击可直接打开对应 Markdown。
- 三栏知识管理台：左侧导航、中栏内容、右侧知识库问答。
- 中栏独立滚动，左右工作区保持固定。
- 新关联显示标题、原文片段、关系依据和线索强度，由用户确认或拒绝。

### 本地语音与桌面角色

- Vosk 本地识别中英文唤醒词“Hi Liora”。
- faster-whisper 本地转写中文、英文和中英混说。
- 唤醒和听写使用两套不同模型，均保存在本机。
- 录音由“开始说 / 说完了”明确控制，不保存音频文件。
- 透明、无边框、始终置顶，支持拖动、位置记忆、托盘和开机启动。
- 提供反思、回顾、知识和天气入口，以及可关闭的晚间提醒。

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

## 安装 Windows 版

这一部分适合只想使用 Liora、不准备修改源码的人。

### 1. 下载安装包

打开 [GitHub Releases](https://github.com/shuijiacui/Liora/releases/latest)，下载最新的 Windows x64 安装程序。当前构建文件名为：

```text
Liora-Setup-0.2.4-x64.exe
```

当前安装包约 1.28 GiB，因为它包含 Electron、Python Runtime、本地语音模型和本地语义模型。安装和首次运行前建议预留数 GB 磁盘空间。

如果 Release 同时提供 `SHA256SUMS.txt`，可以在 PowerShell 中验证下载是否完整：

```powershell
Get-FileHash .\Liora-Setup-0.2.4-x64.exe -Algorithm SHA256
```

当前 `0.2.4` 构建的 SHA-256 为：

```text
93A29955E82ADB9AB8385CBD9F39539285861BEE8BC314CC4D32FFD9576D7EA9
```

### 2. 运行安装程序

双击安装包并选择安装目录。当前安装包没有商业代码签名，Windows SmartScreen 可能显示“未知发布者”。请先确认文件来自本仓库 Release 页面并核对哈希，再决定是否选择“更多信息 → 仍要运行”。

覆盖安装新版本不会主动删除知识库、设置和窗口位置。卸载时默认也不会删除用户数据。

### 3. 配置 AI 能力

没有 API Key 时 Liora 仍可启动，本地索引、语义检索和部分降级对话仍然可用；要使用完整的 AI 追问、知识稿生成和定向修订，建议配置 DeepSeek。

按 `Win + R`，输入：

```text
%APPDATA%\liora-desktop-companion
```

在打开的目录中新建名为 `.env` 的文件。请确认文件不是 `.env.txt`。最小内容如下：

```dotenv
DEEPSEEK_API_KEY=替换为你的_API_Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=30
```

保存后，从系统托盘右键 Liora 并完全退出，再重新启动。只关闭对话气泡不等于退出后台进程。

### 4. 可选：启用联网查证

在同一个 `.env` 中继续加入：

```dotenv
TAVILY_API_KEY=替换为你的_API_Key
TAVILY_BASE_URL=https://api.tavily.com
TAVILY_TIMEOUT_SECONDS=15
TAVILY_MAX_RESULTS=4
```

联网查证不是每轮对话都会发生。只有配置 Tavily Key，并且你明确要求搜索，或问题涉及最新信息、价格、版本、精确数据和明显不确定性时，Liora 才会尝试查询。

## 完成第一次知识沉淀

### 1. 开始反思

点击桌面角色，或右键系统托盘中的 Liora，选择“开始今日反思”。你可以输入文字，也可以点击“开始说”进行语音输入。

不必先组织好语言，可以直接说：

> 我大概知道 Attention 是什么，但总觉得自己没有真正说清楚。

### 2. 回答追问

Liora 会根据当前内容提出一个问题。如果你说“不确定”或直接询问事实，它会先给出必要帮助，而不是机械地不停追问。你决定什么时候聊得足够了。

### 3. 生成知识文件

点击“生成知识文件”。Liora 会围绕真正的主题生成一份脱离聊天也能阅读的知识稿。无法确认的内容应进入“尚待探索”，而不是伪装成确定结论。

### 4. 编辑并确认

你可以逐项直接编辑，也可以输入修改意见让 Liora 再处理一次。满意后点击保存；如果选择不保存，本轮草稿和原始对话会被清理。

### 5. 继续生长和回顾

以后可以从“知识”入口打开旧知识继续完善。知识中的开放问题会进入回顾调度；回顾评分会影响下一次出现时间。

## 连接 Obsidian Vault

Liora 可以不连接 Obsidian，仅使用本地 SQLite；但要获得可迁移、可直接编辑的 Markdown 知识库，推荐连接一个专用 Vault。

### 推荐先创建专用 Vault

如果你刚开始使用，建议在 Obsidian 中创建一个新的 Vault，例如：

```text
D:\Obsidian\Liora
```

当前规则会把专用 Vault 里的每一篇 Markdown 都视为知识。`.obsidian`、`.trash`、`.git`、`node_modules` 和 `templates` 目录会被忽略。不要一开始就连接包含大量日记、模板和无关笔记的主 Vault，除非你确认这些文件都应该进入知识索引。

### 在 Liora 中连接

1. 在系统托盘右键 Liora。
2. 选择“连接 Obsidian 知识库…”。
3. 选择 Vault 根目录，也就是包含 `.obsidian` 文件夹的那一层。
4. 首次连接会扫描 Markdown 并建立本地索引，不会因为扫描而重写所有文件。
5. 新知识默认写入 `00 Inbox/Liora/`。

如果之前已经在 SQLite 中保存知识，可以选择“迁移 SQLite 知识到 Obsidian…”。迁移前会自动备份数据库，并避免重复创建已经迁移的知识。

### Liora 怎样保护原笔记

- 普通扫描只读取 Markdown 和更新本地索引。
- 对普通外部笔记进行 UPDATE 时，Liora 会保留原文，并追加或更新受管理区块。
- 管理区块使用 `<!-- liora:begin -->` 和 `<!-- liora:end -->` 标记。
- 写入采用临时文件加原子替换，且目标路径必须位于所选 Vault 内。
- 不确定或结构性改动进入 ChangeSet，需在管理台确认。

更完整的算法和数据边界说明见 [Obsidian 插件与 Knowledge Engine 设计文档](Obsidian_Plugin_Knowledge_Engine_Design.md)。

## 安装 Obsidian 插件

> 重要：Windows 安装程序不会自动安装 Obsidian 插件。桌面端版本是 `0.2.4`，插件是独立的 `0.6.0` 工程。

插件当前没有发布到 Obsidian 官方社区插件市场，因此需要从仓库构建并手动复制。以下步骤只需要执行一次；修改插件源码后需要重新构建和覆盖部署。

### 1. 准备 Node.js

安装 Node.js `22.12` 或更高版本。打开 PowerShell，确认：

```powershell
node --version
npm.cmd --version
```

如果 PowerShell 提示找不到命令，请重新打开终端，或重新安装 Node.js 并勾选加入 PATH。

### 2. 构建插件

在仓库根目录执行：

```powershell
cd obsidian-plugin
npm.cmd install
npm.cmd run check
```

`check` 会依次完成 TypeScript 类型检查、插件测试和生产构建。成功后，`obsidian-plugin/` 中会生成 `main.js`。

### 3. 复制到 Vault

目标目录必须是：

```text
<你的 Vault>\.obsidian\plugins\liora-knowledge\
```

需要复制的文件结构如下：

```text
liora-knowledge/
├── main.js
├── manifest.json
├── styles.css
└── assets/
    ├── home-banner.png
    └── manager-banner.png
```

可以手动复制，也可以在仓库根目录使用下面的 PowerShell。先把第一行替换成你的真实 Vault 路径：

```powershell
$LioraVault = "D:\Obsidian\Liora"
$LioraPluginDir = Join-Path $LioraVault ".obsidian\plugins\liora-knowledge"
New-Item -ItemType Directory -Force -Path $LioraPluginDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $LioraPluginDir "assets") | Out-Null
Copy-Item "obsidian-plugin\main.js","obsidian-plugin\manifest.json","obsidian-plugin\styles.css" -Destination $LioraPluginDir -Force
Copy-Item "obsidian-plugin\assets\home-banner.png","obsidian-plugin\assets\manager-banner.png" -Destination (Join-Path $LioraPluginDir "assets") -Force
```

### 4. 在 Obsidian 中启用

1. 打开该 Vault。
2. 进入“设置 → 第三方插件”。
3. 如果处于受限模式，先允许第三方插件。
4. 找到并启用 `Liora Knowledge`。
5. 点击左侧房子图标，或按 `Ctrl + P` 打开命令面板并运行“Liora Knowledge: 打开知识首页”。
6. 管理台可以从 Home 顶部入口或命令“打开 Liora 管理台”进入。

### 5. 连接状态说明

通常不需要在插件设置中填写地址或令牌。桌面端运行时会在下面的位置发布临时连接信息：

```text
%APPDATA%\liora-desktop-companion\knowledge-engine.json
```

插件会自动发现它。这个文件中的令牌是本机 Knowledge Engine 的随机访问令牌，不是 DeepSeek API Key。

- 显示 `ENGINE ONLINE`：智能审核、关系、粒度、回顾和知识库提问可用。
- 显示 `VAULT ONLY`：仍可看 Markdown、最近知识和开放问题，但需要 Knowledge Engine 的按钮不可用。
- 手动地址和令牌是高级选项，通常保持为空；插件只允许连接本机地址。

插件的开发说明也可以查看 [obsidian-plugin/README.md](obsidian-plugin/README.md)。

## 从源码运行桌面端

这一部分适合想修改代码、运行测试或自己打包的人。下面以 Windows PowerShell 为主。

### 环境要求

- Git
- Node.js `22.12` 或更高版本
- Python `3.10` 或更高版本
- Windows 10/11 x64（当前完整打包流程只支持 Windows）
- 足够的磁盘空间和网络流量，用于 Node 依赖与三个本地模型目录

先检查工具：

```powershell
git --version
node --version
npm.cmd --version
python --version
```

在 Windows PowerShell 中推荐写 `npm.cmd`，可以避开部分系统对 `npm.ps1` 的执行策略限制。

### 1. 获取代码

```powershell
git clone https://github.com/shuijiacui/Liora.git
cd Liora
```

如果你已经下载 ZIP，请解压后在该目录空白处按住 Shift 右键，选择“在终端中打开”。后续命令都应在包含 `package.json` 的仓库根目录运行。

### 2. 安装 Node.js 依赖

```powershell
npm.cmd install
```

这会安装 Electron、electron-builder 和桌面端开发依赖。`node_modules/` 很大，但不会提交到 Git。

### 3. 准备 Python 环境

可以选择 Conda 或普通 `venv`。二选一即可。

#### 方案 A：Conda / Anaconda（推荐）

```powershell
conda create -n liora python=3.10 -y
conda activate liora
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
$env:LIORA_PYTHON = (Get-Command python).Source
```

`LIORA_PYTHON` 只对当前 PowerShell 窗口生效。以后重新打开终端时，需要再次 `conda activate liora` 并设置它。项目也会自动尝试识别当前 `CONDA_PREFIX` 和用户目录下名为 `ml_env` 的 Conda 环境，但显式设置最可靠。

#### 方案 B：Python venv

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
$env:LIORA_PYTHON = (Resolve-Path ".\.venv\Scripts\python.exe").Path
```

如果系统阻止运行 `Activate.ps1`，可以不激活环境，直接使用：

```powershell
$env:LIORA_PYTHON = (Resolve-Path ".\.venv\Scripts\python.exe").Path
& $env:LIORA_PYTHON -m pip install -r backend\requirements.txt
```

确认关键依赖可以导入：

```powershell
& $env:LIORA_PYTHON -c "import faster_whisper, sounddevice, vosk, opencc, onnxruntime, tokenizers; print('Python dependencies OK')"
```

### 4. 下载本地模型

三个脚本用途不同：

| 命令 | 下载内容 | 用途 |
| --- | --- | --- |
| `setup-voice-model.py` | faster-whisper small | 正文语音转写 |
| `setup-wake-models.py` | Vosk 中英文小模型 | “Hi Liora”常驻唤醒 |
| `setup-embedding-model.py` | BGE 中文 ONNX INT8 | 知识语义检索与关联 |

执行：

```powershell
& $env:LIORA_PYTHON scripts\setup-voice-model.py
& $env:LIORA_PYTHON scripts\setup-wake-models.py
& $env:LIORA_PYTHON scripts\setup-embedding-model.py
```

模型会写入项目根目录的 `.models/`，只需下载一次。该目录已加入 `.gitignore`。

如果磁盘空间有限，可以选择较小但准确率较低的 faster-whisper base：

```powershell
& $env:LIORA_PYTHON scripts\setup-voice-model.py --model base
$env:LIORA_WHISPER_MODEL = "base"
```

下载模型需要访问 Hugging Face 和 Vosk 模型站点。如果网络中断，可以重新执行相同命令；已完成的文件通常会复用缓存。

### 5. 创建源码模式配置

```powershell
Copy-Item .env.example .env
notepad .env
```

至少按需填写 `DEEPSEEK_API_KEY`。`.env` 已被 Git 忽略，不要删除 `.gitignore` 中的相关规则，也不要把真实 Key 粘贴到 Issue、日志或截图中。

### 6. 启动

```powershell
$env:LIORA_PYTHON = (Get-Command python).Source
npm.cmd start
```

启动脚本会打开 Electron，并由主进程在随机本机端口启动 Python Knowledge Engine。看到桌面角色并能打开反思界面，说明桌面端启动成功。

常用开发命令：

```powershell
npm.cmd run dev
npm.cmd run dev:device
npm.cmd run start:device
```

- `dev`：桌面开发模式。
- `dev:device`：在桌面用 800×480 窗口预览小屏设备界面。
- `start:device`：Linux 小屏设备全屏模式。

设备模式目前是软件原型，麦克风、GPIO、功耗、散热和自动恢复仍需针对实际硬件验证，详见 [设备模式说明](docs/device-mode.md)。

## 配置说明

源码模式读取仓库根目录 `.env`；安装版读取 `%APPDATA%\liora-desktop-companion\.env`。同名系统环境变量优先保留，不会被 `.env` 强制覆盖。

### DeepSeek

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | 空 | 为空时使用本地降级策略 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容接口根地址 |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | 使用的模型名，可按服务端支持情况修改 |
| `DEEPSEEK_TIMEOUT_SECONDS` | `30` | 请求超时秒数 |

### 联网查证

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `TAVILY_API_KEY` | 空 | 为空时不进行联网查证 |
| `TAVILY_BASE_URL` | `https://api.tavily.com` | Tavily API 地址 |
| `TAVILY_TIMEOUT_SECONDS` | `15` | 查询超时秒数 |
| `TAVILY_MAX_RESULTS` | `4` | 单次最多保留结果数，后端限制在 1～8 |

### 本地语义和对齐

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LIORA_EMBEDDING_MODEL_ID` | `onnx-community/bge-small-zh-v1.5-ONNX` | 模型标识 |
| `LIORA_EMBEDDING_MODEL_DIR` | 自动定位 | 自定义本地模型目录 |
| `LIORA_EMBEDDING_MAX_LENGTH` | `512` | 最大 token 长度 |
| `LIORA_EMBEDDING_BATCH_SIZE` | `8` | 批处理大小 |
| `LIORA_ALIGNMENT_JUDGE` | `balanced` | `balanced` 只在歧义区调用 DeepSeek；`local` 或 `off` 始终本地判断 |
| `LIORA_ALIGNMENT_DAILY_LIMIT` | `20` | 每天最多产生多少次新的歧义裁判缓存 |

### 运行、语音和天气

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LIORA_PYTHON` | 自动探测 | 源码运行和打包使用的 Python 绝对路径 |
| `LIORA_WHISPER_MODEL` | `small` | 可改为 `base`，必须与已下载模型匹配 |
| `LIORA_RUNTIME` | 空 | 桌面模式留空；专用小屏镜像可设为 `device` |
| `LIORA_DEVICE_WINDOWED` | `0` | 设为 `1` 时以窗口预览设备模式 |
| `LIORA_USER_DATA_DIR` | Electron 默认目录 | 高级选项：覆盖用户数据目录，必须是绝对路径 |
| `LIORA_WEATHER_ENABLED` | `1` | 经纬度存在时启用天气；设为 `0` 可禁用 |
| `LIORA_WEATHER_LOCATION` | 空 | 天气地点显示名 |
| `LIORA_WEATHER_LATITUDE` | 空 | 纬度 |
| `LIORA_WEATHER_LONGITUDE` | 空 | 经度 |

完整模板见 [.env.example](.env.example)。

## 测试与验证

提交代码或重新打包前，至少运行桌面端和后端测试。

### Electron / Node.js 测试

```powershell
npm.cmd test
```

当前版本共有 44 项 Node.js 测试。

### Python 后端测试

```powershell
& $env:LIORA_PYTHON -m unittest discover -s backend\tests -v
```

当前版本共有 67 项后端测试。测试覆盖 API、Markdown 扫描、DeepSeek 降级、Knowledge Engine、语义模型、关系降噪、回顾、语音和联网查证。

### Obsidian 插件检查

```powershell
cd obsidian-plugin
npm.cmd run check
```

这一个命令包含类型检查、插件单元测试和生产构建。修改 `home-view.ts`、`manager-view.ts` 或 `styles.css` 后，应重新执行并把产物部署到测试 Vault。

不要直接在唯一的正式 Vault 中测试会写入 Markdown 的功能。ChangeSet apply、Split 和迁移操作应先在可备份或可回滚的测试 Vault 中验证。

## 构建 Windows 安装包

完整打包目前只支持 Windows。安装包不会包含仓库根目录 `.env`，因此不会把开发者的 API Key 固化进发布文件。

### 1. 准备专用打包环境

推荐先执行：

```powershell
$env:LIORA_PYTHON = (Get-Command python).Source
npm.cmd run setup:packaging
```

它会创建 `.package-venv/` 并安装后端依赖和 PyInstaller。也可以直接让构建脚本使用已经具备依赖的 Conda 环境。

### 2. 根据改动选择命令

后端、Python 依赖、语音模块或 Python 打包配置发生变化时，必须完整构建：

```powershell
npm.cmd run dist:win
```

只修改 Electron 页面、CSS、普通 JavaScript 或图片时，可以复用已存在的 Python Runtime：

```powershell
npm.cmd run dist:win:fast
```

只生成无需安装的目录版：

```powershell
npm.cmd run pack:win
npm.cmd run pack:win:fast
```

产物位置：

```text
release/
├── Liora-Setup-<版本>-x64.exe
├── Liora-Setup-<版本>-x64.exe.blockmap
├── latest.yml
└── win-unpacked/
    └── Liora.exe
```

发布前还应：

1. 更新 `package.json` 和 `package-lock.json` 中的版本。
2. 运行 Node、Python 和插件测试。
3. 确认 `.models/` 已包含需要随安装包发布的模型。
4. 完整构建 Python Runtime。
5. 检查安装包和 `win-unpacked/Liora.exe` 的产品版本。
6. 直接启动打包后的 Knowledge Engine 检查 `/health`。
7. 生成并核对 SHA-256。
8. 确保 `release/` 没有混入旧版本安装包。

详细说明见 [Windows 打包文档](docs/packaging.md)。

## 常见问题

### `npm.cmd start` 提示“没有找到 Python”

项目不会盲目选择 PATH 中的任意 Python。激活正确环境后，在同一个 PowerShell 窗口执行：

```powershell
$env:LIORA_PYTHON = (Get-Command python).Source
& $env:LIORA_PYTHON --version
npm.cmd start
```

如果使用 Anaconda，也可以先运行 `conda env list` 确认环境位置。不要把 `LIORA_PYTHON` 设置成环境目录，它必须指向具体的 `python.exe`。

### Python 存在，但后端仍启动失败

先验证依赖：

```powershell
& $env:LIORA_PYTHON -c "import faster_whisper, sounddevice, vosk, opencc, onnxruntime, tokenizers; print('OK')"
```

如果报 `ModuleNotFoundError`：

```powershell
& $env:LIORA_PYTHON -m pip install -r backend\requirements.txt
```

### PowerShell 不允许运行 `npm.ps1` 或 `Activate.ps1`

使用 `npm.cmd` 代替 `npm`。Python 环境也可以不激活，直接把 `.venv\Scripts\python.exe` 的绝对路径赋给 `LIORA_PYTHON`。

### 本地语义模型显示不可用

源码模式重新执行：

```powershell
& $env:LIORA_PYTHON scripts\setup-embedding-model.py
```

确认 `.models\embeddings\bge-small-zh-v1.5\onnx\model_quantized.onnx` 存在。模型不可用时系统会明确降级为 384 维哈希向量，不会静默联网下载。

### 唤醒词或语音输入不可用

- 确认 `.models\vosk\cn` 和 `.models\vosk\en-us` 存在。
- 确认 `.models\faster-whisper` 中已有所选模型。
- 在 Windows“设置 → 隐私和安全性 → 麦克风”允许桌面应用访问。
- 确认 `sounddevice` 能导入，并检查系统默认输入设备。
- 只需要文字功能时可以暂时关闭托盘中的“语音唤醒”。

### Obsidian 插件显示 `VAULT ONLY`

这表示插件没有连接到正在运行的 Knowledge Engine，不代表 Markdown 丢失。

1. 确认 Liora 桌面端仍在系统托盘运行。
2. 检查 `%APPDATA%\liora-desktop-companion\knowledge-engine.json` 是否存在。
3. 保持插件设置中的手动地址和令牌为空，让它自动发现。
4. 在 Obsidian 中关闭再启用插件，或重载应用。

### Obsidian 中找不到房子图标或 Liora Home

- 确认目录名严格为 `.obsidian\plugins\liora-knowledge`。
- 确认该目录直接包含 `main.js`、`manifest.json` 和 `styles.css`，没有多套一层文件夹。
- 确认 `manifest.json` 中版本是 `0.6.0`。
- 在“设置 → 第三方插件”启用 `Liora Knowledge`。
- 修改 `manifest.json` 后通常需要重启 Obsidian；只修改代码时可以重载插件。

### 最近知识或关联标题点击后无法打开 Markdown

插件会同时兼容 Vault 相对路径和旧索引中的绝对路径。若仍打不开：

1. 确认文件没有被移出当前 Vault。
2. 在 Liora 托盘中执行“刷新知识索引”或“重建知识索引”。
3. 确认 Obsidian 当前打开的 Vault 与 Liora 连接的是同一个目录。

### 新关联看起来只是模板内容相同

`0.2.4` 已清理 Liora/Loria 标记、模板标题和空占位文本，并要求两侧正文具有实际证据。升级并重建索引后，旧的未决候选会被重新计算。已经确认或拒绝的关系会保留用户决定，不会自动删除。

### 修改代码后安装版为什么没有变化

源码目录和已安装程序是两份独立内容：

- 修改 Electron 或后端后，需要重新生成并安装桌面安装包，或直接用 `npm.cmd start` 运行源码。
- 修改 Obsidian 插件后，需要 `npm.cmd run check`，再复制 `main.js`、`styles.css`、`manifest.json` 和插件图片到 Vault。
- 只刷新 Obsidian 不会更新桌面端，重新安装桌面端也不会部署 Obsidian 插件。

## 项目结构

```text
Liora/
├── assets/                 桌宠角色图片
├── backend/                Python Knowledge Engine、语音、数据库和测试
│   ├── main.py             本机 HTTP 服务入口
│   ├── service.py          反思与知识业务编排
│   ├── knowledge_store.py  Vault 扫描、Markdown 解析与安全写入
│   ├── knowledge_intelligence.py
│   │                       对齐、检索、关系与粒度算法
│   └── semantic_embedding.py
│                           本地 BGE ONNX Embedding
├── docs/                   打包和设备模式说明
├── obsidian-plugin/        独立的 Obsidian 插件工程
│   ├── src/home-view.ts    Liora Home
│   ├── src/manager-view.ts 知识管理台
│   └── styles.css          Home 与管理台样式
├── scripts/                启动、模型下载和打包脚本
├── src/                    Electron 主进程、渲染层和共享业务规则
├── tests/                  Node.js 测试
├── .env.example            配置模板，不含真实 Key
├── package.json            桌面端脚本、依赖、版本和打包配置
└── Obsidian_Plugin_Knowledge_Engine_Design.md
                            Knowledge Engine 现状与算法详解
```

### 进一步阅读

- [Knowledge Engine 与 Obsidian 插件设计说明](Obsidian_Plugin_Knowledge_Engine_Design.md)
- [Liora 产品设计文档](Liora设计文档.md)
- [Windows 打包说明](docs/packaging.md)
- [Linux 小屏设备模式](docs/device-mode.md)
- [Obsidian 插件开发说明](obsidian-plugin/README.md)

## 隐私、数据和许可证

### 数据保存在哪里

| 数据 | 保存或处理位置 |
| --- | --- |
| 唤醒词与语音转写 | 本机 Vosk / faster-whisper；不生成录音文件 |
| 临时反思与知识草稿 | Electron 用户数据目录中的 SQLite |
| 已确认知识 | 未连接 Vault 时在 SQLite；连接后以 Obsidian Markdown 为主数据 |
| 索引、向量、关系、回顾和回滚状态 | 本机 SQLite |
| DeepSeek / Tavily API Key | 本地 `.env`；不进入前端、安装包或 Git |
| 联网查证查询 | 配置 Tavily 且触发查证时发送当前问题所需的短查询 |
| 整个 Obsidian Vault | 当前不会整体发送给 DeepSeek 或 Tavily |
| 天气位置 | 本机保存缩减精度后的坐标，不发送给 DeepSeek |

Windows 默认用户数据目录：

```text
%APPDATA%\liora-desktop-companion\
```

使用 DeepSeek 或 Tavily 意味着相应的对话片段、草稿或查询会到达外部服务。具体日志、保留和训练政策应以服务商当时的条款为准。

### 提交代码前

- 不要提交 `.env`、API Key、SQLite 数据库、本地模型或真实 Vault 内容。
- 运行 Node.js、Python 和相关插件测试。
- 新增行为应包含相应测试或明确的验证说明。
- 大型功能建议先通过 Issue 说明使用场景、数据影响和设计方向。

### 许可证

Liora 使用 [PolyForm Noncommercial License 1.0.0](LICENSE)。

你可以出于个人学习、研究、实验和其他非商业目的阅读、运行、修改和分享本项目。未经单独书面授权，不得将 Liora 或其修改版本用于商业目的。

由于许可证限制商业使用，Liora 是一个 **source-available（源码可见）项目**，而不是符合 OSI 定义的开源软件。该许可证不构成对 Liora 名称、标识或品牌身份的商标授权。
