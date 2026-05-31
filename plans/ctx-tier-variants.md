# Context-length model variants — investigation + design

Card: **Multiple model variants by context length (find ctx sweet spots)** — `6a1c1940` [infra][design]

## Context

Every local stage runs the carrier model at `context_window = 128000`. `context_window`
is simultaneously the llama-server `--ctx-size` (KV cache pre-allocated at load) **and**
the token budget. So every stage reserves the full 128k KV even though only
`theme_extract` ingests a large document; everything downstream runs off the distilled
`theme.json` + small structured artifacts. The wasted KV reservation forces extra weight
offload to CPU → slower generation on every downstream stage.

The fix: register multiple variants of the same GGUF at different `--ctx-size` and assign
them per-stage. The card asked to **find the sweet spots** (tier count + values) and
**quantify the payoff**.

---

## Finding 1 — Per-stage max input tokens (the data)

Two sources: **measured** from llmfacade transcript `usage.prompt_tokens`
(`output/`, `backend/logs/`, `research/`), and **analytical** for the scale-sensitive
stages that had no full-set transcripts on disk (built the real prompts against the
tracked 68-card ASD pool + `skeleton.json`, extrapolated linearly to a ~277-card set).
All "gemma-adj" figures apply ×1.25 over tiktoken (tiktoken undercounts Gemma ~10–30%).

| Stage | Source | Max input (gemma-adj) | Scales with set? |
|---|---|---|---|
| `theme_extract` | measured | **~58.7k** | doc-bound; chunk budget = `ctx//2` |
| `conformance` | analytical (ASD→277) | **~24k** | **yes** — whole-set, card+spec/card (largest gate) |
| `reprints` (assign) | measured | **~22k** | yes — whole-set slot list |
| `balance`/interactions | analytical (ASD→277) | **~18.5k** | yes — whole-set card-pool scan |
| `card_gen` | analytical | **~15k** | yes — late batches grow w/ existing-cards ctx |
| `skeleton` relabel | analytical est. | ~13–15k in / ~28k in+out | yes — all slots, chunky streamed output |
| `lands` (investigate) | measured | ~10.5k | no |
| `mechanics` (candidates) | measured | ~7.2k | no |
| `select_best_mechanics` | measured | ~3.9k | no |
| `ai_review` | measured | ~2.9k | no (per-card R/M) |
| `archetypes` / `visual_refs` / `art_prompts` / `art_select` | n/a | small (≤~5k) | no |

**Coverage gap (noted, not hidden):** no `card_gen` / `conformance` / full-set
`interactions` / `skeleton`-relabel transcripts exist on disk — the project has no logged
full-set local run. Those rows are analytical worst-case estimates, not measurements.
A real full-set run would replace them; the script `research/scripts/ctx_token_profile.py`
regenerates them.

**Takeaway:** downstream maxima cluster at **~15–24k gemma-adj** (the whole-set/scaling
stages), with the truly small stages ≤~10k. Only `theme_extract` needs a big window.

## Finding 2 — VRAM payoff per ctx (SWA-aware, real GGUF headers)

Computed with `vram_estimate.estimate_kv_cache_bytes` (q8_0 KV) against the real GGUF
headers. Gemma-4-26B-A4B has **30 layers, sliding_window=1024**, and most layers are
sliding-window-capped — so **only the few global-attention layers' KV scales with ctx**.
KV savings are small and **sub-linear**:

| ctx | KV (q8_0) | freed vs 128k | vlad-updated load (13.2 GiB w) | iq2m load (9.3 GiB w) |
|---|---|---|---|---|
| 128k | 1.50 GiB | — | 16.2 GiB (135% of 12 GiB) | 11.9 GiB (**99%**) |
| 64k | 0.86 GiB | 0.65 GiB | 15.5 GiB (129%) | 11.2 GiB (93%) |
| **48k** | **0.69 GiB** | **0.81 GiB** | 15.3 GiB (128%) | **11.0 GiB (90%)** |
| 32k | 0.53 GiB | 0.97 GiB | 15.1 GiB (126%) | 10.8 GiB (90%) |
| 16k | 0.37 GiB | 1.13 GiB | 15.0 GiB (125%) | 10.7 GiB (89%) |

- **Max possible KV saving is only ~1.2 GiB** (128k→8k). 128k→48k already captures
  **0.81 GiB (~72%)** of it; going below 48k buys only ~0.16–0.32 GiB more.
- **vlad-updated** (13.2 GiB > 12 GiB VRAM): can *never* be fully resident; freeing
  0.81 GiB relocates ~1–2 of 30 layers CPU→GPU → modest tok/s gain (est. ~5–15%).
- **iq2m** (9.3 GiB): at 128k it's 99% of VRAM (spills/contends); at **48k it drops to
  90% → fits with headroom → fully GPU-resident → the large speedup**. This is the
  "unlocks UD-IQ2_M full-residency" win the card predicted.

## Recommendation — 2 tiers, not 3

The card hypothesized HIGH/MID/LOW (3+). The data says **2 tiers is the sweet spot**:

- **HIGH = 128k** — `theme_extract` only (measured 58.7k; chunk budget `ctx//2`).
- **DOWNSTREAM = 48k** — every other stage. Comfortably holds the ~24k worst case
  (conformance) with 2× headroom and room for chunky streamed output (relabel
  input+output ~28k); captures ~72% of the max KV payoff.

Why not 3 tiers: a separate LOW (~16k) tier for the small stages would free only
**~0.32 GiB more** (sub-one-layer) on those stages, but the pipeline's stage order
interleaves small and large stages, so a 3rd tier adds **~8 extra llama-swap reload
boundaries**. The 2-tier split needs **one** swap boundary (after `theme_extract`).
SWA already capped the savings, so the extra tier is a bad trade.

## Design / implementation

1. **Registry** (`settings/models.toml`): add a 48k twin of the carrier
   (`gemma4-26b-vlad-updated-48k`, same `gguf_path`, `context_window = 48000`, same KV
   quant / offload / thinking). Optionally an iq2m-48k twin (the residency win).
   - Each `[llm.*]` key is a distinct llama-swap model id, so same-gguf/different-ctx
     entries coexist; the swap reloads at the tier boundary.
   - *Auto-derivation* (optional, card's "avoid models.toml bloat"): a small helper that
     synthesizes `<key>-<ctx>` twins from a base entry at registry-load time. Given only
     1–2 base models need a twin, hand-authoring is simplest; derive helper only if clean.
2. **Preset** (`settings/model_settings.PRESETS`): `all-local-tiered` — `theme_extract`
   → `gemma4-26b-vlad-updated` (128k), every other stage → the 48k twin. One toggle.
3. **No code-path changes** — `context_window` already flows to `--ctx-size` via
   `_llamacpp_new_model` and to the budget via `get_context_window`. This card is data +
   registry entries + a preset.

## Tests
- `tests/test_settings/` (or wherever registry/preset tests live): registry loads the
  twin(s); `from_preset("all-local-tiered")` assigns 128k to theme + 48k downstream;
  twin `context_window == 48000`; VRAM estimator still passes for the twin.

## Decisions (resolved with the user)
- **Tier design**: **2-tier** (chosen). theme_extract=128k, everything else=48k.
- **Benchmark/validation**: instead of a synthetic live benchmark, the user runs a real
  full pipeline; `research/scripts/ctx_log_audit.py` reads the per-stage transcripts to
  confirm the 48k tier holds (no downstream stage's real input exceeds ~40k) and replaces
  the analytical rows with measured ones. If a stage surprises us, bump the one
  `context_window` number (48k→64k is only +0.17 GiB KV — negligible).

## Status: IMPLEMENTED (pending real-run validation)
- `models.toml`: `gemma4-26b-vlad-updated-48k` + `gemma4-26b-iq2m-48k` twins.
- `model_settings.PRESETS["all-local-tiered"]` + `_LOCAL_DEFAULT_48K`.
- Tests: `tests/test_settings/test_models_toml.py` (twin clone + tiered-preset resolution).
- Durable findings: `learnings/ctx-tier-sweet-spots.md`. Reproducers:
  `research/scripts/{ctx_token_profile,ctx_log_audit}.py`.
- **Validation step (user):** run a full local pipeline, then
  `python research/scripts/ctx_log_audit.py <asset_folder>` and confirm the verdict.

## Out of scope
- Materializing the payoff via a live benchmark harness (separate, optional).
- Per-stage *model* routing beyond ctx (covered by other cards).
- Tuning theme_extract's chunk budget.
</content>
