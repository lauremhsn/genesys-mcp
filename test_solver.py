"""Exercises the knapsack against real pools, including the Pendulum gap check."""

import asyncio

from genesys_mcp.cards import CardSource
from genesys_mcp.solver import build_deck, NoLegalDeck


async def try_build(src, archetype, cap=100, with_staples=True):
    cards = await src.by_archetype(archetype)
    pool = list(cards)
    if with_staples:
        pool += await src.staples()

    print(f"\n=== {archetype} @ {cap} points ===")
    try:
        deck = build_deck(pool, archetype=archetype, point_cap=cap)
    except NoLegalDeck as e:
        print(f"  NoLegalDeck: {e}")
        print(f"  detail: {e.detail}")
        return

    d = deck.to_dict()
    print(f"  main {d['main_size']} | extra {d['extra_size']} | "
          f"points {d['points_spent']}/{d['point_cap']}")
    print("  costed cards picked:")
    for row in d["main_deck"] + d["extra_deck"]:
        if row["points_total"] > 0:
            print(f"    {row['points_total']:>4}  {row['copies']}x {row['name']}")
    if d["points_spent"] > d["point_cap"]:
        print("  !! OVER BUDGET — knapsack is wrong")


async def main():
    src = CardSource()

    await try_build(src, "Dark Magician")
    await try_build(src, "Dark Magician", cap=40)
    await try_build(src, "Dark Magician", cap=0)
    await try_build(src, "Blue-Eyes")
    await try_build(src, "Prank-Kids", with_staples=False)

    print("\n=== Pendulum leak check ===")
    for name in ("Odd-Eyes Pendulum Dragon", "Performapal Pendulum Sorcerer"):
        found = await src.by_name(name)
        if not found:
            print(f"  {name}: excluded by format=genesys")
        else:
            c = found[0]
            print(f"  {name}: returned | frame={c.frame_type} | "
                  f"our filter flags illegal: {not c.is_genesys_legal}")


if __name__ == "__main__":
    asyncio.run(main())
