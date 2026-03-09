# LLM Strategy for MTG AI Set Creator

## 1. Model Selection

### Primary Model: Claude Sonnet (`claude-sonnet-4-20250514`)
- **Score**: 89/100 across 5 test cards (highest of 3 models tested)
- **Strengths**: Best creativity, most detailed design notes, excellent rules text, guaranteed JSON via tool_use
- **Weakness**: Occasional balance misses (overpowered blue instant in testing) — caught by validation pipeline
- **Use for**: All card generation (rares/mythics always, commons/uncommons by default)

### Retry/Bulk Model: GPT-4o-mini (`gpt-4o-mini`)
- **Score**: 84/100 (surprisingly close to Sonnet at 40x lower cost)
- **Strengths**: Extremely cheap ($0.00035/card), good quality for simple cards, valid JSON output
- **Weakness**: NWO violations at common, occasionally sets land colors incorrectly, shorter design notes
- **Use for**: Bulk retry attempts, potential first-pass for simple commons

### Art Prompt Model: Claude Haiku (`claude-haiku-4-5-20251001`)
- **Score**: 92% of Sonnet quality for art prompts, 4x cheaper, 2.3x faster
- **Use for**: All art prompt generation (escalate to Sonnet for mythics/showcase if needed)

### Not Recommended: GPT-4o
- Awkward middle ground — more expensive than GPT-4o-mini with only marginally better quality
- Conservative designs lack creative spark

### Not Viable: Local Models (Llama, Mistral on 8GB GPU)
- 8GB VRAM limits to 7B-13B models — insufficient quality for MTG rules text

## 2. Cost Budget

### Per-Card Cost (Actual from Testing)

| Model | Cost/Card (single) | Cost/Card (batch 5) | Cost/Card (batch 10) |
|-------|-------------------|--------------------|--------------------|
| Claude Sonnet | $0.0129 | $0.0046 | $0.0036 |
| GPT-4o-mini | $0.00035 | ~$0.0002 | ~$0.0001 |

### Per-Set Cost Estimate (280 cards)

| Component | Model | Calls | Est. Cost |
|-----------|-------|-------|-----------|
| Card generation (batch 5) | Claude Sonnet | 56 | $1.29 |
| Retries (25% rate, single) | Claude Sonnet | 70 | $0.90 |
| Mechanic design | Claude Sonnet | 5 | $0.07 |
| Art prompts (batch 5) | Claude Haiku | 56 | $0.31 |
| **Total** | | **~187** | **~$2.57** |

With Batch API (50% off): **~$1.29**

**Budget: $30 allocated, ~$2.57 expected.** Massive headroom for iteration — could regenerate the entire set 10+ times.

### Cost Tracking
Already supported via `GenerationAttempt` model fields: `input_tokens`, `output_tokens`, `cost_usd`, `prompt_version`.

## 3. Prompting Architecture

### System Prompt
- **Version**: v1 (~1,800 tokens)
- **Location**: `research/prompt-templates/system-prompt-v1.md`
- **Contents**: Role definition, MTG rules reference (evergreen keywords, rules text patterns, mana symbols), color pie summary, New World Order guidelines, output format spec, constraints/don'ts
- **Not included** (goes in user prompt): few-shot examples, set-specific mechanics, set context

### User Prompt Template
```
Set Context:
- Set name: {{set_name}}, Code: {{set_code}}
- Theme: {{theme_description}}
- Mechanics: {{mechanics_with_reminder_text}}
- Archetypes: {{archetype_summary}}

Already Generated (avoid duplicates):
- Card names: {{card_name_list}}
- Color distribution: {{color_counts}}
- Archetype coverage: {{archetype_counts}}

Few-Shot Examples:
{{selected_examples}}

Generate {{batch_size}} cards:
{{card_slot_specifications}}
```

### Few-Shot Example Selection
- Library: 25 curated real MTG cards in `research/few-shot-examples/` (indexed in `index.json`)
- Selection per call: 1-2 matching rarity, 1 matching color, 1 matching card type
- ~1,500 tokens for 3-5 examples

### Batch Size: 5 cards per call
- **64% cost savings** vs single-card generation (shared system prompt amortization)
- **100% parse success rate** in testing (tool_use guarantees valid JSON)
- Natural grouping: one per color, or all cards for one archetype
- Retries use single-card mode for maximum context

## 4. Structured Output

### Approach: Tool Use / Function Calling
- **Anthropic**: `generate_card` tool with Card JSON schema as input_schema
- **OpenAI**: `response_format={"type": "json_object"}` with schema in prompt
- **Guarantees**: Valid JSON structure, correct field types, required fields present
- **Parse failure rate**: 0% in testing (19/19 cards across all batch sizes)

### JSON Schema
Derived from `backend/mtgai/models/card.py` Card Pydantic model. Key fields for LLM output:
- `name`, `mana_cost`, `cmc`, `colors`, `color_identity`
- `type_line`, `oracle_text`, `flavor_text`
- `power`, `toughness` (strings), `loyalty` (string)
- `rarity`, `design_notes`

## 5. Validation & Retry Pipeline

### Validation Chain (7 validators, executed in order)
Full design: `research/validation-chain-design.md`

| # | Validator | Severity | What it Catches |
|---|-----------|----------|-----------------|
| 1 | JSON Schema | Hard | Missing fields, wrong types, bad enums |
| 2 | Mana/CMC Consistency | Hard | CMC mismatch, color mismatch, invalid mana format |
| 3 | Rules Text Grammar | Mixed | Self-reference errors, keyword misspellings, bad templates |
| 4 | Color Pie Compliance | Soft | Wrong abilities for the card's colors |
| 5 | Power Level / Balance | Soft | Overpowered stats, NWO violations at common |
| 6 | Text Overflow | Soft | Rules text too long for card frame |
| 7 | Uniqueness | Hard (name) / Soft (mechanical) | Duplicate names, similar cards |

### Retry Strategy
- **Max retries**: 3
- **Feedback format**: Specific, actionable errors with `[HARD]`/`[SOFT]` tags
- **Retry model**: Same as primary (Sonnet) for first retry, GPT-4o-mini for subsequent
- **Escalation**: After 3 failures → flag for human review, card stays at `draft` status
- **Batch handling**: Accept passing cards, retry only failures in single-card mode

## 6. Art Prompt Strategy

### Approach: Separate call (cheap model)
- Art prompts generated AFTER card design is complete
- Uses Claude Haiku (`claude-haiku-4-5-20251001`) — 92% of Sonnet quality at 4x less cost
- Temperature: 0.6
- Cost: $0.31 for entire 280-card set

### Art Prompt Template
```
Given this card data, generate a detailed image generation prompt:
{card_json}

Output JSON with:
- "art_prompt": 100-200 word scene description (subject, composition, lighting, mood, colors).
  Style: "fantasy card game art, detailed digital painting".
  Include: "no text, no words, no letters, no watermark".
  Aspect ratio: ~3:2 (wider than tall).
- "art_description": 1-sentence summary.
```

### When to Escalate to Sonnet
- Mythic rares and showcase cards
- Dual-color lands (need both colors represented visually)
- Cards where Haiku prompts produce poor image results

## 7. Reproducibility

### Temperature Settings

| Task | Temperature | Rationale |
|------|-------------|-----------|
| Card generation (first attempt) | 0.7 | Creative variety |
| Card generation (retry) | 0.5 | More focused |
| Mechanic design | 0.8 | Maximum creativity |
| Art prompt generation | 0.6 | Creative but consistent |
| Validation/classification | 0.0 | Deterministic |

### Prompt Versioning
- All prompts stored as versioned files in `research/prompt-templates/`
- Each `GenerationAttempt` records `prompt_version` used
- Enables correlation of prompt changes with quality changes

### Seed Strategy
- OpenAI: `seed = hash(set_code + collector_number)` for reproducible first attempts
- Anthropic: No seed support — use temperature=0 for deterministic retries

## 8. Context Window Management

### Per-Call Token Budget (~5,000-7,000 tokens input)

| Component | Tokens | Notes |
|-----------|--------|-------|
| System prompt | ~1,800 | Fixed, v1 |
| Few-shot examples (3-5) | ~1,500 | Selected per call |
| Set context (compressed) | ~500 | Names, distribution, archetypes |
| Card slot specifications (batch 5) | ~1,000 | 200 per card |
| **Total input** | **~4,800** | Well within 200K context |

### Set Context Format (compressed, ~500 tokens)
```json
{
  "cards_generated": 142,
  "cards_remaining": 138,
  "card_names": ["Lightning Bolt", "Serra Angel", ...],
  "color_distribution": {"W": 28, "U": 26, "B": 30, "R": 27, "G": 31},
  "archetype_coverage": {"WU": 12, "WB": 8, ...},
  "mechanic_usage": {"Delirium": 15, "Convoke": 8, ...}
}
```

Card name list (~560 tokens for 280 names) is the most important piece for duplicate avoidance.

## 9. Open Questions & Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Sonnet produces overpowered cards | Medium | Validation pipeline catches P+T and cost anomalies; tested and confirmed |
| Retry rate exceeds 25% | Medium | Indicates prompt issues — fix prompts, not model. Budget allows 10x iteration. |
| Model pricing increases | Low | Architecture is model-agnostic. $2.57/set gives massive headroom. |
| Model deprecation | Low | Pin versions in config. Test new models before switching. |
| Few-shot examples have stale oracle text | Low | Verify against Scryfall API before production use |
| Context grows too large mid-set | Low | Compressed summary stays under 600 tokens even at 280 cards |

## Appendix: Test Results

- Model comparison: `research/model-comparison-scores.md` (raw: `model-comparison-results.json`)
- Batch size test: `research/batch-size-analysis.md` (raw: `batch-size-test-results.json`)
- Art prompt comparison: `research/art-prompt-comparison.md` (raw: `art-prompt-test-results.json`)
- Validation chain design: `research/validation-chain-design.md`
- System prompt v1: `research/prompt-templates/system-prompt-v1.md`
- Few-shot examples: `research/few-shot-examples/` (25 cards + index.json)
