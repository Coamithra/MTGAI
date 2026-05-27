"""Reprint knobs — per-rarity reprint targets for a set.

A miniature sibling of skeleton knobs (``mtgai/skeleton/knobs.py``). One target
*per rarity* (``common``/``uncommon``/``rare``/``mythic``): ``None`` = **auto**
(the lean per-rarity reprint rate x how many cards of that rarity the set has),
an int = **pinned** (exact). Auto rarities also get a **proportional jitter** so
re-runs vary; pinned rarities never jitter.

Slots are plain text after the skeleton stage, so we can't count slots per
rarity — instead the auto target estimates a rarity's card count from
``set_size`` x the standard rarity distribution. The resolved breakdown is
*soft*: it's stated to the LLM in the select prompt ("pick 1 rare, 3 uncommon,
4 common"), not hard-enforced — the pool cards carry their printed rarity, so the
model can honour it, but a near miss is fine.
"""

from __future__ import annotations

import contextlib
import random

from pydantic import BaseModel, model_validator

RARITIES: list[str] = ["common", "uncommon", "rare", "mythic"]

# Lean per-rarity reprint rates: fraction of each rarity's cards filled by a pool
# reprint. Below the 2.8% cross-set average (research/reprint-analysis.md §1.3)
# because land cycles are generated separately + there's no nostalgia inflation.
# Mythic is the lowest — the research's high mythic reprint rate (4.7%) is driven
# entirely by nostalgia/return-set splashy creatures, which we don't do; a
# generated set's mythics are all bespoke. A ~277-card set auto-resolves to ~5
# (3 common / 1 uncommon / 1 rare / 0 mythic).
REPRINT_RARITY_RATES: dict[str, float] = {
    "common": 0.030,
    "uncommon": 0.010,
    "rare": 0.020,
    "mythic": 0.020,
}

# Standard rarity distribution weights (mirror the skeleton default rarity
# weights, ~95/98/63/20 per ~276-card set). Used to estimate a set's card count
# per rarity from set_size, since plain-text slots can't be counted by rarity.
RARITY_WEIGHTS: dict[str, int] = {"common": 95, "uncommon": 98, "rare": 63, "mythic": 20}

# Generous upper clamp — real per-rarity targets are single digits.
_MAX_PER_RARITY = 40


class ReprintKnobs(BaseModel):
    """Per-rarity reprint targets + proportional jitter.

    Each rarity is ``None`` (auto-derive) or an explicit non-negative count
    (pinned). ``jitter_pct`` is the fraction of the auto total applied as a
    random +/- nudge at roll time (0 disables; pinned rarities never jitter).
    """

    common: int | None = None
    uncommon: int | None = None
    rare: int | None = None
    mythic: int | None = None
    jitter_pct: float = 0.25

    @model_validator(mode="after")
    def _clamp(self) -> ReprintKnobs:
        for r in RARITIES:
            v = getattr(self, r)
            if v is not None:
                object.__setattr__(self, r, max(0, min(_MAX_PER_RARITY, int(v))))
        object.__setattr__(self, "jitter_pct", max(0.0, min(1.0, float(self.jitter_pct))))
        return self

    def provenance(self) -> dict[str, str]:
        """``{rarity: "user" | "auto"}`` for the UI badge — pinned vs derived."""
        return {r: ("user" if getattr(self, r) is not None else "auto") for r in RARITIES}


def default_knobs() -> ReprintKnobs:
    """All rarities auto, default jitter."""
    return ReprintKnobs()


def from_payload(raw: object) -> ReprintKnobs:
    """Build knobs from an untrusted dict, tolerating junk.

    A rarity value of ``None``/missing/blank/non-numeric means auto. Clamping
    happens in the model validator.
    """
    data = raw if isinstance(raw, dict) else {}
    payload: dict[str, object] = {}
    for r in RARITIES:
        val = data.get(r)
        if val in (None, ""):
            continue  # auto
        with contextlib.suppress(TypeError, ValueError):
            payload[r] = int(float(val))
    if "jitter_pct" in data:
        with contextlib.suppress(TypeError, ValueError):
            payload["jitter_pct"] = float(data["jitter_pct"])
    return ReprintKnobs.model_validate(payload)


def auto_target(rarity: str, set_size: int) -> int:
    """Auto target for a rarity: rate x the set's estimated card count at it."""
    total_w = sum(RARITY_WEIGHTS.values())
    rarity_cards = set_size * RARITY_WEIGHTS.get(rarity, 0) / total_w if total_w else 0
    return round(REPRINT_RARITY_RATES.get(rarity, 0.0) * rarity_cards)


def resolve_targets(
    knobs: ReprintKnobs,
    set_size: int,
    rng: random.Random | None = None,
) -> dict[str, int]:
    """Resolve the per-rarity reprint targets to ask the selector for.

    Pinned rarities are exact. Auto rarities derive from the rate x the rarity's
    estimated card count, then share one proportional jitter realized on the
    largest auto rarity. No slot clamp — placement is soft (plain-text slots).
    """
    rng = rng or random.Random()
    targets: dict[str, int] = {}
    auto_rarities: list[str] = []
    for r in RARITIES:
        pinned = getattr(knobs, r)
        if pinned is not None:
            targets[r] = pinned
        else:
            targets[r] = auto_target(r, set_size)
            auto_rarities.append(r)

    if auto_rarities and knobs.jitter_pct > 0:
        auto_total = sum(targets[r] for r in auto_rarities)
        amount = round(knobs.jitter_pct * auto_total)
        if amount > 0:
            delta = rng.randint(-amount, amount)
            if delta:
                pick = max(auto_rarities, key=lambda r: (targets[r], -RARITIES.index(r)))
                targets[pick] = max(0, targets[pick] + delta)
    return targets
