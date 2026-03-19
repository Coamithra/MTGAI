# Phase 2A Learnings: Art Direction System — Summary

## What We Built

A complete art direction and generation pipeline for MTG card art:
- Style guide + visual references for "Anomalous Descent" setting
- Flux-optimized art prompt generation via Haiku ($0.006/card)
- ComfyUI + Flux.1-dev Q8_0 local image generation (40s/image, 1024×768)
- AI art selection via Haiku vision (3 versions per card, best picked automatically)
- Character reference portraits (8 characters × 3 versions)
- PuLID-Flux face identity injection for character consistency
- Set symbol SVG (descending vortex) with rarity variants

## Key Decisions

### Image Generation: Local Flux.1-dev GGUF
- Q8_0 (12GB) for standard card art, Q5_K_S (8GB) when PuLID needs headroom
- 30 steps, euler sampler, guidance 3.5, 1024×768
- Local is 10-100x cheaper than cloud APIs for iteration
- Quality is dev-set level, not production — anatomy issues, too photorealistic

### Character Identity: PuLID-Flux at weight=0.5
- **Kontext Dev REJECTED**: copies entire reference (style + composition + identity). No strength control. Edit model, not identity extractor.
- **PuLID-Flux ACCEPTED**: extracts face features only. Weight 0.5 = recognizable identity without dominating style. Weight 0.8 = too literal.
- Only works for humanoid characters — skeletons, stone heads, monsters get no benefit
- Required custom onnxruntime shim for insightface (can't build 0.7+ on Windows without C++ compiler visible to pip)

### Art Selection: Haiku Vision is Cheap and Good
- $0.006/card to evaluate 3 versions + pick best
- Catches watermarks, subject mismatches, composition issues
- Does NOT catch anatomy errors (mangled hands, wrong limb count)
- 66/66 high confidence selections, 4/5 match human picks

## Production Gaps (for full 280-card set)

1. **Art quality**: Local Flux Q8 is insufficient. Need cloud API (fal.ai, Replicate) or better local model for final art
2. **Anatomy**: Flux consistently mangles hands/fingers. Need object-gripping compositions or post-processing
3. **Style consistency**: Too photorealistic. Need stronger painterly anchors in prompts or fine-tuned model
4. **Art judge**: Haiku doesn't catch anatomy. Need Opus or specialized vision model for QA
5. **Known MTG characters**: Must use official Scryfall art as reference (Flux can't generate recognizable planeswalkers)

## Cost Summary

| Component | Cost |
|-----------|------|
| Art prompts (Haiku) | ~$0.40 |
| Art selection (Haiku) | ~$0.37 |
| Local Flux generation | $0 (electricity only) |
| PuLID test | $0 (local) |
| **Total Phase 2A** | **~$0.77** |

## Detailed Learnings Files

- `phase2a-style-guide.md` — style guide creation, visual reference system
- `phase2a-prompts.md` — Flux prompt optimization, Haiku prompt builder
- `phase2a-comfyui.md` — ComfyUI setup, VRAM management, GPU crashes, PuLID/Kontext findings
- `phase2a-art-quality.md` — art review, quality assessment, production gaps
