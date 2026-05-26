# Constraints stage — theme-aware skeleton revision (pre-generation)

**Status:** design (not yet implemented). Anchors Trello card `69f9d1ef`
(sMSqWKw6, "Move skeleton revision to pre-card-gen / constraint derivation")
and the tweak list `6a14009b`.

## Problem

The skeleton today is built **purely from `set_size`** against hardcoded
constants — TRC (Theme/setting + Constraints + Requests) plays no part in its
structure. Slots carry a complexity *tier* (`vanilla/.../complex`), never a
*named* mechanic, so the card generator picks mechanics freely → monoculture
(Salvage 12 vs planned 6) and orphaned mechanics. Card requests are pinned
name-only (TC-7) with their type/color/rarity signal discarded, and requests
needing slot kinds the matrix lacks (legendary, planeswalker, land) go
unplaced. The only place TRC currently bites is the *post-generation* reviser —
too late; the structural problems were knowable before any card existed.

## Goal

Insert one **pre-generation** stage that turns the generic, count-derived
matrix into a *themed* one, so each of the ~`set_size` slots already carries the
structural + flavor guidance the generator needs. The post-card-gen
`skeleton_rev` reviser then demotes to a lighter "did anything slip?"
double-check (re-scope tracked separately on `69f9d1ef`).

Pipeline order (mechanics + archetypes already precede skeleton):
```
theme → mechanics(approved.json) → archetypes → skeleton(seed)
      → CONSTRAINTS STAGE (this)  → card_gen → balance → skeleton_rev(double-check) → …
      (visual_refs runs later, just before the art stages — not a pre-skeleton input)
```

## Core design decisions (locked)

### 1. LLM-in / LLM-out, fully fluffy, count-only contract
The matrix is an **ordered list of N addressable items** (index = slot id).
Each item is a free-text tag blob — color, rarity, type, CMC, mechanic,
archetype, role, legendary, etc. are all *prose*, never validated. The sole
hard guarantee is: **we can split the matrix back into N generator prompts.**
The downstream consumer is itself an LLM (the card generator), which handles
fuzzy input well, so we do not validate tag semantics.

### 2. Pass 1 = relabel-in-place of a fixed-size pool
We hand the model the **default skeleton as the seed** (the deterministic
generator output — the "standard MTG set" the constants encode) rendered as N
tagged slot lines, plus TRC + approved mechanics + archetypes. The instruction
is *"rewrite each slot's tags to fit this set — you may change its
color/type/rarity/mechanic — but return all N."*

Every thematic reshape is a **relabel**, not an add/remove:
- "lots of artifacts" → retag slots as artifact
- "half black" → retag colors
- "lots of planeswalkers" → retag some slots planeswalker
- "multicolor themed" → retag monocolor → multicolor

Because N is invariant by construction, the count guarantee is free and the
only check is "got N items back" (else one retry / reconcile by index).
Slot kinds the seed lacks (legendary, planeswalker, land) are created simply by
*writing those words into a slot's tags* — no schema, no `legendary` flag.

### 3. Pass 2 = assign card requests to slots
A second LLM call takes the revised matrix + `card_requests` and assigns each
request to the best slot **by id**, attaching the request as a rider and
**rewriting that slot's tags to fit** (so "Cybertron, legendary land" just
relabels its chosen slot a legendary land). Requests are matched for fit
against archetype + color + mechanic, which is why this stage runs after
archetypes. The one parse guarantee: each request → exactly one slot id.

Kept separate from pass 1 because pass 1 reasons about *whole-set distribution*
while pass 2 is a *matching* problem over a finalized matrix (smaller, cheaper).

### 4. Splitter (the only hard-validated bit)
Deterministic: for each of the N items emit one generator prompt = its tag blob
(+ rider if present) + shared set context (mechanics, archetypes, setting).
Generation becomes **per-slot (or simple ordered-chunk)** — the current
color-keyed batcher (`group_slots_into_batches`) retires, since color is no
longer a structured key.

## Pass-1 prompt spec

The set-design knowledge that currently lives in the validators
(`_check_color_balance`, `_check_creature_density`, `_check_signpost_uncommons`,
curve checks) **moves into the prompt — but as data, not prose.**

- **Rules-as-data.** The seed matrix already *is* ~50% creatures, even colors, a
  smooth curve, 95/98/63/20, 10 signpost multicolor uncommons. The model reads
  those facts off the seed; we do **not** restate them as numbers in prose.
  Single source of truth = the seed generator's constants (same reason we
  deleted `set-template.json` — no duplicated numbers to drift).
- **Prose is limited to three short things:**
  1. *Seed is authoritative* — "this baseline is a deliberately balanced,
     draftable set; preserve its overall shape unless a constraint demands
     otherwise." (Makes preservation the default; deviation the exception.)
  2. *Deviation hazards* — the few things easy to break while relabeling whose
     consequences aren't visible from one matrix: don't strand the multicolor-
     uncommon signposts (one per pair = archetype coverage), keep planeswalkers
     genuinely scarce even in a "planeswalker set," keep it draftable.
  3. *Override examples* — "a set packed with rares," "half black" — to signal
     the kind + magnitude of allowed deviation.
- **Rarity** is the headline instance of preserve-unless-told: keep each slot's
  seed rarity (and the overall distribution) unless the theme explicitly calls
  for a skew. Started fully fluffy (see tripwires).
- **Tags set the slot's *role*, not the card's *text*.** Useful: color, rarity,
  type, rough CMC, a mechanic *menu* (not a verdict) on enough slots to hit
  floors, archetype/faction, a one-line role, legendary/named when relevant.
  Forbidden: ability text, stats, written keywords, creature types — the
  generator owns creative design, and over-tagging here steals its room.
- **Creativity dials, set oppositely:** structural creativity (this pass) is
  *high but caused* (bold where TRC demands, nothing gratuitous); card
  creativity is *protected* by deliberately under-tagging — most slots stay
  lightly tagged so the generator can surprise us; pin a slot hard only when a
  constraint, a mechanic floor, or a request requires it.
- **Mechanics = floors + caps, not full assignment.** Tag only enough slots
  with a named mechanic to hit each mechanic's minimum; cap the max; leave the
  rest open-menu. Kills monoculture + orphans without killing variance.
- **Techniques:** the model emits just the relabeled matrix (no preamble). The
  review surface is the **full matrix rendered in the stage tab** — a human
  reads the slots directly, so we never need the model to narrate its own
  reasoning. Anchor format + boldness with 1–2 few-shots (one themed rewrite,
  one bold deviation). The #1 failure mode is **timidity** (returning a
  near-identical matrix); counter by framing the seed as generic/bland and by
  the few-shot bold-deviation example.

Worked example (format + taste):
```
seed:    142 | U | common | instant | CMC2 | complex
themed:  142 | U | common | instant | ~CMC2 |
         role: cheap Decepticon combat trick that rewards controlling artifacts;
         mechanic menu: {Transform}; archetype: UR tempo
```

## Derived projections (instead of structured fields)

The fluffy matrix stays the single canonical artifact. Whenever deterministic
code needs a structured view, **derive it with a cheap LLM pass** rather than
committing a field:
- **Color-grouping for generation** — optional cheap LLM sort into color
  buckets. Justify on *coherence + dedup* (siblings generated together), NOT
  caching: the dominant prompt-cache win is the stable `[rules + mechanics +
  setting]` prefix shared across all ~277 calls regardless of order; the
  "cards so far" context grows per call and isn't cacheable anyway. Measure
  before adding.
- **Rarity tally** — if tests show rarity drifts too much, add a cheap
  "count rarities, flag if off" pass (or, only then, promote rarity to a
  structured field).

## Resolved decisions
- **No playability floor.** The pass honors the count-only contract and nothing
  else — no minimum creature density, no color/curve guardrails. If the
  constraints push the LLM into a "broken" or unbalanced skeleton, let it; the
  human reviews the matrix in the tab and the prose-level "seed is authoritative"
  framing is the only nudge toward preservation.
- **No directives preamble.** The review surface is the full matrix shown in the
  stage tab, reviewed directly — the model emits only the matrix, no narration.

## Out of scope
- Booster/print rarity-legality enforcement (later phase; see rarity tripwire).
- Full prompt rework of the post-gen `skeleton_rev` reviser to be theme-first
  (tracked separately on `6a13f98e`); here it is only re-scoped + documented as
  a lighter "did anything slip?" double-check.

## Implementation (feat/constraints-stage — as built)

Decided with the user when picking up the card:
- **Full free-text matrix** (the north-star above), with the color batcher kept
  but driven by a **cheap LLM grouping pass** over the blobs (programmatic
  grouping on free text won't work; an LLM groups fine).
- The seed-vs-tweaked review UI is **folded into the Skeleton tab** (one bespoke
  tab shows seed + tweaked + refresh + progress), not a separate Constraints tab.
- `skeleton_rev` **kept, re-scoped** to a lighter post-balance double-check.

### Artifacts + join key
`slot_id` is the stable join key. `skeleton.json` stays the structured seed
(unchanged), so `reprints` (reads structure, writes its own `reprint_selection.json`)
and `lands` (independent) are untouched. The constraints stage writes a parallel
**`constraints.json`** = the fluffy matrix:
```
{ "model_id", "cost_usd", "seed_slot_count",
  "slots": [ {"slot_id": "W-C-01", "blob": "<free-text relabel>", "reserved_card": null}, … ] }
```

### Backend
- `mtgai/generation/constraint_deriver.py` (NEW, mirrors `archetype_generator.py`):
  `derive_constraints()` orchestrates Pass 1 (`relabel_matrix` — seed lines in,
  N blobs out, reconciled by slot_id) + Pass 2 (`assign_requests` — card_requests
  → slot_id, blob rewritten to fold the request in). `load_constraints_matrix()`
  loader. `llm_group_slots()` = the LLM color-batcher used by card-gen.
- Prompts in `mtgai/pipeline/prompts/`: `constraints_relabel_{system,user}.txt`,
  `constraints_assign_{system,user}.txt` (NEW — the existing `constraints_system.txt`
  is the theme-extractor's prose→constraints stub; left alone).
- `pipeline/stages.py`: `run_constraints` (reads skeleton/theme/approved/archetypes,
  derives under `ai_lock`, writes `constraints.json`, emits before/after sections) +
  `clear_constraints`. Registered in `STAGE_RUNNERS` / `STAGE_CLEARERS`.
- `pipeline/models.py`: `constraints` stage after `skeleton`, before `reprints`
  (review_eligible, default break-point on so the Skeleton tab can review the matrix).
- `settings/model_settings.py`: `constraints` → `sonnet` in `DEFAULT_LLM_ASSIGNMENTS`
  + recommended preset (the batcher reuses the same model).
- card-gen consumption: `card_generator` loads `constraints.json` when present and
  builds per-slot prompts from the blob (`prompts.format_fluffy_specs`), grouping via
  `llm_group_slots`; **falls back to the structured `format_slot_specs` +
  `group_slots_into_batches` path when absent** (backward-compat for old sets/tests).

### Frontend
- `wizard.py compute_visible_tabs`: suppress the standalone `constraints` tab.
- `wizard_skeleton.js` (NEW, mirrors `wizard_archetypes.js`): bespoke Skeleton tab —
  seed slot table + tweaked matrix (changed cells highlighted), editable blobs,
  section Refresh AI (re-runs constraints, indeterminate `showBusy`), Save & Continue
  (advances past constraints).
- `pipeline/server.py`: `/api/wizard/constraints/{state,refresh,save}`.
