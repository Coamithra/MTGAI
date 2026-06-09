# Hosted character-ref binding: interleaved labeled refs + name-based art prompts

Trello: MTGAI [6a2752e9](https://trello.com/c/4OaKhQ5K). Library dependency: LLMFacade
[6a275322](https://trello.com/c/4FFTlmAZ) (`feat/labeled-reference-images`) — implemented in parallel.

## Context

Hosted image gen (Gemini/OpenAI) sends reference images as an **unlabeled bag** after one
prompt blob, and art prompts describe recurring entities by **appearance, not name**. A card
featuring 2+ recurring entities (24/74 on the Transformers set) therefore has no reliable
entity→face binding — the model appearance-guesses the correspondence. The fix reproduces the
manual-chat pattern that actually binds identity: "this is Storm Knight:" [img] … then a scene
prompt that **uses the name** "Storm Knight".

## Dependency API (locked, from the LLMFacade plan)

`generate_image(prompt, reference_images=...)` accepts `Sequence[ImageBlock | LabeledImage |
tuple[str, ImageBlock]]`. `LabeledImage(label: str, image: ImageBlock)` is exported from
`llmfacade`. Per-backend:
- **Gemini** (primary, true binding): each `label` is emitted verbatim as a `{text}` part
  immediately before its image; the prompt is the last part.
- **OpenAI** edit endpoint (best-effort): synthesizes a `"Reference image N is <label>."`
  preamble (can't truly interleave). → **the label must be the bare entity name** so this reads
  right; Gemini is fine with a bare name too.
- Unlabeled lists keep today's exact wire shape (back-compat).

## Design

### The agreement constraint
The interleaving **label** (built at `art_gen`) and the **name token** in the prompt (built at
`art_prompts`) must be the SAME string for the model to bind. `art_prompts` runs **before**
`char_portraits` (which produces `art_character_refs`), so neither stage can read the other's
names. The only stable shared anchor is the **`entity_key` slug**. Both stages derive the display
name identically: `entity_key.replace("_", " ").title()` (a shared `entity_display_name` helper).
No new card-schema field — `ArtCharacterRef.entity_key` is enough.

### Part 1 — name-based art prompts (`art/prompt_builder.py`, `art/visual_reference.py`)
- New `visual_reference.entity_display_name(key)` and `get_named_entities(name, type_line,
  oracle_text, flavor_text) -> list[{key, name, kind}]`. Matching improves on the existing
  `key in search_text` (which fails on multi-word underscore slugs) by testing the **spaced**
  name too.
- `build_art_prompt_user_message`: replace the "VISUAL APPEARANCE REFERENCES (render these
  appearances, never the names)" section with a **NAMED ENTITIES** roster — the canonical names,
  instructing the model to refer to each by its exact name (the renderer binds a reference image
  to that name).
- `SYSTEM_PROMPT`: flip the "DO NOT use character names — describe APPEARANCE instead" rule to
  "refer to any NAMED ENTITY by its exact given name; describe any *other* subject by appearance
  (still never invent race/creature-type words)."
- Per the user's scope call ("hosted-only, ignore Flux for now"): this applies to all backends;
  Flux art degrades to bare names until 6a274df0 adds the Flux name→appearance substitution.

### Part 2 — interleaved hosted resolution (`art/image_generator.py`)
- `_resolve_labeled_refs(card, set_dir) -> list[tuple[str, str]]`: `(display_name, abs_path)` per
  `art_character_ref` (display name from `entity_display_name(entity_key)`).
- `generate_image` / `generate_image_hosted` gain an optional `ref_labels: list[str] | None`
  parallel to `ref_paths`. ComfyUI ignores labels (paths only).
- `generate_image_hosted`: when any label is present, build `reference_images` as
  `LabeledImage(label=name, image=ImageBlock.from_path(p))` (drop the label for a ref with none);
  otherwise keep the flat `ImageBlock` list. `LabeledImage` imported function-level (so
  `import mtgai` works before the dependency lands).
- `generate_art_for_set`: build labeled refs per card and thread `ref_labels` through; the
  per-version log records `character_ref_labels`.

## Tests
- `tests/test_art/test_visual_reference.py`: `entity_display_name`; `get_named_entities` matches
  spaced multi-word names + dedupes; empty when no refs.
- `tests/test_art/test_prompt_builder.py` (or existing): the user message contains the NAMED
  ENTITIES roster + names, not the old appearance block.
- `tests/test_art/test_image_generator.py`: `_resolve_labeled_refs` derives the right
  `(name, path)`; `generate_image_hosted` builds `LabeledImage`s when labeled and a flat list when
  not (monkeypatch `LLM.default`). Gated on the dependency symbol — skip if `LabeledImage` absent.

## Out of scope
- Flux name→appearance substitution + PuLID single-humanoid (card 6a274df0).
- OpenAI true interleaving via the Responses API (LLMFacade documents it as a limitation).
- Reprint materialization, any change to `char_portraits` detection quality.

## Verification
`ruff check . && ruff format .`; `python -c "import mtgai"`; `pytest` (art + model). Manual smoke
once the dependency lands: a real Gemini `generate_image` with 2 labeled refs on a 2-entity card.
