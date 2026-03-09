"""
Card Rendering Prototype — Pillow-based approach with real fonts and mana symbols.

Renders a test card ("Thornwood Guardian") to validate:
- Card canvas at MPC spec (822 x 1122 px, 300 DPI)
- Colored frame rectangles approximating an MTG card layout
- Text rendering with word-wrap, bold, italic, different sizes
- Placeholder art area (green gradient — real art comes later)
- Inline mana symbol images (SVG rasterized or fallback circles)
- Set symbol in type bar
- P/T box, collector info

This is a PROTOTYPE for feasibility testing — not the final renderer.

Run from the project root:
    python research/proof-of-concept/render_prototype.py
"""

from __future__ import annotations

import os
import re
import textwrap
import time
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Project root — 2 levels up from this script
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Constants — MPC print spec
# ---------------------------------------------------------------------------
CANVAS_W = 822  # px at 300 DPI (63.5mm + 3mm bleed each side)
CANVAS_H = 1122  # px at 300 DPI (88.9mm + 3mm bleed each side)
DPI = 300
BLEED = 36  # 3mm bleed in px at 300 DPI
BORDER = 12  # visible card border thickness in px (inside bleed)

# Derived safe content area (inside bleed + border)
CONTENT_LEFT = BLEED + BORDER  # 48
CONTENT_TOP = BLEED + BORDER  # 48
CONTENT_RIGHT = CANVAS_W - BLEED - BORDER  # 774
CONTENT_BOTTOM = CANVAS_H - BLEED - BORDER  # 1074
CONTENT_W = CONTENT_RIGHT - CONTENT_LEFT  # 726
CONTENT_H = CONTENT_BOTTOM - CONTENT_TOP  # 1026

# ---------------------------------------------------------------------------
# Layout — pixel positions of card elements (relative to canvas origin)
# These approximate a standard MTG card layout.
# ---------------------------------------------------------------------------

# Name bar: top strip overlapping top of art box
NAME_BAR = {
    "left": CONTENT_LEFT + 6,
    "top": CONTENT_TOP + 6,
    "right": CONTENT_RIGHT - 6,
    "bottom": CONTENT_TOP + 56,
}

# Art box: below name bar
ART_BOX = {
    "left": CONTENT_LEFT + 18,
    "top": NAME_BAR["bottom"] + 4,
    "right": CONTENT_RIGHT - 18,
    "bottom": NAME_BAR["bottom"] + 4 + 478,  # ~478px tall
}

# Type line bar: below art box
TYPE_BAR = {
    "left": CONTENT_LEFT + 6,
    "top": ART_BOX["bottom"] + 6,
    "right": CONTENT_RIGHT - 6,
    "bottom": ART_BOX["bottom"] + 56,
}

# Text box: below type bar
TEXT_BOX = {
    "left": CONTENT_LEFT + 18,
    "top": TYPE_BAR["bottom"] + 6,
    "right": CONTENT_RIGHT - 18,
    "bottom": CONTENT_BOTTOM - 70,  # leave room for collector info and P/T
}

# P/T box: bottom-right corner of text box area
PT_BOX = {
    "left": CONTENT_RIGHT - 100,
    "top": TEXT_BOX["bottom"] - 4,
    "right": CONTENT_RIGHT - 10,
    "bottom": TEXT_BOX["bottom"] + 42,
}

# Collector info bar: very bottom
COLLECTOR_BAR = {
    "left": CONTENT_LEFT + 6,
    "top": CONTENT_BOTTOM - 44,
    "right": CONTENT_RIGHT - 6,
    "bottom": CONTENT_BOTTOM - 6,
}

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
GREEN_DARK = (30, 80, 30)
GREEN_FRAME = (50, 120, 50)
GREEN_BORDER = (25, 70, 25)
GREEN_LIGHT = (90, 160, 90)
GREEN_ART_PLACEHOLDER = (60, 140, 60)
CREAM = (245, 235, 215)  # text box background (parchment)
NAME_BAR_BG = (200, 215, 190)
TYPE_BAR_BG = (200, 215, 190)
PT_BG = (210, 200, 180)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
DARK_GRAY = (60, 60, 60)
MID_GRAY = (120, 120, 120)

# Mana symbol background colors (MTG standard circle colors)
MANA_COLORS: dict[str, tuple[int, int, int]] = {
    "W": (248, 231, 185),  # White — pale gold
    "U": (14, 104, 171),   # Blue
    "B": (21, 11, 0),      # Black
    "R": (211, 32, 42),    # Red
    "G": (0, 115, 62),     # Green
    "C": (204, 194, 193),  # Colorless — gray
    "X": (204, 194, 193),  # Variable — gray
    "T": (204, 194, 193),  # Tap — gray
    "E": (204, 194, 193),  # Energy — gray
}
# Foreground (glyph) colors for mana symbols
MANA_FG_COLORS: dict[str, tuple[int, int, int]] = {
    "W": (33, 28, 20),     # Dark on light background
    "U": (255, 255, 255),  # White on blue
    "B": (204, 194, 193),  # Light on dark background
    "R": (255, 255, 255),  # White on red
    "G": (255, 255, 255),  # White on green
    "C": (33, 28, 20),     # Dark on gray
    "X": (33, 28, 20),
    "T": (33, 28, 20),
    "E": (33, 28, 20),
}
# Generic/numeric mana uses gray background with dark text
MANA_GENERIC_BG = (204, 194, 193)
MANA_GENERIC_FG = (33, 28, 20)

# ---------------------------------------------------------------------------
# Test card data
# ---------------------------------------------------------------------------
CARD = {
    "name": "Thornwood Guardian",
    "mana_cost": "{2}{G}{G}",
    "type_line": "Creature \u2014 Treefolk Warrior",  # em-dash
    "rules_text": "Vigilance\nThornwood Guardian gets +1/+1 for each Forest you control.",
    "flavor_text": "\u201cThe forest does not forget those who walk beneath its canopy.\u201d",
    "power": "2",
    "toughness": "4",
    "rarity": "U",
    "set_code": "TST",
    "collector_number": "001",
    "collector_total": "001",
}

# ---------------------------------------------------------------------------
# Font loading helper
# ---------------------------------------------------------------------------

# Font paths — project assets with system font fallbacks.
FONT_SEARCH_PATHS: dict[str, list[str]] = {
    "name": [
        # Cinzel — decorative serif for card names and type lines
        str(PROJECT_ROOT / "assets" / "fonts" / "cinzel" / "Cinzel-Variable.ttf"),
        "C:/Windows/Fonts/arialbd.ttf",
    ],
    "body": [
        # EB Garamond — elegant serif for rules text
        str(PROJECT_ROOT / "assets" / "fonts" / "eb-garamond" / "EBGaramond-Variable.ttf"),
        "C:/Windows/Fonts/georgia.ttf",
    ],
    "body_italic": [
        # EB Garamond Italic — for flavor text
        str(
            PROJECT_ROOT / "assets" / "fonts" / "eb-garamond" / "EBGaramond-Italic-Variable.ttf"
        ),
        "C:/Windows/Fonts/georgiai.ttf",
    ],
    "body_bold": [
        # EB Garamond at higher weight — for keyword abilities
        str(PROJECT_ROOT / "assets" / "fonts" / "eb-garamond" / "EBGaramond-Variable.ttf"),
        "C:/Windows/Fonts/georgiab.ttf",
    ],
    "info": [
        # Montserrat — clean sans-serif for P/T and collector info
        str(PROJECT_ROOT / "assets" / "fonts" / "montserrat" / "Montserrat-Variable.ttf"),
        "C:/Windows/Fonts/arial.ttf",
    ],
    "info_bold": [
        # Montserrat bold weight — for P/T numbers and mana cost text fallback
        str(PROJECT_ROOT / "assets" / "fonts" / "montserrat" / "Montserrat-Variable.ttf"),
        "C:/Windows/Fonts/arialbd.ttf",
    ],
}


def load_font(role: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a font for the given role at the given pixel size.

    Tries project assets, then system fonts, then falls back to Pillow default.
    """
    for path in FONT_SEARCH_PATHS.get(role, []):
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                continue
    # Fallback — Pillow's built-in bitmap font (very small, low quality)
    print(f"  WARNING: No TrueType font found for role '{role}', using Pillow default.")
    return ImageFont.load_default()


def load_fonts() -> dict[str, ImageFont.FreeTypeFont | ImageFont.ImageFont]:
    """Load all fonts needed for rendering. Returns a dict keyed by role."""
    fonts = {
        "name": load_font("name", 28),
        "mana_cost": load_font("info_bold", 22),
        "type_line": load_font("name", 22),
        "rules": load_font("body", 21),
        "rules_bold": load_font("body_bold", 21),
        "flavor": load_font("body_italic", 19),
        "pt": load_font("info_bold", 30),
        "collector": load_font("info", 14),
        # Small font for mana symbol fallback labels
        "mana_label": load_font("info_bold", 16),
    }
    font_sources: dict[str, str] = {}
    for role, paths in FONT_SEARCH_PATHS.items():
        for p in paths:
            if os.path.isfile(p):
                font_sources[role] = p
                break
        else:
            font_sources[role] = "(Pillow default)"
    print("Fonts loaded:")
    for role, src in font_sources.items():
        print(f"  {role:15s} -> {src}")
    return fonts


# ---------------------------------------------------------------------------
# SVG rasterization — try cairosvg, fall back to Pillow-only
# ---------------------------------------------------------------------------

_svg_backend: str | None = None


def _detect_svg_backend() -> str:
    """Detect which SVG rasterization backend is available."""
    global _svg_backend
    if _svg_backend is not None:
        return _svg_backend

    try:
        import cairosvg  # noqa: F401

        # Verify it can actually work (Cairo native lib must be present)
        cairosvg.svg2png(bytestring=b'<svg xmlns="http://www.w3.org/2000/svg"/>', output_width=1)
        _svg_backend = "cairosvg"
    except Exception:
        _svg_backend = "fallback"

    return _svg_backend


def rasterize_svg(svg_path: str | Path, width: int, height: int) -> Image.Image | None:
    """Rasterize an SVG file to a PIL RGBA Image at the given dimensions.

    Uses cairosvg if available, otherwise returns None (caller should use fallback).
    """
    svg_path = Path(svg_path)
    if not svg_path.is_file():
        return None

    backend = _detect_svg_backend()

    if backend == "cairosvg":
        try:
            import cairosvg

            png_data = cairosvg.svg2png(
                url=str(svg_path), output_width=width, output_height=height
            )
            img = Image.open(BytesIO(png_data)).convert("RGBA")
            return img.resize((width, height), Image.LANCZOS)
        except Exception:
            return None

    return None


# ---------------------------------------------------------------------------
# Mana symbol rendering
# ---------------------------------------------------------------------------

# Regex to parse mana cost strings like "{2}{G}{G}" or rules text like "{T}: ..."
MANA_SYMBOL_RE = re.compile(r"\{([^}]+)\}")

# Cache for rendered mana symbols at various sizes
_mana_symbol_cache: dict[tuple[str, int], Image.Image] = {}


def _make_fallback_mana_symbol(symbol: str, size: int) -> Image.Image:
    """Create a colored circle mana symbol with a text label using Pillow only.

    This is the fallback when SVG rasterization is unavailable. Produces clean,
    recognizable mana symbols with proper MTG coloring.
    """
    # Determine colors
    sym_upper = symbol.upper()
    if sym_upper in MANA_COLORS:
        bg_color = MANA_COLORS[sym_upper]
        fg_color = MANA_FG_COLORS.get(sym_upper, MANA_GENERIC_FG)
    else:
        # Numeric or unknown — gray background
        bg_color = MANA_GENERIC_BG
        fg_color = MANA_GENERIC_FG

    # Create RGBA image with transparent background
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw filled circle with slight border
    margin = 1
    # Circle background
    draw.ellipse(
        [margin, margin, size - margin - 1, size - margin - 1],
        fill=bg_color + (255,),
        outline=(0, 0, 0, 180),
        width=max(1, size // 16),
    )

    # Draw the symbol label centered in the circle
    # Use a font sized to fit nicely inside the circle
    label = sym_upper
    # Tap symbol gets a special label
    if label == "TAP":
        label = "T"
    elif label == "UNTAP":
        label = "Q"

    label_size = int(size * 0.55) if len(label) <= 2 else int(size * 0.4)
    try:
        # Try to load a decent font for the label
        for path in FONT_SEARCH_PATHS.get("info_bold", []):
            if os.path.isfile(path):
                label_font = ImageFont.truetype(path, label_size)
                break
        else:
            label_font = ImageFont.load_default()
    except Exception:
        label_font = ImageFont.load_default()

    label_bbox = draw.textbbox((0, 0), label, font=label_font)
    label_w = label_bbox[2] - label_bbox[0]
    label_h = label_bbox[3] - label_bbox[1]
    label_x = (size - label_w) // 2
    label_y = (size - label_h) // 2 - label_bbox[1]  # compensate for font ascent offset
    draw.text((label_x, label_y), label, font=label_font, fill=fg_color + (255,))

    return img


def _make_svg_mana_symbol(symbol: str, size: int) -> Image.Image | None:
    """Try to rasterize an SVG mana symbol and composite it onto a colored circle.

    The mana SVGs from assets/symbols/mana/ are single-color glyph shapes
    (IcoMoon format). We rasterize the glyph and composite it onto a properly
    colored circular background to match MTG's look.
    """
    sym_lower = symbol.lower()
    svg_path = PROJECT_ROOT / "assets" / "symbols" / "mana" / f"{sym_lower}.svg"

    if not svg_path.is_file():
        return None

    # Rasterize the SVG glyph
    glyph_img = rasterize_svg(svg_path, size, size)
    if glyph_img is None:
        return None

    # Determine colors
    sym_upper = symbol.upper()
    if sym_upper in MANA_COLORS:
        bg_color = MANA_COLORS[sym_upper]
        fg_color = MANA_FG_COLORS.get(sym_upper, MANA_GENERIC_FG)
    else:
        bg_color = MANA_GENERIC_BG
        fg_color = MANA_GENERIC_FG

    # Create circular background
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    margin = 1
    draw.ellipse(
        [margin, margin, size - margin - 1, size - margin - 1],
        fill=bg_color + (255,),
        outline=(0, 0, 0, 180),
        width=max(1, size // 16),
    )

    # The SVG glyphs are filled with #444. We need to recolor them.
    # Extract the alpha channel from the rasterized glyph, then create
    # a solid-color version of the glyph with the desired foreground color.
    glyph_alpha = glyph_img.split()[3]  # alpha channel

    # Also use the RGB brightness as additional alpha info (the glyphs are #444 on transparent)
    # For the IcoMoon glyphs, the filled pixels have alpha > 0
    colored_glyph = Image.new("RGBA", (size, size), fg_color + (255,))
    colored_glyph.putalpha(glyph_alpha)

    # Shrink the glyph slightly to fit within the circle with padding
    glyph_size = int(size * 0.65)
    glyph_offset = (size - glyph_size) // 2
    colored_glyph_resized = colored_glyph.resize((glyph_size, glyph_size), Image.LANCZOS)

    # Paste the colored glyph centered on the circle
    canvas.paste(
        colored_glyph_resized,
        (glyph_offset, glyph_offset),
        colored_glyph_resized,
    )

    return canvas


def get_mana_symbol(symbol: str, size: int) -> Image.Image:
    """Get a rendered mana symbol image at the requested size.

    Tries SVG rasterization first (via cairosvg), falls back to a clean
    Pillow-drawn colored circle with text label.

    Args:
        symbol: The mana symbol code (e.g., "G", "2", "T", "X").
        size: Pixel dimensions (square) for the symbol.

    Returns:
        RGBA PIL Image of the mana symbol.
    """
    cache_key = (symbol.upper(), size)
    if cache_key in _mana_symbol_cache:
        return _mana_symbol_cache[cache_key]

    # Try SVG first
    result = _make_svg_mana_symbol(symbol, size)
    if result is None:
        # Use fallback colored circle with text
        result = _make_fallback_mana_symbol(symbol, size)

    _mana_symbol_cache[cache_key] = result
    return result


def parse_mana_symbols(mana_cost: str) -> list[str]:
    """Parse a mana cost string like '{2}{G}{G}' into symbol codes ['2', 'G', 'G']."""
    return MANA_SYMBOL_RE.findall(mana_cost)


# ---------------------------------------------------------------------------
# Set symbol rendering
# ---------------------------------------------------------------------------

RARITY_TO_SET_SYMBOL: dict[str, str] = {
    "C": "set-symbol-common.svg",
    "U": "set-symbol-uncommon.svg",
    "R": "set-symbol-rare.svg",
    "M": "set-symbol-mythic.svg",
}

# Rarity fallback colors (used when SVG rasterization unavailable)
RARITY_COLORS: dict[str, tuple[int, int, int]] = {
    "C": (20, 20, 20),       # Common — black
    "U": (148, 148, 148),    # Uncommon — silver
    "R": (200, 160, 0),      # Rare — gold
    "M": (200, 60, 20),      # Mythic — orange-red
}


def get_set_symbol(rarity: str, size: int) -> Image.Image:
    """Get a rendered set symbol for the given rarity at the given size.

    Tries SVG rasterization first, falls back to a simple geometric shape.

    Args:
        rarity: Single-letter rarity code ("C", "U", "R", "M").
        size: Pixel height for the symbol.

    Returns:
        RGBA PIL Image of the set symbol.
    """
    # Try SVG rasterization
    svg_filename = RARITY_TO_SET_SYMBOL.get(rarity, "set-symbol-common.svg")
    svg_path = PROJECT_ROOT / "assets" / "symbols" / svg_filename
    result = rasterize_svg(svg_path, size, size)
    if result is not None:
        return result

    # Fallback — draw a simple hexagonal gem shape (approximating MTG set symbols)
    color = RARITY_COLORS.get(rarity, RARITY_COLORS["C"])
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw a hexagon shape similar to the SVG set symbols
    cx, cy = size // 2, size // 2
    r = size // 2 - 2  # radius with slight margin
    # Hexagon points: top, upper-right, lower-right, bottom, lower-left, upper-left
    points = [
        (cx, cy - r),                           # top
        (cx + r, int(cy - r * 0.35)),            # upper right
        (cx + r, int(cy + r * 0.45)),            # lower right
        (cx, cy + r),                            # bottom
        (cx - r, int(cy + r * 0.45)),            # lower left
        (cx - r, int(cy - r * 0.35)),            # upper left
    ]

    # For uncommon/rare/mythic, add a gradient-like effect with two shades
    if rarity in ("R", "M"):
        # Brighter version
        bright = tuple(min(255, c + 60) for c in color)
        draw.polygon(points, fill=bright + (255,), outline=(80, 60, 0, 255))
        # Draw inner highlight
        inner_points = [(int(cx + (x - cx) * 0.6), int(cy + (y - cy) * 0.6)) for x, y in points]
        draw.polygon(inner_points, fill=color + (200,))
    elif rarity == "U":
        bright = tuple(min(255, c + 40) for c in color)
        draw.polygon(points, fill=bright + (255,), outline=(100, 100, 100, 255))
        inner_points = [(int(cx + (x - cx) * 0.6), int(cy + (y - cy) * 0.6)) for x, y in points]
        draw.polygon(inner_points, fill=color + (200,))
    else:
        draw.polygon(points, fill=color + (255,), outline=(60, 60, 60, 200))

    return img


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------


def draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    bbox: dict[str, int],
    radius: int,
    fill: tuple[int, int, int],
    outline: tuple[int, int, int] | None = None,
    outline_width: int = 1,
) -> None:
    """Draw a rounded rectangle from a bbox dict with keys left/top/right/bottom."""
    draw.rounded_rectangle(
        [bbox["left"], bbox["top"], bbox["right"], bbox["bottom"]],
        radius=radius,
        fill=fill,
        outline=outline,
        width=outline_width,
    )


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels using the given font.

    Uses binary search on character count with textwrap for word boundaries.
    """
    # Start with an estimate based on average char width
    avg_char_w = font.getlength("n")
    if avg_char_w <= 0:
        avg_char_w = 8
    chars_per_line = max(1, int(max_width / avg_char_w))

    # Iteratively adjust — decrease chars_per_line until all lines fit
    for attempt in range(20):
        wrapped = textwrap.fill(text, width=chars_per_line)
        lines = wrapped.split("\n")
        max_line_w = max(font.getlength(line) for line in lines)
        if max_line_w <= max_width:
            # Try increasing to use more space
            if attempt == 0:
                # First try — try a bit wider
                chars_per_line += 3
                continue
            break
        chars_per_line -= 2
        if chars_per_line < 5:
            break

    return lines


def draw_text_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    x: int,
    y: int,
    max_width: int,
    color: tuple[int, int, int] = BLACK,
    line_spacing: int = 4,
) -> int:
    """Draw wrapped text and return the Y position after the last line."""
    lines = wrap_text(text, font, max_width)
    for line in lines:
        draw.text((x, y), line, font=font, fill=color)
        bbox = font.getbbox(line)
        line_height = bbox[3] - bbox[1] if bbox else 20
        y += line_height + line_spacing
    return y


def draw_text_with_symbols(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    x: int,
    y: int,
    max_width: int,
    color: tuple[int, int, int] = BLACK,
    line_spacing: int = 4,
    symbol_size: int | None = None,
) -> int:
    """Draw text that may contain inline mana symbols like {T}, {G}, etc.

    Parses {X} patterns in the text, splits into text runs and symbol runs,
    then renders them inline with proper wrapping.

    Returns the Y position after the last line.
    """
    if not MANA_SYMBOL_RE.search(text):
        # No symbols — use the faster plain text renderer
        return draw_text_block(draw, text, font, x, y, max_width, color, line_spacing)

    # Determine symbol size from font metrics if not specified
    if symbol_size is None:
        sample_bbox = font.getbbox("M")
        symbol_size = (sample_bbox[3] - sample_bbox[1]) if sample_bbox else 18

    # Parse text into segments: list of (type, content) where type is "text" or "symbol"
    segments: list[tuple[str, str]] = []
    last_end = 0
    for match in MANA_SYMBOL_RE.finditer(text):
        if match.start() > last_end:
            segments.append(("text", text[last_end : match.start()]))
        segments.append(("symbol", match.group(1)))
        last_end = match.end()
    if last_end < len(text):
        segments.append(("text", text[last_end:]))

    # Render segments inline with word wrapping
    # Use int for all pixel coordinates (font.getlength() returns float)
    cur_x = x
    cur_y = y
    line_height = symbol_size + 2
    symbol_gap = 2  # px gap between symbols and text

    for seg_type, content in segments:
        if seg_type == "symbol":
            sym_img = get_mana_symbol(content, symbol_size)
            # Check if symbol fits on current line
            if cur_x + symbol_size > x + max_width and cur_x > x:
                cur_x = x
                cur_y += line_height + line_spacing
            img.paste(sym_img, (cur_x, cur_y), sym_img)
            cur_x += symbol_size + symbol_gap
        else:
            # Text segment — may need word wrapping
            words = content.split(" ")
            for word in words:
                if not word:
                    cur_x += int(font.getlength(" "))
                    continue
                word_w = font.getlength(word)
                space_w = font.getlength(" ")
                # Add leading space if not at line start
                if cur_x > x:
                    total_w = space_w + word_w
                    prefix = " "
                else:
                    total_w = word_w
                    prefix = ""
                # Wrap to next line if needed
                if cur_x + total_w > x + max_width and cur_x > x:
                    cur_x = x
                    cur_y += line_height + line_spacing
                    prefix = ""
                draw.text((cur_x, cur_y), prefix + word, font=font, fill=color)
                cur_x = int(cur_x + font.getlength(prefix + word))

    # Advance Y past the last line
    cur_y += line_height + line_spacing
    return cur_y


# ---------------------------------------------------------------------------
# Art placeholder
# ---------------------------------------------------------------------------


def draw_art_placeholder(img: Image.Image) -> None:
    """Fill the art box with a green gradient and centered placeholder text."""
    draw = ImageDraw.Draw(img)
    left, top = ART_BOX["left"], ART_BOX["top"]
    right, bottom = ART_BOX["right"], ART_BOX["bottom"]

    # Simple vertical gradient — dark green at top, lighter green at bottom
    for row in range(top, bottom):
        ratio = (row - top) / max(1, bottom - top)
        r = int(GREEN_DARK[0] + (GREEN_LIGHT[0] - GREEN_DARK[0]) * ratio)
        g = int(GREEN_DARK[1] + (GREEN_LIGHT[1] - GREEN_DARK[1]) * ratio)
        b = int(GREEN_DARK[2] + (GREEN_LIGHT[2] - GREEN_DARK[2]) * ratio)
        draw.line([(left, row), (right, row)], fill=(r, g, b))

    # Centered "ART PLACEHOLDER" text
    placeholder_font = load_font("name", 36)
    label = "ART PLACEHOLDER"
    label_bbox = draw.textbbox((0, 0), label, font=placeholder_font)
    label_w = label_bbox[2] - label_bbox[0]
    label_h = label_bbox[3] - label_bbox[1]
    cx = (left + right) // 2 - label_w // 2
    cy = (top + bottom) // 2 - label_h // 2
    # Draw shadow then text for readability
    draw.text((cx + 2, cy + 2), label, font=placeholder_font, fill=(0, 0, 0, 128))
    draw.text((cx, cy), label, font=placeholder_font, fill=WHITE)


# ---------------------------------------------------------------------------
# Mana cost rendering (right-aligned in name bar)
# ---------------------------------------------------------------------------


def draw_mana_cost(
    img: Image.Image,
    mana_cost: str,
    right_edge: int,
    y_center: int,
    symbol_size: int = 28,
    gap: int = 3,
) -> None:
    """Draw mana cost symbols right-aligned at the given position.

    Parses "{2}{G}{G}" into individual symbols and renders each as an image,
    positioned from right to left to achieve right-alignment.

    Args:
        img: The card image to draw on.
        mana_cost: Mana cost string like "{2}{G}{G}".
        right_edge: Right edge X coordinate for alignment.
        y_center: Y coordinate for vertical centering of symbols.
        symbol_size: Pixel size for each mana symbol.
        gap: Pixel gap between symbols.
    """
    symbols = parse_mana_symbols(mana_cost)
    if not symbols:
        return

    # Calculate total width for right-alignment
    total_width = len(symbols) * symbol_size + (len(symbols) - 1) * gap

    # Starting X position (right-aligned)
    start_x = right_edge - total_width
    y_pos = y_center - symbol_size // 2

    for i, symbol in enumerate(symbols):
        sym_img = get_mana_symbol(symbol, symbol_size)
        paste_x = start_x + i * (symbol_size + gap)
        img.paste(sym_img, (paste_x, y_pos), sym_img)


# ---------------------------------------------------------------------------
# Main rendering function
# ---------------------------------------------------------------------------


def render_card(card: dict) -> Image.Image:
    """Render a complete MTG-style card and return the Image."""
    start = time.perf_counter()

    # Create RGBA canvas (need alpha for symbol compositing)
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), WHITE + (255,))
    draw = ImageDraw.Draw(img)

    # --- Layer 1: Bleed area fill (green for this card) ---
    draw.rectangle([0, 0, CANVAS_W, CANVAS_H], fill=GREEN_DARK)

    # --- Layer 2: Card border (green) ---
    draw.rounded_rectangle(
        [BLEED, BLEED, CANVAS_W - BLEED, CANVAS_H - BLEED],
        radius=20,
        fill=GREEN_BORDER,
    )

    # --- Layer 3: Inner card area ---
    draw.rounded_rectangle(
        [CONTENT_LEFT, CONTENT_TOP, CONTENT_RIGHT, CONTENT_BOTTOM],
        radius=14,
        fill=GREEN_FRAME,
    )

    # --- Layer 4: Name bar ---
    draw_rounded_rect(draw, NAME_BAR, radius=8, fill=NAME_BAR_BG, outline=DARK_GRAY)

    # --- Layer 5: Art box ---
    draw_art_placeholder(img)
    draw = ImageDraw.Draw(img)  # re-acquire draw after art placeholder
    # Art box border
    draw.rectangle(
        [ART_BOX["left"], ART_BOX["top"], ART_BOX["right"], ART_BOX["bottom"]],
        outline=DARK_GRAY,
        width=2,
    )

    # --- Layer 6: Type bar ---
    draw_rounded_rect(draw, TYPE_BAR, radius=8, fill=TYPE_BAR_BG, outline=DARK_GRAY)

    # --- Layer 7: Text box ---
    draw_rounded_rect(draw, TEXT_BOX, radius=8, fill=CREAM, outline=DARK_GRAY)

    # --- Layer 8: P/T box ---
    draw_rounded_rect(draw, PT_BOX, radius=10, fill=PT_BG, outline=DARK_GRAY, outline_width=2)

    # --- Layer 9: Collector info bar ---
    draw_rounded_rect(
        draw, COLLECTOR_BAR, radius=6, fill=(40, 40, 40), outline=None
    )

    # ------------------------------------------------------------------
    # Text rendering
    # ------------------------------------------------------------------
    fonts = load_fonts()

    # Card name (top-left of name bar)
    name_x = NAME_BAR["left"] + 10
    name_y = NAME_BAR["top"] + 8
    draw.text((name_x, name_y), card["name"], font=fonts["name"], fill=BLACK)

    # Mana cost — rendered as symbol images, right-aligned in name bar
    mana_symbol_size = 28  # px per symbol
    name_bar_center_y = (NAME_BAR["top"] + NAME_BAR["bottom"]) // 2
    draw_mana_cost(
        img,
        card["mana_cost"],
        right_edge=NAME_BAR["right"] - 8,
        y_center=name_bar_center_y,
        symbol_size=mana_symbol_size,
    )
    draw = ImageDraw.Draw(img)  # re-acquire draw after pasting symbols

    # Type line (left-aligned in type bar, leaving room for set symbol on right)
    type_text = card["type_line"]
    type_bbox = draw.textbbox((0, 0), type_text, font=fonts["type_line"])
    type_h = type_bbox[3] - type_bbox[1]
    type_x = TYPE_BAR["left"] + 12
    type_y = (TYPE_BAR["top"] + TYPE_BAR["bottom"]) // 2 - type_h // 2 - 2
    draw.text((type_x, type_y), type_text, font=fonts["type_line"], fill=BLACK)

    # Set symbol — right side of type bar
    set_symbol_size = 30
    set_symbol = get_set_symbol(card.get("rarity", "C"), set_symbol_size)
    set_sym_x = TYPE_BAR["right"] - set_symbol_size - 10
    set_sym_y = (TYPE_BAR["top"] + TYPE_BAR["bottom"]) // 2 - set_symbol_size // 2
    img.paste(set_symbol, (set_sym_x, set_sym_y), set_symbol)
    draw = ImageDraw.Draw(img)  # re-acquire draw after pasting

    # Rules text — split by \n for separate abilities
    text_x = TEXT_BOX["left"] + 12
    text_max_w = (TEXT_BOX["right"] - TEXT_BOX["left"]) - 24
    current_y = TEXT_BOX["top"] + 10

    rules_parts = card["rules_text"].split("\n")
    for i, part in enumerate(rules_parts):
        part = part.strip()
        if not part:
            continue

        # Check if this is a keyword ability (single word, no spaces after first word)
        # For prototype: render keywords in bold font
        words = part.split()
        is_keyword = len(words) == 1 and part[0].isupper()

        if is_keyword:
            font_to_use = fonts["rules_bold"]
        else:
            font_to_use = fonts["rules"]

        # Use symbol-aware text renderer (handles {T}, {G}, etc. in rules text)
        current_y = draw_text_with_symbols(
            img, draw, part, font_to_use, text_x, current_y, text_max_w, color=BLACK
        )
        # Re-acquire draw after potential symbol pasting
        draw = ImageDraw.Draw(img)
        # Add spacing between abilities
        if i < len(rules_parts) - 1:
            current_y += 6

    # Flavor text separator line
    if card.get("flavor_text"):
        sep_y = current_y + 4
        sep_left = TEXT_BOX["left"] + 40
        sep_right = TEXT_BOX["right"] - 40
        draw.line([(sep_left, sep_y), (sep_right, sep_y)], fill=MID_GRAY, width=1)
        current_y = sep_y + 8

        # Flavor text (italic)
        draw_text_block(
            draw,
            card["flavor_text"],
            fonts["flavor"],
            text_x,
            current_y,
            text_max_w,
            color=DARK_GRAY,
        )

    # P/T text (centered in P/T box)
    pt_text = f"{card['power']}/{card['toughness']}"
    pt_bbox = draw.textbbox((0, 0), pt_text, font=fonts["pt"])
    pt_w = pt_bbox[2] - pt_bbox[0]
    pt_h = pt_bbox[3] - pt_bbox[1]
    pt_x = (PT_BOX["left"] + PT_BOX["right"]) // 2 - pt_w // 2
    pt_y = (PT_BOX["top"] + PT_BOX["bottom"]) // 2 - pt_h // 2 - 2
    draw.text((pt_x, pt_y), pt_text, font=fonts["pt"], fill=BLACK)

    # Collector info (bottom bar)
    rarity_map = {"C": "C", "U": "U", "R": "R", "M": "M"}
    rarity_char = rarity_map.get(card["rarity"], "?")
    collector_text = (
        f"{card['collector_number']}/{card['collector_total']} "
        f"{card['set_code']} \u2022 {rarity_char}"
    )
    collector_bbox = draw.textbbox((0, 0), collector_text, font=fonts["collector"])
    collector_w = collector_bbox[2] - collector_bbox[0]
    collector_h = collector_bbox[3] - collector_bbox[1]
    coll_x = (COLLECTOR_BAR["left"] + COLLECTOR_BAR["right"]) // 2 - collector_w // 2
    coll_y = (COLLECTOR_BAR["top"] + COLLECTOR_BAR["bottom"]) // 2 - collector_h // 2
    draw.text((coll_x, coll_y), collector_text, font=fonts["collector"], fill=WHITE)

    elapsed = time.perf_counter() - start
    print(f"\nRender time: {elapsed:.3f} seconds")

    # Convert to RGB for final output (PNG doesn't need alpha for the card itself)
    return img.convert("RGB")


# ---------------------------------------------------------------------------
# Text layout evaluation
# ---------------------------------------------------------------------------


def evaluate_text_layout() -> str:
    """Run text layout tests and return a summary string."""
    results: list[str] = []
    results.append("=" * 60)
    results.append("TEXT LAYOUT EVALUATION")
    results.append("=" * 60)

    # Test 1: Word wrapping
    results.append("\n--- Test 1: Word wrapping ---")
    font = load_font("body", 21)
    test_text = (
        "Whenever Thornwood Guardian attacks, you may search your library for a "
        "Forest card, put it onto the battlefield tapped, then shuffle."
    )
    max_width = TEXT_BOX["right"] - TEXT_BOX["left"] - 24
    lines = wrap_text(test_text, font, max_width)
    results.append(f"Max width: {max_width}px")
    results.append(f"Input: {test_text}")
    results.append(f"Wrapped into {len(lines)} lines:")
    for i, line in enumerate(lines):
        line_w = font.getlength(line)
        results.append(f"  Line {i + 1} ({line_w:.0f}px): {line}")
    fits = all(font.getlength(l) <= max_width for l in lines)
    results.append(f"All lines fit within bounds: {fits}")

    # Test 2: Font sizing at 300 DPI
    results.append("\n--- Test 2: Font sizes at 300 DPI ---")
    sizes = [14, 16, 18, 20, 22, 24, 28, 32, 36]
    sample = "Thornwood Guardian"
    for size in sizes:
        f = load_font("name", size)
        bbox = f.getbbox(sample)
        h = bbox[3] - bbox[1] if bbox else 0
        w = f.getlength(sample)
        # At 300 DPI, 1 point = 300/72 = 4.17 pixels
        pt_equiv = size * 72 / 300
        results.append(
            f"  {size}px ({pt_equiv:.1f}pt at 300DPI): "
            f"{sample} -> {w:.0f}x{h}px"
        )

    # Test 3: Bold vs italic capability
    results.append("\n--- Test 3: Bold / Italic font variants ---")
    for role in ["body", "body_bold", "body_italic"]:
        f = load_font(role, 21)
        has_truetype = hasattr(f, "path") if hasattr(f, "path") else False
        font_path = getattr(f, "path", "(default)")
        results.append(f"  {role:15s}: TrueType={has_truetype}, path={font_path}")

    # Test 4: Mana symbol rendering
    results.append("\n--- Test 4: Mana symbol rendering ---")
    backend = _detect_svg_backend()
    results.append(f"  SVG backend: {backend}")
    test_symbols = ["W", "U", "B", "R", "G", "2", "X", "T"]
    for sym in test_symbols:
        sym_img = get_mana_symbol(sym, 28)
        results.append(f"  {{{sym}}}: {sym_img.size[0]}x{sym_img.size[1]} {sym_img.mode}")

    # Test 5: Set symbol rendering
    results.append("\n--- Test 5: Set symbol rendering ---")
    for rarity in ["C", "U", "R", "M"]:
        sym_img = get_set_symbol(rarity, 30)
        results.append(f"  {rarity}: {sym_img.size[0]}x{sym_img.size[1]} {sym_img.mode}")

    return "\n".join(results)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point — render the test card and save output."""
    script_dir = Path(__file__).resolve().parent
    output_path = script_dir / "rendered-thornwood-prototype.png"

    print("MTG Card Rendering Prototype")
    print(f"Canvas: {CANVAS_W}x{CANVAS_H} px at {DPI} DPI")
    print(f"Output: {output_path}")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"SVG backend: {_detect_svg_backend()}")
    print()

    # Render the card
    img = render_card(CARD)

    # Save with DPI metadata
    img.save(str(output_path), dpi=(DPI, DPI))
    print(f"Saved: {output_path}")

    # Verify output
    file_size = output_path.stat().st_size
    print(f"File size: {file_size:,} bytes ({file_size / 1024:.1f} KB)")

    # Verify DPI metadata roundtrip
    check = Image.open(str(output_path))
    info_dpi = check.info.get("dpi", "NOT SET")
    print(f"DPI metadata: {info_dpi}")
    print(f"Dimensions: {check.size[0]}x{check.size[1]}")

    # Run text layout evaluation
    print()
    eval_report = evaluate_text_layout()
    print(eval_report)

    # Print layout measurements used
    print()
    print("=" * 60)
    print("LAYOUT MEASUREMENTS (px at 300 DPI)")
    print("=" * 60)
    for name, box in [
        ("Name bar", NAME_BAR),
        ("Art box", ART_BOX),
        ("Type bar", TYPE_BAR),
        ("Text box", TEXT_BOX),
        ("P/T box", PT_BOX),
        ("Collector bar", COLLECTOR_BAR),
    ]:
        w = box["right"] - box["left"]
        h = box["bottom"] - box["top"]
        print(
            f"  {name:15s}: ({box['left']}, {box['top']}) -> "
            f"({box['right']}, {box['bottom']})  [{w}x{h}]"
        )


if __name__ == "__main__":
    main()
