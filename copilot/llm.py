from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain.messages import HumanMessage
from tools.claims import check_duplicate_receipt, get_customer, get_claim_history, send_letter, issue_payment
from dotenv import load_dotenv
import os

load_dotenv()

llm = ChatOpenAI(
    model="openrouter/free",
    base_url="https://openrouter.ai/api/v1",
    temperature=0,
    api_key=os.environ.get("OPENROUTER_API_KEY"),
)

tools = [get_customer, get_claim_history]


# MCP
client = MultiServerMCPClient({
    "files": {"transport": "stdio", "command": "npx",
              "args": ["-y", "@modelcontextprotocol/server-filesystem", "./data/inbox"]},
    "time":  {"transport": "stdio", "command": "uvx", "args": ["mcp-server-time"]},
})
mcp_tools = await client.get_tools()


if __name__ == "__main__":
    agent = create_agent(
        model=llm,
        tools=tools,        
    )

    response = agent.invoke({
        "messages": [
            HumanMessage(content="please get detail of customer C-001"),
        ]
    })
    print(response)