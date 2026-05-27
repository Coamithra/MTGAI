"""Skeleton generator — builds the structural slot matrix for an MTG set."""

from mtgai.skeleton.generator import (
    BalanceReport,
    ConstraintResult,
    ReservedSlotSpec,
    SetConfig,
    SkeletonResult,
    SkeletonSlot,
    build_reserved_slots,
    generate_skeleton,
    save_skeleton,
)
from mtgai.skeleton.knobs import (
    KNOB_SPECS,
    Cycle,
    CycleSpan,
    SkeletonKnobs,
    default_knobs,
    knob_specs_payload,
)

__all__ = [
    "KNOB_SPECS",
    "BalanceReport",
    "ConstraintResult",
    "Cycle",
    "CycleSpan",
    "ReservedSlotSpec",
    "SetConfig",
    "SkeletonKnobs",
    "SkeletonResult",
    "SkeletonSlot",
    "build_reserved_slots",
    "default_knobs",
    "generate_skeleton",
    "knob_specs_payload",
    "save_skeleton",
]
