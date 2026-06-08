"""Skeleton generator — builds the structural slot matrix for an MTG set.

Given a SetConfig and the research-derived set template, this module:
1. Scales rarity counts proportionally to the target set size.
2. Distributes mono-color, multicolor, and colorless slots per rarity.
3. Assigns card types, CMC targets, mechanic tags, and archetype associations.
4. Validates hard and soft structural constraints.
5. Returns a SkeletonResult ready for downstream card generation.
"""

from __future__ import annotations

import logging
import random
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from mtgai.io.atomic import atomic_write_text
from mtgai.skeleton.knobs import (
    ALLIED_PAIRS,
    ENEMY_PAIRS,
    KNOB_SPECS,
    SHARD_TRIOS,
    WEDGE_TRIOS,
    Cycle,
    CycleSpan,
    SkeletonKnobs,
    default_knobs,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_SET_SIZE = 277

COLORS = ["W", "U", "B", "R", "G"]

COLOR_PAIRS = ["WU", "WB", "WR", "WG", "UB", "UR", "UG", "BR", "BG", "RG"]

# The research-derived rarity weights (per ~277-card premier set) now live as the
# ``rarity_*`` defaults on ``SkeletonKnobs`` — the single source of truth that also
# drives clamping + the UI. ``_scale_rarity`` reads them off the knobs.


class MechanicTag(StrEnum):
    """Complexity tier for a skeleton slot."""

    VANILLA = "vanilla"
    FRENCH_VANILLA = "french_vanilla"
    EVERGREEN = "evergreen"
    COMPLEX = "complex"


class SlotCardType(StrEnum):
    """Card types that can appear in a skeleton slot."""

    CREATURE = "creature"
    INSTANT = "instant"
    SORCERY = "sorcery"
    ENCHANTMENT = "enchantment"
    ARTIFACT = "artifact"
    PLANESWALKER = "planeswalker"
    LAND = "land"


class SlotCardSubtype(StrEnum):
    """A fine-grained refinement of a slot's coarse ``card_type``.

    A pure labelling overlay assigned by :func:`_assign_subtypes` after the matrix
    is built: it never changes ``card_type``, color, rarity, or any count, so every
    balance/density invariant still holds. ``None`` means a plain card of the coarse
    type. See ``research/subtype-distribution.md`` for the distribution it models.

    The first four are *recurring* (a few in nearly every set, knob-driven counts);
    the rest are the *irregular bucket* (deciduous specials, 0-2 per set).
    """

    # recurring (standing count knobs)
    EQUIPMENT = "equipment"
    VEHICLE = "vehicle"
    AURA = "aura"
    ARTIFACT_CREATURE = "artifact_creature"
    # irregular / deciduous (the bucket)
    SAGA = "saga"
    CLASS = "class"
    SHRINE = "shrine"
    ENCHANTMENT_CREATURE = "enchantment_creature"
    COLORED_ARTIFACT = "colored_artifact"


# Human-readable label for each subtype, shown in ``render_slot_string`` so the
# relabel LLM + card-gen fallback read the intent directly. Bare values whose
# StrEnum value is already self-explanatory ("equipment", "saga", ...) are omitted.
_SUBTYPE_LABELS: dict[str, str] = {
    SlotCardSubtype.AURA: "aura (local enchantment)",
    SlotCardSubtype.ARTIFACT_CREATURE: "artifact creature",
    SlotCardSubtype.ENCHANTMENT_CREATURE: "enchantment creature",
    SlotCardSubtype.COLORED_ARTIFACT: "colored artifact",
}


def subtype_label(subtype: str) -> str:
    """The display label for a subtype value (falls back to the value itself)."""
    return _SUBTYPE_LABELS.get(subtype, subtype)


class IrregularSubtype(BaseModel):
    """One member of the irregular-subtype bucket (a deciduous special).

    ``parent`` is the coarse ``card_type`` it refines; ``colored`` (when True)
    restricts it to non-colorless slots. ``lo``/``hi`` bound the per-set count when
    the subtype is picked (scaled to set_size, then realized by the seeded RNG).
    """

    subtype: str
    parent: str
    colored: bool = False
    lo: int
    hi: int


# The curated deciduous bucket (research/subtype-distribution.md): subtypes MTG
# reuses across sets but only 0-2 at a time. ``irregular_subtype_count`` says how
# many to include; the seeded RNG picks which. One-set-exclusive types (DSK Rooms,
# MKM Cases) are deliberately absent - a theme that wants them uses card_requests.
# `colored_artifact` is here too: colored non-creature artifacts run ~0-11 in a
# normal set but spike to 30-45 when they're the theme, so the bucket delivers the
# occasional special handful (drawn from the colored non-creature / enchantment
# pool) while the `noncreature_artifact` bias knob stays the lever for a full
# artifact-matters set.
IRREGULAR_SUBTYPES: list[IrregularSubtype] = [
    IrregularSubtype(subtype=SlotCardSubtype.SAGA, parent="enchantment", colored=True, lo=2, hi=5),
    IrregularSubtype(subtype=SlotCardSubtype.CLASS, parent="enchantment", colored=True, lo=2, hi=4),
    IrregularSubtype(
        subtype=SlotCardSubtype.SHRINE, parent="enchantment", colored=True, lo=1, hi=5
    ),
    IrregularSubtype(subtype=SlotCardSubtype.ENCHANTMENT_CREATURE, parent="creature", lo=4, hi=12),
    IrregularSubtype(
        subtype=SlotCardSubtype.COLORED_ARTIFACT, parent="enchantment", colored=True, lo=3, hi=8
    ),
]

# The bucket members' subtype values, in their canonical order — the single source
# of truth for "which strings are a valid irregular-subtype pick". The knob layer
# (``SkeletonKnobs.irregular_subtypes``) and the AI tuner's tool schema both
# validate against this, and ``knobs.py`` can't import it (it's imported *by* this
# module), so membership is enforced here in ``_assign_subtypes``.
IRREGULAR_SUBTYPE_NAMES: list[str] = [str(s.subtype) for s in IRREGULAR_SUBTYPES]


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class SetConfig(BaseModel):
    """User-supplied configuration for a new set.

    Accepts both the new theme.json format (setting, constraints, card_requests)
    and the legacy format (theme, flavor_description, special_constraints).

    Constraints / card_requests / special_constraints accept either bare
    strings or `{text, source}` provenance objects (the wizard persists the
    object form to track AI vs human authorship). Both shapes normalize to
    `list[str]` here — the source field is presentation-only and lives in
    theme.json, not in the downstream skeleton/card-gen path.
    """

    name: str
    code: str  # 3-letter set code
    # New format: single prose blob
    setting: str = ""
    constraints: list[str] = Field(default_factory=list)
    card_requests: list[str] = Field(default_factory=list)
    # Legacy format fields (still accepted for backward compat)
    theme: str = ""
    flavor_description: str = ""
    special_constraints: list[str] = Field(default_factory=list)
    set_size: int = 60  # dev-set default
    mechanic_count: int = 3

    @field_validator("constraints", "card_requests", "special_constraints", mode="before")
    @classmethod
    def _normalize_provenance_items(cls, value: object) -> object:
        if not isinstance(value, list):
            return value  # let Pydantic raise its usual list-required error
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                if item.strip():
                    out.append(item)
            elif isinstance(item, dict) and "text" in item:
                text = item["text"]
                if isinstance(text, str) and text.strip():
                    out.append(text)
        return out


class SkeletonSlot(BaseModel):
    """A single slot in the set skeleton matrix."""

    slot_id: str
    color: str  # "W", "U", "B", "R", "G", "multicolor", "colorless"
    rarity: str  # "common", "uncommon", "rare", "mythic"
    card_type: str  # SlotCardType value
    # Optional fine-grained refinement of ``card_type`` (a ``SlotCardSubtype``
    # value: equipment / vehicle / aura / saga / artifact_creature / ...). Assigned
    # by ``_assign_subtypes`` as a labelling overlay - it never changes the coarse
    # ``card_type``/color/rarity, so reprints, lands, and balance read those
    # unchanged, while ``render_slot_string`` (and thus the relabel + card-gen)
    # surfaces the subtype. ``None`` = a plain card of the coarse type.
    card_subtype: str | None = None
    cmc_target: int
    archetype_tags: list[str] = Field(default_factory=list)
    mechanic_tag: str = MechanicTag.EVERGREEN
    is_reprint_slot: bool = False
    card_id: str | None = None
    notes: str = ""
    color_pair: str | None = None  # for multicolor slots
    # A requested card pinned to this slot ("<name> — <description>"), set by
    # the reserved-slot pass from theme.json card_requests / legendary anchors.
    reserved_card: str | None = None
    # The color pair whose draft archetype this slot is the signpost uncommon
    # for (one multicolor uncommon per pair, set by the default-matrix pass).
    # card-gen reads it to design the gold uncommon that defines the archetype.
    signpost_for: str | None = None
    # The LLM-rewritten one-line descriptor for this slot — the deterministic
    # default (``render_slot_string``) rewritten to fit the set's theme /
    # constraints / requests during Skeleton Generation. ``None`` until the
    # relabel pass runs; card generation reads it as the slot's spec, and the
    # Skeleton tab diffs it against the default. The structured fields above
    # stay the deterministic seed (so reprints/lands read them unchanged).
    tweaked_text: str | None = None
    # The id of the ``Cycle`` this slot is a member of (None for ordinary slots).
    # Card generation pulls cycle members into one batch and threads the cycle's
    # shared template so the family is designed with parallel structure; reprint
    # identification skips them. Land cycles (``card_type == "land"``) are
    # generated by the lands stage, not card-gen.
    cycle_id: str | None = None
    # The cycle's human-readable name (e.g. "Energon Sources"), stamped alongside
    # cycle_id at generation so ``render_slot_string`` can show ``· cycle:<name>``
    # — that puts cycle membership in the descriptor the relabel LLM reads, the
    # same way ``signpost:<pair>`` already is.
    cycle_name: str | None = None
    # This member's colour slot within the cycle — its single colour (``W``),
    # colour-pair (``WG``), or three-colour trio (``WUB``) — so each member is
    # distinguishable in the descriptor (``· cycle:<name> (WG)``).
    cycle_member: str | None = None
    # When this slot was filled by the reprint stage, the chosen reprint's identity
    # ("<name> · <type_line> · <mana_cost>"), stamped alongside ``is_reprint_slot``
    # by ``reprint_selector.apply_selection_to_skeleton``. Card-gen skips reprint
    # slots (it doesn't generate over them) and the lands fixing investigation drops
    # them from its "unfilled slots" view — the reprint is the slot's card now.
    # ``tweaked_text`` is left untouched so a re-roll/clear can cleanly un-stamp.
    reprint_card: str | None = None


# Full color names for the human-readable one-line slot descriptor. WUBRG
# singles plus the two pseudo-colors the matrix uses. The mono colors are
# prefixed "Mono " so the relabel/card-gen LLM can't read a bare "Green" as
# "any card containing green" (e.g. a {U}{G} card is technically green too) and
# slip a multicolor card into a mono slot.
_COLOR_FULL: dict[str, str] = {
    "W": "Mono White",
    "U": "Mono Blue",
    "B": "Mono Black",
    "R": "Mono Red",
    "G": "Mono Green",
    "multicolor": "Multicolor",
    "colorless": "Colorless",
}


def render_slot_string(slot: dict) -> str:
    """Render a skeleton slot to its one-line descriptor.

    ``"White · common · creature · CMC1 · vanilla"`` — the deterministic
    default the Skeleton Generation stage hands to the LLM to rewrite, the
    string card generation falls back to, and the left side of the Skeleton
    tab's diff. Takes a slot dict (the on-disk / loaded shape) so stage runners
    and endpoints can call it without rehydrating a ``SkeletonSlot``.
    """
    # Show the fine-grained subtype label in the type position when present
    # (e.g. "equipment", "aura (local enchantment)", "artifact creature"); else
    # the coarse card_type.
    subtype = slot.get("card_subtype")
    type_str = subtype_label(subtype) if subtype else (slot.get("card_type") or "?")
    parts = [
        _COLOR_FULL.get(slot.get("color", ""), slot.get("color") or "?"),
        slot.get("rarity") or "?",
        type_str,
        f"CMC{slot.get('cmc_target', '?')}",
        slot.get("mechanic_tag") or "",
    ]
    descriptor = " · ".join(p for p in parts if p)
    if slot.get("signpost_for"):
        descriptor += f" · signpost:{slot['signpost_for']}"
    if slot.get("cycle_id"):
        # Show the cycle by name (fall back to the id for a pre-cycle_name skeleton)
        # plus this member's colour slot in the family — its pair (WG), single
        # colour (W), or trio (WUB) — so the relabel LLM sees the family and each
        # member's place in it, mirroring signpost:<pair>.
        label = slot.get("cycle_name") or slot["cycle_id"]
        member = slot.get("cycle_member")
        descriptor += f" · cycle:{label}" + (f" ({member})" if member else "")
    return descriptor


class ReservedSlotSpec(BaseModel):
    """A card the set should contain, mapped onto a skeleton slot.

    Built from ``theme.json`` (``card_requests`` prose + structured
    ``legendary_characters`` / ``notable_cards`` anchors). All constraint
    fields are optional — a name-only spec still gets reserved, taking the
    highest-rarity open slot. ``colors`` uses single-letter codes (``["U", "B"]``).
    """

    name: str
    colors: list[str] = Field(default_factory=list)
    rarity: str | None = None
    card_type: str | None = None  # SlotCardType value
    description: str = ""


class ConstraintResult(BaseModel):
    """Result of a single constraint check."""

    name: str
    passed: bool
    message: str
    is_hard: bool = True


class BalanceReport(BaseModel):
    """Summary of how well the skeleton meets distribution targets."""

    rarity_counts: dict[str, int] = Field(default_factory=dict)
    color_counts: dict[str, int] = Field(default_factory=dict)
    type_counts: dict[str, int] = Field(default_factory=dict)
    cmc_distribution: dict[int, int] = Field(default_factory=dict)
    creature_pct: float = 0.0
    average_cmc: float = 0.0
    multicolor_count: int = 0
    colorless_count: int = 0
    constraints: list[ConstraintResult] = Field(default_factory=list)
    all_hard_passed: bool = True


class SkeletonResult(BaseModel):
    """Complete output of the skeleton generator."""

    config: SetConfig
    slots: list[SkeletonSlot] = Field(default_factory=list)
    archetype_slots: dict[str, list[str]] = Field(default_factory=dict)
    balance_report: BalanceReport = Field(default_factory=BalanceReport)
    total_slots: int = 0
    # Relabel outcome (set by the skeleton stage / refresh after Pass 1). The
    # deterministic generator leaves these at their defaults; ``relabeled_slots``
    # is how many descriptors the LLM rewrote, and ``relabel_incomplete`` is True
    # when the relabel finished below coverage tolerance (partial kept, not
    # discarded). The Skeleton tab reads them to show an "incomplete" warning
    # that survives a page reload (it can't be derived from the slots alone — a
    # slot left on its default is indistinguishable from one the model echoed).
    relabeled_slots: int = 0
    relabel_incomplete: bool = False
    # The theme-tuned structural knobs this skeleton was built from (Phase 0).
    # Defaults reproduce the historical skeleton; ``knobs_defaulted`` is True when
    # the phase-0 tuner failed/was skipped and the build fell back to defaults
    # (surfaced as a tab notice, never a hard error). ``cycles`` mirrors
    # ``knobs.cycles`` at the top level so card-gen / lands can read the per-cycle
    # template by ``cycle_id`` without rehydrating the knobs.
    knobs: SkeletonKnobs = Field(default_factory=default_knobs)
    cycles: list[Cycle] = Field(default_factory=list)
    knobs_defaulted: bool = False
    # Human-readable notes from phase-1 reconciliation (a cycle that didn't fit
    # the rarity budget and was dropped/trimmed). Surfaced as a tab notice.
    knob_warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Rarity scaling
# ---------------------------------------------------------------------------


def _rarity_weights(knobs: SkeletonKnobs) -> dict[str, int]:
    """The four rarity weights (per ~277-card set) from the knobs."""
    return {
        "common": knobs.rarity_common,
        "uncommon": knobs.rarity_uncommon,
        "rare": knobs.rarity_rare,
        "mythic": knobs.rarity_mythic,
    }


def _scale_rarity(set_size: int, knobs: SkeletonKnobs | None = None) -> dict[str, int]:
    """Scale the rarity weights proportionally from the 277-card base.

    Returns a dict like {"common": 21, "uncommon": 21, "rare": 14, "mythic": 4}.
    Adjusts the largest bucket so the total equals *set_size*. With default knobs
    the weights are the historical 95/98/63/20, so this reproduces the old scaling
    exactly.
    """
    knobs = knobs or default_knobs()
    ratio = set_size / BASE_SET_SIZE
    counts = {r: round(c * ratio) for r, c in _rarity_weights(knobs).items()}

    # Clamp mythics to 4-25 regardless of scaling
    counts["mythic"] = max(4, min(25, counts["mythic"]))

    total = sum(counts.values())
    diff = set_size - total
    if diff != 0:
        # Adjust the largest bucket to hit the exact target
        largest = max(counts, key=lambda k: counts[k])
        counts[largest] += diff

    return counts


# ---------------------------------------------------------------------------
# Color distribution
# ---------------------------------------------------------------------------


def _signpost_multi_target(set_size: int, knobs: SkeletonKnobs) -> int:
    """Multicolor-uncommon (signpost) target: ``signposts_per_pair`` x 10 pairs,
    scaled down for small sets with a floor of 5 (the small-set signpost minimum).
    Default ``signposts_per_pair`` == 1 reproduces the historical formula;
    ``signposts_per_pair == 0`` returns 0 (the floor is bypassed — no signposts)."""
    spp = knobs.signposts_per_pair
    if spp <= 0:
        return 0
    return min(10 * spp, max(5, round(10 * spp * set_size / BASE_SET_SIZE)))


def _color_targets(
    rarity: str, count: int, set_size: int, knobs: SkeletonKnobs
) -> tuple[int, int, int]:
    """Return (mono_total, multicolor, colorless) targets for a rarity block.

    Multicolor and colorless are knob-driven fractions of *count* (uncommon
    multicolor is the signpost target, not a fraction); the remainder is mono.
    With default knobs this reproduces the historical split.
    """
    is_small = set_size <= 100
    if rarity == "common":
        multi = 0 if is_small else max(0, round(count * knobs.multicolor_common))
    elif rarity == "uncommon":
        multi = min(_signpost_multi_target(set_size, knobs), count)
    elif rarity == "rare":
        multi = max(0, round(count * knobs.multicolor_rare))
    else:  # mythic
        multi = max(0, round(count * knobs.multicolor_mythic))

    cl_frac = {
        "common": knobs.colorless_common,
        "uncommon": knobs.colorless_uncommon,
        "rare": knobs.colorless_rare,
        "mythic": knobs.colorless_mythic,
    }[rarity]
    colorless = max(0, round(count * cl_frac))

    mono_total = count - multi - colorless
    if mono_total < 0:
        # Squeeze multicolor first, then colorless, so totals never go negative.
        excess = -mono_total
        multi = max(0, multi - excess)
        mono_total = count - multi - colorless
        if mono_total < 0:
            colorless = max(0, colorless + mono_total)
            mono_total = count - multi - colorless
    return mono_total, multi, colorless


def _build_color_slots(
    rarity: str,
    mono_total: int,
    multi: int,
    colorless: int,
    *,
    covered_pairs: list[str] | None = None,
) -> list[dict]:
    """Build the per-slot color dicts for a (mono, multi, colorless) budget.

    Mono slots spread evenly across WUBRG; at common any remainder that would
    break the per-color balance is moved to colorless. Multicolor slots fill the
    least-covered pairs first, where ``covered_pairs`` lists the pairs already
    taken by this rarity's cycle members (an allied-5 / enemy-5 / pairs-10 cycle
    each reserve specific pairs). This keeps *total* per-pair coverage even
    instead of always restarting scalar multis at ``COLOR_PAIRS[0]`` and doubling
    up on the early pairs while leaving cycle-covered pairs with only their lone
    cycle member. Returns dicts: {"color", "color_pair"}.
    """
    slots: list[dict] = []
    per_color = mono_total // 5
    remainder = mono_total - per_color * 5
    if rarity == "common" and remainder > 0:
        colorless += remainder
        remainder = 0

    for i, c in enumerate(COLORS):
        for _ in range(per_color + (1 if i < remainder else 0)):
            slots.append({"color": c, "color_pair": None})

    # Seed each pair's running count with its cycle coverage, then hand each
    # scalar multi to whichever pair is currently least covered (ties broken by
    # COLOR_PAIRS order for determinism). The result: cycle + scalar coverage is
    # as even across the ten pairs as the counts allow.
    coverage = {pair: 0 for pair in COLOR_PAIRS}
    for pair in covered_pairs or []:
        if pair in coverage:
            coverage[pair] += 1
    order = {pair: idx for idx, pair in enumerate(COLOR_PAIRS)}
    for _ in range(multi):
        pair = min(COLOR_PAIRS, key=lambda p: (coverage[p], order[p]))
        coverage[pair] += 1
        slots.append({"color": "multicolor", "color_pair": pair})

    for _ in range(colorless):
        slots.append({"color": "colorless", "color_pair": None})
    return slots


def _distribute_colors(
    rarity: str, count: int, set_size: int, knobs: SkeletonKnobs | None = None
) -> list[dict]:
    """Distribute *count* slots of a given rarity across colors (no cycles).

    Returns a list of dicts: {"color": ..., "color_pair": ...}.
    """
    knobs = knobs or default_knobs()
    mono_total, multi, colorless = _color_targets(rarity, count, set_size, knobs)
    return _build_color_slots(rarity, mono_total, multi, colorless)


# ---------------------------------------------------------------------------
# Card type assignment
# ---------------------------------------------------------------------------

# Hard floor on creature density (see `_check_creature_density`): a low creature
# knob can never push the set below this — the pooled allocator reconciles up to
# it, so the knob bends to the invariant instead of producing an illegal skeleton.
_MIN_CREATURE_DENSITY = 0.50


def _assign_card_types(
    color: str,
    rarity: str,
    block_size: int,
    knobs: SkeletonKnobs | None = None,
) -> list[str]:
    """Return a list of card-type strings for a (color, rarity) block.

    Rules:
    - Creatures fill ``creature_<rarity>`` of the block (knob-driven; the floor
      keeps the per-color/overall creature-density invariant satisfiable).
    - The non-creature remainder is split by the normalized ``noncreature_*``
      bias weights (instant / sorcery / enchantment / artifact). Default weights
      put no artifacts in colored slots, matching the historical generator;
      bumping ``noncreature_artifact`` / ``noncreature_enchantment`` delivers the
      LCI artifact-matters / DSK enchantment-matters skews.
    - Colorless slots are always artifacts.
    """
    if block_size == 0:
        return []

    knobs = knobs or default_knobs()

    if color == "colorless":
        return [SlotCardType.ARTIFACT] * block_size

    creature_frac = {
        "common": knobs.creature_common,
        "uncommon": knobs.creature_uncommon,
        "rare": knobs.creature_rare,
        "mythic": knobs.creature_mythic,
    }.get(rarity, 0.53)
    n_creatures = min(block_size, max(1, round(block_size * creature_frac)))
    remaining = block_size - n_creatures

    weights = knobs.noncreature_weights()
    # Largest-remainder rounding so the four type counts always sum to `remaining`.
    raw = {t: remaining * w for t, w in weights.items()}
    counts = {t: int(v) for t, v in raw.items()}
    leftover = remaining - sum(counts.values())
    for t in sorted(raw, key=lambda k: raw[k] - counts[k], reverse=True)[: max(0, leftover)]:
        counts[t] += 1

    types: list[str] = [SlotCardType.CREATURE] * n_creatures
    types += [SlotCardType.INSTANT] * counts["instant"]
    types += [SlotCardType.SORCERY] * counts["sorcery"]
    types += [SlotCardType.ENCHANTMENT] * counts["enchantment"]
    types += [SlotCardType.ARTIFACT] * counts["artifact"]
    return types[:block_size]


def _assign_card_types_pooled(
    blocks: dict[str, list[dict]],
    rarity: str,
    knobs: SkeletonKnobs | None = None,
) -> dict[str, list[str]]:
    """Assign card types across all of a rarity's color blocks, pooling the
    creature / non-creature split at the **rarity** level instead of rounding it
    independently per (color) block.

    Per-block rounding collapses on small sets: a 1-3 slot colored block forces
    ``>=1`` creature (the ``max(1, …)`` floor, inflating creature density well
    above the knob target) and its lone non-creature remainder always rounds to
    the single highest-weight type, so instants / sorceries / enchantments never
    win a slot and the realized type mix diverges sharply from the knobs (a
    60-card artifact-matters set produced ZERO spells). Pooling the colored slots
    — mirroring how :func:`_assign_mechanic_tags` pools vanilla / french counts
    across the rarity — lets small remainders honour the weight mix and keeps
    creature density on target. On large sets the per-block and pooled results
    converge (big blocks round cleanly).

    Colorless blocks stay forced-artifact (structural) and are excluded from the
    pool. Returns ``{block_key: [type, ...]}`` index-aligned to each block's items.
    """
    knobs = knobs or default_knobs()

    colored = {
        bk: items for bk, items in blocks.items() if items and items[0]["color"] != "colorless"
    }
    result: dict[str, list[str]] = {
        bk: [SlotCardType.ARTIFACT] * len(items)
        for bk, items in blocks.items()
        if bk not in colored
    }

    total = sum(len(items) for items in colored.values())
    if total == 0:
        return result

    creature_frac = {
        "common": knobs.creature_common,
        "uncommon": knobs.creature_uncommon,
        "rare": knobs.creature_rare,
        "mythic": knobs.creature_mythic,
    }.get(rarity, 0.53)
    # The knob bends to the hard density invariant rather than breaking it.
    creature_frac = max(creature_frac, _MIN_CREATURE_DENSITY)
    # creature_frac is the share of the rarity's NON-LAND cards that are creatures,
    # but creatures only ever land in colored slots (colorless slots are forced
    # artifacts). So size the creature count against the full non-land pool
    # (colored + colorless) and place them all in the colored slots — otherwise the
    # all-artifact colorless slots silently drag overall creature density below the
    # 50% hard floor (the old per-block max(1) creature floor masked this by
    # over-stuffing creatures into small blocks).
    nonland_total = total + sum(len(items) for bk, items in blocks.items() if bk not in colored)
    n_creatures = min(total, max(1, round(nonland_total * creature_frac)))
    remaining = total - n_creatures

    weights = knobs.noncreature_weights()
    # Largest-remainder rounding so the four type counts always sum to `remaining`.
    raw = {t: remaining * w for t, w in weights.items()}
    counts = {t: int(v) for t, v in raw.items()}
    leftover = remaining - sum(counts.values())
    for t in sorted(raw, key=lambda k: raw[k] - counts[k], reverse=True)[: max(0, leftover)]:
        counts[t] += 1

    pooled: list[str] = [SlotCardType.CREATURE] * n_creatures
    pooled += [SlotCardType.INSTANT] * counts["instant"]
    pooled += [SlotCardType.SORCERY] * counts["sorcery"]
    pooled += [SlotCardType.ENCHANTMENT] * counts["enchantment"]
    pooled += [SlotCardType.ARTIFACT] * counts["artifact"]

    # Deal the pooled multiset across colored blocks position-major (round-robin
    # by slot index across blocks) so creatures and each spell type spread evenly
    # across colors instead of clumping in one block — same interleave order
    # _assign_mechanic_tags uses for its pooled tags.
    max_len = max(len(items) for items in colored.values())
    coords = [
        (bk, pos) for pos in range(max_len) for bk, items in colored.items() if pos < len(items)
    ]
    assigned: dict[tuple[str, int], str] = {}
    for coord, card_type in zip(coords, pooled, strict=False):
        assigned[coord] = card_type
    for bk, items in colored.items():
        result[bk] = [assigned[(bk, i)] for i in range(len(items))]
    return result


# ---------------------------------------------------------------------------
# CMC assignment
# ---------------------------------------------------------------------------

# Target CMC distribution percentages (from template overall mana curve)
_CMC_DISTRIBUTION: list[tuple[int, float]] = [
    (1, 12.3),
    (2, 29.9),
    (3, 23.8),
    (4, 15.6),
    (5, 10.4),
    (6, 4.4),
    (7, 3.6),
]


def _assign_cmcs(block_size: int, rarity: str) -> list[int]:
    """Assign CMC targets to a block of *block_size* slots.

    Follows the overall mana curve distribution, with mythics skewing higher.
    """
    if block_size == 0:
        return []

    # For mythics, shift the curve upward
    if rarity == "mythic":
        dist = [
            (1, 5.0),
            (2, 15.0),
            (3, 20.0),
            (4, 20.0),
            (5, 18.0),
            (6, 12.0),
            (7, 10.0),
        ]
    else:
        dist = list(_CMC_DISTRIBUTION)

    # Compute bucket sizes
    total_pct = sum(p for _, p in dist)
    buckets: list[tuple[int, int]] = []
    assigned = 0
    for cmc, pct in dist:
        n = round(block_size * pct / total_pct)
        buckets.append((cmc, n))
        assigned += n

    # Fix rounding: adjust the largest bucket
    diff = block_size - assigned
    if diff != 0:
        idx = max(range(len(buckets)), key=lambda i: buckets[i][1])
        cmc_val, cnt = buckets[idx]
        buckets[idx] = (cmc_val, max(0, cnt + diff))

    cmcs: list[int] = []
    for cmc_val, cnt in buckets:
        cmcs.extend([cmc_val] * cnt)

    # Pad or trim if needed (safety)
    while len(cmcs) < block_size:
        cmcs.append(3)
    return cmcs[:block_size]


# ---------------------------------------------------------------------------
# Mechanic tagging
# ---------------------------------------------------------------------------


# Complexity-tier rates, per rarity. ``vanilla`` / ``french`` are fractions of the
# rarity's *creature* slots (a spell or noncreature artifact is never "vanilla");
# ``complex`` is the fraction of the *remaining* slots (non-vanilla/french creatures
# + every non-creature) that get COMPLEX, the rest EVERGREEN. The vanilla / French-
# vanilla rates are tuned to observed recent-set (2023-2025) densities — true vanilla
# ~1% of creatures, French vanilla ~2-3% — rather than the historical ~15%/25% commons
# (WotC made vanilla deciduous in 2021; recent premier sets average ~1 true vanilla and
# ~3 French vanilla creatures). See research notes / git history for the source data.
_TIER_RATES: dict[str, dict[str, float]] = {
    "common": {"vanilla": 0.04, "french": 0.06, "complex": 0.20},
    "uncommon": {"vanilla": 0.0, "french": 0.03, "complex": 0.40},
    "rare": {"vanilla": 0.0, "french": 0.0, "complex": 0.85},
    "mythic": {"vanilla": 0.0, "french": 0.0, "complex": 0.85},
}


def _assign_mechanic_tags(block_types: dict[str, list[str]], rarity: str) -> dict[str, list[str]]:
    """Assign complexity-tier tags across all of a rarity's color blocks.

    Returns ``{block_key: [tag, ...]}`` index-aligned to the matching ``block_types``
    entry, so every slot's tier matches its card type.

    VANILLA and FRENCH_VANILLA are **creature-only** tiers and their counts are
    **pooled across the whole rarity** rather than rounded per block: with only ~1
    vanilla wanted set-wide, a per-block ``round`` would force either zero or one per
    color (the old ``max(1, …)`` floor even stamped "vanilla" onto colorless artifact
    blocks). Pooling makes small, realistic totals achievable and spreads the few
    special tags across colors. Remaining creatures + every non-creature slot split
    EVERGREEN / COMPLEX by the rarity's ``complex`` fraction. Rates: ``_TIER_RATES``.
    """
    rates = _TIER_RATES.get(rarity, _TIER_RATES["rare"])
    assigned: dict[tuple[str, int], str] = {}

    # Interleave slot coordinates round-robin by position across blocks so the few
    # vanilla/french/complex tags spread across colors instead of clumping in one.
    max_len = max((len(t) for t in block_types.values()), default=0)
    interleaved: list[tuple[str, int]] = [
        (bk, pos) for pos in range(max_len) for bk, t in block_types.items() if pos < len(t)
    ]
    creature_coords = [c for c in interleaved if block_types[c[0]][c[1]] == SlotCardType.CREATURE]

    n_creatures = len(creature_coords)
    n_vanilla = min(round(n_creatures * rates["vanilla"]), n_creatures)
    n_french = min(round(n_creatures * rates["french"]), n_creatures - n_vanilla)
    specials = [MechanicTag.VANILLA] * n_vanilla + [MechanicTag.FRENCH_VANILLA] * n_french
    for coord, tag in zip(creature_coords, specials, strict=False):
        assigned[coord] = tag

    # Everything still unassigned (remaining creatures + all non-creatures) splits
    # EVERGREEN / COMPLEX by the complex fraction, in the same interleaved order.
    rest = [c for c in interleaved if c not in assigned]
    n_complex = round(len(rest) * rates["complex"])
    for idx, coord in enumerate(rest):
        assigned[coord] = MechanicTag.COMPLEX if idx < n_complex else MechanicTag.EVERGREEN

    return {bk: [assigned[(bk, i)] for i in range(len(t))] for bk, t in block_types.items()}


# ---------------------------------------------------------------------------
# Archetype tagging
# ---------------------------------------------------------------------------


def _archetype_tags_for_color(color: str, color_pair: str | None) -> list[str]:
    """Return the draft-archetype pair codes relevant to a slot.

    Mono-color slots map to the 4 pairs that include that color.
    Multicolor slots map to their specific pair.
    Colorless slots have no archetype affinity.
    """
    if color == "multicolor" and color_pair:
        return [color_pair]
    if color == "colorless":
        return []
    # Mono-color: find all pairs containing this color
    return [p for p in COLOR_PAIRS if color in p]


# ---------------------------------------------------------------------------
# Slot ID generation
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Constraint validation
# ---------------------------------------------------------------------------


def _check_color_balance(slots: list[SkeletonSlot]) -> list[ConstraintResult]:
    """Hard: each color has the same commons (±0), and same at other rarities (±1)."""
    results: list[ConstraintResult] = []

    for rarity in ["common", "uncommon", "rare", "mythic"]:
        r_slots = [s for s in slots if s.rarity == rarity]
        color_counts = {c: 0 for c in COLORS}
        for s in r_slots:
            if s.color in COLORS:
                color_counts[s.color] += 1

        vals = list(color_counts.values())
        if not vals:
            continue

        spread = max(vals) - min(vals)
        tolerance = 0 if rarity == "common" else 1
        passed = spread <= tolerance
        detail = ", ".join(f"{c}={color_counts[c]}" for c in COLORS)
        results.append(
            ConstraintResult(
                name=f"color_balance_{rarity}",
                passed=passed,
                message=(
                    f"{rarity} color balance: {detail} (spread={spread}, tolerance=±{tolerance})"
                ),
                is_hard=True,
            )
        )

    return results


def _check_creature_density(slots: list[SkeletonSlot]) -> list[ConstraintResult]:
    """Hard: overall creature density >= 50%, each color >= 40% creatures at common."""
    results: list[ConstraintResult] = []
    non_land = [s for s in slots if s.card_type != SlotCardType.LAND]

    min_pct = _MIN_CREATURE_DENSITY * 100
    if non_land:
        creature_count = sum(1 for s in non_land if s.card_type == SlotCardType.CREATURE)
        pct = creature_count / len(non_land) * 100
        results.append(
            ConstraintResult(
                name="overall_creature_density",
                passed=pct >= min_pct,
                message=f"Overall creature density: {pct:.1f}% (min {min_pct:.0f}%)",
                is_hard=True,
            )
        )

    # Per-color at common
    for c in COLORS:
        c_slots = [
            s
            for s in slots
            if s.color == c and s.rarity == "common" and s.card_type != SlotCardType.LAND
        ]
        if not c_slots:
            continue
        creatures = sum(1 for s in c_slots if s.card_type == SlotCardType.CREATURE)
        pct = creatures / len(c_slots) * 100
        results.append(
            ConstraintResult(
                name=f"creature_density_{c}_common",
                passed=pct >= 40.0,
                message=f"{c} common creature density: {pct:.1f}% (min 40%)",
                is_hard=True,
            )
        )

    return results


def _check_signpost_uncommons(
    slots: list[SkeletonSlot],
    set_size: int,
    signposts_per_pair: int = 1,
) -> ConstraintResult:
    """Hard: enough multicolor uncommons to serve as signposts.

    The bar is one per pair (10 at full size, 5 floor for small sets); a higher
    ``signposts_per_pair`` raises the requested count but the hard floor stays
    one-per-pair so the build never fails just for asking for extra signposts.
    ``signposts_per_pair == 0`` opts the set out of gold signposts entirely, so
    the floor is lifted (no multicolor-uncommon requirement).
    """
    multi_unc = [s for s in slots if s.rarity == "uncommon" and s.color == "multicolor"]
    if signposts_per_pair <= 0:
        return ConstraintResult(
            name="signpost_uncommons",
            passed=True,
            message=f"Multicolor uncommons: {len(multi_unc)} (signposts disabled)",
            is_hard=True,
        )
    required = 5 if set_size <= 100 else 10
    # The hard floor stays one-per-pair; signposts_per_pair only raises the
    # *requested* count (shown for context), and only for full-size sets.
    requested = 10 * signposts_per_pair if set_size > 100 else required
    note = f", requested {requested}" if requested != required else ""
    return ConstraintResult(
        name="signpost_uncommons",
        passed=len(multi_unc) >= required,
        message=(f"Multicolor uncommons: {len(multi_unc)} (need >= {required}{note})"),
        is_hard=True,
    )


def _check_rarity_totals(
    slots: list[SkeletonSlot],
    set_size: int,
) -> ConstraintResult:
    """Hard: total non-basic-land slots equals set_size."""
    return ConstraintResult(
        name="rarity_total",
        passed=len(slots) == set_size,
        message=f"Total slots: {len(slots)} (expected {set_size})",
        is_hard=True,
    )


def _check_avg_cmc(slots: list[SkeletonSlot]) -> ConstraintResult:
    """Soft: average CMC between 2.9 and 3.5."""
    non_land = [s for s in slots if s.card_type != SlotCardType.LAND]
    if not non_land:
        return ConstraintResult(
            name="avg_cmc",
            passed=True,
            message="No non-land slots",
            is_hard=False,
        )
    avg = sum(s.cmc_target for s in non_land) / len(non_land)
    return ConstraintResult(
        name="avg_cmc",
        passed=2.9 <= avg <= 3.5,
        message=f"Average CMC: {avg:.2f} (target 2.9-3.5)",
        is_hard=False,
    )


def _check_cmc_coverage(slots: list[SkeletonSlot], set_size: int) -> ConstraintResult:
    """Soft: at least 1 creature per color at CMC 1-5 at common (relaxed for small)."""
    if set_size <= 100:
        return ConstraintResult(
            name="cmc_coverage",
            passed=True,
            message="CMC coverage check relaxed for small set",
            is_hard=False,
        )
    missing: list[str] = []
    for c in COLORS:
        for cmc in range(1, 6):
            found = any(
                s
                for s in slots
                if s.color == c
                and s.rarity == "common"
                and s.card_type == SlotCardType.CREATURE
                and s.cmc_target == cmc
            )
            if not found:
                missing.append(f"{c}@CMC{cmc}")
    passed = len(missing) == 0
    msg = "All colors covered at CMC 1-5" if passed else f"Missing: {', '.join(missing)}"
    return ConstraintResult(name="cmc_coverage", passed=passed, message=msg, is_hard=False)


def _validate_skeleton(
    slots: list[SkeletonSlot],
    set_size: int,
    signposts_per_pair: int = 1,
) -> list[ConstraintResult]:
    """Run all hard and soft constraint checks."""
    results: list[ConstraintResult] = []
    results.extend(_check_color_balance(slots))
    results.extend(_check_creature_density(slots))
    results.append(_check_signpost_uncommons(slots, set_size, signposts_per_pair))
    results.append(_check_rarity_totals(slots, set_size))
    results.append(_check_avg_cmc(slots))
    results.append(_check_cmc_coverage(slots, set_size))
    return results


# ---------------------------------------------------------------------------
# Balance report
# ---------------------------------------------------------------------------


def _build_balance_report(
    slots: list[SkeletonSlot],
    set_size: int,
    signposts_per_pair: int = 1,
) -> BalanceReport:
    """Compile statistics and constraint results into a report."""
    rarity_counts: dict[str, int] = {}
    color_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    cmc_dist: dict[int, int] = {}
    creature_count = 0
    non_land_count = 0
    cmc_sum = 0.0

    for s in slots:
        rarity_counts[s.rarity] = rarity_counts.get(s.rarity, 0) + 1
        color_counts[s.color] = color_counts.get(s.color, 0) + 1
        type_counts[s.card_type] = type_counts.get(s.card_type, 0) + 1

        if s.card_type != SlotCardType.LAND:
            non_land_count += 1
            cmc_sum += s.cmc_target
            cmc_dist[s.cmc_target] = cmc_dist.get(s.cmc_target, 0) + 1
            if s.card_type == SlotCardType.CREATURE:
                creature_count += 1

    constraints = _validate_skeleton(slots, set_size, signposts_per_pair)
    all_hard = all(c.passed for c in constraints if c.is_hard)

    return BalanceReport(
        rarity_counts=rarity_counts,
        color_counts=color_counts,
        type_counts=type_counts,
        cmc_distribution=dict(sorted(cmc_dist.items())),
        creature_pct=(creature_count / non_land_count * 100) if non_land_count else 0.0,
        average_cmc=(cmc_sum / non_land_count) if non_land_count else 0.0,
        multicolor_count=color_counts.get("multicolor", 0),
        colorless_count=color_counts.get("colorless", 0),
        constraints=constraints,
        all_hard_passed=all_hard,
    )


# ---------------------------------------------------------------------------
# Reserved slots — pin requested cards from theme.json onto the matrix
# ---------------------------------------------------------------------------

_RARITY_RANK: dict[str, int] = {"common": 0, "uncommon": 1, "rare": 2, "mythic": 3}

# Types the skeleton matrix never auto-generates (lands come from the `lands`
# stage; planeswalkers are placed explicitly). A request of one of these types
# must match such a slot exactly or it can't be reserved here — stamping it on
# a creature slot would emit a self-contradictory card-gen prompt.
_HARD_MATCH_TYPES: set[str] = {SlotCardType.LAND, SlotCardType.PLANESWALKER}

# Scanned in order: the first keyword found in a type line wins, so
# "Artifact Creature" maps to creature and "Legendary Artifact — Vehicle"
# to artifact.
_TYPE_LINE_KEYWORDS: list[tuple[str, str]] = [
    ("planeswalker", SlotCardType.PLANESWALKER),
    ("creature", SlotCardType.CREATURE),
    ("instant", SlotCardType.INSTANT),
    ("sorcery", SlotCardType.SORCERY),
    ("artifact", SlotCardType.ARTIFACT),
    ("enchantment", SlotCardType.ENCHANTMENT),
    ("land", SlotCardType.LAND),
]


def _card_type_from_type_line(type_line: str | None) -> str | None:
    """Derive a SlotCardType from a full type line (e.g. 'Legendary Creature — X')."""
    tl = (type_line or "").lower()
    for keyword, card_type in _TYPE_LINE_KEYWORDS:
        if keyword in tl:
            return card_type
    return None


def _normalize_rarity(value: object) -> str | None:
    rarity = value.strip().lower() if isinstance(value, str) else ""
    return rarity if rarity in _RARITY_RANK else None


def _normalize_pair(colors: list[str]) -> str:
    """Map two color codes to their canonical COLOR_PAIRS ordering."""
    wanted = set(colors)
    for pair in COLOR_PAIRS:
        if set(pair) == wanted:
            return pair
    return "".join(colors)


def _spec_color_target(colors: list[str]) -> tuple[str, str | None] | None:
    """Map a spec's color codes to a (slot_color, color_pair) match target.

    One color → that mono color; two → a multicolor pair. Zero or 3+ colors
    carry no usable color constraint (returns None) — colorlessness is matched
    via card_type instead.
    """
    codes = [c for c in colors if c in COLORS]
    if len(codes) == 1:
        return (codes[0], None)
    if len(codes) == 2:
        return ("multicolor", _normalize_pair(codes))
    return None


def _is_constrained(spec: ReservedSlotSpec) -> bool:
    return bool(spec.rarity or spec.card_type or _spec_color_target(spec.colors))


def _reservation_score(
    slot: SkeletonSlot,
    spec: ReservedSlotSpec,
    target: tuple[str, str | None] | None,
) -> int:
    """How well a slot satisfies a spec's constraints (higher = better)."""
    score = 0
    if target is not None:
        tcolor, tpair = target
        if slot.color == tcolor and (tpair is None or slot.color_pair == tpair):
            score += 4
    if spec.rarity and slot.rarity == spec.rarity:
        score += 2
    if spec.card_type and slot.card_type == spec.card_type:
        score += 1
    return score


def _format_reserved(spec: ReservedSlotSpec) -> str:
    return f"{spec.name} — {spec.description}" if spec.description else spec.name


def _apply_reservations(
    slots: list[SkeletonSlot],
    reserved: list[ReservedSlotSpec],
) -> list[ReservedSlotSpec]:
    """Claim one slot per reserved spec, in place, best-effort.

    Each spec takes the best-scoring unclaimed, non-reprint, non-land slot
    (ties broken toward higher rarity, then slot_id); a name-only spec scores
    zero everywhere and so takes the highest-rarity open slot. Constrained
    specs are placed first so they win their ideal slots. Reservation only
    stamps ``reserved_card`` — it never changes a slot's color/rarity/type/cmc,
    so balance constraints are unaffected. Returns the specs that found no slot
    — once the matrix is exhausted, or a land/planeswalker request with no
    matching slot (these belong to the lands / explicit-placement stages).
    """
    if not reserved:
        return []

    claimed: set[str] = set()
    unplaced: list[ReservedSlotSpec] = []
    ordered = sorted(reserved, key=lambda s: 0 if _is_constrained(s) else 1)

    for spec in ordered:
        target = _spec_color_target(spec.colors)
        candidates = [
            s
            for s in slots
            if s.slot_id not in claimed
            and not s.is_reprint_slot
            and s.card_type != SlotCardType.LAND
        ]
        if spec.card_type in _HARD_MATCH_TYPES:
            candidates = [s for s in candidates if s.card_type == spec.card_type]
        if not candidates:
            unplaced.append(spec)
            continue
        best = sorted(
            candidates,
            key=lambda s: (
                -_reservation_score(s, spec, target),
                -_RARITY_RANK.get(s.rarity, 0),
                s.slot_id,
            ),
        )[0]
        best.reserved_card = _format_reserved(spec)
        claimed.add(best.slot_id)

    return unplaced


def _normalize_request_items(value: object) -> list[str]:
    """Coerce a card_requests list (bare strings or {text, source}) to strings."""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                out.append(text.strip())
    return out


def _split_request(text: str) -> tuple[str, str]:
    """Split a prose request 'Name — description' into (name, description)."""
    text = text.strip()
    for sep in (" — ", " - ", ": "):
        if sep in text:
            name, desc = text.split(sep, 1)
            return name.strip(), desc.strip()
    return text, ""


def build_reserved_slots(theme: dict) -> list[ReservedSlotSpec]:
    """Build reserved-slot specs from a raw ``theme.json`` dict.

    NOTE: not currently used by the pipeline — Skeleton Generation places
    ``card_requests`` via the LLM relabel pass (``skeleton_relabel`` Pass 2),
    not this deterministic pre-placement. Kept (with ``generate_skeleton``'s
    ``reserved_slots`` parameter + ``_apply_reservations``) for potential reuse
    and still covered by tests.

    Sources, in priority order (first occurrence of a name wins):
      * ``legendary_characters`` / ``notable_cards`` — structured anchors with
        colors, rarity, and a type line → fully-constrained specs.
      * ``card_requests`` — prose ('Name — description') → name-only specs.

    Tolerant of missing keys and either provenance shape; deduped by name.
    """
    specs: list[ReservedSlotSpec] = []
    seen: set[str] = set()

    def _add(
        name: object,
        colors: object,
        rarity: str | None,
        card_type: str | None,
        description: object,
    ) -> None:
        clean_name = name.strip() if isinstance(name, str) else ""
        if not clean_name or clean_name.casefold() in seen:
            return
        seen.add(clean_name.casefold())
        specs.append(
            ReservedSlotSpec(
                name=clean_name,
                colors=[c for c in colors if isinstance(c, str)]
                if isinstance(colors, list)
                else [],
                rarity=rarity,
                card_type=card_type,
                description=description.strip() if isinstance(description, str) else "",
            )
        )

    for entry in theme.get("legendary_characters") or []:
        if isinstance(entry, dict):
            _add(
                entry.get("name"),
                entry.get("colors"),
                _normalize_rarity(entry.get("rarity")),
                _card_type_from_type_line(entry.get("type")),
                entry.get("role"),
            )
    for entry in theme.get("notable_cards") or []:
        if isinstance(entry, dict):
            _add(
                entry.get("name"),
                entry.get("colors"),
                _normalize_rarity(entry.get("rarity")),
                _card_type_from_type_line(entry.get("type")),
                entry.get("notes"),
            )
    for text in _normalize_request_items(theme.get("card_requests")):
        name, desc = _split_request(text)
        _add(name, [], None, None, desc)

    return specs


def _mark_signpost_slots(slots: list[SkeletonSlot], signposts_per_pair: int = 1) -> int:
    """Flag ``signposts_per_pair`` multicolor-uncommon slots per color pair.

    The signpost uncommon is the gold card that defines a draft archetype. For
    each pair in WUBRG order we stamp ``signpost_for`` on up to
    ``signposts_per_pair`` multicolor-uncommon slots carrying that pair (1 by
    default — BLB's Mentor cycle; 2 for DSK/OTJ/MKM-style double signposts; **0
    flags none** — a set with no gold signpost archetypes). This is naturally
    capped at the multicolor-uncommon slots that exist (the same slots
    :func:`_check_signpost_uncommons` counts), so small sets simply leave the
    uncovered pairs without a signpost.

    ``card-gen`` reads the flag (via the archetype lookup) to design the gold
    uncommon that defines that pair's archetype. This is the deterministic
    default matrix; a later LLM skeleton-revision pass may reassign it. Returns
    the number of slots flagged. **Cycle members are skipped** — a cycle is a
    coherent family designed from its own template, so stamping the free-form
    "design the archetype signpost" brief on top would be a competing
    instruction; the cycle's pair archetype context still reaches card-gen via
    the multicolor slot's ``color_pair``.
    """
    per_pair = max(0, signposts_per_pair)
    marked = 0
    for pair in COLOR_PAIRS:
        taken = 0
        for slot in slots:
            if taken >= per_pair:
                break
            if (
                slot.rarity == "uncommon"
                and slot.color == "multicolor"
                and slot.color_pair == pair
                and slot.signpost_for is None
                and not slot.cycle_id
            ):
                slot.signpost_for = pair
                marked += 1
                taken += 1
    return marked


# ---------------------------------------------------------------------------
# Cycles — structural reservations carved before the scalar distribution
# ---------------------------------------------------------------------------


def _cycle_member_colors(span: str) -> list[tuple[str, str | None]]:
    """Return the (color, color_pair) of each member for a cycle span.

    The 5-/10-member spans spread evenly across colors / pairs (balance-preserving
    by construction); three-color spans are ``multicolor`` with no single pair
    (their trio is carried separately by :func:`_expand_cycle`).
    """
    if span == CycleSpan.MONO5:
        return [(c, None) for c in COLORS]
    if span == CycleSpan.PAIRS10:
        return [("multicolor", p) for p in COLOR_PAIRS]
    if span == CycleSpan.ALLIED5:
        return [("multicolor", p) for p in ALLIED_PAIRS]
    if span == CycleSpan.ENEMY5:
        return [("multicolor", p) for p in ENEMY_PAIRS]
    if span in (CycleSpan.SHARDS5, CycleSpan.WEDGES5):
        trios = SHARD_TRIOS if span == CycleSpan.SHARDS5 else WEDGE_TRIOS
        return [("multicolor", None) for _ in trios]
    return []  # unreachable for a valid CycleSpan (every span is handled above)


def _expand_cycle(cycle: Cycle) -> list[dict]:
    """Expand a cycle into member slot dicts (color/pair/type/cmc + cycle_id)."""
    trios: list[str] | None = None
    if cycle.span == CycleSpan.SHARDS5:
        trios = SHARD_TRIOS
    elif cycle.span == CycleSpan.WEDGES5:
        trios = WEDGE_TRIOS
    members: list[dict] = []
    for i, (color, pair) in enumerate(_cycle_member_colors(cycle.span)):
        # This member's colour slot: the trio for shard/wedge spans, else the pair
        # (multicolor spans) or the single colour (mono5).
        member_code = trios[i] if trios else (pair or color)
        note = f"{member_code} member of the {cycle.name} cycle" if trios else ""
        members.append(
            {
                "color": color,
                "color_pair": pair,
                "rarity": cycle.rarity,
                "card_type": cycle.card_type,
                "cmc_target": cycle.cmc_target,
                "cycle_id": cycle.id,
                "cycle_name": cycle.name,
                "cycle_member": member_code,
                "notes": note,
                "archetype_tags": _archetype_tags_for_color(color, pair),
                "mechanic_tag": MechanicTag.EVERGREEN
                if cycle.rarity == "common"
                else MechanicTag.COMPLEX,
            }
        )
    return members


def _reserve_cycles(
    cycles: list[Cycle],
    rarity_counts: dict[str, int],
) -> tuple[dict[str, list[dict]], list[Cycle], list[str]]:
    """Carve cycle members out of the rarity budget, dropping ones that don't fit.

    Returns (members_by_rarity, kept_cycles, warnings). A cycle is dropped (with a
    warning) when its members would take more than half its rarity's budget — the
    feasibility reconciliation that keeps the scalar half of the distribution
    (and the creature/balance invariants it carries) viable. Even spans are
    balance-preserving, so a kept cycle never disturbs color balance.
    """
    members_by_rarity: dict[str, list[dict]] = {r: [] for r in rarity_counts}
    kept: list[Cycle] = []
    warnings: list[str] = []
    for cycle in cycles:
        members = _expand_cycle(cycle)
        rarity = cycle.rarity
        budget = rarity_counts.get(rarity, 0)
        used = len(members_by_rarity.get(rarity, []))
        cap = budget // 2  # leave at least half the rarity for the scalar layer
        if budget == 0 or not members or used + len(members) > cap:
            warnings.append(
                f"Cycle '{cycle.name}' ({cycle.span}, {rarity}) dropped — "
                f"{len(members)} members don't fit the {rarity} budget ({budget})."
            )
            continue
        members_by_rarity[rarity].extend(members)
        kept.append(cycle)
    return members_by_rarity, kept, warnings


def _place_planeswalkers(slots: list[SkeletonSlot], count: int) -> int:
    """Retype up to *count* mythic slots to planeswalker, returning how many.

    Prefers non-creature, non-cycle mythic slots so creature density is
    preserved; never touches a cycle member or a reprint slot.
    """
    if count <= 0:
        return 0
    mythics = [
        s for s in slots if s.rarity == "mythic" and not s.cycle_id and not s.is_reprint_slot
    ]
    candidates = [s for s in mythics if s.card_type != SlotCardType.CREATURE] or mythics
    placed = 0
    for slot in candidates[:count]:
        slot.card_type = SlotCardType.PLANESWALKER
        placed += 1
    return placed


# ---------------------------------------------------------------------------
# Card subtype assignment (a labelling overlay; see research/subtype-distribution.md)
# ---------------------------------------------------------------------------


def _assign_subtypes(
    slots: list[SkeletonSlot],
    knobs: SkeletonKnobs,
    set_size: int,
    set_code: str,
) -> None:
    """Label a subset of slots with a fine-grained ``card_subtype`` in place.

    Recurring subtypes (equipment / vehicle / aura / artifact creature) get a
    knob-driven count, scaled to ``set_size`` and jittered by ``subtype_jitter``;
    then ``irregular_subtype_count`` deciduous specials (saga / class / shrine /
    enchantment creature) are taken from :data:`IRREGULAR_SUBTYPES`, each filling a
    scaled count drawn from its own ``lo``/``hi`` range (its spread comes from that
    range, not ``subtype_jitter``). WHICH specials are taken is theme-driven when
    ``knobs.irregular_subtypes`` lists them (the AI tuner's picks, in order); the
    seeded RNG only shuffles in the rest, so a set with no theme signal falls back
    to pure chance. Everything is realized by an RNG seeded on
    ``set_code`` + ``subtype_seed`` so the same project is stable across re-runs
    (the seed is the raw string, not ``hash()``) and bumping the seed re-rolls.

    Only ordinary slots are eligible: special slots (cycle members, reserved cards,
    signposts) are skipped, and planeswalkers/lands never match a subtype's parent
    type, so structural families stay clean. The labelling only writes
    ``card_subtype`` -- it never changes ``card_type``/color/rarity/counts, so every
    balance invariant still holds.
    """
    rng = random.Random(f"{set_code}|{knobs.subtype_seed}")
    scale = set_size / BASE_SET_SIZE
    jitter = knobs.subtype_jitter

    def _realized(count: int) -> int:
        if count <= 0:
            return 0
        center = count * scale
        return max(0, round(center * (1 + rng.uniform(-jitter, jitter))))

    def _eligible(parent: str, *, colored: bool = False, colorless: bool = False) -> list:
        out = []
        for s in slots:
            if s.card_subtype:  # already labelled by an earlier subtype
                continue
            if s.cycle_id or s.reserved_card or s.signpost_for:
                continue
            if s.card_type != parent:
                continue
            is_cl = s.color == "colorless"
            if colorless and not is_cl:
                continue
            if colored and is_cl:
                continue
            out.append(s)
        return out

    def _label(parent: str, subtype: str, n: int, *, colored=False, colorless=False) -> None:
        if n <= 0:
            return
        pool = _eligible(parent, colored=colored, colorless=colorless)
        rng.shuffle(pool)
        for s in pool[:n]:
            s.card_subtype = subtype

    # Recurring subtypes first, so they claim their slots before the specials.
    _label("artifact", SlotCardSubtype.EQUIPMENT, _realized(knobs.equipment_count), colorless=True)
    _label("artifact", SlotCardSubtype.VEHICLE, _realized(knobs.vehicle_count), colorless=True)
    _label("enchantment", SlotCardSubtype.AURA, _realized(knobs.aura_count), colored=True)
    _label("creature", SlotCardSubtype.ARTIFACT_CREATURE, _realized(knobs.artifact_creature_count))

    # Irregular bucket: weave in `irregular_subtype_count` deciduous specials.
    # WHICH ones is theme-driven when the tuner set `knobs.irregular_subtypes`
    # (validated bucket members, in preference order); the seeded RNG only fills
    # any remaining slots, so a set with no theme signal stays pure chance.
    by_subtype = {str(spec.subtype): spec for spec in IRREGULAR_SUBTYPES}
    ordered: list[IrregularSubtype] = []
    seen: set[str] = set()
    for name in knobs.irregular_subtypes:  # theme picks first, in order, deduped
        spec = by_subtype.get(name)
        if spec is not None and name not in seen:
            ordered.append(spec)
            seen.add(name)
    remaining = [s for s in IRREGULAR_SUBTYPES if str(s.subtype) not in seen]
    rng.shuffle(remaining)  # RNG fallback fills whatever the theme didn't pick
    ordered.extend(remaining)

    for spec in ordered[: max(0, knobs.irregular_subtype_count)]:
        n = max(0, round(rng.randint(spec.lo, spec.hi) * scale))
        _label(spec.parent, spec.subtype, n, colored=spec.colored)


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------


def generate_skeleton(
    config: SetConfig,
    knobs: SkeletonKnobs | None = None,
    reserved_slots: list[ReservedSlotSpec] | None = None,
) -> SkeletonResult:
    """Build the full set skeleton from a config and its tuned ``knobs``.

    Slot distribution targets (rarity counts, color split, type mix, signpost
    density) are knob-driven (:class:`SkeletonKnobs`); the mana curve and the hard
    invariants stay fixed. With default knobs and no cycles this reproduces the
    historical skeleton on the constraint-bearing dimensions.

    Steps:
      0. Carve any ``knobs.cycles`` out of the rarity budget (balance-preserving
         even spans; cycles that don't fit are dropped + recorded).
      1. Scale rarity counts to the target set size (knob weights).
      2. Distribute the *remaining* slots across colors per rarity (knob fractions).
      3. Assign card types per block (knob creature % + non-creature bias).
      4. Assign CMC targets following the mana curve.
      5. Assign mechanic complexity tags.
      6. Append the cycle members (stamped with ``cycle_id``) and tag archetypes.
      7. Retype ``planeswalker_count`` mythic slots; pin ``reserved_slots``.
      8. Run constraint validation.
      9. Return the assembled SkeletonResult (carrying knobs + cycles).

    ``reserved_slots`` (from ``build_reserved_slots(theme)``) stamps requested
    cards onto matching slots without changing slot counts or color/rarity/type,
    so all hard constraints still hold.
    """
    knobs = knobs or default_knobs()
    rarity_counts = _scale_rarity(config.set_size, knobs)
    cycle_members, kept_cycles, knob_warnings = _reserve_cycles(knobs.cycles, rarity_counts)
    for w in knob_warnings:
        logger.info("Skeleton knobs: %s", w)

    all_slots: list[SkeletonSlot] = []
    archetype_index: dict[str, list[str]] = {pair: [] for pair in COLOR_PAIRS}
    # Slot ids are plain zero-padded collector numbers (001, 002, …) assigned in
    # build order. They're an opaque join key + label — nothing parses them — so
    # they deliberately encode no color/rarity that could steer the LLM relabel.
    id_width = max(3, len(str(config.set_size)))

    def _add_slot(item: dict) -> None:
        sid = f"{len(all_slots) + 1:0{id_width}d}"
        slot = SkeletonSlot(
            slot_id=sid,
            color=item["color"],
            rarity=item["rarity"],
            card_type=item["card_type"],
            cmc_target=item["cmc_target"],
            archetype_tags=item["archetype_tags"],
            mechanic_tag=item["mechanic_tag"],
            color_pair=item["color_pair"],
            cycle_id=item.get("cycle_id"),
            cycle_name=item.get("cycle_name"),
            cycle_member=item.get("cycle_member"),
            notes=item.get("notes", ""),
        )
        all_slots.append(slot)
        for tag in item["archetype_tags"]:
            if tag in archetype_index:
                archetype_index[tag].append(sid)

    for rarity, count in rarity_counts.items():
        cyc = cycle_members.get(rarity, [])
        # Scalar half = the rarity budget minus this rarity's cycle members. Cycle
        # multicolor / colorless members count against those budgets (cycles are
        # balance-preserving, so the combined distribution stays balanced).
        scalar_total = count - len(cyc)
        # mono target is taken as the residual below, so only multi / colorless
        # targets are needed here.
        _, multi_t, cl_t = _color_targets(rarity, count, config.set_size, knobs)
        cyc_multi = sum(1 for m in cyc if m["color"] == "multicolor")
        cyc_cl = sum(1 for m in cyc if m["color"] == "colorless")
        # Uncommon multicolor IS the signpost target (signposts_per_pair x 10), so a
        # multicolor cycle at uncommon must NOT shrink it: cycle members are a
        # separate family that can't be signposts (they carry a cycle_id, which
        # _mark_signpost_slots skips), so the signpostable count stays the full
        # target and the cycle's members are additive. Other rarities treat
        # multicolor as a balance fraction, so their cycle members count toward it
        # (subtracted) to hold the total at target.
        multi_goal = multi_t if rarity == "uncommon" else max(0, multi_t - cyc_multi)
        scalar_multi = min(multi_goal, scalar_total)
        scalar_cl = min(max(0, cl_t - cyc_cl), scalar_total - scalar_multi)
        scalar_mono = scalar_total - scalar_multi - scalar_cl
        # The pairs this rarity's cycle members already occupy, so the scalar
        # multis fill the gaps (an allied-5 / enemy-5 cycle covers a non-contiguous
        # set of pairs, so a flat start-offset can't avoid them — feed the actual
        # covered pairs and let _build_color_slots level the per-pair coverage).
        cyc_covered_pairs = [m["color_pair"] for m in cyc if m["color"] == "multicolor"]
        color_assignments = _build_color_slots(
            rarity,
            scalar_mono,
            scalar_multi,
            scalar_cl,
            covered_pairs=cyc_covered_pairs,
        )

        # Group by color for block-level type / mechanic assignment
        blocks: dict[str, list[dict]] = {}
        for ca in color_assignments:
            key = ca["color"] if ca["color"] != "multicolor" else f"multi_{ca['color_pair']}"
            blocks.setdefault(key, []).append(ca)

        # Card types drive the mechanic tier (vanilla/french are creature-only), so
        # resolve every block's types first, then assign tiers pooled across the rarity.
        # Pool the creature / non-creature split across the rarity (not per block) so
        # small-set blocks can't collapse the spell mix or inflate creature density.
        block_types = _assign_card_types_pooled(blocks, rarity, knobs)
        block_mech = _assign_mechanic_tags(block_types, rarity)

        block_queues: dict[str, list[dict]] = {}
        for block_key, block_items in blocks.items():
            types = block_types[block_key]
            mech_tags = block_mech[block_key]

            queue: list[dict] = []
            for i, item in enumerate(block_items):
                color = item["color"]
                color_pair = item["color_pair"]
                queue.append(
                    {
                        "color": color,
                        "color_pair": color_pair,
                        "rarity": rarity,
                        "card_type": types[i],
                        "cmc_target": 0,  # placeholder
                        "archetype_tags": _archetype_tags_for_color(color, color_pair),
                        "mechanic_tag": mech_tags[i],
                    }
                )
            block_queues[block_key] = queue

        # Compute CMCs across the scalar slots, then deal them round-robin across
        # blocks so every color gets a fair spread of the mana curve.
        rarity_cmcs = _assign_cmcs(scalar_total, rarity)
        interleaved: list[dict] = []
        block_keys = list(block_queues.keys())
        max_block = max((len(q) for q in block_queues.values()), default=0)
        for pos in range(max_block):
            for bk in block_keys:
                q = block_queues[bk]
                if pos < len(q):
                    interleaved.append(q[pos])
        for idx, slot_dict in enumerate(interleaved):
            slot_dict["cmc_target"] = rarity_cmcs[idx] if idx < len(rarity_cmcs) else 3

        for bk in block_keys:
            for item in block_queues[bk]:
                _add_slot(item)

        # Cycle members for this rarity land last (kept contiguous so card-gen can
        # batch the family together); they keep their own type / cmc.
        for member in cyc:
            _add_slot(member)

    n_pw = _place_planeswalkers(all_slots, knobs.planeswalker_count)
    if n_pw:
        logger.info("Skeleton: placed %d planeswalker slot(s)", n_pw)

    unplaced = _apply_reservations(all_slots, reserved_slots or [])
    if unplaced:
        logger.info(
            "Skeleton: %d requested card(s) could not be reserved (matrix full): %s",
            len(unplaced),
            ", ".join(s.name for s in unplaced),
        )

    n_signposts = _mark_signpost_slots(all_slots, knobs.signposts_per_pair)
    logger.info("Skeleton: flagged %d signpost uncommon slot(s)", n_signposts)

    # Label fine-grained subtypes last (after special slots are flagged so it skips
    # them); a pure overlay that leaves card_type/color/rarity/counts untouched.
    _assign_subtypes(all_slots, knobs, config.set_size, config.code)
    n_subtypes = sum(1 for s in all_slots if s.card_subtype)
    logger.info("Skeleton: labelled %d slot(s) with a fine-grained subtype", n_subtypes)

    balance = _build_balance_report(all_slots, config.set_size, knobs.signposts_per_pair)

    return SkeletonResult(
        config=config,
        slots=all_slots,
        archetype_slots=archetype_index,
        balance_report=balance,
        total_slots=len(all_slots),
        knobs=knobs,
        cycles=kept_cycles,
        knob_warnings=knob_warnings,
    )


# ---------------------------------------------------------------------------
# Save helpers
# ---------------------------------------------------------------------------


def save_skeleton(result: SkeletonResult, output_dir: Path) -> tuple[Path, Path]:
    """Persist the skeleton to disk as JSON and a human-readable summary.

    Returns (json_path, txt_path).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- skeleton.json ---
    json_path = output_dir / "skeleton.json"
    atomic_write_text(
        json_path,
        result.model_dump_json(indent=2),
    )

    # --- skeleton-overview.txt ---
    txt_path = output_dir / "skeleton-overview.txt"
    lines = _render_overview(result)
    atomic_write_text(txt_path, "\n".join(lines))

    return json_path, txt_path


def _render_overview(result: SkeletonResult) -> list[str]:
    """Build a human-readable overview of the skeleton."""
    br = result.balance_report
    lines: list[str] = [
        f"Set Skeleton Overview: {result.config.name} [{result.config.code}]",
        f"Theme: {result.config.theme}",
        f"Total slots: {result.total_slots}",
        "",
        "=== Rarity Distribution ===",
    ]

    for r in ["common", "uncommon", "rare", "mythic"]:
        lines.append(f"  {r:10s}: {br.rarity_counts.get(r, 0)}")

    lines += [
        "",
        "=== Color Distribution ===",
    ]
    for c in [*COLORS, "multicolor", "colorless"]:
        lines.append(f"  {c:12s}: {br.color_counts.get(c, 0)}")

    lines += [
        "",
        "=== Type Distribution ===",
    ]
    for t in [
        "creature",
        "instant",
        "sorcery",
        "enchantment",
        "artifact",
        "planeswalker",
        "land",
    ]:
        cnt = br.type_counts.get(t, 0)
        if cnt:
            lines.append(f"  {t:14s}: {cnt}")

    lines += [
        "",
        f"Creature %: {br.creature_pct:.1f}%",
        f"Average CMC: {br.average_cmc:.2f}",
        "",
        "=== CMC Curve ===",
    ]
    for cmc in sorted(br.cmc_distribution):
        bar = "#" * br.cmc_distribution[cmc]
        lines.append(f"  CMC {cmc}: {br.cmc_distribution[cmc]:3d}  {bar}")

    lines += [
        "",
        "=== Archetype Coverage ===",
    ]
    for pair in COLOR_PAIRS:
        slot_ids = result.archetype_slots.get(pair, [])
        lines.append(f"  {pair}: {len(slot_ids)} slots")

    lines += [
        "",
        "=== Constraint Checks ===",
    ]
    for c in br.constraints:
        icon = "PASS" if c.passed else "FAIL"
        kind = "HARD" if c.is_hard else "SOFT"
        lines.append(f"  [{icon}] ({kind}) {c.name}: {c.message}")

    lines.append("")
    lines.append("All hard constraints passed: " + ("YES" if br.all_hard_passed else "NO"))

    non_default = [s for s in KNOB_SPECS if getattr(result.knobs, s.key) != s.default]
    if non_default or result.knobs_defaulted:
        lines += ["", "=== Tuned Knobs ==="]
        if result.knobs_defaulted:
            lines.append("  (phase-0 tuning unavailable — defaults used)")
        for spec in non_default:
            val = getattr(result.knobs, spec.key)
            lines.append(f"  {spec.label}: {val} (default {spec.default})")
    if result.cycles:
        lines += ["", f"=== Cycles ({len(result.cycles)}) ==="]
        for cyc in result.cycles:
            lines.append(f"  {cyc.name} — {cyc.span} {cyc.rarity} {cyc.card_type} (id {cyc.id})")
    for w in result.knob_warnings:
        lines.append(f"  ! {w}")

    reserved = [s for s in result.slots if s.reserved_card]
    if reserved:
        lines += ["", f"=== Reserved Cards ({len(reserved)}) ==="]
        for s in sorted(reserved, key=lambda s: s.slot_id):
            lines.append(f"  {s.slot_id:10s}  {s.reserved_card}")

    # --- Slot listing ---
    lines += ["", "=== Slot Matrix ==="]
    for rarity in ["common", "uncommon", "rare", "mythic"]:
        r_slots = sorted(
            [s for s in result.slots if s.rarity == rarity],
            key=lambda s: s.slot_id,
        )
        lines.append(f"\n--- {rarity.upper()} ({len(r_slots)}) ---")
        for s in r_slots:
            arch = ",".join(s.archetype_tags) if s.archetype_tags else "-"
            lines.append(
                f"  {s.slot_id:10s}  {s.card_type:14s}  CMC={s.cmc_target}  "
                f"mech={s.mechanic_tag:15s}  arch={arch}"
            )

    return lines
