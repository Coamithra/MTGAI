# Phase 2A Learnings — Art Quality & Selection

## Art Model (Flux.1-dev Q8_0 local)

### What worked
- Pipeline is solid: 198 images generated reliably, resumable, ~40s/image
- Composition and color identity are generally good
- Flux understands MTG-style scene descriptions well enough for dev set prototyping

### What didn't work
- **Anatomy issues**: AI hands, limbs, body proportions still a problem (e.g., Rebel Firebrand has mangled legs). Flux.1-dev local isn't good enough for production card art.
- **Too realistic**: Many outputs skew photorealistic rather than the stylized/painterly look we want. The style line in prompts ("stylized digital illustration, bold shapes, painterly texture") isn't strong enough to override Flux's realism bias.
- **Violence/dark themes**: Flux is "uncensored" (no hard refusals) but still can't coherently render violent scenes — Murder prompt produced incoherent mush. Midjourney has the same problem. For cards depicting combat/death, prompts MUST be reframed as aftermath/implication rather than direct depiction (e.g., "a fallen figure in shadows" not "a stabbing"). Bake this into the prompt builder as a rule.
- **Negative prompts**: Flux doesn't support negative prompts natively, but we should explore:
  - Stronger positive style anchoring ("thick paint strokes", "visible brushwork", "cel-shaded")
  - Avoiding realism trigger words in prompts
  - If switching models, pick one with negative prompt support (SDXL, Midjourney)

### Production recommendations
- **External art model needed** for final set: Midjourney v6+, DALL-E 3, or Ideogram — better anatomy, better style control, negative prompt support
- **Better judge LLM**: Haiku picks the "best of 3" but doesn't catch anatomy errors well enough. Use Sonnet or Opus for art selection on the production set, or add explicit anatomy checking criteria.
- **Prompt tweaks to try**: Add anti-realism modifiers, stronger painterly style anchors, more specific anatomy guidance ("correct human proportions", "anatomically coherent limbs")

## Art Selector (Haiku vision)
- 66/66 reviewed, all high confidence, $0.37 — extremely cost-effective
- But confidence doesn't correlate with actual quality — Haiku said "high confidence" on Rebel Firebrand despite obvious leg issues
- For production: either upgrade to Sonnet/Opus vision, or add a second-pass anatomy validator

## Verdict
- **Good enough for dev set pipeline validation** — proves the full flow works
- **Not production quality** — revisit model choice and prompt engineering before Phase SC scale-up
