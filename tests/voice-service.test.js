const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');
const { VoiceService } = require('../src/services/voice-service');

class MockChild extends EventEmitter {
  constructor() {
    super();
    this.stdout = new PassThrough();
    this.stderr = new PassThrough();
    this.killed = false;
  }

  kill() {
    this.killed = true;
    return true;
  }

  exit(code = 0) {
    this.emit('exit', code);
  }
}

test('keeps the active process referenced until it has really exited', async () => {
  const children = [];
  const service = new VoiceService('voice-listener.ps1', {
    platform: 'win32',
    spawnProcess: () => {
      const child = new MockChild();
      children.push(child);
      return child;
    }
  });

  assert.equal(service.start('Wake'), true);
  const first = children[0];
  const stopped = service.stop();
  assert.equal(first.killed, true);
  assert.equal(service.process, first);
  assert.equal(service.start('Wake'), false);
  assert.equal(children.length, 1);

  first.exit();
  await stopped;
  assert.equal(service.process, null);
  assert.equal(service.start('Wake'), true);
  assert.equal(children.length, 2);
  assert.equal(service.process, children[1]);
});

test('a stale exit event cannot clear a newer listener', async () => {
  const children = [];
  const service = new VoiceService('voice-listener.ps1', {
    platform: 'win32',
    spawnProcess: () => {
      const child = new MockChild();
      children.push(child);
      return child;
    }
  });

  service.start('Wake');
  const first = children[0];
  const stopped = service.stop();
  first.exit();
  await stopped;
  service.start('Wake');
  const second = children[1];

  first.emit('exit', 0);
  assert.equal(service.process, second);
});

test('tracks readiness on the active listener itself', async () => {
  let child;
  const service = new VoiceService('voice-listener.ps1', {
    platform: 'win32',
    spawnProcess: () => {
      child = new MockChild();
      return child;
    }
  });

  service.start('Wake');
  assert.equal(service.isRunning(), true);
  assert.equal(service.isReady(), false);
  child.stdout.write(`${JSON.stringify({ type: 'ready', recognizer: 'test' })}\n`);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(service.isReady(), true);

  const stopped = service.stop();
  child.exit();
  await stopped;
  assert.equal(service.isRunning(), false);
  assert.equal(service.isReady(), false);
});

test('supports a custom cross-platform wake-listener command', () => {
  let invocation;
  const service = new VoiceService('wake_listener.py', {
    platform: 'linux',
    command: '/usr/bin/python3',
    commandArguments: (script, mode) => ['-u', script, '--mode', mode.toLowerCase()],
    spawnProcess: (command, args) => {
      invocation = { command, args };
      return new MockChild();
    }
  });

  assert.equal(service.start('Wake'), true);
  assert.deepEqual(invocation, {
    command: '/usr/bin/python3',
    args: ['-u', 'wake_listener.py', '--mode', 'wake']
  });
});

test('forwards an in-memory command audio event without changing it', async () => {
  let child;
  const service = new VoiceService('wake_listener.py', {
    platform: 'win32',
    command: 'python.exe',
    spawnProcess: () => {
      child = new MockChild();
      return child;
    }
  });
  const received = new Promise((resolve) => service.once('command-audio', resolve));
  service.start('Wake');
  const payload = {
    type: 'command-audio',
    session_id: 'session-1',
    phase: 'wake-utterance',
    encoding: 'pcm_s16le',
    sample_rate: 16000,
    audio: 'AQIDBA=='
  };
  child.stdout.write(`${JSON.stringify(payload)}\n`);
  assert.deepEqual(await received, { ...payload, runId: 1 });
});
