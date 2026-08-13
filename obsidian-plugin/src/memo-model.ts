export interface LioraMemo {
  id: string;
  text: string;
  date: string;
  time: string;
  done: boolean;
  createdAt: string;
}

export function localDateKey(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function normalizeMemos(value: unknown): LioraMemo[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item): LioraMemo[] => {
    if (!item || typeof item !== "object") return [];
    const raw = item as Partial<LioraMemo>;
    const text = typeof raw.text === "string" ? raw.text.trim().slice(0, 160) : "";
    const date = typeof raw.date === "string" && /^\d{4}-\d{2}-\d{2}$/u.test(raw.date)
      ? raw.date
      : "";
    if (!text || !date) return [];
    return [{
      id: typeof raw.id === "string" && raw.id ? raw.id : `${date}-${text}`,
      text,
      date,
      time: typeof raw.time === "string" && /^\d{2}:\d{2}$/u.test(raw.time) ? raw.time : "",
      done: raw.done === true,
      createdAt: typeof raw.createdAt === "string" ? raw.createdAt : ""
    }];
  });
}

export function memosForDate(memos: LioraMemo[], date: string): LioraMemo[] {
  return memos
    .filter((memo) => memo.date === date)
    .sort((left, right) => {
      if (left.done !== right.done) return Number(left.done) - Number(right.done);
      if (!left.time && right.time) return 1;
      if (left.time && !right.time) return -1;
      return left.time.localeCompare(right.time) || left.createdAt.localeCompare(right.createdAt);
    });
}

export function weekAround(date: Date): Date[] {
  const start = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const mondayOffset = (start.getDay() + 6) % 7;
  start.setDate(start.getDate() - mondayOffset);
  return Array.from({ length: 7 }, (_, index) =>
    new Date(start.getFullYear(), start.getMonth(), start.getDate() + index));
}
