"""Looks inside misc_info for genesys_points, and checks a known-costed card directly."""

import asyncio
import json

from genesys_mcp.ygo_client import YgoClient, YgoApiError


async def main():
    client = YgoClient()

    cards = await client.cards(archetype="Blue-Eyes", format="genesys", misc="yes")
    print("=== misc_info on first card ===")
    print(json.dumps(cards[0].get("misc_info"), indent=2)[:1200])

    hits = [c for c in cards if any("genesys" in k for k in (c.get("misc_info") or [{}])[0])]
    print(f"\ncards whose misc_info mentions genesys: {len(hits)} / {len(cards)}")

    # Abyss Dweller is listed at 100 points on Konami's official table.
    print("\n=== Abyss Dweller, format=genesys&misc=yes ===")
    try:
        one = await client.cards(name="Abyss Dweller", format="genesys", misc="yes")
        print(json.dumps(one[0], indent=2)[:1500])
    except YgoApiError as e:
        print("  YgoApiError:", e.api_message)

    print("\n=== Abyss Dweller, misc=yes only (no format) ===")
    try:
        one = await client.cards(name="Abyss Dweller", misc="yes")
        print(json.dumps(one[0].get("misc_info"), indent=2)[:900])
    except YgoApiError as e:
        print("  YgoApiError:", e.api_message)


if __name__ == "__main__":
    asyncio.run(main())
