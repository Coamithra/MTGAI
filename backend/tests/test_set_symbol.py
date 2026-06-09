"""Tests for the set-symbol (glyph) generation + renderer wiring.

Covers the pure, env-free pieces: the silhouette post-process (:func:`build_silhouette`)
handles either polarity, the per-rarity recolor (:func:`tint_mask`), and the
renderer's preference for a per-project ``symbol.png`` over the placeholder
triangle (:func:`get_set_symbol`).
"""

from __future__ import annotations

from io import BytesIO

import pytest

# Both modules hard-import Pillow at load; skip the whole module without it.
pytest.importorskip("PIL")

from PIL import Image, ImageDraw

from mtgai.art import set_symbol as ss
from mtgai.rendering import symbol_renderer as sr


def _circle_png(bg: tuple[int, int, int], fg: tuple[int, int, int]) -> bytes:
    img = Image.new("RGB", (200, 200), bg)
    ImageDraw.Draw(img).ellipse((60, 60, 140, 140), fill=fg)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _alpha(mask_bytes: bytes) -> Image.Image:
    return Image.open(BytesIO(mask_bytes)).convert("RGBA").getchannel("A")


def test_build_silhouette_dark_shape_on_light_ground():
    """A black icon on white (the prompted Flux output) becomes an opaque shape
    on transparent ground."""
    a = _alpha(ss.build_silhouette(_circle_png((255, 255, 255), (10, 10, 10))))
    assert a.getextrema() == (0, 255)
    assert a.getpixel((a.size[0] // 2, a.size[1] // 2)) == 255  # shape centre opaque
    assert a.getpixel((0, 0)) == 0  # ground transparent


def test_build_silhouette_handles_inverted_polarity():
    """A light shape on a dark ground is silhouetted just the same (the corners
    decide which region is the shape)."""
    a = _alpha(ss.build_silhouette(_circle_png((5, 5, 5), (250, 250, 250))))
    assert a.getpixel((a.size[0] // 2, a.size[1] // 2)) == 255
    assert a.getpixel((0, 0)) == 0


def test_build_silhouette_autocrops_to_square():
    """The shape is autocropped + padded to a centered square so it fills the box."""
    mask = Image.open(BytesIO(ss.build_silhouette(_circle_png((255, 255, 255), (10, 10, 10)))))
    assert mask.width == mask.height
    # Far smaller than the 200px source (cropped to the ~80px circle + margin).
    assert mask.width < 200


def test_build_silhouette_blank_image_has_no_shape():
    """A uniform (blank) image silhouettes to a fully-transparent mask — the
    signal set_user_symbol uses to reject an invisible upload."""
    buf = BytesIO()
    Image.new("RGB", (120, 120), (255, 255, 255)).save(buf, format="PNG")
    mask = Image.open(BytesIO(ss.build_silhouette(buf.getvalue()))).convert("RGBA")
    assert mask.getchannel("A").getbbox() is None


def test_mask_path_for_rejects_traversal(tmp_path):
    """Only 'upload' or an all-digit tag resolves to a mask path; anything that
    could escape the dir (path separators, '..', floats) is rejected."""
    assert ss._mask_path_for(tmp_path, "3") == tmp_path / "mask_v3.png"
    assert ss._mask_path_for(tmp_path, "upload") == tmp_path / "mask_upload.png"
    for bad in ("../../etc/passwd", "..", "3.5", "v3", "", "a"):
        assert ss._mask_path_for(tmp_path, bad) is None


def test_tint_mask_recolors_shape_keeps_alpha():
    mask = Image.open(BytesIO(ss.build_silhouette(_circle_png((255, 255, 255), (10, 10, 10)))))
    tinted = ss.tint_mask(mask, (220, 180, 40))
    cx, cy = tinted.size[0] // 2, tinted.size[1] // 2
    assert tinted.getpixel((cx, cy))[:3] == (220, 180, 40)
    assert tinted.getpixel((cx, cy))[3] == 255  # shape opaque
    assert tinted.getpixel((0, 0))[3] == 0  # ground transparent


def test_get_set_symbol_falls_back_to_placeholder_without_project():
    """With no active project, the renderer returns a placeholder symbol (never
    raises) for every rarity."""
    sr.clear_caches()
    for rarity in ("C", "U", "R", "M"):
        sym = sr.get_set_symbol(rarity, 48)
        assert isinstance(sym, Image.Image)
        assert sym.size == (48, 48)


def test_get_set_symbol_prefers_project_symbol(tmp_path, monkeypatch):
    """When a project ``symbol.png`` exists, the renderer recolors it per rarity
    instead of drawing the placeholder triangle."""
    sr.clear_caches()
    symbol_path = tmp_path / "symbol.png"
    symbol_path.write_bytes(ss.build_silhouette(_circle_png((255, 255, 255), (10, 10, 10))))
    monkeypatch.setattr(sr, "_project_symbol_path", lambda: symbol_path)

    rare = sr.get_set_symbol("R", 64)
    assert rare.size == (64, 64)
    # The centre of the recolored glyph carries the rare tint (the mask's shape).
    fill = sr._SET_SYMBOL_COLORS["R"]["fill"]
    cx, cy = 32, 32
    r, g, b, alpha = rare.getpixel((cx, cy))
    assert (r, g, b) == (int(fill[0]), int(fill[1]), int(fill[2]))
    assert alpha == 255
    # A different rarity recolors the SAME shape differently (cache keyed on rarity).
    common = sr.get_set_symbol("C", 64)
    assert common.getpixel((cx, cy))[:3] != rare.getpixel((cx, cy))[:3]


def test_set_symbol_img_url_carries_mtime_cache_buster(tmp_path):
    """The Set Symbol tab's image URL appends an mtime cache-buster so a Re-roll
    (which overwrites ``preview_v*.png`` in place) shows the fresh pixels instead
    of the browser-cached old glyph. The mtime changes exactly when the file does."""
    import os

    from mtgai.pipeline.server import _set_symbol_img_url

    f = tmp_path / "preview_v1.png"
    f.write_bytes(b"old")
    url1 = _set_symbol_img_url(f)
    assert url1.startswith("/api/wizard/set_symbol/image?file=preview_v1.png&t=")
    assert url1.rsplit("&t=", 1)[1] == str(int(f.stat().st_mtime))

    # Overwriting (a Re-roll) bumps the mtime → a different cache-buster token.
    os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 5))
    url2 = _set_symbol_img_url(f)
    assert url2 != url1
