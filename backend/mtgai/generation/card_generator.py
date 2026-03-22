"""Card generation pipeline for Phase 1C.

Generates cards from skeleton slots via LLM, validates, auto-fixes, and saves.
MANUAL validation warnings ride along as metadata — no LLM retry on design
issues (that's deferred to the council review in Phase 4A+4B).

Only schema-level parse failures trigger a retry (max 3 attempts), since a
card that can't parse at all can't be saved.

Usage:
    python -m mtgai.generation.card_generator          # generate all unfilled slots
    python -m mtgai.generation.card_generator --resume  # resume from progress file
    python -m mtgai.generation.card_generator --dry-run  # show batches without calling LLM
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from mtgai.generation.llm_client import calc_cost, cost_from_result, generate_with_tool
from mtgai.generation.prompts import build_user_prompt, load_system_prompt
from mtgai.io.card_io import load_card, save_card
from mtgai.models.card import Card, GenerationAttempt
from mtgai.models.enums import CardStatus
from mtgai.validation import ValidationError as VError
from mtgai.validation import validate_card_from_raw

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SET_CODE = "ASD"
OUTPUT_ROOT = Path("C:/Programming/MTGAI/output")
SKELETON_PATH = OUTPUT_ROOT / "sets" / DEFAULT_SET_CODE / "skeleton.json"
MECHANICS_PATH = OUTPUT_ROOT / "sets" / DEFAULT_SET_CODE / "mechanics" / "approved.json"
THEME_PATH = OUTPUT_ROOT / "sets" / DEFAULT_SET_CODE / "theme.json"
PROGRESS_PATH = OUTPUT_ROOT / "sets" / DEFAULT_SET_CODE / "generation_progress.json"
LOG_DIR = OUTPUT_ROOT / "sets" / DEFAULT_SET_CODE / "generation_logs"

# LLM settings — defaults kept as constants for backward compat, but the
# active values come from model_settings at runtime (configured via /settings).
MODEL_DEFAULT = "claude-opus-4-6"
MODEL_SONNET = "claude-sonnet-4-6"
MODEL_OPUS = "claude-opus-4-6"
EFFORT = "max"  # Opus-only; thinking is incompatible with forced tool_choice
TEMPERATURE = 1.0
BATCH_SIZE = 5
MAX_RETRIES = 3  # Only for schema parse failures

# Tool schemas for Anthropic tool_use
CARD_TOOL_SCHEMA = {
    "name": "generate_card",
    "description": "Generate a single MTG card",
    "input_schema": {
        "type": "object",
        "required": [
            "name",
            "mana_cost",
            "type_line",
            "oracle_text",
            "rarity",
            "colors",
            "color_identity",
            "cmc",
        ],
        "properties": {
            "name": {"type": "string"},
            "mana_cost": {
                "type": "string",
                "description": "Mana cost like {2}{W}{U}. Empty string for lands.",
            },
            "cmc": {"type": "number"},
            "colors": {
                "type": "array",
                "items": {"type": "string", "enum": ["W", "U", "B", "R", "G"]},
            },
            "color_identity": {
                "type": "array",
                "items": {"type": "string", "enum": ["W", "U", "B", "R", "G"]},
            },
            "type_line": {"type": "string"},
            "oracle_text": {
                "type": "string",
                "description": "Rules text. Use ~ for self-reference.",
            },
            "flavor_text": {"type": ["string", "null"]},
            "power": {"type": ["string", "null"]},
            "toughness": {"type": ["string", "null"]},
            "loyalty": {"type": ["string", "null"]},
            "rarity": {
                "type": "string",
                "enum": ["common", "uncommon", "rare", "mythic"],
            },
            "design_notes": {"type": "string"},
        },
    },
}

CARDS_BATCH_TOOL_SCHEMA = {
    "name": "generate_cards",
    "description": "Generate multiple MTG cards",
    "input_schema": {
        "type": "object",
        "required": ["cards"],
        "properties": {
            "cards": {
                "type": "array",
                "items": CARD_TOOL_SCHEMA["input_schema"],
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Progress tracking — resumable state
# ---------------------------------------------------------------------------


class GenerationProgress:
    """Tracks which slots have been generated, for resumability."""

    def __init__(self, path: Path = PROGRESS_PATH):
        self.path = path
        self.filled_slots: dict[str, str] = {}  # slot_id -> card file path
        self.failed_slots: dict[str, str] = {}  # slot_id -> last error
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_cost_usd: float = 0.0
        self.total_api_calls: int = 0
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.filled_slots = data.get("filled_slots", {})
            self.failed_slots = data.get("failed_slots", {})
            self.total_input_tokens = data.get("total_input_tokens", 0)
            self.total_output_tokens = data.get("total_output_tokens", 0)
            self.total_cost_usd = data.get("total_cost_usd", 0.0)
            self.total_api_calls = data.get("total_api_calls", 0)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "filled_slots": self.filled_slots,
                    "failed_slots": self.failed_slots,
                    "total_input_tokens": self.total_input_tokens,
                    "total_output_tokens": self.total_output_tokens,
                    "total_cost_usd": round(self.total_cost_usd, 4),
                    "total_api_calls": self.total_api_calls,
                    "last_updated": datetime.now(UTC).isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def record_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
    ) -> None:
        self.total_input_tokens += (
            input_tokens + cache_creation_input_tokens + cache_read_input_tokens
        )
        self.total_output_tokens += output_tokens
        self.total_cost_usd += calc_cost(
            model,
            input_tokens,
            output_tokens,
            cache_creation_input_tokens,
            cache_read_input_tokens,
        )
        self.total_api_calls += 1


# ---------------------------------------------------------------------------
# Batch grouping
# ---------------------------------------------------------------------------


def group_slots_into_batches(
    slots: list[dict],
    batch_size: int = BATCH_SIZE,
) -> list[list[dict]]:
    """Group unfilled skeleton slots into batches for generation.

    Groups by color first (mono-color batches), then multicolor signposts,
    then colorless.  Each batch is at most ``batch_size`` slots.
    """
    by_color: dict[str, list[dict]] = {}
    for slot in slots:
        key = slot.get("color_pair") or slot["color"]
        by_color.setdefault(key, []).append(slot)

    batches: list[list[dict]] = []
    for group in (v for _, v in sorted(by_color.items())):
        for i in range(0, len(group), batch_size):
            batches.append(group[i : i + batch_size])
    return batches


# ---------------------------------------------------------------------------
# Single-card retry for parse failures
# ---------------------------------------------------------------------------


def _retry_single_card(
    slot: dict,
    error_msg: str,
    mechanics: list[dict],
    existing_cards: list,
    theme: dict | None,
    model: str,
    attempt: int,
) -> dict | None:
    """Retry generating a single card that failed to parse.

    Returns the raw LLM result dict, or None if the call fails.
    """
    logger.info(
        "    RETRY attempt %d/%d for slot %s",
        attempt,
        MAX_RETRIES,
        slot["slot_id"],
    )
    system_prompt = load_system_prompt()
    existing_dicts = [c.model_dump() if hasattr(c, "model_dump") else c for c in existing_cards]
    user_prompt = build_user_prompt([slot], mechanics, existing_dicts, theme)
    user_prompt += (
        f"\n\n---\n\nPREVIOUS ATTEMPT FAILED:\n{error_msg}\n\n"
        "Please generate a valid card that fixes these issues."
    )

    logger.debug("    Retry prompt length: %d chars", len(user_prompt))

    try:
        t0 = time.time()
        result = generate_with_tool(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tool_schema=CARD_TOOL_SCHEMA,
            model=model,
            temperature=TEMPERATURE,
            max_tokens=4096,
            effort=_select_effort(),
        )
        latency = time.time() - t0
        cost = cost_from_result(result)
        logger.info(
            "    Retry API response: %d in / %d out tokens, $%.4f, %.1fs%s",
            result["input_tokens"],
            result["output_tokens"],
            cost,
            latency,
            f" (cache read {result['cache_read_input_tokens']})"
            if result.get("cache_read_input_tokens")
            else "",
        )
        return result
    except Exception:
        logger.exception(
            "    API call failed on retry %d for slot %s",
            attempt,
            slot["slot_id"],
        )
        return None


# ---------------------------------------------------------------------------
# Generation log — per-card JSON log for post-mortem analysis
# ---------------------------------------------------------------------------


def _save_generation_log(
    slot_id: str,
    card_name: str,
    attempt: int,
    raw_card: dict,
    errors: list[VError],
    applied_fixes: list[str],
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    *,
    user_prompt: str = "",
    system_prompt: str = "",
    latency_s: float = 0.0,
    stop_reason: str = "",
) -> None:
    """Save a per-card generation log for debugging and prompt iteration."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{slot_id}_attempt{attempt}.json"
    log_data = {
        "slot_id": slot_id,
        "card_name": card_name,
        "attempt": attempt,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost_usd, 6),
        "latency_s": round(latency_s, 2),
        "stop_reason": stop_reason,
        "timestamp": datetime.now(UTC).isoformat(),
        "raw_card_data": raw_card,
        "validation_errors": [e.model_dump() for e in errors],
        "validation_error_count": len(errors),
        "validation_error_summary": [
            f"[{e.severity}] {e.validator}.{e.field}: {e.message}" for e in errors
        ],
        "applied_fixes": applied_fixes,
        "applied_fix_count": len(applied_fixes),
        "prompts": {
            "system_prompt_length": len(system_prompt),
            "user_prompt_length": len(user_prompt),
            "user_prompt": user_prompt,
        },
    }
    log_path.write_text(json.dumps(log_data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Batch-level log — full prompt + all raw responses for the entire batch
# ---------------------------------------------------------------------------


def _save_batch_log(
    batch_idx: int,
    slots: list[dict],
    raw_cards: list[dict],
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_s: float,
    stop_reason: str,
    user_prompt: str,
    system_prompt: str,
) -> None:
    """Save a batch-level log with the full prompt and all raw card data."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    slot_ids = [s["slot_id"] for s in slots]
    log_path = LOG_DIR / f"batch_{batch_idx:03d}.json"
    log_data = {
        "batch_index": batch_idx,
        "slot_ids": slot_ids,
        "slot_count": len(slots),
        "card_count_returned": len(raw_cards),
        "model": model,
        "temperature": TEMPERATURE,
        "effort": _select_effort() or EFFORT,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost_usd, 6),
        "latency_s": round(latency_s, 2),
        "stop_reason": stop_reason,
        "timestamp": datetime.now(UTC).isoformat(),
        "raw_cards": raw_cards,
        "prompts": {
            "system_prompt": system_prompt,
            "system_prompt_length": len(system_prompt),
            "user_prompt": user_prompt,
            "user_prompt_length": len(user_prompt),
        },
    }
    log_path.write_text(json.dumps(log_data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Card preview for console logging
# ---------------------------------------------------------------------------


def _card_one_liner(raw: dict) -> str:
    """Format a card as a compact one-liner for console output."""
    name = raw.get("name", "???")
    cost = raw.get("mana_cost", "")
    tl = raw.get("type_line", "")
    p = raw.get("power")
    t = raw.get("toughness")
    oracle = raw.get("oracle_text", "")
    # Truncate oracle to 60 chars
    oracle_short = oracle[:60].replace("\n", " | ")
    if len(oracle) > 60:
        oracle_short += "..."
    pt = f" {p}/{t}" if p is not None else ""
    return f"{name} {cost} — {tl}{pt} — {oracle_short}"


# ---------------------------------------------------------------------------
# Core generation loop
# ---------------------------------------------------------------------------


def _select_model() -> str:
    """Return the generation model from settings (falls back to Opus default)."""
    from mtgai.settings.model_settings import get_llm_model

    return get_llm_model("card_gen")


def _select_effort() -> str | None:
    """Return the effort level from settings (falls back to 'max')."""
    from mtgai.settings.model_settings import get_effort

    return get_effort("card_gen")


def _process_batch_result(
    raw_cards: list[dict],
    slots: list[dict],
    existing_cards: list,
    mechanics: list[dict],
    theme: dict | None,
    model: str,
    input_tokens: int,
    output_tokens: int,
    progress: GenerationProgress,
    *,
    user_prompt: str = "",
    system_prompt: str = "",
    latency_s: float = 0.0,
    stop_reason: str = "",
) -> list[Card]:
    """Validate, auto-fix, and save each card from a batch result.

    Returns the list of successfully saved Card objects.
    """
    saved: list[Card] = []
    cost_per_card = calc_cost(model, input_tokens, output_tokens) / max(len(raw_cards), 1)

    for i, raw in enumerate(raw_cards):
        slot = slots[i] if i < len(slots) else slots[-1]
        slot_id = slot["slot_id"]

        # Log the raw card as received from LLM
        logger.info("  [%s] Raw LLM output: %s", slot_id, _card_one_liner(raw))

        # Inject pipeline metadata before validation
        raw.setdefault("set_code", DEFAULT_SET_CODE)
        raw.setdefault("collector_number", slot_id)
        raw.setdefault("layout", "normal")

        # Validate + auto-fix
        logger.info("  [%s] Running validation (8 validators)...", slot_id)
        card, errors, applied_fixes = validate_card_from_raw(
            raw,
            existing_cards=existing_cards,
            auto_fix=True,
        )

        card_name = raw.get("name", "UNKNOWN")

        # Log validation results
        if applied_fixes:
            logger.info(
                "  [%s] Auto-fixed %d issue(s):",
                slot_id,
                len(applied_fixes),
            )
            for fix in applied_fixes:
                logger.info("    AUTO-FIX: %s", fix)
        if errors:
            logger.info(
                "  [%s] %d MANUAL warning(s) (will ride along as metadata):",
                slot_id,
                len(errors),
            )
            for err in errors:
                logger.info(
                    "    MANUAL: [%s] %s.%s: %s",
                    err.error_code or "?",
                    err.validator,
                    err.field,
                    err.message,
                )
                if err.suggestion:
                    logger.info("      Suggestion: %s", err.suggestion)
        if not applied_fixes and not errors:
            logger.info("  [%s] Validation CLEAN — no errors, no fixes needed", slot_id)

        # Save per-card log
        _save_generation_log(
            slot_id=slot_id,
            card_name=card_name,
            attempt=1,
            raw_card=raw,
            errors=errors,
            applied_fixes=applied_fixes,
            model=model,
            input_tokens=input_tokens // max(len(raw_cards), 1),
            output_tokens=output_tokens // max(len(raw_cards), 1),
            cost_usd=cost_per_card,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            latency_s=latency_s / max(len(raw_cards), 1),
            stop_reason=stop_reason,
        )

        # Schema failure — card couldn't parse at all.  Retry individually.
        if card is None:
            logger.warning(
                "  [%s] SCHEMA PARSE FAILURE — card couldn't be created. Errors: %s",
                slot_id,
                "; ".join(e.message for e in errors),
            )
            card = _retry_parse_failure(
                slot,
                str(errors),
                mechanics,
                existing_cards,
                theme,
                model,
                progress,
            )
            if card is None:
                logger.error(
                    "  [%s] FAILED after %d retries — flagging for manual review",
                    slot_id,
                    MAX_RETRIES,
                )
                progress.failed_slots[slot_id] = f"Schema parse failure after {MAX_RETRIES} retries"
                progress.save()
                continue

        # Card parsed — set pipeline fields
        update_fields: dict = {
            "set_code": DEFAULT_SET_CODE,
            "collector_number": slot_id,
            "slot_id": slot_id,
            "status": CardStatus.DRAFT,
            "created_at": datetime.now(UTC),
            "generation_attempts": [
                GenerationAttempt(
                    attempt_number=1,
                    timestamp=datetime.now(UTC),
                    model_used=model,
                    success=True,
                    validation_errors=[e.message for e in errors],
                    input_tokens=input_tokens // max(len(raw_cards), 1),
                    output_tokens=output_tokens // max(len(raw_cards), 1),
                    cost_usd=cost_per_card,
                ),
            ],
        }

        # Propagate skeleton metadata to card model
        mechanic_tag = slot.get("mechanic_tag", "")
        if mechanic_tag and mechanic_tag not in ("vanilla", "french_vanilla", "evergreen"):
            update_fields["mechanic_tags"] = [mechanic_tag]
        archetype_tags = slot.get("archetype_tags", [])
        if archetype_tags:
            update_fields["draft_archetype"] = archetype_tags[0]

        card = card.model_copy(update=update_fields)

        # Save card
        path = save_card(card, OUTPUT_ROOT)
        progress.filled_slots[slot_id] = str(path)
        existing_cards.append(card)
        saved.append(card)

        logger.info(
            "  [%s] SAVED: %s -> %s",
            slot_id,
            card.name,
            path.name,
        )

    return saved


def _retry_parse_failure(
    slot: dict,
    error_msg: str,
    mechanics: list[dict],
    existing_cards: list,
    theme: dict | None,
    model: str,
    progress: GenerationProgress,
) -> Card | None:
    """Retry a card that completely failed schema validation (couldn't parse)."""
    for attempt in range(2, MAX_RETRIES + 1):
        result = _retry_single_card(
            slot,
            error_msg,
            mechanics,
            existing_cards,
            theme,
            model,
            attempt,
        )
        if result is None:
            continue

        progress.record_call(
            model,
            result["input_tokens"],
            result["output_tokens"],
            result.get("cache_creation_input_tokens", 0),
            result.get("cache_read_input_tokens", 0),
        )

        retry_raw = result["result"]
        retry_raw.setdefault("set_code", DEFAULT_SET_CODE)
        retry_raw.setdefault("collector_number", slot["slot_id"])
        retry_raw.setdefault("layout", "normal")

        logger.info(
            "    Retry %d raw output: %s",
            attempt,
            _card_one_liner(retry_raw),
        )

        card, errors, applied_fixes = validate_card_from_raw(
            retry_raw,
            existing_cards=existing_cards,
            auto_fix=True,
        )

        # Log retry validation
        if applied_fixes:
            for fix in applied_fixes:
                logger.info("    Retry AUTO-FIX: %s", fix)
        if errors:
            for err in errors:
                logger.info(
                    "    Retry MANUAL: [%s] %s",
                    err.error_code or "?",
                    err.message,
                )

        _save_generation_log(
            slot_id=slot["slot_id"],
            card_name=retry_raw.get("name", "UNKNOWN"),
            attempt=attempt,
            raw_card=retry_raw,
            errors=errors,
            applied_fixes=applied_fixes,
            model=model,
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            cost_usd=cost_from_result(result),
        )

        if card is not None:
            logger.info(
                "    Retry %d SUCCEEDED: %s",
                attempt,
                card.name,
            )
            return card
        logger.warning(
            "    Retry %d FAILED: still can't parse",
            attempt,
        )
        error_msg = str(errors)

    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def generate_set(
    *,
    set_code: str = DEFAULT_SET_CODE,
    dry_run: bool = False,
    resume: bool = True,
    progress_callback: Callable[[str, int, int, str, float], None] | None = None,
) -> dict:
    """Generate all unfilled slots in the skeleton.

    Args:
        set_code: Set code to generate for (default: ASD).
        dry_run: If True, print batches and exit without calling the LLM.
        resume: If True, skip slots already in generation_progress.json.
        progress_callback: Optional (item, completed, total, detail, cost) callback.

    Returns:
        Summary dict with total_slots, filled, failed, cost_usd, summary.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Derive paths from set_code
    set_dir = OUTPUT_ROOT / "sets" / set_code
    skeleton_path = set_dir / "skeleton.json"
    mechanics_path = set_dir / "mechanics" / "approved.json"
    theme_path = set_dir / "theme.json"
    progress_path = set_dir / "generation_progress.json"
    log_dir = set_dir / "generation_logs"

    logger.info("=" * 70)
    logger.info("MTGAI Card Generation Pipeline — Phase 1C")
    logger.info("=" * 70)
    active_model = _select_model()
    active_effort = _select_effort()
    logger.info(
        "Model: %s | Effort: %s | Temp: %s | Batch size: %d",
        active_model,
        active_effort or "default",
        TEMPERATURE,
        BATCH_SIZE,
    )
    logger.info("Set: %s | Output: %s", set_code, OUTPUT_ROOT)
    logger.info("Logs: %s", log_dir)
    logger.info("")

    # Load inputs
    skeleton = json.loads(skeleton_path.read_text(encoding="utf-8"))
    mechanics = json.loads(mechanics_path.read_text(encoding="utf-8"))
    theme = json.loads(theme_path.read_text(encoding="utf-8"))

    logger.info(
        "Loaded: skeleton (%d slots), %d mechanics, theme '%s'",
        len(skeleton["slots"]),
        len(mechanics),
        theme.get("name", "?"),
    )

    progress = GenerationProgress(path=progress_path)
    if progress.total_api_calls > 0:
        logger.info(
            "Resuming: %d filled, %d failed, %d API calls so far ($%.4f)",
            len(progress.filled_slots),
            len(progress.failed_slots),
            progress.total_api_calls,
            progress.total_cost_usd,
        )

    # Filter to unfilled slots
    all_slots = skeleton["slots"]
    if resume:
        unfilled = [
            s
            for s in all_slots
            if s["slot_id"] not in progress.filled_slots
            and s["slot_id"] not in progress.failed_slots
        ]
    else:
        unfilled = [s for s in all_slots if s.get("card_id") is None]

    logger.info(
        "Slots: %d total, %d filled, %d failed, %d to generate",
        len(all_slots),
        len(progress.filled_slots),
        len(progress.failed_slots),
        len(unfilled),
    )

    if not unfilled:
        logger.info("Nothing to generate — all slots filled or failed.")
        return

    # Load existing cards for set context + uniqueness checks
    cards_dir = set_dir / "cards"
    existing_cards: list[Card] = []
    if cards_dir.exists():
        for p in sorted(cards_dir.glob("*.json")):
            try:
                existing_cards.append(load_card(p))
            except Exception:
                logger.warning("Could not load existing card: %s", p)
    logger.info("Loaded %d existing cards for set context", len(existing_cards))

    # Group into batches
    batches = group_slots_into_batches(unfilled)

    logger.info("")
    logger.info("Planned: %d batches (%d cards)", len(batches), len(unfilled))
    for i, batch in enumerate(batches, 1):
        slot_ids = [s["slot_id"] for s in batch]
        logger.info("  Batch %d: %s", i, ", ".join(slot_ids))
    logger.info("")

    if dry_run:
        logger.info("DRY RUN — no API calls made.")
        return {
            "total_slots": len(all_slots),
            "filled": len(progress.filled_slots),
            "failed": len(progress.failed_slots),
            "cost_usd": 0.0,
            "summary": "Dry run — no API calls made",
        }

    # Generate!
    system_prompt = load_system_prompt()
    logger.info("System prompt loaded: %d chars", len(system_prompt))
    total_saved = 0
    start_time = time.time()

    for batch_idx, batch in enumerate(batches, 1):
        model = _select_model()
        slot_ids = [s["slot_id"] for s in batch]
        batch_start = time.time()

        logger.info("=" * 60)
        logger.info(
            "BATCH %d/%d [%s] — %d cards: %s",
            batch_idx,
            len(batches),
            model,
            len(batch),
            ", ".join(slot_ids),
        )
        logger.info("-" * 60)

        # Log slot details
        for slot in batch:
            logger.info(
                "  Slot %s: %s %s %s, CMC ~%d, mechanic=%s%s",
                slot["slot_id"],
                slot["color"],
                slot["rarity"],
                slot["card_type"],
                slot["cmc_target"],
                slot.get("mechanic_tag", "-"),
                f", pair={slot['color_pair']}" if slot.get("color_pair") else "",
            )

        existing_dicts = [c.model_dump() for c in existing_cards]
        user_prompt = build_user_prompt(batch, mechanics, existing_dicts, theme)
        logger.info(
            "Prompt built: %d chars (system) + %d chars (user) = %d total",
            len(system_prompt),
            len(user_prompt),
            len(system_prompt) + len(user_prompt),
        )

        tool_schema = CARD_TOOL_SCHEMA if len(batch) == 1 else CARDS_BATCH_TOOL_SCHEMA
        logger.info(
            "Tool schema: %s (batch=%s)",
            tool_schema["name"],
            len(batch) > 1,
        )

        logger.info("Calling LLM API...")
        try:
            t0 = time.time()
            result = generate_with_tool(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tool_schema=tool_schema,
                model=model,
                temperature=TEMPERATURE,
                max_tokens=8192,
                effort=_select_effort(),
            )
            api_latency = time.time() - t0
        except Exception:
            logger.exception(
                "API CALL FAILED for batch %d — marking all slots as failed",
                batch_idx,
            )
            for s in batch:
                progress.failed_slots[s["slot_id"]] = "API call failed"
            progress.save()
            continue

        batch_cost = cost_from_result(result)
        progress.record_call(
            model,
            result["input_tokens"],
            result["output_tokens"],
            result.get("cache_creation_input_tokens", 0),
            result.get("cache_read_input_tokens", 0),
        )

        cache_created = result.get("cache_creation_input_tokens", 0)
        cache_read = result.get("cache_read_input_tokens", 0)
        logger.info(
            "API response: %d input tokens, %d output tokens, $%.4f, %.1fs",
            result["input_tokens"] + cache_created + cache_read,
            result["output_tokens"],
            batch_cost,
            api_latency,
        )
        if cache_created or cache_read:
            logger.info(
                "Cache: %d created, %d read, %d non-cached",
                cache_created,
                cache_read,
                result["input_tokens"],
            )
        logger.info(
            "Stop reason: %s",
            result.get("stop_reason", "unknown"),
        )

        # Normalize result to list of card dicts
        raw_data = result["result"]
        raw_cards = [raw_data] if len(batch) == 1 else raw_data.get("cards", [])

        logger.info("Cards returned: %d (expected %d)", len(raw_cards), len(batch))
        if len(raw_cards) != len(batch):
            logger.warning(
                "CARD COUNT MISMATCH: expected %d, got %d",
                len(batch),
                len(raw_cards),
            )

        # Save batch-level log with full prompts + all raw responses
        _save_batch_log(
            batch_idx=batch_idx,
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
        )

        # Log each raw card preview
        logger.info("")
        logger.info("--- Raw cards from LLM ---")
        for j, rc in enumerate(raw_cards):
            logger.info("  Card %d: %s", j + 1, _card_one_liner(rc))
        logger.info("")

        # Inject set_code into raw cards before validation
        for rc in raw_cards:
            rc.setdefault("set_code", set_code)

        # Process: validate, auto-fix, save
        logger.info("--- Validation + Save ---")
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
        )
        total_saved += len(saved)
        progress.save()

        # Report progress via callback
        if progress_callback is not None:
            progress_callback(
                f"batch {batch_idx}/{len(batches)}",
                total_saved,
                len(all_slots),
                f"Batch {batch_idx}: {len(saved)}/{len(batch)} saved",
                batch_cost,
            )

        batch_elapsed = time.time() - batch_start
        logger.info("")
        logger.info(
            "BATCH %d COMPLETE: %d/%d saved, $%.4f, %.1fs",
            batch_idx,
            len(saved),
            len(batch),
            batch_cost,
            batch_elapsed,
        )
        logger.info(
            "Running totals: %d cards, %d API calls, $%.4f, %d input + %d output tokens",
            total_saved,
            progress.total_api_calls,
            progress.total_cost_usd,
            progress.total_input_tokens,
            progress.total_output_tokens,
        )
        logger.info("")

    elapsed = time.time() - start_time
    logger.info("=" * 70)
    logger.info("GENERATION COMPLETE")
    logger.info("=" * 70)
    logger.info("Cards saved:    %d", total_saved)
    logger.info("Cards failed:   %d", len(progress.failed_slots))
    logger.info("API calls:      %d", progress.total_api_calls)
    logger.info("Input tokens:   %d", progress.total_input_tokens)
    logger.info("Output tokens:  %d", progress.total_output_tokens)
    logger.info("Total cost:     $%.4f", progress.total_cost_usd)
    logger.info("Wall time:      %.1fs (%.1f min)", elapsed, elapsed / 60)
    logger.info("Avg cost/card:  $%.4f", progress.total_cost_usd / max(total_saved, 1))
    logger.info("Avg time/batch: %.1fs", elapsed / max(len(batches), 1))
    if progress.failed_slots:
        logger.info("")
        logger.info("FAILED SLOTS:")
        for sid, reason in progress.failed_slots.items():
            logger.info("  %s: %s", sid, reason)
    logger.info("")
    logger.info("Progress saved: %s", progress_path)
    logger.info("Logs saved:     %s", log_dir)
    logger.info("Cards saved:    %s", cards_dir)

    return {
        "total_slots": len(all_slots),
        "filled": total_saved,
        "failed": len(progress.failed_slots),
        "cost_usd": progress.total_cost_usd,
        "summary": f"Generated {total_saved} cards in {elapsed:.0f}s ($"
        f"{progress.total_cost_usd:.4f})",
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate MTG cards from skeleton slots",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show batches without calling LLM",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore progress file",
    )
    args = parser.parse_args()

    generate_set(dry_run=args.dry_run, resume=not args.no_resume)
