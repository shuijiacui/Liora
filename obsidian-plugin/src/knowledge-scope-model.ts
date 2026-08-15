import { normalizeKnowledgeFolder } from "./knowledge-path-filter.ts";

export type ScopeDecision = "inherit" | "include" | "exclude";

export function folderDecision(folder: string, included: string[], excluded: string[]): ScopeDecision {
  const key = normalizeKnowledgeFolder(folder).toLocaleLowerCase();
  if (included.some((value) => normalizeKnowledgeFolder(value).toLocaleLowerCase() === key)) return "include";
  if (excluded.some((value) => normalizeKnowledgeFolder(value).toLocaleLowerCase() === key)) return "exclude";
  return "inherit";
}

export function applyFolderDecision(
  folder: string,
  decision: ScopeDecision,
  included: string[],
  excluded: string[]
): { included: string[]; excluded: string[] } {
  const normalized = normalizeKnowledgeFolder(folder);
  const key = normalized.toLocaleLowerCase();
  const without = (values: string[]): string[] =>
    values.filter((value) => normalizeKnowledgeFolder(value).toLocaleLowerCase() !== key);
  return {
    included: decision === "include" ? [...without(included), normalized] : without(included),
    excluded: decision === "exclude" ? [...without(excluded), normalized] : without(excluded)
  };
}

export function collectKnowledgeFolders(paths: string[]): string[] {
  const folders = new Map<string, string>();
  for (const path of paths) {
    const parts = normalizeKnowledgeFolder(path).split("/").slice(0, -1);
    for (let index = 1; index <= parts.length; index += 1) {
      const folder = parts.slice(0, index).join("/");
      folders.set(folder.toLocaleLowerCase(), folder);
    }
  }
  return [...folders.values()].sort((left, right) => {
    const depth = left.split("/").length - right.split("/").length;
    return depth || left.localeCompare(right, "zh-CN");
  });
}
