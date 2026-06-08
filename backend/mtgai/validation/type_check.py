"""Validator 3: Type-Line / Stat Consistency.

Catches structural impossibilities that LLMs frequently produce, such as
creatures without power/toughness, planeswalkers without loyalty, auras
missing "Enchant", and equipment missing "Equip".
"""

from __future__ import annotations

import re

from mtgai.models.card import Card
from mtgai.validation import ValidationError, ValidationSeverity

# ---------------------------------------------------------------------------
# Canonical type-line ordering
# ---------------------------------------------------------------------------

# Printed MTG ordering of supertypes / card types. A type line reads
# ``<supertypes> <card types> — <subtypes>``; within each group the words have a
# fixed order on real cards ("Legendary Enchantment", "Artifact Creature",
# "Enchantment Artifact", "Land Creature", "Kindred Sorcery"). Lower rank prints
# first; an unknown word sorts last but keeps its relative position (stable sort).
_SUPERTYPE_ORDER = {"Basic": 0, "Legendary": 1, "Snow": 2, "World": 3}
_CARD_TYPE_ORDER = {
    "Kindred": 0,
    "Tribal": 0,
    "Enchantment": 1,
    "Artifact": 2,
    "Land": 3,
    "Creature": 4,
    "Planeswalker": 5,
    "Battle": 6,
    "Instant": 7,
    "Sorcery": 7,
}

# The three separators we accept between card types and subtypes (em dash, en
# dash, double hyphen). We reuse whichever the card already had when rebuilding.
_TYPE_SEP_RE = re.compile(r"\s(\u2014|\u2013|--)\s")


def _detect_type_sep(type_line: str) -> str:
    """Return the dash separator the type line uses, defaulting to an em dash."""
    match = _TYPE_SEP_RE.search(type_line)
    return match.group(1) if match else "—"


def canonical_type_line(card: Card) -> str:
    """Build the correctly-ordered type line from a card's structured parts.

    ``<supertypes> <card types> [— <subtypes>]`` with each group in printed MTG
    order (so "Creature — Artifact Peacekeeper" becomes "Artifact Creature —
    Peacekeeper"). Card types and supertypes come from ``card_types`` /
    ``supertypes`` (which the schema parser derives from the raw line, correctly
    pulling a card type written after the dash back to the main side); the
    subtypes and dash style are preserved as-is. Returns the original line
    untouched if no card type is recognised (nothing safe to rebuild from).
    """
    supers = sorted(card.supertypes, key=lambda t: _SUPERTYPE_ORDER.get(t, 50))
    types = sorted(card.card_types, key=lambda t: _CARD_TYPE_ORDER.get(t, 50))
    if not types:
        return card.type_line
    main = " ".join(supers + types)
    if card.subtypes:
        sep = _detect_type_sep(card.type_line)
        return f"{main} {sep} {' '.join(card.subtypes)}"
    return main


# ---------------------------------------------------------------------------
# Auto-fixers
# ---------------------------------------------------------------------------


def fix_type_line_order(card: Card, _error: ValidationError) -> Card:
    """Rewrite ``type_line`` (and structured parts) into canonical order.

    Re-derives ``supertypes`` / ``card_types`` / ``subtypes`` from the current
    line (so a card type stranded after the dash is reclassified) and rebuilds
    the string in printed MTG order, keeping every type the card already had.
    """
    from mtgai.validation.schema import _parse_type_line

    parsed = _parse_type_line(card)
    return parsed.model_copy(update={"type_line": canonical_type_line(parsed)})


def fix_enchantment_artifact(card: Card, _error: ValidationError) -> Card:
    """Remove 'Enchantment' from an Enchantment Artifact type line.

    Works from ``type_line`` directly since ``card_types`` may be empty
    (the parsed list isn't always populated by the generation pipeline).
    """
    # Parse type_line: "Legendary Enchantment -- Artifact" -> main / subtypes
    if " -- " in card.type_line:
        main_part, sub_part = card.type_line.split(" -- ", 1)
    else:
        main_part, sub_part = card.type_line, ""

    # Remove "Enchantment" from the main part's words
    words = [w for w in main_part.split() if w != "Enchantment"]
    new_main = " ".join(words)

    # Also ensure "Artifact" is present (it may have been on the subtypes side)
    main_words_lower = [w.lower() for w in words]
    if "artifact" not in main_words_lower:
        # Artifact was after the --, move it to main types
        sub_words = [w for w in sub_part.split() if w.lower() != "artifact"]
        words.append("Artifact")
        new_main = " ".join(words)
        sub_part = " ".join(sub_words)

    new_type_line = f"{new_main} -- {sub_part.strip()}" if sub_part.strip() else new_main

    new_card_types = [t for t in card.card_types if t != "Enchantment"]
    if "Artifact" not in new_card_types:
        new_card_types.append("Artifact")

    return card.model_copy(update={"type_line": new_type_line, "card_types": new_card_types})


def fix_pt_in_oracle(card: Card, _error: ValidationError) -> Card:
    """Move a leaked bare ``N/N`` oracle line into power/toughness and strip it.

    The local card-gen model frequently writes a creature's stats as a standalone
    ``"2/2"`` line in ``oracle_text`` (sometimes omitting the structured fields).
    This recovers it deterministically: fill only currently-empty stat fields (a
    real structured value wins over the leaked line), drop the bare line from the
    rules box, and eat a blank line left dangling above it so no stray gap renders.
    """
    oracle = card.oracle_text or ""
    found: tuple[str, str] | None = None
    new_lines: list[str] = []
    for line in oracle.split("\n"):
        m = BARE_PT_LINE_RE.match(line.strip())
        if m is not None:
            # Strip every bare P/T line (the model occasionally emits more than
            # one) so none renders; the first supplies the recovered stats.
            if found is None:
                found = (m.group("power"), m.group("toughness"))
            while new_lines and not new_lines[-1].strip():
                new_lines.pop()
            continue
        new_lines.append(line)

    if found is None:
        return card

    updates: dict[str, str] = {"oracle_text": "\n".join(new_lines).rstrip("\n")}
    if card.power is None:
        updates["power"] = found[0]
    if card.toughness is None:
        updates["toughness"] = found[1]
    return card.model_copy(update=updates)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _manual(
    field: str, message: str, suggestion: str | None = None, *, error_code: str
) -> ValidationError:
    return ValidationError(
        validator="type_check",
        severity=ValidationSeverity.MANUAL,
        field=field,
        message=message,
        suggestion=suggestion,
        error_code=error_code,
    )


# Power / toughness / loyalty values the validators accept as legal. Anything
# else trips ``type_check.pt_nonstandard`` (a regen trigger). ``*`` is the
# variable-stat marker (Tarmogoyf etc.); ``1+*``/``2+*``/``*+1`` cover the
# rare expression forms; ``X`` shows up on a handful of mythic creatures.
_VALID_PT_VALUES_RE = re.compile(r"^(?:-?\d+|\*|[12]\+\*|\*\+1|X)$")

# Sentinel strings the LLM occasionally drops into power/toughness/loyalty when
# it means "no value here". We have to catch them explicitly because the schema
# accepts ``str | None`` and these all parse as strings. Case-insensitive.
_PT_SENTINELS = frozenset({"null", "none", "n/a", "na", "-", "—", ""})

# A standalone "N/N" line — the local card-gen model's habit of writing a
# creature's stats as a bare line in oracle_text instead of populating the
# structured power/toughness fields (e.g. ``"Energize 1\n\n2/2."``). Matches a
# line that is *entirely* a P/T pair (each side an integer, ``*``, or ``X``,
# optionally period-terminated) so it never catches an inline ``+1/+1`` counter
# clause. Shared with ``rules_text`` so the line-period fixer doesn't cement a
# period onto the leaked stats. ``rules_text`` imports this; keep it public.
BARE_PT_LINE_RE = re.compile(r"^(?P<power>-?\d+|\*|X)\s*/\s*(?P<toughness>-?\d+|\*|X)\.?$")


def find_bare_pt_line(oracle_text: str | None) -> tuple[str, str] | None:
    """Return the ``(power, toughness)`` of a bare ``N/N`` line leaked into oracle.

    Returns the first standalone P/T line's values, or ``None`` if none is
    present. See :data:`BARE_PT_LINE_RE` for the (deliberately narrow) match.
    """
    for line in (oracle_text or "").split("\n"):
        m = BARE_PT_LINE_RE.match(line.strip())
        if m:
            return m.group("power"), m.group("toughness")
    return None


# ---------------------------------------------------------------------------
# Stat-shape helpers (used by validate_type_consistency below)
# ---------------------------------------------------------------------------


def _validate_stat_shape(field: str, value: str | None) -> list[ValidationError]:
    """Catch malformed power/toughness/loyalty strings.

    Produces at most one finding per field. All three findings are regen
    triggers — the card can't be saved with garbage in the stat fields, and
    the LLM needs to write a clean integer (or ``*`` / ``X``) on the next
    attempt.

    Check order matters because some inputs match multiple patterns:
    1. **Sentinels first** so ``"N/A"`` (which also contains ``/``) is
       classified as a "no value" sentinel rather than a slashed stat.
    2. **Slash next** for the canonical ``power="1/1"`` mistake (both stats
       stuffed into one field).
    3. **Nonstandard last** for anything else outside the legal allowlist.
    """
    if value is None:
        return []
    stripped = value.strip()

    # Sentinel strings the LLM uses to mean "no value". Schema accepts these
    # as strings, but they aren't real stats — regen rather than try to coerce.
    # Checked first because ``"N/A"`` etc. would otherwise match the slash rule.
    if stripped.lower() in _PT_SENTINELS:
        return [
            _manual(
                field,
                f"{field}={value!r} is a sentinel string, not a real value — "
                f"use null for absent stats, or a real number/'*' for present ones",
                f"Set {field} to a real value (integer or '*'), or omit the field.",
                error_code="type_check.pt_literal_null",
            )
        ]

    # A slash means the model wrote both stats into one field, like
    # ``power="1/1"``.
    if "/" in value:
        return [
            _manual(
                field,
                f"{field}={value!r} contains '/' — looks like both stats were "
                f"stuffed into one field (write power and toughness separately)",
                f"Set {field} to a single value, e.g. '2'.",
                error_code="type_check.pt_slash",
            )
        ]

    # Everything else: must match the small allowlist of legal MTG stat values.
    if not _VALID_PT_VALUES_RE.match(stripped):
        return [
            _manual(
                field,
                f"{field}={value!r} isn't a legal Magic stat value "
                f"(expected an integer, '*', 'X', or one of '1+*'/'2+*'/'*+1')",
                f"Set {field} to a legal value such as '2' or '*'.",
                error_code="type_check.pt_nonstandard",
            )
        ]

    return []


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def validate_type_consistency(card: Card) -> list[ValidationError]:
    """Check that the card's type line, stats, and abilities are consistent."""
    # If card_types wasn't populated (e.g. loaded from disk), derive from type_line
    if not card.card_types and card.type_line:
        from mtgai.validation.schema import _parse_type_line

        card = _parse_type_line(card)

    errors: list[ValidationError] = []

    # 0. Structural shape of power / toughness / loyalty. These checks fire
    #    BEFORE the "creature has P/T" semantics below so a garbage stat like
    #    ``"1/1"`` or ``"null"`` triggers regen rather than silently passing
    #    the "has power and toughness" gate downstream. All three findings
    #    are regen triggers (see _is_regen_trigger in validation/__init__.py).
    errors += _validate_stat_shape("power", card.power)
    errors += _validate_stat_shape("toughness", card.toughness)
    errors += _validate_stat_shape("loyalty", card.loyalty)

    # 0b. Non-land card must have a mana cost. ``mana_cost`` is typed
    #    ``str | None`` on the model (Land is the only zero-cost card type), so
    #    a None / empty string on anything else slips past schema and produces
    #    an uncastable card downstream — regen.
    if (
        card.type_line
        and "land" not in card.type_line.lower()
        and not (card.mana_cost and card.mana_cost.strip())
    ):
        errors.append(
            _manual(
                "mana_cost",
                "Non-land card has no mana cost — card is uncastable",
                "Set a mana cost. Only Land cards may have an empty cost.",
                error_code="type_check.nonland_missing_cost",
            )
        )

    is_creature = "Creature" in card.card_types
    is_planeswalker = "Planeswalker" in card.card_types
    # A Vehicle is a non-creature permanent that MUST carry printed power/toughness
    # so it can fight once crewed — the one non-creature type that has stats. It
    # therefore inverts the "non-creatures omit P/T" rules below. Match
    # case-insensitively: the schema parser stores subtypes verbatim, so an LLM
    # type line of "Artifact — vehicle" yields subtypes=["vehicle"].
    is_vehicle = any(s.strip().casefold() == "vehicle" for s in card.subtypes)
    has_power = card.power is not None
    has_toughness = card.toughness is not None
    has_loyalty = card.loyalty is not None
    has_faces = card.card_faces is not None and len(card.card_faces) > 0

    # A bare "N/N" line leaked into oracle_text — the local model writing stats
    # as rules text. Recoverable (AUTO) in 1b below.
    leaked_pt = find_bare_pt_line(card.oracle_text) if is_creature else None

    # 1. Creatures must have power and toughness. When the stats are genuinely
    #    absent and *not* recoverable from a leaked oracle line, this is a regen
    #    trigger (see _REGEN_TRIGGER_CODES) — the card can't ship as a P/T-less
    #    creature. When a bare "N/N" line is present, 1b recovers it instead, so
    #    don't also flag for regen.
    if is_creature and (not has_power or not has_toughness) and leaked_pt is None:
        errors.append(
            _manual(
                "power/toughness",
                "Creature is missing power and/or toughness",
                "Set power and toughness for this creature.",
                error_code="type_check.creature_missing_pt",
            )
        )

    # 1b. Vehicles must have power and toughness too — even when they aren't
    #     creatures. A crewed Vehicle with no printed P/T can't fight; the model
    #     tends to omit them because it's been told "non-creatures have no P/T".
    #     Skip DFCs (P/T lives on the faces), mirroring rule 2.
    if is_vehicle and (not has_power or not has_toughness) and not has_faces:
        errors.append(
            _manual(
                "power/toughness",
                "Vehicle is missing power and/or toughness — a Vehicle must have "
                "printed P/T to function when crewed",
                "Set power and toughness for this Vehicle.",
                error_code="type_check.vehicle_missing_pt",
            )
        )

    # 1c. A bare "N/N" P/T line leaked into oracle_text — AUTO-move it to the
    #     structured stat fields and strip it from the rules box. Fires whenever
    #     the line is present (even if the stats are also set) so the redundant
    #     line never renders as a stray "2/2." in the text box.
    if is_creature and leaked_pt is not None:
        errors.append(
            ValidationError(
                validator="type_check",
                severity=ValidationSeverity.AUTO,
                field="power/toughness",
                message=(
                    f'Power/toughness "{leaked_pt[0]}/{leaked_pt[1]}" leaked into '
                    "oracle_text as a bare line — moving it to the stat fields."
                ),
                suggestion="Put creature stats in power/toughness, not oracle_text.",
                error_code="type_check.pt_in_oracle",
            )
        )

    # 2. Non-creatures must NOT have power/toughness (skip DFCs and Vehicles,
    #    which legitimately carry stats while not being creatures).
    if not is_creature and not is_vehicle and (has_power or has_toughness) and not has_faces:
        errors.append(
            _manual(
                "power/toughness",
                "Non-creature card has power and/or toughness set",
                "Remove power/toughness from non-creature cards.",
                error_code="type_check.noncreature_has_pt",
            )
        )

    # 3. Planeswalkers must have loyalty
    if is_planeswalker and not has_loyalty:
        errors.append(
            _manual(
                "loyalty",
                "Planeswalker is missing starting loyalty",
                "Set starting loyalty for this planeswalker.",
                error_code="type_check.pw_missing_loyalty",
            )
        )

    # 4. Non-planeswalkers must NOT have loyalty
    if not is_planeswalker and has_loyalty:
        errors.append(
            _manual(
                "loyalty",
                "Non-planeswalker card has loyalty set",
                "Remove loyalty from non-planeswalker cards.",
                error_code="type_check.non_pw_has_loyalty",
            )
        )

    # 5. Instants and sorceries must NOT have power/toughness
    if ("Instant" in card.card_types or "Sorcery" in card.card_types) and (
        has_power or has_toughness
    ):
        errors.append(
            _manual(
                "power/toughness",
                "Instant or sorcery must not have power/toughness",
                "Remove power/toughness from instant/sorcery cards.",
                error_code="type_check.spell_has_pt",
            )
        )

    # 6. Auras must have "Enchant" ability
    if "Aura" in card.subtypes:
        has_enchant = any(line.startswith("Enchant ") for line in card.oracle_text.split("\n"))
        if not has_enchant:
            errors.append(
                _manual(
                    "oracle_text",
                    "Aura is missing an 'Enchant' ability",
                    "Auras must have an 'Enchant [permanent type]' ability.",
                    error_code="type_check.aura_missing_enchant",
                )
            )

    # 7. Equipment must have "Equip" ability
    if "Equipment" in card.subtypes:
        has_equip = bool(
            re.search(r"(?m)^Equip\b", card.oracle_text)
            or "Equip {" in card.oracle_text
            or "Equip—" in card.oracle_text
        )
        if not has_equip:
            errors.append(
                _manual(
                    "oracle_text",
                    "Equipment is missing an 'Equip' ability",
                    "Equipment must have an 'Equip {cost}' ability.",
                    error_code="type_check.equipment_missing_equip",
                )
            )

    # 8. Enchantment Artifact is almost never correct — strip Enchantment
    if "Enchantment" in card.card_types and "Artifact" in card.card_types:
        errors.append(
            ValidationError(
                validator="type_check",
                severity=ValidationSeverity.AUTO,
                field="type_line",
                message=(
                    "Enchantment Artifact is an extremely rare type combination "
                    "(only Theros gods' weapons in all of MTG). "
                    "Removing 'Enchantment' to make this a plain Artifact."
                ),
                suggestion="Remove 'Enchantment' from type_line.",
                error_code="type_check.enchantment_artifact",
            )
        )

    # 8b. Type line must be in canonical printed order: supertypes, then card
    #     types, then a dash, then subtypes. LLMs frequently strand a card type
    #     after the dash ("Creature — Artifact Peacekeeper") or order the main
    #     types wrong ("Creature Artifact"); the structured parts come out right
    #     but the raw string — what renders — keeps the bad order. AUTO-rebuild it.
    if card.type_line:
        parsed = card if card.card_types else None
        if parsed is None:
            from mtgai.validation.schema import _parse_type_line

            parsed = _parse_type_line(card)
        if parsed.card_types and card.type_line != canonical_type_line(parsed):
            errors.append(
                ValidationError(
                    validator="type_check",
                    severity=ValidationSeverity.AUTO,
                    field="type_line",
                    message=(
                        f"Type line '{card.type_line}' is out of canonical order — "
                        f"rewriting to '{canonical_type_line(parsed)}' "
                        "(card types before the dash, subtypes after)."
                    ),
                    suggestion="Order the type line as <supertypes> <card types> — <subtypes>.",
                    error_code="type_check.type_line_order",
                )
            )

    # 9. Type line matches card_types/subtypes/supertypes
    if card.type_line:
        type_line_lower = card.type_line.lower()
        for supertype in card.supertypes:
            if supertype.lower() not in type_line_lower:
                errors.append(
                    _manual(
                        "type_line",
                        f"Supertype '{supertype}' not found in type_line '{card.type_line}'",
                        "Ensure type_line includes all supertypes.",
                        error_code="type_check.supertype_missing",
                    )
                )
        for card_type in card.card_types:
            if card_type.lower() not in type_line_lower:
                errors.append(
                    _manual(
                        "type_line",
                        f"Card type '{card_type}' not found in type_line '{card.type_line}'",
                        "Ensure type_line includes all card types.",
                        error_code="type_check.card_type_missing",
                    )
                )
        # Subtypes should appear after a dash separator
        dash_match = re.search(r"\s(?:\u2014|\u2013|--)\s", card.type_line)
        if card.subtypes and dash_match:
            subtype_part = card.type_line[dash_match.end() :].lower()
            for subtype in card.subtypes:
                if subtype.lower() not in subtype_part:
                    errors.append(
                        _manual(
                            "type_line",
                            f"Subtype '{subtype}' not found after dash in "
                            f"type_line '{card.type_line}'",
                            "Ensure type_line includes all subtypes after the dash separator.",
                            error_code="type_check.subtype_missing",
                        )
                    )
        elif card.subtypes and not dash_match:
            errors.append(
                _manual(
                    "type_line",
                    f"Card has subtypes {card.subtypes} but type_line "
                    f"'{card.type_line}' has no dash separator",
                    "Use ' — ' (em dash) to separate types from subtypes.",
                    error_code="type_check.missing_dash",
                )
            )

    # 9. Cards with power/toughness should include "Creature" in card_types
    #    (Vehicles are the exception — they carry P/T without being creatures).
    if has_power and has_toughness and not is_creature and not is_vehicle:
        errors.append(
            _manual(
                "card_types",
                "Card has power/toughness but 'Creature' is not in card_types",
                "Card has power/toughness but 'Creature' is not in card_types.",
                error_code="type_check.pt_without_creature",
            )
        )

    return errors
