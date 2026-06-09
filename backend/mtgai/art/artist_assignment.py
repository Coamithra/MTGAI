"""Artist assignment + cameo knob for the Art Prompt Generation stage.

Two small, deterministic, side-effect-free helpers the ``prompt_builder``
art-prompt stage leans on, kept out of ``prompt_builder`` so they're unit-
testable without the LLM/IO surface:

* :func:`assign_artists` — distribute a card pool across the project's Artist
  Directory (``art-direction/artists.json``). Policy: **round-robin** — sort the
  pool into a stable ``(rarity, colour, collector_number)`` order then deal it
  out one card at a time (card *i* → ``artists[i % N]``). Because the sort
  clusters each rarity (and colour) into a contiguous run, dealing round-robin
  spreads every rarity — especially the showcase mythics/rares — across all the
  painters instead of letting the first artist's slice swallow the whole mythic
  tier (the way a contiguous split did). Per-artist totals stay near-equal
  (differ by ≤1). Deterministic (same pool + same directory → same map) so a
  re-run / resume doesn't reshuffle credits, and reproducible in tests.

* :class:`ArtPromptKnobs` + load/save — the tunable per-card **cameo
  probability** persisted to ``art-direction/art-prompt-knobs.json``. The
  builder rolls a seeded RNG per card against it to decide whether to instruct
  the LLM to feature a style-guide entity.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Rarity ordering for the stable sort (mythic first). The sort only groups each
# rarity into a contiguous run; the round-robin deal then fans that run out
# across all artists. Unknown rarities sort last.
_RARITY_RANK: dict[str, int] = {
    "mythic": 0,
    "rare": 1,
    "uncommon": 2,
    "common": 3,
    "special": 4,
    "bonus": 5,
}

# Colour ordering inside a rarity band (WUBRG, then multicolour, then
# colourless) so the deal walks the pool in a stable, predictable order.
_COLOR_RANK: dict[str, int] = {"W": 0, "U": 1, "B": 2, "R": 3, "G": 4}

KNOBS_FILENAME = "art-prompt-knobs.json"
DEFAULT_CAMEO_PROBABILITY = 0.25


class ArtPromptKnobs(BaseModel):
    """Tunable knobs for the Art Prompt Generation stage.

    ``cameo_probability`` is the per-card chance (0.0-1.0) that the LLM is
    instructed to weave in a named style-guide character / location / element.
    Surfaced + editable in the wizard's Art Prompts tab.
    """

    cameo_probability: float = Field(default=DEFAULT_CAMEO_PROBABILITY, ge=0.0, le=1.0)


def _knobs_path(asset_dir: Path) -> Path:
    return asset_dir / "art-direction" / KNOBS_FILENAME


def load_art_prompt_knobs(asset_dir: Path) -> ArtPromptKnobs:
    """Load the stage knobs from ``<asset>/art-direction/art-prompt-knobs.json``.

    Returns defaults when the file is absent or malformed — the knob is a pure
    tuning surface, never a hard dependency.
    """
    path = _knobs_path(asset_dir)
    if not path.exists():
        return ArtPromptKnobs()
    try:
        return ArtPromptKnobs.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Could not read %s (%s); using default art-prompt knobs", path, e)
        return ArtPromptKnobs()


def save_art_prompt_knobs(asset_dir: Path, knobs: ArtPromptKnobs) -> None:
    """Persist the stage knobs (creating ``art-direction/`` if needed)."""
    from mtgai.io.atomic import atomic_write_text

    path = _knobs_path(asset_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, knobs.model_dump_json(indent=2))


def _sort_key(card: dict) -> tuple[int, int, str]:
    """Stable ``(rarity, colour, collector_number)`` sort key for the pool."""
    rarity = str(card.get("rarity") or "common").lower()
    colors = card.get("colors") or []
    if isinstance(colors, list) and colors:
        first_color = str(colors[0])
        color_rank = _COLOR_RANK.get(first_color, 5)
    else:
        # Colourless (no colours) sorts after the five mono colours; a multi-
        # colour card uses its first colour above, so a gold WU card sits in W.
        color_rank = 6
    return (
        _RARITY_RANK.get(rarity, 99),
        color_rank,
        str(card.get("collector_number") or ""),
    )


def assign_artists(cards: list[dict], artists: list[dict]) -> dict[str, str]:
    """Map each card's collector number → an artist name (round-robin policy).

    ``cards`` are the cards to credit (the caller excludes lands/reprints).
    ``artists`` is the loaded directory (``[{name, style_prompt}, ...]``).

    The pool is sorted into ``(rarity, colour, collector_number)`` order then
    dealt out round-robin — card *i* → ``artists[i % len(artists)]``. Since the
    sort groups each rarity into a contiguous run, the deal fans that run across
    all painters, so the showcase mythics/rares are split among several artists
    rather than handed wholesale to the first one. Per-artist totals stay
    near-equal (differ by ≤1). Deterministic: identical inputs yield an identical
    map, so a resume / re-run keeps credits stable.

    Returns ``{}`` when there are no artists or no cards (the caller leaves
    ``card.artist`` at its default in that case).
    """
    if not artists or not cards:
        return {}

    ordered = sorted(cards, key=_sort_key)
    a = len(artists)

    assignment: dict[str, str] = {}
    for i, card in enumerate(ordered):
        cn = str(card.get("collector_number") or "")
        if cn:
            assignment[cn] = artists[i % a]["name"]
    return assignment
