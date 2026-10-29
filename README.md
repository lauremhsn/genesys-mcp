# genesys-mcp

An MCP toolkit for building Yu-Gi-Oh! decks in the **Genesys** format, built with
FastMCP and connected to an agent through the OpenAI Agents SDK.

Genesys is Konami's alternate format. Link and Pendulum monsters are banned, the
Forbidden & Limited list is not used, and every card carries a point cost from 0
to 100. The combined cost of the Main, Extra and Side Deck cannot exceed the
event's point cap, which is normally 100. Most cards cost nothing, so the budget
creates sharp either/or decisions: six staples cost the entire 100 on their own.

That constraint is what the toolkit solves.

## The three tools

| Category | Tool | What it does |
|---|---|---|
| **Data** | `lookup_cards` | Reads Genesys-legal cards and their point costs. Changes nothing. |
| **Action** | `save_deck` | Validates a decklist against Genesys rules and writes it to SQLite. |
| **Orchestration** | `build_genesys_deck` | Looks up an archetype and the format staples, allocates the point budget across them, and saves the result. |

Saved-deck reads are exposed as **resources** rather than tools, since they read
state without changing it:

- `genesys://archetypes` — every archetype name in the database
- `decks://saved` — summaries of locally saved decks
- `decks://saved/{deck_name}` — one full decklist

### `lookup_cards(archetype=None, card_name=None)`

Takes an archetype **or** an exact card name, never both — passing both or
neither is an error rather than a silent fallback. Returns each card's name,
type, point cost, whether it belongs in the main or extra deck, and whether
Genesys allows it at all.

### `save_deck(deck_name, main_deck, extra_deck=None, point_cap=100, archetype=None, overwrite=False)`

Checks the 40–60 card main deck, the 15-card extra deck limit, the 3-copy limit
per card name, and the combined point cap *before* writing anything. Refuses to
overwrite an existing deck name unless `overwrite=True`.

Validation lives here rather than only in the solver on purpose: an agent can
call this tool with a hand-assembled decklist that never went through the
solver, and that path still has to be safe.

### `build_genesys_deck(archetype, deck_name, point_cap=100, main_size=40, overwrite=False)`

The orchestration tool. Calls the data layer for the archetype and for the
format staples, solves the budget allocation, then calls the action layer to
persist the result.

## How the solver works

Two resources are scarce at once, and that turned out to be the whole problem.

**Points.** Most cards cost 0, a few cost up to 100, and the deck must stay
under the cap.

**Deck slots.** The main deck is exactly 40 cards (up to 60), the extra deck at
most 15.

A one-dimensional model over points alone produces a technically legal deck that
no one would play: cheap staples have excellent value *per point* and terrible
value *per slot*, so the optimizer buys 31 copies of cheap generic cards and the
archetype disappears entirely. The first working version of this solver built a
"Dark Magician deck" containing zero Dark Magician cards.

The current approach:

1. **Free archetype cards claim slots first.** They cost no points, so reserving
   half the main deck for them carries no budget risk, and it guarantees the
   deck actually plays its own engine.
2. **An exact 0/1 knapsack over both constraints** allocates the remaining slots
   and the whole point budget. Each allowed copy of a card is a separate item,
   with later copies worth less so the solver doesn't spend everything on three
   copies of one card. Archetype cards stay in this pool with a 2× score weight,
   so they compete on merit rather than being structurally excluded.
3. **Main and extra deck are solved separately** but share one budget, since
   Genesys counts Main, Extra and Side together.

Card quality is scored by view count from the card database as a popularity
proxy. This measures what people look up, not what is strong — an honest
limitation. The alternative, using Konami's point costs as the value signal,
is circular: maximizing points under a point budget is degenerate.

The DP table is roughly `items × slots × points`, about 126 × 21 × 101 cells.
Exact rather than greedy, because at this size approximation buys nothing.

## Failure cases

Each tool fails predictably with an explanation rather than a silent fallback.
Every tool returns an object with an `ok` field; on failure it carries `error`,
`message` and `detail`.

| Tool | Failure | Example |
|---|---|---|
| `lookup_cards` | Unknown archetype or card name | The card database's own 400 response is passed through |
| `lookup_cards` | Both or neither argument given | `Provide exactly one of archetype or card_name.` |
| `save_deck` | Any Genesys rule broken | `main deck has 6 cards; Genesys requires 40-60` |
| `save_deck` | Deck name already used | Suggests `overwrite` |
| `build_genesys_deck` | Archetype cannot field an engine | See below |

The interesting one:

```
Knightmare has only 3 legal main-deck cards, filling at most 9 of the 20 slots
reserved for the archetype's own engine (9 of its cards are Link or Pendulum
monsters, which Genesys bans). The rest would be generic staples, not a
Knightmare deck.
```

Archetypes that currently trigger this: **Knightmare**, **Dracoslayer**,
**Dinomist**, **Igknight**, **Metalfoes**.

Errors are returned as structured values rather than raised, because FastMCP
masks exception details by default — which would reduce the message above to a
generic internal error, exactly the silent failure to avoid.

## Setup

Windows / PowerShell, from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If `Activate.ps1` is blocked by execution policy, run
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` once in that window.

Create a `.env` file in the repository root:

```
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.5-flash
```

`.env` is gitignored.

### Why Gemini

The assignment requires the OpenAI Agents SDK, which is the agent *framework* —
it does not require OpenAI's models. OpenAI no longer grants free credits to new
API accounts, so this project points the SDK at Gemini through its
OpenAI-compatible endpoint. The whole project runs at no cost.

The SDK's `litellm` extra is not usable here: it only exists up to
`openai-agents` 0.2.8, which pins `openai<2`, while current `openai-agents`
requires `openai>=3`. Using Gemini's compatibility endpoint directly avoids the
conflict and removes an adapter from the chain.

`set_tracing_disabled(True)` is the first line of the agent. Without it the SDK
tries to upload traces to OpenAI and throws auth errors that look like real
failures.

## Running it

Interactive agent:

```powershell
python agent.py
```

One-shot:

```powershell
python agent.py "Build me a Dark Magician deck for a 100 point event and call it dm-demo"
python agent.py "Build me a Knightmare deck, call it km-test"
python agent.py "What does Abyss Dweller cost in Genesys?"
```

The MCP server on its own, over stdio:

```powershell
python -m genesys_mcp.server
```

## Tests

```powershell
python test_cards.py     # card normalization, Link/Pendulum filtering
python test_solver.py    # knapsack, budget edges, the no-legal-deck case
python test_store.py     # save/load round-trip and every rejection path
python test_server.py    # all three tools, success and failure paths
```

Two exploratory scripts:

```powershell
python inspect_deck.py "Blue-Eyes"   # full decklist with archetype share
python find_failures.py              # archetypes that cannot field an engine
```

## Data source

Card data comes from the [YGOPRODeck API](https://ygoprodeck.com/api-guide/),
which is free and needs no key.

Genesys point costs live in `misc_info[0].genesys_points`, and are only returned
when **both** `format=genesys` and `misc=yes` are passed. Neither alone works.

Two things worth knowing if you extend this:

**`format=genesys` does not filter out Link and Pendulum monsters**, despite
banning them. Verified: `Decode Talker` (Link) and `Odd-Eyes Pendulum Dragon`
(Pendulum) both return results under that filter. The legality check in
`cards.py` is therefore load-bearing, not defensive decoration.

**The API has no historical banlists.** It exposes only the current TCG, OCG and
Goat lists, which is why this project uses the Genesys point system rather than
a banlist snapshot — a better constraint anyway, since it is a real optimization
problem rather than a filter.

The published rate limit is 20 requests per second, and exceeding it blocks the
IP for an hour. The client throttles to 5 per second for headroom and caches
every response to `cache/` for 24 hours.

## Known limitations

- Card quality is scored by popularity, not play strength.
- The 50% archetype floor is a design choice, not a Genesys rule. Without it the
  optimizer correctly concludes generic staples beat archetype cards, which
  makes the archetype parameter meaningless.
- `sqlite3` is synchronous while the server is async. Fine for a single user;
  real concurrency would want a thread executor or `aiosqlite`.
- Side decks are not modelled, though Genesys counts them toward the cap.