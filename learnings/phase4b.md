# Phase 4B Learnings: AI Design Review

## Haiku dry-run strategy works

Running the full review pipeline capped to Haiku first ($0.58 for 59 cards) before the real Opus run catches pipeline bugs and validates infrastructure without bleeding money. Two Haiku runs found and fixed:
- Council synthesis crash (missing `verdict` key in tool output — Haiku sometimes omits required fields)
- Cost calculation using wrong model (logged requested model, not effective model after capping)
- Review logs recording `claude-opus-4-6` when actually running Haiku

## Validator warnings in review prompts are valuable

Adding `generation_attempts[].validation_errors` to the review prompt helped the AI reviewer catch real issues it would have missed otherwise:
- B-R-01: hexproof + indestructible in black (color pie validator flagged, reviewer fixed)
- X-U-01: informal mana language (validator flagged, reviewer fixed)
- Text overflow issues on 3 cards (validator flagged, reviewer trimmed)

## False positive cleanup matters

Several validator checks produced noise that confused the LLM reviewer:
- **`card_types` parsing bug**: Cards loaded from disk had empty `card_types` despite `type_line` saying "Creature". Fixed by having `validate_type_consistency` call `_parse_type_line` when `card_types` is empty. Cleaned 21 card files.
- **Malfunction enters-tapped redundancy**: Validator flagged "enters tapped" inside reminder text as redundant. This was a set-specific check that doesn't belong in the general validator — removed entirely. Cleaned 6 card files.
- **Reminder text detection**: "Oracle text contains what looks like reminder text" fires on every card with Salvage/Malfunction/Overclock. That's correct behavior — the reminder text IS supposed to be there. These are noise for the reviewer.

## Review log format

- JSON logs needed for machine consumption (resumability, summary report generation)
- Markdown logs alongside JSON for human reading — much more useful than trying to read escaped JSON
- Code fences (```` ``` ````) cause horizontal scrolling in many markdown viewers — use blockquotes (`>`) instead for card text
- Prompts in collapsible `<details>` blocks keep the markdown scannable

## `generate_with_tool` should return effective model

Added `"model"` to the return dict so callers know what model actually ran after `MTGAI_MAX_MODEL` capping. Essential for correct cost calculation and logging.

## Future idea: Differentiated council viewpoints

Currently all 3 council reviewers get the identical prompt, so they tend to converge (especially weaker models like Haiku). This undermines the 2-of-3 consensus filter — if they all see the same thing, the filter adds cost without value.

**Proposed improvement**: Give each reviewer a distinct lens:
1. **Rules/Templating reviewer** — oracle text correctness, keyword interactions, MTG templating, reminder text
2. **Balance/Limited reviewer** — power level vs CMC/rarity, limited playability, comparison to real MTG cards
3. **Design/Creative reviewer** — card identity, kitchen sink, color pie, flavor, mechanical elegance

**Caveat**: Needs an A/B test before adopting. Phase 1B taught us that assumptions about review strategies are often wrong (e.g., detailed checklists detected everything but produced the worst fixes). Good candidate for testing when scaling to 280 cards.
