import requests
from aworld.cmd.data_model import BaseAWorldAgent, ChatCompletionRequest
from aworld.output.base import Output

QWEN3_API_URL = "https://modelfactory.lenovo.com/app-workspace-172-1749106801220-vscode/v1/chat/completions"

class AWorldAgent(BaseAWorldAgent):
    def name(self):
        return "qwen3_agent"

    def description(self):
        return "对接Qwen3大模型的Agent"

    async def run(self, prompt: str = None, request: ChatCompletionRequest = None):
        user_message = prompt or (request.messages[-1].content if request and request.messages else "")
        payload = {
            "model": "/dfs/data/aisz/panhui9/cache_dir/mogao/Qwen3-235B-FP8",
            "messages": [{"role": "user", "content": user_message}],
            "chat_template_kwargs": {"enable_thinking": True},
            "max_tokens": 1000,
            "temperature": 0.6,
            "stream": False
        }
        resp = requests.post(QWEN3_API_URL, json=payload, verify=False)
        resp.raise_for_status()
        data = resp.json()
        reply = data["choices"][0]["message"]["content"]
        yield Output.text(reply) 