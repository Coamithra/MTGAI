"""Card image rendering — layout, colors, fonts, and symbol rendering.

Submodules:
    layout           — Print spec constants and bounding box definitions for card zones
    colors           — MTG color schemes for mana symbols, rarity, and frame mapping
    fonts            — Font loading and caching by role and size
    symbol_renderer  — Mana and set symbol rendering (SVG with Pillow fallback)
"""

from mtgai.rendering.colors import (
    MANA_COLORS,
    MANA_FG_COLORS,
    RARITY_COLORS,
    frame_key_for_identity,
)
from mtgai.rendering.fonts import FontManager, get_font_manager
from mtgai.rendering.layout import (
    CANVAS_H,
    CANVAS_W,
    DPI,
    FRAME_H,
    FRAME_W,
    ZONES_NATIVE,
    ZONES_PRINT,
    BoundingBox,
)
from mtgai.rendering.symbol_renderer import (
    get_mana_symbol,
    get_set_symbol,
    parse_mana_cost,
    svg_backend,
)

__all__ = [
    "CANVAS_H",
    "CANVAS_W",
    "DPI",
    "FRAME_H",
    "FRAME_W",
    "MANA_COLORS",
    "MANA_FG_COLORS",
    "RARITY_COLORS",
    "ZONES_NATIVE",
    "ZONES_PRINT",
    "BoundingBox",
    "FontManager",
    "frame_key_for_identity",
    "get_font_manager",
    "get_mana_symbol",
    "get_set_symbol",
    "parse_mana_cost",
    "svg_backend",
]
