"""Phase B/C integration tests for cycles (card 6a16d8ff).

Covers cycle-coherent batching in card-gen, the CYCLE MEMBER prompt instruction,
reprint identification skipping cycle members, and the lands stage generating a
land cycle (``generate_with_tool`` monkeypatched — no real model).
"""

from __future__ import annotations

import json
from pathlib import Path

import mtgai.generation.land_generator as land_gen
from mtgai.generation.card_generator import group_slots_into_batches
from mtgai.generation.prompts import format_slot_specs
from mtgai.generation.reprint_selector import _load_slot_texts

# ---------------------------------------------------------------------------
# Cycle-coherent batching
# ---------------------------------------------------------------------------


def _slot(slot_id, color, color_pair=None, cycle_id=None, card_type="creature"):
    return {
        "slot_id": slot_id,
        "color": color,
        "color_pair": color_pair,
        "card_type": card_type,
        "rarity": "rare",
        "cmc_target": 3,
    } | ({"cycle_id": cycle_id} if cycle_id else {})


class TestCycleBatching:
    def test_cycle_members_batched_together(self):
        slots = [
            _slot("1", "W", cycle_id="titans"),
            _slot("2", "U", cycle_id="titans"),
            _slot("3", "B", cycle_id="titans"),
            _slot("4", "R", cycle_id="titans"),
            _slot("5", "G", cycle_id="titans"),
            _slot("6", "W"),
            _slot("7", "U"),
        ]
        batches = group_slots_into_batches(slots, batch_size=10)
        cycle_batch = next(b for b in batches if b[0].get("cycle_id") == "titans")
        assert len(cycle_batch) == 5
        assert {s["color"] for s in cycle_batch} == {"W", "U", "B", "R", "G"}
        # The two ordinary slots are not in the cycle batch.
        assert all(
            not s.get("cycle_id") for b in batches if b[0].get("cycle_id") != "titans" for s in b
        )

    def test_large_cycle_split_by_batch_size(self):
        slots = [_slot(str(i), "multicolor", color_pair="WU", cycle_id="gates") for i in range(10)]
        batches = group_slots_into_batches(slots, batch_size=4)
        cycle_batches = [b for b in batches if b[0].get("cycle_id") == "gates"]
        assert [len(b) for b in cycle_batches] == [4, 4, 2]


# ---------------------------------------------------------------------------
# CYCLE MEMBER prompt note
# ---------------------------------------------------------------------------


class TestCyclePromptNote:
    def test_tweaked_path_includes_template(self):
        slots = [
            {
                "slot_id": "1",
                "color": "W",
                "rarity": "rare",
                "card_type": "creature",
                "cmc_target": 6,
                "tweaked_text": "White rare creature CMC6",
                "cycle_id": "titans",
                "cycle_template": "A mono-color titan with a color-keyed ability.",
            }
        ]
        out = format_slot_specs(slots)
        assert "CYCLE MEMBER" in out
        assert "A mono-color titan" in out

    def test_structured_path_includes_note(self):
        slots = [_slot("1", "W", cycle_id="titans")]
        out = format_slot_specs(slots)
        assert "CYCLE MEMBER" in out

    def test_non_cycle_slot_has_no_note(self):
        out = format_slot_specs([_slot("1", "W")])
        assert "CYCLE MEMBER" not in out


# ---------------------------------------------------------------------------
# Reprint candidate slots: all unfilled slots (cycle avoidance is prompt-driven)
# ---------------------------------------------------------------------------


def test_load_slot_texts_includes_cycle_members(tmp_path: Path):
    """Slots are plain text after the skeleton stage, so the reprint stage offers
    *every* unfilled slot to the placement LLM — cycle members included. Avoiding
    them is the placement prompt's job (the descriptor carries a ``cycle:`` tag),
    not a structured filter."""
    skeleton = {
        "slots": [
            {
                "slot_id": "1",
                "color": "W",
                "rarity": "common",
                "card_type": "creature",
                "cmc_target": 2,
                "mechanic_tag": "vanilla",
                "card_id": None,
            },
            {
                "slot_id": "2",
                "color": "U",
                "rarity": "common",
                "card_type": "creature",
                "cmc_target": 2,
                "mechanic_tag": "vanilla",
                "card_id": None,
                "cycle_id": "c",
            },
            # A filled slot is excluded (you can't reprint over an assigned card).
            {"slot_id": "3", "tweaked_text": "taken", "card_id": "already"},
        ]
    }
    path = tmp_path / "skeleton.json"
    path.write_text(json.dumps(skeleton), encoding="utf-8")
    ids = {s["slot_id"] for s in _load_slot_texts(path)}
    assert ids == {"1", "2"}  # both unfilled (incl. cycle member); "3" is taken


# ---------------------------------------------------------------------------
# Land-cycle generation (Phase C)
# ---------------------------------------------------------------------------


def test_generate_land_cycles_writes_members(tmp_path: Path, monkeypatch):
    skeleton = {
        "cycles": [
            {
                "id": "gates",
                "name": "Guildgates",
                "span": "pairs10",
                "rarity": "common",
                "card_type": "land",
                "template": "Enters tapped; taps for the pair.",
            }
        ],
        "slots": [
            {
                "slot_id": "045",
                "color": "multicolor",
                "color_pair": "WU",
                "card_type": "land",
                "rarity": "common",
                "cmc_target": 0,
                "cycle_id": "gates",
            },
            {
                "slot_id": "046",
                "color": "multicolor",
                "color_pair": "UB",
                "card_type": "land",
                "rarity": "common",
                "cmc_target": 0,
                "cycle_id": "gates",
            },
        ],
    }

    def fake_tool(**kwargs):
        return {
            "result": {
                "lands": [
                    {
                        "name": "Azorius Gate",
                        "type_line": "Land",
                        "oracle_text": "Enters tapped.",
                        "flavor_text": "A.",
                    },
                    {
                        "name": "Dimir Gate",
                        "type_line": "Land",
                        "oracle_text": "Enters tapped.",
                        "flavor_text": "B.",
                    },
                ]
            },
            "input_tokens": 5,
            "output_tokens": 5,
        }

    monkeypatch.setattr(land_gen, "generate_with_tool", fake_tool)
    monkeypatch.setattr(land_gen, "cost_from_result", lambda _r: 0.002)

    summary = land_gen.generate_land_cycles(
        skeleton, {"name": "Test", "flavor_description": "A city."}, "model", "TST", tmp_path
    )
    assert summary["total_cards"] == 2
    files = sorted(p.name for p in tmp_path.glob("*.json"))
    assert any("azorius_gate" in f for f in files)
    azorius = json.loads(
        (tmp_path / next(p for p in files if "azorius" in p)).read_text(encoding="utf-8")
    )
    assert azorius["card_types"] == ["Land"]
    assert azorius["collector_number"] == "045"
    # color_identity derived from the WU pair
    assert set(azorius["color_identity"]) == {"W", "U"}


def test_generate_land_cycles_noop_without_land_cycles(tmp_path: Path):
    skeleton = {"slots": [{"slot_id": "1", "color": "W", "card_type": "creature"}]}
    summary = land_gen.generate_land_cycles(skeleton, {}, "m", "TST", tmp_path)
    assert summary == {"total_cards": 0, "cost_usd": 0.0}
