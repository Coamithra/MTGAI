# Phase 0A Learnings

## What Worked
- Scryfall API is well-behaved: clean pagination, consistent field names, no auth needed
- 100ms rate limiting was sufficient — no rate limit errors across ~30 requests
- `is:booster` filter eliminates most non-playable cards; layout filter catches the rest
- 5-set sample gives robust averages with low standard deviation on most metrics
- Analysis script produces both human-readable output and structured JSON — useful for both documentation and downstream consumption

## Scryfall API Quirks
- Basic lands are counted within the rarity field (they're "common" rarity) — don't double-count when adding basic_lands separately
- `keywords` array is comprehensive but includes non-evergreen mechanics unique to each set. To find "set-specific mechanics," subtract evergreen keywords from the full keywords list
- `card_faces` is null for normal cards, not an empty list — handle with `card.get("card_faces")` not `card.get("card_faces", [])`
- Color pairs in the API use single letters sorted alphabetically (BG, not GB) — consistent sorting needed when grouping

## Data Surprises
- **Multicolor variance is huge**: MKM had 26.1% multicolor cards, LCI only 9.9%. This is the most theme-dependent variable.
- **LCI is an outlier** on several axes: 291 cards (largest), 113 commons, 15.1% colorless (highest), 44 artifact-only cards. Its artifact/transform DFC theme inflated these numbers.
- **Removal counts are higher than expected** (~78/set avg) because the regex is broad — "deals X damage" matches many creatures with ETB/attack triggers, not just dedicated removal spells. The count is useful as a relative comparison between sets but should not be taken as the "number of removal spells."
- **First strike and hexproof are rarer than expected**: ~1.2 and ~0.8 per set respectively. These have been shifted to less frequent use in modern design.
- **Planeswalkers are scarce**: only 1-2 per set in booster-eligible cards. Many planeswalkers live in Commander products now.
- **Legendary creatures are abundant**: 19-43 per set (avg 28). Recent sets push legendary status broadly for Commander appeal.

## Parameter Adjustments for Downstream
- Set template uses avg=277 cards, but our target of 280 is within range — no scaling needed
- Removal detection regex should be refined in Phase 1C validators to distinguish "true removal" from "damage-dealing creatures"
- Multicolor percentage should be a set-level design decision, not a fixed target (range 10-26%)
- Common count of ~95 is lower than the "101 commons" often cited — likely because some recent sets use Play Booster structure differently

## Anti-patterns to Avoid
- Don't treat keyword counts as exact — the Scryfall `keywords` field is comprehensive but includes variant forms
- Don't assume basic lands are separate from rarity counts
- Don't hardcode "10 signpost uncommons" — LCI only had 9 color pairs covered
- Don't use exact averages as rigid targets — use them as centers of acceptable ranges

## Verification Results
- All 5 set card counts match Scryfall set pages exactly
- Color distribution sums to ~100% (within 0.2% rounding)
- Rarity counts sum to total (basic lands are within common count)
- Template produces a valid 277-card allocation
- Template ranges are not so tight they'd reject real sets (all 5 sets fall within ranges)
- Draft booster can be constructed from the template allocation
