# AI Design Review: regen-instance round conflation + safety-valve misbranding (card 6a29a27f)

## Context
On an inserted `ai_review.N` instance (a regen bounce), the AI Design Review tab
mis-presents cards. Three distinct symptoms, all **presentation** (no engine /
loop-semantics change):

0. **(PRIMARY) Stale verdict on a regenerated card.** A card the loop bounced
   back to card_gen gets a fresh body, but `reviews/<cn>.json` is keyed by
   collector number and merged content-blind, so the tab still paints the
   *predecessor's* red-X "rejected" stamp, "WHY REJECTED…" reason, and
   "Tweaked by AI" / WHAT CHANGED diff — all belonging to the archived old body.
   Such a card should RESET to bare "to review" until the new round verdicts the
   new body.
1. **Round conflation / headline.** The instance only re-reviews the
   regenerated subset, but the headline reports the full round-1 tally.
2. **Safety-valve misbranding.** Cards carrying a `flagged_by="conformance"`
   `regen_reason` that the conformance gate ACCEPTED at budget exhaustion (the
   documented safety valve — "NOT a quality bar") show a red-X design rejection
   with "WHY REJECTED: SPEC wants CMC6…". The design council voted OK; this is an
   unresolved *upstream* flag, not a design rejection.

## Root cause
`reviews/<cn>.json` (AI verdict) and `regen_reason`/`flagged_by` (gate flags) are
both keyed by collector number and merged onto the live card by
`server._effective_decision` / `_ai_review_tiles` content-blind. The codebase
already has the exact staleness primitive for USER decisions
(`save_decision` stamps `card_signature`; `_effective_decision` ignores a
signature-mismatched decision via `decision_is_stale`). The AI-verdict path has
no equivalent. The `reviewed.json` sidecar already records the signature each
card was reviewed under (`record_reviewed`, line ~2666) — the same comparison the
resume-skip uses (`_persisted_revise_unfixable`, line ~2782).

## Design (server-side; `pipeline/server.py` + small helper in `review/ai_review.py`)

### P0 — review staleness
- New `ai_review.review_is_stale(reviewed_sig: str | None, card: dict) -> bool`:
  mirrors `decision_is_stale` — True when a recorded signature exists and no
  longer matches `card_signature(card)`; False when no signature (legacy /
  pre-tracking → keep current behavior).
- `_ai_review_load` also loads `reviewed.json` (`load_reviewed`) and returns it.
- `_ai_review_tiles`: for each card, if its review is stale (recorded sig ≠ live
  sig), pass `review=None` to `review_tile` (bare tile) **and** drop the AI
  verdict from `_effective_decision` so the stale verdict can't paint. A user
  decision is still honoured if non-stale (its own signature check already
  handles the regen case). A still-`flagged` card with a stale review surfaces as
  the flagged/conformance state (P2), not the old verdict.
- Net effect: a regenerated-but-not-yet-re-reviewed card → `reviewed:false`,
  bare text, "To review"; counts as `pending` in the headline.

### P2 — conformance-accepted chip vs design rejection
- `_effective_decision`: when a card is `flagged` AND `flagged_by ==
  "conformance"` AND the AI review verdict is OK/absent (i.e. design review did
  NOT reject it), return a new verdict bucket
  `{"verdict": "flagged_upstream", "reason": regen_reason, "source":
  "conformance", "gate": "conformance"}` instead of `"rejected"`.
  - A genuine design rejection (`flagged_by == "ai_review"`, OR a present
    REVISE AI verdict, OR a user "rejected" decision) keeps `"rejected"`.
  - Carries the gate label so the tab attributes the WHY correctly.
- `_ai_review_summary`: count `flagged_upstream` separately (`upstream_flagged`),
  NOT in `rejected`. Keep `approved`/`rejected`/`pending`/`total`.

### JS (`wizard_ai_review.js`)
- Handle the `flagged_upstream` verdict: amber chip "Conformance flag (accepted)"
  + the reason attributed to the upstream gate, NOT the red-X "Why rejected" box.
  New tile class `flagged-upstream` (amber border) + amber stamp glyph.
- `effective()` fallback (live-streamed tiles w/o `effective`) unchanged — the
  live council stream only fires for cards under review this round, which are by
  definition fresh (not stale, not upstream-flagged).
- Summary bar: add an "N upstream flag" stat when > 0.
- Filter bar: keep existing; `flagged_upstream` is neither approved nor rejected
  nor pending — add a "Flagged upstream" filter chip shown only when count > 0.
- Sort priority: upstream-flagged sits with the needs-attention group (between
  to-review and approved) — it's informational, not actionable by this stage.

## Out of scope
- Any engine change to clear/demote `regen_reason` at budget exhaustion (the
  card floats it as a possibility; the chosen direction is presentational only —
  clearing it would change loop semantics).
- Instance-scoped reviews/ sidecar (reviews stay shared; staleness handles the
  cross-instance display correctly).

## Tests (`tests/test_pipeline/test_wizard_ai_review.py`)
- `test_regenerated_card_with_stale_review_resets_to_pending`: write card + OK
  review + `reviewed.json` recording the OLD signature, then rewrite the body →
  state reports `reviewed:false`, `effective.verdict == "pending"`, no rejected.
- `test_legacy_review_without_recorded_signature_still_shows_verdict`: no
  `reviewed.json` → OK still maps to approved (back-compat; existing tests).
- `test_conformance_accepted_flag_renders_as_upstream_not_rejected`: flagged_by
  conformance + OK/absent AI verdict → `effective.verdict == "flagged_upstream"`,
  `gate == "conformance"`, reason carried; summary `upstream_flagged == 1`,
  `rejected == 0`.
- `test_ai_review_flag_still_rejected`: flagged_by ai_review → still `rejected`.
- `test_reviewed_signature_match_keeps_verdict`: recorded sig == live sig → OK
  stays approved.

## Verification
- ruff check/format, full pytest from backend/.
- JS: no harness — manual-verification note (regen instance tab: regenerated
  cards show bare "to review"; conformance survivors show amber chip).
