const ALWAYS_IGNORED_DIRECTORIES = new Set([
  ".git", ".obsidian", ".trash", "node_modules", ".agents", ".claude", ".opencode"
]);
const DEFAULT_EXCLUDED_DIRECTORIES = new Set(["copilot", "templates"]);

export function normalizeKnowledgeFolder(value: string): string {
  return String(value ?? "").trim().replace(/\\/gu, "/").replace(/^\/+|\/+$/gu, "");
}

export function isManagedKnowledgePath(
  path: string,
  includedFolders: string[] = [],
  excludedFolders: string[] = []
): boolean {
  const directories = normalizeKnowledgeFolder(path).split("/").slice(0, -1);
  const folded = directories.map((part) => part.toLocaleLowerCase());
  if (folded.some((part) => ALWAYS_IGNORED_DIRECTORIES.has(part))) return false;

  const folder = folded.join("/");
  const matches: Array<{ depth: number; managed: boolean }> = [];
  for (const value of includedFolders) {
    const rule = normalizeKnowledgeFolder(value).toLocaleLowerCase();
    if (rule && (folder === rule || folder.startsWith(`${rule}/`))) {
      matches.push({ depth: rule.split("/").length, managed: true });
    }
  }
  for (const value of excludedFolders) {
    const rule = normalizeKnowledgeFolder(value).toLocaleLowerCase();
    if (rule && (folder === rule || folder.startsWith(`${rule}/`))) {
      matches.push({ depth: rule.split("/").length, managed: false });
    }
  }
  if (matches.length) {
    matches.sort((left, right) => right.depth - left.depth || Number(right.managed) - Number(left.managed));
    return matches[0].managed;
  }
  return !folded.some((part) => DEFAULT_EXCLUDED_DIRECTORIES.has(part));
}

export function isIgnoredKnowledgePath(
  path: string,
  includedFolders: string[] = [],
  excludedFolders: string[] = []
): boolean {
  return !isManagedKnowledgePath(path, includedFolders, excludedFolders);
}
