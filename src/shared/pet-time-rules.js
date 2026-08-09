(function exposePetTimeRules(root, factory) {
  const rules = factory();
  if (typeof module === 'object' && module.exports) module.exports = rules;
  if (root) root.LioraPetTime = rules;
})(typeof globalThis !== 'undefined' ? globalThis : this, () => {
  function isSleepTime(value = new Date()) {
    const date = value instanceof Date ? value : new Date(value);
    const hour = date.getHours();
    return hour < 8 || hour >= 22;
  }

  function idleStateForTime(value = new Date()) {
    return isSleepTime(value) ? 'sleepy' : 'idle';
  }

  return { isSleepTime, idleStateForTime };
});
