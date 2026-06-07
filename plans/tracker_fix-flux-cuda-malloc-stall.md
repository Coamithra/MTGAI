# Tracker: fix/flux-cuda-malloc-stall

Card 6a2545cb — "Art tail still ~40s/step even with Q5: --disable-cuda-malloc causes per-step GPU memory stall"

## Phase 1: Pick Up the Card
- [x] Pull latest master (worktree off origin/master HEAD ad2cdcf, includes PR#31 Q5 fix)
- [x] Read the card (description)
- [x] Move card to Doing
- [x] Create worktree and branch (.trees/fix/flux-cuda-malloc-stall) + push

## Phase 2: Research
- [x] Read the referenced code (image_generator.py start_comfyui, Popen args ~line 299)
- [x] git log/blame on the `--disable-cuda-malloc` line

### Findings: documented instability?
The flag `--disable-cuda-malloc  # Avoid cudaMallocAsync instability` was added in
commit `7ce00fc` ("Phase 2A: flush_comfyui() fix for GPU state accumulation + crash
resilience", 2026-03-18). That commit's REAL fix for the silent batch-generation
crashes was `flush_comfyui()` (POST /free + /history between images) — documented in
`learnings/phase2a-comfyui.md` §11 "GPU State Accumulation Causes Silent Crashes".
That learnings entry attributes the crashes to GPU state accumulation and credits the
flush fix, NOT the cuda-malloc flag. The flag's comment is bare/speculative ("Avoid
cudaMallocAsync instability") with **no documented crash/hang tied specifically to
cudaMallocAsync** anywhere in the repo or commit history.

**Decision: simply remove the flag (the simpler correct option).** Per the card and
CLAUDE.md guidance: no documented instability => remove. The async allocator
(cudaMallocAsync, ComfyUI's default) is required for fast diffusion; the measured 13x
slowdown (2.90s/step vs 40.1s/step, both "full load: True" on a clean 12GB GPU)
vastly outweighs a hypothetical instability, and the real crash cause it was bundled
with is already independently fixed by flush_comfyui(). No env mitigation added.

## Phase 4: Implement
- [x] Remove `--disable-cuda-malloc` element + trailing comment from start_comfyui Popen args
- [x] No CLAUDE.md change needed (no documented contract changes)

## Phase 5: Verify
- [x] Add unit test asserting start_comfyui's Popen args do NOT contain "--disable-cuda-malloc"
- [x] ruff check . / ruff format .
- [x] python -c "import mtgai"
- [x] pytest (full suite)

## Phase 6: Ship
- [x] Commit + push
- [x] /review + fix findings
- [x] Pull master into branch
- [x] PR + self-merge
- [x] Clean up worktree/branch
- [x] Delete tracker
- [x] Move card to Done + comment
