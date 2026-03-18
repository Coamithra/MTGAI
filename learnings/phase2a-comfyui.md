# Phase 2A Learnings: ComfyUI + Flux + Art Pipeline

## What We Built

- ComfyUI installed at `C:\Programming\ComfyUI` with Python 3.12 venv
- ComfyUI-GGUF custom node for loading quantized models
- Flux.1-dev Q8_0 GGUF pipeline: UnetLoaderGGUF → DualCLIPLoaderGGUF → FluxGuidance → KSampler → VAEDecode
- API workflow JSON at `backend/mtgai/art/workflows/flux_dev_gguf.json`
- `backend/mtgai/art/image_generator.py` — batch art generation via ComfyUI API
- `backend/mtgai/art/art_selector.py` — Haiku vision-based art version selector
- Auto-start ComfyUI, VRAM pre-check, resumable progress, per-card logging
- HTML report generation with side-by-side version comparison

## Hardware

- GPU: NVIDIA RTX 4070 Ti, 12GB VRAM
- Flux Q8_0 GGUF fits comfortably (~9.6GB torch VRAM at runtime, ~2GB free)
- Research originally assumed 8GB VRAM — 12GB means we can use Q8_0 instead of Q5_K
- Q5_K_S also downloaded as fallback at `models/unet/flux1-dev-Q5_K_S.gguf`

## Models

| File | Size | Source |
|------|------|--------|
| `flux1-dev-Q8_0.gguf` | 12GB | `city96/FLUX.1-dev-gguf` (ungated) |
| `flux1-dev-Q5_K_S.gguf` | 8GB | `city96/FLUX.1-dev-gguf` (ungated, fallback) |
| `t5-v1_1-xxl-encoder-Q8_0.gguf` | 4.8GB | `city96/t5-v1_1-xxl-encoder-gguf` (ungated) |
| `clip_l.safetensors` | 235MB | `comfyanonymous/flux_text_encoders` (ungated) |
| `ae.safetensors` | 320MB | `black-forest-labs/FLUX.1-dev` (gated, needs HF login) |

## Performance

Final production settings (30 steps, 1024x768, Q8_0):
- **~40s per image** (warm, models already in VRAM)
- **~60-80s first image** (cold start, model loading)
- Resolution: 1024x768 (landscape, 1.33:1 — close to art box 1.38:1)
- Output: ~1-2MB PNG per image
- Full batch: 66 cards × 3 versions × 40s = **~2.2 hours**

### Resolution Decision

Print specs require 661×478px art box at 300 DPI. We tested two resolutions:
- **1536×1024** (original): 5x more pixels than needed, ~78s/image at 30 steps
- **1024×768** (final): 2.4x more pixels than needed, ~40s/image at 30 steps

1024×768 is nearly **2x faster** with zero quality loss for our use case. Still 60% more pixels than the art box, giving cropping flexibility without waste.

### Steps Decision

- **20 steps** (original): ~48s at 1536×1024. Decent quality.
- **30 steps** (final): ~40s at 1024×768. Finer details, 15% better quality per subjective test. Diminishing returns past 30.
- At 1024×768, the resolution reduction more than compensated for the extra steps.

## Key Learnings

### 1. CRITICAL: ComfyUI subprocess.PIPE Crashes on Windows

**The #1 bug that burned hours of debugging.** When starting ComfyUI via `subprocess.Popen(stdout=subprocess.PIPE, stderr=subprocess.STDOUT)`, tqdm's progress bar tries to flush stderr and crashes with `OSError: [Errno 22] Invalid argument`. Every generation silently fails.

**Symptoms:** ComfyUI starts, models load, prompts queue, but every generation returns `status_str: "error"` with `exception_message: "[Errno 22] Invalid argument"` in the KSampler node. The poller sees no completion and times out.

**Fix:** Use `subprocess.DEVNULL` for both stdout and stderr:
```python
proc = subprocess.Popen(
    [python_exe, main_py, "--listen", "127.0.0.1", "--port", "8188"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
```

**Why we didn't catch it sooner:** The first test images worked because ComfyUI was started manually in a real terminal (where stderr works fine). The bug only appeared when the batch script started ComfyUI as a subprocess.

### 2. VRAM Pre-Check Prevents Cryptic Failures

Added `check_vram()` that runs before starting ComfyUI:
- Queries `nvidia-smi` for free VRAM
- Lists GPU-using apps by name (Chrome, Discord, Reaper, etc.) if VRAM is insufficient
- Gives actionable error: "Close some of these and try again"
- Threshold: 10,500MB free (models need ~9.6GB + ~1GB compute)

Note: On Windows WDDM, nvidia-smi reports "N/A" for per-process VRAM. We can only show process names, not individual VRAM usage.

### 3. Zombie ComfyUI Processes

ComfyUI started via subprocess can outlive the parent Python script (e.g., if the script crashes or times out). The zombie holds port 8188 and ~10GB RAM. Subsequent runs fail with "ComfyUI process exited unexpectedly" because the port is taken.

**Mitigation:** The batch script uses try/finally to terminate ComfyUI, and `ensure_comfyui()` checks if the port is already in use. If stuck, manually kill: `taskkill /PID <pid> /F`.

### 4. Local Flux GGUF Quality is "Rough" But Serviceable

The Q8_0 quantized local model produces serviceable but noticeably lower quality than cloud/full-precision Flux. Fine for pipeline development and draft art, but likely insufficient for final print-quality card art.

**Decision:** Use local Flux for iteration and pipeline testing. Plan to evaluate cloud services (fal.ai / "nano banana", Replicate, Midjourney) for production-quality art at a later stage. The image generation backend is designed to be swappable.

### 5. Multi-Version Generation + AI Selection is Cheap and Effective

Generating 3 versions per card and letting Haiku pick the best one is an excellent strategy:
- **Cost:** ~$0.006/card for Haiku vision review (3 images + prompt + reasoning)
- **Quality:** Haiku correctly identified artifacts, prompt mismatches, and composition issues
- **Agreement:** 4/5 match with human picks on a 5-card test; the 2 disagreements had valid reasoning
- **Speed:** ~6 seconds per card review

Haiku caught things like:
- Watermark artifacts in generated images
- Subject mismatch (skeleton rendered instead of "gaunt human")
- Missing setting-specific elements (no sci-fi ruins when prompt requested post-apocalyptic)
- Anatomical oddities (spherical knee protrusions)

**Full set cost estimate:** 66 cards × $0.006 = **~$0.40** for AI art selection

### 6. Hands/Fingers Are the Main Artifact Issue

Local Flux GGUF consistently struggles with open hands and spread fingers. Strategies that help:
- **Object-gripping poses** (weapons, tools, shields) hide finger artifacts
- **Prayer/clasped hands** work well
- **Profile/silhouette** angles minimize hand visibility
- **Landscapes and objects** (artifacts, lands) have zero hand issues

Consider biasing art prompts toward object-holding compositions for creature cards.

### 7. Flux.1-dev is a Gated Model

The VAE (`ae.safetensors`) lives in the gated `black-forest-labs/FLUX.1-dev` repo. Requires:
- Accepting the license at the model page on HuggingFace
- HF token authentication (`huggingface_hub.login()`)
- Token stored in `.env` as `HUGGINGFACE=hf_...`

The GGUF quantizations of the main model and T5 encoder are hosted by `city96` and are ungated.

### 8. HuggingFace CLI Doesn't Work in Git Bash on Windows

`huggingface-cli` installed to the venv Scripts dir but Git Bash can't execute it. Workaround: use the Python API directly:
```python
from huggingface_hub import hf_hub_download
hf_hub_download('repo/name', 'filename', local_dir='target_dir')
```

### 9. ComfyUI Flux Workflow Specifics

- **CFG must be 1.0** — Flux dev uses internal guidance via `FluxGuidance` node (set to 3.5), NOT classifier-free guidance
- **Must use `EmptySD3LatentImage`** not `EmptyLatentImage` — Flux uses 16-channel latent space
- **`DualCLIPLoaderGGUF`** with `type: "flux"` loads CLIP-L as encoder 1 and T5-XXL as encoder 2
- **Sampler:** euler + simple scheduler, 30 steps for quality (20 is minimum viable)
- **Negative prompt:** required by KSampler node but should be empty string for Flux

### 10. ComfyUI API is Simple

Queue a prompt via POST to `http://127.0.0.1:8188/prompt` with `{"prompt": workflow_dict}`. Poll `http://127.0.0.1:8188/history/{prompt_id}` for completion. No auth needed for local server. Check for `status_str == "error"` in history to catch generation failures — don't just wait for timeout.

## Pipeline Architecture

```
Card JSON (with art_prompt)
    ↓
image_generator.py → ComfyUI API → 3 versions per card → output/sets/ASD/art/
    ↓
art_selector.py → Haiku vision → pick best version → selection logs + HTML report
    ↓
Human review of HTML report → approve/reject/regenerate
```

## Files Created

- `backend/mtgai/art/image_generator.py` — batch generation, VRAM check, auto-starts ComfyUI, resumable
- `backend/mtgai/art/art_selector.py` — Haiku vision selector, HTML report generator
- `backend/mtgai/art/workflows/flux_dev_gguf.json` — ComfyUI API workflow (10 nodes)
- `backend/scripts/generate_all_art.py` — batch runner for full set generation
- `output/sets/ASD/art/` — generated art (versioned: `*_v1.png`, `*_v2.png`, `*_v3.png`)
- `output/sets/ASD/art-generation-logs/` — per-card generation metadata + batch progress
- `output/sets/ASD/art-selection-logs/` — per-card Haiku review results
- `output/sets/ASD/reports/art-selection-report.html` — visual comparison report

### 11. GPU State Accumulation Causes Silent Crashes During Batch Generation

Character portrait generation (768×1024) crashed silently after 2-7 images. Both Python and ComfyUI processes died with no trace — no crash.json, no Event Viewer entries, no GPU TDR errors. Pattern worsened each run (7→5→2 images), suggesting stale GPU state accumulating.

**Root cause:** No CUDA cache cleanup between image generations. ComfyUI accumulates CUDA cache, history buffers, and internal state across every generation call.

**Fix:** Added `flush_comfyui()` to `image_generator.py` — calls two ComfyUI API endpoints after every image:
- `POST /free {"unload_models": false, "free_memory": true}` — triggers `torch.cuda.empty_cache()` inside ComfyUI
- `POST /history {"clear": true}` — clears completed generation history from RAM

This replaced the heavy-handed restart-every-2-images workaround that was previously needed.

**Why card art (198 images) worked but portraits crashed:** Unknown. Possibly the portrait dimensions (768×1024 vs 1024×768), session length, or subtle CUDA allocator behavior differences. The flush fix prevents the issue regardless.

### 12. Known MTG Characters Need Official Reference Art

Flux has no concept of specific MTG characters. Generating Jace portraits produced generic "young man in blue robes" — nothing recognizable as Jace. For canonical planeswalkers/characters appearing in custom sets, fetch official art from Scryfall instead:
- API: `https://api.scryfall.com/cards/named?fuzzy=<character_name>` → `image_uris.art_crop`
- Pick cards where the face is clearly visible (many Jace arts have face hidden under hood)
- Save as `<slug>_official.png` alongside generated portraits

## What's Next

- Character reference portraits DONE (24/24 generated, 8/8 picked)
- Jace uses official Scryfall art (Jace, Wielder of Mysteries — best facial clarity)
- Next: 2A-6 sample card arts with character identity injection (Kontext Dev + PuLID)
- Evaluate cloud services for production art quality upgrade
