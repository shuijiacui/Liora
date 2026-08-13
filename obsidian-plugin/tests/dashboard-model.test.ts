import assert from "node:assert/strict";
import test from "node:test";
import {
  buildReflectionPromptActionUrl,
  buildDashboardUrl,
  buildReflectionPromptsUrl,
  extractOpenQuestions,
  normalizeEngineDashboard,
  normalizeEngineUrl
} from "../src/dashboard-model.ts";

test("normalizes loopback Knowledge Engine URLs", () => {
  assert.equal(normalizeEngineUrl(" http://127.0.0.1:43117/ "), "http://127.0.0.1:43117");
  assert.equal(normalizeEngineUrl("http://localhost:9000/base/"), "http://localhost:9000/base");
  assert.equal(buildDashboardUrl("http://127.0.0.1:43117"),
    "http://127.0.0.1:43117/api/dashboard");
  assert.equal(buildReflectionPromptsUrl("http://127.0.0.1:43117", 99),
    "http://127.0.0.1:43117/api/reflection-prompts?limit=20");
  assert.equal(
    buildReflectionPromptActionUrl("http://127.0.0.1:43117", "question/一", "start"),
    "http://127.0.0.1:43117/api/reflection-prompts/question%2F%E4%B8%80/start"
  );
});

test("rejects non-local Knowledge Engine URLs", () => {
  assert.throws(() => normalizeEngineUrl("https://example.com"), /只允许连接本机/);
  assert.throws(() => normalizeEngineUrl("not a URL"), /格式不正确/);
});

test("extracts open questions without leaking into the next section", () => {
  assert.deepEqual(extractOpenQuestions(
    "# Attention\n\n## 尚待探索\n\n- 为什么需要缩放？\n- 多个头如何分工？\n\n## 下一步\n\n手算例子。\n"
  ), ["为什么需要缩放？", "多个头如何分工？"]);
});

test("normalizes the dashboard API response", () => {
  const result = normalizeEngineDashboard({
    knowledge_count: 12,
    open_question_count: 3,
    recent: [
      {
        id: "KO-1",
        title: "Self Attention",
        relative_path: "03_Knowledge/Self Attention.md",
        updated_at: "2026-08-12T10:00:00+08:00",
        snippet: "根据输入动态聚合信息。"
      },
      { title: "missing path" },
      null
    ],
    open_questions: [{
      knowledge_id: "KO-1",
      title: "Self Attention",
      path: "03_Knowledge/Self Attention.md",
      question: "为什么要缩放？"
    }],
    health: { growing: 0, stable: 0, due: 0 }
  });
  assert.equal(result.total, 12);
  assert.equal(result.openQuestionCount, 3);
  assert.deepEqual(result.recent, [{
    id: "KO-1",
    title: "Self Attention",
    path: "03_Knowledge/Self Attention.md",
    updatedAt: "2026-08-12T10:00:00+08:00",
    summary: "根据输入动态聚合信息。"
  }]);
  assert.deepEqual(result.openQuestions, [{
    knowledgeId: "KO-1",
    title: "Self Attention",
    path: "03_Knowledge/Self Attention.md",
    question: "为什么要缩放？"
  }]);
});
