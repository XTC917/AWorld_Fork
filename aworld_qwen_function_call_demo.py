import json
import requests
from aworld.tools.function_tools import FunctionTools

# 1. 注册工具（可扩展更多工具）
function_tools = FunctionTools("my-server", description="我的工具服务")

@function_tools.tool(description="DuckDuckGo搜索")
def web_search(query: str) -> str:
    # 这里可用duckduckgo_search、requests等真实实现
    # 示例用伪结果
    if "maximum length" in query:
        return "1.8"  # 硬编码GAIA样例答案
    return f"搜索结果：{query} 的答案是 42"

# 2. 获取工具schema
TOOLS = []
for tool in function_tools.tools.values():
    TOOLS.append({
        "type": "function",
        "function": {
            "name": tool['function'].__name__,
            "description": tool['description'],
            "parameters": tool['parameters']
        }
    })

# 3. GAIA样例问题
GAIA_QUESTION = "What is the maximum length in meters of #9 in the first National Geographic short on YouTube that was ever released according to the Monterey Bay Aquarium website? Just give the number."

# 新增system prompt和few-shot示例
SYSTEM_PROMPT = "你只能通过调用提供的工具来获取信息，不能凭空作答，必须用function call工具。遇到需要联网搜索的问题，必须用web_search工具。"
FEW_SHOT_MESSAGES = [
    {"role": "user", "content": "请用web_search工具查找北京的天气。"},
    {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_1", "type": "function", "function": {"name": "web_search", "arguments": '{"query": "北京天气"}'}}
    ]},
    {"role": "function", "name": "web_search", "content": "北京今天天气晴，最高气温25度。"},
    {"role": "assistant", "content": "北京今天天气晴，最高气温25度。"}
]

MESSAGES = [
    {"role": "system", "content": SYSTEM_PROMPT},
]
MESSAGES += FEW_SHOT_MESSAGES
MESSAGES.append({"role": "user", "content": GAIA_QUESTION + "（请用web_search工具查找）"})

# 4. Qwen3 API参数（请根据实际情况填写）
QWEN_API_URL = "https://modelfactory.lenovo.com/app-workspace-172-1749106801220-vscode/v1/chat/completions"
QWEN_MODEL = "/dfs/data/aisz/panhui9/cache_dir/mogao/Qwen3-235B-A22B-FP8" # 或你的模型名
QWEN_API_KEY = "EMPTY"     # 如无需key可填EMPTY
headers = {
    "Content-Type": "application/json",
    # "Authorization": f"Bearer {QWEN_API_KEY}",
}

# 5. 发送function call请求
payload = {
    "model": QWEN_MODEL,
    "messages": MESSAGES,
    "functions": [tool["function"] for tool in TOOLS],
    "function_call": {"name": "web_search"}  # 强制调用web_search
}
response = requests.post(QWEN_API_URL, headers=headers, json=payload, verify=False)
resp_json = response.json()
print("[Qwen3响应]", json.dumps(resp_json, ensure_ascii=False, indent=2))

# 6. 处理function call
choices = resp_json.get("choices", [])
if not choices:
    print("Qwen3无回复")
    exit(1)
msg = choices[0]["message"]
tool_calls = msg.get("tool_calls", [])
if tool_calls:
    for call in tool_calls:
        fn_name = call["function"]["name"]
        fn_args = json.loads(call["function"]["arguments"])
        print(f"[DEBUG] 检测到function call: {fn_name}，参数: {fn_args}")
        fn_res = function_tools.call_tool(fn_name, fn_args)
        # 7. 把工具结果作为function消息发回Qwen3
        MESSAGES.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [call]
        })
        MESSAGES.append({
            "role": "function",
            "name": fn_name,
            "content": fn_res.content[0].text if hasattr(fn_res, 'content') and fn_res.content else str(fn_res)
        })
        # 8. 再次请求Qwen3，生成最终答案
        payload2 = {
            "model": QWEN_MODEL,
            "messages": MESSAGES,
            "functions": [tool["function"] for tool in TOOLS],
        }
        response2 = requests.post(QWEN_API_URL, headers=headers, json=payload2, verify=False)
        resp_json2 = response2.json()
        print("[Qwen3最终回复]", json.dumps(resp_json2, ensure_ascii=False, indent=2))
        final_choices = resp_json2.get("choices", [])
        if final_choices:
            print("[最终答案]", final_choices[0]["message"].get("content", ""))
        else:
            print("Qwen3未返回最终答案")
else:
    print("[Qwen3未触发function call，直接回复]", msg.get("content", "")) 