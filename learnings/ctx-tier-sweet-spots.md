# Context-length tiers — finding the sweet spots

Carrier: **Gemma 4 26B-A4B** (`gemma4-26b-vlad-updated`, 13.2 GiB GGUF) on an **RTX 4070 Ti
(12 GiB)**. Born from the 2026-05-31 IQ4_XS-vs-Vlad / MoE-offload investigation
(Trello `6a1c1940`). Reproduce the numbers with `research/scripts/ctx_token_profile.py`
(analytical) and `research/scripts/ctx_log_audit.py` (from a real run's transcripts).

## The problem

`context_window` in `models.toml` is simultaneously the llama-server `--ctx-size` (KV
cache pre-allocated at load) **and** the token budget. Every stage ran the carrier at
128k, so every stage reserved the full 128k KV (~1.5 GiB) even though only
`theme_extract` ingests a large document. On a 12 GiB card where the carrier's weights
(13.2 GiB) *already* exceed VRAM, that wasted KV forces extra weight layers onto the CPU
→ slower generation on every downstream stage.

## Finding 1 — per-stage max input tokens

Measured from llmfacade transcript `usage.prompt_tokens` where logs exist; analytical
(real prompts built against the 68-card ASD pool, extrapolated to ~277) for the
scale-sensitive stages that had **no full-set transcripts on disk**. "gemma-adj" = ×1.25
over tiktoken (tiktoken undercounts the Gemma tokenizer ~10–30%).

| Stage | Max input (gemma-adj) | Source | Scales w/ set? |
|---|---|---|---|
| `theme_extract` | **~58.7k** | measured | doc-bound (chunk budget = `ctx//2`) |
| `conformance` | ~24k | analytical | yes — whole-set, card+spec/card (largest gate) |
| `reprints` | ~22k | measured | yes — whole-set slot list |
| `balance`/interactions | ~18.5k | analytical | yes — whole-set card-pool scan |
| `card_gen` | ~15k | analytical | yes — late batches grow w/ existing-cards ctx |
| `skeleton` relabel | ~13–15k in / ~28k in+out | analytical | yes — all slots, chunky streamed output |
| `lands` | ~10.5k | measured | no |
| `mechanics` | ~7.2k | measured | no |
| `ai_review` | ~2.9k | measured | no (per-card R/M) |
| `archetypes`/`visual_refs`/`art_*` | ≤~5k | n/a | no |

**Only `theme_extract` needs a large window.** Every downstream stage's worst case is
≤~24k. (Coverage caveat: the analytical rows are worst-case estimates — the project had
no logged full-set local run when this was written. A real run + `ctx_log_audit.py`
replaces them with measurements; the 2-tier sizing has 2× headroom either way.)

## Finding 2 — VRAM payoff per ctx (SWA-aware, real GGUF headers)

KV computed with `vram_estimate.estimate_kv_cache_bytes` (q8_0 KV) from the real GGUF
headers. **Gemma 4 26B is SWA: 30 layers, `sliding_window=1024`**, and most layers are
sliding-window-capped — so **only the few global-attention layers' KV scales with ctx**.
KV savings are small and **sub-linear**:

| ctx | KV (q8_0) | freed vs 128k | vlad-updated load (13.2 GiB w) | iq2m load (9.3 GiB w) |
|---|---|---|---|---|
| 128k | 1.50 GiB | — | 16.2 GiB (135% of 12 GiB) | 11.9 GiB (**99%**) |
| 64k | 0.86 GiB | 0.65 GiB | 15.5 GiB (129%) | 11.2 GiB (93%) |
| **48k** | **0.69 GiB** | **0.81 GiB** | 15.3 GiB (128%) | **11.0 GiB (90%)** |
| 32k | 0.53 GiB | 0.97 GiB | 15.1 GiB (126%) | 10.8 GiB (90%) |
| 16k | 0.37 GiB | 1.13 GiB | 15.0 GiB (125%) | 10.7 GiB (89%) |

- **Max possible KV saving is only ~1.2 GiB** (128k→8k). 128k→48k captures **0.81 GiB
  (~72%)** of it; going below 48k buys only ~0.16–0.32 GiB more (sub-one-layer).
- **vlad-updated** (13.2 GiB > 12 GiB): can never be fully resident; freeing 0.81 GiB
  relocates ~1–2 of 30 layers CPU→GPU → **modest** tok/s gain (est. ~5–15%; not yet
  live-benchmarked — see below).
- **iq2m** (9.3 GiB): 99% of VRAM at 128k (spills/contends) → **90% at 48k → fully
  GPU-resident → the large speedup**. Lowering iq2m's ctx is what unlocks its
  full-residency speed.

## Decision — 2 tiers, not 3

The card hypothesized HIGH/MID/LOW (3+). **The SWA data says 2 tiers is the sweet spot:**

- **HIGH = 128k** — `theme_extract` only (measured 58.7k; its chunk budget is `ctx//2`,
  so a smaller ctx would split big docs into more chunks/calls).
- **DOWNSTREAM = 48k** — every other stage. Holds the ~24k worst case with 2× headroom
  and room for chunky streamed output (relabel input+output ~28k).

Why not a 3rd "LOW ~16k" tier: it would free only **~0.32 GiB more** on the small stages
but the pipeline interleaves small/large stages, so it adds **~8 extra llama-swap reload
boundaries**. The 2-tier split needs **one** (after `theme_extract`). SWA already capped
the savings — the extra tier is a bad trade.

## Implementation (shipped)

- `models.toml`: `gemma4-26b-vlad-updated-48k` (the DOWNSTREAM twin the preset uses) +
  `gemma4-26b-iq2m-48k` (the residency-win option, for manual assignment). Same GGUF as
  the 128k entry, distinct `model_id` (= distinct llama-swap model, so same-gguf/
  different-ctx entries coexist and swap at the boundary).
- `model_settings.PRESETS["all-local-tiered"]`: `theme_extract` → 128k carrier, every
  other stage → the 48k twin. One toggle.
- No code-path change: `context_window` already flows to `--ctx-size`
  (`_llamacpp_new_model`) and the budget (`get_context_window`).

## Open / deferred

- **Live tok/s benchmark**: the VRAM payoff is exact; the tok/s *delta* (128k vs 48k on
  the carrier) needs a live GPU run. Deferred — validate with a real full-pipeline run +
  `ctx_log_audit.py` (confirms the per-stage maxima fit 48k) and an A/B speed check.
- **Auto-derivation of ctx twins**: only 1–2 base models need a twin, so they're
  hand-authored. A registry-load helper synthesizing `<key>-<ctx>` twins is deferred
  until twin count justifies the machinery.
</content>
