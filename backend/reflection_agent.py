import re


START_PROMPT = "今天学到了什么有意思的东西？"
COMPLETE_PROMPT = "谢谢你认真把它讲给我听。我已经替你把这次反思保存下来了。"


def _compact(content: str, limit: int = 28) -> str:
    value = re.sub(r"\s+", " ", content.strip())
    return value if len(value) <= limit else f"{value[:limit]}…"


def follow_up(content: str, turn_number: int) -> str:
    text = content.strip()
    compact = _compact(text)

    if turn_number == 1:
        if len(text) < 8 or any(word in text for word in ("不知道", "没什么", "忘了")):
            return "没关系，哪怕只挑一个很小的片段：今天哪个瞬间让你停下来想了一下？"
        if any(word in text.lower() for word in ("像", "类似", "区别", "对比", "vs")):
            return f"你提到“{compact}”。这个联系为什么会让你觉得成立？"
        if any(word in text for word in ("因为", "所以", "意味着")):
            return "如果用一个具体例子来说明你的理解，你会怎么讲？"
        return f"在“{compact}”里面，哪个概念让你印象最深？"

    if turn_number == 2:
        if any(word in text for word in ("例子", "比如", "例如")):
            return "这个例子帮助你看清了什么？它有没有仍然说不通的地方？"
        if any(word in text for word in ("不确定", "可能", "应该", "猜")):
            return "你觉得最需要以后再验证的是哪一部分？"
        return "如果把这件事讲给明天的自己，你最希望自己记住哪一点？"

    return "最后，用一句话留下你现在最想记住的理解吧。"


def make_summary(user_messages: list[str]) -> str:
    cleaned = [_compact(message, 80) for message in user_messages if message.strip()]
    if not cleaned:
        return "完成了一次学习反思。"
    if len(cleaned) == 1:
        return cleaned[0]
    return f"{cleaned[0]}；最后留下：{cleaned[-1]}"


def make_knowledge_draft(user_messages: list[str], existing: dict | None = None) -> dict:
    cleaned = [_compact(message, 120) for message in user_messages if message.strip()]
    if not cleaned:
        raise ValueError("至少说下一点内容后再整理吧。")

    existing_content = (existing or {}).get("content", {})
    existing_chain = list(existing_content.get("logic_chain") or [])
    chain = []
    for item in [*existing_chain, *cleaned]:
        if item and item not in chain:
            chain.append(item)
    title_source = existing_content.get("title") or cleaned[0]
    title = _compact(title_source, 18).rstrip("。！？；：") or "新的理解"
    existing_core = str(existing_content.get("core_insight") or "").strip()
    core_insight = (
        f"{existing_core}；新的感悟：{cleaned[-1]}"
        if existing_core
        else cleaned[-1]
    )
    uncertain = [
        item for item in cleaned if any(word in item for word in ("不确定", "可能", "不知道", "疑问", "？"))
    ]
    return {
        "title": title,
        "core_insight": core_insight,
        "logic_chain": chain[-6:],
        "open_questions": uncertain[-3:],
        "next_step": "之后遇到新的例子时，继续补充和验证这条理解。",
    }
