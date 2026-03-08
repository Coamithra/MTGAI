"""Set, SetSkeleton, and DraftArchetype models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from mtgai.models.card import Card
from mtgai.models.mechanic import Mechanic


class DraftArchetype(BaseModel):
    """One of the 10 two-color draft archetypes."""

    color_pair: str
    name: str
    description: str
    primary_mechanics: list[str] = Field(default_factory=list)
    signpost_uncommon: str | None = None


class SetSkeleton(BaseModel):
    """The structural backbone of a set before individual cards are generated."""

    total_cards: int
    commons: int
    uncommons: int
    rares: int
    mythics: int
    basic_lands: int
    slot_matrix: dict = Field(default_factory=dict)


class Set(BaseModel):
    """A complete MTG set."""

    name: str
    code: str
    theme: str
    description: str = ""
    cards: list[Card] = Field(default_factory=list)
    mechanics: list[Mechanic] = Field(default_factory=list)
    draft_archetypes: list[DraftArchetype] = Field(default_factory=list)
    skeleton: SetSkeleton | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    version: str = "0.1.0"
