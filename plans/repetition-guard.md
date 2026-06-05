# Adopt llmfacade RepetitionGuard; remove our own repetition-loop detector

Card: `6a235414` (refactor). Branch: `refactor/repetition-guard`.

## Context
llmfacade now ships built-in repetition-loop detection: `RepetitionGuard` (config)
+ `RepetitionLoopError` (raised), both exported from the package top level. Its
detector (`detect_repetition_loop`) uses the **exact same period-banded thresholds**
we hand-rolled in `theme_extractor` (tail 4096, max_period 120, check_every 64) —
it was ported from MTGAI. So `RepetitionGuard()` with defaults reproduces our
current detection byte-for-byte.

Behaviour:
- `send`/`asend` (guard active): runs under the hood as a stream, checks every
  `check_every` chars, on a hit discards + retries up to `retries` (default 2)
  escalating `repeat_penalty`/`dry`, then raises `RepetitionLoopError` (or, with
  `on_exhausted="return_last"`, returns the last looping attempt).
- `stream`/`astream` (guard active): abort on first hit and raise
  `RepetitionLoopError` (no transparent retry — deltas already yielded).
- Scans **assistant output text + tool-call arguments**, NOT thinking/reasoning
  blocks. (Our own detector also only scanned streamed output text, so the swap is
  behaviour-preserving. True thinking-loop detection is a llmfacade follow-up.)

llmfacade is an **editable path dep** (`../../LLMFacade`), so `RepetitionGuard` /
`RepetitionLoopError` are already importable — no version bump.

## What we own today (inventory)
The ONLY hand-rolled repetition-*detection* logic is in
`backend/mtgai/pipeline/theme_extractor.py`:
- `_detect_tandem_repeat`, `_detect_repetition_loop` (public entry), the bands
  (`_build_repetition_thresholds`, `_MIN_REPS_BY_PERIOD`, `_MIN_TOTAL_BY_PERIOD`),
  the constants (`_REPETITION_TAIL_CHARS`, `_REPETITION_MAX_PERIOD`).
- Mid-stream check (every 64 chars) in `_stream_single_call` → emits a
  `repetition_abort` outcome + `error` event with `partial_text`.
- Post-call check `_detect_repetition_loop(raw)` in `_attempt_json_subcall`.
- Tests: `backend/tests/test_pipeline/test_repetition_detector.py`.

Everything else the audit surfaced is NOT repetition detection and **stays**:
- Truncation detection (`OutputTruncatedError`, `finish_reason=="length"`) in
  `token_utils` / `gate_common` — a distinct concern.
- Preventive temperature floor `floor_for_local` (`temperatures.py`) — prevention.
- Gate DRY/temp escalation on a *truncation* retry — complementary, truncation-triggered.
- `theme_extractor._RETRY_REPEAT_PENALTIES` — the subcall *retry* escalation
  (response, not detection); the guard doesn't retry on streams so this still owns it.

## Design (file-by-file)

### 1. `mtgai/generation/llm_client.py` — central adoption
- Import `RepetitionGuard`, `RepetitionLoopError` from llmfacade.
- Module-level guards (defaults == our former bands):
  - `_LLAMACPP_REP_GUARD = RepetitionGuard(escalate_dry=True)` — tool + stream calls.
  - `_LLAMACPP_REP_GUARD_TEXT = RepetitionGuard(escalate_dry=True, on_exhausted="return_last")`
    — free-text `generate_text`, preserving its "partial reply is still useful, no raise" contract.
- `_generate_llamacpp` (tool, `send`): pass `repetition_detection=_LLAMACPP_REP_GUARD`
  on the convo. Wrap `convo.send` with `except RepetitionLoopError` (BEFORE the
  `except LLMError`, since it subclasses LLMError) → re-raise as `OutputTruncatedError`
  with the loop detail. This routes a detected loop into **every existing
  truncation-retry handler** (`generate_gate_tool`, `reprint_selector`,
  `slot_grouper`, `mechanic_generator` escalation) unchanged — same as a real
  truncation, which is what an unrecoverable loop effectively is.
- `_generate_text_llamacpp` (`send`): `repetition_detection=_LLAMACPP_REP_GUARD_TEXT`
  (return_last → no behavioural break; transparent retry is pure upside).
- `_stream_text_llamacpp` (`stream`): `repetition_detection=_LLAMACPP_REP_GUARD`.
  The stream aborts + raises `RepetitionLoopError` mid-iteration; both consumers
  (`gate_common.stream_flag_batch`, `skeleton_relabel`) already catch `Exception`
  and treat it as a retryable mid-stream failure — **no change needed there**.
- Anthropic paths: guard NOT set (cloud models don't fall into Gemma-style loops;
  avoids changing cloud behaviour/cost).

### 2. `mtgai/pipeline/theme_extractor.py` — swap detector for the guard
- Delete `_detect_tandem_repeat`, `_detect_repetition_loop`,
  `_build_repetition_thresholds`, `_MIN_REPS_BY_PERIOD`, `_MIN_TOTAL_BY_PERIOD`,
  `_REPETITION_TAIL_CHARS`, `_REPETITION_MAX_PERIOD`, the whole "Repetition loop
  detection" section + the module-comment paragraph describing it.
- Its own streaming convo (`_stream_single_call`): set `repetition_detection`
  (default `RepetitionGuard()`) on the convo. Remove the mid-stream
  `_detect_repetition_loop(theme_text)` check + the `chars_since_check` plumbing
  that only fed it.
- Catch `RepetitionLoopError` raised from `convo.stream`: map to the existing
  `repetition_abort` outcome + `error` event (`message=exc.detail`,
  `partial_text=exc.partial_text`), preserving the UI + the `_run_json_subcall`
  retry-with-escalating-repeat_penalty behaviour byte-for-byte.
- Remove the post-call `_detect_repetition_loop(raw)` check in
  `_attempt_json_subcall` (the guard caught it mid-stream already).
- Keep `_RETRY_REPEAT_PENALTIES` + the subcall retry loop (response, not detection).

### 3. Tests
- Delete `tests/test_pipeline/test_repetition_detector.py` (it tested the deleted
  detector; the band logic now lives + is tested in llmfacade).
- Add a small `tests/test_generation/test_repetition_guard_wiring.py`: assert
  `_LLAMACPP_REP_GUARD` is a `RepetitionGuard` and that `_generate_llamacpp`
  converts a `RepetitionLoopError` from `send` into `OutputTruncatedError` (monkeypatch
  the convo). Keeps the contract under test without re-testing llmfacade's detector.

### 4. Docs
- `CLAUDE.md` "Local LLMs": replace the implication that we hand-roll loop detection
  with a note that loop detection is delegated to llmfacade's `RepetitionGuard`
  (configured centrally in `llm_client`; converts to `OutputTruncatedError` on the
  tool path; streams abort→retry); keep the temp-floor + DRY-on-truncation notes.
- Trim the `theme_extractor` module comment that described the bespoke detector.

## Out of scope
- True thinking/reasoning-token loop detection (llmfacade doesn't scan thinking
  blocks) — follow-up card against LLMFacade.
- Removing truncation detection or the preventive temp-floor/DRY machinery.
- Touching the Anthropic code paths.

## Verification
- `ruff check .` + `ruff format .` clean.
- `python -c "import mtgai"`.
- `pytest` (esp. `tests/test_pipeline`, `tests/test_generation`).
- Manual smoke (flag for user): a local theme extraction; confirm a repetition loop
  is still caught (now via the guard) + retried/aborted as before. Confirm Anthropic
  path unaffected.
