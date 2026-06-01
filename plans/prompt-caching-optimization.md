# Prompt-Caching Optimization — Generation Pipeline (theme → card_gen)

## Context

Every LLM call in the pipeline routes through `generate_with_tool()` in
[llm_client.py](../backend/mtgai/generation/llm_client.py). Caching is **already enabled by
default** (`cache: bool = True`), but today it only wraps **the system prompt + tool schema**
in an Anthropic `cache_control: ephemeral` block. The expensive mistake is *where each stage
puts its bulk static content*:

- **Card generation** makes ~200–250 calls per set (one card per call). Its ~1.1k-token MTG
  rules system prompt is cached — but the ~5–6k tokens of **static set-context** (setting prose,
  all mechanics + 2 examples each, archetypes, preventive guidance) are assembled by
  [`build_user_prompt`](../backend/mtgai/generation/prompts.py) into the **user message**, which
  is *not* cached. That static block is byte-identical across every batch yet re-billed at full
  input price ~200–250× per set. **This is the single biggest leak.**
- **Mechanics** (~150+ council/reviewer calls) already places its ~8–10k-token static content in
  the *system* prompt → already cached. One cheap extra win remains (below).
- **Structural stages** (archetypes, skeleton, reprints, lands, theme) are low call-volume
  (1–6 calls each). Some put static context in the user message; the per-stage ROI is small, but
  since **all stages will eventually run on cloud**, we migrate them onto the same cached-prefix
  pattern for consistency and to capture retry/regen/re-roll reuse.

Goal: relocate each call's large STATIC payload into the cached prefix so it is read at ~0.1×
instead of re-billed at 1.0× on every call, and add a general transport primitive so any stage
can adopt the pattern. Caching is a no-op for local llama.cpp, so every change is safe regardless
of the model assigned.

## Recommended approach

**Option B — a general multi-block-system primitive** in the transport, then migrate stages to it
(card_gen first). This is barely larger than a card_gen-only string hack but becomes the reusable
mechanism every stage uses to push static context into cached system blocks. **No llmfacade
change is required** — llmfacade already models a list of independently-cacheable `SystemBlock`s
and exposes an `auto_cache_last_user` knob (both verified in
`C:/Programming/LLMFacade/src/llmfacade/providers/anthropic.py` and `.../conversation.py`).

### Hard constraint — the 4-breakpoint cap

Anthropic allows **max 4 `cache_control` markers per request**; llmfacade does **not** dedupe or
cap them. Budget per call:

1. tool schema (auto-cached when `cache=True`)
2. system block #1 — base instructions
3. system block #2 — **combined** static context (one block, *not* one-per-formatter)
4. last user block (only if `cache_user=True`)

**Rule: bundle all static context into ONE system block.** card_gen uses markers 1–3 (no
`cache_user`). The mechanics reviewer uses 1, 2, 4. Never emit a separate cached block per
context formatter (setting/mechanics/archetypes/constraints would blow the cap).

## 1. Transport change — [llm_client.py](../backend/mtgai/generation/llm_client.py)

- **`generate_with_tool`** (line 689): add a keyword-only `system_blocks: list[str | tuple[str, bool]] | None = None`
  (each item is plain `str` = uncached, or `(text, cache)`), plus optional `cache_user: bool = False`.
  Prefer a *new* param over widening `system_prompt` so the ~6 existing callers and the
  llamacpp/budget paths (which assume `system_prompt` is a `str`) are untouched. Raise `ValueError`
  if both a non-default `system_prompt` and `system_blocks` are passed. Omitting `system_blocks`
  keeps behavior byte-for-byte identical.
- **`_generate_anthropic`** (line 412): when `system_blocks` is given, build
  `[SystemBlock(text=t, cache=(c and cache)) for (t, c) in normalized]` (the `and cache` preserves
  the existing `cache=False` contract); else keep today's single-block path. Thread
  `auto_cache_last_user=cache_user` into `new_conversation` (line 426). Do **not** import
  `SystemBlock` outside `llm_client` — convert tuples inside the transport.
- **llamacpp path** (`_generate_llamacpp`): flatten any `system_blocks` to one joined system string
  before dispatch; cache flags are ignored locally and returned `cache_*` fields stay 0.

## 2. card_gen refactor (HIGH) — [prompts.py](../backend/mtgai/generation/prompts.py) + [card_generator.py](../backend/mtgai/generation/card_generator.py)

- **Split the prompt builder.** Add `build_static_set_context(mechanics, theme, archetypes)`
  returning **only** the static sections 1–4, reusing `format_setting_prose`,
  `format_mechanic_block(mechanics, set())`, `format_archetypes_section`,
  `format_preventive_guidance` **unchanged**. Trim
  [`build_user_prompt`](../backend/mtgai/generation/prompts.py) to emit **only** the dynamic
  sections 5–7 (existing-card context, cycle siblings, slot specs). Keep its signature so the retry
  path and tests still work.
- **Existing-card context MUST stay dynamic.** `format_set_context(existing_cards)` (prompts.py:215)
  grows every batch (new line + recomputed color distribution + bumped total). It must remain in the
  user message — placing it in the cached block would bust the cache on every call (worse than
  today). Sections 1–4 are pure functions of `(mechanics, theme, archetypes)` with no per-batch
  values, so they are safe to cache.
- **Call sites** (main loop ~1224–1258 and `_retry_single_card` ~312–336): compute
  `static_ctx = build_static_set_context(...)` **once, hoisted out of the batch loop**, and call
  `generate_with_tool(system_blocks=[(load_system_prompt(), True), (static_ctx, True)],
  user_prompt=<dynamic>, ...)`, dropping the `system_prompt=` kwarg. Update `_save_batch_log` /
  `_save_generation_log` (~1338) to log the full effective system (base + separator + static_ctx)
  so the sidecar transcripts still show everything.
- **Net per batch:** full-price tokens drop from `(~1.1k system + ~5–6k static + dynamic)` to
  `(dynamic only)`; the ~6–7k stable prefix is a 1.25× write on batch 1 and a 0.1× read on
  batches 2..N. Back-to-back batches stay inside the 5-min TTL, so the cache stays warm across a run.

## 3. Mechanics reviewer win (MED) — [mechanic_generator.py](../backend/mtgai/generation/mechanic_generator.py)

The 3 council reviewers in a single round receive a **byte-identical** user prompt (the rendered
mechanic block; `build_reviewer_prompts`, ~1168). Pass `cache_user=True` on that reviewer call so
reviewers 2 & 3 read the user block from cache (the ~8.35k system prompt is already cached). The
synth/candidate user prompts differ per call → leave them dynamic. Requires the optional
`cache_user` param from step 1; can land separately.

## 4. Per-stage migration (LOW, "everything" scope)

Apply the same pattern — **static context → one combined cached system block; dynamic content →
user message** — to the remaining stages. Several already do this correctly; the work is an audit +
relocation where they don't. Savings here are small (1–6 calls/stage, no large same-run reuse
except retries/regens), so this is consistency + future-proofing, not the money.

| Stage | Calls/run | Status / action | Priority |
|---|---|---|---|
| card_gen | ~200–250 | Split static into cached system blocks (steps 2) | **HIGH** |
| mechanics reviewers | 150+ | System already cached; add `cache_user` for the 3-reviewer round (step 3) | **MED** |
| mechanics candidate/pick/synth | ~12–24 | Big system already cached; confirm template byte-stability | LOW |
| theme extraction | 1–6 | System already cached (`SystemBlock(cache=True)`); no change | LOW |
| skeleton relabel (pass 1) | 1–3 | Static already in system template; retries reuse it; no change | LOW |
| archetypes | 1 (+regen) | Verify whether static context is in system (`archetype_system.txt`) or user; if user, move to cached system block | LOW |
| skeleton knobs | 1–6 | Move setting/mechanics/archetypes/constraints from user → one cached system block | LOW |
| reprints select | 1 | Move context + ~350-card pool from user → one cached system block (helps re-rolls/regens within TTL) | LOW |
| reprints place | 1–3 | Move chosen-list/context to cached system; retries then read from cache | LOW |
| lands | 1–2 | Move setting/(mechanics/archetypes)/constraints from user → cached system block | LOW |

For each migration, reuse the existing `skeleton_prompt_blocks.py` formatters to build the bundle,
keep it to **one** cached context block (cap rule), and leave per-call dynamic content (slot
listings, card requests, chosen reprints, growing collections) in the user message.

## 5. Byte-stability & risks

- **Cached prefix must be identical across same-run calls.** `build_static_set_context` and every
  `skeleton_prompt_blocks` formatter are deterministic pure functions of their loaded JSON (list
  order preserved, no `datetime.now()`/`uuid`/unsorted `json.dumps`). Hoist their computation out of
  any per-call loop so the same string object is reused.
- **Never cache growing/per-call content:** existing-card context, slot specs, card requests,
  chosen-reprint lists. These stay in the user message.
- **5-min TTL:** only same-run reuse matters; cross-run almost never hits. A batch gap >5 min just
  re-writes the prefix (self-healing, no correctness impact). Default TTL is correct — don't raise
  to 1h unless batches routinely exceed 5 min.
- **Local models unaffected:** the llamacpp path flattens `system_blocks` to one string and ignores
  cache flags; `cache_*` stay 0.

## Verification

1. **Unit** ([test_card_generator.py](../backend/tests/test_card_generator.py),
   `test_prompts.py`): assert `build_static_set_context(...)` contains setting/mechanics/archetypes/
   guidance and is **byte-identical** across two calls with the same inputs; assert
   `build_user_prompt(...)` no longer contains sections 1–4. Adjust existing split assertions.
2. **llamacpp** (`test_llm_client_llamacpp.py`): confirm `system_blocks` flattens to one system
   string and cache flags are ignored.
3. **Cache integration** (gate behind an API-key env so keyless CI skips): run card_gen on a tiny
   capped set against Anthropic and assert via the already-returned
   `cache_creation_input_tokens` / `cache_read_input_tokens` (llm_client.py:461–462):
   - batch 1 → `cache_creation > 0`, `cache_read == 0`
   - batches 2..N → `cache_read > 0` (≥ ~6k), small `input_tokens`
   - `progress.total_cost_usd` (via `calc_cost`, which already prices reads at 0.1× / writes at
     1.25×) drops clearly vs. a pre-change run on the same fixture; total tokens roughly unchanged
     (moved, not added).

## Sequencing

1. Transport: add `system_blocks` (+ optional `cache_user`) to `generate_with_tool` /
   `_generate_anthropic`; flatten for llamacpp. Backward compatible.
2. prompts.py: add `build_static_set_context`; trim `build_user_prompt` to dynamic sections.
3. card_generator.py: hoist `static_ctx`, switch both call sites to `system_blocks`, fix the two log
   sidecars. (Delivers the HIGH-ROI win.)
4. Tests: unit split + byte-stability + small-set cache-read integration.
5. mechanics reviewer `cache_user=True` (MED).
6. Structural-stage migrations using the same primitive (LOW; can be incremental).

## Critical files

- [backend/mtgai/generation/llm_client.py](../backend/mtgai/generation/llm_client.py) — transport primitive
- [backend/mtgai/generation/prompts.py](../backend/mtgai/generation/prompts.py) — static/dynamic split
- [backend/mtgai/generation/card_generator.py](../backend/mtgai/generation/card_generator.py) — call sites + logs
- [backend/mtgai/generation/mechanic_generator.py](../backend/mtgai/generation/mechanic_generator.py) — reviewer `cache_user`
- [backend/mtgai/generation/skeleton_prompt_blocks.py](../backend/mtgai/generation/skeleton_prompt_blocks.py) — reused context formatters for structural-stage migration
- [backend/tests/test_card_generator.py](../backend/tests/test_card_generator.py) — tests
