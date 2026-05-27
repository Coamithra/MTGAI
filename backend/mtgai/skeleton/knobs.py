"""Skeleton knobs — the theme-tunable structural parameters of a set.

The skeleton's *structure* used to be hardcoded module constants in
``generator.py`` (rarity ratio, multicolor density, creature %, type mix), scaled
only by ``set_size``. Research (``research/set-design.md``) shows real sets keep a
small set of structural invariants fixed while a handful of theme-dependent
variables — multicolor density most of all — carry set identity. This module is
the single source of truth for those tunable variables:

* **Scalar knobs** — flat ``SkeletonKnobs`` fields (rarity weights, multicolor /
  colorless / creature fractions, non-creature type bias, planeswalker count,
  signposts per pair). Each has a :class:`KnobSpec` with ``{default, min, max,
  step}`` in :data:`KNOB_SPECS`. That one definition drives AI-output validation,
  manual-input validation, and the UI control bounds — the bounds the user sees
  *are* the bounds enforced. Defaults reproduce today's skeleton on the
  constraint-bearing dimensions (see ``plans/skeleton-knobs.md``).
* **Cycles** — :class:`Cycle` structural reservations carved before the scalar
  distribution. A cycle whose span is "one per color" / "one per pair" is
  balance-preserving by construction, so it lets a set make a bold structural
  statement (10 dual lands, a mono-5 rare cycle) without breaking the ±0
  color-balance invariant.

**The LLM proposes, the deterministic layer disposes.** Phase 0 (the tuner) may
only move knobs within these clamp ranges; phase 1 (``generate_skeleton``) always
reconciles to the hard invariants. A value out of range is clamped on validation
(``model_validator``), so neither a hallucinated AI value nor a hand-typed one can
ever produce an illegal skeleton.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Knob specs — one source of truth for bounds (AI clamp + manual validate + UI)
# ---------------------------------------------------------------------------


class KnobKind(StrEnum):
    INT = "int"
    FLOAT = "float"


class KnobSpec(BaseModel):
    """Bounds + metadata for one scalar knob.

    ``key`` matches the field name on :class:`SkeletonKnobs`. ``group`` buckets the
    knob in the UI; ``label`` / ``help`` are display text. Validation, AI clamping,
    and the UI control's ``min``/``max``/``step`` all read from this one object.
    """

    key: str
    label: str
    group: str
    kind: KnobKind
    default: float
    min: float
    max: float
    step: float
    help: str = ""

    def clamp(self, value: float) -> float:
        """Clamp *value* into [min, max], coercing to int for INT knobs."""
        v = max(self.min, min(self.max, value))
        return round(v) if self.kind == KnobKind.INT else float(v)


# Rarity weights are expressed as counts for a ~277-card premier set (the unit the
# research tables use); the generator scales them to the project's set_size. The
# fraction knobs are fractions of that rarity's slot count.
KNOB_SPECS: list[KnobSpec] = [
    # --- Rarity weights (research §2.1, scaled to set_size) ---
    KnobSpec(
        key="rarity_common",
        label="Commons",
        group="rarity",
        kind=KnobKind.INT,
        default=95,
        min=86,
        max=113,
        step=1,
        help="Common weight per ~277-card set (scaled to your set size).",
    ),
    KnobSpec(
        key="rarity_uncommon",
        label="Uncommons",
        group="rarity",
        kind=KnobKind.INT,
        default=98,
        min=92,
        max=100,
        step=1,
        help="Uncommon weight per ~277-card set.",
    ),
    KnobSpec(
        key="rarity_rare",
        label="Rares",
        group="rarity",
        kind=KnobKind.INT,
        default=63,
        min=60,
        max=70,
        step=1,
        help="Rare weight per ~277-card set (MKM ran 70 for its gold theme).",
    ),
    KnobSpec(
        key="rarity_mythic",
        label="Mythics",
        group="rarity",
        kind=KnobKind.INT,
        default=20,
        min=20,
        max=22,
        step=1,
        help="Mythic weight per ~277-card set.",
    ),
    # --- Multicolor density (research §2.2 — the largest theme variable) ---
    # Uncommon multicolor is signpost-driven (see signposts_per_pair), not a
    # loose fraction, so there is no multicolor_uncommon knob.
    KnobSpec(
        key="multicolor_common",
        label="Multicolor commons",
        group="multicolor",
        kind=KnobKind.FLOAT,
        default=0.04,
        min=0.0,
        max=0.12,
        step=0.01,
        help="Fraction of commons that are gold (large sets only; small sets "
        "stay mono). Gold commons as a clean one-per-pair set are better modeled "
        "as a pairs10 common cycle.",
    ),
    KnobSpec(
        key="multicolor_rare",
        label="Multicolor rares",
        group="multicolor",
        kind=KnobKind.FLOAT,
        default=0.25,
        min=0.10,
        max=0.45,
        step=0.01,
        help="Fraction of rares that are gold.",
    ),
    KnobSpec(
        key="multicolor_mythic",
        label="Multicolor mythics",
        group="multicolor",
        kind=KnobKind.FLOAT,
        default=0.30,
        min=0.10,
        max=0.50,
        step=0.01,
        help="Fraction of mythics that are gold.",
    ),
    # --- Colorless density (research §2.2 — LCI 15%, MKM 3%) ---
    KnobSpec(
        key="colorless_common",
        label="Colorless commons",
        group="colorless",
        kind=KnobKind.FLOAT,
        default=0.06,
        min=0.0,
        max=0.18,
        step=0.01,
    ),
    KnobSpec(
        key="colorless_uncommon",
        label="Colorless uncommons",
        group="colorless",
        kind=KnobKind.FLOAT,
        default=0.07,
        min=0.0,
        max=0.18,
        step=0.01,
    ),
    KnobSpec(
        key="colorless_rare",
        label="Colorless rares",
        group="colorless",
        kind=KnobKind.FLOAT,
        default=0.03,
        min=0.0,
        max=0.15,
        step=0.01,
    ),
    KnobSpec(
        key="colorless_mythic",
        label="Colorless mythics",
        group="colorless",
        kind=KnobKind.FLOAT,
        default=0.05,
        min=0.0,
        max=0.15,
        step=0.01,
    ),
    # --- Creature density per rarity (research §2.3) ---
    KnobSpec(
        key="creature_common",
        label="Creature % (common)",
        group="creature",
        kind=KnobKind.FLOAT,
        default=0.53,
        min=0.45,
        max=0.62,
        step=0.01,
    ),
    KnobSpec(
        key="creature_uncommon",
        label="Creature % (uncommon)",
        group="creature",
        kind=KnobKind.FLOAT,
        default=0.53,
        min=0.45,
        max=0.62,
        step=0.01,
    ),
    KnobSpec(
        key="creature_rare",
        label="Creature % (rare)",
        group="creature",
        kind=KnobKind.FLOAT,
        default=0.55,
        min=0.45,
        max=0.65,
        step=0.01,
    ),
    KnobSpec(
        key="creature_mythic",
        label="Creature % (mythic)",
        group="creature",
        kind=KnobKind.FLOAT,
        default=0.50,
        min=0.40,
        max=0.65,
        step=0.01,
    ),
    # --- Non-creature type bias (relative weights, normalized; research §2.3
    # DSK enchantments / LCI artifacts). Artifact defaults to 0 so colored slots
    # carry no artifacts by default, matching today's generator. ---
    KnobSpec(
        key="noncreature_instant",
        label="Instant bias",
        group="noncreature",
        kind=KnobKind.FLOAT,
        default=0.35,
        min=0.0,
        max=1.0,
        step=0.05,
    ),
    KnobSpec(
        key="noncreature_sorcery",
        label="Sorcery bias",
        group="noncreature",
        kind=KnobKind.FLOAT,
        default=0.30,
        min=0.0,
        max=1.0,
        step=0.05,
    ),
    KnobSpec(
        key="noncreature_enchantment",
        label="Enchantment bias",
        group="noncreature",
        kind=KnobKind.FLOAT,
        default=0.35,
        min=0.0,
        max=1.0,
        step=0.05,
    ),
    KnobSpec(
        key="noncreature_artifact",
        label="Artifact bias",
        group="noncreature",
        kind=KnobKind.FLOAT,
        default=0.0,
        min=0.0,
        max=1.0,
        step=0.05,
    ),
    # --- Counts ---
    KnobSpec(
        key="planeswalker_count",
        label="Planeswalkers",
        group="special",
        kind=KnobKind.INT,
        default=0,
        min=0,
        max=2,
        step=1,
        help="Mythic planeswalker slots. Defaults to 0 to leave the failure-path "
        "skeleton unchanged; the modern norm is 1.",
    ),
    KnobSpec(
        key="signposts_per_pair",
        label="Signposts per pair",
        group="special",
        kind=KnobKind.INT,
        default=1,
        min=1,
        max=2,
        step=1,
        help="Multicolor uncommon signposts per color pair (BLB ran 1, DSK/OTJ/MKM 2).",
    ),
]

KNOB_SPEC_BY_KEY: dict[str, KnobSpec] = {s.key: s for s in KNOB_SPECS}


# ---------------------------------------------------------------------------
# Cycles
# ---------------------------------------------------------------------------


class CycleSpan(StrEnum):
    """How a cycle's members spread across colors.

    The five-/ten-member spans are balance-preserving (they add slots evenly
    across colors or pairs), which is *why* real design uses the cycle as the unit
    for a bold structural statement. ``single`` is the escape hatch for a one-off
    structural slot and is placed as colorless to stay balance-safe.
    """

    MONO5 = "mono5"  # one per WUBRG
    PAIRS10 = "pairs10"  # one per two-color pair
    ALLIED5 = "allied5"  # one per allied pair
    ENEMY5 = "enemy5"  # one per enemy pair
    WEDGES5 = "wedges5"  # one per enemy-based three-color wedge
    SHARDS5 = "shards5"  # one per allied-based three-color shard
    COLORLESS1 = "colorless1"  # a single colorless member
    SINGLE = "single"  # a one-off structural slot (placed colorless)


# Member count for each span — used by the feasibility check + UI without
# expanding the slots. SINGLE / COLORLESS1 are 1.
CYCLE_SPAN_SIZE: dict[str, int] = {
    CycleSpan.MONO5: 5,
    CycleSpan.PAIRS10: 10,
    CycleSpan.ALLIED5: 5,
    CycleSpan.ENEMY5: 5,
    CycleSpan.WEDGES5: 5,
    CycleSpan.SHARDS5: 5,
    CycleSpan.COLORLESS1: 1,
    CycleSpan.SINGLE: 1,
}

# Color-pair groupings (canonical COLOR_PAIRS ordering). Allied = neighbors on the
# W-U-B-R-G wheel; enemy = the rest. Their union is all 10 pairs.
ALLIED_PAIRS: list[str] = ["WU", "UB", "BR", "RG", "WG"]
ENEMY_PAIRS: list[str] = ["WB", "WR", "UR", "UG", "BG"]
ALL_PAIRS: list[str] = ["WU", "WB", "WR", "WG", "UB", "UR", "UG", "BR", "BG", "RG"]
# Three-color combos. Shards are allied-arc (e.g. WUB); wedges are enemy-based
# (e.g. WBG). Five each; used only for color flavor — they all count as
# "multicolor" with no single color_pair.
SHARD_TRIOS: list[str] = ["WUB", "UBR", "BRG", "RGW", "GWU"]
WEDGE_TRIOS: list[str] = ["WBG", "URW", "BGU", "RWB", "GUR"]

_RARITIES = {"common", "uncommon", "rare", "mythic"}
_CARD_TYPES = {"creature", "instant", "sorcery", "enchantment", "artifact", "planeswalker", "land"}


class Cycle(BaseModel):
    """A structural reservation spanning several balanced slots.

    Members share a ``card_type`` and a design ``template`` (a one-line prose
    brief card-gen renders into a coherent family). ``cmc_target`` seeds the
    members' mana value (0 for lands). The deterministic build expands the span
    into slots, stamps each member's ``cycle_id``, and decrements the rarity
    budget before distributing the scalar remainder.
    """

    id: str
    name: str
    rarity: str = "uncommon"
    span: CycleSpan = CycleSpan.MONO5
    card_type: str = "creature"
    template: str = ""
    cmc_target: int = 3
    notes: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> Cycle:
        if self.rarity not in _RARITIES:
            object.__setattr__(self, "rarity", "uncommon")
        if self.card_type not in _CARD_TYPES:
            object.__setattr__(self, "card_type", "creature")
        # Lands have no mana value; clamp others to the curve range.
        cmc = 0 if self.card_type == "land" else max(0, min(12, self.cmc_target))
        object.__setattr__(self, "cmc_target", cmc)
        return self

    @property
    def size(self) -> int:
        return CYCLE_SPAN_SIZE.get(self.span, 1)


# ---------------------------------------------------------------------------
# SkeletonKnobs
# ---------------------------------------------------------------------------


class SkeletonKnobs(BaseModel):
    """The tunable structural parameters, clamped to the knob specs on validation.

    Every scalar field mirrors a :data:`KNOB_SPECS` entry (a drift test enforces
    this). ``provenance`` maps each knob key to ``"default" | "ai" | "user"`` for
    the UI badge; ``pinned`` lists keys a re-tune must leave alone. Construct via
    :meth:`from_payload` to also collect human-readable clamp warnings.
    """

    # rarity weights
    rarity_common: int = 95
    rarity_uncommon: int = 98
    rarity_rare: int = 63
    rarity_mythic: int = 20
    # multicolor fractions
    multicolor_common: float = 0.04
    multicolor_rare: float = 0.25
    multicolor_mythic: float = 0.30
    # colorless fractions
    colorless_common: float = 0.06
    colorless_uncommon: float = 0.07
    colorless_rare: float = 0.03
    colorless_mythic: float = 0.05
    # creature fractions
    creature_common: float = 0.53
    creature_uncommon: float = 0.53
    creature_rare: float = 0.55
    creature_mythic: float = 0.50
    # non-creature type bias
    noncreature_instant: float = 0.35
    noncreature_sorcery: float = 0.30
    noncreature_enchantment: float = 0.35
    noncreature_artifact: float = 0.0
    # counts
    planeswalker_count: int = 0
    signposts_per_pair: int = 1
    # cycles
    cycles: list[Cycle] = Field(default_factory=list)
    # metadata (not clamped knobs)
    provenance: dict[str, str] = Field(default_factory=dict)
    pinned: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _round_int_knobs(cls, data: Any) -> Any:
        # An int knob may arrive as a float (LLM tool call, hand-edited JSON);
        # Pydantic rejects a fractional float for an int field before the
        # after-clamp runs, so round it here first. Copy first — never mutate the
        # caller's dict (it may be a reused theme/config fragment).
        if isinstance(data, dict):
            data = dict(data)
            for spec in KNOB_SPECS:
                if spec.kind == KnobKind.INT and spec.key in data:
                    try:
                        data[spec.key] = round(float(data[spec.key]))
                    except (TypeError, ValueError):
                        data.pop(spec.key)  # let the field default kick in
        return data

    @model_validator(mode="after")
    def _clamp_all(self) -> SkeletonKnobs:
        for spec in KNOB_SPECS:
            object.__setattr__(self, spec.key, spec.clamp(getattr(self, spec.key)))
        # Drop pins for keys that aren't real knobs.
        object.__setattr__(self, "pinned", [k for k in self.pinned if k in KNOB_SPEC_BY_KEY])
        return self

    def noncreature_weights(self) -> dict[str, float]:
        """Normalized {type: weight} for the four non-creature types.

        Falls back to an even split if all four are zero (the LLM zeroed
        everything), so the distributor never divides by zero.
        """
        raw = {
            "instant": self.noncreature_instant,
            "sorcery": self.noncreature_sorcery,
            "enchantment": self.noncreature_enchantment,
            "artifact": self.noncreature_artifact,
        }
        total = sum(raw.values())
        if total <= 0:
            return {k: 0.25 for k in raw}
        return {k: v / total for k, v in raw.items()}

    @classmethod
    def from_payload(
        cls, raw: object, *, source: str | None = None
    ) -> tuple[SkeletonKnobs, list[str]]:
        """Build knobs from an untrusted dict, returning (knobs, warnings).

        Each scalar value is validated against its spec; values outside [min, max]
        are clamped and reported in ``warnings``. ``source`` (``"ai"`` / ``"user"``)
        stamps provenance for every knob key present in ``raw`` that differs from
        the default; absent keys keep the default value + ``"default"`` provenance.
        Unknown keys and malformed types are ignored. ``cycles`` are validated
        through :class:`Cycle` (bad entries dropped).
        """
        data: dict = raw if isinstance(raw, dict) else {}
        warnings: list[str] = []
        payload: dict[str, Any] = {}
        provenance: dict[str, str] = {}

        for spec in KNOB_SPECS:
            if spec.key not in data:
                provenance[spec.key] = "default"
                continue
            try:
                val = float(data[spec.key])
            except (TypeError, ValueError):
                warnings.append(f"{spec.label}: ignored non-numeric value")
                provenance[spec.key] = "default"
                continue
            clamped = spec.clamp(val)
            if abs(clamped - val) > 1e-9:
                warnings.append(f"{spec.label}: {_fmt(val)} clamped to {_fmt(clamped)}")
            payload[spec.key] = clamped
            if source and abs(clamped - spec.default) > 1e-9:
                provenance[spec.key] = source
            else:
                provenance[spec.key] = "default"

        cycles: list[Cycle] = []
        for entry in data.get("cycles") or []:
            if not isinstance(entry, dict):
                continue
            try:
                cycles.append(Cycle.model_validate(entry))
            except Exception:  # drop malformed cycle, keep the rest
                warnings.append("Dropped a malformed cycle entry")

        pinned = [
            k for k in (data.get("pinned") or []) if isinstance(k, str) and k in KNOB_SPEC_BY_KEY
        ]
        # Caller-supplied provenance (e.g. preserving prior pins) overrides ours.
        prov_override = data.get("provenance")
        if isinstance(prov_override, dict):
            for k, v in prov_override.items():
                if k in KNOB_SPEC_BY_KEY and isinstance(v, str):
                    provenance[k] = v

        payload["cycles"] = cycles
        payload["provenance"] = provenance
        payload["pinned"] = pinned
        return cls.model_validate(payload), warnings

    def merge_pins_from(self, base: SkeletonKnobs) -> SkeletonKnobs:
        """Return a copy with ``base``'s pinned knob values restored.

        Used by the phase-0 re-tune: the AI re-tunes everything, then the user's
        pinned knobs are forced back to their pinned values (and provenance), so a
        re-roll respects "you handle the rest, but multicolor stays at 24%".
        """
        if not base.pinned:
            return self
        updates: dict[str, float] = {}
        provenance = dict(self.provenance)
        for key in base.pinned:
            if key in KNOB_SPEC_BY_KEY:
                updates[key] = getattr(base, key)
                provenance[key] = base.provenance.get(key, "user")
        return self.model_copy(
            update={**updates, "provenance": provenance, "pinned": list(base.pinned)}
        )


def _fmt(v: float) -> str:
    return str(int(v)) if abs(v - round(v)) < 1e-9 else f"{v:.2f}"


def default_knobs() -> SkeletonKnobs:
    """A fresh SkeletonKnobs at every default (all provenance ``"default"``)."""
    return SkeletonKnobs(provenance={s.key: "default" for s in KNOB_SPECS})


def knob_specs_payload() -> list[dict]:
    """The knob specs as plain dicts for the wizard UI to render controls from."""
    return [s.model_dump() for s in KNOB_SPECS]
