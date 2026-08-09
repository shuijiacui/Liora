const fs = require('node:fs');

function loadEnvFile(filePath, target = process.env) {
  let content;
  try {
    content = fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, '');
  } catch {
    return target;
  }

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const separator = line.indexOf('=');
    const key = line.slice(0, separator).trim();
    let value = line.slice(separator + 1).trim();
    if (!key || Object.prototype.hasOwnProperty.call(target, key)) continue;
    if (
      value.length >= 2
      && ((value.startsWith('"') && value.endsWith('"'))
        || (value.startsWith("'") && value.endsWith("'")))
    ) {
      value = value.slice(1, -1);
    }
    target[key] = value;
  }
  return target;
}

module.exports = { loadEnvFile };
