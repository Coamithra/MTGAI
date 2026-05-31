# Post-fix council re-run — findings catalog (LIVE, in progress)

Working catalog for the manual verification of the shipped council fix
(commits `c29628e` + `e45c827` + `4ee5525`: gate on "is it broken?" via
**majority-of-effective-OK**, taste categories removed). Companion to the
2026-05-30 captured *bad* run documented in `README.md`.

- **Run:** transformers (`TF`) set, mechanics stage, **2026-05-31**.
- **Model:** `gemma4-26b-vlad-updated` (local Gemma, reasoning/"thinking" mode).
- **Transcripts:** `sets (new)/transformers/mechanics/logs/` (live; overwritten on re-run).
- **Status:** run ongoing — cases appended as they surface.

---

## Headline: the pass-rate fix works

Reviewers now return genuine OK and candidates clear the council on round 1
(e.g. **Modulate 3/3 effective-OK → pass**), vs the old **0/108 raw OK** where
the unanimous-OK gate never fired. The core goal — escape the structurally-
guaranteed-REVISE gate — is met.

## Central thesis (the recurring gap)

> The council + synth reliably audit **rules-text consistency & wording**, but
> never simulate **"what actually happens when you play this."** Gameplay
> (`playable`) flaws are caught only by accident — **outvoted** (Integrate) or
> **fixed sideways** (Overdrive) — never by deliberate play-pattern reasoning.

---

## Case 1 — Integrate  (passed; a correct major flag was OUTVOTED)

**Definition.** Keyword `Integrate {cost}`: "(When this enters, you may pay
[cost]. If so, it becomes an Equipment and attaches to a creature you control.)"
Examples: **Scrap-Bot** (1/1, `Integrate {1}`) and Decepticon Striker (grants
the equipped creature an attack-trigger).

**Real flaws.**
1. **`playable`** — Scrap-Bot becomes a **do-nothing Equipment**: it grants the
   equipped creature *nothing* (no stats, no ability). You pay extra to turn a
   1/1 into a blank attachment. (Striker is fine — it grants an effect.)
2. **`self_consistent` / rules soundness** — reminder says it *"becomes an
   Equipment"* (i.e. stops being a creature) but the rationale says Integrated
   permanents are *"both creatures and artifacts."* Contradiction. And per the
   "Equipment that's also a creature" rule (CR 301.5e), a permanent can't be a
   creature **and** an attached Equipment at once — it unattaches. So "stays a
   creature and stays attached" is illegal as written.
3. **`wording`** — literal `[cost]` placeholder in the reminder text.

**Council vote: 2 OK (no issues) / 1 REVISE.** The lone REVISE (`af1b4a3f`)
**nailed flaw #1** verbatim ("makes cards like Scrap-Bot dead cards… provide no
stats or abilities") **and** flaw #3 (`[cost]` placeholder).

**Outcome: PASSED.** `ok_votes*2 > n` → `2*2 > 3` → majority OK. The correct,
concrete `playable/**major**` defect was **discarded by headcount**.

**Misses.** No reviewer raised flaw #2 (creature-vs-Equipment soundness / 301.5e).

**Prompt/strategy implications.**
- **Severity-weighted gate:** a `major` defect in a blocking category from *any*
  reviewer should not be outvoted (block, or force a synth fix-in-place + re-
  review). These defects are objective/verifiable; false positives are rare, so
  a lone correct catch shouldn't lose to two who didn't trace the example.
- **Reviewer prompt:** add explicit checks — (a) "does each example card actually
  *do something* when its own mechanic is used, or is it a do-nothing/trap?",
  (b) "if the mechanic changes a permanent's types, is the result legal &
  unambiguous (still a creature? can it attack/block?)".

---

## Case 2 — Overdrive  (rejected 3/3, but for the WRONG reasons; fixed sideways)

**Definition (original).** `Overdrive {T}, tap an artifact`: examples gave the
creature **"+1/+1 until end of turn"** (Scrap-Metal Scout) and **"a +1/+1
counter + gains vigilance until end of turn"** (Cybertronian Juggernaut).
Reminder: "(Tap this and an artifact to give it +1/+1 until end of turn.)"

**Real flaw (gameplay / `playable`).** Self-buff via a `{T}` cost is near-
useless: paying `{T}` taps the creature, so it can't be declared as an attacker
*or* a blocker — the only functional line is the post-declare-block defensive
trick. And **vigilance "until end of turn" on an already-tapped creature is pure
nonsense** (vigilance only matters when attacking; it's already tapped). The
rationale even hand-waves it ("can't attack or block effectively that turn, but
provides a burst of power" — a burst you can't use to attack).

**Council vote: 3/3 unanimous REVISE — all citing only SURFACE defects:**
- `self_consistent/major` (×3): example 2's counter+vigilance contradicts the
  reminder's "+1/+1 until end of turn".
- `wording` (×2–3): the reminder's *"it"* is ambiguous (creature or artifact?).

Not one of the three reasoned about the dead vigilance or the unusable self-buff.
Right verdict (reject), wrong reason — a **systematic** blind spot, not one
flaky reviewer.

**Synth revision (`a20f3e97`).** Redefined to a **permanent +1/+1 counter**
("Tap this creature and an artifact: put a +1/+1 counter on this creature") and
moved **vigilance to a plain static keyword** on Juggernaut. Result: functional
(a slow self-grower; a bit weak) — **both gameplay flaws gone.**

**…but fixed for the wrong reasons.** The synth's `synthesis` / `consensus_issues`
/ `review_notes` mention only consistency, the `it` ambiguity, templating, and
"better archetype support" — **never** the gameplay problem. The fix is a lucky
byproduct: collapsing "EOT buff vs counter" to *counters* incidentally kills the
wasted-buff issue; pulling vigilance out to fix templating incidentally kills the
nonsense. **Had the synth reconciled the other way** (everything → "+1/+1 EOT"),
the flaw would have **survived and worsened**, and re-review would have passed it.

**Re-review round 2:** revised version → OK so far (on track to pass).

**Implication.** Reinforces the prompt-strengthening direction: the synth only
fixes what the council *names*. If the council names only surface defects, deep
`playable` flaws are fixed by luck or not at all. Reviewers must be pushed to
simulate the actual play pattern.

---

## Case 3 — Protocol  (rejected 2-1; the user's gameplay flaw was never named)

**Definition.** Keyword `Protocol {X}`: "(When you cast an artifact spell, you
may pay {X}. If so, create a 0/1 Servo.)" Examples: Quintesson Drone (`{U}`,
`Protocol {1}` → **one** Servo) and Quintesson Overseer (`{2}{U}{B}`,
`Protocol {1}` → **two** Servos).

**Real flaws.**
1. **`playable` (gameplay)** — read literally, the `{X}` is a chosen variable but
   the output is a fixed 0/1 Servo, so paying more does nothing: a
   strictly-dominated cost, you always pay the minimum. "More expensive to do the
   same thing." *(User's catch.)*
2. **`self_consistent`** — `Protocol {1}` makes one Servo on Drone but two on
   Overseer; the notation doesn't encode the effect.
3. **`wording`** — `{X}` placeholder vs the examples' `{1}`; and "When you cast"
   (reminder) vs "Whenever you cast" (examples).
4. Weak/grindy 0/1 Servos (taste, non-blocking).

**Council vote: 1 OK (no issues) / 2 REVISE → effective 1/3 → FAIL (rejected).**
Both REVISErs caught flaw #2 (`self_consistent/major`, example-2 token count) and
flagged the `{X}` — but **only as "invalid templating"** (`wording`), never as
flaw #1.

**Misses.** The `{X}`-doesn't-scale **gameplay** flaw was named by **no one**.
The `{X}` was seen as a templating defect, not a dominated-cost design flaw —
**prediction confirmed**: notation-wrong is visible, play-pattern-pointless is not.

**Not an outvote** (the major contradiction got the majority, so the gate worked).
But it reinforces the thesis *and* the "fixed sideways" risk: the synth is now
revising, and the likely fix — hardcode the cost to a fixed `{1}` + reconcile the
token count — would make flaw #1 **vanish as a byproduct of fixing the
templating**, not because anyone understood it. *(Synth outcome: TODO — update
see resolution just below.)*

**Synth outcome (landed) — prediction confirmed (fixed sideways) + synth churn.**
The synth (`0975468f`) hardcoded `{X}` -> `{1}`, fully defined the Servo, and made
Protocol create one token (extra token moved to a separate ability on the rare).
Flaw #1 vanished -- but its `synthesis`/`review_notes` cite **only** the `{X}`
placeholder + token-count consistency; the scaling problem was **never reasoned
about**, just removed as a byproduct. Round-2 re-review then came back **3/3 REVISE
again**: the examples still write `Protocol {1}`, which all three flagged as
**invalid notation for a triggered ability** (reads as activated; redundant with
the reminder), and one caught that the example creatures **lack the `Artifact`
supertype** (so casting them would not trigger their own Protocol). Classic synth
**churn** -- fixes the named issues, surfaces/leaves others, does not converge.

**Notable:** those round-2 catches (triggered-vs-activated, missing supertype) are
*sharp rules reasoning* -- so the reviewers are competent at rules; the blind spot
is **specifically gameplay-value**, which makes the "point its reasoning at 'play
it out'" prompt approach more promising, not less.

**Round-3 update (about to pass technically, still silly).** Synth round 3
(`33f4`) fixed the notation (Drone is now just `Protocol`, cost folded into the
reminder); the round-3 reviewer dropped to **wording/MINOR only** (should be
"you may pay {1}. If you do..."; omits "token") -> about to PASS. But the
**Overseer example is now self-redundant**: it has `Protocol` (pay {1} on
artifact-cast -> 1 Servo) AND a free "Whenever you cast an artifact spell, create
two Servos" -> you would never pay {1} for one when you get two free. The synth
*created* this in round 2 (splitting "Overseer makes 2" into a separate ability to
fix the `self_consistent` bug) and it survived round 3. A `self_consistent` fix
birthed a `playable` one, no reviewer caught it, and it is set to pass. Also an
example-card-quality miss (same family as Scrap-Bot): the mechanic is fine, the
example card is nonsensical -- reviewers should sanity-check whether any ability
is pointless/dominated *on its own card*.

---

## Operational findings (not strategy, but affects the run)

- **Reasoning-mode transport.** This model runs with `thinking_style` set and
  emits a `reasoning` block; it returns the verdict as a **fenced ```json block
  in `text`**, NOT a native `tool_calls` entry. Any log parser must read the
  fenced JSON (the old run used native tool_calls). 
- **Thinking-overrun truncations.** Reviewers spend 16k–30k chars on chain-of-
  thought; occasionally a call burns its whole 8192-token output budget thinking
  and hits `finish_reason=length` with **zero answer**. Handled by
  `_generate_with_escalation` bumping 8192 → 16384 (sticky for the run). Cost: a
  wasted call + retry. **This is a different truncation cause than the synth re-
  emit blamed in `learnings/reasoning-budget-overrun.md`** — here it's the
  *reviewers* over-thinking.
- **Recurring templating bugs in generation:** `[cost]` placeholder (Integrate),
  `Modulate {1}` keyword templating flagged. (Tracked separately as deferred
  follow-up `6a1c6d36` — generation-source reminder/example lockstep.)

---

## Case 4 -- Reformat / "Reconstruct N" (Protocol's regen: council is RIGHT, generator + synth are the problem)

Protocol's from-scratch regen abandoned the concept and produced a new **B/G**
mechanic, **Reformat** -- ETB: sacrifice a permanent -> +1/+1 counter(s) + become
an artifact. Examples: Scrap Scavenger (1 counter), Apex Reconstruct (2 counters).

**This time the council is RIGHT -- the flaws are real, not over-strictness:**
- "put a +1/+1 counter on **it**" is genuinely ambiguous: "it" reads as the
  *sacrificed* permanent (now in the graveyard), not the entering creature.
  Trivially fixable ("on this creature"), but a real bug.
- Example 2 makes *two* counters vs the reminder's one (same generator tic as
  Protocol's Overseer).
Both are **generation-source** bugs (deferred follow-up `6a1c6d36`,
reminder/example lockstep). The council catches them correctly; the *generator*
keeps producing them. So not all churn is council over-strictness.

**Key lesson -- the synth FLATTENS instead of PARAMETERIZING.** Synth `b9f7`
resolved the consistency bug by (its own words) "ensur[ing] the keyword has a
**fixed, consistent effect** across all examples" -- it deleted Apex Reconstruct's
two counters, making every card a flat +1/+1. The design-correct fix was to
**parameterize**: `Reconstruct N` (sacrifice a permanent -> put N +1/+1 counters on
this creature), Scrap Scavenger = N1, Apex = N2 -- exactly how MTG scales keywords
(Annihilator N, Devour N, Fabricate N). Cross-example variation isn't an
inconsistency to erase; it's the parameter N waiting to be named. (The keyword is
even named "Reformat" while the example card is literally "Apex *Reconstruct*".)

**New, distinct blind spot:** faced with "rare example does more", the synth
resolves it by **flattening to one value**, never by **generalizing to `Keyword N`**
-- it buys consistency by deleting design space. Mirror of Protocol's `{X}`: there a
*meaningless* variable should have been *removed*; here a *meaningful* variation
should have been *parameterized*. The synth flattened both -- it can't tell spurious
from meaningful variation.

Mixed result: the flattened Reformat is blander, and it churned hard (rounds 1+2 =
6 REVISE) -- but it ultimately **PASSED on round 3 (2 OK / 1 `wording/minor`
REVISE)**, the lone REVISE outvoted (the same severity-blind majority quirk). So it
landed `verdict=OK` in the pool, not best-effort REVISE. Net: a blander mechanic,
passed, after an enormous call count for one slot (the Protocol saga + 6 Reformat
reviews).

**Fix applied this session (prompt):** taught the generator (`mechanic_system.txt`)
and the shared reviewer/synth system prompt (`mechanic_review_system.txt`) about
parameterized `Keyword N` -- Scry/Fabricate/Devour N examples, the "scalable
variation is a parameter, not a contradiction" framing (reviewers stop
false-flagging it; the synth parameterizes instead of flattening), plus the
anti-`{X}` guard. See "Applied this session".

---

## KEY FINDING (Protocol round 3): the gate ignores severity -- minor nits block

`_effective_verdict` (`mechanic_generator.py`) marks a REVISE as blocking if ANY
issue is in a blocking category {playable, wording, self_consistent, other} --
**severity is never checked**. So a `wording/minor` blocks exactly as hard as a
`playable/major`.

Protocol round 3 is the proof. The mechanic is functionally fine (no playability
flags left), but it keeps failing on reminder-text TEMPLATING nits:
- `cb6d1` (`wording/minor` x2): "should be 'you may pay {1}. If you do, ...'" + omits "token".
- `e8db7` (`wording/major` + `minor`): "use 'pay {1}: create'" + omits "token".

The two reviewers' fixes **contradict each other**, and e8db7's `{1}: create` colon
syntax is *activated*-ability templating -- **wrong** for a *triggered* ability. So
the synth can never satisfy all of them -> guaranteed churn until max rounds ->
regen / best-effort REVISE. This is the **old 0/108 over-strictness reborn** as
`wording/minor` instead of taste. (It also burned a large share of the run's calls.)

**Mirror image of the gameplay blind spot, fixed by the SAME lever:** weight by
severity -- only `major` blocking defects gate; treat `minor` as advisory (like
`elegant`). That simultaneously (a) lets a lone `playable/major` catch count
(Integrate) and (b) stops trivial wording trapping a sound mechanic (Protocol).

## EFFICIENCY FINDING: wasted final-round synth before a from-scratch regen

`council_review` runs Phase 2 (synth) on *every* failing round with no "is this
the last round?" guard (`mechanic_generator.py`, the `for _round in range(1,
max_iterations+1)` loop, synth at ~line 1055). So on the final review round
(round 3) the synth still runs and revises the mechanic -- but when that REVISE
result triggers a **from-scratch regen**, the regen re-drafts using only the
reviewers' `reasons` (computed at line 1040, *before* the synth) and **discards
the synth's revised mechanic**. The code even comments it knows the last-round
revision is "unconfirmed... honestly left REVISE" (line ~1094).

Observed on Protocol: the round-3 synth (`bceb`, a HEAVY-budget local call,
~159s) ran and was immediately thrown away when the from-scratch regen
(`candidates-291`) started. One of the priciest calls in the stage, wasted, per
regenerated mechanic.

**Caveat (so the fix is correct, not blanket):** the final-round synth is NOT
always wasted -- on the *last* attempt (post-regen council, no regen left), the
still-REVISE result is accepted best-effort and the kept mechanic IS that synth's
revision. So only skip it when a regen will follow.

**Fix:** skip the Phase-2 synth on the final review round **only when a regen
attempt remains** (pass the caller's remaining-attempts state into
`council_review`, e.g. a `regen_remaining` / `skip_final_synth` flag). Saves one
HEAVY synth call per regenerated mechanic -- directly targets the stage's
call-count sore point (the old 157).

Related UX gap: the from-scratch regen phase has **no thumbs and no dedicated
indicator** -- the slot keeps a stale "Reviewing..." badge while the model
re-drafts (a long, silent wait at local-model speed), so it reads as a stall.

## Applied this session (shipped, not just proposed)

- **Reminder-text length: hard `under 100 characters` -> soft `concise`**
  (`mechanic_review_system.txt`, `wording` criterion). The 100-char cap
  false-flagged legitimate Cascade/Convoke/Trample-class reminders (120-230
  chars); now a soft nudge, not a hard blocking number. Live immediately (no
  template cache, so it took effect mid-run). NOTE: `wording` is still a blocking
  category and the gate still ignores severity, so the severity fix is still
  needed to fully prevent a "not concise" wording flag from blocking.

- **Parameterized `Keyword N` guidance** added to `mechanic_system.txt` (generator)
  and `mechanic_review_system.txt` (shared reviewer/synth): scalable variation across
  examples is a *parameter* (Scry/Fabricate/Devour N), not a `self_consistent`
  contradiction; the synth should *parameterize*, not *flatten*; includes the
  anti-`{X}` guard ("the parameter must change the effect"). Targets the Reformat
  flatten and the generator's example/reminder mismatch at the source. Live
  immediately (no template cache).
  - *Resolved:* the generator prompt's two hard "under 100 characters" mandates
    (`mechanic_system.txt` lines ~36 & ~60) were also loosened to `concise`.

- **Severity-weighted gate** (`mechanic_generator.py`): `_effective_verdict` now
  gates only on a `major` blocking defect; `minor` blocking issues are advisory
  (like `elegant`). The council exit changed from "majority of effective-OK" to
  **"no open `major` blocking defect"** -- so a lone correct major can't be
  outvoted (the Integrate fix) AND trivial `minor` nits stop trapping a sound
  mechanic (the Protocol fix). Subsumes candidate #3 (any open major already
  triggers a synth + re-review). Tests flipped/added.

- **Reviewer "play it out" pass** (`mechanic_review_system.txt`): a procedural step
  telling each reviewer to simulate every example card -- does it do something when
  its own mechanic is used (dead-on-use), are type/zone changes legal (attack/block,
  Equipment-that-is-a-creature, vanished referents), is any ability pointless/
  dominated on its own card. Framed as `playable`/`self_consistent`: function, not taste.

- **Skip the wasted final-round synth before a regen** (`mechanic_generator.py`):
  `council_review` gained `skip_final_synth`; the regen loop passes it while a regen
  attempt remains, so the final-round synth (which the regen would discard) is
  skipped -- one HEAVY call saved per regenerated mechanic. Left on for the last
  attempt (its revision is kept best-effort). Tests added, both sides.

- **Picker JSON-repair tolerance** (`mechanic_generator.py`): `_salvage_tool_json`
  recovers selections from raw text (fenced block, or control-token / jammed-tool-
  name noise) when the local model emits no structured tool call, so the picker keeps
  the model's real ranking instead of silently degrading to first-N. Strict parse only
  -- genuinely malformed pseudo-JSON still falls back. Tests added.

- **Generator guardrails** (`mechanic_system.txt`): "no ambiguous referents" (name
  the object, never a bare "it" -- the Reformat bug) + "both examples must match the
  reminder; a bigger rare is a `Keyword N` parameter, not a different effect".

All live immediately (prompts: no template cache; logic in `mechanic_generator.py`).
**Full suite green: 1445 passed.**

- **Regen-phase UX gap fixed** (backend + frontend): the re-draft phase now emits a
  `mechanic_council_update` with `kind: "regenerating"` (reusing the council channel,
  no new event type), and `wizard_mechanics.js` shows a "Regenerating from scratch…"
  header badge instead of a frozen "Reviewing…" while the LLM re-drafts. Cleared when
  the fresh draft lands. Test added.

## Candidate changes — ALL APPLIED this session (detail/rationale below; see "Applied this session" for what shipped)

1. **Severity-weighted gate** — major blocking defect from any reviewer overrides
   majority (block or force synth fix + re-review); keep majority for minor/advisory.
   - *Variant worth trying:* have each reviewer return an **overall `ok` / `nit` /
     `major` rating in addition to** the per-issue list, so the gate reads a holistic
     self-classification (dealbreaker vs nit) rather than inferring severity from the
     issues. (The data is already there per-issue; this just makes the reviewer
     commit to the call explicitly.)
2. **Reviewer prompt: add a "play it out" pass** — example-card function (trap/
   do-nothing check) + type-change rules soundness (attack/block legality).
3. (Maybe) **synth must address every cited major-blocking issue**, even on an
   otherwise-passing round, so a dissenting correct flag still gets a fix pass.

## Still collecting
- Watching whether revised Overdrive passes re-review with anything still off.
- Need more `playable`-flaw samples to confirm #1 vs #2 leverage.
- Final picker slate + total call count + truncation tally (vs old 157). -> see below.

## Final run result (run COMPLETE, 2026-05-31)

- **Total calls: 40** (6 draft, 28 review, 5 synth, 1 pick) vs the old run's
  **157** -- a ~75% cut.
- **Reviewer OK rate: 37%** (10/27 effective) vs old **0/108 (0%)**. The structurally-
  guaranteed-REVISE gate is decisively escaped.
- **Pool: all 5 candidates `verdict=OK`** (Modulate, Integrate, Overdrive, Reformat,
  Linkup) vs the old run's all-REVISE slate. Design intent ("pool ends (near-)all
  council-passing") restored.
- **Issue categories cited across the run: wording 16, self_consistent 11,
  playable 2.** The thesis in one line -- the council churns on wording/consistency
  and almost never flags playability.
- **Only 1 truncation** all run (thinking-overrun; escalation handled it).

**Caveat -- "all-OK" means "passed the gate", not "flawless".** The OK pool still
contains every flaw we catalogued: Integrate's dead Scrap-Bot example (passed via
outvote), Overdrive (fixed sideways), Protocol's synth-churn, Reformat's flatten.
The blind spots let real gameplay/example issues ride along under an OK stamp.

**Picker output was malformed (operational).** The `select_best_mechanics` call
emitted corrupted, non-JSON text -- a `<|"|>`-style control-token artifact with the
tool name jammed onto the payload
(`select_best_mechanics{overall_rationale:<|"|>...`) -- so the slate didn't parse
cleanly. Its rationale implies it meant to pick 3 ("one simple + two moderate", full
WUBRG spread). Same class as the reasoning-mode transport issue: the local model
doesn't reliably emit clean structured output; the picker needs the same
fenced-JSON / repair tolerance the reviewers got. Final persisted state:
`mechanics/candidates.json` with all 5 OK; **no `approved.json` written** -- check
what the wizard renders for the picks.
