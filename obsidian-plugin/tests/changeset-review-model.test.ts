import assert from "node:assert/strict";
import test from "node:test";

import { buildChangeSetReview, knowledgeFieldLabel } from "../src/changeset-review-model.ts";

test("create review shows a single proposed-content preview and omits empty sections", () => {
  const review = buildChangeSetReview({
    action: "create",
    diff: [
      { field: "title", before: null, after: "线性结构" },
      { field: "core_insight", before: null, after: "前驱和后继形成线性秩序。" },
      { field: "sources", before: null, after: [] }
    ]
  });

  assert.equal(review.mode, "create");
  assert.equal(review.summary, "预览将写入的 2 个知识区块");
  assert.deepEqual(review.fields.map((item) => item.label), ["标题", "核心理解"]);
  assert.ok(review.fields.every((item) => item.before === null));
});

test("update review preserves both sides and uses readable field labels", () => {
  const review = buildChangeSetReview({
    action: "update",
    diff: [{ field: "next_step", before: "旧行动", after: "新行动" }]
  });

  assert.equal(review.mode, "update");
  assert.equal(review.summary, "查看 1 处内容变化");
  assert.deepEqual(review.fields[0], {
    field: "next_step",
    label: "下一步",
    before: "旧行动",
    after: "新行动"
  });
  assert.equal(knowledgeFieldLabel("custom_field"), "custom_field");
});
