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

test("normalizes only evidence-backed knowledge-gap prompts", () => {
  const prompts = normalizeReflectionPrompts({
    items: [{
      id: "PROMPT-1",
      kind: "knowledge_gap",
      knowledge_id: "KO-1",
      title: "注意力",
      path: "03_Knowledge/注意力.md",
      context: "注意力会动态聚合信息。",
      prompt: "为什么点积需要缩放？",
      reason_code: "open_question",
      reason: "这个问题来自尚待探索。"
    }, {
      id: "invented",
      kind: "recall",
      prompt: "一个没有证据的问题",
      reason_code: "model_guess"
    }]
  });
  assert.equal(prompts.length, 1);
  assert.equal(prompts[0].prompt, "为什么点积需要缩放？");
});

test("creates a safe Vault fallback from parsed open questions", () => {
  const prompts = promptsFromDashboardQuestions([{
    knowledgeId: "KO-1",
    title: "注意力",
    path: "注意力.md",
    question: "为什么需要缩放？"
  }]);
  assert.equal(prompts[0].kind, "knowledge_gap");
  assert.match(prompts[0].reason, /Liora没有额外猜测/u);
});
