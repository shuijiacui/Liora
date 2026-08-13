import assert from "node:assert/strict";
import test from "node:test";
import { comparableVaultPath, vaultPathCandidates } from "../src/vault-path-model.ts";

test("resolves engine and Windows paths into Vault-relative Markdown candidates", () => {
  assert.deepEqual(
    vaultPathCandidates("D:\\obsidian\\Liora\\03_Knowledge\\BFS.md", "D:\\obsidian\\Liora"),
    ["03_Knowledge/BFS.md", "D:/obsidian/Liora/03_Knowledge/BFS.md"]
  );
  assert.deepEqual(vaultPathCandidates("03_Knowledge/BFS"), ["03_Knowledge/BFS", "03_Knowledge/BFS.md"]);
  assert.equal(comparableVaultPath("03_Knowledge\\BFS.md"), "03_knowledge/bfs.md");
});
