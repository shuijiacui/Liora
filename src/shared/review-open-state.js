(function reviewOpenStateModule(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.LioraReviewOpenState = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function createReviewOpenState() {
  function normalizeSessionId(value) {
    return typeof value === 'string' ? value.trim() : '';
  }

  function receiveReviewTask({ activeView, busy, pendingSessionId, eventSessionId }) {
    const incoming = normalizeSessionId(eventSessionId);
    const pending = incoming || normalizeSessionId(pendingSessionId);
    return {
      pendingSessionId: pending || null,
      shouldOpen: activeView === 'idle' && !busy
    };
  }

  function consumeReviewTask(expectedSessionId, actualSessionId) {
    const expected = normalizeSessionId(expectedSessionId);
    const actual = normalizeSessionId(actualSessionId);
    const accepted = !expected || expected === actual;
    return {
      accepted,
      pendingSessionId: accepted ? null : expected || null
    };
  }

  return { receiveReviewTask, consumeReviewTask };
});
