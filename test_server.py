"""Calls all three MCP tools in-process, success and failure paths."""

import asyncio
import json
from pathlib import Path

import genesys_mcp.server as srv
from genesys_mcp.store import DeckStore


def show(label, result):
    print(f"\n--- {label} ---")
    if isinstance(result, dict) and not result.get("ok", True):
        print(f"  error: {result['error']}")
        print(f"  message: {result['message']}")
        if result.get("detail"):
            print(f"  detail: {json.dumps(result['detail'])[:300]}")
    else:
        print(f"  {json.dumps(result, default=str)[:400]}")


async def main():
    test_db = Path("test_server.db")
    test_db.unlink(missing_ok=True)
    srv._store = DeckStore(test_db)

    print("=== DATA TOOL: lookup_cards ===")
    show("archetype", await srv.lookup_cards(archetype="Blue-Eyes"))
    show("single card", await srv.lookup_cards(card_name="Abyss Dweller"))
    show("FAIL unknown archetype", await srv.lookup_cards(archetype="Nonexistent Deck"))
    show("FAIL both args", await srv.lookup_cards(archetype="Blue-Eyes", card_name="Raigeki"))
    show("FAIL neither arg", await srv.lookup_cards())

    print("\n=== ORCHESTRATION TOOL: build_genesys_deck ===")
    built = await srv.build_genesys_deck(archetype="Dark Magician", deck_name="dm-100")
    if built["ok"]:
        d = built["deck"]
        print(f"  main {d['main_size']} | extra {d['extra_size']} | "
              f"points {d['points_spent']}/{d['point_cap']} | "
              f"archetype share {d['archetype_share']:.0%}")
        print(f"  saved: {built['saved']}")
    else:
        show("build failed", built)

    show("FAIL duplicate name", await srv.build_genesys_deck(
        archetype="Dark Magician", deck_name="dm-100"))
    show("FAIL no legal deck", await srv.build_genesys_deck(
        archetype="Knightmare", deck_name="km"))
    show("FAIL unknown archetype", await srv.build_genesys_deck(
        archetype="Nonexistent Deck", deck_name="x"))

    print("\n=== ACTION TOOL: save_deck ===")
    tiny = [{"name": f"Card {i}", "copies": 3, "points_each": 0} for i in range(14)]
    show("valid 42-card deck", srv.save_deck(deck_name="handmade", main_deck=tiny))
    show("FAIL too small", srv.save_deck(deck_name="stub", main_deck=tiny[:2]))
    show("FAIL over cap", srv.save_deck(
        deck_name="pricey",
        main_deck=tiny[:13] + [{"name": "Imperial Order", "copies": 3, "points_each": 100}],
    ))
    show("FAIL malformed entry", srv.save_deck(
        deck_name="broken", main_deck=[{"name": "No copies field"}]))

    print("\n=== RESOURCES ===")
    print("  saved decks:", [d["name"] for d in srv.saved_decks()])
    loaded = srv.saved_deck(deck_name="dm-100")
    print(f"  dm-100 main entries: {len(loaded.get('main_deck', []))}")
    print("  missing deck:", srv.saved_deck(deck_name="nope"))

    test_db.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
