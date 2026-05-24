# TC-3: Archetype generation pipeline stage

## Context

The pipeline turns setting prose -> mechanics -> skeleton -> cards. Draft
archetypes (the 10 two-color "play this deck" identities) are currently produced
in two suboptimal places: the theme extractor emits a rough `draft_archetypes`
list from prose *before* mechanics exist, and the legacy `prompts.py` /
`generation` code paths read those. TC-3 adds a dedicated LLM stage that
generates a clean, per-set archetype list informed by both the setting prose AND
the approved mechanics, written to `<asset>/archetypes.json`. This is the
single source later stages (TC-6 prompts, TC-7 skeleton) will consume.

Mirrors the shipped TC-2 mechanic stage: a generator module (prompt assembly +
tool schema + post-processing + the LLM round-trip), a stage runner, a prompt
pair under `pipeline/prompts/`, and unit tests with a mocked LLM.

## Design

### New: `backend/mtgai/generation/archetype_generator.py`
Mirrors `mechanic_generator.py`.

- `COLOR_PAIRS: list[str]` — the canonical 10 two-color pairs in WUBRG guild
  order: `WU WB WR WG UB UR UG BR BG RG`.
- `ARCHETYPE_TOOL_SCHEMA` — tool-use schema. Array `archetypes`, each item:
  `color_pair` (enum of the 10 pairs), `name`, `description` (1-2 sentence
  strategy), `primary_mechanics` (string[]), `signpost_uncommon` (string —
  the gold uncommon that signals the archetype), `speed`
  (enum: aggro/midrange/control/tempo/combo). Schema field names match the
  existing `DraftArchetype` model so callers can `DraftArchetype(**a)`.
- Prompt assembly:
  - `_format_mechanics_block(approved)` — render approved mechanics (name,
    colors, complexity, design notes) so the LLM ties archetypes to real
    set mechanics.
  - `_format_constraints_block`, `_format_creature_types_block`,
    `_format_characters_block` — reuse the same prose-context shaping the
    mechanic generator uses (theme.json fields).
  - `build_archetype_prompts(theme, approved, set_name)` -> (system, user)
    from `archetype_system.txt` / `archetype_user.txt`.
- Post-processing:
  - `normalize_color_pair(raw)` — uppercase + reorder to WUBRG guild order so
    "UW"/"wu" -> "WU"; returns None if not a valid 2-color pair.
  - `dedupe_and_complete(archetypes)` — keep one archetype per color pair, in
    canonical order, dropping malformed/duplicate pairs. Does NOT fabricate
    missing pairs (a short list is a soft failure surfaced by the runner).
- `generate_archetypes(*, theme=None, approved=None) -> dict` — the LLM
  round-trip. Reads `theme.json` + `mechanics/approved.json` from the active
  project when args are None, resolves the model via
  `settings.get_llm_model_id("archetypes")`, calls `generate_with_tool`,
  writes a per-call log sidecar (`<asset>/archetypes/logs/<isots>.json`,
  same shape as the mechanic log), returns
  `{"archetypes": list[dict], "input_tokens", "output_tokens", "model_id"}`.
  Raises `RuntimeError` if fewer than `MIN_ARCHETYPES` (8) survive dedupe.

### New prompts: `pipeline/prompts/archetype_system.txt`, `archetype_user.txt`
System prompt carries set name, theme, flavor, approved-mechanics block,
creature types, constraints, characters, and the 10-pair list with the WUBRG
guild names. User prompt asks for exactly 10 archetypes (one per pair) with the
signpost-uncommon + primary-mechanics fields, Tarkir/guild style.

### `backend/mtgai/pipeline/stages.py`
- `run_archetypes(progress_cb, emitter)` — AUTO stage (no break point).
  Mirrors `run_mechanics`: requires `theme.json` + `mechanics/approved.json`,
  holds the AI lock, calls `generate_archetypes()`, writes
  `<asset>/archetypes.json`, emits an overview `kv` section + a `table`
  section (Pair / Name / Speed / Strategy). Returns a `StageResult`.
- Register `"archetypes": run_archetypes` in `STAGE_RUNNERS` between
  `mechanics` and `skeleton`.
- `clear_archetypes()` — `_remove_path(_set_dir() / "archetypes.json")` and the
  `archetypes/` log dir; register in `STAGE_CLEARERS`.

### `backend/mtgai/pipeline/models.py`
- Insert `{"stage_id": "archetypes", "display_name": "Archetype Generation",
  "review_eligible": True}` into `STAGE_DEFINITIONS` between `mechanics` and
  `skeleton`. (`load_state` already syncs new stages into old projects.)

### Settings
`archetypes` is ALREADY present in `LLM_STAGE_NAMES`, `DEFAULT_LLM_ASSIGNMENTS`
(sonnet), and the `recommended`/`all-haiku`/`all-local` presets — no change
needed there. It is NOT a structural break point, so it runs automatically.

### `backend/mtgai/generation/prompts.py` (consume archetypes.json)
The card lists `prompts.py` as a touch point ("consume archetypes.json instead
of hardcoded strings — see TC-6"). `prompts.py` already reads
`theme["draft_archetypes"]`, not hardcoded strings. Full prompts-module rework
is explicitly TC-6. For TC-3 we keep the change minimal and forward-compatible:
add a `load_archetypes()` helper in the generator + have `build_user_prompt`/
`format_slot_specs` accept an optional `archetypes` list that, when provided,
overrides the theme's `draft_archetypes`. This wires the new file through
without rewriting the prompts module (TC-6 owns that).

## archetypes.json schema (downstream contract)

A JSON array; each element matches `mtgai.models.set.DraftArchetype` plus a
`speed` hint:

```json
[
  {
    "color_pair": "WU",
    "name": "Ancient Technology",
    "description": "Control the board with automatons and relics; grind value with Salvage.",
    "primary_mechanics": ["Salvage", "Malfunction"],
    "signpost_uncommon": "A WU gold creature that salvages on ETB and rewards artifacts in hand.",
    "speed": "control"
  }
]
```

- `color_pair`: one of `WU WB WR WG UB UR UG BR BG RG` (WUBRG guild order).
- `name`: short archetype name.
- `description`: 1-2 sentence strategy (maps to `DraftArchetype.description`).
- `primary_mechanics`: list of approved-mechanic names this deck leans on.
- `signpost_uncommon`: prose describing the gold uncommon that signals the deck.
- `speed`: aggro | midrange | control | tempo | combo (a hint; not on the
  Pydantic model, tolerated as an extra key — `DraftArchetype` ignores extras
  by default, and downstream reads `color_pair`/`name`/`description`).

Exactly one entry per color pair, in canonical order, normally 10 entries
(>= 8 enforced).

## Tests — `backend/tests/test_archetype_generator.py`
Pure functions + a mocked LLM round-trip (no real model, per the OOM rule):
- `test_build_archetype_prompts_substitutes_fields` — set name, theme,
  approved-mechanic names, constraints, characters thread into the prompts.
- `test_build_archetype_prompts_handles_missing_blocks` — placeholders, no
  KeyError on a bare theme / empty approved list.
- `test_normalize_color_pair` — `UW`->`WU`, `wu`->`WU`, lowercase, invalid
  ("WW", "X", "WUB", "") -> None.
- `test_dedupe_and_complete_keeps_one_per_pair_in_order` — dupes collapse,
  output is in WUBRG guild order, malformed dropped.
- `test_generate_archetypes_returns_normalized` (mocked `generate_with_tool`,
  pinned active project + theme.json + approved.json) — returns 10 normalized
  archetypes, token counts pass through.
- `test_generate_archetypes_raises_when_undercounted` — < 8 -> RuntimeError.

Plus a clearer test added to `test_pipeline/test_stage_clearers.py`:
- `test_clear_archetypes_removes_file_and_logs`.

## Out of scope
- A dedicated wizard Archetypes tab / human-review UI (AUTO stage; no break
  point). Archetypes are review-eligible so a user *could* add a break point,
  but no bespoke tab is built here.
- The full `prompts.py` / skeleton rework (TC-6 / TC-7). TC-3 only writes
  `archetypes.json` + threads an optional override param.
- Regenerating the theme extractor's `draft_archetypes` (kept as the pre-
  mechanic seed).

## Verification
- `ruff check .` / `ruff format .` clean.
- `python -c "import mtgai"`.
- `pytest tests/test_archetype_generator.py tests/test_pipeline/test_stage_clearers.py
  tests/test_validation/` green.
- Manual (deferred, needs a real model): open a project with a theme + approved
  mechanics, run the archetypes stage, confirm `archetypes.json` has 10
  pair-keyed entries and the wizard run view shows the table.
