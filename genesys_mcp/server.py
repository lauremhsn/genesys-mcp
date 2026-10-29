"""FastMCP server exposing exactly three tools: one Data, one Action, one Orchestration.

Saved-deck lookups are exposed as resources rather than tools, since they read
state without changing it and do not need to be routable actions.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .cards import CardSource
from .solver import NoLegalDeck, build_deck
from .store import DeckExistsError, DeckStore, DeckValidationError
from .ygo_client import YgoApiError

mcp = FastMCP("genesys-mcp")

_cards = CardSource()
_store = DeckStore()


def _fail(kind: str, message: str, **detail: Any) -> dict[str, Any]:
    return {"ok": False, "error": kind, "message": message, "detail": detail}


@mcp.tool
async def lookup_cards(
    archetype: str | None = None,
    card_name: str | None = None,
) -> dict[str, Any]:
    """Look up Yu-Gi-Oh! cards that are legal in the Genesys format, with their point costs.

    Genesys assigns most cards a cost of 0 and a few powerful cards a cost of up to
    100. Deck construction must stay within a point cap. This tool only reads card
    data; it never builds or saves a deck.

    Provide exactly one of:
      archetype: an archetype name, e.g. "Blue-Eyes", "Dark Magician".
      card_name: an exact card name, e.g. "Abyss Dweller".

    Returns {"ok": true, "count": int, "cards": [...]} where each card has
    name, type, points, deck ("main" or "extra") and legal (false for Link and
    Pendulum monsters, which Genesys bans).

    Returns {"ok": false, "error": ...} if neither or both arguments are given,
    or if the archetype or card name is not in the database.
    """
    if bool(archetype) == bool(card_name):
        return _fail(
            "bad_arguments",
            "Provide exactly one of archetype or card_name.",
            archetype=archetype,
            card_name=card_name,
        )

    try:
        cards = (
            await _cards.by_archetype(archetype)
            if archetype
            else await _cards.by_name(card_name)
        )
    except YgoApiError as e:
        return _fail(
            "not_found",
            e.api_message,
            query=archetype or card_name,
        )

    return {
        "ok": True,
        "count": len(cards),
        "cards": [
            {**c.to_dict(), "legal": c.is_genesys_legal}
            for c in sorted(cards, key=lambda c: (-c.points, c.name))
        ],
    }


@mcp.tool
def save_deck(
    deck_name: str,
    main_deck: list[dict[str, Any]],
    extra_deck: list[dict[str, Any]] | None = None,
    point_cap: int = 100,
    archetype: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Save a decklist to the local database after checking it against Genesys rules.

    Each entry in main_deck and extra_deck must be an object with:
      name (str), copies (int, 1-3), points_each (int).

    Validates the 40-60 card main deck, the 15-card extra deck limit, the 3-copy
    limit per card name, and the combined point cap before writing anything.

    Returns {"ok": true, "saved": name, "points_spent": int, ...} on success.

    Returns {"ok": false, "error": "invalid_deck", "detail": {"violations": [...]}}
    if any rule is broken, or {"ok": false, "error": "name_taken"} if a deck with
    that name exists and overwrite is false.
    """
    try:
        result = _store.save(
            name=deck_name,
            main=main_deck,
            extra=extra_deck or [],
            point_cap=point_cap,
            archetype=archetype,
            overwrite=overwrite,
        )
    except DeckValidationError as e:
        return _fail("invalid_deck", str(e), violations=e.violations)
    except DeckExistsError as e:
        return _fail("name_taken", str(e), deck_name=deck_name)
    except KeyError as e:
        return _fail(
            "bad_arguments",
            f"Every card entry needs name, copies and points_each; missing {e}.",
        )

    return {"ok": True, **result}


@mcp.tool
async def build_genesys_deck(
    archetype: str,
    deck_name: str,
    point_cap: int = 100,
    main_size: int = 40,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Build a legal Genesys deck around an archetype under a point cap, then save it.

    Coordinates the other two tools: looks up the archetype's cards and the format
    staples, allocates the point budget across them, and saves the finished decklist.

    Two resources are scarce at once — Genesys points and deck slots — so the costed
    cards are chosen with an exact knapsack over both. Free archetype cards claim
    half the main deck first so the result plays its own engine rather than a pile
    of generic staples.

    point_cap is the tournament's budget; 100 is standard and 0 is legal.

    Returns {"ok": true, "deck": {...}, "saved": {...}} with the full decklist,
    points spent, and what share of the main deck is archetype cards.

    Returns {"ok": false, "error": "no_legal_deck"} when the archetype cannot
    field a legal deck — for example when too many of its cards are Link or
    Pendulum monsters, which Genesys bans — with the binding constraint in detail.
    """
    try:
        pool = await _cards.by_archetype(archetype)
        pool += await _cards.staples()
    except YgoApiError as e:
        return _fail("not_found", e.api_message, archetype=archetype)

    try:
        deck = build_deck(
            pool, archetype=archetype, point_cap=point_cap, main_size=main_size
        )
    except NoLegalDeck as e:
        return _fail("no_legal_deck", str(e), **e.detail)

    payload = deck.to_dict()

    try:
        saved = _store.save(
            name=deck_name,
            main=payload["main_deck"],
            extra=payload["extra_deck"],
            point_cap=point_cap,
            archetype=archetype,
            overwrite=overwrite,
        )
    except DeckExistsError as e:
        return {
            "ok": False,
            "error": "name_taken",
            "message": str(e),
            "deck": payload,
        }
    except DeckValidationError as e:
        return _fail("invalid_deck", str(e), violations=e.violations)

    return {"ok": True, "deck": payload, "saved": saved}


@mcp.resource("genesys://archetypes")
async def archetypes() -> list[str]:
    """Every archetype name the card database recognises."""
    return await _cards.archetype_names()


@mcp.resource("decks://saved")
def saved_decks() -> list[dict[str, Any]]:
    """Summaries of every deck saved locally, newest first."""
    return _store.list_decks()


@mcp.resource("decks://saved/{deck_name}")
def saved_deck(deck_name: str) -> dict[str, Any]:
    """The full decklist for one saved deck."""
    deck = _store.load(deck_name)
    if deck is None:
        return {"error": f"No saved deck named {deck_name!r}."}
    return deck


if __name__ == "__main__":
    mcp.run()
