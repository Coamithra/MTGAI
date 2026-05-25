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

__all__ = [
    "BalanceReport",
    "ConstraintResult",
    "ReservedSlotSpec",
    "SetConfig",
    "SkeletonResult",
    "SkeletonSlot",
    "build_reserved_slots",
    "generate_skeleton",
    "save_skeleton",
]
