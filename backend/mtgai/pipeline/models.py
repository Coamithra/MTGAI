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

from pydantic import AliasChoices, BaseModel, Field, model_validator

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


# Separator between a stage_id and its instance ordinal for repeated stage
# instances (e.g. ``balance.2``). URL-safe (RFC 3986 unreserved) so instance
# ids can flow straight into ``/pipeline/<tab_id>`` without encoding. The
# plan's original ``#`` is the URL fragment delimiter and would truncate.
INSTANCE_SEP = "."


def make_instance_id(stage_id: str, ordinal: int) -> str:
    """Instance id for the ``ordinal``-th copy of a stage.

    ``ordinal <= 1`` is the backbone instance and keeps ``instance_id ==
    stage_id`` (so existing URLs, break-point keys, model assignments,
    runner/clearer lookups, and old persisted state all keep working).
    Inserted copies (ordinal >= 2) get ``f"{stage_id}{INSTANCE_SEP}{ordinal}"``.
    """
    return stage_id if ordinal <= 1 else f"{stage_id}{INSTANCE_SEP}{ordinal}"


class StageState(BaseModel):
    """State of a single pipeline stage.

    A stage can appear more than once in a pipeline run (repeated instances
    inserted by the review→regen loop). ``stage_id`` stays the **template
    key** — shared across instances for runner/clearer/model/break-point
    resolution — while ``instance_id`` is the per-instance identity used for
    tab routing. The backbone instance of each stage keeps ``instance_id ==
    stage_id``; inserted copies get ``f"{stage_id}.{n}"`` (see
    :func:`make_instance_id`) with ``display_name`` suffixed ("Balance
    Analysis 2").
    """

    stage_id: str
    # Backfilled to stage_id when absent so projects whose pipeline-state.json
    # predates instance ids load as all-backbone (see _default_instance).
    instance_id: str = ""
    display_name: str
    status: StageStatus = StageStatus.PENDING
    review_mode: StageReviewMode = StageReviewMode.AUTO
    review_eligible: bool = True  # Can be set to review mode?
    progress: StageProgress = Field(default_factory=StageProgress)
    # Per-instance runner output (from StageResult.artifacts). Persisted in
    # pipeline-state.json so a review instance's findings survive reload and
    # later card_gen runs that clear the per-card flags — the /state endpoints
    # read this to show "the cards THIS instance flagged".
    result: dict = Field(default_factory=dict)
    # The instance_id whose output snapshot is THIS instance's entry card-pool
    # state (its immediate predecessor in ``stages``). Stamped when the instance
    # starts running; used by ``engine.rerun_instance`` to restore the right pool
    # before a manual re-run. Derivable from list position, but persisting it makes
    # restore robust against ``_sync_stages_with_definitions`` reordering / reload.
    # ``None`` for the first stage (no predecessor) and for pre-version-tracking
    # state (migrates in as a from-live re-run).
    entry_snapshot_id: str | None = None

    @model_validator(mode="after")
    def _default_instance(self) -> StageState:
        if not self.instance_id:
            self.instance_id = self.stage_id
        return self


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
    # The currently-running/paused/failed stage *instance*. ``validation_alias``
    # accepts the legacy ``current_stage_id`` key from pre-instance
    # pipeline-state.json (a backbone stage_id is a valid instance_id), so old
    # projects load unchanged; new state serializes under the new name.
    current_instance_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("current_instance_id", "current_stage_id"),
    )
    overall_status: PipelineStatus = PipelineStatus.NOT_STARTED
    total_cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    def current_stage(self) -> StageState | None:
        """Return the current stage instance, or None if not set."""
        if self.current_instance_id is None:
            return None
        for stage in self.stages:
            if stage.instance_id == self.current_instance_id:
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
    {"stage_id": "mechanics", "display_name": "Mechanic Generation", "review_eligible": True},
    {"stage_id": "archetypes", "display_name": "Archetype Generation", "review_eligible": True},
    # Skeleton Generation builds the deterministic default + runs the LLM
    # relabel (theme/constraints/requests → tweaked_text per slot) in one stage.
    {"stage_id": "skeleton", "display_name": "Skeleton Generation", "review_eligible": True},
    {"stage_id": "reprints", "display_name": "Reprint Selection", "review_eligible": True},
    {"stage_id": "lands", "display_name": "Land Generation", "review_eligible": False},
    {"stage_id": "card_gen", "display_name": "Card Generation", "review_eligible": True},
    # Single post-card_gen gate running two whole-set LLM steps internally:
    # conformance (per-card vs slot spec) then interactions (whole-pool combo
    # scan). Combines their findings; either flagging a card bounces to card_gen
    # (re-inserting only [card_gen, conformance]).
    {
        "stage_id": "conformance",
        "display_name": "Conformance & Interactions",
        "review_eligible": True,
    },
    {"stage_id": "ai_review", "display_name": "AI Design Review", "review_eligible": True},
    # Finalization auto-runs (reminder injection + auto-fix), but the user can
    # opt to "Stop after this step" to manually edit any finalized card before
    # continuing — review_eligible surfaces that intent (break-point defaults
    # off; the pause is wired through review_mode independent of this flag).
    {"stage_id": "finalize", "display_name": "Finalization", "review_eligible": True},
    # visual_refs feeds only the art stages (prompt_builder + character refs),
    # so it sits here — right before art_prompts — not pre-skeleton.
    {
        "stage_id": "visual_refs",
        "display_name": "Visual References & Artists",
        "review_eligible": True,
    },
    {"stage_id": "art_prompts", "display_name": "Art Prompt Generation", "review_eligible": False},
    # char_portraits KEEPS its stage_id (not renamed to char_refs) to avoid
    # churning model/image assignments, break_points keys, /pipeline URLs, and
    # persisted pipeline-state.json; only the display_name changed.
    {"stage_id": "char_portraits", "display_name": "Character References", "review_eligible": True},
    # art_gen is MERGED: art generation + best-of-N selection + human art review.
    # The old art_select + human_art_review stage_ids are retired (folded in here).
    {"stage_id": "art_gen", "display_name": "Art Generation & Review", "review_eligible": True},
    # rendering is MERGED: render + final review (QA dropped entirely). The old
    # render_qa + human_final_review stage_ids are retired (folded in here).
    {"stage_id": "rendering", "display_name": "Rendering & Final Review", "review_eligible": True},
]


def _resolve_break_point(stage_id: str, break_points: dict[str, str]) -> bool:
    """True iff the wizard should pause after this stage given the settings.

    Falls back to ``DEFAULT_BREAK_POINTS`` so human review stages start
    checked-on for new sets while still letting users uncheck them.
    """
    from mtgai.settings.model_settings import DEFAULT_BREAK_POINTS

    return break_points.get(stage_id, DEFAULT_BREAK_POINTS.get(stage_id, "auto")) == "review"


def break_point_states(break_points: dict[str, str]) -> dict[str, bool]:
    """Map every pipeline stage to whether the wizard should pause after it.

    Single source for the ``settings.break_points`` -> bool resolution
    used by the Project Settings break-points list (server-side payload)
    and the per-tab "Stop after this step" checkbox (wizard bootstrap).

    ``theme_extract`` is included as a virtual entry — it isn't a pipeline
    stage (it runs before the engine kicks off) but the Theme tab reads
    its bit for the same per-tab checkbox the stage tabs use.
    """
    out = {
        defn["stage_id"]: _resolve_break_point(defn["stage_id"], break_points)
        for defn in STAGE_DEFINITIONS
    }
    out["theme_extract"] = _resolve_break_point("theme_extract", break_points)
    return out


def build_stages(
    config: PipelineConfig, break_points: dict[str, str] | None = None
) -> list[StageState]:
    """Build the ordered stage list from definitions + user config.

    ``break_points`` (when provided) seeds review_mode from the per-set
    settings.toml; falls back to ``stage_review_modes`` on the config
    for callers that haven't migrated to break_points yet.
    """
    bp = break_points or {}
    stages = []
    for defn in STAGE_DEFINITIONS:
        stage_id = defn["stage_id"]
        review_mode = config.stage_review_modes.get(stage_id, StageReviewMode.AUTO)
        if break_points is not None and _resolve_break_point(stage_id, bp):
            review_mode = StageReviewMode.REVIEW
        stages.append(
            StageState(
                stage_id=stage_id,
                display_name=defn["display_name"],
                review_eligible=defn["review_eligible"],
                review_mode=review_mode,
            )
        )
    return stages


def create_pipeline_state(
    config: PipelineConfig, break_points: dict[str, str] | None = None
) -> PipelineState:
    """Create a fresh pipeline state from user configuration."""
    return PipelineState(
        config=config,
        stages=build_stages(config, break_points=break_points),
    )
