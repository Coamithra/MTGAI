# Tracker: fix/mechanic-council-strictness

Card: [Investigate & iterate on mechanic council review strategy (0% pass rate)](https://trello.com/c/9folYC0O) (id `6a1a9fa9`)
Scope (user-chosen): **Minimal (1–3)** — soften reviewer prompt, cut taste categories, majority exit. Defer synth/generation/dedup to follow-up cards.

## Phase 1: Pick up
- [x] Pull latest master
- [x] Read card + research/mechanic-council-strictness README + logs
- [x] Move card to Doing
- [x] Create worktree + branch
- [x] Tracker doc

## Phase 2: Research (done)
- Parsed 108 reviewer calls / 408 issues: unique(95)+interesting(93) = over-strict taste noise; wording(86)+self_consistent(72)+some playable = legit "broken" flags.
- Exit `all_ok = all(verdict==OK)` never fires at 0% OK rate.

## Phase 3: Design (user-aligned)
Council becomes an "is it broken?" gate, not "is it excellent?":
1. Reviewer prompt → workable-not-broken framing; explicit do-not-reject list.
2. `MECHANIC_ISSUE_CATEGORIES`: drop `interesting`+`unique`; add `BLOCKING_CATEGORIES`={playable,wording,self_consistent,other}; `elegant` advisory.
3. Exit: majority of *effective* OK (REVISE only counts if it cites a blocking defect).

## Phase 4: Implement
- [x] Rewrite `mechanic_review_system.txt` + `mechanic_review_user.txt`
- [x] `MECHANIC_ISSUE_CATEGORIES` (drop interesting/unique) + `MECHANIC_BLOCKING_CATEGORIES`
- [x] `_effective_verdict` + majority exit in `council_review`
- [x] Filter `_open_issue_reasons` to blocking categories
- [x] Update tests (majority pass, advisory-only soft pass, effective-verdict; fix interesting-category tests)
- [x] Update CLAUDE.md council contract

## Phase 5: Verify
- [x] ruff check / format clean
- [x] python -c import mtgai
- [x] pytest full suite: 1441 passed
- [ ] Flag: live local-Gemma mechanics run for real pass-rate validation (not unit-testable)

## Phase 6: Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] Pull master, merge, cleanup
- [ ] Move card to Done + comment
- [ ] Create follow-up cards for synth(4) / generation-source(5) / dedup(6)
