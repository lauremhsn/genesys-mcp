"""Checks normalization, and whether format=genesys already excludes Link/Pendulum."""

import asyncio
from collections import Counter

from genesys_mcp.cards import CardSource


async def main():
    src = CardSource()

    for name in ("Blue-Eyes", "Dark Magician", "Prank-Kids"):
        cards = await src.by_archetype(name)
        main = [c for c in cards if not c.is_extra_deck]
        extra = [c for c in cards if c.is_extra_deck]
        illegal = [c for c in cards if not c.is_genesys_legal]
        costed = [c for c in cards if c.points > 0]
        print(f"\n{name}: {len(cards)} cards | main {len(main)} | extra {len(extra)}")
        print(f"  frame types: {dict(Counter(c.frame_type for c in cards))}")
        print(f"  flagged illegal by our filter: {len(illegal)}")
        if illegal:
            for c in illegal[:5]:
                print(f"    {c.frame_type:<18} {c.name}")
        print(f"  costed: {len(costed)} | total if 1 copy each: {sum(c.points for c in costed)}")
        for c in sorted(costed, key=lambda c: -c.points)[:5]:
            print(f"    {c.points:>4}  {c.name}")

    print("\n=== does format=genesys already exclude Links? ===")
    links = await src.by_name("Decode Talker")
    print(f"  Decode Talker (Link) under format=genesys: {len(links)} results")


if __name__ == "__main__":
    asyncio.run(main())
