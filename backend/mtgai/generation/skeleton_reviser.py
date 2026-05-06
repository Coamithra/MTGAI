"""Skeleton revision pipeline for Phase 4A-rev.

Given balance analysis findings (mechanic distribution mismatches, complexity
tier mismatches, artifact density gaps), proposes targeted slot changes via LLM
and regenerates only the affected cards.

Usage:
    python -m mtgai.generation.skeleton_reviser           # run revision
    python -m mtgai.generation.skeleton_reviser --dry-run  # propose only, don't regenerate
    python -m mtgai.generation.skeleton_reviser --max-rounds 1  # limit to 1 round
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from mtgai.analysis.balance import analyze_set
from mtgai.generation.card_generator import (
    CARD_TOOL_SCHEMA,
    CARDS_BATCH_TOOL_SCHEMA,
    OUTPUT_ROOT,
    TEMPERATURE,
    GenerationProgress,
    _process_batch_result,
    _save_batch_log,
    group_slots_into_batches,
)
from mtgai.generation.llm_client import cost_from_result, generate_with_tool
from mtgai.generation.prompts import load_system_prompt
from mtgai.io.card_io import load_card
from mtgai.models.card import Card
from mtgai.settings.model_settings import get_effort, get_llm_model

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SET_CODE = "ASD"
SKELETON_PATH = OUTPUT_ROOT / "sets" / DEFAULT_SET_CODE / "skeleton.json"
MECHANICS_PATH = OUTPUT_ROOT / "sets" / DEFAULT_SET_CODE / "mechanics" / "approved.json"
DISTRIBUTION_PATH = OUTPUT_ROOT / "sets" / DEFAULT_SET_CODE / "mechanics" / "distribution.json"
THEME_PATH = OUTPUT_ROOT / "sets" / DEFAULT_SET_CODE / "theme.json"
BALANCE_PATH = OUTPUT_ROOT / "sets" / DEFAULT_SET_CODE / "reports" / "balance-analysis.json"
CARDS_DIR = OUTPUT_ROOT / "sets" / DEFAULT_SET_CODE / "cards"
ARCHIVE_DIR = CARDS_DIR / "archive"
REPORTS_DIR = OUTPUT_ROOT / "sets" / DEFAULT_SET_CODE / "reports"
REVISION_LOG_DIR = OUTPUT_ROOT / "sets" / DEFAULT_SET_CODE / "revision_logs"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class SlotChange(BaseModel):
    """A single proposed change to a skeleton slot."""

    slot_id: str
    current_card_name: str
    action: Literal["regenerate", "modify_slot"]
    new_constraints: dict | None = None
    reasoning: str


class RevisionPlan(BaseModel):
    """LLM-proposed revision plan for the set."""

    analysis: str
    changes: list[SlotChange]
    expected_improvements: dict


class RevisionRound(BaseModel):
    """Record of a single revision round."""

    round_number: int
    timestamp: str
    plan: RevisionPlan
    slots_changed: list[str]
    cards_archived: list[str]
    cards_regenerated: list[str]
    cost_usd: float
    pre_metrics: dict
    post_metrics: dict


class RevisionReport(BaseModel):
    """Full revision report across all rounds."""

    set_code: str
    rounds: list[RevisionRound] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    total_cards_replaced: int = 0


# ---------------------------------------------------------------------------
# Revision log — persist full prompt + response per round
# ---------------------------------------------------------------------------


def _save_revision_log(
    round_num: int,
    system_prompt: str,
    user_prompt: str,
    raw_response: dict,
    parsed_plan: RevisionPlan,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_s: float,
    revision_log_dir: Path = REVISION_LOG_DIR,
    *,
    effort: str | None = None,
) -> Path:
    """Save detailed revision log with full prompts and LLM response."""
    revision_log_dir.mkdir(parents=True, exist_ok=True)
    log_path = revision_log_dir / f"revision_round_{round_num:02d}.json"

    log_data = {
        "round_number": round_num,
        "timestamp": datetime.now(UTC).isoformat(),
        "model": model,
        "temperature": 0.5,
        "effort": effort or "default",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost_usd, 6),
        "latency_s": round(latency_s, 2),
        "prompts": {
            "system_prompt": system_prompt,
            "system_prompt_length": len(system_prompt),
            "user_prompt": user_prompt,
            "user_prompt_length": len(user_prompt),
        },
        "raw_tool_response": raw_response,
        "parsed_plan": {
            "analysis": parsed_plan.analysis,
            "num_changes": len(parsed_plan.changes),
            "changes": [c.model_dump() for c in parsed_plan.changes],
            "expected_improvements": parsed_plan.expected_improvements,
        },
    }

    log_path.write_text(
        json.dumps(log_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Revision log saved: %s", log_path)
    return log_path


# ---------------------------------------------------------------------------
# Step 1: Compact card serialization
# ---------------------------------------------------------------------------


def serialize_card_compact(card: Card) -> str:
    """One-line card summary for LLM prompt.

    Format: slot_id | name | mana_cost | type_line [P/T] | oracle (truncated)
    """
    slot = card.slot_id or card.collector_number or "?"
    name = card.name
    cost = card.mana_cost or ""
    tl = card.type_line

    # Add P/T or loyalty
    stats = ""
    if card.power is not None and card.toughness is not None:
        stats = f" {card.power}/{card.toughness}"
    elif card.loyalty is not None:
        stats = f" [{card.loyalty}]"

    # Truncate oracle text, strip reminder text
    oracle = card.oracle_text or ""
    # Remove reminder text in parens
    oracle = re.sub(r"\([^)]*\)", "", oracle).strip()
    # Collapse whitespace
    oracle = re.sub(r"\s+", " ", oracle)
    # Truncate
    if len(oracle) > 80:
        oracle = oracle[:77] + "..."

    return f"{slot} | {name} | {cost} | {tl}{stats} | {oracle}"


def serialize_all_cards(cards: list[Card]) -> str:
    """Serialize all cards to compact format, one per line."""
    lines = [serialize_card_compact(c) for c in cards]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 2: Revision prompt
# ---------------------------------------------------------------------------

REVISION_TOOL_SCHEMA = {
    "name": "propose_revision_plan",
    "description": "Propose a revision plan to fix structural set-level issues",
    "input_schema": {
        "type": "object",
        "properties": {
            "analysis": {
                "type": "string",
                "description": (
                    "Brief analysis of the structural issues and overall revision strategy"
                ),
            },
            "changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "slot_id": {"type": "string"},
                        "current_card_name": {"type": "string"},
                        "action": {
                            "type": "string",
                            "enum": ["regenerate", "modify_slot"],
                        },
                        "new_constraints": {
                            "type": "object",
                            "description": (
                                "New slot constraints. Only include fields that change."
                            ),
                            "properties": {
                                "card_type": {"type": "string"},
                                "cmc_target": {"type": "integer"},
                                "mechanic_tag": {"type": "string"},
                                "notes": {
                                    "type": "string",
                                    "description": (
                                        "Brief mechanic/structural constraint ONLY, e.g. "
                                        "'Must use Malfunction 2' or "
                                        "'Artifact creature, no Salvage'. "
                                        "Do NOT specify exact ability text, stats, "
                                        "creature types, or keywords — leave creative "
                                        "decisions to the generation model."
                                    ),
                                },
                            },
                        },
                        "reasoning": {"type": "string"},
                    },
                    "required": [
                        "slot_id",
                        "current_card_name",
                        "action",
                        "reasoning",
                    ],
                },
            },
            "expected_improvements": {
                "type": "object",
                "description": ("Expected post-revision mechanic distribution and artifact count"),
                "properties": {
                    "salvage_count": {"type": "integer"},
                    "malfunction_count": {"type": "integer"},
                    "overclock_count": {"type": "integer"},
                    "artifact_count": {"type": "integer"},
                },
            },
        },
        "required": ["analysis", "changes", "expected_improvements"],
    },
}

REVISION_SYSTEM_PROMPT = """\
You are an expert Magic: The Gathering set designer. You analyze set-wide \
structural problems and propose targeted fixes by reassigning skeleton slots.

Your job is to fix SET-LEVEL issues (mechanic distribution, artifact density, \
complexity tier mismatches) — NOT card-level design quality issues. You do this \
by identifying which cards to replace and what constraints the replacement \
cards should have.

Rules:
- Preserve load-bearing cards (signpost uncommons, key removal, archetype \
enablers, reprints)
- Prefer replacing generic/vanilla cards over mechanically interesting ones
- Don't change more slots than necessary
- Each replacement must serve a specific structural need
- New slot constraints must be achievable (valid color/rarity/type/CMC combos)
- A card can serve multiple purposes (e.g., an artifact creature with \
Malfunction fixes both artifact density AND mechanic distribution)"""


def _extract_set_level_issues(balance: dict) -> str:
    """Extract only set-level issues from the balance analysis."""
    lines: list[str] = []

    # Mechanic distribution
    for mech in balance.get("mechanic_distribution", []):
        name = mech["mechanic_name"]
        planned = mech["total_planned"]
        actual = mech["total_actual"]
        if actual != planned:
            direction = "OVER" if actual > planned else "UNDER"
            lines.append(
                f"- {name}: {actual} actual vs {planned} planned ({direction}, "
                f"delta {actual - planned:+d})"
            )

    # Complexity tier mismatches
    tier_issues = [
        i for i in balance.get("issues", []) if i.get("check") == "conformance.mechanic_tier"
    ]
    if tier_issues:
        lines.append(f"\nComplexity tier mismatches ({len(tier_issues)} cards):")
        for issue in tier_issues:
            lines.append(
                f"- {issue['slot_id']} ({issue['card_name']}): "
                f"slot expects {issue['expected']}, card is {issue['actual']}"
            )

    # Degenerate interactions
    interaction_flags = balance.get("interaction_flags", [])
    if interaction_flags:
        lines.append(f"\nDegenerate interactions ({len(interaction_flags)} flagged):")
        for flag in interaction_flags:
            cards = ", ".join(flag.get("cards_involved", []))
            enabler = flag.get("enabler_card", "?")
            slot = flag.get("enabler_slot_id", "?")
            desc = flag.get("description", "")[:120]
            constraint = flag.get("replacement_constraint", "")
            lines.append(f"- [{flag.get('severity', 'WARN')}] {cards}: {desc}")
            lines.append(f"  Enabler: {enabler} ({slot}) — replace with: {constraint}")

    return "\n".join(lines)


def build_revision_prompt(
    cards: list[Card],
    balance: dict,
    mechanics: list[dict],
    distribution: dict,
    theme: dict,
) -> tuple[str, str]:
    """Build (system_prompt, user_prompt) for the revision LLM call."""
    sections: list[str] = []

    # 1. Compact card list
    card_list = serialize_all_cards(cards)
    sections.append(f"## Current Cards in the Set\n\n```\n{card_list}\n```")

    # 2. Balance findings (set-level only)
    issues_text = _extract_set_level_issues(balance)
    sections.append(f"## Structural Issues to Fix\n\n{issues_text}")

    # 3. Mechanic definitions
    mech_lines: list[str] = []
    for mech in mechanics:
        mech_lines.append(f"### {mech['name']}")
        mech_lines.append(f"- Type: {mech['keyword_type']}")
        mech_lines.append(f"- Reminder text: {mech['reminder_text']}")
        mech_lines.append(f"- Colors: {', '.join(mech['colors'])}")
        mech_lines.append(f"- Complexity: {mech['complexity']}")
        rarity_range = mech.get("rarity_range", [])
        if rarity_range:
            mech_lines.append(f"- Appears at: {', '.join(rarity_range)}")
        mech_lines.append(f"- Design notes: {mech['design_notes'][:200]}")
        mech_lines.append("")
    sections.append("## Custom Mechanics\n\n" + "\n".join(mech_lines))

    # 4. Mechanic distribution targets
    dist_lines: list[str] = []
    for mech_name in ("salvage", "malfunction", "overclock"):
        if mech_name in distribution:
            d = distribution[mech_name]
            dist_lines.append(
                f"- {mech_name.title()}: {d['total']} cards planned "
                f"(by rarity: {json.dumps(d['by_rarity'])})"
            )
            # Show assigned slots
            for slot in d.get("slot_assignments", []):
                dist_lines.append(f"  - {slot['slot_id']}: {slot.get('mechanic_usage', '')[:100]}")
    sections.append("## Mechanic Distribution Targets\n\n" + "\n".join(dist_lines))

    # 5. Set theme summary
    sections.append(
        f"## Set Theme\n\n"
        f"**{theme['name']}** ({theme['code']})\n\n"
        f"{theme['theme']}\n\n"
        f"Special constraints: {', '.join(theme.get('special_constraints', []))}"
    )

    # 6. Instructions
    sections.append(
        "## Instructions\n\n"
        "Propose a revision plan to fix the structural issues listed above. "
        "For each change, specify the slot_id, current card name, action "
        "(regenerate or modify_slot), new constraints if modifying the slot, "
        "and reasoning.\n\n"
        "Keep `notes` brief — specify only the mechanic constraint and "
        "structural role (e.g. 'Must use Malfunction 2', 'UB signpost, "
        "needs Overclock'). Do NOT design the card — no ability text, "
        "stats, creature types, or keywords. The generation model handles "
        "creative design.\n\n"
        "Focus on:\n"
        "1. Reducing Salvage count from 12 toward 6 (replace Salvage cards "
        "with cards using Malfunction or Overclock, or simpler cards)\n"
        "2. Increasing Malfunction count from 3 toward 5\n"
        "3. Increasing Overclock count from 1 toward 3\n"
        "4. Fixing complexity tier mismatches where possible\n"
        "5. Consider making some replacements artifact creatures to improve "
        "artifact density\n\n"
        "Reprints (Murder, Elvish Mystic) must NOT be replaced."
    )

    user_prompt = "\n\n---\n\n".join(sections)
    return REVISION_SYSTEM_PROMPT, user_prompt


# ---------------------------------------------------------------------------
# Step 3: Apply revision plan
# ---------------------------------------------------------------------------


def _find_card_file(slot_id: str, cards_dir: Path) -> Path | None:
    """Find the card JSON file for a given slot_id (collector_number)."""
    for p in cards_dir.glob("*.json"):
        if p.name.startswith(f"{slot_id}_"):
            return p
    # Fallback: load and check collector_number
    for p in cards_dir.glob("*.json"):
        try:
            card = load_card(p)
            if card.collector_number == slot_id or card.slot_id == slot_id:
                return p
        except Exception:
            continue
    return None


def archive_card(slot_id: str, cards_dir: Path, archive_dir: Path) -> str | None:
    """Move a card file to the archive directory. Returns archived filename or None."""
    card_file = _find_card_file(slot_id, cards_dir)
    if card_file is None:
        logger.warning("No card file found for slot %s — skipping archive", slot_id)
        return None

    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / card_file.name
    # If already archived, add timestamp suffix
    if dest.exists():
        ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        dest = archive_dir / f"{card_file.stem}_{ts}{card_file.suffix}"

    shutil.move(str(card_file), str(dest))
    logger.info("Archived: %s -> %s", card_file.name, dest.name)
    return dest.name


def update_skeleton_slot(
    skeleton: dict,
    slot_id: str,
    new_constraints: dict,
) -> None:
    """Update a skeleton slot's constraints in-place."""
    for slot in skeleton["slots"]:
        if slot["slot_id"] == slot_id:
            for key, value in new_constraints.items():
                if key in slot:
                    slot[key] = value
                elif key == "notes":
                    slot["notes"] = value
            return
    logger.warning("Slot %s not found in skeleton", slot_id)


def apply_revision_plan(
    plan: RevisionPlan,
    skeleton: dict,
    cards_dir: Path,
    archive_dir: Path,
) -> list[str]:
    """Archive old cards, update skeleton slots.

    Returns list of slot_ids that need regeneration.
    """
    slots_to_regenerate: list[str] = []
    archived: list[str] = []

    for change in plan.changes:
        sid = change.slot_id
        logger.info(
            "Processing change: %s (%s) — %s",
            sid,
            change.current_card_name,
            change.action,
        )

        # Archive the old card
        arch_name = archive_card(sid, cards_dir, archive_dir)
        if arch_name:
            archived.append(arch_name)

        # Apply all new_constraints to the skeleton slot for both actions
        if change.new_constraints:
            update_skeleton_slot(skeleton, sid, change.new_constraints)
            logger.info(
                "  Updated slot constraints: %s",
                json.dumps(change.new_constraints),
            )

        slots_to_regenerate.append(sid)

    return slots_to_regenerate


# ---------------------------------------------------------------------------
# Step 3b: Regenerate slots using existing pipeline
# ---------------------------------------------------------------------------


def regenerate_slots(
    slot_ids: list[str],
    skeleton: dict,
    set_code: str,
    model: str | None = None,
    mechanics_path: Path = MECHANICS_PATH,
    cards_dir: Path = CARDS_DIR,
    revision_log_dir: Path = REVISION_LOG_DIR,
) -> list[Card]:
    """Regenerate specific slots using the 1C card generation pipeline.

    Reuses the existing batch generation infrastructure but only for
    the specified slot_ids.  Pass ``model`` to override the default.
    """
    gen_model = model or get_llm_model("skeleton_rev", set_code)
    gen_effort = get_effort("skeleton_rev", set_code)
    # Get slot dicts for the slots we need to regenerate
    slots_to_gen = [s for s in skeleton["slots"] if s["slot_id"] in slot_ids]

    if not slots_to_gen:
        logger.warning("No slots found to regenerate")
        return []

    # Derive theme path from mechanics_path location
    theme_path = mechanics_path.parent.parent / "theme.json"

    # Load mechanics and theme
    mechanics = json.loads(mechanics_path.read_text(encoding="utf-8"))
    theme = json.loads(theme_path.read_text(encoding="utf-8"))

    # Load existing cards (excluding archived ones — only what's in cards_dir)
    existing_cards: list[Card] = []
    if cards_dir.exists():
        for p in sorted(cards_dir.glob("*.json")):
            try:
                existing_cards.append(load_card(p))
            except Exception:
                logger.warning("Could not load card: %s", p)

    # Create a temporary progress tracker for regeneration
    progress = GenerationProgress.__new__(GenerationProgress)
    progress.path = Path("/dev/null")  # Don't persist this
    progress.filled_slots = {}
    progress.failed_slots = {}
    progress.total_input_tokens = 0
    progress.total_output_tokens = 0
    progress.total_cost_usd = 0.0
    progress.total_api_calls = 0

    # Group into batches and generate
    batches = group_slots_into_batches(slots_to_gen)
    system_prompt = load_system_prompt()
    all_saved: list[Card] = []

    logger.info("Regenerating %d slots in %d batches", len(slot_ids), len(batches))

    for batch_idx, batch in enumerate(batches, 1):
        model = gen_model
        batch_slot_ids = [s["slot_id"] for s in batch]

        logger.info(
            "REGEN BATCH %d/%d [%s]: %s",
            batch_idx,
            len(batches),
            model,
            ", ".join(batch_slot_ids),
        )

        # Build prompt using existing prompts module
        from mtgai.generation.prompts import build_user_prompt

        existing_dicts = [c.model_dump() for c in existing_cards]
        user_prompt = build_user_prompt(batch, mechanics, existing_dicts, theme)

        tool_schema = CARD_TOOL_SCHEMA if len(batch) == 1 else CARDS_BATCH_TOOL_SCHEMA

        try:
            t0 = time.time()
            result = generate_with_tool(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tool_schema=tool_schema,
                model=model,
                temperature=TEMPERATURE,
                max_tokens=8192,
                effort=gen_effort,
            )
            api_latency = time.time() - t0
        except Exception:
            logger.exception("API call failed for regen batch %d", batch_idx)
            for s in batch:
                progress.failed_slots[s["slot_id"]] = "API call failed"
            continue

        batch_cost = cost_from_result(result)
        progress.record_call(
            model,
            result["input_tokens"],
            result["output_tokens"],
            result.get("cache_creation_input_tokens", 0),
            result.get("cache_read_input_tokens", 0),
        )

        logger.info(
            "API response: %d in / %d out tokens, $%.4f, %.1fs",
            result["input_tokens"],
            result["output_tokens"],
            batch_cost,
            api_latency,
        )

        # Normalize result
        raw_data = result["result"]
        raw_cards = [raw_data] if len(batch) == 1 else raw_data.get("cards", [])

        logger.info("Cards returned: %d (expected %d)", len(raw_cards), len(batch))

        # Save batch log to standard generation_logs
        from mtgai.io.asset_paths import set_artifact_dir

        log_dir = set_artifact_dir(set_code) / "generation_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        _save_batch_log(
            batch_idx=900 + batch_idx,  # Use high batch numbers to avoid collision
            slots=batch,
            raw_cards=raw_cards,
            model=model,
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            cost_usd=batch_cost,
            latency_s=api_latency,
            stop_reason=result.get("stop_reason", ""),
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            effort=gen_effort,
        )

        # Also save a copy to revision_logs with full detail
        revision_log_dir.mkdir(parents=True, exist_ok=True)
        regen_log_path = revision_log_dir / f"regen_batch_{batch_idx:02d}.json"
        regen_log_data = {
            "batch_index": batch_idx,
            "slot_ids": batch_slot_ids,
            "timestamp": datetime.now(UTC).isoformat(),
            "model": model,
            "effort": gen_effort or "default",
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "cost_usd": round(batch_cost, 6),
            "latency_s": round(api_latency, 2),
            "stop_reason": result.get("stop_reason", ""),
            "raw_cards": raw_cards,
            "prompts": {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            },
        }
        regen_log_path.write_text(
            json.dumps(regen_log_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Regen log saved: %s", regen_log_path)

        # Process: validate, auto-fix, save
        saved = _process_batch_result(
            raw_cards,
            batch,
            existing_cards,
            mechanics,
            theme,
            model,
            result["input_tokens"],
            result["output_tokens"],
            progress,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            latency_s=api_latency,
            stop_reason=result.get("stop_reason", ""),
            effort=gen_effort,
        )
        all_saved.extend(saved)

    logger.info(
        "Regeneration complete: %d/%d cards saved, $%.4f",
        len(all_saved),
        len(slot_ids),
        progress.total_cost_usd,
    )
    return all_saved


# ---------------------------------------------------------------------------
# Metrics extraction for before/after comparison
# ---------------------------------------------------------------------------


def extract_metrics(balance: dict) -> dict:
    """Extract key metrics from a balance analysis for comparison."""
    metrics: dict = {}

    for mech in balance.get("mechanic_distribution", []):
        name = mech["mechanic_name"].lower()
        metrics[f"{name}_count"] = mech["total_actual"]

    # Count complexity tier mismatches
    tier_mismatches = sum(
        1 for i in balance.get("issues", []) if i.get("check") == "conformance.mechanic_tier"
    )
    metrics["tier_mismatches"] = tier_mismatches

    # Count artifacts (approximate from card types)
    metrics["summary"] = balance.get("summary", {})
    metrics["total_issues"] = balance.get("summary", {}).get("WARN", 0)

    return metrics


# ---------------------------------------------------------------------------
# Revision report generation
# ---------------------------------------------------------------------------


def write_revision_report(report: RevisionReport, path: Path) -> None:
    """Write a human-readable revision report as markdown."""
    lines: list[str] = []
    lines.append("# Skeleton Revision Report")
    lines.append(f"\nSet: {report.set_code}")
    lines.append(f"Total rounds: {len(report.rounds)}")
    lines.append(f"Total cost: ${report.total_cost_usd:.4f}")
    lines.append(f"Total cards replaced: {report.total_cards_replaced}")

    for rnd in report.rounds:
        lines.append(f"\n---\n\n## Round {rnd.round_number}")
        lines.append(f"\nTimestamp: {rnd.timestamp}")
        lines.append(f"Cost: ${rnd.cost_usd:.4f}")
        lines.append(f"\n### Analysis\n\n{rnd.plan.analysis}")

        lines.append(f"\n### Changes ({len(rnd.plan.changes)})")
        for change in rnd.plan.changes:
            lines.append(f"\n- **{change.slot_id}** ({change.current_card_name}) — {change.action}")
            if change.new_constraints:
                lines.append(f"  - New constraints: {json.dumps(change.new_constraints)}")
            lines.append(f"  - Reasoning: {change.reasoning}")

        lines.append("\n### Expected Improvements")
        for key, val in rnd.plan.expected_improvements.items():
            lines.append(f"- {key}: {val}")

        lines.append("\n### Metrics Comparison")
        lines.append("\n| Metric | Before | After |")
        lines.append("| ------ | ------ | ----- |")
        all_keys = set(rnd.pre_metrics) | set(rnd.post_metrics)
        for key in sorted(all_keys):
            if key == "summary":
                continue
            pre = rnd.pre_metrics.get(key, "—")
            post = rnd.post_metrics.get(key, "—")
            lines.append(f"| {key} | {pre} | {post} |")

        lines.append("\n### Regenerated Cards")
        for card_name in rnd.cards_regenerated:
            lines.append(f"- {card_name}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Revision report written: %s", path)


# ---------------------------------------------------------------------------
# Main pipeline: run_revision
# ---------------------------------------------------------------------------


def run_revision(
    set_code: str = DEFAULT_SET_CODE,
    max_rounds: int = 2,
    dry_run: bool = False,
    model: str | None = None,
) -> dict:
    """Full revision pipeline.

    1. Serialize cards compactly
    2. Send to LLM with balance findings
    3. Apply revision plan (archive + update skeleton)
    4. Regenerate affected slots
    5. Re-run balance analysis
    6. Loop if issues remain (max max_rounds)

    Returns:
        Summary dict (model_dump of RevisionReport).
    """
    # Derive all paths from set_code. set_artifact_dir routes to the
    # project's asset_folder when configured, else the legacy
    # output/sets/<CODE>/.
    from mtgai.io.asset_paths import set_artifact_dir

    set_dir = set_artifact_dir(set_code)
    skeleton_path = set_dir / "skeleton.json"
    mechanics_path = set_dir / "mechanics" / "approved.json"
    distribution_path = set_dir / "mechanics" / "distribution.json"
    theme_path = set_dir / "theme.json"
    balance_path = set_dir / "reports" / "balance-analysis.json"
    cards_dir = set_dir / "cards"
    archive_dir = cards_dir / "archive"
    reports_dir = set_dir / "reports"
    revision_log_dir = set_dir / "revision_logs"

    report = RevisionReport(set_code=set_code)

    for round_num in range(1, max_rounds + 1):
        logger.info("=" * 70)
        logger.info("REVISION ROUND %d/%d", round_num, max_rounds)
        logger.info("=" * 70)

        # Load current state
        skeleton = json.loads(skeleton_path.read_text(encoding="utf-8"))
        mechanics = json.loads(mechanics_path.read_text(encoding="utf-8"))
        distribution = json.loads(distribution_path.read_text(encoding="utf-8"))
        theme = json.loads(theme_path.read_text(encoding="utf-8"))
        balance = json.loads(balance_path.read_text(encoding="utf-8"))

        # Load cards
        cards: list[Card] = []
        for p in sorted(cards_dir.glob("*.json")):
            try:
                cards.append(load_card(p))
            except Exception:
                logger.warning("Could not load card: %s", p)

        logger.info("Loaded %d cards", len(cards))

        # Check if there are still set-level issues
        issues_text = _extract_set_level_issues(balance)
        if not issues_text.strip():
            logger.info("No set-level issues found — revision complete")
            break

        logger.info("Set-level issues:\n%s", issues_text)

        # Pre-revision metrics
        pre_metrics = extract_metrics(balance)

        # Build and send revision prompt
        system_prompt, user_prompt = build_revision_prompt(
            cards, balance, mechanics, distribution, theme
        )

        logger.info(
            "Revision prompt: %d chars (system) + %d chars (user)",
            len(system_prompt),
            len(user_prompt),
        )

        if dry_run:
            logger.info("DRY RUN — prompt built but not sent")
            logger.info("System prompt:\n%s", system_prompt[:500])
            logger.info("User prompt (first 2000 chars):\n%s", user_prompt[:2000])
            break

        rev_model = model or get_llm_model("skeleton_rev", set_code)
        rev_effort = get_effort("skeleton_rev", set_code)
        t0 = time.time()
        result = generate_with_tool(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tool_schema=REVISION_TOOL_SCHEMA,
            model=rev_model,
            temperature=0.5,  # Lower temp for analytical task
            max_tokens=8192,
            effort=rev_effort,
        )
        revision_latency = time.time() - t0
        revision_cost = cost_from_result(result)

        logger.info(
            "Revision API: %d in / %d out tokens, $%.4f, %.1fs",
            result["input_tokens"],
            result["output_tokens"],
            revision_cost,
            revision_latency,
        )

        # Parse revision plan
        raw_plan = result["result"]
        plan = RevisionPlan(
            analysis=raw_plan["analysis"],
            changes=[SlotChange(**c) for c in raw_plan["changes"]],
            expected_improvements=raw_plan.get("expected_improvements", {}),
        )

        # Save detailed revision log (full prompts + response)
        _save_revision_log(
            round_num=round_num,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            raw_response=raw_plan,
            parsed_plan=plan,
            model=rev_model,
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            cost_usd=revision_cost,
            latency_s=revision_latency,
            revision_log_dir=revision_log_dir,
            effort=rev_effort,
        )

        logger.info("Revision plan: %d changes proposed", len(plan.changes))
        logger.info("Analysis: %s", plan.analysis[:200])
        for change in plan.changes:
            logger.info(
                "  %s (%s): %s — %s",
                change.slot_id,
                change.current_card_name,
                change.action,
                change.reasoning[:80],
            )

        if not plan.changes:
            logger.info("No changes proposed — revision complete")
            break

        # Apply the plan
        logger.info("\n--- Applying revision plan ---")
        slots_to_regen = apply_revision_plan(plan, skeleton, cards_dir, archive_dir)

        # Save updated skeleton
        skeleton_path.write_text(
            json.dumps(skeleton, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Skeleton updated: %s", skeleton_path)

        # Regenerate affected slots
        logger.info("\n--- Regenerating %d slots ---", len(slots_to_regen))
        regen_cards = regenerate_slots(
            slots_to_regen,
            skeleton,
            set_code,
            model=model,
            mechanics_path=mechanics_path,
            cards_dir=cards_dir,
            revision_log_dir=revision_log_dir,
        )
        regen_cost = sum((a.cost_usd or 0) for c in regen_cards for a in c.generation_attempts)

        # Re-run balance analysis
        logger.info("\n--- Re-running balance analysis ---")
        new_analysis = analyze_set(set_code)
        new_balance = new_analysis.model_dump()

        # Save updated balance analysis
        balance_path.write_text(
            json.dumps(new_balance, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Post-revision metrics
        post_metrics = extract_metrics(new_balance)

        # Record round
        round_cost = revision_cost + regen_cost
        rnd = RevisionRound(
            round_number=round_num,
            timestamp=datetime.now(UTC).isoformat(),
            plan=plan,
            slots_changed=slots_to_regen,
            cards_archived=[c.current_card_name for c in plan.changes],
            cards_regenerated=[c.name for c in regen_cards],
            cost_usd=round_cost,
            pre_metrics=pre_metrics,
            post_metrics=post_metrics,
        )
        report.rounds.append(rnd)
        report.total_cost_usd += round_cost
        report.total_cards_replaced += len(regen_cards)

        logger.info(
            "\nROUND %d COMPLETE: %d cards replaced, $%.4f",
            round_num,
            len(regen_cards),
            round_cost,
        )
        logger.info(
            "Metrics: salvage %s→%s, malfunction %s→%s, overclock %s→%s",
            pre_metrics.get("salvage_count"),
            post_metrics.get("salvage_count"),
            pre_metrics.get("malfunction_count"),
            post_metrics.get("malfunction_count"),
            pre_metrics.get("overclock_count"),
            post_metrics.get("overclock_count"),
        )

    # Write revision report
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "revision-report.md"
    write_revision_report(report, report_path)

    # Also save structured JSON
    json_path = reports_dir / "revision-report.json"
    json_path.write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )

    logger.info("\n" + "=" * 70)
    logger.info("REVISION COMPLETE")
    logger.info("=" * 70)
    logger.info("Rounds: %d", len(report.rounds))
    logger.info("Total cards replaced: %d", report.total_cards_replaced)
    logger.info("Total cost: $%.4f", report.total_cost_usd)
    logger.info("Report: %s", report_path)

    return report.model_dump()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Revise skeleton slots to fix set-level balance issues",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build revision prompt but don't call LLM or regenerate",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=2,
        help="Maximum revision rounds (default: 2)",
    )
    parser.add_argument(
        "--set",
        default=DEFAULT_SET_CODE,
        help=f"Set code (default: {DEFAULT_SET_CODE})",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LLM model override (e.g. claude-haiku-4-5-20251001)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    run_revision(
        set_code=args.set,
        max_rounds=args.max_rounds,
        dry_run=args.dry_run,
        model=args.model,
    )
