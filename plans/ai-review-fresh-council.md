# AI review: fresh council each synthesis iteration, regen after 3 failed rounds

Card: [ilypIszb](https://trello.com/c/ilypIszb) (`refactor`)

## Context
`mtgai/review/ai_review.py::_review_council` (R/M + PW/saga tier) currently runs the
3-reviewer panel **once**, then a synthesizer iterates by **re-reviewing its own
revision** (single `submit_review` call per iteration). No independent voice ever
re-litigates a revision. We want a **fresh full council** to judge each revision,
mirroring the proven `mechanic_generator.council_review` loop, and to flag the card
for a from-scratch regen if it's still problematic after 3 fresh-council rounds.

## Target loop shape
```
initial panel (round 1, 3 reviewers on the original card)
  └─ 2-of-3 OK?  → PASS (verdict OK, unchanged)
  └─ problematic → synth revise #1 → fresh council #1 (round 2)
                     └─ 2-of-3 OK?  → PASS (verdict OK, changed)
                     └─ problematic → synth revise #2 → fresh council #2 (round 3)
                                        └─ ... → synth revise #3 → fresh council #3 (round 4)
                                                   └─ still problematic → FLAG FOR REGEN (verdict REVISE)
```
- `MAX_COUNCIL_ROUNDS = 3` = the number of fresh council *review* rounds after the
  initial panel (so 4 panels + 3 synth revisions max per problematic card).
- The synthesizer's own verdict is **ignored** (it over-claims, like mechanics);
  consensus is computed in code. The synth is now purely a *reviser*.

## Design (file-by-file)

### `mtgai/review/ai_review.py`
- Add `MAX_COUNCIL_ROUNDS = 3`. Keep `MAX_ITERATIONS = 5` for the unchanged
  single-reviewer (`_review_single`) C/U loop.
- Add `CouncilMemberReview.round: int = 1` (backward-compatible; tags which panel a
  review belongs to so the audit trail + tile know the deciding round).
- New helpers:
  - `_CostAcc` — accumulate input/output tokens (incl. cache), cost, latency, model
    across an LLM call (dedups the repeated bookkeeping block).
  - `_council_consensus_ok(reviews, num_reviewers)` — 2-of-3 filter: passes iff a
    strict majority of the **full** panel voted OK (`ok*2 > num_reviewers`). A
    collapsed panel (no reviews) never passes.
  - `_run_council_panel(...)` — run one fresh independent panel on a card dict;
    emits the `{"kind":"round","round":N,"verdicts":[...]}` SSE as each reviewer
    returns; returns `(reviews, acc, panel_verdicts)`.
  - `_run_synth(...)` — one `submit_synthesis` revise-in-place call; emits the
    round's `synth: running → done`; returns `(iteration|None, acc, revised_card|None)`.
  - `_dedup_issues(reviews)` — flatten + dedup the surviving panel issues (the regen
    reason text).
- Rewrite `_review_council` as the round loop above. `max_iterations` param renamed
  to `max_rounds=MAX_COUNCIL_ROUNDS`.
  - `council_reviews` accumulates **all** rounds' reviews (flat, each `round`-tagged).
  - `iterations` holds the synth revise-in-place steps (one per round, `iteration`==round).
  - `current_card` threads the latest revision; `card_was_changed` set on first revise.
  - Final verdict: `OK` on a consensus pass; `REVISE` after the 3rd fresh council
    still problematic, or if a synth fails / declines to revise a consensus-flagged
    card (keep the best in-place attempt saved; the runner flags REVISE→regen).
  - Keep the `_error_review_result` escape only for a **fully collapsed initial
    panel** (every reviewer errored on round 1 → can't judge).
- `review_tile`: show only the **last** round's reviews in the compact `council`
  summary (filter by max `round`), so a reload reflects the deciding panel.
- Markdown report (`_review_to_markdown`): include the round in the reviewer header.

### Behaviour preserved
- `review_all_cards` contract is unchanged: any card ending `final_verdict=="REVISE"`
  lands in `unfixable`, and `stages.run_ai_review` flags it `flagged_by="ai_review"`,
  `rerun_from="card_gen"`. The redesign just makes REVISE mean "council couldn't
  fix it in 3 fresh rounds" instead of "synth still REVISE after 5 self-iterations".
- SSE contract is unchanged shape-wise; the wizard JS already renders any number of
  rounds, each as an N-slot panel + optional synth slot — so every fresh council now
  shows as a full 3-slot panel automatically.

## Tests (`backend/tests/test_review/test_ai_review.py`)
- Update `test_synthesis_failure_does_not_pass_as_ok`: a synth failure after a
  consensus-REVISE panel now flags REVISE carrying the **council's** issue (not a
  synthetic `review_error`); assert that + `iterations==[]`, `council_reviews==3`.
- Keep `test_all_reviewers_fail_does_not_pass_as_ok` (collapsed initial panel → error).
- Keep `test_all_reviewers_ok_returns_real_verdict` (all-OK → OK, no synth).
- Add:
  - `test_two_of_three_ok_passes_without_synth` — 2 OK / 1 REVISE on round 1 → OK,
    `iterations==[]`.
  - `test_revise_then_fresh_council_oks` — round-1 panel flags, synth revises, fresh
    council OKs → final OK, `card_was_changed`, `iterations==1`, two rounds of reviews.
  - `test_persistently_problematic_flags_for_regen` — every panel flags → final
    REVISE, `iterations==3`, `council_reviews==12` (4 panels × 3).
  - `test_synth_self_ok_is_ignored` — synth returns verdict OK but a fresh council
    still flags → loop does NOT trust the synth verdict.

## Out of scope
- `_review_single` (C/U single-reviewer loop) is untouched.
- No new cancellation points inside `_review_council` (card-boundary cancel stays);
  noted: a problematic R/M card now costs up to ~15 LLM calls (4×3 + 3 synth).

## Verification
- `ruff check . && ruff format .`; `python -c "import mtgai"`; `pytest tests/test_review/`.
- Manual smoke optional (engine review on a small pool via `/pipeline`).
