"""Validator 4: Rules Text Grammar & Formatting.

The most important validator — catches rules text grammar issues that LLMs
commonly produce: self-references, outdated phrasing, invalid mana symbols,
keyword formatting, planeswalker ability structure, and set-specific nonbos.
"""

from __future__ import annotations

import re

from mtgai.models.card import Card
from mtgai.validation import ValidationError, ValidationSeverity

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EVERGREEN_KEYWORDS = {
    "deathtouch",
    "defender",
    "double strike",
    "enchant",
    "equip",
    "first strike",
    "flash",
    "flying",
    "haste",
    "hexproof",
    "indestructible",
    "lifelink",
    "menace",
    "reach",
    "trample",
    "vigilance",
    "ward",
    "protection",
}

# Keyword actions that appear in ability text (not standalone keywords)
KEYWORD_ACTIONS = {
    "attach",
    "cast",
    "counter",
    "create",
    "destroy",
    "discard",
    "exchange",
    "exile",
    "fight",
    "mill",
    "play",
    "reveal",
    "sacrifice",
    "scry",
    "search",
    "shuffle",
    "tap",
    "untap",
    "activate",
    "adapt",
    "amass",
    "bolster",
    "connive",
    "discover",
    "explore",
    "investigate",
    "manifest",
    "proliferate",
    "surveil",
    "transform",
    "venture",
}

# Custom mechanics for the Anomalous Descent (ASD) set
CUSTOM_KEYWORDS = {"salvage", "malfunction", "overclock"}

MANA_SYM_VALID = re.compile(r"\{(\d+|[WUBRGCXSTQ](?:/[WUBRGP])?)\}")
MANA_SYM_ANY = re.compile(r"\{[^}]+\}")
SELF_REF_BAD = re.compile(
    r"\bthis (creature|card|permanent|enchantment|artifact|planeswalker"
    r"|instant|sorcery)\b",
    re.IGNORECASE,
)
LOYALTY_ABILITY = re.compile(r"^[+\-\u2212]?\d+: .+\.$", re.MULTILINE)

ALL_KEYWORDS = EVERGREEN_KEYWORDS | CUSTOM_KEYWORDS


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _manual(
    field: str, message: str, suggestion: str | None = None, *, error_code: str
) -> ValidationError:
    return ValidationError(
        validator="rules_text",
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
        validator="rules_text",
        severity=ValidationSeverity.AUTO,
        field=field,
        message=message,
        suggestion=suggestion,
        error_code=error_code,
    )


def _is_keyword_line(line: str) -> bool:
    """Return True if the line looks like a keyword-only line (comma-separated)."""
    if not line.strip():
        return False
    if any(ch in line for ch in ".:\u2014"):
        return False
    parts = [p.strip().lower() for p in line.split(",")]
    return any(
        any(p == kw or p.startswith(kw + " ") for kw in ALL_KEYWORDS) for p in parts
    )


def _is_keyword_only_line(line: str) -> bool:
    """Return True if every comma-separated segment is a recognized keyword.

    Handles parameterized keywords like "Ward {2}", "Protection from red",
    "Salvage 3", "Malfunction 2", etc. — checks only the base keyword word.
    """
    stripped = line.strip()
    if not stripped:
        return False

    parts = [p.strip() for p in stripped.split(",")]
    for part in parts:
        if not part:
            return False
        # Extract the base keyword: first word(s) that match a known keyword
        part_lower = part.lower()
        matched = False
        for kw in ALL_KEYWORDS:
            if (
                part_lower == kw
                or part_lower.startswith(kw + " ")
                or part_lower.startswith(kw + " {")
            ):
                matched = True
                break
        if not matched:
            return False
    return True


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def validate_rules_text(card: Card) -> list[ValidationError]:
    """Check oracle_text for grammar, formatting, and set-specific issues."""
    errors: list[ValidationError] = []

    oracle = card.oracle_text or ""
    if not oracle:
        # Check 12 still applies even with empty oracle text
        errors += _check_custom_mechanic_reminder(card)
        return errors

    lines = oracle.split("\n")

    # ------------------------------------------------------------------
    # 1. Self-reference: card name in oracle text — AUTO
    # ------------------------------------------------------------------
    if card.name and card.name in oracle:
        errors.append(
            _auto(
                "oracle_text",
                f'Oracle text uses card name "{card.name}". Fix: replace with "~"',
                error_code="rules_text.card_name_in_oracle",
            )
        )

    # ------------------------------------------------------------------
    # 2. "this creature/card/permanent" instead of ~ — MANUAL
    # ------------------------------------------------------------------
    for i, line in enumerate(lines, start=1):
        for m in SELF_REF_BAD.finditer(line):
            errors.append(
                _manual(
                    "oracle_text",
                    f'Line {i}: "{m.group()}" should use "~" or '
                    f'"this" only in specific MTG contexts',
                    'Replace with "~" to refer to this card.',
                    error_code="rules_text.this_creature",
                )
            )

    # ------------------------------------------------------------------
    # 3. Invalid mana symbols in text — MANUAL
    # ------------------------------------------------------------------
    for m in MANA_SYM_ANY.finditer(oracle):
        token = m.group()
        if not MANA_SYM_VALID.fullmatch(token):
            suggestion = None
            inner = token[1:-1]
            combined = re.match(r"^(\d+)([WUBRGC])$", inner)
            if combined:
                suggestion = (
                    f'Use "{{{combined.group(1)}}}{{{combined.group(2)}}}" instead of "{token}"'
                )
            errors.append(
                _manual(
                    "oracle_text",
                    f"Invalid mana symbol: {token}",
                    suggestion,
                    error_code="rules_text.invalid_mana_symbol",
                )
            )

    # ------------------------------------------------------------------
    # 4. "enters the battlefield" (outdated post-MOM 2023) — AUTO
    # ------------------------------------------------------------------
    if "enters the battlefield" in oracle.lower():
        errors.append(
            _auto(
                "oracle_text",
                'Oracle text uses outdated "enters the battlefield" phrasing',
                'Replace "enters the battlefield" with "enters".',
                error_code="rules_text.etb_outdated",
            )
        )

    # ------------------------------------------------------------------
    # 5. "Tap:" or "tap:" instead of "{T}:" — AUTO
    # ------------------------------------------------------------------
    if re.search(r"\b[Tt]ap:", oracle):
        errors.append(
            _auto(
                "oracle_text",
                '"Tap:" should be the tap symbol',
                'Use "{T}:" for tap costs.',
                error_code="rules_text.tap_colon",
            )
        )

    # ------------------------------------------------------------------
    # 6. Informal mana costs in activated abilities — MANUAL
    # ------------------------------------------------------------------
    for line in lines:
        if ": " in line:
            cost_part = line.split(": ", 1)[0]
            if re.search(r"\bpay\s+\d+\b", cost_part, re.IGNORECASE):
                errors.append(
                    _manual(
                        "oracle_text",
                        "Informal mana cost in activated ability — "
                        f'found "pay N" in cost: "{cost_part}"',
                        "Use mana symbols like {2} instead of 'pay 2'.",
                        error_code="rules_text.informal_cost",
                    )
                )

    # ------------------------------------------------------------------
    # 7. "Add one [color] mana" or "add W" — MANUAL
    # ------------------------------------------------------------------
    if re.search(r"[Aa]dd (?:one )?\w+ mana", oracle):
        errors.append(
            _manual(
                "oracle_text",
                'Informal mana production — use mana symbols instead of "add ... mana"',
                'Use "{W}" / "{U}" etc. for mana production.',
                error_code="rules_text.informal_mana_production",
            )
        )
    if re.search(r"[Aa]dd [WUBRG](?:\s|\.)", oracle):
        errors.append(
            _manual(
                "oracle_text",
                "Informal mana production — use mana symbols instead of bare color letters",
                'Use "{W}" / "{U}" etc. for mana production.',
                error_code="rules_text.informal_mana_bare",
            )
        )

    # ------------------------------------------------------------------
    # 8. Planeswalker loyalty abilities — MANUAL
    # ------------------------------------------------------------------
    if card.type_line and "Planeswalker" in card.type_line:
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(r"^[+\-\u2212]?\d+:", stripped) and not LOYALTY_ABILITY.match(stripped):
                errors.append(
                    _manual(
                        "oracle_text",
                        f'Line {i}: Loyalty ability has incorrect format: "{stripped}"',
                        "Loyalty abilities must match the pattern "
                        '"+N: Effect." (ending with a period).',
                        error_code="rules_text.pw_loyalty_format",
                    )
                )

    # ------------------------------------------------------------------
    # 9. Keyword-only lines formatting (comma separation) — AUTO
    # ------------------------------------------------------------------
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if "," in stripped:
            continue  # Already has commas, skip
        words_lower = stripped.lower()
        found_keywords: list[str] = []
        for kw in ALL_KEYWORDS:
            if re.search(rf"\b{re.escape(kw)}\b", words_lower):
                found_keywords.append(kw)
        if len(found_keywords) >= 2:
            errors.append(
                _auto(
                    "oracle_text",
                    f'Line {i}: Multiple keywords without commas: "{stripped}"',
                    'Keyword lists should be comma-separated, e.g. "Flying, trample".',
                    error_code="rules_text.keyword_commas",
                )
            )

    # ------------------------------------------------------------------
    # 10. Lines ending with periods — AUTO
    # ------------------------------------------------------------------
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if _is_keyword_only_line(stripped):
            continue
        if re.match(r"^[A-Z]\w+(\s\w+)?\s*[—\-]", stripped):
            continue
        if not stripped.endswith(".") and not stripped.endswith('"'):
            errors.append(
                _auto(
                    "oracle_text",
                    f'Line {i}: Does not end with a period or closing quote: "{stripped}"',
                    "Rules text lines should end with a period.",
                    error_code="rules_text.line_period",
                )
            )

    # ------------------------------------------------------------------
    # 11. Reminder text in oracle_text — MANUAL
    # ------------------------------------------------------------------
    for m in re.finditer(r"\(([^)]+)\)", oracle):
        paren_content = m.group(1)
        if len(paren_content) >= 20:
            errors.append(
                _manual(
                    "oracle_text",
                    f'Oracle text contains what looks like reminder text: "({paren_content})"',
                    "Move reminder text to the reminder_text field.",
                    error_code="rules_text.reminder_in_oracle",
                )
            )

    # ------------------------------------------------------------------
    # 12. Custom mechanic reminder text — MANUAL
    # ------------------------------------------------------------------
    errors += _check_custom_mechanic_reminder(card)

    # ------------------------------------------------------------------
    # 13. Haste + Malfunction nonbo — MANUAL
    # ------------------------------------------------------------------
    oracle_lower = oracle.lower()
    has_malfunction = "malfunction" in oracle_lower or "malfunction" in [
        t.lower() for t in card.mechanic_tags
    ]
    has_haste = "haste" in oracle_lower

    if has_malfunction and has_haste:
        errors.append(
            _manual(
                "oracle_text",
                "Haste is a nonbo with Malfunction — the creature enters "
                "tapped, so haste is negated",
                "Remove haste or remove Malfunction from this card.",
                error_code="rules_text.haste_malfunction_nonbo",
            )
        )

    # ------------------------------------------------------------------
    # 14. Keyword capitalization — AUTO
    # ------------------------------------------------------------------
    for line in lines:
        if not _is_keyword_line(line):
            continue
        parts = [p.strip() for p in line.split(",")]
        for part in parts[1:]:
            if not part:
                continue
            if part[0].isupper() and part.lower() in ALL_KEYWORDS:
                errors.append(
                    _auto(
                        "oracle_text",
                        f'Keyword "{part}" should be lowercase '
                        f"(except at start of line)",
                        f'Use "{part.lower()}"',
                        error_code="rules_text.keyword_capitalization",
                    )
                )

    # ------------------------------------------------------------------
    # 15. "cannot" / "can not" → "can't" — AUTO
    # ------------------------------------------------------------------
    oracle_lower_stripped = oracle.lower()
    if "can not" in oracle_lower_stripped or "cannot" in oracle_lower_stripped:
        errors.append(
            _auto(
                "oracle_text",
                'MTG rules text uses "can\'t", not "can not" or "cannot"',
                'Replace with "can\'t"',
                error_code="rules_text.cannot",
            )
        )

    # ------------------------------------------------------------------
    # 16. "Enters tapped" redundancy with Malfunction — MANUAL
    # ------------------------------------------------------------------
    has_malfunction_text = "malfunction" in oracle_lower
    has_enters_tapped = "enters tapped" in oracle_lower

    if has_malfunction_text and has_enters_tapped:
        errors.append(
            _manual(
                "oracle_text",
                "Malfunction already causes the permanent to enter tapped — "
                "explicit 'enters tapped' is redundant",
                error_code="rules_text.malfunction_enters_tapped",
            )
        )

    return errors


def _check_custom_mechanic_reminder(card: Card) -> list[ValidationError]:
    """Check that cards with custom mechanics have reminder text."""
    errors: list[ValidationError] = []
    for mechanic in CUSTOM_KEYWORDS:
        if mechanic in [t.lower() for t in card.mechanic_tags] and not card.reminder_text:
            errors.append(
                _manual(
                    "reminder_text",
                    f'Card uses custom mechanic "{mechanic}" but has no reminder text',
                    f'Add reminder text explaining the "{mechanic}" mechanic.',
                    error_code="rules_text.custom_mechanic_no_reminder",
                )
            )
    return errors


# ---------------------------------------------------------------------------
# Auto-fix functions
# ---------------------------------------------------------------------------


def fix_card_name_in_oracle(card: Card, error: ValidationError) -> Card:
    """Replace card name with ~ in oracle text."""
    if not card.name or not card.oracle_text:
        return card
    new_oracle = card.oracle_text.replace(card.name, "~")
    return card.model_copy(update={"oracle_text": new_oracle})


def fix_enters_the_battlefield(card: Card, error: ValidationError) -> Card:
    """Replace 'enters the battlefield' with 'enters'."""
    if not card.oracle_text:
        return card
    new_oracle = re.sub(r"enters the battlefield", "enters", card.oracle_text, flags=re.IGNORECASE)
    return card.model_copy(update={"oracle_text": new_oracle})


def fix_tap_colon(card: Card, error: ValidationError) -> Card:
    """Replace 'Tap:' / 'tap:' with '{T}:'."""
    if not card.oracle_text:
        return card
    new_oracle = re.sub(r"\b[Tt]ap:", "{T}:", card.oracle_text)
    return card.model_copy(update={"oracle_text": new_oracle})


def fix_keyword_commas(card: Card, error: ValidationError) -> Card:
    """Insert commas between keywords on keyword-only lines."""
    if not card.oracle_text:
        return card

    new_lines = []
    for line in card.oracle_text.split("\n"):
        stripped = line.strip()
        if not stripped or "," in stripped:
            new_lines.append(line)
            continue

        # Find all keyword matches in this line
        words_lower = stripped.lower()
        found_keywords: list[tuple[int, int, str]] = []
        for kw in ALL_KEYWORDS:
            for m in re.finditer(rf"\b{re.escape(kw)}\b", words_lower):
                found_keywords.append((m.start(), m.end(), kw))

        if len(found_keywords) >= 2:
            # Sort by position and rebuild with commas
            found_keywords.sort(key=lambda x: x[0])
            # Extract the actual text segments (preserving original case)
            segments = []
            for start, end, _ in found_keywords:
                segments.append(stripped[start:end])
            new_lines.append(", ".join(segments))
        else:
            new_lines.append(line)

    new_oracle = "\n".join(new_lines)
    return card.model_copy(update={"oracle_text": new_oracle})


def fix_line_periods(card: Card, error: ValidationError) -> Card:
    """Append period to non-keyword lines that are missing one."""
    if not card.oracle_text:
        return card

    new_lines = []
    for line in card.oracle_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            new_lines.append(line)
            continue
        if _is_keyword_only_line(stripped):
            new_lines.append(line)
            continue
        if re.match(r"^[A-Z]\w+(\s\w+)?\s*[—\-]", stripped):
            new_lines.append(line)
            continue
        if not stripped.endswith(".") and not stripped.endswith('"'):
            new_lines.append(line + ".")
        else:
            new_lines.append(line)

    new_oracle = "\n".join(new_lines)
    return card.model_copy(update={"oracle_text": new_oracle})


def fix_keyword_capitalization(card: Card, error: ValidationError) -> Card:
    """Lowercase non-first keywords on keyword lines."""
    if not card.oracle_text:
        return card

    new_lines = []
    for line in card.oracle_text.split("\n"):
        if not _is_keyword_line(line):
            new_lines.append(line)
            continue
        parts = [p.strip() for p in line.split(",")]
        fixed_parts = [parts[0]]  # Keep first keyword's case
        for part in parts[1:]:
            if part and part[0].isupper() and part.lower() in ALL_KEYWORDS:
                fixed_parts.append(part[0].lower() + part[1:])
            else:
                fixed_parts.append(part)
        new_lines.append(", ".join(fixed_parts))

    new_oracle = "\n".join(new_lines)
    return card.model_copy(update={"oracle_text": new_oracle})


def fix_cannot(card: Card, error: ValidationError) -> Card:
    """Replace "cannot" / "can not" with "can't" in oracle text."""
    if not card.oracle_text:
        return card
    new_oracle = re.sub(r"\bcannot\b", "can't", card.oracle_text, flags=re.IGNORECASE)
    new_oracle = re.sub(r"\bcan not\b", "can't", new_oracle, flags=re.IGNORECASE)
    return card.model_copy(update={"oracle_text": new_oracle})
