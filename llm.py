"""LLM client (GIVEN). Same OpenRouter setup as your other projects."""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

llm = ChatOpenAI(
    model=os.getenv("LLM_MODEL", "openai/gpt-6-luna"),
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    temperature=0,
)