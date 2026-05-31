# Tracker: feat/ctx-tier-variants

Card: **Multiple model variants by context length (find ctx sweet spots)** — `6a1c1940` [infra][design]
URL: https://trello.com/c/peHQmbl1

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, refs)
- [x] Move card to Doing
- [x] Create worktree + branch (`feat/ctx-tier-variants`), push upstream
- [x] Create this tracker doc

## Phase 2: Research / Measurement (the point of the card)
- [x] Read referenced code: model_settings.py, models.toml, llm_client._llamacpp_new_model, token_utils, vram_estimate, theme_extractor chunking, model_registry
- [x] Build transcript analyzer → per-stage MAX input-token table (from llmfacade JSONL `usage.prompt_tokens`)
- [x] Map convo/tool names → pipeline stages (audit script attributes by stage-log dir)
- [x] Compute analytical KV-VRAM per ctx tier for the carrier (vlad-updated) + iq2m via vram_estimate (SWA-aware, real GGUF header)
- [x] Quantify per-tier payoff: KV freed (~1.2 GiB max, sub-linear), residency crossover
- [x] Summarize findings (learnings/ctx-tier-sweet-spots.md)

## Phase 3: Design
- [x] Decide tier count + ctx values → 2 tiers: 128k theme / 48k downstream
- [x] Decide: hand-author twins (auto-derive deferred — only 1-2 twins)
- [x] Decide: validation via real full-run + ctx_log_audit.py (not synthetic benchmark)
- [x] Write plan doc
- [x] Align with user (2-tier + run-the-pipeline approved)

## Phase 4: Implement
- [x] Variant entries in models.toml (vlad-updated-48k + iq2m-48k)
- [x] Per-stage preset in model_settings.PRESETS (all-local-tiered)
- [x] Update CLAUDE.md + learnings doc

## Phase 5: Verify
- [x] ruff check + ruff format (clean)
- [x] python -c "import mtgai" (OK)
- [x] pytest (140 passed incl. 2 new twin/preset tests)
- [x] Manual smoke: registry loads twins; tiered preset resolves 128k/48k correctly
- [ ] User validation: full run + ctx_log_audit.py confirms 48k holds

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] Pull master, resolve conflicts
- [ ] Merge to master, clean up worktree/branch
- [ ] Delete plan + tracker
- [ ] Move card to Done + comment
- [ ] Follow-up cards if needed
- [ ] Final overview to user
</content>
