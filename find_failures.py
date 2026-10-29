"""Finds archetypes that genuinely cannot field an engine once Genesys bans apply."""

import asyncio

from genesys_mcp.cards import CardSource
from genesys_mcp.solver import build_deck, NoLegalDeck
from genesys_mcp.ygo_client import YgoApiError

CANDIDATES = [
    "Igknight", "Dinomist", "Majespecter", "Metalfoes", "Endymion",
    "Performapal", "Odd-Eyes", "Mathmech", "Marincess", "@Ignister",
    "Knightmare", "Mekk-Knight", "Prank-Kids", "Code Talker", "Dracoslayer",
]


async def main():
    src = CardSource()
    staples = await src.staples()

    fails, builds = [], []
    for name in CANDIDATES:
        try:
            cards = await src.by_archetype(name)
        except YgoApiError:
            print(f"  {name}: not an archetype name")
            continue

        legal_main = [c for c in cards if c.is_genesys_legal and not c.is_extra_deck]
        banned = [c for c in cards if not c.is_genesys_legal]

        try:
            deck = build_deck(list(cards) + staples, archetype=name, point_cap=100)
            share = deck.archetype_share()
            builds.append((name, len(cards), len(banned), share))
        except NoLegalDeck as e:
            fails.append((name, len(cards), len(banned), len(legal_main), str(e)))

    print("\n=== FAILS (usable as the demo failure case) ===")
    for name, total, banned, legal, msg in fails:
        print(f"\n  {name}: {total} cards, {banned} banned, {legal} legal main")
        print(f"    {msg}")

    print("\n=== BUILDS ===")
    for name, total, banned, share in builds:
        print(f"  {name}: {total} cards, {banned} banned -> archetype share {share:.0%}")


if __name__ == "__main__":
    asyncio.run(main())
