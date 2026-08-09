const test = require('node:test');
const assert = require('node:assert/strict');
const { createVoiceStatus } = require('../src/services/voice-state');

function status(overrides = {}) {
  return createVoiceStatus({
    backendAvailable: true,
    wakeEnabled: true,
    wakeReady: true,
    mode: 'wake',
    stage: 'idle',
    error: '',
    recognizer: 'test',
    ...overrides
  });
}

test('manual dictation remains available while wake recognition restarts', () => {
  const value = status({ wakeReady: false });
  assert.equal(value.available, true);
  assert.equal(value.wakeAvailable, false);
});

test('disabling wake recognition does not disable the microphone button', () => {
  const value = status({ wakeEnabled: false, wakeReady: false });
  assert.equal(value.available, true);
  assert.equal(value.wakeEnabled, false);
});

test('dictation is unavailable only when the Python backend is unavailable', () => {
  const value = status({ backendAvailable: false });
  assert.equal(value.available, false);
});
