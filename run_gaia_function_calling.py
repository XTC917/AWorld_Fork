import os
import sys
import json
import asyncio
from aworld.agents.llm_agent import Agent
from aworld.config.conf import AgentConfig
from aworld.core.common import Observation
from aworld.core.context.base import Context

# 自动注册所有工具
import importlib, pkgutil
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

# 加载GAIA数据集
GAIA_PATH = "examples/gaia/GAIA/2023/metadata.jsonl"
with open(GAIA_PATH, "r", encoding="utf-8") as f:
    gaia_data = [json.loads(line) for line in f if line.strip()]

# 构建Agent
agent_conf = AgentConfig(
    llm_provider=os.getenv("LLM_PROVIDER", "openai"),
    llm_model_name=os.getenv("LLM_MODEL_NAME", "gpt-4o"),
    llm_api_key=os.getenv("LLM_API_KEY", "your_openai_api_key"),
    llm_base_url=os.getenv("LLM_BASE_URL", ""),
    llm_temperature=0.0,
)
agent = Agent(
    conf=agent_conf,
    name="gaia_function_call_agent",
    system_prompt="你是一个善于分步调用工具解决复杂问题的AI助手。遇到需要外部信息、计算、检索等问题，必须用function calling工具链，不允许凭空作答。最终答案请用<answer>标签包裹。",
)

# 评测主流程
async def main(max_questions=10):
    correct = 0
    for idx, item in enumerate(gaia_data[:max_questions]):
        print(f"\n==== 题目{idx+1}: {item['Question']}")
        obs = Observation(content=item["Question"])
        # 关键：每次都初始化上下文，防止function calling链路失效
        agent._init_context(Context())
        # 直接用llm_and_tool_execution，不用Task/Runner体系
        actions = await agent.llm_and_tool_execution(obs)
        final = actions[0].policy_info if actions else ""
        print("Agent回复:", final)
        # 提取<answer>标签内容
        import re
        match = re.search(r"<answer>(.*?)</answer>", final, re.DOTALL)
        pred = match.group(1).strip() if match else final.strip()
        gt = item["Final answer"].strip()
        if pred == gt:
            correct += 1
            print("✅ 正确")
        else:
            print(f"❌ 错误，标准答案: {gt}")
    print(f"\n总共{max_questions}题，正确{correct}，准确率: {correct/max_questions*100:.1f}%")

if __name__ == "__main__":
    asyncio.run(main(10))  # 可调整题目数量 