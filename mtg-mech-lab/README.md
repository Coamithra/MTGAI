# mtg-mech-lab

A standalone prototype for honing the **mechanic generation + council-review prompts**
before they get ported into the real MTGAI pipeline (`backend/mtgai/generation/mechanic_generator.py`).
Lives inside the MTGAI repo but is **not wired into anything** — it's a sandbox.

> Context: the real pipeline already does a *single-shot, single-reviewer* soundness
> check on each mechanic. The goal is to upgrade that to a **council** (like the card
> review) so mechanics come out *playable, correctly worded, interesting, not
> self-contradictory, unique, and elegant*. This lab is where we tune the prompts.
> See `plans/mechanics-council-review.md` for the production plan.

## What it does

Mimics, in miniature, what the pipeline does to mechanics:

1. **Generate** candidate mechanics one at a time (each with two example cards),
   threading the already-designed ones so they vary.
2. **Review** each draft with a **council** — N independent reviewers critique it
   cold (theme-free) against six standards, then a synthesizer applies a ≥2-of-N
   consensus filter and revises the mechanic in place, looping until it's clean or
   the iteration budget runs out.

It reuses MTGAI's `generate_with_tool` transport, so the same models, model
registry, and `.env` API key the real pipeline uses apply here — prompts tuned
here transfer 1:1. Defaults to the **same local model the real `mechanics` stage
uses** (`vlad-gemma4-26b-dynamic`).

## Run it

Use the MTGAI venv python (it already has `llmfacade` installed). From this folder:

```powershell
& ../backend/.venv/Scripts/python.exe mech_lab.py --count 4
```

Each run writes `runs/<timestamp>.{md,json}` (readable report + raw data) and,
when it generated drafts, `runs/<timestamp>.drafts.json`. `runs/` is gitignored.

## The iteration loop (the whole point)

The prose prompts live in **`prompts/*.txt`** — that's what we edit:

| file | role |
|------|------|
| `gen_system.txt` / `gen_user.txt` | how mechanics are generated |
| `review_system.txt` | the shared review standards (the six qualities) — used by reviewers AND the synthesizer |
| `review_user.txt` | the individual council member's instructions |
| `synth_user.txt` | the synthesizer/chair's instructions (consensus filter + revise) |

The structural JSON tool schemas live in `mech_lab.py`.

**To tune the review without re-rolling the drafts** (so output changes reflect
prompt edits, not generation randomness), generate once then replay:

```powershell
# 1. generate a fixed set of drafts  ->  runs/<ts>.drafts.json
& ../backend/.venv/Scripts/python.exe mech_lab.py --count 4

# 2. edit prompts/review_system.txt, prompts/synth_user.txt, ...

# 3. re-review the SAME drafts
& ../backend/.venv/Scripts/python.exe mech_lab.py --drafts runs/<ts>.drafts.json
```

Hand-author a `*.drafts.json` of deliberately flawed mechanics (a reskinned
keyword, a contradictory reminder, a boring stat-bump, an infinite loop) — plus
one genuinely *strong* mechanic — to pressure-test that the council flags each
failure mode **without over-rejecting the good one**.

## Useful flags

```
--theme PATH          theme JSON to generate against (default themes/sample.json)
--count N             how many mechanics to generate
--drafts PATH         skip generation, review these drafts (replay)
--model ID            model for everything (default vlad-gemma4-26b-dynamic, local Gemma)
--review-model ID     override just the review model
--council N           reviewers per round (default 3)
--iterations N        max review rounds (default 3)
--gen-temp / --review-temp / --synth-temp    sampling temperatures
--repeat-penalty F    llamacpp only; provider default 1.1 (synth retries escalate to 1.20)
--no-review           only generate (sanity-check the gen prompts)
```

For the API ceiling, `--model claude-sonnet-4-6` / `claude-opus-4-6` (needs
`ANTHROPIC_API_KEY` in `C:/Programming/MTGAI/.env`; there is no key locally right
now, so it's local-only until one is added). Other local options are in
`backend/mtgai/settings/models.toml`.

---

## Findings so far (2026-05-29)

First end-to-end cycle on local Gemma (`vlad-gemma4-26b-dynamic`), council of 3.

### ✅ The reviewer prompts work excellently

Generation produced a textbook-mediocre mechanic — **"Drift"** (`keyword_action`,
UBR, cx2): *"Drift a card from the top of your library to your hand."* All three
independent reviewers nailed it without any coordination:

- **unique/major** — all three flagged it as just *"Draw a card"* reworded;
  one specifically named Impulse / Sleight of Hand as the real precedent.
- **self_consistent/major** — all three caught that the *rationale* claims Drift
  covers Hand→Battlefield and Battlefield→Graveyard, but the reminder text +
  examples only ever define Library→Hand. A real self-contradiction.
- **wording/major** — tagged `keyword_action` but the examples use it like a
  triggered ability (Scry-style), so the templating is ambiguous.
- **interesting/major** — "a flat 'draw a card' with no tension or decision."

That's senior-designer-level critique catching exactly the mediocrity we're after.
The six-standard review prompt (`review_system.txt`) is a strong v1 — **don't gut it.**

### ❌ The synthesizer step structurally breaks on local Gemma

The synth call (`SYNTH_TOOL` / `synth_user.txt`) has to re-emit the **entire**
revised mechanic (both example cards) + consensus prose in one shot, with all 3
full reviews as input (~3.4k tokens). On Gemma it loops to the token cap and
produces nothing parseable — bumped the output budget 3072 → 8192 and it *still*
truncated (8192 completion tokens, **empty** text + zero tool-calls,
`finish_reason=length`). Generation and the 3 reviewers work fine because their
outputs are bounded; it's specifically the heavy nested re-emit that overwhelms it.

**This also affects the production plan:** that plan mirrors the *card* council,
whose synth re-emits the whole card. On the local model the mechanics stage uses
by default, that step would fail constantly. The plan should be revised to match
whatever shape we land on here.

### → Proposed next iteration (NOT yet implemented)

Split the synth into two bounded calls, each matching a shape Gemma already handles:

1. **Consensus** (small output): verdict + the ≥2-of-N issues + a short prose *fix brief*.
2. **Revise** (shaped exactly like generation, which works): "here's the mechanic +
   this fix brief → emit the improved mechanic." Maps nicely to the real pipeline's
   regenerate-with-`regen_reason` pattern.

### Open TODOs when picking this back up

- [ ] Implement the two-call synth split (consensus → revise) in `mech_lab.py` +
      replace `synth_user.txt` with `consensus_user.txt` + `revise_user.txt`.
- [ ] Re-run on the saved Drift draft (replay) to confirm a clean revision.
- [ ] Add a hand-authored `themes/`-adjacent drafts file: one strong mechanic +
      several broken ones (reskin / contradiction / boring / infinite loop) and
      verify catch-rate vs false-positive-rate.
- [ ] Try `--council 5` and a couple of themes to gauge variance.
- [ ] Once happy: port `review_system.txt` + the (reshaped) synth prompts + tool
      schemas into `mechanic_generator.py` per the production plan, and update the
      plan to the two-call synth shape.

## Not production

Nothing here is wired into MTGAI. The artifacts to port back are the prompt files
and the tool schemas in `mech_lab.py`.
