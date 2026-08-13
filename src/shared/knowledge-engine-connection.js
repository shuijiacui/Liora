const fs = require('node:fs');
const path = require('node:path');

const CONNECTION_FILE = 'knowledge-engine.json';

function connectionPath(userDataPath) {
  return path.join(userDataPath, CONNECTION_FILE);
}

function connectionPayload({ port, token, pid = process.pid, updatedAt = new Date().toISOString() }) {
  const safePort = Number(port);
  const safeToken = String(token || '').trim();
  if (!Number.isInteger(safePort) || safePort < 1 || safePort > 65535 || !safeToken) {
    throw new Error('Knowledge Engine 连接信息无效。');
  }
  return {
    schema_version: 1,
    host: '127.0.0.1',
    port: safePort,
    token: safeToken,
    pid: Number(pid) || process.pid,
    updated_at: updatedAt
  };
}

function publishConnection(userDataPath, details) {
  const destination = connectionPath(userDataPath);
  const temporary = `${destination}.${process.pid}.tmp`;
  fs.mkdirSync(userDataPath, { recursive: true });
  fs.writeFileSync(temporary, JSON.stringify(connectionPayload(details), null, 2), {
    encoding: 'utf8',
    mode: 0o600
  });
  fs.renameSync(temporary, destination);
  return destination;
}

function removeConnection(userDataPath, token) {
  const destination = connectionPath(userDataPath);
  try {
    const current = JSON.parse(fs.readFileSync(destination, 'utf8'));
    if (String(current.token || '') !== String(token || '')) return false;
    fs.unlinkSync(destination);
    return true;
  } catch (error) {
    if (error && error.code === 'ENOENT') return false;
    throw error;
  }
}

module.exports = {
  CONNECTION_FILE,
  connectionPath,
  connectionPayload,
  publishConnection,
  removeConnection
};
