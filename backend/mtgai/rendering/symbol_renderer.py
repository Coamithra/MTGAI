"""Mana and set symbol rendering for MTG cards.

Renders mana symbols (e.g. {W}, {2}, {T}) and set-rarity symbols as PIL RGBA
images at any requested pixel size, with caching.

Rendering pipeline (in order of preference):
    1. **pycairo + svg.path** — parses SVG path data and renders with Cairo's
       antialiased path engine. Works on Windows without native Cairo DLLs
       since pycairo ≥1.24 bundles its own libcairo.
    2. **cairosvg** — full SVG-to-PNG via cairocffi + native libcairo.
       Preferred if available (Linux/macOS) but rarely works on Windows.
    3. **Pillow fallback** — colored circles with text labels. Functional
       but visually basic.

SVG assets:
    Mana symbols:  ``assets/symbols/mana/{code}.svg``  (IcoMoon glyph format)
    Set symbols:   ``assets/symbols/set-symbol-{rarity}.svg``
"""

from __future__ import annotations

import logging
import math
import re
import xml.etree.ElementTree as ET
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
MANA_PNG_DIR = PROJECT_ROOT / "assets" / "symbols" / "mana-png"
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
# Symbol code → SVG filename mapping (where name != code.lower())
# ---------------------------------------------------------------------------
SYMBOL_SVG_MAP: dict[str, str] = {
    "T": "tap",
    "TAP": "tap",
    "Q": "untap",
    "UNTAP": "untap",
}


def _svg_filename(symbol: str) -> str:
    """Map a mana symbol code to its SVG filename (without extension)."""
    key = symbol.upper()
    return SYMBOL_SVG_MAP.get(key, symbol.lower())


# ---------------------------------------------------------------------------
# SVG backend detection
# ---------------------------------------------------------------------------
_svg_backend: str | None = None


def _detect_svg_backend() -> str:
    """Detect the best available SVG rendering backend.

    Tries (in order): cairosvg, pycairo+svg.path, fallback.
    """
    global _svg_backend
    if _svg_backend is not None:
        return _svg_backend

    # 1. Try cairosvg (full SVG renderer via cairocffi)
    try:
        import cairosvg

        cairosvg.svg2png(
            bytestring=b'<svg xmlns="http://www.w3.org/2000/svg"/>',
            output_width=1,
        )
        _svg_backend = "cairosvg"
        logger.info("SVG backend: cairosvg (native Cairo available)")
        return _svg_backend
    except Exception:
        pass

    # 2. Try pycairo + svg.path (bundled Cairo, path-only rendering)
    try:
        import cairo  # pycairo — bundles libcairo on Windows
        from svg.path import parse_path  # noqa: F401

        # Quick smoke test
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        cairo.Context(surface)
        _svg_backend = "pycairo"
        logger.info(
            "SVG backend: pycairo %s + svg.path (Cairo %s)",
            cairo.version,
            cairo.cairo_version_string(),
        )
        return _svg_backend
    except Exception:
        pass

    _svg_backend = "fallback"
    logger.info("SVG backend: Pillow fallback (no Cairo available)")
    return _svg_backend


def svg_backend() -> str:
    """Return the current SVG backend name."""
    return _detect_svg_backend()


# ---------------------------------------------------------------------------
# pycairo SVG path rasterization
# ---------------------------------------------------------------------------


def _parse_svg_color(color_str: str | None) -> tuple[float, float, float] | None:
    """Parse an SVG fill color like ``'#F8F6D8'`` to ``(r, g, b)`` floats 0-1."""
    if not color_str or color_str == "none":
        return None
    s = color_str.strip()
    if s.startswith("#") and len(s) == 7:
        return (int(s[1:3], 16) / 255, int(s[3:5], 16) / 255, int(s[5:7], 16) / 255)
    return None


def _draw_svg_path_data(ctx, d: str) -> None:
    """Trace an SVG path ``d`` attribute onto a Cairo context (no fill/stroke)."""
    from svg.path import Arc, Close, CubicBezier, Line, Move, QuadraticBezier, parse_path

    for seg in parse_path(d):
        if isinstance(seg, Move):
            ctx.move_to(seg.end.real, seg.end.imag)
        elif isinstance(seg, Line):
            ctx.line_to(seg.end.real, seg.end.imag)
        elif isinstance(seg, CubicBezier):
            ctx.curve_to(
                seg.control1.real, seg.control1.imag,
                seg.control2.real, seg.control2.imag,
                seg.end.real, seg.end.imag,
            )
        elif isinstance(seg, QuadraticBezier):
            qp0, qp1, qp2 = seg.start, seg.control, seg.end
            cp1 = qp0 + (2 / 3) * (qp1 - qp0)
            cp2 = qp2 + (2 / 3) * (qp1 - qp2)
            ctx.curve_to(cp1.real, cp1.imag, cp2.real, cp2.imag, qp2.real, qp2.imag)
        elif isinstance(seg, Close):
            ctx.close_path()
        elif isinstance(seg, Arc):
            for t in range(1, 21):
                pt = seg.point(t / 20.0)
                ctx.line_to(pt.real, pt.imag)


def _rasterize_svg_pycairo(
    svg_path: Path,
    width: int,
    height: int,
) -> Image.Image | None:
    """Rasterize a multi-element SVG using pycairo + svg.path.

    Handles ``<circle>``, ``<path>``, ``<g>`` transforms, per-element
    fill colors, and ``fill-rule="evenodd"``. Works with both simple
    IcoMoon glyph SVGs and complete Scryfall mana symbol SVGs.
    """
    if not svg_path.is_file():
        return None

    try:
        import cairo
        from svg.path import parse_path  # noqa: F401
    except ImportError:
        return None

    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()
    except ET.ParseError:
        return None

    vb = root.get("viewBox", "0 0 100 100").split()
    vb_w, vb_h = float(vb[2]), float(vb[3])

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_antialias(cairo.ANTIALIAS_BEST)
    ctx.scale(width / vb_w, height / vb_h)

    def _render_elem(elem, parent_fill=None):
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        fill = elem.get("fill") or parent_fill
        fill_rule = elem.get("fill-rule", "")

        if tag == "g":
            transform = elem.get("transform", "")
            has_transform = bool(transform)
            if has_transform:
                ctx.save()
                m = re.match(r"translate\(([^,\s]+)[\s,]+([^)]+)\)", transform)
                if m:
                    ctx.translate(float(m.group(1)), float(m.group(2)))
            for child in elem:
                _render_elem(child, fill)
            if has_transform:
                ctx.restore()

        elif tag == "circle":
            color = _parse_svg_color(fill)
            if color:
                cx = float(elem.get("cx", "50"))
                cy = float(elem.get("cy", "50"))
                r = float(elem.get("r", "50"))
                ctx.arc(cx, cy, r, 0, 2 * math.pi)
                ctx.set_source_rgba(*color, 1.0)
                ctx.fill()

        elif tag == "path":
            d = elem.get("d")
            color = _parse_svg_color(fill)
            if d and color:
                if fill_rule == "evenodd":
                    ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
                else:
                    ctx.set_fill_rule(cairo.FILL_RULE_WINDING)
                _draw_svg_path_data(ctx, d)
                ctx.set_source_rgba(*color, 1.0)
                ctx.fill()

    for elem in root:
        _render_elem(elem)

    buf = surface.get_data()
    return Image.frombuffer(
        "RGBA", (width, height), bytes(buf), "raw", "BGRA", 0, 1
    )


# ---------------------------------------------------------------------------
# cairosvg rasterization (legacy)
# ---------------------------------------------------------------------------


def _rasterize_svg_cairosvg(
    svg_path: Path,
    width: int,
    height: int,
) -> Image.Image | None:
    """Rasterize an SVG file via cairosvg (requires native libcairo)."""
    if not svg_path.is_file():
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
        logger.debug("cairosvg rasterization failed for %s: %s", svg_path, exc)
        return None


def _rasterize_svg(svg_path: Path, width: int, height: int) -> Image.Image | None:
    """Rasterize an SVG file using the best available backend."""
    backend = _detect_svg_backend()

    if backend == "cairosvg":
        return _rasterize_svg_cairosvg(svg_path, width, height)
    if backend == "pycairo":
        return _rasterize_svg_pycairo(svg_path, width, height)
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


def _make_circle_background(
    size: int,
    bg: tuple[int, int, int],
) -> Image.Image:
    """Draw a filled circle with outline for a mana symbol background.

    Matches real MTG mana symbols: filled circle with a prominent dark
    border ring for definition at small sizes.
    """
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    border_w = max(2, size // 12)
    margin = 1
    # Dark border ring
    draw.ellipse(
        [margin, margin, size - margin - 1, size - margin - 1],
        fill=(0, 0, 0, 220),
    )
    # Inner fill (inset by border width)
    inner = margin + border_w
    draw.ellipse(
        [inner, inner, size - inner - 1, size - inner - 1],
        fill=(*bg, 255),
    )
    return canvas


def _make_fallback_mana_symbol(symbol: str, size: int) -> Image.Image:
    """Draw a colored circle with a centered text label using pure Pillow."""
    bg, fg = _mana_colors(symbol)

    img = _make_circle_background(size, bg)
    draw = ImageDraw.Draw(img)

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
    label_y = (size - label_h) // 2 - label_bbox[1]
    draw.text((label_x, label_y), label, font=label_font, fill=(*fg, 255))

    return img


def _make_svg_mana_symbol(symbol: str, size: int) -> Image.Image | None:
    """Rasterize an SVG mana glyph and composite it onto a colored circle.

    Uses the appropriate SVG filename mapping (e.g., T → tap.svg).
    """
    svg_name = _svg_filename(symbol)
    svg_path = MANA_SVG_DIR / f"{svg_name}.svg"
    glyph_img = _rasterize_svg(svg_path, size, size)
    if glyph_img is None:
        return None

    bg, fg = _mana_colors(symbol)

    # Create circular background
    canvas = _make_circle_background(size, bg)

    # Extract alpha channel from glyph, recolor to foreground
    glyph_alpha = glyph_img.split()[3]
    colored_glyph = Image.new("RGBA", (size, size), (*fg, 255))
    colored_glyph.putalpha(glyph_alpha)

    # Shrink glyph to fit within circle with padding
    glyph_size = int(size * 0.72)
    glyph_offset = (size - glyph_size) // 2
    colored_glyph_resized = colored_glyph.resize((glyph_size, glyph_size), Image.LANCZOS)

    canvas.paste(
        colored_glyph_resized,
        (glyph_offset, glyph_offset),
        colored_glyph_resized,
    )
    return canvas


SCRYFALL_SVG_DIR = PROJECT_ROOT / "assets" / "symbols" / "scryfall"


def _load_scryfall_svg(symbol: str, size: int) -> Image.Image | None:
    """Rasterize a complete Scryfall mana symbol SVG at the given size.

    These SVGs contain the full symbol (circle bg + glyph) with official
    colors, so no compositing is needed — just rasterize and return.
    """
    key = symbol.upper()
    if key == "TAP":
        key = "T"
    elif key == "UNTAP":
        key = "Q"

    svg_path = SCRYFALL_SVG_DIR / f"{key}.svg"
    return _rasterize_svg_pycairo(svg_path, size, size)


def _load_prerendered_mana_symbol(symbol: str, size: int) -> Image.Image | None:
    """Load a pre-rendered mana symbol image from the mana-png directory.

    These are high-quality 800x800 RGBA WebP images from printmtg.com,
    scaled to the requested size with LANCZOS resampling.
    """
    key = symbol.upper()
    if key == "TAP":
        key = "T"
    elif key == "UNTAP":
        key = "Q"

    img_path = MANA_PNG_DIR / f"{key}.webp"
    if not img_path.is_file():
        return None

    try:
        img = Image.open(img_path).convert("RGBA")
        if img.size != (size, size):
            img = img.resize((size, size), Image.LANCZOS)
        return img
    except Exception as exc:
        logger.debug("Failed to load pre-rendered symbol %s: %s", key, exc)
        return None


def get_mana_symbol(symbol: str, size: int) -> Image.Image:
    """Get a rendered mana symbol image at the requested pixel size.

    Priority: Scryfall SVG > pre-rendered WebP > SVG glyph composite > fallback.
    """
    cache_key = (symbol.upper(), size)
    if cache_key in _mana_cache:
        return _mana_cache[cache_key]

    # 1. Scryfall official SVGs (vector, official colors, best quality)
    result = _load_scryfall_svg(symbol, size)

    # 2. Pre-rendered WebP from printmtg (800x800, good quality)
    if result is None:
        result = _load_prerendered_mana_symbol(symbol, size)

    # 3. SVG glyph composite via pycairo (IcoMoon glyphs on colored circles)
    if result is None:
        result = _make_svg_mana_symbol(symbol, size)

    # 4. Pillow fallback (colored circles with text labels)
    if result is None:
        result = _make_fallback_mana_symbol(symbol, size)

    _mana_cache[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# Set symbol rendering — ASD "Descending Vortex" via pycairo
# ---------------------------------------------------------------------------
_set_symbol_cache: dict[tuple[str, int], Image.Image] = {}

# Rarity color schemes for the set symbol (triangle + spiral)
_SET_SYMBOL_COLORS: dict[str, dict[str, tuple[int, int, int] | tuple[float, ...]]] = {
    "C": {
        "fill": (20, 20, 20),
        "stroke": (50, 50, 50),
        "spiral": (60, 60, 60),
        "dot": (40, 40, 40),
    },
    "U": {
        "fill": (160, 165, 175),
        "stroke": (100, 105, 115),
        "spiral": (115, 120, 130),
        "dot": (130, 135, 145),
    },
    "R": {
        "fill": (220, 180, 40),
        "stroke": (139, 105, 20),
        "spiral": (160, 120, 20),
        "dot": (180, 140, 30),
    },
    "M": {
        "fill": (230, 90, 30),
        "stroke": (160, 50, 10),
        "spiral": (180, 60, 15),
        "dot": (200, 70, 20),
    },
}


def _make_pycairo_set_symbol(rarity: str, size: int) -> Image.Image | None:
    """Draw the ASD set symbol (descending vortex triangle) with pycairo.

    A downward-pointing triangle with three spiral arms converging
    to a central point — representing the "Anomalous Descent."
    """
    try:
        import cairo
    except ImportError:
        return None

    colors = _SET_SYMBOL_COLORS.get(rarity, _SET_SYMBOL_COLORS["C"])
    fill_c = colors["fill"]
    stroke_c = colors["stroke"]
    spiral_c = colors["spiral"]
    dot_c = colors["dot"]

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx = cairo.Context(surface)
    ctx.set_antialias(cairo.ANTIALIAS_BEST)

    # Scale to work in 0-100 coordinate space
    ctx.scale(size / 100.0, size / 100.0)

    # --- Filled triangle pointing down ---
    ctx.move_to(50, 8)
    ctx.line_to(88, 85)
    ctx.line_to(12, 85)
    ctx.close_path()

    # Fill
    ctx.set_source_rgba(fill_c[0] / 255, fill_c[1] / 255, fill_c[2] / 255, 1.0)
    ctx.fill_preserve()

    # Stroke outline
    ctx.set_source_rgba(stroke_c[0] / 255, stroke_c[1] / 255, stroke_c[2] / 255, 1.0)
    ctx.set_line_width(3.0)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.stroke()

    # --- Three spiral arms ---
    ctx.set_source_rgba(spiral_c[0] / 255, spiral_c[1] / 255, spiral_c[2] / 255, 1.0)
    ctx.set_line_width(2.5)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)

    # Center arm (top → center)
    ctx.move_to(50, 28)
    ctx.curve_to(62, 38, 58, 50, 50, 62)
    ctx.stroke()

    # Left arm
    ctx.move_to(36, 40)
    ctx.curve_to(46, 36, 50, 48, 44, 62)
    ctx.stroke()

    # Right arm
    ctx.move_to(64, 40)
    ctx.curve_to(54, 36, 50, 48, 56, 62)
    ctx.stroke()

    # --- Central anomaly dot ---
    ctx.arc(50, 52, 3, 0, 2 * math.pi)
    ctx.set_source_rgba(dot_c[0] / 255, dot_c[1] / 255, dot_c[2] / 255, 1.0)
    ctx.fill()

    # --- Metallic highlight for R/M ---
    if rarity in ("R", "M"):
        # Subtle highlight on upper-left triangle face
        ctx.move_to(50, 15)
        ctx.line_to(30, 70)
        ctx.line_to(50, 70)
        ctx.close_path()
        highlight_alpha = 0.15 if rarity == "R" else 0.20
        ctx.set_source_rgba(1.0, 1.0, 1.0, highlight_alpha)
        ctx.fill()
    elif rarity == "U":
        ctx.move_to(50, 15)
        ctx.line_to(30, 70)
        ctx.line_to(50, 70)
        ctx.close_path()
        ctx.set_source_rgba(1.0, 1.0, 1.0, 0.10)
        ctx.fill()

    # Convert to PIL
    buf = surface.get_data()
    return Image.frombuffer("RGBA", (size, size), bytes(buf), "raw", "BGRA", 0, 1)


def _make_fallback_set_symbol(rarity: str, size: int) -> Image.Image:
    """Draw a hexagonal gem shape (Pillow fallback for set symbol)."""
    color = RARITY_COLORS.get(rarity, RARITY_COLORS["C"])
    highlight = RARITY_HIGHLIGHT_COLORS.get(rarity, color)

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = size // 2, size // 2
    r = size // 2 - 2

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


def get_set_symbol(rarity: str, size: int) -> Image.Image:
    """Get a rendered set symbol for the given rarity at the given size.

    Tries pycairo (drawn ASD vortex symbol), then SVG rasterization,
    then Pillow fallback hexagon.
    """
    cache_key = (rarity.upper(), size)
    if cache_key in _set_symbol_cache:
        return _set_symbol_cache[cache_key]

    # 1. Try pycairo-drawn ASD set symbol
    result = _make_pycairo_set_symbol(rarity, size)

    # 2. Try SVG rasterization (cairosvg only — pycairo can't handle
    #    the multi-element set symbol SVGs with strokes+gradients)
    if result is None and _detect_svg_backend() == "cairosvg":
        svg_filename = RARITY_SET_SYMBOL_FILES.get(rarity, "set-symbol-common.svg")
        svg_path = SET_SYMBOL_DIR / svg_filename
        result = _rasterize_svg_cairosvg(svg_path, size, size)

    # 3. Pillow fallback
    if result is None:
        result = _make_fallback_set_symbol(rarity, size)

    _set_symbol_cache[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------
def clear_caches() -> None:
    """Drop all cached symbol images."""
    _mana_cache.clear()
    _set_symbol_cache.clear()
