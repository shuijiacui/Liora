(function initializeVoiceDraft(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.LioraVoiceDraft = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, () => {
  function mergeVoiceTranscript(existing, transcript) {
    const current = String(existing || '').trimEnd();
    const recognized = String(transcript || '').trim();
    if (!recognized) return current;
    return current ? `${current}\n${recognized}` : recognized;
  }

  return { mergeVoiceTranscript };
});
