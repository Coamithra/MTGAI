"""Card data model — the single source of truth for card structure.

Designed for compatibility with Scryfall's data model while adding
pipeline-specific fields. Reference: https://scryfall.com/docs/api/cards
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from mtgai.models.enums import CardLayout, CardStatus, Color, Rarity


class ManaCost(BaseModel):
    """Parsed representation of a mana cost string like '{2}{W}{U}'."""

    raw: str
    cmc: float
    colors: list[Color] = Field(default_factory=list)
    generic: int = 0
    white: int = 0
    blue: int = 0
    black: int = 0
    red: int = 0
    green: int = 0
    colorless: int = 0
    x_count: int = 0


class GenerationAttempt(BaseModel):
    """Tracks a single generation or render attempt for a card."""

    attempt_number: int
    timestamp: datetime
    prompt_used: str | None = None
    model_used: str | None = None
    success: bool
    error_message: str | None = None
    validation_errors: list[str] = Field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    prompt_version: str | None = None


class CardFace(BaseModel):
    """For double-faced, split, or adventure cards.

    Each face has its own name, mana cost, type line, etc.
    Mirrors Scryfall's card_faces structure.
    """

    name: str
    mana_cost: str | None = None
    type_line: str
    oracle_text: str = ""
    flavor_text: str | None = None
    power: str | None = None
    toughness: str | None = None
    loyalty: str | None = None
    colors: list[Color] = Field(default_factory=list)
    art_path: str | None = None
    art_prompt: str | None = None


class Card(BaseModel):
    """Full card data model.

    Scryfall-compatible field names where applicable, plus pipeline fields.
    """

    # === Identity ===
    id: str | None = None
    name: str
    layout: CardLayout = CardLayout.NORMAL

    # === Mana & Colors ===
    mana_cost: str | None = None
    mana_cost_parsed: ManaCost | None = None
    cmc: float = 0.0
    colors: list[Color] = Field(default_factory=list)
    color_identity: list[Color] = Field(default_factory=list)

    # === Typeline ===
    type_line: str
    supertypes: list[str] = Field(default_factory=list)
    card_types: list[str] = Field(default_factory=list)
    subtypes: list[str] = Field(default_factory=list)

    # === Rules & Flavor ===
    oracle_text: str = ""
    flavor_text: str | None = None
    reminder_text: str | None = None

    # === Stats ===
    power: str | None = None
    toughness: str | None = None
    loyalty: str | None = None

    # === Set & Collector Info ===
    collector_number: str = ""
    rarity: Rarity = Rarity.COMMON
    set_code: str = ""
    artist: str = "AI Generated"

    # === Pipeline State ===
    status: CardStatus = CardStatus.DRAFT
    generation_attempts: list[GenerationAttempt] = Field(default_factory=list)
    art_generation_attempts: list[GenerationAttempt] = Field(default_factory=list)
    render_attempts: list[GenerationAttempt] = Field(default_factory=list)

    # === File Paths (relative to output/sets/<set-code>/) ===
    art_path: str | None = None
    render_path: str | None = None
    art_prompt: str | None = None

    # === Design Metadata ===
    design_notes: str | None = None
    is_reprint: bool = False
    scryfall_id: str | None = None
    draft_archetype: str | None = None
    mechanic_tags: list[str] = Field(default_factory=list)
    slot_id: str | None = None

    # === Double-Faced / Multi-Face ===
    card_faces: list[CardFace] | None = None

    # === Timestamps ===
    created_at: datetime | None = None
    updated_at: datetime | None = None
