# AI Design Review UI

## Context

Trello card `6a209abd` — the AI Design Review stage (`ai_review`, backend
`mtgai/review/ai_review.py`, the hybrid Design Review council gate) needs a fully
featured wizard tab, matching the polish of the earlier stage tabs. Today
`wizard_ai_review.js` is a placeholder: a collapsible list of `CardReviewResult`s
that fetches a `/api/wizard/ai_review/state` endpoint **that does not exist** (it
`catch`es the 404 and renders an empty state). There is no live council, no
stamps, no manual review.

The card asks for:

1. **Full card grid**, distinguishing reviewed vs to-be-reviewed cards.
2. **Approval / rejection stamps** — green check (approved) or red X + reddened
   background (rejected) with a short rejection reason below.
3. **Live council thumbs up/down** during review (mirror the mechanics council).
4. **Per-card submenu**: Approve / Revise (textbox → in-place LLM revision) /
   Regenerate (flag the slot back to `card_gen`).
5. Revise executes immediately, re-opens for another round.
6. Stop-after toggle + continue button — the shell already handles these.

## How the backend maps to "approved / rejected"

`run_ai_review` (stages.py) runs `review_all_cards` which:
- **Revises in place** (the council's primary action) — applied + saved to the
  card JSON. `card_was_changed=True`.
- A card still rated REVISE after the iteration budget is **unfixable** → flagged
  (`flagged_by="ai_review"`, `regen_reason=...`, status→DRAFT) and the stage sets
  `rerun_from="card_gen"` so the engine loops back.

So the natural verdict mapping for the UI:
- **approved** (green check): `final_verdict == "OK"` and the card is not flagged.
- **rejected** (red X + red bg): the card carries `flagged_by`/`regen_reason`
  (the council couldn't fix it; it's bound for regeneration).

User manual decisions override the AI verdict and must persist. Stored in a
sidecar `<asset>/reviews/decisions.json`:
`{ "<collector_number>": {verdict: "approved"|"rejected", reason: str, source: "user"} }`.
The `/state` endpoint merges this over the AI verdict so a reload keeps the user's
call. (AI verdicts themselves live in the existing `reviews/<cn>.json`.)

## Design — Backend

### 1. Stream hooks for the council (`pipeline/stage_hooks.py`)

New `build_ai_review_hooks(emitter)` → `AiReviewStreamHooks` with:
- `on_reset()` → emits `ai_review_reset`.
- `on_card_start(card)` → `ai_review_card_start` `{collector_number, card_name, rarity, review_tier}` (the card enters review; tab shows a "reviewing" badge + spinner).
- `on_council(cn, event)` → `ai_review_council` `{collector_number, event}` where
  `event` mirrors the mechanics council shape: `{kind:"round", round, verdicts:[...], synth}` etc. The tab renders the live thumbs.
- `on_card_done(result_tile)` → `ai_review_card_done` carrying the per-card
  result tile (verdict, issues, changed, council_reviews summary).

Event names registered in `wizard.js` SSE subscription list.

### 2. Thread hooks through `ai_review.py`

`review_all_cards(... , hooks=None)` → `review_set(..., hooks=None)`. In
`review_set`'s per-card loop:
- `hooks.on_card_start(card)` before reviewing.
- pass an `on_council` callback into `_review_single` / `_review_council`. These
  build the round/verdict events: a single reviewer emits one "round" with one
  verdict slot; the council emits one round with `num_reviewers` verdict slots
  filled as each reviewer returns, then a synth state. Iterations append rounds.
- `hooks.on_card_done(...)` after `_save_review_log`, carrying the result tile
  (built by a shared `_review_tile(result, card)` so `/state` + the stream emit
  the same shape).

`run_ai_review` builds the hooks via `build_ai_review_hooks(emitter)` and threads
them in. `emitter.event("ai_review_reset")` fires once at stage start.

The council/single review loops are best-effort with the hook (a hook raising must
never break review) — wrap each call in try/except like mechanics does.

### 3. `GET /api/wizard/ai_review/state`

Returns:
```
{ cards: ReviewTile[], has_content, summary: {reviewed, revised, ok, rejected, cost_usd},
  ...stage_state_base("ai_review") }
```
Each `ReviewTile` merges:
- the card's display fields (name, mana_cost, type_line, oracle_text, rarity, p/t/loyalty, colors, collector_number) from the live `cards/` pool (the **current** card — post-revision, since revisions are saved in place);
- its AI review (`final_verdict`, `final_issues`, `card_was_changed`, `review_tier`, `council_reviews` summarized to verdict/issue-count) from `reviews/<cn>.json` if present, else `reviewed=False`;
- the **effective decision** (user override from `decisions.json`, else AI verdict→approved/rejected, else "pending" when not yet reviewed);
- whether the card is currently `flagged` (carries `regen_reason`).

Loads card-gen cards via the existing `_load_card_gen_cards` (skips lands), so the
grid shows the reviewable pool. Reviewed status comes from the presence of
`reviews/<cn>.json`.

### 4. Manual action endpoints (all under `guarded_ai` where they call the LLM, all `_heal_failed_stage("ai_review")` on success)

- **`POST /api/wizard/ai_review/approve`** `{collector_number}` — no LLM. Writes a
  `{verdict:"approved", source:"user"}` decision, clears any `regen_reason`/`flagged_by`
  on the card (un-rejects it), heals. Returns the updated tile.
- **`POST /api/wizard/ai_review/revise`** `{collector_number, instructions}` — LLM.
  Mirrors council revise-in-place: builds a revise prompt from the current card +
  the user's instructions, runs one `generate_with_tool` with the review tool
  schema, applies the revision via `_apply_revision`, saves the card. Records a
  `{verdict:"approved", source:"user", reason:"revised by user"}` decision (the
  user revised it → it's now their accepted version; they can revise again).
  Returns the updated tile (with the new card text). Streams council? No — a manual
  revise is a single targeted call; surfaces via `showBusy` indeterminate strip.
- **`POST /api/wizard/ai_review/regenerate`** `{collector_number}` — no LLM. Flags
  the slot for card_gen via `_flag_cards_for_regen` (reason = "User requested a
  from-scratch regeneration in design review"), records `{verdict:"rejected",
  source:"user"}`. This stamps `rerun_from`-style flag on the card; the engine's
  loop picks it up when the stage re-runs / advances. Returns the updated tile.

A new `revise_card_in_place(card, instructions, model, effort)` helper in
`ai_review.py` owns the single-call revise so the endpoint stays thin and the
logic is unit-testable.

### Decisions persistence helpers (`ai_review.py`)
`load_decisions(set_dir)` / `save_decision(set_dir, cn, decision)` — small JSON
sidecar read/write (atomic). Keep it in `ai_review.py` next to the review I/O.

## Design — Frontend (`wizard_ai_review.js`, full rewrite)

Card-tile grid (reuse the `.wiz-cardgen-*` look, scoped to ai-review). Each tile:
- card name / cost / type / oracle / p-t / rarity (like card_gen tiles).
- **Stamp**: approved → a green ✓ badge in the corner; rejected → a red ✗ badge,
  the whole tile background reddened, and the rejection reason in a footer line.
  Pending (not yet reviewed) → muted "to review" tag, dimmed.
- **Live council panel** while the card is under review (`_council` state fed by
  `ai_review_council` events) — round rows with 👍/👎/⟳/· slots, mirroring
  `wizard_mechanics.js` councilRoundRowHtml. A "Reviewing…" pulsing badge.
- **Submenu** (⋯ button → small menu): Approve / Revise… / Regenerate. Revise opens
  an inline textarea + Submit; submit posts `/revise`, repaints the tile from the
  response. Approve posts `/approve`. Regenerate confirms then posts `/regenerate`.

SSE bridge `W.onAiReviewStream(name, data)`:
- `ai_review_reset` — clear live council state, mark all reviewed tiles pending.
- `ai_review_card_start` — mark that card "reviewing", init `_council`.
- `ai_review_council` — append/update the card's `_council` rounds, repaint tile.
- `ai_review_card_done` — store the result on the tile, repaint (stamp appears).

Instance-aware (ai_review is a SNAPSHOT/RERUNNABLE stage — it can appear as
`ai_review.2`), so keep per-instance state in a Map keyed by `tab.id`, exactly
like card_gen/conformance.

Footer (§1): `paused_for_review` + latest → "Next step: <stage>" advance button;
otherwise the standard notes. Reuse `W.advanceStage`.

Form lock (§3): lock the submenu/action buttons while `aiBusy()` (own-lock or
stage running). Manual actions route through `W.runAiAction`.

## Tests

`tests/test_review/test_ai_review_ui.py` (new):
- `test_review_tile_shape` — `_review_tile` merges card + review + decision into
  the documented keys.
- `test_decisions_roundtrip` — `save_decision` then `load_decisions`.
- `test_revise_card_in_place_applies` — monkeypatch `generate_with_tool` to return
  a revised card; assert `_apply_revision` produced the new oracle text.
- `test_effective_decision_mapping` — OK→approved, flagged→rejected, unreviewed→pending,
  user override wins.

(Server endpoints + SSE are integration-level; covered by the manual smoke.)

## Out of scope
- Re-architecting the review loop itself (tier selection, iteration budget) — UI only.
- Materializing reprints / lands into the review pool (lands intentionally skipped).
- Persisting council *transcripts* beyond what `reviews/<cn>.json` already stores.

## Verification
- `ruff check .` / `ruff format .`, `python -c "import mtgai"`, `pytest` from backend.
- Manual: `python -m mtgai.review serve --open`, open a project past card_gen,
  walk the AI Design Review tab: confirm stamps render, council thumbs animate
  (needs a live review run), submenu Approve/Revise/Regenerate work, stop/continue.
  Council animation + revise LLM call need a configured model — flag as
  manual-only (can't unit test the live SSE).
