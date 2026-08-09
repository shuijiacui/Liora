const test = require('node:test');
const assert = require('node:assert/strict');
const { createRuntimeProfile, resolveRuntimeMode } = require('../src/platform/runtime-profile');

test('desktop remains the safe default on every operating system', () => {
  assert.equal(resolveRuntimeMode({ argv: [], env: {} }), 'desktop');
  const profile = createRuntimeProfile({ argv: [], env: {}, osPlatform: 'linux' });
  assert.equal(profile.mode, 'desktop');
  assert.equal(profile.capabilities.tray, true);
});

test('device flag selects the dedicated hardware capabilities', () => {
  const profile = createRuntimeProfile({
    argv: ['--device', '--device-windowed'],
    env: {},
    osPlatform: 'linux'
  });
  assert.equal(profile.mode, 'device');
  assert.equal(profile.deviceWindowed, true);
  assert.deepEqual(profile.capabilities, {
    deviceClock: true,
    hideToTray: false,
    inAppReminders: true,
    systemNotifications: false,
    tray: false,
    wakeWord: false,
    windowDrag: false
  });
});

test('environment can select device mode while an explicit desktop flag wins', () => {
  assert.equal(resolveRuntimeMode({ argv: [], env: { LIORA_RUNTIME: 'device' } }), 'device');
  assert.equal(
    resolveRuntimeMode({ argv: ['--desktop'], env: { LIORA_RUNTIME: 'device' } }),
    'desktop'
  );
});

test('wake word capability is exposed only for Windows desktop', () => {
  assert.equal(createRuntimeProfile({ osPlatform: 'win32' }).capabilities.wakeWord, true);
  assert.equal(createRuntimeProfile({ osPlatform: 'linux' }).capabilities.wakeWord, false);
  assert.equal(
    createRuntimeProfile({ argv: ['--device'], osPlatform: 'win32' }).capabilities.wakeWord,
    false
  );
});
