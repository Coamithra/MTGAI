"""Tests for the reworked Character References stage (``char_portraits``).

Covers the LLM-free logic — recurring-entity parsing, neutral-prompt building
from the art-direction dictionary, and ``art_character_refs`` attachment — plus a
regression that the ASD-hardcoded extraction is gone. Live image generation
(ComfyUI) is NOT exercised here; ``generate_character_refs`` is driven through its
detection + attach seams with the LLM call mocked.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mtgai.art import character_portraits as cp
from mtgai.io.card_io import load_card
from mtgai.models.card import Card

# ---------------------------------------------------------------------------
# ASD-hardcoded extraction removal regression
# ---------------------------------------------------------------------------


def test_asd_portrait_dict_is_gone() -> None:
    """The hand-tuned ASD character dict + its scan-time builders are removed.

    Descriptions now come from the per-project art-direction dictionary, not a
    hardcoded ``{feretha: ..., koyl: ...}`` table.
    """
    assert not hasattr(cp, "_extract_portrait_details")
    assert not hasattr(cp, "_build_portrait_prompts")
    assert not hasattr(cp, "generate_character_portraits")
    # Source must not carry the old hardcoded character keys.
    src = Path(cp.__file__).read_text(encoding="utf-8")
    for asd_key in ("feretha", "koyl", "marcus tyro", "head scientist"):
        assert asd_key not in src.lower(), f"ASD-hardcoded key {asd_key!r} still present"


# NOTE: recurring-entity *detection* parsing moved to ``test_entity_tags.py``
# when the detection pass was unified into ``mtgai.art.entity_tags`` (card
# 6a27581d). This file keeps the char_portraits-owned logic: neutral-prompt
# building, ``art_character_refs`` attachment, and slugify.


# ---------------------------------------------------------------------------
# Neutral-prompt building from the art-direction dictionary
# ---------------------------------------------------------------------------


def test_neutral_prompt_pulls_appearance_and_strips_name_prefix() -> None:
    refs = {
        "legendary_characters": {
            "aria": "Aria, Storm Knight: a tall woman in silver storm-plate armor"
        }
    }
    prompt = cp.build_neutral_prompt(
        {"entity_key": "aria", "name": "Aria", "kind": "character"}, refs
    )
    assert "silver storm-plate armor" in prompt
    assert "Aria, Storm Knight:" not in prompt  # the "Name:" prefix is stripped
    assert "no dramatic composition" in prompt  # neutral-reference suffix present


def test_neutral_prompt_location_framing_and_flux_replacement() -> None:
    refs = {
        "landmarks": {"the_spire": "a towering moktar obelisk over the sea"},
        "flux_term_replacements": {"moktar": "lion-headed"},
    }
    prompt = cp.build_neutral_prompt(
        {"entity_key": "the_spire", "name": "The Spire", "kind": "location"}, refs
    )
    assert "establishing view of this place" in prompt
    assert "lion-headed" in prompt  # flux replacement applied
    assert "moktar" not in prompt


def test_neutral_prompt_falls_back_to_note_when_not_in_dict() -> None:
    prompt = cp.build_neutral_prompt(
        {
            "entity_key": "mystery",
            "name": "Mystery",
            "kind": "character",
            "note": "a hooded figure",
        },
        {},
    )
    assert "hooded figure" in prompt


# ---------------------------------------------------------------------------
# art_character_refs attachment
# ---------------------------------------------------------------------------


def _write_card(cards_dir: Path, cn: str, name: str) -> None:
    card = Card(name=name, type_line="Creature", collector_number=cn, set_code="TST")
    (cards_dir / f"{cn}_{name.lower()}.json").write_text(
        card.model_dump_json(indent=2), encoding="utf-8"
    )


def test_attach_populates_only_featuring_cards(tmp_path: Path) -> None:
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    _write_card(cards_dir, "001", "ariacharge")
    _write_card(cards_dir, "002", "aria")
    _write_card(cards_dir, "003", "lonewolf")

    entities = [{"entity_key": "aria", "name": "Aria", "cards": ["001", "002"]}]
    ref_paths = {"aria": "art-direction/character-refs/aria_v1.png"}

    modified = cp.attach_refs_to_cards(entities, ref_paths, cards_dir)
    assert modified == 2

    c1 = load_card(cards_dir / "001_ariacharge.json")
    c3 = load_card(cards_dir / "003_lonewolf.json")
    assert len(c1.art_character_refs) == 1
    assert c1.art_character_refs[0].entity_key == "aria"
    assert c1.art_character_refs[0].ref_image_path.endswith("aria_v1.png")
    assert c3.art_character_refs == []  # not a featuring card


def test_attach_is_idempotent(tmp_path: Path) -> None:
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    _write_card(cards_dir, "001", "ariacharge")
    entities = [{"entity_key": "aria", "name": "Aria", "cards": ["001"]}]
    ref_paths = {"aria": "art-direction/character-refs/aria_v1.png"}

    assert cp.attach_refs_to_cards(entities, ref_paths, cards_dir) == 1
    # Second run with identical input rewrites nothing.
    assert cp.attach_refs_to_cards(entities, ref_paths, cards_dir) == 0
    c1 = load_card(cards_dir / "001_ariacharge.json")
    assert len(c1.art_character_refs) == 1  # not duplicated


def test_attach_skips_entity_without_generated_image(tmp_path: Path) -> None:
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    _write_card(cards_dir, "001", "ariacharge")
    # ref_paths missing for 'aria' -> no attachment.
    modified = cp.attach_refs_to_cards(
        [{"entity_key": "aria", "name": "Aria", "cards": ["001"]}], {}, cards_dir
    )
    assert modified == 0
    assert load_card(cards_dir / "001_ariacharge.json").art_character_refs == []


def test_clear_refs_on_cards(tmp_path: Path) -> None:
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    _write_card(cards_dir, "001", "ariacharge")
    cp.attach_refs_to_cards(
        [{"entity_key": "aria", "name": "Aria", "cards": ["001"]}],
        {"aria": "art-direction/character-refs/aria_v1.png"},
        cards_dir,
    )
    assert cp.clear_refs_on_cards(cards_dir) == 1
    assert load_card(cards_dir / "001_ariacharge.json").art_character_refs == []
    # Idempotent: a second clear modifies nothing.
    assert cp.clear_refs_on_cards(cards_dir) == 0


def test_attach_preserves_refs_for_entities_outside_this_run(tmp_path: Path) -> None:
    """A re-run that produces a different entity set must not clobber an existing
    ref for an entity it didn't touch."""
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    _write_card(cards_dir, "001", "card")
    # First run attaches 'aria'.
    cp.attach_refs_to_cards(
        [{"entity_key": "aria", "name": "Aria", "cards": ["001"]}],
        {"aria": "art-direction/character-refs/aria_v1.png"},
        cards_dir,
    )
    # Second run produces only 'bolt'; 'aria' must survive.
    cp.attach_refs_to_cards(
        [{"entity_key": "bolt", "name": "Bolt", "cards": ["001"]}],
        {"bolt": "art-direction/character-refs/bolt_v1.png"},
        cards_dir,
    )
    keys = {r.entity_key for r in load_card(cards_dir / "001_card.json").art_character_refs}
    assert keys == {"aria", "bolt"}


@pytest.mark.parametrize(
    "name,expected", [("Aria, Storm Knight", "aria_storm_knight"), ("X-Y!", "x_y")]
)
def test_slugify(name: str, expected: str) -> None:
    assert cp._slugify(name) == expected
