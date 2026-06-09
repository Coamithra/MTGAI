# Fix: art_select best-of-N judge is dead on the default config

Card 6a27f2b1 [bug].

## Context
The best-of-N art judge (`art_selector.select_best_version`) hard-pins the Anthropic
provider (`_get_provider("anthropic")`), but the shipped default `art_select`
assignment is a local, **text-only** Gemma. On the default config the judge call
fails per card, is caught by `select_art_for_set`, and silently falls back to
`source="auto_fallback"` picking v1. Result: every card's v2..vN Flux renders are
generated then thrown away, and best-of-N never runs — an expensive feature off by
default with no visible signal.

The `VISION_REQUIRED_STAGES` save-guard added on 2026-06-09 only covers the wizard
model picker; presets/defaults bypass `wizard_project_save_model`, so the default
config still ships a text-only judge.

## Design
Two changes (card fix options 1 + 3), keeping the local-by-default policy intact
(no change to the default model = no silent paid-cloud call).

### 1. Resolve the provider from the registry (`art_selector.select_best_version`)
Replace the hard-pinned `_get_provider("anthropic")` with
`_get_provider(_resolve_provider(model))` so a vision-capable model on any provider
routes correctly (today all vision LLM entries are Anthropic, so this is a no-op for
the working case + correct-by-construction for the future). Update the stale comment.

### 2. Pre-flight vision check + loud skip (`art_selector.select_art_for_set`)
Resolve the `art_select` model ONCE at stage start and check `supports_vision` on its
registry entry (a context-tier twin inherits its base's flag). When the judge model
is text-only:
- emit ONE WARN naming the model + the fix ("assign a vision-capable model"),
- for every multi-version card, skip the LLM call and auto-pick v1 with
  `source="auto_fallback"` + a clear `judge_skipped` reason (counted in a new
  `judge_skipped` summary field) — no per-card exception spam, no wasted call.
- summary gains `judge_skipped` (int), `judge_skipped_reason` (str|None),
  `art_select_model` (str).

New helper `_judge_is_vision_capable(model_id) -> bool` (unknown id ⇒ False ⇒ skip
loudly).

### 3. Surface the skip in the engine (`pipeline/stages.run_art_gen`)
Add a `judge_skipped` branch to the stage `detail` message, mirroring the existing
`judge_failed` branch.

## Out of scope
- Changing the default/preset `art_select` assignment to a hosted vision model
  (violates local-by-default).
- Avoiding the *upstream* waste of generating v2..vN Flux versions when the judge
  can't run (lives in `image_generator.generate_art_for_set`; bigger change).
- Tightening `VISION_REQUIRED_STAGES` picker to "vision AND Anthropic-capable".

## Tests (`tests/test_art_selector.py`)
- Update `test_judge_failure_falls_back_to_v1` + `test_judge_success_path_unchanged`
  to assign a vision-capable `art_select` model (else the new pre-flight skips the
  judge and they no longer exercise it).
- New `test_text_only_judge_skips_best_of_n`: default (text-only) judge ⇒
  `select_best_version` never called, v1 auto-picked, `summary["judge_skipped"]==1`,
  reason set, `auto_fallback` decision.
- New `test_judge_is_vision_capable`: True for a vision model_id, False for a
  text-only one + unknown id.

## Verification
- `ruff check .` / `ruff format .` clean
- `python -c "import mtgai"`
- `pytest tests/test_art_selector.py` + full `pytest`
