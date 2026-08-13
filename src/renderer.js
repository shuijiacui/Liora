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
const reviewBadge = document.querySelector('#review-badge');
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
const deferReviewButton = document.querySelector('#defer-review');
const recordingState = document.querySelector('#recording-state');
const recordingTimer = document.querySelector('#recording-timer');
const confirmationActions = document.querySelector('#confirmation-actions');
const ratingActions = document.querySelector('#rating-actions');
const independentRecallInput = document.querySelector('#independent-recall');
const ratingButtons = [...document.querySelectorAll('[data-reflection-rating]')];
const confirmKnowledgeButton = document.querySelector('#confirm-knowledge');
const continueReflectionButton = document.querySelector('#continue-reflection');
const editKnowledgeButton = document.querySelector('#edit-knowledge');
const discardKnowledgeButton = document.querySelector('#discard-knowledge');
const deferReviewDraftButton = document.querySelector('#defer-review-draft');
const draftEditor = document.querySelector('#draft-editor');
const draftEditorActions = document.querySelector('#draft-editor-actions');
const saveDraftButton = document.querySelector('#save-draft');
const reviseDraftButton = document.querySelector('#revise-draft');
const cancelDraftEditButton = document.querySelector('#cancel-draft-edit');
const draftFeedbackInput = document.querySelector('#draft-feedback-input');
const draftFields = {
  title: document.querySelector('#draft-title'),
  core_insight: document.querySelector('#draft-core'),
  key_points: document.querySelector('#draft-key-points'),
  logic_chain: document.querySelector('#draft-logic-chain'),
  examples: document.querySelector('#draft-examples'),
  extensions: document.querySelector('#draft-extensions'),
  boundaries: document.querySelector('#draft-boundaries'),
  connections: document.querySelector('#draft-connections'),
  open_questions: document.querySelector('#draft-open-questions'),
  next_step: document.querySelector('#draft-next-step')
};
const discardConfirmationActions = document.querySelector('#discard-confirmation-actions');
const confirmDiscardButton = document.querySelector('#confirm-discard');
const cancelDiscardButton = document.querySelector('#cancel-discard');
const knowledgeCard = document.querySelector('#knowledge-card');
const knowledgeTitle = document.querySelector('#knowledge-title');
const knowledgeCore = document.querySelector('#knowledge-core');
const knowledgeSections = document.querySelector('#knowledge-sections');
const knowledgeNextStep = document.querySelector('#knowledge-next-step');
const knowledgeSources = document.querySelector('#knowledge-sources');
const knowledgeSourceList = document.querySelector('#knowledge-source-list');
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
let conversationView = 'reflection';
let pendingReviewSessionId = null;
const conversationDrafts = { reflection: '', review: '' };
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
  const providerLabel = labels[payload?.provider] || '本地';
  modelStatus.textContent = payload?.web_used ? `${providerLabel} · 联网` : providerLabel;
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
  setHidden(composer, !['reflection', 'review'].includes(view));
  setHidden(reflectionActions, !['reflection', 'review'].includes(view));
  deferReviewButton.hidden = view !== 'review';
  setHidden(confirmationActions, view !== 'confirmation' || discardConfirming);
  deferReviewDraftButton.hidden = view !== 'confirmation'
    || conversationView !== 'review'
    || discardConfirming;
  setHidden(ratingActions, view !== 'rating');
  setHidden(discardConfirmationActions, view !== 'confirmation' || !discardConfirming);
  setHidden(draftEditorActions, view !== 'draft-edit');
  setHidden(draftEditor, view !== 'draft-edit');
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
  draftEditor.hidden = true;
}

function renderKnowledgeContent(content, meta = '') {
  const safe = content || {};
  currentMessage.hidden = true;
  knowledgeBrowser.hidden = true;
  draftEditor.hidden = true;
  knowledgeCard.hidden = false;
  knowledgeTitle.textContent = safe.title || '未命名知识';
  knowledgeCore.textContent = safe.core_insight || '';
  knowledgeSections.replaceChildren();
  const sections = [
    ['关键要点', 'key_points', false],
    ['原理与推理', 'logic_chain', true],
    ['例子与反例', 'examples', false],
    ['延伸理解', 'extensions', false],
    ['边界与误区', 'boundaries', false],
    ['知识联系', 'connections', false],
    ['尚待探索', 'open_questions', false]
  ];
  for (const [title, key, ordered] of sections) {
    const values = safe[key] || [];
    if (!values.length) continue;
    const section = document.createElement('section');
    section.className = 'knowledge-section';
    const heading = document.createElement('h3');
    heading.textContent = title;
    const list = document.createElement(ordered ? 'ol' : 'ul');
    for (const item of values) {
      const row = document.createElement('li');
      row.textContent = item;
      list.appendChild(row);
    }
    section.append(heading, list);
    knowledgeSections.appendChild(section);
  }
  knowledgeNextStep.textContent = safe.next_step ? `下一步：${safe.next_step}` : '';
  knowledgeNextStep.hidden = !safe.next_step;
  knowledgeSourceList.replaceChildren();
  for (const source of safe.sources || []) {
    const row = document.createElement('li');
    if (source.url) {
      const link = document.createElement('button');
      link.className = 'knowledge-source-link';
      link.type = 'button';
      link.textContent = source.title || source.url;
      link.title = source.url;
      link.addEventListener('click', () => void window.liora.openKnowledgeSource(source.url));
      row.appendChild(link);
    } else {
      row.textContent = source.title || '参考资料';
    }
    knowledgeSourceList.appendChild(row);
  }
  knowledgeSources.hidden = knowledgeSourceList.children.length === 0;
  knowledgeMeta.textContent = meta;
}

function linesToText(items) {
  return (items || []).join('\n');
}

function textToLines(value) {
  return String(value || '').split(/\r?\n/u).map((item) => item.trim()).filter(Boolean);
}

function fillDraftEditor(content) {
  const safe = content || {};
  draftFields.title.value = safe.title || '';
  draftFields.core_insight.value = safe.core_insight || '';
  for (const key of ['key_points', 'logic_chain', 'examples', 'extensions', 'boundaries', 'connections', 'open_questions']) {
    draftFields[key].value = linesToText(safe[key]);
  }
  draftFields.next_step.value = safe.next_step || '';
}

function draftFromEditor() {
  return {
    title: draftFields.title.value.trim(),
    core_insight: draftFields.core_insight.value.trim(),
    key_points: textToLines(draftFields.key_points.value),
    logic_chain: textToLines(draftFields.logic_chain.value),
    examples: textToLines(draftFields.examples.value),
    extensions: textToLines(draftFields.extensions.value),
    boundaries: textToLines(draftFields.boundaries.value),
    connections: textToLines(draftFields.connections.value),
    open_questions: textToLines(draftFields.open_questions.value),
    next_step: draftFields.next_step.value.trim(),
    sources: pendingKnowledgeDraft?.sources || []
  };
}

function setBusy(value) {
  busy = value;
  input.disabled = value;
  sendButton.disabled = value;
  finishButton.disabled = value || voiceState.listening;
  microphoneButton.disabled = value || !voiceState.available || voiceState.stage === 'transcribing';
  confirmKnowledgeButton.disabled = value;
  continueReflectionButton.disabled = value;
  editKnowledgeButton.disabled = value;
  saveDraftButton.disabled = value;
  reviseDraftButton.disabled = value;
  cancelDraftEditButton.disabled = value;
  discardKnowledgeButton.disabled = value;
  deferReviewDraftButton.disabled = value;
  confirmDiscardButton.disabled = value;
  cancelDiscardButton.disabled = value;
  deferReviewButton.disabled = value;
  ratingButtons.forEach((button) => { button.disabled = value; });
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
  if (['reflection', 'review'].includes(conversationView)) {
    conversationDrafts[conversationView] = input.value;
  }
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

function applyReflection(payload, view = conversationView) {
  conversationView = payload?.session?.session_type === 'review' ? 'review' : view;
  sessionId = payload.session.id;
  updateProvider(payload);
  if (payload.awaiting_confirmation && payload.knowledge_draft) {
    pendingKnowledgeDraft = payload.knowledge_draft;
    discardConfirming = false;
    setView('confirmation');
    interactionKicker.textContent = '知识文件草稿';
    renderKnowledgeContent(payload.knowledge_draft, '可以直接编辑，也可以告诉 Liora 如何修改');
    setState('thinking');
    return;
  }
  setView(conversationView);
  showMessage(
    latestAssistantMessage(payload.messages),
    conversationView === 'review' ? 'LIORA · 回顾' : 'LIORA · 反思'
  );
  setState('asking');
  input.focus();
}

async function openReflection(forceNew = false, knowledgeId = null) {
  if (busy) return;
  sessionId = null;
  conversationView = 'reflection';
  input.value = conversationDrafts.reflection;
  input.placeholder = '写下今天值得留下的理解…';
  finishButton.textContent = '生成知识文件';
  resizeInput();
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
  conversationDrafts[conversationView] = '';
  resizeInput();
  showMessage('正在理解你刚才的表达…');
  setState('thinking');
  try {
    applyReflection(await window.liora.sendReflection(sessionId, value));
  } catch (error) {
    input.value = value;
    conversationDrafts[conversationView] = value;
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
  showMessage('正在围绕核心主题构建一份完整的知识文件…');
  setState('thinking');
  try {
    applyReflection(await window.liora.finishReflection(sessionId));
  } catch (error) {
    showError(error.message || '暂时无法整理这次反思。');
    setView(conversationView);
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
    showMessage(payload.review_required
      ? `“${payload.knowledge.title}”有一点拿不准，Liora已经放进 Obsidian 管理台等你确认。`
      : `“${payload.knowledge.title}”已经存进你的知识记录。`);
    setState('happy');
    if (payload.session?.prompt_id) {
      independentRecallInput.checked = false;
      showMessage('Liora收好啦。刚才这次复述，你觉得讲得怎么样？');
      setView('rating');
    } else {
      window.setTimeout(() => void closeInteraction(), 1500);
    }
  } catch (error) {
    showError(error.message || '这条知识暂时没有保存成功。');
  } finally {
    setBusy(false);
  }
}

async function openReview(expectedSessionId = null) {
  if (busy) return;
  sessionId = null;
  reviewBadge.hidden = true;
  conversationView = 'review';
  input.value = conversationDrafts.review;
  input.placeholder = '不看笔记，讲给 Liora 听…';
  finishButton.textContent = '整理这次回顾';
  resizeInput();
  await openShell('review');
  setBusy(true);
  setState('thinking');
  showMessage('Liora正在翻找最值得回顾的小问题…', 'LIORA · 回顾');
  try {
    const payload = await window.liora.startReview();
    if (payload.available === false) {
      sessionId = null;
      setView('review-empty');
      showMessage(payload.message || 'Liora暂时没有找到该回顾的小问题。', 'LIORA · 回顾');
      setState('happy');
      return;
    }
    const consumed = window.LioraReviewOpenState.consumeReviewTask(
      expectedSessionId,
      payload.session?.id
    );
    if (!consumed.accepted) {
      reviewBadge.hidden = false;
      pendingReviewSessionId = consumed.pendingSessionId;
      throw new Error('Liora收到的回顾任务发生了变化，请再点一次“回顾”。');
    }
    pendingReviewSessionId = consumed.pendingSessionId;
    applyReflection(payload, 'review');
  } catch (error) {
    sessionId = null;
    setView('review-empty');
    showError(error.message || 'Liora暂时没能打开回顾。');
    setState('sleepy');
  } finally {
    setBusy(false);
  }
}

async function deferReview() {
  if (!sessionId || busy || conversationView !== 'review') return;
  setBusy(true);
  showError();
  try {
    await window.liora.deferReview(sessionId, 3);
    sessionId = null;
    showMessage('Liora先把这个小问题放回三天后。', 'LIORA · 回顾');
    setView('review-empty');
    setState('happy');
  } catch (error) {
    showError(error.message || 'Liora暂时没能把它放一放。');
  } finally {
    setBusy(false);
  }
}

async function rateReflection(rating) {
  if (!sessionId || busy) return;
  setBusy(true);
  showError();
  try {
    const independentRecall = independentRecallInput.checked;
    const payload = await window.liora.rateReflection(sessionId, rating, independentRecall);
    const next = new Date(payload.knowledge_state.next_entry_at);
    const nextText = Number.isNaN(next.getTime())
      ? '合适的时候'
      : new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(next);
    showMessage(`Liora记住这次手感啦，大约在${nextText}再来找你。`);
    setState('happy');
    window.setTimeout(() => void closeInteraction(), 1800);
  } catch (error) {
    showError(error.message || 'Liora暂时没记住这次手感，请再点一次。');
  } finally {
    setBusy(false);
  }
}

function continueReflection() {
  discardConfirming = false;
  pendingKnowledgeDraft = null;
  setView(conversationView);
  showMessage('你可以继续聊。我会用新的理解重新构建知识文件。');
  setState('asking');
  input.focus();
}

function openDraftEditor() {
  if (!pendingKnowledgeDraft || busy) return;
  discardConfirming = false;
  setView('draft-edit');
  currentMessage.hidden = true;
  knowledgeCard.hidden = true;
  knowledgeBrowser.hidden = true;
  draftEditor.hidden = false;
  interactionKicker.textContent = '编辑知识文件';
  fillDraftEditor(pendingKnowledgeDraft);
  draftFeedbackInput.value = '';
  draftFields.title.focus();
}

function showDraftPreview() {
  if (!pendingKnowledgeDraft || busy) return;
  setView('confirmation');
  interactionKicker.textContent = '知识文件草稿';
  renderKnowledgeContent(pendingKnowledgeDraft, '可以直接编辑，也可以告诉 Liora 如何修改');
}

async function saveDraft() {
  if (!sessionId || busy) return;
  const content = draftFromEditor();
  if (!content.title || !content.core_insight || (!content.key_points.length && !content.logic_chain.length)) {
    showError('请至少保留标题、核心理解，以及关键要点或推理过程。');
    return;
  }
  setBusy(true);
  showError();
  try {
    applyReflection(await window.liora.updateReflectionDraft(sessionId, content));
  } catch (error) {
    showError(error.message || '草稿修改暂时没有保存成功。');
  } finally {
    setBusy(false);
  }
}

async function reviseDraft() {
  if (!sessionId || busy) return;
  const instruction = draftFeedbackInput.value.trim();
  if (!instruction) {
    showError('先告诉 Liora 希望怎样修改这份知识文件。');
    draftFeedbackInput.focus();
    return;
  }
  const content = draftFromEditor();
  setBusy(true);
  showError();
  showMessage('正在根据你的意见修改知识文件…', 'LIORA');
  setState('thinking');
  try {
    applyReflection(await window.liora.reviseReflectionDraft(sessionId, content, instruction));
  } catch (error) {
    showError(error.message || '暂时无法按意见修改。');
    setView('draft-edit');
    draftEditor.hidden = false;
    fillDraftEditor(content);
    draftFeedbackInput.value = instruction;
    setState('asking');
  } finally {
    setBusy(false);
  }
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
  interactionKicker.textContent = '知识文件草稿';
  renderKnowledgeContent(pendingKnowledgeDraft, '可以直接编辑，也可以告诉 Liora 如何修改');
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
  const inConversation = ['reflection', 'review'].includes(activeView);
  recordingState.hidden = !inConversation || !voiceState.listening || transcribing;
  microphoneButton.classList.toggle('is-listening', voiceState.listening && !transcribing);
  microphoneLabel.textContent = transcribing
    ? '正在转写'
    : voiceState.listening ? '说完了' : '开始说';
  microphoneButton.disabled = busy || !voiceState.available || transcribing;
  finishButton.disabled = busy || voiceState.listening;
  if (transcribing && inConversation) {
    showMessage('正在听清并整理你刚才说的话…');
    setState('thinking');
  }
  if (status.error && inConversation) showError(status.error);
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
  if (button.dataset.feature === 'review') void openReview(pendingReviewSessionId);
  if (button.dataset.feature === 'knowledge') void openKnowledge();
  if (button.dataset.feature === 'weather') void openWeather();
}));
closeInteractionButton.addEventListener('click', closeInteraction);
composer.addEventListener('submit', (event) => {
  event.preventDefault();
  void sendReflection(input.value);
});
input.addEventListener('input', resizeInput);
input.addEventListener('input', () => {
  if (['reflection', 'review'].includes(conversationView)) {
    conversationDrafts[conversationView] = input.value;
  }
});
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
deferReviewButton.addEventListener('click', deferReview);
deferReviewDraftButton.addEventListener('click', deferReview);
confirmKnowledgeButton.addEventListener('click', confirmKnowledge);
ratingButtons.forEach((button) => button.addEventListener('click', () => {
  void rateReflection(button.dataset.reflectionRating);
}));
continueReflectionButton.addEventListener('click', continueReflection);
editKnowledgeButton.addEventListener('click', openDraftEditor);
saveDraftButton.addEventListener('click', saveDraft);
reviseDraftButton.addEventListener('click', reviseDraft);
cancelDraftEditButton.addEventListener('click', showDraftPreview);
draftEditor.addEventListener('submit', (event) => event.preventDefault());
document.querySelectorAll('[data-draft-suggestion]').forEach((button) => {
  button.addEventListener('click', () => {
    draftFeedbackInput.value = button.dataset.draftSuggestion || '';
    draftFeedbackInput.focus();
  });
});
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
window.liora.onOpenReview((event) => {
  const next = window.LioraReviewOpenState.receiveReviewTask({
    activeView,
    busy,
    pendingSessionId: pendingReviewSessionId,
    eventSessionId: event?.session_id
  });
  pendingReviewSessionId = next.pendingSessionId;
  reviewBadge.hidden = false;
  if (next.shouldOpen) void openReview(pendingReviewSessionId);
});
window.liora.onVoiceStatus(updateVoiceStatus);
window.liora.onVoiceWake(() => {
  const generation = ++voicePromptGeneration;
  setState('asking');
  void openShell('voice').then(() => {
    if (generation === voicePromptGeneration && activeView === 'voice') {
      showMessage('我在听。自然地告诉我你想反思、回顾、查看知识，还是问天气。');
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
    if (event?.intent === 'review') await openReview();
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
  if (!['reflection', 'review'].includes(activeView) || !event.text) return;
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
