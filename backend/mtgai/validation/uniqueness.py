"""Validator 9: Uniqueness — name/collector-number collision, mechanical similarity.

Checks for duplicate or near-duplicate cards within the set to prevent
accidental clones, name collisions, and collector number conflicts.
"""

from __future__ import annotations

import contextlib
from difflib import SequenceMatcher

from mtgai.models.card import Card
from mtgai.validation import ValidationError, ValidationSeverity


def _manual(
    field: str, message: str, suggestion: str | None = None, *, error_code: str
) -> ValidationError:
    return ValidationError(
        validator="uniqueness",
        severity=ValidationSeverity.MANUAL,
        field=field,
        message=message,
        suggestion=suggestion,
        error_code=error_code,
    )


def _auto(
    field: str, message: str, suggestion: str | None = None, *, error_code: str
) -> ValidationError:
    return ValidationError(
        validator="uniqueness",
        severity=ValidationSeverity.AUTO,
        field=field,
        message=message,
        suggestion=suggestion,
        error_code=error_code,
    )


def _levenshtein(a: str, b: str) -> int:
    """Compute the Levenshtein edit distance between two strings."""
    m, n = len(a), len(b)
    prev = list(range(n + 1))
    curr = [0] * (n + 1)

    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,  # deletion
                curr[j - 1] + 1,  # insertion
                prev[j - 1] + cost,  # substitution
            )
        prev, curr = curr, prev

    return prev[n]


def _text_similarity(a: str, b: str) -> float:
    """Return similarity ratio (0.0-1.0) between two strings."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def validate_uniqueness(card: Card, existing_cards: list[Card]) -> list[ValidationError]:
    """Check for duplicate names, collector numbers, and mechanical similarity."""
    errors: list[ValidationError] = []
    card_name_lower = card.name.lower()

    for existing in existing_cards:
        existing_name_lower = existing.name.lower()

        # 1. Exact name match (case-insensitive) -> MANUAL
        if card_name_lower == existing_name_lower:
            errors.append(
                _manual(
                    "name",
                    f'Card name "{card.name}" already exists in the set '
                    f"(card #{existing.collector_number})",
                    "Choose a different name.",
                    error_code="uniqueness.duplicate_name",
                )
            )
            continue

        # 2. Near-duplicate name (Levenshtein distance <= 2) -> MANUAL
        if _levenshtein(card_name_lower, existing_name_lower) <= 2:
            errors.append(
                _manual(
                    "name",
                    f'Card name "{card.name}" is very similar to existing '
                    f'"{existing.name}" (#{existing.collector_number}). '
                    f"Consider a more distinct name.",
                    error_code="uniqueness.near_duplicate_name",
                )
            )

    # 3. Collector number collision -> AUTO (assign next available)
    if card.collector_number:
        taken = {e.collector_number for e in existing_cards if e.collector_number}
        if card.collector_number in taken:
            # Find next available collector number
            max_num = 0
            for cn in taken | {card.collector_number}:
                with contextlib.suppress(ValueError):
                    max_num = max(max_num, int(cn))
            next_num = str(max_num + 1).zfill(len(card.collector_number))
            errors.append(
                _auto(
                    "collector_number",
                    f'Collector number "{card.collector_number}" is '
                    f'already assigned — reassigning to "{next_num}"',
                    f"Reassign to {next_num}.",
                    error_code="uniqueness.collector_number_collision",
                )
            )

    # 4. Mechanical similarity -> MANUAL
    card_colors_set = set(card.colors)
    card_types_set = set(card.card_types)

    for existing in existing_cards:
        if (
            card.cmc == existing.cmc
            and card_colors_set == set(existing.colors)
            and card_types_set == set(existing.card_types)
        ):
            similarity = _text_similarity(card.oracle_text, existing.oracle_text)
            pct = round(similarity * 100)
            if pct > 80:
                errors.append(
                    _manual(
                        "oracle_text",
                        f'Card is mechanically similar to "{existing.name}" '
                        f"(#{existing.collector_number}): same color, same "
                        f"CMC, {pct}% text similarity.",
                        error_code="uniqueness.mechanical_similarity",
                    )
                )

    return errors


# ---------------------------------------------------------------------------
# Auto-fix functions
# ---------------------------------------------------------------------------


def fix_collector_number(card: Card, error: ValidationError) -> Card:
    """Reassign collector number to the next available one.

    The suggestion field contains the new number (set during validation when
    existing_cards was available).
    """
    if not error.suggestion:
        return card
    # Extract the number from "Reassign to 004."
    import re

    m = re.search(r"Reassign to (\S+)", error.suggestion)
    if not m:
        return card
    return card.model_copy(update={"collector_number": m.group(1).rstrip(".")})
