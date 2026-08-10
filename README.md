# Liora

<p align="center">
  <img src="assets/character/idle.png" width="180" alt="Liora 桌面角色">
</p>

<p align="center">
  <strong>一个会追问、会陪你复盘，并把零散想法沉淀为个人知识的桌面 AI 伙伴。</strong>
</p>

<p align="center">
  A privacy-first desktop AI companion that turns daily reflections into a growing personal knowledge base.
</p>

Liora 不是另一个等待提问的聊天机器人。它安静地待在桌面上，邀请你回顾今天学到的内容，通过自然追问帮助你澄清理解，并结合可靠知识构建一份可以独立阅读、继续生长的知识文件。

项目当前处于积极开发的原型阶段，主要面向 Windows 桌面，同时提供适配通用 Linux 小屏设备的运行模式。

## 为什么是 Liora？

多数 AI 助手擅长直接给出答案，Liora 更关心你是否真正形成了自己的理解。

```text
自然表达 → AI 追问 → 主动复盘 → 确认理解 → 沉淀为长期知识
```

它希望降低维护个人知识库的成本：不要求你先整理好一切，而是从一次轻量、自然的反思开始，让知识在对话中逐渐成形。

## 核心能力

### 反思，也会在需要时提供帮助

- 通过开放式问题引导回忆、自我解释和进一步思考
- 持续自然追问，不用固定轮数强行结束对话
- 用户拿不准时会先简短解释或纠正，再继续推进思考
- 可选联网查证最新或精确信息，并把来源带入知识文件
- 支持文字输入与最长一分钟的手动语音输入
- DeepSeek 不可用时自动切换到本地反思策略
- 未完成的反思和待确认草稿可在重新打开后恢复

### 从对话构建完整知识文件

- 对话用于识别主题、关注点和认知缺口，最终文件不是聊天摘要
- 主动补充核心原理、关键要点、例子、延伸、边界和知识联系
- 保存前可以直接编辑，也可以给出意见让 Liora 定向修改
- 使用 SQLite 保存已确认知识及其修订版本
- 可从已有知识继续思考，并保存为同一条知识的新版本
- 可连接 Obsidian Vault，以 Markdown 作为长期主数据
- 支持中文全文搜索、文件夹筛选和标签筛选

### 本地语音与隐私优先

- 使用 Vosk 在本地识别中英文唤醒词 “Hi Liora”
- 使用 faster-whisper 在本地转写中文、英文和中英混说
- 音频仅在内存中短暂存在，转写后立即释放
- 低置信度或意图含糊时不猜测跳转
- 语音原文不会发送给 DeepSeek，位置也不会发送给大模型

### 一个真正待在桌面上的角色

- 透明、无边框、始终置顶的桌面角色
- 六种角色状态、呼吸动画与自然过渡
- 支持拖动、位置记忆、系统托盘和开机启动
- 每晚一次可关闭的低打扰反思提醒
- 支持反思、知识和天气三个轻量入口

### 两种运行形态

- **桌面模式**：透明悬浮角色、托盘、拖动和系统通知
- **设备模式**：面向 800×480 起步的 Linux 小屏全屏界面

设备模式目前是可运行的软件原型，麦克风、功耗、散热、GPIO 和自动恢复等能力仍需结合具体硬件验证。详见[硬件模式说明](docs/device-mode.md)。

## 快速开始

### 环境要求

- Node.js 22.12 或更高版本
- Python 3.10 或更高版本
- Windows、macOS 或 Linux；当前桌面产品配置主要在 Windows 上验证

Electron 会依次从 `LIORA_PYTHON`、当前 Conda 环境、PyCharm 项目 SDK 和默认 `ml_env` 路径寻找 Python。需要手动指定时：

```powershell
$env:LIORA_PYTHON="C:\path\to\python.exe"
```

### 安装

```powershell
npm.cmd install
python -m pip install -r backend\requirements.txt
python scripts\setup-voice-model.py
python scripts\setup-wake-models.py
```

语音模型首次下载需要数百 MB；之后只读取项目 `.models` 目录中的本地缓存。可以通过 `LIORA_WHISPER_MODEL=base` 使用更轻量但准确率较低的听写模型。

### 启动桌面模式

```powershell
npm.cmd start
```

也可以显式指定桌面模式：

```powershell
npm.cmd run start:desktop
```

### 预览设备模式

在电脑上打开一个 800×480 的普通窗口：

```powershell
npm.cmd run dev:device
```

在 Linux 小屏设备中全屏启动：

```bash
npm run start:device
```

## 配置

复制 `.env.example` 为 `.env`，按需填写配置。`.env` 已被 Git 忽略，不会进入提交。

### DeepSeek

```dotenv
DEEPSEEK_API_KEY=你的_API_Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=30
```

未配置或调用失败时，Liora 会自动使用本地反思策略；用户输入仍会正常保存在本机。API Key 不会传给前端，也不会写入日志。

### 联网查证（可选）

```dotenv
TAVILY_API_KEY=你的_API_Key
TAVILY_BASE_URL=https://api.tavily.com
TAVILY_TIMEOUT_SECONDS=15
TAVILY_MAX_RESULTS=4
```

联网查证默认关闭。只有配置 Key 后，且用户明确要求搜索，或表达中出现最新信息、精确数据和明显不确定性时才会发起搜索。Liora 只发送当前问题所需的短查询，不发送整段反思记录；搜索失败时会明确降级到模型已有知识。

### 天气

天气功能默认关闭。可以在 Liora 中主动授权一次当前位置，也可以在 `.env` 中配置固定地点：

```dotenv
LIORA_WEATHER_ENABLED=1
LIORA_WEATHER_LOCATION=上海
LIORA_WEATHER_LATITUDE=31.2304
LIORA_WEATHER_LONGITUDE=121.4737
```

Liora 只保存缩减到两位小数的坐标。位置仅用于天气请求，不会发送给 DeepSeek；拒绝定位或断网不会影响反思功能。

## 使用方式

- 点击角色或“反思”：开始当前一轮反思
- 点击“开始说 / 说完了”：手动控制语音采集边界
- 点击“生成知识文件”：围绕当前主题构建一份独立可读的知识草稿
- 点击“编辑与修改”：直接编辑草稿，或告诉 Liora 如何定向修改
- 点击“这样保存”：确认当前草稿并写入知识记录
- 点击“继续聊聊”：回到当前反思，之后重新构建知识文件
- 点击“知识”：搜索已确认知识，或基于某条知识继续思考
- 说“Hi Liora”：唤出功能入口，并可继续说出天气、反思或知识意图
- 将鼠标移到角色上：展开“反思 / 知识 / 天气”入口
- 按住角色拖动：改变桌面停靠位置
- 使用托盘菜单：显示、隐藏、复位、设置提醒或退出

进入反思功能后，Liora 不会因为听到唤醒词就立即录制正文；是否开始录音始终由用户控制。

## 连接 Obsidian

Liora 采用 **Markdown 主数据 + SQLite 运行状态与索引** 的存储方式：

1. 在托盘菜单中选择“连接 Obsidian 知识库…”，然后选择 Vault 根目录。
2. 首次连接只扫描 Markdown 并建立本地索引，不修改已有笔记。
3. “迁移 SQLite 知识到 Obsidian…”会先创建一致性备份，再导出现有知识。
4. 配置完成后，新确认的知识将原子写入 `00 Inbox/Liora/`。
5. 对普通 Obsidian 笔记保持只读；只有用户明确继续完善并确认时，Liora 才会更新托管区块。

知识搜索使用 SQLite FTS5 trigram 索引标题、正文、路径和标签，支持中文连续文本。索引只是可重建缓存，Markdown 始终是主数据。

Liora 创建的知识文件包含以下 frontmatter：

```yaml
---
id: "稳定 UUID"
type: knowledge
title: "知识标题"
created: "2026-08-09T10:20:00+00:00"
updated: "2026-08-09T10:20:00+00:00"
version: 1
source: liora
schema_version: 1
---
```

## 隐私与数据

| 数据 | 保存或处理位置 |
|---|---|
| 唤醒词与语音转写 | 本机 Vosk / faster-whisper；不生成音频文件 |
| 临时反思与知识草稿 | Electron 用户数据目录中的 SQLite |
| 已确认知识 | SQLite，或连接后的 Obsidian Vault |
| DeepSeek API Key | 本地 `.env`，不进入安装包或 Git |
| 联网查证查询 | 仅在配置 Tavily 后发送当前问题所需的短查询 |
| 天气位置 | 本机保存缩减精度后的坐标，不发送给 DeepSeek |

Windows 开发环境中的默认数据库位置为：

```text
%APPDATA%\liora-desktop-companion\liora.sqlite3
```

## 技术架构

```text
Electron 桌面 / Linux 小屏界面
              │
              ├── 文字与交互状态
              ├── Vosk 离线唤醒
              └── faster-whisper 本地转写
              │
              ▼
       Python Reflection Service
              │
              ├── DeepSeek / 本地降级策略
              ├── 反思与知识整理
              └── SQLite 状态与全文索引
                          │
                          └── Obsidian Markdown
```

```text
assets/character/  角色状态素材
backend/           Python 反思服务、SQLite、语音与测试
docs/              硬件模式和打包说明
scripts/           启动、模型下载和打包脚本
src/               Electron 主进程、界面和共享业务规则
tests/             Electron 侧业务与语音生命周期测试
```

## 开发与验证

运行 Electron/Node.js 测试：

```powershell
npm.cmd test
```

只运行语音相关测试：

```powershell
npm.cmd run test:voice
```

运行 Python 后端测试：

```powershell
python -m unittest discover -s backend\tests -v
```

Windows 安装程序、本地模型职责和快速重打包方式见[打包说明](docs/packaging.md)。

## Roadmap

- [x] 桌面角色、反思对话与本地知识存储
- [x] 中英文离线唤醒与本地语音转写
- [x] 知识确认、版本修订和 Obsidian 连接
- [x] 桌面与 Linux 小屏双运行模式
- [ ] 语义检索与知识之间的自动关联
- [ ] 基于长期记录的复习提醒
- [ ] 个人认知模型与成长轨迹
- [ ] 在具体小屏硬件上完成语音、功耗和稳定性验证

## 参与项目

欢迎提交 Issue、改进建议和用于非商业目的的 Pull Request。较大的功能改动建议先发起 Issue，说明使用场景和设计方向，以便减少重复工作。

提交代码前请确保：

- 没有提交 `.env`、API Key、数据库或本地模型
- Node.js 与 Python 测试通过
- 新增行为包含相应测试或验证说明
- 贡献内容可以按照本项目许可证用于非商业目的

## 许可证与非商业使用

Liora 采用 [PolyForm Noncommercial License 1.0.0](LICENSE)。

你可以出于个人学习、研究、实验和其他非商业目的阅读、运行、修改和分享本项目。未经单独书面授权，不得将 Liora 或其修改版本用于商业目的。任何商业授权需求请先联系项目维护者。

除另有说明的第三方组件外，仓库中的程序代码、文档和原创视觉素材均受该非商业许可证约束。

由于许可证限制商业使用，Liora 是一个 **source-available（源码可见）项目**，而不是符合 OSI 定义的开源软件。

该许可证不构成对 Liora 名称、标识或品牌身份的商标授权。
