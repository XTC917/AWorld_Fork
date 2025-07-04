import httpx
import asyncio

class AWorldAgent:
    def name(self):
        return "qwen3_agent"

    def description(self):
        return "千问本地大模型 Agent (Ollama qwen:7b)"

    async def run(self, prompt=None, request=None):
        # 获取用户输入
        if prompt:
            user_input = prompt
        elif request and request.messages:
            user_input = request.messages[-1].content
        else:
            user_input = ""
        # 调用本地 Ollama API
        url = "http://localhost:11434/v1/chat/completions"
        payload = {
            "model": "qwen:7b",
            "messages": [
                {"role": "user", "content": user_input}
            ]
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, timeout=60)
                response.raise_for_status()
                data = response.json()
                # Ollama 返回格式兼容
                if "choices" in data and data["choices"]:
                    content = data["choices"][0]["message"]["content"]
                    yield content
                else:
                    yield "[Ollama无回复]"
            except Exception as e:
                yield f"[Ollama请求失败] {e}" 