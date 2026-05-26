"""Unit tests for the constraint-deriver pure functions + mocked round-trip.

The two LLM passes (relabel / assign) and the color-batcher are exercised
with a monkeypatched ``generate_with_tool`` — no real model is ever loaded.
The reconcile logic (count guarantee, request placement, group dedup) is the
focus; cost math is stubbed out where it would otherwise need the price table.
"""

from __future__ import annotations

import json

import pytest

from mtgai.generation import constraint_deriver as cd
from mtgai.generation.prompts import format_slot_specs


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
            "notes": "",
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
            "notes": "",
        },
        {
            "slot_id": "B-U-03",
            "color": "B",
            "rarity": "uncommon",
            "card_type": "creature",
            "cmc_target": 3,
            "mechanic_tag": "complex",
            "signpost_for": None,
            "reserved_card": None,
            "notes": "",
        },
        {
            "slot_id": "M-U-04",
            "color": "multicolor",
            "rarity": "uncommon",
            "card_type": "creature",
            "cmc_target": 4,
            "mechanic_tag": "complex",
            "signpost_for": "WU",
            "reserved_card": None,
            "notes": "",
        },
        {
            "slot_id": "R-R-05",
            "color": "R",
            "rarity": "rare",
            "card_type": "sorcery",
            "cmc_target": 5,
            "mechanic_tag": "complex",
            "signpost_for": None,
            "reserved_card": None,
            "notes": "",
        },
        {
            "slot_id": "G-C-06",
            "color": "G",
            "rarity": "common",
            "card_type": "creature",
            "cmc_target": 3,
            "mechanic_tag": "evergreen",
            "signpost_for": None,
            "reserved_card": None,
            "notes": "",
        },
    ]


def _theme() -> dict:
    return {
        "code": "TST",
        "name": "",
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
        set_params=ms.SetParams(set_name="Test", set_size=6, mechanic_count=1),
    )
    active_project.write_active_project(
        active_project.ProjectState(set_code="TST", settings=settings)
    )
    return asset


# ---------------------------------------------------------------------------
# Seed rendering
# ---------------------------------------------------------------------------


def test_render_seed_matrix_one_line_per_slot() -> None:
    lines = cd.render_seed_matrix(_seed_slots()).splitlines()
    assert len(lines) == 6
    assert lines[0].startswith("W-C-01 | White | common | creature | CMC2")
    # The multicolor uncommon carries its signpost marker.
    assert "signpost: WU" in cd.render_seed_matrix([_seed_slots()[3]])


# ---------------------------------------------------------------------------
# Pass 1 — relabel + reconcile
# ---------------------------------------------------------------------------


def test_relabel_reconciles_missing_and_drops_unknown(_project, monkeypatch) -> None:
    seed = _seed_slots()

    def stub(*_a, **_k):
        # Blobs for all but the last seed slot, plus a bogus slot_id.
        slots = [{"slot_id": s["slot_id"], "blob": f"themed {s['slot_id']}"} for s in seed[:-1]]
        slots.append({"slot_id": "BOGUS-99", "blob": "ignore me"})
        return {"result": {"slots": slots}, "model": "m", "input_tokens": 1, "output_tokens": 2}

    monkeypatch.setattr(cd, "generate_with_tool", stub)
    matrix, _resp = cd.relabel_matrix(
        seed_slots=seed,
        theme=_theme(),
        approved=_approved(),
        archetypes=[],
        set_name="T",
        set_size=6,
        model="m",
    )
    # Count guarantee: every seed slot present, in order; unknown dropped.
    assert [m["slot_id"] for m in matrix] == [s["slot_id"] for s in seed]
    assert matrix[0]["blob"] == "themed W-C-01"
    # The dropped slot is filled from its seed line (carries its rarity).
    assert "common" in matrix[-1]["blob"]
    assert all(m["reserved_card"] is None for m in matrix)


# ---------------------------------------------------------------------------
# Pass 2 — request assignment
# ---------------------------------------------------------------------------


def test_assign_requests_places_and_rewrites(monkeypatch) -> None:
    matrix = [
        {"slot_id": "A", "blob": "x", "reserved_card": None},
        {"slot_id": "B", "blob": "y", "reserved_card": None},
    ]

    def stub(*_a, **_k):
        return {
            "result": {
                "assignments": [
                    {"request": "Cogwarden", "slot_id": "B", "blob": "Cogwarden, legendary"},
                ]
            },
            "model": "m",
            "input_tokens": 1,
            "output_tokens": 1,
        }

    monkeypatch.setattr(cd, "generate_with_tool", stub)
    out, resp = cd.assign_requests(matrix=matrix, card_requests=[{"text": "Cogwarden"}], model="m")
    placed = next(m for m in out if m["slot_id"] == "B")
    assert placed["reserved_card"] == "Cogwarden"
    assert placed["blob"] == "Cogwarden, legendary"
    assert resp is not None


def test_assign_requests_no_requests_skips_call(monkeypatch) -> None:
    called = {"n": 0}

    def stub(*_a, **_k):
        called["n"] += 1
        return {"result": {}, "model": "m"}

    monkeypatch.setattr(cd, "generate_with_tool", stub)
    matrix = [{"slot_id": "A", "blob": "x", "reserved_card": None}]
    out, resp = cd.assign_requests(matrix=matrix, card_requests=[], model="m")
    assert resp is None
    assert called["n"] == 0
    assert out == matrix


def test_assign_requests_skips_duplicate_slot(monkeypatch) -> None:
    matrix = [{"slot_id": "A", "blob": "x", "reserved_card": None}]

    def stub(*_a, **_k):
        return {
            "result": {
                "assignments": [
                    {"request": "First", "slot_id": "A", "blob": "first"},
                    {"request": "Second", "slot_id": "A", "blob": "second"},  # dup slot, skipped
                    {"request": "Third", "slot_id": "ZZZ", "blob": "nope"},  # unknown slot, skipped
                ]
            },
            "model": "m",
            "input_tokens": 1,
            "output_tokens": 1,
        }

    monkeypatch.setattr(cd, "generate_with_tool", stub)
    out, _resp = cd.assign_requests(matrix=matrix, card_requests=[{"text": "x"}], model="m")
    assert out[0]["reserved_card"] == "First"
    assert out[0]["blob"] == "first"


# ---------------------------------------------------------------------------
# Orchestrator round-trip
# ---------------------------------------------------------------------------


def test_derive_constraints_round_trip(_project, monkeypatch) -> None:
    def stub(*_a, **k):
        name = k["tool_schema"]["name"]
        if name == "submit_themed_matrix":
            slots = [
                {"slot_id": s["slot_id"], "blob": f"themed {s['slot_id']}"} for s in _seed_slots()
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
                            "slot_id": "R-R-05",
                            "blob": "Cogwarden — legendary artifact guardian",
                        },
                    ]
                },
                "model": "m",
                "input_tokens": 5,
                "output_tokens": 5,
            }
        raise AssertionError(f"unexpected tool {name}")

    monkeypatch.setattr(cd, "generate_with_tool", stub)
    monkeypatch.setattr(cd, "cost_from_result", lambda _r: 0.01)

    out = cd.derive_constraints()
    assert len(out["slots"]) == 6
    assert out["seed_slot_count"] == 6
    placed = [m for m in out["slots"] if m["reserved_card"]]
    assert len(placed) == 1
    assert placed[0]["slot_id"] == "R-R-05"
    assert placed[0]["blob"] == "Cogwarden — legendary artifact guardian"
    assert out["input_tokens"] == 15
    assert out["output_tokens"] == 25
    assert out["cost_usd"] == pytest.approx(0.02)
    assert out["model_id"]  # resolved from settings


# ---------------------------------------------------------------------------
# On-disk loader
# ---------------------------------------------------------------------------


def test_load_constraints_matrix(_project) -> None:
    asset = _project
    assert cd.load_constraints_matrix(asset) is None  # absent → None
    (asset / "constraints.json").write_text(
        json.dumps({"slots": [{"slot_id": "A", "blob": "b", "reserved_card": None}]}),
        encoding="utf-8",
    )
    loaded = cd.load_constraints_matrix(asset)
    assert loaded is not None
    assert loaded[0]["slot_id"] == "A"


# ---------------------------------------------------------------------------
# LLM color-batcher
# ---------------------------------------------------------------------------


def test_llm_group_slots_reconciles_to_every_slot_once(monkeypatch) -> None:
    slots = [{"slot_id": f"S{i}", "blob": "b"} for i in range(12)]

    def stub(*_a, **_k):
        return {
            "result": {
                "groups": [
                    ["S0", "S1", "S2"],
                    ["S0", "S3"],  # S0 dup → only S3 survives
                    ["S4", "S5", "S6", "S7", "S8"],
                ]
            },  # S9..S11 omitted → appended as a leftover chunk
            "model": "m",
        }

    monkeypatch.setattr(cd, "generate_with_tool", stub)
    groups = cd.llm_group_slots(slots, batch_size=5, model="m")
    flat = [s for g in groups for s in g]
    assert set(flat) == {f"S{i}" for i in range(12)}  # every slot covered
    assert len(flat) == 12  # exactly once (no duplicates)
    assert all(len(g) <= 5 for g in groups)  # cap respected


def test_llm_group_slots_small_list_single_group() -> None:
    groups = cd.llm_group_slots([{"slot_id": "A", "blob": "b"}], batch_size=5, model="m")
    assert groups == [["A"]]


def test_llm_group_slots_falls_back_on_error(monkeypatch) -> None:
    slots = [{"slot_id": f"S{i}", "blob": "b"} for i in range(8)]

    def boom(*_a, **_k):
        raise RuntimeError("model down")

    monkeypatch.setattr(cd, "generate_with_tool", boom)
    groups = cd.llm_group_slots(slots, batch_size=5, model="m")
    flat = [s for g in groups for s in g]
    assert sorted(flat) == sorted(s["slot_id"] for s in slots)
    assert all(len(g) <= 5 for g in groups)


# ---------------------------------------------------------------------------
# Card-gen consumption — format_slot_specs blob branch
# ---------------------------------------------------------------------------


def test_format_slot_specs_uses_blob_when_present() -> None:
    slots = [
        {
            "slot_id": "A",
            "color": "W",
            "rarity": "common",
            "card_type": "creature",
            "cmc_target": 2,
            "_blob": "Blue tempo trick; mechanic menu: {Salvage}",
            "reserved_card": "Megatron",
        }
    ]
    out = format_slot_specs(slots)
    assert "Blue tempo trick" in out
    assert "{Salvage}" in out
    assert "Megatron" in out  # reserved_card repeated explicitly
    # The structured line is NOT emitted when a blob is present.
    assert "White common creature" not in out


def test_format_slot_specs_structured_path_without_blob() -> None:
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
