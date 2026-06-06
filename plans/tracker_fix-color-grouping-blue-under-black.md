# Tracker: fix/color-grouping-blue-under-black

Card 6a23e51b — "Card grid color-grouping mis-files blue cards under Black"

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card
- [x] Move card to Doing
- [x] Create worktree and branch

## Phase 2: Research
- [x] Read enums.py Color StrEnum
- [x] Read card.py model (colors/color_identity: list[Color])
- [x] Read validation/schema.py (Card.model_validate path)
- [x] Read validation/mana.py derive_mana_fields
- [x] Read wizard_card_gen.js cardColorKey
- [x] Confirm Pydantic rejects name-form colors (root cause: data persisted out-of-band)

## Phase 3: Design
- [x] Pydantic v2 field validator on Card: normalize name-form -> WUBRG letters for colors + color_identity + ManaCost.colors + CardFace.colors
- [x] Harden cardColorKey() in JS to map names -> letters

## Phase 4: Implement
- [x] Add color-normalization validator (enums.py helper + card.py validator)
- [x] Harden JS cardColorKey

## Phase 5: Verify
- [x] ruff check .
- [x] ruff format .
- [x] python -c "import mtgai"
- [x] pytest (validation suite must not regress)
- [x] Add unit tests in tests/test_validation/

## Phase 6: Review & Ship
- [x] Commit + push
- [x] /review and fix findings
- [x] Pull master into branch
- [x] Re-run lint + tests
- [x] PR + self-merge
- [x] Clean up worktree + branch
- [x] Delete tracker
- [x] Move card to Done + comment
- [x] Final overview
