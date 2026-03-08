> **STATUS: APPLIED** — All items in this document have been integrated into the master plan and individual phase plans as of 2026-03-08. This file is retained for reference only. Do not use this as a source of truth — refer to the individual phase plans instead.

# Cross-Cutting Synthesis: Suggested Master Plan Changes

> Compiled from all 8 phase planning agents. These are changes that affect the master plan structure, dependencies, or scope.

---

## 1. Corrections / Factual Updates

### 1a. Play Boosters, not Draft Boosters
**Source**: Phase 0A agent
**Issue**: The master plan uses old Draft Booster composition (10C + 3U + 1R/M + 1 land). MTG switched to Play Boosters starting with Murders at Karlov Manor (Feb 2024).
**Play Booster composition**: 6C + 3U + 1R/M + 1 land + 1 wildcard + 1 foil + 1 art card/ad (varies)
**Action**: Update all booster references in master plan (Phases 4B, 5A) to use Play Booster structure, or explicitly decide to use a simplified custom booster structure.

### 1b. Draft Packs: 24, not 18
**Source**: Phase 4+5 agent
**Issue**: An 8-player draft pod needs 24 packs (3 per player), not 18.
**Action**: Update Phase 5A from "18 boosters" to "24 boosters (8-player pod)".

### 1c. Mythic Copies in Playset: 2x, not 4x
**Source**: Phase 4+5 agent
**Issue**: 4x mythics doesn't match real-world rarity feel. 2x is more realistic for a custom set.
**Action**: Update Phase 5A playset definition. Make mythic copy count configurable (default 2x).

---

## 2. Scope Additions (Recommended)

### 2a. Analyze 5 Sets Instead of 3
**Source**: Phase 0A agent
**Rationale**: Better statistical grounding, especially for detecting trends vs outliers.
**Suggested sets**: Duskmourn, Bloomburrow, Thunder Junction, Karlov Manor, Lost Caverns of Ixalan
**Action**: Update Phase 0A from "3 recent sets" to "5 recent sets".

### 2b. Store Raw Scryfall Data
**Source**: Phase 0A agent
**Rationale**: Raw data is reused by Phases 0C (schema validation), 0E (few-shot examples), 1C (reprint selection), and 4 (benchmarking).
**Action**: Add `data/scryfall/` directory to project structure. Phase 0A stores raw JSON alongside analysis.

### 2c. Missing Data Points
**Source**: Phase 0A agent
**Action**: Add to Phase 0A research scope: removal density per color, as-fan calculations, subtype frequency, multicolor pair distribution, DFC/special layout prevalence.

### 2d. Budget 20 Basic Lands with Custom Art
**Source**: Phase 4+5 agent
**Issue**: Basic lands need custom art but aren't accounted for in art budget or card count.
**Action**: Add basic lands to set card count (~20 basics = 4 per color). Factor into art generation budget.

### 2e. Add Phase 5C: Assembly
**Source**: Phase 4+5 agent
**Rationale**: After printing arrives, need sorting guide, set guide insert, and box labels.
**Action**: Add Phase 5C to master plan with: sorting guide, set guide insert, box label templates.

### 2f. Cost Calculator Before Print Order
**Source**: Phase 4+5 agent
**Action**: Add cost estimation tool to Phase 5A that calculates total print cost before committing.

### 2g. Set Symbol Design
**Source**: Phase 0B + Phase 2 agents
**Consensus**: Create placeholder set symbol in Phase 0B (needed for 1-card PoC), finalize in Phase 2A as part of art direction.
**Action**: Add set symbol placeholder to Phase 0B deliverables, finalize in Phase 2A.

---

## 3. Architecture Decisions (New)

### 3a. Shared Config System
**Source**: Phase 0B + 0C agents
**Decision**: Use `pydantic-settings` for shared configuration. Config files in `config/` directory:
- `config/print-specs.json` — DPI, bleed, dimensions, color space
- `config/card-layout.json` — frame dimensions, text areas, font sizes
- `config/fonts.json` — font paths and fallbacks
- `config/symbols.json` — symbol font/SVG paths
**Action**: Add shared config system to Phase 0C deliverables.

### 3b. Schema Enhancements
**Source**: Phase 0C+0D agent
**Additional fields not in master plan**:
- Card: `draft_archetype`, `mechanic_tags`, `slot_id`, `is_reprint`, `scryfall_id`, `design_notes`, `art_prompt`
- GenerationAttempt: `input_tokens`, `output_tokens`, `cost_usd`, `prompt_version`
- Power/toughness as strings (for `*/*` creatures) — Scryfall compatibility
**Action**: Update Phase 0C schema section in master plan.

### 3c. Tool Use / Function Calling for Structured Output
**Source**: Phase 0D agent
**Decision**: Use LLM tool use / function calling for card generation instead of raw JSON mode — guarantees schema validity.
**Action**: Note in Phase 0D and 0E.

### 3d. Batch of 5 Cards as Default Generation Size
**Source**: Phase 0D agent
**Rationale**: Best tradeoff between context awareness, cost, and quality. Single cards are expensive; batches of 10+ degrade quality.
**Action**: Note in Phase 0D strategy.

### 3e. Separate Cheaper Model for Art Prompts
**Source**: Phase 0D agent
**Decision**: Use GPT-4o-mini or Haiku for art prompt generation — doesn't need expensive model.
**Action**: Note in Phase 0D and 2A.

### 3f. Rendering Stack: Pillow + Cairo/Pango
**Source**: Phase 2 agent
**Decision**: Pillow for image composition, Cairo/Pango for text layout (best rich text support: inline symbols, italic reminder text, dynamic sizing).
**Action**: Note in Phase 0B tech decisions and Phase 2C.

### 3g. Proxy Render Mode
**Source**: Phase 2 agent
**Decision**: Support text-only card rendering without art for early pipeline testing.
**Action**: Add to Phase 2C scope. Enables testing the full pipeline before art generation.

### 3h. Dual Resolution Output
**Source**: Phase 2 agent
**Decision**: Render both screen-resolution (72 DPI) for review and print-resolution (300+ DPI) for export.
**Action**: Add to Phase 2C scope.

---

## 4. Dependency / Ordering Changes

### 4a. Run Balance Analysis Before Art Generation
**Source**: Phase 4+5 agent
**Rationale**: Catch set balance issues before investing in 280+ art pieces. Art is expensive and time-consuming; balance fixes may require adding/removing/changing cards.
**Current**: Phase 4 runs after Phase 2 (art + rendering).
**Proposed**: Run Phase 4A+4B (balance + limited analysis) after Phase 1C, BEFORE Phase 2B (art generation). Phase 4C (quality checks) can still run later.
**Action**: Update dependency graph:
```
Phase 1C → Phase 4A+4B (balance gate) → Phase 2B (art generation) → Phase 2C → Phase 4C → Phase 5
```

### 4b. Design CLI Structure in Phase 1A (for Phase 3A)
**Source**: Phase 3 agent
**Rationale**: Define the full CLI command group structure in Phase 1A even if most commands are stubs. Avoids refactoring when Phase 3A extends it.
**Action**: Update Phase 1A to include CLI architecture design (Typer-based), not just the 3 minimal commands.

### 4c. Text Overflow Constants as Phase 0C Deliverable
**Source**: Phase 1 agent
**Rationale**: Text overflow limits feed into prompt constraints (telling the LLM how much text can fit). Should be defined before card generation starts.
**Action**: Move text overflow constants (max characters per field, font size assumptions) from Phase 1C validation to Phase 0C setup.

### 4d. Prototype Validation-Retry Loop in Phase 0E
**Source**: Phase 0E agent
**Rationale**: The retry loop is critical infrastructure. Testing it during the prompt spike catches issues before Phase 1C relies on it.
**Action**: Add retry loop prototyping to Phase 0E scope.

---

## 5. Timeline Estimates (Aggregate)

| Phase | Estimated Time |
|-------|---------------|
| 0A | 8-12 hours |
| 0B | 5-8 days (parallel with 0A) |
| 0C | ~3 hours |
| 0D | ~9 hours |
| 0E | 5-6 working days |
| 1A | 2-3 days |
| 1B | 1-2 days |
| 1C | 5-7 days |
| 2A | 3-4 days |
| 2B | 10 calendar days (daily limits) |
| 2C | 5-7 days |
| 3A+3B | 3-4 days |
| 4 | 2-3 days |
| 5 | 2-3 days + shipping |

**Total**: ~8-12 weeks for V1 (with parallelization)

---

## 6. Budget Refinements

| Category | Master Plan | Revised Estimate | Notes |
|----------|-------------|-----------------|-------|
| LLM (card design) | ~$30/set | **~$5-10/set** | Claude Sonnet ~$5, GPT-4o ~$3.50. Even with heavy retries, well under $30 |
| Art generation | ~$20/mo | **$20-40/mo** | May need 2 months if spreading over daily limits. Local generation (SDXL/Flux) is free but lower quality |
| Art budget total | ~$50 MAX | **$50-80** | Realistic with subscription + some local generation |
| Printing | TBD | **TBD** | Phase 0B will lock this down. EU services avoid Dutch customs |
| Basic land art | Not budgeted | **+$0-10** | 20 basics × art generation cost |

---

## 7. Revised Dependency Graph

```
Phase 0A ─────────┐
Phase 0B ─────────┼──→ Phase 0C (setup) ──→ Phase 0D (LLM strategy) ──→ Phase 0E (prompt spike)
                  │                                                          │
                  │    ┌─────────────────────────────────────────────────────┘
                  │    │
                  │    ▼
                  │    Phase 1A (skeleton + CLI architecture)
                  │        │
                  │        ▼
                  │    Phase 1B (mechanics) ──→ Design Review (5 sample cards)
                  │        │
                  │        ▼
                  │    Phase 1C (card generation + validation library)
                  │        │
                  │        ├──→ Phase 4A+4B (balance gate) ◄── NEW POSITION
                  │        │        │
                  │        │        ▼
                  │    Phase 2A (art direction, parallel with 1A-1C)
                  │        │
                  │        ▼
                  │    Phase 2B (art generation) ◄── only after balance gate passes
                  │        │
                  │        ▼
                  │    Phase 2C (card renderer)
                  │        │
                  │        ▼
                  │    Phase 3A+3B (review tools)
                  │        │
                  │        ▼
                  │    Phase 4C (quality checks)
                  │        │
                  │        ▼
                  │    Phase 5A (print files) ──→ 5B (print order) ──→ 5C (assembly)
                  │
                  └──→ Print specs locked (hard dep for 2C)
```
