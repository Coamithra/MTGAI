"""Validator 2: Mana Cost / CMC Consistency.

Verifies internal consistency between mana_cost, cmc, colors, color_identity,
and mana_cost_parsed fields. Catches format errors, CMC miscalculations,
color mismatches, and canonical colored-symbol ordering violations.

Colored mana symbols in ``mana_cost`` are ordered by the canonical MTG colour
wheel: generic/X/colorless first, then the colored pips along the *shortest
contiguous arc* of WUBRG (the "shortest way around" rule — so ``{G}{W}`` not
``{W}{G}`` for the green-white pair). See :func:`canonical_color_sequence`. This
is distinct from the ``colors`` / ``color_identity`` *list* fields, which match
Scryfall's flat WUBRG sort regardless of how the cost reads.
"""

from __future__ import annotations

import re

from mtgai.models.card import Card, ManaCost
from mtgai.models.enums import Color
from mtgai.validation import ValidationError, ValidationSeverity

# Recognized single mana symbols (inner text, sans braces):
#   {2}        generic
#   {W}/{C}/{X} colored / colorless / variable
#   {W/U}      hybrid (two colors)
#   {W/P}      phyrexian
#   {2/W}      monocolor (twobrid) hybrid — pay 2 generic OR one W
# A leading digit run is either pure generic OR the generic half of a twobrid.
#
# This is deliberately NARROWER than ``rules_text.MANA_SYM_VALID`` (which also
# accepts {S}/{T}/{Q}): {T}/{Q} are ability-activation symbols that appear in
# *oracle text*, never in a castable ``mana_cost``; {S} (snow) is a legal cost
# symbol but unsupported by this toolchain. Rather than silently rewrite an
# unsupported/unknown cost symbol, ``validate_mana_consistency`` flags it MANUAL
# (``mana.unrecognized_symbol``) — see _invalid_format_is_auto_fixable.
MANA_SYMBOL_PATTERN = re.compile(r"\{(\d+(?:/[WUBRGP])?|[WUBRGCX](?:/[WUBRGP])?)\}")
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
            parts = sym.split("/")
            # Twobrid ({2/W}): CMC is the generic half (the higher cost). A
            # color/phyrexian hybrid ({W/U}, {W/P}) is worth 1.
            if parts[0].isdigit():
                cmc += int(parts[0])
            else:
                cmc += 1
            for part in parts:
                if part in COLOR_SYMBOLS:
                    colors.add(part)
                    color_sequence.append(part)
        elif sym in COLOR_SYMBOLS:
            cmc += 1
            colors.add(sym)
            color_sequence.append(sym)

    return cmc, colors, x_count, color_sequence


# The WUBRG colour wheel as a cycle. Real Magic prints a multicolour cost's
# colored pips along the *shortest contiguous arc* of this wheel (the "shortest
# way around" rule), NOT in flat WUBRG order — so e.g. the green-white pair is
# {G}{W} (the G->W arc), not {W}{G}, and the red-white pair is {R}{W}, not {W}{R}.
_WHEEL = ("W", "U", "B", "R", "G")


def canonical_color_sequence(colors: set[str]) -> list[str]:
    """Return the colors in canonical MTG print order for that *combination*.

    Real cards order colored mana symbols along the **shortest contiguous arc**
    of the WUBRG colour wheel (the "shortest way around" rule), not in flat WUBRG
    order. This reproduces every printed ordering verified against Scryfall:

    * **Mono / colorless** — the single color (trivial).
    * **Two colors** — the wheel pairs ``WU UB BR RG GW`` (allied, adjacent) and
      ``WB UR BG RW GU`` (enemy); the three wheel-wrap pairs ``GW``/``RW``/``GU``
      are exactly where a naive WUBRG sort disagreed (it produced ``WG``/``WR``/
      ``UG``) — the bug this fixes.
    * **Three colors** — the ten shards/wedges, e.g. Bant ``GWU``, Esper ``WUB``,
      Grixis ``UBR``, Abzan ``WBG``, Mardu ``RWB``, Sultai ``BGU``.
    * **Four colors** — the contiguous-arc-minus-one-gap order, e.g. Atraxa
      ``GWUB``, Saskia ``BRGW``, Yidris ``UBRG``, Kynaios ``RGWU``.
    * **Five colors** — always ``WUBRG``.

    The algorithm: among the five cyclic rotations of the wheel, pick the one
    whose first present color begins the **shortest** window covering every
    present color (i.e. the *largest* gap between consecutive present colors is
    placed after the last one), then read the present colors off in that order.
    The three-color **wedges** are the one exception — their three colors sit
    equidistant on the wheel (no unique largest gap), so there's no single
    shortest arc; they instead follow the Khans convention of the center color
    (the one whose two enemies are the other two) in the *middle*, flanked by the
    pair in wheel order: Abzan ``WBG``, Jeskai ``URW``, Sultai ``BGU``,
    Mardu ``RWB``, Temur ``GUR``.
    """
    present = [c for c in _WHEEL if c in colors]
    n = len(_WHEEL)
    # 0/1 colour is trivial; 5 colours is always flat WUBRG (no gaps to weigh).
    if len(present) <= 1 or len(present) == n:
        return present

    present_idx = sorted(_WHEEL.index(c) for c in present)
    gaps = [(present_idx[i] - present_idx[i - 1]) % n for i in range(len(present_idx))]
    max_gap = max(gaps)

    # A unique largest gap defines a single shortest arc (2-/4-colour and the
    # three-colour shards): start right after that gap and read clockwise.
    if gaps.count(max_gap) == 1:
        start = present_idx[gaps.index(max_gap)]
        rotation = [_WHEEL[(start + k) % n] for k in range(n)]
        return [c for c in rotation if c in colors]

    # No unique largest gap -> a three-colour wedge (three equidistant colours,
    # each an enemy of the others, spaced by 2 on the wheel). It reads as an arc
    # of +2 ("enemy") steps: the center color sits in the middle, flanked by the
    # pair, e.g. Jeskai U->R->W (each step +2 mod 5). Start at the color whose
    # -2 predecessor is absent (the head of that chain).
    start = next(i for i in present_idx if _WHEEL[(i - 2) % n] not in colors)
    chain = [_WHEEL[(start + 2 * k) % n] for k in range(len(present_idx))]
    return chain


def cost_has_compound_symbol(symbols: list[str]) -> bool:
    """True if any parsed symbol is a hybrid/phyrexian/twobrid (contains ``/``).

    The canonical reorder is restricted to *simple* costs (generic/X/C + plain
    WUBRG pips). A cost carrying a compound symbol like ``{G/U}`` / ``{G/P}`` /
    ``{2/W}`` is left untouched — reordering a hybrid pip risks changing the
    perceived semantics, and our generator effectively never emits them.
    """
    return any("/" in s for s in symbols)


def _canonical_symbol_order(symbols: list[str]) -> list[str]:
    """Reorder mana symbols into canonical MTG order.

    Canonical order is ``{X}`` first, then generic/numeric, then colorless
    ``{C}``, then the colored symbols in the canonical sequence for the cost's
    color *combination* (the shortest-cyclic-arc wheel rule — see
    :func:`canonical_color_sequence`), e.g. ``{G}{W}`` (not ``{W}{G}``) for the
    green-white pair. The sort is stable, so repeated symbols keep their relative
    order. This is the single source of truth shared by the ordering validator
    and its fixer, so a fixed cost always passes the check.

    A cost containing a compound symbol (hybrid/phyrexian/twobrid) is returned
    **unchanged** (conservative skip — see :func:`cost_has_compound_symbol`); the
    check and fixer also bail on such costs so a hybrid pip is never reordered.
    """
    if cost_has_compound_symbol(symbols):
        return list(symbols)

    colored = {s for s in symbols if s in COLOR_SYMBOLS}
    color_rank = {c: i for i, c in enumerate(canonical_color_sequence(colored))}

    def _key(sym: str) -> tuple[int, int]:
        if sym == "X":
            return (0, 0)
        if sym.isdigit():
            return (1, 0)
        if sym == "C":
            return (2, 0)
        return (3, color_rank.get(sym, 99))

    return sorted(symbols, key=_key)


def derive_mana_fields(mana_cost: str | None, oracle_text: str | None = None) -> dict:
    """Derive ``cmc``, ``colors``, and ``color_identity`` from a card's mana.

    These three fields are fully implied by ``mana_cost`` (cmc + colors) and the
    mana symbols in ``oracle_text`` (color_identity), so card generation no longer
    asks the LLM for them — it computes them here instead, from the single source
    of truth. Returns a dict with ``cmc`` (float), ``colors`` and
    ``color_identity`` (WUBRG-ordered lists of color letters). With an empty /
    missing ``mana_cost`` (e.g. lands), cmc is 0 and colors is empty, but
    color_identity still picks up any colored mana symbols in the oracle text.
    """
    cmc, colors, _x_count, _seq = _parse_mana_cost(mana_cost or "")
    identity: set[str] = set(colors)
    for match in MANA_SYMBOL_ANY.finditer(oracle_text or ""):
        for char in match.group(0)[1:-1]:  # strip { }
            if char in COLOR_SYMBOLS:
                identity.add(char)

    def _order(c: str) -> int:
        return WUBRG_ORDER.get(c, 99)

    return {
        "cmc": cmc,
        "colors": sorted(colors, key=_order),
        "color_identity": sorted(identity, key=_order),
    }


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
    # 1. Mana cost format validation
    #    AUTO when every malformed brace is a clean concatenation the fixer can
    #    split losslessly ({2W} -> {2}{W}); MANUAL when any brace is an
    #    unrecognized symbol ({S} snow) the fixer would otherwise silently
    #    delete or mangle — escalate to an LLM retry instead of a lossy rewrite.
    # ------------------------------------------------------------------
    stripped = MANA_SYMBOL_PATTERN.sub("", card.mana_cost)
    if stripped:
        if _invalid_format_is_auto_fixable(card.mana_cost):
            errors.append(
                _auto(
                    "mana_cost",
                    f"Invalid mana_cost format: '{card.mana_cost}'",
                    "Split combined symbols, e.g. {2W} -> {2}{W}.",
                    error_code="mana.invalid_format",
                )
            )
        else:
            errors.append(
                _manual(
                    "mana_cost",
                    f"Unrecognized mana symbol(s) in mana_cost: '{card.mana_cost}'",
                    "Use only valid mana symbols (generic, WUBRG, C, X, hybrid, "
                    "phyrexian, twobrid); fix the cost by hand or regenerate.",
                    error_code="mana.unrecognized_symbol",
                )
            )
        # Don't return early — the fixer will normalize before next validation

    # ------------------------------------------------------------------
    # 2. Parse symbols and compute CMC / colors
    # ------------------------------------------------------------------
    computed_cmc, computed_colors, x_count, _color_sequence = _parse_mana_cost(card.mana_cost)

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
    # 6. Canonical symbol ordering — AUTO
    #    Generic/X must precede colored, and colored must follow the canonical
    #    colour-wheel sequence for the cost's color combination (the
    #    shortest-cyclic-arc rule, NOT flat WUBRG — see canonical_color_sequence).
    #    The old check only ordered the colored symbols among themselves, so a
    #    misplaced generic like {B}{G}{1} (canonical {1}{B}{G}) slipped through.
    # ------------------------------------------------------------------
    # `stripped` non-empty means the cost has unparseable symbols (e.g. a
    # {2/W} twobrid the pattern can't match). Those are owned by the
    # invalid_format check above; skip the order check so we never emit a flag
    # whose fixer would have to rebuild from a lossy `findall`. A compound
    # (hybrid/phyrexian/twobrid) symbol is left untouched too (conservative —
    # reordering a hybrid pip risks changing perceived semantics).
    cost_symbols = MANA_SYMBOL_PATTERN.findall(card.mana_cost)
    skip_order = stripped or cost_has_compound_symbol(cost_symbols)
    canonical_symbols = _canonical_symbol_order(cost_symbols)
    if not skip_order and cost_symbols != canonical_symbols:
        got = "".join(f"{{{s}}}" for s in cost_symbols)
        want = "".join(f"{{{s}}}" for s in canonical_symbols)
        errors.append(
            _auto(
                "mana_cost",
                f"Mana symbols are not in canonical order (generic/X before colored, "
                f"colored in colour-wheel order): got {got}, expected {want}",
                f"Reorder to {want}",
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


# Standalone single-symbol tokens a combined brace can be split into. A digit
# run is generic; a single colored/colorless/variable letter stands alone.
# `P` and `/` are deliberately absent: they only appear *inside* a hybrid
# ({W/P}, {2/W}), which is already a valid whole symbol kept verbatim — there
# is no legal standalone {/} or {P}.
_SPLITTABLE_TOKEN_RE = re.compile(r"\d+|[WUBRGCX]")
_STANDALONE_SYMBOLS = COLOR_SYMBOLS | {"C", "X"}


def _split_combined_symbol(inner: str) -> list[str] | None:
    """Split a combined brace's inner text into standalone symbols, losslessly.

    ``{2W}`` -> ``["{2}", "{W}"]``, ``{2WU}`` -> ``["{2}", "{W}", "{U}"]``. Returns
    ``None`` when the inner text can't be fully consumed into *recognized*
    standalone symbols — e.g. ``{S}`` (snow), ``{2/W}`` (a hybrid, not a
    concatenation), or anything with a stray character. The caller then leaves
    the symbol verbatim rather than emitting garbage (``{/}``) or silently
    dropping the unknown letter, so an AUTO fix never lossy-rewrites a cost it
    doesn't fully understand.
    """
    parts: list[str] = []
    pos = 0
    for m in _SPLITTABLE_TOKEN_RE.finditer(inner):
        if m.start() != pos:  # an unrecognized char was skipped — bail
            return None
        token = m.group(0)
        if not (token.isdigit() or token in _STANDALONE_SYMBOLS):
            return None
        parts.append(f"{{{token}}}")
        pos = m.end()
    if pos != len(inner) or not parts:
        return None
    return parts


def _invalid_format_is_auto_fixable(mana_cost: str) -> bool:
    """True if every malformed brace in ``mana_cost`` is a clean concatenation.

    A cost is AUTO-fixable only when each brace that isn't already a valid symbol
    splits losslessly into recognized standalone symbols (so ``fix_invalid_format``
    can normalize it). A single unrecognized symbol ({S}, a stray ``{/}``) makes
    the whole finding MANUAL so the cost is never silently mutated.
    """
    found_fixable = False
    for match in MANA_SYMBOL_ANY.finditer(mana_cost):
        whole = match.group(0)
        if MANA_SYMBOL_PATTERN.fullmatch(whole):
            continue
        if _split_combined_symbol(whole[1:-1]) is None:
            return False
        found_fixable = True
    return found_fixable


def fix_invalid_format(card: Card, error: ValidationError) -> Card:
    """Normalize a malformed mana_cost by splitting *concatenated* symbols.

    Handles patterns like {2W} -> {2}{W}, {WW} -> {W}{W}, {2WU} -> {2}{W}{U}.
    Each digit run becomes a generic symbol and each colored letter its own.

    Non-lossy: a brace whose inner text isn't a clean concatenation of known
    standalone symbols (e.g. {S} snow, or a {2/W} hybrid) is kept **verbatim**.
    If any such unrecognized symbol survives, the cost is still invalid, so the
    mana.invalid_format finding is left for the LLM-retry (MANUAL) path rather
    than presenting a silently-mutated cost as fixed.
    """
    if not card.mana_cost:
        return card

    # All-or-nothing: only rewrite when every malformed brace splits cleanly into
    # recognized symbols. If any brace is an unrecognized symbol ({S}) we leave
    # the WHOLE cost untouched (the validator already flagged it MANUAL) rather
    # than partially rewriting — a partial mutation of a MANUAL cost is exactly
    # the silent-mutation footgun this fixer is being hardened against.
    if not _invalid_format_is_auto_fixable(card.mana_cost):
        return card

    normalized_parts: list[str] = []
    for match in MANA_SYMBOL_ANY.finditer(card.mana_cost):
        whole = match.group(0)
        if MANA_SYMBOL_PATTERN.fullmatch(whole):
            normalized_parts.append(whole)
            continue
        split = _split_combined_symbol(whole[1:-1])
        # _invalid_format_is_auto_fixable guarantees split is not None here.
        normalized_parts.extend(split)

    new_cost = "".join(normalized_parts)
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
    """Reorder mana_cost symbols into canonical order.

    Generic/X/C first, then the colored pips in the canonical colour-wheel
    sequence for the cost's color combination (the shortest-cyclic-arc rule, e.g.
    ``{G}{W}`` not ``{W}{G}`` — see :func:`canonical_color_sequence`). A cost with
    a compound (hybrid/phyrexian/twobrid) symbol is left untouched (conservative
    skip; the check never flags it either).
    """
    if not card.mana_cost:
        return card

    # A malformed remainder (e.g. an unmatched {2/W} twobrid) would be dropped
    # by rebuilding from `findall` — bail and let invalid_format handle it.
    if MANA_SYMBOL_PATTERN.sub("", card.mana_cost):
        return card

    symbols = MANA_SYMBOL_PATTERN.findall(card.mana_cost)
    if not symbols or cost_has_compound_symbol(symbols):
        return card

    new_cost = "".join(f"{{{s}}}" for s in _canonical_symbol_order(symbols))
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
            # Hybrid — count for the colored half. {2/W} (twobrid) adds its
            # generic half to the generic total and its color to that color.
            parts = sym.split("/")
            if parts[0].isdigit():
                generic += int(parts[0])
            colored_half = next((p for p in parts if p in COLOR_SYMBOLS), None)
            if colored_half == "W":
                w += 1
            elif colored_half == "U":
                u += 1
            elif colored_half == "B":
                b += 1
            elif colored_half == "R":
                r += 1
            elif colored_half == "G":
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
