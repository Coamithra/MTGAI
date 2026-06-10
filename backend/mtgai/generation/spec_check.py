"""Deterministic spec self-check for card generation.

The skeleton relabel writes each slot a one-line descriptor (``tweaked_text``,
falling back to :func:`render_slot_string`) that often pins *hard, parseable*
targets — an exact CMC (``CMC4``), a color identity (``Blue/Green``), a card
type (``enchantment creature``). Today a card that misses one of these is only
caught a full stage later by the LLM conformance gate, each miss costing a whole
regen round; measured live, ~53% of slots were flagged in round 1 and a handful
of exact-CMC misses burned 4-6 rounds re-rolling blind because the model is
never told the delta.

This module is the cheap, deterministic front line: parse the *unambiguous* hard
targets from the descriptor (pure regex, no LLM), compare them to the generated
card's structured fields (``cmc`` / ``colors`` / ``type_line``), and on a
mismatch hand the named delta back to card_gen's existing per-card retry loop.

**Conservative by construction.** A false negative (extracting nothing when the
spec is fuzzy) is free — the conformance gate remains the backstop. A false
positive (extracting a target the descriptor didn't really pin) poisons retries,
so every extractor only fires on an unambiguous match and bails to ``None``
otherwise.

It adds **zero** LLM calls for a conforming card — the check is pure
parsing/arithmetic, run only after a card has otherwise passed validation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Color vocabulary
# ---------------------------------------------------------------------------

_COLOR_WORD_TO_LETTER: dict[str, str] = {
    "white": "W",
    "blue": "U",
    "black": "B",
    "red": "R",
    "green": "G",
}
# Letters that legitimately appear as a bare token in a color-set phrasing.
_COLOR_LETTERS = frozenset("WUBRG")

# A color word that, when it appears ALONE in the color field, denotes an
# ambiguous / non-extractable identity — we never pin a concrete color set from
# these (the actual colors are unconstrained or unknown from the word alone).
_AMBIGUOUS_COLOR_WORDS = frozenset({"multicolor", "multicolour", "colorless", "colourless", "gold"})


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpecTargets:
    """The hard, parseable targets extracted from a slot descriptor.

    Each field is ``None`` when the descriptor did not *unambiguously* pin it —
    ``None`` means "no constraint", never "constraint of zero".
    """

    cmc: int | None = None
    colors: frozenset[str] | None = None  # WUBRG letters; frozenset() = colorless
    card_type: str | None = None  # normalized noun, e.g. "creature", "enchantment creature"

    def is_empty(self) -> bool:
        return self.cmc is None and self.colors is None and self.card_type is None


@dataclass(frozen=True)
class SpecMiss:
    """One named mismatch between a generated card and a parsed target."""

    field: str  # "cmc" | "colors" | "card_type"
    want: str
    got: str

    def describe(self) -> str:
        return f"Slot spec wants {self.field} {self.want}, but the card is {self.got}"


# ---------------------------------------------------------------------------
# Descriptor text resolution
# ---------------------------------------------------------------------------


def _descriptor_for_slot(slot: dict) -> str:
    """The text to parse: ``tweaked_text`` if present, else the rendered default.

    Mirrors :func:`prompts.format_slot_specs` — the relabeled ``tweaked_text`` is
    the authoritative spec; a slot the relabel never touched falls back to its
    deterministic ``render_slot_string`` default.
    """
    tweaked = (slot.get("tweaked_text") or "").strip()
    if tweaked:
        return tweaked
    # Local import: skeleton.generator imports nothing from this module, but keep
    # the dependency lazy to avoid any import-order surprises.
    from mtgai.skeleton.generator import render_slot_string

    return render_slot_string(slot)


def _structured_fields(descriptor: str) -> list[str]:
    """Split a ``A · B · C`` descriptor into its middot-delimited fields.

    Returns the stripped fields. A descriptor without the canonical ``·`` shape
    yields a single-element list (the whole string), so callers that want the
    structured color/type positions get nothing usable — which is correct, those
    positions only exist in the canonical shape.
    """
    return [f.strip() for f in descriptor.split("·")]


# ---------------------------------------------------------------------------
# CMC
# ---------------------------------------------------------------------------

# CMC4 / CMC 4 / cmc4 — the canonical descriptor form. Word-boundary anchored so
# it never grabs a digit out of unrelated prose.
_CMC_RE = re.compile(r"\bCMC\s*(\d{1,2})\b", re.IGNORECASE)


def _parse_cmc(descriptor: str) -> int | None:
    """Extract an exact CMC target, or ``None`` if absent / ambiguous.

    Only a single unambiguous ``CMCn`` token counts. A descriptor that names two
    *different* CMCs (e.g. a hand-edited "CMC2 or CMC3") is ambiguous → ``None``.
    A range like "CMC3" repeated identically is fine.
    """
    matches = {int(m.group(1)) for m in _CMC_RE.finditer(descriptor)}
    if len(matches) == 1:
        return next(iter(matches))
    return None


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------

# "Blue/Green", "White-Blue", "Blue/Green/Red" — an explicit color-set phrasing
# joining 2+ color WORDS with / or -. Anchored on word boundaries.
_color_word_alt = "|".join(_COLOR_WORD_TO_LETTER)
_COLOR_PAIR_RE = re.compile(
    rf"\b(?:{_color_word_alt})(?:\s*[/-]\s*(?:{_color_word_alt}))+\b",
    re.IGNORECASE,
)
# An EXPLICIT colour-locked tag the relabel appends — "signpost:WU" /
# "cycle:Name (WUB)". The relabel prompt locks a signpost slot's colour to its
# pair, so these letters ARE the identity. A *bare* trailing "· UR" is NOT
# matched here (it's an ambiguous archetype leftover that can contradict the
# structured mono colour field, e.g. "Blue · … · UR") — only the prefixed forms.
_LETTER_TAG_RE = re.compile(r"\b(?:signpost:|cycle:[^()]*\()([WUBRG]{2,3})\b")


def _letters_from_words(text: str) -> frozenset[str] | None:
    found = {
        _COLOR_WORD_TO_LETTER[m.group(0).lower()]
        for m in re.finditer(_color_word_alt, text, re.IGNORECASE)
    }
    return frozenset(found) if found else None


def _parse_colors(descriptor: str) -> frozenset[str] | None:
    """Extract an exact color-identity target, or ``None`` if absent / ambiguous.

    Recognizes, in order of confidence:

    * An explicit joined phrasing — ``Blue/Green``, ``White-Blue`` — in the
      STRUCTURED head of the descriptor (before any free-text ``(note)``). The
      strongest signal a multicolor identity was pinned. Scoped to the head so a
      passing prose mention ("a red-green themed beast") in the note can't
      override the structured mono color field — a false positive that would
      poison retries.
    * A ``signpost:XY`` / ``cycle:... (XYZ)`` letter tag → its WUBRG letters.
    * The structured color FIELD (the first ``·``-delimited field) when it is a
      single, unambiguous color word.

    Returns ``None`` (no constraint) for any ambiguous color field —
    multicolor / colorless / gold words, or a field that isn't a clean color.
    A mono color word in the structured field IS a constraint (the card must be
    exactly that one color), since the relabel pins color explicitly.
    """
    # The structured head is everything up to the first free-text note; color
    # signals are read only from here so the note's prose can't false-positive.
    head = descriptor.split("(", 1)[0]

    # 1. Explicit joined color phrasing (Blue/Green, White-Blue).
    m = _COLOR_PAIR_RE.search(head)
    if m:
        letters = _letters_from_words(m.group(0))
        if letters and len(letters) >= 2:
            return letters

    # 2. signpost:/cycle: letter tag — explicit two/three-color identity. The
    # ``cycle:`` tag opens its own "(colors)" paren, so scan the full descriptor
    # (the regex itself requires the signpost:/cycle: prefix, so the note's prose
    # can't match).
    tag = _LETTER_TAG_RE.search(descriptor)
    if tag:
        letters = frozenset(tag.group(1).upper())
        if letters <= _COLOR_LETTERS and len(letters) >= 2:
            return letters

    # 3. Structured color field (position 0 of the canonical descriptor).
    # ``render_slot_string`` writes "Mono White" for a single colour; strip that
    # prefix so the bare colour word matches.
    fields = _structured_fields(descriptor)
    if len(fields) >= 2:  # canonical "A · B · ..." shape
        color_field = fields[0].lower().removeprefix("mono ").strip()
        if color_field in _AMBIGUOUS_COLOR_WORDS:
            return None
        if color_field in _COLOR_WORD_TO_LETTER:
            return frozenset({_COLOR_WORD_TO_LETTER[color_field]})
    return None


# ---------------------------------------------------------------------------
# Card type
# ---------------------------------------------------------------------------

# Singular type nouns we recognize, longest compound first so "enchantment
# creature" wins over a bare "creature"/"enchantment".
_COMPOUND_TYPES = ("enchantment creature", "artifact creature")
_SIMPLE_TYPES = (
    "creature",
    "instant",
    "sorcery",
    "enchantment",
    "artifact",
    "planeswalker",
    "land",
)


def _parse_card_type(descriptor: str) -> str | None:
    """Extract a card-type target from the structured TYPE field, or ``None``.

    Reads the type FIELD (the third ``·``-delimited field in the canonical
    ``Color · rarity · type · CMCn · mechanic`` shape) rather than scanning the
    whole descriptor — the free-text note routinely mentions types in passing
    ("draws a card", "an artifact you control") and scanning there would
    false-positive. A subtype parenthetical (``creature (spider)``,
    ``aura (local enchantment)``) is tolerated: we match the leading noun.

    Returns the normalized noun (compound preserved) or ``None`` when the field
    is absent / not a recognized type.
    """
    fields = _structured_fields(descriptor)
    if len(fields) < 3:
        return None
    # The canonical shape puts the type in field index 2.
    type_field = fields[2].lower()
    # Strip a trailing "(subtype)" parenthetical so "creature (spider)" → "creature".
    type_field = re.sub(r"\(.*?\)", "", type_field).strip()
    for compound in _COMPOUND_TYPES:
        if compound in type_field:
            return compound
    for simple in _SIMPLE_TYPES:
        if re.search(rf"\b{simple}\b", type_field):
            return simple
    return None


# ---------------------------------------------------------------------------
# Top-level parse
# ---------------------------------------------------------------------------


def parse_spec_targets(slot: dict) -> SpecTargets:
    """Parse the unambiguous hard targets from a slot's descriptor.

    Pure function over the slot dict — reads ``tweaked_text`` (or the rendered
    default) and never calls an LLM. Any target the descriptor doesn't pin
    unambiguously is left ``None``.
    """
    descriptor = _descriptor_for_slot(slot)
    if not descriptor:
        return SpecTargets()
    return SpecTargets(
        cmc=_parse_cmc(descriptor),
        colors=_parse_colors(descriptor),
        card_type=_parse_card_type(descriptor),
    )


# ---------------------------------------------------------------------------
# Compare a generated card to the targets
# ---------------------------------------------------------------------------


def _card_colors(card) -> frozenset[str]:
    """The card's actual colors as WUBRG letters (handles hybrid via mana_cost)."""
    return frozenset(str(c) for c in (card.colors or []))


def _type_line_has(type_line: str, target_type: str) -> bool:
    """True if ``type_line`` satisfies a parsed ``card_type`` target.

    A type line is the printed form ("Enchantment Creature — God",
    "Legendary Creature — Human Wizard"). A compound target requires BOTH nouns
    present; a simple target requires its noun present as a whole word.
    """
    tl = type_line.lower()
    if " " in target_type:  # compound: every word must appear
        return all(re.search(rf"\b{re.escape(w)}\b", tl) for w in target_type.split())
    return re.search(rf"\b{re.escape(target_type)}\b", tl) is not None


def check_card_against_spec(card, targets: SpecTargets) -> list[SpecMiss]:
    """Return the named mismatches between ``card`` and ``targets`` (empty = OK).

    Only checks targets that are non-``None``. CMC compares the card's integer
    CMC (mana costs in this pipeline are always whole numbers). Colors compares
    the exact set. Type checks the printed ``type_line`` contains the noun(s).
    """
    misses: list[SpecMiss] = []

    if targets.cmc is not None:
        actual_cmc = round(card.cmc)
        if actual_cmc != targets.cmc:
            misses.append(SpecMiss("cmc", str(targets.cmc), f"CMC{actual_cmc}"))

    if targets.colors is not None:
        actual = _card_colors(card)
        if actual != targets.colors:
            misses.append(
                SpecMiss(
                    "colors",
                    _colors_phrase(targets.colors),
                    _colors_phrase(actual),
                )
            )

    if targets.card_type is not None and not _type_line_has(
        card.type_line or "", targets.card_type
    ):
        misses.append(SpecMiss("card_type", targets.card_type, f"'{card.type_line}'"))

    return misses


def _colors_phrase(colors: frozenset[str]) -> str:
    """Human-readable color phrase: "colorless" / "Blue" / "Blue/Green"."""
    if not colors:
        return "colorless"
    _letter_to_word = {v: k.capitalize() for k, v in _COLOR_WORD_TO_LETTER.items()}
    # Order WUBRG for a stable, conventional reading.
    ordered = [_letter_to_word[c] for c in "WUBRG" if c in colors]
    return "/".join(ordered)


# ---------------------------------------------------------------------------
# Infeasibility — arithmetic contradiction repair
# ---------------------------------------------------------------------------


def detect_infeasible(targets: SpecTargets) -> str | None:
    """Detect a CMC-vs-color arithmetic contradiction; return a hybrid hint.

    N *distinct* colors require at least N mana pips with plain colored mana, so
    a spec demanding fewer total mana than colors (e.g. Blue/Green at CMC1) is
    satisfiable ONLY with hybrid pips ({G/U}) — which the local model never
    reaches for on its own. Returns an explicit hybrid suggestion string in that
    case so the retry prompt can route the model to the one legal satisfier,
    else ``None``.
    """
    if targets.cmc is None or not targets.colors:
        return None
    n_colors = len(targets.colors)
    if n_colors >= 2 and targets.cmc < n_colors:
        phrase = _colors_phrase(targets.colors)
        example = "{" + "/".join(sorted(targets.colors)) + "}"
        return (
            f"This slot wants {phrase} at CMC{targets.cmc}, but {n_colors} distinct colors "
            f"need at least CMC{n_colors} with plain colored pips. The ONLY legal way to hit "
            f"both is HYBRID mana — use a hybrid pip like {example} so a single pip counts "
            f"toward both colors and keeps the cost at CMC{targets.cmc}."
        )
    return None


# ---------------------------------------------------------------------------
# Retry-prompt feedback
# ---------------------------------------------------------------------------


def format_spec_feedback(
    card_name: str,
    misses: list[SpecMiss],
    infeasible_hint: str | None = None,
) -> str:
    """Build the LLM-facing retry feedback naming each spec delta.

    Mirrors the shape of ``validation.format_validation_feedback`` so it threads
    cleanly into ``card_generator._retry_card``'s prompt: a header naming the
    card, one bullet per delta, and the hybrid suggestion when the spec is
    arithmetically infeasible without it.
    """
    lines = [
        f"The card '{card_name}' does not match its slot's hard spec. Fix ONLY these "
        f"mismatches while keeping everything else about the card:",
    ]
    for m in misses:
        lines.append(f"- {m.describe()}.")
    if infeasible_hint:
        lines.append("")
        lines.append(infeasible_hint)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------


@dataclass
class SpecCheckCounters:
    """Aggregate spec-check outcomes for the generation summary.

    Surfaced so the effect is measurable next run: how many cards were checked,
    how many retried, how many a retry repaired, and how many specs could not be
    satisfied after the retry budget (accepted best-effort, left for the
    conformance gate).
    """

    specs_checked: int = 0  # cards that pinned at least one hard target
    spec_retries: int = 0  # cards that missed and triggered a retry (per-card, not call count)
    spec_repaired: int = 0  # cards a retry brought into spec
    spec_conflicts: list[dict] = field(default_factory=list)  # unresolved misses, accepted as-is

    def as_summary(self) -> dict:
        return {
            "specs_checked": self.specs_checked,
            "spec_retries": self.spec_retries,
            "spec_repaired": self.spec_repaired,
            "spec_conflicts": list(self.spec_conflicts),
        }
