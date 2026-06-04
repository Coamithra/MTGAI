# Art/Render Rework — Frozen Cross-Card Contracts

The art/render topology reorg (card 6a20b13a) has shipped. These contracts are
**frozen on master** so the five rework cards can be built in parallel without
integration drift. **Build to these seams. Do not change them. If you believe a
contract must change, stop and flag it — do not unilaterally diverge.**

Stage tail (5): `visual_refs` → `art_prompts` → `char_portraits` → `art_gen` → `rendering`.
(`char_portraits` keeps its stage_id; display is "Character References".)

---

## 1. Card model field — `art_character_refs` (already on master)

`mtgai/models/card.py` now has:

```python
class ArtCharacterRef(BaseModel):
    entity_key: str        # slug key into the art-direction dictionary
    ref_image_path: str    # repo-relative path under the asset folder

class Card(BaseModel):
    ...
    art_character_refs: list[ArtCharacterRef] = Field(default_factory=list)
```

- **Producer:** Character References stage (`char_portraits`, card 6a20aa84) populates it.
- **Consumer:** Art Generation stage (`art_gen`, card 6a20adda) reads it to feed
  PuLID/IP-Adapter (Flux) or provider reference-conditioning.
- Do not rename or restructure this field. Add fields to `ArtCharacterRef` only if
  additive + defaulted.

## 2. Art-direction dictionary — `art-direction/visual-references.json`

Owned/produced by **Visual References refactor (card 6a209d65)**. Must stay loadable
by the existing consumers in `mtgai/art/visual_reference.py` (`get_refs`,
`detect_named_characters`, `get_character_ref_paths`, `get_flux_term_replacements`)
**or** that card updates those consumers in lockstep. Existing keyed shape:

```json
{
  "legendary_characters": { "<slug>": "<art-direction prose>" },
  "creature_types":       { "<slug>": "<art-direction prose>" },
  "factions":             { "<slug>": "<art-direction prose>" },
  "landmarks":            { "<slug>": "<art-direction prose>" },
  "flux_term_replacements": { "<invented word>": "<renderable phrase>" },
  "visual_motifs": "<set-wide motif prose>",
  "set_art_direction": "<NEW: set-wide art-direction prose, card 6a209d65 step 'Final Step'>"
}
```

- `entity_key` values in `art_character_refs` (contract #1) are slugs that exist as
  keys somewhere in this dict (any of the keyed sub-dicts).
- **Consumers:** `art_prompts` (6a20a6c5) and `char_portraits` (6a20aa84) read this.
- The Visual References card may enrich the prose + add the `set_art_direction` key;
  it must NOT remove the four keyed sub-dicts or `flux_term_replacements` without
  updating every consumer.

## 3. Artist Directory — `art-direction/artists.json` (NEW)

Owned/produced by **Visual References refactor (card 6a209d65)**, "Additional Step:
Artist Directory". Frozen shape:

```json
{ "artists": [ { "name": "<made-up artist name>", "style_prompt": "<style description>" } ] }
```

- Sizing: ≥ ~10 cards per artist (lean toward fewer artists). The producer decides count.
- **Consumer:** Art Prompt Generation (6a20a6c5) reads `artists`, assigns one per card
  to `card.artist`, and feeds the chosen `style_prompt` into the LLM that authors the
  art prompt. Build to `{name, style_prompt}`; add fields only additively.

## 4. Wizard tab + endpoint conventions

Each card owns its own files; no card re-touches `STAGE_DEFINITIONS`, the
`STAGE_RUNNERS`/`STAGE_CLEARERS` maps, `DEFAULT_BREAK_POINTS`, or the position-coupled
tests (the foundation card froze those). Per card, net-new UI work:

- `visual_refs`     → `wizard_visual_refs.js`  + `/api/wizard/visual_refs/{state,refresh,save,...}`
- `art_prompts`     → `wizard_art_prompts.js`  + `/api/wizard/art_prompts/{state,refresh,save,...}`
- `char_portraits`  → `wizard_char_refs.js`    + `/api/wizard/char_refs/{state,refresh,upload,save,...}`
- `art_gen`         → `wizard_art_gen.js`       + `/api/wizard/art_gen/{state,refresh,...}` (merged gen+select+review)
- `rendering`       → `wizard_rendering.js`     + `/api/wizard/rendering/{state,save-card,remove-card,...}`

All AI-touching endpoints use the `guarded_ai(...)` pattern (AI-lock, 409 on busy,
cancellable). Register renderers via `registerStageRenderer('<stage_id>', ...)` and add
the `<script>` tag in `wizard.html`. Follow `plans/wizard-tab-conventions.md`.

`server.py` (endpoint blocks), `wizard.html` (script tags), and `card.py` are the only
files multiple cards may touch — keep edits **append-only / additive** and in distinct
regions so the orchestrator's serialized merges stay conflict-light.

## 5. Stage merged-runner names (frozen)

`stages.run_art_gen` and `stages.run_rendering` are the entry points. Swap their
**internals** only. `run_art_gen` currently interim-chains
`mtgai.art.image_generator.generate_art_for_set` + `mtgai.art.art_selector.select_art_for_set`.
`run_rendering` calls `CardRenderer.render_set` (QA dropped).
