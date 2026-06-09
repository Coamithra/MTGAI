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


# ---------------------------------------------------------------------------
# Recurring-entity detection parsing
# ---------------------------------------------------------------------------


def _cards_fixture() -> list[dict]:
    return [
        {"collector_number": "001", "name": "Aria's Charge"},
        {"collector_number": "002", "name": "Aria, Storm Knight"},
        {"collector_number": "003", "name": "Lone Wolf"},
    ]


def _patch_llm(monkeypatch, entities: list[dict]) -> None:
    def fake_generate_with_tool(*_args, **_kwargs):
        return {
            "result": {"entities": entities},
            "input_tokens": 10,
            "output_tokens": 10,
        }

    monkeypatch.setattr(cp, "generate_with_tool", fake_generate_with_tool)
    monkeypatch.setattr(cp, "cost_from_result", lambda _r: 0.0)


def test_detection_keeps_only_multi_card_entities(monkeypatch) -> None:
    """A one-card entity (or one whose cards reduce to <2 valid) is dropped."""
    _patch_llm(
        monkeypatch,
        [
            {"entity_key": "aria", "name": "Aria", "kind": "character", "cards": ["001", "002"]},
            {"entity_key": "lone_wolf", "name": "Lone Wolf", "kind": "creature", "cards": ["003"]},
        ],
    )
    entities, cost = cp.detect_recurring_entities(_cards_fixture(), {}, model_id="m")
    keys = {e["entity_key"] for e in entities}
    assert keys == {"aria"}
    assert cost == 0.0


def test_detection_drops_unknown_collector_numbers(monkeypatch) -> None:
    """Hallucinated collector numbers are filtered; if <2 remain the entity drops."""
    _patch_llm(
        monkeypatch,
        [
            # only 001 is real -> reduced to 1 valid card -> dropped
            {"entity_key": "ghost", "name": "Ghost", "kind": "character", "cards": ["001", "999"]},
        ],
    )
    entities, _ = cp.detect_recurring_entities(_cards_fixture(), {}, model_id="m")
    assert entities == []


def test_detection_dedups_keys_and_cards(monkeypatch) -> None:
    _patch_llm(
        monkeypatch,
        [
            {
                "entity_key": "Aria",
                "name": "Aria",
                "kind": "character",
                "cards": ["001", "001", "002"],
            },
            {
                "entity_key": "aria",
                "name": "Aria dup",
                "kind": "character",
                "cards": ["001", "002"],
            },
        ],
    )
    entities, _ = cp.detect_recurring_entities(_cards_fixture(), {}, model_id="m")
    assert len(entities) == 1
    assert entities[0]["entity_key"] == "aria"  # slugified
    assert entities[0]["cards"] == ["001", "002"]  # deduped, order-preserving


def test_detection_empty_cards_is_noop(monkeypatch) -> None:
    _patch_llm(monkeypatch, [{"entity_key": "x", "name": "X", "kind": "c", "cards": ["a", "b"]}])
    assert cp.detect_recurring_entities([], {}, model_id="m") == ([], 0.0)


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


# ---------------------------------------------------------------------------
# Periodic ComfyUI recycle (VRAM-leak mitigation), mirroring generate_art_for_set
# ---------------------------------------------------------------------------


def _wire_char_loop(monkeypatch, tmp_path: Path, n_entities: int, versions: int = 1) -> None:
    """Seed a tmp project + mock every external seam of generate_character_refs so
    the image loop runs without a real ComfyUI / LLM."""
    set_dir = tmp_path / "set"
    (set_dir / "cards").mkdir(parents=True)

    class _Settings:
        def get_llm_model_id(self, _stage: str) -> str:
            return "stub-model"

        def get_thinking(self, _stage: str) -> str | None:
            return None

    class _Proj:
        set_code = "TST"
        settings = _Settings()

    entities = [
        {"entity_key": f"e{i}", "name": f"Entity {i}", "kind": "character", "cards": [], "note": ""}
        for i in range(n_entities)
    ]

    monkeypatch.setattr("mtgai.runtime.active_project.require_active_project", lambda: _Proj())
    monkeypatch.setattr("mtgai.io.asset_paths.set_artifact_dir", lambda: set_dir)
    monkeypatch.setattr(cp, "detect_recurring_entities", lambda *a, **k: (entities, 0.0))
    monkeypatch.setattr(cp, "VERSIONS_PER_ENTITY", versions)
    monkeypatch.setattr(cp, "ensure_comfyui", lambda log_dir=None: "proc0")
    monkeypatch.setattr(cp, "kill_comfyui", lambda proc=None: None)
    monkeypatch.setattr(cp, "is_comfyui_running", lambda: True)
    monkeypatch.setattr(cp, "generate_image_comfyui", lambda *a, **k: (b"img", {}))


def test_char_loop_recycles_comfyui_at_threshold(monkeypatch, tmp_path: Path) -> None:
    """Every COMFYUI_RECYCLE_EVERY images ComfyUI is recycled — but never on the
    last entity (a restart right before the finally-kill is pointless)."""
    _wire_char_loop(monkeypatch, tmp_path, n_entities=8, versions=1)
    recycles: list = []
    monkeypatch.setattr(
        cp, "recycle_comfyui", lambda proc, log_dir=None: recycles.append(proc) or "procN"
    )
    monkeypatch.setattr(cp, "COMFYUI_RECYCLE_EVERY", 4)

    summary = cp.generate_character_refs()

    assert summary["generated"] == 8
    # 1 image/entity → recycle fires after entity 4; the would-be fire after
    # entity 8 is suppressed because it's the last entity.
    assert len(recycles) == 1


def test_char_loop_recycle_disabled_when_zero(monkeypatch, tmp_path: Path) -> None:
    """COMFYUI_RECYCLE_EVERY == 0 disables the periodic recycle entirely."""
    _wire_char_loop(monkeypatch, tmp_path, n_entities=8, versions=1)
    recycles: list = []
    monkeypatch.setattr(
        cp, "recycle_comfyui", lambda proc, log_dir=None: recycles.append(proc) or "procN"
    )
    monkeypatch.setattr(cp, "COMFYUI_RECYCLE_EVERY", 0)

    cp.generate_character_refs()

    assert recycles == []


def test_char_loop_recycles_only_at_entity_boundary(monkeypatch, tmp_path: Path) -> None:
    """With 3 versions/entity and a threshold of 3, the recycle still fires only
    at the entity boundary (never mid-entity), so an entity's versions stay on one
    ComfyUI session."""
    _wire_char_loop(monkeypatch, tmp_path, n_entities=3, versions=3)
    recycles: list = []
    monkeypatch.setattr(
        cp, "recycle_comfyui", lambda proc, log_dir=None: recycles.append(proc) or "procN"
    )
    monkeypatch.setattr(cp, "COMFYUI_RECYCLE_EVERY", 3)

    summary = cp.generate_character_refs()

    assert summary["generated"] == 9
    # Entity 0 (3 imgs) → recycle; entity 1 (3 imgs) → recycle; entity 2 is last
    # → suppressed. Two recycles, both at entity boundaries.
    assert len(recycles) == 2
