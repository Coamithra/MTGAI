# Card subtype distribution (last 12 premier sets)

Source: `research/scripts/subtype_analysis.py` over the 12 most recent premier
sets with booster data on Scryfall (Jan 2024 – Jan 2026): MKM, OTJ, BLB, DSK, FDN,
DFT, TDM, FIN, EOE, SPM, TLA, ECL. Raw aggregate: `research/raw-data/subtype-analysis.json`.
(Two newer sets — SOS, TMT — had no `is:booster` data yet and were dropped.)

This is the Stage-1 deliverable for the [skeleton-detail card](https://trello.com/c/qHGgod0O):
which fine-grained card subtypes the skeleton should model, and how to split them
into *recurring* (standing knobs) vs *irregular/special* (a bucket we pick 0–N
from) vs *one-set-exclusive* (exclude).

## Findings (per ~277-card set)

| Subtype | In sets | avg/set | avg(when present) | min | max | Class |
|---|---|---|---|---|---|---|
| Equipment | 12/12 | 6.8 | 6.8 | 2 | 24 | **recurring** |
| Aura | 12/12 | 5.5 | 5.5 | 2 | 10 | **recurring** |
| Artifact Creature | 12/12 | 11.0 | 11.0 | 1 | 34 | **recurring** |
| Vehicle | 8/12 | 5.2 | 7.9 | 0 | 41 | **recurring** (deciduous) |
| Saga | 4/12 | 1.5 | 4.5 | 0 | 7 | *irregular* |
| Enchantment Creature | 2/12 | 3.8 | 23.0 | 0 | 31 | *irregular* (theme-defining) |
| Class | 1/12 | 0.8 | 10.0 | 0 | 10 | *irregular* (deciduous) |
| Shrine | 1/12 | 0.4 | 5.0 | 0 | 5 | *irregular* (deciduous) |
| Room | 1/12 | 1.9 | 23.0 | 0 | 23 | **exclude** (DSK-only) |
| Case | 1/12 | 1.0 | 12.0 | 0 | 12 | **exclude** (MKM-only) |

Outliers worth noting (they're why ranges are wide, and why randomization needs to
respect a *range*, not a point): FIN ran 24 Equipment + 15 Enchantment Creatures
(Final Fantasy gear/espers); DFT ran 41 Vehicles (Aetherdrift racing); EOE 34
Artifact Creatures (sci-fi); DSK 31 Enchantment Creatures + 23 Rooms (Eerie/haunt).

## Classification → implementation

**Recurring → standing count knobs** (every set carries a few; AI tuner bumps them
for a matching theme). Defaults are lean, below the averages, since the high-end
counts are theme spikes:

| Subtype | Parent type | Eligible slots | Default | Range |
|---|---|---|---|---|
| Equipment | artifact | colorless artifacts | 5 | 0–24 |
| Vehicle | artifact | colorless artifacts | 2 | 0–12 |
| Aura | enchantment | colored enchantments | 5 | 0–12 |
| Artifact Creature | creature | any creature | 4 | 0–34 |

**Irregular → the "irregular bucket"** (deciduous types MTG reuses across sets, but
only 0–2 per set). A single `irregular_subtype_count` knob (default 1, range 0–3)
says *how many* of these to include; a seeded RNG picks *which* (theme/LLM-driven
selection is deferred — "random chance now"). Each, when chosen, fills a small
count within its typical range:

| Subtype | Parent type | Typical count when present |
|---|---|---|
| Saga | enchantment (colored) | 2–5 |
| Class | enchantment (colored) | 2–4 |
| Shrine | enchantment (colored) | 1–5 |
| Enchantment Creature | creature | 4–12 |

**Exclude:** Room, Case — each appeared in exactly one set with a set-bespoke
identity. Per the card's rule ("if a type only exists in one set, it's special to
that set"), the skeleton doesn't pre-bake these; a theme that wants them can
introduce them through card_requests / the relabel.

## Randomization requirement

Counts must be drawn from a *range*, deterministically and re-rollably (the
pipeline is resumable; the Skeleton tab diff must be stable). Realization:
`realized = round(center × set_size/277 × (1 + U(−jitter, +jitter)))`, RNG seeded
by `f"{set_code}|{subtype_seed}"` (a stable string seed). `subtype_jitter` (default
0.30) and `subtype_seed` (re-roll handle) are themselves knobs.
