from aworld.config.conf import AgentConfig, ClientType
from aworld.agents.llm_agent import Agent
from aworld.core.common import Observation
from aworld.core.context.base import Context

# Qwen3 配置
QWEN3_API_URL = "https://modelfactory.lenovo.com/app-workspace-172-1748942586592-vscode/v1"
QWEN3_MODEL = "/dfs/data/aisz/panhui9/cache_dir/mogao/Qwen3-235B-A22B-FP8"

# 构建 AgentConfig
agent_config = AgentConfig(
    llm_provider="openai",  # 兼容OpenAI协议
    llm_model_name=QWEN3_MODEL,
    llm_base_url=QWEN3_API_URL,
    llm_client_type=ClientType.HTTP,  # 强制用HTTP
    llm_temperature=0.6,
    max_tokens=1000,
    llm_api_key="",  # 如果不需要认证就留空
)

# 构建 Agent
agent = Agent(
    conf=agent_config,
    name="qwen3_agent",
    system_prompt="你是一个有用的AI助手。",
    agent_prompt="请用中文简明扼要地回答用户问题。",
)

# 手动初始化 context，防止 agent_context 为 None
context = Context()
agent._init_context(context)

def main():
    import sys
    if len(sys.argv) > 1:
        question = sys.argv[1]
    else:
        question = "量子纠缠如何解释？"
    obs = Observation(content=question)
    actions = agent.policy(obs)
    for action in actions:
        print("Qwen3 Agent 回复：", action.policy_info)

if __name__ == "__main__":
    main() 