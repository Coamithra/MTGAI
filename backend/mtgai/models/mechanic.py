"""Mechanic model for set-specific keyword and ability mechanics."""

from pydantic import BaseModel, Field

from mtgai.models.enums import Color, Rarity


class Mechanic(BaseModel):
    """A set-specific keyword or ability mechanic."""

    name: str
    keyword_type: str  # "keyword_ability", "ability_word", "keyword_action"
    reminder_text: str
    rules_template: str = ""
    description: str = ""
    colors: list[Color] = Field(default_factory=list)
    allowed_rarities: list[Rarity] = Field(default_factory=list)
    card_type_affinity: list[str] = Field(default_factory=list)
    is_evergreen: bool = False
    example_cards: list[str] = Field(default_factory=list)
    design_notes: str | None = None
    complexity: int = 1
    flavor_connection: str = ""
    common_patterns: list[str] = Field(default_factory=list)
    uncommon_patterns: list[str] = Field(default_factory=list)
    rare_patterns: list[str] = Field(default_factory=list)
    distribution: dict[str, int] = Field(default_factory=dict)  # rarity -> count
