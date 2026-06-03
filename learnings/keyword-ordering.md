# MTG Keyword Ability Ordering Convention

## Rule
Standard evergreen/keyword abilities should appear **before** complex triggered/activated abilities in oracle text. This matches official MTG templating.

## Example (Wrong — Koyl Yrenum current)
```
Whenever another creature dies, you may pay {B}. If you do, look at the top two cards...
When Koyl Yrenum dies, look at the top three cards...
Shroud
```

## Example (Correct)
```
Shroud
Whenever another creature dies, you may pay {B}. If you do, look at the top two cards...
When Koyl Yrenum dies, look at the top three cards...
```

## Ordering on Real MTG Cards
1. **Evergreen keywords** — flying, first strike, double strike, deathtouch, haste, hexproof, indestructible, lifelink, menace, reach, shroud, trample, vigilance, defender, flash, ward
2. **Set/deciduous keywords** — e.g. Salvage, Malfunction, Overclock (our custom mechanics)
3. **Triggered abilities** — "When...", "Whenever...", "At the beginning of..."
4. **Activated abilities** — "{cost}: {effect}"
5. **Static abilities** — continuous effects
6. **Flavor/reminder** — at the bottom

Multiple keywords on one line are comma-separated (e.g. "Flying, vigilance").

## Where to Fix
This is a card generation issue, not a rendering issue. The LLM prompts should instruct the model to place keyword abilities first, and the validation cascade should catch and auto-fix any that slip through.

## Status: RESOLVED (feat/keyword-ordering-validator)
Both fixes landed:
- **Validator (durable backstop):** `mtgai/validation/keyword_ordering.py` — an AUTO check + fixer wired into the `validate_card` runner and the auto-fix registry (`validation/__init__.py`). It flags a keyword-ability line sitting below a complex ability and stable-partitions keyword lines to the top, moving each line whole so injected reminder text is preserved. Keyword vocabulary reuses `rules_text.ALL_KEYWORDS` (evergreen + the set's custom mechanics); `shroud` was added to `EVERGREEN_KEYWORDS` (it was missing).
- **Prompt instruction:** the card-gen system prompt (`research/prompt-templates/system-prompt-v1.md`, MTG Rules Reference section) now tells the model to template keywords at the top of the textbox.
- **Tests:** `TestKeywordOrdering` in `tests/test_validation/test_validators.py`.
