# Mechanic council review strictness — captured run

Snapshot of the `mechanics` stage logs from the **transformers** set generation
run on **2026-05-30** (~09:33–09:55 local). Captured as evidence for the Trello
investigation into the per-candidate council review strategy.

Source: `sets (new)/transformers/mechanics/logs/` (copied here to survive a re-run,
which overwrites that dir).

## What this is

Full per-call llmfacade transcripts (`.jsonl` + `.html`) for one complete
`mechanics` stage run:

- **12** candidate drafts (6 slots × 2 attempts — every slot needed a regen)
- **108** reviewer calls
- **36** synthesizer calls
- **1** picker call

**157 LLM calls** for one mechanics stage. Model: `vlad-gemma4-26b-dynamic` (local).

## Headline finding

**0 of 108 reviewer calls returned OK.** The council's only "pass" exit
(`council_review`) requires *all 3* reviewers to return OK in one round, so it
never fired. Every one of the 6 slots therefore:

1. failed its first draft's 3 council rounds,
2. regenerated from scratch (threading the council's reasons),
3. failed the regen's 3 council rounds too,
4. and was accepted **best-effort, flagged REVISE** (the
   `generate_mechanic_candidates` fallback at `mechanic_generator.py:1610`).

The entire pool of 6 ended up flagged REVISE; the picker (`pick_best_mechanics`)
selected **Rebuild / Shift / Overdrive** — all REVISE — for the final slate.
This inverts the design intent ("the pool ends up (near-)all council-passing").

## The 6-candidate crop (accepted draft = slot's regen; 1st attempt in parens)

| # | Accepted (REVISE) | 1st attempt (discarded) | Picked? |
|---|-------------------|-------------------------|---------|
| 1 | Rebuild           | Consume Energon         | ✅ |
| 2 | Shift             | Scanner                 | ✅ |
| 3 | Spark-Siphon      | Energon Scarcity        |    |
| 4 | Energon Scarcity  | Energon Scarcity        |    |
| 5 | Scan              | Deploy Mini-Con         |    |
| 6 | Overdrive         | Ravage                  | ✅ |

## Problems to investigate (see Trello card)

1. **Unanimous-OK exit + ~0% reviewer OK rate = structurally guaranteed REVISE.**
   The gate never passes; the "cheap common path" (all-OK round 1) never triggers.
   Highest-leverage knob: relax the exit (majority / 2-of-3) and/or the reviewer bar.
2. **`unique` + `interesting` are ~unpassable for simple, common-viable mechanics**
   — exactly what the set needs. The theme-blind reviewer sees only the bare
   skeleton, so a clean sac-for-counter reads as "reskin of aristocrats" +
   "flat stat bump" every round.
3. **The synth churns instead of converging** — e.g. Rebuild gained an `exile`
   clause in round 1 and lost it again in round 3, and the synth introduced its
   own templating bugs (a literal `{cost}` placeholder, non-standard "If you do…")
   that the next round's reviewers then flagged. Reviewers re-litigate every round.
4. **One class of *legitimate* recurring flag:** the generator emits reminder-text
   vs example-card cost contradictions (a real `self_consistent` bug worth fixing
   at the generation source, not via the council).
5. **Cost:** worst-case (max rounds + regen) hit on *every* slot — 157 calls.
6. **Minor secondary bug:** dedup only adds to `seen_names` on accept, so a name
   rejected at one slot can recur — the pool here contains two "Energon Scarcity".
