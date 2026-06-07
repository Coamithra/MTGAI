"""Pins that the Character References + Art Generation *refresh endpoints* scope
the LLM tok/s poller to the LLM-only sub-phase, NEVER the ComfyUI image phase.

Card 6a25497b scoped the poller in the ENGINE runners (``stages.run_char_portraits``
via ``detect_poller``, ``stages.run_art_gen`` polling only the ``art_select``
judge). But the UI buttons call the REFRESH ENDPOINTS in ``server.py``, which still
wrapped the WHOLE call (including the ComfyUI image-generation phase) in
``_bus_poller``. That poller probes ``/upstream/<model>/slots`` every ~0.5s, which
makes managed-mode llama-swap RELOAD the just-unloaded LLM into VRAM during image
gen, starving Flux (~1.6s/step -> ~25-40s/step). Card 6a254d60 mirrors the
engine-path scoping onto the endpoints. These tests guard that contract.

The tests patch the underlying gen/select functions + ``server._bus_poller`` with
a tracking context manager, then drive the endpoints and assert:
  * char_refs/refresh passes a ``detect_poller`` to ``generate_character_refs``
    (and does NOT wrap the whole call in a poller span);
  * art_gen/refresh + art_gen/reroll poll ONLY the judge phase (``art_select``),
    with NO poller built/active around the ComfyUI ``generate_art_for_set`` call.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from mtgai.pipeline import server
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


def _seed_project(isolated_output):
    asset = isolated_output / "sets" / "TST"
    asset.mkdir(parents=True, exist_ok=True)
    (asset / "cards").mkdir(parents=True, exist_ok=True)
    settings = ms.ModelSettings(
        asset_folder=str(asset),
        set_params=ms.SetParams(set_name="Brass Sky", set_size=60, mechanic_count=3),
    )
    active_project.write_active_project(
        active_project.ProjectState(set_code="TST", settings=settings)
    )
    return asset


class _TrackingPoller:
    """A ``_bus_poller`` stand-in that records its enter/exit + whether active.

    The image-gen stub asserts the poller is NOT active while it runs, proving the
    ComfyUI phase is out-of-band of any tok/s poller span.
    """

    def __init__(self, stage_id: str) -> None:
        self.stage_id = stage_id
        self.active = False
        self.entered = False

    def __enter__(self):
        self.active = True
        self.entered = True
        return self

    def __exit__(self, *_exc) -> None:
        self.active = False


def _patch_tracking_bus_poller(monkeypatch):
    """Replace ``server._bus_poller`` with a factory that records every poller it
    builds (keyed by stage_id) so a test can assert which phases were polled."""
    built: dict[str, _TrackingPoller] = {}

    @contextmanager
    def fake_bus_poller(stage_id, **_kw):
        poller = _TrackingPoller(stage_id)
        built[stage_id] = poller
        with poller:
            yield

    # For char_refs the poller is *passed* (not entered on the event loop), so the
    # endpoint needs the raw context-manager object, not an already-entered one.
    def bus_poller_cm(stage_id, **_kw):
        return fake_bus_poller(stage_id, **_kw)

    monkeypatch.setattr(server, "_bus_poller", bus_poller_cm)
    return built


def test_char_refs_refresh_passes_detect_poller_not_whole_wrap(
    client, isolated_output, monkeypatch
):
    """char_refs/refresh must pass the poller as ``detect_poller`` to
    ``generate_character_refs`` (scoped to step-1 detection inside the worker),
    NOT wrap the entire call (incl. ComfyUI image gen) in a poller span."""
    _seed_project(isolated_output)
    built = _patch_tracking_bus_poller(monkeypatch)

    captured: dict[str, object] = {}

    def fake_generate_character_refs(*_a, detect_poller=None, **_k):
        captured["detect_poller"] = detect_poller
        # The endpoint must hand us a context manager (the poller), not enter it
        # itself: at call time, NO poller span may be active around us.
        captured["any_poller_active_at_call"] = any(p.active for p in built.values())
        # Honour the contract: enter the detect_poller around "detection" only.
        from contextlib import nullcontext

        with detect_poller or nullcontext():
            captured["detect_poller_active_inside"] = (
                isinstance(detect_poller, _TrackingPoller) and detect_poller.active
            ) or (built.get("char_portraits") is not None and built["char_portraits"].active)
        return {"generated": 1, "entities": 1, "cards_modified": 1, "failed": 0, "cost_usd": 0.0}

    monkeypatch.setattr(
        "mtgai.art.character_portraits.generate_character_refs",
        fake_generate_character_refs,
    )

    resp = client.post("/api/wizard/char_refs/refresh")
    assert resp.status_code == 200, resp.text

    # The endpoint passed a poller as detect_poller (not None).
    assert captured.get("detect_poller") is not None, (
        "char_refs/refresh must pass a detect_poller to generate_character_refs"
    )
    # It must NOT have wrapped the whole call: no poller span active at call time.
    assert captured.get("any_poller_active_at_call") is False, (
        "the poller must NOT wrap the whole generate_character_refs call"
    )
    # And the poller IS entered around the detection sub-phase (telemetry kept).
    assert captured.get("detect_poller_active_inside") is True
    # Exactly the char_portraits poller was built (no stray art poller).
    assert set(built) == {"char_portraits"}


def test_art_gen_refresh_polls_only_judge_not_image_gen(client, isolated_output, monkeypatch):
    """art_gen/refresh must run the ComfyUI ``generate_art_for_set`` phase with NO
    poller and wrap ONLY the ``select_art_for_set`` judge in ``_bus_poller`` keyed
    to the ``art_select`` model (matching ``stages.run_art_gen``)."""
    _seed_project(isolated_output)
    built = _patch_tracking_bus_poller(monkeypatch)

    state: dict[str, object] = {}

    def fake_gen(**_k):
        # No poller may exist/be active during the ComfyUI generate phase.
        state["pollers_at_gen"] = set(built)
        state["any_active_at_gen"] = any(p.active for p in built.values())
        return {"generated": 2, "skipped": 0, "failed": 0, "cancelled": False}

    def fake_select(**_k):
        state["judge_poller_active"] = (
            built.get("art_select") is not None and built["art_select"].active
        )
        return {"reviewed": 2, "estimated_cost_usd": 0.0, "cancelled": False}

    monkeypatch.setattr("mtgai.art.image_generator.generate_art_for_set", fake_gen)
    monkeypatch.setattr("mtgai.art.art_selector.select_art_for_set", fake_select)

    resp = client.post("/api/wizard/art_gen/refresh", json={})
    assert resp.status_code == 200, resp.text

    # The image-gen phase ran with no poller built at all.
    assert state.get("pollers_at_gen") == set(), (
        "no LLM poller may be built before/around the ComfyUI image-generation phase"
    )
    assert state.get("any_active_at_gen") is False
    # The judge phase IS polled — telemetry preserved — keyed to art_select.
    assert "art_select" in built and built["art_select"].entered
    assert state.get("judge_poller_active") is True
    # And the old whole-call "art_gen" poller is gone.
    assert "art_gen" not in built


def test_art_gen_reroll_polls_only_judge_not_image_gen(client, isolated_output, monkeypatch):
    """art_gen/reroll (single-card) must apply the same scoping: ComfyUI gen with
    NO poller, judge wrapped in the ``art_select`` poller."""
    _seed_project(isolated_output)
    built = _patch_tracking_bus_poller(monkeypatch)

    state: dict[str, object] = {}

    def fake_gen(**_k):
        state["pollers_at_gen"] = set(built)
        state["any_active_at_gen"] = any(p.active for p in built.values())
        return {"generated": 1, "skipped": 0, "failed": 0, "cancelled": False}

    def fake_select(**_k):
        state["judge_poller_active"] = (
            built.get("art_select") is not None and built["art_select"].active
        )
        return {"reviewed": 1, "estimated_cost_usd": 0.0, "cancelled": False}

    monkeypatch.setattr("mtgai.art.image_generator.generate_art_for_set", fake_gen)
    monkeypatch.setattr("mtgai.art.art_selector.select_art_for_set", fake_select)

    resp = client.post("/api/wizard/art_gen/reroll", json={"collector_number": "001"})
    assert resp.status_code == 200, resp.text

    assert state.get("pollers_at_gen") == set(), (
        "no LLM poller may be built before/around the ComfyUI image-generation phase"
    )
    assert state.get("any_active_at_gen") is False
    assert "art_select" in built and built["art_select"].entered
    assert state.get("judge_poller_active") is True
    assert "art_gen" not in built
