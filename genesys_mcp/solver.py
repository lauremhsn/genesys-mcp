"""Genesys deck construction under a hard point budget.

Two resources are scarce: Genesys points and deck slots. Free archetype cards
claim slots first (they cost no points), then a 2D knapsack allocates the
remaining slots and the whole point budget across the costed pool. Main and
extra deck are solved separately because their slot limits differ, but they
share one budget — Genesys counts Main, Extra and Side together.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .cards import Card

MAX_COPIES = 3
MAIN_MIN, MAIN_MAX = 40, 60
EXTRA_MAX = 15
ARCHETYPE_FLOOR = 0.5


class NoLegalDeck(Exception):
    """No deck satisfying the format and the budget could be built."""

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message)
        self.detail = detail or {}


@dataclass
class DeckResult:
    main: dict[int, int] = field(default_factory=dict)
    extra: dict[int, int] = field(default_factory=dict)
    cards_by_id: dict[int, Card] = field(default_factory=dict)
    points_spent: int = 0
    point_cap: int = 100
    archetype: str | None = None

    @property
    def main_size(self) -> int:
        return sum(self.main.values())

    @property
    def extra_size(self) -> int:
        return sum(self.extra.values())

    def entries(self, section: str) -> list[dict]:
        source = self.main if section == "main" else self.extra
        rows = []
        for card_id, copies in source.items():
            card = self.cards_by_id[card_id]
            rows.append({
                "name": card.name,
                "copies": copies,
                "type": card.type,
                "points_each": card.points,
                "points_total": card.points * copies,
                "archetype": card.archetype == self.archetype,
            })
        rows.sort(key=lambda r: (-r["points_total"], r["name"]))
        return rows

    def archetype_share(self) -> float:
        rows = self.entries("main")
        total = sum(r["copies"] for r in rows)
        if not total:
            return 0.0
        return sum(r["copies"] for r in rows if r["archetype"]) / total

    def to_dict(self) -> dict:
        return {
            "main_deck": self.entries("main"),
            "extra_deck": self.entries("extra"),
            "main_size": self.main_size,
            "extra_size": self.extra_size,
            "points_spent": self.points_spent,
            "point_cap": self.point_cap,
            "points_remaining": self.point_cap - self.points_spent,
            "archetype_share": round(self.archetype_share(), 3),
        }


def score(card: Card, archetype: str | None) -> float:
    """Popularity as a playability proxy, weighted toward archetype identity."""
    base = math.log10(max(card.views, 1) + 1)
    if archetype and card.archetype == archetype:
        base *= 2.0
    return base


def _expand(cards: list[Card], archetype: str | None, budget: int) -> list[tuple[Card, float]]:
    """One item per allowed copy, with later copies worth less."""
    items: list[tuple[Card, float]] = []
    for card in cards:
        if card.points <= 0 or card.points > budget:
            continue
        value = score(card, archetype)
        for copy_index in range(MAX_COPIES):
            items.append((card, value / (copy_index + 1)))
    return items


def _knapsack(items: list[tuple[Card, float]], slot_cap: int, point_cap: int) -> list[Card]:
    """Exact 0/1 knapsack over two constraints: one slot and N points per item."""
    n = len(items)
    if n == 0 or slot_cap <= 0 or point_cap <= 0:
        return []

    width = point_cap + 1
    prev = [[0.0] * width for _ in range(slot_cap + 1)]
    table = [prev]

    for card, value in items:
        cost = card.points
        cur = [row[:] for row in prev]
        for s in range(1, slot_cap + 1):
            prev_s = prev[s - 1]
            cur_s = cur[s]
            for b in range(cost, width):
                cand = prev_s[b - cost] + value
                if cand > cur_s[b]:
                    cur_s[b] = cand
        table.append(cur)
        prev = cur

    chosen: list[Card] = []
    s, b = slot_cap, point_cap
    for i in range(n, 0, -1):
        if table[i][s][b] != table[i - 1][s][b]:
            card, _ = items[i - 1]
            chosen.append(card)
            s -= 1
            b -= card.points
    return chosen


def build_deck(
    pool: list[Card],
    archetype: str | None = None,
    point_cap: int = 100,
    main_size: int = 40,
) -> DeckResult:
    legal = [c for c in pool if c.is_genesys_legal]
    if not legal:
        raise NoLegalDeck(
            "Every card in this pool is a Link or Pendulum monster, which Genesys "
            "does not allow.",
            {"pool_size": len(pool)},
        )

    main_pool = [c for c in legal if not c.is_extra_deck]
    extra_pool = [c for c in legal if c.is_extra_deck]

    ceiling = len(main_pool) * MAX_COPIES
    if ceiling < main_size:
        raise NoLegalDeck(
            f"Only {len(main_pool)} legal main-deck cards are available, which caps "
            f"the deck at {ceiling} cards with {MAX_COPIES} copies each — short of "
            f"the {main_size}-card minimum.",
            {
                "legal_main_cards": len(main_pool),
                "max_reachable": ceiling,
                "required": main_size,
                "removed_as_illegal": len(pool) - len(legal),
            },
        )

    main: dict[int, int] = {}
    extra: dict[int, int] = {}
    by_id: dict[int, Card] = {}
    spent = 0

    def by_score(cards):
        return sorted(cards, key=lambda c: score(c, archetype), reverse=True)

    def fill(target, candidates, limit, per_card=MAX_COPIES):
        for card in candidates:
            while sum(target.values()) < limit and target.get(card.id, 0) < per_card:
                target[card.id] = target.get(card.id, 0) + 1
                by_id[card.id] = card
            if sum(target.values()) >= limit:
                return

    def take(target, cards, limit):
        nonlocal spent
        for card in cards:
            if sum(target.values()) >= limit:
                break
            if target.get(card.id, 0) >= MAX_COPIES:
                continue
            target[card.id] = target.get(card.id, 0) + 1
            by_id[card.id] = card
            spent += card.points

    free_engine = by_score(
        c for c in main_pool if c.points == 0 and c.archetype == archetype
    )
    fill(main, free_engine, int(main_size * ARCHETYPE_FLOOR))

    main_costed = _knapsack(
        _expand(main_pool, archetype, point_cap),
        slot_cap=main_size - sum(main.values()),
        point_cap=point_cap,
    )
    take(main, main_costed, main_size)

    extra_costed = _knapsack(
        _expand(extra_pool, archetype, point_cap - spent),
        slot_cap=EXTRA_MAX,
        point_cap=point_cap - spent,
    )
    take(extra, extra_costed, EXTRA_MAX)

    fill(main, by_score(c for c in main_pool if c.points == 0), main_size)

    if sum(main.values()) < main_size:
        raise NoLegalDeck(
            f"Could only assemble {sum(main.values())} main-deck cards; "
            f"{main_size} are required.",
            {"assembled": sum(main.values()), "required": main_size},
        )

    fill(extra, by_score(c for c in extra_pool if c.points == 0), EXTRA_MAX, per_card=1)

    return DeckResult(
        main=main,
        extra=extra,
        cards_by_id=by_id,
        points_spent=spent,
        point_cap=point_cap,
        archetype=archetype,
    )
