"""MTG color schemes for card rendering.

Provides color constants for mana symbols, rarity indicators, and the mapping
from card color identity to frame image filenames.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Mana symbol colors — circle backgrounds for mana cost rendering
# ---------------------------------------------------------------------------
MANA_COLORS: dict[str, tuple[int, int, int]] = {
    "W": (248, 231, 185),  # White — pale gold
    "U": (14, 104, 171),  # Blue
    "B": (21, 11, 0),  # Black
    "R": (211, 32, 42),  # Red
    "G": (0, 115, 62),  # Green
    "C": (204, 194, 193),  # Colorless — gray
    "X": (204, 194, 193),  # Variable — gray
    "T": (204, 194, 193),  # Tap — gray
    "E": (204, 194, 193),  # Energy — gray
    "S": (204, 194, 193),  # Snow — gray
    "P": (204, 194, 193),  # Phyrexian — gray
}

# Foreground / glyph colors drawn on top of the mana circle
MANA_FG_COLORS: dict[str, tuple[int, int, int]] = {
    "W": (33, 28, 20),  # Dark on light background
    "U": (255, 255, 255),  # White on blue
    "B": (204, 194, 193),  # Light on dark background
    "R": (255, 255, 255),  # White on red
    "G": (255, 255, 255),  # White on green
    "C": (33, 28, 20),  # Dark on gray
    "X": (33, 28, 20),
    "T": (33, 28, 20),
    "E": (33, 28, 20),
    "S": (33, 28, 20),
    "P": (33, 28, 20),
}

# Generic / numeric mana uses these when the symbol code is not in the above dicts
MANA_GENERIC_BG = (204, 194, 193)
MANA_GENERIC_FG = (33, 28, 20)

# ---------------------------------------------------------------------------
# Rarity colors — for set symbol coloring and rarity indicators
# ---------------------------------------------------------------------------
RARITY_COLORS: dict[str, tuple[int, int, int]] = {
    "C": (20, 20, 20),  # Common — black
    "U": (148, 148, 148),  # Uncommon — silver
    "R": (200, 160, 0),  # Rare — gold
    "M": (200, 60, 20),  # Mythic — orange-red
}

# Rarity gradient highlight colors (brighter shade for metallic effect)
RARITY_HIGHLIGHT_COLORS: dict[str, tuple[int, int, int]] = {
    "C": (60, 60, 60),
    "U": (200, 200, 210),
    "R": (255, 220, 80),
    "M": (255, 120, 60),
}

# ---------------------------------------------------------------------------
# Set symbol filenames by rarity
# ---------------------------------------------------------------------------
RARITY_SET_SYMBOL_FILES: dict[str, str] = {
    "C": "set-symbol-common.svg",
    "U": "set-symbol-uncommon.svg",
    "R": "set-symbol-rare.svg",
    "M": "set-symbol-mythic.svg",
}

# ---------------------------------------------------------------------------
# Frame key mapping — color identity to frame filename suffix
#
# The M15 frame images are named m15Frame{KEY}.png where KEY is one of:
#   W=white, U=blue, B=black, R=red, G=green
#   M=multicolor (gold), A=artifact (gray), L=land (brown)
#   V=vehicle/colorless
#
# For lands, there are also color-specific land frames: lw, lu, lb, lr, lg, lm
# ---------------------------------------------------------------------------
COLOR_TO_FRAME_KEY: dict[str, str] = {
    "W": "W",
    "U": "U",
    "B": "B",
    "R": "R",
    "G": "G",
}

# Eldrazi / devoid frame
ELDRAZI_FRAME = "eldrazi"


def frame_key_for_identity(color_identity: list[str], is_land: bool = False) -> str:
    """Determine the frame key for a card based on its color identity.

    Args:
        color_identity: List of color codes, e.g. ["W"], ["U", "B"], [].
        is_land: Whether the card is a land (uses land-specific frames).

    Returns:
        Frame key string for use with ``layout.frame_path()``.
        Examples: "W", "M", "A", "L", "lw"
    """
    colors = sorted(set(color_identity))

    if is_land:
        if len(colors) == 0:
            return "L"
        if len(colors) == 1:
            return f"l{colors[0].lower()}"
        return "lm"  # multicolor land

    if len(colors) == 0:
        return "A"  # artifact / colorless
    if len(colors) == 1:
        return COLOR_TO_FRAME_KEY.get(colors[0], "A")
    return "M"  # multicolor (gold)


# ---------------------------------------------------------------------------
# Common rendering colors
# ---------------------------------------------------------------------------
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
DARK_GRAY = (60, 60, 60)
MID_GRAY = (120, 120, 120)
CREAM = (245, 235, 215)  # text box parchment background
