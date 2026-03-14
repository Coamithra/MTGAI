"""Reminder text injection — adds reminder text programmatically after LLM review.

Loads mechanic definitions and injects reminder text into oracle text for the
first USE of each custom keyword on a card.  Distinguishes between cards that
USE a keyword (get reminder text) vs. cards that merely REFERENCE it (don't).

Heuristics:
  - **keyword_ability** (Salvage X, Malfunction N): keyword + number = USE.
    Bare keyword without number (e.g., "malfunction counter", "whenever you
    salvage") is a REFERENCE — no injection.
  - **keyword_action** (Overclock): keyword as main verb of a clause = USE.
    Keyword in a trigger/conditional context ("whenever you overclock") = REFERENCE.

Usage (pipeline integration):
    from mtgai.generation.reminder_injector import finalize_reminder_text
    card = finalize_reminder_text(card, mechanics)
"""

from __future__ import annotations

import re

from mtgai.models.card import Card

# Number-to-word mapping — MTG convention spells out small numbers in reminder text.
_NUM_WORDS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
}

# Regex to strip existing parenthesized reminder text (20+ chars = likely reminder).
REMINDER_STRIP_RE = re.compile(r"\s*\([^)]{20,}\)\.?")

# Patterns preceding a keyword that indicate a trigger/conditional context
# (i.e., the card REFERENCES the keyword rather than USING it).
_TRIGGER_PREFIXES = re.compile(
    r"\b(whenever|if|each time)\b.*\b(you|~|it|they)\s*$",
    re.IGNORECASE,
)


def _num_to_word(n: int) -> str:
    """Convert integer to English word (1-12), fallback to str for larger."""
    return _NUM_WORDS.get(n, str(n))


def _build_reminder(template: str, param: int | None) -> str:
    """Substitute numeric parameter into a reminder text template.

    Templates from approved.json use ``X`` or ``N`` as placeholders.
    Handles plural/singular for "cards", "counters", etc.
    """
    if param is None:
        return template

    word = _num_to_word(param)
    result = template

    # Replace X or N placeholder with the spelled-out number
    result = re.sub(r"\bX\b", word, result)
    result = re.sub(r"\bN\b", word, result)

    # Handle singular when param == 1: "one X counters" → "one X counter"
    if param == 1:
        result = re.sub(r"\bone (\w+\s+)?cards\b", r"one \1card", result)
        result = re.sub(r"\bone (\w+\s+)?counters\b", r"one \1counter", result)
        result = re.sub(r"\bone (\w+\s+)?tokens\b", r"one \1token", result)

    return result


def _find_keyword_ability_use(oracle: str, keyword: str) -> re.Match | None:
    """Find the first USE of a parameterized keyword ability (e.g., Salvage X).

    A USE is keyword + number (e.g., "salvage 3", "malfunction 2").
    Bare keyword without a number is a REFERENCE (e.g., "malfunction counter",
    "whenever you salvage") and is skipped.
    """
    pattern = re.compile(
        rf"\b({re.escape(keyword)})\s+(\d+)\b",
        re.IGNORECASE,
    )
    return pattern.search(oracle)


def _find_keyword_action_use(oracle: str, keyword: str) -> re.Match | None:
    """Find the first USE of a non-parameterized keyword action (e.g., Overclock).

    A USE is the keyword as the main verb/action of a clause:
        "{T}: Overclock."
        "When ~ enters, overclock."

    A REFERENCE is the keyword in a trigger/conditional context:
        "Whenever ~ overclocks, ..."  (conjugated — won't match word boundary)
        "Whenever you overclock, ..."  (preceded by trigger pattern)

    Returns the first non-reference match, or None.
    """
    pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)

    for match in pattern.finditer(oracle):
        # Look backwards from the match to the start of the line/sentence
        line_start = oracle.rfind("\n", 0, match.start()) + 1
        preceding = oracle[line_start : match.start()]

        # Skip if preceded by a trigger/conditional pattern
        if _TRIGGER_PREFIXES.search(preceding):
            continue

        return match

    return None


def strip_reminder_text(oracle: str) -> str:
    """Remove parenthesized reminder text (20+ chars) from oracle text.

    Also cleans up double-spaces and trailing whitespace left behind.
    """
    cleaned = REMINDER_STRIP_RE.sub("", oracle)
    # Collapse multiple spaces into one
    cleaned = re.sub(r"  +", " ", cleaned)
    # Clean up lines
    lines = [line.strip() for line in cleaned.split("\n")]
    return "\n".join(line for line in lines if line)


def inject_reminder_text(card: Card, mechanics: list[dict]) -> Card:
    """Inject reminder text for custom mechanics on first USE only.

    Distinguishes between cards that USE a keyword (get reminder text) and
    cards that merely REFERENCE it (don't).  See module docstring for the
    heuristics.

    Args:
        card: The card to process.
        mechanics: List of mechanic dicts (from approved.json), each with
            ``name``, ``reminder_text``, and ``keyword_type`` keys.

    Returns:
        A new Card with reminder text injected into oracle_text.
    """
    oracle = card.oracle_text or ""
    if not oracle:
        return card

    for mech in mechanics:
        name = mech["name"]
        reminder_template = mech["reminder_text"]
        keyword_type = mech.get("keyword_type", "keyword_ability")

        if keyword_type == "keyword_action":
            match = _find_keyword_action_use(oracle, name)
            param = None
        else:
            match = _find_keyword_ability_use(oracle, name)
            param = int(match.group(2)) if match else None

        if not match:
            continue

        reminder = _build_reminder(reminder_template, param)

        # Find insertion point: after the keyword phrase and any following period.
        end = match.end()
        if end < len(oracle) and oracle[end] == ".":
            end += 1  # include the period before reminder

        # Insert reminder text
        oracle = oracle[:end] + f" {reminder}" + oracle[end:]

    if oracle != (card.oracle_text or ""):
        return card.model_copy(update={"oracle_text": oracle})
    return card


def finalize_reminder_text(card: Card, mechanics: list[dict]) -> Card:
    """Strip any existing inline reminder text, then inject fresh from definitions.

    This is the top-level function for pipeline use.  It ensures cards always
    have correct, up-to-date reminder text regardless of what the LLM produced.
    """
    oracle = card.oracle_text or ""
    if not oracle:
        return card

    clean_oracle = strip_reminder_text(oracle)
    if clean_oracle != oracle:
        card = card.model_copy(update={"oracle_text": clean_oracle})

    return inject_reminder_text(card, mechanics)
