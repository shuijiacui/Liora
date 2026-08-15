import assert from "node:assert/strict";
import test from "node:test";
import {
  normalizeReflectionPrompts,
  promptsFromDashboardQuestions,
  QUESTION_VOICES,
  voiceFor
} from "../src/question-card-model.ts";

test("every question-card title mentions Liora", () => {
  assert.ok(QUESTION_VOICES.length >= 5);
  for (const voice of QUESTION_VOICES) {
    assert.match(voice.eyebrow, /Liora/u);
    assert.ok(voice.eyebrow.length <= 20);
  }
});

test("question-card wording changes deterministically without changing the prompt", () => {
  const first = voiceFor("prompt-id", 0);
  const second = voiceFor("prompt-id", 1);
  assert.notEqual(first.eyebrow, second.eyebrow);
  assert.deepEqual(voiceFor("prompt-id", 0), first);
});

test("normalizes grounded open, diagnostic and transfer prompts", () => {
  const prompts = normalizeReflectionPrompts({
    items: [{
      id: "PROMPT-1",
      kind: "open_question",
      knowledge_id: "KO-1",
      title: "注意力",
      path: "03_Knowledge/注意力.md",
      context: "注意力会动态聚合信息。",
      prompt: "为什么点积需要缩放？",
      reason_code: "open_question",
      reason: "这个问题来自尚待探索。"
    }, {
      id: "PROMPT-2",
      kind: "diagnostic",
      knowledge_id: "KO-1",
      title: "注意力",
      path: "03_Knowledge/注意力.md",
      prompt: "如何准确解释缩放点积？",
      reason_code: "kc_uncertainty",
      reason: "Liora 还不能确定你是否掌握这一组件。",
      target_kc_ids: ["KC-1"],
      rubric: { evidence_claim_ids: ["CLAIM-1"] },
      learner_state: { label: "unknown", mastery: 0.35, uncertainty: 0.75 }
    }, {
      id: "invented",
      kind: "recall",
      prompt: "一个没有证据的问题",
      reason_code: "model_guess"
    }]
  });
  assert.equal(prompts.length, 2);
  assert.equal(prompts[0].prompt, "为什么点积需要缩放？");
  assert.equal(prompts[1].kind, "diagnostic");
  assert.deepEqual(prompts[1].targetKcIds, ["KC-1"]);
});

test("creates a safe Vault fallback from parsed open questions", () => {
  const prompts = promptsFromDashboardQuestions([{
    knowledgeId: "KO-1",
    title: "注意力",
    path: "注意力.md",
    question: "为什么需要缩放？"
  }]);
  assert.equal(prompts[0].kind, "open_question");
  assert.match(prompts[0].reason, /Liora没有额外猜测/u);
});
