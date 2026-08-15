import type { ChangeSet } from "./knowledge-service";

const FIELD_LABELS: Record<string, string> = {
  title: "标题",
  core_insight: "核心理解",
  key_points: "关键要点",
  logic_chain: "推理过程",
  examples: "例子",
  extensions: "延伸理解",
  boundaries: "适用边界",
  connections: "知识连接",
  open_questions: "尚待探索",
  next_step: "下一步",
  sources: "来源"
};

export interface ChangeSetReviewField {
  field: string;
  label: string;
  before: unknown;
  after: unknown;
}

export interface ChangeSetReviewModel {
  mode: "create" | "update";
  summary: string;
  fields: ChangeSetReviewField[];
}

function hasContent(value: unknown): boolean {
  if (value === null || value === undefined || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  return true;
}

export function knowledgeFieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field;
}

export function buildChangeSetReview(item: Pick<ChangeSet, "action" | "diff">): ChangeSetReviewModel {
  const mode = item.action === "create" ? "create" : "update";
  const changes = mode === "create"
    ? item.diff.filter((change) => hasContent(change.after))
    : item.diff;
  const fields = changes.map((change) => ({
    ...change,
    label: knowledgeFieldLabel(change.field)
  }));
  return {
    mode,
    summary: mode === "create"
      ? `预览将写入的 ${fields.length} 个知识区块`
      : `查看 ${fields.length} 处内容变化`,
    fields
  };
}
