const test = require('node:test');
const assert = require('node:assert/strict');
const { idleStateForTime, isSleepTime } = require('../src/shared/pet-time-rules');

function atLocalHour(hour, minute = 0) {
  return new Date(2026, 7, 8, hour, minute, 0, 0);
}

test('uses sleepy before 08:00 and from 22:00 onward', () => {
  assert.equal(isSleepTime(atLocalHour(7, 59)), true);
  assert.equal(isSleepTime(atLocalHour(8, 0)), false);
  assert.equal(isSleepTime(atLocalHour(21, 59)), false);
  assert.equal(isSleepTime(atLocalHour(22, 0)), true);
  assert.equal(idleStateForTime(atLocalHour(23, 30)), 'sleepy');
  assert.equal(idleStateForTime(atLocalHour(12, 0)), 'idle');
});
