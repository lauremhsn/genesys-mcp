"""Verifies the client works and answers whether genesys_points needs misc=yes."""

import asyncio

from genesys_mcp.ygo_client import YgoClient, YgoApiError


async def main():
    client = YgoClient()

    for params in (
        {"archetype": "Blue-Eyes", "format": "genesys"},
        {"archetype": "Blue-Eyes", "format": "genesys", "misc": "yes"},
    ):
        cards = await client.cards(**params)
        scored = [c for c in cards if "genesys_points" in c]
        print(f"\n{params}")
        print(f"  cards: {len(cards)} | with genesys_points: {len(scored)}")
        if scored:
            top = sorted(scored, key=lambda c: int(c["genesys_points"]), reverse=True)[:3]
            for c in top:
                print(f"    {c['genesys_points']:>4}  {c['name']}")
        else:
            print(f"  keys on first card: {sorted(cards[0].keys())}")

    print("\n--- failure case ---")
    try:
        await client.cards(archetype="Not A Real Archetype", format="genesys")
    except YgoApiError as e:
        print(f"  YgoApiError: {e.api_message}")
    except Exception as e:
        print(f"  {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())