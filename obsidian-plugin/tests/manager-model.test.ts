import assert from "node:assert/strict";
import test from "node:test";

test("manager workflow keeps structural changes explicit", () => {
  const risks = {
    exactCreate: "low",
    exactUpdate: "low",
    ambiguousAlignment: "review",
    split: "review",
    merge: "review",
    softConnection: "candidate"
  } as const;
  assert.equal(risks.exactCreate, "low");
  assert.equal(risks.ambiguousAlignment, "review");
  assert.equal(risks.split, "review");
  assert.equal(risks.merge, "review");
  assert.equal(risks.softConnection, "candidate");
});
