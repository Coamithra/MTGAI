# Tracker: fix/literal-backslash-n

Card 6a297bb1 — Normalize literal backslash-n from LLM output at the model boundary.

## Phase 1: Pick Up the Card
- [x] Claim the card (two-phase handshake — claim comment posted, no contender)
- [x] Pull latest master
- [x] Read the card + comments (user-agreed design in latest comment)
- [x] Create worktree and branch (`fix/literal-backslash-n`)

## Phase 2: Research
- [x] Read validation framework (`validation/__init__.py`, validate_card sequence, _AUTO_FIX_REGISTRY)
- [x] Read neighboring validators (rules_text, keyword_ordering, text_overflow) for style
- [x] Read mechanics persistence path (mechanic_generator.persist_mechanic_selection)
- [x] Read render-time backstop (rendering/text_engine.py:278)
- [x] Read existing validator tests for layout/helpers

## Phase 3: Design
- [x] Settle module/function names, ordering in sequence, registry key
  - New module `validation/whitespace.py`: `normalize_escaped_whitespace(text)` (canonical),
    `validate_escaped_whitespace(card)` (AUTO, per-field on oracle_text/flavor_text),
    `fix_escaped_whitespace(card, error)` (fixes `error.field` via model_copy).
  - Error code `whitespace.literal_escape`; runs FIRST in validate_card (before mana) so
    its fix applies before line-structure-dependent fixers re-read the card.
  - `persist_mechanic_selection` normalizes each candidate's example_cards (non-mutating
    copies) via the SAME `normalize_escaped_whitespace` before writing candidates/approved.
- [x] (User alignment already done — design fixed in card comment)

## Phase 4: Implement
- [x] New AUTO check + fixer (canonical normalize function, one implementation)
- [x] Register early in validate_card sequence + _AUTO_FIX_REGISTRY
- [x] Reuse fixer from mechanics persistence path
- [x] Update CLAUDE.md (validate_card sequence + new whitespace check documented)
- [x] Review follow-up: pre-normalize pass in validate_card_from_raw + finalize_card so
      line-based validators compute findings on real lines; literal \r handled; TEXT_FIELDS public

## Phase 5: Verify
- [x] ruff check . / ruff format . clean
- [x] Smoke import
- [x] Full pytest from backend/ (2624 passed pre-review; re-run after review fixes)
- [x] Spot-check the diff

## Phase 6: Review & Ship
- [x] Commit + push
- [x] /review (fresh-agent peer review), fix findings
- [ ] Pull master into branch, re-run lint + tests
- [ ] PR + self-merge, fast-forward root master
- [ ] Clean up worktree + branch
- [ ] Delete tracker doc
- [ ] Move card to Done + comment PR link
