import fs from "node:fs";
import path from "node:path";

export interface DiscoveredConnection {
  engineUrl: string;
  accessToken: string;
}

interface ConnectionFile {
  schema_version?: unknown;
  host?: unknown;
  port?: unknown;
  token?: unknown;
}

export function defaultConnectionPath(environment: NodeJS.ProcessEnv = process.env): string {
  const override = String(environment.LIORA_USER_DATA_DIR || "").trim();
  const appData = String(environment.APPDATA || "").trim();
  const directory = override || (appData ? path.join(appData, "liora-desktop-companion") : "");
  return directory ? path.join(directory, "knowledge-engine.json") : "";
}

export function parseConnectionFile(value: unknown): DiscoveredConnection | null {
  if (!value || typeof value !== "object") return null;
  const item = value as ConnectionFile;
  const host = String(item.host || "").trim();
  const port = Number(item.port);
  const token = String(item.token || "").trim();
  if (item.schema_version !== 1 || host !== "127.0.0.1") return null;
  if (!Number.isInteger(port) || port < 1 || port > 65535 || !token) return null;
  return { engineUrl: `http://127.0.0.1:${port}`, accessToken: token };
}

export function discoverConnection(filePath = defaultConnectionPath()): DiscoveredConnection | null {
  if (!filePath) return null;
  try {
    return parseConnectionFile(JSON.parse(fs.readFileSync(filePath, "utf8")));
  } catch {
    return null;
  }
}
