"""Stage registry — maps stage_id to actual pipeline function calls.

Each stage runner receives a set_code and a progress callback, calls the
appropriate library function, and returns a StageResult with summary info.
Stages that aren't yet wired to real functions use stub implementations
that log and return immediately.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtgai.pipeline.models import ProgressCallback

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OUTPUT_ROOT = Path("C:/Programming/MTGAI/output")


def _set_dir(set_code: str) -> Path:
    return OUTPUT_ROOT / "sets" / set_code


# ---------------------------------------------------------------------------
# Stage result
# ---------------------------------------------------------------------------


@dataclass
class StageResult:
    """Summary returned by a stage runner."""

    success: bool = True
    total_items: int = 0
    completed_items: int = 0
    failed_items: int = 0
    cost_usd: float = 0.0
    detail: str = ""
    error_message: str | None = None
    artifacts: dict = field(default_factory=dict)  # stage-specific outputs


# ---------------------------------------------------------------------------
# Stage runners
# ---------------------------------------------------------------------------


def run_skeleton(set_code: str, progress_cb: ProgressCallback | None) -> StageResult:
    """Generate the set skeleton."""
    from mtgai.skeleton.generator import generate_skeleton
    from mtgai.skeleton.models import SetConfig

    set_dir = _set_dir(set_code)
    config_path = set_dir / "set-config.json"
    template_path = Path("C:/Programming/MTGAI/config/set-template.json")

    if not config_path.exists():
        return StageResult(
            success=False,
            error_message=f"Set config not found: {config_path}",
        )

    config_data = json.loads(config_path.read_text(encoding="utf-8"))
    config = SetConfig(**config_data)

    result = generate_skeleton(config, template_path)

    # Save skeleton
    skeleton_path = set_dir / "skeleton.json"
    skeleton_path.parent.mkdir(parents=True, exist_ok=True)
    skeleton_path.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    slot_count = len(result.slots)
    logger.info("Skeleton generated: %d slots", slot_count)
    return StageResult(
        total_items=slot_count,
        completed_items=slot_count,
        detail=f"Generated skeleton with {slot_count} slots",
    )


def run_reprints(set_code: str, progress_cb: ProgressCallback | None) -> StageResult:
    """Select reprints from curated pool."""
    from mtgai.generation.reprint_selector import select_reprints

    set_dir = _set_dir(set_code)
    skeleton_path = set_dir / "skeleton.json"

    if not skeleton_path.exists():
        return StageResult(success=False, error_message="skeleton.json not found")

    result = select_reprints(skeleton_path=skeleton_path)

    count = len(result.selections)
    # Save selection result
    output_path = set_dir / "reprint_selection.json"
    output_path.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("Selected %d reprints", count)
    return StageResult(
        total_items=count,
        completed_items=count,
        cost_usd=getattr(result, "cost_usd", 0.0),
        detail=f"Selected {count} reprints",
    )


def run_lands(set_code: str, progress_cb: ProgressCallback | None) -> StageResult:
    """Generate land cards."""
    from mtgai.generation.land_generator import generate_lands

    result = generate_lands(set_code=set_code)
    count = result.get("total_cards", 6)
    return StageResult(
        total_items=count,
        completed_items=count,
        cost_usd=result.get("cost_usd", 0.0),
        detail=f"Generated {count} land cards",
    )


def run_card_gen(set_code: str, progress_cb: ProgressCallback | None) -> StageResult:
    """Generate cards from skeleton slots."""
    from mtgai.generation.card_generator import generate_set

    result = generate_set(
        set_code=set_code,
        progress_callback=progress_cb,
    )
    return StageResult(
        total_items=result.get("total_slots", 0),
        completed_items=result.get("filled", 0),
        failed_items=result.get("failed", 0),
        cost_usd=result.get("cost_usd", 0.0),
        detail=result.get("summary", "Card generation complete"),
    )


def run_balance(set_code: str, progress_cb: ProgressCallback | None) -> StageResult:
    """Run balance analysis on the generated set."""
    from mtgai.analysis.balance import analyze_set

    result = analyze_set(set_code)

    issues = len(result.issues) if hasattr(result, "issues") else 0
    return StageResult(
        detail=f"Balance analysis complete — {issues} issues found",
        artifacts={"issues": issues},
    )


def run_skeleton_rev(set_code: str, progress_cb: ProgressCallback | None) -> StageResult:
    """Run skeleton revision based on balance findings."""
    from mtgai.generation.skeleton_reviser import run_revision

    result = run_revision(set_code=set_code)

    replaced = result.get("total_cards_replaced", 0)
    rounds = len(result.get("rounds", []))
    return StageResult(
        total_items=replaced,
        completed_items=replaced,
        cost_usd=result.get("total_cost_usd", 0.0),
        detail=f"Skeleton revision: {rounds} rounds, {replaced} cards replaced",
    )


def run_ai_review(set_code: str, progress_cb: ProgressCallback | None) -> StageResult:
    """Run AI design review on all cards."""
    from mtgai.review.ai_review import review_all_cards

    result = review_all_cards(
        set_code=set_code,
        progress_callback=progress_cb,
    )
    reviewed = result.get("reviewed", 0)
    revised = result.get("revised", 0)
    return StageResult(
        total_items=reviewed,
        completed_items=reviewed,
        cost_usd=result.get("cost_usd", 0.0),
        detail=f"AI review complete — {reviewed} reviewed, {revised} revised",
    )


def run_finalize(set_code: str, progress_cb: ProgressCallback | None) -> StageResult:
    """Run post-review finalization (reminder text injection + validation)."""
    from mtgai.review.finalize import finalize_set

    result = finalize_set(set_code=set_code)

    modified = result.get("cards_modified", 0)
    manual = result.get("total_manual_errors", 0)
    return StageResult(
        total_items=result.get("total_cards", 0),
        completed_items=result.get("total_cards", 0),
        detail=f"Finalized — {modified} cards modified, {manual} manual errors remaining",
    )


def run_human_card_review(set_code: str, progress_cb: ProgressCallback | None) -> StageResult:
    """Human card review — this is a pause point, not an automated stage.

    The engine pauses here and the user uses the review gallery UI.
    This function is a no-op; the engine handles the pause via always_review.
    """
    return StageResult(detail="Awaiting human card review via gallery UI")


def run_art_prompts(set_code: str, progress_cb: ProgressCallback | None) -> StageResult:
    """Generate art prompts for all cards."""
    from mtgai.art.prompt_builder import generate_prompts_for_set

    result = generate_prompts_for_set(
        set_code=set_code,
        progress_callback=progress_cb,
    )

    processed = result.get("processed", 0)
    return StageResult(
        total_items=processed + result.get("skipped", 0),
        completed_items=processed,
        cost_usd=result.get("cost_usd", 0.0),
        detail=f"Generated {processed} art prompts",
    )


def run_char_portraits(set_code: str, progress_cb: ProgressCallback | None) -> StageResult:
    """Generate character reference portraits."""
    from mtgai.art.character_portraits import generate_character_portraits

    result = generate_character_portraits(set_code=set_code)

    generated = result.get("generated", 0)
    return StageResult(
        total_items=generated,
        completed_items=generated,
        detail=f"Generated portraits for {generated} characters",
    )


def run_art_gen(set_code: str, progress_cb: ProgressCallback | None) -> StageResult:
    """Generate art for all cards via ComfyUI + Flux."""
    from mtgai.art.image_generator import generate_art_for_set

    result = generate_art_for_set(
        set_code=set_code,
        progress_callback=progress_cb,
    )

    generated = result.get("generated", 0)
    return StageResult(
        total_items=generated + result.get("skipped", 0),
        completed_items=generated,
        failed_items=result.get("failed", 0),
        detail=f"Generated art for {generated} cards",
    )


def run_art_select(set_code: str, progress_cb: ProgressCallback | None) -> StageResult:
    """Select best art version per card via Haiku vision."""
    from mtgai.art.art_selector import select_best_art_for_set

    result = select_best_art_for_set(
        set_code=set_code,
        progress_callback=progress_cb,
    )

    selected = result.get("selected", 0)
    return StageResult(
        total_items=selected,
        completed_items=selected,
        cost_usd=result.get("cost_usd", 0.0),
        detail=f"Selected art for {selected} cards",
    )


def run_human_art_review(set_code: str, progress_cb: ProgressCallback | None) -> StageResult:
    """Human art review — pause point for art gallery review."""
    return StageResult(detail="Awaiting human art review via gallery UI")


def run_rendering(set_code: str, progress_cb: ProgressCallback | None) -> StageResult:
    """Render all cards to print-ready images."""
    from mtgai.rendering.card_renderer import CardRenderer

    renderer = CardRenderer()
    result = renderer.render_set(
        set_code=set_code,
        progress_callback=progress_cb,
    )

    rendered = result.get("rendered", 0)
    return StageResult(
        total_items=rendered + result.get("skipped", 0),
        completed_items=rendered,
        failed_items=result.get("failed", 0),
        detail=f"Rendered {rendered} cards ({result.get('elapsed_seconds', 0):.1f}s)",
    )


def run_render_qa(set_code: str, progress_cb: ProgressCallback | None) -> StageResult:
    """Re-run validators on rendered cards for final QA."""
    from mtgai.validation import validate_card_from_raw

    set_dir = _set_dir(set_code)
    cards_dir = set_dir / "cards"

    if not cards_dir.exists():
        return StageResult(success=False, error_message="cards/ directory not found")

    card_files = sorted(cards_dir.glob("*.json"))
    errors_found = 0
    cards_clean = 0

    for card_file in card_files:
        data = json.loads(card_file.read_text(encoding="utf-8"))
        _card, errors, _fixes = validate_card_from_raw(data)
        manual_errors = [e for e in errors if e.severity.value == "MANUAL"]
        if manual_errors:
            errors_found += len(manual_errors)
        else:
            cards_clean += 1

    total = len(card_files)
    return StageResult(
        total_items=total,
        completed_items=total,
        detail=f"QA complete — {cards_clean}/{total} clean, {errors_found} issues",
        artifacts={"errors_found": errors_found, "cards_clean": cards_clean},
    )


def run_human_final_review(set_code: str, progress_cb: ProgressCallback | None) -> StageResult:
    """Human final review — pause point for rendered card review."""
    return StageResult(detail="Awaiting human final review via gallery UI")


# ---------------------------------------------------------------------------
# Stage registry
# ---------------------------------------------------------------------------

STAGE_RUNNERS = {
    "skeleton": run_skeleton,
    "reprints": run_reprints,
    "lands": run_lands,
    "card_gen": run_card_gen,
    "balance": run_balance,
    "skeleton_rev": run_skeleton_rev,
    "ai_review": run_ai_review,
    "finalize": run_finalize,
    "human_card_review": run_human_card_review,
    "art_prompts": run_art_prompts,
    "char_portraits": run_char_portraits,
    "art_gen": run_art_gen,
    "art_select": run_art_select,
    "human_art_review": run_human_art_review,
    "rendering": run_rendering,
    "render_qa": run_render_qa,
    "human_final_review": run_human_final_review,
}
