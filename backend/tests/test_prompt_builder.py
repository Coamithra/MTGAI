"""Tests for art prompt generation, focused on Card immutability.

``generate_prompts_for_set`` must persist a *copy* of the card with
``art_prompt`` set (via ``model_copy``) rather than mutating the loaded Card in
place, per the project's immutable-card convention.
"""

import json

import pytest

import mtgai.art.prompt_builder as pb
from mtgai.models.card import Card, Color, Rarity


@pytest.fixture
def loaded_card() -> Card:
    return Card(
        name="Test Bear",
        mana_cost="{1}{G}",
        cmc=2.0,
        type_line="Creature — Bear",
        oracle_text="",
        power="2",
        toughness="2",
        rarity=Rarity.COMMON,
        colors=[Color.GREEN],
        color_identity=[Color.GREEN],
        collector_number="001",
        set_code="TST",
        card_types=["Creature"],
        subtypes=["Bear"],
    )


def test_generate_prompts_persists_copy_without_mutating_original(
    monkeypatch, tmp_path, loaded_card
):
    set_dir = tmp_path / "set"
    (set_dir / "cards").mkdir(parents=True)
    card_file = set_dir / "cards" / "001_test-bear.json"
    card_file.write_text(json.dumps({"stub": True}), encoding="utf-8")

    saved: list[Card] = []

    monkeypatch.setattr(pb, "load_card", lambda _p: loaded_card)
    monkeypatch.setattr(pb, "save_card", lambda card, set_dir=None: saved.append(card))
    monkeypatch.setattr(pb, "generate_visual_description", lambda _c: ("a bear", 10, 20))
    monkeypatch.setattr(pb, "assemble_full_prompt", lambda _c, _d: "FULL PROMPT")
    monkeypatch.setattr(pb, "get_character_ref_paths", lambda _c: [])
    monkeypatch.setattr(pb.time, "sleep", lambda _s: None)

    import mtgai.io.asset_paths as asset_paths
    import mtgai.runtime.active_project as active_project

    monkeypatch.setattr(asset_paths, "set_artifact_dir", lambda: set_dir)
    monkeypatch.setattr(
        active_project,
        "require_active_project",
        lambda: type("P", (), {"set_code": "TST"})(),
    )

    summary = pb.generate_prompts_for_set()

    assert summary["processed"] == 1
    # The original loaded card is untouched.
    assert loaded_card.art_prompt is None
    # A copy with the prompt set is what gets persisted.
    assert len(saved) == 1
    assert saved[0] is not loaded_card
    assert saved[0].art_prompt == "FULL PROMPT"
    # Everything else carries over unchanged.
    assert saved[0].name == loaded_card.name
    assert saved[0].collector_number == loaded_card.collector_number


def test_dry_run_does_not_save(monkeypatch, tmp_path, loaded_card):
    set_dir = tmp_path / "set"
    (set_dir / "cards").mkdir(parents=True)
    (set_dir / "cards" / "001_test-bear.json").write_text("{}", encoding="utf-8")

    saved: list[Card] = []
    monkeypatch.setattr(pb, "load_card", lambda _p: loaded_card)
    monkeypatch.setattr(pb, "save_card", lambda card, set_dir=None: saved.append(card))
    monkeypatch.setattr(pb, "generate_visual_description", lambda _c: ("a bear", 10, 20))
    monkeypatch.setattr(pb, "assemble_full_prompt", lambda _c, _d: "FULL PROMPT")
    monkeypatch.setattr(pb, "get_character_ref_paths", lambda _c: [])
    monkeypatch.setattr(pb.time, "sleep", lambda _s: None)

    import mtgai.io.asset_paths as asset_paths
    import mtgai.runtime.active_project as active_project

    monkeypatch.setattr(asset_paths, "set_artifact_dir", lambda: set_dir)
    monkeypatch.setattr(
        active_project,
        "require_active_project",
        lambda: type("P", (), {"set_code": "TST"})(),
    )

    pb.generate_prompts_for_set(dry_run=True)

    assert saved == []
    assert loaded_card.art_prompt is None
