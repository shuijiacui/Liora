const test = require('node:test');
const assert = require('node:assert/strict');
const {
  containsWakeWord,
  normalizeTranscript,
  removeWakeWord,
  shouldAcceptWake,
  wakeConfidenceThreshold
} = require('../src/services/voice-utils');

test('normalizes punctuation and spaces', () => {
  assert.equal(normalizeTranscript(' Li Ora！ '), 'liora');
});

test('recognizes English variants and likely Chinese recognizer transcripts', () => {
  for (const value of [
    'Hi Liora',
    'Hey Liora',
    'Hi Leora',
    'Hi Lee Aura',
    'Hey Lia Ora',
    '嗨莉奥拉',
    '海丽奥拉'
  ]) {
    assert.equal(containsWakeWord(value), true, value);
  }
  assert.equal(containsWakeWord('Liora'), false);
  assert.equal(containsWakeWord('莉奥拉'), false);
  assert.equal(containsWakeWord('今天学习了注意力机制'), false);
});

test('keeps speech after the wake word for dictation', () => {
  assert.equal(removeWakeWord('嗨莉奥拉，今天学习了注意力机制'), '今天学习了注意力机制');
  assert.equal(removeWakeWord('Hi Liora, help me reflect'), 'help me reflect');
});

test('rejects low-confidence wake-word matches', () => {
  assert.equal(shouldAcceptWake({ text: 'Hi Liora', confidence: 0.91 }), true);
  assert.equal(shouldAcceptWake({ text: 'Hi Liora', confidence: 0.42 }), false);
  assert.equal(shouldAcceptWake({ text: 'Liora', confidence: 0.99 }), false);
  assert.equal(wakeConfidenceThreshold({ culture: 'en-US' }), 0.65);
  assert.equal(wakeConfidenceThreshold({ culture: 'zh-CN' }), 0.7);
  assert.equal(shouldAcceptWake({ text: 'Hi Leora', confidence: 0.66, culture: 'en-US' }), true);
});
