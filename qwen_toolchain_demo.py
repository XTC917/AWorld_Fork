import os
os.environ["CURL_CA_BUNDLE"] = ""
os.environ["PYTHONHTTPSVERIFY"] = "0"
from langchain_core.tools import tool
from langchain_community.tools.ddg_search import DuckDuckGoSearchRun
from langchain_openai import ChatOpenAI
from langchain.agents import initialize_agent, AgentType
from langchain_core.prompts import SystemMessagePromptTemplate, ChatPromptTemplate

# 1. 注册duckduckgo搜索工具
@tool
def web_search(query: str) -> str:
    """用DuckDuckGo搜索引擎查找信息，返回结果。"""
    search_docs = DuckDuckGoSearchRun().run(query)
    return search_docs

TOOLS = [web_search]

llm = ChatOpenAI(
    model="qwen-turbo",
    base_url="https://modelfactory.lenovo.com/app-workspace-172-1749106801220-vscode/v1/chat/completions",
    api_key="EMPTY",  # Qwen API如无需key可填EMPTY
    temperature=0.0
)

agent = initialize_agent(
    TOOLS,
    llm,
    agent=AgentType.OPENAI_FUNCTIONS,
    verbose=True,
)

GAIA_QUESTION = "What is the maximum length in meters of #9 in the first National Geographic short on YouTube that was ever released according to the Monterey Bay Aquarium website? Just give the number."

if __name__ == "__main__":
    print("[GAIA样例问题]", GAIA_QUESTION)
    answer = agent.run(GAIA_QUESTION)
    print("[最终答案]", answer) 