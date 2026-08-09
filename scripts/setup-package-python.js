const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const projectRoot = path.resolve(__dirname, '..');
const environmentPath = path.join(projectRoot, '.package-venv');
const environmentPython = path.join(
  environmentPath,
  process.platform === 'win32' ? 'Scripts' : 'bin',
  process.platform === 'win32' ? 'python.exe' : 'python'
);

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

function findBasePython() {
  const executableName = process.platform === 'win32' ? 'python.exe' : 'python';
  const candidates = [
    process.env.LIORA_PYTHON,
    process.env.CONDA_PREFIX ? path.join(process.env.CONDA_PREFIX, executableName) : null,
    pythonFromIdeaConfig(),
    path.join(os.homedir(), '.conda', 'envs', 'ml_env', executableName)
  ].filter(Boolean);
  const found = candidates.find((candidate) => path.isAbsolute(candidate) && fs.existsSync(candidate));
  if (!found) throw new Error('没有找到 Python，请通过 LIORA_PYTHON 指定 Python 3.10+ 解释器。');
  return found;
}

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: projectRoot,
    env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
    stdio: 'inherit',
    windowsHide: true
  });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status || 1);
}

if (!fs.existsSync(environmentPython)) {
  run(findBasePython(), ['-m', 'venv', environmentPath]);
}
run(environmentPython, [
  '-m',
  'pip',
  'install',
  '--disable-pip-version-check',
  '--timeout',
  '300',
  '--retries',
  '10',
  '-r',
  path.join(projectRoot, 'backend', 'requirements.txt'),
  'pyinstaller==6.22.0'
]);
console.log(`Liora packaging Python ready: ${environmentPython}`);
