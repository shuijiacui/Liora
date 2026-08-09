const RUNTIME_MODES = Object.freeze({
  DESKTOP: 'desktop',
  DEVICE: 'device'
});

function hasFlag(argv, flag) {
  return Array.isArray(argv) && argv.includes(flag);
}

function resolveRuntimeMode({ argv = [], env = process.env } = {}) {
  if (hasFlag(argv, '--device')) return RUNTIME_MODES.DEVICE;
  if (hasFlag(argv, '--desktop')) return RUNTIME_MODES.DESKTOP;

  const configured = String(env.LIORA_RUNTIME || '').trim().toLowerCase();
  return configured === RUNTIME_MODES.DEVICE ? RUNTIME_MODES.DEVICE : RUNTIME_MODES.DESKTOP;
}

function createRuntimeProfile({ argv = [], env = process.env, osPlatform = process.platform } = {}) {
  const mode = resolveRuntimeMode({ argv, env });
  const deviceWindowed = mode === RUNTIME_MODES.DEVICE
    && (hasFlag(argv, '--device-windowed') || env.LIORA_DEVICE_WINDOWED === '1');
  const desktop = mode === RUNTIME_MODES.DESKTOP;

  return Object.freeze({
    mode,
    osPlatform,
    deviceWindowed,
    capabilities: Object.freeze({
      deviceClock: !desktop,
      hideToTray: desktop,
      inAppReminders: !desktop,
      systemNotifications: desktop,
      tray: desktop,
      wakeWord: desktop && osPlatform === 'win32',
      windowDrag: desktop
    })
  });
}

module.exports = {
  RUNTIME_MODES,
  createRuntimeProfile,
  resolveRuntimeMode
};
