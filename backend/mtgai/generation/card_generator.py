"""Card generation pipeline for Phase 1C.

Generates cards from skeleton slots via LLM, runs format-hygiene validation,
auto-fixes what it can, and saves. Design-judgment heuristics (power-level,
color-pie, mechanical similarity) live in
:mod:`mtgai.analysis.heuristic_checks` and are run fresh at council-review /
final-QA time — they don't ride along on the saved card.

Two things trigger an LLM retry (capped at ``MAX_RETRIES``):

* Schema parse failure — the card can't be parsed as a ``Card`` at all.
* Text overflow — oracle text / type line / flavor / name exceeds the
  character limits. Overflow usually means the LLM lost the plot; regenerate
  rather than ship a card that won't fit on the frame.

Validation surfaces these as a single ``regen_required`` flag from
:func:`mtgai.validation.validate_card_from_raw`, so this module reacts to one
signal regardless of which check tripped.

Usage:
    python -m mtgai.generation.card_generator          # generate all unfilled slots
    python -m mtgai.generation.card_generator --resume  # resume from progress file
    python -m mtgai.generation.card_generator --dry-run  # show batches without calling LLM
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from mtgai.generation.archetype_generator import load_archetypes
from mtgai.generation.llm_client import calc_cost, cost_from_result, generate_with_tool
from mtgai.generation.prompts import (
    build_static_set_context,
    build_user_prompt,
    load_system_prompt,
)
from mtgai.generation.token_budgets import BATCH, STANDARD
from mtgai.io.atomic import atomic_write_text
from mtgai.io.card_io import load_card, save_card
from mtgai.models.card import Card, GenerationAttempt
from mtgai.models.enums import CardStatus
from mtgai.validation import ValidationError as VError
from mtgai.validation import format_validation_feedback, validate_card_from_raw
from mtgai.validation.mana import derive_mana_fields

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Stage paths are derived from the active project's asset_folder via
# ``set_artifact_dir`` at run time — no module-level OUTPUT_ROOT here.

# LLM settings — model + effort come from per-set model_settings at runtime.
TEMPERATURE = 1.0
# One card per LLM call (was 5). A single-card request uses the simpler
# CARD_TOOL_SCHEMA (one object, not an array), so the model has far less to
# track per call and breaks the design rules less often. Trades more API calls
# for higher per-card reliability — bump back up once the prompt is simplified
# and the output holds together at larger batches.
BATCH_SIZE = 1
MAX_RETRIES = 3  # Only for schema parse failures

# TEMPORARY (testing): cap how many cards a single run will generate so the
# stage can be exercised end-to-end without producing a full ~277-card set.
# This counts *total* card-gen cards (already-filled + about-to-generate), so
# resuming a capped run tops up to the cap instead of adding another fresh
# batch. Set to ``None`` to generate the whole skeleton again.
TEMP_CARD_LIMIT: int | None = None

# Tool schemas for Anthropic tool_use
# NOTE: cmc, colors, and color_identity are intentionally NOT requested — they're
# fully implied by mana_cost (cmc, colors) and oracle mana symbols (color_identity),
# and asking for them alongside mana_cost made the model fill the derived fields
# and leave mana_cost null. We derive all three from mana_cost in
# ``_process_batch_result`` via ``derive_mana_fields``. ``layout`` likewise isn't
# asked (always "normal" for this pipeline; injected programmatically).
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
        ],
        "properties": {
            "name": {"type": "string"},
            "mana_cost": {
                "type": "string",
                "description": (
                    "Mana cost in WUBRG order, e.g. {2}{W}{U}. Empty string for lands. "
                    "This is the only mana field — color and CMC are derived from it."
                ),
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


def _card_gen_log_dir() -> Path:
    """Dedicated log folder for card generation, under the active asset folder.

    Follows the ``<asset>/<stage>/logs`` convention the other stages use
    (mechanics → ``mechanics/logs``, archetypes → ``archetypes/logs``). Both
    llmfacade's HTML/JSONL transcript (routed via ``generate_with_tool(log_dir=...)``)
    and the bespoke per-card / per-batch JSON sidecars — which capture the
    post-generation validation errors, applied auto-fixes, and cost that
    llmfacade's transcript can't see — land here. Single source of truth, so
    moving the folder is a one-line change.
    """
    from mtgai.io.asset_paths import set_artifact_dir

    return set_artifact_dir() / "card_gen" / "logs"


# ---------------------------------------------------------------------------
# Progress tracking — resumable state
# ---------------------------------------------------------------------------


class GenerationProgress:
    """Tracks which slots have been generated, for resumability."""

    def __init__(self, path: Path):
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
        atomic_write_text(
            self.path,
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
    confirmed_cycles: dict[str, list[str]] | None = None,
    batch_size: int = BATCH_SIZE,
) -> list[list[dict]]:
    """Group unfilled skeleton slots into batches for generation.

    Driven by the LLM cycle-sort pass (:mod:`mtgai.generation.slot_grouper`)
    rather than the slot's swingable structured fields, since the skeleton
    relabel can have textually pulled a card out of its cycle while the seed
    ``cycle_id`` stayed put.

    ``confirmed_cycles`` is a mapping ``{cycle_id -> [slot_id, ...]}`` of
    families the cycle-sort pass confirmed by reading each member's
    ``tweaked_text``. Each confirmed family becomes its own batch (split into
    ordered sub-batches when oversized, so the card-gen loop can thread already-
    generated members into later sub-batches as siblings). Slots not in any
    confirmed family — including those whose seed ``cycle_id`` lost membership
    in the audit — are batched in deterministic ``slot_id`` order, chunked at
    ``batch_size``. No colour batching: the relabel can swing colour, so the
    seed colour groups by the *seed*, not the card's actual colour.

    ``confirmed_cycles=None`` means "skip cycle batching" — used by dry runs
    and unit tests that don't make the LLM call. An empty dict means "the LLM
    audit ran and confirmed nothing" → every slot batches as ordinary.
    """
    confirmed_cycles = confirmed_cycles or {}
    by_id: dict[str, dict] = {s["slot_id"]: s for s in slots}

    batches: list[list[dict]] = []
    placed: set[str] = set()

    # Confirmed cycle families first, deterministically by cycle_id, each split
    # into ordered sub-batches when oversized. The slot's ``cycle_id`` stamp
    # carries through to the card-gen loop, which uses it to thread siblings
    # from prior sub-batches into the prompt.
    for cid in sorted(confirmed_cycles):
        members: list[dict] = []
        for sid in confirmed_cycles[cid]:
            slot = by_id.get(sid)
            if slot is None or sid in placed:
                continue
            members.append(slot)
            placed.add(sid)
        for i in range(0, len(members), batch_size):
            batches.append(members[i : i + batch_size])

    # All remaining slots — including ones the audit dropped from their cycle —
    # in deterministic slot_id order. No colour key (the relabel may have
    # swung the slot's colour; batching by the seed colour groups by stale data
    # and adds no caching win: only the system prompt + tool schema cache).
    remaining = sorted(
        (s for s in slots if s["slot_id"] not in placed),
        key=lambda s: s["slot_id"],
    )
    for i in range(0, len(remaining), batch_size):
        batches.append(remaining[i : i + batch_size])
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
    *,
    effort: str | None = None,
    archetypes: list[dict] | None = None,
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
    static_ctx = build_static_set_context(mechanics, theme, archetypes)
    existing_dicts = [c.model_dump() if hasattr(c, "model_dump") else c for c in existing_cards]
    user_prompt = build_user_prompt([slot], mechanics, existing_dicts, theme, archetypes)
    user_prompt += (
        f"\n\n---\n\nPREVIOUS ATTEMPT FAILED:\n{error_msg}\n\n"
        "Please generate a valid card that fixes these issues."
    )

    logger.debug("    Retry prompt length: %d chars", len(user_prompt))

    # Route llmfacade's transcript alongside the bespoke per-card logs. The
    # bespoke log still owns the post-generation validation/fix/cost detail
    # llmfacade can't see; this just co-locates the raw conversation HTML.
    #
    # The base instructions + static set-context go in cached system blocks so
    # the ~6-7k-token prefix is read at ~0.1x across batches/retries instead of
    # re-billed in the user message (caching is a no-op on the llamacpp path).
    try:
        t0 = time.time()
        result = generate_with_tool(
            system_blocks=[(system_prompt, True), (static_ctx, True)],
            user_prompt=user_prompt,
            tool_schema=CARD_TOOL_SCHEMA,
            model=model,
            temperature=TEMPERATURE,
            max_tokens=STANDARD,
            effort=effort,
            log_dir=_card_gen_log_dir(),
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
    log_dir = _card_gen_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{slot_id}_attempt{attempt}.json"
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
    atomic_write_text(log_path, json.dumps(log_data, indent=2, ensure_ascii=False))


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
    *,
    effort: str | None = None,
) -> None:
    """Save a batch-level log with the full prompt and all raw card data."""
    log_dir = _card_gen_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    slot_ids = [s["slot_id"] for s in slots]
    log_path = log_dir / f"batch_{batch_idx:03d}.json"
    log_data = {
        "batch_index": batch_idx,
        "slot_ids": slot_ids,
        "slot_count": len(slots),
        "card_count_returned": len(raw_cards),
        "model": model,
        "temperature": TEMPERATURE,
        "effort": effort or "default",
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
    atomic_write_text(log_path, json.dumps(log_data, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Card preview for console logging
# ---------------------------------------------------------------------------


def _card_one_liner(raw: dict) -> str:
    """Format a card as a compact one-liner for console output.

    Defensive on every field — this is a log helper called from retry paths
    and must never raise. The LLM sometimes emits ``oracle_text: null``
    (instead of an empty string) on a retry response, and an unguarded
    ``oracle[:60]`` crashed the whole card_gen stage with
    ``'NoneType' object is not subscriptable``. Coerce every value to a
    string first.
    """
    name = raw.get("name") or "???"
    cost = raw.get("mana_cost") or ""
    tl = raw.get("type_line") or ""
    p = raw.get("power")
    t = raw.get("toughness")
    oracle = raw.get("oracle_text") or ""
    # Truncate oracle to 60 chars
    oracle_short = str(oracle)[:60].replace("\n", " | ")
    if len(str(oracle)) > 60:
        oracle_short += "..."
    pt = f" {p}/{t}" if p is not None and t is not None else ""
    return f"{name} {cost} — {tl}{pt} — {oracle_short}"


# ---------------------------------------------------------------------------
# Core generation loop
# ---------------------------------------------------------------------------


def _select_model() -> str:
    """Return the generation model from the active project's settings."""
    from mtgai.runtime.active_project import require_active_project

    return require_active_project().settings.get_llm_model_id("card_gen")


def _select_effort() -> str | None:
    """Return the effort level from the active project's settings."""
    from mtgai.runtime.active_project import require_active_project

    return require_active_project().settings.get_effort("card_gen")


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
    set_code: str,
    user_prompt: str = "",
    system_prompt: str = "",
    latency_s: float = 0.0,
    stop_reason: str = "",
    effort: str | None = None,
    set_dir: Path | None = None,
    archetypes: list[dict] | None = None,
    card_saved_callback: Callable[[Card], None] | None = None,
) -> list[Card]:
    """Validate, auto-fix, and save each card from a batch result.

    ``set_code`` is the active project's set_code, resolved once at
    the top of ``generate_set`` and threaded through so per-batch
    helpers don't re-query the active project (matches the
    "resolve once at the top of the run" guarantee in CLAUDE.md).

    Returns the list of successfully saved Card objects.
    """
    from mtgai.settings.model_registry import get_registry

    saved: list[Card] = []
    cost_per_card = calc_cost(model, input_tokens, output_tokens) / max(len(raw_cards), 1)
    # Provenance shows the base; `model` is the effective ctx twin used to generate.
    display_model = get_registry().public_model_id(model)

    for i, raw in enumerate(raw_cards):
        slot = slots[i] if i < len(slots) else slots[-1]
        slot_id = slot["slot_id"]

        # Log the raw card as received from LLM
        logger.info("  [%s] Raw LLM output: %s", slot_id, _card_one_liner(raw))

        # Inject pipeline metadata before validation. ``layout`` isn't set here —
        # the Card model defaults it to "normal" (the only layout this pipeline
        # produces), so it's neither asked of the LLM nor injected.
        raw.setdefault("set_code", set_code)
        raw.setdefault("collector_number", slot_id)
        # cmc / colors / color_identity are no longer requested from the LLM —
        # derive them from mana_cost (+ oracle symbols) so the validators (color
        # pie etc.) see correct values rather than the model's omissions.
        raw.update(derive_mana_fields(raw.get("mana_cost"), raw.get("oracle_text")))

        # Validate + auto-fix (format hygiene only — design-judgment heuristics
        # run later, fresh, against the card the council is about to review).
        logger.info("  [%s] Running format-hygiene validation...", slot_id)
        card, errors, applied_fixes, regen_required = validate_card_from_raw(
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
                "  [%s] %d remaining issue(s):",
                slot_id,
                len(errors),
            )
            for err in errors:
                logger.info(
                    "    %s: [%s] %s.%s: %s",
                    err.severity.value,
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

        # Regen-trigger — schema parse failure (card is None) or text overflow.
        # Both signal "this card can't ship as-is; regenerate." We use the same
        # retry loop and the same per-attempt cap regardless of which tripped.
        if regen_required:
            if card is None:
                logger.warning(
                    "  [%s] SCHEMA PARSE FAILURE — card couldn't be created. Errors: %s",
                    slot_id,
                    "; ".join(e.message for e in errors),
                )
                # No parsed card means we don't have a name for the feedback
                # header; the errors list is already the LLM-friendly summary.
                feedback = str(errors)
            else:
                overflow_errors = [
                    e for e in errors if e.error_code and e.error_code.startswith("text_overflow.")
                ]
                logger.warning(
                    "  [%s] TEXT OVERFLOW — %d field(s) over limit, regenerating",
                    slot_id,
                    len(overflow_errors),
                )
                feedback = format_validation_feedback(
                    card_name,
                    overflow_errors,
                    slot_color=slot.get("color", ""),
                    slot_rarity=slot.get("rarity", ""),
                    slot_type=slot.get("card_type", ""),
                )
            card = _retry_card(
                slot,
                feedback,
                mechanics,
                existing_cards,
                theme,
                model,
                progress,
                set_code=set_code,
                effort=effort,
                archetypes=archetypes,
            )
            if card is None:
                logger.error(
                    "  [%s] FAILED after %d retries — flagging for manual review",
                    slot_id,
                    MAX_RETRIES,
                )
                progress.failed_slots[slot_id] = f"Regen failed after {MAX_RETRIES} retries"
                progress.save()
                continue

        # Card parsed — set pipeline fields
        update_fields: dict = {
            "set_code": set_code,
            "collector_number": slot_id,
            "slot_id": slot_id,
            "status": CardStatus.DRAFT,
            "created_at": datetime.now(UTC),
            "generation_attempts": [
                GenerationAttempt(
                    attempt_number=1,
                    timestamp=datetime.now(UTC),
                    model_used=display_model,
                    success=True,
                    validation_errors=[e.message for e in errors],
                    input_tokens=input_tokens // max(len(raw_cards), 1),
                    output_tokens=output_tokens // max(len(raw_cards), 1),
                    cost_usd=cost_per_card,
                ),
            ],
        }

        # Skeleton-seed metadata (``mechanic_tag`` / ``archetype_tags``) is NOT
        # stamped onto the card. Those fields are swingable seeds the relabel
        # doesn't update, so stamping them risks mislabeling the card with
        # data the descriptor (and therefore the actual card) no longer matches.
        # The generated card's own ``type_line`` / ``oracle_text`` / ``colors``
        # are authoritative; if mechanic_tags / draft_archetype are needed
        # downstream, derive them from the actual card later.

        card = card.model_copy(update=update_fields)

        # Save card — route through the project's set_dir so asset_folder
        # routing wins over the legacy OUTPUT_ROOT/sets/<CODE>/ default.
        path = save_card(card, set_dir=set_dir)
        progress.filled_slots[slot_id] = str(path)
        existing_cards.append(card)
        saved.append(card)

        logger.info(
            "  [%s] SAVED: %s -> %s",
            slot_id,
            card.name,
            path.name,
        )

        # Live-stream hook: caller (engine emitter or /refresh endpoint) gets
        # one notification per successful save so the Card Generation tab can
        # pop each card in as it lands. Wrapped so a buggy callback never
        # kills the run — the canonical state is on disk regardless.
        if card_saved_callback is not None:
            try:
                card_saved_callback(card)
            except Exception:
                logger.exception("card_saved_callback raised for %s", slot_id)

    return saved


def _retry_card(
    slot: dict,
    error_msg: str,
    mechanics: list[dict],
    existing_cards: list,
    theme: dict | None,
    model: str,
    progress: GenerationProgress,
    *,
    set_code: str,
    effort: str | None = None,
    archetypes: list[dict] | None = None,
) -> Card | None:
    """Retry a card that hit a regen trigger (schema parse failure or text overflow).

    ``error_msg`` is the LLM-facing feedback for the retry — typically the
    output of :func:`format_validation_feedback` for overflow, or a stringified
    error list for a parse failure (where no parsed card exists yet).
    """
    for attempt in range(2, MAX_RETRIES + 1):
        result = _retry_single_card(
            slot,
            error_msg,
            mechanics,
            existing_cards,
            theme,
            model,
            attempt,
            effort=effort,
            archetypes=archetypes,
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
        retry_raw.setdefault("set_code", set_code)
        retry_raw.setdefault("collector_number", slot["slot_id"])
        retry_raw.update(
            derive_mana_fields(retry_raw.get("mana_cost"), retry_raw.get("oracle_text"))
        )

        logger.info(
            "    Retry %d raw output: %s",
            attempt,
            _card_one_liner(retry_raw),
        )

        card, errors, applied_fixes, regen_required = validate_card_from_raw(
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
                    "    Retry %s: [%s] %s",
                    err.severity.value,
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

        if card is not None and not regen_required:
            logger.info(
                "    Retry %d SUCCEEDED: %s",
                attempt,
                card.name,
            )
            return card
        # Either schema still failed (card is None) or text overflow still
        # trips the regen flag — rebuild the feedback for the next attempt.
        logger.warning(
            "    Retry %d FAILED: %s",
            attempt,
            "still can't parse" if card is None else "text still overflows",
        )
        if card is None:
            error_msg = str(errors)
        else:
            overflow_errors = [
                e for e in errors if e.error_code and e.error_code.startswith("text_overflow.")
            ]
            error_msg = format_validation_feedback(
                card.name,
                overflow_errors,
                slot_color=slot.get("color", ""),
                slot_rarity=slot.get("rarity", ""),
                slot_type=slot.get("card_type", ""),
            )

    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _find_card_file(slot_id: str, cards_dir: Path) -> Path | None:
    """Find the card JSON file for a given slot_id (collector_number)."""
    for p in cards_dir.glob("*.json"):
        if p.name.startswith(f"{slot_id}_"):
            return p
    # Fallback: load and check collector_number / slot_id.
    for p in cards_dir.glob("*.json"):
        try:
            card = load_card(p)
            if card.collector_number == slot_id or card.slot_id == slot_id:
                return p
        except Exception:
            continue
    return None


def archive_card(slot_id: str, cards_dir: Path, archive_dir: Path) -> str | None:
    """Move a slot's card file to ``archive_dir``. Returns the archived name or None.

    Used by the review→regen loop: before regenerating a flagged slot, its prior
    card is archived rather than overwritten, so every attempt is preserved.
    """
    card_file = _find_card_file(slot_id, cards_dir)
    if card_file is None:
        logger.warning("No card file found for slot %s — skipping archive", slot_id)
        return None

    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / card_file.name
    if dest.exists():
        ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        dest = archive_dir / f"{card_file.stem}_{ts}{card_file.suffix}"

    shutil.move(str(card_file), str(dest))
    logger.info("Archived: %s -> %s", card_file.name, dest.name)
    return dest.name


def _collect_flagged_slots(cards_dir: Path) -> dict[str, str]:
    """Map slot_id -> regen_reason for every card a review gate flagged.

    Scans the on-disk cards (the flag is persisted on the Card), so the loop
    survives a restart between a gate flagging and card_gen re-running.
    """
    flagged: dict[str, str] = {}
    if not cards_dir.exists():
        return flagged
    for p in sorted(cards_dir.glob("*.json")):
        try:
            card = load_card(p)
        except Exception:
            continue
        if card.regen_reason and card.slot_id:
            flagged[card.slot_id] = card.regen_reason
    return flagged


def _install_prefab_cards(
    *,
    set_dir: Path,
    set_code: str,
    progress_path: Path,
    total_slots: int,
    card_saved_callback: Callable[[Card], None] | None,
    progress_callback: Callable[[str, int, int, str, float], None] | None,
) -> dict:
    """Install the prefab card pool, bypassing every LLM call (debug toggle).

    Copies ``prefab_data/cards/*.json`` into ``<set_dir>/cards/`` — re-stamping
    ``set_code`` to the active project and clearing any ``regen_reason`` /
    ``flagged_by`` so a fresh copy reads clean — records each as a filled slot
    in ``generation_progress.json``, and streams every card through the same
    ``card_saved`` / ``progress`` callbacks the LLM path uses, so the Card
    Generation tab and downstream stages behave identically to a real run.

    Always overwrites (idempotent): on a re-entrant regen pass this re-installs
    the clean prefabs over any gate-flagged card, which is the prefab analogue
    of card_gen's archive-and-regenerate-with-cleared-flag contract.
    """
    from mtgai.generation.prefab import load_prefab_cards

    cards = load_prefab_cards()
    progress = GenerationProgress(path=progress_path)
    logger.info("PREFAB MODE: installing %d prefab card(s) — no LLM calls", len(cards))

    if progress_callback is not None:
        progress_callback(
            "preparing", 0, total_slots, f"Installing {len(cards)} prefab cards…", 0.0
        )

    saved = 0
    for card in cards:
        card = card.model_copy(
            update={"set_code": set_code, "regen_reason": None, "flagged_by": None}
        )
        path = save_card(card, set_dir=set_dir)
        slot_id = card.slot_id or card.collector_number
        progress.filled_slots[slot_id] = str(path)
        progress.failed_slots.pop(slot_id, None)
        saved += 1
        if card_saved_callback is not None:
            try:
                card_saved_callback(card)
            except Exception:
                logger.warning(
                    "card_saved_callback failed for prefab card %s", card.name, exc_info=True
                )
        if progress_callback is not None:
            progress_callback("prefab", saved, total_slots, f"Installed {card.name}", 0.0)
    progress.save()

    logger.info("PREFAB MODE: installed %d card(s) into %s", saved, set_dir / "cards")
    return {
        "total_slots": total_slots,
        "filled": saved,
        "failed": 0,
        "cost_usd": 0.0,
        "summary": f"Installed {saved} prefab cards (no LLM calls)",
        "cancelled": False,
    }


def generate_set(
    *,
    dry_run: bool = False,
    resume: bool = True,
    progress_callback: Callable[[str, int, int, str, float], None] | None = None,
    card_saved_callback: Callable[[Card], None] | None = None,
) -> dict:
    """Generate all unfilled slots in the active project's skeleton.

    Args:
        dry_run: If True, print batches and exit without calling the LLM.
        resume: If True, skip slots already in generation_progress.json.
        progress_callback: Optional (item, completed, total, detail, cost) callback.
        card_saved_callback: Optional ``(Card) -> None`` invoked once per card
            after it lands on disk — used by the engine emitter and the manual
            ``/refresh`` endpoint to stream each card to the Card Generation
            tab as it's generated. Exceptions are swallowed and logged so a
            broken callback can never kill a run (the canonical state is on
            disk regardless).

    Returns:
        Summary dict with total_slots, filled, failed, cost_usd, summary.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime import ai_lock
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    set_code = project.set_code
    set_dir = set_artifact_dir()
    skeleton_path = set_dir / "skeleton.json"
    mechanics_path = set_dir / "mechanics" / "approved.json"
    theme_path = set_dir / "theme.json"
    progress_path = set_dir / "generation_progress.json"
    log_dir = _card_gen_log_dir()

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
    logger.info("Set: %s | Output: %s", set_code, set_dir)
    logger.info("Logs: %s", log_dir)
    logger.info("")

    # Load inputs
    skeleton = json.loads(skeleton_path.read_text(encoding="utf-8"))
    mechanics = json.loads(mechanics_path.read_text(encoding="utf-8"))
    theme = json.loads(theme_path.read_text(encoding="utf-8"))
    # TC-3 archetypes.json drives slot annotations when present; an empty/missing
    # file falls back to theme.draft_archetypes (None lets build_user_prompt do that).
    archetypes = load_archetypes(set_dir) or None

    # Stamp each cycle member with its cycle's shared template so the family is
    # generated with parallel structure (format_slot_specs reads cycle_template).
    cycle_templates = {
        c.get("id"): c.get("template", "")
        for c in (skeleton.get("cycles") or [])
        if isinstance(c, dict) and c.get("id")
    }
    for s in skeleton["slots"]:
        cid = s.get("cycle_id")
        if cid and cycle_templates.get(cid):
            s["cycle_template"] = cycle_templates[cid]

    logger.info(
        "Loaded: skeleton (%d slots), %d mechanics, theme '%s', %d archetypes",
        len(skeleton["slots"]),
        len(mechanics),
        theme.get("name", "?"),
        len(archetypes) if archetypes else 0,
    )

    # Debug: prefab cards — skip all LLM generation and install the hand-made
    # pool from prefab_data/cards/. The whole point is speed, so this returns
    # immediately; the regen loop, cycle-sort, and batching below never run.
    # A dry run still reports its plan rather than installing prefabs.
    # FIRST PASS ONLY. A follow-up card_gen instance (Card Generation 2+,
    # entered after a Conformance & Interactions bounce) carries gate-flagged
    # cards that must be *actually* regenerated; re-installing the identical
    # prefab would re-trip the gate and spin the review/regen loop forever.
    # Any card on disk carrying a regen_reason is the canonical "this is a
    # regen pass" signal, so prefab steps aside and the normal LLM path below
    # regenerates the flagged slots.
    from mtgai.generation.prefab import prefab_cards_available

    if (
        not dry_run
        and project.settings.debug.use_prefab_cards
        and not _collect_flagged_slots(set_dir / "cards")
        and prefab_cards_available()
    ):
        return _install_prefab_cards(
            set_dir=set_dir,
            set_code=set_code,
            progress_path=progress_path,
            total_slots=len(skeleton["slots"]),
            card_saved_callback=card_saved_callback,
            progress_callback=progress_callback,
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

    # --- Review→regen loop: regenerate cards a gate flagged ---
    # A gate (conformance / interactions / design review) sets ``regen_reason`` on
    # a card it can't accept. Treat those slots as needing regeneration: archive
    # the prior card, drop it from the progress ledger so it re-enters ``unfilled``
    # (the cap math self-adjusts — len(filled) drops, remaining rises), and stamp
    # the reason onto its slot dict so ``format_slot_specs`` threads it into the
    # prompt. The regenerated card is built fresh, so its flag clears naturally.
    flagged_reasons = _collect_flagged_slots(set_dir / "cards")
    if flagged_reasons:
        archive_dir = set_dir / "cards" / "_regen_archive"
        for sid in flagged_reasons:
            archive_card(sid, set_dir / "cards", archive_dir)
            progress.filled_slots.pop(sid, None)
            progress.failed_slots.pop(sid, None)
        for s in skeleton["slots"]:
            if s.get("slot_id") in flagged_reasons:
                s["regen_reason"] = flagged_reasons[s["slot_id"]]
        logger.info(
            "Review->regen: regenerating %d flagged slot(s): %s",
            len(flagged_reasons),
            ", ".join(sorted(flagged_reasons)),
        )

    # Filter to unfilled slots. Ordinary (non-land) slots plus any land slot that
    # is a cycle member (e.g. a guildgate cycle) are generated here — card-gen owns
    # land cycles now, batching them with their shared template. A stray standalone
    # land (none exist today) stays excluded; the `lands` stage handles basics + its
    # one investigated bonus dual. Reprint-stamped slots are also excluded — the
    # reprint stage already claimed them (the reprint IS the slot's card), so
    # generating over them would double-fill the slot.
    all_slots = [
        s
        for s in skeleton["slots"]
        if (s.get("card_type") != "land" or s.get("cycle_id")) and not s.get("is_reprint_slot")
    ]
    if resume:
        unfilled = [
            s
            for s in all_slots
            if s["slot_id"] not in progress.filled_slots
            and s["slot_id"] not in progress.failed_slots
        ]
    else:
        unfilled = [s for s in all_slots if s.get("card_id") is None]

    # TEMPORARY testing cap — see TEMP_CARD_LIMIT. Trim to at most this many
    # *total* card-gen cards (already-filled + about-to-generate) so resuming a
    # capped run tops up to the cap rather than adding another fresh batch.
    # Remove this block (or set TEMP_CARD_LIMIT=None) to generate the full set.
    if TEMP_CARD_LIMIT is not None:
        remaining = max(0, TEMP_CARD_LIMIT - len(progress.filled_slots))
        if len(unfilled) > remaining:
            logger.warning(
                "TEMP_CARD_LIMIT=%d active — generating %d of %d unfilled slots "
                "(%d already filled). Set TEMP_CARD_LIMIT=None for the full set.",
                TEMP_CARD_LIMIT,
                remaining,
                len(unfilled),
                len(progress.filled_slots),
            )
            unfilled = unfilled[:remaining]

    logger.info(
        "Slots: %d total, %d filled, %d failed, %d to generate",
        len(all_slots),
        len(progress.filled_slots),
        len(progress.failed_slots),
        len(unfilled),
    )

    if not unfilled:
        logger.info("Nothing to generate — all slots filled or failed.")
        return {
            "total_slots": len(all_slots),
            "filled": len(progress.filled_slots),
            "failed": len(progress.failed_slots),
            "cost_usd": progress.total_cost_usd,
            "summary": "Nothing to generate — all slots already filled or failed.",
            "cancelled": False,
        }

    # Surface the work total *before* the (LLM-bearing) cycle-sort pass and the
    # first batch. Without this, the engine only learns the total from the
    # first per-batch callback below — so the Card Generation tab sits on
    # "0/?" with no progress bar through cycle-sort and the whole first batch
    # (one LLM call, minutes on a local model), making a running stage look
    # stuck. completed=0 matches the first batch tick, which counts cards saved
    # this run (so the count never jumps backwards).
    if progress_callback is not None:
        progress_callback(
            "preparing",
            0,
            len(all_slots),
            f"Preparing to generate {len(unfilled)} cards…",
            0.0,
        )

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

    # Cycle-sort LLM pass: show the model the full relabeled slot listing and
    # let it identify cycles purely from the descriptor text (see slot_grouper).
    # The batcher then groups identified cycles together — the per-slot
    # ``cycle_template`` stamped from the structural seed flows through when
    # the identified cycle's members all share that seed, so the prompt's cycle
    # note still fires for the canonical case. Dry runs skip the LLM call.
    if dry_run:
        confirmed_cycles: dict[str, list[str]] = {}
    else:
        from mtgai.generation.slot_grouper import find_cycle_families

        logger.info("Running cycle-sort on %d unfilled slots...", len(unfilled))
        confirmed_cycles = find_cycle_families(
            slots=unfilled,
            model=active_model,
            log_dir=log_dir,
        )
        logger.info(
            "Cycle-sort identified %d cycle(s) covering %d slot_ids",
            len(confirmed_cycles),
            sum(len(v) for v in confirmed_cycles.values()),
        )
    batches = group_slots_into_batches(unfilled, confirmed_cycles=confirmed_cycles)

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
    # Static set-context (setting prose, mechanics, archetypes, preventive
    # guidance) is a pure function of the run's inputs, so hoist it out of the
    # batch loop and reuse one immutable string. It rides in a cached system
    # block per batch (written once, read at ~0.1x thereafter); `effective_system`
    # is the full base + static text, logged so the sidecars still show everything.
    static_ctx = build_static_set_context(mechanics, theme, archetypes)
    effective_system = f"{system_prompt}\n\n---\n\n{static_ctx}"
    logger.info(
        "System prompt loaded: %d chars base + %d chars static context",
        len(system_prompt),
        len(static_ctx),
    )
    total_saved = 0
    cancelled = False
    start_time = time.time()

    # Per-cycle siblings collected during THIS run. When an oversized cycle is
    # split into ordered sub-batches, each later sub-batch's prompt gets the
    # prior members so the family is designed with parallel structure — stronger
    # than the generic existing-cards "don't duplicate" framing. Keyed by the
    # confirmed cycle's id; only confirmed cycles populate it.
    cycle_siblings_by_id: dict[str, list[dict]] = {cid: [] for cid in confirmed_cycles}

    for batch_idx, batch in enumerate(batches, 1):
        # Honor a Cancel from the progress strip (→ ai_lock.request_cancel()).
        # An in-flight LLM call can't be interrupted, so we stop at the next
        # batch boundary; cards already saved persist in
        # generation_progress.json, so a Retry resumes from here.
        if ai_lock.is_cancelled():
            logger.warning(
                "Card generation CANCELLED by user after batch %d/%d (%d cards saved).",
                batch_idx - 1,
                len(batches),
                total_saved,
            )
            cancelled = True
            break

        slot_ids = [s["slot_id"] for s in batch]
        batch_start = time.time()

        logger.info("=" * 60)
        logger.info(
            "BATCH %d/%d [%s] — %d cards: %s",
            batch_idx,
            len(batches),
            active_model,
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
        # Cycle siblings: when all batch slots share a confirmed cycle_id AND the
        # cycle already has saved members this run, thread them in. (With
        # BATCH_SIZE=1 every cycle batch after the first hits this; with larger
        # batches an oversized cycle's sub-batches 2+ hit this.)
        batch_cycle_ids = {s.get("cycle_id") for s in batch}
        siblings_for_batch: list[dict] | None = None
        if len(batch_cycle_ids) == 1:
            cid = next(iter(batch_cycle_ids))
            if cid and cycle_siblings_by_id.get(cid):
                siblings_for_batch = list(cycle_siblings_by_id[cid])
        user_prompt = build_user_prompt(
            batch,
            mechanics,
            existing_dicts,
            theme,
            archetypes,
            cycle_siblings=siblings_for_batch,
        )
        logger.info(
            "Prompt built: %d chars (system+static) + %d chars (user) = %d total",
            len(effective_system),
            len(user_prompt),
            len(effective_system) + len(user_prompt),
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
                system_blocks=[(system_prompt, True), (static_ctx, True)],
                user_prompt=user_prompt,
                tool_schema=tool_schema,
                model=active_model,
                temperature=TEMPERATURE,
                max_tokens=BATCH,
                effort=active_effort,
                log_dir=log_dir,
            )
            api_latency = time.time() - t0
        except Exception:
            # A Cancel mid-call hard-kills the local llama-server (see
            # llm_client.interrupt_local_inference), so the in-flight call raises
            # here. That's a clean cancel, not a batch failure: don't stamp the
            # slots API-failed (they'd wrongly show as errors and skew Retry);
            # just stop. Cards already saved persist for resume.
            if ai_lock.is_cancelled():
                logger.warning(
                    "Card generation CANCELLED by user during batch %d/%d (%d saved).",
                    batch_idx,
                    len(batches),
                    total_saved,
                )
                cancelled = True
                break
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
            active_model,
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
            model=active_model,
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            cost_usd=batch_cost,
            latency_s=api_latency,
            stop_reason=result.get("stop_reason", ""),
            user_prompt=user_prompt,
            system_prompt=effective_system,
            effort=active_effort,
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
            active_model,
            result["input_tokens"],
            result["output_tokens"],
            progress,
            set_code=set_code,
            user_prompt=user_prompt,
            system_prompt=effective_system,
            latency_s=api_latency,
            stop_reason=result.get("stop_reason", ""),
            effort=active_effort,
            set_dir=set_dir,
            archetypes=archetypes,
            card_saved_callback=card_saved_callback,
        )
        total_saved += len(saved)
        progress.save()

        # Push newly-saved cards into the per-cycle sibling list so later sub-
        # batches of the same confirmed cycle see them. We re-check the batch's
        # shared cycle_id here (set above) rather than recomputing from `saved`,
        # since the generated card's own ``slot_id`` may not survive an auto-fix.
        if siblings_for_batch is not None or (
            len(batch_cycle_ids) == 1 and next(iter(batch_cycle_ids)) in cycle_siblings_by_id
        ):
            cid = next(iter(batch_cycle_ids))
            if cid:
                cycle_siblings_by_id.setdefault(cid, []).extend(c.model_dump() for c in saved)

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
    logger.info("GENERATION CANCELLED" if cancelled else "GENERATION COMPLETE")
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

    summary = (
        f"Cancelled after {total_saved} cards ({elapsed:.0f}s, "
        f"${progress.total_cost_usd:.4f}) — Retry to resume"
        if cancelled
        else f"Generated {total_saved} cards in {elapsed:.0f}s (${progress.total_cost_usd:.4f})"
    )
    return {
        "total_slots": len(all_slots),
        "filled": total_saved,
        "failed": len(progress.failed_slots),
        "cost_usd": progress.total_cost_usd,
        "summary": summary,
        "cancelled": cancelled,
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
