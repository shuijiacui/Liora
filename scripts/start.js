const { spawn } = require('node:child_process');
const electronExecutable = require('electron');

const environment = { ...process.env };
delete environment.ELECTRON_RUN_AS_NODE;

const child = spawn(electronExecutable, ['.', ...process.argv.slice(2)], {
  cwd: process.cwd(),
  env: environment,
  stdio: 'inherit',
  windowsHide: false
});

child.on('error', (error) => {
  console.error('Unable to start Liora:', error.message);
  process.exitCode = 1;
});

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }

  process.exit(code ?? 0);
});
