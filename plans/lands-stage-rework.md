# Plan: Slim the `lands` stage to basics + a single investigated dual-land; move land cycles into card-gen

## Context

The `lands` stage today does three things ([land_generator.py](../backend/mtgai/generation/land_generator.py)): (1) 5 basic lands with set-flavored text, (2) one generic common nonbasic fixing land — *always* designed unless a land cycle exists, and (3) any **land cycles** budgeted in the skeleton (`generate_land_cycles`, one LLM call per cycle).

Two problems motivate the rework:

1. **Cycle/skip detection leans on stale structured fields.** The stage decides "skip the generic nonbasic" via `has_land_cycles`, computed from `slot["card_type"] == "land" and slot["cycle_id"]`. The skeleton's structured fields (`color`/`rarity`/`card_type`) are *deterministic default seeds* — the LLM relabel/reprint passes only rewrite `tweaked_text`, leaving the seeds unchanged, so for ordinary slots they no longer reflect the final design. The stage should stop depending on them as a design signal.
2. **Land cycles are a structural family already designed elsewhere.** Card-gen already batches cycles by `cycle_id`, threads each cycle's shared `template`, and the whole downstream flow (validation/finalize/art/render) handles Land cards. The only thing keeping land cycles out of card-gen is a one-line filter.

**Intended outcome:** the `lands` stage becomes (a) basic lands, plus (b) a single LLM call that *investigates the skeleton* and adds **one** from-scratch dual/fixing land **only when** the set shows a dearth of multicolor fixing or a strong multicolor theme. Land cycles move into card-gen and are generated alongside every other card. No reliance on stale per-slot structured fields for design decisions.

This investigation is intentionally the **last word on the set's fixing**: a single bespoke *bonus* land that tops up only if upstream stages left a gap. Fixing is decided in three places, in order — reserved **cycles** in the skeleton step (e.g. a guildgate cycle), mana-fixing **reprints** chosen in the reprint step (the pool carries Evolving Wilds / Gateway Plaza / taplands), and finally this stage. So the prompt is given visibility into *both* upstream sources and instructed to add the bonus dual only when neither already satisfies the multicolor need (or when a strong gold theme justifies a marquee rare dual on top).

**Key reliability note (why this is safe):** `cycle_id` and the *reserved-cycle* `card_type="land"` seed are structural reservations the LLM passes never mutate — distinct from ordinary-slot seeds the relabel rewrites. Card-gen feeds the model each slot's `tweaked_text` (the authoritative descriptor), using the seeds only to *route* (batch cycles / include land slots). The investigation step judges multicolor density from `tweaked_text` + the archetype block, not from stale `color` counts.

**Decisions (confirmed with user):**
- The dual land is **designed from scratch** (`is_reprint=False`). No reprint-pool materialization (`convert_to_card` stays unused).
- It is a **rare** (`Rarity.RARE`), not the old generic common tapland — a premium, possibly-untapped dual appropriate to a rare slot, since it's a deliberate bespoke addition rather than baseline Limited fixing.

---

## Changes

### 1. Card-gen: include land-cycle slots — `backend/mtgai/generation/card_generator.py`

The single gate at lines 813–815:
```python
all_slots = [s for s in skeleton["slots"] if s.get("card_type") != "land"]
```
becomes (include ordinary slots + any land slot that is a cycle member; a stray standalone land — none exist today — stays excluded):
```python
all_slots = [
    s for s in skeleton["slots"]
    if s.get("card_type") != "land" or s.get("cycle_id")
]
```
Update the adjacent comment (land cycles are now owned here, not the `lands` stage).

**Nothing else in card-gen changes** — the cycle-template stamping (lines 785–793, reads `skeleton["cycles"]`), `group_slots_into_batches` (lines 187–221, pulls cycle members into their own batch by `cycle_id`), and `_cycle_note()` in [prompts.py:282](../backend/mtgai/generation/prompts.py) (CYCLE MEMBER instruction + template) already work for land cycles.

### 2. `lands` stage → basics + investigation — `backend/mtgai/generation/land_generator.py`

**Remove** (moved to card-gen): `generate_land_cycles`, `_make_cycle_land_card`, `_build_cycle_prompt`, `_build_cycle_tool_schema`, `_land_member_colors`, `_land_member_label`, `_LETTER_TO_COLOR`/`_COLOR_FULL` if unused, and the `has_land_cycles` detection + Phase-C block in `generate_lands`.

**Split** the existing combined prompt: keep Task 1 (5 basic flavors) as `_build_basics_prompt` / `_build_basics_tool_schema`; drop Task 2 (the always-on nonbasic) from it.

**Add** an investigation pass:
- `_build_investigation_prompt(set_config, slot_texts, reprints, theme, approved, archetypes, constraints) -> (system, user)` — reuses the shared formatters in [skeleton_prompt_blocks.py](../backend/mtgai/generation/skeleton_prompt_blocks.py) (`format_setting_block`, `format_mechanics_block`, `format_archetypes_block`, `format_constraints_block`) for set context. It gives the LLM visibility into **all existing fixing** so the bonus land is a genuine top-up: (1) the full unfilled-slot descriptor listing (each slot's `tweaked_text`) — land cycles reserved in the skeleton appear here; (2) a short summary of the **reprint selections** (names + type_line/role) so the model knows whether mana-fixing reprints like Evolving Wilds / Gateway Plaza were chosen. It judges multicolor density from this authoritative prose, not stale seeds. The prompt instructs: add **exactly one rare** dual/fixing land — a premium, setting-appropriate dual (need not enter tapped) — **only if** a real gap remains after accounting for cycle + reprint fixing, **or** a strong multicolor theme justifies a marquee dual on top.
- `_build_investigation_tool_schema()` — `{ needs_dual_land: bool (req), reasoning: str (req), dual_land?: {name, type_line, oracle_text, flavor_text} }`. The `dual_land` shape matches the old `nonbasic` object so we **reuse `_make_nonbasic_card`** (it already infers `color_identity` from `{W}{U}…` symbols and sets `is_reprint=False` / `L-06`) — but set its rarity to **`Rarity.RARE`**: since the old common-nonbasic caller is removed, either change the hardcoded `Rarity.COMMON` in `_make_nonbasic_card` to `RARE` or add an explicit `rarity` param. Update its `design_notes` accordingly.

**Rewrite `generate_lands`** to: (1) basics call → write `L-01..L-05` (unchanged `_make_basic_card`); (2) load slot descriptors + theme/mechanics/archetypes/constraints, run the investigation call; (3) if `needs_dual_land`, build via `_make_nonbasic_card` and write `L-06`; (4) return `{total_cards, cost_usd}`.

**Reuse for data loading:** `reprint_selector.extract_set_config(skeleton_path)` (already imported) and `reprint_selector._load_slot_texts(skeleton_path)` (returns `[{slot_id, text}]` from `tweaked_text` with default-descriptor fallback). Mirror how `reprint_selector._select_from_pool` loads `theme.json` / `mechanics/approved.json` / `archetypes.json` for the formatter inputs (same asset-dir pattern). For the reprint summary, read `<asset>/reprint_selection.json` (written by the `reprints` stage, which runs before `lands`) — **graceful if absent or empty** (reprints skipped → treat as no fixing reprints). Model stays `project.settings.get_llm_model_id("lands")`.

### 3. Stage UI — `backend/mtgai/pipeline/stages.py` (`run_lands`, ~line 760)

- `init_sections` "call" section: change `"Asking for": "5 basic flavor texts + 1 nonbasic design"` to reflect basics + dual-land investigation.
- `count = result.get("total_cards", 6)` → fallback `5` (now 5 or 6).
- The `card_grid` cascade and `PromptEvalPoller` ("Designing lands") need no structural change; the investigation is a second guarded AI call under the same lock, so `_on_call_start` may fire twice (acceptable — keep the "Asking for" label generic).
- `_artifacts` mapping already has `"lands": _no_artifacts` (line 1259) — unchanged; land-cycle card files are now owned/cleared by card-gen.

### 4. Tests — `backend/tests/`

- Search `backend/tests` for `generate_land_cycles` / `_make_cycle_land_card` / `land_generator` and remove/migrate those cases.
- Add: investigation returns `needs_dual_land` + design and `generate_lands` writes 5 (decline) or 6 (accept) cards; assert no cycle generation happens in the lands stage.
- Add a card-gen test: a skeleton with a land cycle now yields those land slots in `group_slots_into_batches` / the generated set (filter change), batched as their own cycle.
- Check `backend/scripts/generate_lands.py` (the legacy CLI this module was extracted from) — update its call/flow or leave it pointing at the new `generate_lands` if it just delegates.

### 5. Docs — `CLAUDE.md`

Update the **Reprint Selection / lands** bullet: the `lands` stage = basics + one investigated from-scratch dual land; land cycles are generated by **card-gen** (drop the `generate_land_cycles` / "lands stage generates land cycles" wording, and the "land slots skipped by card-gen" claim).

---

## Verification

1. **Lint/tests:** from `backend/`, `PYTHONIOENCODING=utf-8 ruff check . && ruff format --check .` and `PYTHONIOENCODING=utf-8 python -m pytest` (targeted: `tests/` land + card-gen tests). Use `rtk` prefixes.
2. **Unit-level:** new tests above pass — investigation decision branches, card-gen filter includes cycle land slots, lands stage emits no cycle calls.
3. **End-to-end (manual, via the wizard — `python -m mtgai.review serve --open`):**
   - Open a project whose skeleton has a **land cycle** (e.g. a `pairs10` guildgate). Run **card-gen** → confirm the cycle's land cards (`<slot_id>_*.json`, Land type, parallel oracle text from the shared template) land in `cards/` and render with land frames.
   - Run the **Land** stage → confirm 5 basics always, and the dual-land decision is sane against all three fixing sources: with a guildgate **cycle** present, or a mana-fixing **reprint** (e.g. Evolving Wilds) in `reprint_selection.json`, the investigation should **decline** (reasoning cites the existing fixing); on a multicolor-heavy set with neither it should **add one rare** dual (`L-06`, `is_reprint=False`, `rarity == rare`, renders with a rare frame).
   - Confirm the Land tab UI (call KV + card grid cascade) still renders and the progress strip shows "Designing lands".
4. **Sanity:** confirm a relabeled land-cycle slot's `tweaked_text` still describes a land (the relabel preserves card type by instruction) so card-gen produces Land-type cards — spot-check one transcript in `generation_logs`.
