# Art tail on a shared single GPU: the LLM↔ComfyUI contention saga

**TL;DR** — On a single 12 GB GPU, running the art stages (`char_portraits`,
`art_gen`) inside the pipeline (which has just run local-LLM stages) is a
fundamentally different beast from the old ASD art runs, which executed as a
**standalone script on a pristine GPU with no LLM ever loaded**. That difference
plus an intervening **ComfyUI update** produced one crash + five compounding
performance regressions, each of which *masked the next*. All are fixed (PRs
#30–#35); this doc records the chain so the wrong turns aren't repeated.

> **Supersedes the perf claims in `phase2a-comfyui.md`.** That doc says "Flux
> Q8_0 GGUF fits comfortably (~9.6 GB) ... ~40 s/image." That was TRUE then
> (standalone script, clean GPU, older ComfyUI) and is **false now** under the
> current ComfyUI on 12 GB. Do not trust those numbers for the in-pipeline path.

## Why it worked before and broke now

ASD generated art via `backend/scripts/generate_all_art.py` — a standalone batch
on a GPU where no llama-server had ever run, against an older ComfyUI. The
wizard pipeline instead interleaves local-LLM stages and the art stages in **one
long-lived process on one GPU**. Every regression below is a consequence of that
interleaving and/or the ComfyUI bump.

## The chain (fix order — each unmasked the next)

1. **Crash — LLM VRAM never freed before ComfyUI** (PR #30). `ensure_comfyui()`
   → `check_vram()` needs ~10.2 GB free, but the resident local Gemma (~9 GB)
   left ~0.6 GB → `RuntimeError: Insufficient VRAM`. The error message even
   listed `llama-server.exe` (the app's *own* managed subprocess) as a process to
   "close." Fix: `llm_client.unload_local_models()` before `ensure_comfyui`.

2. **ComfyUI-version regression: Q8 no longer fits** (PR #31). The current
   ComfyUI build loads `flux1-dev-Q8_0.gguf` at a **~12.2 GB** footprint (vs
   ~9.6 GB in the old build), so on 12 GB it "loads partially" and spills ~2.8 GB
   to CPU → ~31–37 s/step. **This is the trap**: the stale doc said Q8 fits, so
   "Q8 is too big for 12 GB" looked like a fundamental limit — it's not; it's a
   version regression. Fix: VRAM-aware quant selection (`select_flux_quant`)
   defaulting to **`flux1-dev-Q5_K_S.gguf`** (~8 GB, loads fully) on ≤~12 GB
   cards, Q8 only when free VRAM ≥ ~14 GB; `MIN_VRAM_FREE_MB` 10200 → 9000.

3. **`--disable-cuda-malloc` per-step stall** (PR #32). This flag (added
   post-ASD "to avoid cudaMallocAsync instability") forces the sync allocator,
   which under the current ComfyUI stalls on per-step memory ops **even when the
   model is fully loaded** — GPU pinned at 100 % util but only ~70 W of 285 W
   (memory-bound, not compute). With Q5 fully loaded: 40 s/step *with* the flag
   vs **2.9 s/step without**. I initially (wrongly) cleared this flag because I
   tested it with Q8, whose CPU-offload masked the effect. Fix: remove the flag
   (its sibling crash-fix, `flush_comfyui()`, is the real instability guard).

4. **Lingering llama-server CUDA context** (PR #33). `unload_local_models()`
   originally only *evicted the model* (`unload_all()` → POST
   `/api/models/unload`); the `llama-server`/`llama-swap` **processes stayed
   alive** holding a live CUDA context that contended with Flux (~10 s/step).
   PROOF: killing the process mid-run jumped the rate 11 → 1.6 s/step instantly.
   Fix: `unload_local_models()` calls the provider's `shutdown()` (kills the
   subprocess tree) and drops it from `_PROVIDERS` so the next LLM call
   cold-starts cleanly. Trade-off: one ~20–30 s LLM reload next time one's needed
   (acceptable — ComfyUI is killed before `art_gen`'s judge).

5. **tok/s poller reloads the LLM mid-image-gen** (PRs #34 + #35). The art
   stages wrapped their *whole* run in the LLM tok/s poller (`make_poller` /
   `_bus_poller`), which probes `/upstream/<model>/slots` every ~0.5 s — a
   **model-specific** endpoint that makes managed-mode llama-swap **(re)load**
   that model into VRAM during the image phase, undoing the shutdown and
   re-contending (~25 s/step). Fix: scope the poller to the LLM sub-phase only —
   #34 fixed the **engine** runners (`run_char_portraits` passes `detect_poller`;
   `run_art_gen` polls only the `art_select` judge), #35 fixed the **UI refresh
   endpoints** (`char_refs/refresh`, `art_gen/refresh`, `art_gen/reroll`) which
   the tab buttons actually call — the engine fix alone missed those.

## Verified end state (12 GB RTX 4070 Ti)

`char_portraits` "Generate references" end-to-end: detect → LLM **shut down**
(stays down: 0 `/slots` polls during image gen) → ComfyUI ready ~4 s → Q5
"loaded completely; full load: True" → **1.6 s/step (~60 s/image)**, GPU 96 % util
@ **~205 W** (full compute) → 24 images saved → "Attached references to 38 cards."
Vs the starting state: hard crash, or (once past the crash) ~15–20 min/image.

## Lessons for future GPU debugging

- **100 % util but low wattage (~70–90 W of 285) = a memory-bound stall**, not
  compute. Real Flux diffusion draws ~200 W+. Check `power.draw`, not just `util`.
- **"full load: True" in ComfyUI logs ≠ fast** — a lingering CUDA context or the
  sync allocator can still cripple per-step time with the model fully resident.
- **Isolate one variable at a time on a *clean* GPU.** `backend/scripts/`-style
  one-off probes that start ComfyUI with a single knob flipped (quant, flag) and
  report s/step from the comfyui.log were what untangled this; reasoning from the
  pipeline run alone conflated multiple causes.
- **The UI buttons hit the refresh endpoints, not the engine runners** — fixing a
  stage's engine path does not fix its tab button. Check both.
- A registry `context_window` / quant choice tuned on one ComfyUI/driver version
  is not portable across upgrades — re-profile after a ComfyUI bump.
