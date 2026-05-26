# Skeleton Generation — deterministic default + LLM relabel (one stage)

**Status:** implemented on `feat/skeleton-generation` (card `69f9d1ef`). Supersedes
the earlier separate `constraints` stage (collapsed in per design feedback).

## Problem

The skeleton was built purely from `set_size` against hardcoded constants — the
theme/constraints/requests (TRC) played no part in its structure. Slots carried a
complexity *tier* (`vanilla`/…/`complex`), never a *named* mechanic, so the card
generator picked mechanics freely → monoculture (Salvage 12 vs planned 6) and
orphaned mechanics. Card requests went unplaced. The only place TRC bit was the
*post-generation* reviser — too late; the structural problems were knowable before
any card existed, and fixing them post-hoc cost ~$3.44/run in wasted regeneration.

## Design (as built)

**One stage, "Skeleton Generation"** (`skeleton`, between `archetypes` and
`reprints`), two phases:

1. **Deterministic default.** `skeleton/generator.generate_skeleton()` builds the
   balanced default skeleton from the project's `set_params` (`set_size`, *not*
   theme.json). Saved to `skeleton.json` immediately, so a relabel failure leaves a
   usable un-themed skeleton.
2. **LLM relabel** (`generation/skeleton_relabel.relabel_skeleton`). Each slot is
   rendered to a one-line descriptor — `render_slot_string`, e.g.
   `"White · common · creature · CMC1 · vanilla"` — and the LLM rewrites it to fit
   the set:
   - **Pass 1 (relabel):** rewrite every descriptor. Name the mechanics (kill the
     monoculture — floors/caps in the prompt), swing color/type/rarity where the
     setting demands, add legendaries/lands by writing the words in. Count-invariant
     (N in, N out, reconciled by `slot_id`; a dropped slot keeps its default).
   - **Pass 2 (assign):** place each `theme.json` `card_request` onto the best-fit
     slot and rewrite that slot's descriptor + set `reserved_card`.

The rewrite is stored per slot as `SkeletonSlot.tweaked_text`. **The structured
fields stay the deterministic default** — only `tweaked_text` + `reserved_card`
carry the relabel — so `reprints`/`lands` (which read the structured shape) are
untouched, and the programmatic color batcher still groups card-gen siblings.

## Why this shape

- **No separate `constraints` stage / artifact.** "constraints" is just a
  `theme.json` field (an *input*); naming an output that too was confusing. The
  default skeleton is a deterministic intermediate — no separate file; it lives as
  the structured fields of `skeleton.json`, re-rendered to a string for the diff.
- **Structured default → string per slot → LLM rewrite → strcmp.** The diff between
  default and tweaked is just two strings; the Skeleton tab shows it with a
  word-level LCS diff highlighting the changed tokens. Clean to review, robust to
  however the model reformats the line.
- **`tweaked_text` is card-gen's spec.** `prompts.format_slot_specs` emits it
  verbatim (else falls back to `render_slot_string`); `signpost`/`reprint`/archetype
  instructions still thread from the structured fields.

## Surfaces

- `pipeline/stages.run_skeleton` — both phases, under the AI lock; relabel logs →
  `<asset>/skeleton/logs`. Auto-runs (no manual "generate" gate); default break-point
  `review` so the user reviews on the Skeleton tab.
- `gallery/templates/static/wizard_skeleton.js` — per-slot default-vs-tweaked diff,
  editable tweaked line, section Refresh (`/api/wizard/skeleton/{state,refresh,save}`).
- Model assignment `skeleton` (local by default). `skeleton_rev` kept but re-scoped
  to a post-balance double-check (theme-first prompt rework on card `6a13f98e`).

## Out of scope
- Booster/print rarity-legality enforcement (later phase).
- Re-running reprints/lands off the *relabeled* (vs default) structure — they read
  the deterministic default fields, which is sufficient for now.
