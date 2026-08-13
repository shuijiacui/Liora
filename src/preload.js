const { contextBridge, ipcRenderer } = require('electron');

function subscribe(channel, callback) {
  const listener = (_event, ...args) => callback(...args);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
}

contextBridge.exposeInMainWorld('liora', {
  platformInfo: () => ipcRenderer.invoke('platform:get-info'),
  weatherStatus: () => ipcRenderer.invoke('weather:get-status'),
  setWeatherLocation: (location) => ipcRenderer.invoke('weather:set-location', location),
  beginDrag: () => ipcRenderer.send('window:drag-start'),
  moveDrag: () => ipcRenderer.send('window:drag-move'),
  endDrag: () => ipcRenderer.send('window:drag-end'),
  hide: () => ipcRenderer.send('window:hide'),
  openMenu: () => ipcRenderer.send('tray:open-menu'),
  setDialogOpen: (open) => ipcRenderer.invoke('dialog:set-open', open),
  startReflection: (forceNew = false, knowledgeId = null) => ipcRenderer.invoke('reflection:start', forceNew, knowledgeId),
  startReview: () => ipcRenderer.invoke('review:start'),
  sendReflection: (sessionId, content) => ipcRenderer.invoke('reflection:send', sessionId, content),
  finishReflection: (sessionId) => ipcRenderer.invoke('reflection:finish', sessionId),
  updateReflectionDraft: (sessionId, content) => ipcRenderer.invoke('reflection:update-draft', sessionId, content),
  reviseReflectionDraft: (sessionId, content, instruction) => ipcRenderer.invoke('reflection:revise-draft', sessionId, content, instruction),
  confirmReflection: (sessionId) => ipcRenderer.invoke('reflection:confirm', sessionId),
  rateReflection: (sessionId, rating, independentRecall = null) => ipcRenderer.invoke(
    'reflection:rate', sessionId, rating, independentRecall
  ),
  discardReflection: (sessionId) => ipcRenderer.invoke('reflection:discard', sessionId),
  deferReview: (sessionId, days = 3) => ipcRenderer.invoke('review:defer', sessionId, days),
  reflectionHistory: () => ipcRenderer.invoke('reflection:history'),
  openKnowledgeSource: (url) => ipcRenderer.invoke('knowledge:open-source', url),
  knowledgeList: (options = {}) => ipcRenderer.invoke('knowledge:list', options),
  knowledgeGet: (knowledgeId) => ipcRenderer.invoke('knowledge:get', knowledgeId),
  knowledgeStorageStatus: () => ipcRenderer.invoke('knowledge:storage-status'),
  chooseKnowledgeVault: () => ipcRenderer.invoke('knowledge:choose-vault'),
  scanKnowledgeVault: () => ipcRenderer.invoke('knowledge:scan'),
  rebuildKnowledgeVault: () => ipcRenderer.invoke('knowledge:rebuild'),
  migrateKnowledgeToVault: () => ipcRenderer.invoke('knowledge:migrate'),
  voiceStatus: () => ipcRenderer.invoke('voice:get-status'),
  setDictation: (active) => ipcRenderer.invoke('voice:set-dictation', active),
  onEnter: (callback) => subscribe('pet:enter', callback),
  onOpenReflection: (callback) => subscribe('reflection:open', callback),
  onOpenReview: (callback) => subscribe('review:open', callback),
  onVoiceStatus: (callback) => subscribe('voice:status', callback),
  onVoiceWake: (callback) => subscribe('voice:wake', callback),
  onVoiceProcessing: (callback) => subscribe('voice:processing', callback),
  onVoiceCommand: (callback) => subscribe('voice:command', callback),
  onVoiceClarify: (callback) => subscribe('voice:clarify', callback),
  onVoiceTranscript: (callback) => subscribe('voice:transcript', callback),
  onReminder: (callback) => subscribe('reminder:show', callback),
  onWeather: (callback) => subscribe('weather:update', callback),
  onRequestWeatherLocation: (callback) => subscribe('weather:request-location', callback)
});
