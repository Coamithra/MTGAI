# Reprints tab: manual select + place reprints

Card: [Reprints tab: manual select + place reprints](https://trello.com/c/rQZ20z02) (`6a17151a`)

## Context

Reprint selection is fully LLM-driven today (`select_reprints` → two passes: pick
from the 227-card pool by set-fit, then place on plain-text skeleton slots). The
Reprints tab (`wizard_reprints.js`) is a **read-only** grid of those picks + a
per-rarity knob panel + a full-rerun "Refresh AI" button. There is no manual
path: the user can't hand-pick which pool cards reprint or which slot each lands
on.

This card adds the manual path as a **hybrid**: AI proposes, the user overrides
per-pick, mirroring the archetypes tab's preserve-on-refresh contract (§5/§13 of
`wizard-tab-conventions.md`).

## Design

### Pin model (the preserve contract)

Each selection carries a **`pinned`** flag (new field on `SelectionPair`,
default `False`):

- AI-chosen/placed picks → `pinned=False` (shown with the "AI" provenance badge).
- User-added / user-reassigned picks → `pinned=True` (shown with "edited").
- **Refresh AI** keeps every pinned pick exactly (card + slot) and re-rolls only
  the non-pinned picks to fill the remaining target. The AI is barred from
  re-using a pinned card or a pinned slot, so no dup picks / slot collisions.

This is the direct analog of archetypes' `_ai_generated` flag + `focus_pairs`
refresh.

### Backend — `mtgai/generation/reprint_selector.py`

1. **`SelectionPair`**: add `pinned: bool = False`. Backward-compatible — the
   engine path and existing `reprint_selection.json` files default to `False`.

2. **`select_reprints(..., pinned: list[SelectionPair] | None = None)`**: when
   pins are supplied —
   - drop pinned card names from the pool offered to the select pass;
   - drop pinned slot_ids from the slot list offered to the place pass;
   - reduce the AI target to `max(0, total - len(pinned))`, and subtract pinned
     per-rarity counts from the soft mix told to the select pass;
   - return `pinned + ai_selections` as the final selection list.

### Backend — `mtgai/pipeline/server.py`

3. **`_resolve_selection_pairs(asset, raw)`** helper: given raw
   `[{card_name, slot_id, reason?, pinned?}]`, rebuild authoritative
   `SelectionPair`s — look the candidate up by name in the pool, the slot text up
   by id in the skeleton's open slots; reject unknown card / unknown-or-taken
   slot / duplicate card / duplicate slot. Returns `(pairs, error)`. Shared by
   `/save` (all picks) and `/refresh` (pinned subset). The server never trusts
   client-supplied card blobs — it rebuilds from the pool.

4. **`GET /api/wizard/reprints/pool`**: returns `{pool: [...candidate dicts...],
   open_slots: [{slot_id, text}]}` for the manual picker (lazy-loaded when the
   browser panel opens). `open_slots` = `_load_slot_texts(skeleton)`.

5. **`POST /api/wizard/reprints/save`**: manual write, **no AI**. Body
   `{selections: [{card_name, slot_id, reason?, pinned?}]}`. Validates via
   `_resolve_selection_pairs`, builds a `ReprintSelection`, writes
   `reprint_selection.json`, re-stamps the skeleton (`apply_selection_to_skeleton`),
   calls `_heal_failed_stage("reprints")`, returns `{success, navigate_to, ...state}`.
   Zero reprints is valid. Mirrors `archetypes/save`.

6. **`POST /api/wizard/reprints/refresh`**: accept optional `pinned:
   [{card_name, slot_id, reason?}]` in the body; resolve via
   `_resolve_selection_pairs` and pass to `select_reprints(pinned=...)`. Pins
   survive the re-roll. (Existing knobs + cancel behaviour unchanged.)

### Frontend — `wizard_reprints.js`

The grid becomes **editable on the latest tab** (past tabs stay read-only → Edit
cascade, §6). Per the conventions, build by *calling* shared helpers.

- **Per-tile controls** (latest, non-past): a provenance badge
  (`W.provenanceBadge(pinned ? 'user' : 'ai')`), a slot `<select>` (open slots +
  current), a **Pin** toggle, and a **Remove** (×) button. Reassigning a slot or
  toggling pin marks the pick `pinned=true` (preserve-on-refresh).
- **Pool browser**: a collapsible `<details>` panel with a search box filtering
  the 227-card pool client-side; each row shows name + rarity pill + cost +
  oracle snippet + an **Add / Added** toggle. Adding appends a pinned pick
  auto-placed on the first free open slot (blocked when no slots remain).
- **Refresh AI**: now sends the current pinned picks as `pinned` → preserves
  them, AI re-rolls the rest. Confirm copy notes pins survive.
- **Footer**: a **Save & Continue** primary button (paused_for_review, latest)
  via `W.saveAndAdvance` → `POST /api/wizard/reprints/save` then advance — same
  shape as archetypes. Working edits persist on Save (and on Refresh, which
  writes). Form-lock + status pill + Stop-after toggle unchanged.

### One surface, not two

The card says "the UX *may* want two surfaces" (select vs place). I'm doing
**one surface**: the pool browser is the select step, the per-tile slot dropdown
is the place step, both on the same tab. Simpler, fewer endpoints, and the
add-auto-places-then-reassign flow covers "pick the slot or accept the AI's
placement" without a second screen.

## Tests

- `tests/test_reprint_selector.py::TestSelectReprints` — add a pinned-preserve
  case: pins survive, AI fills `total - len(pins)` around them, pinned card/slot
  excluded from the AI passes.
- `tests/test_pipeline/test_wizard_reprints.py` — `/pool` shape; `/save` happy
  path (writes json + stamps skeleton + heals); `/save` rejects unknown card /
  taken slot / dup; `/refresh` honours `pinned`.

## Out of scope

- **Materialization** (`convert_to_card` → card files) — separate card
  `6a171971`. Note: `apply_selection_to_skeleton` already *reserves* the slot
  (card-gen skips it), so manual placement is meaningful today even without
  materialization.
- A separate two-pane select/place UX (one surface chosen above).
- Pool editing / adding new pool cards.
