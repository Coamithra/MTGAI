---
name: qa-bot
description: >
  Run a self-driving QA session against the MTGAI wizard. Boots the server in
  --debug mode, drives the app via claude-in-chrome to adversarially break it,
  logs each bug to Trello, and farms fixes to subagents (CONTRIBUTING, full
  auto self-merge), looping until a server restart is warranted. Use when the
  user says "QA Bot", "run QA", "self-drive QA", or "find bugs in the app".
---

# QA Bot — self-driving QA orchestrator

You are the **QA orchestrator**. Your job: keep the MTGAI wizard under continuous
adversarial test, turn every bug you find into a tracked + fixed Trello card, and
keep the cycle going. The app is a single live instance behind an app-wide AI
mutex (one AI call at a time), so **QA driving is serial** — one probe at a time.

**Drive the app yourself, in this (master) chat.** Do **not** spawn subagents for
QA driving — the user wants to watch the probing happen live, and a subagent's
browser session is opaque. You hold the single browser session and drive every
probe directly. The *only* thing you delegate is the **bug fixing** (code edits in
separate worktrees), which genuinely parallelizes — see §5. So: QA driving =
master chat, serial; fixes = subagents, parallel.

This skill assumes the Part-A debug harness exists (it ships with the QA Bot
card): `serve --debug`, the floating 🐛 QA Debug panel, and the
`/api/debug/*` endpoints. See `reference.md` for the endpoint + probe-area
cheatsheet.

**Coverage memory.** Trello records *bugs*; it does not record what you tested
and found **clean**. So a fresh orchestrator (after a handoff) would re-probe the
same areas blind. The fix is the **QA journal** — a persistent cross-session log
of every probe and its outcome. Read it at startup, append to it after every
probe, summarise it at handoff. Format + location: see §1.5 and `reference.md`.

## 0. Preconditions (check first, don't assume)

- **Chrome extension connected.** This skill drives the app with the
  `mcp__claude-in-chrome__*` tools. If they aren't available, load them via
  ToolSearch (`{query: "claude-in-chrome", max_results: 30}`). If the extension
  isn't connected, ask the user to connect it — do **not** fall back to
  computer-use pixel clicking (the browser is read-tier there).
- **On `master`, clean-ish.** This skill runs from the repo root checkout.
- **No server already running** on the target port (default 8080).

## 1. Boot the system

1. `git pull origin master` (fast-forward). If it won't fast-forward, stop and
   tell the user — don't force.
2. Launch the server **in the background** with debug mode on:
   `cd backend && python -m mtgai.review serve --debug --port 8080`
   (run_in_background). Wait until `http://localhost:8080/pipeline` answers.
3. Open Chrome to `http://localhost:8080/pipeline` (navigate tool). Confirm the
   floating **🐛 QA Debug** panel is present (bottom-right) — that proves debug
   mode is live. If it's missing, the server didn't get `--debug`; fix that
   before continuing.

## 1.5. Load the QA journal (cross-session memory)

The journal lives at `output/qa-runs/QA-JOURNAL.md` (repo-relative;
gitignored, so it persists locally across sessions with no commit churn).

1. **Read it now**, before the first probe. If it doesn't exist yet, create it
   with the header below. It is the record of what prior sessions already
   exercised and what they found.
2. **Note the current `master` short-SHA** (`git rev-parse --short HEAD`) to stamp
   new entries. The SHA is metadata — it records what each result ran against — but
   by default it does **not** trigger re-testing (see step 3).
3. **Default behaviour: never re-test. Always look for new problems.** Treat
   *any* journal entry — clean **or** bug-filed, at any SHA — as already covered,
   and spend the session on ground the journal does **not** yet cover. Re-running
   a probe an earlier session already did (including re-checking a fix or a
   stale-SHA clean) happens **only when the user explicitly asks for it** (e.g.
   "re-verify the skeleton fixes", "re-run the theme probes"). Absent such an
   order, prefer untested areas and skip everything in the journal.

Journal format — probes are grouped under a `## <date>` header and a
`### <short-SHA>` subheader, with one append-only table per SHA. Add a new
`### <short-SHA>` table when the SHA changes within a day, and a new `## <date>`
header when the date rolls over:

```markdown
# QA Journal — MTGAI wizard

Persistent cross-session QA coverage log. Each probe appends one row, grouped
under a `## <date>` header and a `### <short-SHA>` subheader (the `master`
commit the probes ran against — useful for tracing regressions).
Outcome: `clean` (exercised, no bug) / `bug` (filed — link the Trello card) /
`partial` (couldn't fully exercise — say why, e.g. ComfyUI not running).
Default: a recorded area is covered — skip it and find new ground. Re-test only
when the user explicitly orders it.

## 2026-06-06

### b754962

| Area / Tab | What was exercised | Outcome | Card / Notes |
|-----------|--------------------|---------|--------------|
```

## 2. Configure for cheap, fast runs

Per the card: always use the cheapest 2-bit Gemma with thinking disabled — QA
exercises the app *plumbing*, not card quality, so janky cards are fine.

- Use the debug panel (or `POST /api/debug/quick-project`) to spin up a QA
  project: small `set_size`, `prefab` ON (card_gen/mechanics short-circuit),
  optional inline theme text. This applies the `qa` preset automatically
  (all-Gemma-2bit, thinking off).
- To test a *specific* later stage without waiting on the slow early phases, use
  **Seed to stage** (`POST /api/debug/seed-stage`) — it clones a finished golden
  project and drops the wizard straight onto the chosen tab.
- Never touch the native OS save/open dialog. The debug Save button + the
  quick-project / open-path endpoints write server-side. If you ever see an OS
  file picker, you've taken a wrong path — back out and use the debug surface.

## 3. The QA loop

Repeat until the **restart trigger** (§5):

1. **Pick the next probe area** from the checklist in `reference.md`, steered by
   the **QA journal** (§1.5): pick areas — and within an area, controls/inputs —
   the journal does **not** yet cover; skip what it already records (clean or bug),
   unless the user explicitly ordered a re-test. The goal each session is *new*
   ground, not re-verification. Rotate so coverage stays broad: project settings →
   theme → mechanics → skeleton → card_gen → gates → ai_review → finalize →
   art/render tabs → cross-cutting like cancel-mid-run, tab-switch,
   edit-past-stage, bad input.

2. **Drive the probe yourself** for that ONE area — in this chat, not a subagent
   (see the intro). For that area:
   - go to the exact tab URL and drive it with the claude-in-chrome tools,
   - **the click-first mandate** (§3.5): drive the *real UI* — click the actual
     control, type into the actual field, press the actual Save/Refresh/Re-pick
     button, and read the outcome back from the *rendered DOM / a screenshot*, one
     screenshot per meaningful step. Direct `fetch()`/`javascript_tool` calls to
     `/api/*` are a **fallback only**, for inputs the UI cannot express (malformed
     JSON bodies, `Infinity`, out-of-order endpoint calls, ids the form would
     never submit),
   - the adversarial brief: *click every control, feed empty/huge/weird input,
     double-click, cancel mid-run, switch tabs mid-run, edit a past stage,
     reload mid-action, hit endpoints out of order* — try to break it,
   - for each confirmed bug, capture the evidence in §4 (repro steps, expected
     vs actual, console errors via `read_console_messages`, failing network calls
     via `read_network_requests`, a screenshot).
   Because the app is serial, run probes **one at a time** — never two browser
   drivers at once.

3. **Triage each bug you hit.** Confirm it's real and not test-harness noise
   (a 409 "AI busy" during a deliberate concurrent action is *expected*, not a
   bug). Dedupe against bugs already filed this session.

4. **File it on Trello** (board `69f86a83`, list `To Do`, label `bug`):
   `trello --board 69f86a83 card add "To Do" "<title>" "<repro + expected/actual + console/network + which file likely>"`.
   Title is a short imperative. Keep the running bug list in your context.

5. **Farm the fix** (full auto self-merge — the user opted into this). Spawn a
   fix subagent (general-purpose) told to **follow `CONTRIBUTING.md` end-to-end**
   for that Trello card: tracker doc → worktree → research → design → implement →
   verify → `/review` → PR → self-merge → clean up → move card to Done. Fix
   subagents edit code in **their own worktrees**, so several can run in
   parallel (only the browser driving is serial). Pass the card id + your full
   repro so they can act cold.

6. **Log it in the journal** (every probe, bug or not — this is the
   coverage memory). Append one row to `output/qa-runs/QA-JOURNAL.md` under the
   `## <date>` / `### <short-SHA>` table for this session (create the header +
   subheader + table if the date or SHA is new) with the area/tab, a terse "what
   was exercised", the outcome (`clean` / `bug` / `partial`), and the Trello card
   link or a short note. A probe that found nothing still gets a `clean` row —
   that is the whole point, so the next session doesn't re-run it. One row per
   probe; never delete prior rows.

7. **Keep driving.** Don't wait for fixes to land before the next probe —
   queue them and continue QA. Track how many fixes have merged.

## 3.5. Click-first: drive the UI, not the API

The whole point of a claude-in-chrome QA bot is to exercise the app the way a
real user does. A probe that fires `fetch()` at `/api/*` tests only the **server
contract**: it bypasses button wiring, event handlers, client-side validation,
the exact request shape the UI builds, the in-app dialog system, SSE repaint, and
layout. Endpoint-only probing reliably finds 500s and missing server validation,
but it **silently skips the entire UI layer**, so dead controls, mis-wired
handlers, a button that posts the wrong body, or a modal that will not close go
uncaught. (Not hypothetical: an early run of this skill drifted almost entirely
to `fetch()`, and every bug it found was an endpoint-level 500 while the UI layer
went untested.)

Rules for every probe:
- **Primary is real interaction.** Click the control, type into the field, press
  the real button. Read the outcome back from the **rendered DOM / a screenshot**,
  not from the JSON response. One screenshot per meaningful step, as evidence.
- **Fallback is `fetch()`.** Use it only for inputs the UI genuinely cannot
  express: malformed JSON bodies, non-finite numbers, calling endpoints out of
  order, a nonexistent id the form would never submit. These test the durable
  server backstop and are worth keeping, as the *supplement*, not the main course.
- **Record the split.** For each thing exercised, note whether it was *clicked*
  or *fetched*, so endpoint-only drift is visible at triage (§4) and in the
  journal row.

Journal implication (§1.5): a `clean` row is only as strong as the layer it
tested. An area exercised **only via `fetch()`** is `partial` (UI layer
untested), **not** `clean`, so a later UI-first re-probe of it is new ground, not
a re-test, and is **not** blocked by the "skip covered areas" default.

## 4. Bug evidence to capture

For each confirmed bug, capture the following — it's what goes on the Trello card
(§3 step 4) and backs the journal row (§3 step 6):
- `title` — short imperative ("Skeleton refresh 500s on empty knobs")
- `area` / `tab`
- `repro` — numbered steps a cold reader can replay
- `expected` vs `actual`
- `how`: per thing exercised, *clicked* (real UI) or *fetched* (direct `/api/*`);
  see §3.5. An area covered only by `fetch()` is `partial`, not `clean`.
- `console` — relevant console errors (verbatim)
- `network` — any 4xx/5xx the action caused (method + path + status)
- `screenshot` — path/ref
- `severity` — crash / broken-feature / cosmetic
No bug ⇒ note "clean: <what was exercised>" so coverage is auditable.

## 5. Restart trigger + handoff

The server holds Python state in memory; merged fixes only take effect after a
restart. When **enough fixes have merged to matter** (rule of thumb: ~3–5 merged
fixes, or any fix to server/engine/stage code, or the app gets wedged), do a
**clean cycle**:

1. Stop driving; let in-flight fix subagents finish + merge.
2. Kill the server process.
3. **Flush the journal first.** Make sure every probe from this session has its
   row in `output/qa-runs/QA-JOURNAL.md` — that table, not your context, is what
   survives the handoff. Then post a short status (bugs found, cards filed, fixes
   merged, areas still uncovered) and re-invoke this skill from a clean context (a
   new `/qa-bot`, or `/loop /qa-bot` for unattended cycles). A fresh orchestrator
   avoids context rot across long sessions.
4. The new orchestrator pulls master (picking up the merged fixes), **reads the
   journal**, reboots `serve --debug`, and resumes the loop on areas the journal
   does **not** yet cover. It does **not** re-check the just-merged fixes on its
   own — confirming a fix is a re-test, which only happens when the user asks.

## 6. Stop conditions

- The user says stop.
- A full rotation of the probe checklist comes back clean (no new confirmed
  bugs) — report "QA pass clean" with the coverage list and stop.
- The harness itself is broken (debug panel/endpoints failing) — that's a bug in
  *this* feature; file it and stop rather than QA-ing blind.

## Etiquette

- One browser driver at a time. Respect the AI mutex — a 409 busy is the app
  working correctly, not a bug.
- Keep QA projects under `output/qa-runs/` (the debug endpoints already do).
  Never QA against the user's real golden project — seed-stage clones it.
- Every bug becomes a Trello card *before* you spawn its fixer, so nothing is
  lost if a fixer fails.
