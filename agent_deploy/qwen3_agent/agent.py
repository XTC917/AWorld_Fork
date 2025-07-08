import httpx
import asyncio

class AWorldAgent:
    def name(self):
        return "qwen3_agent"

    def description(self):
        return "千问本地大模型 Agent (Ollama qwen:7b)"

    async def run(self, prompt=None, request=None):
        # 构造多轮对话历史
        if request and request.messages:
            messages = [{"role": m.role, "content": m.content} for m in request.messages]
        elif prompt:
            messages = [{"role": "user", "content": prompt}]
        else:
            messages = []

        url = "http://localhost:11434/v1/chat/completions"
        payload = {
            "model": "qwen:7b",
            "messages": messages
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, timeout=60)
                response.raise_for_status()
                data = response.json()
                if "choices" in data and data["choices"]:
                    content = data["choices"][0]["message"]["content"]
                    yield content
                else:
                    yield "[Ollama无回复]"
            except Exception as e:
                yield f"[Ollama请求失败] {e}" 