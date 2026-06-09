# Plan: Unify art-prompt entity resolution (text + image refs)

Trello: [Art-prompt appearance-text and attached image-refs use different entity
resolution and disagree](https://trello.com/c/tMHN40aA) (`6a27581d`).

## Context

Two mechanisms decide which entities a card "features", and they disagree:

1. **Appearance TEXT** (`art_prompts` stage): `prompt_builder.generate_art_prompt`
   → `visual_reference.get_visual_references()` — a brittle substring match
   (`if key in search_text`) against name/type/oracle/flavor. Misses
   plural/singular and surface-form variants ("autoroopers" key vs "Autorooper"
   on the card).
2. **Reference IMAGES** (`char_portraits` stage): `detect_recurring_entities()`
   is an LLM pass that writes `card.art_character_refs`. Precise, but it runs
   *after* `art_prompts` and only keeps entities on 2+ cards.

The card frames this as a **half-finished migration**: the LLM entity→card
decision already exists (char_portraits); the appearance-text path was never
switched onto it. Because `art_character_refs` is produced *later* in the
pipeline, the true unify requires moving the LLM detection to run **at
`art_prompts` time** and having both paths consume that one result.

User-confirmed scope (AskUserQuestion): **Full LLM unify** + **per-card entity
chips on the Art Prompts tab, with editable override**.

## Design

### One detection pass → one artifact

New module `mtgai/art/entity_tags.py`:

- `detect_entity_tags(cards, visual_refs, *, model_id, log_dir, thinking)` — the
  single LLM pass. Entity-centric output `[{entity_key, name, kind, cards, note}]`
  over **every** featured dictionary entity (NO 2+ filter; 1-card entities kept).
  Reads name/type/oracle/flavor only (NOT `art_prompt`, breaking the old
  circularity so it can run before prompts exist).
- `ensure_entity_tags(set_dir, cards, visual_refs, *, model_id, log_dir,
  thinking, force)` — load the sidecar if present (and not `force`), else run
  detection, **preserve manual-source per-card tags**, persist, return.
- Sidecar `art-direction/entity-tags.json`:
  `{"cards": {cn: {"tags": [{entity_key, kind}], "source": "ai"|"manual"}},
    "entities_meta": {entity_key: {name, kind, note}}}`.
- `effective_card_tags(data, cn)` → the per-card tag list (art_prompts + UI).
- `recurring_from_tags(data, min_cards=2)` → `[{entity_key,name,kind,cards,note}]`
  for char_portraits (image generation + `entities.json`), derived by counting
  the effective tags (respects manual edits). No second LLM pass.

### Consumers

- **`art_prompts`** (`prompt_builder.generate_prompts_for_set`): at the start,
  `ensure_entity_tags(force=force)`. Per card, `effective_card_tags` →
  `visual_reference.get_visual_references_for_keys(keys)` → the appearance-text
  block fed to the authoring LLM. `generate_art_prompt` gains an optional
  `visual_refs: str | None` param (None → legacy `get_visual_references`, kept
  for tests/back-compat).
- **`char_portraits`** (`character_portraits.generate_character_refs`): replace
  the in-stage `detect_recurring_entities` LLM call with `ensure_entity_tags`
  (reuses the sidecar art_prompts wrote; detects only if it's missing) +
  `recurring_from_tags`. `build_neutral_prompt` / `attach_refs_to_cards` /
  `clear_refs_on_cards` unchanged. `entities.json` keeps its shape, so the
  Character References tab is untouched.

### Robust dictionary lookup

`visual_reference.py`:
- `normalize_entity_key(s)` — shared slug (lowercase, non-alnum→`_`).
- `get_visual_references_for_keys(keys)` — normalized index over the four keyed
  sub-dicts; formats `[Label: Key] desc` exactly like the old function, so a
  `optimus_prime` tag matches an `optimus prime` dict key. Old
  `get_visual_references` (substring) retained for the legacy/test path.
- `get_entity_catalog()` — flat `[{entity_key, kind, name}]` for the UI add-tag
  picker. `character_portraits._appearance_for_entity` switched to the
  normalized lookup too.

### Clearer

`stages.clear_art_prompts` (new, replacing `_no_artifacts`) removes
`art-direction/entity-tags.json` so a cascade re-run re-detects.

### UI (Art Prompts tab)

- `/api/wizard/art_prompts/state` augments each tile with `entity_tags`
  (effective per-card) + returns `entity_catalog` for the picker.
- New `POST /api/wizard/art_prompts/tags {collector_number, tags}` — persist a
  card's manual tag list (source=manual), return the updated tile.
- `wizard_art_prompts.js` renders per-tile chips ("Optimus [character]") with
  ✕-remove + an add picker; edits gated on latest-tab + not-locked; preserved
  across AI refresh (manual source).

## Tests

- `tests/test_entity_tags.py` (new): detection parse/dedup/slugify (moved from
  test_character_refs), 1-card retention, `recurring_from_tags` 2+ filter,
  `ensure_entity_tags` manual-preservation + sidecar round-trip,
  `effective_card_tags`.
- `tests/test_prompt_builder.py`: patch the new seams (`ensure_entity_tags`,
  `get_visual_references_for_keys`); existing assertions unchanged.
- `tests/test_character_refs.py`: drop the `detect_recurring_entities` tests
  (moved); add a `generate_character_refs` test that the sidecar is consumed.
- `visual_reference` lookup test: `get_visual_references_for_keys` matches an
  underscore tag against a spaced dict key.

## Out of scope

- Re-authoring already-written art prompts when a user edits a card's tags
  (the chip is the source of truth; applying to the prompt = Refresh AI).
- Novel recurring entities not present in the visual-references dictionary
  (the dictionary is the single source of truth for appearance prose).
