"""Normalizes YGOPRODeck responses into the shape the solver works with."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ygo_client import YgoClient

EXTRA_DECK_TYPES = {
    "Fusion Monster",
    "Link Monster",
    "Pendulum Effect Fusion Monster",
    "Synchro Monster",
    "Synchro Pendulum Effect Monster",
    "Synchro Tuner Monster",
    "XYZ Monster",
    "XYZ Pendulum Effect Monster",
}

# Genesys bans these outright, regardless of point cost.
ILLEGAL_FRAMES = {"link", "normal_pendulum", "effect_pendulum", "ritual_pendulum",
                  "fusion_pendulum", "synchro_pendulum", "xyz_pendulum"}


@dataclass
class Card:
    id: int
    name: str
    type: str
    frame_type: str
    race: str
    points: int
    views: int = 0
    attribute: str | None = None
    level: int | None = None
    atk: int | None = None
    desc: str = ""
    archetype: str | None = None

    @property
    def is_extra_deck(self) -> bool:
        return self.type in EXTRA_DECK_TYPES

    @property
    def is_monster(self) -> bool:
        return "Monster" in self.type

    @property
    def is_spell(self) -> bool:
        return self.type == "Spell Card"

    @property
    def is_trap(self) -> bool:
        return self.type == "Trap Card"

    @property
    def is_genesys_legal(self) -> bool:
        return self.frame_type not in ILLEGAL_FRAMES

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "points": self.points,
            "deck": "extra" if self.is_extra_deck else "main",
        }


def parse_card(raw: dict[str, Any]) -> Card:
    misc = raw.get("misc_info") or [{}]
    return Card(
        id=raw["id"],
        name=raw["name"],
        type=raw.get("type", ""),
        frame_type=raw.get("frameType", ""),
        race=raw.get("race", ""),
        points=int(misc[0].get("genesys_points") or 0),
        views=int(misc[0].get("views") or 0),
        attribute=raw.get("attribute"),
        level=raw.get("level"),
        atk=raw.get("atk"),
        desc=raw.get("desc", ""),
        archetype=raw.get("archetype"),
    )


@dataclass
class CardPool:
    archetype: list[Card] = field(default_factory=list)
    staples: list[Card] = field(default_factory=list)

    @property
    def all(self) -> list[Card]:
        seen = {c.id: c for c in self.archetype}
        for c in self.staples:
            seen.setdefault(c.id, c)
        return list(seen.values())


class CardSource:
    """The data tool's backing logic: fetch and normalize, nothing more."""

    def __init__(self, client: YgoClient | None = None):
        self._client = client or YgoClient()

    async def by_archetype(self, archetype: str) -> list[Card]:
        raw = await self._client.cards(
            archetype=archetype, format="genesys", misc="yes"
        )
        return [parse_card(r) for r in raw]

    async def staples(self) -> list[Card]:
        raw = await self._client.cards(staple="yes", format="genesys", misc="yes")
        return [parse_card(r) for r in raw]

    async def by_name(self, name: str) -> list[Card]:
        raw = await self._client.cards(name=name, format="genesys", misc="yes")
        return [parse_card(r) for r in raw]

    async def archetype_names(self) -> list[str]:
        return await self._client.archetypes()
