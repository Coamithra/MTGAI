# Granular Model Routing — Future Work

## Problem
Currently the pipeline has hardcoded model assignments per module (Opus for generation/review, Haiku for art prompts/selection) with only a blunt `MTGAI_MAX_MODEL` env var as a cap. The production system needs per-stage configuration for both LLM and image generation models.

## Vision
A config-driven routing system where each pipeline stage specifies its own model and provider independently:

| Pipeline Stage | Example Config |
|---|---|
| Card generation (R/M) | Opus / expensive model |
| Card generation (C/U) | Haiku / cheap model |
| AI review council | OpenAI reasoning model |
| Reprint selection | Local LLM |
| Art prompts | Haiku |
| Art generation (R/M) | High-quality image model (Midjourney if API available) |
| Art generation (C/U) | Local Flux / cheaper model |
| Art selection | Haiku vision |

## Why
- Different stages have wildly different quality/cost tradeoffs
- Model landscape changes fast — new providers, new price points
- Want to mix providers freely (Anthropic, OpenAI, local, image-gen APIs)
- Creative tasks need expensive models; mechanical tasks waste money on them

## Prior Art
The wingedsheep MTG card generator (`learnings/wingedsheep-mtg-card-generator.md`, line 85) uses a JSON config mapping task names to model IDs. Simple and effective.

## Implementation Notes
- `llm_client.py` already abstracts model calls — extend with a routing config
- Image generation is currently ComfyUI-only — would need provider abstraction layer
- Config should support per-rarity overrides (e.g., Opus for mythics, Haiku for commons)
- Should be a JSON/YAML config file, not env vars — too many knobs for env vars
