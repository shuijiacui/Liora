const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {
  connectionPayload,
  publishConnection,
  removeConnection
} = require('../src/shared/knowledge-engine-connection');

test('publishes a loopback-only Knowledge Engine connection atomically', (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'liora-connection-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));

  const destination = publishConnection(directory, {
    port: 43117,
    token: 'temporary-token',
    pid: 42,
    updatedAt: '2026-08-12T12:00:00.000Z'
  });
  const stored = JSON.parse(fs.readFileSync(destination, 'utf8'));

  assert.deepEqual(stored, {
    schema_version: 1,
    host: '127.0.0.1',
    port: 43117,
    token: 'temporary-token',
    pid: 42,
    updated_at: '2026-08-12T12:00:00.000Z'
  });
  assert.equal(removeConnection(directory, 'another-token'), false);
  assert.equal(fs.existsSync(destination), true);
  assert.equal(removeConnection(directory, 'temporary-token'), true);
  assert.equal(fs.existsSync(destination), false);
});

test('rejects invalid Knowledge Engine connection details', () => {
  assert.throws(() => connectionPayload({ port: 0, token: 'token' }), /无效/);
  assert.throws(() => connectionPayload({ port: 43117, token: '' }), /无效/);
});
