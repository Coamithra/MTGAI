"""Validator 4: Rules Text Grammar & Formatting.

The most important validator — catches rules text grammar issues that LLMs
commonly produce: self-references, outdated phrasing, invalid mana symbols,
keyword formatting, planeswalker ability structure, and rules nonbos.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

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
    "shroud",
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

MANA_SYM_VALID = re.compile(r"\{(\d+|[WUBRGCXSTQ](?:/[WUBRGP])?)\}")
MANA_SYM_ANY = re.compile(r"\{[^}]+\}")

# Lines like "Artifact." / "Creature" at the start of oracle_text — the LLM
# redundantly stating the type as a heading. The type already lives in
# ``type_line``; the prefix is stripped by ``fix_oracle_type_prefix``.
_TYPE_PREFIX_RE = re.compile(
    r"^(?:Artifact|Creature|Enchantment|Instant|Sorcery|Land|Planeswalker|Battle|Tribal)\.?$"
)
SELF_REF_BAD = re.compile(
    r"\bthis (creature|card|permanent|enchantment|artifact|planeswalker"
    r"|instant|sorcery)\b",
    re.IGNORECASE,
)
LOYALTY_ABILITY = re.compile(r"^[+\-\u2212]?\d+: .+\.$", re.MULTILINE)

# Custom-mechanic keywords (the active set's named mechanics) are resolved per
# call rather than hardcoded, so the rules-text validators recognize ANY set's
# custom keywords as valid keyword-only lines. Resolution order:
#   1. an explicit override set via ``set_custom_keywords`` — the seam for tests
#      and callers that want to pass the vocabulary in directly; else
#   2. the active project's ``mechanics/approved.json`` keyword-ability names; else
#   3. empty (evergreen-only).
# The parsed result is cached by ``(path, mtime_ns, size)``; a cache hit still
# stats the file (cheap) but skips the read + JSON parse. The cache tuple is
# immutable and swapped atomically; readers snapshot it into a local before
# indexing, so a concurrent write can't tear a read (worst case: two threads
# recompute the same value, which is idempotent).
_custom_keywords_override: frozenset[str] | None = None
_approved_cache: tuple[str, tuple[int, int], frozenset[str]] | None = None

# Only keyword-ability mechanics template as standalone keyword-only lines
# (e.g. "Frostbite 2"). Ability words and keyword actions appear inside ability
# text, so they must not classify a line as keyword-only. reminder_injector
# defaults a missing keyword_type to this same value.
_KEYWORD_ABILITY_TYPE = "keyword_ability"


def set_custom_keywords(keywords: Iterable[str] | None) -> None:
    """Override the custom-keyword vocabulary the validators recognize.

    Pass an iterable of mechanic names to pin them (lowercased); pass ``None``
    to clear the override and fall back to active-project resolution. The seam
    lets callers feed keywords in directly and lets tests supply a set's
    mechanics without an on-disk project.
    """
    global _custom_keywords_override
    if keywords is None:
        _custom_keywords_override = None
    else:
        _custom_keywords_override = frozenset(k.strip().lower() for k in keywords if k.strip())


def _active_custom_keywords() -> frozenset[str]:
    """Resolve custom keywords from the active project's approved mechanics.

    Reads ``<asset_folder>/mechanics/approved.json`` and returns the lowercased
    ``name`` of each keyword-ability mechanic. Returns an empty set when no
    project is open,
    the file is missing, or it can't be parsed — the validators then fall back
    to evergreen-only recognition. Cached by ``(path, mtime_ns, size)``.
    """
    global _approved_cache

    from mtgai.io.asset_paths import NoAssetFolderError, set_artifact_dir

    try:
        path = set_artifact_dir() / "mechanics" / "approved.json"
    except NoAssetFolderError:
        return frozenset()

    try:
        st = path.stat()
    except OSError:
        _approved_cache = None
        return frozenset()

    key = str(path)
    stamp = (st.st_mtime_ns, st.st_size)
    cache = _approved_cache  # snapshot once: atomic read of an immutable tuple
    if cache is not None and cache[0] == key and cache[1] == stamp:
        return cache[2]

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()

    names = frozenset(
        m["name"].strip().lower()
        for m in data
        if isinstance(m, dict)
        and m.get("keyword_type", _KEYWORD_ABILITY_TYPE) == _KEYWORD_ABILITY_TYPE
        and isinstance(m.get("name"), str)
        and m["name"].strip()
    )
    _approved_cache = (key, stamp, names)
    return names


def custom_keywords() -> frozenset[str]:
    """Return the active set's custom-mechanic keywords (override or approved.json)."""
    if _custom_keywords_override is not None:
        return _custom_keywords_override
    return _active_custom_keywords()


def all_keywords() -> set[str]:
    """Return every keyword the validators recognize: evergreen + custom."""
    return EVERGREEN_KEYWORDS | custom_keywords()


# Parenthesized spans hold reminder text (injected programmatically by
# ``reminder_injector``, never LLM-generated). Validators that scan or rewrite
# oracle text must skip these spans byte-for-byte — a reminder may legitimately
# contain phrases the fixers target ("enters the battlefield", "can't"/"cannot").
_PAREN_SPAN_RE = re.compile(r"\([^)]*\)")

# A permanent that enters tapped negates haste — a set-agnostic rules nonbo.
_ENTERS_TAPPED_RE = re.compile(r"enters (the battlefield )?tapped", re.IGNORECASE)
_HASTE_RE = re.compile(r"\bhaste\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _strip_reminder(text: str) -> str:
    """Return ``text`` with parenthesized reminder spans removed.

    Used by scans so a phrase that only appears inside reminder text isn't
    reported as an error.
    """
    return _PAREN_SPAN_RE.sub("", text)


def _sub_outside_parens(pattern: re.Pattern[str], repl: str, text: str) -> str:
    """Apply ``pattern.sub(repl, ...)`` only to the spans *outside* parentheses.

    Parenthesized reminder text is preserved verbatim, so a fixer can't
    silently rewrite injected reminder phrasing. Reassembles the original
    string with non-paren segments transformed and paren segments untouched.
    """
    out: list[str] = []
    last = 0
    for m in _PAREN_SPAN_RE.finditer(text):
        out.append(pattern.sub(repl, text[last : m.start()]))
        out.append(m.group())
        last = m.end()
    out.append(pattern.sub(repl, text[last:]))
    return "".join(out)


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
    kws = all_keywords()
    return any(any(p == kw or p.startswith(kw + " ") for kw in kws) for p in parts)


def _is_keyword_only_line(line: str) -> bool:
    """Return True if every comma-separated segment is a recognized keyword.

    Handles parameterized keywords like "Ward {2}", "Protection from red",
    "Salvage 3", "Malfunction 2", etc. — checks only the base keyword word.
    """
    stripped = line.strip()
    if not stripped:
        return False

    parts = [p.strip() for p in stripped.split(",")]
    kws = all_keywords()
    for part in parts:
        if not part:
            return False
        # Extract the base keyword: first word(s) that match a known keyword
        part_lower = part.lower()
        matched = False
        for kw in kws:
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
    #    Skip matches inside parenthesized reminder text and inside
    #    quoted granted-ability text (e.g. has "When this creature dies, …").
    # ------------------------------------------------------------------
    for i, line in enumerate(lines, start=1):
        line_no_reminder = re.sub(r"\([^)]*\)", "", line)
        line_no_quoted = re.sub(r'"[^"]*"', "", line_no_reminder)
        for m in SELF_REF_BAD.finditer(line_no_quoted):
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
    oracle_no_reminder_lower = _strip_reminder(oracle).lower()
    if "enters the battlefield" in oracle_no_reminder_lower:
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
    if re.search(r"[Aa]dd (?:one )?(?:white|blue|black|red|green) mana", oracle):
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
        for kw in all_keywords():
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
        if not stripped.endswith((".", '"', ")")):
            errors.append(
                _auto(
                    "oracle_text",
                    f'Line {i}: Does not end with a period or closing quote: "{stripped}"',
                    "Rules text lines should end with a period.",
                    error_code="rules_text.line_period",
                )
            )

    # ------------------------------------------------------------------
    # 13. Haste + enters-tapped nonbo — MANUAL
    # ------------------------------------------------------------------
    # Scan outside reminder text: a reminder may legitimately describe entering
    # tapped (e.g. a custom mechanic's reminder) without being a real nonbo.
    oracle_body = _strip_reminder(oracle)
    has_haste = bool(_HASTE_RE.search(oracle_body))
    enters_tapped = bool(_ENTERS_TAPPED_RE.search(oracle_body))

    if has_haste and enters_tapped:
        errors.append(
            _manual(
                "oracle_text",
                "Haste is a nonbo with entering tapped — the permanent "
                "enters tapped, so haste is negated",
                "Remove haste, or remove the enters-tapped clause.",
                error_code="rules_text.haste_enters_tapped_nonbo",
            )
        )

    # ------------------------------------------------------------------
    # 14. Keyword capitalization — AUTO
    # ------------------------------------------------------------------
    kws = all_keywords()
    for line in lines:
        if not _is_keyword_line(line):
            continue
        parts = [p.strip() for p in line.split(",")]
        for part in parts[1:]:
            if not part:
                continue
            if part[0].isupper() and part.lower() in kws:
                errors.append(
                    _auto(
                        "oracle_text",
                        f'Keyword "{part}" should be lowercase (except at start of line)',
                        f'Use "{part.lower()}"',
                        error_code="rules_text.keyword_capitalization",
                    )
                )

    # ------------------------------------------------------------------
    # 15. "cannot" / "can not" → "can't" — AUTO
    # ------------------------------------------------------------------
    if "can not" in oracle_no_reminder_lower or "cannot" in oracle_no_reminder_lower:
        errors.append(
            _auto(
                "oracle_text",
                'MTG rules text uses "can\'t", not "can not" or "cannot"',
                'Replace with "can\'t"',
                error_code="rules_text.cannot",
            )
        )

    # ------------------------------------------------------------------
    # 16. Modal bullets typed as ``*`` instead of ``•`` — AUTO
    #     LLMs often default to markdown asterisks for bulleted lists. MTG
    #     uses a bullet point (U+2022) for modal-spell choices. Substitute
    #     the bullet character when ``*`` appears at the start of a line
    #     followed by whitespace (the unambiguous modal-bullet pattern;
    #     leaves mid-line ``**bold**`` and bare ``*`` alone).
    # ------------------------------------------------------------------
    if re.search(r"(?m)^\s*\*\s+\S", oracle):
        errors.append(
            _auto(
                "oracle_text",
                "Modal bullets use '*' instead of '•'",
                "Replace leading '*' on bullet lines with '•'.",
                error_code="rules_text.modal_asterisk_bullet",
            )
        )

    # ------------------------------------------------------------------
    # 17. Oracle starts with a redundant type word — AUTO
    #     Some LLM outputs prefix the oracle with the card's type ("Artifact.",
    #     "Creature.", "Land") as if it were a header. The type is already in
    #     ``type_line``; the redundant prefix isn't MTG templating. Strip it.
    # ------------------------------------------------------------------
    if lines and _TYPE_PREFIX_RE.match(lines[0].strip()):
        errors.append(
            _auto(
                "oracle_text",
                f'Oracle text starts with redundant type prefix line "{lines[0]!r}"',
                "Remove the type-only first line — the type is already in type_line.",
                error_code="rules_text.oracle_type_prefix",
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


_ETB_RE = re.compile(r"enters the battlefield", re.IGNORECASE)


def fix_enters_the_battlefield(card: Card, error: ValidationError) -> Card:
    """Replace 'enters the battlefield' with 'enters' outside reminder text."""
    if not card.oracle_text:
        return card
    new_oracle = _sub_outside_parens(_ETB_RE, "enters", card.oracle_text)
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
        for kw in all_keywords():
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
        if not stripped.endswith((".", '"', ")")):
            new_lines.append(line + ".")
        else:
            new_lines.append(line)

    new_oracle = "\n".join(new_lines)
    return card.model_copy(update={"oracle_text": new_oracle})


def fix_keyword_capitalization(card: Card, error: ValidationError) -> Card:
    """Lowercase non-first keywords on keyword lines."""
    if not card.oracle_text:
        return card

    kws = all_keywords()
    new_lines = []
    for line in card.oracle_text.split("\n"):
        if not _is_keyword_line(line):
            new_lines.append(line)
            continue
        parts = [p.strip() for p in line.split(",")]
        fixed_parts = [parts[0]]  # Keep first keyword's case
        for part in parts[1:]:
            if part and part[0].isupper() and part.lower() in kws:
                fixed_parts.append(part[0].lower() + part[1:])
            else:
                fixed_parts.append(part)
        new_lines.append(", ".join(fixed_parts))

    new_oracle = "\n".join(new_lines)
    return card.model_copy(update={"oracle_text": new_oracle})


_CANNOT_RE = re.compile(r"\bcannot\b", re.IGNORECASE)
_CAN_NOT_RE = re.compile(r"\bcan not\b", re.IGNORECASE)


def fix_cannot(card: Card, error: ValidationError) -> Card:
    """Replace "cannot" / "can not" with "can't" outside reminder text."""
    if not card.oracle_text:
        return card
    new_oracle = _sub_outside_parens(_CANNOT_RE, "can't", card.oracle_text)
    new_oracle = _sub_outside_parens(_CAN_NOT_RE, "can't", new_oracle)
    return card.model_copy(update={"oracle_text": new_oracle})


def fix_modal_asterisk_bullet(card: Card, error: ValidationError) -> Card:
    """Replace leading ``*`` on bullet lines with ``•`` (the MTG bullet point).

    Only fires on lines whose first non-whitespace character is ``*`` followed
    by whitespace — so mid-line ``**bold**`` and bare ``*`` are left alone.
    """
    if not card.oracle_text:
        return card
    new_oracle = re.sub(r"(?m)^(\s*)\*(\s+)", r"\1•\2", card.oracle_text)
    return card.model_copy(update={"oracle_text": new_oracle})


def fix_oracle_type_prefix(card: Card, error: ValidationError) -> Card:
    """Strip a leading "Artifact." / "Creature." / etc. line from oracle_text.

    Also eats a single blank line immediately following it so the remaining
    oracle text doesn't start with an empty line.
    """
    if not card.oracle_text:
        return card
    lines = card.oracle_text.split("\n")
    if not lines or not _TYPE_PREFIX_RE.match(lines[0].strip()):
        return card
    rest = lines[1:]
    if rest and not rest[0].strip():
        rest = rest[1:]
    return card.model_copy(update={"oracle_text": "\n".join(rest)})
