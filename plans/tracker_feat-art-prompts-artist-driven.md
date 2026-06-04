# Tracker: feat/art-prompts-artist-driven

Card 6a20a6c5 — Art Prompt Generation rework (artist-driven, LLM-authored, editable UI)

DONE: artist directory + art-direction loaders; artist_assignment module (grouped
policy + cameo knobs); prompt_builder rework (LLM-authored full prompt, cameo,
artist stamp, streaming callback); run_art_prompts internals swap; stage_hooks
art_prompt tile + hooks; server endpoints (state/refresh/knobs/save-card);
wizard_art_prompts.js rebuild (streaming + edit + artist reassign + cameo slider);
wizard.js SSE names; CLAUDE.md doc; tests (21 in test_prompt_builder.py).
Verified: ruff clean, import OK, full pytest 1701 passed / 1 skipped.

STOP after commit + push (no merge, no worktree removal, no Trello).
