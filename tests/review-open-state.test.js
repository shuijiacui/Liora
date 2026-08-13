const test = require('node:test');
const assert = require('node:assert/strict');
const {
  consumeReviewTask,
  receiveReviewTask
} = require('../src/shared/review-open-state');

test('opens an incoming review immediately only while idle', () => {
  assert.deepEqual(receiveReviewTask({
    activeView: 'idle', busy: false, pendingSessionId: null, eventSessionId: 'review-1'
  }), { pendingSessionId: 'review-1', shouldOpen: true });
});

test('queues a review without interrupting reflection or busy work', () => {
  assert.deepEqual(receiveReviewTask({
    activeView: 'reflection', busy: false, pendingSessionId: null, eventSessionId: 'review-1'
  }), { pendingSessionId: 'review-1', shouldOpen: false });
  assert.deepEqual(receiveReviewTask({
    activeView: 'idle', busy: true, pendingSessionId: null, eventSessionId: 'review-2'
  }), { pendingSessionId: 'review-2', shouldOpen: false });
});

test('consumes only the review session that Obsidian requested', () => {
  assert.deepEqual(consumeReviewTask('review-1', 'review-1'), {
    accepted: true, pendingSessionId: null
  });
  assert.deepEqual(consumeReviewTask('review-1', 'review-2'), {
    accepted: false, pendingSessionId: 'review-1'
  });
});
