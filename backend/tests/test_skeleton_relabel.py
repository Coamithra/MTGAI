"""Unit tests for skeleton relabel — the LLM half of Skeleton Generation.

The two passes (relabel / assign) are exercised with a monkeypatched
``generate_with_tool`` — no real model is ever loaded. The reconcile logic
(count guarantee, request placement) is the focus; cost math is stubbed where
it would otherwise need the price table.
"""

from __future__ import annotations

import json

import pytest

from mtgai.generation import skeleton_relabel as sr
from mtgai.generation.prompts import format_slot_specs
from mtgai.skeleton.generator import render_slot_string


def _seed_slots() -> list[dict]:
    return [
        {
            "slot_id": "W-C-01",
            "color": "W",
            "rarity": "common",
            "card_type": "creature",
            "cmc_target": 2,
            "mechanic_tag": "vanilla",
            "signpost_for": None,
            "reserved_card": None,
        },
        {
            "slot_id": "U-C-02",
            "color": "U",
            "rarity": "common",
            "card_type": "instant",
            "cmc_target": 2,
            "mechanic_tag": "complex",
            "signpost_for": None,
            "reserved_card": None,
        },
        {
            "slot_id": "M-U-03",
            "color": "multicolor",
            "rarity": "uncommon",
            "card_type": "creature",
            "cmc_target": 4,
            "mechanic_tag": "complex",
            "signpost_for": "WU",
            "reserved_card": None,
        },
        {
            "slot_id": "R-R-04",
            "color": "R",
            "rarity": "rare",
            "card_type": "sorcery",
            "cmc_target": 5,
            "mechanic_tag": "complex",
            "signpost_for": None,
            "reserved_card": None,
        },
    ]


def _theme() -> dict:
    return {
        "code": "TST",
        "setting": "A test world of clockwork warbeasts.",
        "constraints": [{"text": "lots of artifacts"}],
        "card_requests": [{"text": "Cogwarden, legendary artifact guardian"}],
    }


def _approved() -> list[dict]:
    return [{"name": "Salvage", "colors": ["U", "G"], "reminder_text": "(do salvage)"}]


@pytest.fixture
def _project(isolated_output):
    """Pin a minimal active project with skeleton/theme/mechanics/archetypes on disk."""
    from mtgai.runtime import active_project
    from mtgai.settings import model_settings as ms

    asset = isolated_output / "sets" / "TST"
    (asset / "mechanics").mkdir(parents=True, exist_ok=True)
    (asset / "skeleton.json").write_text(json.dumps({"slots": _seed_slots()}), encoding="utf-8")
    (asset / "theme.json").write_text(json.dumps(_theme()), encoding="utf-8")
    (asset / "mechanics" / "approved.json").write_text(json.dumps(_approved()), encoding="utf-8")
    (asset / "archetypes.json").write_text(
        json.dumps([{"color_pair": "WU", "name": "Tempo", "description": "win with fliers"}]),
        encoding="utf-8",
    )
    settings = ms.ModelSettings(
        asset_folder=str(asset),
        set_params=ms.SetParams(set_name="Test", set_size=4, mechanic_count=1),
    )
    active_project.write_active_project(
        active_project.ProjectState(set_code="TST", settings=settings)
    )
    return asset


# ---------------------------------------------------------------------------
# Default descriptor rendering
# ---------------------------------------------------------------------------


def test_render_slot_string_format() -> None:
    s = _seed_slots()[0]
    assert render_slot_string(s) == "White · common · creature · CMC2 · vanilla"
    # The multicolor uncommon carries its signpost marker.
    assert render_slot_string(_seed_slots()[2]).endswith("· signpost:WU")


# ---------------------------------------------------------------------------
# Pass 1 — relabel + reconcile
# ---------------------------------------------------------------------------


def test_relabel_reconciles_missing_and_drops_unknown(_project, monkeypatch) -> None:
    seed = _seed_slots()

    def stub(*_a, **_k):
        # Rewrites for all but the last seed slot, plus a bogus slot_id.
        slots = [{"slot_id": s["slot_id"], "text": f"themed {s['slot_id']}"} for s in seed[:-1]]
        slots.append({"slot_id": "BOGUS-99", "text": "ignore me"})
        return {"result": {"slots": slots}, "model": "m", "input_tokens": 1, "output_tokens": 2}

    monkeypatch.setattr(sr, "generate_with_tool", stub)
    tweaked, _resp = sr.relabel_slots(
        slots=seed,
        theme=_theme(),
        approved=_approved(),
        archetypes=[],
        set_name="T",
        set_size=4,
        model="m",
    )
    # Count guarantee: every seed slot present; unknown dropped.
    assert set(tweaked) == {s["slot_id"] for s in seed}
    assert tweaked["W-C-01"] == "themed W-C-01"
    # The dropped slot keeps its default descriptor.
    assert tweaked["R-R-04"] == render_slot_string(seed[-1])


# ---------------------------------------------------------------------------
# Pass 2 — request assignment
# ---------------------------------------------------------------------------


def test_assign_requests_places_and_rewrites(monkeypatch) -> None:
    tweaked = {"A": "x", "B": "y"}

    def stub(*_a, **_k):
        return {
            "result": {
                "assignments": [
                    {"request": "Cogwarden", "slot_id": "B", "text": "Cogwarden, legendary"},
                ]
            },
            "model": "m",
            "input_tokens": 1,
            "output_tokens": 1,
        }

    monkeypatch.setattr(sr, "generate_with_tool", stub)
    out, reserved, resp = sr.assign_requests(
        slots=[{"slot_id": "A"}, {"slot_id": "B"}],
        tweaked=tweaked,
        card_requests=[{"text": "Cogwarden"}],
        model="m",
    )
    assert reserved == {"B": "Cogwarden"}
    assert out["B"] == "Cogwarden, legendary"
    assert resp is not None


def test_assign_requests_no_requests_skips_call(monkeypatch) -> None:
    called = {"n": 0}

    def stub(*_a, **_k):
        called["n"] += 1
        return {"result": {}, "model": "m"}

    monkeypatch.setattr(sr, "generate_with_tool", stub)
    _out, reserved, resp = sr.assign_requests(
        slots=[{"slot_id": "A"}], tweaked={"A": "x"}, card_requests=[], model="m"
    )
    assert resp is None
    assert reserved == {}
    assert called["n"] == 0


def test_assign_requests_skips_duplicate_and_unknown(monkeypatch) -> None:
    def stub(*_a, **_k):
        return {
            "result": {
                "assignments": [
                    {"request": "First", "slot_id": "A", "text": "first"},
                    {"request": "Second", "slot_id": "A", "text": "second"},  # dup slot, skipped
                    {"request": "Third", "slot_id": "ZZ", "text": "nope"},  # unknown slot, skipped
                ]
            },
            "model": "m",
            "input_tokens": 1,
            "output_tokens": 1,
        }

    monkeypatch.setattr(sr, "generate_with_tool", stub)
    out, reserved, _resp = sr.assign_requests(
        slots=[{"slot_id": "A"}], tweaked={"A": "x"}, card_requests=[{"text": "x"}], model="m"
    )
    assert reserved == {"A": "First"}
    assert out["A"] == "first"


# ---------------------------------------------------------------------------
# Orchestrator round-trip
# ---------------------------------------------------------------------------


def test_relabel_skeleton_round_trip(_project, monkeypatch) -> None:
    def stub(*_a, **k):
        name = k["tool_schema"]["name"]
        if name == "submit_relabeled_slots":
            slots = [
                {"slot_id": s["slot_id"], "text": f"themed {s['slot_id']}"} for s in _seed_slots()
            ]
            return {
                "result": {"slots": slots},
                "model": "m",
                "input_tokens": 10,
                "output_tokens": 20,
            }
        if name == "submit_request_assignments":
            return {
                "result": {
                    "assignments": [
                        {
                            "request": "Cogwarden, legendary artifact guardian",
                            "slot_id": "R-R-04",
                            "text": "Cogwarden — legendary artifact guardian",
                        },
                    ]
                },
                "model": "m",
                "input_tokens": 5,
                "output_tokens": 5,
            }
        raise AssertionError(f"unexpected tool {name}")

    monkeypatch.setattr(sr, "generate_with_tool", stub)
    monkeypatch.setattr(sr, "cost_from_result", lambda _r: 0.01)

    out = sr.relabel_skeleton(slots=_seed_slots())
    updates = out["updates"]
    assert set(updates) == {s["slot_id"] for s in _seed_slots()}
    assert updates["W-C-01"]["tweaked_text"] == "themed W-C-01"
    # The placed request rewrites its slot + sets reserved_card.
    assert updates["R-R-04"]["reserved_card"] == "Cogwarden, legendary artifact guardian"
    assert updates["R-R-04"]["tweaked_text"] == "Cogwarden — legendary artifact guardian"
    assert out["input_tokens"] == 15
    assert out["output_tokens"] == 25
    assert out["cost_usd"] == pytest.approx(0.02)
    assert out["model_id"]  # resolved from settings


# ---------------------------------------------------------------------------
# Card-gen consumption — format_slot_specs tweaked_text branch
# ---------------------------------------------------------------------------


def test_format_slot_specs_uses_tweaked_text() -> None:
    slots = [
        {
            "slot_id": "A",
            "color": "W",
            "rarity": "common",
            "card_type": "creature",
            "cmc_target": 2,
            "tweaked_text": "Blue · common · instant · CMC2 · Salvage",
            "reserved_card": "Megatron",
        }
    ]
    out = format_slot_specs(slots)
    assert "Blue · common · instant · CMC2 · Salvage" in out
    assert "Megatron" in out  # reserved_card repeated explicitly
    # The structured fallback line is NOT emitted when tweaked_text is present.
    assert "White common creature" not in out


def test_format_slot_specs_structured_path_without_tweak() -> None:
    slots = [
        {
            "slot_id": "A",
            "color": "W",
            "rarity": "common",
            "card_type": "creature",
            "cmc_target": 2,
            "mechanic_tag": "vanilla",
        }
    ]
    out = format_slot_specs(slots)
    assert "White common creature" in out
