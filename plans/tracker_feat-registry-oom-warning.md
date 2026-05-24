# Tracker: feat/registry-oom-warning

Card 69f86d59 — Registry-load warning when n_gpu_layers=-1 risks OOM

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked learnings doc)
- [x] Move card to Doing
- [x] Create worktree and branch

## Phase 2: Research
- [x] Read model_registry.py + models.toml
- [x] Read llamacpp benchmark learnings (the source of the card)
- [x] Trace registry load + _llamacpp_new_model usage
- [x] Confirm nvidia-smi available + output format
- [x] Confirm no gguf python lib; design self-contained GGUF header parse + filesize fallback
- [x] Confirm llmfacade `fit` path is the sibling card's domain (out of scope)

## Phase 3: Design
- [x] Draft approach (this plan)
- [x] Check for reusable patterns

## Phase 4: Implement
- [x] New module: vram_estimate.py (GGUF size, KV cache estimate, nvidia-smi free VRAM, verdict)
- [x] Wire into ModelRegistry.load() — warn >85% free, refuse (strict-only raise) >100% total
- [x] Add config knobs (MTGAI_DISABLE_VRAM_CHECK, MTGAI_VRAM_CHECK_STRICT) so a misestimate can't brick startup
- [x] Fix registry comment to match warn-only-default behaviour
- [ ] Update CLAUDE.md / models.toml comments if a contract changes

## Phase 5: Verify
- [x] ruff check (card files clean; 61 pre-existing errors in untouched tests, also on master)
- [x] ruff format --check (card files clean)
- [x] python -c "import mtgai"
- [x] pytest test_vram_estimate.py (37 passed) + test_validation (71 passed) + full suite (1051 passed; test_config.py skipped — pre-existing missing pydantic_settings dep, untouched by this card)
- [x] Fixed test_unknown_when_no_gguf_path: was calling _llamacpp_model("", gguf_path=None) → duplicate gguf_path arg; now _llamacpp_model(None) (gguf_path is the 1st positional)
- [x] Manual smoke: SKIPPED — real model load would OOM; estimation math validated against synthetic GGUF + mocked nvidia-smi instead (see summary "Manual testing needed")

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review and fix findings
- [ ] Pull master into branch
- [ ] Re-run lint + tests
- [ ] Merge to master + push
- [ ] Clean up worktree + branch
- [ ] Delete tracker
- [ ] Move card to Done
- [ ] Comment on card
- [ ] Follow-up cards
