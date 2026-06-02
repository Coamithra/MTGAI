# Card-gen Refresh AI button leaks backbone state into regen-instance tabs

Card: 6a1efa4a4a0f8a28b068837c

## Context

The Card Generation tab can appear more than once: the review->regen loop appends
an inserted `card_gen.2` span after a gate flags cards (see "Re-entrant pipeline"
in CLAUDE.md). Each instance is its own wizard tab with `tab.id == instance_id`.

The "Refresh AI…" button is rendered on **every** card_gen tab (it was placed in
`mountShellHtml`, unconditionally). But `POST /api/wizard/card_gen/refresh`:
- always regenerates the **whole live pool** from scratch (`clear_card_gen_cards()`
  + `generate_set`), i.e. it operates on the backbone tip pool regardless of which
  tab clicked it, and
- returns `wizard_card_gen_state()` with **no `instance_id`** — so the response is
  backbone state (`is_regen_instance=false`, the full fresh pool).

`onRefreshCards` then writes that backbone response into the **clicking tab's**
local state (`local.cards`, `local.isRegenInstance`, etc.). When the clicking tab
is an inserted regen instance (`card_gen.2`), this cross-wires: the regen
highlight turns off and the full fresh pool is shown in a tab that should be
showing that instance's snapshot. Benign today (no data loss) but misleading.

## Design

**Chosen fix: gate the Refresh button to the latest/tip instance.**

Two options were on the table (per the card):
1. Gate the button to the latest/backbone instance.
2. Have `/refresh` echo back the instance it targeted.

Option 1 is the more robust and conceptually correct fix. The Refresh action
*regenerates the whole live pool from scratch* — that only makes sense for the
tip instance (the live `cards/` folder is always the loop tip). A non-tip regen
instance is a frozen snapshot under `history/<id>/`; "refresh" has no coherent
meaning there. Hiding the button on non-tip tabs removes the cross-wire at the
source and matches the established `isLatest` convention every other stage tab
uses (`state.latestTabId === instanceId`), including this tab's own footer.

Option 2 would keep a button on non-tip tabs that, when clicked, silently
regenerates the *tip's* pool while the user is looking at a historical snapshot —
still misleading even if the local state no longer cross-wires. Rejected.

### File-by-file changes

`backend/mtgai/gallery/templates/static/wizard_card_gen.js`:
- `mountShellHtml()` takes the refresh-button HTML as a parameter (or the render
  path conditionally injects/removes it) so the button only renders on the tip
  instance. Cleanest: compute `isLatest` in `render()` and pass it to
  `mountShellHtml(isLatest)`; render the button only when latest.
- The button lives in the "Generation progress" section header. When not latest,
  the section header row keeps the `<h3>` but drops the button.
- Update the §13 doc comment (module header + inline) to say the button is gated
  to the tip instance, not "always rendered".
- `setLocked` selector list referencing `cg-refresh-btn` stays correct
  (`setTabLocked` no-ops on absent selectors).

No server change required: gating the trigger removes the cross-wire. `/refresh`
remains tip-only by construction, which is now the only place it can be invoked.

### Edge cases

- `state` can be null/absent (first paint before wizard state lands). Existing
  `isLatest = !state || state.latestTabId === instanceId` treats "no state" as
  latest — consistent with the footer's own logic, so the button shows in the
  single-instance/no-state case (correct: backbone IS the tip).
- `render()` only builds the shell once (`!local.initialized`). `latestTabId` can
  in principle change after first paint (a new instance is appended). The footer
  already repaints on re-render via `paintFooter`; the button should follow the
  same liveness. So the button visibility must be re-evaluated on the re-render
  path too, not only at first mount — handle by toggling the button's presence in
  `render()`'s re-render branch (cheap show/hide), keyed off the current
  `isLatest`.

## Tests

No JS unit tests in this repo. Python side is verified by ruff + import + pytest
(no Python logic changed — server endpoint untouched). The UI behavior needs a
manual smoke: load a regen-instance tab (`card_gen.2`), confirm the Refresh AI
button is absent; load the tip tab, confirm it is present and still works.

## Out of scope

- The "always-backbone refresh" semantics of `/refresh` itself (pre-dates this
  card; tip-only is correct).
- Any server-side instance echo (option 2) — not pursued.
