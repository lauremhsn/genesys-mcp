"""Confirms nonzero Genesys point costs exist and are queryable in volume."""

import asyncio
from collections import Counter

from genesys_mcp.ygo_client import YgoClient


def points(card):
    misc = card.get("misc_info") or [{}]
    return misc[0].get("genesys_points")


async def main():
    client = YgoClient()

    one = await client.cards(name="Abyss Dweller", format="genesys", misc="yes")
    print(f"Abyss Dweller: {points(one[0])} points (Konami's table lists 100)")

    staples = await client.cards(staple="yes", format="genesys", misc="yes")
    costed = [c for c in staples if (points(c) or 0) > 0]
    print(f"\nstaples in genesys: {len(staples)} | nonzero points: {len(costed)}")

    dist = Counter(points(c) for c in staples)
    print("point distribution:", dict(sorted(dist.items(), key=lambda kv: -(kv[0] or 0))))

    print("\ntop costed staples:")
    for c in sorted(costed, key=lambda c: points(c), reverse=True)[:10]:
        print(f"  {points(c):>4}  {c['name']}")


if __name__ == "__main__":
    asyncio.run(main())
