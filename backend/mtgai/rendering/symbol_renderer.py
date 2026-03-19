"""Mana and set symbol rendering for MTG cards.

Renders mana symbols (e.g. {W}, {2}, {T}) and set-rarity symbols as PIL RGBA
images at any requested pixel size, with caching.

SVG rasterization is attempted via ``cairosvg`` first; if that library or its
native ``libcairo`` dependency is unavailable (common on Windows), a Pillow
fallback draws colored circles with text labels — visually clean and
recognizable, matching MTG's standard mana symbol color scheme.

SVG assets:
    Mana symbols:  ``assets/symbols/mana/{code}.svg``  (IcoMoon glyph format)
    Set symbols:   ``assets/symbols/set-symbol-{rarity}.svg``
"""

from __future__ import annotations

import logging
import re
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from mtgai.rendering.colors import (
    MANA_COLORS,
    MANA_FG_COLORS,
    MANA_GENERIC_BG,
    MANA_GENERIC_FG,
    RARITY_COLORS,
    RARITY_HIGHLIGHT_COLORS,
    RARITY_SET_SYMBOL_FILES,
)
from mtgai.rendering.fonts import get_font_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MANA_SVG_DIR = PROJECT_ROOT / "assets" / "symbols" / "mana"
SET_SYMBOL_DIR = PROJECT_ROOT / "assets" / "symbols"

# ---------------------------------------------------------------------------
# Mana cost parsing regex
# ---------------------------------------------------------------------------
MANA_SYMBOL_RE = re.compile(r"\{([^}]+)\}")


def parse_mana_cost(mana_cost: str) -> list[str]:
    """Parse a mana cost string like ``{2}{G}{G}`` into symbol codes.

    Returns:
        List of symbol code strings, e.g. ``["2", "G", "G"]``.
    """
    return MANA_SYMBOL_RE.findall(mana_cost)


# ---------------------------------------------------------------------------
# SVG backend detection
# ---------------------------------------------------------------------------
_svg_backend: str | None = None


def _detect_svg_backend() -> str:
    """Detect whether cairosvg is available and functional.

    Returns:
        ``"cairosvg"`` if the library works, ``"fallback"`` otherwise.
    """
    global _svg_backend
    if _svg_backend is not None:
        return _svg_backend

    try:
        import cairosvg

        # Verify the native Cairo library is actually present
        cairosvg.svg2png(
            bytestring=b'<svg xmlns="http://www.w3.org/2000/svg"/>',
            output_width=1,
        )
        _svg_backend = "cairosvg"
        logger.info("SVG backend: cairosvg (native Cairo available)")
    except Exception:
        _svg_backend = "fallback"
        logger.info("SVG backend: Pillow fallback (cairosvg/libcairo not available)")

    return _svg_backend


def svg_backend() -> str:
    """Return the current SVG backend name (``"cairosvg"`` or ``"fallback"``)."""
    return _detect_svg_backend()


# ---------------------------------------------------------------------------
# SVG rasterization
# ---------------------------------------------------------------------------
def _rasterize_svg(svg_path: Path, width: int, height: int) -> Image.Image | None:
    """Rasterize an SVG file to a PIL RGBA image at the given dimensions.

    Returns ``None`` if the file doesn't exist or cairosvg isn't available.
    """
    if not svg_path.is_file():
        return None

    if _detect_svg_backend() != "cairosvg":
        return None

    try:
        import cairosvg

        png_data = cairosvg.svg2png(
            url=str(svg_path),
            output_width=width,
            output_height=height,
        )
        img = Image.open(BytesIO(png_data)).convert("RGBA")
        return img.resize((width, height), Image.LANCZOS)
    except Exception as exc:
        logger.debug("SVG rasterization failed for %s: %s", svg_path, exc)
        return None


# ---------------------------------------------------------------------------
# Mana symbol rendering
# ---------------------------------------------------------------------------
_mana_cache: dict[tuple[str, int], Image.Image] = {}


def _mana_colors(
    symbol: str,
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Return (background, foreground) color for a mana symbol code."""
    key = symbol.upper()
    bg = MANA_COLORS.get(key, MANA_GENERIC_BG)
    fg = MANA_FG_COLORS.get(key, MANA_GENERIC_FG)
    return bg, fg


def _make_fallback_mana_symbol(symbol: str, size: int) -> Image.Image:
    """Draw a colored circle with a centered text label using pure Pillow.

    This is the fallback when SVG rasterization is unavailable.
    """
    bg, fg = _mana_colors(symbol)

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Filled circle with thin outline
    margin = 1
    draw.ellipse(
        [margin, margin, size - margin - 1, size - margin - 1],
        fill=(*bg, 255),
        outline=(0, 0, 0, 180),
        width=max(1, size // 16),
    )

    # Label text
    label = symbol.upper()
    if label == "TAP":
        label = "T"
    elif label == "UNTAP":
        label = "Q"

    label_size = int(size * 0.55) if len(label) <= 2 else int(size * 0.4)
    fm = get_font_manager()
    label_font: ImageFont.FreeTypeFont | ImageFont.ImageFont = fm.get("info_bold", label_size)

    label_bbox = draw.textbbox((0, 0), label, font=label_font)
    label_w = label_bbox[2] - label_bbox[0]
    label_h = label_bbox[3] - label_bbox[1]
    label_x = (size - label_w) // 2
    # Compensate for font ascent offset
    label_y = (size - label_h) // 2 - label_bbox[1]
    draw.text((label_x, label_y), label, font=label_font, fill=(*fg, 255))

    return img


def _make_svg_mana_symbol(symbol: str, size: int) -> Image.Image | None:
    """Rasterize an SVG mana glyph and composite it onto a colored circle.

    The mana SVGs (IcoMoon format) are single-color (#444) glyph shapes.
    We rasterize the glyph, recolor it, and paste it onto a properly
    colored circular background to match MTG's standard look.

    Returns ``None`` if the SVG file doesn't exist or cairosvg isn't
    available.
    """
    svg_path = MANA_SVG_DIR / f"{symbol.lower()}.svg"
    glyph_img = _rasterize_svg(svg_path, size, size)
    if glyph_img is None:
        return None

    bg, fg = _mana_colors(symbol)

    # Create circular background
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    margin = 1
    draw.ellipse(
        [margin, margin, size - margin - 1, size - margin - 1],
        fill=(*bg, 255),
        outline=(0, 0, 0, 180),
        width=max(1, size // 16),
    )

    # Recolor the glyph: use the alpha channel from the SVG raster,
    # then create a solid-color glyph with the desired foreground color
    glyph_alpha = glyph_img.split()[3]
    colored_glyph = Image.new("RGBA", (size, size), (*fg, 255))
    colored_glyph.putalpha(glyph_alpha)

    # Shrink glyph to fit within the circle with padding
    glyph_size = int(size * 0.65)
    glyph_offset = (size - glyph_size) // 2
    colored_glyph_resized = colored_glyph.resize((glyph_size, glyph_size), Image.LANCZOS)

    canvas.paste(
        colored_glyph_resized,
        (glyph_offset, glyph_offset),
        colored_glyph_resized,
    )
    return canvas


def get_mana_symbol(symbol: str, size: int) -> Image.Image:
    """Get a rendered mana symbol image at the requested pixel size.

    Tries SVG rasterization first (via cairosvg), falls back to a clean
    Pillow-drawn colored circle with text label.

    Args:
        symbol: Mana symbol code (e.g. ``"G"``, ``"2"``, ``"T"``).
        size: Pixel dimensions (square image).

    Returns:
        RGBA PIL Image of the mana symbol.
    """
    cache_key = (symbol.upper(), size)
    if cache_key in _mana_cache:
        return _mana_cache[cache_key]

    result = _make_svg_mana_symbol(symbol, size)
    if result is None:
        result = _make_fallback_mana_symbol(symbol, size)

    _mana_cache[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# Set symbol rendering
# ---------------------------------------------------------------------------
_set_symbol_cache: dict[tuple[str, int], Image.Image] = {}


def get_set_symbol(rarity: str, size: int) -> Image.Image:
    """Get a rendered set symbol for the given rarity at the given size.

    Tries SVG rasterization first. Falls back to a Pillow-drawn hexagonal
    gem shape.

    Args:
        rarity: Single-letter rarity code (``"C"``/``"U"``/``"R"``/``"M"``).
        size: Pixel height for the symbol (output is square).

    Returns:
        RGBA PIL Image of the set symbol.
    """
    cache_key = (rarity.upper(), size)
    if cache_key in _set_symbol_cache:
        return _set_symbol_cache[cache_key]

    # Try SVG rasterization
    svg_filename = RARITY_SET_SYMBOL_FILES.get(rarity, "set-symbol-common.svg")
    svg_path = SET_SYMBOL_DIR / svg_filename
    result = _rasterize_svg(svg_path, size, size)
    if result is None:
        result = _make_fallback_set_symbol(rarity, size)

    _set_symbol_cache[cache_key] = result
    return result


def _make_fallback_set_symbol(rarity: str, size: int) -> Image.Image:
    """Draw a hexagonal gem shape approximating an MTG set symbol.

    Uses rarity-appropriate coloring with a simple gradient-like effect
    for metallic rarity tiers (uncommon/rare/mythic).
    """
    color = RARITY_COLORS.get(rarity, RARITY_COLORS["C"])
    highlight = RARITY_HIGHLIGHT_COLORS.get(rarity, color)

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = size // 2, size // 2
    r = size // 2 - 2

    # Hexagon vertices
    points = [
        (cx, cy - r),
        (cx + r, int(cy - r * 0.35)),
        (cx + r, int(cy + r * 0.45)),
        (cx, cy + r),
        (cx - r, int(cy + r * 0.45)),
        (cx - r, int(cy - r * 0.35)),
    ]

    if rarity in ("R", "M"):
        draw.polygon(points, fill=(*highlight, 255), outline=(80, 60, 0, 255))
        inner = [(int(cx + (x - cx) * 0.6), int(cy + (y - cy) * 0.6)) for x, y in points]
        draw.polygon(inner, fill=(*color, 200))
    elif rarity == "U":
        draw.polygon(points, fill=(*highlight, 255), outline=(100, 100, 100, 255))
        inner = [(int(cx + (x - cx) * 0.6), int(cy + (y - cy) * 0.6)) for x, y in points]
        draw.polygon(inner, fill=(*color, 200))
    else:
        draw.polygon(points, fill=(*color, 255), outline=(60, 60, 60, 200))

    return img


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------
def clear_caches() -> None:
    """Drop all cached symbol images."""
    _mana_cache.clear()
    _set_symbol_cache.clear()
