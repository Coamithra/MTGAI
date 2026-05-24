# TC-4: Visual Reference Extraction Stage

## Context

The art pipeline (`art/visual_reference.py`, `art/character_portraits.py`,
`art/prompt_builder.py`) reads a per-project
`<asset>/art-direction/visual-references.json` to inject plain-English visual
descriptions of setting-specific entities into Flux art prompts. Today that
file is produced by hand. TC-4 adds an LLM stage that reads the setting prose
in `theme.json` and produces the file automatically — mirroring the just-shipped
TC-3 archetype stage in structure.

## Existing consumer contract (the authoritative schema)

`art/visual_reference.py` and `art/character_portraits.py` already read these
top-level keys, each a `dict[str, str]` (entity-key -> plain-English visual
description):

- `legendary_characters` — named legends. `character_portraits.py` parses
  `"Name: visual desc..."` from the value.
- `creature_types` — setting-specific races/creatures.
- `factions` — organizations / armies.
- `landmarks` — locations.
- `flux_term_replacements` — `dict[str, str]` mapping a setting term to a
  Flux-legible phrase (e.g. `"moktar" -> "tawny-furred lion-headed humanoid"`).

The card's `{creatures, characters, term_replacements}` maps onto these:
creatures = `creature_types`, characters = `legendary_characters`,
term_replacements = `flux_term_replacements`. We keep the richer existing key
names so current consumers (and downstream card 69f9d47e's `characters.json`)
keep working without edits. We add one new top-level key:

- `visual_motifs` — `list[str]` of set-wide art-direction notes (recurring
  colors, materials, lighting, architecture). New, additive, ignored by
  current consumers; useful to the art-prompt builder and the 69f9d47e style
  guide.

Final on-disk schema (`<asset>/art-direction/visual-references.json`):

```json
{
  "legendary_characters": {"<key>": "Name: visual description"},
  "creature_types":       {"<key>": "visual description"},
  "factions":             {"<key>": "visual description"},
  "landmarks":            {"<key>": "visual description"},
  "flux_term_replacements": {"<setting-term>": "<flux phrase>"},
  "visual_motifs": ["set-wide art note", "..."]
}
```

Keys are lowercased slugs (the consumers match keys as lowercase substrings of
card text). Empty categories are written as `{}` / `[]`.

## Design

### New: `backend/mtgai/art/visual_reference_extractor.py`
Mirrors `generation/archetype_generator.py`:
- `VISUAL_REF_TOOL_SCHEMA` — Anthropic `input_schema` dict. Top-level array
  `entities` (each: `category`, `key`, `name`, `visual_description`,
  `flux_replacement?`) plus `visual_motifs` array. An array-of-entities shape
  is friendlier to the model than five parallel dict objects.
- `build_visual_reference_prompts(theme, set_name)` — reads
  `pipeline/prompts/visual_references_{system,user}.txt`, threading the theme
  prose, flavor description, legendary characters, creature types, factions
  hints, constraints. Tolerant block formatters for missing fields (like TC-3).
- `assemble_visual_references(entities, motifs)` — pure function turning the
  flat entity list into the nested category-dict schema above; slugifies keys,
  dedupes, drops malformed entries, builds `flux_term_replacements` from any
  entity carrying a `flux_replacement`.
- `load_visual_references(asset_dir=None)` — on-disk loader, returns `{}` when
  absent (parallels `load_archetypes`).
- `generate_visual_references(theme=None)` — resolves model via
  `settings.get_llm_model_id("visual_refs")`, reads `theme.json`, assembles
  prompts, calls `generate_with_tool`, writes a per-call log sidecar under
  `<asset>/art-direction/logs/`, returns
  `{references, input_tokens, output_tokens, model_id}`.

### New prompt files
- `pipeline/prompts/visual_references_system.txt`
- `pipeline/prompts/visual_references_user.txt`

### `pipeline/models.py`
Add to `STAGE_DEFINITIONS` after `archetypes`, before `skeleton`:
`{"stage_id": "visual_refs", "display_name": "Visual References", "review_eligible": True}`.
The wizard auto-renders a generic stage tab from this — no bespoke tab UI.

### `pipeline/stages.py`
- `run_visual_refs(progress_cb, emitter)` — mirrors `run_archetypes`: requires
  `theme.json`, holds the AI lock, calls `generate_visual_references`, writes
  `<asset>/art-direction/visual-references.json`, emits overview + a small
  per-category count table. AUTO stage (no break point).
- Register in `STAGE_RUNNERS` after `archetypes`.
- `clear_visual_refs()` — removes `visual-references.json` + the
  `art-direction/logs/` dir. Register in `STAGE_CLEARERS`. NOTE: `art-direction/`
  also holds `character-refs/` (a later stage's output), so we only remove the
  file and the logs dir, not the whole folder.

### `settings/model_settings.py`
- `LLM_STAGE_NAMES["visual_refs"] = "Visual References"`
- `DEFAULT_LLM_ASSIGNMENTS["visual_refs"] = "sonnet"` (prose comprehension +
  creative visual writing; same tier as archetypes/mechanics)
- `PRESETS["recommended"]["llm"]["visual_refs"] = "sonnet"`
- `PRESETS["all-local"]["llm"]["visual_refs"] = "gemma4-26b-vram-dynamic"`
  (all-haiku derives from `DEFAULT_LLM_ASSIGNMENTS` so it's covered.)

### CLAUDE.md
Add a one-line bullet documenting the new `visual_reference_extractor` stage
under the art section.

## Pipeline position rationale
The stage only depends on `theme.json` (prose) — not mechanics, archetypes,
skeleton, or cards. Its output is consumed far downstream (char_portraits,
art_prompts). Placing it right after `archetypes` clusters all the
prose-reading LLM stages together while keeping the gameplay-design spine
(skeleton → reprints → card_gen) intact. It runs AUTO (no human break).

## Tests — `backend/tests/test_visual_reference_extractor.py`
All LLM calls mocked (monkeypatch `generate_with_tool`). No real model.
- `test_build_visual_reference_prompts_substitutes_fields`
- `test_build_visual_reference_prompts_handles_missing_blocks`
- `test_assemble_visual_references_groups_by_category`
- `test_assemble_visual_references_slugifies_and_dedupes`
- `test_assemble_visual_references_builds_flux_replacements`
- `test_assemble_visual_references_drops_malformed`
- `test_load_visual_references_returns_empty_when_missing`
- `test_load_visual_references_reads_dict`
- `test_generate_visual_references_writes_file_and_log` (mocked, pinned project)
- Round-trip: produced file is consumable by `visual_reference.get_refs()`-shape
  (assert keys + that `character_portraits._build_portrait_prompts` accepts it).

## Out of scope
- The `characters.json` restructure, negative prompts, Scryfall reference art
  (that's card 69f9d47e, which depends on this).
- Any change to how `prompt_builder.py` / `character_portraits.py` consume the
  file (they already read the schema we emit).
- A bespoke wizard tab (the generic stage tab suffices; no custom review UI).
