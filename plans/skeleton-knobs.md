# Theme-Driven Skeleton Knobs + Cycle Primitive

**Status:** proposed. Builds on **Skeleton Generation** (`plans/skeleton-generation.md`).
**Trello:** [Theme-driven skeleton knobs + cycle primitive](https://trello.com/c/gL2qnXFr)

## Problem

The skeleton's *structure* is hardcoded. `generator.py` encodes the average of
five recent premier sets as module constants — `BASE_RARITY_COUNTS` (95/98/63/20),
the multicolor budgets (`0.04` common / `0.25` rare / `0.30` mythic), `_CREATURE_PCT`,
the type ratios, the mana curve — and only *scales* them by `set_size`. The LLM
relabel (phase 2) repaints per-slot *flavor* on top, but it is count-invariant and
only writes `tweaked_text`; the structural shape never moves.

Our own research (`research/set-design.md`) shows this is exactly backwards from how
real sets vary. It separates **structural invariants** (held constant across wildly
different themes) from **theme-dependent variables** (the set's identity), and flags
**multicolor density as "the single largest theme-dependent structural variable"**
(9.9% LCI → 26.1% MKM). Concretely, every theme lever our research says *should* swing
is a constant in the generator:

| Theme lever (research range) | Generator today |
|---|---|
| Multicolor density 10–26% | fixed `0.04`/`0.25`/`0.30`, no theme input |
| Rarity ratio bends (MKM ran 70 rares for its gold theme) | fixed 95/98/63/20, scaled only by size |
| Multicolor commons when theme demands (BLB ran 10, one per pair) | `0` for small sets; the ±0 common color-balance check squeezes them out |
| Card-type skew (DSK 47 enchantments; LCI 44 artifacts) | fixed creature % + instant/sorcery ratios |
| **Cycles** (OTJ fastland cycle, BLB Mentor cycle, guildgate-style common duals) | **no representation at all** — and `land_generator` emits exactly **one** nonbasic land |

Result: every generated set regresses to the same shape, and structural set-defining
gestures (a 10-card dual-land cycle, a gold-saturated guild set, an enchantment-matters
set) are impossible to express.

## Design

A new **phase 0** inside the existing `skeleton` stage, before the deterministic build.
The stage becomes three phases, all under the AI lock:

```
phase 0  knob tuning (LLM)     TRC + archetypes + default knobs ──► SkeletonKnobs
phase 1  deterministic build   generate_skeleton(config, knobs)  ──► default skeleton
phase 2  relabel (LLM)         (unchanged) per-slot tweaked_text
```

Keeping it a phase (not a new stage/artifact) follows the prior decision that collapsed
the standalone `constraints` stage into `skeleton` — knobs persist as a section of
`skeleton.json` (a `knobs` field on `SkeletonResult`), not a separate file.

### Core principle: the LLM proposes, the deterministic layer disposes

Phase 0 only moves knobs **within clamp ranges derived from the research**, and phase 1
**always** reconciles to the hard invariants. The LLM cannot emit an illegal skeleton —
it can only bend the bendable knobs inside legal bounds. This preserves the "structural
invariants are fixed" guarantee while letting the "theme-dependent variables" vary.

**Hard invariants (never knobs — phase 1 enforces them, and they clamp the knobs):**
per-color balance (±0 at common), creature-density floor, all-10-archetype-pair signpost
coverage, rarity totals = `set_size`, the broad mana-curve shape. These come straight from
the research's "structural invariants" list.

### Two kinds of knob

**1. Scalar distribution knobs** — reshape phase 1's targets. Default = today's constants
(so an absent/failed phase 0 reproduces the current skeleton exactly), clamp = research range:

| Knob | Default | Clamp range | Research source |
|---|---|---|---|
| `rarity_ratio` {C,U,R,M} | 95/98/63/20 | C 86–113, U 92–100, R 60–70, M 20–22 | §2.1 card counts |
| `multicolor_pct[rarity]` (U/R/M) | 0/.25/.30 | overall 10–26%; per-rarity from §2.2 | "largest theme variable" |
| `colorless_pct[rarity]` | current | 3–15% overall | §2.2 |
| `creature_pct[rarity]` | `_CREATURE_PCT` | 50–60% | §2.3 |
| `noncreature_bias` {ench,art,inst,sorc} | current ratios | theme-dependent | §2.3 (DSK/LCI skews) |
| `planeswalker_count` | 1 | 1–2, always mythic | §3.3 |
| `signposts_per_pair` | 1 | 1–2 | §3.5 |

Renormalized to hit `set_size` exactly after clamping.

**2. Cycles** — structural reservations carved *before* scalar distribution. A `Cycle`:

```
Cycle: id, name, rarity, span, card_type, template, notes
  span ∈ { mono5 (one per WUBRG), pairs10 (one per color pair),
           allied5, enemy5, wedges5, shards5, colorless1, single }
```

Phase 1 reserves a cycle's slots first, decrementing the rarity budget, then distributes
the remainder with the scalar knobs. **Key elegance: a cycle whose span is "one per color"
or "one per pair" is inherently balance-preserving** — it adds slots evenly across colors/
pairs, so it never disturbs the ±0 color-balance invariant. That is *why* real design uses
the cycle as the unit: it lets a set make a bold structural statement (10 dual lands! a
mono-5 rare cycle!) without breaking balance. Each member slot is stamped with `cycle_id`
+ the shared `template` so card-gen renders a coherent family; the relabel can still refine.

This also fixes the multicolor-common case correctly: **BLB's 10 gold commons are a cycle**
(one per pair), not a loose scalar — modeling them as a `pairs10` common cycle keeps them
balanced by construction, instead of forcing the distributor to fight the ±0 rule. So
multicolor-at-common is expressed via cycles, while scalar `multicolor_pct` covers the loose
U/R/M density.

### Knob schema: one source of truth for ranges + validation

Each knob's `{default, min, max, step, label}` lives in a single `SkeletonKnobs` schema
(Pydantic, with `field_validator`s). That one definition drives **everything**:

- **AI output validation** — phase 0's returned values are clamped/validated through it.
- **Manual-input validation** — a user-set value is validated through the *same* path
  (server-side on save, mirrored client-side for instant feedback), so a hand-typed value
  can never produce an illegal skeleton either.
- **UI control bounds** — the wizard renders each control (slider / stepper) straight from
  `min/max/step`, so the bounds the user sees *are* the bounds we enforce.

Beyond per-knob range checks there is a **feasibility check** on the combination: cycle
reservations + the per-color creature floor + signpost coverage must fit within the rarity
budget. If a knob/cycle combo is infeasible, phase 1 reconciles (clamps the offending knob)
and records what it changed, surfaced as a tab notice — the build never silently produces a
skeleton that fails a hard invariant.

### Manual control + AI provenance (UI)

The user must be able to **drive the knobs directly, not just review them**. Per
`plans/wizard-tab-conventions.md`:

- **Auto-run, then editable** (standard wizard flow): on stage entry phase 0 runs and fills
  every knob with an AI-tuned value + a short rationale; the Knobs panel sits above the slot
  diff with each value editable.
- **Provenance per knob** — a badge shows whether each value is `default`, `ai-tuned`, or
  `user-set`, so "see what the AI did" is answerable at a glance (and diffed against default).
- **Pin / lock** — the user can pin a knob to a manual value; a Refresh (re-roll of phase 0)
  **respects pinned knobs** and only re-tunes the rest. This is what lets the user say "gold
  set, multicolor at 24%, you handle the rest."
- **Apply cascade** — editing a knob re-runs phase 1 (cheap, deterministic) and offers to
  re-run the relabel (phase 2), consistent with the past-tab edit-cascade convention.

### Phase 0 mechanics (mirror the relabel)

A single structured tool call (knobs are small — a tool call, not the relabel's free-text
stream). Reuse the relabel's `_format_*` block helpers (setting / mechanics / archetypes /
constraints / card_requests) for the prompt context — lift them to a shared module.
Model assignment: `skeleton` (shared). Prompts: `pipeline/prompts/skeleton_knobs_{system,user}.txt`.
Logs → `<asset>/skeleton/logs`. **Failure handling mirrors the relabel:** an LLM failure or
unparseable output falls back to the default constants and flags `knobs_defaulted` on the
result (surfaced as a tab notice), never a hard error — the default skeleton stays usable.

## Surfaces

- `pipeline/stages.run_skeleton` — insert phase 0 before `generate_skeleton`; thread `knobs`
  into `generate_skeleton(config, knobs)`. New phase string "Tuning the skeleton to fit the set".
- `wizard_skeleton.js` — the **Knobs panel** above the slot diff (controls bounded by the
  schema, provenance badges, pin/lock, Refresh re-roll) — see "Manual control + AI provenance"
  above.
- New endpoint `POST /api/wizard/skeleton/knobs` (set + validate + re-build), alongside the
  existing `/api/wizard/skeleton/{state,refresh,save}`. Validation runs through the shared
  `SkeletonKnobs` schema.
- `skeleton.json` — `SkeletonResult.knobs` + `SkeletonResult.cycles`; `SkeletonSlot.cycle_id`.

## Rollout (phased — de-risks the land/cycle entanglement)

- **Phase A — scalar knobs only.** Knob schema + phase 0 tuning + clamping + thread into
  `_scale_rarity` / `_distribute_colors` / `_assign_card_types`. No cycles. Defaults = current
  constants → zero behavior change when phase 0 is absent or fails. Delivers gold-heavy /
  artifact-heavy / enchantment-heavy sets immediately. **Lowest risk: pure parameterization
  of existing constants.**
- **Phase B — spell cycles.** `Cycle` model + reservation pass (reuse `_apply_reservations`
  machinery) for *non-land* cycles: gold-uncommon signpost cycles (reconcile with
  `_mark_signpost_slots`), mono-5 rare cycles, colorless cycles. **Cycle-coherent generation
  (required, not optional):** a cycle's members are pulled out of the color batcher
  (`group_slots_into_batches`) into a single cycle-batch and generated in one call, so the LLM
  designs the family with parallel structure and a shared template. Where a cycle is too large
  or mixed to fit one call, fall back to sequential generation with the already-built siblings
  injected into each member's prompt as reference. The `cycle_id` + shared `template` stamp
  (set in phase 1) is what enables both paths.
- **Phase C — land cycles (the guildgate case).** Introduce land slots into the skeleton
  budget and integrate with the `lands` stage. This is the most entangled (crosses the
  skeleton/lands boundary), hence last.

## Open questions

1. **Land-cycle rendering owner** (Phase C — *deferred until Phase C starts*): does the
   `lands` stage render skeleton-budgeted land cycles from their specs, or does card-gen?
   Lean: skeleton *budgets*, lands stage *renders* (it's the land specialist).

## Out of scope

- Booster / print-run collation legality.
- Bending the hard invariants (mana curve, per-color balance, creature floor, signpost
  coverage) — deliberately fixed; they are what keep generated sets playable.
- Knob revision by `skeleton_reviser` — it stays a slot-level post-balance double-check.
