# Tracker: feat/skeleton-generation (card 69f9d1ef)

Reshape of the constraints stage into ONE "Skeleton Generation" stage.
Design: `plans/skeleton-generation.md`.

## State: MERGED to master, pending live validation

- [x] Design locked with user (one stage; default→string→LLM rewrite→tweaked_text;
      structured fields stay default; word-level diff UI; auto-run; local default)
- [x] Implemented: skeleton_relabel.py (was constraint_deriver.py), run_skeleton
      (default + relabel), SkeletonSlot.tweaked_text + render_slot_string,
      card_gen reads tweaked_text + programmatic batcher, /api/wizard/skeleton/*,
      wizard_skeleton.js diff UI, constraints stage/json/fold/batcher removed
- [x] settings: `skeleton` assignment + break-point + Settings UI row; local default
- [x] Verified: ruff clean, 1235 pytest pass, boot-smoke (endpoints + JS wired)
- [x] /review done — 2 should-fix + 2 nits all fixed (Settings row, unplaced-request
      warning + "N/M placed", build_reserved_slots note, gold spine)
- [x] CLAUDE.md + plan updated; merged to master (FF)
- [ ] LIVE VALIDATION (DoD): regenerate a real set (Transformers) and confirm the
      relabel/quality — needs the user's local-model env; card stays in Doing until done

## Follow-ups (separate cards)
- 6a15fa81 — review nits from the first (constraints) pass; re-check relevance
  (the LLM-batcher caching nit is now moot — batcher removed; the save-validation
  nit moot — endpoint reworked). Can likely be closed.
- 6a13f98e — theme-first rework of the post-balance skeleton_rev prompt.
