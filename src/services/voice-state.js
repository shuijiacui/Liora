function createVoiceStatus({
  backendAvailable,
  wakeEnabled,
  wakeReady,
  mode,
  stage,
  error,
  recognizer
}) {
  return {
    enabled: Boolean(backendAvailable),
    available: Boolean(backendAvailable),
    wakeEnabled: Boolean(wakeEnabled),
    wakeAvailable: Boolean(wakeEnabled && wakeReady),
    mode,
    listening: mode === 'dictation',
    stage,
    error,
    recognizer
  };
}

module.exports = { createVoiceStatus };
