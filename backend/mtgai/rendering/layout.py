"""Print spec constants and bounding box definitions for M15 card zones.

Zone coordinates were determined by pixel analysis of the M15 frame images
(2010x2814 RGBA PNGs) and their companion mask files (Title, Type, Rules, etc.).
The transparent region (alpha == 0) in the frames is where card art shows through.

Two coordinate systems are provided:
- Native: 2010x2814 (raw frame image resolution)
- Scaled:  822x1122 (target print resolution at 300 DPI for MPC poker-size cards)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root — 4 levels up: rendering/ -> mtgai/ -> backend/ -> PROJECT_ROOT
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# ---------------------------------------------------------------------------
# Print spec constants
# ---------------------------------------------------------------------------
FRAME_W = 2010  # native frame image width (px)
FRAME_H = 2814  # native frame image height (px)
CANVAS_W = 822  # target print width at 300 DPI (63.5mm + 3mm bleed each side)
CANVAS_H = 1122  # target print height at 300 DPI (88.9mm + 3mm bleed each side)
DPI = 300

SCALE_X = CANVAS_W / FRAME_W  # ~0.4090
SCALE_Y = CANVAS_H / FRAME_H  # ~0.3987

# Bleed and border at print resolution
BLEED = 36  # 3mm bleed in px at 300 DPI
BORDER = 12  # visible card border thickness at print resolution


# ---------------------------------------------------------------------------
# BoundingBox dataclass
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Axis-aligned bounding box in pixel coordinates.

    All values are in pixels. Use ``scaled()`` to convert from native
    frame coordinates (2010x2814) to print coordinates (822x1122).
    """

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center_x(self) -> int:
        return (self.left + self.right) // 2

    @property
    def center_y(self) -> int:
        return (self.top + self.bottom) // 2

    @property
    def size(self) -> tuple[int, int]:
        """(width, height) tuple."""
        return (self.width, self.height)

    def as_tuple(self) -> tuple[int, int, int, int]:
        """Return (left, top, right, bottom) for use with PIL."""
        return (self.left, self.top, self.right, self.bottom)

    def padded(self, px: int) -> BoundingBox:
        """Return a new box inset by ``px`` pixels on all sides."""
        return BoundingBox(
            left=self.left + px,
            top=self.top + px,
            right=self.right - px,
            bottom=self.bottom - px,
        )

    def scaled(self, sx: float = SCALE_X, sy: float = SCALE_Y) -> BoundingBox:
        """Scale from native frame coords to print coords."""
        return BoundingBox(
            left=round(self.left * sx),
            top=round(self.top * sy),
            right=round(self.right * sx),
            bottom=round(self.bottom * sy),
        )

    def __repr__(self) -> str:
        return (
            f"BoundingBox(left={self.left}, top={self.top}, "
            f"right={self.right}, bottom={self.bottom}) "
            f"[{self.width}x{self.height}]"
        )


# ---------------------------------------------------------------------------
# Zone definitions at NATIVE resolution (2010 x 2814)
#
# Determined from pixel analysis of m15FrameW.png and mask images:
#   m15MaskTitle.png  -> rows 134-296,  cols 119-1890  (name/title bar)
#   m15FrameW.png     -> alpha==0 region: rows 319-1560, cols 155-1854  (art window)
#   m15MaskType.png   -> rows 1583-1745, cols 119-1889  (type bar)
#   m15MaskRules.png  -> rows 1760-2595, cols 148-1861  (text/rules box)
#   m15PTW.png        -> 377x206 overlay, positioned at bottom-right of rules box
#   Border mask       -> outer border rows 0-79 / 2610-2813, cols 0-79 / 1930-2009
#   Brightness scan   -> collector bar (dark region) starts at row 2610
# ---------------------------------------------------------------------------

# Outer border of the card (everything outside this is bleed)
NATIVE_BORDER = BoundingBox(left=0, top=0, right=2010, bottom=2814)

# Content area (inside the black border)
NATIVE_CONTENT = BoundingBox(left=80, top=80, right=1930, bottom=2610)

# Name / title bar — top opaque region above art window
NATIVE_NAME_BAR = BoundingBox(left=119, top=134, right=1890, bottom=296)

# Art window — transparent region where art shows through
NATIVE_ART_WINDOW = BoundingBox(left=155, top=319, right=1855, bottom=1561)

# Type bar — opaque strip between art window and text box
NATIVE_TYPE_BAR = BoundingBox(left=119, top=1583, right=1889, bottom=1745)

# Text / rules box — large opaque region below type bar
NATIVE_TEXT_BOX = BoundingBox(left=148, top=1760, right=1861, bottom=2595)

# P/T box — overlays bottom-right of text box
# The PT overlay image is 377x206. Positioned right-aligned with rules box,
# bottom-aligned with rules box bottom.
# Calibrated from Card Conjurer: 1136/1500, 1858/2100, 282x154 scaled to 2010x2814
NATIVE_PT_BOX = BoundingBox(left=1522, top=2490, right=1900, bottom=2696)

# Collector bar — dark region at the very bottom of the card
NATIVE_COLLECTOR_BAR = BoundingBox(left=148, top=2610, right=1861, bottom=2750)

# ---------------------------------------------------------------------------
# Zone definitions at PRINT resolution (822 x 1122)
# Computed by scaling native coordinates.
# ---------------------------------------------------------------------------
PRINT_BORDER = NATIVE_BORDER.scaled()
PRINT_CONTENT = NATIVE_CONTENT.scaled()
PRINT_NAME_BAR = NATIVE_NAME_BAR.scaled()
PRINT_ART_WINDOW = NATIVE_ART_WINDOW.scaled()
PRINT_TYPE_BAR = NATIVE_TYPE_BAR.scaled()
PRINT_TEXT_BOX = NATIVE_TEXT_BOX.scaled()
PRINT_PT_BOX = NATIVE_PT_BOX.scaled()
PRINT_COLLECTOR_BAR = NATIVE_COLLECTOR_BAR.scaled()

# ---------------------------------------------------------------------------
# P/T overlay image dimensions (for compositing the separate PT box image)
# ---------------------------------------------------------------------------
PT_OVERLAY_W = 377  # width of m15PT*.png files
PT_OVERLAY_H = 206  # height of m15PT*.png files

# Active (non-transparent) region within the PT overlay image
PT_OVERLAY_ACTIVE = BoundingBox(left=29, top=9, right=375, bottom=177)

# ---------------------------------------------------------------------------
# Convenience: all zones as a dict (native resolution)
# ---------------------------------------------------------------------------
ZONES_NATIVE: dict[str, BoundingBox] = {
    "border": NATIVE_BORDER,
    "content": NATIVE_CONTENT,
    "name_bar": NATIVE_NAME_BAR,
    "art_window": NATIVE_ART_WINDOW,
    "type_bar": NATIVE_TYPE_BAR,
    "text_box": NATIVE_TEXT_BOX,
    "pt_box": NATIVE_PT_BOX,
    "collector_bar": NATIVE_COLLECTOR_BAR,
}

ZONES_PRINT: dict[str, BoundingBox] = {
    "border": PRINT_BORDER,
    "content": PRINT_CONTENT,
    "name_bar": PRINT_NAME_BAR,
    "art_window": PRINT_ART_WINDOW,
    "type_bar": PRINT_TYPE_BAR,
    "text_box": PRINT_TEXT_BOX,
    "pt_box": PRINT_PT_BOX,
    "collector_bar": PRINT_COLLECTOR_BAR,
}


# ---------------------------------------------------------------------------
# Frame file paths
# ---------------------------------------------------------------------------
FRAMES_DIR = PROJECT_ROOT / "assets" / "frames" / "m15"


def frame_path(color_key: str) -> Path:
    """Return the path to the M15 frame image for the given color key.

    Args:
        color_key: One of W, U, B, R, G, M (multicolor), A (artifact),
                   L (land), V (vehicle/colorless), or a land variant
                   (lw, lu, lb, lr, lg, lm).
    """
    # Map short keys to filenames
    key_upper = color_key.upper()
    if len(key_upper) == 1:
        return FRAMES_DIR / f"m15Frame{key_upper}.png"
    # Land frames use lowercase: lw, lu, lb, lr, lg, lm
    return FRAMES_DIR / f"{color_key.lower()}.png"


def pt_box_path(color_key: str) -> Path:
    """Return the path to the M15 P/T box overlay for the given color key."""
    key_upper = color_key.upper()
    if len(key_upper) == 1:
        return FRAMES_DIR / f"m15PT{key_upper}.png"
    return FRAMES_DIR / f"m15PT{color_key[0].upper()}.png"
