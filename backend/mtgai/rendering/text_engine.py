"""Text rendering engine for MTG cards.

Handles all text rendering on MTG cards including inline mana symbols,
bold keywords, italic reminder text, and dynamic font sizing. Works at
NATIVE resolution (2010x2814) — the card_renderer handles scaling.

Text zones:
    Name bar     — Cinzel font, left-aligned card name
    Mana cost    — right-aligned mana symbol images in name bar
    Type bar     — Cinzel font left-aligned, set symbol right-aligned
    Text box     — oracle text + flavor text with dynamic font sizing
    P/T box      — power/toughness centered on the PT overlay image
    Collector bar — small info text at the bottom
"""

from __future__ import annotations

import logging
import re
from enum import StrEnum

from PIL import Image, ImageDraw, ImageFont

from mtgai.rendering.colors import BLACK, DARK_GRAY
from mtgai.rendering.fonts import FontManager, get_font_manager
from mtgai.rendering.layout import (
    NATIVE_PT_BOX,
    PT_OVERLAY_ACTIVE,
    BoundingBox,
)
from mtgai.rendering.symbol_renderer import (
    get_mana_symbol,
    get_set_symbol,
    parse_mana_cost,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Regex to match mana symbols like {W}, {2}, {T}, {X}, {2/W}, etc.
MANA_SYMBOL_RE = re.compile(r"\{([^}]+)\}")

# Regex to match reminder text in parentheses (>=20 chars inside)
REMINDER_RE = re.compile(r"\([^)]{20,}\)")

# Keywords that can appear as standalone abilities on keyword lines.
# Single-word evergreen and set keywords recognized for bold rendering.
EVERGREEN_KEYWORDS: frozenset[str] = frozenset(
    {
        "Deathtouch",
        "Defender",
        "Double strike",
        "Enchant",
        "Equip",
        "First strike",
        "Flash",
        "Flying",
        "Haste",
        "Hexproof",
        "Indestructible",
        "Intimidate",
        "Lifelink",
        "Menace",
        "Prowess",
        "Reach",
        "Shroud",
        "Trample",
        "Vigilance",
        "Ward",
        # Set-specific keywords
        "Overclock",
    }
)

# Parameterized keywords that appear as "Keyword N" or "Keyword X"
PARAMETERIZED_KEYWORDS: frozenset[str] = frozenset(
    {
        "Salvage",
        "Malfunction",
        "Ward",
        "Scry",
        "Mill",
        "Surveil",
        "Fabricate",
        "Crew",
        "Equip",
        "Cycling",
    }
)

# Padding inside each zone box (pixels at native resolution)
ZONE_PADDING = 20

# Default and minimum font sizes (pixels at native resolution 2010x2814)
# Real MTG rules text is ~8.5pt at print size (63x88mm) = ~85px at native res.
# Bumped to 95 so sparse-text cards (vanilla creatures, simple spells) fill the
# text box at a size matching real MTG cards. Dense cards shrink via find_best_font_size.
# Card Conjurer reference: rules text = 3.52% of 2814 = 99px native
DEFAULT_BODY_SIZE = 99
MIN_BODY_SIZE = 55

# Line spacing as fraction of font size
# Card Conjurer: line height is implicit textSize advance (tight spacing)
LINE_SPACING_RATIO = 0.15

# Card Conjurer: paragraph breaks add textSize * 0.35 extra spacing
PARAGRAPH_SPACING_RATIO = 0.35

# Card Conjurer: flavor separator = 95% of text box width
FLAVOR_SEPARATOR_WIDTH_RATIO = 0.95

# Card Conjurer: inline symbol diameter = textSize * 0.78
SYMBOL_SIZE_RATIO = 0.78

# Gap between inline symbols and adjacent text (px at native res)
# wingedsheep reference: 0.07em margin each side of inline symbols
SYMBOL_GAP = 14


# ---------------------------------------------------------------------------
# Segment types for parsed oracle text
# ---------------------------------------------------------------------------


class SegmentType(StrEnum):
    """Type of a parsed text segment."""

    TEXT = "text"
    SYMBOL = "symbol"
    BOLD_TEXT = "bold_text"
    ITALIC_TEXT = "italic_text"


class TextSegment:
    """A single segment of parsed card text.

    Attributes:
        kind: The segment type (TEXT, SYMBOL, BOLD_TEXT, ITALIC_TEXT).
        content: The text content or symbol code.
    """

    __slots__ = ("content", "kind")

    def __init__(self, kind: SegmentType, content: str) -> None:
        self.kind = kind
        self.content = content

    def __repr__(self) -> str:
        return f"TextSegment({self.kind.value}, {self.content!r})"


class ParsedParagraph:
    """A paragraph of parsed text segments (one oracle ability or line).

    Attributes:
        segments: List of TextSegment making up this paragraph.
        is_keyword_line: Whether this is a keyword-only line (e.g.,
            "Flying, vigilance").
    """

    __slots__ = ("is_keyword_line", "segments")

    def __init__(
        self,
        segments: list[TextSegment],
        *,
        is_keyword_line: bool = False,
    ) -> None:
        self.segments = segments
        self.is_keyword_line = is_keyword_line


# ---------------------------------------------------------------------------
# Wrapped line representation
# ---------------------------------------------------------------------------


class WrappedElement:
    """An element within a wrapped line (text run or symbol).

    Attributes:
        kind: Segment type.
        content: Text string or symbol code.
        width: Measured pixel width of this element.
    """

    __slots__ = ("content", "kind", "width")

    def __init__(
        self,
        kind: SegmentType,
        content: str,
        width: float,
    ) -> None:
        self.kind = kind
        self.content = content
        self.width = width


class WrappedLine:
    """A single line of wrapped text ready for rendering.

    Attributes:
        elements: List of WrappedElement on this line.
        line_height: Pixel height of the tallest element.
    """

    __slots__ = ("elements", "line_height")

    def __init__(
        self,
        elements: list[WrappedElement],
        line_height: float,
    ) -> None:
        self.elements = elements
        self.line_height = line_height


# ---------------------------------------------------------------------------
# TextEngine
# ---------------------------------------------------------------------------


class TextEngine:
    """Text rendering engine for MTG cards at native resolution.

    Handles parsing oracle text into typed segments, measuring and
    word-wrapping, dynamic font sizing, and drawing text with inline
    mana symbols onto PIL Images.

    Usage::

        engine = TextEngine()
        engine.render_text_box(img, oracle_text, flavor_text, card_name, box)
        engine.render_card_name(img, "Elvish Mystic", name_bar_box)
    """

    def __init__(self, font_manager: FontManager | None = None) -> None:
        self.fm = font_manager or get_font_manager()

    # ------------------------------------------------------------------
    # 1. Oracle text parsing
    # ------------------------------------------------------------------

    def parse_oracle(
        self,
        oracle_text: str,
        card_name: str = "",
    ) -> list[ParsedParagraph]:
        """Parse oracle text into paragraphs of typed segments.

        Splits on ``\\n`` for paragraphs, replaces ``~`` with card
        name, and identifies mana symbols, reminder text (italic),
        and keyword lines (bold).

        Args:
            oracle_text: Raw oracle text with ``~``, ``{W}``, etc.
            card_name: Card name to substitute for ``~``.

        Returns:
            List of ParsedParagraph, one per ``\\n``-delimited line.
        """
        if not oracle_text:
            return []

        # Normalize literal "\n" (two chars: backslash + n) to actual newlines.
        # Some card JSONs store escaped newlines that json.load preserves as literal.
        text = oracle_text.replace("\\n", "\n")

        # Replace self-reference
        text = text.replace("~", card_name) if card_name else text

        paragraphs: list[ParsedParagraph] = []
        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if not line:
                continue

            is_kw = self._is_keyword_line(line)
            # Real MTG cards do NOT bold keywords — same weight as rules text
            segments = self._parse_line_segments(line, bold_all=False)
            paragraphs.append(ParsedParagraph(segments, is_keyword_line=is_kw))

        return paragraphs

    def parse_flavor(self, flavor_text: str) -> list[ParsedParagraph]:
        """Parse flavor text into italic paragraphs.

        Args:
            flavor_text: Raw flavor text string.

        Returns:
            List of ParsedParagraph (all segments are ITALIC_TEXT).
        """
        if not flavor_text:
            return []

        # Normalize literal "\n" to actual newlines
        flavor_text = flavor_text.replace("\\n", "\n")

        paragraphs: list[ParsedParagraph] = []
        for raw_line in flavor_text.split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            segments = [TextSegment(SegmentType.ITALIC_TEXT, line)]
            paragraphs.append(ParsedParagraph(segments))

        return paragraphs

    def _is_keyword_line(self, line: str) -> bool:
        """Check if a line is a keyword ability line.

        A keyword line is a comma-separated list of keyword abilities,
        like ``"Flying"`` or ``"Vigilance, lifelink"`` or
        ``"Salvage 2"`` or ``"Malfunction 1 (...reminder...)"``

        Does NOT match lines with colons (activated abilities) or
        "Whenever"/"When"/"At" (triggered abilities).
        """
        # Strip reminder text for keyword detection
        stripped = REMINDER_RE.sub("", line).strip()
        # Remove trailing comma/period after stripping reminder
        stripped = stripped.rstrip(",. ")

        # Activated/triggered ability patterns are not keyword lines
        if ":" in stripped:
            return False
        triggers = ("whenever ", "when ", "at the ", "if ", "as ")
        lower = stripped.lower()
        for trigger in triggers:
            if lower.startswith(trigger):
                return False

        # Check each comma-separated part
        parts = [p.strip() for p in stripped.split(",")]
        for part in parts:
            if not part:
                continue
            words = part.split()
            if not words:
                continue
            # First word should be a known keyword (case-insensitive)
            kw = words[0]
            kw_title = kw.capitalize()
            if kw_title in EVERGREEN_KEYWORDS:
                continue
            if kw_title in PARAMETERIZED_KEYWORDS:
                # Allow "Salvage 4", "Ward {1}{U}", etc.
                continue
            # Unknown — not a keyword line
            return False

        return True

    def _parse_line_segments(
        self,
        line: str,
        *,
        bold_all: bool = False,
    ) -> list[TextSegment]:
        """Parse a single line into text, symbol, and italic segments.

        Args:
            line: A single line of oracle text (no newlines).
            bold_all: If True, non-symbol/non-italic text is BOLD_TEXT.

        Returns:
            List of TextSegment.
        """
        segments: list[TextSegment] = []

        # Build a list of (start, end, type, content) spans
        spans: list[tuple[int, int, SegmentType, str]] = []

        # Find mana symbols
        for m in MANA_SYMBOL_RE.finditer(line):
            spans.append((m.start(), m.end(), SegmentType.SYMBOL, m.group(1)))

        # Find reminder text
        for m in REMINDER_RE.finditer(line):
            spans.append(
                (
                    m.start(),
                    m.end(),
                    SegmentType.ITALIC_TEXT,
                    m.group(0),
                )
            )

        # Sort spans by start position
        spans.sort(key=lambda s: s[0])

        # Remove overlapping spans (symbols inside reminder text)
        filtered: list[tuple[int, int, SegmentType, str]] = []
        last_end = 0
        for start, end, kind, content in spans:
            if start < last_end:
                # This span overlaps with the previous — skip symbols
                # inside reminder text, but keep the reminder
                if kind == SegmentType.SYMBOL:
                    continue
                # If it's a reminder overlapping a symbol, we still
                # keep the reminder and the symbol was already added.
                # Let's rebuild: drop any previously added symbols
                # that fall within this reminder's range.
                filtered = [f for f in filtered if not (f[0] >= start and f[1] <= end)]
            filtered.append((start, end, kind, content))
            last_end = max(last_end, end)

        # Fill gaps with text segments
        text_kind = SegmentType.BOLD_TEXT if bold_all else SegmentType.TEXT
        pos = 0
        for start, end, kind, content in filtered:
            if start > pos:
                gap_text = line[pos:start]
                if gap_text:
                    segments.append(TextSegment(text_kind, gap_text))
            segments.append(TextSegment(kind, content))
            pos = end

        # Trailing text
        if pos < len(line):
            trailing = line[pos:]
            if trailing:
                segments.append(TextSegment(text_kind, trailing))

        return segments

    # ------------------------------------------------------------------
    # 2. Segment measurement
    # ------------------------------------------------------------------

    def measure_segment(
        self,
        segment: TextSegment,
        font_size: int,
    ) -> float:
        """Measure the pixel width of a single segment.

        Args:
            segment: The text segment to measure.
            font_size: Body font size in pixels (used to derive all
                related sizes).

        Returns:
            Width in pixels.
        """
        if segment.kind == SegmentType.SYMBOL:
            sym_size = int(font_size * SYMBOL_SIZE_RATIO)
            return float(sym_size + SYMBOL_GAP)

        font = self._font_for_segment(segment, font_size)
        return font.getlength(segment.content)

    def _font_for_segment(
        self,
        segment: TextSegment,
        font_size: int,
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """Get the appropriate font for a segment type and size."""
        if segment.kind == SegmentType.BOLD_TEXT:
            return self.fm.get("body_bold", font_size)
        if segment.kind == SegmentType.ITALIC_TEXT:
            return self.fm.get("body_italic", font_size)
        return self.fm.get("body", font_size)

    # ------------------------------------------------------------------
    # 3. Word wrapping
    # ------------------------------------------------------------------

    def wrap_paragraph(
        self,
        paragraph: ParsedParagraph,
        font_size: int,
        max_width: int,
    ) -> list[WrappedLine]:
        """Wrap a paragraph's segments into lines fitting max_width.

        Text segments break at word boundaries. Symbols are
        unbreakable atomic elements. Mixed text+symbol content
        flows inline on the same line.

        Args:
            paragraph: Parsed paragraph with segments.
            font_size: Body text font size in pixels.
            max_width: Maximum line width in pixels.

        Returns:
            List of WrappedLine.
        """
        sym_size = int(font_size * SYMBOL_SIZE_RATIO)
        line_h = float(sym_size + 2)

        # Flatten segments into word-level elements
        word_elements = self._flatten_to_words(paragraph, font_size)

        if not word_elements:
            return []

        # Greedy line-filling algorithm
        lines: list[WrappedLine] = []
        current_elems: list[WrappedElement] = []
        current_width = 0.0

        for elem in word_elements:
            elem_width = elem.width
            needed = elem_width
            if current_elems and elem.kind != SegmentType.SYMBOL:
                # Add space before non-symbol text if not at line start
                # But only if the previous element was also non-symbol
                # or this is a new word
                pass  # space is already included in content

            # Check if element fits on current line
            if current_elems and current_width + needed > max_width:
                # Emit current line and start new one
                lines.append(WrappedLine(current_elems, line_h))
                current_elems = []
                current_width = 0.0

                # Strip leading space from text elements at line start
                if elem.kind != SegmentType.SYMBOL and elem.content.startswith(" "):
                    content = elem.content.lstrip(" ")
                    font = self._font_for_element(elem, font_size)
                    w = font.getlength(content) if content else 0.0
                    elem = WrappedElement(elem.kind, content, w)
                    needed = w

            current_elems.append(elem)
            current_width += needed

        if current_elems:
            lines.append(WrappedLine(current_elems, line_h))

        return lines

    def _flatten_to_words(
        self,
        paragraph: ParsedParagraph,
        font_size: int,
    ) -> list[WrappedElement]:
        """Flatten a paragraph's segments into word-level elements.

        Text segments are split at word boundaries; each word becomes
        a separate element with a leading space (except the first word
        on a line). Symbols stay as single elements.
        """
        elements: list[WrappedElement] = []
        sym_size = int(font_size * SYMBOL_SIZE_RATIO)

        for seg in paragraph.segments:
            if seg.kind == SegmentType.SYMBOL:
                w = float(sym_size + SYMBOL_GAP)
                elements.append(WrappedElement(SegmentType.SYMBOL, seg.content, w))
                continue

            font = self._font_for_segment(seg, font_size)
            text = seg.content

            # Split into words preserving leading whitespace info
            # We need to handle spaces carefully: if the text starts
            # with a space, the first word gets it. Words after the
            # first get a leading space.
            if not text.strip():
                # Pure whitespace — measure as-is
                w = font.getlength(text)
                elements.append(WrappedElement(seg.kind, text, w))
                continue

            # Split preserving leading space on subsequent words
            words = text.split(" ")
            first = True
            for i, word in enumerate(words):
                if i == 0 and not word:
                    # Text starts with space — add it to the next word
                    first = False
                    continue
                if not word:
                    continue

                if first and i == 0:
                    # Very first word — no leading space needed
                    # unless text starts with space
                    content = word
                    first = False
                else:
                    content = " " + word

                w = font.getlength(content)
                elements.append(WrappedElement(seg.kind, content, w))

            # Preserve trailing space (e.g., "Add " before a symbol)
            if text.endswith(" "):
                space_w = font.getlength(" ")
                elements.append(WrappedElement(seg.kind, " ", space_w))

        return elements

    def _font_for_element(
        self,
        elem: WrappedElement,
        font_size: int,
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """Get the font for a WrappedElement."""
        if elem.kind == SegmentType.BOLD_TEXT:
            return self.fm.get("body_bold", font_size)
        if elem.kind == SegmentType.ITALIC_TEXT:
            return self.fm.get("body_italic", font_size)
        return self.fm.get("body", font_size)

    # ------------------------------------------------------------------
    # 4. Height measurement
    # ------------------------------------------------------------------

    def measure_text_height(
        self,
        paragraphs: list[ParsedParagraph],
        font_size: int,
        max_width: int,
    ) -> float:
        """Measure total height of paragraphs when wrapped.

        Args:
            paragraphs: List of ParsedParagraph to measure.
            font_size: Body font size in pixels.
            max_width: Available width for wrapping.

        Returns:
            Total height in pixels including inter-paragraph spacing.
        """
        if not paragraphs:
            return 0.0

        line_spacing = font_size * LINE_SPACING_RATIO
        para_spacing = font_size * PARAGRAPH_SPACING_RATIO
        total = 0.0

        for i, para in enumerate(paragraphs):
            lines = self.wrap_paragraph(para, font_size, max_width)
            for j, wl in enumerate(lines):
                total += wl.line_height
                if j < len(lines) - 1:
                    total += line_spacing
            if i < len(paragraphs) - 1:
                total += para_spacing

        return total

    def _count_wrapped_lines(
        self,
        oracle_paras: list[ParsedParagraph],
        flavor_paras: list[ParsedParagraph],
        font_size: int,
        max_width: int,
    ) -> int:
        """Count total wrapped lines across all paragraphs."""
        total = 0
        for para in oracle_paras:
            total += len(self.wrap_paragraph(para, font_size, max_width))
        for para in flavor_paras:
            total += len(self.wrap_paragraph(para, font_size, max_width))
        return total

    # ------------------------------------------------------------------
    # 5. Dynamic font sizing
    # ------------------------------------------------------------------

    def find_best_font_size(
        self,
        oracle_paragraphs: list[ParsedParagraph],
        flavor_paragraphs: list[ParsedParagraph],
        box: BoundingBox,
        default_size: int = DEFAULT_BODY_SIZE,
        min_size: int = MIN_BODY_SIZE,
    ) -> int:
        """Find the largest font size where all text fits in the box.

        Tries sizes from default_size down to min_size. The box
        height accounts for padding, the flavor separator line,
        and inter-section spacing.

        Args:
            oracle_paragraphs: Parsed oracle text paragraphs.
            flavor_paragraphs: Parsed flavor text paragraphs.
            box: BoundingBox of the text zone (before padding).
            default_size: Starting (largest) font size to try.
            min_size: Smallest acceptable font size.

        Returns:
            Best font size in pixels.
        """
        padded = box.padded(ZONE_PADDING)
        available_w = padded.width
        available_h = padded.height

        for size in range(default_size, min_size - 1, -1):
            height = self._total_content_height(
                oracle_paragraphs, flavor_paragraphs, size, available_w
            )
            if height <= available_h:
                return size

        return min_size

    def _total_content_height(
        self,
        oracle_paras: list[ParsedParagraph],
        flavor_paras: list[ParsedParagraph],
        font_size: int,
        max_width: int,
    ) -> float:
        """Calculate total height of oracle + separator + flavor."""
        total = 0.0

        if oracle_paras:
            total += self.measure_text_height(oracle_paras, font_size, max_width)

        if oracle_paras and flavor_paras:
            # Separator line + more space above (2x) than below (1x)
            separator_space = font_size * PARAGRAPH_SPACING_RATIO * 3
            separator_line = 6.0
            total += separator_space + separator_line

        if flavor_paras:
            total += self.measure_text_height(flavor_paras, font_size, max_width)

        return total

    def _would_overlap_pt(
        self,
        oracle_paras: list[ParsedParagraph],
        flavor_paras: list[ParsedParagraph],
        font_size: int,
        padded: BoundingBox,
    ) -> bool:
        """Check if rendered text would overlap the P/T box.

        Simulates the full text layout (with vertical centering) and checks
        whether any line's bounding box intersects the P/T box region.
        Only lines whose right edge extends past the P/T box left edge count.

        Args:
            oracle_paras: Parsed oracle paragraphs.
            flavor_paras: Parsed flavor paragraphs.
            font_size: Font size to test.
            padded: Padded text box bounding box.

        Returns:
            True if any text line would visually overlap the P/T box.
        """
        max_width = padded.width
        line_spacing = font_size * LINE_SPACING_RATIO
        para_spacing = font_size * PARAGRAPH_SPACING_RATIO

        # Compute starting Y with vertical centering (same logic as render)
        total_h = self._total_content_height(oracle_paras, flavor_paras, font_size, max_width)
        available_h = padded.height
        if total_h < available_h:
            y_offset = (available_h - total_h) / 2
            cur_y = float(padded.top + y_offset)
        else:
            cur_y = float(padded.top)

        # P/T overlap boundary — use active region left edge with 15px margin
        pt_y_top = float(NATIVE_PT_BOX.top)
        pt_x_left = float(NATIVE_PT_BOX.left + PT_OVERLAY_ACTIVE.left - 15)

        # Walk all paragraphs: oracle, then separator gap, then flavor
        all_sections: list[tuple[list[ParsedParagraph], float]] = []
        if oracle_paras:
            all_sections.append((oracle_paras, cur_y))
        if oracle_paras and flavor_paras:
            # Account for separator space (same as render_text_box)
            oracle_h = self.measure_text_height(oracle_paras, font_size, max_width)
            separator_space = para_spacing * 2 + 6.0 + para_spacing
            flavor_start = cur_y + oracle_h + separator_space
            all_sections.append((flavor_paras, flavor_start))
        elif flavor_paras:
            all_sections.append((flavor_paras, cur_y))

        for paras, section_y in all_sections:
            y = section_y
            for p_idx, para in enumerate(paras):
                lines = self.wrap_paragraph(para, font_size, max_width)
                for l_idx, wl in enumerate(lines):
                    line_bottom = y + wl.line_height
                    # Only check lines that are in the P/T vertical zone
                    if line_bottom > pt_y_top:
                        # Compute right edge of this line
                        line_width = sum(e.width for e in wl.elements)
                        line_right = padded.left + line_width
                        if line_right > pt_x_left:
                            return True
                    y += wl.line_height
                    if l_idx < len(lines) - 1:
                        y += line_spacing
                if p_idx < len(paras) - 1:
                    y += para_spacing

        return False

    # ------------------------------------------------------------------
    # 6. Rendering primitives
    # ------------------------------------------------------------------

    def draw_wrapped_paragraphs(
        self,
        img: Image.Image,
        paragraphs: list[ParsedParagraph],
        font_size: int,
        x: int,
        y: int,
        max_width: int,
        color: tuple[int, int, int] = BLACK,
    ) -> float:
        """Draw wrapped paragraphs onto an image.

        Renders text with proper fonts, inline mana symbols, and
        inter-paragraph spacing.

        Args:
            img: PIL Image to draw on.
            paragraphs: Parsed paragraphs to render.
            font_size: Body font size in pixels.
            x: Left X coordinate.
            y: Top Y coordinate.
            max_width: Maximum line width.
            color: Default text color (RGB tuple).

        Returns:
            Y coordinate after the last drawn line.
        """
        draw = ImageDraw.Draw(img)
        line_spacing = font_size * LINE_SPACING_RATIO
        para_spacing = font_size * PARAGRAPH_SPACING_RATIO
        sym_size = int(font_size * SYMBOL_SIZE_RATIO)
        cur_y = float(y)

        for p_idx, para in enumerate(paragraphs):
            lines = self.wrap_paragraph(para, font_size, max_width)

            for l_idx, wl in enumerate(lines):
                cur_x = float(x)

                for elem in wl.elements:
                    if elem.kind == SegmentType.SYMBOL:
                        sym_img = get_mana_symbol(elem.content, sym_size)
                        # Vertically center symbol relative to line
                        sym_y = int(cur_y + (wl.line_height - sym_size) / 2)
                        img.paste(
                            sym_img,
                            (int(cur_x), sym_y),
                            sym_img,
                        )
                        cur_x += elem.width
                    else:
                        font = self._font_for_element(elem, font_size)
                        elem_color = color
                        if elem.kind == SegmentType.ITALIC_TEXT:
                            elem_color = DARK_GRAY
                        # Draw text baseline-aligned within line
                        draw.text(
                            (int(cur_x), int(cur_y)),
                            elem.content,
                            font=font,
                            fill=elem_color,
                        )
                        cur_x += elem.width

                # Re-acquire draw after symbol pasting
                draw = ImageDraw.Draw(img)

                cur_y += wl.line_height
                if l_idx < len(lines) - 1:
                    cur_y += line_spacing

            if p_idx < len(paragraphs) - 1:
                cur_y += para_spacing

        return cur_y

    def _draw_flavor_separator(
        self,
        draw: ImageDraw.ImageDraw,
        y: float,
        box_left: int,
        box_right: int,
    ) -> None:
        """Draw a centered horizontal separator line for flavor text.

        A thin line approximately 60% of the text box width, centered
        horizontally.
        """
        box_w = box_right - box_left
        sep_w = int(box_w * FLAVOR_SEPARATOR_WIDTH_RATIO)
        sep_left = box_left + (box_w - sep_w) // 2
        sep_right = sep_left + sep_w
        # Subtle separator matching real MTG cards
        draw.line(
            [(sep_left, int(y)), (sep_right, int(y))],
            fill=(140, 140, 140),
            width=3,
        )

    # ------------------------------------------------------------------
    # 7. High-level rendering helpers
    # ------------------------------------------------------------------

    def render_card_name(
        self,
        img: Image.Image,
        name: str,
        box: BoundingBox,
    ) -> None:
        """Render card name in the name bar, left-aligned.

        Uses the Cinzel (name) font. Shrinks font size if the name
        is too long to fit within the box width (minus padding and
        space reserved for mana cost).

        Args:
            img: PIL Image to draw on.
            name: Card name string.
            box: BoundingBox of the name bar zone.
        """
        draw = ImageDraw.Draw(img)
        padded = box.padded(ZONE_PADDING)

        # Reserve ~40% of name bar width for mana cost on the right
        max_name_width = int(padded.width * 0.60)

        # Start at a default size, shrink if needed
        default_size = int(box.height * 0.50)
        font_size = default_size

        for _ in range(20):
            font = self.fm.get("name", font_size)
            name_width = font.getlength(name)
            if name_width <= max_name_width or font_size <= 20:
                break
            font_size -= 1

        font = self.fm.get("name", font_size)

        # Vertically center in the box
        bbox = draw.textbbox((0, 0), name, font=font)
        text_h = bbox[3] - bbox[1]
        text_y = box.center_y - text_h // 2 - bbox[1]

        draw.text(
            (padded.left, text_y),
            name,
            font=font,
            fill=BLACK,
        )

    def render_mana_cost(
        self,
        img: Image.Image,
        mana_cost: str | None,
        box: BoundingBox,
    ) -> None:
        """Render mana cost symbols right-aligned in the name bar.

        Parses ``{2}{G}{G}`` into individual symbols and renders
        each as an image positioned from right to left.

        Args:
            img: PIL Image to draw on.
            mana_cost: Mana cost string like ``"{2}{G}{G}"``, or None.
            box: BoundingBox of the name bar zone.
        """
        if not mana_cost:
            return

        symbols = parse_mana_cost(mana_cost)
        if not symbols:
            return

        # Symbol size: proportional to box height
        symbol_size = int(box.height * 0.50)
        gap = max(3, symbol_size // 10)

        # Calculate total width
        total_w = len(symbols) * symbol_size + (len(symbols) - 1) * gap

        # Right-aligned with padding
        right_edge = box.right - ZONE_PADDING
        start_x = right_edge - total_w
        y_pos = box.center_y - symbol_size // 2

        for i, symbol in enumerate(symbols):
            sym_img = get_mana_symbol(symbol, symbol_size)
            paste_x = start_x + i * (symbol_size + gap)
            img.paste(sym_img, (paste_x, y_pos), sym_img)

    def render_type_line(
        self,
        img: Image.Image,
        type_line: str,
        box: BoundingBox,
    ) -> None:
        """Render type line text left-aligned in the type bar.

        Uses the Cinzel (name) font. Leaves room on the right for
        the set symbol.

        Args:
            img: PIL Image to draw on.
            type_line: Type line string (e.g., ``"Creature -- Human Soldier"``).
            box: BoundingBox of the type bar zone.
        """
        draw = ImageDraw.Draw(img)
        padded = box.padded(ZONE_PADDING)

        # Replace "--" with em-dash for display
        display_type = type_line.replace(" -- ", " \u2014 ")

        # Reserve ~20% for set symbol on the right
        max_width = int(padded.width * 0.80)

        # Start at default size, shrink if needed
        default_size = int(box.height * 0.45)
        font_size = default_size

        for _ in range(20):
            font = self.fm.get("name", font_size)
            text_w = font.getlength(display_type)
            if text_w <= max_width or font_size <= 18:
                break
            font_size -= 1

        font = self.fm.get("name", font_size)

        # Vertically center
        bbox = draw.textbbox((0, 0), display_type, font=font)
        text_h = bbox[3] - bbox[1]
        text_y = box.center_y - text_h // 2 - bbox[1]

        draw.text(
            (padded.left, text_y),
            display_type,
            font=font,
            fill=BLACK,
        )

    def render_set_symbol(
        self,
        img: Image.Image,
        rarity: str,
        box: BoundingBox,
    ) -> None:
        """Render set symbol right-aligned in the type bar.

        Args:
            img: PIL Image to draw on.
            rarity: Rarity code (``"C"``, ``"U"``, ``"R"``, ``"M"``).
            box: BoundingBox of the type bar zone.
        """
        # Symbol size: proportional to box height
        symbol_size = int(box.height * 0.55)

        # Map full rarity names to single-char codes
        rarity_map: dict[str, str] = {
            "common": "C",
            "uncommon": "U",
            "rare": "R",
            "mythic": "M",
        }
        code = rarity_map.get(rarity.lower(), rarity.upper())

        sym_img = get_set_symbol(code, symbol_size)

        # Right-aligned with padding, vertically centered
        sym_x = box.right - ZONE_PADDING - symbol_size
        sym_y = box.center_y - symbol_size // 2

        img.paste(sym_img, (sym_x, sym_y), sym_img)

    def render_text_box(
        self,
        img: Image.Image,
        oracle_text: str,
        flavor_text: str | None,
        card_name: str,
        box: BoundingBox,
        has_pt: bool = False,
    ) -> None:
        """Render the full text box: oracle + separator + flavor.

        Uses a unified iterative fit loop that evaluates all constraints
        (box height, PT overlap, line count) together at each content
        reduction level before deciding to escalate:

            Level 0: oracle + reminder + flavor  (full content)
            Level 1: oracle + reminder           (drop flavor)
            Level 2: oracle only                 (drop flavor + strip reminder)

        Args:
            img: PIL Image to draw on.
            oracle_text: Card oracle text (may be empty).
            flavor_text: Card flavor text (may be None or empty).
            card_name: Card name for ``~`` substitution.
            box: BoundingBox of the text box zone.
            has_pt: If True, check for P/T box overlap and shrink to avoid it.
        """
        max_lines = 8
        padded = box.padded(ZONE_PADDING)
        max_width = padded.width

        # Pre-parse content for each reduction level
        full_oracle_paras = self.parse_oracle(oracle_text, card_name)
        full_flavor_paras = self.parse_flavor(flavor_text or "")

        if not full_oracle_paras and not full_flavor_paras:
            return

        has_flavor = bool(full_flavor_paras)
        has_reminder = bool(REMINDER_RE.search(oracle_text or ""))
        stripped_oracle = REMINDER_RE.sub("", oracle_text or "").strip() if has_reminder else None
        stripped_oracle_paras = (
            self.parse_oracle(stripped_oracle, card_name) if stripped_oracle else None
        )

        # Content reduction levels: (oracle_paras, flavor_paras, label)
        levels: list[tuple[list[ParsedParagraph], list[ParsedParagraph], str]] = [
            (full_oracle_paras, full_flavor_paras, "full"),
        ]
        if has_flavor:
            levels.append((full_oracle_paras, [], "no flavor"))
        if has_reminder:
            levels.append((stripped_oracle_paras, [], "no flavor + no reminder"))  # type: ignore[arg-type]

        # Unified fit loop — evaluate all constraints at each level
        oracle_paras = full_oracle_paras
        flavor_paras = full_flavor_paras
        font_size = DEFAULT_BODY_SIZE

        for oracle_paras, flavor_paras, label in levels:
            # Find largest font where content fits the text box height
            font_size = self.find_best_font_size(oracle_paras, flavor_paras, box)

            # If creature, shrink further until no PT overlap
            if has_pt:
                while font_size > MIN_BODY_SIZE and self._would_overlap_pt(
                    oracle_paras, flavor_paras, font_size, padded
                ):
                    font_size -= 1

            # Check line count at the final render font size
            total_lines = self._count_wrapped_lines(
                oracle_paras, flavor_paras, font_size, max_width
            )

            if total_lines <= max_lines:
                break  # all constraints satisfied

            logger.info(
                "  Content level '%s': %d lines > %d max, escalating", label, total_lines, max_lines
            )

        # Post-loop warnings
        if has_pt and self._would_overlap_pt(oracle_paras, flavor_paras, font_size, padded):
            logger.warning("  Text still overlaps PT box at min font size %d", MIN_BODY_SIZE)
        if self._count_wrapped_lines(oracle_paras, flavor_paras, font_size, max_width) > max_lines:
            logger.warning("  Still > %d lines at max content reduction", max_lines)

        # --- Render with final parameters ---
        para_spacing = font_size * PARAGRAPH_SPACING_RATIO

        # Card Conjurer: true vertical centering (containerHeight - totalTextHeight) / 2
        total_h = self._total_content_height(oracle_paras, flavor_paras, font_size, max_width)
        available_h = padded.height
        if total_h < available_h:
            y_offset = (available_h - total_h) / 2
            cur_y = float(padded.top + y_offset)
        else:
            cur_y = float(padded.top)

        # Draw oracle text
        if oracle_paras:
            cur_y = self.draw_wrapped_paragraphs(
                img,
                oracle_paras,
                font_size,
                padded.left,
                int(cur_y),
                max_width,
                color=BLACK,
            )

        # Draw flavor separator + flavor text
        if flavor_paras:
            if oracle_paras:
                # More space above separator to push it down
                cur_y += para_spacing * 2
                # Draw separator line
                draw = ImageDraw.Draw(img)
                self._draw_flavor_separator(draw, cur_y, padded.left, padded.right)
                cur_y += 6.0  # separator line height
                cur_y += para_spacing

            self.draw_wrapped_paragraphs(
                img,
                flavor_paras,
                font_size,
                padded.left,
                int(cur_y),
                max_width,
                color=DARK_GRAY,
            )

    def render_pt_box(
        self,
        img: Image.Image,
        power: str | None,
        toughness: str | None,
        pt_img: Image.Image,
    ) -> None:
        """Render P/T text centered on the P/T box overlay image.

        The pt_img is composited onto the card separately; this method
        draws the P/T text onto that overlay image at the correct
        position within its active region.

        Args:
            img: The P/T overlay image (not the main card image).
            power: Power string (e.g., ``"4"`` or ``"*"``).
            toughness: Toughness string (e.g., ``"5"`` or ``"*"``).
            pt_img: The P/T overlay image to draw text onto.
        """
        if power is None or toughness is None:
            return

        pt_text = f"{power}/{toughness}"

        # Use the active area within the PT overlay for centering
        active = PT_OVERLAY_ACTIVE
        draw = ImageDraw.Draw(pt_img)

        # Size font relative to the active area height
        font_size = int(active.height * 0.55)
        font = self.fm.get("info_bold", font_size)

        # Measure and center
        bbox = draw.textbbox((0, 0), pt_text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        text_x = active.center_x - text_w // 2 - bbox[0]
        text_y = active.center_y - text_h // 2 - bbox[1]

        draw.text((text_x, text_y), pt_text, font=font, fill=BLACK)

    def render_collector_info(
        self,
        img: Image.Image,
        collector_number: str,
        set_code: str,
        rarity: str,
        total_cards: int,
        box: BoundingBox,
    ) -> None:
        """Render collector info text in the bottom bar.

        Format: ``"W-C-01/66 ASD * C"`` (using bullet separator).

        Args:
            img: PIL Image to draw on.
            collector_number: Collector number string.
            set_code: Three-letter set code.
            rarity: Rarity string (full name or single char).
            total_cards: Total cards in the set.
            box: BoundingBox of the collector bar zone.
        """
        draw = ImageDraw.Draw(img)
        padded = box.padded(ZONE_PADDING)

        # Map rarity to display character
        rarity_map: dict[str, str] = {
            "common": "C",
            "uncommon": "U",
            "rare": "R",
            "mythic": "M",
        }
        rarity_char = rarity_map.get(rarity.lower(), rarity.upper()[:1])

        text = f"{collector_number}/{total_cards} {set_code} \u2022 {rarity_char}"

        # Font size: proportional to box height
        font_size = int(padded.height * 0.55)
        font = self.fm.get("info", font_size)

        # Vertically center
        bbox = draw.textbbox((0, 0), text, font=font)
        text_h = bbox[3] - bbox[1]
        text_y = box.center_y - text_h // 2 - bbox[1]

        # Left-aligned with padding
        draw.text(
            (padded.left, text_y),
            text,
            font=font,
            fill=(200, 200, 200),  # light gray on dark bar
        )

        # Artist credit on the right side
        artist_text = "AI Generated"
        artist_bbox = draw.textbbox((0, 0), artist_text, font=font)
        artist_w = artist_bbox[2] - artist_bbox[0]
        artist_x = padded.right - artist_w
        draw.text(
            (artist_x, text_y),
            artist_text,
            font=font,
            fill=(200, 200, 200),
        )
