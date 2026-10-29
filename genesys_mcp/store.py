"""Local deck storage. The action tool's backing logic: writes, never fetches."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "decks.db"

MAX_COPIES = 3
MAIN_MIN, MAIN_MAX = 40, 60
EXTRA_MAX = 15

SCHEMA = """
CREATE TABLE IF NOT EXISTS decks (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    archetype   TEXT,
    point_cap   INTEGER NOT NULL,
    points_spent INTEGER NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deck_cards (
    deck_id     INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    card_id     INTEGER NOT NULL,
    name        TEXT NOT NULL,
    section     TEXT NOT NULL CHECK (section IN ('main', 'extra')),
    copies      INTEGER NOT NULL CHECK (copies BETWEEN 1 AND 3),
    points_each INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS deck_cards_deck ON deck_cards(deck_id);
"""


class DeckValidationError(ValueError):
    """The deck violates a Genesys construction rule."""

    def __init__(self, message: str, violations: list[str] | None = None):
        super().__init__(message)
        self.violations = violations or []


class DeckExistsError(ValueError):
    """A deck with this name is already stored."""


class DeckStore:
    def __init__(self, path: Path | None = None):
        self._path = path or DB_PATH
        with closing(self._connect()) as conn, conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def validate(main: list[dict], extra: list[dict], point_cap: int) -> int:
        violations: list[str] = []

        main_size = sum(r["copies"] for r in main)
        extra_size = sum(r["copies"] for r in extra)

        if not MAIN_MIN <= main_size <= MAIN_MAX:
            violations.append(
                f"main deck has {main_size} cards; Genesys requires "
                f"{MAIN_MIN}-{MAIN_MAX}"
            )
        if extra_size > EXTRA_MAX:
            violations.append(f"extra deck has {extra_size} cards; the limit is {EXTRA_MAX}")

        counts: dict[str, int] = {}
        for row in main + extra:
            counts[row["name"]] = counts.get(row["name"], 0) + row["copies"]
        for name, total in counts.items():
            if total > MAX_COPIES:
                violations.append(f"{total} copies of {name}; the limit is {MAX_COPIES}")

        spent = sum(r["points_each"] * r["copies"] for r in main + extra)
        if spent > point_cap:
            violations.append(f"deck costs {spent} points; the cap is {point_cap}")

        if violations:
            raise DeckValidationError(
                f"Deck fails {len(violations)} Genesys rule(s).", violations
            )
        return spent

    def save(
        self,
        name: str,
        main: list[dict],
        extra: list[dict],
        point_cap: int = 100,
        archetype: str | None = None,
        overwrite: bool = False,
    ) -> dict:
        spent = self.validate(main, extra, point_cap)

        with closing(self._connect()) as conn, conn:
            existing = conn.execute(
                "SELECT id FROM decks WHERE name = ?", (name,)
            ).fetchone()
            if existing and not overwrite:
                raise DeckExistsError(
                    f"A deck named {name!r} already exists. Pass overwrite=true to replace it."
                )
            if existing:
                conn.execute("DELETE FROM deck_cards WHERE deck_id = ?", (existing["id"],))
                conn.execute("DELETE FROM decks WHERE id = ?", (existing["id"],))

            cursor = conn.execute(
                "INSERT INTO decks (name, archetype, point_cap, points_spent, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (name, archetype, point_cap, spent,
                 datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
            deck_id = cursor.lastrowid
            conn.executemany(
                "INSERT INTO deck_cards (deck_id, card_id, name, section, copies, points_each)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (deck_id, row.get("card_id", 0), row["name"], section,
                     row["copies"], row["points_each"])
                    for section, rows in (("main", main), ("extra", extra))
                    for row in rows
                ],
            )

        return {
            "saved": name,
            "replaced": bool(existing),
            "main_size": sum(r["copies"] for r in main),
            "extra_size": sum(r["copies"] for r in extra),
            "points_spent": spent,
            "point_cap": point_cap,
        }

    def list_decks(self) -> list[dict]:
        with closing(self._connect()) as conn, conn:
            rows = conn.execute(
                "SELECT name, archetype, point_cap, points_spent, created_at"
                " FROM decks ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def load(self, name: str) -> dict | None:
        with closing(self._connect()) as conn, conn:
            deck = conn.execute("SELECT * FROM decks WHERE name = ?", (name,)).fetchone()
            if deck is None:
                return None
            cards = conn.execute(
                "SELECT name, section, copies, points_each FROM deck_cards"
                " WHERE deck_id = ? ORDER BY section, name",
                (deck["id"],),
            ).fetchall()

        return {
            "name": deck["name"],
            "archetype": deck["archetype"],
            "point_cap": deck["point_cap"],
            "points_spent": deck["points_spent"],
            "created_at": deck["created_at"],
            "main_deck": [dict(c) for c in cards if c["section"] == "main"],
            "extra_deck": [dict(c) for c in cards if c["section"] == "extra"],
        }

    def delete(self, name: str) -> bool:
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute("DELETE FROM decks WHERE name = ?", (name,))
        return cursor.rowcount > 0
