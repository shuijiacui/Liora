import assert from "node:assert/strict";
import test from "node:test";
import { localDateKey, memosForDate, normalizeMemos, weekAround } from "../src/memo-model.ts";

test("normalizes and orders lightweight memos", () => {
  const memos = normalizeMemos([
    { id: "later", text: " 晚上回顾 ", date: "2026-08-13", time: "20:00", done: false },
    { id: "anytime", text: "整理问题", date: "2026-08-13", done: false },
    { id: "done", text: "已经完成", date: "2026-08-13", time: "09:00", done: true },
    { text: "缺少日期" }
  ]);
  assert.equal(memos.length, 3);
  assert.deepEqual(memosForDate(memos, "2026-08-13").map((memo) => memo.id), ["later", "anytime", "done"]);
});

test("builds a Monday-first local week", () => {
  const days = weekAround(new Date(2026, 7, 13));
  assert.deepEqual(days.map(localDateKey), [
    "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13",
    "2026-08-14", "2026-08-15", "2026-08-16"
  ]);
});
