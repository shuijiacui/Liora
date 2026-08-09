const test = require('node:test');
const assert = require('node:assert/strict');
const { VoiceCommandCoordinator } = require('../src/services/voice-command-coordinator');

function audio(sessionId, phase = 'follow-up') {
  return { session_id: sessionId, phase, encoding: 'pcm_s16le', audio: 'AQID', sample_rate: 16000 };
}

test('one session can route only one feature', async () => {
  const routed = [];
  const coordinator = new VoiceCommandCoordinator({
    transcribe: async () => ({ text: '今天天气怎么样', confidence: 0.9 }),
    routeIntent: () => ({ intent: 'weather', confidence: 0.9, ambiguous: false, commandText: '今天天气怎么样' }),
    onRoute: (event) => routed.push(event.intent),
    onClarify: () => assert.fail('should not clarify')
  });
  coordinator.start('one');
  coordinator.enqueue(audio('one'));
  coordinator.enqueue(audio('one'));
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(routed, ['weather']);
});

test('a late old transcription cannot override a newer wake session', async () => {
  let resolveOld;
  const routed = [];
  const coordinator = new VoiceCommandCoordinator({
    transcribe: (event) => event.session_id === 'old'
      ? new Promise((resolve) => { resolveOld = resolve; })
      : Promise.resolve({ text: '查看知识', confidence: 0.9 }),
    routeIntent: (text) => ({
      intent: text.includes('天气') ? 'weather' : 'knowledge',
      confidence: 0.9,
      ambiguous: false,
      commandText: text
    }),
    onRoute: (event) => routed.push(event.intent),
    onClarify: () => {}
  });
  coordinator.start('old');
  coordinator.enqueue(audio('old'));
  await new Promise((resolve) => setImmediate(resolve));
  coordinator.start('new');
  coordinator.enqueue(audio('new'));
  resolveOld({ text: '今天天气怎么样', confidence: 0.9 });
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(routed, ['knowledge']);
});

test('ambiguous follow-up asks for clarification instead of routing', async () => {
  const clarified = [];
  const coordinator = new VoiceCommandCoordinator({
    transcribe: async () => ({ text: '聊聊天气知识', confidence: 0.9 }),
    routeIntent: () => ({ intent: null, confidence: 0.5, ambiguous: true, commandText: '聊聊天气知识' }),
    onRoute: () => assert.fail('should not route'),
    onClarify: (event) => clarified.push(event.reason)
  });
  coordinator.start('ambiguous');
  coordinator.enqueue(audio('ambiguous'));
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(clarified, ['']);
});
