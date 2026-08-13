function decodePath(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function normalize(value: string): string {
  return decodePath(String(value || "").trim())
    .replace(/^file:\/+?/iu, "")
    .replace(/\\/gu, "/")
    .replace(/[?#].*$/u, "")
    .replace(/^\.\//u, "")
    .replace(/\/{2,}/gu, "/")
    .replace(/\/$/u, "");
}

export function vaultPathCandidates(rawPath: string, vaultBasePath = ""): string[] {
  const raw = normalize(rawPath).replace(/^\[\[|\]\]$/gu, "");
  if (!raw) return [];
  const base = normalize(vaultBasePath).replace(/\/$/u, "");
  const values: string[] = [];
  const add = (value: string): void => {
    const clean = value.replace(/^\/+/, "");
    if (clean && !values.some((item) => item.toLocaleLowerCase() === clean.toLocaleLowerCase())) values.push(clean);
  };

  if (base && (raw.toLocaleLowerCase() === base.toLocaleLowerCase()
    || raw.toLocaleLowerCase().startsWith(`${base.toLocaleLowerCase()}/`))) {
    add(raw.slice(base.length));
  }
  add(raw);
  for (const value of [...values]) {
    if (!/\.md$/iu.test(value)) add(`${value}.md`);
  }
  return values;
}

export function comparableVaultPath(value: string): string {
  return normalize(value).replace(/^\/+/, "").toLocaleLowerCase();
}
