(function knowledgeQueryModule(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.LioraKnowledgeQuery = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function createKnowledgeQuery() {
  function clean(value, maxLength = 200) {
    return String(value || '').trim().slice(0, maxLength);
  }

  function buildKnowledgePath(options = {}) {
    const params = new URLSearchParams();
    params.set('limit', String(Math.min(Math.max(Number(options.limit) || 20, 1), 50)));
    params.set('offset', String(Math.max(Number(options.offset) || 0, 0)));
    const query = clean(options.query);
    const folder = clean(options.folder, 500);
    const tag = clean(options.tag, 100).replace(/^#+/, '');
    const sort = ['relevance', 'updated', 'title'].includes(options.sort)
      ? options.sort
      : 'relevance';
    if (query) params.set('q', query);
    if (folder) params.set('folder', folder);
    if (tag) params.set('tag', tag);
    params.set('sort', sort);
    return `/api/knowledge?${params.toString()}`;
  }

  return { buildKnowledgePath };
});
