const states = {
  idle: { label: '待机', file: 'idle.png' },
  asking: { label: '对话', file: 'asking.png' },
  thinking: { label: '思考', file: 'thinking.png' },
  happy: { label: '完成', file: 'happy.png' },
  thanks: { label: '感谢', file: 'thanks.png' },
  sleepy: { label: '休息', file: 'sleepy.png' }
};

const appElement = document.querySelector('#app');
const featureRail = document.querySelector('#feature-rail');
const featureButtons = [...document.querySelectorAll('[data-feature]')];
const interactionBubble = document.querySelector('#interaction-bubble');
const interactionKicker = document.querySelector('#interaction-kicker');
const currentMessage = document.querySelector('#current-message');
const closeInteractionButton = document.querySelector('#close-interaction');
const modelStatus = document.querySelector('#model-status');
const errorElement = document.querySelector('#reflection-error');
const composer = document.querySelector('#composer');
const input = document.querySelector('#reflection-input');
const sendButton = document.querySelector('#send-button');
const reflectionActions = document.querySelector('#reflection-actions');
const microphoneButton = document.querySelector('#microphone-button');
const microphoneLabel = document.querySelector('#microphone-label');
const finishButton = document.querySelector('#finish-button');
const recordingState = document.querySelector('#recording-state');
const recordingTimer = document.querySelector('#recording-timer');
const confirmationActions = document.querySelector('#confirmation-actions');
const confirmKnowledgeButton = document.querySelector('#confirm-knowledge');
const continueReflectionButton = document.querySelector('#continue-reflection');
const reorganizeKnowledgeButton = document.querySelector('#reorganize-knowledge');
const discardKnowledgeButton = document.querySelector('#discard-knowledge');
const discardConfirmationActions = document.querySelector('#discard-confirmation-actions');
const confirmDiscardButton = document.querySelector('#confirm-discard');
const cancelDiscardButton = document.querySelector('#cancel-discard');
const knowledgeCard = document.querySelector('#knowledge-card');
const knowledgeTitle = document.querySelector('#knowledge-title');
const knowledgeCore = document.querySelector('#knowledge-core');
const knowledgeChain = document.querySelector('#knowledge-chain');
const knowledgeQuestions = document.querySelector('#knowledge-questions');
const knowledgeQuestionList = document.querySelector('#knowledge-question-list');
const knowledgeNextStep = document.querySelector('#knowledge-next-step');
const knowledgeMeta = document.querySelector('#knowledge-meta');
const knowledgeBrowser = document.querySelector('#knowledge-browser');
const knowledgeSearchForm = document.querySelector('#knowledge-search-form');
const knowledgeSearchInput = document.querySelector('#knowledge-search-input');
const knowledgeFolderFilter = document.querySelector('#knowledge-folder-filter');
const knowledgeTagFilter = document.querySelector('#knowledge-tag-filter');
const knowledgeSort = document.querySelector('#knowledge-sort');
const knowledgeResultSummary = document.querySelector('#knowledge-result-summary');
const knowledgeResults = document.querySelector('#knowledge-results');
const knowledgeLoadMore = document.querySelector('#knowledge-load-more');
const knowledgeActions = document.querySelector('#knowledge-actions');
const backToKnowledgeButton = document.querySelector('#back-to-knowledge');
const extendKnowledgeButton = document.querySelector('#extend-knowledge');
const knowledgeBadge = document.querySelector('#knowledge-badge');
const weatherActions = document.querySelector('#weather-actions');
const weatherLocationButton = document.querySelector('#weather-location-button');
const proactiveReminder = document.querySelector('#proactive-reminder');
const proactiveReminderTitle = document.querySelector('#proactive-reminder-title');
const proactiveReminderBody = document.querySelector('#proactive-reminder-body');
const deviceStatus = document.querySelector('#device-status');
const deviceClock = document.querySelector('#device-clock');
const deviceDate = document.querySelector('#device-date');
const pet = document.querySelector('#pet');
const character = document.querySelector('#character');
const stateLabel = document.querySelector('#state-label');
const hideButton = document.querySelector('#hide-button');

let visibleSprite = document.querySelector('#sprite-current');
let hiddenSprite = document.querySelector('#sprite-next');
let currentState = 'idle';
let activeView = 'idle';
let sessionId = null;
let busy = false;
let drag = null;
let knowledgeItems = [];
let selectedKnowledge = null;
let knowledgeTotal = 0;
let knowledgeHasMore = false;
let knowledgeLoading = false;
let knowledgeRequestGeneration = 0;
let knowledgeSearchTimer = null;
let pendingKnowledgeDraft = null;
let discardConfirming = false;
let lastWeatherStatus = { configured: false };
let locationBusy = false;
let reminderTimer = null;
let clockTimer = null;
let recordingTicker = null;
let recordingStartedAt = null;
let featureHideTimer = null;
let circadianTimer = null;
let runtimeInfo = {
  mode: 'desktop',
  capabilities: { deviceClock: false, hideToTray: false, tray: false, wakeWord: false, windowDrag: false }
};
let voiceState = {
  enabled: true,
  available: false,
  wakeEnabled: false,
  wakeAvailable: false,
  listening: false,
  mode: 'wake',
  stage: 'idle',
  error: ''
};
let voiceNavigationBusy = false;
let voicePromptGeneration = 0;

function setHidden(element, hidden) {
  element.hidden = hidden;
}

function hideFeatureRail(delay = 0) {
  clearTimeout(featureHideTimer);
  featureHideTimer = window.setTimeout(() => {
    appElement.classList.remove('is-feature-visible');
    featureRail.setAttribute('aria-hidden', 'true');
    restoreIdleState();
  }, delay);
}

function showFeatureRail(duration = 0) {
  if (activeView !== 'idle') return;
  clearTimeout(featureHideTimer);
  appElement.classList.add('is-feature-visible');
  featureRail.setAttribute('aria-hidden', 'false');
  setState('happy');
  if (duration > 0) hideFeatureRail(duration);
}

function showError(message = '') {
  errorElement.hidden = !message;
  errorElement.textContent = message;
}

function spriteUrl(file) {
  return `../assets/character/${file}`;
}

function enter() {
  pet.classList.add('is-entering');
  requestAnimationFrame(() => requestAnimationFrame(() => pet.classList.remove('is-entering')));
}

function setState(stateId) {
  if (!states[stateId] || stateId === currentState) return;
  currentState = stateId;
  const state = states[stateId];
  hiddenSprite.onload = () => {
    pet.classList.add('is-changing');
    hiddenSprite.classList.add('is-visible');
    visibleSprite.classList.remove('is-visible');
    window.setTimeout(() => {
      const previous = visibleSprite;
      visibleSprite = hiddenSprite;
      hiddenSprite = previous;
      pet.classList.remove('is-changing');
    }, 280);
  };
  hiddenSprite.src = spriteUrl(state.file);
  stateLabel.textContent = state.label;
}

function idleStateForNow() {
  return window.LioraPetTime?.idleStateForTime(new Date()) || 'idle';
}

function restoreIdleState() {
  if (activeView !== 'idle' || appElement.classList.contains('is-feature-visible')) return;
  setState(idleStateForNow());
}

function updateProvider(payload) {
  const labels = { deepseek: 'DeepSeek', local: '本地', 'local-fallback': '本地降级' };
  modelStatus.textContent = labels[payload?.provider] || '本地';
  modelStatus.title = payload?.notice || payload?.model || '';
}

function updateClock() {
  const now = new Date();
  deviceClock.textContent = new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit', minute: '2-digit', hour12: false
  }).format(now);
  deviceDate.textContent = new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric', day: 'numeric', weekday: 'short'
  }).format(now);
}

function applyRuntimeInfo(info) {
  runtimeInfo = info;
  document.body.dataset.platform = info.mode;
  deviceStatus.hidden = !info.capabilities.deviceClock;
  hideButton.hidden = !info.capabilities.hideToTray;
  pet.classList.toggle('pet--fixed', !info.capabilities.windowDrag);
  character.setAttribute('aria-label', info.mode === 'device'
    ? '点击和 Liora 开始反思'
    : '点击和 Liora 开始反思，拖动可移动');
  if (info.capabilities.deviceClock) {
    updateClock();
    clearInterval(clockTimer);
    clockTimer = window.setInterval(updateClock, 15_000);
  }
}

function setView(view) {
  activeView = view;
  appElement.dataset.view = view;
  const idle = view === 'idle';
  featureRail.hidden = !idle;
  interactionBubble.hidden = idle;
  if (!idle) {
    clearTimeout(featureHideTimer);
    appElement.classList.remove('is-feature-visible');
  }
  setHidden(composer, view !== 'reflection');
  setHidden(reflectionActions, view !== 'reflection');
  setHidden(confirmationActions, view !== 'confirmation' || discardConfirming);
  setHidden(discardConfirmationActions, view !== 'confirmation' || !discardConfirming);
  setHidden(knowledgeBrowser, view !== 'knowledge' || Boolean(selectedKnowledge));
  setHidden(knowledgeActions, view !== 'knowledge' || !selectedKnowledge);
  setHidden(weatherActions, view !== 'weather');
  if (idle) {
    setHidden(knowledgeCard, true);
    setHidden(recordingState, true);
    showError();
  }
}

function showMessage(text, kicker = 'LIORA') {
  interactionKicker.textContent = kicker;
  currentMessage.textContent = text;
  currentMessage.hidden = false;
  knowledgeBrowser.hidden = true;
  knowledgeCard.hidden = true;
}

function renderKnowledgeContent(content, meta = '') {
  const safe = content || {};
  currentMessage.hidden = true;
  knowledgeBrowser.hidden = true;
  knowledgeCard.hidden = false;
  knowledgeTitle.textContent = safe.title || '未命名知识';
  knowledgeCore.textContent = safe.core_insight || '';
  knowledgeChain.replaceChildren();
  for (const item of safe.logic_chain || []) {
    const row = document.createElement('li');
    row.textContent = item;
    knowledgeChain.appendChild(row);
  }
  knowledgeQuestionList.replaceChildren();
  for (const item of safe.open_questions || []) {
    const row = document.createElement('li');
    row.textContent = item;
    knowledgeQuestionList.appendChild(row);
  }
  knowledgeQuestions.hidden = knowledgeQuestionList.children.length === 0;
  knowledgeNextStep.textContent = safe.next_step ? `下一步：${safe.next_step}` : '';
  knowledgeNextStep.hidden = !safe.next_step;
  knowledgeMeta.textContent = meta;
}

function setBusy(value) {
  busy = value;
  input.disabled = value;
  sendButton.disabled = value;
  finishButton.disabled = value || voiceState.listening;
  microphoneButton.disabled = value || !voiceState.available || voiceState.stage === 'transcribing';
  confirmKnowledgeButton.disabled = value;
  continueReflectionButton.disabled = value;
  reorganizeKnowledgeButton.disabled = value;
  discardKnowledgeButton.disabled = value;
  confirmDiscardButton.disabled = value;
  cancelDiscardButton.disabled = value;
  closeInteractionButton.disabled = value;
}

function setKnowledgeLoading(value) {
  knowledgeLoading = value;
  knowledgeSearchInput.disabled = value;
  knowledgeFolderFilter.disabled = value;
  knowledgeTagFilter.disabled = value;
  knowledgeSort.disabled = value;
  knowledgeLoadMore.disabled = value;
}

async function openShell(view) {
  showError();
  setView(view);
  await window.liora.setDialogOpen(true);
}

async function closeInteraction() {
  if (busy) return;
  if (voiceState.listening) await window.liora.setDictation(false).then(updateVoiceStatus);
  stopRecordingTimer();
  sessionId = null;
  pendingKnowledgeDraft = null;
  discardConfirming = false;
  selectedKnowledge = null;
  knowledgeRequestGeneration += 1;
  setKnowledgeLoading(false);
  setView('idle');
  restoreIdleState();
  await window.liora.setDialogOpen(false);
}

function latestAssistantMessage(messages) {
  return [...(messages || [])].reverse().find((item) => item.role === 'assistant')?.content
    || '今天有什么值得留下的理解？';
}

function applyReflection(payload) {
  sessionId = payload.session.id;
  updateProvider(payload);
  if (payload.awaiting_confirmation && payload.knowledge_draft) {
    pendingKnowledgeDraft = payload.knowledge_draft;
    discardConfirming = false;
    setView('confirmation');
    interactionKicker.textContent = '整理好的知识';
    renderKnowledgeContent(payload.knowledge_draft, '确认后才会正式保存');
    setState('thinking');
    return;
  }
  setView('reflection');
  showMessage(latestAssistantMessage(payload.messages));
  setState('asking');
  input.focus();
}

async function openReflection(forceNew = false, knowledgeId = null) {
  if (busy) return;
  await openShell('reflection');
  setBusy(true);
  setState('thinking');
  showMessage(knowledgeId ? '正在找回这条知识…' : '让我想想从哪里开始…');
  try {
    applyReflection(await window.liora.startReflection(forceNew, knowledgeId));
  } catch (error) {
    showError(error.message || '暂时无法开始反思，请稍后再试。');
    setState('sleepy');
  } finally {
    setBusy(false);
  }
}

async function sendReflection(content) {
  const value = String(content || '').trim();
  if (!sessionId || !value || busy) return;
  setBusy(true);
  showError();
  input.value = '';
  resizeInput();
  showMessage('正在理解你刚才的表达…');
  setState('thinking');
  try {
    applyReflection(await window.liora.sendReflection(sessionId, value));
  } catch (error) {
    input.value = value;
    resizeInput();
    showError(error.message || '这段内容没有保存成功，请再试一次。');
    showMessage('我还在听，你可以重新发送这一段。');
    setState('asking');
  } finally {
    setBusy(false);
  }
}

async function finishReflection() {
  if (!sessionId || busy || voiceState.listening) return;
  setBusy(true);
  showError();
  showMessage('正在把整段对话连成一条清晰的逻辑…');
  setState('thinking');
  try {
    applyReflection(await window.liora.finishReflection(sessionId));
  } catch (error) {
    showError(error.message || '暂时无法整理这次反思。');
    setView('reflection');
    setState('asking');
  } finally {
    setBusy(false);
  }
}

async function confirmKnowledge() {
  if (!sessionId || busy) return;
  setBusy(true);
  try {
    const payload = await window.liora.confirmReflection(sessionId);
    knowledgeBadge.hidden = false;
    showMessage(`“${payload.knowledge.title}”已经存进你的知识记录。`);
    setState('happy');
    window.setTimeout(() => void closeInteraction(), 1500);
  } catch (error) {
    showError(error.message || '这条知识暂时没有保存成功。');
  } finally {
    setBusy(false);
  }
}

function continueReflection() {
  discardConfirming = false;
  pendingKnowledgeDraft = null;
  setView('reflection');
  showMessage('你可以继续补充，我会等你说完后再重新整理。');
  setState('asking');
  input.focus();
}

function askToDiscardKnowledge() {
  if (!sessionId || busy || activeView !== 'confirmation') return;
  discardConfirming = true;
  setView('confirmation');
  showMessage('这次整理不会进入知识记录，对话内容也会清除。确定不保存吗？', '确认一下');
  setState('asking');
}

function cancelDiscardKnowledge() {
  if (busy || !pendingKnowledgeDraft) return;
  discardConfirming = false;
  setView('confirmation');
  interactionKicker.textContent = '整理好的知识';
  renderKnowledgeContent(pendingKnowledgeDraft, '确认后才会正式保存');
  setState('thinking');
}

async function discardKnowledge() {
  if (!sessionId || busy || !discardConfirming) return;
  setBusy(true);
  showError();
  try {
    await window.liora.discardReflection(sessionId);
    sessionId = null;
    pendingKnowledgeDraft = null;
    discardConfirming = false;
    setView('completion');
    showMessage('好，这次就让它留在这里。', 'LIORA');
    setState('happy');
    window.setTimeout(() => void closeInteraction(), 1500);
  } catch (error) {
    showError(error.message || '暂时无法放弃这次整理，请再试一次。');
  } finally {
    setBusy(false);
  }
}

async function openKnowledge() {
  if (busy || knowledgeLoading) return;
  await openShell('knowledge');
  selectedKnowledge = null;
  interactionKicker.textContent = '你的知识';
  showMessage('正在整理可搜索的知识索引…');
  knowledgeBadge.hidden = true;
  await loadKnowledge({ reset: true });
}

function replaceFacetOptions(select, items, allLabel, valueKey, labelFor) {
  const selected = select.value;
  const options = [new Option(allLabel, '')];
  for (const item of items || []) {
    const value = valueKey(item);
    options.push(new Option(`${labelFor(item)} · ${item.count}`, value));
  }
  select.replaceChildren(...options);
  if ([...select.options].some((option) => option.value === selected)) select.value = selected;
}

function renderKnowledgeFacets(facets = {}) {
  replaceFacetOptions(
    knowledgeFolderFilter,
    facets.folders,
    '全部文件夹',
    (item) => item.folder || '.',
    (item) => item.folder || 'Vault 根目录'
  );
  replaceFacetOptions(
    knowledgeTagFilter,
    facets.tags,
    '全部标签',
    (item) => item.tag,
    (item) => `#${item.tag}`
  );
}

function itemMeta(item) {
  const values = [item.folder || 'Vault 根目录'];
  if (item.tags?.length) values.push(item.tags.map((tag) => `#${tag}`).join(' '));
  if (item.updated_at) values.push(String(item.updated_at).slice(0, 10));
  return values.join(' · ');
}

function renderKnowledgeResults() {
  selectedKnowledge = null;
  setView('knowledge');
  interactionKicker.textContent = '你的知识';
  currentMessage.hidden = true;
  knowledgeCard.hidden = true;
  knowledgeBrowser.hidden = false;
  knowledgeResults.replaceChildren();
  const query = knowledgeSearchInput.value.trim();
  knowledgeResultSummary.textContent = query
    ? `找到 ${knowledgeTotal} 条与“${query}”相关的知识`
    : `共 ${knowledgeTotal} 条知识`;

  if (!knowledgeItems.length) {
    const empty = document.createElement('p');
    empty.className = 'knowledge-result-summary';
    empty.textContent = query || knowledgeFolderFilter.value || knowledgeTagFilter.value
      ? '没有匹配的内容，试试更短的关键词或清除筛选。'
      : '这里还没有知识记录。完成一次反思后，它会出现在这里。';
    knowledgeResults.appendChild(empty);
  }
  for (const item of knowledgeItems) {
    const button = document.createElement('button');
    button.className = 'knowledge-result';
    button.type = 'button';
    const title = document.createElement('strong');
    title.textContent = item.title || item.content?.title || '未命名知识';
    const snippet = document.createElement('span');
    snippet.textContent = item.snippet || item.content?.core_insight || '打开查看完整内容';
    const meta = document.createElement('small');
    meta.textContent = itemMeta(item);
    button.append(title, snippet, meta);
    button.addEventListener('click', () => showKnowledgeDetail(item));
    knowledgeResults.appendChild(button);
  }
  knowledgeLoadMore.hidden = !knowledgeHasMore;
}

function showKnowledgeDetail(item) {
  selectedKnowledge = item;
  setView('knowledge');
  interactionKicker.textContent = '知识详情';
  renderKnowledgeContent(item.content, `${itemMeta(item)} · 版本 ${item.version || 1}`);
  knowledgeActions.hidden = false;
  setState('happy');
}

async function loadKnowledge({ reset = false } = {}) {
  if (knowledgeLoading) return;
  const generation = ++knowledgeRequestGeneration;
  setKnowledgeLoading(true);
  showError();
  if (reset) {
    knowledgeItems = [];
    knowledgeTotal = 0;
    knowledgeHasMore = false;
  }
  try {
    const payload = await window.liora.knowledgeList({
      query: knowledgeSearchInput.value,
      folder: knowledgeFolderFilter.value,
      tag: knowledgeTagFilter.value,
      sort: knowledgeSort.value,
      limit: 20,
      offset: reset ? 0 : knowledgeItems.length
    });
    if (generation !== knowledgeRequestGeneration || activeView !== 'knowledge') return;
    knowledgeItems = reset
      ? (payload.items || [])
      : [...knowledgeItems, ...(payload.items || [])];
    knowledgeTotal = Number(payload.total || 0);
    knowledgeHasMore = Boolean(payload.has_more);
    renderKnowledgeFacets(payload.facets);
    renderKnowledgeResults();
    setState(knowledgeItems.length ? 'happy' : 'asking');
  } catch (error) {
    if (generation === knowledgeRequestGeneration) {
      showError(error.message || '暂时无法搜索知识记录。');
      showMessage('知识索引暂时没有准备好，请稍后再试。');
      setState('sleepy');
    }
  } finally {
    if (generation === knowledgeRequestGeneration) setKnowledgeLoading(false);
  }
}

function weatherDescription(code) {
  if (code === 0) return '晴朗';
  if ([1, 2].includes(code)) return '晴间多云';
  if (code === 3) return '多云';
  if ([45, 48].includes(code)) return '有雾';
  if ((code >= 51 && code <= 67) || (code >= 80 && code <= 82)) return '有雨';
  if ((code >= 71 && code <= 77) || (code >= 85 && code <= 86)) return '有雪';
  if (code >= 95) return '可能有雷雨';
  return '天气有些变化';
}

function weatherNarrative(status) {
  if (!status?.configured) return '我还不知道你在哪里。点击“使用当前位置”，我就能介绍今天的天气。';
  const location = String(status.location || '').trim();
  const locationPrefix = location && location !== '当前位置' ? location : '这里';
  const temperature = Number(status.current?.temperature);
  if (!Number.isFinite(temperature)) return `${locationPrefix}的位置已经记下了，我正在获取今天的天气，请稍等一下。`;
  const now = new Date();
  const today = (status.hourly || []).filter((item) => {
    const date = new Date(item.time);
    return date.getFullYear() === now.getFullYear()
      && date.getMonth() === now.getMonth()
      && date.getDate() === now.getDate();
  });
  const apparentValues = today.map((item) => Number(item.apparentTemperature)).filter(Number.isFinite);
  const low = apparentValues.length ? Math.round(Math.min(...apparentValues)) : Math.round(temperature);
  const high = apparentValues.length ? Math.round(Math.max(...apparentValues)) : Math.round(temperature);
  const rain = today.reduce((maximum, item) => Math.max(maximum, Number(item.precipitationProbability) || 0), 0);
  const advice = rain >= 60
    ? '今天有比较明显的降雨可能，出门记得带伞。'
    : high - low >= 7
      ? '今天温差比较明显，晚些时候注意增减衣物。'
      : '天气变化不算大，按现在的体感安排就好。';
  return `${locationPrefix}现在${weatherDescription(status.current.weatherCode)}，${Math.round(temperature)}℃，体感约${Math.round(status.current.apparentTemperature)}℃。今天体感大约在 ${low}～${high}℃，最高降雨概率 ${Math.round(rain)}%。${advice}`;
}

function renderWeather(status) {
  lastWeatherStatus = status || { configured: false };
  if (activeView !== 'weather') return;
  interactionKicker.textContent = '今天天气';
  showMessage(weatherNarrative(lastWeatherStatus));
  weatherLocationButton.textContent = locationBusy
    ? '定位中…'
    : lastWeatherStatus.configured ? '更新当前位置' : '使用当前位置';
  weatherLocationButton.disabled = locationBusy;
}

async function openWeather() {
  if (busy) return;
  await openShell('weather');
  setState('asking');
  renderWeather(await window.liora.weatherStatus());
}

function geolocationErrorMessage(error) {
  if (error?.code === 1) return '没有获得位置权限。请在 Windows“隐私和安全性 → 位置”中允许桌面应用访问位置。';
  if (error?.code === 2) return '暂时无法确定当前位置，请检查系统定位服务或使用手动坐标。';
  if (error?.code === 3) return '获取位置超时，请稍后再试。';
  return error?.message || '暂时无法获取当前位置。';
}

async function resolveCurrentLocationName(coordinates) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 8_000);
  try {
    const response = await fetch(window.LioraLocationName.bigDataCloudUrl(coordinates), {
      signal: controller.signal
    });
    if (!response.ok) throw new Error(`location request failed (${response.status})`);
    return window.LioraLocationName.locationNameFromBigDataCloud(await response.json());
  } finally {
    clearTimeout(timer);
  }
}

async function requestCurrentLocation() {
  if (locationBusy) return;
  if (activeView !== 'weather') await openWeather();
  if (!navigator.geolocation) {
    showError('当前系统不支持自动定位，请使用手动坐标。');
    return;
  }
  locationBusy = true;
  showError();
  renderWeather(lastWeatherStatus);
  try {
    const position = await new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: false,
        timeout: 12_000,
        maximumAge: 6 * 60 * 60 * 1000
      });
    });
    const coordinates = {
      latitude: position.coords.latitude,
      longitude: position.coords.longitude
    };
    let location = '';
    try {
      location = await resolveCurrentLocationName(coordinates);
    } catch (error) {
      console.warn('Could not resolve the current city in the renderer:', error);
    }
    lastWeatherStatus = await window.liora.setWeatherLocation({
      ...coordinates,
      location,
      accuracy: position.coords.accuracy
    });
    renderWeather(lastWeatherStatus);
  } catch (error) {
    showError(geolocationErrorMessage(error));
  } finally {
    locationBusy = false;
    renderWeather(lastWeatherStatus);
  }
}

function startRecordingTimer() {
  if (recordingTicker) return;
  recordingStartedAt = Date.now();
  updateRecordingTimer();
  recordingTicker = window.setInterval(updateRecordingTimer, 250);
}

function stopRecordingTimer() {
  clearInterval(recordingTicker);
  recordingTicker = null;
  recordingStartedAt = null;
  recordingTimer.textContent = '00:00 / 01:00';
}

function updateRecordingTimer() {
  const elapsed = Math.min(60, Math.floor((Date.now() - recordingStartedAt) / 1000));
  const minutes = Math.floor(elapsed / 60);
  const seconds = elapsed % 60;
  recordingTimer.textContent = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')} / 01:00`;
}

function updateVoiceStatus(status) {
  voiceState = { ...voiceState, ...status };
  const transcribing = voiceState.stage === 'transcribing';
  if (voiceState.listening && !transcribing) startRecordingTimer();
  if (!voiceState.listening || transcribing) stopRecordingTimer();
  recordingState.hidden = activeView !== 'reflection' || !voiceState.listening || transcribing;
  microphoneButton.classList.toggle('is-listening', voiceState.listening && !transcribing);
  microphoneLabel.textContent = transcribing
    ? '正在转写'
    : voiceState.listening ? '说完了' : '开始说';
  microphoneButton.disabled = busy || !voiceState.available || transcribing;
  finishButton.disabled = busy || voiceState.listening;
  if (transcribing && activeView === 'reflection') {
    showMessage('正在听清并整理你刚才说的话…');
    setState('thinking');
  }
  if (status.error && activeView === 'reflection') showError(status.error);
}

function resizeInput() {
  input.style.height = 'auto';
  input.style.height = `${Math.min(input.scrollHeight, 86)}px`;
}

function movementFromStart(event) {
  return Math.hypot(event.screenX - drag.startX, event.screenY - drag.startY);
}

character.addEventListener('pointerdown', (event) => {
  if (event.button !== 0) return;
  drag = { pointerId: event.pointerId, startX: event.screenX, startY: event.screenY, moved: false };
  character.setPointerCapture(event.pointerId);
  if (runtimeInfo.capabilities.windowDrag) {
    pet.classList.add('is-dragging');
    window.liora.beginDrag();
  }
});
pet.addEventListener('pointerenter', () => showFeatureRail());
pet.addEventListener('pointerleave', () => hideFeatureRail(650));
featureRail.addEventListener('pointerenter', () => showFeatureRail());
featureRail.addEventListener('pointerleave', () => hideFeatureRail(450));
character.addEventListener('pointermove', (event) => {
  if (!drag || event.pointerId !== drag.pointerId || !runtimeInfo.capabilities.windowDrag) return;
  if (movementFromStart(event) > 5) drag.moved = true;
  if (drag.moved) window.liora.moveDrag();
});
character.addEventListener('pointerup', (event) => {
  if (!drag || event.pointerId !== drag.pointerId) return;
  const moved = drag.moved || movementFromStart(event) > 5;
  if (character.hasPointerCapture(event.pointerId)) character.releasePointerCapture(event.pointerId);
  if (runtimeInfo.capabilities.windowDrag) window.liora.endDrag();
  pet.classList.remove('is-dragging');
  drag = null;
  if (!moved && activeView === 'idle') {
    if (runtimeInfo.mode === 'device') showFeatureRail(10_000);
    else void openReflection();
  }
});
character.addEventListener('pointercancel', () => {
  if (runtimeInfo.capabilities.windowDrag) window.liora.endDrag();
  pet.classList.remove('is-dragging');
  drag = null;
});
character.addEventListener('keydown', (event) => {
  if ((event.key === 'Enter' || event.key === ' ') && activeView === 'idle') void openReflection();
});

featureButtons.forEach((button) => button.addEventListener('click', () => {
  if (button.dataset.feature === 'reflection') void openReflection();
  if (button.dataset.feature === 'knowledge') void openKnowledge();
  if (button.dataset.feature === 'weather') void openWeather();
}));
closeInteractionButton.addEventListener('click', closeInteraction);
composer.addEventListener('submit', (event) => {
  event.preventDefault();
  void sendReflection(input.value);
});
input.addEventListener('input', resizeInput);
input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    composer.requestSubmit();
  }
});
microphoneButton.addEventListener('click', async () => {
  if (busy || !voiceState.available) return;
  showError();
  updateVoiceStatus(await window.liora.setDictation(!voiceState.listening));
});
finishButton.addEventListener('click', finishReflection);
confirmKnowledgeButton.addEventListener('click', confirmKnowledge);
continueReflectionButton.addEventListener('click', continueReflection);
reorganizeKnowledgeButton.addEventListener('click', finishReflection);
discardKnowledgeButton.addEventListener('click', askToDiscardKnowledge);
confirmDiscardButton.addEventListener('click', discardKnowledge);
cancelDiscardButton.addEventListener('click', cancelDiscardKnowledge);
knowledgeSearchForm.addEventListener('submit', (event) => {
  event.preventDefault();
  clearTimeout(knowledgeSearchTimer);
  void loadKnowledge({ reset: true });
});
knowledgeSearchInput.addEventListener('input', () => {
  clearTimeout(knowledgeSearchTimer);
  knowledgeSearchTimer = window.setTimeout(() => void loadKnowledge({ reset: true }), 320);
});
knowledgeFolderFilter.addEventListener('change', () => void loadKnowledge({ reset: true }));
knowledgeTagFilter.addEventListener('change', () => void loadKnowledge({ reset: true }));
knowledgeSort.addEventListener('change', () => void loadKnowledge({ reset: true }));
knowledgeLoadMore.addEventListener('click', () => void loadKnowledge());
backToKnowledgeButton.addEventListener('click', renderKnowledgeResults);
extendKnowledgeButton.addEventListener('click', () => {
  if (selectedKnowledge) void openReflection(true, selectedKnowledge.id);
});
weatherLocationButton.addEventListener('click', requestCurrentLocation);
hideButton.addEventListener('click', () => window.liora.hide());
proactiveReminder.addEventListener('click', () => {
  proactiveReminder.hidden = true;
  void openReflection();
});
document.addEventListener('contextmenu', (event) => {
  if (event.target.closest('textarea') || !runtimeInfo.capabilities.tray) return;
  event.preventDefault();
  window.liora.openMenu();
});

window.liora.onEnter(enter);
window.liora.onOpenReflection(() => void openReflection());
window.liora.onVoiceStatus(updateVoiceStatus);
window.liora.onVoiceWake(() => {
  const generation = ++voicePromptGeneration;
  setState('asking');
  void openShell('voice').then(() => {
    if (generation === voicePromptGeneration && activeView === 'voice') {
      showMessage('我在听。自然地告诉我你想聊聊、查看知识，还是问天气。');
    }
  });
});
window.liora.onVoiceProcessing(() => {
  if (activeView !== 'voice') return;
  setState('thinking');
  showMessage('我听到了，正在理解你的意思…');
});
window.liora.onVoiceCommand(async (event) => {
  if (voiceNavigationBusy || busy) return;
  voicePromptGeneration += 1;
  voiceNavigationBusy = true;
  try {
    if (event?.intent === 'reflection') await openReflection();
    if (event?.intent === 'knowledge') await openKnowledge();
    if (event?.intent === 'weather') await openWeather();
  } finally {
    voiceNavigationBusy = false;
  }
});
window.liora.onVoiceClarify((event) => {
  const generation = ++voicePromptGeneration;
  setState('asking');
  void openShell('voice').then(() => {
    if (generation === voicePromptGeneration && activeView === 'voice') {
      showMessage(event?.message || '我没有听清想进入哪个功能，请再叫我一次。');
    }
  });
});
window.liora.onVoiceTranscript((event) => {
  showError();
  if (activeView !== 'reflection' || !event.text) return;
  input.value = window.LioraVoiceDraft.mergeVoiceTranscript(input.value, event.text);
  resizeInput();
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
  showMessage('已经转写到输入框了。请确认或修改，确认无误后再发送。');
  setState('asking');
});
window.liora.onReminder((payload) => {
  if (!payload || runtimeInfo.mode !== 'device') return;
  proactiveReminderTitle.textContent = payload.title || 'Liora';
  proactiveReminderBody.textContent = payload.body || '';
  proactiveReminder.hidden = false;
  clearTimeout(reminderTimer);
  reminderTimer = window.setTimeout(() => { proactiveReminder.hidden = true; }, 10_000);
});
window.liora.onWeather((status) => {
  lastWeatherStatus = status;
  renderWeather(status);
});
window.liora.onRequestWeatherLocation(() => void requestCurrentLocation());

window.addEventListener('DOMContentLoaded', async () => {
  try {
    applyRuntimeInfo(await window.liora.platformInfo());
  } catch (error) {
    console.warn('Could not read Liora platform capabilities:', error);
    applyRuntimeInfo(runtimeInfo);
  }
  setView('idle');
  restoreIdleState();
  enter();
  clearInterval(circadianTimer);
  circadianTimer = window.setInterval(restoreIdleState, 60_000);
  window.liora.voiceStatus().then(updateVoiceStatus);
  window.liora.weatherStatus().then((status) => { lastWeatherStatus = status; });
});
