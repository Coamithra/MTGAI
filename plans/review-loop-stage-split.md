# Post-`card_gen` stage split for the review→regen loop

## Context / relationship to `balance-stage-rework.md`

[`plans/balance-stage-rework.md`](balance-stage-rework.md) defines the **mechanism** and is
committed: forward-only insertion of repeated stage instances, the `regen_reason` /
`flagged_by` card-flag substrate, `StageResult.rerun_from`, the index-driven engine walk
(`while i < len(stages)`), and budget-exhaustion → pause-for-human. None of that changes here.

This doc locks the **stage split that rides on that mechanism** — how many post-`card_gen`
stages there should be, what each one checks, and four deliberate amendments to the stage
decisions in `balance-stage-rework.md`. Where the two disagree, **this doc wins on the split**;
`balance-stage-rework.md` stays the source of truth for the engine/loop plumbing.

## Organizing principle

Under the loop, every post-`card_gen` stage is exactly one of three kinds:

- **Gate** — checks one dimension; on failure writes regen flags onto the offending cards and
  sets `rerun_from="card_gen"`. The engine inserts a fresh `card_gen` + the span up to that
  gate and walks forward. When a gate's `stage_id` hits `MAX_REVIEW_ROUNDS` with flags
  remaining, that instance pauses for human review (keeps the best attempt, leaves cards
  flagged).
- **Transform** — deterministically rewrites cards, no flagging. Cannot live inside the loop
  (a later regen would wipe its work); runs once after the gates converge.
- **Human pause** — sign-off, and the surface where exhausted flags land.

**Cost rule that dictates gate order:** a bounce at gate *i* re-inserts the entire span from
`card_gen` through *i*. So gates are ordered **cheap → expensive** and **independent →
dependent**: the cheapest, most-likely-to-flag, most-independent gate runs first; the
expensive, usually-clean, most-dependent gate runs last.

## The split

```
card_gen → conformance → interactions → design_review → finalize → human_card_review
            └──────────────── loop gates ───────────────┘          transform     human gate
```

| Stage | `stage_id` | Kind | Checks | Action on failure |
|---|---|---|---|---|
| **Conformance** *(new)* | `conformance` | Gate (LLM, per-card vs slot spec) | Each card fulfils its slot's `tweaked_text` spec | Flag the deviating **card** → `rerun_from="card_gen"` |
| **Interaction Check** *(reworked `balance`)* | `balance` | Gate (LLM, whole-pool relational) | Degenerate combos across the finished pool | Flag the **enabler** card → regen with `replacement_constraint` |
| **Design Review** | `ai_review` | Gate (LLM, tiered council, **hybrid**) | Per-card design quality | **Revise in place** ≤ N iters; flag only the **unfixable** for regen |
| **Finalization** | `finalize` | Transform (deterministic, no LLM) | — | Reminder injection → validate → AUTO-fix → save; MANUAL residue → human gate |
| **Card Review** | `human_card_review` | Human pause | — | Sign-off + loop-exhaustion landing surface |

All three gates **skip basic lands and reprints** (staples are already balanced; reprints are
not even materialized yet).

## What each stage checks

### Conformance (new gate — runs first)
One whole-set LLM call: each card paired with its slot's `tweaked_text` (falling back to
`render_slot_string` when a slot was never relabeled). The model judges adherence
**holistically — no descriptor parser**. Per card:
- Color / card type / rarity match the slot.
- Uses the slot's assigned mechanic (if one was relabeled in).
- Honours theme constraints and `card_requests` placed on the slot.
- Hits the relabeled design intent — signpost archetype, cycle-member template, reserved-card
  request.

Flags every non-conforming `slot_id` with `flagged_by="conformance"` and a one-line reason
("slot wants X, card is Y"). Runs **first** because (a) it is the most objective gate and the
one most likely to flag a fresh set, (b) regenerating a non-conforming card changes the combo
landscape, so there is no point scanning interactions on a card about to be replaced, and (c)
a conformance bounce re-runs only `card_gen` — the cheapest possible span.

### Interaction Check (reworked `balance` — second gate)
Keeps the substance of today's `analyze_interactions`: one whole-pool LLM scan for degenerate
combos / infinite loops / oppressive lock pieces, naming the enabler card and a
`replacement_constraint`. Flags the **enabler** (which may be fine in isolation) with
`flagged_by="balance"`, threading `replacement_constraint` into `regen_reason`. Runs after
conformance so it scans a pool that already matches the plan; relational, so it cannot be
per-card.

### Design Review (`ai_review` — hybrid, last gate)
Unchanged review substance: tiered council+iteration (single reviewer for C/U, 3-reviewer
council + 2-of-3 synthesis for R/M + planeswalkers/sagas), checking templating, power level
vs rarity, color-pie, kitchen-sink / false-variability, keyword nonbos, and the 8 pointed
questions. **Behaviour is hybrid:** the council **revises in place** (its measured strength —
see `learnings/phase1b.md`: in-place council revision produced the best, most surgical fixes;
"analysis ≠ action"). Its existing `MAX_ITERATIONS` is the in-place budget. Only cards it
**cannot** fix in N iterations get flagged for full regen (`flagged_by="ai_review"`,
`rerun_from="card_gen"`). The loop is the overflow path, not the primary one. Runs last: it is
the most expensive gate and most cards already conform + are non-degenerate by the time they
reach it.

### Finalization (`finalize` — transform, after the loop converges)
Deterministic, no LLM, `review_eligible=False`. Strip + re-inject reminder text from mechanic
definitions (reminder text is never LLM-generated), run the full validator suite, apply AUTO
fixes, save. Residual MANUAL errors are surfaced to the human gate, **not** spun back into the
loop — post-review they are rare and need human eyes. Must run after all gates pass, or a
regen would discard its work.

### Card Review (`human_card_review` — human pause)
The existing no-op pause (default break-on). Also the surface where loop-exhausted instances
land: a gate that hit `MAX_REVIEW_ROUNDS` with flags remaining pauses here, with the flagged
cards + their `regen_reason` visible in the gallery.

## Amendments to `balance-stage-rework.md` (four)

The plan's mechanism (loop, flag substrate, instance insertion, budget→pause) stands. These
four stage decisions change:

1. **Gate order: `conformance` before `interactions`.** The plan lists
   `balance → conformance`; swap to `conformance → balance`. Rationale: cheapest /
   most-independent / most-likely-to-flag first (cost rule above).
2. **`skeleton_rev`: delete, do not migrate.** Drop the plan's Part 3 skeleton_rev migration
   and the Part 2 "transitional shim / SKIPPED default" note. Its job is gone: card
   regeneration is now the engine's, slots are themed + balanced upstream by the relabel, and
   the only residual case (a slot so contradictory no card can conform) is exactly what
   budget-exhaustion → pause-for-human already handles. Strip `run_revision` and its private
   round loop; keep only `regenerate_slots`' scoped-regen mechanics **iff** the engine reuses
   them.
3. **`ai_review`: hybrid, not full regen-loop.** The plan's Part 3 gives ai_review "the same
   flag-and-regen behaviour (its in-stage `MAX_ITERATIONS` repair becomes engine-level
   regen)". Instead, **keep** in-place council revision as the primary action and use the loop
   only for the unfixable remainder. Migrating it fully to regen-from-scratch should be
   A/B-tested before adoption (same discipline that produced the council), not assumed.
4. **Rename display only:** "Balance Analysis" → "Interaction Check". Keep `stage_id="balance"`
   so URLs, break-point keys, and model assignments don't churn.

## Deletions (plan's list, confirmed + extended)

- `analysis/coverage.py` + its models; algorithmic `analysis/conformance.py`; most of
  `analysis/helpers.py`'s regex/parsing; `analyze_set()`; `BalanceAnalysisResult`;
  `report.py`'s markdown/JSON `save_report`; the `mtgai review balance` CLI command.
- **Added by this doc:** `generation/skeleton_reviser.py`'s `run_revision` (+ its
  `RevisionPlan` / `RevisionRound` / `RevisionReport` models and balance-findings prompt
  builder). Keep `regenerate_slots` only if the engine's scoped regen reuses it.
- Keep + adapt `analysis/interactions.py`; add the new LLM `conformance` module.

## Dropped concerns — still covered

- **Set-level structural balance** (per-color counts, creature density, rarity totals,
  signpost coverage, mana-fixing inventory): an **upstream** invariant now. The skeleton is
  balanced by construction (knob-clamped) and conformance guarantees each card matches its
  balanced slot → the aggregate is balanced transitively. No downstream coverage gate needed.
- **Per-card power level:** lives in Design Review (where `phase4a.md` always said it belonged),
  with `render_qa`'s heuristic sweep (power level, color pie, mechanical similarity) as the
  final non-loop safety net at the end of the pipeline.

## Files to change (delta over `balance-stage-rework.md`)

`balance-stage-rework.md` already enumerates the loop plumbing (Part 1 instance-based
pipeline, Part 2 loop + flag substrate). On top of that:

- `pipeline/models.py` — `STAGE_DEFINITIONS`: insert `conformance` **before** `balance`;
  relabel `balance` display to "Interaction Check"; **remove** `skeleton_rev`.
- `pipeline/stages.py` — add `run_conformance`; rework `run_balance` to the interaction-only
  flagging runner; **remove** `run_skeleton_rev` + its registry/clearer entries; registry +
  clearer for `conformance`.
- `analysis/` — add LLM `conformance` module; adapt `interactions.py`; delete
  coverage/algorithmic-conformance/report/`analyze_set`.
- `generation/skeleton_reviser.py` — delete `run_revision` (+ revision models); keep
  `regenerate_slots` only if reused by the engine.
- `review/ai_review.py` — add the flag-on-unfixable escape (`rerun_from="card_gen"` for cards
  still REVISE after `MAX_ITERATIONS`); otherwise unchanged (in-place revision retained).
- `gallery/templates/static/` — new `wizard_conformance.js`; rework `wizard_balance.js` to the
  interaction-flag view; **delete** `wizard_skeleton_rev.js`. Endpoints
  `/api/wizard/{conformance,balance}/state` per the reprints `/state` convention.
- `review/cli.py` — remove the `balance` command.

## Verification

- **Gate order:** force a conformance miss + an interaction miss in the same set; assert the
  strip grows `conformance → card_gen 2 → conformance 2 → … → balance → …`, conformance
  settles before interactions runs, and a conformance bounce re-inserts only `[card_gen,
  conformance]`.
- **ai_review hybrid:** a card with a fixable issue is revised in place (no regen, no extra
  instance); a card still REVISE after `MAX_ITERATIONS` flags + triggers one regen span.
- **skeleton_rev gone:** `STAGE_DEFINITIONS` has no `skeleton_rev`; a state persisted with a
  legacy `skeleton_rev` stage reconciles cleanly on load (dropped from the backbone).
- **Exhaustion:** set the cap low + a persistent conformance failure; confirm the conformance
  instance pauses for human review with flagged cards shown.
- **Lint/tests:** `cd backend; ruff check . && ruff format . && pytest`. `mtgai review --help`
  no longer lists `balance`.

## Open / deferred

- **A/B test** before any future move of `ai_review` from in-place revise to full regen-loop.
- The plan's **conformance LLM prompt** (per-card adherence, no parser) is new prompt surface —
  budget a calibration pass like the mechanic/skeleton relabel prompts got.
