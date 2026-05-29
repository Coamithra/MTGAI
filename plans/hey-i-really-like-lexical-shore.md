# Plan: Council-grade per-mechanic review

## Context

Mechanics are the core of a set, but the LLM still produces mediocre ones. The card pipeline
has a review system the user likes — a tiered **council** (3 independent reviewers + a 2-of-3
consensus synthesizer) with a **revise-in-place iteration loop** (`_review_council` in
[ai_review.py:614](backend/mtgai/review/ai_review.py#L614)). Mechanics, by contrast, get only a
**single-shot, single-reviewer, theme-free soundness check** before each draft joins the candidate
pool (`review_mechanic` in [mechanic_generator.py:574](backend/mtgai/generation/mechanic_generator.py#L574)).
It catches wording/templating/loop problems but never iterates, never cross-checks, and explicitly
does not judge whether a mechanic is *interesting, elegant, or unique*.

**Goal:** Upgrade the per-mechanic review into a full council + iteration loop modelled on the card
council, so every candidate mechanic is pressure-tested on: **playable, correctly worded,
interesting, not self-contradictory, unique, elegant**.

**Decisions locked with the user:**
- **Per-mechanic council only** — no new slate-level holistic pass, no new re-entrant regen stage.
  Inter-candidate overlap stays the picker's job (`select_best_mechanics` already weighs "non-overlap").
- **Always full council** — every candidate gets all 3 reviewers + synthesis (not tiered by complexity).
- **Theme-free** — reviewers judge each mechanic cold (the deliberate anti-"but it fits!" guard).
  "Unique" therefore means *not a reskin of a printed Magic keyword* (judged from the reviewer's own
  MTG knowledge), reviewing each mechanic in **isolation** — exactly as today.

## Update — 2026-05-29: prototype findings (`mtg-mech-lab/`)

Before touching the real pipeline, the prompts + flow were prototyped standalone in
[`mtg-mech-lab/`](../mtg-mech-lab/README.md) (reuses `generate_with_tool`; defaults to the same
local Gemma the `mechanics` stage uses). First end-to-end cycle results:

- **✅ The expanded six-standard reviewer prompt works.** A textbook-mediocre generated mechanic
  ("Drift" = *"draw a card"* reworded) was independently flagged by all 3 reviewers as a reskin
  (unique), self-contradictory (rationale ≠ reminder/examples), ambiguous keyword templating
  (wording), and a flavorless stat-bump (interesting). This validates the checklist below.
- **❌ The single-call synthesizer (re-emit the whole `revised_mechanic`) truncates on local Gemma.**
  Re-emitting the full mechanic + both example cards + consensus prose, with all 3 reviews as input,
  loops to the token cap and returns nothing parseable (8192 completion tokens, empty text + zero
  tool-calls, `finish_reason=length`). Generation and the 3 reviewers work because their outputs are
  bounded. **This is the card-council shape the Design section below mirrors — so that shape must change
  for the local-default `mechanics` model.**

**Revised synthesis design (supersedes the single-call synthesis in step 3 / the tool schemas below):**
split the synthesizer into **two bounded calls**, each matching a shape Gemma already handles:
1. **Consensus** (small output): `{synthesis, consensus_issues[] (with agreement counts), verdict,
   revision_brief}` — no full mechanic re-emit.
2. **Revise** (shaped exactly like generation, which works): given the original mechanic + the
   `revision_brief`, emit `{revised_mechanic, change_summary}`. This is essentially "regenerate this
   mechanic applying these fixes" and maps cleanly to the pipeline's existing regenerate-with-
   `regen_reason` pattern. Skip it entirely when consensus finds nothing actionable.

The iteration loop then re-reviews the revised mechanic each round (verdict comes from the reviewers,
not the synthesizer). Still TODO in the prototype: implement + validate this split, add a hand-authored
good/bad draft set to measure catch-rate vs false-positive-rate, then port back. The rest of this plan
(council structure, theme-free checklist, safe fallback, signature/return-shape preservation) stands.

## Update — 2026-05-29 (final): the council becomes a regenerate-GATE — supersedes the synthesis design below

After prototyping the full loop in [`mtg-mech-lab/`](../mtg-mech-lab/README.md) across ~6
Transformers-theme iterations (lab commits `e440bf6`, `a9337c5`, `53837aa`), the picture and the user's
decisions changed enough to **replace the synth-based design below**.

### What the prototype established
- **The six-standard reviewer prompt is excellent** — validated v1 to port (`mtg-mech-lab/prompts/review_system.txt`).
- **The synth (revise-in-place) is the weak, unreliable link.** The truncation turned out to be
  *reasoning-budget overrun* (local Gemma is a reasoning model whose chain-of-thought ate the token
  budget before the answer — see [`learnings/reasoning-budget-overrun.md`](reasoning-budget-overrun.md));
  fixing the budget unblocked it, BUT even then, and even with explicit anti-regression rules, the synth
  still ~⅓ of the time **stripped existing definitions, re-introduced `[placeholder]`s, or claimed fixes
  it never made**. A synth that grades its own work also needed a **re-review** net (exit on *reviewer*
  consensus, not the synth's self-verdict).
- **An originality gate in the GENERATION prompt is what actually lifted idea quality** — naming the
  tired patterns (sac-for-mana, stat-pump, equip-move, temp-keyword) and demanding a real recurring
  decision. It produced the run's standout, **Integrate** (a creature that sacrifices itself to become a
  bespoke Equipment — on-theme, a genuine keep-or-convert decision).
- **gen-temp 0.9 beats 1.1** (1.1 clustered + degraded templating without adding novelty). Keep 0.9.

### Locked decisions (these supersede the synth-based Design section)
1. **Revise → regenerate.** Drop the synthesizer entirely. The council is a **pass/fail quality gate**,
   not a fixer. A flagged candidate is **discarded and regenerated from scratch**, threading the
   council's reasons into the gen prompt — reusing the proven `card_gen` regenerate-with-`regen_reason`
   pattern. This removes the two-call consensus→revise machinery from this plan and sidesteps the synth's
   unreliability. (A regenerated candidate is "re-reviewed" simply by passing through the gate like any
   fresh draft, so no separate re-review loop is needed.)
2. **The pool must be 2N *working* mechanics.** `generate_mechanic_candidates` keeps generating /
   regenerating until the pool holds `candidate_count` (= 2N) candidates that all **pass council**
   (attempt-capped). This matters because `pick_best_mechanics` selects N on **theme fit** — the
   dimension the theme-blind council deliberately can't judge. A pool of 2N *sound* mechanics is what
   gives the theme-fit pick real choice. **Small-set caveat:** 2N scales with N, so a small set gets a
   thin pool and weaker theme-fit selection — consider a higher multiple or a floor for small N (open).

### Revised flow
generate candidate → **council gate** (3 theme-free reviewers, six standards) → consensus OK? keep :
discard + regenerate-with-reasons → repeat per slot until 2N pass (attempt cap) → `pick_best_mechanics`
selects N on **theme fit** + diversity → persist `approved.json`.

### Revised port (replaces the synth pieces)
- **Port from the lab:** `gen_system` pitfalls + originality gate → `mechanic_system.txt`; six-standard
  `review_system` → `mechanic_review_system.txt`; council-member `review_user` → `mechanic_review_user.txt`.
  **No synth prompts** (no consensus/revise files).
- **Schemas:** add `MECHANIC_REVIEWER_TOOL_SCHEMA` (`{verdict, issues}`); **drop** the synth/consensus/
  revise schemas. Keep `MECHANIC_ITEM_SCHEMA` (gen + regen).
- **Orchestration moves up a level.** The gate+regen loop lives in **`generate_mechanic_candidates`**
  (not inside `review_mechanic`): review each draft; on consensus REVISE, regenerate that slot with the
  reasons rather than tweak it. `review_mechanic` becomes a `council_gate(draft) -> {verdict, issues}`
  helper with no mechanic re-emit. Reviewers run **sequentially** — the app-wide AI mutex forbids
  parallel calls.
- **Verdict → selection:** stamp `_review_verdict`; the pool is all-OK by construction, so the pick
  selects mainly on theme fit (pass verdicts through as a guard).
- **Budgets:** reviewers + gen at `STANDARD` (no synth → no `HEAVY` need here; the reasoning-budget
  headroom still matters for gen on local Gemma).
- **Streaming:** existing `on_draft`/`on_finalized` hooks already re-fire on a regenerated slot; add the
  verdict to the finalized event if useful.

### Updated files to touch
- `backend/mtgai/generation/mechanic_generator.py` — reviewer schema, `council_gate`, regen-until-2N-pass
  loop in `generate_mechanic_candidates`, verdict stamp; remove the synth schemas + `review_mechanic`'s tweak path.
- `backend/mtgai/pipeline/prompts/` — `mechanic_system.txt`, `mechanic_review_system.txt`,
  `mechanic_review_user.txt`. (No consensus/revise prompts.)
- `backend/mtgai/pipeline/stages.py` — `run_mechanics` (cancellation between regens, phase strings).
- `backend/mtgai/pipeline/stage_hooks.py` — verdict in finalized event (optional).
- `backend/tests/test_mechanic_generator.py` — replace review_mechanic tests with council-gate +
  regen-until-pass + verdict tests.

### Open questions
- **Regen attempt cap** when the model can't produce 2N passing (keep best-effort flagged + human pause?
  accept a smaller pool?) — mirror `card_gen`'s `MAX_REVIEW_ROUNDS`.
- **Small-set pool multiple** (2N vs 3N vs a floor) so theme-fit selection has room.
- **Cost.** Council on every draft + regens, sequential (AI mutex), ~7–8k reasoning tokens/call on local
  Gemma (~minutes each). Options: a cheaper single-reviewer gate for pool culling + full council only for
  finalists; or assign a faster/stronger model to `mechanics`. The stronger-model path is also the route
  to *consistent* quality (local Gemma is ~⅔ rule-consistent and creatively capped).

## Design (SUPERSEDED — see the "final" update directly above; kept for history)

Replace the body of `review_mechanic()` with a council orchestrator while keeping its **public
signature and return shape identical** — `{mechanic, review_notes, input_tokens, output_tokens}`.
That single guarantee means every call site, the `_review_notes` stamp, the `on_finalized` hook, and
the wizard's "Reviewer tweak: …" line keep working with **zero downstream changes** (call site:
[mechanic_generator.py:1182](backend/mtgai/generation/mechanic_generator.py#L1182)).

Mirror `_review_council`'s flow, mechanic-specific and theme-free:

1. **Phase 1 — 3 independent reviewers.** Each gets the same theme-free review prompt + the rendered
   mechanic block (`_format_mechanic_for_review`, already exists) and returns `{verdict: OK|REVISE, issues[]}`.
   Run with a modest temperature (~0.4) so the three are not identical. Each call wrapped in try/except —
   a failed reviewer is skipped, not fatal.
2. **Skip synthesis if all 3 say OK** → return the draft unchanged, empty `review_notes` (mirrors
   [ai_review.py:710](backend/mtgai/review/ai_review.py#L710)). This is the common, cheap path.
3. **Phase 2 — synthesizer.** Sees the original mechanic + all 3 reviews, applies a **2-of-3 consensus
   filter** (act only on issues ≥2 reviewers raised; discard lone-reviewer issues as likely false
   positives), and produces an improved mechanic + verdict + changelog.
   ⚠️ **See the 2026-05-29 update:** on the local `mechanics` model the single-call form (re-emit the
   full `revised_mechanic`) truncates — implement this as the **two-call consensus → revise split**
   described above. The single-call schema below is the original card-council shape, kept for reference.
4. **Iteration loop** (`MAX_MECHANIC_REVIEW_ITERATIONS`, propose **3**): re-review the `revised_mechanic`;
   if still REVISE, revise again until OK or budget exhausted. Keep the latest revision (mirrors
   [ai_review.py:749](backend/mtgai/review/ai_review.py#L749)). Synthesis + iterations run at a lower
   temperature (~0.2).
5. **Safe fallback preserved.** Any failure / malformed output at any phase falls back to the best
   mechanic so far (original draft if Phase 1 collapses) — a bad review never destroys a good draft.
   The existing **anti-rename guard** ([mechanic_generator.py:626](backend/mtgai/generation/mechanic_generator.py#L626))
   is applied to the final mechanic.
6. **Output.** `review_notes` = the synthesizer's changelog (empty when nothing changed); token totals
   summed across all council + iteration calls. All `generate_with_tool` calls keep passing
   `log_dir` so transcripts land in `<asset>/mechanics/logs` as today.

### Expanded review checklist (theme-free)

Rewrite `mechanic_review_system.txt` to grow today's checklist (reminder text, soundness, color/pie,
complexity honesty, example cards) with explicit dimensions for the qualities the user named:
- **Interesting** — does it create a real decision / texture, or is it a flavorless stat bump?
- **Elegant** — minimal rules surface for the gameplay it buys; no needless clauses.
- **Self-consistent** — reminder text, cost/trigger structure, and example cards all agree.
- **Unique** — not a thin reskin of a printed Magic keyword (name it if so, e.g. "this is Convoke").

Keep the existing "What NOT to change" rules (no rename, no rarity-distribution edits, no keyword_type
edits) and the verdict/issues output contract. Reviewers and the synthesizer share this system prompt.
(The prototype's `review_system.txt` is the validated v1 to port from.)

### New/changed pieces (all in `mechanic_generator.py` + prompts)

- **Constants:** `MECHANIC_COUNCIL_SIZE = 3`, `MAX_MECHANIC_REVIEW_ITERATIONS = 3` (tunable).
- **Tool schemas:** add `MECHANIC_REVIEWER_TOOL_SCHEMA` (`{verdict, issues}`) for Phase-1 critique. For
  synthesis, per the 2026-05-29 update, prefer **two** schemas — `MECHANIC_CONSENSUS_TOOL_SCHEMA`
  (`{synthesis, consensus_issues[], verdict, revision_brief}`) and `MECHANIC_REVISE_TOOL_SCHEMA`
  (`{revised_mechanic, change_summary}`, `revised_mechanic` reusing the existing `MECHANIC_ITEM_SCHEMA`)
  — over the original single `MECHANIC_SYNTHESIS_TOOL_SCHEMA`. The current `MECHANIC_REVIEW_TOOL_SCHEMA`
  is superseded; remove it.
- **Prompt builders:** `build_review_prompts` stays for the reviewer pair; add a
  `build_consensus_prompts(mech, reviews)` (renders the original mechanic + the 3 critiques with the
  2-of-3 instruction) and a `build_revise_prompts(mech, revision_brief)`.
- **New prompt files** under `backend/mtgai/pipeline/prompts/`:
  `mechanic_review_system.txt` (expanded checklist + verdict/issues contract — overwrite),
  `mechanic_review_user.txt` (add verdict/issues instruction — overwrite),
  `mechanic_consensus_user.txt` + `mechanic_revise_user.txt` (new — port from the prototype's reshaped
  synth prompts once validated; both reuse the review system prompt).

### Files to modify

- `backend/mtgai/generation/mechanic_generator.py` — schemas, prompt builders, council orchestrator
  inside `review_mechanic`. (Signature + return shape unchanged; call site untouched.)
- `backend/mtgai/pipeline/prompts/mechanic_review_system.txt`, `mechanic_review_user.txt` — overwrite.
- `backend/mtgai/pipeline/prompts/mechanic_consensus_user.txt`, `mechanic_revise_user.txt` — new.
- `backend/tests/test_mechanic_generator.py` and `backend/tests/test_pipeline/test_wizard_mechanics.py`
  — update/extend (see below).

### Explicitly out of scope (per the user's choices)

- No slate-level holistic review pass; no new pipeline stage; no re-entrant regen loop / engine wiring.
- No theme/archetype context in the reviewer. No wizard frontend changes (return shape is identical, so
  the "Reviewing…" badge and "Reviewer tweak:" line already cover it — the badge simply stays up a bit
  longer while the council runs).

## Cost / model note

Always-full-council multiplies the mechanics stage's LLM calls per candidate (3 reviewers, +1–2
synthesis calls and up to 2 more iterations only when a revision is needed) — roughly 4–6× today's
per-mechanic cost, over a pool of ≤ ~12. This is the accepted trade for the set's most important stage;
the council runs on the active project's `mechanics` model assignment, and the per-call safe-fallback
keeps it robust to local-model flakiness. The prototype confirms the local default works for generation
+ reviewers; the synthesis reshape (above) is what keeps it robust there. Worth assigning a capable
model to `mechanics`.

## Verification

1. **Unit tests** (`pytest` from `backend/`, monkeypatching `generate_with_tool` as the existing tests
   do): all-3-OK → no synthesis, draft returned unchanged; mixed verdicts → consensus runs and the
   2-of-3 filter drops a lone-reviewer issue; consensus actionable → revise call fires; REVISE→OK across
   iterations; iteration budget exhausted → keeps last revision; Phase-1 total failure → original draft
   returned; revise-call failure → keeps prior mechanic; anti-rename guard still reverts a renamed
   mechanic. Update any existing `review_mechanic` test that assumed a single LLM call.
2. **Lint:** `ruff check .` / `ruff format .` from `backend/`.
3. **End-to-end:** `python -m mtgai.review serve --open`, open a project, run/refresh the Mechanics
   stage. Confirm candidates stream in with the "Reviewing…" badge then resolve with a "Reviewer tweak:"
   note when revised; confirm `<asset>/mechanics/logs` shows 3 reviewer transcripts + the consensus/
   revise transcripts per revised candidate, and that obviously-broken seeds get fixed (e.g. a reskinned
   keyword gets flagged/reworded, a contradictory reminder gets reconciled).
