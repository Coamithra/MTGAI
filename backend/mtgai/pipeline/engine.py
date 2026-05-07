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
)
from mtgai.pipeline.stages import STAGE_RUNNERS, StageResult

logger = logging.getLogger(__name__)


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

    Atomic write via tempfile + os.replace so concurrent readers (e.g.
    a wizard route hitting load_state mid-save) never see a truncated
    or empty file. Plain ``write_text`` truncates first, then writes —
    that gap can race a reader and produce JSONDecodeError.
    """
    import os
    import tempfile

    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state.updated_at = datetime.now(UTC)
    payload = json.dumps(state.model_dump(mode="json"), indent=2, default=str)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".pipeline-state-", suffix=".json.tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_state() -> PipelineState | None:
    """Load pipeline state from disk for the active project, or None if not found.

    Reconciles the on-disk ``stages`` list against the current
    :data:`STAGE_DEFINITIONS` so projects whose ``pipeline-state.json``
    predates a newly-added stage still load with a complete stage list.
    Missing stages are inserted as PENDING at their canonical position
    so the engine runs them on next advance — graceful upgrade for old
    projects without bespoke per-stage migration logic.
    """
    path = _state_path()
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    state = PipelineState.model_validate(data)
    _sync_stages_with_definitions(state)
    return state


def _sync_stages_with_definitions(state: PipelineState) -> bool:
    """Insert any missing stages from STAGE_DEFINITIONS into ``state.stages``.

    Mutates ``state`` in place. Existing stages are kept untouched —
    we don't want to clobber their persisted progress / review_mode.
    Missing stages get a fresh ``StageState`` in PENDING; the engine
    runs them on the next advance. Returns True if any stage was
    inserted, False if the loaded state already covered every stage —
    callers (e.g. ``cleanup_orphan_running_stages``) use this to decide
    whether to persist the synced shape.
    """
    have = {s.stage_id: s for s in state.stages}
    if all(d["stage_id"] in have for d in STAGE_DEFINITIONS):
        return False
    new_stages: list[StageState] = []
    for defn in STAGE_DEFINITIONS:
        sid = defn["stage_id"]
        if sid in have:
            new_stages.append(have[sid])
            continue
        new_stages.append(
            StageState(
                stage_id=sid,
                display_name=defn["display_name"],
                review_eligible=defn["review_eligible"],
                status=StageStatus.PENDING,
            )
        )
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
            "Demoted %d orphan RUNNING stage(s) on project open: %s",
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
        self.bus.pipeline_status(self.state.overall_status, self.state.current_stage_id)

        try:
            self._run_loop()
        except Exception:
            logger.exception("Pipeline engine crashed")
            self.state.overall_status = PipelineStatus.FAILED
            save_state(self.state)
            self.bus.pipeline_status(self.state.overall_status, self.state.current_stage_id)
        finally:
            self._running = False

    def _run_loop(self) -> None:
        for stage in self.state.stages:
            # Check cancellation
            if self._cancel_event.is_set():
                self.state.overall_status = PipelineStatus.CANCELLED
                save_state(self.state)
                self.bus.pipeline_status(self.state.overall_status, self.state.current_stage_id)
                logger.info("Pipeline cancelled")
                return

            # Skip completed/skipped stages
            if stage.status in (StageStatus.COMPLETED, StageStatus.SKIPPED):
                continue

            # Run the stage
            self.state.current_stage_id = stage.stage_id
            stage.status = StageStatus.RUNNING
            stage.progress = StageProgress(started_at=datetime.now(UTC))
            save_state(self.state)
            self.bus.stage_update(
                stage.stage_id,
                stage.status,
                stage.progress.model_dump(mode="json"),
            )
            logger.info("Starting stage: %s", stage.display_name)

            # Build progress callback + section emitter for this stage
            progress_cb = self._make_progress_callback(stage)
            emitter = StageEmitter(self.bus, stage.stage_id, _time.monotonic())
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

                # Accumulate cost
                self.state.total_cost_usd += result.cost_usd
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
                )
                self.bus.pipeline_status(self.state.overall_status, stage.stage_id)
                logger.error(
                    "Stage %s failed: %s\n%s",
                    stage.display_name,
                    exc,
                    traceback.format_exc(),
                )
                return

            # Check if human review is needed
            if stage.review_mode == StageReviewMode.REVIEW:
                stage.status = StageStatus.PAUSED_FOR_REVIEW
                self.state.overall_status = PipelineStatus.PAUSED
                save_state(self.state)
                self.bus.stage_update(
                    stage.stage_id,
                    stage.status,
                    stage.progress.model_dump(mode="json"),
                )
                self.bus.pipeline_status(self.state.overall_status, stage.stage_id)
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
            )
            logger.info("Stage %s completed", stage.display_name)

        # All stages done
        all_done = all(
            s.status in (StageStatus.COMPLETED, StageStatus.SKIPPED) for s in self.state.stages
        )
        if all_done:
            self.state.overall_status = PipelineStatus.COMPLETED
            self.state.current_stage_id = None
            save_state(self.state)
            self.bus.pipeline_status(self.state.overall_status, None)
            logger.info("Pipeline completed! Total cost: $%.2f", self.state.total_cost_usd)

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
        self.bus.stage_update(current.stage_id, current.status)
        logger.info("Skipped stage: %s", current.display_name)

        self.run()

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

            self.state.total_cost_usd += cost

            # Persist periodically (every item)
            save_state(self.state)

            # Publish SSE events
            self.bus.item_progress(stage.stage_id, item, completed, total, detail)
            if cost > 0:
                self.bus.cost_update(stage.progress.cost_usd, self.state.total_cost_usd)

        return callback
