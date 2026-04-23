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
This is a card generation issue, not a rendering issue. The LLM prompts in `mtgai/generation/prompts.py` should instruct the model to place keyword abilities first. Could also be caught by the `rules_text` validator as an ordering check.
