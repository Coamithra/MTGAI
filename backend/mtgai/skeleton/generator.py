"""Skeleton generator — builds the structural slot matrix for an MTG set.

Given a SetConfig and the research-derived set template, this module:
1. Scales rarity counts proportionally to the target set size.
2. Distributes mono-color, multicolor, and colorless slots per rarity.
3. Assigns card types, CMC targets, mechanic tags, and archetype associations.
4. Validates hard and soft structural constraints.
5. Returns a SkeletonResult ready for downstream card generation.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_SET_SIZE = 277

COLORS = ["W", "U", "B", "R", "G"]

COLOR_PAIRS = ["WU", "WB", "WR", "WG", "UB", "UR", "UG", "BR", "BG", "RG"]

BASE_RARITY_COUNTS: dict[str, int] = {
    "common": 95,
    "uncommon": 98,
    "rare": 63,
    "mythic": 20,
}


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
    cmc_target: int
    archetype_tags: list[str] = Field(default_factory=list)
    mechanic_tag: str = MechanicTag.EVERGREEN
    is_reprint_slot: bool = False
    card_id: str | None = None
    notes: str = ""
    color_pair: str | None = None  # for multicolor slots


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


# ---------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------


def _load_template(template_path: Path) -> dict:
    """Read and parse the set-template.json file."""
    return json.loads(template_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Rarity scaling
# ---------------------------------------------------------------------------


def _scale_rarity(set_size: int) -> dict[str, int]:
    """Scale rarity counts proportionally from the 277-card base.

    Returns a dict like {"common": 21, "uncommon": 21, "rare": 14, "mythic": 4}.
    Adjusts the largest bucket so the total equals *set_size*.
    """
    ratio = set_size / BASE_SET_SIZE
    counts = {r: round(c * ratio) for r, c in BASE_RARITY_COUNTS.items()}

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


def _distribute_colors(rarity: str, count: int, set_size: int) -> list[dict]:
    """Distribute *count* slots of a given rarity across colors.

    Returns a list of dicts: {"color": ..., "color_pair": ...}.
    """
    is_small = set_size <= 100
    slots: list[dict] = []

    # --- Multicolor budget ---
    if rarity == "common":
        multi = 0 if is_small else max(0, round(count * 0.04))
    elif rarity == "uncommon":
        # Signpost uncommons: 10 for full set, scaled down for small
        multi = min(10, max(5, round(10 * set_size / BASE_SET_SIZE)))
        multi = min(multi, count)
    elif rarity == "rare":
        multi = max(0, round(count * 0.25))
    else:  # mythic
        multi = max(0, round(count * 0.30))

    # --- Colorless budget ---
    if rarity == "common":
        colorless = max(1, round(count * 0.06))
    elif rarity == "uncommon":
        colorless = max(1, round(count * 0.07))
    elif rarity == "rare":
        colorless = max(0, round(count * 0.03))
    else:
        colorless = max(0, round(count * 0.05))

    mono_total = count - multi - colorless
    if mono_total < 0:
        # Squeeze multicolor if needed
        excess = -mono_total
        multi = max(0, multi - excess)
        mono_total = count - multi - colorless
        if mono_total < 0:
            colorless = max(0, colorless + mono_total)
            mono_total = count - multi - colorless

    per_color = mono_total // 5
    remainder = mono_total - per_color * 5

    # At common the color-balance constraint requires ±0 spread, so any
    # remainder that would make one color larger than another must be moved
    # to the colorless bucket instead.
    if rarity == "common" and remainder > 0:
        colorless += remainder
        remainder = 0

    # Distribute mono-color: each color gets per_color, spread remainder
    for i, c in enumerate(COLORS):
        n = per_color + (1 if i < remainder else 0)
        for _ in range(n):
            slots.append({"color": c, "color_pair": None})

    # Multicolor: cycle through pairs so coverage is even
    for i in range(multi):
        pair = COLOR_PAIRS[i % len(COLOR_PAIRS)]
        slots.append({"color": "multicolor", "color_pair": pair})

    # Colorless
    for _ in range(colorless):
        slots.append({"color": "colorless", "color_pair": None})

    return slots


# ---------------------------------------------------------------------------
# Card type assignment
# ---------------------------------------------------------------------------

# Per-rarity creature target percentages (from template)
_CREATURE_PCT: dict[str, float] = {
    "common": 53.0,
    "uncommon": 53.0,
    "rare": 55.0,
    "mythic": 50.0,
}


def _assign_card_types(
    color: str,
    rarity: str,
    block_size: int,
) -> list[str]:
    """Return a list of card-type strings for a (color, rarity) block.

    Rules:
    - Creatures fill ~50-55% of the block.
    - Instants + sorceries fill ~30% at common, ~25% at higher rarities.
    - Remainder goes to enchantments / artifacts.
    - Colorless slots are always artifacts.
    - Planeswalkers only at mythic (max 1 per set, placed explicitly later).
    """
    if block_size == 0:
        return []

    if color == "colorless":
        return [SlotCardType.ARTIFACT] * block_size

    creature_pct = _CREATURE_PCT.get(rarity, 53.0)
    n_creatures = max(1, round(block_size * creature_pct / 100))
    n_creatures = min(n_creatures, block_size)

    remaining = block_size - n_creatures

    # Noncreature split
    if rarity == "common":
        instant_ratio, sorcery_ratio = 0.40, 0.30
    elif rarity == "uncommon":
        instant_ratio, sorcery_ratio = 0.35, 0.30
    else:
        instant_ratio, sorcery_ratio = 0.30, 0.30

    n_instants = max(0, round(remaining * instant_ratio))
    n_sorceries = max(0, round(remaining * sorcery_ratio))
    n_enchantments = remaining - n_instants - n_sorceries
    if n_enchantments < 0:
        n_sorceries += n_enchantments
        n_enchantments = 0

    types: list[str] = (
        [SlotCardType.CREATURE] * n_creatures
        + [SlotCardType.INSTANT] * n_instants
        + [SlotCardType.SORCERY] * n_sorceries
        + [SlotCardType.ENCHANTMENT] * n_enchantments
    )
    return types[:block_size]


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


def _assign_mechanic_tags(block_size: int, rarity: str) -> list[str]:
    """Assign complexity-tier tags to a block of slots.

    Common: ~15% vanilla, ~25% french_vanilla, ~40% evergreen, ~20% complex
    Uncommon: ~5% french_vanilla, ~55% evergreen, ~40% complex
    Rare/Mythic: mostly complex
    """
    if block_size == 0:
        return []

    if rarity == "common":
        n_vanilla = max(1, round(block_size * 0.15))
        n_french = max(1, round(block_size * 0.25))
        n_complex = max(0, round(block_size * 0.20))
        n_evergreen = block_size - n_vanilla - n_french - n_complex
        if n_evergreen < 0:
            n_complex += n_evergreen
            n_evergreen = 0
    elif rarity == "uncommon":
        n_vanilla = 0
        n_french = max(0, round(block_size * 0.05))
        n_complex = max(1, round(block_size * 0.40))
        n_evergreen = block_size - n_french - n_complex
        if n_evergreen < 0:
            n_complex += n_evergreen
            n_evergreen = 0
    else:
        n_vanilla = 0
        n_french = 0
        n_evergreen = max(0, round(block_size * 0.15))
        n_complex = block_size - n_evergreen

    tags: list[str] = (
        [MechanicTag.VANILLA] * n_vanilla
        + [MechanicTag.FRENCH_VANILLA] * n_french
        + [MechanicTag.EVERGREEN] * n_evergreen
        + [MechanicTag.COMPLEX] * n_complex
    )
    while len(tags) < block_size:
        tags.append(MechanicTag.EVERGREEN)
    return tags[:block_size]


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


def _slot_id(color: str, rarity: str, index: int, color_pair: str | None = None) -> str:
    """Generate a human-readable slot identifier.

    Format: <COLOR>-<RARITY_LETTER>-<NN>
    Examples: W-C-01, UB-U-03, X-R-02 (X = colorless)
    """
    rarity_letter = rarity[0].upper()  # C, U, R, M
    if color == "multicolor" and color_pair:
        color_code = color_pair
    elif color == "colorless":
        color_code = "X"
    else:
        color_code = color
    return f"{color_code}-{rarity_letter}-{index:02d}"


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

    if non_land:
        creature_count = sum(1 for s in non_land if s.card_type == SlotCardType.CREATURE)
        pct = creature_count / len(non_land) * 100
        results.append(
            ConstraintResult(
                name="overall_creature_density",
                passed=pct >= 50.0,
                message=f"Overall creature density: {pct:.1f}% (min 50%)",
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
) -> ConstraintResult:
    """Hard: enough multicolor uncommons to serve as signposts."""
    multi_unc = [s for s in slots if s.rarity == "uncommon" and s.color == "multicolor"]
    required = 5 if set_size <= 100 else 10
    return ConstraintResult(
        name="signpost_uncommons",
        passed=len(multi_unc) >= required,
        message=(f"Multicolor uncommons: {len(multi_unc)} (need >= {required})"),
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
) -> list[ConstraintResult]:
    """Run all hard and soft constraint checks."""
    results: list[ConstraintResult] = []
    results.extend(_check_color_balance(slots))
    results.extend(_check_creature_density(slots))
    results.append(_check_signpost_uncommons(slots, set_size))
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

    constraints = _validate_skeleton(slots, set_size)
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
# Main generator
# ---------------------------------------------------------------------------


def generate_skeleton(
    config: SetConfig,
    template_path: Path,
) -> SkeletonResult:
    """Build the full set skeleton from a config and template.

    Steps:
      1. Load template and scale rarity counts.
      2. Distribute colors within each rarity.
      3. Assign card types per (color, rarity) block.
      4. Assign CMC targets following the mana curve.
      5. Assign mechanic complexity tags.
      6. Tag slots with draft archetype associations.
      7. Run constraint validation.
      8. Return the assembled SkeletonResult.
    """
    _template = _load_template(template_path)  # available for future use
    rarity_counts = _scale_rarity(config.set_size)

    all_slots: list[SkeletonSlot] = []
    archetype_index: dict[str, list[str]] = {pair: [] for pair in COLOR_PAIRS}

    for rarity, count in rarity_counts.items():
        color_assignments = _distribute_colors(rarity, count, config.set_size)

        # Group by color for block-level type / mechanic assignment
        blocks: dict[str, list[dict]] = {}
        for ca in color_assignments:
            key = ca["color"] if ca["color"] != "multicolor" else f"multi_{ca['color_pair']}"
            blocks.setdefault(key, []).append(ca)

        # Build per-block type and mechanic lists; collect interim slots
        # (CMC is assigned below via interleaved distribution).
        block_queues: dict[str, list[dict]] = {}
        for block_key, block_items in blocks.items():
            block_size = len(block_items)
            representative_color = block_items[0]["color"]

            types = _assign_card_types(representative_color, rarity, block_size)
            mech_tags = _assign_mechanic_tags(block_size, rarity)

            queue: list[dict] = []
            for i, item in enumerate(block_items):
                color = item["color"]
                color_pair = item["color_pair"]
                arch_tags = _archetype_tags_for_color(color, color_pair)
                queue.append(
                    {
                        "color": color,
                        "color_pair": color_pair,
                        "rarity": rarity,
                        "card_type": types[i],
                        "cmc_target": 0,  # placeholder
                        "archetype_tags": arch_tags,
                        "mechanic_tag": mech_tags[i],
                    }
                )
            block_queues[block_key] = queue

        # Compute CMCs at the rarity level for accurate distribution,
        # then deal them round-robin across blocks so every color gets
        # a fair spread of the mana curve.
        rarity_cmcs = _assign_cmcs(count, rarity)
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

        # Flatten back to a single list preserving original block order
        interim_slots: list[dict] = []
        for bk in block_keys:
            interim_slots.extend(block_queues[bk])

        # Assign slot IDs and build final SkeletonSlot objects
        for item in interim_slots:
            color = item["color"]
            color_pair = item["color_pair"]

            existing = [
                s
                for s in all_slots
                if s.color == color
                and s.rarity == rarity
                and (color != "multicolor" or s.color_pair == color_pair)
            ]
            idx = len(existing) + 1

            sid = _slot_id(color, rarity, idx, color_pair)
            slot = SkeletonSlot(
                slot_id=sid,
                color=color,
                rarity=rarity,
                card_type=item["card_type"],
                cmc_target=item["cmc_target"],
                archetype_tags=item["archetype_tags"],
                mechanic_tag=item["mechanic_tag"],
                color_pair=color_pair,
            )
            all_slots.append(slot)

            for tag in item["archetype_tags"]:
                if tag in archetype_index:
                    archetype_index[tag].append(sid)

    balance = _build_balance_report(all_slots, config.set_size)

    return SkeletonResult(
        config=config,
        slots=all_slots,
        archetype_slots=archetype_index,
        balance_report=balance,
        total_slots=len(all_slots),
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
    json_path.write_text(
        result.model_dump_json(indent=2),
        encoding="utf-8",
    )

    # --- skeleton-overview.txt ---
    txt_path = output_dir / "skeleton-overview.txt"
    lines = _render_overview(result)
    txt_path.write_text("\n".join(lines), encoding="utf-8")

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
