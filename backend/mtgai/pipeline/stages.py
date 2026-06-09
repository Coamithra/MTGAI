"""Stage registry — maps stage_id to actual pipeline function calls.

Each stage runner receives a progress callback + emitter, calls the
appropriate library function, and returns a StageResult with summary
info. The active project (set_code, settings, asset_folder) is read
from :mod:`mtgai.runtime.active_project` — runners no longer take a
``set_code`` parameter. Stages that aren't yet wired to real functions
use stub implementations that log and return immediately.

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

from mtgai.generation.phase_poller import make_poller
from mtgai.io.atomic import atomic_write_text
from mtgai.pipeline.stage_hooks import (
    build_art_prompt_hooks,
    build_card_gen_hooks,
    build_mechanic_hooks,
    build_skeleton_hooks,
    emit_skeleton_done,
    slots_by_id_from_skeleton,
)

if TYPE_CHECKING:
    from mtgai.pipeline.events import StageEmitter
    from mtgai.pipeline.models import ProgressCallback

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_dir() -> Path:
    """Where the active project's artifacts live.

    Thin wrapper around :func:`mtgai.io.asset_paths.set_artifact_dir`
    kept for the by-now-familiar local name. Raises
    :class:`NoAssetFolderError` if no project is open or its
    ``asset_folder`` is empty.
    """
    from mtgai.io.asset_paths import set_artifact_dir

    return set_artifact_dir()


def _is_land_stage_card(card: dict) -> bool:
    """True for a lands-stage basic/dual (collector number ``L-*``).

    Card-gen owns everything else in ``cards/`` (ordinary slots + land *cycles*,
    whose collector numbers are slot ids, not ``L-*``). Mirrors the convention
    the Lands tab uses to scope its own view, and is the single seam both
    :func:`clear_card_gen_cards` and the card_gen refresh endpoint share so the
    Lands tab's output is preserved identically by each.
    """
    return str(card.get("collector_number") or "").upper().startswith("L-")


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
    # Set by a review *gate* that flagged cards: the upstream stage_id to bounce
    # to (always "card_gen"). The engine inserts a fresh instance span
    # [rerun_from … this gate] after the current step and walks forward into it.
    # None on a clean pass (or a non-gate stage).
    rerun_from: str | None = None


# ---------------------------------------------------------------------------
# Stage runners
# ---------------------------------------------------------------------------


def run_mechanics(
    progress_cb: ProgressCallback | None,
    emitter: StageEmitter,
) -> StageResult:
    """Generate the set's custom mechanic candidates.

    First entry in :data:`STAGE_RUNNERS` (mechanics → skeleton →
    reprints → ...). Loads ``theme.json`` + ``set_params``, asks the
    generator for a candidate pool of twice ``mechanic_count`` (produced
    one at a time and validated, to survive local-model JSON degradation), writes
    them to ``<set>/mechanics/candidates.json``, and returns
    ``PAUSED_FOR_REVIEW``-equivalent (the engine flips the status because
    ``mechanics`` defaults to a break-point in
    :data:`mtgai.settings.model_settings.DEFAULT_BREAK_POINTS`).

    The user picks ``mechanic_count`` candidates on the wizard's
    Mechanics tab; the bespoke ``/api/wizard/mechanics/save`` endpoint
    writes ``approved.json`` + sidecars and resumes the engine.
    """
    from mtgai.generation.mechanic_generator import (
        candidate_count,
        detect_keyword_collisions,
        generate_mechanic_candidates,
        known_keyword_set,
        persist_mechanic_selection,
        pick_best_mechanics,
    )
    from mtgai.runtime import ai_lock
    from mtgai.runtime.active_project import require_active_project

    set_dir = _set_dir()
    theme_path = set_dir / "theme.json"
    if not theme_path.exists():
        return StageResult(
            success=False,
            error_message=(
                f"theme.json not found: {theme_path}. "
                "Run theme extraction (Theme tab) before mechanic generation."
            ),
        )

    mech_dir = set_dir / "mechanics"
    mech_dir.mkdir(parents=True, exist_ok=True)
    candidates_path = mech_dir / "candidates.json"

    # Debug: prefab mechanics — skip the LLM council/generation entirely and
    # install the pre-made selection (approved.json + sidecars) from
    # prefab_data/mechanics/. mechanics is a break-point, so the engine still
    # pauses on the Mechanics tab for review; the tab reads the copied
    # candidates.json / approved.json from disk like a normal run.
    if require_active_project().settings.debug.use_prefab_mechanics:
        from mtgai.generation.prefab import install_prefab_mechanics, prefab_mechanics_available

        if prefab_mechanics_available():
            emitter.phase("running", "Installing prefab mechanics")
            approved = install_prefab_mechanics(mech_dir)
            names = [a.get("name", "?") for a in approved]
            emitter.init_sections(
                [
                    {
                        "section_id": "overview",
                        "title": "Mechanic Generation (prefab)",
                        "content_type": "kv",
                        "status": "done",
                        "content": {
                            "Source": "prefab_data/mechanics",
                            "Mechanics": ", ".join(names) or "(none)",
                        },
                    }
                ]
            )
            emitter.phase("done", f"Installed {len(approved)} prefab mechanics")
            return StageResult(
                total_items=len(approved),
                completed_items=len(approved),
                detail=(
                    f"Installed {len(approved)} prefab mechanics — review on the Mechanics tab"
                ),
            )

    sp = require_active_project().settings.set_params
    pool = candidate_count(sp.mechanic_count)

    sections: list[dict] = [
        {
            "section_id": "overview",
            "title": "Mechanic Generation",
            "content_type": "kv",
            "status": "running",
            "content": {
                "Set": sp.set_name or "(unnamed)",
                "Set size": str(sp.set_size),
                "Mechanic count": str(sp.mechanic_count),
                "Candidates requested": str(pool),
            },
        }
    ]
    for i in range(pool):
        sections.append(
            {
                "section_id": f"candidate_{i}",
                "title": f"Candidate {i + 1}",
                "content_type": "mechanic_candidate",
                "status": "pending",
            }
        )
    emitter.init_sections(sections)
    emitter.phase("running", "Calling LLM for mechanic candidates")

    # Per-candidate collision check runs in the ``on_finalized`` hook below so
    # the wizard can render the warning the moment a finalized candidate
    # arrives. Built once (loads a template file) and reused across the loop.
    known_keywords = known_keyword_set()

    with ai_lock.hold("Mechanic generation") as acquired:
        if not acquired:
            return StageResult(
                success=False,
                error_message="Another AI action holds the lock; try again later.",
            )

        # Pre-allocate the merged candidates list so each finalized mechanic
        # can be written to candidates.json immediately — mirrors the
        # refresh-endpoint pattern. Without this, a mid-engine-run F5 on the
        # Mechanics tab reads an empty candidates.json (or stale) and shows
        # nothing; with incremental persist the user sees partial progress
        # on disk that survives reload.
        merged_engine: list[dict] = [{} for _ in range(pool)]

        # Stream candidates into the wizard as they're produced. Each accepted
        # draft fires on_draft (pre-review) and then on_finalized (post-review);
        # the wizard replaces the "Reviewing…" placeholder with the final card.
        # The hooks (shared with the refresh endpoints via ``stage_hooks``) own
        # the event payloads, the ``_ai_generated`` tag, the collision check, and
        # the incremental persist of ``merged_engine`` to candidates.json (so a
        # mid-engine-run F5 reads a snapshot matching the last event).
        #
        # ``emit_phase`` adds the engine's per-candidate progress-strip ticks
        # ("Generating/Reviewing candidate X/N"); without them the strip would
        # freeze on the initial label for the full ~5-minute Gemma run. The
        # refresh path drives the strip with an indeterminate showBusy bar
        # instead, so it leaves phase off.
        hooks = build_mechanic_hooks(
            emitter,
            pool=pool,
            merged=merged_engine,
            candidates_path=candidates_path,
            known_keywords=known_keywords,
            emit_phase=True,
        )

        try:
            with make_poller("mechanics", emitter.phase, activity_prefix="Designing mechanics"):
                response = generate_mechanic_candidates(
                    on_reset=hooks.on_reset,
                    on_draft=hooks.on_draft,
                    on_finalized=hooks.on_finalized,
                    on_council=hooks.on_council,
                )
        except Exception as exc:
            logger.exception("Mechanic generation failed")
            return StageResult(success=False, error_message=str(exc))

        candidates = response["mechanics"]
        # Tag each freshly-LLM-generated candidate with provenance so
        # the wizard's preserve-on-edit contract works across reloads.
        # ``wizard_mechanics.js`` flips this to False on user edits and
        # the refresh-* endpoints preserve it for rows they don't
        # overwrite.
        for mech in candidates:
            mech["_ai_generated"] = True

        # Persist the raw LLM output + emit candidate sections inside
        # the AI lock so a parallel save / refresh can't observe the
        # half-written state.
        atomic_write_text(
            candidates_path,
            json.dumps(candidates, indent=2, ensure_ascii=False),
        )

        collisions = detect_keyword_collisions(candidates)
        for idx, mech in enumerate(candidates):
            emitter.update(
                f"candidate_{idx}",
                status="done",
                content={
                    "mechanic": mech,
                    "collision_with": collisions.get(idx),
                },
            )

        # Auto-pick the best `mechanic_count` so the stage produces its own
        # approved.json + sidecars — the wizard pre-selects these for review,
        # and a non-halting (auto-continue) run proceeds with them. The
        # picker degrades to the first N candidates on any LLM failure, so
        # the stage never auto-continues without a selection on disk.
        emitter.phase("running", "Selecting the best mechanics")
        with make_poller("mechanics", emitter.phase, activity_prefix="Picking the best mechanics"):
            pick = pick_best_mechanics(candidates=candidates)
        approved = persist_mechanic_selection(
            mech_dir,
            candidates,
            pick["picks"],
            source="ai",
            overall_rationale=pick["overall_rationale"],
            selections=pick["selections"],
            model_id=pick["model_id"],
        )
        picked_names = [a.get("name", "?") for a in approved]

    emitter.update(
        "overview",
        status="done",
        content={
            "Set": sp.set_name or "(unnamed)",
            "Set size": str(sp.set_size),
            "Mechanic count": str(sp.mechanic_count),
            "Candidates": str(len(candidates)),
            "AI picks": ", ".join(picked_names) or "(none)",
            "Model": response.get("model_id", "?"),
            "Tokens": (
                f"{response.get('input_tokens', 0)} in / {response.get('output_tokens', 0)} out"
            ),
        },
    )
    emitter.phase(
        "done",
        f"Generated {len(candidates)} candidates; AI picked {len(picked_names)}",
    )

    return StageResult(
        total_items=len(candidates),
        completed_items=len(picked_names),
        detail=f"AI picked {len(picked_names)} mechanics — review on the Mechanics tab",
    )


def run_archetypes(
    progress_cb: ProgressCallback | None,
    emitter: StageEmitter,
) -> StageResult:
    """Generate the set's ten two-color draft archetypes.

    Runs between ``mechanics`` and ``skeleton``. Reads ``theme.json`` +
    ``mechanics/approved.json``, asks the LLM for one archetype per color
    pair, writes them to ``<set>/archetypes.json``, and emits an overview
    + a table of the picks. AUTO stage (no break point) — the engine
    advances straight to ``skeleton`` once it finishes.
    """
    from mtgai.generation.archetype_generator import generate_archetypes
    from mtgai.runtime import ai_lock

    set_dir = _set_dir()
    theme_path = set_dir / "theme.json"
    if not theme_path.exists():
        return StageResult(
            success=False,
            error_message=(
                f"theme.json not found: {theme_path}. "
                "Run theme extraction (Theme tab) before archetype generation."
            ),
        )
    approved_path = set_dir / "mechanics" / "approved.json"
    if not approved_path.exists():
        return StageResult(
            success=False,
            error_message=(
                f"approved.json not found: {approved_path}. "
                "Approve mechanics (Mechanics tab) before archetype generation."
            ),
        )

    emitter.init_sections(
        [
            {
                "section_id": "overview",
                "title": "Archetype Generation",
                "content_type": "kv",
                "status": "running",
            },
            {
                "section_id": "archetypes",
                "title": "Draft Archetypes",
                "content_type": "table",
                "status": "pending",
            },
        ]
    )
    emitter.phase("running", "Calling LLM for draft archetypes")

    with ai_lock.hold("Archetype generation") as acquired:
        if not acquired:
            return StageResult(
                success=False,
                error_message="Another AI action holds the lock; try again later.",
            )

        try:
            with make_poller("archetypes", emitter.phase, activity_prefix="Designing archetypes"):
                response = generate_archetypes()
        except Exception as exc:
            logger.exception("Archetype generation failed")
            return StageResult(success=False, error_message=str(exc))

        archetypes = response["archetypes"]
        archetypes_path = set_dir / "archetypes.json"
        atomic_write_text(
            archetypes_path,
            json.dumps(archetypes, indent=2, ensure_ascii=False),
        )

    rows: list[list[str]] = [["Pair", "Name", "Intent"]]
    for arch in archetypes:
        rows.append(
            [
                str(arch.get("color_pair", "?")),
                str(arch.get("name", "")),
                str(arch.get("description", "")),
            ]
        )
    emitter.update("archetypes", status="done", content={"rows": rows, "scrollable": True})

    emitter.update(
        "overview",
        status="done",
        content={
            "Archetypes": str(len(archetypes)),
            "Model": response.get("model_id", "?"),
            "Tokens": (
                f"{response.get('input_tokens', 0)} in / {response.get('output_tokens', 0)} out"
            ),
        },
    )
    emitter.phase("done", f"Generated {len(archetypes)} draft archetypes")

    return StageResult(
        total_items=len(archetypes),
        completed_items=len(archetypes),
        detail=f"Generated {len(archetypes)} draft archetypes",
    )


def run_visual_refs(
    progress_cb: ProgressCallback | None,
    emitter: StageEmitter,
) -> StageResult:
    """Build the set's art-direction dictionary + artist directory from theme.json.

    Runs just before the art stages (between ``finalize`` and
    ``art_prompts``): ``art_prompts`` + ``char_portraits`` are its only
    consumers, and nothing from ``skeleton`` through ``card_gen`` needs it.
    This is a **transform** over data ``theme.json`` already holds, in three
    LLM steps under one AI-lock hold:

    1. The keyed art-direction dictionary — a consistent, full visual brief
       per setting-specific entity (characters, creature types, factions,
       landmarks) plus set-wide visual motifs + Flux term replacements.
    2. The set-wide ``set_art_direction`` prose, merged into the same file.
    3. The made-up artist directory, written to ``art-direction/artists.json``.

    Outputs land under ``<set>/art-direction/`` — the per-project files the
    art pipeline (``art/visual_reference.py``, ``art/character_portraits.py``,
    ``art_prompts``) consumes. AUTO stage (no break point) — the engine
    advances straight to ``art_prompts``.
    """
    from mtgai.art.visual_reference_extractor import (
        generate_artists,
        generate_set_art_direction,
        generate_visual_references,
    )
    from mtgai.runtime import ai_lock

    set_dir = _set_dir()
    theme_path = set_dir / "theme.json"
    if not theme_path.exists():
        return StageResult(
            success=False,
            error_message=(
                f"theme.json not found: {theme_path}. "
                "Run theme extraction (Theme tab) before the visual-references stage."
            ),
        )

    emitter.init_sections(
        [
            {
                "section_id": "overview",
                "title": "Visual References & Artists",
                "content_type": "kv",
                "status": "running",
            },
            {
                "section_id": "categories",
                "title": "Art-Direction Entities",
                "content_type": "table",
                "status": "pending",
            },
            {
                "section_id": "artists",
                "title": "Artist Directory",
                "content_type": "table",
                "status": "pending",
            },
        ]
    )
    emitter.phase("running", "Transforming theme into art direction")

    with ai_lock.hold("Visual-reference generation") as acquired:
        if not acquired:
            return StageResult(
                success=False,
                error_message="Another AI action holds the lock; try again later.",
            )

        try:
            with make_poller(
                "visual_refs", emitter.phase, activity_prefix="Generating art direction"
            ):
                ref_response = generate_visual_references()
                references = ref_response["references"]
                if ai_lock.is_cancelled():
                    return StageResult(success=False, error_message="Cancelled.")
                set_response = generate_set_art_direction()
                references["set_art_direction"] = set_response["set_art_direction"]
                if ai_lock.is_cancelled():
                    return StageResult(success=False, error_message="Cancelled.")
                artist_response = generate_artists()
        except Exception as exc:
            logger.exception("Visual-reference generation failed")
            return StageResult(success=False, error_message=str(exc))

        art_dir = set_dir / "art-direction"
        art_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            art_dir / "visual-references.json",
            json.dumps(references, indent=2, ensure_ascii=False),
        )
        atomic_write_text(
            art_dir / "artists.json",
            json.dumps({"artists": artist_response["artists"]}, indent=2, ensure_ascii=False),
        )

    category_labels: list[tuple[str, str]] = [
        ("legendary_characters", "Legendary Characters"),
        ("creature_types", "Creature Types"),
        ("factions", "Factions"),
        ("landmarks", "Landmarks"),
    ]
    rows: list[list[str]] = [["Category", "Count", "Entities"]]
    total_entities = 0
    for key, label in category_labels:
        entries = references.get(key) or {}
        total_entities += len(entries)
        names = ", ".join(sorted(entries.keys()))
        rows.append([label, str(len(entries)), names])
    emitter.update("categories", status="done", content={"rows": rows, "scrollable": True})

    artists = artist_response["artists"]
    artist_rows: list[list[str]] = [["Artist", "Style"]]
    for a in artists:
        artist_rows.append([a["name"], a["style_prompt"]])
    emitter.update("artists", status="done", content={"rows": artist_rows, "scrollable": True})

    motifs = references.get("visual_motifs") or []
    replacements = references.get("flux_term_replacements") or {}
    total_in = (
        ref_response.get("input_tokens", 0)
        + set_response.get("input_tokens", 0)
        + artist_response.get("input_tokens", 0)
    )
    total_out = (
        ref_response.get("output_tokens", 0)
        + set_response.get("output_tokens", 0)
        + artist_response.get("output_tokens", 0)
    )
    emitter.update(
        "overview",
        status="done",
        content={
            "Entities": str(total_entities),
            "Flux term replacements": str(len(replacements)),
            "Visual motifs": str(len(motifs)),
            "Artists": str(len(artists)),
            "Set art direction": "set" if references.get("set_art_direction") else "(none)",
            "Model": ref_response.get("model_id", "?"),
            "Tokens": f"{total_in} in / {total_out} out",
        },
    )
    emitter.phase(
        "done", f"Generated {total_entities} art-direction entities + {len(artists)} artists"
    )

    return StageResult(
        total_items=total_entities,
        completed_items=total_entities,
        detail=f"Generated {total_entities} art-direction entities + {len(artists)} artists",
    )


def run_skeleton(
    progress_cb: ProgressCallback | None,
    emitter: StageEmitter,
) -> StageResult:
    """Generate the set skeleton: deterministic default → LLM relabel.

    Two phases in one stage. First builds the deterministic, balanced *default*
    skeleton from the project's set params. Then renders each slot to a one-line
    descriptor and runs the LLM relabel (``skeleton_relabel.relabel_skeleton``):
    Pass 1 rewrites every descriptor to fit the theme / constraints / mechanics,
    Pass 2 places ``card_requests`` onto slots. The rewrite is stored per slot as
    ``tweaked_text`` (card generation's spec); the structured fields stay the
    default so ``reprints`` / ``lands`` read them unchanged. The default skeleton
    is saved before the LLM runs, so a relabel failure leaves a usable (un-themed)
    skeleton the user can re-roll from the Skeleton tab.
    """
    from mtgai.generation.skeleton_knobs_tuner import tune_skeleton_knobs
    from mtgai.generation.skeleton_relabel import relabel_skeleton
    from mtgai.runtime import ai_lock
    from mtgai.runtime.active_project import require_active_project
    from mtgai.skeleton.generator import SetConfig, generate_skeleton, render_slot_string

    set_dir = _set_dir()
    theme_path = set_dir / "theme.json"
    if not theme_path.exists():
        return StageResult(
            success=False,
            error_message=f"Theme not found: {theme_path}. Create one at /pipeline/theme first.",
        )

    emitter.init_sections(
        [
            {"section_id": "overview", "title": "Skeleton Generation", "content_type": "kv"},
            {"section_id": "slots", "title": "Default → Tweaked", "content_type": "table"},
        ]
    )

    theme_data = json.loads(theme_path.read_text(encoding="utf-8"))
    config = SetConfig(**theme_data)
    # set_size + set_name are project parameters (settings.set_params), not
    # theme.json content — theme.json no longer carries them, so SetConfig would
    # otherwise fall back to its dev-set default (60). Pull the real values.
    sp = require_active_project().settings.set_params
    config = config.model_copy(update={"set_size": sp.set_size, "name": sp.set_name or config.name})

    skeleton_path = set_dir / "skeleton.json"
    skeleton_path.parent.mkdir(parents=True, exist_ok=True)

    # Phases 0-2 share one AI-lock hold: phase 0 (knob tuning) and phase 2
    # (relabel) are both LLM calls; the deterministic build (phase 1) sits between
    # them. The default skeleton is saved right after the build, before the
    # relabel — so a relabel failure still leaves a usable (un-themed) skeleton.
    emitter.phase("running", "Tuning the skeleton to fit the set")
    with ai_lock.hold("Skeleton generation") as acquired:
        if not acquired:
            return StageResult(
                success=False,
                error_message="Another AI action holds the lock; try again later.",
            )

        # Phase 0: LLM knob tuning (default-on-failure — never a hard error).
        with make_poller("skeleton", emitter.phase, activity_prefix="Tuning skeleton knobs"):
            knobs, knob_meta = tune_skeleton_knobs(theme=theme_data)

        # Phase 1: deterministic build from the tuned knobs.
        emitter.phase("running", "Building the skeleton")
        result = generate_skeleton(config, knobs=knobs)
        result.knobs_defaulted = bool(knob_meta.get("defaulted"))
        atomic_write_text(
            skeleton_path,
            json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False),
        )
        slot_count = len(result.slots)

        # Phase 2: LLM relabel + request placement. The on_slot/on_reset stream
        # hooks (shared with the refresh endpoint via ``stage_hooks``) clear the
        # tab's provisional rows at the start of every attempt and push each
        # relabeled/placed slot as it lands; the tab's onSkeletonStream handler
        # consumes them.
        emitter.phase("running", "Relabeling the skeleton to fit the set")
        sk_hooks = build_skeleton_hooks(emitter)
        try:
            with make_poller("skeleton", emitter.phase, activity_prefix="Relabeling skeleton"):
                relabel = relabel_skeleton(
                    slots=[s.model_dump() for s in result.slots],
                    # Surface each relabel/assign attempt on the progress strip's
                    # activity line — the relabel retries silently and can take a
                    # while, so "attempt 2/3" is the feedback the user needs.
                    on_progress=lambda msg: emitter.phase("running", msg),
                    on_slot=sk_hooks.on_slot,
                    on_reset=sk_hooks.on_reset,
                )
        except Exception as exc:
            logger.exception("Skeleton relabel failed")
            return StageResult(
                success=False,
                error_message=(
                    f"Default skeleton built ({slot_count} slots) but the relabel failed: {exc}. "
                    "Re-roll from the Skeleton tab."
                ),
            )

        # A user Cancel during the relabel makes relabel_skeleton stop early and
        # return a partial/all-default map — don't apply or persist it over the
        # default skeleton (already saved above). Fail the stage so the engine halts
        # (mirrors card_gen); the user re-rolls from the Skeleton tab.
        if ai_lock.is_cancelled():
            return StageResult(
                success=False,
                error_message=(
                    "Skeleton relabel cancelled by user. The default (un-themed) "
                    "skeleton was kept — re-roll from the Skeleton tab."
                ),
            )

        updates = relabel["updates"]
        for slot in result.slots:
            upd = updates.get(slot.slot_id)
            if not upd:
                continue
            slot.tweaked_text = upd.get("tweaked_text")
            if upd.get("reserved_card"):
                slot.reserved_card = upd["reserved_card"]
        # Persist the relabel outcome so the tab can flag a partial (incomplete)
        # relabel after a reload — kept, not discarded (see relabel_skeleton).
        result.relabeled_slots = int(relabel.get("relabeled", 0))
        result.relabel_incomplete = bool(relabel.get("incomplete"))
        atomic_write_text(
            skeleton_path,
            json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False),
        )
        # Terminal stream event so the Skeleton tab settles its live view (drops
        # the streaming dim, shows the incomplete warning if any) without waiting
        # for the stage to fully complete.
        emit_skeleton_done(
            emitter,
            incomplete=result.relabel_incomplete,
            relabeled=result.relabeled_slots,
        )

    # Default → Tweaked table (the diff the Skeleton tab renders richly).
    changed = 0
    placed = 0
    slot_rows: list[list[str]] = [["Slot", "Default", "Tweaked", "Req"]]
    for slot in result.slots:
        default_text = render_slot_string(slot.model_dump())
        tweaked_text = slot.tweaked_text or default_text
        if tweaked_text != default_text:
            changed += 1
        if slot.reserved_card:
            placed += 1
        slot_rows.append(
            [slot.slot_id, default_text, tweaked_text, "★" if slot.reserved_card else ""]
        )
    emitter.update("slots", status="done", content={"rows": slot_rows, "scrollable": True})

    requested = relabel.get("requests_total", placed)
    placed_str = f"{placed}/{requested}" if requested else str(placed)
    from mtgai.skeleton.knobs import KNOB_SPECS

    total_cost = relabel.get("cost_usd", 0.0) + knob_meta.get("cost_usd", 0.0)
    # How many knobs the tuner moved off their defaults (the "what did the AI do"
    # at the structural level).
    tuned_knobs = sum(1 for spec in KNOB_SPECS if getattr(result.knobs, spec.key) != spec.default)
    knobs_cell = "defaults" if result.knobs_defaulted else f"{tuned_knobs} tuned"
    overview = {
        "Set": config.name or config.code,
        "Slots": str(slot_count),
        "Slots changed": str(changed),
        "Requests placed": placed_str,
        "Knobs": knobs_cell,
        "Model": relabel.get("model_id", "?"),
        "Cost": f"${total_cost:.4f}",
    }
    if result.cycles:
        overview["Cycles"] = ", ".join(c.name for c in result.cycles)
    emitter.update("overview", status="done", content=overview)
    incomplete = bool(relabel.get("incomplete"))
    incomplete_note = " (relabel incomplete — re-roll to finish)" if incomplete else ""
    cycle_note = f", {len(result.cycles)} cycle(s)" if result.cycles else ""
    emitter.phase(
        "done",
        f"Skeleton ready — {slot_count} slots, {changed} relabeled{cycle_note}{incomplete_note}",
    )
    logger.info(
        "Skeleton: %d slots, %d relabeled, %s requests placed, %d cycle(s)%s",
        slot_count,
        changed,
        placed_str,
        len(result.cycles),
        " [INCOMPLETE]" if incomplete else "",
    )
    return StageResult(
        total_items=slot_count,
        completed_items=slot_count,
        cost_usd=total_cost,
        detail=(
            f"Skeleton: {slot_count} slots, {changed} relabeled, "
            f"{placed_str} requests placed{cycle_note}{incomplete_note}"
        ),
    )


def run_reprints(
    progress_cb: ProgressCallback | None,
    emitter: StageEmitter,
) -> StageResult:
    """Select reprints from curated pool."""
    from mtgai.generation.reprint_selector import (
        _load_slot_texts,
        apply_selection_to_skeleton,
        load_reprint_pool,
        select_reprints,
    )
    from mtgai.runtime import ai_lock

    set_dir = _set_dir()
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
    slots = _load_slot_texts(skeleton_path)
    emitter.update(
        "pool",
        status="done",
        content={
            "Pool size": str(len(pool)),
            "Setting-agnostic": str(len(eligible_pool)),
            "Open slots": str(len(slots)),
        },
    )

    emitter.update("selections", status="running", detail="Asking the model to pick…")
    emitter.phase("running", f"Selecting reprints from pool of {len(eligible_pool)}")

    import time as _time

    # Hold the app-wide AI lock for the LLM work (one AI action at a time). This
    # is also what makes the Cancel button work for the engine-driven stage:
    # ai_lock.request_cancel() is a no-op unless the lock is held, and
    # select_reprints polls ai_lock.is_cancelled() between its passes/attempts.
    with ai_lock.hold("Reprint selection") as acquired:
        if not acquired:
            return StageResult(
                success=False,
                error_message="Another AI action holds the lock; try again later.",
            )
        # Spin up a poller so the activity banner shows a prompt-eval heartbeat
        # + generation tok/s during the (potentially long) llamacpp call. make_poller
        # no-ops (NullPoller) for Anthropic, which doesn't expose /slots.
        with make_poller(
            "reprints",
            emitter.phase,
            activity_prefix=f"Selecting reprints (pool={len(eligible_pool)})",
        ):
            result = select_reprints(skeleton_path=skeleton_path)

        # A user Cancel makes select_reprints stop before the placement pass and
        # return a selection with no AI placements — don't persist it. Fail the
        # stage so the engine halts (mirrors run_skeleton / run_card_gen); the
        # user re-rolls from the tab.
        if ai_lock.is_cancelled():
            return StageResult(
                success=False,
                error_message="Reprint selection cancelled by user.",
            )

    count = len(result.selections)
    # Save selection result
    output_path = set_dir / "reprint_selection.json"
    atomic_write_text(
        output_path,
        json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False),
    )

    # Incorporate the picks into the skeleton: stamp each placed slot is_reprint_slot
    # + reprint_card (reset-then-stamp, so a re-run replaces cleanly). Downstream,
    # card-gen skips these slots and the lands fixing investigation drops them from
    # its unfilled-slot view — the reprint is the slot's card now.
    apply_selection_to_skeleton(skeleton_path, result)

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
    progress_cb: ProgressCallback | None,
    emitter: StageEmitter,
) -> StageResult:
    """Generate land cards."""
    import time as _time

    from mtgai.generation.land_generator import generate_lands
    from mtgai.runtime import ai_lock

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
                "Asking for": "basic-land alternates + dual-land investigation",
            },
            detail="Generating…",
        )
        emitter.update("lands", status="running")
        emitter.phase(
            "running",
            f"Calling {provider_label} for land flavor + fixing investigation",
        )

    # Buffer the saved cards so we can stagger their reveal AFTER the LLM
    # calls return. The two calls (basics, then the fixing investigation) yield
    # ~10-20 basic-land alternates plus maybe a dual; emitting them one-by-one
    # with a short sleep gives the UI a cascading fade-in (matches the fade-in
    # CSS) and is much nicer to watch than a "boom, all of them appear" moment.
    saved_cards: list = []

    def _on_card_saved(card) -> None:
        saved_cards.append(card)

    # Hold the app-wide AI lock for the LLM work (one AI action at a time). This
    # is also what makes the Cancel button work for the engine-driven stage:
    # ai_lock.request_cancel() is a no-op unless the lock is held, and
    # generate_lands polls ai_lock.is_cancelled() between its two LLM calls.
    with ai_lock.hold("Land generation") as acquired:
        if not acquired:
            return StageResult(
                success=False,
                error_message="Another AI action holds the lock; try again later.",
            )
        with make_poller("lands", emitter.phase, activity_prefix="Designing lands"):
            result = generate_lands(
                on_call_start=_on_call_start,
                on_card_saved=_on_card_saved,
            )

        # A user Cancel stops generate_lands at a call boundary (it returns a
        # ``cancelled`` shape, keeping any basics already written). Fail the stage
        # so the engine halts instead of marching on to card_gen with a partial
        # land set; a Retry re-runs generate_lands from scratch over the dir.
        if result.get("cancelled") or ai_lock.is_cancelled():
            return StageResult(
                success=False,
                error_message="Land generation cancelled by user.",
            )

    count = result.get("total_cards", 5)
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


def run_card_gen(progress_cb: ProgressCallback | None, emitter: StageEmitter) -> StageResult:
    """Generate cards from skeleton slots.

    Holds the app-wide AI lock for the whole run (one AI action at a time),
    which is also what makes the progress strip's Cancel button work: it hits
    ``/api/ai/cancel`` → ``ai_lock.request_cancel()``, and ``generate_set``'s
    batch loop polls ``ai_lock.is_cancelled()`` to stop at the next batch
    boundary. A user cancel surfaces as a failed stage so the engine halts
    instead of marching on to balance/review on a partial set;
    ``generation_progress.json`` keeps the cards saved so far, so Retry resumes.
    """
    from mtgai.generation.card_generator import generate_set
    from mtgai.runtime import ai_lock

    emitter.phase("running", "Generating cards from skeleton slots")

    # Load the skeleton once so each streamed card tile gets the final
    # relabeled descriptor for its slot — same map shape /state and /refresh
    # build. Empty-on-missing is fine: the tile's ``slot_text`` just stays "".
    # Wrapped wide because ``_set_dir()`` raises ``NoAssetFolderError`` when
    # no project is open, and we want this lookup to be a strict enhancement
    # never a blocker (tests + edge runs without a skeleton still work).
    slots_by_id: dict[str, dict] = {}
    try:
        slots_by_id = slots_by_id_from_skeleton(_set_dir() / "skeleton.json")
    except Exception:
        logger.warning("Failed to read skeleton.json for slot_text lookup", exc_info=True)

    # Stream each saved card to the Card Generation tab as it lands so the
    # grid fills in live (mirrors the skeleton relabel's per-slot streaming).
    # No reset event from the engine path: the first run starts on an empty
    # cards/ dir and a resume must keep existing cards on screen — only the
    # refresh endpoint (which wiped cards/) fires card_gen_reset.
    cg_hooks = build_card_gen_hooks(emitter, slots_by_id=slots_by_id)

    with ai_lock.hold("Card generation") as acquired:
        if not acquired:
            return StageResult(
                success=False,
                error_message="Another AI action holds the lock; try again later.",
            )
        with make_poller("card_gen", emitter.phase, activity_prefix="Generating cards"):
            result = generate_set(
                progress_callback=progress_cb,
                card_saved_callback=cg_hooks.on_card_saved,
            )

    # Terminal phase emission: every other runner (archetypes, visual_refs,
    # reprints, lands) emits ``phase("done", …)`` when it finishes; without it
    # the global progress strip stays stuck on the last ``"running"`` phase
    # because the replay buffer has no terminal event to feed late subscribers.
    # (``pipeline_status: paused`` doesn't clear the strip either — that path
    # only fires for ``completed``/``cancelled``/``failed``.) Emitted on both
    # the cancelled and success exits so the strip clears in either case.
    summary = result.get("summary", "Card generation complete")
    emitter.phase("done", summary)

    if result.get("cancelled"):
        return StageResult(
            success=False,
            total_items=result.get("total_slots", 0),
            completed_items=result.get("filled", 0),
            failed_items=result.get("failed", 0),
            cost_usd=result.get("cost_usd", 0.0),
            error_message=summary,
        )

    return StageResult(
        total_items=result.get("total_slots", 0),
        completed_items=result.get("filled", 0),
        failed_items=result.get("failed", 0),
        cost_usd=result.get("cost_usd", 0.0),
        detail=summary,
    )


def _load_set_cards() -> list:
    """Load every generated card for the active project (empty list if none)."""
    from mtgai.io.card_io import load_card

    cards_dir = _set_dir() / "cards"
    cards = []
    if cards_dir.exists():
        for p in sorted(cards_dir.glob("*.json")):
            try:
                cards.append(load_card(p))
            except Exception:
                logger.warning("Could not load card for review gate: %s", p)
    return cards


def _flag_cards_for_regen(flags: list[tuple[str, str]], flagged_by: str) -> list[dict]:
    """Stamp ``regen_reason`` / ``flagged_by`` on each ``(slot_id, reason)``; save.

    Demotes the card to DRAFT and re-saves it (immutably, via ``model_copy``).
    The persisted flag is what the engine's loop and ``card_gen`` act on. Returns
    one ``{slot_id, card_name, reason}`` per card actually flagged (file found),
    for the gate's result artifact + tab.
    """
    from mtgai.io.card_io import load_card, save_card
    from mtgai.models.card import Card
    from mtgai.models.enums import CardStatus

    set_dir = _set_dir()
    cards_dir = set_dir / "cards"
    # Index by slot_id *and* collector_number: gates flag by slot_id, but
    # ai_review reports by collector_number (CardReviewResult has no slot_id).
    # They're equal for generated cards, but indexing both means a flag is never
    # silently lost if a future scheme diverges them.
    by_slot: dict[str, Card] = {}
    if cards_dir.exists():
        for p in sorted(cards_dir.glob("*.json")):
            try:
                c = load_card(p)
            except Exception:
                continue
            if c.slot_id:
                by_slot[c.slot_id] = c
            if c.collector_number:
                by_slot.setdefault(c.collector_number, c)

    flagged: list[dict] = []
    for slot_id, reason in flags:
        card = by_slot.get(slot_id)
        if card is None:
            logger.warning(
                "Gate %s flagged slot %s but no card found — skipping", flagged_by, slot_id
            )
            continue
        updated = card.model_copy(
            update={
                "regen_reason": reason,
                "flagged_by": flagged_by,
                "status": CardStatus.DRAFT,
            }
        )
        save_card(updated, set_dir=set_dir)
        flagged.append({"slot_id": slot_id, "card_name": card.name, "reason": reason})
    return flagged


def _cards_to_recheck(instance_id: str, cards: list) -> set[str] | None:
    """Card ids a later Conformance & Interactions instance should re-check.

    ``None`` (check the whole pool) for the **backbone** instance
    (``instance_id == "conformance"``) and as a safe fallback whenever the scope
    can't be resolved. For an **inserted** instance (``conformance.2`` …) it
    returns only the cards regenerated since this gate's *previous* instance ran
    — found by diffing the live pool against that instance's output snapshot
    (carried-over cards are byte-identical copies; a regenerated card differs).

    The returned set holds each in-scope card's ``slot_id`` *and*
    ``collector_number`` so both gate steps (conformance keys on ``slot_id``,
    interactions on either) match against it directly.
    """
    from mtgai.pipeline import history
    from mtgai.pipeline.engine import load_state

    state = load_state()
    if state is None:
        return None
    idx = next((i for i, s in enumerate(state.stages) if s.instance_id == instance_id), None)
    if idx is None:
        return None
    stage_id = state.stages[idx].stage_id
    # The reference pool is the nearest *prior* instance of this same gate; the
    # cards changed since it ran are exactly what card_gen just regenerated.
    prior = next((s for s in reversed(state.stages[:idx]) if s.stage_id == stage_id), None)
    if prior is None:
        return None  # backbone / first instance — nothing earlier to scope against
    changed = history.changed_since_snapshot(prior.instance_id)
    if changed is None:
        return None  # missing snapshot (pre-version-tracking) — re-check everything
    ids: set[str] = set()
    for c in cards:
        if (c.collector_number and c.collector_number in changed) or (
            c.slot_id and c.slot_id in changed
        ):
            if c.slot_id:
                ids.add(c.slot_id)
            if c.collector_number:
                ids.add(c.collector_number)
    return ids


def run_conformance(progress_cb: ProgressCallback | None, emitter: StageEmitter) -> StageResult:
    """Merged review gate — conformance + interactions in one stage (stage_id ``conformance``).

    Runs two batched, flag-only, streamed LLM steps back-to-back under one
    AI-lock hold and one tok/s poller (both resolve the shared ``conformance``
    model assignment), each driving one of the tab's two per-card checkboxes:

    1. **Conformance** (``analysis.conformance.check_conformance``) — each card
       vs. its slot spec.
    2. **Interaction Check** (``analysis.interactions.analyze_interactions``) —
       degenerate-combo scan over cumulative-context batches (each batch checks
       its ~40 new cards against all prior cards), flagging each combo's enabler.

    Cards are flagged for regeneration only after *both* steps succeed (a card
    flagged by both gets its reasons joined), so a persistent truncation in
    either step raises out of here with the pool untouched — the engine marks
    the stage FAILED and a re-run starts clean. Either step flagging a card
    bounces the pipeline to ``card_gen``; a clean pass advances to ai_review.
    """
    from mtgai.analysis.conformance import check_conformance
    from mtgai.analysis.duplicates import find_duplicate_names, find_duplicates
    from mtgai.analysis.interactions import analyze_interactions
    from mtgai.runtime import ai_lock

    set_dir = _set_dir()
    skeleton_path = set_dir / "skeleton.json"
    slots_by_id: dict[str, dict] = {}
    if skeleton_path.exists():
        sk = json.loads(skeleton_path.read_text(encoding="utf-8"))
        slots_by_id = {
            s["slot_id"]: s
            for s in (sk.get("slots") or [])
            if isinstance(s, dict) and s.get("slot_id")
        }
    cards = _load_set_cards()
    mechanics: list[dict] = []
    mech_path = set_dir / "mechanics" / "approved.json"
    if mech_path.exists():
        try:
            mechanics = json.loads(mech_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Could not read approved mechanics for interaction check")

    name_by_slot: dict[str, str] = {}
    for c in cards:
        if c.slot_id:
            name_by_slot[c.slot_id] = c.name
        if c.collector_number:
            name_by_slot.setdefault(c.collector_number, c.name)

    # A later instance of this gate re-checks only the cards regenerated since
    # its predecessor ran; the backbone (first) instance checks the whole pool
    # (``recheck is None``). Both LLM steps + the duplicate scan honour the scope.
    recheck = _cards_to_recheck(emitter.instance_id, cards)
    if recheck is not None:
        logger.info(
            "Conformance instance %s scoped to %d regenerated card(s)",
            emitter.instance_id,
            len(recheck),
        )

    with ai_lock.hold("Conformance & Interactions") as acquired:
        if not acquired:
            return StageResult(
                success=False, error_message="Another AI action holds the lock; try again later."
            )

        def _display(pairs: list[tuple[str, str]]) -> list[dict]:
            return [
                {"slot_id": sid, "card_name": name_by_slot.get(sid, ""), "reason": reason}
                for sid, reason in pairs
            ]

        # Each step streams its results to the tab the instant its LLM call
        # returns, so the Conformance and Interaction Check sections fill in
        # independently instead of the tab waiting for the whole stage. The
        # reset tells the tab to (re)render both sections in a "checking" state.
        emitter.event("conformance_reset")

        # Duplicate Check runs first and is purely algorithmic (no LLM call):
        # flag cards functionally identical modulo mana cost, plus cards that
        # share a name with another card (illegal in MTG — the dup-name scan is
        # the only stage that enforces name uniqueness, catching collisions a
        # regen pass can introduce). Both keep the lowest collector number per
        # group. Findings are folded into the per-card conformance checklist
        # below (each starts as an X), rather than shown as a separate section.
        # Bias both scans to flag the regenerated card (not its carried-over
        # twin) so the flag survives the recheck scoping below — otherwise a
        # regen that took the lower collector number would keep the regen card
        # and flag-then-drop the carried-over twin, shipping the collision.
        dup_findings, _dup_analysis = find_duplicates(cards, regenerating=recheck)
        name_findings, _name_analysis = find_duplicate_names(cards, regenerating=recheck)
        dup_by_slot: dict[str, str] = {}
        for f in [*dup_findings, *name_findings]:
            # A card hit by both scans (a same-name functional clone) keeps both
            # reasons so the regen prompt knows to redesign *and* rename.
            dup_by_slot[f.slot_id] = (
                f"{dup_by_slot[f.slot_id]} | {f.reason}" if f.slot_id in dup_by_slot else f.reason
            )
        if recheck is not None:
            # Scope the duplicate hits to the regenerated cards too — an
            # already-vetted carried-over card must not be re-flagged here.
            dup_by_slot = {sid: r for sid, r in dup_by_slot.items() if sid in recheck}

        # Conformance scans the pool in streamed batches (one call per ~40 cards)
        # and fills a live checklist: the full card list up front
        # (conformance_cards), then a verdict per card as the stream resolves it
        # (conformance_card). conf_by_slot holds the latest verdict per slot for
        # the authoritative step snapshot (reload / buffer-cleared); keying by
        # slot_id dedupes a card that re-fires when its batch is retried, while
        # preserving first-seen (listing) order. Seeded from the start list so the
        # snapshot carries every card even if a batch is cancelled mid-run.
        # Duplicates (dup_by_slot) are seeded as failed rows and skip the call.
        conf_by_slot: dict[str, dict] = {}

        def _on_conf_start(card_list: list[dict]) -> None:
            for c in card_list:
                conf_by_slot[c["slot_id"]] = {
                    "slot_id": c["slot_id"],
                    "card_name": c.get("card_name", ""),
                    "conforms": c.get("conforms"),
                    "reason": c.get("reason", ""),
                }
            emitter.event("conformance_cards", cards=card_list)

        def _on_conf_card(rec: dict) -> None:
            conf_by_slot[rec["slot_id"]] = rec
            emitter.event("conformance_card", **rec)

        with make_poller("conformance", emitter.phase, activity_prefix="Reviewing cards"):
            emitter.phase("running", "Checking each card against its slot spec")
            conf_findings, conf_analysis, conf_cost = check_conformance(
                cards,
                slots_by_id,
                pre_flagged=dup_by_slot,
                restrict_to=recheck,
                on_start=_on_conf_start,
                on_card=_on_conf_card,
                on_progress=lambda msg: emitter.phase("running", msg),
                should_cancel=ai_lock.is_cancelled,
            )
            # check_conformance breaks its batch loop early on cancel and
            # returns partial findings. Halt here before the whole-set
            # interactions LLM call (and before any flagging), so a mid-gate
            # Cancel is a clean stop — never partial conformance + full
            # interactions stamped onto cards (matches run_card_gen /
            # run_skeleton / run_reprints cancel semantics).
            if ai_lock.is_cancelled():
                emitter.phase("done", "Conformance & Interactions cancelled")
                return StageResult(success=False, error_message="Conformance cancelled")
            conf_pairs = [(f.slot_id, f.reason) for f in conf_findings]
            conf_step = {
                "id": "conformance",
                "label": "Conformance",
                "flagged": _display(conf_pairs),
                "analysis": conf_analysis,
                "passed": not conf_pairs,
                "cards": list(conf_by_slot.values()),
            }
            emitter.event("conformance_step", step=conf_step)

            emitter.phase("running", "Scanning the pool for degenerate interactions")
            # The interaction step streams the same way as conformance: the full
            # card list up front (interaction_cards), then a per-card verdict as
            # each batch resolves it (interaction_card) — driving the tab's second
            # checkbox per card. inter_by_slot dedupes/keeps the latest verdict per
            # card for the authoritative step snapshot, seeded from the start list.
            inter_by_slot: dict[str, dict] = {}

            def _on_inter_start(card_list: list[dict]) -> None:
                for c in card_list:
                    inter_by_slot[c["slot_id"]] = {
                        "slot_id": c["slot_id"],
                        "card_name": c.get("card_name", ""),
                        "interacts": c.get("interacts"),
                        "reason": c.get("reason", ""),
                    }
                emitter.event("interaction_cards", cards=card_list)

            def _on_inter_card(rec: dict) -> None:
                inter_by_slot[rec["slot_id"]] = rec
                emitter.event("interaction_card", **rec)

            inter_flags, inter_analysis, inter_cost = analyze_interactions(
                cards,
                mechanics,
                new_only=recheck,
                on_start=_on_inter_start,
                on_card=_on_inter_card,
                on_progress=lambda msg: emitter.phase("running", msg),
                should_cancel=ai_lock.is_cancelled,
            )
            if ai_lock.is_cancelled():
                emitter.phase("done", "Conformance & Interactions cancelled")
                return StageResult(success=False, error_message="Interactions cancelled")
            # The interaction reason threads diagnosis + replacement constraint
            # into the regen prompt (vs. the conformance reason, used as-is).
            inter_pairs = [
                (
                    f.enabler_slot_id,
                    (
                        f"Avoid this degenerate interaction: {f.reason}. "
                        f"Replacement constraint: {f.replacement_constraint}"
                    ).strip(),
                )
                for f in inter_flags
            ]
            inter_step = {
                "id": "interactions",
                "label": "Interaction Check",
                "flagged": _display(inter_pairs),
                "analysis": inter_analysis,
                "passed": not inter_pairs,
                "cards": list(inter_by_slot.values()),
            }
            emitter.event("conformance_step", step=inter_step)

    # Merge by slot_id (a card flagged by multiple steps keeps every reason) and
    # flag once. conf_pairs already folds in the duplicate findings (seeded as
    # failed conformance rows), so the duplicates regen alongside the rest.
    merged: dict[str, list[str]] = {}
    for sid, reason in [*conf_pairs, *inter_pairs]:
        merged.setdefault(sid, []).append(reason)
    flagged = _flag_cards_for_regen(
        [(sid, " | ".join(reasons)) for sid, reasons in merged.items()], "conformance"
    )

    n_dups = len(dup_by_slot)
    steps = [conf_step, inter_step]
    emitter.phase("done", f"Conformance & Interactions: {len(flagged)} card(s) flagged")
    detail = (
        f"Conformance & Interactions: {len(flagged)} card(s) flagged for regeneration "
        f"(conformance {len(conf_pairs)} incl. {n_dups} duplicate(s), "
        f"interactions {len(inter_pairs)})"
        if flagged
        else "Conformance & Interactions: all cards conform and the pool is clean"
    )
    return StageResult(
        total_items=len(cards),
        completed_items=len(cards),
        cost_usd=conf_cost + inter_cost,
        detail=detail,
        rerun_from="card_gen" if flagged else None,
        artifacts={"steps": steps, "flagged": flagged, "passed": not flagged},
    )


def run_ai_review(progress_cb: ProgressCallback | None, emitter: StageEmitter) -> StageResult:
    """Design Review gate (hybrid) — council revises in place; flags the unfixable.

    The tiered council + iteration loop is unchanged: it revises cards in place
    (its measured strength). This stage only adds the loop's *escape hatch* — a
    card still rated REVISE after the iteration budget is flagged
    (``flagged_by="ai_review"``) and bounces to ``card_gen`` for a from-scratch
    regen. The loop is the overflow path, not the primary one.
    """
    from mtgai.pipeline.stage_hooks import build_ai_review_hooks
    from mtgai.review.ai_review import review_all_cards
    from mtgai.runtime import ai_lock

    emitter.phase("running", "Reviewing cards")
    # Live-review stream hooks drive the AI Design Review tab's per-card council
    # (thumbs) and stamps. The reset fires once at stage start so a re-run clears
    # the prior run's live council state on any mounted tab.
    hooks = build_ai_review_hooks(emitter)
    # Hold the app-wide AI lock for the whole council loop (one AI action at a
    # time) — this is also what makes the progress strip's Cancel button work:
    # request_cancel() is a no-op unless the lock is held, and review_all_cards
    # polls ai_lock.is_cancelled() at each card boundary. Mirrors run_card_gen.
    with ai_lock.hold("AI design review") as acquired:
        if not acquired:
            return StageResult(
                success=False,
                error_message="Another AI action holds the lock; try again later.",
            )
        with make_poller("ai_review", emitter.phase, activity_prefix="Reviewing cards"):
            result = review_all_cards(
                progress_callback=progress_cb,
                should_cancel=ai_lock.is_cancelled,
                hooks=hooks,
            )

    reviewed = result.get("reviewed", 0)
    revised = result.get("revised", 0)
    unfixable = result.get("unfixable", []) or []

    # A user Cancel halts the loop mid-set, so the unfixable list is partial —
    # don't flag from it. Fail the stage so the engine stops (matches
    # run_card_gen / run_conformance); the per-card reviews completed so far stay
    # saved, so a Retry resumes. Best in-place revisions already applied persist.
    if result.get("cancelled"):
        emitter.phase("done", "AI review cancelled")
        return StageResult(
            success=False,
            total_items=reviewed,
            completed_items=reviewed,
            cost_usd=result.get("cost_usd", 0.0),
            error_message="AI review cancelled by user.",
        )

    flagged = _flag_cards_for_regen([(u["slot_id"], u["reason"]) for u in unfixable], "ai_review")
    detail = f"AI review complete — {reviewed} reviewed, {revised} revised"
    if flagged:
        detail += f", {len(flagged)} flagged for regeneration"
    emitter.phase("done", detail)
    return StageResult(
        total_items=reviewed,
        completed_items=reviewed,
        cost_usd=result.get("cost_usd", 0.0),
        detail=detail,
        rerun_from="card_gen" if flagged else None,
        artifacts={"flagged": flagged},
    )


def run_finalize(progress_cb: ProgressCallback | None, emitter: StageEmitter) -> StageResult:
    """Run post-review finalization (reminder injection + validation + sanity gate).

    After the algorithmic reminder/validate/auto-fix pass, a final LLM **sanity
    check** soft-excludes any card with an obvious unfixable defect (capped at
    :data:`~mtgai.review.finalize.SANITY_CAP_FRACTION`; nondestructive + reversible
    in the Finalization tab). That pass makes LLM calls, so — unlike the old
    lockless finalize — hold the app-wide AI lock for the duration (also what makes
    the strip's Cancel button work: ``request_cancel`` is a no-op unless the lock
    is held, and ``check_sanity`` polls ``is_cancelled`` at each batch boundary),
    wrap a tok/s poller, and stream the sanity checklist to the tab.
    """
    from mtgai.pipeline.stage_hooks import build_sanity_hooks
    from mtgai.review.finalize import finalize_set
    from mtgai.runtime import ai_lock

    emitter.phase("running", "Finalizing cards")
    hooks = build_sanity_hooks(emitter)

    with ai_lock.hold("Finalization") as acquired:
        if not acquired:
            return StageResult(
                success=False,
                error_message="Another AI action holds the lock; try again later.",
            )
        with make_poller("finalize", emitter.phase, activity_prefix="Sanity-checking cards"):
            result = finalize_set(
                on_sanity_start=hooks.on_start,
                on_sanity_card=hooks.on_card,
                on_sanity_progress=hooks.on_progress,
                should_cancel=ai_lock.is_cancelled,
            )

    modified = result.get("cards_modified", 0)
    manual = result.get("total_manual_errors", 0)
    excluded = result.get("excluded_cards", []) or []
    detail = f"Finalized — {modified} cards modified, {manual} manual errors remaining"
    if result.get("sanity_cap_breached"):
        flagged_n = result.get("sanity_flagged_count", 0)
        detail += f"; sanity check flagged {flagged_n} (>cap, none excluded)"
    elif excluded:
        detail += f", {len(excluded)} excluded by sanity check"
    emitter.phase("done", detail)
    return StageResult(
        total_items=result.get("total_cards", 0),
        completed_items=result.get("total_cards", 0),
        cost_usd=result.get("sanity_cost", 0.0),
        detail=detail,
    )


def run_art_prompts(progress_cb: ProgressCallback | None, emitter: StageEmitter) -> StageResult:
    """Generate art prompts for all cards."""
    from mtgai.art.prompt_builder import generate_prompts_for_set
    from mtgai.runtime import ai_lock

    emitter.phase("running", "Writing art prompts")

    # Stream each freshly-prompted card to the Art Prompts tab as it lands (same
    # byte-identical tile shape /state emits), so the grid pops in one card at a
    # time. The engine path does NOT emit a reset — a first run starts empty and a
    # resume must keep already-prompted cards visible (mirrors run_card_gen).
    ap_hooks = build_art_prompt_hooks(emitter)

    # Hold the app-wide AI lock for the whole loop (one AI action at a time) and
    # thread the cancel hook so the Cancel button halts at the next card boundary
    # (request_cancel() is a no-op unless the lock is held). Mirrors run_card_gen.
    with ai_lock.hold("Art prompt generation") as acquired:
        if not acquired:
            return StageResult(
                success=False,
                error_message="Another AI action holds the lock; try again later.",
            )
        with make_poller("art_prompts", emitter.phase, activity_prefix="Writing art prompts"):
            result = generate_prompts_for_set(
                progress_callback=progress_cb,
                should_cancel=ai_lock.is_cancelled,
                card_saved_callback=ap_hooks.on_card_saved,
            )

    processed = result.get("processed", 0)
    if result.get("cancelled"):
        emitter.phase("done", "Art prompt generation cancelled")
        return StageResult(
            success=False,
            total_items=processed + result.get("skipped", 0),
            completed_items=processed,
            cost_usd=result.get("estimated_cost_usd", 0.0),
            error_message="Art prompt generation cancelled by user.",
        )

    emitter.phase("done", f"Generated {processed} art prompts")
    return StageResult(
        total_items=processed + result.get("skipped", 0),
        completed_items=processed,
        cost_usd=result.get("estimated_cost_usd", 0.0),
        detail=f"Generated {processed} art prompts",
    )


def run_set_symbol(progress_cb: ProgressCallback | None, emitter: StageEmitter) -> StageResult:
    """Generate the set's identifying glyph (the type-line symbol).

    Set-identity art direction (sits right after ``visual_refs``): one LLM call
    proposes an iconic emblem from the theme, ComfyUI/Flux renders a few square
    candidates, and each is reduced to a clean 2-tone alpha mask the renderer
    recolors per rarity (replacing the hardcoded placeholder triangle). Holds the
    AI lock for the concept call + Flux loop; the concept tok/s poller is scoped
    to the LLM step only (never the image phase — see card 6a25497b). Candidates
    stream live to the Set Symbol tab.
    """
    from mtgai.art.set_symbol import generate_set_symbol
    from mtgai.pipeline.stage_hooks import build_set_symbol_hooks
    from mtgai.runtime import ai_lock

    emitter.phase("running", "Proposing set-symbol concept")
    hooks = build_set_symbol_hooks(emitter)
    with ai_lock.hold("Set symbol generation") as acquired:
        if not acquired:
            return StageResult(
                success=False,
                error_message="Another AI action holds the lock; try again later.",
            )
        result = generate_set_symbol(
            should_cancel=ai_lock.is_cancelled,
            on_reset=hooks.on_reset,
            on_concept=hooks.on_concept,
            on_version=hooks.on_version,
            concept_poller=make_poller(
                "set_symbol", emitter.phase, activity_prefix="Proposing concept"
            ),
        )

    generated = result.get("generated", 0)
    if result.get("cancelled"):
        emitter.phase("done", "Set symbol cancelled")
        return StageResult(
            success=False,
            total_items=generated,
            completed_items=generated,
            cost_usd=result.get("cost_usd", 0.0),
            error_message="Set symbol generation cancelled by user.",
        )

    # No active glyph at all (every Flux render failed and there's no prior/
    # uploaded symbol): fail loudly rather than completing green while the
    # renderer silently falls back to the placeholder triangle.
    if not result.get("selected_version"):
        emitter.phase("done", "Set symbol generation produced no usable glyph")
        return StageResult(
            success=False,
            total_items=0,
            completed_items=0,
            failed_items=result.get("failed", 0),
            cost_usd=result.get("cost_usd", 0.0),
            error_message="Set symbol generation failed: no candidate glyph was produced.",
        )

    concept = result.get("concept", "set symbol")
    emitter.phase("done", f"Generated {generated} set-symbol candidate(s): {concept}")
    return StageResult(
        total_items=generated,
        completed_items=generated,
        failed_items=result.get("failed", 0),
        cost_usd=result.get("cost_usd", 0.0),
        detail=f"Generated {generated} candidate(s) for '{concept}'",
    )


def run_char_portraits(progress_cb: ProgressCallback | None, emitter: StageEmitter) -> StageResult:
    """Detect recurring entities, generate neutral reference images, attach refs.

    The reworked Character References stage (card 6a20aa84): it reads each card's
    ``art_prompt`` (so it runs after ``art_prompts``), LLM-detects the named
    characters/locations that appear on more than one card, generates a neutral
    canonical reference image per entity (ComfyUI/Flux), and writes
    ``art_character_refs`` back onto the relevant cards for the Art Generation
    stage to consume (PuLID/IP-Adapter). Holds the app-wide AI lock for the LLM
    detection + image loop and threads the cancel hook so the Cancel button halts
    at the next entity/image boundary; entities stream live to the tab.
    """
    from mtgai.art.character_portraits import generate_character_refs
    from mtgai.pipeline.stage_hooks import build_char_refs_hooks
    from mtgai.runtime import ai_lock

    emitter.phase("running", "Finding recurring entities")
    hooks = build_char_refs_hooks(emitter)
    with ai_lock.hold("Character references") as acquired:
        if not acquired:
            return StageResult(
                success=False,
                error_message="Another AI action holds the lock; try again later.",
            )
        # The LLM tok/s poller wraps ONLY the step-1 entity-detection call, NOT
        # the ComfyUI image-generation phase that follows: polling a llama-swap
        # model endpoint during image gen would reload the (deliberately
        # unloaded) LLM into VRAM and starve Flux (card 6a25497b). Pass it down
        # as detect_poller so generate_character_refs scopes it to detection.
        result = generate_character_refs(
            should_cancel=ai_lock.is_cancelled,
            on_reset=hooks.on_reset,
            on_entity_start=hooks.on_entity_start,
            on_entity_image=hooks.on_entity_image,
            detect_poller=make_poller(
                "char_portraits", emitter.phase, activity_prefix="Finding entities"
            ),
        )

    generated = result.get("generated", 0)
    entities = result.get("entities", 0)
    modified = result.get("cards_modified", 0)
    if result.get("cancelled"):
        emitter.phase("done", "Character references cancelled")
        return StageResult(
            success=False,
            total_items=entities,
            completed_items=generated,
            cost_usd=result.get("cost_usd", 0.0),
            error_message="Character references cancelled by user.",
        )

    emitter.phase("done", f"Referenced {entities} recurring entities ({modified} cards updated)")
    return StageResult(
        total_items=entities,
        completed_items=generated,
        failed_items=result.get("failed", 0),
        cost_usd=result.get("cost_usd", 0.0),
        detail=f"Generated references for {entities} entities; attached to {modified} cards",
    )


def run_art_gen(progress_cb: ProgressCallback | None, emitter: StageEmitter) -> StageResult:
    """Merged Art Generation stage: generate best-of-N, judge, human review.

    One cohesive stage (the old ``art_select`` + ``human_art_review`` are folded
    in): for every card it generates ``SetParams.art_versions_per_card`` candidate
    images (provider from the ``art_gen`` image assignment — local Flux/ComfyUI
    direct, OpenAI/Google stubbed), conditions on ``Card.art_character_refs``
    (PuLID/IP-Adapter), then the LLM judge (the ``art_select`` model assignment)
    auto-picks the best per card. The merged Art Generation tab then lets the user
    re-pick / reroll / upload over the auto-pick (its ``review`` break-point is on
    by default).

    The whole span (generate + judge) runs under ONE app-wide AI-lock hold so the
    Cancel button halts it at a card boundary (kept partial output is resumable).
    Per-card art lands stream to the tab as ``art_gen_card`` events; a single
    ``art_gen_reset`` fires at the start.
    """
    from mtgai.art.art_selector import select_art_for_set
    from mtgai.art.image_generator import (
        art_versions_for_card,
        card_names_by_collector_number,
        generate_art_for_set,
    )
    from mtgai.runtime import ai_lock

    emitter.event("art_gen_reset")

    # Resolve the asset dir + cn->name map up front so each per-card emit can
    # attach its art versions cheaply. Best-effort: a missing project (only the
    # case in unit tests that mock the gen funcs) degrades to no-versions tiles
    # rather than failing the stage.
    from mtgai.io.asset_paths import NoAssetFolderError

    try:
        asset_dir: Path | None = _set_dir()
        name_by_cn = card_names_by_collector_number(asset_dir)
    except NoAssetFolderError:
        asset_dir = None
        name_by_cn = {}

    def gen_progress(cn, completed, total, message, cost):
        # Mirror the upstream progress to the stage strip AND stream a per-card
        # tile (with its freshly written art versions) to the merged Art
        # Generation tab so art shows up live, labeled — not only on F5/finish.
        if progress_cb is not None:
            progress_cb(cn, completed, total, message, cost)
        versions = (
            art_versions_for_card(asset_dir, cn, name_by_cn.get(cn, ""))
            if asset_dir is not None
            else []
        )
        emitter.event(
            "art_gen_card",
            collector_number=cn,
            phase="generated",
            detail=message,
            versions=versions,
        )

    def judge_progress(cn, completed, total, message, cost):
        if progress_cb is not None:
            progress_cb(cn, completed, total, message, cost)
        emitter.event("art_gen_card", collector_number=cn, phase="judged", detail=message)

    with ai_lock.hold("Art generation") as acquired:
        if not acquired:
            return StageResult(
                success=False,
                error_message="Another AI action holds the lock; try again later.",
            )

        # No LLM tok/s poller around image generation: this is a pure
        # ComfyUI/Flux phase with NO LLM call, and polling a llama-swap model
        # endpoint here would reload the (deliberately unloaded) LLM into VRAM
        # and starve Flux (card 6a25497b). The per-card art_gen_card events carry
        # the live progress; only the judge phase below gets a poller.
        emitter.phase("running", "Generating art")
        gen_result = generate_art_for_set(
            progress_callback=gen_progress,
            should_cancel=ai_lock.is_cancelled,
        )
        generated = gen_result.get("generated", 0)

        if gen_result.get("cancelled"):
            emitter.phase("done", "Art generation cancelled")
            return StageResult(
                success=False,
                total_items=generated + gen_result.get("skipped", 0),
                completed_items=generated,
                error_message="Art generation cancelled by user.",
            )

        # Best-of-N judge (folded in from the old art_select stage). Same lock
        # hold — one AI action at a time. Resolves the ``art_select`` model.
        emitter.phase("running", "Judging art")
        with make_poller("art_select", emitter.phase, activity_prefix="Judging art"):
            sel_result = select_art_for_set(
                progress_callback=judge_progress,
                should_cancel=ai_lock.is_cancelled,
            )

    reviewed = sel_result.get("reviewed", 0)
    sel_cost = sel_result.get("estimated_cost_usd", 0.0)
    if sel_result.get("cancelled"):
        emitter.phase("done", "Art judging cancelled")
        return StageResult(
            success=False,
            total_items=generated + gen_result.get("skipped", 0),
            completed_items=generated,
            cost_usd=sel_cost,
            error_message="Art judging cancelled by user.",
        )

    judge_failed = sel_result.get("judge_failed", 0)
    judge_skipped = sel_result.get("judge_skipped", 0)
    # ``reviewed`` counts every card that ended with a pick — including the
    # skipped/failed ones that auto-picked v1. Report only the genuinely-judged
    # cards as "judged" so the headline doesn't contradict the skip/fail clauses.
    truly_judged = max(reviewed - judge_skipped - judge_failed, 0)
    detail = f"Generated art for {generated} cards, judged {truly_judged}"
    if gen_result.get("judge_disabled_single_version"):
        # The art_select model is text-only, so best-of-N can't run: the gen step
        # generated 1 version per card (instead of v1..vN) to avoid wasted Flux
        # compute, and the select step auto-picks that single version. Surface it
        # so the run doesn't look like a clean best-of-N pass — the user must
        # assign a vision-capable judge to enable best-of-N. (When the gen step
        # collapses to 1 version the select step counts those as ``auto_single``,
        # not ``judge_skipped``, so this gen-side flag is the signal source.)
        detail += " (best-of-N disabled — art_select model is text-only; 1 version per card)"
    elif judge_skipped:
        # The art_select model is text-only, so best-of-N was skipped entirely
        # (v1 auto-picked). Surface it so the run doesn't look like a clean
        # best-of-N pass — the user must assign a vision-capable judge to enable it.
        # (Reached when multi-version art already existed from a prior vision-judge
        # run, e.g. the judge model was changed to text-only on a resume.)
        detail += (
            f" (best-of-N skipped — art_select model is text-only; {judge_skipped} auto-picked v1)"
        )
    if judge_failed:
        # The vision judge was unavailable (no credits / keyless / local model);
        # those cards fell back to v1 so rendering still has art. Surface it so
        # the tab + state don't silently look like a clean best-of-N pass.
        detail += f" (judge unavailable — defaulted {judge_failed} to v1)"

    emitter.phase("done", detail)
    return StageResult(
        total_items=generated + gen_result.get("skipped", 0),
        completed_items=generated,
        failed_items=gen_result.get("failed", 0),
        cost_usd=sel_cost,
        detail=detail,
    )


def run_rendering(progress_cb: ProgressCallback | None, emitter: StageEmitter) -> StageResult:
    """Render every card to a print-ready image, streaming each into the tab.

    Merged terminal stage (topology reorg): render-only, **no QA / pixel-check
    pass** — detection without remediation is noise at the end of the pipeline.
    The user's two final-review actions (manual field edit, remove card) live on
    the Rendering & Final Review tab and re-render the affected card(s) through
    the per-card endpoints. The stage holds the app-wide AI lock for the whole
    render loop (so the Cancel button can halt it at a card boundary) even though
    rendering isn't an LLM call — it keeps the one-heavy-action-at-a-time
    invariant and the cancel/heal plumbing uniform with the other long runners.

    Streams a ``render_reset`` once, then a ``render_card`` per rendered card so
    the gallery fills in live (mirrors the card_gen / ai_review streams).
    """
    from mtgai.rendering.card_renderer import CardRenderer
    from mtgai.runtime import ai_lock

    emitter.event("render_reset")

    def on_card(cn: str, completed: int, total: int, detail: str, _elapsed: float) -> None:
        emitter.event("render_card", collector_number=cn)
        emitter.phase("running", detail, completed=completed, total=total)
        if progress_cb is not None:
            progress_cb(cn, completed, total, detail, _elapsed)

    renderer = CardRenderer()
    with ai_lock.hold("Rendering") as acquired:
        if not acquired:
            return StageResult(
                success=False,
                error_message="Another AI action holds the lock; try again later.",
            )
        result = renderer.render_set(
            progress_callback=on_card,
            should_cancel=ai_lock.is_cancelled,
        )

    rendered = result.get("rendered", 0)
    if result.get("cancelled"):
        emitter.phase("done", "Rendering cancelled")
        return StageResult(
            success=False,
            total_items=rendered + result.get("skipped", 0),
            completed_items=rendered,
            failed_items=result.get("failed", 0),
            error_message="Rendering cancelled by user.",
        )

    detail = f"Rendered {rendered} cards ({result.get('elapsed_seconds', 0):.1f}s)"
    emitter.phase("done", detail)
    return StageResult(
        total_items=rendered + result.get("skipped", 0),
        completed_items=rendered,
        failed_items=result.get("failed", 0),
        detail=detail,
    )


# ---------------------------------------------------------------------------
# Stage registry
# ---------------------------------------------------------------------------

STAGE_RUNNERS = {
    "mechanics": run_mechanics,
    "archetypes": run_archetypes,
    "skeleton": run_skeleton,
    "reprints": run_reprints,
    "lands": run_lands,
    "card_gen": run_card_gen,
    "conformance": run_conformance,
    "ai_review": run_ai_review,
    "finalize": run_finalize,
    "visual_refs": run_visual_refs,
    "set_symbol": run_set_symbol,
    "art_prompts": run_art_prompts,
    "char_portraits": run_char_portraits,
    "art_gen": run_art_gen,
    "rendering": run_rendering,
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
# - Clearers read the active project's artifact dir and run synchronously.
# - File-not-found is fine (clear is idempotent); permission / I/O
#   errors propagate so the caller can surface them.
# - Stages that only flag cards or mutate them in place (``conformance``,
#   ``ai_review``, ``art_prompts``) intentionally no-op — their effects are erased
#   by re-running ``card_gen``'s clearer further upstream in the cascade.
#   ``finalize`` is the exception: it owns durable reports + reversible per-card
#   sanity markers (which the renderer's hard print gate honours), so it gets a
#   real clearer (:func:`clear_finalize`) instead.

StageClearer = Callable[[], None]


def _no_artifacts() -> None:
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


def clear_mechanics() -> None:
    """Wipe the active project's ``mechanics/`` directory.

    Owns ``candidates.json``, ``approved.json``, ``evergreen-keywords.json``,
    ``pointed-questions.json``, ``functional-tags.json``. Cascading from
    a Theme / Project Settings edit drops everything mechanic-related so
    the next run regenerates from scratch.
    """
    _remove_path(_set_dir() / "mechanics")


def clear_archetypes() -> None:
    """Wipe the active project's archetype artifacts.

    Owns ``archetypes.json`` and the ``archetypes/`` log directory.
    Cascading from a Mechanics / Theme / Project Settings edit drops the
    archetype list so the next run regenerates from the new mechanics.
    """
    _remove_path(_set_dir() / "archetypes.json")
    _remove_path(_set_dir() / "archetypes")


def clear_visual_refs() -> None:
    """Wipe the active project's visual-reference artifacts.

    Owns ``art-direction/visual-references.json`` and the
    ``art-direction/logs/`` directory. The surrounding ``art-direction/``
    folder also holds ``character-refs/`` (owned by ``char_portraits``),
    so this clearer deletes only the file + logs it produced, never the
    whole folder. Cascading from a Theme / Project Settings edit drops the
    references so the next run regenerates from the new prose.
    """
    _remove_path(_set_dir() / "art-direction" / "visual-references.json")
    _remove_path(_set_dir() / "art-direction" / "logs")


def clear_set_symbol() -> None:
    """Wipe the active project's per-set glyph artifacts.

    Owns ``art-direction/set-symbol/`` (the concept, candidate rasters/masks/
    previews, the selected ``symbol.png``, and the stage logs). Removing it drops
    the project glyph so the renderer falls back to the placeholder triangle until
    the stage re-runs. Cascading from an upstream art-direction / theme edit drops
    it so the next run regenerates from the new identity."""
    from mtgai.art.set_symbol import clear_set_symbol as _clear

    _clear()


def clear_skeleton() -> None:
    """Wipe the skeleton + its relabel logs.

    Owns ``skeleton.json`` (default fields + ``tweaked_text``) and the
    ``skeleton/`` log directory (the relabel-pass transcripts). Cascading from
    an Archetypes / Mechanics / Theme edit drops it so the next run rebuilds the
    default and re-relabels.
    """
    _remove_path(_set_dir() / "skeleton.json")
    _remove_path(_set_dir() / "skeleton")


def clear_reprints() -> None:
    """Wipe the reprint selection + its LLM transcripts, and un-stamp the skeleton.

    Owns ``reprint_selection.json`` and the ``reprints/`` log directory (the
    ``assign_reprints`` LLM transcripts). Cascading from a Skeleton / upstream
    edit drops both so the next run re-selects from a clean slate. Also clears the
    ``is_reprint_slot`` / ``reprint_card`` stamps the reprint stage wrote into
    ``skeleton.json``, so those slots return to ordinary generatable slots.
    """
    from mtgai.generation.reprint_selector import reset_reprint_stamps

    set_dir = _set_dir()
    _remove_path(set_dir / "reprint_selection.json")
    _remove_path(set_dir / "reprints")

    skeleton_path = set_dir / "skeleton.json"
    if skeleton_path.exists():
        try:
            skeleton = json.loads(skeleton_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            skeleton = None
        if isinstance(skeleton, dict) and reset_reprint_stamps(skeleton):
            atomic_write_text(skeleton_path, json.dumps(skeleton, indent=2, ensure_ascii=False))


def clear_card_gen_cards() -> None:
    """Delete card_gen-owned artifacts, preserving the Lands tab's ``L-*`` cards.

    Removes every ``cards/*.json`` whose collector number is *not* ``L-*`` (the
    ordinary slots + land cycles card_gen owns), plus ``generation_progress.json``
    and the ``cards/_regen_archive/`` bag. The ``lands`` stage's separately
    generated basics/dual live in the same shared ``cards/`` dir but are owned by
    an earlier stage a cascade may leave un-re-run, so they survive — a card_gen
    reset shouldn't cost the user their lands.

    Shared by :func:`clear_card_gen` (the cascade clearer) and
    ``/api/wizard/card_gen/refresh`` so the two scopings never drift. A malformed
    card JSON is treated as non-land (deleted) — same as the refresh endpoint.
    """
    set_dir = _set_dir()
    cards_dir = set_dir / "cards"
    if cards_dir.exists():
        for path in cards_dir.glob("*.json"):
            try:
                card = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                card = None
            if isinstance(card, dict) and _is_land_stage_card(card):
                continue
            path.unlink(missing_ok=True)
    _remove_path(cards_dir / "_regen_archive")
    _remove_path(set_dir / "generation_progress.json")


def clear_card_gen() -> None:
    """Reset card_gen output, preserving the Lands tab's ``L-*`` cards.

    Delegates to :func:`clear_card_gen_cards`. Historically this wiped the entire
    ``cards/`` directory, which destroyed the ``lands`` stage's ``L-*`` basics/dual
    whenever a cascade reached ``card_gen`` without re-running ``lands`` — directly
    contradicting the refresh endpoint, which preserves them. It is now scoped to
    card_gen-owned cards only (ordinary slots + land cycles) + ``generation_progress.json``
    + ``_regen_archive/``; the in-place mutators downstream (ai_review, finalize,
    art_prompts) still reset via the same cards being regenerated.
    """
    clear_card_gen_cards()


def clear_lands() -> None:
    """Delete the lands stage's ``L-*`` cards and its LLM transcripts.

    The lands stage writes its basics/dual printings into the shared ``cards/``
    dir with ``L-*`` collector numbers — the exact cards :func:`clear_card_gen_cards`
    *preserves* (because lands, not card_gen, owns them). So a cascade that clears a
    stage at/before lands must drop them here, or a partial/failed lands re-run leaves
    stale land cards behind (a successful re-run overwrites them, a failed one does not).
    Uses the shared :func:`_is_land_stage_card` predicate so the L-* convention lives in
    one place. Also wipes the ``lands/`` log directory (``land_generator`` transcripts).
    """
    set_dir = _set_dir()
    cards_dir = set_dir / "cards"
    if cards_dir.exists():
        for path in cards_dir.glob("*.json"):
            try:
                card = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(card, dict) and _is_land_stage_card(card):
                path.unlink(missing_ok=True)
    _remove_path(set_dir / "lands")


def clear_finalize() -> None:
    """Reset the finalize stage's durable artifacts and per-card markers.

    The finalize stage produces two kinds of durable output a stage-clear must
    erase, or a now-PENDING finalize keeps serving stale data:

    - **Reports** (``reports/finalize-report.{json,md}`` + ``reports/finalize-user-edits.json``):
      ``/api/wizard/finalize/state`` reads the JSON sidecar back, so a leftover report
      paints the full *completed* summary (cap-breach banner, auto-edited badges) over a
      reset stage. The sanity gate's LLM transcripts (``finalize/logs/``) go too.
    - **Per-card sanity markers** (``sanity_excluded`` + ``sanity_exclusion_reason``,
      stamped by the finalize sanity gate — ``review/sanity_check.py``): these live on
      ``cards/*.json``, and the renderer + ``/api/wizard/rendering/state`` *hide*
      ``sanity_excluded`` cards (the hard print gate). A stale exclusion from a prior
      finalize run would keep a card hidden across an upstream unlock/regen with no
      current verdict backing it.

    Field-scoped like :func:`clear_card_gen_cards`: card files are NOT deleted (cards are
    card_gen-owned, not finalize-owned); only the two finalize-owned fields are reset in
    place (to ``False`` / ``None``), every other field left untouched. Best-effort +
    idempotent — clearing an already-clean project is a no-op, and malformed/unreadable
    card JSON is skipped.
    """
    set_dir = _set_dir()
    reports_dir = set_dir / "reports"
    _remove_path(reports_dir / "finalize-report.json")
    _remove_path(reports_dir / "finalize-report.md")
    _remove_path(reports_dir / "finalize-user-edits.json")
    _remove_path(set_dir / "finalize")  # sanity-gate LLM transcripts (finalize/logs)

    cards_dir = set_dir / "cards"
    if cards_dir.exists():
        for path in cards_dir.glob("*.json"):
            try:
                card = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(card, dict):
                continue
            if not card.get("sanity_excluded") and card.get("sanity_exclusion_reason") is None:
                continue
            card["sanity_excluded"] = False
            card["sanity_exclusion_reason"] = None
            atomic_write_text(path, json.dumps(card, indent=2, ensure_ascii=False))


def clear_art_prompts() -> None:
    """Clear the art_prompts stage's owned artifact: the unified entity-tags sidecar.

    ``art-direction/entity-tags.json`` is produced at art_prompts time (the single
    source both the appearance-text and image-ref paths read), so a cascade/edit
    re-run must drop it to force re-detection. The authored ``card.art_prompt``
    values themselves live on the card JSON (card_gen-owned) and are not cleared
    here, mirroring the prior no-op clearer.
    """
    from mtgai.art.entity_tags import entity_tags_path

    _remove_path(entity_tags_path(_set_dir()))


def clear_char_portraits() -> None:
    """Delete the character reference portraits.

    Path matches ``mtgai.art.character_portraits`` (out_dir):
    ``<set>/art-direction/character-refs``. The surrounding
    ``art-direction/`` folder also holds visual-references.json,
    which is an upstream input — only the ``character-refs``
    subdirectory belongs to this stage. The stage ALSO writes
    ``art_character_refs`` onto the cards, so a cascade/edit re-run must clear
    those too (else stale refs survive a regenerated entity set).
    """
    from mtgai.art.character_portraits import clear_refs_on_cards

    set_dir = _set_dir()
    _remove_path(set_dir / "art-direction" / "character-refs")
    _remove_path(set_dir / "char_portraits")
    clear_refs_on_cards(set_dir / "cards")


def clear_art_gen() -> None:
    """Wipe the merged art-generation stage's artifacts.

    Owns the generated ``art/`` images plus everything the merged stage writes:
    ``art-generation-logs`` (image-generation transcripts, ``image_generator``),
    ``art-selection-logs`` (the per-card best-of-N pick records the renderer
    reads in ``resolve_art_path``, folded in from the retired ``art_select``
    stage, ``art_selector``), and the ``art_gen/`` dir holding ``decisions.json``
    (the pick + manual-override record). The two log dirs match the log-viewer
    map in ``server.get_stage_logs``. Like the sibling clearers, it also scrubs
    the field the stage stamps onto cards — ``art_path`` — so a regenerated art
    pool isn't shadowed by stale picks pointing at now-deleted PNGs.
    """
    set_dir = _set_dir()
    _remove_path(set_dir / "art")
    _remove_path(set_dir / "art-generation-logs")
    _remove_path(set_dir / "art-selection-logs")
    _remove_path(set_dir / "art_gen")

    cards_dir = set_dir / "cards"
    if cards_dir.exists():
        for path in cards_dir.glob("*.json"):
            try:
                card = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(card, dict) or card.get("art_path") is None:
                continue
            card["art_path"] = None
            atomic_write_text(path, json.dumps(card, indent=2, ensure_ascii=False))


def clear_rendering() -> None:
    _remove_path(_set_dir() / "renders")


STAGE_CLEARERS: dict[str, StageClearer] = {
    "mechanics": clear_mechanics,
    "archetypes": clear_archetypes,
    "skeleton": clear_skeleton,
    "reprints": clear_reprints,
    "lands": clear_lands,
    "card_gen": clear_card_gen,
    "conformance": _no_artifacts,
    "ai_review": _no_artifacts,
    "finalize": clear_finalize,
    "visual_refs": clear_visual_refs,
    "set_symbol": clear_set_symbol,
    "art_prompts": clear_art_prompts,
    "char_portraits": clear_char_portraits,
    "art_gen": clear_art_gen,
    "rendering": clear_rendering,
}


def clear_stage_artifacts(stage_id: str) -> None:
    """Run the registered clearer for ``stage_id`` against the active project.

    Raises ``KeyError`` if no clearer is registered — callers should
    treat that as a programming error (every stage in
    ``STAGE_DEFINITIONS`` must have a clearer entry, even if no-op).
    """
    clearer = STAGE_CLEARERS[stage_id]
    clearer()
