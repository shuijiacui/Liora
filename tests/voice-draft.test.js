const test = require('node:test');
const assert = require('node:assert/strict');
const { mergeVoiceTranscript } = require('../src/shared/voice-draft');

test('voice transcript becomes an editable draft instead of an automatic submission', () => {
  assert.equal(mergeVoiceTranscript('', ' 今天学习了注意力机制。 '), '今天学习了注意力机制。');
});

test('voice transcript is appended without overwriting typed text', () => {
  assert.equal(
    mergeVoiceTranscript('我先写了一部分。', '然后用语音补充。'),
    '我先写了一部分。\n然后用语音补充。'
  );
});
