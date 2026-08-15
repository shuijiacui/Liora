import assert from "node:assert/strict";
import test from "node:test";

import { applyFolderDecision, collectKnowledgeFolders, folderDecision } from "../src/knowledge-scope-model.ts";

test("collects every folder level once in stable hierarchy order", () => {
  assert.deepEqual(
    collectKnowledgeFolders(["Notes/Private/one.md", "Notes/two.md", "Copilot/skill.md"]),
    ["Copilot", "Notes", "Notes/Private"]
  );
});

test("folder decisions are mutually exclusive and can return to inheritance", () => {
  const excluded = applyFolderDecision("Notes/Private", "exclude", ["Notes/Private"], []);
  assert.deepEqual(excluded, { included: [], excluded: ["Notes/Private"] });
  assert.equal(folderDecision("notes/private", excluded.included, excluded.excluded), "exclude");
  assert.deepEqual(
    applyFolderDecision("Notes/Private", "inherit", excluded.included, excluded.excluded),
    { included: [], excluded: [] }
  );
});
