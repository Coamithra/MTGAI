"""Tests for the per-stage artifact clearer registry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mtgai.pipeline import stages as stages_mod
from mtgai.pipeline.models import STAGE_DEFINITIONS


@pytest.fixture
def fake_output_root(tmp_path: Path, isolated_output: Path) -> Path:
    """Tmp ``output`` root for stage-clearer tests.

    Uses :func:`isolated_output` (in :mod:`tests.conftest`) which
    patches ``asset_paths`` + ``model_settings`` + ``runtime_state``
    so ``set_artifact_dir`` resolves into ``tmp_path``. Stage clearers
    route through that helper, so this fixture doesn't need its own
    monkeypatching beyond what the shared fixture does.
    """
    del isolated_output  # used for its side-effect (patching modules)
    return tmp_path


def _open_test_project(code: str, asset_dir: Path) -> None:
    """Pin ``code`` as the active project with ``asset_dir`` as its asset folder.

    Stage clearers route through ``set_artifact_dir`` → reads from the
    active project. Pinning the asset folder is enough; settings.toml
    no longer lives at ``output/sets/<CODE>/``.
    """
    from mtgai.runtime import active_project
    from mtgai.settings.model_settings import ModelSettings

    active_project.write_active_project(
        active_project.ProjectState(
            set_code=code, settings=ModelSettings(asset_folder=str(asset_dir))
        )
    )


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
    _open_test_project("TST", set_dir)

    stages_mod.clear_stage_artifacts("skeleton")
    assert not (set_dir / "skeleton.json").exists()


def test_clear_archetypes_removes_file_and_logs(fake_output_root: Path) -> None:
    set_dir = fake_output_root / "sets" / "TST"
    set_dir.mkdir(parents=True)
    (set_dir / "archetypes.json").write_text("[]", encoding="utf-8")
    log_dir = set_dir / "archetypes" / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "2026.json").write_text("{}", encoding="utf-8")
    _open_test_project("TST", set_dir)

    stages_mod.clear_stage_artifacts("archetypes")
    assert not (set_dir / "archetypes.json").exists()
    assert not (set_dir / "archetypes").exists()


def test_clear_card_gen_preserves_lands(fake_output_root: Path) -> None:
    """card_gen-owned cards + progress + regen archive go; the Lands tab's L-* stay.

    The old behaviour wiped the whole ``cards/`` dir, destroying the lands stage's
    ``L-*`` basics/dual whenever a cascade reached card_gen without re-running
    lands. The scoped clearer deletes only what card_gen owns.
    """
    set_dir = fake_output_root / "sets" / "TST"
    cards_dir = set_dir / "cards"
    cards_dir.mkdir(parents=True)
    (cards_dir / "001_foo.json").write_text('{"collector_number": "001"}', encoding="utf-8")
    (cards_dir / "L-01_plains.json").write_text('{"collector_number": "L-01"}', encoding="utf-8")
    archive = cards_dir / "_regen_archive"
    archive.mkdir()
    (archive / "001_foo.json").write_text("{}", encoding="utf-8")
    (set_dir / "generation_progress.json").write_text("{}", encoding="utf-8")
    _open_test_project("TST", set_dir)

    stages_mod.clear_stage_artifacts("card_gen")

    assert not (cards_dir / "001_foo.json").exists(), "card_gen card should be gone"
    assert (cards_dir / "L-01_plains.json").exists(), "Lands tab L-* must survive"
    assert not archive.exists(), "_regen_archive should be cleared"
    assert not (set_dir / "generation_progress.json").exists(), "progress should be cleared"


def test_clear_lands_removes_land_cards_and_logs(fake_output_root: Path) -> None:
    """The lands clearer drops its ``L-*`` cards (the ones card_gen preserves)
    plus its log dir, and leaves card_gen's ordinary cards untouched.

    Without this, a cascade clearing a stage at/before lands left stale ``L-*``
    cards behind: clear_card_gen_cards preserves them (lands owns them), and a
    partial/failed lands re-run never overwrites them.
    """
    set_dir = fake_output_root / "sets" / "TST"
    cards_dir = set_dir / "cards"
    cards_dir.mkdir(parents=True)
    (cards_dir / "L-01_plains.json").write_text('{"collector_number": "L-01"}', encoding="utf-8")
    (cards_dir / "L-06_dual.json").write_text('{"collector_number": "L-06"}', encoding="utf-8")
    (cards_dir / "001_foo.json").write_text('{"collector_number": "001"}', encoding="utf-8")
    logs = set_dir / "lands" / "logs"
    logs.mkdir(parents=True)
    (logs / "basics.json").write_text("{}", encoding="utf-8")
    _open_test_project("TST", set_dir)

    stages_mod.clear_stage_artifacts("lands")

    assert not (cards_dir / "L-01_plains.json").exists(), "lands L-* card should be gone"
    assert not (cards_dir / "L-06_dual.json").exists(), "lands dual should be gone"
    assert (cards_dir / "001_foo.json").exists(), "card_gen card must survive a lands clear"
    assert not (set_dir / "lands").exists(), "lands log dir should be cleared"


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
    _open_test_project("TST", set_dir)

    stages_mod.clear_stage_artifacts("char_portraits")

    assert not refs_dir.exists()
    assert visual_refs.exists(), "upstream visual-references.json must be preserved"


def test_clear_art_gen_removes_art_log_dirs_and_decisions(fake_output_root: Path) -> None:
    # The merged art_gen stage owns the generated art/ images, both transcript
    # dirs it writes (art-generation-logs from image_generator, art-selection-logs
    # from art_selector), and the art_gen/ dir holding decisions.json (pick +
    # manual-override record). It also scrubs the art_path it stamps onto cards.
    # It must NOT touch art-direction/ — that's upstream visual_refs output.
    set_dir = fake_output_root / "sets" / "TST"
    art_dir = set_dir / "art"
    art_dir.mkdir(parents=True)
    (art_dir / "001_foo_v1.png").write_bytes(b"\x89PNG")
    gen_logs = set_dir / "art-generation-logs"
    gen_logs.mkdir(parents=True)
    (gen_logs / "001_foo.json").write_text("{}", encoding="utf-8")
    sel_logs = set_dir / "art-selection-logs"
    sel_logs.mkdir(parents=True)
    (sel_logs / "001_foo.json").write_text("{}", encoding="utf-8")
    decisions = set_dir / "art_gen" / "decisions.json"
    decisions.parent.mkdir(parents=True)
    decisions.write_text("{}", encoding="utf-8")
    # A card stamped with art_path by the selection sub-step.
    cards_dir = set_dir / "cards"
    cards_dir.mkdir(parents=True)
    card_path = cards_dir / "001_foo.json"
    card_path.write_text(
        json.dumps({"name": "Foo", "art_path": "art/001_foo_v1.png"}), encoding="utf-8"
    )
    # Upstream visual_refs artifact — must survive an art_gen clear.
    art_direction = set_dir / "art-direction"
    art_direction.mkdir(parents=True)
    visual_refs = art_direction / "visual-references.json"
    visual_refs.write_text("{}", encoding="utf-8")
    _open_test_project("TST", set_dir)

    stages_mod.clear_stage_artifacts("art_gen")
    assert not art_dir.exists()
    assert not gen_logs.exists()
    assert not sel_logs.exists()
    assert not decisions.parent.exists(), "art_gen/decisions.json must be cleared"
    assert json.loads(card_path.read_text(encoding="utf-8"))["art_path"] is None
    assert visual_refs.exists(), "upstream art-direction/ output must be preserved"


def test_clear_reprints_removes_selection_json(fake_output_root: Path) -> None:
    set_dir = fake_output_root / "sets" / "TST"
    set_dir.mkdir(parents=True)
    (set_dir / "reprint_selection.json").write_text("{}", encoding="utf-8")
    _open_test_project("TST", set_dir)

    stages_mod.clear_stage_artifacts("reprints")
    assert not (set_dir / "reprint_selection.json").exists()


def test_clear_reprints_unstamps_skeleton(fake_output_root: Path) -> None:
    # Clearing reprints must also revert the reprint stamps the stage wrote into
    # skeleton.json, so the slot returns to an ordinary (generatable) slot.
    import json

    set_dir = fake_output_root / "sets" / "TST"
    set_dir.mkdir(parents=True)
    (set_dir / "reprint_selection.json").write_text("{}", encoding="utf-8")
    skeleton = {
        "slots": [
            {"slot_id": "A", "is_reprint_slot": True, "reprint_card": "Murder · Instant"},
            {"slot_id": "B", "is_reprint_slot": False},
        ]
    }
    (set_dir / "skeleton.json").write_text(json.dumps(skeleton), encoding="utf-8")
    _open_test_project("TST", set_dir)

    stages_mod.clear_stage_artifacts("reprints")

    slots = {s["slot_id"]: s for s in json.loads((set_dir / "skeleton.json").read_text())["slots"]}
    assert slots["A"]["is_reprint_slot"] is False
    assert slots["A"]["reprint_card"] is None
    # The skeleton itself survives (only the stamps were cleared).
    assert (set_dir / "skeleton.json").exists()


def test_clear_rendering_removes_renders_dir(fake_output_root: Path) -> None:
    set_dir = fake_output_root / "sets" / "TST"
    renders_dir = set_dir / "renders"
    renders_dir.mkdir(parents=True)
    (renders_dir / "001.png").write_bytes(b"\x89PNG")
    _open_test_project("TST", set_dir)

    stages_mod.clear_stage_artifacts("rendering")
    assert not renders_dir.exists()


def test_clear_is_idempotent_on_missing_artifacts(fake_output_root: Path) -> None:
    """Clearing a stage whose artifacts don't exist should not raise."""
    _open_test_project("NEVER", fake_output_root / "sets" / "NEVER")
    stages_mod.clear_stage_artifacts("skeleton")
    stages_mod.clear_stage_artifacts("card_gen")
    stages_mod.clear_stage_artifacts("rendering")


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
    _open_test_project("TST", set_dir)

    for stage_id in (
        "conformance",
        "ai_review",
        "art_prompts",
    ):
        stages_mod.clear_stage_artifacts(stage_id)

    assert sentinel.exists(), "in-place mutator clearers must not touch cards/"


def test_clear_finalize_removes_reports_and_resets_sanity_markers(
    fake_output_root: Path,
) -> None:
    """The finalize clearer drops its reports + resets the per-card sanity markers.

    Finalize owns durable reports (``reports/finalize-report.{json,md}`` +
    ``reports/finalize-user-edits.json``) AND the reversible ``sanity_excluded`` /
    ``sanity_exclusion_reason`` markers it stamps onto ``cards/*.json``. A no-op clearer
    left all of these stale across an upstream unlock, so a now-PENDING finalize kept
    serving the old completed summary and excluded cards stayed hidden from the print
    set with no current verdict. The clearer must scrub the two finalize-owned fields
    *in place* without touching any other card field, and without deleting card files.
    """
    import json

    set_dir = fake_output_root / "sets" / "TST"
    reports_dir = set_dir / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "finalize-report.json").write_text('{"total_cards": 3}', encoding="utf-8")
    (reports_dir / "finalize-report.md").write_text("# report", encoding="utf-8")
    (reports_dir / "finalize-user-edits.json").write_text('{"001": true}', encoding="utf-8")

    logs_dir = set_dir / "finalize" / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "sanity.html").write_text("<html></html>", encoding="utf-8")

    cards_dir = set_dir / "cards"
    cards_dir.mkdir(parents=True)
    excluded = cards_dir / "001_foo.json"
    excluded.write_text(
        json.dumps(
            {
                "collector_number": "001",
                "name": "Foo",
                "oracle_text": "Flying",
                "sanity_excluded": True,
                "sanity_exclusion_reason": "missing power/toughness",
            }
        ),
        encoding="utf-8",
    )
    clean = cards_dir / "002_bar.json"
    clean.write_text(
        json.dumps({"collector_number": "002", "name": "Bar", "sanity_excluded": False}),
        encoding="utf-8",
    )
    _open_test_project("TST", set_dir)

    stages_mod.clear_stage_artifacts("finalize")

    # Reports + sanity-gate transcripts gone.
    assert not (reports_dir / "finalize-report.json").exists()
    assert not (reports_dir / "finalize-report.md").exists()
    assert not (reports_dir / "finalize-user-edits.json").exists()
    assert not (set_dir / "finalize").exists(), "sanity-gate finalize/logs should be cleared"

    # Card files survive; only the two finalize-owned fields were reset, other fields intact.
    assert excluded.exists(), "card files are card_gen-owned and must not be deleted"
    after = json.loads(excluded.read_text(encoding="utf-8"))
    assert after["sanity_excluded"] is False
    assert after["sanity_exclusion_reason"] is None
    assert after["name"] == "Foo", "non-finalize fields must be untouched"
    assert after["oracle_text"] == "Flying"
    # An already-clean card is left exactly as it was.
    assert clean.exists()
    assert json.loads(clean.read_text(encoding="utf-8")) == {
        "collector_number": "002",
        "name": "Bar",
        "sanity_excluded": False,
    }


def test_clear_finalize_is_idempotent_on_clean_project(fake_output_root: Path) -> None:
    """Clearing finalize on a project with no reports and clean cards must not raise."""
    import json

    set_dir = fake_output_root / "sets" / "TST"
    cards_dir = set_dir / "cards"
    cards_dir.mkdir(parents=True)
    (cards_dir / "001_foo.json").write_text(
        json.dumps({"collector_number": "001", "name": "Foo"}), encoding="utf-8"
    )
    _open_test_project("TST", set_dir)

    stages_mod.clear_stage_artifacts("finalize")  # no reports dir, no markers — a no-op
    stages_mod.clear_stage_artifacts("finalize")  # second pass still clean


def test_unknown_stage_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        stages_mod.clear_stage_artifacts("not_a_stage")
