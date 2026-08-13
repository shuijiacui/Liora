import assert from "node:assert/strict";
import test from "node:test";
import { buildRelationEvidence, markdownPassages } from "../src/relation-evidence-model.ts";

test("extracts clean Markdown passages and pairs the most related content", () => {
  const source = "---\ntitle: BFS\n---\n\n## 核心理解\n\nBFS 使用先进先出队列按层遍历图，能够求无权最短路。\n\n## 例子\n\n- 每次从队首取出一个节点。";
  const target = "## 核心理解\n\n队列是一种先进先出的线性结构。\n\n## 应用\n\n- 队列支持 BFS 按层访问节点。";
  const passages = markdownPassages(source);
  assert.ok(passages.some((value) => value.includes("先进先出队列")));
  const evidence = buildRelationEvidence(source, target, "BFS", "队列");
  assert.ok(evidence);
  assert.match(evidence.sourceExcerpt, /队列|BFS/u);
  assert.match(evidence.targetExcerpt, /队列|BFS/u);
});
