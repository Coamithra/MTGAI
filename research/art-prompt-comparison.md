# Art Prompt Generation: Model Comparison

**Date:** 2026-03-08
**Task:** 0D-7 — Compare card-design models vs cheaper models for generating image prompts from card data.

---

## 1. Side-by-Side Prompt Comparison

### Card 1: Sentinel of Dawn (White Angel Creature)

| Model | Art Prompt |
|-------|-----------|
| **Claude Sonnet** | A majestic angel warrior in gleaming white and gold armor stands atop a stone watchtower at dawn, massive feathered wings spread wide against the rising sun. The angel holds a radiant spear and wears a helm with flowing plumes. Below, two human soldiers in white tabards kneel in reverence, their weapons gleaming in the golden morning light. The scene is bathed in warm sunrise colors - brilliant golds, soft oranges, and pure whites. Dramatic rays of sunlight pierce through clouds behind the angel, creating a divine atmosphere. |
| **Claude Haiku** | A majestic white-winged angel warrior stands at the crest of a golden dawn, radiating divine light. She wears gleaming plate armor adorned with celestial symbols, holding a luminous sword pointed skyward. Two smaller angelic soldiers materialize beside her in bursts of holy radiance. The background shows a breaking sunrise with warm golden and pale yellow hues bleeding across a purple-blue sky. Ethereal light rays stream downward around the figures. |
| **GPT-4o-mini** | A majestic Angel Soldier, the Sentinel of Dawn, gracefully descends from a radiant sky, her wings outstretched, shimmering with golden light. She is adorned in intricate silver armor that reflects the morning sun. Below her, two small, valiant white Soldier tokens stand at attention, their expressions filled with determination. The background features a breathtaking sunrise, casting warm hues of orange and pink across the clouds. |

### Card 2: Arcane Dissolution (Blue Counterspell)

| Model | Art Prompt |
|-------|-----------|
| **Claude Sonnet** | A powerful wizard with flowing blue robes stands with arms outstretched, magical energy swirling around their hands as they counter an incoming spell. Arcane symbols and runes dissolve into sparkling blue particles in the air around them. The background shows a mystical library or tower interior with floating books and scrolls. Ethereal blue and silver light emanates from the wizard's magic. |
| **Claude Haiku** | A swirling vortex of ethereal blue and purple magical energy dissolving an incoming spell mid-cast, with shimmering arcane runes fragmenting into wisps of light. The composition shows a magical barrier or shield of crystalline energy dispersing an enemy's attack. Mystical sparkles and flowing ribbons of mana cascade outward from the center point of impact. |
| **GPT-4o-mini** | A mystical scene depicting a powerful sorceress casting a shimmering spell of counter magic. She stands confidently at the center of a swirling vortex of arcane energy, her hands raised as ethereal blue and violet light radiates from her fingertips. The background features a stormy sky filled with swirling clouds and flashes of lightning. |

### Card 3: Pyroclastic Surge (Red Board Wipe)

| Model | Art Prompt |
|-------|-----------|
| **Claude Sonnet** | A devastating volcanic eruption unleashing a massive pyroclastic flow across a mountainous landscape, with superheated ash and debris cascading down rocky slopes in a deadly avalanche of molten rock and gas. Ancient stone structures, twisted trees, and fleeing creatures are consumed by the roiling cloud of destruction. Dramatic lighting with intense oranges, deep reds, and blazing yellows. |
| **Claude Haiku** | A catastrophic explosion of molten lava and superheated flames erupting across a battlefield, engulfing everything in its path. Massive waves of pyroclastic fire surge outward from a central volcanic rupture. Multiple creatures and figures are caught in the devastating inferno, their silhouettes barely visible through the roiling heat and smoke. The ground cracks and glows with magma beneath the surface. |
| **GPT-4o-mini** | A dramatic scene of a powerful volcanic eruption unleashing a fiery surge across a battlefield. In the foreground, molten lava and ash swirl in chaotic patterns. Silhouettes of creatures and planeswalkers caught in the surge are depicted in mid-reaction, their forms obscured by smoke and fire. The sky is filled with dark, ominous clouds illuminated by bursts of fiery orange and red. |

### Card 4: Mossback Titan (Green Beast)

| Model | Art Prompt |
|-------|-----------|
| **Claude Sonnet** | A colossal ancient beast emerging from a primordial forest, its massive form covered in thick moss, ferns, and small trees growing directly from its rocky hide. The creature has a turtle-like shell merged with stone and earth, with glowing green veins of natural magic pulsing through the moss. Ancient oaks and twisted roots sprout from its back, creating a living ecosystem. The titan's eyes glow with emerald light as it tramples through a misty woodland clearing, leaving deep footprints that instantly bloom with new plant life. |
| **Claude Haiku** | A colossal moss-covered beast emerges from an ancient forest, its massive body composed of living stone and verdant vegetation. The creature's back is a sprawling landscape of bioluminescent moss, twisted roots, and crystalline growths that glow with emerald and jade light. Towering trees and lush ferns surround it, their roots intertwining with the titan's limbs. |
| **GPT-4o-mini** | A colossal Mossback Titan, a mythical beast resembling a giant, moss-covered creature with thick, gnarled limbs and vibrant green foliage. The Titan stands proudly in a lush, verdant forest, surrounded by towering ancient trees and a carpet of soft moss. Sunlight filters through the canopy, casting dappled shadows on the ground and illuminating the Titan's intricate textures. |

### Card 5: Twilight Expanse (Land)

| Model | Art Prompt |
|-------|-----------|
| **Claude Sonnet** | A vast, ethereal landscape at the boundary between day and night, where rolling hills stretch toward a horizon split between golden sunset and deep purple twilight. Ancient stone monoliths emerge from misty grasslands, their surfaces carved with faint runes that glow softly with white and black energy. Wispy clouds drift across a sky painted in gradients of amber, violet, and deep indigo. Crystalline formations jut from the earth, some radiating pure white light while others pulse with shadowy darkness. |
| **Claude Haiku** | A vast, ethereal landscape suspended between day and night, where a luminous twilight sky dominates the composition. The scene depicts a sprawling realm divided by a subtle horizon line--warm golden and amber tones bleeding into deep indigo and violet hues. Massive crystalline formations and floating islands emerge from mist-shrouded terrain below. Delicate wisps of magical energy drift through the air. |
| **GPT-4o-mini** | A breathtaking landscape of the Twilight Expanse, a mystical land at dusk. A vast expanse of rolling hills and a shimmering lake reflecting the vibrant hues of twilight, with deep purples, soft blues, and hints of warm oranges and pinks in the sky. Silhouettes of ancient trees with twisted branches frame the lake, while ethereal wisps of fog gently rise from the water's surface. A winding path leads toward the horizon. |

---

## 2. Quality Scoring (1-5 Scale)

### Scoring Criteria
- **Specificity**: How concrete and detailed are the visual descriptions? (vs vague/generic)
- **Visual Richness**: Will this prompt produce vivid, interesting art?
- **Style Consistency**: Does it include appropriate style markers for fantasy card art?
- **Card Faithfulness**: Does the art prompt reflect the card's mechanics, colors, and flavor?

### Sentinel of Dawn

| Criterion | Sonnet | Haiku | GPT-4o-mini |
|-----------|--------|-------|-------------|
| Specificity | 5 | 4 | 4 |
| Visual Richness | 5 | 4 | 4 |
| Style Consistency | 5 | 5 | 4 |
| Card Faithfulness | 5 | 4 | 4 |
| **Average** | **5.0** | **4.25** | **4.0** |

Notes: Sonnet's watchtower scene with kneeling soldiers is the most evocative. Haiku incorrectly describes the tokens as "angelic soldiers" rather than human soldiers. GPT-4o-mini uses the card name ("Sentinel of Dawn") inside the prompt and refers to "Soldier tokens" directly, which is more game-mechanical than visual.

### Arcane Dissolution

| Criterion | Sonnet | Haiku | GPT-4o-mini |
|-----------|--------|-------|-------------|
| Specificity | 5 | 4 | 4 |
| Visual Richness | 5 | 5 | 4 |
| Style Consistency | 5 | 5 | 4 |
| Card Faithfulness | 5 | 5 | 4 |
| **Average** | **5.0** | **4.75** | **4.0** |

Notes: Haiku's approach of focusing on the spell effect itself (vortex dissolving an incoming spell) rather than a caster is arguably more interesting for card art. Sonnet adds nice environmental detail (library/tower). GPT-4o-mini is solid but more generic (sorceress in a storm).

### Pyroclastic Surge

| Criterion | Sonnet | Haiku | GPT-4o-mini |
|-----------|--------|-------|-------------|
| Specificity | 5 | 5 | 4 |
| Visual Richness | 5 | 5 | 4 |
| Style Consistency | 5 | 5 | 5 |
| Card Faithfulness | 5 | 5 | 5 |
| **Average** | **5.0** | **5.0** | **4.5** |

Notes: All three models nail this one -- board wipes are visually straightforward. Sonnet and Haiku both produce excellent catastrophic volcanic imagery. Haiku's "ground cracks and glows with magma" is a great detail. GPT-4o-mini is slightly less vivid but still good. All correctly convey the "hits everything" nature of the card.

### Mossback Titan

| Criterion | Sonnet | Haiku | GPT-4o-mini |
|-----------|--------|-------|-------------|
| Specificity | 5 | 5 | 4 |
| Visual Richness | 5 | 5 | 4 |
| Style Consistency | 5 | 5 | 5 |
| Card Faithfulness | 5 | 4 | 4 |
| **Average** | **5.0** | **4.75** | **4.25** |

Notes: Sonnet's "footprints that instantly bloom with new plant life" subtly references the land-based P/T bonus. Haiku adds interesting "bioluminescent moss" and "crystalline growths." GPT-4o-mini is solid but more straightforward and uses the card name in the prompt text (bad practice for image gen).

### Twilight Expanse

| Criterion | Sonnet | Haiku | GPT-4o-mini |
|-----------|--------|-------|-------------|
| Specificity | 5 | 4 | 5 |
| Visual Richness | 5 | 4 | 5 |
| Style Consistency | 5 | 5 | 5 |
| Card Faithfulness | 5 | 4 | 4 |
| **Average** | **5.0** | **4.25** | **4.75** |

Notes: Sonnet beautifully captures the W/B duality with white and black energy in crystalline formations. GPT-4o-mini produces a very pleasant landscape with practical details (lake, path, trees). Haiku is more abstract with "floating islands" which don't feel grounded. Sonnet is the only model that clearly references both colors the land produces.

### Overall Score Summary

| Model | Sentinel | Dissolution | Surge | Titan | Expanse | **Overall Avg** |
|-------|----------|-------------|-------|-------|---------|-----------------|
| **Claude Sonnet** | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | **5.0** |
| **Claude Haiku** | 4.25 | 4.75 | 5.0 | 4.75 | 4.25 | **4.6** |
| **GPT-4o-mini** | 4.0 | 4.0 | 4.5 | 4.25 | 4.75 | **4.3** |

**Haiku quality vs Sonnet: 92%** (4.6 / 5.0)
**GPT-4o-mini quality vs Sonnet: 86%** (4.3 / 5.0)

---

## 3. Token Usage & Cost Comparison

### Raw Token Counts (5 cards)

| Model | Total Input | Total Output | Total Tokens | Avg Latency |
|-------|------------|-------------|-------------|-------------|
| Claude Sonnet | 1,349 | 1,174 | 2,523 | 6.52s |
| Claude Haiku | 1,349 | 1,158 | 2,507 | 2.80s |
| GPT-4o-mini | 1,203 | 1,027 | 2,230 | 4.63s |

### Estimated Cost per Card (art prompt only)

| Model | Input $/1M | Output $/1M | Cost per Card | Cost per 280-Card Set |
|-------|-----------|-------------|---------------|----------------------|
| Claude Sonnet | $3.00 | $15.00 | $0.0043 | **$1.21** |
| Claude Haiku | $0.80 | $4.00 | $0.0011 | **$0.31** |
| GPT-4o-mini | $0.15 | $0.60 | $0.0001 | **$0.04** |

*Calculation: (input_tokens/5 * input_rate + output_tokens/5 * output_rate) per card, scaled to 280 cards.*

### Cost Savings

| Switch From -> To | Savings per Set | Quality Loss |
|-------------------|----------------|-------------|
| Sonnet -> Haiku | $0.90 (74% cheaper) | ~8% (4.6 vs 5.0) |
| Sonnet -> GPT-4o-mini | $1.17 (97% cheaper) | ~14% (4.3 vs 5.0) |

---

## 4. Qualitative Observations

### Claude Sonnet Strengths
- Consistently the most evocative and visually specific prompts
- Best at translating card mechanics into visual metaphors (e.g., "footprints blooming with plant life" for the land-scaling titan)
- Strongest color/identity faithfulness (W/B duality in Twilight Expanse)
- Never uses card name or game-mechanical language in prompts

### Claude Haiku Strengths
- Very close to Sonnet quality -- often indistinguishable
- Fastest model (2.8s avg vs 6.5s for Sonnet)
- Good at dramatic, dynamic compositions
- Occasionally adds interesting creative details Sonnet doesn't (bioluminescent moss)
- Minor weaknesses: sometimes slightly less grounded (floating islands for a land)

### GPT-4o-mini Strengths
- Cheapest by a very large margin (97% cheaper than Sonnet for art prompts)
- Reliable JSON output (used json_object mode)
- Good landscape descriptions (Twilight Expanse was its best)
- Weaknesses: tends to use card names in prompts (bad for image generation), occasionally more generic, slightly less vivid than Anthropic models

### Common Issues Across All Models
- All models follow the format instructions well (100-200 word prompts, JSON output, style markers)
- All include the required "no text/watermark" and aspect ratio instructions
- None produced parse errors or format violations

---

## 5. Recommendation

### Use Claude Haiku for art prompt generation.

**Rationale:**

1. **Quality is sufficient.** At 92% of Sonnet's quality, Haiku comfortably exceeds the 80% threshold. The quality difference between Haiku and Sonnet is subtle -- both produce vivid, specific, style-appropriate prompts. The gap matters more for card *design* (rules text, balance) where precision is critical. For art prompts, "very good" is good enough because the image generation model introduces its own variance.

2. **Cost is low.** At $0.31 per 280-card set, art prompts with Haiku are essentially free compared to the overall budget. Even Sonnet at $1.21 is cheap, but there's no reason to spend 4x more for marginal improvement.

3. **Speed matters for iteration.** Haiku is 2.3x faster than Sonnet (2.8s vs 6.5s avg). When generating 280 art prompts, that's ~13 minutes vs ~30 minutes. This enables faster iteration on art direction.

4. **GPT-4o-mini is a reasonable alternative** but has the card-name-in-prompt issue and slightly lower quality. If Anthropic API is unavailable, GPT-4o-mini is an acceptable fallback at even lower cost.

### Configuration

```python
# In MTGAIConfig
llm_art_prompt_model: str = "claude-haiku-4-5-20251001"
llm_art_prompt_temperature: float = 0.6
```

### When to Escalate to Sonnet
- Mythic rares and showcase cards where art quality is paramount
- Cards with subtle color identity (like dual-color lands) where the prompt needs to reflect both colors
- If Haiku prompts consistently produce poor image results during Phase 2A testing
