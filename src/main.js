const {
  app,
  BrowserWindow,
  dialog,
  Menu,
  Notification,
  Tray,
  ipcMain,
  nativeImage,
  screen,
  session,
  shell
} = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { VoiceService } = require('./services/voice-service');
const { VoiceCommandCoordinator } = require('./services/voice-command-coordinator');
const { createVoiceStatus } = require('./services/voice-state');
const { routeVoiceIntent } = require('./services/voice-intent');
const { shouldAcceptWake } = require('./services/voice-utils');
const {
  WeatherService,
  configuredWeatherSettings,
  reverseGeocodeLocation,
  roundedCoordinates,
  weatherLocationKey,
  weatherLocationNeedsName
} = require('./services/weather-service');
const { loadEnvFile } = require('./services/env-file');
const { createRuntimeProfile } = require('./platform/runtime-profile');
const { createWindowAdapter } = require('./platform/window-adapter');
const { cleanLocationName } = require('./shared/location-name');
const { buildKnowledgePath } = require('./shared/knowledge-query');
const {
  publishConnection: publishKnowledgeEngineConnection,
  removeConnection: removeKnowledgeEngineConnection
} = require('./shared/knowledge-engine-connection');

loadEnvFile(path.join(__dirname, '..', '.env'));
if (process.env.LIORA_USER_DATA_DIR && path.isAbsolute(process.env.LIORA_USER_DATA_DIR)) {
  app.setPath('userData', process.env.LIORA_USER_DATA_DIR);
}
loadEnvFile(path.join(app.getPath('userData'), '.env'));
const runtimeProfile = createRuntimeProfile({ argv: process.argv.slice(1) });

let petWindow = null;
let tray = null;
let isQuitting = false;
let dragSession = null;
let saveTimer = null;
let windowMode = 'compact';
let backendProcess = null;
let backendReady = null;
let backendPort = 0;
let backendToken = '';
let reminderTimer = null;
let voiceService = null;
let voiceReady = false;
let dictationReady = false;
let voiceMode = 'wake';
let whisperStage = 'idle';
let voiceError = '';
let voiceRecognizer = '';
let voiceRestartTimer = null;
let dictationTimer = null;
let lastWakeAt = 0;
let voiceCommandCoordinator = null;
let platformWindow = null;
let weatherService = null;
let weatherLocationResolution = null;

const WAKE_COOLDOWN_MS = 2500;

const hasSingleInstanceLock = app.requestSingleInstanceLock();

if (!hasSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', () => showPet());
}

function projectPath(...segments) {
  return path.join(__dirname, '..', ...segments);
}

function assetPath(...segments) {
  return projectPath('assets', ...segments);
}

function bundledResourcePath(...segments) {
  return app.isPackaged
    ? path.join(process.resourcesPath, ...segments)
    : projectPath(...segments);
}

function packagedRuntimePath() {
  return bundledResourcePath('python', 'liora-runtime', 'liora-runtime.exe');
}

function settingsPath() {
  return path.join(app.getPath('userData'), 'window-state.json');
}

function reminderSettingsPath() {
  return path.join(app.getPath('userData'), 'reminder-settings.json');
}

function voiceSettingsPath() {
  return path.join(app.getPath('userData'), 'voice-settings.json');
}

function weatherSettingsPath() {
  return path.join(app.getPath('userData'), 'weather-settings.json');
}

function knowledgeSettingsPath() {
  return path.join(app.getPath('userData'), 'knowledge-settings.json');
}

function readKnowledgeSettings() {
  try {
    const settings = JSON.parse(fs.readFileSync(knowledgeSettingsPath(), 'utf8'));
    const vaultPath = String(settings.vaultPath || '').trim();
    return vaultPath && fs.statSync(vaultPath).isDirectory() ? { vaultPath } : {};
  } catch {
    return {};
  }
}

function writeKnowledgeSettings(settings) {
  fs.mkdirSync(path.dirname(knowledgeSettingsPath()), { recursive: true });
  fs.writeFileSync(knowledgeSettingsPath(), JSON.stringify(settings, null, 2));
}

async function showKnowledgeResult(title, message, type = 'info') {
  const options = {
    type,
    title,
    message,
    buttons: ['知道了']
  };
  await (petWindow ? dialog.showMessageBox(petWindow, options) : dialog.showMessageBox(options));
}

async function chooseKnowledgeVault() {
  const current = readKnowledgeSettings().vaultPath;
  const options = {
    title: '选择 Obsidian Vault',
    defaultPath: current,
    properties: ['openDirectory']
  };
  const result = await (petWindow ? dialog.showOpenDialog(petWindow, options) : dialog.showOpenDialog(options));
  if (result.canceled || !result.filePaths[0]) return null;
  const vaultPath = path.resolve(result.filePaths[0]);
  const configured = await backendRequest('POST', '/api/storage/configure', { vault_path: vaultPath });
  writeKnowledgeSettings({ vaultPath });
  const scan = configured.scan || {};
  await showKnowledgeResult(
    '知识库已连接',
    `已连接到：${vaultPath}\n\n扫描 ${scan.scanned || 0} 个 Markdown 文件，当前索引 ${scan.active || 0} 条知识。`
  );
  tray?.setContextMenu(trayMenu());
  return configured;
}

async function scanKnowledgeVault() {
  const payload = await backendRequest('POST', '/api/storage/scan', {});
  const scan = payload.scan || {};
  await showKnowledgeResult(
    '知识索引已刷新',
    `扫描 ${scan.scanned || 0} 个文件；新增 ${scan.indexed || 0}，更新 ${scan.updated || 0}，移除 ${scan.deleted || 0}，错误 ${scan.errors || 0}。`,
    scan.errors ? 'warning' : 'info'
  );
  return payload;
}

async function rebuildKnowledgeVault() {
  const payload = await backendRequest('POST', '/api/storage/rebuild', {});
  const scan = payload.scan || {};
  await showKnowledgeResult(
    '知识索引已重建',
    `已重新解析 ${scan.scanned || 0} 个 Markdown 文件，当前索引 ${scan.active || 0} 条，错误 ${scan.errors || 0}。`,
    scan.errors ? 'warning' : 'info'
  );
  return payload;
}

async function migrateKnowledgeToVault() {
  const options = {
    type: 'question',
    title: '迁移现有知识',
    message: '将 SQLite 中现有的知识导出到 Obsidian？',
    detail: '迁移前会自动备份数据库。该操作可重复执行，不会重复创建已经迁移的知识。',
    buttons: ['开始迁移', '取消'],
    defaultId: 0,
    cancelId: 1
  };
  const confirmation = await (petWindow ? dialog.showMessageBox(petWindow, options) : dialog.showMessageBox(options));
  if (confirmation.response !== 0) return null;
  const payload = await backendRequest('POST', '/api/storage/migrate', {});
  const migration = payload.migration || {};
  const backup = migration.backup_path ? `\n备份：${migration.backup_path}` : '';
  await showKnowledgeResult(
    '知识迁移完成',
    `共 ${migration.total || 0} 条；迁移 ${migration.migrated || 0}，跳过 ${migration.skipped || 0}，失败 ${migration.failed || 0}。${backup}`,
    migration.failed ? 'warning' : 'info'
  );
  return payload;
}

function readVoiceSettings() {
  try {
    return { enabled: true, ...JSON.parse(fs.readFileSync(voiceSettingsPath(), 'utf8')) };
  } catch {
    return { enabled: true };
  }
}

function writeVoiceSettings(settings) {
  fs.mkdirSync(path.dirname(voiceSettingsPath()), { recursive: true });
  fs.writeFileSync(voiceSettingsPath(), JSON.stringify(settings, null, 2));
}

function readWeatherSettings() {
  try {
    return JSON.parse(fs.readFileSync(weatherSettingsPath(), 'utf8'));
  } catch {
    return {};
  }
}

function writeWeatherSettings(settings) {
  fs.mkdirSync(path.dirname(weatherSettingsPath()), { recursive: true });
  fs.writeFileSync(weatherSettingsPath(), JSON.stringify(settings, null, 2));
}

function readReminderSettings() {
  try {
    return {
      enabled: true,
      lastShownDate: '',
      ...JSON.parse(fs.readFileSync(reminderSettingsPath(), 'utf8'))
    };
  } catch {
    return { enabled: true, lastShownDate: '' };
  }
}

function writeReminderSettings(settings) {
  fs.mkdirSync(path.dirname(reminderSettingsPath()), { recursive: true });
  fs.writeFileSync(reminderSettingsPath(), JSON.stringify(settings, null, 2));
}

function localDateKey(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  const pad = (part) => String(part).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function markReminderHandledToday() {
  const settings = readReminderSettings();
  writeReminderSettings({ ...settings, lastShownDate: localDateKey() });
}

function readSavedPosition() {
  if (!runtimeProfile.capabilities.windowDrag) return null;
  try {
    const value = JSON.parse(fs.readFileSync(settingsPath(), 'utf8'));
    if (Number.isFinite(value.x) && Number.isFinite(value.y)) {
      return { x: Math.round(value.x), y: Math.round(value.y) };
    }
  } catch {
    // The first launch has no saved state, so the default dock is used.
  }
  return null;
}

function savePosition() {
  const compactPosition = platformWindow?.savedPosition(petWindow);
  if (!compactPosition) return;

  try {
    fs.mkdirSync(path.dirname(settingsPath()), { recursive: true });
    fs.writeFileSync(settingsPath(), JSON.stringify(compactPosition, null, 2));
  } catch (error) {
    console.warn('Could not save Liora window position:', error.message);
  }
}

function schedulePositionSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(savePosition, 250);
}

function setWindowMode(mode) {
  if (!petWindow || petWindow.isDestroyed() || mode === windowMode) {
    return;
  }
  windowMode = mode;
  platformWindow.setWindowMode(petWindow, mode);
  schedulePositionSave();
}

function dockPet() {
  if (!petWindow || petWindow.isDestroyed()) {
    return;
  }
  platformWindow.dockWindow(petWindow);
  savePosition();
}

function showPet() {
  if (!petWindow || petWindow.isDestroyed()) {
    return;
  }
  platformWindow.showWindow(petWindow);
  petWindow.webContents.send('pet:enter');
}

function openReflection() {
  markReminderHandledToday();
  showPet();
  setWindowMode('dialog');
  petWindow?.webContents.send('reflection:open');
}

function openReview() {
  showPet();
  setWindowMode('dialog');
  petWindow?.webContents.send('review:open');
}

function togglePet() {
  if (!petWindow || petWindow.isDestroyed()) {
    return;
  }
  if (!runtimeProfile.capabilities.hideToTray) {
    showPet();
    return;
  }
  if (petWindow.isVisible()) {
    void cancelDictation();
    platformWindow.hideWindow(petWindow);
  } else {
    showPet();
  }
}

function setLaunchAtLogin(enabled) {
  app.setLoginItemSettings({
    openAtLogin: enabled,
    path: process.execPath,
    args: app.isPackaged ? [] : [projectPath()]
  });
}

function setDailyReminder(enabled) {
  const settings = readReminderSettings();
  writeReminderSettings({ ...settings, enabled });
  tray?.setContextMenu(trayMenu());
  if (enabled) maybeShowDailyReminder();
}

function voiceStatus() {
  return createVoiceStatus({
    backendAvailable: dictationReady,
    wakeEnabled: runtimeProfile.capabilities.wakeWord && readVoiceSettings().enabled,
    wakeReady: voiceService?.isReady() ?? voiceReady,
    mode: voiceMode,
    stage: whisperStage,
    error: voiceError,
    recognizer: voiceRecognizer
  });
}

function sendVoiceStatus() {
  if (petWindow && !petWindow.isDestroyed()) {
    petWindow.webContents.send('voice:status', voiceStatus());
  }
}

function resetDictationTimeout() {
  clearTimeout(dictationTimer);
  if (voiceMode === 'dictation') {
    dictationTimer = setTimeout(() => void finishDictation(), 60_000);
  }
}

function returnToWakeMode() {
  voiceMode = 'wake';
  whisperStage = 'idle';
  voiceReady = voiceService?.isReady() ?? false;
  resetDictationTimeout();
  sendVoiceStatus();
  if (
    runtimeProfile.capabilities.wakeWord
    && !voiceService?.isRunning()
    && !isQuitting
    && readVoiceSettings().enabled
  ) {
    clearTimeout(voiceRestartTimer);
    voiceRestartTimer = setTimeout(startVoiceRecognition, 300);
  }
}

async function startDictation() {
  if (!dictationReady || voiceMode === 'dictation') return voiceStatus();
  voiceCommandCoordinator?.cancel();
  clearTimeout(voiceRestartTimer);
  voiceMode = 'dictation';
  whisperStage = 'loading';
  voiceError = '';
  voiceReady = false;
  await voiceService?.stop();
  resetDictationTimeout();
  sendVoiceStatus();
  try {
    const status = await backendRequest('POST', '/api/voice/start', {});
    whisperStage = status.state || whisperStage;
    sendVoiceStatus();
  } catch (error) {
    voiceError = `本地语音转写启动失败：${error.message}`;
    returnToWakeMode();
  }
  return voiceStatus();
}

async function finishDictation() {
  if (voiceMode !== 'dictation') return voiceStatus();
  clearTimeout(dictationTimer);
  try {
    await backendRequest('POST', '/api/voice/stop', {});
  } catch (error) {
    voiceError = `停止语音输入失败：${error.message}`;
    returnToWakeMode();
  }
  return voiceStatus();
}

async function cancelDictation() {
  clearTimeout(dictationTimer);
  if (voiceMode !== 'dictation') {
    if (!voiceService?.isRunning() && readVoiceSettings().enabled) startVoiceRecognition();
    sendVoiceStatus();
    return voiceStatus();
  }
  try {
    await backendRequest('POST', '/api/voice/cancel', {});
  } catch (error) {
    console.warn(`Could not cancel Liora dictation: ${error.message}`);
  }
  returnToWakeMode();
  return voiceStatus();
}

function handleBackendVoiceEvent(event) {
  if (!event || typeof event !== 'object') return;
  if (event.type === 'voice-warning') {
    console.warn(`Liora voice: ${event.message || 'unknown warning'}`);
    return;
  }
  if (event.type === 'voice-transcript') {
    if (voiceMode !== 'dictation') return;
    petWindow?.webContents.send('voice:transcript', event);
    returnToWakeMode();
    return;
  }
  if (event.type !== 'voice-status') return;
  whisperStage = event.state || whisperStage;
  if (event.error) voiceError = event.error;
  sendVoiceStatus();
  if (voiceMode === 'dictation' && (event.state === 'idle' || event.state === 'error')) {
    returnToWakeMode();
  }
}

function handleRecognizedSpeech(event) {
  if (voiceMode !== 'wake' || !shouldAcceptWake(event)) return;
  const now = Date.now();
  if (now - lastWakeAt < WAKE_COOLDOWN_MS) return;
  lastWakeAt = now;
  const session = getVoiceCommandCoordinator().start(event.session_id || randomUUID());
  showPet();
  setWindowMode('dialog');
  petWindow?.webContents.send('voice:wake', { sessionId: session.id });
}

function sendVoiceClarification({ transcript, route, reason }) {
  let message = '我听到了，但还不能确定你想进入反思、回顾、知识还是天气。';
  if (reason === 'low-confidence') {
    message = '这句话我没有听清。你可以再说一次“Hi Liora”，然后自然地告诉我想做什么。';
  } else if (route?.ambiguous) {
    message = '这句话里有不止一个方向，我先不替你决定。你想反思、回顾、看知识，还是问天气？';
  } else if (reason === 'timeout') {
    message = '我在听，不过没有听到后续内容。需要时再叫我一声。';
  }
  petWindow?.webContents.send('voice:clarify', {
    message,
    transcript: String(transcript || '').slice(0, 160)
  });
}

function getVoiceCommandCoordinator() {
  if (voiceCommandCoordinator) return voiceCommandCoordinator;
  voiceCommandCoordinator = new VoiceCommandCoordinator({
    transcribe: (event) => backendRequest('POST', '/api/voice/command-transcript', {
      encoding: event.encoding,
      sample_rate: event.sample_rate,
      audio: event.audio
    }),
    routeIntent: routeVoiceIntent,
    onRoute: (event) => petWindow?.webContents.send('voice:command', event),
    onClarify: sendVoiceClarification
  });
  return voiceCommandCoordinator;
}

function handleVoiceCommandAudio(event) {
  if (voiceMode === 'wake' && getVoiceCommandCoordinator().enqueue(event)) {
    petWindow?.webContents.send('voice:processing');
  }
}

function handleVoiceCommandTimeout(event) {
  getVoiceCommandCoordinator().timeout(event?.session_id);
}

function initializeVoiceService() {
  if (voiceService || !runtimeProfile.capabilities.wakeWord) return;
  const packaged = app.isPackaged;
  voiceService = new VoiceService(packaged ? 'wake' : projectPath('backend', 'wake_listener.py'), {
    command: packaged ? packagedRuntimePath() : findPythonExecutable(),
    commandArguments: (scriptPath, mode) => packaged
      ? [
          'wake',
          '--models-dir',
          bundledResourcePath('models', 'vosk'),
          '--mode',
          String(mode || 'wake').toLowerCase()
        ]
      : [
          '-u',
          scriptPath,
          '--models-dir',
          projectPath('.models', 'vosk'),
          '--mode',
          String(mode || 'wake').toLowerCase()
        ]
  });
  voiceService.on('ready', (event) => {
    voiceReady = true;
    voiceError = '';
    voiceRecognizer = Array.isArray(event.recognizers)
      ? event.recognizers.map((item) => `${item.description || ''} ${item.culture || ''}`.trim()).join(' + ')
      : `${event.recognizer || ''} ${event.culture || ''}`.trim();
    sendVoiceStatus();
    tray?.setContextMenu(trayMenu());
  });
  voiceService.on('recognized', handleRecognizedSpeech);
  voiceService.on('command-audio', handleVoiceCommandAudio);
  voiceService.on('command-timeout', handleVoiceCommandTimeout);
  voiceService.on('warning', (event) => console.warn(`Liora voice: ${event.message}`));
  voiceService.on('error', (event) => {
    voiceReady = false;
    voiceError = event.message || '语音识别启动失败。';
    sendVoiceStatus();
  });
  voiceService.on('exit', (event) => {
    voiceReady = false;
    sendVoiceStatus();
    if (!event.intentional && !isQuitting && readVoiceSettings().enabled) {
      voiceMode = 'wake';
      clearTimeout(voiceRestartTimer);
      voiceRestartTimer = setTimeout(startVoiceRecognition, 5000);
    }
  });
}

function startVoiceRecognition() {
  if (!readVoiceSettings().enabled || !runtimeProfile.capabilities.wakeWord) return;
  initializeVoiceService();
  voiceError = '';
  if (voiceMode !== 'wake') return;
  voiceService.start('Wake');
  sendVoiceStatus();
}

function setVoiceEnabled(enabled) {
  if (!runtimeProfile.capabilities.wakeWord) return;
  writeVoiceSettings({ enabled });
  clearTimeout(voiceRestartTimer);
  if (enabled) {
    startVoiceRecognition();
  } else {
    voiceCommandCoordinator?.cancel();
    voiceReady = false;
    voiceMode = 'wake';
    whisperStage = 'idle';
    voiceError = '';
    void voiceService?.stop();
    void backendRequest('POST', '/api/voice/cancel', {}).catch(() => {});
    sendVoiceStatus();
  }
  tray?.setContextMenu(trayMenu());
}

function disableWeather() {
  writeWeatherSettings({
    ...readWeatherSettings(),
    enabled: false,
    updatedAt: new Date().toISOString()
  });
  weatherLocationResolution = null;
  initializeWeatherService();
}

function trayMenu() {
  const openAtLogin = app.getLoginItemSettings().openAtLogin;
  const knowledgeConfigured = Boolean(readKnowledgeSettings().vaultPath);
  const weatherConfigured = Boolean(weatherService?.status().configured);
  return Menu.buildFromTemplate([
    { label: '开始今日反思', click: openReflection },
    { label: '开始知识回顾', click: openReview },
    { type: 'separator' },
    {
      label: petWindow?.isVisible() ? '隐藏 Liora' : '显示 Liora',
      click: togglePet
    },
    {
      label: '回到右下角',
      click: () => {
        dockPet();
        showPet();
      }
    },
    { type: 'separator' },
    {
      label: '开机启动',
      type: 'checkbox',
      checked: openAtLogin,
      click: (menuItem) => setLaunchAtLogin(menuItem.checked)
    },
    {
      label: '每日反思提醒（20:00 后）',
      type: 'checkbox',
      checked: readReminderSettings().enabled,
      click: (menuItem) => setDailyReminder(menuItem.checked)
    },
    {
      label: weatherConfigured ? '更新天气位置' : '启用天气（使用当前位置）',
      click: requestWeatherLocation
    },
    {
      label: '关闭天气',
      visible: weatherConfigured,
      click: disableWeather
    },
    {
      label: '语音唤醒（说“Hi Liora”）',
      type: 'checkbox',
      enabled: runtimeProfile.capabilities.wakeWord,
      checked: runtimeProfile.capabilities.wakeWord && readVoiceSettings().enabled,
      click: (menuItem) => setVoiceEnabled(menuItem.checked)
    },
    { type: 'separator' },
    {
      label: knowledgeConfigured ? '更换 Obsidian 知识库…' : '连接 Obsidian 知识库…',
      click: () => void chooseKnowledgeVault().catch((error) => showKnowledgeResult('无法连接知识库', error.message, 'error'))
    },
    {
      label: '刷新知识索引',
      enabled: knowledgeConfigured,
      click: () => void scanKnowledgeVault().catch((error) => showKnowledgeResult('刷新失败', error.message, 'error'))
    },
    {
      label: '重建知识索引',
      enabled: knowledgeConfigured,
      click: () => void rebuildKnowledgeVault().catch((error) => showKnowledgeResult('重建失败', error.message, 'error'))
    },
    {
      label: '迁移 SQLite 知识到 Obsidian…',
      enabled: knowledgeConfigured,
      click: () => void migrateKnowledgeToVault().catch((error) => showKnowledgeResult('迁移失败', error.message, 'error'))
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => {
        isQuitting = true;
        app.quit();
      }
    }
  ]);
}

function showTrayMenu() {
  tray?.popUpContextMenu(trayMenu());
}

function createTray() {
  if (!runtimeProfile.capabilities.tray) return;
  const sourceImage = nativeImage.createFromPath(assetPath('character', 'idle.png'));
  const size = sourceImage.getSize();
  const headCrop = sourceImage.crop({
    x: Math.round(size.width * 0.13),
    y: Math.round(size.height * 0.04),
    width: Math.round(size.width * 0.74),
    height: Math.round(size.height * 0.58)
  });
  tray = new Tray(headCrop.resize({ width: 32, height: 32, quality: 'best' }));
  tray.setToolTip('Liora · 桌面反思伙伴');
  tray.setContextMenu(trayMenu());
  tray.on('click', togglePet);
}

async function maybeShowDailyReminder() {
  const settings = readReminderSettings();
  const now = new Date();
  const today = localDateKey(now);
  if (!settings.enabled || now.getHours() < 20 || settings.lastShownDate === today) {
    return;
  }

  try {
    const history = await backendRequest('GET', '/api/reflections?limit=20');
    const completedToday = history.sessions.some(
      (session) => session.session_type !== 'review'
        && session.completed_at
        && localDateKey(session.completed_at) === today
    );
    if (completedToday) {
      markReminderHandledToday();
      return;
    }
  } catch (error) {
    console.warn('Could not check daily reflection status:', error.message);
    return;
  }

  markReminderHandledToday();
  platformWindow.presentReminder(
    petWindow,
    { title: 'Liora 想听听你的今天', body: '今天有什么值得留下来的知识？' },
    openReflection
  );
}

function scheduleDailyReminder() {
  setTimeout(maybeShowDailyReminder, 15_000);
  reminderTimer = setInterval(maybeShowDailyReminder, 15 * 60 * 1000);
}

function sendWeatherStatus() {
  if (petWindow && !petWindow.isDestroyed()) {
    petWindow.webContents.send('weather:update', weatherService?.status() || { configured: false });
  }
}

function currentWeatherSettings() {
  return configuredWeatherSettings(process.env, readWeatherSettings());
}

function isCurrentLocationResolution(attempt) {
  const latest = currentWeatherSettings();
  return weatherLocationNeedsName(latest) && weatherLocationKey(latest) === attempt.key;
}

function initializeWeatherService() {
  weatherService?.stop();
  const settings = currentWeatherSettings();
  const service = new WeatherService(settings);
  weatherService = service;
  service.on('update', () => {
    if (weatherService !== service) return;
    sendWeatherStatus();
    tray?.setContextMenu(trayMenu());
  });
  service.on('reminder', (reminder) => {
    if (weatherService !== service) return;
    platformWindow.presentReminder(
      petWindow,
      { title: reminder.title, body: reminder.body },
      showPet
    );
  });
  service.on('warning', (error) => {
    if (weatherService !== service) return;
    console.warn(`Could not refresh Liora weather: ${error.message}`);
  });
  service.start();
  sendWeatherStatus();
  tray?.setContextMenu(trayMenu());

  if (weatherLocationNeedsName(settings)) {
    const key = weatherLocationKey(settings);
    if (weatherLocationResolution?.key === key) return;

    const attempt = { key, promise: null };
    weatherLocationResolution = attempt;
    attempt.promise = reverseGeocodeLocation(settings)
      .then((value) => {
        const location = cleanLocationName(value);
        if (!location || !isCurrentLocationResolution(attempt)) return;
        const latest = currentWeatherSettings();
        writeWeatherSettings({
          ...readWeatherSettings(),
          enabled: true,
          latitude: latest.latitude,
          longitude: latest.longitude,
          location,
          source: latest.source,
          updatedAt: new Date().toISOString()
        });
        initializeWeatherService();
      })
      .catch((error) => {
        if (isCurrentLocationResolution(attempt)) {
          console.warn(`Could not resolve saved weather location name: ${error.message}`);
        }
      })
      .finally(() => {
        if (weatherLocationResolution === attempt) weatherLocationResolution = null;
      });
  }
}

function requestWeatherLocation() {
  showPet();
  petWindow?.webContents.send('weather:request-location');
}

function isTrustedRenderer(webContents, requestingOrigin = '') {
  if (!webContents || BrowserWindow.fromWebContents(webContents) !== petWindow) return false;
  try {
    const target = new URL(requestingOrigin || webContents.getURL());
    return target.protocol === 'file:';
  } catch {
    return false;
  }
}

function configureSessionPermissions() {
  session.defaultSession.setPermissionCheckHandler((webContents, permission, requestingOrigin) => {
    return permission === 'geolocation' && isTrustedRenderer(webContents, requestingOrigin);
  });
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback, details) => {
    const requestingUrl = details?.requestingUrl || webContents?.getURL() || '';
    callback(permission === 'geolocation' && isTrustedRenderer(webContents, requestingUrl));
  });
}

function createPetWindow() {
  petWindow = platformWindow.createWindow(readSavedPosition());
  petWindow.once('ready-to-show', showPet);
  if (runtimeProfile.capabilities.windowDrag) {
    petWindow.on('move', schedulePositionSave);
  }
  petWindow.on('show', () => tray?.setContextMenu(trayMenu()));
  petWindow.on('hide', () => tray?.setContextMenu(trayMenu()));
  petWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      if (runtimeProfile.capabilities.hideToTray) {
        platformWindow.hideWindow(petWindow);
      } else {
        platformWindow.showWindow(petWindow);
      }
    }
  });
  petWindow.on('closed', () => {
    petWindow = null;
  });
}

function pythonFromIdeaConfig() {
  try {
    const xml = fs.readFileSync(projectPath('.idea', 'misc.xml'), 'utf8');
    const match = xml.match(/project-jdk-name="([^"]+)"/);
    if (!match) {
      return null;
    }
    const sdkPath = match[1];
    return process.platform === 'win32'
      ? path.join(sdkPath, 'python.exe')
      : path.join(sdkPath, 'bin', 'python');
  } catch {
    return null;
  }
}

function findPythonExecutable() {
  const executableName = process.platform === 'win32' ? 'python.exe' : 'python';
  const candidates = [
    process.env.LIORA_PYTHON,
    process.env.CONDA_PREFIX ? path.join(process.env.CONDA_PREFIX, executableName) : null,
    pythonFromIdeaConfig(),
    path.join(os.homedir(), '.conda', 'envs', 'ml_env', executableName),
    process.platform === 'win32' ? null : '/usr/bin/python3',
    process.platform === 'win32' ? null : '/usr/local/bin/python3'
  ].filter(Boolean);
  const found = candidates.find((candidate) => path.isAbsolute(candidate) && fs.existsSync(candidate));
  if (!found) {
    throw new Error('没有找到 Python。请通过 LIORA_PYTHON 指定 Python 3.10+ 解释器。');
  }
  return found;
}

function findAvailablePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      server.close(() => resolve(address.port));
    });
  });
}

async function startBackend() {
  backendPort = await findAvailablePort();
  backendToken = randomUUID();
  const packaged = app.isPackaged;
  const python = packaged ? packagedRuntimePath() : findPythonExecutable();
  const args = [
    ...(packaged ? ['backend'] : ['-u', projectPath('backend', 'main.py')]),
    '--data-dir',
    app.getPath('userData'),
    '--port',
    String(backendPort),
    '--token',
    backendToken,
    '--models-dir',
    bundledResourcePath('models')
  ];
  const vaultPath = readKnowledgeSettings().vaultPath;
  if (vaultPath) args.push('--vault-path', vaultPath);

  return new Promise((resolve, reject) => {
    let settled = false;
    let errorText = '';
    let stdoutBuffer = '';
    backendProcess = spawn(python, args, {
      cwd: packaged ? app.getPath('userData') : projectPath(),
      env: {
        ...process.env,
        PYTHONIOENCODING: 'utf-8',
        PYTHONUTF8: '1'
      },
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe']
    });

    const timeout = setTimeout(() => {
      if (!settled) {
        settled = true;
        reject(new Error(`Python 后端启动超时。${errorText}`));
      }
    }, packaged ? 20_000 : 8000);

    backendProcess.stdout.setEncoding('utf8');
    backendProcess.stdout.on('data', (chunk) => {
      stdoutBuffer += chunk;
      const lines = stdoutBuffer.split(/\r?\n/);
      stdoutBuffer = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith('LIORA_BACKEND_READY') && !settled) {
          settled = true;
          clearTimeout(timeout);
          resolve();
          continue;
        }
        if (line.startsWith('LIORA_VOICE_EVENT ')) {
          try {
            handleBackendVoiceEvent(JSON.parse(line.slice('LIORA_VOICE_EVENT '.length)));
          } catch (error) {
            console.warn(`Could not read Liora voice event: ${error.message}`);
          }
          continue;
        }
        if (line.startsWith('LIORA_REFLECTION_EVENT ')) {
          try {
            const event = JSON.parse(line.slice('LIORA_REFLECTION_EVENT '.length));
            if (event?.type === 'review-task-started') {
              showPet();
              petWindow?.webContents.send('review:open', event);
            }
          } catch (error) {
            console.warn(`Could not read Liora reflection event: ${error.message}`);
          }
        }
      }
    });
    backendProcess.stderr.setEncoding('utf8');
    backendProcess.stderr.on('data', (chunk) => {
      errorText += chunk;
      console.warn(`Liora backend: ${chunk.trim()}`);
    });
    backendProcess.on('error', (error) => {
      if (!settled) {
        settled = true;
        clearTimeout(timeout);
        reject(error);
      }
    });
    backendProcess.on('exit', (code) => {
      backendProcess = null;
      dictationReady = false;
      sendVoiceStatus();
      if (!settled) {
        settled = true;
        clearTimeout(timeout);
        reject(new Error(`Python 后端提前退出（${code}）。${errorText}`));
      }
    });
  });
}

async function backendRequest(method, requestPath, payload) {
  await backendReady;
  const body = payload === undefined ? null : Buffer.from(JSON.stringify(payload));
  const aiRequest = requestPath.endsWith('/finish')
    || requestPath.endsWith('/revise')
    || requestPath.includes('/messages')
    || requestPath === '/api/voice/command-transcript';
  const requestTimeout = aiRequest ? 75_000 : 8_000;
  return new Promise((resolve, reject) => {
    const request = http.request(
      {
        host: '127.0.0.1',
        port: backendPort,
        path: requestPath,
        method,
        headers: {
          'X-Liora-Token': backendToken,
          ...(body
            ? { 'Content-Type': 'application/json', 'Content-Length': body.length }
            : {})
        },
        timeout: requestTimeout
      },
      (response) => {
        const chunks = [];
        response.on('data', (chunk) => chunks.push(chunk));
        response.on('end', () => {
          try {
            const value = JSON.parse(Buffer.concat(chunks).toString('utf8'));
            if (response.statusCode >= 400) {
              reject(new Error(value.error || '反思服务暂时不可用。'));
            } else {
              resolve(value);
            }
          } catch {
            reject(new Error('反思服务返回了无法读取的数据。'));
          }
        });
      }
    );
    request.on('timeout', () => request.destroy(new Error('反思服务响应超时。')));
    request.on('error', reject);
    if (body) {
      request.write(body);
    }
    request.end();
  });
}

function isPetSender(event) {
  return BrowserWindow.fromWebContents(event.sender) === petWindow;
}

function registerIpc() {
  ipcMain.on('window:drag-start', (event) => {
    if (!isPetSender(event) || !runtimeProfile.capabilities.windowDrag) return;
    dragSession = {
      window: petWindow,
      cursor: screen.getCursorScreenPoint(),
      bounds: petWindow.getBounds()
    };
  });

  ipcMain.on('window:drag-move', (event) => {
    if (!dragSession || !isPetSender(event) || !runtimeProfile.capabilities.windowDrag) return;
    const cursor = screen.getCursorScreenPoint();
    const size = { width: dragSession.bounds.width, height: dragSession.bounds.height };
    const target = platformWindow.clampToWorkArea(
      {
        x: dragSession.bounds.x + cursor.x - dragSession.cursor.x,
        y: dragSession.bounds.y + cursor.y - dragSession.cursor.y
      },
      size
    );
    dragSession.window.setBounds({ ...target, ...size }, false);
  });

  ipcMain.on('window:drag-end', (event) => {
    if (dragSession && isPetSender(event) && runtimeProfile.capabilities.windowDrag) {
      savePosition();
      dragSession = null;
    }
  });

  ipcMain.on('window:hide', (event) => {
    if (isPetSender(event) && runtimeProfile.capabilities.hideToTray) {
      void cancelDictation();
      platformWindow.hideWindow(petWindow);
    }
  });
  ipcMain.on('tray:open-menu', (event) => {
    if (isPetSender(event) && runtimeProfile.capabilities.tray) showTrayMenu();
  });
  ipcMain.handle('platform:get-info', (event) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return runtimeProfile;
  });
  ipcMain.handle('weather:get-status', (event) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return weatherService?.status() || { configured: false };
  });
  ipcMain.handle('weather:set-location', async (event, payload) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    const coordinates = roundedCoordinates(payload?.latitude, payload?.longitude);
    if (!coordinates) throw new Error('定位结果无效，请手动配置城市。');
    let location = cleanLocationName(payload?.location);
    if (!location) {
      try {
        location = cleanLocationName(await reverseGeocodeLocation(coordinates));
      } catch (error) {
        console.warn(`Could not resolve Liora weather location name: ${error.message}`);
      }
    }
    writeWeatherSettings({
      enabled: true,
      ...coordinates,
      location: location || '当前位置',
      source: 'geolocation',
      updatedAt: new Date().toISOString()
    });
    initializeWeatherService();
    return weatherService.status();
  });
  ipcMain.handle('dialog:set-open', async (event, open) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    setWindowMode(open ? 'dialog' : 'compact');
    if (!open) await cancelDictation();
    return { ok: true };
  });
  ipcMain.handle('voice:get-status', (event) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return voiceStatus();
  });
  ipcMain.handle('voice:set-dictation', async (event, active) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return active ? startDictation() : finishDictation();
  });
  ipcMain.handle('reflection:start', (event, forceNew = false, knowledgeId = null) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return backendRequest('POST', '/api/reflections/start', {
      force_new: Boolean(forceNew),
      knowledge_id: knowledgeId || null
    });
  });
  ipcMain.handle('reflection:send', (event, sessionId, content) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return backendRequest('POST', `/api/reflections/${encodeURIComponent(sessionId)}/messages`, { content });
  });
  ipcMain.handle('reflection:finish', (event, sessionId) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return backendRequest('POST', `/api/reflections/${encodeURIComponent(sessionId)}/finish`, {});
  });
  ipcMain.handle('reflection:update-draft', (event, sessionId, content) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return backendRequest('POST', `/api/reflections/${encodeURIComponent(sessionId)}/draft`, { content });
  });
  ipcMain.handle('reflection:revise-draft', (event, sessionId, content, instruction) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return backendRequest('POST', `/api/reflections/${encodeURIComponent(sessionId)}/revise`, {
      content,
      instruction
    });
  });
  ipcMain.handle('reflection:confirm', (event, sessionId) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return backendRequest('POST', `/api/reflections/${encodeURIComponent(sessionId)}/confirm`, {});
  });
  ipcMain.handle('review:start', (event) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return backendRequest('POST', '/api/reviews/start', {});
  });
  ipcMain.handle('review:defer', (event, sessionId, days = 3) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return backendRequest('POST', `/api/reflections/${encodeURIComponent(sessionId)}/defer`, { days });
  });
  ipcMain.handle('reflection:rate', (event, sessionId, rating, independentRecall = null) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return backendRequest('POST', `/api/reflections/${encodeURIComponent(sessionId)}/rate`, {
      rating,
      independent_recall: typeof independentRecall === 'boolean' ? independentRecall : null
    });
  });
  ipcMain.handle('reflection:discard', (event, sessionId) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return backendRequest('POST', `/api/reflections/${encodeURIComponent(sessionId)}/discard`, {});
  });
  ipcMain.handle('reflection:history', (event) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return backendRequest('GET', '/api/reflections?limit=20');
  });
  ipcMain.handle('knowledge:open-source', async (event, value) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    const url = new URL(String(value || ''));
    if (!['http:', 'https:'].includes(url.protocol)) throw new Error('不支持的来源链接。');
    await shell.openExternal(url.toString());
    return { ok: true };
  });
  ipcMain.handle('knowledge:list', (event, options = {}) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return backendRequest('GET', buildKnowledgePath(options));
  });
  ipcMain.handle('knowledge:get', (event, knowledgeId) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return backendRequest('GET', `/api/knowledge/${encodeURIComponent(knowledgeId)}`);
  });
  ipcMain.handle('knowledge:storage-status', (event) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return backendRequest('GET', '/api/storage');
  });
  ipcMain.handle('knowledge:choose-vault', (event) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return chooseKnowledgeVault();
  });
  ipcMain.handle('knowledge:scan', (event) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return scanKnowledgeVault();
  });
  ipcMain.handle('knowledge:rebuild', (event) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return rebuildKnowledgeVault();
  });
  ipcMain.handle('knowledge:migrate', (event) => {
    if (!isPetSender(event)) throw new Error('unauthorized');
    return migrateKnowledgeToVault();
  });
}

app.whenReady().then(() => {
  app.setAppUserModelId(
    runtimeProfile.mode === 'desktop' ? 'com.liora.desktop-companion' : 'com.liora.device'
  );
  platformWindow = createWindowAdapter({
    profile: runtimeProfile,
    BrowserWindow,
    Notification,
    screen,
    preloadPath: path.join(__dirname, 'preload.js'),
    indexPath: path.join(__dirname, 'index.html')
  });
  configureSessionPermissions();
  backendReady = startBackend();
  backendReady.then(() => {
    try {
      publishKnowledgeEngineConnection(app.getPath('userData'), {
        port: backendPort,
        token: backendToken
      });
    } catch (error) {
      console.warn(`Unable to publish Knowledge Engine connection: ${error.message}`);
    }
    dictationReady = true;
    sendVoiceStatus();
  }).catch((error) => console.error('Unable to start Liora backend:', error.message));
  registerIpc();
  createPetWindow();
  createTray();
  initializeWeatherService();
  scheduleDailyReminder();
  startVoiceRecognition();
});

app.on('activate', showPet);
app.on('window-all-closed', () => {
  // Liora keeps living in the tray until the user explicitly exits.
});
app.on('before-quit', () => {
  isQuitting = true;
  savePosition();
  clearInterval(reminderTimer);
  clearTimeout(voiceRestartTimer);
  clearTimeout(dictationTimer);
  weatherService?.stop();
  void voiceService?.stop();
  try {
    removeKnowledgeEngineConnection(app.getPath('userData'), backendToken);
  } catch (error) {
    console.warn(`Unable to remove Knowledge Engine connection: ${error.message}`);
  }
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});
