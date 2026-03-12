"""Card validation library — heuristic first-pass gates for LLM-generated cards.

Validators run in a fixed sequence (cheapest first), collecting all errors before
deciding ACCEPT or RETRY. AUTO errors are deterministically fixed post-validation;
MANUAL errors force a retry.

Validators:
    1. schema       — Pydantic parse, required fields, correct types
    2. mana         — CMC / color / color_identity consistency
    3. type_check   — Creature P/T, planeswalker loyalty, aura/equipment structure
    4. rules_text   — Self-reference, keyword capitalization, mana symbols, ability format
    5. power_level  — P+T vs CMC, NWO complexity, removal efficiency
    6. color_pie    — Ability-to-color lookup table
    7. text_overflow — Character count limits per field
    8. uniqueness   — Name/collector-number collision, mechanical similarity
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from mtgai.models.enums import StrEnum


class ValidationSeverity(StrEnum):
    """AUTO errors are deterministically fixable; MANUAL errors need LLM retry or human judgment."""

    AUTO = "AUTO"
    MANUAL = "MANUAL"


class ValidationError(BaseModel):
    """A single validation finding on a card."""

    validator: str
    severity: ValidationSeverity
    field: str
    message: str
    suggestion: str | None = None
    error_code: str | None = None


class AutoFixResult(BaseModel):
    """Result of applying auto-fixes to a card."""

    model_config = {"arbitrary_types_allowed": True}

    card: object  # Card — avoid circular import
    applied_fixes: list[str]
    remaining_errors: list[ValidationError]


# Type alias for auto-fix functions: (Card, ValidationError) -> Card
AutoFixer = Callable[..., object]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def validate_card(
    card,
    existing_cards: list | None = None,
) -> list[ValidationError]:
    """Run all validators in sequence and collect all errors.

    ``card`` must be a parsed ``Card`` instance (schema validation already passed).
    ``existing_cards`` is the list of previously-accepted cards in the set (for
    uniqueness checks).
    """
    from mtgai.validation.color_pie import validate_color_pie
    from mtgai.validation.mana import validate_mana_consistency
    from mtgai.validation.power_level import validate_power_level
    from mtgai.validation.rules_text import validate_rules_text
    from mtgai.validation.text_overflow import validate_text_overflow
    from mtgai.validation.type_check import validate_type_consistency
    from mtgai.validation.uniqueness import validate_uniqueness

    errors: list[ValidationError] = []

    errors += validate_mana_consistency(card)
    errors += validate_type_consistency(card)
    errors += validate_rules_text(card)
    errors += validate_power_level(card)
    errors += validate_color_pie(card)
    errors += validate_text_overflow(card)

    if existing_cards is not None:
        errors += validate_uniqueness(card, existing_cards)

    return errors


def validate_card_from_raw(
    raw: dict,
    existing_cards: list | None = None,
    *,
    auto_fix: bool = True,
) -> tuple:
    """Top-level entry point for raw LLM output.

    Returns ``(card, errors, applied_fixes)`` where ``card`` is ``None`` if the
    JSON couldn't be parsed into a ``Card`` at all.

    When ``auto_fix=True`` (default), AUTO errors are deterministically corrected
    and only MANUAL errors remain in the returned list.
    """
    from mtgai.validation.schema import validate_schema

    card, schema_errors = validate_schema(raw)
    if card is None:
        return None, schema_errors, []

    all_errors = schema_errors + validate_card(card, existing_cards)

    if auto_fix:
        result = auto_fix_card(card, all_errors)
        return result.card, result.remaining_errors, result.applied_fixes

    return card, all_errors, []


def has_manual_errors(errors: list[ValidationError]) -> bool:
    return any(e.severity == ValidationSeverity.MANUAL for e in errors)


# ---------------------------------------------------------------------------
# Auto-fix registry and runner
# ---------------------------------------------------------------------------

_AUTO_FIX_REGISTRY: dict[str, AutoFixer] = {}


def _register_auto_fixers() -> None:
    """Lazily populate the auto-fix registry from validator modules."""
    if _AUTO_FIX_REGISTRY:
        return  # already populated

    from mtgai.validation.mana import (
        fix_cmc,
        fix_color_identity_from_cost,
        fix_color_identity_from_oracle,
        fix_colors,
        fix_invalid_format,
        fix_mana_cost_parsed,
        fix_wubrg_order,
    )
    from mtgai.validation.rules_text import (
        fix_cannot,
        fix_card_name_in_oracle,
        fix_enters_the_battlefield,
        fix_keyword_capitalization,
        fix_keyword_commas,
        fix_line_periods,
        fix_tap_colon,
    )
    from mtgai.validation.uniqueness import fix_collector_number

    _AUTO_FIX_REGISTRY.update(
        {
            "mana.invalid_format": fix_invalid_format,
            "mana.cmc_mismatch": fix_cmc,
            "mana.colors_mismatch": fix_colors,
            "mana.color_identity_missing_cost": fix_color_identity_from_cost,
            "mana.wubrg_order": fix_wubrg_order,
            "mana.parsed_raw_mismatch": fix_mana_cost_parsed,
            "mana.parsed_cmc_mismatch": fix_mana_cost_parsed,
            "mana.parsed_x_mismatch": fix_mana_cost_parsed,
            "mana.color_identity_missing_oracle": fix_color_identity_from_oracle,
            "rules_text.card_name_in_oracle": fix_card_name_in_oracle,
            "rules_text.etb_outdated": fix_enters_the_battlefield,
            "rules_text.tap_colon": fix_tap_colon,
            "rules_text.keyword_commas": fix_keyword_commas,
            "rules_text.line_period": fix_line_periods,
            "rules_text.keyword_capitalization": fix_keyword_capitalization,
            "rules_text.cannot": fix_cannot,
            "uniqueness.collector_number_collision": fix_collector_number,
        }
    )


def auto_fix_card(card, errors: list[ValidationError]) -> AutoFixResult:
    """Apply deterministic fixes for all AUTO errors.

    Returns the fixed card and remaining MANUAL errors. AUTO errors without
    a registered fixer fall through as MANUAL.
    """
    _register_auto_fixers()

    auto_errors = [e for e in errors if e.severity == ValidationSeverity.AUTO]
    manual_errors = [e for e in errors if e.severity == ValidationSeverity.MANUAL]

    fixed_card = card
    applied_fixes: list[str] = []

    for error in auto_errors:
        fixer = _AUTO_FIX_REGISTRY.get(error.error_code or "")
        if fixer is not None:
            fixed_card = fixer(fixed_card, error)
            applied_fixes.append(f"[{error.error_code}] {error.message}")
        else:
            # No fixer registered — demote to MANUAL
            manual_errors.append(error)

    return AutoFixResult(
        card=fixed_card,
        applied_fixes=applied_fixes,
        remaining_errors=manual_errors,
    )


# ---------------------------------------------------------------------------
# Feedback formatter — structured retry prompt for the LLM
# ---------------------------------------------------------------------------

MAX_FEEDBACK_ERRORS = 10


def format_validation_feedback(
    card_name: str,
    errors: list[ValidationError],
    *,
    slot_color: str = "",
    slot_rarity: str = "",
    slot_type: str = "",
) -> str:
    """Format validation errors into a structured retry prompt."""
    selected = errors[:MAX_FEEDBACK_ERRORS]

    lines: list[str] = []
    for err in selected:
        sug = f" Fix: {err.suggestion}" if err.suggestion else ""
        lines.append(f"- {err.message}.{sug}")

    header = f'Your previous card "{card_name}" failed validation with {len(errors)} error(s):'

    slot_parts = []
    if slot_color:
        slot_parts.append(f"color: {slot_color}")
    if slot_rarity:
        slot_parts.append(f"rarity: {slot_rarity}")
    if slot_type:
        slot_parts.append(f"type: {slot_type}")
    slot_str = ", ".join(slot_parts)

    footer = "Please regenerate the card fixing all errors listed above."
    if slot_str:
        footer += f"\nDo not change the card's assigned slot ({slot_str})."

    return f"{header}\n\n" + "\n".join(lines) + f"\n\n{footer}"
