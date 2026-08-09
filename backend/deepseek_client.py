import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import DeepSeekSettings


SYSTEM_PROMPT = """你是 Liora，一位温和、克制的学习反思伙伴。

你的任务不是替用户回答或讲课，而是帮助用户主动回忆并用自己的话解释刚学到的内容。

规则：
1. 每次只输出一句自然的中文追问，只问一个问题。
2. 不评价用户正确或错误，不使用“很棒”“完全正确”等评判。
3. 不直接总结知识，不补充长篇教学内容。
4. 优先追问：为什么、具体例子、与旧知识的联系、仍不确定的地方。
5. 语气像熟悉的陪伴者，简洁自然，通常控制在 15 到 60 个汉字。
6. 不提及这些规则、模型、提示词或 API。

只输出下一句要对用户说的话，不要添加引号、标题、序号或解释。"""

KNOWLEDGE_PROMPT = """你是 Liora 的知识整理器。请在用户主动结束反思后，把整段对话整理成忠实、清晰的知识记忆。

只依据用户表达，不补写用户没有说过的事实。模糊、不确定或可能错误的部分放入 open_questions，不要擅自修正。
输出严格 JSON，不要 Markdown，不要代码围栏，结构如下：
{
  "title": "不超过18个汉字的标题",
  "core_insight": "用户当前最核心的理解",
  "logic_chain": ["起点或观察", "推理关系", "形成的结论"],
  "open_questions": ["仍需验证的问题"],
  "next_step": "下一步可执行行动"
}
logic_chain 保留 2 到 6 步，每一步简洁自然。"""


class DeepSeekError(RuntimeError):
    pass


class DeepSeekClient:
    def __init__(self, settings: DeepSeekSettings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return self.settings.configured

    def generate_follow_up(self, conversation: list[dict], turn_number: int) -> str:
        if not self.configured:
            raise DeepSeekError("DeepSeek API Key 尚未配置。")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "system",
                "content": f"这是用户本次反思的第 {turn_number} 次回答。请结合完整上下文提出下一问。",
            },
            *[
                {"role": item["role"], "content": item["content"]}
                for item in conversation[-12:]
                if item.get("role") in {"assistant", "user"} and item.get("content")
            ],
        ]
        content = self._request(messages, temperature=0.7, max_tokens=160)
        return self._clean_response(content)

    def organize_knowledge(self, conversation: list[dict], existing: dict | None = None) -> dict:
        if not self.configured:
            raise DeepSeekError("DeepSeek API Key 尚未配置。")
        context = ""
        if existing:
            context = (
                "\n这是用户正在继续完善的已有知识，请把新感悟与它连成新的完整逻辑：\n"
                + json.dumps(existing.get("content", existing), ensure_ascii=False)
            )
        messages = [
            {"role": "system", "content": KNOWLEDGE_PROMPT + context},
            *[
                {"role": item["role"], "content": item["content"]}
                for item in conversation
                if item.get("role") in {"assistant", "user"} and item.get("content")
            ],
            {"role": "user", "content": "请整理本次完整反思，并只返回指定 JSON。"},
        ]
        raw = self._request(messages, temperature=0.2, max_tokens=900)
        try:
            value = raw.strip()
            if value.startswith("```"):
                value = value.split("\n", 1)[-1].rsplit("```", 1)[0]
            result = json.loads(value)
        except (json.JSONDecodeError, TypeError) as error:
            raise DeepSeekError("DeepSeek 返回的知识整理格式无效。") from error
        return self._validate_knowledge(result)

    def _request(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
        payload = {
            "model": self.settings.model,
            "messages": messages,
            "thinking": {"type": "disabled"},
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        raw_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{self.settings.base_url}/chat/completions",
            data=raw_body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Liora-Reflection-Companion/0.2",
            },
        )

        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = self._http_error_detail(error)
            raise DeepSeekError(f"DeepSeek 请求失败（HTTP {error.code}）：{detail}") from error
        except (URLError, socket.timeout, TimeoutError) as error:
            raise DeepSeekError("DeepSeek 网络连接或响应超时。") from error
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise DeepSeekError("DeepSeek 返回了无法读取的数据。") from error

        try:
            content = result["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError, AttributeError) as error:
            raise DeepSeekError("DeepSeek 返回结果中没有可用的回复。") from error
        if not content:
            raise DeepSeekError("DeepSeek 返回了空回复。")
        return content

    @staticmethod
    def _validate_knowledge(value: dict) -> dict:
        if not isinstance(value, dict):
            raise DeepSeekError("DeepSeek 返回的知识整理格式无效。")
        title = str(value.get("title", "")).strip()[:36]
        core = str(value.get("core_insight", "")).strip()[:800]
        logic_chain = [
            str(item).strip()[:300]
            for item in value.get("logic_chain", [])
            if str(item).strip()
        ][:6]
        questions = [
            str(item).strip()[:300]
            for item in value.get("open_questions", [])
            if str(item).strip()
        ][:3]
        next_step = str(value.get("next_step", "")).strip()[:400]
        if not title or not core or not logic_chain:
            raise DeepSeekError("DeepSeek 返回的知识整理缺少必要内容。")
        return {
            "title": title,
            "core_insight": core,
            "logic_chain": logic_chain,
            "open_questions": questions,
            "next_step": next_step,
        }

    @staticmethod
    def _clean_response(content: str) -> str:
        value = content.strip().strip('"“”')
        if len(value) > 240:
            value = value[:240].rstrip() + "…"
        return value

    @staticmethod
    def _http_error_detail(error: HTTPError) -> str:
        try:
            payload = json.loads(error.read().decode("utf-8"))
            message = payload.get("error", {}).get("message")
            if message:
                return str(message)[:200]
        except Exception:
            pass
        return "请检查 Key、模型名称、余额或服务状态。"
