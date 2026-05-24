# MTG AI Set Creator — Progress Tracker (DEPRECATED)

> **Deprecated 2026-05-24.** Task tracking has moved to the Trello board:
> [MTGAI](https://trello.com/b/Am3RvaZM) (id `69f86a83`, lists `To Do` → `Doing` → `Done`).
> Per-card scratch trackers (`plans/tracker_<branch>.md`) and the runbook in
> `CONTRIBUTING.md` are unaffected — only this project-wide master tracker is retired.

This file used to be the master progress log (Execution Protocol, per-phase task
checklists for Phases 0A–TC/SC/5, session notes, and a deferred-improvements appendix).
That history is preserved in git — to read it:

```bash
git show HEAD~1:plans/TRACKER.md          # last full version
git log --follow -p -- plans/TRACKER.md   # full history
```

The one deferred improvement that was *not* already on Trello — **token-count
calibration for local models** (tiktoken undercounts Gemma) — was migrated to its own
`infra` card on the board before this file was retired. Everything else was either a
completed phase (recoverable from git) or already tracked on Trello.

`plans/master-plan.md` still holds the project overview, decisions, and dependency graph.
