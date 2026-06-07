# Tracker: fix/free-vram-before-comfyui

Trello card 6a252d96 — Art tail crashes after LLM stages: local LLM VRAM never freed before ComfyUI/Flux

## Phase 1: Pick Up the Card
- [x] Pull latest master (fetched origin/master @ c6e064b)
- [x] Read the card
- [x] Move card to Doing
- [x] Create worktree and branch

## Phase 2: Research
- [ ] Read llm_client.py _PROVIDERS + interrupt() pattern (around :240-270)
- [ ] Read llmfacade llamacpp.py unload_all/unload/shutdown (:1293-1356)
- [ ] Read character_portraits.py:533 ensure_comfyui call site
- [ ] Read image_generator.py:839 ensure_comfyui + :264 ensure_comfyui + check_vram
- [ ] Check import direction / cycle risk between art layer and llm_client

## Phase 3: Design
- [ ] Decide: centralize in ensure_comfyui vs call from two stage callers
- [ ] Justify decision in tracker

## Phase 4: Implement
- [ ] Add llm_client.unload_local_models() helper
- [ ] Call before ensure_comfyui in char_portraits + image_generator

## Phase 5: Verify
- [ ] ruff check . / ruff format .
- [ ] python -c "import mtgai"
- [ ] pytest (add focused unit test for helper + call-order)

## Phase 6: Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] pull master into branch
- [ ] PR + self-merge
- [ ] clean up worktree/branch
- [ ] delete tracker
- [ ] move card to Done + comment

## Design decision
Centralize the unload INSIDE `ensure_comfyui()` (image_generator.py), via a lazy
`from mtgai.generation.llm_client import unload_local_models` placed right before
`check_vram()`. Justification:
- No cycle risk: `llm_client` never imports the art layer (verified by grep);
  the art layer already depends on `llm_client` one-directionally
  (character_portraits.py:49 already imports it at module level).
- Both crash sites (char_portraits.py:533, image_generator.py:839) route through
  `ensure_comfyui()`, plus char_portraits' ComfyUI-restart path (:558ff). One
  edit covers every ComfyUI entry point.
- Placing the unload immediately before `check_vram()` means the VRAM check sees
  the freed memory (nvidia-smi is shelled fresh each call, no caching).
- Lazy import inside the function keeps module-import graph clean (no import-time
  coupling of the art layer to llm_client construction).

Helper `llm_client.unload_local_models()`: best-effort, only acts if the
llamacpp provider was ALREADY constructed (`_PROVIDERS.get("llamacpp")`, never
constructs one), mirrors the existing `interrupt_local_inference()` pattern;
swallows `UnsupportedFeature` (cloud-only / bare llama-server) and any error,
logs at info/debug. No-op when no llamacpp provider is cached.
