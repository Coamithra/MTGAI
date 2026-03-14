# Post-Review Finalization Report

**Set:** ASD
**Timestamp:** 2026-03-14T19:04:23.876425+00:00
**Cards processed:** 61
**Cards modified:** 11
**Auto-fixes applied:** 5
**MANUAL errors for review:** 2

## Auto-Fixes Applied

### B-R-01 — Koyl Yrenum, the Vizier
- [rules_text.line_period] Line 3: Does not end with a period or closing quote: "Shroud"

### B-R-02 — The Brain Engine
- [type_check.enchantment_artifact] Enchantment Artifact is an extremely rare type combination (only Theros gods' weapons in all of MTG). Removing 'Enchantment' to make this a plain Artifact.

### L-06 — Descent Waypoint
- [rules_text.card_name_in_oracle] Oracle text uses card name "Descent Waypoint". Fix: replace with "~"
- [rules_text.etb_outdated] Oracle text uses outdated "enters the battlefield" phrasing

### W-C-02 — Fault-Trained Sentinel
- [rules_text.line_period] Line 1: Does not end with a period or closing quote: "Vigilance\nMalfunction 1"

## MANUAL Errors (Human Review Required)

### G-R-02 — The Subsurface Reclaims
- **[rules_text.this_creature]** Line 1: "this creature" should use "~" or "this" only in specific MTG contexts
  - *Suggestion:* Replace with "~" to refer to this card.

### W-C-02 — Fault-Trained Sentinel
- **[power_level.overstatted]** Power 2 + Toughness 3 = 5 on a CMC 2.0 common creature exceeds P+T <= CMC+2 guideline
  - *Suggestion:* Consider raising the mana cost or lowering stats.
