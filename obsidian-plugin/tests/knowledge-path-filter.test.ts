import assert from "node:assert/strict";
import test from "node:test";

import { isIgnoredKnowledgePath, isManagedKnowledgePath } from "../src/knowledge-path-filter.ts";

test("ignores Copilot agent resources at any depth and with any casing", () => {
  assert.equal(isIgnoredKnowledgePath("Copilot/skills/writing.md"), true);
  assert.equal(isIgnoredKnowledgePath("Resources/copilot/prompts/review.md"), true);
  assert.equal(isIgnoredKnowledgePath("COPILOT/README.md"), true);
});

test("manual folder rules inherit and the more specific child overrides its parent", () => {
  assert.equal(isManagedKnowledgePath("Notes/Private/Secret.md", [], ["Notes/Private"]), false);
  assert.equal(
    isManagedKnowledgePath("Notes/Private/Shared/Teach.md", ["Notes/Private/Shared"], ["Notes/Private"]),
    true
  );
});

test("a manual include can opt the default Copilot folder back into management", () => {
  assert.equal(isManagedKnowledgePath("Copilot/skills/writing.md", ["Copilot"], []), true);
});

test("agent skill mirror directories can never enter personal knowledge", () => {
  for (const folder of [".agents", ".claude", ".opencode"]) {
    assert.equal(isManagedKnowledgePath(`${folder}/skills/writing.md`, [folder], []), false);
  }
});

test("keeps user notes whose filename merely mentions copilot", () => {
  assert.equal(isIgnoredKnowledgePath("Notes/Using Copilot.md"), false);
  assert.equal(isIgnoredKnowledgePath("Knowledge/copilot-workflow.md"), false);
});
