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
    assert url1.rsplit("&t=", 1)[1] == str(f.stat().st_mtime_ns)

    # Overwriting (a Re-roll) bumps the mtime → a different cache-buster token.
    # Nanosecond resolution catches even a sub-second re-roll.
    os.utime(f, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns + 1_000_000))
    url2 = _set_symbol_img_url(f)
    assert url2 != url1


# ---------------------------------------------------------------------------
# Skip the ComfyUI boot when all glyph masks already exist (card 6a285af6)
# ---------------------------------------------------------------------------


def _wire_symbol(monkeypatch, tmp_path):
    """Seed a tmp project + mock every external seam of generate_set_symbol so the
    version loop runs without a real ComfyUI / LLM. Returns the symbol_dir."""
    asset_dir = tmp_path / "set"
    symbol_dir = asset_dir / "art-direction" / "set-symbol"
    symbol_dir.mkdir(parents=True)

    class _Settings:
        def get_llm_model_id(self, _stage):
            return "stub-model"

        def get_thinking(self, _stage):
            return None

    class _Proj:
        set_code = "TST"
        settings = _Settings()

    monkeypatch.setattr("mtgai.runtime.active_project.require_active_project", lambda: _Proj())
    monkeypatch.setattr("mtgai.io.asset_paths.set_artifact_dir", lambda: asset_dir)
    monkeypatch.setattr(ss, "_load_theme", lambda _d: {})
    monkeypatch.setattr(ss, "_load_visual_refs", lambda _d: {})
    monkeypatch.setattr(
        ss,
        "propose_symbol_concept",
        lambda **k: ({"concept": "an emblem", "image_prompt": "a glyph"}, 0.0),
    )
    monkeypatch.setattr(ss, "generate_image_comfyui", lambda *a, **k: (b"raw", {}))
    monkeypatch.setattr(ss, "build_silhouette", lambda _b: b"mask")
    monkeypatch.setattr(ss, "_write_preview", lambda *a, **k: None)
    return symbol_dir


def test_symbol_skips_comfyui_boot_when_all_masks_present(monkeypatch, tmp_path):
    """A resume where all glyph masks already exist (force=False) must NOT boot
    ComfyUI — booting just to iterate-and-skip is pure waste and the VRAM pre-check
    inside ensure_comfyui can spuriously FAIL the stage. Regression for card
    6a285af6. Fails without the needs-work gate (ensure_comfyui ran
    unconditionally)."""
    symbol_dir = _wire_symbol(monkeypatch, tmp_path)
    monkeypatch.setattr(
        ss, "ensure_comfyui", lambda log_dir=None: pytest.fail("must not boot ComfyUI")
    )
    killed = []
    monkeypatch.setattr(ss, "kill_comfyui", lambda proc=None: killed.append(proc))
    for v in range(1, ss.VERSIONS + 1):
        (symbol_dir / f"mask_v{v}.png").write_bytes(b"old")

    summary = ss.generate_set_symbol()

    assert summary["generated"] == 0
    assert summary["versions"] == list(range(1, ss.VERSIONS + 1))
    # Never booted → never kill (kill_comfyui(None) would tear down an external one).
    assert killed == []


def test_symbol_boots_comfyui_when_a_mask_missing(monkeypatch, tmp_path):
    """The mirror case: when even one mask is missing, ComfyUI IS booted."""
    symbol_dir = _wire_symbol(monkeypatch, tmp_path)
    booted = []
    monkeypatch.setattr(ss, "ensure_comfyui", lambda log_dir=None: booted.append(1) or "proc0")
    monkeypatch.setattr(ss, "kill_comfyui", lambda proc=None: None)
    # All but the last mask present.
    for v in range(1, ss.VERSIONS):
        (symbol_dir / f"mask_v{v}.png").write_bytes(b"old")

    summary = ss.generate_set_symbol()

    assert booted == [1]
    assert summary["generated"] == 1  # only the one missing version
