"""Card data model — the single source of truth for card structure.

Designed for compatibility with Scryfall's data model while adding
pipeline-specific fields. Reference: https://scryfall.com/docs/api/cards
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

from mtgai.models.enums import CardLayout, CardStatus, Color, Rarity


def _normalize_colors(value: object) -> object:
    """Coerce each entry of a color list to a canonical WUBRG ``Color``.

    Accepts the Scryfall-canonical letter (``"U"``) AND the full color name
    (``"blue"`` / ``"White"``, case-insensitive), normalizing every entry to the
    letter form so name-form colors persisted out-of-band can never mis-group
    downstream (e.g. ``"blue"`` collapsing to the Black ``"B"`` key in the UI).
    A non-list value is returned untouched for Pydantic to reject normally.
    """
    if not isinstance(value, (list, tuple)):
        return value
    out: list = []
    for item in value:
        # Colorless tokens ('C', 'Colorless') denote the ABSENCE of color; the
        # canonical form is an empty list, so drop them rather than raising —
        # local models sometimes emit ['C']/['Colorless'] for a colorless card.
        if isinstance(item, str) and item.strip().lower() in ("c", "colorless"):
            continue
        out.append(Color.coerce(item))
    return out


# ``list[Color]`` that also accepts full color names, normalizing to WUBRG letters.
ColorList = Annotated[list[Color], BeforeValidator(_normalize_colors)]


def _coerce_optional_str(value: object) -> object:
    """Coerce loosely-typed values to ``str`` for optional text / stat fields.

    Local models occasionally emit ``power``/``toughness`` as ints or
    ``flavor_text`` as a list of lines; normalize so the strict schema accepts
    them instead of crashing a downstream strict load (e.g. finalize). ``None``
    and ``str`` pass through unchanged.
    """
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):  # avoid bool->"True"/"False" surprises
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "\n".join(str(v) for v in value)
    return value


# ``str | None`` that also accepts ints (stats) and lists-of-lines (flavor text).
OptionalStr = Annotated[str | None, BeforeValidator(_coerce_optional_str)]


class ManaCost(BaseModel):
    """Parsed representation of a mana cost string like '{2}{W}{U}'."""

    raw: str
    cmc: float
    colors: ColorList = Field(default_factory=list)
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
    flavor_text: OptionalStr = None
    power: OptionalStr = None
    toughness: OptionalStr = None
    loyalty: OptionalStr = None
    colors: ColorList = Field(default_factory=list)
    art_path: str | None = None
    art_prompt: str | None = None


class ArtCharacterRef(BaseModel):
    """A structured reference-image attachment for a recurring entity.

    Written by the Character References stage (``char_portraits``) onto every
    card that features a named character / location / element appearing on more
    than one card, and read by the Art Generation stage (``art_gen``) to feed
    PuLID / IP-Adapter (Flux) or provider reference-conditioning. Replaces the
    old scan-at-render-time ``get_character_ref_paths`` approach with an explicit
    produced artifact. ``entity_key`` is the slug key into the art-direction
    dictionary; ``ref_image_path`` is repo-relative (under the asset folder).
    """

    entity_key: str
    ref_image_path: str


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
    colors: ColorList = Field(default_factory=list)
    color_identity: ColorList = Field(default_factory=list)

    # === Typeline ===
    type_line: str
    supertypes: list[str] = Field(default_factory=list)
    card_types: list[str] = Field(default_factory=list)
    subtypes: list[str] = Field(default_factory=list)

    # === Rules & Flavor ===
    oracle_text: str = ""
    flavor_text: OptionalStr = None
    reminder_text: str | None = None

    # === Stats ===
    power: OptionalStr = None
    toughness: OptionalStr = None
    loyalty: OptionalStr = None

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
    # Review→regen loop flags. A gate stage (conformance / interactions /
    # design review) sets these on a card it can't accept; ``card_gen`` treats a
    # slot whose card has ``regen_reason`` as needing regeneration, threads the
    # reason into the retry prompt, then clears both on a successful new card.
    # Persisted + gallery-visible so the flag survives restarts.
    regen_reason: str | None = None
    flagged_by: str | None = None  # which gate flagged it: conformance|balance|ai_review
    # Finalize sanity-check exclusion. The terminal sanity gate (review/sanity_check.py)
    # soft-excludes a card with an obvious defect (missing P/T, garbled text, bogus mana
    # symbol) it can't auto-fix: the card stays on disk but is marked here so the
    # Finalization tab shows it darkened (with the reason + an Undo) and every downstream
    # art/render stage skips it. Reversible — clearing both fields restores the card.
    sanity_excluded: bool = False
    sanity_exclusion_reason: str | None = None

    # === File Paths (relative to output/sets/<set-code>/) ===
    art_path: str | None = None
    render_path: str | None = None
    art_prompt: str | None = None
    # Reference-image attachments for recurring entities, written by the
    # Character References stage and consumed by Art Generation (PuLID/IP-Adapter
    # / provider reference-conditioning). Empty for cards with no recurring entity.
    art_character_refs: list[ArtCharacterRef] = Field(default_factory=list)

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
