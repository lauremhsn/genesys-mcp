# Reflection

The three categories were given to us, but working out what counts as one
purpose was harder than I expected. `lookup_cards` only reads card data,
`save_deck` only writes a decklist, and `build_genesys_deck` uses both. The
question I kept coming back to was whether a tool changes anything. My storage
code has four operations (save, list, load, delete) and I was going to expose
all of them, which would have put me at six tools instead of three. But listing
and loading saved decks don't change anything, they just read, so I made those
resources instead. That got me to exactly three tools without dropping anything
I needed. I also ended up checking the Genesys rules again inside `save_deck`
even though the solver already produces legal decks. That felt redundant until I
thought about who actually calls it. The agent can hand `save_deck` a decklist
it wrote itself that never went through the solver, and if the checks only lived
upstream, that path would write an illegal deck straight to the database.

Three was the right number here, but `build_genesys_deck` does a lot more
internally than the other two and I went back and forth on splitting it. It
looks up the archetype's cards, looks up the format staples, runs the solver,
and then saves. If I split those into separate tools, the agent would have to
carry a few hundred cards between every call, which is a lot of tokens and a lot
of chances for the model to mess up the data on the way through. Keeping the
heavy work inside one tool and having the agent pass short arguments seemed like
the better trade, even if it looks less single-purpose than the other two. The
first thing I'd change next is how cards get scored, since right now it uses how
often people view them in the card database, which is popularity and not how
good the card actually is. After that I'd add side decks, because Genesys counts
them toward the point cap and I ignore them completely, and probably a tool that
upgrades a deck you already have instead of building one from scratch. One
smaller thing I ran into: my error message said twenty slots were "reserved for
the archetype's engine" without saying whose rule that was, and the agent told
the user it was an official Genesys rule. It isn't, it's a policy I made up
because the optimizer kept producing legal decks nobody would actually play. So
a vague tool message doesn't just confuse the model, it comes back out as the
model stating something wrong with confidence.