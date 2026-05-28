"""Phase B/C integration tests for cycles (card 6a16d8ff).

Covers cycle-coherent batching in card-gen (ordinary *and* land cycles, which
card-gen owns now — not the lands stage), the CYCLE MEMBER prompt instruction,
and that the reprint stage offers every unfilled slot to placement (cycle
avoidance is prompt-driven).

After the cycle-sort redesign (plans/card-gen-free-text-redesign.md),
``group_slots_into_batches`` is driven by the LLM-confirmed family dict, not
the structural ``cycle_id`` alone — the tests below thread an explicit
``confirmed_cycles`` to document the new contract.
"""

from __future__ import annotations

import json
from pathlib import Path

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
        confirmed = {"titans": ["1", "2", "3", "4", "5"]}
        batches = group_slots_into_batches(slots, confirmed_cycles=confirmed, batch_size=10)
        cycle_batch = next(b for b in batches if b[0].get("cycle_id") == "titans")
        assert len(cycle_batch) == 5
        assert {s["color"] for s in cycle_batch} == {"W", "U", "B", "R", "G"}
        # The two ordinary slots are not in the cycle batch.
        assert all(
            not s.get("cycle_id") for b in batches if b[0].get("cycle_id") != "titans" for s in b
        )

    def test_large_cycle_split_by_batch_size(self):
        slots = [_slot(str(i), "multicolor", color_pair="WU", cycle_id="gates") for i in range(10)]
        confirmed = {"gates": [s["slot_id"] for s in slots]}
        batches = group_slots_into_batches(slots, confirmed_cycles=confirmed, batch_size=4)
        cycle_batches = [b for b in batches if b[0].get("cycle_id") == "gates"]
        assert [len(b) for b in cycle_batches] == [4, 4, 2]

    def test_land_cycle_members_batched_together(self):
        # Land cycles are owned by card-gen now: land slots carrying a cycle_id
        # batch as their own cycle just like any other family, so a guildgate
        # cycle is designed together with its shared template.
        slots = [
            _slot("g1", "multicolor", color_pair="WU", cycle_id="gates", card_type="land"),
            _slot("g2", "multicolor", color_pair="UB", cycle_id="gates", card_type="land"),
            _slot("c1", "W", card_type="creature"),
        ]
        confirmed = {"gates": ["g1", "g2"]}
        batches = group_slots_into_batches(slots, confirmed_cycles=confirmed, batch_size=10)
        gate_batch = next(b for b in batches if b[0].get("cycle_id") == "gates")
        assert len(gate_batch) == 2
        assert all(s["card_type"] == "land" for s in gate_batch)


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
