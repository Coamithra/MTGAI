# Resource-economy / enablement-coverage check (card 6a29d07d)

## Context
Conformance hunts excess synergy; the council checks rules-soundness. Nobody counts
**enablement coverage** — whether a consumed resource (Food, Treasure, custom set tokens)
actually has enough makers, in the right colors. The user's "does anything even create Food
tokens?" had no automated answer. This adds an algorithmic (zero-LLM) economy analysis beside
the duplicate scan in the conformance stage.

## Design

### New module: `mtgai/analysis/resource_economy.py`
Pure-Python, no LLM. Public entry: `analyze_resource_economy(cards, mechanics) -> (report_dict, warnings)`.

1. **Resource discovery** (`discover_resources`):
   - Predefined MTG token nouns: Food, Treasure, Clue, Blood, Map, Gold, Powerstone, Incubator,
     Junk, Shard, Walker, Role, etc. (a curated `PREDEFINED_TOKENS` set).
   - Set-custom token types parsed from approved mechanics' `reminder_text` via
     `create ... <Name> token` capture (Squall → Cloud).
   - `create ... <Name> token` patterns mined from the pool's own oracle text.
   - Canonical capitalized noun; case-insensitive dedup.

2. **Maker/consumer extraction per card** (`scan_card`):
   - Strip reminder (parenthesized) text first — matches project convention; mechanic-driven
     consumption is joined via the mechanic-coverage channel, not double-counted from injected
     reminders.
   - Maker: `create [a/an/two/N] [adjectives] <Resource> token(s)` → count makers.
   - Consumer: `sacrifice [a/an/N/...] [adjectives] <Resource>` (token optional) → consumer.
   - A card can be both. Skip basics + reprints (`filter_gate_cards`).
   - Tally per color (each of the card's `colors`, or "C" for colorless) and per rarity.

3. **Keyword-mechanic coverage** (`scan_mechanics`):
   - Per approved mechanic: count carrier cards (oracle text starts with / contains the keyword).
   - If a mechanic's reminder text `create`s a resource → join mechanic as a maker source.
   - If a mechanic's reminder text `sacrifice`s a resource → join mechanic as a consumer source.

4. **Verdicts** (`_warnings`):
   - Always produce the economy report (resources × {makers, consumers, per-color, per-rarity,
     joined mechanics}).
   - WARN: a resource with `consumers >= MIN_CONSUMERS_TO_WARN (3)` and `makers <= 1`.
   - WARN: a resource whose consumers' dominant color is disjoint from its makers' colors
     (color-mismatch) when both sides are non-trivial (consumers >= 2, makers >= 1).
   - V1 produces NO regen flags and does NOT bounce — advisory only.

### Integration: `stages.run_conformance`
- Call `analyze_resource_economy(cards, mechanics)` cheaply (no lock contention; pure CPU)
  right after the duplicate scan, before the LLM steps.
- Build an `economy_step = {"id": "economy", "label": "Resource Economy", "report": ..., "warnings": ...}`
  and append it as the THIRD entry in `artifacts["steps"]`.
- Emit it live via the existing `conformance_step` SSE event.

### Tab JS: `wizard_conformance.js`
- Handle `conformance_step` for `step.id === 'economy'` in `onConformanceStream` (store on instance).
- Render an economy panel below the per-card checklist: a table of resources (rows) ×
  makers / consumers / per-color breakdown, plus a warning callout per warning.
- Also rebuild from `result.steps` on reload.

## Tests: `backend/tests/test_analysis/test_resource_economy.py`
- discovery from mechanics reminder text (Squall→Cloud) + pool patterns
- maker extraction: "create two Food tokens", "create a Food token"
- consumer extraction: "Sacrifice a Food token: ..."
- a card that does both
- healthy economy → no warnings
- zero/one-maker with >=3 consumers → warns
- color-mismatch → warns
- basics + reprints skipped

## Out of scope
- Regen flagging / pipeline bounce (V1 is advisory).
- LLM-based semantic resource detection.
