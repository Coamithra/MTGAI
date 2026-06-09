"""Pipeline engine — executes stages sequentially with pause/resume support.

The engine runs in a background thread (via asyncio.to_thread) so the
FastAPI event loop stays responsive. It publishes events to an EventBus
for real-time SSE streaming to the dashboard.

State is persisted to disk after every stage transition for crash recovery.
"""

from __future__ import annotations

import json
import logging
import threading
import time as _time
import traceback
from datetime import UTC, datetime
from pathlib import Path

from mtgai.pipeline.events import EventBus, StageEmitter
from mtgai.pipeline.models import (
    STAGE_DEFINITIONS,
    PipelineState,
    PipelineStatus,
    ProgressCallback,
    StageProgress,
    StageReviewMode,
    StageState,
    StageStatus,
    make_instance_id,
)
from mtgai.pipeline.stages import STAGE_RUNNERS, StageResult
from mtgai.runtime import ai_lock

logger = logging.getLogger(__name__)

# Review→regen loop caps, *per gate*. A gate (conformance / ai_review) that
# flags cards bounces the pipeline to ``card_gen`` for another round; these cap
# how many generation rounds the *automatic* loop runs for each gate before it
# gives up and accepts the still-flagged cards as-is. The budgets are SEPARATE
# so conformance churn (fixing early conformance/interaction flaws) cannot
# starve the later council (ai_review) of its own regen rounds: without a
# per-gate split, a card that burned the whole shared budget on conformance
# fixes would reach the council with nothing left, and a genuine council flag
# would be silently accepted as-is.
#
# Counting (derived from the plan, no stored counter): every bounce — from
# either gate — inserts exactly one ``card_gen`` and one ``conformance``
# instance (their spans both start at card_gen and reach at least conformance);
# only an ``ai_review`` bounce additionally inserts an ``ai_review`` instance.
# So, with N_x = number of instances of stage x:
#   ai_review regen rounds   = N_ai_review - 1
#   conformance regen rounds = N_card_gen - N_ai_review
# Each is compared to its own budget below. Total card_gen is bounded by
# 1 + MAX_REGEN_ROUNDS + MAX_AI_REVIEW_REGEN, so the loop still always finishes.
#
# These are safety valves against a never-conforming card looping forever, NOT
# quality targets: most sets settle in 0-2 rounds per gate.
MAX_REGEN_ROUNDS = 5  # conformance & interactions gate
MAX_AI_REVIEW_REGEN = 2  # design-review council → 3 total council passes


def _state_path() -> Path:
    """Where ``pipeline-state.json`` lives for the active project.

    Routes through :func:`set_artifact_dir` so the file lands in the
    user's configured ``asset_folder``. Raises
    :class:`NoAssetFolderError` if no project is open or the asset
    folder isn't set; the engine never reaches this path without an
    active project, so a raise is the right signal at the boundary.
    """
    from mtgai.io.asset_paths import set_artifact_dir

    return set_artifact_dir() / "pipeline-state.json"


def save_state(state: PipelineState) -> None:
    """Persist pipeline state to disk.

    Atomic write (temp file + retrying ``os.replace``) via
    :func:`mtgai.io.atomic.atomic_write_text` so concurrent readers (e.g. a
    wizard route hitting load_state mid-save) never see a truncated file, and
    a transient Windows lock on the temp file (Defender's on-access scanner,
    the search indexer, a sync client) is retried instead of crashing the
    engine thread. Plain ``write_text`` gives neither guarantee.
    """
    from mtgai.io.atomic import atomic_write_text

    state.updated_at = datetime.now(UTC)
    payload = json.dumps(state.model_dump(mode="json"), indent=2, default=str)
    atomic_write_text(_state_path(), payload)


def load_state() -> PipelineState | None:
    """Load pipeline state from disk for the active project, or None if not found.

    Reconciles the on-disk ``stages`` list against the current
    :data:`STAGE_DEFINITIONS` — both membership and order — so projects
    whose ``pipeline-state.json`` predates a newly-added stage *or* a
    stage reorder still load with a complete, canonically-ordered stage
    list. Missing stages are inserted as PENDING and existing ones are
    moved to their canonical position so the engine runs them in the
    right order on next advance — a graceful upgrade for old projects
    without bespoke per-stage migration logic.
    """
    path = _state_path()
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    state = PipelineState.model_validate(data)
    _sync_stages_with_definitions(state)
    return state


def _sync_stages_with_definitions(state: PipelineState) -> bool:
    """Reconcile ``state.stages`` with STAGE_DEFINITIONS — order *and* membership.

    Mutates ``state`` in place. Reconciles the **backbone** (the one
    ``instance_id == stage_id`` instance of each definition) into canonical
    STAGE_DEFINITIONS order, preserving each existing backbone's persisted
    progress / review_mode and inserting a fresh PENDING ``StageState`` for any
    missing one; backbone stages no longer in STAGE_DEFINITIONS are dropped.

    **Dynamically-inserted instances are preserved.** The review→regen loop
    appends repeated instances (e.g. ``card_gen.2``/``balance.2``) right after
    the backbone stage that flagged them. Those non-backbone instances are kept
    in place relative to the nearest preceding backbone they trail, so a state
    with duplicates round-trips through ``load_state()`` unchanged. (The old
    implementation rebuilt from a ``{stage_id: stage}`` dict, which silently
    destroyed every duplicate on reload.)

    Returns True if anything changed (a stage was added, dropped, or moved),
    False if the loaded state already matched canonically — callers (e.g.
    ``cleanup_orphan_running_stages``) use this to decide whether to persist the
    synced shape, so a clean state's bytes stay untouched.
    """
    canonical_set = {d["stage_id"] for d in STAGE_DEFINITIONS}

    # Existing backbone instances, by stage_id (preserves progress/review_mode).
    existing_backbone = {s.stage_id: s for s in state.stages if s.instance_id == s.stage_id}

    # Group inserted (non-backbone) instances under the stage_id of the nearest
    # preceding backbone in the existing order, preserving their relative order.
    # Inserts whose stage_id is no longer canonical are dropped along with their
    # vanished backbone.
    inserts_after: dict[str, list[StageState]] = {}
    leading_inserts: list[StageState] = []
    anchor: str | None = None
    for s in state.stages:
        if s.instance_id == s.stage_id:
            anchor = s.stage_id
        elif s.stage_id in canonical_set:
            if anchor is None:
                leading_inserts.append(s)
            else:
                inserts_after.setdefault(anchor, []).append(s)

    new_stages: list[StageState] = list(leading_inserts)
    for defn in STAGE_DEFINITIONS:
        sid = defn["stage_id"]
        backbone = existing_backbone.get(sid)
        if backbone is not None:
            new_stages.append(backbone)
        else:
            new_stages.append(
                StageState(
                    stage_id=sid,
                    display_name=defn["display_name"],
                    review_eligible=defn["review_eligible"],
                    status=StageStatus.PENDING,
                )
            )
        new_stages.extend(inserts_after.get(sid, []))

    if [s.instance_id for s in new_stages] == [s.instance_id for s in state.stages]:
        return False
    state.stages = new_stages
    return True


def cleanup_orphan_running_stages() -> list[str]:
    """Demote any persisted ``RUNNING`` stage to ``FAILED`` for the active project.

    Called from ``/api/project/{open,materialize}`` once the
    active-project pointer is set, so :func:`set_artifact_dir` resolves
    cleanly. Reads the freshly-opened project's ``pipeline-state.json``,
    flips any ``RUNNING`` stage left over from a crashed prior process
    to ``FAILED``, and writes the file back. Returns a list of
    ``"<set_code>:<stage_id>"`` strings that were demoted, mainly for
    logging.

    Returns ``[]`` when no project is open, no ``asset_folder`` is set,
    or no ``pipeline-state.json`` exists yet — none of those are error
    states.
    """
    from mtgai.io.asset_paths import NoAssetFolderError

    try:
        state_path = _state_path()
    except NoAssetFolderError:
        return []
    if not state_path.exists():
        return []

    try:
        state = PipelineState.model_validate_json(state_path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("cleanup_orphan_running_stages: failed to load %s", state_path)
        return []
    # ``load_state`` would also sync, but we read the file directly so we
    # can tell whether syncing changed anything (the test contract is
    # "leave a clean state's bytes alone"). Track migration as one of
    # the change conditions below.
    synced = _sync_stages_with_definitions(state)

    demoted: list[str] = []
    now = datetime.now(UTC)
    changed = synced
    for stage in state.stages:
        if stage.status == StageStatus.RUNNING:
            stage.status = StageStatus.FAILED
            stage.progress.error_message = "Interrupted — server restart"
            stage.progress.finished_at = now
            demoted.append(f"{state.config.set_code}:{stage.stage_id}")
            changed = True

    if state.overall_status == PipelineStatus.RUNNING:
        state.overall_status = PipelineStatus.FAILED
        changed = True

    if changed:
        state.updated_at = now
        save_state(state)

    if demoted:
        logger.warning(
            "Previous run likely died while %d stage(s) were RUNNING (silent crash / "
            "restart) — demoted to FAILED on project open: %s. Use 'Retry this step' to resume.",
            len(demoted),
            ", ".join(demoted),
        )
    return demoted


class PipelineEngine:
    """Executes pipeline stages sequentially with pause/resume/cancel."""

    def __init__(self, state: PipelineState, event_bus: EventBus) -> None:
        self.state = state
        self.bus = event_bus
        self._cancel_event = threading.Event()
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def cancel(self) -> None:
        """Request cancellation. The engine checks this between stages."""
        self._cancel_event.set()
        logger.info("Pipeline cancellation requested")

    def run(self) -> None:
        """Main loop — advance through stages sequentially.

        This runs in a background thread. It stops when:
        - All stages are complete
        - A stage fails
        - A stage is set to review mode (pauses for human review)
        - cancel() is called
        """
        self._running = True
        self.state.overall_status = PipelineStatus.RUNNING
        save_state(self.state)
        self.bus.pipeline_status(self.state.overall_status, self.state.current_instance_id)

        try:
            self._run_loop()
        except Exception:
            logger.exception("Pipeline engine crashed")
            self.state.overall_status = PipelineStatus.FAILED
            save_state(self.state)
            self.bus.pipeline_status(self.state.overall_status, self.state.current_instance_id)
        finally:
            self._running = False

    def _run_loop(self) -> None:
        # Index-driven walk (not ``for stage in …``) so the review→regen loop
        # can *insert* repeated stage instances after the current index and have
        # them picked up on the next iteration. ``len()`` is re-read each pass.
        i = 0
        while i < len(self.state.stages):
            stage = self.state.stages[i]

            # Check cancellation
            if self._cancel_event.is_set():
                self.state.overall_status = PipelineStatus.CANCELLED
                save_state(self.state)
                self.bus.pipeline_status(self.state.overall_status, self.state.current_instance_id)
                logger.info("Pipeline cancelled")
                return

            # Skip completed/skipped stages
            if stage.status in (StageStatus.COMPLETED, StageStatus.SKIPPED):
                i += 1
                continue

            # Run the stage. Stamp this instance's entry-pool pointer (its
            # immediate predecessor's output snapshot) so a later manual re-run
            # restores the right card pool before walking forward from here.
            stage.entry_snapshot_id = self.state.stages[i - 1].instance_id if i > 0 else None
            self.state.current_instance_id = stage.instance_id
            stage.status = StageStatus.RUNNING
            stage.progress = StageProgress(started_at=datetime.now(UTC))
            save_state(self.state)
            self.bus.stage_update(
                stage.stage_id,
                stage.status,
                stage.progress.model_dump(mode="json"),
                instance_id=stage.instance_id,
            )
            logger.info("Starting stage: %s", stage.display_name)

            # Build progress callback + section emitter for this stage
            progress_cb = self._make_progress_callback(stage)
            emitter = StageEmitter(
                self.bus, stage.stage_id, _time.monotonic(), instance_id=stage.instance_id
            )
            emitter.phase(
                "starting",
                f"Starting {stage.display_name}",
            )

            # Execute the stage runner
            try:
                runner = STAGE_RUNNERS.get(stage.stage_id)
                if runner is None:
                    raise ValueError(f"No runner registered for stage: {stage.stage_id}")

                result: StageResult = runner(progress_cb, emitter)

                if not result.success:
                    raise RuntimeError(result.error_message or "Stage failed")

                # Update stage progress from result
                stage.progress.total_items = result.total_items
                stage.progress.completed_items = result.completed_items
                stage.progress.failed_items = result.failed_items
                stage.progress.cost_usd = result.cost_usd
                stage.progress.detail = result.detail
                stage.progress.finished_at = datetime.now(UTC)
                # Persist this instance's runner output so its tab can render
                # what it found even after a later card_gen clears card flags.
                stage.result = result.artifacts or {}

                # Reconcile (don't accumulate) the run total. ``result.cost_usd``
                # is the stage's authoritative final cost — set verbatim into
                # ``stage.progress.cost_usd`` just above — and for several stages
                # (card_gen, ai_review, art_prompts, art_gen) it is the SAME total
                # that already flowed through ``_make_progress_callback`` per item
                # during the run. Adding it here would double-count those stages
                # (and on a resumed card_gen, re-add the prior run's persisted
                # cost the callbacks never re-emitted). Recomputing the total as
                # the sum of every stage's authoritative ``progress.cost_usd`` is
                # idempotent and immune to both: each stage is counted exactly once
                # at its final value. (See ``_recompute_total_cost``.)
                self._recompute_total_cost()
                self.bus.cost_update(result.cost_usd, self.state.total_cost_usd)

            except Exception as exc:
                stage.status = StageStatus.FAILED
                stage.progress.error_message = str(exc)
                stage.progress.finished_at = datetime.now(UTC)
                self.state.overall_status = PipelineStatus.FAILED
                save_state(self.state)
                self.bus.stage_update(
                    stage.stage_id,
                    stage.status,
                    stage.progress.model_dump(mode="json"),
                    instance_id=stage.instance_id,
                )
                self.bus.pipeline_status(self.state.overall_status, stage.instance_id)
                logger.error(
                    "Stage %s failed: %s\n%s",
                    stage.display_name,
                    exc,
                    traceback.format_exc(),
                )
                return

            # Inter-stage bookkeeping runs under the AI lock. The runner just
            # released its own hold, so without a re-acquire this window is
            # lock-free and a guarded_ai endpoint (e.g. card_gen/refresh ->
            # clear_card_gen_cards) could grab the lock and mutate the live
            # cards/ folder mid-snapshot-copy or wipe the regen flags the span
            # below is inserted to consume. The hold is released before the
            # loop walks into the next stage — the next runner takes its OWN
            # hold, and the lock is strictly non-reentrant, so holding through
            # the runner call would busy-back the runner and silently skip it.
            #
            # If an endpoint won the sub-millisecond release->reacquire race
            # (interstage is None), the live pool may be mutating under us:
            # skip the snapshot rather than copy a pool in flux — the instance
            # degrades to a from-live re-run, the same best-effort contract as
            # a snapshot failure. _handle_rerun still runs either way: it
            # mutates only engine-owned in-memory state + pipeline-state.json
            # (guarded by the engine-running checks, not the AI lock), and
            # skipping it would orphan the gate's stamped flags entirely.
            with ai_lock.hold(f"Finishing {stage.display_name}") as interstage:
                if interstage is None:
                    logger.warning(
                        "Skipping card-pool snapshot for instance %s — AI lock "
                        "held by another action (re-run degrades to from-live)",
                        stage.instance_id,
                    )
                else:
                    # Per-instance card-pool snapshot: capture this instance's
                    # output (live cards/ + progress) into history/<instance_id>/
                    # so it can be re-run from its entry later and its tab can
                    # show its own pool. This single seam covers every downstream
                    # branch (rerun-insert, review pause, normal complete) since
                    # the live folder already holds the instance's output here.
                    self._snapshot_instance_output(stage)

                # A review runner that flagged cards bounces the pipeline: insert
                # fresh instances of the upstream span and walk forward into them.
                # Capped at MAX_REGEN_ROUNDS rounds (see _handle_rerun): past the
                # cap the gate completes and still-flagged cards are accepted
                # as-is.
                rerun = self._handle_rerun(result, i)
            if rerun == "inserted":
                i += 1  # walk into the freshly-inserted regen span
                continue

            # Check if human review is needed.
            #
            # A review-INELIGIBLE stage (e.g. ``lands``, ``art_prompts``) must
            # NEVER pause for review — that's its documented contract. Force its
            # review_mode to AUTO so a stale/erroneous persisted REVIEW (e.g. a
            # debug-seeded clone that carried a "review" mode from its golden
            # source) can never sneak it past the pause check below.
            #
            # A review-ELIGIBLE backbone instance re-resolves from the project's
            # LIVE break points (not the build-time-frozen review_mode) so a
            # "Stop after this step" toggled *while this stage was running*
            # takes effect on the stage that just finished. Inserted regen-loop
            # copies stay pinned to their build-time AUTO (matching
            # _build_rerun_span) so an active loop still flows.
            if not stage.review_eligible:
                stage.review_mode = StageReviewMode.AUTO
            elif stage.instance_id == stage.stage_id:
                stage.review_mode = (
                    StageReviewMode.REVIEW
                    if _live_break_point(stage.stage_id)
                    else StageReviewMode.AUTO
                )

            if stage.review_mode == StageReviewMode.REVIEW:
                stage.status = StageStatus.PAUSED_FOR_REVIEW
                self.state.overall_status = PipelineStatus.PAUSED
                save_state(self.state)
                self.bus.stage_update(
                    stage.stage_id,
                    stage.status,
                    stage.progress.model_dump(mode="json"),
                    instance_id=stage.instance_id,
                    result=stage.result,
                )
                self.bus.pipeline_status(self.state.overall_status, stage.instance_id)
                logger.info(
                    "Stage %s complete — paused for human review",
                    stage.display_name,
                )
                return  # Yield control — resume() will restart the loop

            # Stage completed without review needed
            stage.status = StageStatus.COMPLETED
            save_state(self.state)
            self.bus.stage_update(
                stage.stage_id,
                stage.status,
                stage.progress.model_dump(mode="json"),
                instance_id=stage.instance_id,
                result=stage.result,
            )
            logger.info("Stage %s completed", stage.display_name)
            i += 1

        # All stages done
        all_done = all(
            s.status in (StageStatus.COMPLETED, StageStatus.SKIPPED) for s in self.state.stages
        )
        if all_done:
            self.state.overall_status = PipelineStatus.COMPLETED
            self.state.current_instance_id = None
            save_state(self.state)
            self.bus.pipeline_status(self.state.overall_status, None)
            logger.info("Pipeline completed! Total cost: $%.2f", self.state.total_cost_usd)

    def _handle_rerun(self, result: StageResult, index: int) -> str | None:
        """Forward-only re-entrancy for a gate that flagged cards.

        When a review gate sets ``result.rerun_from`` (the upstream stage to
        bounce to — always ``card_gen``), the flagging gate is marked COMPLETED
        and a fresh PENDING instance span ``[rerun_from … this gate]``
        (canonical order, each at its next ordinal, AUTO so the loop flows) is
        inserted right after ``index``. Returns ``"inserted"`` so the walk steps
        into the regen span.

        **Round cap** (per gate — ``MAX_REGEN_ROUNDS`` for the conformance gate,
        ``MAX_AI_REVIEW_REGEN`` for the design-review council): the loop is
        capped, not infinite, and each gate spends its OWN budget so conformance
        churn can't starve the council. Once a gate has run its share of regen
        rounds, a further flag from it no longer bounces — the gate just
        completes and its still-flagged cards are accepted as-is so the pipeline
        can finish. A safety valve against a never-conforming card, not a
        quality bar.

        Returns ``None`` when there's nothing to re-run (a clean pass / non-gate
        stage) or when the cap has been hit, leaving the normal review-pause /
        complete handling to mark the gate done and walk forward.
        """
        if not result.rerun_from:
            return None

        gate = self.state.stages[index]
        gate_sid = gate.stage_id

        # Cap the review->regen loop, PER GATE (see MAX_REGEN_ROUNDS /
        # MAX_AI_REVIEW_REGEN). Each gate spends its own budget so conformance
        # churn can't starve the council. Derive each gate's rounds-so-far from
        # the plan (every bounce inserts one card_gen + one conformance; only an
        # ai_review bounce also inserts an ai_review), then compare to the cap
        # for the gate that actually flagged. Past its cap we stop looping and
        # accept the flagged cards as-is; returning None lets the caller's normal
        # "stage completed" path mark this gate done and walk forward.
        n_card_gen = sum(1 for s in self.state.stages if s.stage_id == "card_gen")
        n_ai_review = sum(1 for s in self.state.stages if s.stage_id == "ai_review")
        if gate_sid == "ai_review":
            regen_rounds, cap = n_ai_review - 1, MAX_AI_REVIEW_REGEN
        else:
            regen_rounds, cap = n_card_gen - n_ai_review, MAX_REGEN_ROUNDS
        if regen_rounds >= cap:
            logger.warning(
                "Gate %s flagged cards, but its review->regen loop hit its cap "
                "(%d rounds) -- accepting the flagged cards as-is and continuing.",
                gate.display_name,
                cap,
            )
            return None

        # Mark the flagging gate complete, then insert the regen span after it.
        gate.status = StageStatus.COMPLETED
        save_state(self.state)
        self.bus.stage_update(
            gate.stage_id,
            gate.status,
            gate.progress.model_dump(mode="json"),
            instance_id=gate.instance_id,
            result=gate.result,
        )

        span = self._build_rerun_span(result.rerun_from, gate_sid)
        self.state.stages[index + 1 : index + 1] = span
        save_state(self.state)
        logger.info(
            "Gate %s flagged cards — inserting regen span [%s]",
            gate.display_name,
            ", ".join(s.instance_id for s in span),
        )
        return "inserted"

    def _build_rerun_span(self, rerun_from: str, gate_sid: str) -> list[StageState]:
        """Fresh PENDING instances for the canonical stage span ``rerun_from..gate_sid``.

        Each gets the next free ordinal for its stage_id and an AUTO review_mode
        so the inserted span runs without pausing — only a re-flag bounces again.
        """
        canonical = [d["stage_id"] for d in STAGE_DEFINITIONS]
        defn_by_id = {d["stage_id"]: d for d in STAGE_DEFINITIONS}
        try:
            lo, hi = canonical.index(rerun_from), canonical.index(gate_sid)
        except ValueError:
            logger.error(
                "Rerun span endpoints not in STAGE_DEFINITIONS: %s..%s", rerun_from, gate_sid
            )
            return []

        span: list[StageState] = []
        for sid in canonical[lo : hi + 1]:
            defn = defn_by_id[sid]
            ordinal = sum(1 for s in self.state.stages if s.stage_id == sid) + 1
            span.append(
                StageState(
                    stage_id=sid,
                    instance_id=make_instance_id(sid, ordinal),
                    display_name=f"{defn['display_name']} {ordinal}",
                    review_eligible=defn["review_eligible"],
                    review_mode=StageReviewMode.AUTO,
                    status=StageStatus.PENDING,
                )
            )
        return span

    def resume(self) -> None:
        """Resume pipeline after human review.

        Marks the current paused stage as completed and restarts the loop.
        Should be called in a background thread (via asyncio.to_thread).
        """
        current = self.state.current_stage()
        if current is None:
            logger.warning("resume() called but no current stage")
            return
        if current.status != StageStatus.PAUSED_FOR_REVIEW:
            # The tip already completed (e.g. a project saved/reopened after a
            # review-eligible stage finished but before its successor ran), yet
            # overall_status is still PAUSED with a pending stage waiting. Don't
            # no-op into a dead-end: re-point the engine at that pending stage
            # and walk the loop forward. _run_loop skips COMPLETED stages, so a
            # plain run() picks up the first pending one from here.
            if (
                current.status in (StageStatus.COMPLETED, StageStatus.SKIPPED)
                and self.state.overall_status == PipelineStatus.PAUSED
            ):
                nxt = self.state.next_pending_stage()
                if nxt is not None:
                    logger.info(
                        "resume() from completed tip %s — advancing to pending stage %s",
                        current.stage_id,
                        nxt.stage_id,
                    )
                    self.state.current_instance_id = nxt.instance_id
                    save_state(self.state)
                    self.run()
                    return
            logger.warning(
                "resume() called but current stage %s is %s, not paused",
                current.stage_id,
                current.status,
            )
            return

        current.status = StageStatus.COMPLETED
        current.progress.finished_at = datetime.now(UTC)
        save_state(self.state)
        self.bus.stage_update(
            current.stage_id,
            current.status,
            current.progress.model_dump(mode="json"),
            instance_id=current.instance_id,
        )
        logger.info("Resumed pipeline after review of %s", current.display_name)

        # Continue with the next stages
        self.run()

    def retry_current(self) -> None:
        """Retry the current failed stage.

        Resets the stage to PENDING and restarts the loop.
        Should be called in a background thread.
        """
        current = self.state.current_stage()
        if current is None or current.status != StageStatus.FAILED:
            logger.warning("retry() called but no failed current stage")
            return

        current.status = StageStatus.PENDING
        current.progress = StageProgress()
        save_state(self.state)
        logger.info("Retrying stage: %s", current.display_name)

        self.run()

    def skip_current(self) -> None:
        """Skip the current paused or failed stage.

        Should be called in a background thread.
        """
        current = self.state.current_stage()
        if current is None:
            return
        if current.status not in (StageStatus.PAUSED_FOR_REVIEW, StageStatus.FAILED):
            logger.warning("skip() called but current stage is %s", current.status)
            return

        current.status = StageStatus.SKIPPED
        current.progress.finished_at = datetime.now(UTC)
        save_state(self.state)
        self.bus.stage_update(current.stage_id, current.status, instance_id=current.instance_id)
        logger.info("Skipped stage: %s", current.display_name)

        self.run()

    def _recompute_total_cost(self) -> None:
        """Set ``state.total_cost_usd`` to the sum of every stage's cost.

        The single accounting point for the run total: each stage's
        ``progress.cost_usd`` is its authoritative cost (live-accumulated by
        the progress callback, then overwritten to ``result.cost_usd`` at
        completion), so summing them counts every stage exactly once. This is
        idempotent — unlike ``+= cost`` per item *and* ``+= result.cost_usd``
        at completion, which double-counted any stage that reports per-item
        cost through the callback (card_gen, ai_review, art_prompts, art_gen)
        and re-added a resumed card_gen's persisted prior-run cost.
        """
        self.state.total_cost_usd = sum(s.progress.cost_usd for s in self.state.stages)

    def _make_progress_callback(self, stage) -> ProgressCallback:
        """Create a progress callback bound to the given stage."""

        def callback(
            item: str,
            completed: int,
            total: int,
            detail: str,
            cost: float,
        ) -> None:
            stage.progress.current_item = item
            stage.progress.completed_items = completed
            stage.progress.total_items = total
            stage.progress.detail = detail
            stage.progress.cost_usd += cost

            # Keep the run total in lockstep with the per-stage costs it sums.
            # The live in-flight stage's ``progress.cost_usd`` was just bumped
            # above, so recomputing the sum (rather than mirroring the same
            # ``+= cost`` and then re-adding ``result.cost_usd`` at completion)
            # is what makes the total single-counted — see the completion path.
            self._recompute_total_cost()

            # Persist periodically (every item)
            save_state(self.state)

            # Publish SSE events
            self.bus.item_progress(
                stage.stage_id, item, completed, total, detail, instance_id=stage.instance_id
            )
            if cost > 0:
                self.bus.cost_update(stage.progress.cost_usd, self.state.total_cost_usd)

        return callback

    def _snapshot_instance_output(self, stage: StageState) -> None:
        """Snapshot a completed snapshot-eligible instance's card pool. Best-effort.

        A snapshot failure must never crash the run — the only consequence is that
        this instance can't be re-run from history (it degrades to a from-live
        re-run), so we log and continue.

        The caller (``_run_loop``'s inter-stage block) holds ``ai_lock`` while
        calling this, so no guarded_ai endpoint can mutate the live ``cards/``
        folder mid-copy — the "no concurrent writer" invariant ``history.py``
        documents. This method does not take the lock itself.
        """
        from mtgai.pipeline import history

        if stage.stage_id not in history.SNAPSHOT_STAGES:
            return
        try:
            history.snapshot_instance(stage.instance_id)
        except Exception:
            logger.exception(
                "Card-pool snapshot for instance %s failed (continuing)", stage.instance_id
            )


def _live_break_point(stage_id: str) -> bool:
    """Whether the wizard should pause after ``stage_id`` per the project's *live* settings.

    Reads the active project's current ``break_points`` (kept in sync by
    ``apply_settings`` -> ``write_active_project``), so a "Stop after this step"
    toggled mid-run is honoured at the engine's pause decision instead of the
    review_mode frozen onto the stage at build time. No open project (e.g. a
    bare test harness) falls back to the stage defaults via ``_resolve_break_point``.
    """
    from mtgai.pipeline.models import _resolve_break_point
    from mtgai.runtime.active_project import read_active_project

    project = read_active_project()
    break_points = project.settings.break_points if project is not None else {}
    return _resolve_break_point(stage_id, break_points)


def _build_forward_path(state: PipelineState, after_stage_id: str) -> list[StageState]:
    """Fresh PENDING instances for every canonical stage strictly after ``after_stage_id``.

    The forward mirror of :meth:`PipelineEngine._build_rerun_span` (which builds the
    *backward* slice ``rerun_from..gate``). Each new instance gets the next free
    ordinal for its stage_id via :func:`make_instance_id` — a stage with a surviving
    earlier sibling becomes ``conformance.2`` while one with none becomes the backbone
    ``ai_review`` — which is what re-establishes the gate that must *follow* a
    regenerated loop instance. The duplicable loop stages stay AUTO so the regen tail
    flows (matching the engine's own insert span); post-loop stages honour the
    project's break points so human-review pauses still fire.
    """
    from mtgai.pipeline import history
    from mtgai.pipeline.models import _resolve_break_point
    from mtgai.runtime.active_project import read_active_project

    project = read_active_project()
    break_points = project.settings.break_points if project is not None else {}

    canonical = [d["stage_id"] for d in STAGE_DEFINITIONS]
    defn_by_id = {d["stage_id"]: d for d in STAGE_DEFINITIONS}
    try:
        start = canonical.index(after_stage_id) + 1
    except ValueError:
        logger.error("Forward-path anchor %s not in STAGE_DEFINITIONS", after_stage_id)
        return []

    path: list[StageState] = []
    for sid in canonical[start:]:
        defn = defn_by_id[sid]
        ordinal = sum(1 for s in state.stages if s.stage_id == sid) + 1
        if sid in history.RERUNNABLE_STAGES:
            review_mode = StageReviewMode.AUTO
        else:
            review_mode = (
                StageReviewMode.REVIEW
                if _resolve_break_point(sid, break_points)
                else StageReviewMode.AUTO
            )
        display = defn["display_name"] if ordinal <= 1 else f"{defn['display_name']} {ordinal}"
        path.append(
            StageState(
                stage_id=sid,
                instance_id=make_instance_id(sid, ordinal),
                display_name=display,
                review_eligible=defn["review_eligible"],
                review_mode=review_mode,
                status=StageStatus.PENDING,
            )
        )
    return path


def rerun_instance(state: PipelineState, instance_id: str) -> str | None:
    """Reset the pipeline to re-run instance ``instance_id`` from its entry pool.

    The forward mirror of the engine's review->regen insertion, and the generalized
    form of the wizard edit-cascade. Mutates ``state`` in place + touches the
    filesystem (snapshot restore + history truncation), then leaves the engine to be
    kicked by the caller — it walks forward from the reset instance exactly as a
    normal run, so a re-flag inserts a fresh span as usual. Must run under the AI
    lock with no engine running.

    Steps (uniform for any duplicable instance):

    1. Restore the entry card pool — the predecessor instance's output snapshot. The
       snapshot already encodes the correct flag/content state, so no manual flag
       fix-up is needed. A missing snapshot (migration) degrades to a from-live run.
    2. Truncate: drop every stage after the target + delete their history snapshots.
    3. Reset the target to PENDING (clear result/progress) + drop its own snapshot
       (it re-emits on completion).
    4. Re-append the canonical forward path as fresh PENDING instances.
    5. Point ``current_instance_id`` at the target + set ``NOT_STARTED`` so kickoff
       runs it.

    Returns the restored entry snapshot id (or ``None`` when there was no predecessor
    / no snapshot). Raises ``ValueError`` if the instance isn't found.
    """
    from mtgai.pipeline import history

    idx = next((i for i, s in enumerate(state.stages) if s.instance_id == instance_id), None)
    if idx is None:
        raise ValueError(f"Unknown instance id {instance_id!r}")
    target = state.stages[idx]

    # 1. Restore entry state from the predecessor's output snapshot.
    entry_id = target.entry_snapshot_id
    if entry_id is None and idx > 0:
        entry_id = state.stages[idx - 1].instance_id
    if entry_id is not None and not history.restore_snapshot(entry_id):
        logger.warning(
            "Re-run %s: entry snapshot %s missing — running from live cards",
            instance_id,
            entry_id,
        )

    # 2. Truncate downstream (state + history).
    for s in state.stages[idx + 1 :]:
        history.delete_snapshot(s.instance_id)
    del state.stages[idx + 1 :]

    # 3. Reset the target itself.
    history.delete_snapshot(target.instance_id)
    target.status = StageStatus.PENDING
    target.progress = StageProgress()
    target.result = {}

    # 4. Re-append the canonical forward path.
    state.stages.extend(_build_forward_path(state, target.stage_id))

    # 5. Aim the engine at the reset instance.
    state.current_instance_id = target.instance_id
    state.overall_status = PipelineStatus.NOT_STARTED
    save_state(state)
    logger.info(
        "Re-run %s: entry=%s, re-appended forward path [%s]",
        instance_id,
        entry_id,
        ", ".join(s.instance_id for s in state.stages[idx + 1 :]),
    )
    return entry_id
