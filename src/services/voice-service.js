const { EventEmitter } = require('node:events');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');

class VoiceService extends EventEmitter {
  constructor(scriptPath, options = {}) {
    super();
    this.scriptPath = scriptPath;
    this.spawnProcess = options.spawnProcess || spawn;
    this.platform = options.platform || process.platform;
    this.process = null;
    this.currentRun = null;
    this.nextRunId = 1;
    this.mode = 'Wake';
    this.command = options.command || null;
    this.commandArguments = options.commandArguments || null;
  }

  start(mode = this.mode) {
    if (this.currentRun || (!this.command && this.platform !== 'win32')) {
      return false;
    }

    const systemPowerShell = path.join(
      process.env.SystemRoot || 'C:\\Windows',
      'System32',
      'WindowsPowerShell',
      'v1.0',
      'powershell.exe'
    );
    const powershell = fs.existsSync(systemPowerShell) ? systemPowerShell : 'powershell.exe';
    const command = this.command || powershell;
    const args = this.commandArguments
      ? this.commandArguments(this.scriptPath, mode)
      : ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', this.scriptPath, '-Mode', this.mode];
    this.mode = mode;
    const child = this.spawnProcess(
      command,
      args,
      { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] }
    );
    const run = {
      id: this.nextRunId++,
      child,
      ready: false,
      intentional: false,
      switching: false,
      stopPromise: null,
      resolveStopped: null,
      finalize: null
    };
    this.currentRun = run;
    this.process = child;

    const output = readline.createInterface({ input: child.stdout });
    output.on('line', (line) => {
      try {
        const event = JSON.parse(line);
        if (this.currentRun !== run) return;
        if (event.type === 'ready') run.ready = true;
        this.emit(event.type, { ...event, runId: run.id });
      } catch {
        if (line.trim()) this.emit('warning', { message: line.trim() });
      }
    });

    child.stderr.setEncoding('utf8');
    child.stderr.on('data', (chunk) => {
      if (chunk.trim()) this.emit('warning', { message: chunk.trim() });
    });
    let finalized = false;
    run.finalize = (code) => {
      if (finalized) return;
      finalized = true;
      output.close();
      const isCurrent = this.currentRun === run;
      if (isCurrent) {
        this.currentRun = null;
        this.process = null;
        this.emit('exit', {
          code,
          intentional: run.intentional,
          switching: run.switching,
          runId: run.id
        });
      }
      run.resolveStopped?.();
      if (isCurrent && run.switching) this.start(this.mode);
    };
    child.on('error', (error) => {
      if (this.currentRun === run) this.emit('error', { message: error.message, runId: run.id });
      run.finalize(null);
    });
    child.once('exit', run.finalize);
    return true;
  }

  async switchMode(mode) {
    if (mode === this.mode && this.currentRun) return;
    this.mode = mode;
    if (!this.currentRun) {
      this.start(mode);
      return;
    }
    this.currentRun.switching = true;
    await this.stop();
  }

  stop() {
    const run = this.currentRun;
    if (!run) return Promise.resolve();
    if (run.stopPromise) return run.stopPromise;

    run.intentional = true;
    run.stopPromise = new Promise((resolve) => {
      run.resolveStopped = resolve;
    });
    try {
      if (!run.child.kill()) run.finalize(run.child.exitCode);
    } catch (error) {
      this.emit('error', { message: error.message, runId: run.id });
      run.finalize(run.child.exitCode);
    }
    return run.stopPromise;
  }

  isRunning() {
    return Boolean(this.currentRun);
  }

  isReady() {
    return Boolean(this.currentRun?.ready);
  }
}

module.exports = { VoiceService };
