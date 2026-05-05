"""Tests for the per-stage artifact clearer registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtgai.pipeline import stages as stages_mod
from mtgai.pipeline.models import STAGE_DEFINITIONS


@pytest.fixture
def fake_output_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(stages_mod, "OUTPUT_ROOT", tmp_path)
    return tmp_path


def test_every_stage_has_a_clearer() -> None:
    """The dispatch contract: every defined stage has a registered clearer."""
    for defn in STAGE_DEFINITIONS:
        assert defn["stage_id"] in stages_mod.STAGE_CLEARERS, (
            f"stage {defn['stage_id']} missing from STAGE_CLEARERS"
        )


def test_clear_skeleton_removes_skeleton_json(fake_output_root: Path) -> None:
    set_dir = fake_output_root / "sets" / "TST"
    set_dir.mkdir(parents=True)
    (set_dir / "skeleton.json").write_text("{}", encoding="utf-8")

    stages_mod.clear_stage_artifacts("skeleton", "TST")
    assert not (set_dir / "skeleton.json").exists()


def test_clear_card_gen_removes_cards_dir(fake_output_root: Path) -> None:
    set_dir = fake_output_root / "sets" / "TST"
    cards_dir = set_dir / "cards"
    cards_dir.mkdir(parents=True)
    (cards_dir / "001_foo.json").write_text("{}", encoding="utf-8")

    stages_mod.clear_stage_artifacts("card_gen", "TST")
    assert not cards_dir.exists()


def test_clear_char_portraits_targets_real_output_dir(fake_output_root: Path) -> None:
    """Path must match what character_portraits.py actually writes to.

    The portrait pipeline writes under
    ``<set>/art-direction/character-refs/`` — siblings of
    ``visual-references.json``, which is upstream input and must be
    preserved.
    """
    set_dir = fake_output_root / "sets" / "TST"
    art_dir = set_dir / "art-direction"
    art_dir.mkdir(parents=True)
    visual_refs = art_dir / "visual-references.json"
    visual_refs.write_text("{}", encoding="utf-8")
    refs_dir = art_dir / "character-refs"
    refs_dir.mkdir()
    (refs_dir / "feretha_v1.png").write_bytes(b"\x89PNG")

    stages_mod.clear_stage_artifacts("char_portraits", "TST")

    assert not refs_dir.exists()
    assert visual_refs.exists(), "upstream visual-references.json must be preserved"


def test_clear_art_gen_removes_art_dir(fake_output_root: Path) -> None:
    set_dir = fake_output_root / "sets" / "TST"
    art_dir = set_dir / "art"
    art_dir.mkdir(parents=True)
    (art_dir / "001_foo_v1.png").write_bytes(b"\x89PNG")

    stages_mod.clear_stage_artifacts("art_gen", "TST")
    assert not art_dir.exists()


def test_clear_reprints_removes_selection_json(fake_output_root: Path) -> None:
    set_dir = fake_output_root / "sets" / "TST"
    set_dir.mkdir(parents=True)
    (set_dir / "reprint_selection.json").write_text("{}", encoding="utf-8")

    stages_mod.clear_stage_artifacts("reprints", "TST")
    assert not (set_dir / "reprint_selection.json").exists()


def test_clear_rendering_removes_renders_dir(fake_output_root: Path) -> None:
    set_dir = fake_output_root / "sets" / "TST"
    renders_dir = set_dir / "renders"
    renders_dir.mkdir(parents=True)
    (renders_dir / "001.png").write_bytes(b"\x89PNG")

    stages_mod.clear_stage_artifacts("rendering", "TST")
    assert not renders_dir.exists()


def test_clear_is_idempotent_on_missing_artifacts(fake_output_root: Path) -> None:
    """Clearing a stage whose artifacts don't exist should not raise."""
    stages_mod.clear_stage_artifacts("skeleton", "NEVER")
    stages_mod.clear_stage_artifacts("card_gen", "NEVER")
    stages_mod.clear_stage_artifacts("rendering", "NEVER")


def test_in_place_mutator_clearers_are_no_ops(fake_output_root: Path) -> None:
    """Stages that mutate cards in place register no-ops on purpose.

    Their effects are erased by re-running ``card_gen``'s clearer
    upstream in the cascade — duplicating the deletion here would
    risk wiping artifacts the cascade meant to keep.
    """
    set_dir = fake_output_root / "sets" / "TST"
    cards_dir = set_dir / "cards"
    cards_dir.mkdir(parents=True)
    sentinel = cards_dir / "001_foo.json"
    sentinel.write_text("{}", encoding="utf-8")

    for stage_id in ("ai_review", "finalize", "art_prompts", "art_select", "skeleton_rev"):
        stages_mod.clear_stage_artifacts(stage_id, "TST")

    assert sentinel.exists(), "in-place mutator clearers must not touch cards/"


def test_unknown_stage_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        stages_mod.clear_stage_artifacts("not_a_stage", "TST")
