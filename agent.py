"""MCP host/client: an OpenAI Agents SDK agent wired to the genesys-mcp server.

Uses Gemini through its OpenAI-compatible endpoint, so no OpenAI billing is needed.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
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

Genesys rules and this toolkit's build policies are different things. The point
cap, the 3-copy limit, the 40-card minimum and the Link/Pendulum ban are format
rules. Reserving half the main deck for the archetype is this tool's own choice.
Never describe a tool policy as a Genesys rule.
"""

def _summarize(result) -> str:
    blocks = [c.text for c in getattr(result, "content", []) if hasattr(c, "text")]
    if not blocks:
        return "<- (no text content)"
    try:
        payload = json.loads(blocks[0])
    except (json.JSONDecodeError, TypeError):
        return "<- " + blocks[0][:160]

    if not isinstance(payload, dict):
        return "<- " + json.dumps(payload)[:160]
    if payload.get("ok") is False:
        return f"<- ok=false  {payload.get('error')}: {payload.get('message', '')[:240]}"
    if "deck" in payload:
        d = payload["deck"]
        return (f"<- ok=true  main={d['main_size']} extra={d['extra_size']} "
                f"points={d['points_spent']}/{d['point_cap']} "
                f"archetype={d['archetype_share']:.0%}")
    if "count" in payload:
        return f"<- ok=true  {payload['count']} cards"
    return "<- ok=true  " + json.dumps(payload)[:160]


class TracingMCPServer(MCPServerStdio):
    """Prints every call that crosses the MCP client/server boundary."""

    async def call_tool(self, tool_name, arguments=None, meta=None):
        print(f"\n  -> {tool_name}")
        for key, value in (arguments or {}).items():
            print(f"       {key} = {repr(value)[:120]}")
        start = time.monotonic()
        result = await super().call_tool(tool_name, arguments, meta)
        print(f"     {_summarize(result)}  [{time.monotonic() - start:.1f}s]\n")
        return result

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

    args = [a for a in sys.argv[1:] if a != "--trace"]
    server_cls = TracingMCPServer if "--trace" in sys.argv else MCPServerStdio

    model = build_model()

    async with server_cls(
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

        if args:
            result = await Runner.run(agent, " ".join(args), max_turns=12)
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
