const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const projectRoot = path.resolve(__dirname, '..');
const executableName = process.platform === 'win32' ? 'python.exe' : 'python';

function pythonFromIdeaConfig() {
  try {
    const xml = fs.readFileSync(path.join(projectRoot, '.idea', 'misc.xml'), 'utf8');
    const match = xml.match(/project-jdk-name="([^"]+)"/);
    if (!match) return null;
    return process.platform === 'win32'
      ? path.join(match[1], 'python.exe')
      : path.join(match[1], 'bin', 'python');
  } catch {
    return null;
  }
}

function findPython() {
  const packagingPython = path.join(
    projectRoot,
    '.package-venv',
    process.platform === 'win32' ? 'Scripts' : 'bin',
    executableName
  );
  const candidates = [
    packagingPython,
    process.env.LIORA_PYTHON,
    process.env.CONDA_PREFIX ? path.join(process.env.CONDA_PREFIX, executableName) : null,
    pythonFromIdeaConfig(),
    path.join(os.homedir(), '.conda', 'envs', 'ml_env', executableName)
  ].filter(Boolean);
  const found = candidates.find((candidate) => {
    if (!path.isAbsolute(candidate) || !fs.existsSync(candidate)) return false;
    const check = spawnSync(
      candidate,
      ['-c', 'import PyInstaller, faster_whisper, sounddevice, vosk, opencc'],
      { cwd: projectRoot, windowsHide: true, stdio: 'ignore' }
    );
    return check.status === 0;
  });
  if (!found) throw new Error('没有找到用于构建的 Python，请通过 LIORA_PYTHON 指定解释器。');
  return found;
}

if (process.platform !== 'win32') {
  throw new Error('当前独立运行时构建只支持 Windows。');
}

const python = findPython();
const args = [
  '-m',
  'PyInstaller',
  '--noconfirm',
  '--clean',
  '--distpath',
  path.join(projectRoot, '.package-build', 'python'),
  '--workpath',
  path.join(projectRoot, '.package-build', 'pyinstaller-work'),
  path.join(projectRoot, 'packaging', 'liora-runtime.spec')
];
const result = spawnSync(python, args, {
  cwd: projectRoot,
  env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
  stdio: 'inherit',
  windowsHide: true
});
if (result.error) throw result.error;
if (result.status !== 0) process.exit(result.status || 1);

const runtime = path.join(
  projectRoot,
  '.package-build',
  'python',
  'liora-runtime',
  'liora-runtime.exe'
);
if (!fs.existsSync(runtime)) throw new Error(`Python 运行时未生成：${runtime}`);
console.log(`Liora Python runtime ready: ${runtime}`);
