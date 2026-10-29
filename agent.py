"""MCP host/client: an OpenAI Agents SDK agent wired to the genesys-mcp server.

Uses Gemini through its OpenAI-compatible endpoint, so no OpenAI billing is needed.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from agents import Agent, OpenAIChatCompletionsModel, Runner, set_tracing_disabled
from agents.mcp import MCPServerStdio
from dotenv import load_dotenv
from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parent
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

INSTRUCTIONS = """\
You help a Yu-Gi-Oh! player build decks for the Genesys format.

Genesys rules that matter: Link and Pendulum monsters are banned entirely, there
is no Forbidden & Limited list, up to 3 copies of a card are allowed, and every
card has a point cost from 0 to 100. The combined cost of the Main, Extra and
Side Deck cannot exceed the event's point cap, which is normally 100.

You have three tools:
- lookup_cards reads card data. It takes an archetype OR a card name, never both.
- build_genesys_deck builds a complete legal deck around an archetype and saves it.
- save_deck stores a decklist you assembled yourself.

Prefer build_genesys_deck when the user wants a deck. Use lookup_cards when they
ask about specific cards or point costs.

Every tool returns an object with an "ok" field. When ok is false, read the
"message" and "detail" and explain the problem to the user in plain language.
Do not retry a failed call with the same arguments. If a deck name is taken,
ask the user whether to overwrite it or pick another name.

Report point totals exactly as the tools return them. Never estimate a cost.
"""


def build_model() -> OpenAIChatCompletionsModel:
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY is not set. Put it in .env next to this file.")

    client = AsyncOpenAI(api_key=api_key, base_url=GEMINI_BASE_URL)
    return OpenAIChatCompletionsModel(
        model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash"),
        openai_client=client,
    )


async def main() -> None:
    # The SDK uploads traces to OpenAI by default, which fails without an OpenAI key.
    set_tracing_disabled(True)

    model = build_model()

    async with MCPServerStdio(
        params={
            "command": sys.executable,
            "args": ["-m", "genesys_mcp.server"],
            "cwd": str(ROOT),
        },
        cache_tools_list=True,
        client_session_timeout_seconds=120,
        name="genesys-mcp",
    ) as server:
        tools = await server.list_tools()
        print(f"Connected to genesys-mcp. Tools: {', '.join(t.name for t in tools)}\n")

        agent = Agent(
            name="Genesys Deck Builder",
            instructions=INSTRUCTIONS,
            mcp_servers=[server],
            model=model,
        )

        if len(sys.argv) > 1:
            result = await Runner.run(agent, " ".join(sys.argv[1:]), max_turns=12)
            print(result.final_output)
            return

        history: list = []
        print("Ask for a deck, or Ctrl+C to quit.\n")
        while True:
            try:
                prompt = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not prompt:
                continue

            result = await Runner.run(agent, history + [{"role": "user", "content": prompt}], max_turns=12)
            print(f"\n{result.final_output}\n")
            history = result.to_input_list()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
