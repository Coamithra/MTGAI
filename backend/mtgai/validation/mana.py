"""Validator 2: Mana Cost / CMC Consistency.

Verifies internal consistency between mana_cost, cmc, colors, color_identity,
and mana_cost_parsed fields. Catches format errors, CMC miscalculations,
color mismatches, and WUBRG ordering violations.
"""

from __future__ import annotations

import re

from mtgai.models.card import Card, ManaCost
from mtgai.models.enums import Color
from mtgai.validation import ValidationError, ValidationSeverity

MANA_SYMBOL_PATTERN = re.compile(r"\{(\d+|[WUBRGCX](?:/[WUBRGP])?)\}")
MANA_SYMBOL_ANY = re.compile(r"\{[^}]+\}")
WUBRG_ORDER = {"W": 0, "U": 1, "B": 2, "R": 3, "G": 4}
COLOR_SYMBOLS = {"W", "U", "B", "R", "G"}
_COLOR_LETTER_TO_ENUM = {c.value: c for c in Color}


def _manual(
    field: str, message: str, suggestion: str | None = None, *, error_code: str
) -> ValidationError:
    return ValidationError(
        validator="mana",
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
        validator="mana",
        severity=ValidationSeverity.AUTO,
        field=field,
        message=message,
        suggestion=suggestion,
        error_code=error_code,
    )


# ---------------------------------------------------------------------------
# Shared parsing helper
# ---------------------------------------------------------------------------


def _parse_mana_cost(mana_cost: str) -> tuple[float, set[str], int, list[str]]:
    """Parse a mana_cost string and return (cmc, colors, x_count, color_sequence)."""
    symbols = MANA_SYMBOL_PATTERN.findall(mana_cost)
    cmc: float = 0.0
    colors: set[str] = set()
    x_count = 0
    color_sequence: list[str] = []

    for sym in symbols:
        if sym.isdigit():
            cmc += int(sym)
        elif sym == "X":
            x_count += 1
        elif sym == "C":
            cmc += 1
        elif "/" in sym:
            cmc += 1
            parts = sym.split("/")
            for part in parts:
                if part in COLOR_SYMBOLS:
                    colors.add(part)
                    color_sequence.append(part)
        elif sym in COLOR_SYMBOLS:
            cmc += 1
            colors.add(sym)
            color_sequence.append(sym)

    return cmc, colors, x_count, color_sequence


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def validate_mana_consistency(card: Card) -> list[ValidationError]:
    """Check mana_cost, cmc, colors, and color_identity for internal consistency."""
    errors: list[ValidationError] = []

    # Cards with no mana cost (lands, tokens, etc.) — skip most checks
    if not card.mana_cost:
        errors += _check_oracle_text_color_identity(card)
        return errors

    # ------------------------------------------------------------------
    # 1. Mana cost format validation — AUTO (fixable by splitting symbols)
    # ------------------------------------------------------------------
    stripped = MANA_SYMBOL_PATTERN.sub("", card.mana_cost)
    if stripped:
        errors.append(
            _auto(
                "mana_cost",
                f"Invalid mana_cost format: '{card.mana_cost}'",
                "Split combined symbols, e.g. {2W} -> {2}{W}.",
                error_code="mana.invalid_format",
            )
        )
        # Don't return early — the fixer will normalize before next validation

    # ------------------------------------------------------------------
    # 2. Parse symbols and compute CMC / colors
    # ------------------------------------------------------------------
    computed_cmc, computed_colors, x_count, color_sequence = _parse_mana_cost(card.mana_cost)

    # ------------------------------------------------------------------
    # 3. CMC check — AUTO (recomputable)
    # ------------------------------------------------------------------
    if abs(card.cmc - computed_cmc) > 0.01:
        errors.append(
            _auto(
                "cmc",
                f"cmc is {card.cmc} but mana_cost '{card.mana_cost}' computes to {computed_cmc}",
                f"Fix: set cmc to {computed_cmc}",
                error_code="mana.cmc_mismatch",
            )
        )

    # ------------------------------------------------------------------
    # 4. Colors check — AUTO (recomputable)
    # ------------------------------------------------------------------
    card_colors = {c.value for c in card.colors}
    if card_colors != computed_colors:
        expected_sorted = sorted(computed_colors, key=lambda c: WUBRG_ORDER.get(c, 99))
        errors.append(
            _auto(
                "colors",
                f"colors is {_format_color_set(card_colors)} but mana_cost implies "
                f"{_format_color_set(computed_colors)}",
                f"Fix: set colors to [{', '.join(expected_sorted)}]",
                error_code="mana.colors_mismatch",
            )
        )

    # ------------------------------------------------------------------
    # 5. Color identity includes mana_cost colors — AUTO
    # ------------------------------------------------------------------
    card_identity = {c.value for c in card.color_identity}
    if not computed_colors.issubset(card_identity):
        missing = computed_colors - card_identity
        missing_sorted = sorted(missing, key=lambda c: WUBRG_ORDER.get(c, 99))
        errors.append(
            _auto(
                "color_identity",
                f"color_identity is missing mana_cost colors: {', '.join(missing_sorted)}",
                f"Fix: add {', '.join(missing_sorted)} to color_identity",
                error_code="mana.color_identity_missing_cost",
            )
        )

    # ------------------------------------------------------------------
    # 6. WUBRG ordering — AUTO
    # ------------------------------------------------------------------
    seen: set[str] = set()
    unique_sequence: list[str] = []
    for c in color_sequence:
        if c not in seen:
            seen.add(c)
            unique_sequence.append(c)

    correct_order = sorted(unique_sequence, key=lambda c: WUBRG_ORDER[c])
    if unique_sequence != correct_order:
        errors.append(
            _auto(
                "mana_cost",
                f"Mana symbols are not in WUBRG order: "
                f"got {unique_sequence}, expected {correct_order}",
                f"Reorder colored mana to WUBRG: {', '.join(correct_order)}",
                error_code="mana.wubrg_order",
            )
        )

    # ------------------------------------------------------------------
    # 7. mana_cost_parsed consistency — AUTO (recomputable)
    # ------------------------------------------------------------------
    if card.mana_cost_parsed is not None:
        p = card.mana_cost_parsed
        if p.raw != card.mana_cost:
            errors.append(
                _auto(
                    "mana_cost_parsed.raw",
                    f"mana_cost_parsed.raw is '{p.raw}' but mana_cost is '{card.mana_cost}'",
                    f"Fix: set mana_cost_parsed.raw to '{card.mana_cost}'",
                    error_code="mana.parsed_raw_mismatch",
                )
            )
        if abs(p.cmc - computed_cmc) > 0.01:
            errors.append(
                _auto(
                    "mana_cost_parsed.cmc",
                    f"mana_cost_parsed.cmc is {p.cmc} but computed CMC is {computed_cmc}",
                    f"Fix: set mana_cost_parsed.cmc to {computed_cmc}",
                    error_code="mana.parsed_cmc_mismatch",
                )
            )
        if x_count > 0 and p.x_count != x_count:
            errors.append(
                _auto(
                    "mana_cost_parsed.x_count",
                    f"mana_cost_parsed.x_count is {p.x_count} but mana_cost has "
                    f"{x_count} X symbol(s)",
                    f"Fix: set mana_cost_parsed.x_count to {x_count}",
                    error_code="mana.parsed_x_mismatch",
                )
            )

    # ------------------------------------------------------------------
    # 8. Oracle text mana references must be in color_identity — AUTO
    # ------------------------------------------------------------------
    errors += _check_oracle_text_color_identity(card)

    # ------------------------------------------------------------------
    # 9. Land cards should not have a mana cost — MANUAL
    # ------------------------------------------------------------------
    if "Land" in card.card_types:
        errors.append(
            _manual(
                "mana_cost",
                f"Land card has a mana_cost '{card.mana_cost}'",
                "Lands typically have no mana cost — remove mana_cost or set to empty.",
                error_code="mana.land_with_cost",
            )
        )

    return errors


def _check_oracle_text_color_identity(card: Card) -> list[ValidationError]:
    """Scan oracle_text for mana symbols and verify they appear in color_identity."""
    if not card.oracle_text:
        return []

    oracle_colors: set[str] = set()
    for match in MANA_SYMBOL_ANY.finditer(card.oracle_text):
        symbol_contents = match.group(0)[1:-1]  # strip { }
        for char in symbol_contents:
            if char in COLOR_SYMBOLS:
                oracle_colors.add(char)

    card_identity = {c.value for c in card.color_identity}
    missing = oracle_colors - card_identity
    if missing:
        missing_sorted = sorted(missing, key=lambda c: WUBRG_ORDER.get(c, 99))
        return [
            _auto(
                "color_identity",
                f"Oracle text references mana colors not in color_identity: "
                f"{', '.join(missing_sorted)}",
                f"Fix: add {', '.join(missing_sorted)} to color_identity",
                error_code="mana.color_identity_missing_oracle",
            )
        ]
    return []


def _format_color_set(colors: set[str]) -> str:
    """Format a color set in WUBRG order for display."""
    ordered = sorted(colors, key=lambda c: WUBRG_ORDER.get(c, 99))
    return "{" + ", ".join(ordered) + "}"


# ---------------------------------------------------------------------------
# Auto-fix functions
# ---------------------------------------------------------------------------


def fix_invalid_format(card: Card, error: ValidationError) -> Card:
    """Normalize malformed mana_cost by splitting combined symbols.

    Handles patterns like {2W} -> {2}{W}, {WW} -> {W}{W}, {2WU} -> {2}{W}{U}.
    Each digit sequence becomes a generic mana symbol, each color letter becomes
    its own symbol.
    """
    if not card.mana_cost:
        return card

    normalized_parts: list[str] = []
    for match in MANA_SYMBOL_ANY.finditer(card.mana_cost):
        inner = match.group(0)[1:-1]  # strip { }
        # Already a valid symbol — keep as-is
        if MANA_SYMBOL_PATTERN.fullmatch(match.group(0)):
            normalized_parts.append(match.group(0))
            continue
        # Split inner into digit runs and individual color/special letters
        for token in re.findall(r"\d+|[WUBRGCXP/]", inner):
            if token.isdigit() or token == "/" :
                normalized_parts.append(f"{{{token}}}")
            elif token in COLOR_SYMBOLS or token in ("C", "X"):
                normalized_parts.append(f"{{{token}}}")

    if normalized_parts:
        new_cost = "".join(normalized_parts)
    else:
        # Fallback: couldn't parse at all, leave unchanged
        return card

    update: dict = {"mana_cost": new_cost}
    if card.mana_cost_parsed is not None:
        new_parsed = card.mana_cost_parsed.model_copy(update={"raw": new_cost})
        update["mana_cost_parsed"] = new_parsed
    return card.model_copy(update=update)


def fix_cmc(card: Card, error: ValidationError) -> Card:
    """Recompute CMC from mana_cost."""
    if not card.mana_cost:
        return card
    computed_cmc, _, _, _ = _parse_mana_cost(card.mana_cost)
    return card.model_copy(update={"cmc": computed_cmc})


def fix_colors(card: Card, error: ValidationError) -> Card:
    """Recompute colors from mana_cost."""
    if not card.mana_cost:
        return card
    _, computed_colors, _, _ = _parse_mana_cost(card.mana_cost)
    sorted_colors = sorted(computed_colors, key=lambda c: WUBRG_ORDER.get(c, 99))
    color_enums = [_COLOR_LETTER_TO_ENUM[c] for c in sorted_colors]
    return card.model_copy(update={"colors": color_enums})


def fix_color_identity_from_cost(card: Card, error: ValidationError) -> Card:
    """Add missing mana_cost colors to color_identity."""
    if not card.mana_cost:
        return card
    _, computed_colors, _, _ = _parse_mana_cost(card.mana_cost)
    current_identity = {c.value for c in card.color_identity}
    merged = current_identity | computed_colors
    sorted_merged = sorted(merged, key=lambda c: WUBRG_ORDER.get(c, 99))
    identity_enums = [_COLOR_LETTER_TO_ENUM[c] for c in sorted_merged]
    return card.model_copy(update={"color_identity": identity_enums})


def fix_wubrg_order(card: Card, error: ValidationError) -> Card:
    """Reorder mana_cost symbols into WUBRG order."""
    if not card.mana_cost:
        return card

    symbols = MANA_SYMBOL_PATTERN.findall(card.mana_cost)
    non_color = []
    color_syms = []
    for sym in symbols:
        if sym in COLOR_SYMBOLS or "/" in sym:
            color_syms.append(sym)
        else:
            non_color.append(sym)

    # Sort color symbols by WUBRG (for hybrids, use first color)
    def _sort_key(sym: str) -> int:
        first_color = sym.split("/")[0]
        return WUBRG_ORDER.get(first_color, 99)

    color_syms.sort(key=_sort_key)

    new_cost = "".join(f"{{{s}}}" for s in non_color + color_syms)
    update: dict = {"mana_cost": new_cost}

    # Also update mana_cost_parsed.raw if present
    if card.mana_cost_parsed is not None:
        new_parsed = card.mana_cost_parsed.model_copy(update={"raw": new_cost})
        update["mana_cost_parsed"] = new_parsed

    return card.model_copy(update=update)


def fix_mana_cost_parsed(card: Card, error: ValidationError) -> Card:
    """Recompute mana_cost_parsed from mana_cost."""
    if not card.mana_cost:
        return card

    computed_cmc, computed_colors, x_count, _ = _parse_mana_cost(card.mana_cost)

    symbols = MANA_SYMBOL_PATTERN.findall(card.mana_cost)
    generic = 0
    w, u, b, r, g, c_count = 0, 0, 0, 0, 0, 0
    for sym in symbols:
        if sym.isdigit():
            generic += int(sym)
        elif sym == "X":
            pass
        elif sym == "C":
            c_count += 1
        elif "/" in sym:
            # Hybrid — count for first color
            first = sym.split("/")[0]
            if first == "W":
                w += 1
            elif first == "U":
                u += 1
            elif first == "B":
                b += 1
            elif first == "R":
                r += 1
            elif first == "G":
                g += 1
        elif sym == "W":
            w += 1
        elif sym == "U":
            u += 1
        elif sym == "B":
            b += 1
        elif sym == "R":
            r += 1
        elif sym == "G":
            g += 1

    sorted_colors = sorted(computed_colors, key=lambda cc: WUBRG_ORDER.get(cc, 99))
    color_enums = [_COLOR_LETTER_TO_ENUM[cc] for cc in sorted_colors]

    new_parsed = ManaCost(
        raw=card.mana_cost,
        cmc=computed_cmc,
        colors=color_enums,
        generic=generic,
        white=w,
        blue=u,
        black=b,
        red=r,
        green=g,
        colorless=c_count,
        x_count=x_count,
    )
    return card.model_copy(update={"mana_cost_parsed": new_parsed})


def fix_color_identity_from_oracle(card: Card, error: ValidationError) -> Card:
    """Add oracle-text-referenced colors to color_identity."""
    if not card.oracle_text:
        return card

    oracle_colors: set[str] = set()
    for match in MANA_SYMBOL_ANY.finditer(card.oracle_text):
        symbol_contents = match.group(0)[1:-1]
        for char in symbol_contents:
            if char in COLOR_SYMBOLS:
                oracle_colors.add(char)

    current_identity = {c.value for c in card.color_identity}
    merged = current_identity | oracle_colors
    sorted_merged = sorted(merged, key=lambda c: WUBRG_ORDER.get(c, 99))
    identity_enums = [_COLOR_LETTER_TO_ENUM[c] for c in sorted_merged]
    return card.model_copy(update={"color_identity": identity_enums})
