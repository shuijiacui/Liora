const WAKE_PHRASES = [
  'hi liora',
  'hey liora',
  'hi leora',
  'hey leora',
  'hi laura',
  'hey laura',
  'hi lora',
  'hey lora',
  'hi lee aura',
  'hey lee aura',
  'hi lia ora',
  'hey lia ora',
  '嗨莉奥拉',
  '嗨丽奥拉',
  '嗨里奥拉',
  '海莉奥拉',
  '海丽奥拉',
  '海里奥拉'
];

function normalizeTranscript(text) {
  return String(text || '')
    .toLocaleLowerCase()
    .replace(/[\s\p{P}\p{S}]/gu, '');
}

function containsWakeWord(text) {
  const normalized = normalizeTranscript(text);
  return WAKE_PHRASES.some((phrase) => normalized.includes(normalizeTranscript(phrase)));
}

function wakeConfidenceThreshold(event) {
  return String(event?.culture || '').toLowerCase().startsWith('en-') ? 0.65 : 0.7;
}

function shouldAcceptWake(event, minimumConfidence = wakeConfidenceThreshold(event)) {
  const confidence = Number(event?.confidence);
  return Number.isFinite(confidence)
    && confidence >= minimumConfidence
    && containsWakeWord(event?.text);
}

function removeWakeWord(text) {
  let result = String(text || '');
  for (const phrase of WAKE_PHRASES) {
    const expression = new RegExp(
      phrase.split(/\s+/u).map((part) => [...part].join('\\s*')).join('\\s*'),
      'iu'
    );
    if (expression.test(result)) {
      result = result.replace(expression, '');
      break;
    }
  }
  return result.replace(/^[\s，。！？、,.!?：:；;~-]+/u, '').trim();
}

module.exports = {
  containsWakeWord,
  normalizeTranscript,
  removeWakeWord,
  shouldAcceptWake,
  wakeConfidenceThreshold
};
