const test = require('node:test');
const assert = require('node:assert/strict');
const { buildKnowledgePath } = require('../src/shared/knowledge-query');

test('knowledge query encodes search filters and pagination safely', () => {
  const path = buildKnowledgePath({
    query: '检索 练习',
    folder: 'Projects/学习',
    tag: '#记忆',
    sort: 'title',
    limit: 25,
    offset: 50
  });
  const url = new URL(path, 'http://liora.local');
  assert.equal(url.pathname, '/api/knowledge');
  assert.equal(url.searchParams.get('q'), '检索 练习');
  assert.equal(url.searchParams.get('folder'), 'Projects/学习');
  assert.equal(url.searchParams.get('tag'), '记忆');
  assert.equal(url.searchParams.get('sort'), 'title');
  assert.equal(url.searchParams.get('limit'), '25');
  assert.equal(url.searchParams.get('offset'), '50');
});

test('knowledge query applies bounded defaults', () => {
  const url = new URL(buildKnowledgePath({ limit: 999, offset: -4, sort: 'unknown' }), 'http://liora.local');
  assert.equal(url.searchParams.get('limit'), '50');
  assert.equal(url.searchParams.get('offset'), '0');
  assert.equal(url.searchParams.get('sort'), 'relevance');
});
