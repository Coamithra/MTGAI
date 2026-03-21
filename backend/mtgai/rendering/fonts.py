"""Font loading and caching for card rendering.

Loads TrueType fonts from the project's ``assets/fonts/`` directory by role
(name, body, body_italic, info) and pixel size, with a per-instance LRU cache
so each (role, size) combination is loaded only once.

Font roles:
    name         — Cinzel (decorative serif) for card names and type lines
    body         — EB Garamond (elegant serif) for rules text
    body_italic  — EB Garamond Italic for flavor text and reminder text
    info         — Montserrat (clean sans-serif) for P/T, collector info, mana labels

All font sizes are in **pixels** (at 300 DPI, 1 pt ~ 4.17 px).
"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import ImageFont

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Project root — 4 levels up: rendering/ -> mtgai/ -> backend/ -> PROJECT_ROOT
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
FONTS_DIR = PROJECT_ROOT / "assets" / "fonts"

# ---------------------------------------------------------------------------
# Font file paths — project assets with Windows system-font fallbacks
# ---------------------------------------------------------------------------
# Real MTG fonts: Beleren Bold (names/types), MPlantin (rules), Relay Medium (info)
# Fallback chain: MTG font → previous project font → Windows system font
FONT_PATHS: dict[str, list[Path]] = {
    "name": [
        FONTS_DIR / "beleren" / "beleren2016-bold.ttf",
        FONTS_DIR / "beleren" / "beleren-bold.ttf",
        FONTS_DIR / "cinzel" / "Cinzel-Variable.ttf",
        Path("C:/Windows/Fonts/arialbd.ttf"),
    ],
    "name_sc": [
        FONTS_DIR / "beleren" / "beleren2016-smallcaps-bold.ttf",
        FONTS_DIR / "beleren" / "belerensmallcaps-bold.ttf",
        Path("C:/Windows/Fonts/arialbd.ttf"),
    ],
    "body": [
        FONTS_DIR / "mplantin" / "mplantin.ttf",
        FONTS_DIR / "eb-garamond" / "EBGaramond-Variable.ttf",
        Path("C:/Windows/Fonts/georgia.ttf"),
    ],
    "body_italic": [
        FONTS_DIR / "mplantin" / "mplantin-italic.ttf",
        FONTS_DIR / "eb-garamond" / "EBGaramond-Italic-Variable.ttf",
        Path("C:/Windows/Fonts/georgiai.ttf"),
    ],
    "body_bold": [
        FONTS_DIR / "mplantin" / "mplantin-bold.ttf",
        FONTS_DIR / "eb-garamond" / "EBGaramond-Variable.ttf",
        Path("C:/Windows/Fonts/georgiab.ttf"),
    ],
    "info": [
        FONTS_DIR / "relay" / "relay-medium.ttf",
        FONTS_DIR / "montserrat" / "Montserrat-Variable.ttf",
        Path("C:/Windows/Fonts/arial.ttf"),
    ],
    "info_bold": [
        FONTS_DIR / "relay" / "relay-medium.ttf",
        FONTS_DIR / "montserrat" / "Montserrat-Variable.ttf",
        Path("C:/Windows/Fonts/arialbd.ttf"),
    ],
}

# Supported role names (for validation)
FONT_ROLES = frozenset(FONT_PATHS.keys())

# Variable font weight axis values per role (None = use default)
# Beleren Bold and MPlantin Bold are already bold, no axis needed.
FONT_WEIGHTS: dict[str, int | None] = {
    "name": None,  # Beleren Bold is already bold weight
    "name_sc": None,  # Beleren Small Caps Bold
    "body": None,  # MPlantin Regular
    "body_italic": None,  # MPlantin Italic
    "body_bold": None,  # MPlantin Bold (separate file)
    "info": None,  # Relay Medium
    "info_bold": None,  # Relay Medium (already medium weight)
}

# ---------------------------------------------------------------------------
# Default font sizes (pixels) for each rendering purpose
#
# At 300 DPI: 28px ~ 6.7pt, 21px ~ 5pt, 14px ~ 3.4pt
# These are for the print-resolution canvas (822x1122).
# For native resolution (2010x2814), multiply by ~2.45.
# ---------------------------------------------------------------------------
DEFAULT_SIZES: dict[str, int] = {
    "card_name": 44,  # 3.81% of card height (Card Conjurer reference)
    "mana_cost": 36,
    "type_line": 37,  # 3.24% of card height
    "rules_text": 40,  # 3.52% of card height
    "rules_bold": 40,
    "flavor_text": 38,
    "pt_text": 42,  # 3.71% of card height
    "collector": 22,
    "mana_label": 24,
}


# ---------------------------------------------------------------------------
# FontManager — loads and caches TrueType fonts by (role, size)
# ---------------------------------------------------------------------------
class FontManager:
    """Font loader with per-instance cache.

    Usage::

        fm = FontManager()
        name_font = fm.get("name", 28)
        body_font = fm.get("body", 21)

    Fonts are loaded once per (role, size) pair and cached for the lifetime
    of the FontManager instance.
    """

    def __init__(self) -> None:
        self._cache: dict[tuple[str, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
        self._resolved_paths: dict[str, Path | None] = {}

    def _resolve_path(self, role: str) -> Path | None:
        """Find the first existing font file for the given role."""
        if role in self._resolved_paths:
            return self._resolved_paths[role]

        candidates = FONT_PATHS.get(role, [])
        for p in candidates:
            if p.is_file():
                self._resolved_paths[role] = p
                return p

        self._resolved_paths[role] = None
        return None

    def get(
        self,
        role: str,
        size: int,
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """Load a font for the given role at the given pixel size.

        Args:
            role: Font role key — one of ``name``, ``body``, ``body_italic``,
                  ``body_bold``, ``info``, ``info_bold``.
            size: Font size in pixels (not points).

        Returns:
            A PIL FreeTypeFont, or the Pillow default bitmap font as a last resort.
        """
        cache_key = (role, size)
        if cache_key in self._cache:
            return self._cache[cache_key]

        font_path = self._resolve_path(role)
        if font_path is not None:
            try:
                font = ImageFont.truetype(str(font_path), size)
                # Apply variable font weight if specified
                weight = FONT_WEIGHTS.get(role)
                if weight is not None:
                    import contextlib

                    with contextlib.suppress(Exception):
                        font.set_variation_by_axes([weight])
                self._cache[cache_key] = font
                return font
            except OSError as exc:
                logger.warning(
                    "Failed to load %s at size %d from %s: %s",
                    role,
                    size,
                    font_path,
                    exc,
                )

        logger.warning(
            "No TrueType font found for role '%s' — using Pillow default bitmap font.", role
        )
        fallback = ImageFont.load_default()
        self._cache[cache_key] = fallback
        return fallback

    def get_card_fonts(self) -> dict[str, ImageFont.FreeTypeFont | ImageFont.ImageFont]:
        """Load a complete set of fonts for card rendering at default sizes.

        Returns a dict keyed by purpose (``card_name``, ``mana_cost``, etc.)
        matching the keys in ``DEFAULT_SIZES``.
        """
        role_map: dict[str, str] = {
            "card_name": "name",
            "mana_cost": "info_bold",
            "type_line": "name",
            "rules_text": "body",
            "rules_bold": "body_bold",
            "flavor_text": "body_italic",
            "pt_text": "info_bold",
            "collector": "info",
            "mana_label": "info_bold",
        }
        return {
            purpose: self.get(role, DEFAULT_SIZES[purpose]) for purpose, role in role_map.items()
        }

    def info(self) -> dict[str, str]:
        """Return a diagnostic dict mapping role -> resolved font file path."""
        result: dict[str, str] = {}
        for role in FONT_PATHS:
            p = self._resolve_path(role)
            result[role] = str(p) if p else "(not found — Pillow default)"
        return result

    def clear_cache(self) -> None:
        """Drop all cached font objects (useful after DPI or scale changes)."""
        self._cache.clear()
        self._resolved_paths.clear()


# ---------------------------------------------------------------------------
# Module-level singleton for convenience
# ---------------------------------------------------------------------------
_default_manager: FontManager | None = None


def get_font_manager() -> FontManager:
    """Return the module-level singleton FontManager (created on first call)."""
    global _default_manager
    if _default_manager is None:
        _default_manager = FontManager()
    return _default_manager
