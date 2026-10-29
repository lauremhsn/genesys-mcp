"""Dumps a full decklist, marking which cards belong to the archetype."""

import asyncio
import sys

from genesys_mcp.cards import CardSource
from genesys_mcp.solver import build_deck


async def main():
    archetype = sys.argv[1] if len(sys.argv) > 1 else "Dark Magician"
    src = CardSource()
    pool = await src.by_archetype(archetype) + await src.staples()
    deck = build_deck(pool, archetype=archetype, point_cap=100)

    for section in ("main", "extra"):
        rows = deck.entries(section)
        owned = 0
        print(f"\n=== {section} deck ({sum(r['copies'] for r in rows)} cards) ===")
        for r in sorted(rows, key=lambda r: r["name"]):
            card = next(c for c in deck.cards_by_id.values() if c.name == r["name"])
            tag = "ARCH" if card.archetype == archetype else "    "
            owned += r["copies"] if card.archetype == archetype else 0
            pts = f"{r['points_total']:>3}p" if r["points_total"] else "   -"
            print(f"  {tag} {pts}  {r['copies']}x {r['name']}")
        total = sum(r["copies"] for r in rows)
        if total:
            print(f"  -> archetype cards: {owned}/{total} ({owned / total:.0%})")


if __name__ == "__main__":
    asyncio.run(main())
