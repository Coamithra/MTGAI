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
import traceback
from datetime import UTC, datetime
from pathlib import Path

import time as _time

from mtgai.pipeline.events import EventBus, StageEmitter
from mtgai.pipeline.models import (
    PipelineState,
    PipelineStatus,
    ProgressCallback,
    StageProgress,
    StageReviewMode,
    StageStatus,
)
from mtgai.pipeline.stages import STAGE_RUNNERS, StageResult

logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path("C:/Programming/MTGAI/output")


def _state_path(set_code: str) -> Path:
    return OUTPUT_ROOT / "sets" / set_code / "pipeline-state.json"


def save_state(state: PipelineState) -> None:
    """Persist pipeline state to disk."""
    path = _state_path(state.config.set_code)
    path.parent.mkdir(parents=True, exist_ok=True)
    state.updated_at = datetime.now(UTC)
    path.write_text(
        json.dumps(state.model_dump(mode="json"), indent=2, default=str),
        encoding="utf-8",
    )


def load_state(set_code: str) -> PipelineState | None:
    """Load pipeline state from disk, or None if not found."""
    path = _state_path(set_code)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return PipelineState.model_validate(data)


def cleanup_orphan_running_stages() -> list[str]:
    """Demote any persisted ``RUNNING`` stage to ``FAILED``.

    Called on server boot, before any engine is constructed: at that
    point the in-memory pipeline registry is empty, so any
    ``StageStatus.RUNNING`` (or ``PipelineStatus.RUNNING``) on disk
    came from a previous process that exited mid-stage. Mark the
    stage failed with a clear message and reset the overall status so
    the user can retry from the wizard.

    Returns a list of ``"<set_code>:<stage_id>"`` strings that were
    demoted, mainly for logging.
    """
    sets_root = OUTPUT_ROOT / "sets"
    if not sets_root.exists():
        return []

    demoted: list[str] = []
    now = datetime.now(UTC)
    for state_path in sets_root.glob("*/pipeline-state.json"):
        try:
            state = PipelineState.model_validate_json(state_path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("cleanup_orphan_running_stages: failed to load %s", state_path)
            continue

        changed = False
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
            save_state(state)

    if demoted:
        logger.warning(
            "Demoted %d orphan RUNNING stage(s) on boot: %s",
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

                result: StageResult = runner(
                    self.state.config.set_code,
                    progress_cb,
                    emitter,
                )

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
            if stage.always_review or stage.review_mode == StageReviewMode.REVIEW:
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
