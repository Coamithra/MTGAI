# Card generation: free-text-driven redesign

## Context

The `card_gen` stage is the step that turns each skeleton slot into a real card.
Today it's a **hybrid**: it emits each slot's free-text `tweaked_text` into the
prompt (good), but it *also* reads the slot's structured fields (`color`,
`color_pair`, `cycle_id`, `mechanic_tag`, `archetype_tags`) to (a) group slots
into batches, (b) scope which mechanics appear in the prompt, and (c) stamp
metadata onto the generated card.

The problem: after the skeleton **relabel**, those structured fields are stale
*defaults*. The relabel only ever writes `tweaked_text` + `reserved_card` back
to a slot (`backend/mtgai/pipeline/stages.py:554`); everything else is left at
the deterministic seed value. The relabel's free text can swing a slot's
effective color/rarity/type/mechanic — and can even **pull a card out of its
cycle** in prose while the structural `cycle_id` still says it's a member. So
any card-gen decision made from the structured fields is made from data that no
longer describes the card.

**Goal:** drive `card_gen` entirely from each slot's free text (`tweaked_text`),
treating structured fields as untrustworthy — *except* where a structured field
is a genuine **cross-stage contract** rather than a theme attribute (see "What
stays structured"). The one place free text can't be parsed algorithmically —
**which slots form a cycle that must be designed as a mirrored family** — gets a
small dedicated LLM pass.

### Decisions locked in with the user
- **No color batching, no color LLM-sort.** Color is a swingable seed; batching
  by it groups cards by their *seed* color, not their actual one. (Note: this is
  *not* a caching win — only the system prompt + tool schema are cached
  `backend/mtgai/generation/llm_client.py:310`; the mechanic block is in the
  uncached user prompt. The reasons are correctness + simplicity.)
- **The only LLM grouping pass needed is cycle identification**, and it must
  **mistrust the structured `cycle_id`** (the relabel can have textually removed
  a member).
- **Oversized cycles**: split into sub-batches, and feed already-generated
  members of the same cycle into the later sub-batch prompts so they still mirror.

## The field-trust model (the spine of the design)

| Bucket | Fields | Card-gen treatment |
|---|---|---|
| Swingable seed | `color`, `color_pair`, `rarity`, `card_type`*, `cmc_target`, `mechanic_tag`, `archetype_tags`, `notes` | **Do not read for card design or grouping.** The card's true values come from the LLM's generated output, and its spec comes from `tweaked_text`. |
| Cross-stage contract | `slot_id`, `card_type == "land"` | **Keep.** `slot_id` is the join/resume key. `card_type=="land"` is how the `lands` stage claims slots (`land_generator.py:291`); card-gen must skip exactly those slots to stay consistent — this is a contract, not a theme attribute. |
| Structural, but mistrusted here | `cycle_id` / `cycle_name` / `cycle_member`, cycle `template` | Used only as the **candidate set + reliable design brief** for the cycle-sort LLM pass, which prunes members the text no longer supports. |
| Reliable additive flag | `signpost_for`, `is_reprint_slot`, `reserved_card` | Keep as additive prompt enrichment — never reassigned, and they carry intent the free text may not restate. |

\* `card_type` appears in both rows: its `"land"` value is the lands contract
(trusted for skip), but its other values (creature/instant/…) are swingable seed
(not trusted for design — the LLM returns the real type).

## Design changes

### 1. Cycle identification LLM pass — new module `backend/mtgai/generation/slot_grouper.py`
Mirror the proven assign pattern from `skeleton_relabel.assign_requests`
(`backend/mtgai/generation/skeleton_relabel.py:532`) and
`reprint_selector._place_reprints` (`backend/mtgai/generation/reprint_selector.py:457`):
plain-text slot listing → `generate_with_tool` with a small tool schema →
parse back to `slot_id`s → retry/dedup.

- **Input**: the unfilled non-land slots grouped by structural `cycle_id` into
  *candidate families* (a superset — a "pulled-out" card still carries its tag),
  each presented as `slot_id: <tweaked_text>` lines under their cycle name, using
  the shared `skeleton_prompt_blocks` formatters
  (`backend/mtgai/generation/skeleton_prompt_blocks.py`) for set context
  (setting/mechanics/archetypes).
- **Task**: for each candidate family, return the `slot_id`s whose **free text**
  still reads as a member of that mirrored family; drop any whose text no longer
  fits. Authoritative signal = the text, not the tag.
- **Tool schema**: `{ "cycles": [ { "name": str, "slot_ids": [str] } ] }`.
- **Robustness**: temperature 0, `RELABEL`-style retry/dedup (validate each
  `slot_id` is real + not already placed). Transcript → `<asset>/generation_logs`.
  Model = the active project's `card_gen` assignment (no new registry key).
- **Failure fallback**: if the pass yields nothing usable after retries, fall
  back to grouping by structural `cycle_id` (old behavior) and log a warning —
  never break the stage.
- Map each confirmed family back to its structural cycle to recover the shared
  `template` (the template *prose* is a reliable design brief; only *membership*
  was in doubt).

### 2. Replace `group_slots_into_batches` (`card_generator.py:187`)
New batching, sourced from the sort result instead of structured color/cycle:
- **Confirmed cycle families first**, each its own batch. If a family exceeds
  `BATCH_SIZE`, split into ordered sub-batches and tag them so the loop knows to
  thread siblings (change 4).
- **All remaining slots** in deterministic `slot_id` order, chunked at
  `BATCH_SIZE`. No color key.

### 3. Stop color-scoping mechanics (`prompts.py:370` in `build_user_prompt`)
Drop the `relevant_colors` computation; always include **every** set mechanic via
`format_mechanic_block(mechanics, set())`. Rationale: a relabeled card may use a
mechanic outside its seed color, so color-scoping can omit the mechanic the card
needs. Sets have a handful of mechanics, so the cost is trivial.

### 4. Oversized-cycle sibling context (loop in `generate_set` + `build_user_prompt`/`format_slot_specs`)
When a cycle's later sub-batch runs, pass that cycle's already-saved members
(collected during this run) into the prompt as an explicit **"SIBLING CYCLE
MEMBERS — mirror their structure/wording"** block carrying their full
`oracle_text`. This is stronger than the generic existing-cards context (which
only says "don't duplicate"). Thread via a new optional `cycle_siblings`
parameter on `build_user_prompt`.

### 5. Stop stamping stale seed metadata (`card_generator.py:599-604`)
Remove the `mechanic_tags` (from `mechanic_tag`) and `draft_archetype` (from
`archetype_tags`) stamps — they're written from swingable seeds and can mislabel
the card. The generated card's own returned fields are authoritative; if these
tags are needed downstream, derive them from the actual card later.

### 6. `format_slot_specs` cleanup (`prompts.py:167`)
The `tweaked_text` path already emits free text verbatim — keep it. Keep the
reliable additive flags (`signpost_for`, `is_reprint_slot`, `reserved_card`,
cycle note/template). The structured fallback branch (no `tweaked_text`) stays
only as a safety net for an un-relabeled skeleton; it is effectively dead once
relabel always runs.

## What we are NOT changing
- **skeleton.json is not mutated by card-gen** — the `lands` and `reprints`
  stages keep reading the structured fields they depend on (`land_generator.py:291`,
  `reprint_selector.py:231`). This redesign is read-side only.
- Resume ledger, per-card/batch logging, validation+auto-fix, parse-failure retry
  (`card_generator.py:625`) — unchanged.
- Land-slot skipping stays keyed on `card_type == "land"`.

## Verification
1. **Unit-test the cycle sort** (`backend/tests/test_generation/test_slot_grouper.py`,
   new): mock `generate_with_tool` to (a) confirm a full family, (b) prune a
   member whose text was changed, (c) fall back to `cycle_id` on total failure.
2. **Unit-test batching**: a `pairs10` (10-member) cycle splits into ordered
   sub-batches all tagged to the same cycle; non-cycle slots chunk in `slot_id`
   order; no color key.
3. **`build_user_prompt`**: asserts all mechanics present regardless of slot
   colors; sibling block appears for a cycle's 2nd sub-batch with prior oracle text.
4. **End-to-end dry run**: `python -m mtgai.generation.card_generator --dry-run`
   on a project whose skeleton has a relabeled cycle (and ideally a member whose
   `tweaked_text` was edited out of the family) — confirm the planned batches
   group the confirmed cycle together and exclude the pruned member.
5. `ruff check .` / `ruff format .` and `pytest` from `backend/`.
6. Confirm `lands` + `reprints` still run unchanged against the same skeleton
   (no structured fields were altered).
