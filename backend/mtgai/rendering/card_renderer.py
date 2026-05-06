"""Card image renderer — composites art, frame, text, and symbols.

Renders MTG cards by layering art, M15 frame templates, and text
at native resolution (2010x2814), then scaling to print resolution
(822x1122 at 300 DPI).

Usage::

    renderer = CardRenderer(assets_root, output_root)
    img = renderer.render_card(card, "ASD")
    renderer.render_and_save(card, "ASD")
    renderer.render_set("ASD")

CLI::

    python -m mtgai.rendering --set ASD [--card W-C-01] [--dry-run] [--force]
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from mtgai.io.card_io import load_card
from mtgai.io.paths import card_slug
from mtgai.models.card import Card
from mtgai.rendering.colors import (
    BLACK,
    WHITE,
    frame_key_for_identity,
)
from mtgai.rendering.fonts import (
    DEFAULT_SIZES,
    FontManager,
    get_font_manager,
)
from mtgai.rendering.layout import (
    CANVAS_H,
    CANVAS_W,
    FRAME_H,
    FRAME_W,
    NATIVE_ART_WINDOW,
    NATIVE_COLLECTOR_BAR,
    NATIVE_NAME_BAR,
    NATIVE_PT_BOX,
    NATIVE_TEXT_BOX,
    NATIVE_TYPE_BAR,
    PT_OVERLAY_ACTIVE,
    BoundingBox,
    frame_path,
    pt_box_path,
)
from mtgai.rendering.symbol_renderer import (
    get_mana_symbol,
    get_set_symbol,
    parse_mana_cost,
)
from mtgai.rendering.text_engine import TextEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scale factor from print-resolution font sizes to native resolution
# Native is ~2.45x larger than print (2010/822 ≈ 2.4453)
# ---------------------------------------------------------------------------
NATIVE_SCALE = FRAME_W / CANVAS_W  # ~2.4453

# Rarity enum value -> single-letter code for display / symbol lookup
RARITY_CODE: dict[str, str] = {
    "common": "C",
    "uncommon": "U",
    "rare": "R",
    "mythic": "M",
}


def _rarity_letter(rarity_value: str) -> str:
    """Convert rarity enum value to single letter code."""
    return RARITY_CODE.get(rarity_value, "C")


# ---------------------------------------------------------------------------
# Text rendering helpers (standalone, no TextEngine dependency)
#
# These provide basic text layout directly. When text_engine.py is
# ready, CardRenderer can delegate to it instead.
# ---------------------------------------------------------------------------


def _wrap_text(
    text: str,
    font,
    max_width: int,
) -> list[str]:
    """Word-wrap text to fit within max_width pixels.

    Splits on spaces and builds lines greedily.
    """
    words = text.split(" ")
    lines: list[str] = []
    current_line = ""

    for word in words:
        if not word:
            continue
        test = f"{current_line} {word}".strip()
        if font.getlength(test) <= max_width:
            current_line = test
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)

    return lines if lines else [""]


def _draw_text_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    box: BoundingBox,
    color: tuple[int, int, int] = BLACK,
    y_offset: int = 0,
) -> None:
    """Draw text centered horizontally and vertically within a box."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = box.left + (box.width - tw) // 2
    y = box.top + (box.height - th) // 2 - bbox[1] + y_offset
    draw.text((x, y), text, font=font, fill=color)


# ---------------------------------------------------------------------------
# MANA_SYMBOL_RE for inline symbol parsing in rules text
# ---------------------------------------------------------------------------
import re

MANA_SYMBOL_RE = re.compile(r"\{([^}]+)\}")


# ---------------------------------------------------------------------------
# CardRenderer
# ---------------------------------------------------------------------------
class CardRenderer:
    """Renders MTG cards by compositing art, frames, and text.

    Args:
        assets_root: Path to the project ``assets/`` directory.
        output_root: Path to the ``output/`` directory tree.
    """

    def __init__(
        self,
        assets_root: Path,
        output_root: Path,
    ) -> None:
        self.assets_root = Path(assets_root)
        self.output_root = Path(output_root)
        self.fm: FontManager = get_font_manager()
        self.text_engine = TextEngine(self.fm)
        # Frame image cache to avoid reloading per card
        self._frame_cache: dict[str, Image.Image] = {}
        self._pt_cache: dict[str, Image.Image] = {}
        self._crown_cache: dict[str, Image.Image] = {}
        self._title_mask: Image.Image | None = None
        self._crown_underlay: Image.Image | None = None

    # ------------------------------------------------------------------
    # Frame key
    # ------------------------------------------------------------------
    def determine_frame_key(self, card: Card) -> str:
        """Map card to frame key based on colors and type_line.

        Returns one of: W, U, B, R, G, M, A, L, or land variants
        (lw, lu, lb, lr, lg, lm).
        """
        type_lower = card.type_line.lower()
        is_land = "land" in type_lower
        is_artifact = "artifact" in type_lower

        # Color identity as list of single-letter strings
        identity = [c.value if hasattr(c, "value") else str(c) for c in card.color_identity]

        # Colored artifacts still get the artifact frame (until colored artifact
        # frames are implemented — see learnings/colored-artifact-frames.md)
        if is_artifact and not is_land:
            return "A"

        return frame_key_for_identity(identity, is_land=is_land)

    # ------------------------------------------------------------------
    # Art resolution
    # ------------------------------------------------------------------
    def resolve_art_path(
        self,
        card: Card,
        set_code: str,
    ) -> Path | None:
        """Find the selected art image for a card.

        Checks ``art-selection-logs/<CN>.json`` for the ``pick`` field
        (e.g. "v2"), then finds the matching file in ``art/``.

        Returns ``None`` if no art is found.
        """
        from mtgai.io.asset_paths import set_artifact_dir

        set_dir = set_artifact_dir()
        cn = card.collector_number

        # 1. Check art selection log
        log_path = set_dir / "art-selection-logs" / f"{cn}.json"
        if log_path.is_file():
            try:
                log_data = json.loads(log_path.read_text(encoding="utf-8"))
                pick = log_data.get("pick", "")  # e.g. "v2"
                version_files = log_data.get("version_files", [])

                # Find file matching the pick version
                for fname in version_files:
                    if f"_{pick}." in fname:
                        art_file = set_dir / "art" / fname
                        if art_file.is_file():
                            return art_file

                # Fallback: try constructing path directly
                slug = card_slug(cn, card.name)
                direct = set_dir / "art" / f"{slug}_{pick}.png"
                if direct.is_file():
                    return direct

            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning("Bad art selection log for %s: %s", cn, exc)

        # 2. Fallback: check card's art_path field
        if card.art_path:
            p = Path(card.art_path)
            if p.is_absolute() and p.is_file():
                return p
            rel = set_dir / card.art_path
            if rel.is_file():
                return rel

        # 3. Fallback: find any v1 art file
        slug = card_slug(cn, card.name)
        v1 = set_dir / "art" / f"{slug}_v1.png"
        if v1.is_file():
            return v1

        return None

    # ------------------------------------------------------------------
    # Legendary crown
    # ------------------------------------------------------------------

    # Map color identity to crown filename (wingedsheep naming convention)
    CROWN_KEY_MAP: dict[str, str] = {
        "W": "W",
        "U": "U",
        "B": "B",
        "R": "R",
        "G": "G",
        "M": "Gold",
        "A": "Artifact",
        "L": "Land",
    }
    # Two-color pairs
    CROWN_PAIR_MAP: dict[tuple[str, ...], str] = {
        ("U", "W"): "WU",
        ("B", "W"): "WB",
        ("R", "W"): "WR",
        ("G", "W"): "WG",
        ("B", "U"): "UB",
        ("R", "U"): "UR",
        ("G", "U"): "UG",
        ("B", "R"): "BR",
        ("B", "G"): "BG",
        ("R", "G"): "RG",
    }

    # Crown positioning (mtgrender CSS: left=1mm, top=1.5mm, w=61.1mm, h=14mm)
    # At native res (2010x2814): 1mm ≈ 32px
    CROWN_X = 31
    CROWN_Y = 47
    CROWN_W = 1934
    CROWN_H = 443

    def _load_title_mask(self) -> Image.Image:
        """Load and cache the title bar mask alpha channel.

        Returns an L-mode image (FRAME_W x FRAME_H) where white pixels
        indicate the name bar shape.
        """
        if self._title_mask is not None:
            return self._title_mask

        path = self.assets_root / "frames" / "m15" / "m15MaskTitle.png"
        img = Image.open(path).convert("RGBA")
        self._title_mask = img.split()[3]
        return self._title_mask

    def _make_crown_underlay(self) -> Image.Image:
        """Create and cache the black underlay for the legendary crown zone.

        Returns a full-canvas RGBA image that is opaque black everywhere
        above the art window EXCEPT where the title bar mask is. This
        blacks out the frame's colored pixels behind the crown while
        preserving the name bar.
        """
        if self._crown_underlay is not None:
            return self._crown_underlay

        title_alpha = self._load_title_mask()
        title_inv = ImageChops.invert(title_alpha)

        # Mask: opaque in rows 0 to art window top, transparent elsewhere
        zone_mask = Image.new("L", (FRAME_W, FRAME_H), 0)
        draw = ImageDraw.Draw(zone_mask)
        draw.rectangle(
            [(0, 0), (FRAME_W - 1, NATIVE_ART_WINDOW.top - 1)],
            fill=255,
        )

        # Remove title bar area: keep it transparent so the name bar is preserved
        combined = ImageChops.multiply(zone_mask, title_inv)

        underlay = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 255))
        underlay.putalpha(combined)

        self._crown_underlay = underlay
        return self._crown_underlay

    def _load_legendary_crown(self, card: Card) -> Image.Image | None:
        """Load the legendary crown overlay with title bar punched out.

        Uses m15MaskTitle to create a transparent cutout in the crown
        where the frame's name bar should show through. The crown's
        decorative filigree renders on top of a black background
        (provided by _make_crown_underlay), while the title bar
        area is left transparent so the frame's own name bar is visible.

        Returns a full-canvas-size RGBA image, or None if no crown file found.
        """
        identity = sorted(c.value if hasattr(c, "value") else str(c) for c in card.color_identity)
        is_land = "land" in card.type_line.lower()

        # Determine crown filename
        if is_land:
            crown_name = "Land"
        elif len(identity) == 0:
            crown_name = "Artifact"
        elif len(identity) == 1:
            crown_name = self.CROWN_KEY_MAP.get(identity[0], "Gold")
        else:
            # Multicolor: always use Gold crown (we use gold frames, not 2-color)
            crown_name = "Gold"

        if crown_name in self._crown_cache:
            return self._crown_cache[crown_name]

        crown_dir = self.assets_root / "frames" / "m15" / "crowns"
        crown_path = crown_dir / f"{crown_name}.png"
        if not crown_path.is_file():
            logger.debug("No crown file: %s", crown_path)
            return None

        crown_img = Image.open(crown_path).convert("RGBA")

        # Scale directly to target dimensions
        crown_fitted = crown_img.resize((self.CROWN_W, self.CROWN_H), Image.LANCZOS)

        # Place on full-canvas overlay
        overlay = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
        overlay.paste(crown_fitted, (self.CROWN_X, self.CROWN_Y), crown_fitted)

        # Punch out the title bar shape so the frame's name bar shows through
        title_alpha = self._load_title_mask()
        title_inv = ImageChops.invert(title_alpha)
        crown_alpha = overlay.split()[3]
        new_alpha = ImageChops.multiply(crown_alpha, title_inv)
        overlay.putalpha(new_alpha)

        self._crown_cache[crown_name] = overlay
        return overlay

    # ------------------------------------------------------------------
    # Frame / PT box loading (cached)
    # ------------------------------------------------------------------
    def _load_frame(self, frame_key: str) -> Image.Image:
        """Load an M15 frame PNG (RGBA). Cached per frame_key."""
        if frame_key in self._frame_cache:
            return self._frame_cache[frame_key].copy()

        fp = frame_path(frame_key)
        if not fp.is_file():
            logger.warning(
                "Frame file not found: %s — falling back to A",
                fp,
            )
            fp = frame_path("A")

        img = Image.open(fp).convert("RGBA")
        self._frame_cache[frame_key] = img
        return img.copy()

    def _load_pt_box(self, frame_key: str) -> Image.Image:
        """Load the P/T box overlay for the given frame key."""
        # For multicolor or land frames, map to a single-letter key
        if len(frame_key) > 1:
            # Land variants (lw, lu, etc.) -> use first color letter
            pt_key = frame_key[1].upper() if frame_key.startswith("l") else "M"
        else:
            pt_key = frame_key

        if pt_key in self._pt_cache:
            return self._pt_cache[pt_key].copy()

        pp = pt_box_path(pt_key)
        if not pp.is_file():
            logger.warning(
                "PT box file not found: %s — falling back to A",
                pp,
            )
            pp = pt_box_path("A")

        img = Image.open(pp).convert("RGBA")
        self._pt_cache[pt_key] = img
        return img.copy()

    # ------------------------------------------------------------------
    # Art compositing
    # ------------------------------------------------------------------
    @staticmethod
    def _fit_art(
        art: Image.Image,
        window: BoundingBox,
    ) -> Image.Image:
        """Scale art to fill the art window, center-crop excess.

        Uses "fill and center-crop": scale so the shorter dimension
        exactly fills the window, then center-crop the excess.
        """
        target_w = window.width
        target_h = window.height
        art_w, art_h = art.size

        # Scale factor: whichever dimension needs MORE scaling
        scale = max(target_w / art_w, target_h / art_h)
        new_w = round(art_w * scale)
        new_h = round(art_h * scale)

        scaled = art.resize((new_w, new_h), Image.LANCZOS)

        # Center-crop to target
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        cropped = scaled.crop((left, top, left + target_w, top + target_h))
        return cropped

    @staticmethod
    def _make_placeholder_art(
        window: BoundingBox,
    ) -> Image.Image:
        """Create a gray placeholder when no art is available."""
        img = Image.new("RGBA", window.size, (80, 80, 80, 255))
        draw = ImageDraw.Draw(img)

        # Subtle gradient
        for y in range(window.height):
            ratio = y / max(1, window.height - 1)
            val = int(60 + 40 * ratio)
            draw.line(
                [(0, y), (window.width, y)],
                fill=(val, val, val, 255),
            )

        # Centered label
        fm = get_font_manager()
        label_font = fm.get("name", int(60 * NATIVE_SCALE))
        label = "NO ART"
        bbox = draw.textbbox((0, 0), label, font=label_font)
        lw = bbox[2] - bbox[0]
        lh = bbox[3] - bbox[1]
        x = (window.width - lw) // 2
        y = (window.height - lh) // 2 - bbox[1]
        draw.text(
            (x + 3, y + 3),
            label,
            font=label_font,
            fill=(0, 0, 0, 100),
        )
        draw.text(
            (x, y),
            label,
            font=label_font,
            fill=(200, 200, 200, 255),
        )
        return img

    # ------------------------------------------------------------------
    # Text rendering at native resolution
    # ------------------------------------------------------------------
    def _native_size(self, purpose: str) -> int:
        """Get font pixel size at native resolution for a purpose."""
        base = DEFAULT_SIZES.get(purpose, 21)
        return round(base * NATIVE_SCALE)

    def _render_name_bar(
        self,
        canvas: Image.Image,
        card: Card,
    ) -> None:
        """Render card name (left) and mana cost symbols (right)."""
        draw = ImageDraw.Draw(canvas)
        box = NATIVE_NAME_BAR
        pad = 50  # px padding inside bar (matches real MTG card inset)

        # Mana cost — right-aligned as symbol images (render first to know width)
        mana_width = 0
        if card.mana_cost:
            symbols = parse_mana_cost(card.mana_cost)
            if symbols:
                sym_size = self._native_size("mana_cost")
                gap = 6
                mana_width = len(symbols) * sym_size + (len(symbols) - 1) * gap
                start_x = box.right - pad - mana_width
                sym_y = box.top + (box.height - sym_size) // 2

                # Drop shadow: -0.2mm left, 0.2mm down, 85% opacity black
                # 0.2mm at native res = 0.2/25.4 * 300 * NATIVE_SCALE ≈ 6px
                shadow_offset = max(3, round(6 * NATIVE_SCALE / 2.45))

                for i, sym in enumerate(symbols):
                    sym_img = get_mana_symbol(sym, sym_size)
                    px = start_x + i * (sym_size + gap)

                    # Draw shadow: dark circle behind symbol
                    shadow = Image.new("RGBA", (sym_size, sym_size), (0, 0, 0, 0))
                    shadow_draw = ImageDraw.Draw(shadow)
                    shadow_draw.ellipse(
                        [0, 0, sym_size - 1, sym_size - 1],
                        fill=(0, 0, 0, 217),  # 85% opacity
                    )
                    canvas.paste(
                        shadow,
                        (px - shadow_offset, sym_y + shadow_offset),
                        shadow,
                    )

                    # Draw symbol on top
                    canvas.paste(sym_img, (px, sym_y), sym_img)

        # Card name — left-aligned, shrink-to-fit around mana cost
        name_text = card.name
        max_name_width = box.width - 2 * pad - mana_width - 20  # gap before symbols
        name_size = self._native_size("card_name")
        min_size = max(40, name_size // 2)

        for _ in range(30):
            name_font = self.fm.get("name", name_size)
            nw = name_font.getlength(name_text)
            if nw <= max_name_width or name_size <= min_size:
                break
            name_size -= 2

        name_font = self.fm.get("name", name_size)

        # Re-acquire draw after symbol pasting
        draw = ImageDraw.Draw(canvas)
        nbbox = draw.textbbox((0, 0), name_text, font=name_font)
        nh = nbbox[3] - nbbox[1]
        name_y = box.top + (box.height - nh) // 2 - nbbox[1]
        draw.text(
            (box.left + pad, name_y),
            name_text,
            font=name_font,
            fill=BLACK,
        )

    def _render_type_bar(
        self,
        canvas: Image.Image,
        card: Card,
    ) -> None:
        """Render type line (left) and set symbol (right)."""
        draw = ImageDraw.Draw(canvas)
        box = NATIVE_TYPE_BAR
        pad = 50

        # Set symbol — right-aligned (render first to know reserved width)
        rarity_code = _rarity_letter(str(card.rarity))
        sym_size = self._native_size("mana_cost")
        set_sym = get_set_symbol(rarity_code, sym_size)
        sym_x = box.right - pad - sym_size
        sym_y = box.top + (box.height - sym_size) // 2
        canvas.paste(set_sym, (sym_x, sym_y), set_sym)

        # Type line — left-aligned, shrink-to-fit
        type_text = card.type_line.replace(" -- ", " \u2014 ")
        max_type_width = sym_x - box.left - pad - 20  # leave gap before symbol

        type_size = self._native_size("type_line")
        min_size = max(40, type_size // 2)

        for _ in range(30):
            type_font = self.fm.get("name", type_size)
            tw = type_font.getlength(type_text)
            if tw <= max_type_width or type_size <= min_size:
                break
            type_size -= 2

        type_font = self.fm.get("name", type_size)
        tbbox = draw.textbbox((0, 0), type_text, font=type_font)
        th = tbbox[3] - tbbox[1]
        ty = box.top + (box.height - th) // 2 - tbbox[1]
        draw.text(
            (box.left + pad, ty),
            type_text,
            font=type_font,
            fill=BLACK,
        )

    def _render_text_box(
        self,
        canvas: Image.Image,
        card: Card,
        has_pt: bool,
    ) -> None:
        """Render oracle text and flavor text via TextEngine.

        Uses dynamic font sizing to fit all content, with inline mana
        symbols, bold keywords, italic reminder text, and flavor separator.
        """
        self.text_engine.render_text_box(
            canvas,
            card.oracle_text or "",
            card.flavor_text,
            card.name,
            NATIVE_TEXT_BOX,
            has_pt=has_pt,
        )

    def _render_text_with_symbols(
        self,
        canvas: Image.Image,
        draw: ImageDraw.ImageDraw,
        text: str,
        font,
        bold_font,
        x: int,
        y: int,
        max_width: int,
        color: tuple[int, int, int],
        line_spacing: int,
        sym_size: int,
    ) -> int:
        """Render a single ability line with inline mana symbols.

        Returns the Y position after the last line.
        """
        # Check if this is a simple keyword (single word, no symbols)
        words_check = text.split()
        is_keyword = (
            len(words_check) == 1
            and not MANA_SYMBOL_RE.search(text)
            and words_check[0][0].isupper()
        )

        if not MANA_SYMBOL_RE.search(text):
            # Plain text — use bold for keywords
            use_font = bold_font if is_keyword else font
            wrapped = _wrap_text(text, use_font, max_width)
            for line in wrapped:
                draw.text((x, y), line, font=use_font, fill=color)
                lbbox = use_font.getbbox(line)
                lh = lbbox[3] - lbbox[1] if lbbox else sym_size
                y += lh + line_spacing
            return y

        # Parse into segments: text and symbol runs
        segments: list[tuple[str, str]] = []
        last_end = 0
        for match in MANA_SYMBOL_RE.finditer(text):
            if match.start() > last_end:
                segments.append(("text", text[last_end : match.start()]))
            segments.append(("symbol", match.group(1)))
            last_end = match.end()
        if last_end < len(text):
            segments.append(("text", text[last_end:]))

        cur_x = x
        cur_y = y
        line_height = sym_size + 4
        sym_gap = round(3 * NATIVE_SCALE)

        for seg_type, content in segments:
            if seg_type == "symbol":
                sym_img = get_mana_symbol(content, sym_size)
                if cur_x + sym_size > x + max_width and cur_x > x:
                    cur_x = x
                    cur_y += line_height + line_spacing
                canvas.paste(sym_img, (cur_x, cur_y), sym_img)
                cur_x += sym_size + sym_gap
            else:
                words = content.split(" ")
                for word in words:
                    if not word:
                        cur_x += round(font.getlength(" "))
                        continue
                    word_w = font.getlength(word)
                    space_w = font.getlength(" ")
                    if cur_x > x:
                        total_w = space_w + word_w
                        prefix = " "
                    else:
                        total_w = word_w
                        prefix = ""
                    if cur_x + total_w > x + max_width and cur_x > x:
                        cur_x = x
                        cur_y += line_height + line_spacing
                        prefix = ""
                    draw.text(
                        (cur_x, cur_y),
                        prefix + word,
                        font=font,
                        fill=color,
                    )
                    cur_x = round(cur_x + font.getlength(prefix + word))

        cur_y += line_height + line_spacing
        return cur_y

    def _render_pt_box(
        self,
        canvas: Image.Image,
        card: Card,
        frame_key: str,
    ) -> None:
        """Load P/T box overlay and render P/T text centered."""
        pt_img = self._load_pt_box(frame_key)

        # Composite at the native PT box position
        canvas.paste(
            pt_img,
            (NATIVE_PT_BOX.left, NATIVE_PT_BOX.top),
            pt_img,
        )

        # Draw P/T text centered within the active region
        draw = ImageDraw.Draw(canvas)
        pt_size = self._native_size("pt_text")
        pt_font = self.fm.get("name_sc", pt_size)  # Card Conjurer uses belerenbsc for P/T
        pt_text = f"{card.power}/{card.toughness}"

        # Active region offset within the overlay
        active = BoundingBox(
            left=NATIVE_PT_BOX.left + PT_OVERLAY_ACTIVE.left,
            top=NATIVE_PT_BOX.top + PT_OVERLAY_ACTIVE.top,
            right=NATIVE_PT_BOX.left + PT_OVERLAY_ACTIVE.right,
            bottom=NATIVE_PT_BOX.top + PT_OVERLAY_ACTIVE.bottom,
        )
        _draw_text_centered(draw, pt_text, pt_font, active, BLACK)

    def _render_collector_bar(
        self,
        canvas: Image.Image,
        card: Card,
        total_cards: int,
        has_pt: bool = False,
    ) -> None:
        """Render collector number, set code, rarity, and artist."""
        draw = ImageDraw.Draw(canvas)
        box = NATIVE_COLLECTOR_BAR
        pad = 30

        coll_size = self._native_size("collector")
        coll_font = self.fm.get("info", coll_size)

        rarity_char = _rarity_letter(str(card.rarity))
        cn = card.collector_number

        # Vertical positioning: creatures center in the bar (PT box pushes things
        # down), non-creatures hug the top edge so text sits near the frame.
        left_text = f"{rarity_char} \u2022 {cn}/{total_cards} {card.set_code} \u2022 EN"
        lbbox = draw.textbbox((0, 0), left_text, font=coll_font)
        lh = lbbox[3] - lbbox[1]
        if has_pt:
            ly = box.top + (box.height - lh) // 2 - lbbox[1]
        else:
            ly = box.top + 8 - lbbox[1]  # near top edge of collector bar

        # Left side: rarity • collector number / total • set code • EN
        draw.text(
            (box.left + pad, ly),
            left_text,
            font=coll_font,
            fill=WHITE,
        )

        # Right side: paintbrush + artist credit
        # On creatures, right-align to PT box edge and nudge down slightly
        artist_name = card.artist or "AI Generated"
        artist_text = f"\u270e {artist_name}"  # ✎ pencil icon as paintbrush stand-in
        abbox = draw.textbbox((0, 0), artist_text, font=coll_font)
        aw = abbox[2] - abbox[0]
        right_edge = NATIVE_PT_BOX.right - pad if has_pt else box.right - pad
        artist_y = ly + 10 if has_pt else ly
        draw.text(
            (right_edge - aw, artist_y),
            artist_text,
            font=coll_font,
            fill=WHITE,
        )

    # ------------------------------------------------------------------
    # Main render pipeline
    # ------------------------------------------------------------------
    def render_card(
        self,
        card: Card,
        set_code: str,
        total_cards: int = 66,
    ) -> Image.Image:
        """Render a single card to a PIL Image.

        Compositing order:
        1. Create RGBA canvas at native resolution (2010x2814)
        2. Load and fit art into the art window
        3. Load frame template (RGBA with transparent art window)
        4. Alpha-composite frame ON TOP (art shows through)
        5. Render all text zones
        6. If creature: composite P/T box overlay + P/T text
        7. Scale to print resolution (822x1122) with LANCZOS
        8. Convert to RGB and return
        """
        t0 = time.perf_counter()
        cn = card.collector_number

        # 1. Canvas
        canvas = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 255))

        # 2. Art
        art_path_resolved = self.resolve_art_path(card, set_code)
        if art_path_resolved is not None:
            try:
                art_img = Image.open(art_path_resolved).convert("RGBA")
                fitted_art = self._fit_art(art_img, NATIVE_ART_WINDOW)
                canvas.paste(
                    fitted_art,
                    (NATIVE_ART_WINDOW.left, NATIVE_ART_WINDOW.top),
                )
                logger.debug(
                    "  Art: %s (%dx%d -> %dx%d)",
                    art_path_resolved.name,
                    art_img.size[0],
                    art_img.size[1],
                    fitted_art.size[0],
                    fitted_art.size[1],
                )
            except Exception as exc:
                logger.warning("  Failed to load art for %s: %s", cn, exc)
                placeholder = self._make_placeholder_art(NATIVE_ART_WINDOW)
                canvas.paste(
                    placeholder,
                    (NATIVE_ART_WINDOW.left, NATIVE_ART_WINDOW.top),
                )
        else:
            logger.info("  No art found for %s — using placeholder", cn)
            placeholder = self._make_placeholder_art(NATIVE_ART_WINDOW)
            canvas.paste(
                placeholder,
                (NATIVE_ART_WINDOW.left, NATIVE_ART_WINDOW.top),
            )

        # 3-4. Frame (alpha composite on top — art shows through)
        frame_key = self.determine_frame_key(card)
        frame_img = self._load_frame(frame_key)
        canvas = Image.alpha_composite(canvas, frame_img)

        # 4b. Legendary crown (mtgrender approach: black base + crown + title cutout)
        # 1. Black underlay: blacks out the frame behind the crown (except title bar)
        # 2. Crown overlay: has title bar punched out so frame name bar shows through
        type_lower = card.type_line.lower()
        is_legendary_creature = "legendary" in type_lower and "creature" in type_lower
        if is_legendary_creature:
            crown = self._load_legendary_crown(card)
            if crown is not None:
                underlay = self._make_crown_underlay()
                canvas = Image.alpha_composite(canvas, underlay)
                canvas = Image.alpha_composite(canvas, crown)

        # 5. Text zones
        self._render_name_bar(canvas, card)
        self._render_type_bar(canvas, card)

        has_pt = card.power is not None and card.toughness is not None
        self._render_text_box(canvas, card, has_pt)

        # 6. P/T box (creatures only)
        if has_pt:
            self._render_pt_box(canvas, card, frame_key)

        # 7. Collector bar
        self._render_collector_bar(canvas, card, total_cards, has_pt=has_pt)

        # 8. Scale to print resolution
        final = canvas.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)

        # 9. Convert to RGB (drop alpha for output)
        final_rgb = final.convert("RGB")

        elapsed = time.perf_counter() - t0
        logger.info(
            "  Rendered %s: %s (%.2fs)",
            cn,
            card.name,
            elapsed,
        )
        return final_rgb

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def render_and_save(
        self,
        card: Card,
        set_code: str,
        total_cards: int = 66,
    ) -> Path:
        """Render a card and save to output/sets/<SET>/renders/.

        Returns the path of the saved PNG.
        """
        from mtgai.io.asset_paths import set_artifact_dir

        img = self.render_card(card, set_code, total_cards)

        # Build the path from the project's set_dir so renders land in
        # the user's asset_folder when configured.
        set_dir = set_artifact_dir()
        dest = set_dir / "renders" / f"{card_slug(card.collector_number, card.name)}.png"
        dest.parent.mkdir(parents=True, exist_ok=True)

        img.save(str(dest), dpi=(300, 300))
        logger.info(
            "  Saved %s (%s bytes)",
            dest.name,
            f"{dest.stat().st_size:,}",
        )
        return dest

    # ------------------------------------------------------------------
    # Batch rendering
    # ------------------------------------------------------------------
    def render_set(
        self,
        set_code: str,
        card_filter: str | None = None,
        dry_run: bool = False,
        force: bool = False,
        progress_callback: Callable[[str, int, int, str, float], None] | None = None,
    ) -> dict:
        """Render all cards in a set.

        Args:
            set_code: The set code (e.g. "ASD").
            card_filter: Optional collector number prefix filter.
            dry_run: If True, log what would be done without rendering.
            force: If True, re-render even if output already exists.

        Returns:
            Summary dict with keys: set_code, rendered, skipped,
            failed, errors, dry_run, elapsed_seconds.
        """
        from mtgai.io.asset_paths import set_artifact_dir

        t0 = time.perf_counter()
        set_dir = set_artifact_dir()
        cards_dir = set_dir / "cards"

        # Discover card files
        card_files = sorted(cards_dir.glob("*.json"))
        if card_filter:
            card_files = [f for f in card_files if f.name.startswith(card_filter)]

        if not card_files:
            logger.warning(
                "No cards found for set %s (filter=%s)",
                set_code,
                card_filter,
            )
            return {
                "set_code": set_code,
                "rendered": 0,
                "skipped": 0,
                "failed": 0,
                "errors": [],
                "dry_run": dry_run,
                "elapsed_seconds": 0.0,
            }

        total_cards = len(list(cards_dir.glob("*.json")))

        rendered = 0
        skipped = 0
        failed = 0
        errors: list[dict] = []

        for card_file in card_files:
            try:
                card = load_card(card_file)
            except Exception as exc:
                logger.error(
                    "Failed to load %s: %s",
                    card_file.name,
                    exc,
                )
                failed += 1
                errors.append(
                    {
                        "card": card_file.name,
                        "error": str(exc),
                    }
                )
                continue

            cn = card.collector_number

            # Check if render already exists. set_dir was resolved at
            # the top of render_set via set_artifact_dir, so this honours
            # the project's asset_folder.
            dest = set_dir / "renders" / f"{card_slug(cn, card.name)}.png"
            if dest.is_file() and not force:
                logger.info(
                    "SKIP %s — render exists: %s",
                    cn,
                    dest.name,
                )
                skipped += 1
                continue

            if dry_run:
                art = self.resolve_art_path(card, set_code)
                art_status = art.name if art else "NO ART"
                logger.info(
                    "DRY RUN %s: %s [frame=%s, art=%s]",
                    cn,
                    card.name,
                    self.determine_frame_key(card),
                    art_status,
                )
                rendered += 1
                continue

            # Render
            try:
                logger.info(
                    "RENDER %s: %s",
                    cn,
                    card.name,
                )
                self.render_and_save(card, set_code, total_cards)
                rendered += 1
                if progress_callback is not None:
                    completed = rendered + skipped + failed
                    progress_callback(cn, completed, len(card_files), f"Rendered {card.name}", 0.0)
            except Exception as exc:
                logger.error(
                    "FAILED %s: %s — %s",
                    cn,
                    card.name,
                    exc,
                )
                failed += 1
                errors.append(
                    {
                        "card": cn,
                        "name": card.name,
                        "error": str(exc),
                    }
                )

        elapsed = time.perf_counter() - t0

        summary = {
            "set_code": set_code,
            "rendered": rendered,
            "skipped": skipped,
            "failed": failed,
            "errors": errors,
            "dry_run": dry_run,
            "elapsed_seconds": round(elapsed, 2),
        }

        # Save summary
        summary_dir = set_dir / "reports"
        summary_dir.mkdir(parents=True, exist_ok=True)
        summary_path = summary_dir / "render-summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        logger.info("Render summary saved: %s", summary_path)

        return summary
