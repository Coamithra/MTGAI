"""Stage registry — maps stage_id to actual pipeline function calls.

Each stage runner receives a set_code and a progress callback, calls the
appropriate library function, and returns a StageResult with summary info.
Stages that aren't yet wired to real functions use stub implementations
that log and return immediately.

Each stage also has a clearer (``STAGE_CLEARERS``) used by the wizard
edit-flow cascade: when the user accepts edits to a past stage, every
downstream stage's clearer runs to wipe its on-disk artifacts. Stages
that don't own dedicated artifacts (analysis-only stages, in-place
mutators, human review pauses) register a no-op so the dispatch stays
uniform.
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtgai.pipeline.events import StageEmitter
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


def run_skeleton(
    set_code: str,
    progress_cb: ProgressCallback | None,
    emitter: StageEmitter,
) -> StageResult:
    """Generate the set skeleton."""
    from mtgai.skeleton.generator import SetConfig, generate_skeleton

    set_dir = _set_dir(set_code)
    theme_path = set_dir / "theme.json"
    template_path = Path("C:/Programming/MTGAI/research/set-template.json")

    if not theme_path.exists():
        return StageResult(
            success=False,
            error_message=f"Theme not found: {theme_path}. Create one at /pipeline/theme first.",
        )

    emitter.init_sections(
        [
            {"section_id": "overview", "title": "Set Overview", "content_type": "kv"},
            {"section_id": "rarity", "title": "Rarity Counts", "content_type": "table"},
            {
                "section_id": "colors",
                "title": "Color Distribution",
                "content_type": "table",
            },
            {"section_id": "types", "title": "Type Distribution", "content_type": "table"},
            {"section_id": "slots", "title": "Slot List", "content_type": "table"},
        ]
    )
    emitter.phase("running", "Generating skeleton")

    theme_data = json.loads(theme_path.read_text(encoding="utf-8"))
    config = SetConfig(**theme_data)
    emitter.update(
        "overview",
        status="done",
        content={
            "Set code": config.code,
            "Set name": config.name,
            "Size": str(config.set_size),
            "Theme": (config.theme or "")[:120],
        },
    )

    result = generate_skeleton(config, template_path)

    # Save skeleton
    skeleton_path = set_dir / "skeleton.json"
    skeleton_path.parent.mkdir(parents=True, exist_ok=True)
    skeleton_path.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    rarity_rows = [["Rarity", "Count"]]
    for r, n in result.balance_report.rarity_counts.items():
        rarity_rows.append([r.title(), str(n)])
    emitter.update("rarity", status="done", content={"rows": rarity_rows})

    color_label: dict[str, str] = {
        "W": "White",
        "U": "Blue",
        "B": "Black",
        "R": "Red",
        "G": "Green",
        "multicolor": "Multicolor",
        "colorless": "Colorless",
    }
    color_rows: list[list[str]] = [["Color", "Count"]]
    for c, n in result.balance_report.color_counts.items():
        color_rows.append([color_label.get(c, c), str(n)])
    emitter.update("colors", status="done", content={"rows": color_rows})

    type_rows: list[list[str]] = [["Type", "Count"]]
    for t, n in sorted(
        result.balance_report.type_counts.items(),
        key=lambda kv: -kv[1],
    ):
        type_rows.append([t.title(), str(n)])
    emitter.update("types", status="done", content={"rows": type_rows})

    slot_rows: list[list[str]] = [["Slot", "Color", "Rarity", "Type", "CMC", "Mechanic"]]
    for slot in result.slots:
        slot_rows.append(
            [
                slot.slot_id,
                color_label.get(slot.color, slot.color),
                slot.rarity[:1].upper(),
                slot.card_type,
                str(slot.cmc_target),
                slot.mechanic_tag,
            ]
        )
    emitter.update(
        "slots",
        status="done",
        content={"rows": slot_rows, "scrollable": True},
    )

    slot_count = len(result.slots)
    emitter.phase(
        "done",
        f"Skeleton ready — {slot_count} slots",
    )
    logger.info("Skeleton generated: %d slots", slot_count)
    return StageResult(
        total_items=slot_count,
        completed_items=slot_count,
        detail=f"Generated skeleton with {slot_count} slots",
    )


def run_reprints(
    set_code: str,
    progress_cb: ProgressCallback | None,
    emitter: StageEmitter,
) -> StageResult:
    """Select reprints from curated pool."""
    from mtgai.generation.reprint_selector import (
        identify_reprint_slots,
        load_reprint_pool,
        select_reprints,
    )

    set_dir = _set_dir(set_code)
    skeleton_path = set_dir / "skeleton.json"

    if not skeleton_path.exists():
        return StageResult(success=False, error_message="skeleton.json not found")

    emitter.init_sections(
        [
            {
                "section_id": "pool",
                "title": "Pool & Slots",
                "content_type": "kv",
                "status": "running",
            },
            {
                "section_id": "selections",
                "title": "Picked Reprints",
                "content_type": "card_grid",
                "status": "pending",
            },
        ]
    )
    emitter.phase("running", "Loading reprint pool")

    pool = load_reprint_pool()
    eligible_pool = [c for c in pool if c.setting_agnostic is not False]
    slots = identify_reprint_slots(skeleton_path)
    emitter.update(
        "pool",
        status="done",
        content={
            "Pool size": str(len(pool)),
            "Setting-agnostic": str(len(eligible_pool)),
            "Eligible slots": str(len(slots)),
        },
    )

    emitter.update("selections", status="running", detail="Asking the model to pick…")
    emitter.phase("running", f"Selecting reprints from pool of {len(eligible_pool)}")

    import time as _time

    from mtgai.generation.llm_client import _get_provider, _resolve_provider
    from mtgai.generation.phase_poller import NullPoller, PromptEvalPoller
    from mtgai.settings.model_settings import get_llm_model

    # Spin up a poller so the activity banner shows real prompt-eval%
    # / generation tok/s during the (potentially long) llamacpp call.
    # Anthropic doesn't expose /slots, so we no-op for that provider.
    reprint_model = get_llm_model("reprints", set_code)
    provider_name = _resolve_provider(reprint_model)
    if provider_name == "llamacpp":
        try:
            poller_ctx: PromptEvalPoller | NullPoller = PromptEvalPoller(
                provider=_get_provider("llamacpp"),
                model_id=reprint_model,
                emit=emitter.phase,
                phase_kind="running",
                activity_prefix=f"Selecting reprints (pool={len(eligible_pool)})",
            )
        except Exception as e:  # provider construction failure — skip telemetry
            logger.warning("Reprints poller setup failed (%s); continuing without telemetry", e)
            poller_ctx = NullPoller()
    else:
        poller_ctx = NullPoller()

    with poller_ctx:
        result = select_reprints(skeleton_path=skeleton_path)

    count = len(result.selections)
    # Save selection result
    output_path = set_dir / "reprint_selection.json"
    output_path.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Cascade tile reveal so the user sees picks land one-by-one rather
    # than all at once after the LLM call. The picks are already chosen;
    # this is purely visual pacing on top of the existing fade-in CSS.
    emitter.update("selections", content={"items": []}, detail=f"Revealing {count}…")
    for pair in result.selections:
        c = pair.candidate
        tile = {
            "name": c.name,
            "mana_cost": c.mana_cost or "",
            "type_line": c.type_line,
            "rarity": c.rarity,
            "oracle_text": c.oracle_text,
            "slot_id": pair.slot.slot_id,
            "reason": pair.reason,
        }
        emitter.update("selections", append_item=tile)
        _time.sleep(0.18)

    emitter.update("selections", status="done", detail="")
    emitter.phase("done", f"Picked {count} reprints")
    logger.info("Selected %d reprints", count)
    return StageResult(
        total_items=count,
        completed_items=count,
        cost_usd=getattr(result, "cost_usd", 0.0),
        detail=f"Selected {count} reprints",
    )


def run_lands(
    set_code: str,
    progress_cb: ProgressCallback | None,
    emitter: StageEmitter,
) -> StageResult:
    """Generate land cards."""
    import time as _time

    from mtgai.generation.land_generator import generate_lands

    emitter.init_sections(
        [
            {
                "section_id": "call",
                "title": "Land Design Call",
                "content_type": "kv",
                "status": "pending",
            },
            {
                "section_id": "lands",
                "title": "Lands",
                "content_type": "card_grid",
                "status": "pending",
                "content": {"items": []},
            },
        ]
    )

    # Capture the resolved model_id so the final "done" kv reflects what
    # actually ran, not a hardcoded label.
    state = {"model_id": "(unresolved)"}

    def _on_call_start(model_id: str) -> None:
        state["model_id"] = model_id
        is_local = not model_id.startswith("claude-")
        provider_label = (
            "local Gemma" if "gemma" in model_id else ("local model" if is_local else "Anthropic")
        )
        emitter.update(
            "call",
            status="running",
            content={
                "Model": model_id,
                "Asking for": "5 basic flavor texts + 1 nonbasic design",
            },
            detail="Generating…",
        )
        emitter.update("lands", status="running")
        emitter.phase(
            "running",
            f"Calling {provider_label} for land flavor + nonbasic design",
        )

    # Buffer the saved cards so we can stagger their reveal AFTER the LLM
    # call returns. The single Haiku/Gemma call returns all 6 lands at
    # once, but emitting them one-by-one with a short sleep gives the UI
    # a cascading fade-in (matches the fade-in CSS) and is much nicer to
    # watch than a "boom, all 6 appear" moment.
    saved_cards: list = []

    def _on_card_saved(card) -> None:  # noqa: ANN001
        saved_cards.append(card)

    from mtgai.generation.llm_client import _get_provider, _resolve_provider
    from mtgai.generation.phase_poller import NullPoller, PromptEvalPoller
    from mtgai.settings.model_settings import get_llm_model

    lands_model = get_llm_model("lands", set_code)
    if _resolve_provider(lands_model) == "llamacpp":
        try:
            poller_ctx: PromptEvalPoller | NullPoller = PromptEvalPoller(
                provider=_get_provider("llamacpp"),
                model_id=lands_model,
                emit=emitter.phase,
                phase_kind="running",
                activity_prefix="Designing lands",
            )
        except Exception as e:
            logger.warning("Lands poller setup failed (%s); continuing without telemetry", e)
            poller_ctx = NullPoller()
    else:
        poller_ctx = NullPoller()

    with poller_ctx:
        result = generate_lands(
            set_code=set_code,
            on_call_start=_on_call_start,
            on_card_saved=_on_card_saved,
        )
    count = result.get("total_cards", 6)
    cost = result.get("cost_usd", 0.0)

    # Cascade: emit each tile with a short delay so the UI can animate.
    for card in saved_cards:
        tile = {
            "name": card.name,
            "mana_cost": card.mana_cost or "",
            "type_line": card.type_line,
            "rarity": card.rarity.value if hasattr(card.rarity, "value") else str(card.rarity),
            "oracle_text": card.oracle_text or "",
            "flavor_text": card.flavor_text or "",
        }
        emitter.update("lands", append_item=tile)
        _time.sleep(0.2)

    cost_label = f"${cost:.4f}" if cost > 0 else "$0.00 (local)"
    emitter.update(
        "call",
        status="done",
        content={
            "Model": state["model_id"],
            "Cost": cost_label,
            "Cards": str(count),
        },
        detail="",
    )
    emitter.update("lands", status="done", detail="")
    emitter.phase("done", f"Generated {count} land cards")
    return StageResult(
        total_items=count,
        completed_items=count,
        cost_usd=cost,
        detail=f"Generated {count} land cards",
    )


def run_card_gen(
    set_code: str, progress_cb: ProgressCallback | None, emitter: StageEmitter
) -> StageResult:
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


def run_balance(
    set_code: str, progress_cb: ProgressCallback | None, emitter: StageEmitter
) -> StageResult:
    """Run balance analysis on the generated set."""
    from mtgai.analysis.balance import analyze_set

    result = analyze_set(set_code)

    issues = len(result.issues) if hasattr(result, "issues") else 0
    return StageResult(
        detail=f"Balance analysis complete — {issues} issues found",
        artifacts={"issues": issues},
    )


def run_skeleton_rev(
    set_code: str, progress_cb: ProgressCallback | None, emitter: StageEmitter
) -> StageResult:
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


def run_ai_review(
    set_code: str, progress_cb: ProgressCallback | None, emitter: StageEmitter
) -> StageResult:
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


def run_finalize(
    set_code: str, progress_cb: ProgressCallback | None, emitter: StageEmitter
) -> StageResult:
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


def run_human_card_review(
    set_code: str, progress_cb: ProgressCallback | None, emitter: StageEmitter
) -> StageResult:
    """Human card review — this is a pause point, not an automated stage.

    The engine pauses here and the user uses the review gallery UI.
    This function is a no-op; the engine handles the pause via always_review.
    """
    return StageResult(detail="Awaiting human card review via gallery UI")


def run_art_prompts(
    set_code: str, progress_cb: ProgressCallback | None, emitter: StageEmitter
) -> StageResult:
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


def run_char_portraits(
    set_code: str, progress_cb: ProgressCallback | None, emitter: StageEmitter
) -> StageResult:
    """Generate character reference portraits."""
    from mtgai.art.character_portraits import generate_character_portraits

    result = generate_character_portraits(set_code=set_code)

    generated = result.get("generated", 0)
    return StageResult(
        total_items=generated,
        completed_items=generated,
        detail=f"Generated portraits for {generated} characters",
    )


def run_art_gen(
    set_code: str, progress_cb: ProgressCallback | None, emitter: StageEmitter
) -> StageResult:
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


def run_art_select(
    set_code: str, progress_cb: ProgressCallback | None, emitter: StageEmitter
) -> StageResult:
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


def run_human_art_review(
    set_code: str, progress_cb: ProgressCallback | None, emitter: StageEmitter
) -> StageResult:
    """Human art review — pause point for art gallery review."""
    return StageResult(detail="Awaiting human art review via gallery UI")


def run_rendering(
    set_code: str, progress_cb: ProgressCallback | None, emitter: StageEmitter
) -> StageResult:
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


def run_render_qa(
    set_code: str, progress_cb: ProgressCallback | None, emitter: StageEmitter
) -> StageResult:
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


def run_human_final_review(
    set_code: str, progress_cb: ProgressCallback | None, emitter: StageEmitter
) -> StageResult:
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


# ---------------------------------------------------------------------------
# Stage artifact clearers — per-stage on-disk cleanup
# ---------------------------------------------------------------------------
#
# Used by the wizard edit-flow (§9.3 of plans/wizard-ui-redesign.md):
# when the user accepts edits to a past stage, every downstream stage's
# clearer runs to delete that stage's owned artifacts. Stages that
# don't own dedicated artifacts (analysis-only, in-place card mutators,
# human review pauses) register the ``_no_artifacts`` no-op so the
# dispatch stays uniform — callers never need to special-case them.
#
# Conventions:
# - Clearers receive a validated ``set_code`` and run synchronously.
# - File-not-found is fine (clear is idempotent); permission / I/O
#   errors propagate so the caller can surface them.
# - Stages that mutate cards in place (``ai_review``, ``finalize``,
#   ``art_prompts``, ``art_select``, ``skeleton_rev``) intentionally
#   no-op — their effects are erased by re-running ``card_gen``'s
#   clearer further upstream in the cascade.

StageClearer = Callable[[str], None]


def _no_artifacts(_set_code: str) -> None:
    """No-op clearer for stages that do not own dedicated artifacts."""
    return None


def _remove_path(path: Path) -> None:
    """Delete ``path`` whether it's a file or a directory; ignore missing."""
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def clear_skeleton(set_code: str) -> None:
    _remove_path(_set_dir(set_code) / "skeleton.json")


def clear_reprints(set_code: str) -> None:
    _remove_path(_set_dir(set_code) / "reprint_selection.json")


def clear_card_gen(set_code: str) -> None:
    """Wipe the entire ``cards/`` directory for the set.

    ``card_gen`` owns the per-card JSON files. Lands, reprints, and
    every later in-place mutator (ai_review, finalize, art_prompts,
    art_select) all touch files in this directory; clearing it on a
    cascade upstream of ``card_gen`` resets all of them at once.
    """
    _remove_path(_set_dir(set_code) / "cards")


def clear_char_portraits(set_code: str) -> None:
    """Delete the character reference portraits.

    Path matches ``mtgai.art.character_portraits`` (out_dir):
    ``<set>/art-direction/character-refs``. The surrounding
    ``art-direction/`` folder also holds visual-references.json,
    which is an upstream input — only the ``character-refs``
    subdirectory belongs to this stage.
    """
    _remove_path(_set_dir(set_code) / "art-direction" / "character-refs")


def clear_art_gen(set_code: str) -> None:
    _remove_path(_set_dir(set_code) / "art")


def clear_rendering(set_code: str) -> None:
    _remove_path(_set_dir(set_code) / "renders")


STAGE_CLEARERS: dict[str, StageClearer] = {
    "skeleton": clear_skeleton,
    "reprints": clear_reprints,
    "lands": _no_artifacts,
    "card_gen": clear_card_gen,
    "balance": _no_artifacts,
    "skeleton_rev": _no_artifacts,
    "ai_review": _no_artifacts,
    "finalize": _no_artifacts,
    "human_card_review": _no_artifacts,
    "art_prompts": _no_artifacts,
    "char_portraits": clear_char_portraits,
    "art_gen": clear_art_gen,
    "art_select": _no_artifacts,
    "human_art_review": _no_artifacts,
    "rendering": clear_rendering,
    "render_qa": _no_artifacts,
    "human_final_review": _no_artifacts,
}


def clear_stage_artifacts(stage_id: str, set_code: str) -> None:
    """Run the registered clearer for ``stage_id`` against ``set_code``.

    Raises ``KeyError`` if no clearer is registered — callers should
    treat that as a programming error (every stage in
    ``STAGE_DEFINITIONS`` must have a clearer entry, even if no-op).
    """
    clearer = STAGE_CLEARERS[stage_id]
    clearer(set_code)
