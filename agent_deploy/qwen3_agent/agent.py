import httpx

# 导入AWorld所有主要工具，确保注册到ToolFactory
import aworld.tools.function_tools
import aworld.tools.template_tool
import aworld.tools.async_template_tool
import aworld.tools.function_tools_adapter
import aworld.tools.function_tools_executor
import aworld.tools.tool_action
import aworld.tools.utils

# 自动import examples/tools/下所有主要工具实现
import examples.tools.html
import examples.tools.browsers
import examples.tools.gym_tool
import examples.tools.document
import examples.tools.apis
import examples.tools.trace
import examples.tools.android
import examples.tools.interpreters

# 检测所有已注册工具并打印
try:
    from aworld.core.tool.tool_desc import get_tool_desc
    import json
    print("\n[工具注册检测] 当前已注册工具如下：")
    print(json.dumps(get_tool_desc(), ensure_ascii=False, indent=2))
except Exception as e:
    print(f"[工具注册检测] 检测失败: {e}")

QWEN3_API_URL = "https://modelfactory.lenovo.com/app-workspace-172-1749106801220-vscode/v1/chat/completions"

class AWorldAgent:
    def name(self):
        return "qwen3_agent"

    def description(self):
        return "对接Qwen3大模型的Agent（Lenovo ModelFactory接口）"

    async def run(self, prompt=None, request=None):
        # 构造多轮对话历史
        if request and request.messages:
            messages = [{"role": m.role, "content": m.content} for m in request.messages]
        elif prompt:
            messages = [{"role": "user", "content": prompt}]
        else:
            messages = [{"role": "user", "content": "请回答我的问题"}]

        payload = {
            "model": "/dfs/data/aisz/panhui9/cache_dir/mogao/Qwen3-235B-A22B-FP8",
            "messages": messages,
            "chat_template_kwargs": {"enable_thinking": True},
            "max_tokens": 3000,
            "temperature": 0.6,
            "stream": False
        }
        
        try:
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.post(QWEN3_API_URL, json=payload, timeout=60)
                response.raise_for_status()
                data = response.json()
                print("Qwen3原始响应：", data)  # 保留调试
                
                # 检测工具调用
                tool_call_detected = False
                if "choices" in data and data["choices"]:
                    msg = data["choices"][0]["message"]
                    # 检查是否有tool_calls字段或tool_name等
                    tool_calls = msg.get("tool_calls")
                    if tool_calls:
                        tool_call_detected = True
                        print("[工具调用检测] tool_calls:", tool_calls)
                    # 兼容其他可能的工具调用字段
                    if "tool_name" in msg:
                        tool_call_detected = True
                        print("[工具调用检测] tool_name:", msg["tool_name"])
                    if tool_call_detected is False:
                        print("[工具调用检测] 本次推理未检测到工具调用。")
                    content = msg.get("content")
                    if not content:
                        content = msg.get("reasoning_content")
                    if content:
                        yield content
                    else:
                        yield "[Qwen3返回空内容]"
                else:
                    print("[工具调用检测] 本次推理未检测到工具调用。")
                    yield "[Qwen3无回复]"
        except httpx.TimeoutException:
            yield "[Qwen3请求超时]"
        except httpx.HTTPStatusError as e:
            yield f"[Qwen3 HTTP错误] {e.response.status_code}: {e.response.text}"
        except Exception as e:
            yield f"[Qwen3请求失败] {str(e)}" 