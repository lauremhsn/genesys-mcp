"""Round-trips a real solver deck through storage, then checks each rejection."""

import asyncio
from pathlib import Path

from genesys_mcp.cards import CardSource
from genesys_mcp.solver import build_deck
from genesys_mcp.store import DeckStore, DeckValidationError, DeckExistsError

TEST_DB = Path("test_decks.db")


async def main():
    if TEST_DB.exists():
        TEST_DB.unlink()
    store = DeckStore(TEST_DB)

    src = CardSource()
    pool = await src.by_archetype("Dark Magician") + await src.staples()
    deck = build_deck(pool, archetype="Dark Magician", point_cap=100)
    d = deck.to_dict()

    print("=== save ===")
    print(" ", store.save("timaeus-test", d["main_deck"], d["extra_deck"],
                          point_cap=100, archetype="Dark Magician"))

    print("\n=== duplicate name ===")
    try:
        store.save("timaeus-test", d["main_deck"], d["extra_deck"], point_cap=100)
    except DeckExistsError as e:
        print(f"  DeckExistsError: {e}")

    print("\n=== overwrite ===")
    print(" ", store.save("timaeus-test", d["main_deck"], d["extra_deck"],
                          point_cap=100, archetype="Dark Magician", overwrite=True))

    print("\n=== load round-trip ===")
    loaded = store.load("timaeus-test")
    main_n = sum(c["copies"] for c in loaded["main_deck"])
    extra_n = sum(c["copies"] for c in loaded["extra_deck"])
    print(f"  main {main_n} | extra {extra_n} | points {loaded['points_spent']}")
    print(f"  matches solver: {main_n == d['main_size'] and loaded['points_spent'] == d['points_spent']}")

    print("\n=== rejections ===")
    cases = {
        "too few main cards": (d["main_deck"][:3], d["extra_deck"], 100),
        "over point cap": (d["main_deck"], d["extra_deck"], 50),
        "four copies": (
            [{"name": "Dark Magician", "copies": 3, "points_each": 0},
             {"name": "Dark Magician", "copies": 1, "points_each": 0}]
            + [{"name": f"Filler {i}", "copies": 3, "points_each": 0} for i in range(12)],
            [], 100,
        ),
    }
    for label, (main, extra, cap) in cases.items():
        try:
            store.validate(main, extra, cap)
            print(f"  {label}: NOT CAUGHT")
        except DeckValidationError as e:
            print(f"  {label}: {e.violations}")

    print("\n=== list ===")
    for row in store.list_decks():
        print(" ", row)

    print("\n=== delete ===")
    print("  deleted:", store.delete("timaeus-test"))
    print("  remaining:", store.list_decks())
    TEST_DB.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
