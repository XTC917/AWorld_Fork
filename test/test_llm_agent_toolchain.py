import asyncio
import httpx
import json
from aworld.core.tool.tool_desc import get_tool_desc
from aworld.core.tool.base import ToolFactory
from aworld.core.common import ActionModel, Observation
from aworld.core.event.base import Message, Constants
from aworld.core.context.base import Context

import sys, os
sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/../'))

# 主动import所有工具，确保注册
import importlib
import pkgutil
import re
import inspect

def import_all_tools():
    tool_pkgs = ["aworld.tools", "examples.tools"]
    for pkg in tool_pkgs:
        try:
            m = importlib.import_module(pkg)
            for _, modname, ispkg in pkgutil.iter_modules(m.__path__):
                importlib.import_module(f"{pkg}.{modname}")
        except Exception as e:
            print(f"[WARN] import {pkg} failed: {e}")
import_all_tools()

# QWEN3_API_KEY定义相关全部移除

QWEN3_API_URL = "https://modelfactory.lenovo.com/app-workspace-172-1749106801220-vscode/v1/chat/completions"
# QWEN3_API_KEY = "你的Qwen3 API KEY"  # 如果需要认证，填你的key，否则可去掉

QWEN3_MODEL = "/dfs/data/aisz/panhui9/cache_dir/mogao/Qwen3-235B-A22B-FP8"

# 选用GAIA复杂问题
GAIA_QUESTION = "Which contributor to the version of OpenCV where support was added for the Mask-RCNN model has the same name as a former Chinese head of government when the names are transliterated to the Latin alphabet?"

# 只注册search_api__duck_go工具
all_tools = get_tool_desc()
if 'search_api__duck_go' in all_tools:
    SIMPLE_TOOL_NAME = 'search_api__duck_go'
    SIMPLE_TOOL_DESC = all_tools[SIMPLE_TOOL_NAME]
else:
    raise RuntimeError('未检测到search_api__duck_go工具，请检查工具注册！')

SYSTEM_PROMPT = "你只能通过调用提供的工具来获取信息，不能凭空作答，必须用function call工具。遇到需要联网搜索的问题，必须用duckduckgo搜索工具。"

FEW_SHOT_MESSAGES = [
    {"role": "user", "content": "请用duckduckgo搜索工具查找北京的天气。"},
    {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_1", "type": "function", "function": {"name": SIMPLE_TOOL_NAME, "arguments": '{"query": "北京天气"}'}}
    ]},
    {"role": "tool", "tool_call_id": "call_1", "name": SIMPLE_TOOL_NAME, "content": "北京今天天气晴，最高气温25度。"},
    {"role": "assistant", "content": "北京今天天气晴，最高气温25度。"}
]

def build_functions_desc():
    """将AWorld已注册工具转为OpenAI function calling格式"""
    tool_desc = get_tool_desc()
    functions = []
    for tool_name, tool_info in tool_desc.items():
        for action in tool_info["actions"]:
            params = {}
            for pname, pinfo in action["params"].items():
                params[pname] = {
                    "type": pinfo["type"],
                    "description": pinfo["desc"]
                }
            functions.append({
                "name": f"{tool_name}__{action['name']}",
                "description": action["desc"],
                "parameters": {
                    "type": "object",
                    "properties": params,
                    "required": [k for k, v in action["params"].items() if v["required"]]
                }
            })
    return functions

def execute_tool_call(tool_call):
    """本地执行Qwen3返回的function call"""
    name = tool_call["name"]
    arguments = tool_call.get("arguments", {})
    # 兼容Qwen3参数格式
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            arguments = {}
    # 拆分工具名和action名
    if "__" in name:
        tool_name, action_name = name.split("__", 1)
    else:
        tool_name, action_name = name, None
    tool = ToolFactory(tool_name)
    if not tool:
        return f"[本地未找到工具: {tool_name}]"
    try:
        result = tool.execute(action_name, **arguments)
        return result
    except Exception as e:
        return f"[工具执行异常: {e}]"

def extract_json_from_content(content):
    # 尝试提取content中的第一个JSON对象
    try:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception as e:
        print(f"[WARN] 解析content中的JSON失败: {e}")
    return None

async def main():
    print(f"[DEBUG] function call极简测试，仅注册工具: {SIMPLE_TOOL_NAME}")
    functions = [SIMPLE_TOOL_DESC]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    messages += FEW_SHOT_MESSAGES
    messages.append({"role": "user", "content": GAIA_QUESTION + "（请用duckduckgo搜索工具查找）"})

    payload = {
        "model": QWEN3_MODEL,
        "messages": messages,
        "functions": functions,
        "function_call": "auto"
    }
    headers = {"Content-Type": "application/json"}

    import httpx
    async with httpx.AsyncClient(verify=False, timeout=60) as client:
        response = await client.post(QWEN3_API_URL, json=payload, headers=headers)
        resp = response.json()
        print("[DEBUG] Qwen3响应:", json.dumps(resp, ensure_ascii=False, indent=2))
        tool_calls = resp.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])
        print(f"[DEBUG] tool_calls: {tool_calls}")
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        json_call = extract_json_from_content(content)
        if json_call and "name" in json_call:
            tool_name = json_call["name"]
            arguments = json_call.get("arguments", {})
            print(f"[DEBUG] 解析到content中的工具调用: {tool_name}, 参数: {arguments}")
            tool = ToolFactory(tool_name)
            if tool:
                action = ActionModel(tool_name=tool_name, action_name=tool_name, params=arguments)
                msg = Message(category="action", payload=[action], sender="tester")
                if inspect.iscoroutinefunction(tool.step):
                    result_msg = await tool.step(msg)
                else:
                    result_msg = tool.step(msg)
                print(f"[DEBUG] 工具step返回: {result_msg}")
            else:
                print(f"[WARN] 工具未找到: {tool_name}")
        print("[DEBUG] Qwen3最终回复:\n", content)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())