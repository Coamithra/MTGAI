"""Pipeline state models — persisted to disk as JSON for crash recovery.

The pipeline is a linear sequence of stages. Each stage has a status,
a review mode (auto/review), and optional sub-item progress tracking.
The full state is saved to output/sets/<SET>/pipeline-state.json after
every stage transition and sub-item completion.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class StageReviewMode(StrEnum):
    """How the pipeline handles stage completion.

    Two-value flag in the wizard model: ``AUTO`` = no break (the engine
    advances to the next stage automatically), ``REVIEW`` = break (the
    engine pauses after the stage finishes and waits for the user to
    advance via the Next-step button).
    """

    AUTO = "auto"  # Run and continue automatically
    REVIEW = "review"  # Pause after completion for human review


class StageStatus(StrEnum):
    """Lifecycle status of a pipeline stage."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED_FOR_REVIEW = "paused_for_review"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineStatus(StrEnum):
    """Overall pipeline status."""

    NOT_STARTED = "not_started"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Progress callback protocol
# ---------------------------------------------------------------------------

# Signature: (item, completed, total, detail, cost_usd) -> None
ProgressCallback = Callable[[str, int, int, str, float], None]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class StageProgress(BaseModel):
    """Progress within a single stage."""

    total_items: int = 0
    completed_items: int = 0
    failed_items: int = 0
    current_item: str | None = None  # e.g. "W-C-05" or "batch 3/12"
    detail: str = ""  # Human-readable status line
    cost_usd: float = 0.0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None


class StageState(BaseModel):
    """State of a single pipeline stage."""

    stage_id: str
    display_name: str
    status: StageStatus = StageStatus.PENDING
    review_mode: StageReviewMode = StageReviewMode.AUTO
    review_eligible: bool = True  # Can be set to review mode?
    always_review: bool = False  # Human review stages — always pause
    progress: StageProgress = Field(default_factory=StageProgress)


class PipelineConfig(BaseModel):
    """User-provided configuration for a pipeline run.

    The wizard surfaces only break-point overrides via
    ``stage_review_modes``. ``StageStatus.SKIPPED`` is still used
    internally for stages that the engine auto-skips (e.g. character
    portraits when a set has no character cards), but there is no
    user-facing knob to mark a stage as skipped.
    """

    set_code: str
    set_name: str
    set_size: int = 60
    # Per-stage review mode overrides (stage_id -> mode)
    stage_review_modes: dict[str, StageReviewMode] = Field(default_factory=dict)


class PipelineState(BaseModel):
    """Full pipeline state — persisted to disk."""

    config: PipelineConfig
    stages: list[StageState]
    current_stage_id: str | None = None
    overall_status: PipelineStatus = PipelineStatus.NOT_STARTED
    total_cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    def current_stage(self) -> StageState | None:
        """Return the current stage, or None if not set."""
        if self.current_stage_id is None:
            return None
        for stage in self.stages:
            if stage.stage_id == self.current_stage_id:
                return stage
        return None

    def next_pending_stage(self) -> StageState | None:
        """Return the next stage that hasn't been completed/skipped."""
        for stage in self.stages:
            if stage.status in (StageStatus.PENDING, StageStatus.FAILED):
                return stage
        return None


# ---------------------------------------------------------------------------
# Stage definitions — the canonical ordered list of pipeline stages
# ---------------------------------------------------------------------------

STAGE_DEFINITIONS: list[dict] = [
    {
        "stage_id": "skeleton",
        "display_name": "Skeleton Generation",
        "review_eligible": True,
        "always_review": False,
    },
    {
        "stage_id": "reprints",
        "display_name": "Reprint Selection",
        "review_eligible": True,
        "always_review": False,
    },
    {
        "stage_id": "lands",
        "display_name": "Land Generation",
        "review_eligible": False,
        "always_review": False,
    },
    {
        "stage_id": "card_gen",
        "display_name": "Card Generation",
        "review_eligible": True,
        "always_review": False,
    },
    {
        "stage_id": "balance",
        "display_name": "Balance Analysis",
        "review_eligible": True,
        "always_review": False,
    },
    {
        "stage_id": "skeleton_rev",
        "display_name": "Skeleton Revision",
        "review_eligible": True,
        "always_review": False,
    },
    {
        "stage_id": "ai_review",
        "display_name": "AI Design Review",
        "review_eligible": True,
        "always_review": False,
    },
    {
        "stage_id": "finalize",
        "display_name": "Finalization",
        "review_eligible": False,
        "always_review": False,
    },
    {
        "stage_id": "human_card_review",
        "display_name": "Card Review",
        "review_eligible": True,
        "always_review": True,
    },
    {
        "stage_id": "art_prompts",
        "display_name": "Art Prompt Generation",
        "review_eligible": False,
        "always_review": False,
    },
    {
        "stage_id": "char_portraits",
        "display_name": "Character Portraits",
        "review_eligible": True,
        "always_review": False,
    },
    {
        "stage_id": "art_gen",
        "display_name": "Art Generation",
        "review_eligible": False,
        "always_review": False,
    },
    {
        "stage_id": "art_select",
        "display_name": "Art Selection",
        "review_eligible": True,
        "always_review": False,
    },
    {
        "stage_id": "human_art_review",
        "display_name": "Art Review",
        "review_eligible": True,
        "always_review": True,
    },
    {
        "stage_id": "rendering",
        "display_name": "Card Rendering",
        "review_eligible": False,
        "always_review": False,
    },
    {
        "stage_id": "render_qa",
        "display_name": "Render QA",
        "review_eligible": True,
        "always_review": False,
    },
    {
        "stage_id": "human_final_review",
        "display_name": "Final Review",
        "review_eligible": True,
        "always_review": True,
    },
]


def build_stages(config: PipelineConfig) -> list[StageState]:
    """Build the ordered stage list from definitions + user config."""
    stages = []
    for defn in STAGE_DEFINITIONS:
        stage_id = defn["stage_id"]
        review_mode = config.stage_review_modes.get(stage_id, StageReviewMode.AUTO)
        # Human review stages are always in review mode
        if defn["always_review"]:
            review_mode = StageReviewMode.REVIEW
        stages.append(
            StageState(
                stage_id=stage_id,
                display_name=defn["display_name"],
                review_eligible=defn["review_eligible"],
                always_review=defn["always_review"],
                review_mode=review_mode,
            )
        )
    return stages


def create_pipeline_state(config: PipelineConfig) -> PipelineState:
    """Create a fresh pipeline state from user configuration."""
    return PipelineState(
        config=config,
        stages=build_stages(config),
    )
