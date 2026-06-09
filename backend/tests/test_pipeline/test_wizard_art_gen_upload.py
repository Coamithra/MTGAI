"""Regression tests for ``POST /api/wizard/art_gen/upload`` version numbering.

The upload endpoint used to pick the new version as ``len(glob) + 1``. With a
version gap on disk — the acknowledged exhausted-retries state, e.g. only
``_v2.png`` and ``_v3.png`` survive — ``len == 2`` gave ``next_v == 3`` and the
write silently OVERWROTE the existing generated ``_v3.png`` (and, if v3 was the
stamped pick, its decision record then pointed at the user's different image).

The fix computes the next version as ``max(existing version numbers) + 1`` and
never writes over an existing file, so the upload lands as ``_v4.png`` and leaves
``_v3.png`` byte-identical.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mtgai.art.art_selector import load_art_decisions
from mtgai.art.image_generator import next_art_version
from mtgai.io.paths import card_slug
from mtgai.review.server import app
from mtgai.runtime import active_project, ai_lock, extraction_run
from mtgai.settings import model_settings as ms


@pytest.fixture(autouse=True)
def _reset(isolated_output):
    ai_lock.reset_for_tests()
    extraction_run.reset()
    yield
    ai_lock.reset_for_tests()
    extraction_run.reset()


@pytest.fixture
def client():
    return TestClient(app)


def _seed_project(asset_dir: Path) -> None:
    asset_dir.mkdir(parents=True, exist_ok=True)
    settings = ms.ModelSettings(
        asset_folder=str(asset_dir),
        set_params=ms.SetParams(set_name="Brass Sky", set_size=60, mechanic_count=3),
    )
    active_project.write_active_project(
        active_project.ProjectState(set_code="TST", settings=settings)
    )


def _write_card(asset_dir: Path, cn: str, name: str) -> str:
    cards = asset_dir / "cards"
    cards.mkdir(parents=True, exist_ok=True)
    slug = card_slug(cn, name)
    (cards / f"{slug}.json").write_text(
        json.dumps(
            {
                "collector_number": cn,
                "name": name,
                "rarity": "common",
                "mana_cost": "{R}",
                "type_line": "Instant",
                "oracle_text": "Deal 3 damage to any target.",
                "colors": ["R"],
                "status": "draft",
            }
        ),
        encoding="utf-8",
    )
    return slug


# ---------------------------------------------------------------------------
# next_art_version helper (the core fix)
# ---------------------------------------------------------------------------


def test_next_art_version_no_files_is_one(tmp_path):
    assert next_art_version(tmp_path, "001_bolt") == 1


def test_next_art_version_uses_max_not_count(tmp_path):
    # Gapped: only _v2 and _v3 on disk. count+1 would give 3 (collision); the
    # correct answer is max(2, 3) + 1 == 4.
    (tmp_path / "001_bolt_v2.png").write_bytes(b"v2")
    (tmp_path / "001_bolt_v3.png").write_bytes(b"v3")
    assert next_art_version(tmp_path, "001_bolt") == 4


def test_next_art_version_skips_non_numeric_suffix(tmp_path):
    (tmp_path / "001_bolt_v3.png").write_bytes(b"v3")
    (tmp_path / "001_bolt_v3a.png").write_bytes(b"weird")  # not a plain int -> skipped
    assert next_art_version(tmp_path, "001_bolt") == 4


# ---------------------------------------------------------------------------
# POST /api/wizard/art_gen/upload — the regression scenario end to end
# ---------------------------------------------------------------------------


def test_upload_with_version_gap_does_not_overwrite(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    slug = _write_card(asset, "001", "Lightning Bolt")

    art_dir = asset / "art"
    art_dir.mkdir(parents=True, exist_ok=True)
    v2 = art_dir / f"{slug}_v2.png"
    v3 = art_dir / f"{slug}_v3.png"
    v2.write_bytes(b"GENERATED-V2-PIXELS")
    v3.write_bytes(b"GENERATED-V3-PIXELS")

    uploaded = b"USER-UPLOADED-PIXELS"
    resp = client.post(
        "/api/wizard/art_gen/upload",
        data={"collector_number": "001"},
        files={"file": ("art.png", io.BytesIO(uploaded), "image/png")},
    )
    assert resp.status_code == 200

    # The upload landed as _v4, NOT _v3.
    v4 = art_dir / f"{slug}_v4.png"
    assert v4.exists()
    assert v4.read_bytes() == uploaded

    # The pre-existing generated _v3 is untouched (byte-identical).
    assert v3.read_bytes() == b"GENERATED-V3-PIXELS"
    assert v2.read_bytes() == b"GENERATED-V2-PIXELS"

    # The decision record points at the uploaded file (authoritative anchor),
    # and its positional pick agrees with the file's place in the sorted glob.
    decisions = load_art_decisions(asset)
    rec = decisions["001"]
    assert rec["picked_file"] == v4.name
    assert rec["source"] == "user"
    version_files = rec["version_files"]
    assert version_files.index(v4.name) + 1 == int(rec["pick"].lstrip("v"))
