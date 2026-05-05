# Contributing: Tackling a Trello Card

Step-by-step workflow for picking up and completing any card from the [MTGAI Trello board](https://trello.com/b/Am3RvaZM) (board id `69f86a83`).

---

## Before You Start: Create a Tracker Doc

**This is mandatory.** Before doing anything else, create a file `plans/tracker_<branch>.md` with every step from this runbook as a checkbox list. Example:

```markdown
# Tracker: fix/some-bug

## Phase 1: Pick Up the Card
- [ ] Pull latest master
- [ ] Read the card (description, comments, linked plan)
- [ ] Move card to Doing
- [ ] Create worktree and branch

## Phase 2: Research
- [ ] Read the referenced code
- [ ] Trace the call chain
...
```

Check off each step as you complete it. This is your source of truth for progress — if you get interrupted or context is lost, the tracker tells you exactly where you left off. Delete the tracker file after the card is shipped.

---

## Worktree Quick Reference

All work happens in an isolated **git worktree** under `.trees/` (gitignored). This lets multiple agents work on different cards simultaneously without interfering with each other. The root checkout stays on `master` — never switch it to a feature branch.

| Command | What it does |
|---------|-------------|
| `git worktree add .trees/<name> -b <branch> master` | Create a new worktree + branch from master |
| `git worktree list` | Show all active worktrees |
| `git worktree remove .trees/<name>` | Remove a worktree (clean up) |
| `git worktree prune` | Clean up stale worktree references |

**Key rules:**
- Each worktree gets its own branch; a branch can only be checked out in one worktree at a time
- Gitignored files (`.env`, `backend/.venv/`, `output/`, `backend/.llmfacade/`) do NOT exist in new worktrees — recreate them manually if needed for local testing (provider API keys, llamacpp swap state, generated cards)
- All worktree directories live under `.trees/` (gitignored at repo root)

---

## Phase 1: Pick Up the Card

1. **Pull latest master** — `git pull origin master` so you start from the newest code
2. **Read the card** — Read the card description and any linked spec under `plans/<file>.md`. The plan is the long-form source of truth; the card is a pointer
3. **Move card to Doing** — `trello --board 69f86a83 card move <card_id> Doing`
4. **Create worktree and branch** — Branch off `master` with a descriptive prefix:
    - Bugs: `fix/<short-name>` (e.g. `fix/theme-extractor-loop`)
    - Features: `feat/<short-name>` (e.g. `feat/archetype-stage`)
    - Refactoring: `refactor/<short-name>`
    - Docs / plans only: `docs/<short-name>`
    ```
    git worktree add .trees/<branch> -b <branch> master
    cd .trees/<branch>
    git push -u origin <branch>
    ```
5. **All subsequent work happens inside `.trees/<branch>/`**

## Phase 2: Research

Dig into the problem before proposing solutions. Use `/research` for topics that need external context (e.g. Scryfall schema details, llama.cpp endpoint contracts, Pydantic v2 quirks, ComfyUI workflow internals).

6. **Read the referenced code** — Card descriptions and `plans/*.md` cite specific files and line numbers. Read them — descriptions can drift
7. **Trace the call chain** — For bugs, trace how the problematic code gets invoked. For features, trace the existing system the feature plugs into (the pipeline stages in `mtgai/pipeline/stages.py` are the orchestration spine; the validation cascade in `mtgai/validation/__init__.py` is the auto-fix spine; `mtgai/generation/llm_client.py` is the unified provider entry point — all documented in `CLAUDE.md`)
8. **Identify the blast radius** — Which pipeline stages does this touch? Which validators / fixers does it interact with? Does it change card schema, mechanic definitions, or the model registry? Cross-check `models.toml`, validator registry, reminder injector heuristics, and pipeline stage registry if you're adding fields
9. **Research unknowns** — Use `/research` for anything that needs external knowledge: Scryfall conventions, MTG comprehensive rules, Anthropic SDK contract details, llama.cpp / llmfacade behaviour, Flux / ComfyUI quirks
10. **Summarize findings** — Brief writeup of what you learned: root cause (bugs), design options (features), or risk areas (refactors). Becomes input to the design phase

## Phase 3: Design

11. **Draft the approach** — Either update the existing `plans/<file>.md` or write one. Include:
    - **Context**: what the card is about and why it matters
    - **Design**: file-by-file changes; new public API; new validators / fixers / pipeline stages; new models in `models.toml`
    - **Tests**: which test files get new tests, with names (validation tests are the most important category — see `tests/test_validation/`)
    - **Out of scope**: what you're explicitly *not* doing
12. **Check for reusable patterns** — Look for existing utilities and conventions before inventing new ones (e.g. validator + auto-fixer pairs, `card.model_copy(update={...})` for immutable updates, `ModelSettings.from_preset(...)`, `EventBus` for SSE, `_make_card(**overrides)` test helper, `_resolve_provider(model_id)` for routing)
13. **Align with the user** — Present the plan, get approval before writing code

## Phase 4: Implement

14. **Make the changes** — Edit files per the approved plan. Follow project conventions:
    - **Python 3.12+, managed with uv.** Always use `python` (not `python3`). Set `PYTHONIOENCODING=utf-8` when running Python directly
    - **Style**: Ruff with isort import sorting; line length 100; full type annotations; snake_case throughout
    - **Data models**: Pydantic v2 (`BaseModel`); `StrEnum` for enumerations; `X | Y` union syntax (not `Union[X, Y]`); `list[X]` (not `List[X]`)
    - **Field naming**: match Scryfall's API where applicable (`oracle_text`, not `rules_text`)
    - **Cards are immutable** — fixers and reviewers return new instances via `card.model_copy(update={...})`
    - **All commands run from `backend/`** — `ruff check .`, `ruff format .`, `pytest`, `python -m mtgai.*`
    - **Comments**: default to none; only add when the *why* is non-obvious. Don't narrate what the code does; identifiers handle that
15. **Document new conventions** — Update `CLAUDE.md` if the change introduces new pipeline stages, new validators / fixers, new model registry fields, new CLI entry points, or modifies a documented contract. CLAUDE.md is the source of truth

## Phase 5: Verify

16. **Lint** — From `backend/`: `ruff check .` and `ruff format .` must be clean
17. **Smoke import** — `python -c "import mtgai"` to catch syntax errors and broken imports
18. **Run unit tests** — From `backend/`: `pytest`. Single-test invocation: `pytest tests/test_validation/test_validators.py::test_xyz`. Validation tests are the most-protected category — never let them regress
19. **Manual smoke for pipeline / LLM / art changes** — Unit tests don't cover everything:
    - Pipeline / dashboard changes: `python -m mtgai.review serve --open` and walk the affected stage
    - LLM client / theme extractor changes: a real `generate_with_tool(...)` round-trip on a small model, or a theme extraction on a known corpus; check `output/extraction_logs/` for the per-call meta sidecars
    - Renderer / art changes: render one card via `python -m mtgai.rendering --set ASD --card <id> --force` and eyeball the PNG
    - Validation / finalize changes: `python -m mtgai.review finalize --dry-run --set ASD`
    - Document the steps in the plan's "Verification" section
20. **Spot-check the diff** — Read through one more time for typos, off-by-ones, missing `await`, dict keys that don't exist, and `# removed` / dead-code residue
21. **Flag what needs manual testing** — Leave a note for the user of anything that can't be unit-tested (e.g. "verify the new mechanic renders correctly with reminder text on a sample card")

## Phase 6: Review & Ship

22. **Commit** — Descriptive message in the project's existing style (imperative, single-line subject, body explains *why* not *what*). Reference the card if useful. Push to the feature branch
23. **Peer review** — Run `/review` (spawns a fresh agent against the branch diff vs `master` with no prior context). It catches logic errors, missed edge cases, convention violations, naming issues we've gone blind to. Fix every finding before proceeding — even minor ones — unless the fix is a major undertaking (in which case track it as a follow-up card)
24. **Pull master into the branch** — `git pull origin master` to pick up anything that landed while you were working. Resolve conflicts using the rules below

### Merge Conflict Rules

24.1. **Default to master's version.** If a conflict is in code you didn't intentionally change, accept master's side. Someone else fixed a bug or added a feature — don't silently revert their work
24.2. **Assume incoming changes are important.** Treat every conflict as "master has a critical fix" until you've read the diff and confirmed otherwise. Be very careful about overwriting new code with your version
24.3. **Only keep your side for lines you specifically wrote.** If you changed a function and master also changed it, read both versions carefully. Merge surgically — keep their fixes, layer your feature on top
24.4. **If the merge is messy, restart from master.** When conflicts are widespread or hard to reason about, it's safer to take master wholesale and reimplement your changes on top. A clean re-apply is better than a botched merge
24.5. **Re-read the final result.** After resolving, read through every conflicted file in full. Make sure the merged code actually makes sense — don't just trust the conflict markers

25. **Re-run lint + unit tests** — Make sure the merge didn't break anything. From `backend/`: `ruff check .`, `pytest`
26. **Return to the root checkout** — `cd` back to the project root (where `master` is checked out). Remaining steps run from here
27. **Merge to master** — `git merge <branch> && git push`
28. **Clean up the worktree and branch**
    ```
    git worktree remove .trees/<branch>
    git worktree prune
    git branch -d <branch>
    git push origin --delete <branch>
    ```
29. **Delete the plan + tracker files** — If the card has a `plans/<file>.md` behind it, delete it now (`git rm plans/<file>.md && git rm plans/tracker_<branch>.md && git commit -m "Remove <name> plan; <feature/fix> is implemented" && git push`). The plans directory is for *open* work only; the tracker doc is per-card scratch
30. **Move card to Done** — `trello --board 69f86a83 card move <card_id> Done`
31. **Comment on the card** — `trello --board 69f86a83 comment add <card_id> "<summary>"`. Include: what changed, which files, what it fixes/adds, the commit hash(es), and what needs manual testing. Leaves a paper trail for future debugging
32. **Create follow-up cards** — If review, implementation, or testing surfaced issues that are out of scope for this card (pre-existing bugs, minor improvements, edge cases deferred as too risky to bundle), create new Trello cards (`trello --board 69f86a83 card add "To Do" "<title>" "<desc>"`). Reference the original card so there's a trail. Don't let follow-up work disappear into commit messages — if it's worth noting, it's worth tracking
33. **Write an overview of the changes made** — As the final step, post a concise overview to the user summarizing the work: what changed (the user-facing behavior delta, not a file list), which files were touched, anything that still needs manual testing or follow-up, and the commit hash(es) and merged branch. This is the closing handoff — it's how the user picks the session up cold and knows the card is actually shipped

---

## Quick Reference: Card Categories

| Category | Key concerns |
|----------|-------------|
| **Validation / fixer bugs** | Cards are immutable Pydantic models; AUTO vs MANUAL severity; fixer must round-trip through `validate_card_from_raw`. Re-run the full `tests/test_validation/` suite |
| **Pipeline stage changes** | Touches `pipeline/stages.py`, `pipeline/engine.py`, and the SSE event contract in `pipeline/events.py`. Smoke via the dashboard at `/pipeline` |
| **LLM client / theme extractor** | Provider routing in `_resolve_provider`; cascade `provider < model < convo < per_call` for llmfacade knobs; check both Anthropic and llamacpp paths. Watch for repetition loops on Gemma |
| **Art / renderer** | High visual blast radius — always eyeball one rendered PNG. ComfyUI must be killed on exit; pycairo handles SVG symbols |
| **Model registry / settings** | New columns in `models.toml` need a mirror in `LLMModel` and threading through `_llamacpp_new_model` if launch-time |
| **Refactoring** | High blast radius across the pipeline. Run lint + full pytest, then a one-card end-to-end through the dashboard |
