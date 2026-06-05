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
Only the *fixes* (code edits in separate worktrees) run in parallel.

This skill assumes the Part-A debug harness exists (it ships with the QA Bot
card): `serve --debug`, the floating 🐛 QA Debug panel, and the
`/api/debug/*` endpoints. See `reference.md` for the endpoint + probe-area
cheatsheet.

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

1. **Pick the next probe area** from the checklist in `reference.md` (rotate so
   coverage stays broad: project settings → theme → mechanics → skeleton →
   card_gen → gates → ai_review → finalize → art/render tabs → cross-cutting
   like cancel-mid-run, tab-switch, edit-past-stage, bad input).

2. **Spawn a QA probe subagent** (fresh context) for that ONE area. Give it:
   - the area + the exact tab URL,
   - the claude-in-chrome tools to use,
   - the adversarial brief: *click every control, feed empty/huge/weird input,
     double-click, cancel mid-run, switch tabs mid-run, edit a past stage,
     reload mid-action, hit endpoints out of order* — try to break it,
   - the **bug report contract** (§4): report back ONLY confirmed bugs, each
     with repro steps, expected vs actual, console errors
     (`read_console_messages`), failing network calls (`read_network_requests`),
     and a screenshot.
   Because the app is serial, run probes **one at a time** — never two browser
   drivers at once.

3. **Triage each reported bug.** Confirm it's real and not test-harness noise
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

6. **Keep driving.** Don't wait for fixes to land before the next probe —
   queue them and continue QA. Track how many fixes have merged.

## 4. Bug report contract (probe → orchestrator)

A probe reports a JSON-ish list of confirmed bugs. Each:
- `title` — short imperative ("Skeleton refresh 500s on empty knobs")
- `area` / `tab`
- `repro` — numbered steps a cold reader can replay
- `expected` vs `actual`
- `console` — relevant console errors (verbatim)
- `network` — any 4xx/5xx the action caused (method + path + status)
- `screenshot` — path/ref
- `severity` — crash / broken-feature / cosmetic
No bug ⇒ report "clean: <what was exercised>" so coverage is auditable.

## 5. Restart trigger + handoff

The server holds Python state in memory; merged fixes only take effect after a
restart. When **enough fixes have merged to matter** (rule of thumb: ~3–5 merged
fixes, or any fix to server/engine/stage code, or the app gets wedged), do a
**clean cycle**:

1. Stop driving; let in-flight fix subagents finish + merge.
2. Kill the server process.
3. **Hand off to a fresh orchestrator**: post a short status (bugs found, cards
   filed, fixes merged, areas still uncovered) and re-invoke this skill from a
   clean context (a new `/qa-bot`, or `/loop /qa-bot` for unattended cycles).
   A fresh orchestrator avoids context rot across long sessions.
4. The new orchestrator pulls master (picking up the merged fixes), reboots
   `serve --debug`, and resumes the loop — prioritising areas the prior session
   left uncovered + re-checking the bugs that were just fixed.

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
