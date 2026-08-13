const test = require('node:test');
const assert = require('node:assert/strict');
const { routeVoiceIntent } = require('../src/services/voice-intent');

test('routes natural bilingual requests after removing the wake word', () => {
  assert.equal(routeVoiceIntent('Hi Liora，今天天气怎么样').intent, 'weather');
  assert.equal(routeVoiceIntent('嗨莉奥拉，陪我复盘一下今天').intent, 'reflection');
  assert.equal(routeVoiceIntent('Hi Liora，考考我以前学过的内容').intent, 'review');
  assert.equal(routeVoiceIntent('开始复述').intent, 'review');
  assert.equal(routeVoiceIntent('回顾一下').intent, 'review');
  assert.equal(routeVoiceIntent('我之前都记了哪些笔记').intent, 'knowledge');
  assert.equal(routeVoiceIntent('Do I need an umbrella today?').intent, 'weather');
});

test('does not route unrelated or weak speech', () => {
  assert.equal(routeVoiceIntent('Hi Liora').intent, null);
  assert.equal(routeVoiceIntent('帮我播放音乐').intent, null);
});

test('marks competing feature signals as ambiguous', () => {
  const result = routeVoiceIntent('我想聊聊今天学习的天气知识');
  assert.equal(result.intent, null);
  assert.equal(result.ambiguous, true);
});

test('keeps browsing past records in knowledge instead of active review', () => {
  assert.equal(routeVoiceIntent('看看回顾记录').intent, 'knowledge');
  assert.equal(routeVoiceIntent('我想回顾之前记录的知识').intent, 'knowledge');
});
