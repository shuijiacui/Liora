# Windows 打包与后续修改

Liora 的安装包是源代码的构建产物，不会替代或锁定 `D:\Liora` 中的项目文件。日后继续修改源码，再重新执行对应命令即可生成新版。

## 两套本地语音模型

- `.models/vosk/`：只用于低延迟、常驻的中英文唤醒词识别（“Hi Liora”）。
- `.models/sensevoice/`：SenseVoice-Small INT8 ONNX，用于唤醒后的语音命令和点击“说完了”后的完整多语言听写。

它们承担的任务不同，与是否部署到硬件无关。当前 Windows 安装包保留了唤醒和听写两项能力，因此同时携带两套模型。SenseVoice 使用单一 INT8 引擎，不再携带 Whisper 回退、PyTorch、CTranslate2 或 PyAV；空闲 180 秒后会卸载模型。如果以后不需要语音唤醒，可以移除 Vosk 监听和模型；如果不需要语音输入，可以进一步移除 SenseVoice。

## 首次准备

安装 Node.js 与项目依赖，并确保 `.models/` 中已有两类模型。可选地创建一套更精简的专用 Python 打包环境：

```powershell
npm.cmd install
npm.cmd run setup:packaging
```

如果专用环境尚未准备好，构建脚本会尝试使用 `LIORA_PYTHON`、当前 Conda 环境或本机的 `ml_env`。

## 生成安装包

Python 后端、依赖或语音模块有改动时，执行完整构建：

```powershell
npm.cmd run dist:win
```

仅修改 Electron 页面、样式、图片或普通 JavaScript 时，可复用已有 Python 运行时并快速构建：

```powershell
npm.cmd run dist:win:fast
```

只生成无需安装的目录版，可分别使用：

```powershell
npm.cmd run pack:win
npm.cmd run pack:win:fast
```

输出位于 `release/`。正式安装程序名为 `Liora-Setup-<版本>-x64.exe`，目录版入口为 `release/win-unpacked/Liora.exe`。

## 安装版配置和数据

- 安装包不会包含项目根目录的 `.env`，避免把 API Key 固化进可分发文件。
- 如需让安装版使用 DeepSeek，在 `%APPDATA%\liora-desktop-companion\.env` 中填写 `DEEPSEEK_API_KEY=...`，完全退出并重启 Liora。
- SQLite、窗口位置、天气、语音和 Obsidian 配置仍保存在 `%APPDATA%\liora-desktop-companion\`，重新打包或覆盖安装不会删除这些数据。
- 当前安装包未做商业代码签名，Windows SmartScreen 可能在首次运行时提示“未知发布者”。

## 发布新版

在 `package.json` 中提升 `version`，运行测试，然后重新执行 `npm.cmd run dist:win`。旧安装版不会影响源码；新版安装程序可覆盖安装，同时保留用户数据。
