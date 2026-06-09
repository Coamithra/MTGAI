"""Per-set symbol (glyph) generation — the small emblem in every card's type line.

The ``set_symbol`` pipeline stage (sits right after ``visual_refs``, before
``art_prompts``). It produces a **per-project** identifying glyph so a set no
longer renders the same hardcoded placeholder "descending vortex" triangle that
``rendering/symbol_renderer.py`` draws by default.

Three steps under one AI-lock hold (the runner ``stages.run_set_symbol``):

1. **Concept** — one ``generate_with_tool`` call (the ``set_symbol`` LLM
   assignment) reads the theme setting prose + the ``visual_refs`` art-direction
   (``set_art_direction`` + ``visual_motifs``) and proposes ONE iconic emblem:
   a short ``concept`` plus a Flux ``image_prompt``.
2. **Image gen** — ComfyUI/Flux renders ``VERSIONS`` square candidates from the
   prompt (the existing ``image_generator.generate_image_comfyui``).
3. **Silhouette** — each raster is reduced to a clean 2-tone **alpha mask**
   (:func:`build_silhouette`): a single opaque shape on transparent ground,
   autocropped + centered so it fills the type-line symbol box. The renderer
   recolors this mask per rarity at render time (keeping the existing
   ``_SET_SYMBOL_COLORS`` scheme), so one shape serves all four rarities.

Output under ``<asset>/art-direction/set-symbol/``:

    raw_v{n}.png      Flux raster (kept for re-silhouette / debugging)
    mask_v{n}.png     RGBA alpha mask (RGB black, A = shape coverage)
    preview_v{n}.png  light-grey-tinted preview the wizard tab shows
    symbol.png        the SELECTED mask — the file the renderer reads
    concept.json      {concept, image_prompt, versions, selected_version, source}

The renderer prefers ``symbol.png`` when present and falls back to the
placeholder triangle otherwise (see ``symbol_renderer.get_set_symbol``).
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

from mtgai.art.image_generator import ensure_comfyui, generate_image_comfyui, kill_comfyui
from mtgai.generation import temperatures as temps
from mtgai.generation.llm_client import cost_from_result, generate_with_tool
from mtgai.generation.prompts import format_setting_prose
from mtgai.generation.token_budgets import STANDARD
from mtgai.io.atomic import atomic_write_text

logger = logging.getLogger(__name__)

# Square candidates so the glyph isn't letterboxed; Flux's default resolution.
IMG_SIZE = 768
# How many candidate glyphs to render per run (re-roll surfaces alternates).
VERSIONS = 3

# The subdir (under the asset folder) the stage owns end-to-end.
SET_SYMBOL_SUBDIR = ("art-direction", "set-symbol")

# Tab-preview tint — a light grey that reads on the dark wizard background. The
# real render recolors per rarity from the mask, so this is display-only.
_PREVIEW_TINT = (216, 220, 228)

# Appended to the model's image_prompt so the raster is a clean, thresholdable
# icon regardless of how literally the model followed instructions.
_GLYPH_STYLE_SUFFIX = (
    "Solid flat black silhouette icon on a pure solid white background, "
    "centered, minimalist vector logo style, one bold simple shape, very high "
    "contrast, no text, no letters, no gradient, no shading, no outline, no border."
)

_CONCEPT_SYSTEM_PROMPT = (
    "You design the SET SYMBOL for a Magic: The Gathering set — the small glyph "
    "that sits in every card's type line (the mark tinted by rarity). Propose ONE "
    "simple, iconic emblem drawn from the set's core identity (its central image, "
    "myth, faction, or motif).\n\n"
    "Hard constraints — the symbol must read as a clean 2-tone silhouette at about "
    "30 pixels tall:\n"
    "- A SINGLE bold shape with minimal internal detail.\n"
    "- NO text, letters, numbers, or fine/thin lines.\n"
    "- Instantly recognizable as a flat icon, not a scene or illustration.\n\n"
    "Return a short `concept` (a few words naming the emblem) and an `image_prompt` "
    "describing that emblem as a flat icon for an image generator. Keep the prompt "
    "to one or two sentences; describe only the shape, not a background or style "
    "(the pipeline appends the icon styling)."
)

_CONCEPT_TOOL_SCHEMA = {
    "name": "propose_set_symbol",
    "description": "Propose the set's identifying glyph as a flat 2-tone icon.",
    "input_schema": {
        "type": "object",
        "properties": {
            "concept": {
                "type": "string",
                "description": "A few words naming the emblem (e.g. 'a cracked phoenix feather').",
            },
            "image_prompt": {
                "type": "string",
                "description": "One or two sentences describing the emblem as a flat icon shape.",
            },
            "rationale": {
                "type": "string",
                "description": "Optional: why this emblem fits the set's identity.",
            },
        },
        "required": ["concept", "image_prompt"],
    },
}


# ---------------------------------------------------------------------------
# Silhouette post-processing
# ---------------------------------------------------------------------------
def build_silhouette(raw_png_bytes: bytes) -> bytes:
    """Reduce a raster glyph to a clean 2-tone alpha mask (PNG bytes).

    The mask is RGBA with ``RGB = black`` and ``A = shape coverage`` so the
    renderer can recolor it per rarity by swapping the RGB and keeping alpha.
    Robust to either polarity (dark shape on light ground OR light shape on dark
    ground): the background is inferred from the corners and the alpha derived so
    the *shape* is opaque. Mid-tones are contrast-stretched toward binary (edges
    stay anti-aliased), then the shape is autocropped + recentered on a square so
    it fills the type-line symbol box consistently regardless of Flux margins.
    """
    img = Image.open(BytesIO(raw_png_bytes)).convert("RGB")
    gray = ImageOps.grayscale(img)
    w, h = gray.size

    # Infer background polarity from the four corners. If the ground is dark, the
    # shape is the light region (alpha = luminance); else alpha = inverse.
    corner_pts = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    corner_vals = [float(gray.getpixel(p)) for p in corner_pts]  # type: ignore[arg-type]
    bg_is_dark = (sum(corner_vals) / len(corner_vals)) < 128

    alpha = gray if bg_is_dark else ImageChops.invert(gray)

    # Contrast-stretch around the mid so faint grey haze drops out but edge
    # anti-aliasing survives: map [LO..HI] -> [0..255], clamp outside.
    lo, hi = 70, 170
    alpha = alpha.point(
        lambda v: 0 if v <= lo else (255 if v >= hi else int((v - lo) * 255 / (hi - lo)))
    )

    # Autocrop to the shape's bounding box, then pad back to a centered square
    # (with a small margin) so the glyph fills the box rather than floating.
    bbox = alpha.getbbox()
    if bbox:
        alpha = alpha.crop(bbox)
    side = max(alpha.size)
    margin = max(2, side // 12)
    canvas = Image.new("L", (side + 2 * margin, side + 2 * margin), 0)
    off = ((canvas.width - alpha.width) // 2, (canvas.height - alpha.height) // 2)
    canvas.paste(alpha, off)

    mask = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    mask.putalpha(canvas)
    out = BytesIO()
    mask.save(out, format="PNG")
    return out.getvalue()


def tint_mask(mask: Image.Image, rgb: tuple[int, int, int]) -> Image.Image:
    """Recolor an alpha mask: fill the opaque region with ``rgb``, keep alpha."""
    mask = mask.convert("RGBA")
    solid = Image.new("RGBA", mask.size, (*rgb, 255))
    solid.putalpha(mask.getchannel("A"))
    return solid


def _write_preview(mask_bytes: bytes, dest: Path) -> None:
    """Write a light-grey-tinted preview of a mask for the wizard tab."""
    mask = Image.open(BytesIO(mask_bytes)).convert("RGBA")
    tint_mask(mask, _PREVIEW_TINT).save(dest, format="PNG")


# ---------------------------------------------------------------------------
# Concept (LLM)
# ---------------------------------------------------------------------------
def propose_symbol_concept(
    *, model_id: str, thinking: str | None, theme: dict, visual_refs: dict, log_dir: Path
) -> tuple[dict, float]:
    """LLM-propose the glyph concept + Flux prompt. Returns ``(payload, cost)``.

    ``payload`` is ``{concept, image_prompt, rationale}`` (best-effort: a missing
    field degrades to an empty string and the caller falls back).
    """
    setting = format_setting_prose(theme)
    set_dir_prose = str(visual_refs.get("set_art_direction") or "").strip()
    motifs = [str(m) for m in (visual_refs.get("visual_motifs") or []) if str(m).strip()]

    parts = ["Set identity to draw the emblem from:\n"]
    if setting:
        parts.append(f"# Setting\n{setting[:4000]}\n")
    if set_dir_prose:
        parts.append(f"# Set art direction\n{set_dir_prose}\n")
    if motifs:
        parts.append("# Recurring visual motifs\n- " + "\n- ".join(motifs[:8]) + "\n")
    parts.append("\nPropose the single best set symbol for this identity via the tool.")
    user_prompt = "\n".join(parts)

    response = generate_with_tool(
        system_prompt=_CONCEPT_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        tool_schema=_CONCEPT_TOOL_SCHEMA,
        model=model_id,
        thinking=thinking,
        temperature=temps.CREATIVE,
        max_tokens=STANDARD,
        log_dir=log_dir,
    )
    cost = cost_from_result(response)
    result = response.get("result") or {}
    payload = {
        "concept": str(result.get("concept") or "").strip(),
        "image_prompt": str(result.get("image_prompt") or "").strip(),
        "rationale": str(result.get("rationale") or "").strip(),
    }
    return payload, cost


# ---------------------------------------------------------------------------
# Paths / state helpers
# ---------------------------------------------------------------------------
def _symbol_dir() -> Path:
    from mtgai.io.asset_paths import set_artifact_dir

    return set_artifact_dir().joinpath(*SET_SYMBOL_SUBDIR)


def _load_theme(asset_dir: Path) -> dict:
    theme_path = asset_dir / "theme.json"
    if theme_path.exists():
        try:
            loaded = json.loads(theme_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                return loaded
        except Exception:
            logger.warning("Could not parse %s; proceeding without theme prose", theme_path)
    return {}


def _load_visual_refs(asset_dir: Path) -> dict:
    refs_path = asset_dir / "art-direction" / "visual-references.json"
    if refs_path.exists():
        try:
            loaded = json.loads(refs_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                return loaded
        except Exception:
            logger.warning("Could not parse %s; proceeding without art direction", refs_path)
    return {}


def _read_concept(symbol_dir: Path) -> dict:
    path = symbol_dir / "concept.json"
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                return loaded
        except Exception:
            pass
    return {}


def _mask_path_for(symbol_dir: Path, version_tag: str) -> Path | None:
    """Resolve the mask file for a version tag, or None for an invalid tag.

    ``version_tag`` must be ``"upload"`` or all-digits — anything else (path
    separators, ``..``) is rejected so a user-supplied tag can't escape the
    set-symbol dir."""
    if version_tag == "upload":
        return symbol_dir / "mask_upload.png"
    if version_tag.isdigit():
        return symbol_dir / f"mask_v{version_tag}.png"
    return None


def _select_version(symbol_dir: Path, version_tag: str) -> bool:
    """Copy ``mask_<tag>.png`` -> ``symbol.png`` and record the selection.

    ``version_tag`` is a version number (``"1"``) or ``"upload"``. Returns False
    for an invalid tag or a missing source mask.
    """
    src = _mask_path_for(symbol_dir, version_tag)
    if src is None or not src.is_file():
        return False
    shutil.copyfile(src, symbol_dir / "symbol.png")
    concept = _read_concept(symbol_dir)
    concept["selected_version"] = version_tag
    atomic_write_text(
        symbol_dir / "concept.json", json.dumps(concept, indent=2, ensure_ascii=False)
    )
    return True


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def generate_set_symbol(
    force: bool = False,
    should_cancel: Callable[[], bool] | None = None,
    on_reset: Callable[[], None] | None = None,
    on_concept: Callable[[str, str], None] | None = None,
    on_version: Callable[[int, str], None] | None = None,
    concept_poller: AbstractContextManager | None = None,
) -> dict:
    """Generate the set's identifying glyph and select the first version.

    Args:
        force: regenerate even if ``symbol.png`` already exists.
        should_cancel: polled at version boundaries; stop early (keep partial).
        on_reset: fired once before image generation begins.
        on_concept: ``on_concept(concept, image_prompt)`` after the LLM proposes.
        on_version: ``on_version(version_number, mask_rel_path)`` per saved glyph.
        concept_poller: context manager wrapping ONLY the step-1 LLM concept call
            (tok/s telemetry). It must NOT span the ComfyUI image phase — polling
            llama-swap during image gen reloads the unloaded LLM and starves Flux
            (card 6a25497b). Defaults to a no-op.

    Returns a summary dict.
    """
    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    settings = project.settings
    set_code = project.set_code
    asset_dir = set_artifact_dir()
    symbol_dir = asset_dir / "art-direction" / "set-symbol"
    log_dir = symbol_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    theme = _load_theme(asset_dir)
    visual_refs = _load_visual_refs(asset_dir)

    model_id = settings.get_llm_model_id("set_symbol")
    thinking = settings.get_thinking("set_symbol")

    # Step 1 — concept. The tok/s poller wraps ONLY this LLM call.
    logger.info("Proposing set-symbol concept (model=%s)", model_id)
    with concept_poller or nullcontext():
        concept_payload, cost = propose_symbol_concept(
            model_id=model_id,
            thinking=thinking,
            theme=theme,
            visual_refs=visual_refs,
            log_dir=log_dir,
        )

    image_prompt = (
        concept_payload.get("image_prompt")
        or concept_payload.get("concept")
        or ("A simple bold abstract emblem")
    )
    concept_text = concept_payload.get("concept") or image_prompt
    if on_concept is not None:
        on_concept(concept_text, image_prompt)

    flux_prompt = f"{image_prompt}. {_GLYPH_STYLE_SUFFIX}"

    base_summary = {
        "set_code": set_code,
        "concept": concept_text,
        "image_prompt": image_prompt,
        "generated": 0,
        "failed": 0,
        "cost_usd": round(cost, 4),
        "errors": [],
    }

    if on_reset is not None:
        on_reset()

    generated = 0
    failed = 0
    cancelled = False
    errors: list[dict] = []
    saved_versions: list[int] = []

    comfyui_proc = ensure_comfyui(log_dir=log_dir)
    try:
        for version in range(1, VERSIONS + 1):
            if should_cancel is not None and should_cancel():
                cancelled = True
                break
            mask_dest = symbol_dir / f"mask_v{version}.png"
            if mask_dest.is_file() and not force:
                saved_versions.append(version)
                if on_version is not None:
                    on_version(version, mask_dest.relative_to(asset_dir).as_posix())
                continue
            try:
                image_data, _ = generate_image_comfyui(
                    prompt=flux_prompt, width=IMG_SIZE, height=IMG_SIZE
                )
                (symbol_dir / f"raw_v{version}.png").write_bytes(image_data)
                mask_bytes = build_silhouette(image_data)
                mask_dest.write_bytes(mask_bytes)
                _write_preview(mask_bytes, symbol_dir / f"preview_v{version}.png")
                generated += 1
                saved_versions.append(version)
                if on_version is not None:
                    on_version(version, mask_dest.relative_to(asset_dir).as_posix())
            except Exception as exc:  # best-effort per version
                logger.error("Set-symbol version %d failed: %s", version, exc)
                failed += 1
                errors.append({"version": version, "error": str(exc)})
    finally:
        kill_comfyui(comfyui_proc)

    # Pick the active symbol. A forced re-roll switches to the first fresh AI
    # candidate (the user asked for a new glyph). Otherwise a still-valid prior
    # selection wins — including a user upload, which stays pinned across resumes
    # — falling back to the first available candidate.
    concept_payload["versions"] = saved_versions
    concept_payload["source"] = "flux"
    saved_tags = [str(v) for v in saved_versions]
    prior_selected = str(_read_concept(symbol_dir).get("selected_version") or "")
    if force and saved_tags:
        selected = saved_tags[0]
    elif prior_selected in saved_tags or prior_selected == "upload":
        selected = prior_selected
    else:
        selected = saved_tags[0] if saved_tags else None
    concept_payload["selected_version"] = selected

    # Copy the chosen mask into symbol.png, then write concept.json ONCE (the
    # selection is already stamped on concept_payload, so no _select_version
    # re-read/re-write here).
    if selected is not None:
        chosen_mask = _mask_path_for(symbol_dir, selected)
        if chosen_mask is not None and chosen_mask.is_file():
            shutil.copyfile(chosen_mask, symbol_dir / "symbol.png")
    atomic_write_text(
        symbol_dir / "concept.json", json.dumps(concept_payload, indent=2, ensure_ascii=False)
    )

    return {
        **base_summary,
        "generated": generated,
        "failed": failed,
        "errors": errors,
        "versions": saved_versions,
        "selected_version": selected,
        "cancelled": cancelled,
    }


def set_user_symbol(image_bytes: bytes) -> str:
    """Adopt a user-uploaded image as the set symbol.

    Builds the silhouette mask from the upload, stores ``raw_upload``/
    ``mask_upload``/``preview_upload`` + selects it as ``symbol.png``. Returns the
    repo-relative path of the active ``symbol.png``.

    Raises ``ValueError`` if the upload has no detectable shape (a blank/near-
    blank image would silhouette to a fully-transparent mask → an invisible
    symbol). Validation happens BEFORE any file write, so a bad upload never
    clobbers a good ``symbol.png``.
    """
    from mtgai.io.asset_paths import set_artifact_dir

    asset_dir = set_artifact_dir()
    symbol_dir = asset_dir / "art-direction" / "set-symbol"

    mask_bytes = build_silhouette(image_bytes)
    if Image.open(BytesIO(mask_bytes)).convert("RGBA").getchannel("A").getbbox() is None:
        raise ValueError("Uploaded image has no detectable shape (it appears blank).")

    symbol_dir.mkdir(parents=True, exist_ok=True)
    (symbol_dir / "raw_upload.png").write_bytes(image_bytes)
    (symbol_dir / "mask_upload.png").write_bytes(mask_bytes)
    _write_preview(mask_bytes, symbol_dir / "preview_upload.png")
    _select_version(symbol_dir, "upload")
    return (symbol_dir / "symbol.png").relative_to(asset_dir).as_posix()


def select_symbol_version(version_tag: str) -> bool:
    """Set the active ``symbol.png`` to an already-generated version. See
    :func:`_select_version`."""
    return _select_version(_symbol_dir(), str(version_tag))


def clear_set_symbol() -> None:
    """Remove the active project's set-symbol artifacts (stage clearer)."""
    symbol_dir = _symbol_dir()
    if symbol_dir.exists():
        shutil.rmtree(symbol_dir, ignore_errors=True)
