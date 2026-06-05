"""HTTP-level tests for the Skeleton tab's input-validation path.

Pins the FastAPI contract for ``/api/wizard/skeleton/{knobs,save}``: a non-dict
``knobs`` value is a clean 400 (was a bare 500 — card 6a235147), an out-of-bucket
``irregular_subtypes`` pick is dropped with a warning, a valid dict still rebuilds
+ clamps numeric out-of-range, and ``/save`` rejects an unknown ``slot_id``.

The rebuild is purely deterministic (no AI), so no LLM is stubbed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mtgai.review.server import app
from mtgai.runtime import active_project, ai_lock, extraction_run
from mtgai.settings import model_settings as ms
from mtgai.skeleton.generator import SetConfig, generate_skeleton


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


def _seed_project(asset_dir: Path) -> str:
    """Active project + a real (small) skeleton.json. Returns a valid slot_id."""
    config = SetConfig(name="Test Set", code="TST", set_size=60, mechanic_count=3)
    result = generate_skeleton(config)
    skeleton = result.model_dump(mode="json")
    (asset_dir / "skeleton.json").write_text(
        json.dumps(skeleton, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    settings = ms.ModelSettings(
        asset_folder=str(asset_dir),
        set_params=ms.SetParams(set_name="Test Set", set_size=60, mechanic_count=3),
    )
    active_project.write_active_project(
        active_project.ProjectState(set_code="TST", settings=settings)
    )
    return skeleton["slots"][0]["slot_id"]


# ---------------------------------------------------------------------------
# PRIMARY: non-dict `knobs` is a clean 400, never a 500
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_knobs", ["hello", [1, 2, 3], 5, True])
def test_knobs_non_dict_value_is_400_not_500(client, isolated_output, bad_knobs):
    _seed_project(isolated_output)
    resp = client.post("/api/wizard/skeleton/knobs", json={"knobs": bad_knobs})
    assert resp.status_code == 400, resp.text
    assert "error" in resp.json()


def test_knobs_null_value_is_accepted(client, isolated_output):
    # `knobs: null` means "no knob edits" — a valid deterministic rebuild.
    _seed_project(isolated_output)
    resp = client.post("/api/wizard/skeleton/knobs", json={"knobs": None})
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Valid dict still rebuilds + clamps numeric out-of-range (unchanged behaviour)
# ---------------------------------------------------------------------------


def test_knobs_valid_dict_rebuilds_200(client, isolated_output):
    _seed_project(isolated_output)
    resp = client.post("/api/wizard/skeleton/knobs", json={"knobs": {"planeswalker_count": 1}})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["slots"]


def test_knobs_numeric_out_of_range_clamps_with_warning(client, isolated_output):
    _seed_project(isolated_output)
    resp = client.post("/api/wizard/skeleton/knobs", json={"knobs": {"rarity_common": 9999}})
    assert resp.status_code == 200, resp.text
    assert resp.json()["warnings"]  # the clamp is reported


# ---------------------------------------------------------------------------
# SECONDARY A: out-of-bucket irregular_subtypes is dropped with a warning
# ---------------------------------------------------------------------------


def test_knobs_unknown_irregular_subtype_dropped_with_warning(client, isolated_output):
    _seed_project(isolated_output)
    resp = client.post(
        "/api/wizard/skeleton/knobs",
        json={"knobs": {"irregular_subtypes": ["not_a_subtype", "saga"]}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # The bogus value is dropped, the real one kept (the rebuilt knobs round-trip
    # the cleaned picks); a warning surfaces the drop.
    assert body["knobs"]["irregular_subtypes"] == ["saga"]
    assert any("not_a_subtype" in w for w in body["warnings"])


# ---------------------------------------------------------------------------
# SECONDARY B: /save rejects an unknown slot_id
# ---------------------------------------------------------------------------


def test_save_unknown_slot_id_is_400(client, isolated_output):
    _seed_project(isolated_output)
    resp = client.post(
        "/api/wizard/skeleton/save",
        json={"slots": [{"slot_id": "ZZZ999", "tweaked_text": "x"}]},
    )
    assert resp.status_code == 400, resp.text
    assert "ZZZ999" in resp.json()["error"]


def test_save_known_slot_id_succeeds(client, isolated_output):
    slot_id = _seed_project(isolated_output)
    resp = client.post(
        "/api/wizard/skeleton/save",
        json={"slots": [{"slot_id": slot_id, "tweaked_text": "Hand-edited descriptor"}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] is True
