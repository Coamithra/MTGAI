"""Card validation library — format-hygiene checks for generated cards.

This module owns the **format-hygiene** validators that run at gen time: the
checks whose findings either auto-fix the card (AUTO) or signal that the card
needs to be regenerated (regen-trigger). The design-judgment heuristics
(power-level, color-pie, mechanical similarity) used to ride along here as
MANUAL warnings stamped on the card; they've moved to
:mod:`mtgai.analysis.heuristic_checks` so they're computed fresh against the
card's current state at council-review / final-QA time.

Validators run in a fixed sequence (cheapest first). AUTO findings are
deterministically fixed by ``auto_fix_card``. Schema parse failures and any
remaining text-overflow findings are returned to the caller as a single
``regen_required`` boolean so the card-gen retry loop has one signal to react to.

Validators owned by this module:
    1. schema         — Pydantic parse, required fields, correct types
    2. mana           — CMC / color / color_identity consistency (AUTO-fixable)
    3. type_check     — Creature P/T, planeswalker loyalty, aura/equipment
    4. rules_text     — Self-reference, keyword caps, mana symbols (AUTO-fixable)
    5. keyword_ordering — Keyword abilities above complex abilities (AUTO-fixable)
    6. text_overflow  — Character count limits (REGEN trigger)
    7. uniqueness     — Collector-number collision (AUTO-fixable)

Design-judgment validators (consumed by analysis.heuristic_checks):
    - power_level
    - color_pie
    - uniqueness.validate_mechanical_similarity
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
# Runner — format hygiene only
# ---------------------------------------------------------------------------


def validate_card(
    card,
    existing_cards: list | None = None,
) -> list[ValidationError]:
    """Run all **format-hygiene** validators in sequence and collect all errors.

    ``card`` must be a parsed ``Card`` instance (schema validation already passed).
    ``existing_cards`` is the list of previously-accepted cards in the set
    (needed for collector-number collision detection).

    Design-judgment checks (power-level, color-pie, mechanical similarity) are
    deliberately **not** run here — they live in
    :func:`mtgai.analysis.heuristic_checks.check_card_heuristics` and are called
    by the council reviewer / final QA, not the gen pipeline.
    """
    from mtgai.validation.keyword_ordering import validate_keyword_ordering
    from mtgai.validation.mana import validate_mana_consistency
    from mtgai.validation.rules_text import validate_rules_text
    from mtgai.validation.text_overflow import validate_text_overflow
    from mtgai.validation.type_check import validate_type_consistency
    from mtgai.validation.uniqueness import validate_collector_number

    errors: list = []

    errors += validate_mana_consistency(card)
    errors += validate_type_consistency(card)
    errors += validate_rules_text(card)
    errors += validate_keyword_ordering(card)
    errors += validate_text_overflow(card)

    if existing_cards is not None:
        errors += validate_collector_number(card, existing_cards)

    return errors


def validate_card_from_raw(
    raw: dict,
    existing_cards: list | None = None,
    *,
    auto_fix: bool = True,
) -> tuple:
    """Top-level entry point for raw LLM output.

    Returns ``(card, errors, applied_fixes, regen_required)`` where:

    * ``card`` is ``None`` if the JSON couldn't be parsed into a ``Card`` at all.
    * ``errors`` holds remaining MANUAL findings after auto-fix (when
      ``auto_fix=True``) or all errors (when ``auto_fix=False``).
    * ``applied_fixes`` describes the AUTO fixes that were applied.
    * ``regen_required`` is ``True`` when the card cannot be saved as-is and
      the caller should regenerate it — set on schema parse failure (``card``
      is ``None``) or when text-overflow findings remain. The card-gen retry
      loop uses this single boolean as its regen signal.
    """
    from mtgai.validation.schema import validate_schema

    card, schema_errors = validate_schema(raw)
    if card is None:
        return None, schema_errors, [], True

    all_errors = schema_errors + validate_card(card, existing_cards)

    if auto_fix:
        result = auto_fix_card(card, all_errors)
        regen = any(_is_regen_trigger(e) for e in result.remaining_errors)
        return result.card, result.remaining_errors, result.applied_fixes, regen

    regen = any(_is_regen_trigger(e) for e in all_errors)
    return card, all_errors, [], regen


# Error codes that kick the card-gen retry loop. Anything matching this
# allowlist is structurally severe enough that we'd rather regenerate the
# card than save it and let the council clean up. Pure error-code prefix
# match — validators only need to know which code to emit, not how the
# downstream pipeline treats it. Keep this list small: a regen costs an LLM
# call, so a finding lands here only if the card is *uninterpretable* as a
# Magic object (won't render, can't be cast, P/T is garbage).
_REGEN_TRIGGER_CODES: tuple[str, ...] = (
    # Type-line overflow is deliberately NOT here: it's AUTO-fixed by trimming
    # trailing subtypes (text_overflow.fix_type_line_overflow), so it never needs
    # a regenerate. Only the content overflows below — which need a real rewrite
    # the deterministic fixers can't do — kick the regen loop.
    "text_overflow.name",  # card name too long to fit
    "text_overflow.oracle",  # rules text too long for the frame
    "text_overflow.flavor",  # flavor text too long
    "text_overflow.combined",  # oracle + flavor together too long
    "type_check.pt_slash",  # ``power="1/1"`` etc. (both stats in one field)
    "type_check.pt_literal_null",  # ``"null"`` / ``"None"`` / ``"-"`` sentinels in stats
    "type_check.pt_nonstandard",  # non-numeric, non-``*``/``X`` garbage in stats
    "type_check.noncreature_has_pt",  # P/T on an artifact/equipment — invalid MTG
    "type_check.nonland_missing_cost",  # non-land with no mana_cost — uncastable
)


def _is_regen_trigger(e: ValidationError) -> bool:
    """True if ``e``'s error_code is on the regen allowlist (see _REGEN_TRIGGER_CODES).

    Entries ending in ``.`` match any code beginning with the prefix
    (``text_overflow.`` covers ``text_overflow.name`` / ``.oracle`` / etc.); bare
    entries match that exact code (``type_check.pt_slash`` matches only itself).
    """
    code = e.error_code or ""
    return any(code.startswith(prefix) for prefix in _REGEN_TRIGGER_CODES)


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

    from mtgai.validation.keyword_ordering import fix_keyword_ordering
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
        fix_modal_asterisk_bullet,
        fix_oracle_type_prefix,
        fix_tap_colon,
    )
    from mtgai.validation.text_overflow import fix_type_line_overflow
    from mtgai.validation.type_check import fix_enchantment_artifact, fix_type_line_order
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
            "rules_text.modal_asterisk_bullet": fix_modal_asterisk_bullet,
            "rules_text.oracle_type_prefix": fix_oracle_type_prefix,
            "keyword_ordering.misplaced": fix_keyword_ordering,
            "uniqueness.collector_number_collision": fix_collector_number,
            "type_check.enchantment_artifact": fix_enchantment_artifact,
            "type_check.type_line_order": fix_type_line_order,
            "text_overflow.type_line": fix_type_line_overflow,
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
