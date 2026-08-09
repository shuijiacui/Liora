const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { loadEnvFile } = require('../src/services/env-file');

test('loads simple quoted values without overriding the process environment', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'liora-env-'));
  const file = path.join(directory, '.env');
  fs.writeFileSync(file, 'LIORA_RUNTIME=device\nLIORA_WEATHER_LOCATION="上海"\n', 'utf8');
  const target = { LIORA_RUNTIME: 'desktop' };
  loadEnvFile(file, target);
  assert.equal(target.LIORA_RUNTIME, 'desktop');
  assert.equal(target.LIORA_WEATHER_LOCATION, '上海');
  fs.unlinkSync(file);
  fs.rmdirSync(directory);
});
