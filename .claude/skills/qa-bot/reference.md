# QA Bot — reference cheatsheet

## Debug endpoints (only mounted under `serve --debug`)

All are POST with a JSON body unless noted. The 🐛 QA Debug panel calls these;
you can also `fetch()` them from the page via `mcp__claude-in-chrome__javascript_tool`.

| Endpoint | Body | Effect |
|---|---|---|
| `GET /api/debug/state` | — | `{enabled, prefab_cards, prefab_mechanics, golden_candidates, stages, active}` |
| `POST /api/debug/quick-project` | `{set_code?, set_size?, theme_text?, prefab?}` | Create + activate a QA project (qa preset, no picker). Returns `{navigate}`. |
| `POST /api/debug/seed-stage` | `{target_stage, source_dir?}` | Clone a golden project, jump the wizard to `target_stage` (everything before it COMPLETED). Returns `{navigate}`. |
| `POST /api/debug/open-path` | `{path}` | Open a `.mtg` from a server path or a folder containing one. |
| `POST /api/debug/save-mtg` | `{}` | Write the active project's `.mtg` to its asset folder (Save bypass). |

`target_stage` is a pipeline `stage_id`: `mechanics, archetypes, skeleton,
reprints, lands, card_gen, conformance, ai_review, finalize, visual_refs,
art_prompts, char_portraits, art_gen, rendering`.

## Launch

```
git pull origin master
cd backend && python -m mtgai.review serve --debug --port 8080   # background
# open http://localhost:8080/pipeline ; confirm the 🐛 QA Debug panel
```

`--debug` sets `MTGAI_DEBUG=1`. Without it the debug router + panel don't mount.
You can also export `MTGAI_QA_GOLDEN=<path>` to force which finished project
seed-stage clones from (otherwise it auto-picks the newest under `sets (new)/`
or `output/sets/`).

## Probe-area checklist (rotate for broad coverage)

**Project Settings** — set code/size/mechanic-count bounds; preset apply/save;
model + thinking + break-point toggles; asset folder; debug toggles; Save;
required-field validation; Start with no theme.

**Theme** — upload PDF/text; section refresh; edit + accept cascade; start
extraction then cancel; empty/huge input.

**Pipeline stages** (mechanics → rendering) — for each tab: Refresh/Re-roll,
Re-pick/Re-run-this-step, per-card/per-row edit + save, pin, remove, knob panels
(out-of-range values), Save & Continue. Cancel mid-run. Switch tabs mid-run.

**Gates** (conformance, ai_review) — per-card approve/revise/regenerate; live
council stream; decisions persistence across reload.

**Cross-cutting** — cancel during every long run; double-submit (expect 409);
edit a past stage (unlock cascade + content cascade); reload mid-action;
project switch mid-run (expect 409 without force); navigate to a not-yet-visible
tab URL (expect redirect); malformed/empty endpoint bodies (expect 400, not 500).

## What is NOT a bug

- A 409 "AI busy" when you deliberately fire a second AI action — that's the
  mutex working.
- A redirect from an unreachable tab URL to the latest tab.
- Janky / low-quality generated cards — QA tests plumbing, not card quality.
- ComfyUI/Flux art steps failing when ComfyUI isn't running — out of scope;
  seed-stage gets you to the tab, running art needs the external tool.

## Bug → card → fix

1. `trello --board 69f86a83 card add "To Do" "<title>" "<repro/expected/actual/console/network>"`
2. Spawn a fix subagent: "Follow CONTRIBUTING.md end-to-end for Trello card
   <id> (full auto self-merge). Repro: <…>." It works in its own worktree.
3. Continue probing; fixes merge in parallel. Restart the server after a few
   land (see SKILL §5).
