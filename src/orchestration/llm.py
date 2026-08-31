"""Per-agent model selection through OpenRouter (docs/architecture.md §3.11:
cheap model for classification/routing, stronger model only where reasoning
is genuinely needed). One API key, multiple providers/models — this is what
lets different agents in the graph use different models without managing
separate provider credentials.
"""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Cheap/fast tier: intent classification, structured extraction — high
# volume, low-stakes judgment calls.
CHEAP_MODEL = "anthropic/claude-haiku-4.5"

# Stronger tier: risk narrative, draft response generation — lower volume,
# needs better judgment/writing quality.
STRONG_MODEL = "anthropic/claude-sonnet-5"


def get_llm(tier: str = "cheap", temperature: float = 0.0, max_tokens: int = 1024) -> ChatOpenAI:
    # Explicit cap: without one, ChatOpenAI requests the model's full context
    # ceiling (65536) on every call, which OpenRouter reserves against account
    # balance up front regardless of actual usage — every call in this graph
    # only ever needs a short JSON field or a <80-word draft, so 1024 is
    # generous headroom, not a real limit on anything this system does.
    model = CHEAP_MODEL if tier == "cheap" else STRONG_MODEL
    return ChatOpenAI(
        model=model,
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def demo() -> None:
    llm = get_llm("cheap")
    response = llm.invoke("Reply with exactly one word: 'ok'")
    assert "ok" in response.content.lower(), response.content
    print(f"llm.demo(): {CHEAP_MODEL} via OpenRouter responded: {response.content!r}")


if __name__ == "__main__":
    demo()
