# Plan: UI warning when conformance base is too small for the set size

Card 6a27f773. Follow-up to PR #96 (interaction-gate low-context fix).

## Context
The interaction step now bounds its cumulative existing-context to the assigned
conformance model's actual `context_window` and logs a WARN when it drops context
(`interactions._bound_existing_context` + the WARN in `analyze_interactions`).
That degradation is loud in the **server log** but invisible to the user driving
the wizard. Add a non-blocking, user-facing notice on Project Settings, mirroring
the existing `VISION_REQUIRED_STAGES` text-only-model warning.

## Design

**Projection (backend, authoritative).** Estimate the interaction step's *largest*
cumulative batch prompt for the configured `set_size` and compare it to the
conformance stage's resolved context window (which already accounts for the
≥400-set_size full-window exception via `get_llm_model_id`).

- `analysis/interactions.py`: new pure `project_largest_batch_tokens(set_size,
  mechanic_count=0) -> int`. Builds the largest batch (≈all gate cards as existing
  context + a final `BATCH_SIZE` of new cards) from synthetic representative card
  lines and measures it with the **same** `_build_batch_prompt` +
  `count_messages_tokens` the runtime fit-check uses, so the projection tracks the
  real bound. Uses `set_size` as the gate-card count (basics/reprints are a small
  fraction; over-estimating context is the safe direction for a warning).
- `settings/model_settings.py`: new `ModelSettings.conformance_context_status() ->
  dict` — for the *currently assigned* conformance model, returns
  `{model_name, context_window, set_size, projected_tokens, budget_tokens, fits}`.
  `context_window` is the **effective** window (post twin / ≥400 exception, via
  `get_llm_model_id("conformance")`); `budget_tokens` mirrors `check_pre_call`:
  `int(ctx*(1-SAFETY_MARGIN)) - MAX_TOKENS`. `fits = projected <= budget`.

**Payload + reactivity (backend).** Thread the blob through both project payloads
and recompute it on the two inputs that change it (model + set_size):
- `_project_payload` + `/api/project/new` draft: add `conformance_context`.
- `/api/wizard/project/models` response: add `conformance_context` (from new
  settings) so a conformance-model change updates the note.
- `/api/wizard/project/params` response: add `conformance_context` so a set_size /
  mechanic_count change updates the note.

**Picker note (JS).** `wizard_project.js renderModelAssignmentsSection`: on the
`conformance` row, render an amber `wiz-vision-warn` note when
`conformance_context.fits === false`. `saveModel` + `saveParams` capture the
recomputed blob from their responses and `rerenderModelAssignments` so the note is
live.

## Out of scope
- The optional interaction `BATCH_SIZE` clamp for tiny windows (a separate, larger
  runtime change to `interactions.py`; left as a possible follow-up). The warning
  is the user-facing ask.
- Full set_size reactivity already covered via the `/params` recompute.

## Tests
- `tests/test_analysis/` (or nearest): `project_largest_batch_tokens` grows
  monotonically with set_size and is 0 at set_size 0.
- `tests/` settings: `conformance_context_status` reports `fits=False` for a small
  window + large set, `fits=True` for a roomy window; respects the ≥400 exception.

## Verification
- `ruff check . && ruff format .`, `python -c "import mtgai"`, `pytest`.
- Manual: `serve --open`, Project Settings → set a large set_size + assign a
  low-context local model to Conformance → amber note appears; switch to a
  large-window model → note clears.
