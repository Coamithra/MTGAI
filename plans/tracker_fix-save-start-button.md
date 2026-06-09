# Tracker: fix/save-start-button

Card 6a285b4f — Save & Start: writeMtgFile re-renders footer mid-flow, detaching captured Start button.

## Phase 1: Pick Up
- [x] Claim card (move Doing + claim comment + 10s wait, earliest wins)
- [x] Pull master
- [x] Read card + CONTRIBUTING
- [x] Create worktree + branch
- [ ] Push branch

## Phase 2: Research
- [x] Read wizard_project.js (onSaveAndStart ~1584, writeMtgFile ~514, debug ~476)
- [x] Read CLAUDE.md Project Settings tab section
- [x] Survey writeMtgFile callers (onSaveClick relies on rerender; onSaveAndStart broken)
- [x] Pick least-invasive fix: option (b) writeMtgFile {rerender} opt

## Phase 3: Design
- [x] Draft approach (rerender opt, default true; start flow passes false)

## Phase 4: Implement
- [x] Make change

## Phase 5: Verify
- [x] node --check (SYNTAX OK)
- [x] ruff check (backend) clean
- [x] pytest (backend) 2550 passed; no llama procs spawned
- [x] smoke import OK
- [x] code-trace both paths (dirty save+start, clean start, failures, dbl-click)
- [x] file wired in wizard.html (page-serve unchanged; node --check covers JS)

## Phase 6: Ship
- [x] Commit + push
- [x] /review (self cold-review: found markClean->refreshFooterLabel re-enables
      the live btn even with rerender:false; added btn.disabled=true re-assert)
- [ ] pull master into branch
- [ ] PR + self-merge
- [ ] delete tracker before final push
- [ ] cleanup worktree + branch
- [ ] card -> Done + summary comment
