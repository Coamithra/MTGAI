"""Skeleton knob tuner — phase 0 of the skeleton stage.

Before the deterministic build, this asks an LLM to tune the structural knobs
(:class:`SkeletonKnobs`) to the set's theme via a single structured tool call, then
clamps/validates the result through the knob schema. The LLM proposes; the schema
+ ``generate_skeleton`` dispose, so a hallucinated value can never produce an
illegal skeleton.

Failure handling mirrors the relabel: any LLM/transport/parse failure falls back to
the default knobs (or the caller's pinned base) and flags ``defaulted`` — never a
hard error, so the default skeleton stays usable. Pinned knobs (the user said
"multicolor stays at 24%, you handle the rest") are restored after the AI tune.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from mtgai.generation import temperatures as temps
from mtgai.generation.llm_client import cost_from_result, generate_with_tool
from mtgai.generation.skeleton_prompt_blocks import (
    format_archetypes_block,
    format_card_requests,
    format_constraints_block,
    format_mechanics_block,
    format_setting_block,
)
from mtgai.generation.token_budgets import STANDARD
from mtgai.skeleton.knobs import (
    CYCLE_SPAN_SIZE,
    KNOB_SPECS,
    CycleSpan,
    KnobKind,
    SkeletonKnobs,
    default_knobs,
)

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "pipeline" / "prompts"

_CARD_TYPE_VALUES = ["creature", "instant", "sorcery", "enchantment", "artifact", "land"]


def _read_template(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def _fmt_num(v: float, kind: KnobKind) -> str:
    return str(int(v)) if kind == KnobKind.INT else f"{v:.2f}"


def build_tool_schema() -> dict:
    """Build the ``submit_skeleton_knobs`` tool schema from the knob specs.

    One numeric property per scalar knob (range echoed in its description), an
    ``irregular_subtypes`` enum array (which deciduous specials the theme wants),
    plus a ``cycles`` array. Generated from :data:`KNOB_SPECS` + the irregular
    bucket so the schema can never drift from the validation bounds.
    """
    from mtgai.skeleton.generator import IRREGULAR_SUBTYPE_NAMES

    properties: dict[str, Any] = {}
    for spec in KNOB_SPECS:
        properties[spec.key] = {
            "type": "integer" if spec.kind == KnobKind.INT else "number",
            "description": (
                f"{spec.label}. Default {_fmt_num(spec.default, spec.kind)}, "
                f"range {_fmt_num(spec.min, spec.kind)} to {_fmt_num(spec.max, spec.kind)}."
                + (f" {spec.help}" if spec.help else "")
            ),
        }
    properties["irregular_subtypes"] = {
        "type": "array",
        "description": (
            "WHICH deciduous 'special' subtypes the theme wants, most-fitting first "
            "(e.g. a myth/history theme -> saga; a devotion/temple theme -> shrine; "
            "an eerie/enchantment theme -> enchantment_creature). Pick up to "
            "irregular_subtype_count of them and set that knob to match. Leave EMPTY "
            "when the theme has no preference — a seeded RNG then picks for you."
        ),
        "items": {"type": "string", "enum": list(IRREGULAR_SUBTYPE_NAMES)},
    }
    properties["cycles"] = {
        "type": "array",
        "description": "Structural cycles the theme calls for (often empty).",
        "items": {
            "type": "object",
            "required": ["id", "name", "rarity", "span", "card_type"],
            "properties": {
                "id": {"type": "string", "description": "Short lowercase id, no spaces."},
                "name": {"type": "string"},
                "rarity": {"type": "string", "enum": ["common", "uncommon", "rare", "mythic"]},
                "span": {"type": "string", "enum": [s.value for s in CycleSpan]},
                "card_type": {"type": "string", "enum": _CARD_TYPE_VALUES},
                "cmc_target": {"type": "integer", "description": "0 for lands."},
                "template": {
                    "type": "string",
                    "description": "One-line shared design brief for every member.",
                },
                "notes": {"type": "string"},
            },
        },
    }
    return {
        "name": "submit_skeleton_knobs",
        "description": "Submit the theme-tuned structural knobs for the set skeleton.",
        "input_schema": {"type": "object", "properties": properties},
    }


def _knob_listing() -> str:
    lines: list[str] = []
    for spec in KNOB_SPECS:
        lines.append(
            f"- {spec.key} ({spec.label}): default {_fmt_num(spec.default, spec.kind)}, "
            f"range {_fmt_num(spec.min, spec.kind)} to {_fmt_num(spec.max, spec.kind)}"
        )
    return "\n".join(lines)


def _cycle_span_listing() -> str:
    blurbs = {
        CycleSpan.MONO5: "one per color (W/U/B/R/G)",
        CycleSpan.PAIRS10: "one per two-color pair (10 members) — the guild / dual-land case",
        CycleSpan.ALLIED5: "one per allied pair (5 members)",
        CycleSpan.ENEMY5: "one per enemy pair (5 members)",
        CycleSpan.SHARDS5: "one per allied three-color shard (5 members)",
        CycleSpan.WEDGES5: "one per enemy three-color wedge (5 members)",
    }
    return "\n".join(
        f"- {span.value} ({CYCLE_SPAN_SIZE[span]}): {blurbs[span]}" for span in CycleSpan
    )


def _existing_cycles_listing(base: SkeletonKnobs) -> str:
    """Describe the user's pre-defined cycles so the AI doesn't re-propose or fight them.

    These cycles are carried over verbatim by ``merge_pins_from`` after the tune, so
    the prompt tells the AI to treat them as fixed and only propose *additional*
    cycles the theme wants alongside them.
    """
    if not base.cycles:
        return "(none — propose cycles only if the theme genuinely wants a family.)"
    lines = ["These cycles are already defined and will be KEPT — do not re-propose them:"]
    for c in base.cycles:
        cmc = f", cmc {c.cmc_target}" if c.cmc_target else ""
        tmpl = f" — {c.template}" if c.template else ""
        lines.append(f"- {c.name} ({c.span}, {c.rarity} {c.card_type}{cmc}){tmpl}")
    lines.append("Propose only ADDITIONAL cycles the theme wants beyond these.")
    return "\n".join(lines)


def tune_knobs(
    *,
    theme: dict,
    approved: list[dict],
    archetypes: list[dict],
    set_name: str,
    set_size: int,
    model: str,
    base: SkeletonKnobs | None = None,
    log_dir: Path | None = None,
) -> tuple[SkeletonKnobs, dict]:
    """Run phase 0. Returns (knobs, meta).

    ``meta`` carries ``defaulted`` (True when the LLM call failed and defaults were
    used), ``model_id``, token counts, and ``cost_usd``. ``base``'s pinned knobs are
    restored after the AI tune so a re-roll respects them.
    """
    base = base or default_knobs()
    # Base instructions (system block #1) + the bulk static set context (system
    # block #2, cached) + a short dynamic trigger in the user turn. The two cached
    # system blocks are byte-stable across this run's tune/re-tune calls so a
    # re-roll within the 5-min TTL reads them at ~0.1x. No-op on llamacpp (the
    # blocks flatten to one system string). card_generator.py is the reference.
    system_prompt = _read_template("skeleton_knobs_system.txt").format(
        set_name=set_name or "(unnamed set)",
    )
    context_block = _read_template("skeleton_knobs_context.txt").format(
        setting_block=format_setting_block(theme),
        mechanics_block=format_mechanics_block(approved),
        archetypes_block=format_archetypes_block(archetypes),
        constraints_block=format_constraints_block(
            theme.get("constraints") or theme.get("special_constraints") or []
        ),
        card_requests=format_card_requests(theme.get("card_requests") or []),
        knob_listing=_knob_listing(),
        cycle_spans=_cycle_span_listing(),
        existing_cycles=_existing_cycles_listing(base),
    )
    user_prompt = _read_template("skeleton_knobs_user.txt").format(set_size=set_size)

    from mtgai.settings.model_registry import get_registry

    meta: dict[str, Any] = {
        # Provenance shows the base; `model` is the effective ctx twin used for
        # the generate call.
        "model_id": get_registry().public_model_id(model),
        "defaulted": False,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
    }
    try:
        response = generate_with_tool(
            system_blocks=[(system_prompt, True), (context_block, True)],
            user_prompt=user_prompt,
            tool_schema=build_tool_schema(),
            model=model,
            temperature=temps.BALANCED,
            max_tokens=STANDARD,
            log_dir=log_dir,
        )
    except Exception as exc:  # default-on-failure, never a hard error
        logger.warning("Skeleton knob tuning failed; keeping the base knobs: %s", exc)
        # Fall back to `base`, not `default_knobs()`: `base` already carries the
        # user's pinned knobs AND their defined cycles (a fresh project's `base`
        # IS default_knobs()), so an AI failure can't silently discard them.
        meta["defaulted"] = True
        return base, meta

    result = response.get("result")
    meta["input_tokens"] = response.get("input_tokens", 0)
    meta["output_tokens"] = response.get("output_tokens", 0)
    meta["cost_usd"] = cost_from_result(response)
    if not isinstance(result, dict):
        logger.warning("Skeleton knob tuning returned no tool result; keeping the base knobs")
        meta["defaulted"] = True
        return base, meta  # `base` keeps the user's pinned knobs + cycles

    knobs, warnings = SkeletonKnobs.from_payload(result, source="ai")
    knobs = knobs.merge_pins_from(base)
    for w in warnings:
        logger.info("Skeleton knob tuning clamp: %s", w)
    logger.info(
        "Tuned skeleton knobs (model=%s, cycles=%d, cost=$%.4f)",
        model,
        len(knobs.cycles),
        meta["cost_usd"],
    )
    return knobs, meta


def tune_skeleton_knobs(
    *,
    base: SkeletonKnobs | None = None,
    theme: dict | None = None,
    approved: list[dict] | None = None,
    archetypes: list[dict] | None = None,
) -> tuple[SkeletonKnobs, dict]:
    """Load the active project's set context and run :func:`tune_knobs`.

    Mirrors ``skeleton_relabel.relabel_skeleton``'s self-loading shape so the stage
    and the wizard endpoint can both call it with no arguments. Reads
    ``theme.json`` + ``mechanics/approved.json`` + ``archetypes.json`` unless passed
    in; routes the transcript to ``<asset>/skeleton/logs``.
    """
    import json

    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    settings = project.settings
    model_id = settings.get_llm_model_id("skeleton")
    asset_dir = set_artifact_dir()
    log_dir = asset_dir / "skeleton" / "logs"

    if theme is None:
        theme_path = asset_dir / "theme.json"
        theme = json.loads(theme_path.read_text(encoding="utf-8")) if theme_path.exists() else {}
    if approved is None:
        approved_path = asset_dir / "mechanics" / "approved.json"
        loaded = (
            json.loads(approved_path.read_text(encoding="utf-8")) if approved_path.exists() else []
        )
        approved = loaded if isinstance(loaded, list) else []
    if archetypes is None:
        from mtgai.generation.archetype_generator import load_archetypes

        archetypes = load_archetypes(asset_dir)
    assert theme is not None

    sp = settings.set_params
    return tune_knobs(
        theme=theme,
        approved=approved,
        archetypes=archetypes,
        set_name=sp.set_name or project.set_code or "Custom Set",
        set_size=sp.set_size or 277,
        model=model_id,
        base=base,
        log_dir=log_dir,
    )
