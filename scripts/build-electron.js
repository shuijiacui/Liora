const { spawnSync } = require('node:child_process');
const path = require('node:path');

const projectRoot = path.resolve(__dirname, '..');
const electronBuilderCli = path.join(
  projectRoot,
  'node_modules',
  'electron-builder',
  'out',
  'cli',
  'cli.js'
);
const target = process.argv[2] === '--dir' ? '--dir' : 'nsis';
const result = spawnSync(
  process.execPath,
  [electronBuilderCli, '--win', target, '--publish', 'never'],
  {
    cwd: projectRoot,
    env: {
      ...process.env,
      ELECTRON_BUILDER_CACHE: path.join(projectRoot, '.package-build', 'electron-builder-cache')
    },
    stdio: 'inherit'
  }
);

if (result.error) {
  throw result.error;
}
process.exit(result.status ?? 1);
