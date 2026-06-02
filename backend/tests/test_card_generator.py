"""Unit tests for the card-generator's pure pieces.

The full ``generate_set`` orchestrator is exercised through the wizard
endpoint tests (``test_wizard_card_gen.py``). Here we cover the pure
helpers the cycle-sort redesign introduced:

* ``group_slots_into_batches`` — drives batching off the cycle-sort result
  instead of swingable structured seeds (no colour batching, oversized
  cycles split into ordered sub-batches all tagged to the same cycle).
* ``build_user_prompt`` with ``cycle_siblings`` — later sub-batches of an
  oversized cycle see prior members' full oracle text.
"""

from __future__ import annotations

from mtgai.generation.card_generator import _card_one_liner, group_slots_into_batches
from mtgai.generation.prompts import build_user_prompt, format_cycle_siblings


def _slot(slot_id: str, *, cycle_id: str | None = None, **extra) -> dict:
    return {
        "slot_id": slot_id,
        "color": extra.pop("color", "W"),
        "rarity": "common",
        "card_type": "creature",
        "cmc_target": 2,
        "mechanic_tag": "evergreen",
        "cycle_id": cycle_id,
        "tweaked_text": extra.pop("tweaked_text", None),
        **extra,
    }


# ---------------------------------------------------------------------------
# group_slots_into_batches
# ---------------------------------------------------------------------------


def test_no_confirmed_cycles_chunks_in_slot_id_order() -> None:
    """No colour batching: pure slot_id order at batch_size."""
    slots = [
        _slot("003", color="R"),
        _slot("001", color="W"),
        _slot("002", color="U"),
        _slot("004", color="B"),
    ]
    batches = group_slots_into_batches(slots, confirmed_cycles={}, batch_size=2)
    assert [[s["slot_id"] for s in b] for b in batches] == [["001", "002"], ["003", "004"]]


def test_confirmed_cycle_becomes_own_batch_then_ordinary() -> None:
    """A confirmed family is pulled out as its own batch; remaining slots
    chunk in slot_id order."""
    slots = [
        _slot("001", cycle_id="gates"),
        _slot("002"),
        _slot("003", cycle_id="gates"),
        _slot("004"),
    ]
    batches = group_slots_into_batches(
        slots,
        confirmed_cycles={"gates": ["001", "003"]},
        batch_size=2,
    )
    # Family first (both members in one batch since batch_size=2), then ordinary.
    assert [s["slot_id"] for s in batches[0]] == ["001", "003"]
    assert [s["slot_id"] for s in batches[1]] == ["002", "004"]


def test_oversized_cycle_splits_into_ordered_subbatches_tagged_to_cycle() -> None:
    """A 10-member pairs10 cycle at batch_size=3 splits into 4 ordered sub-batches,
    all carrying the same cycle_id so the loop's sibling logic can thread prior
    members in."""
    cycle = [_slot(f"{i:03d}", cycle_id="pairs10") for i in range(1, 11)]
    confirmed = {"pairs10": [s["slot_id"] for s in cycle]}
    batches = group_slots_into_batches(cycle, confirmed_cycles=confirmed, batch_size=3)
    assert len(batches) == 4
    # Order is preserved.
    flat_ids = [s["slot_id"] for b in batches for s in b]
    assert flat_ids == [f"{i:03d}" for i in range(1, 11)]
    # Every sub-batch is tagged to the same cycle (the loop reads this to
    # decide whether to thread siblings).
    for b in batches:
        cids = {s["cycle_id"] for s in b}
        assert cids == {"pairs10"}


def test_audit_pruned_slot_lands_in_ordinary_pile_in_slot_id_order() -> None:
    """A slot whose seed cycle_id is "gates" but which the audit dropped (not
    in confirmed_cycles["gates"]) batches as ordinary, sorted by slot_id with
    the rest — its stale seed cycle_id is not used as a grouping key."""
    slots = [
        _slot("001", cycle_id="gates"),
        _slot("002", cycle_id="gates"),  # pruned by the audit
        _slot("003", cycle_id="gates"),
        _slot("009"),  # ordinary
    ]
    batches = group_slots_into_batches(
        slots,
        confirmed_cycles={"gates": ["001", "003"]},
        batch_size=10,  # one big batch for the ordinary pile
    )
    # Family batch (audit-confirmed members only):
    assert [s["slot_id"] for s in batches[0]] == ["001", "003"]
    # Ordinary batch: 002 (pruned) and 009 in slot_id order.
    assert [s["slot_id"] for s in batches[1]] == ["002", "009"]


def test_none_confirmed_cycles_skips_cycle_batching_for_dry_runs() -> None:
    """``confirmed_cycles=None`` (the dry-run / no-LLM path) batches everything
    as ordinary slots in slot_id order — no cycle batches."""
    slots = [
        _slot("001", cycle_id="gates"),
        _slot("002", cycle_id="gates"),
        _slot("003"),
    ]
    batches = group_slots_into_batches(slots, confirmed_cycles=None, batch_size=10)
    assert len(batches) == 1
    assert [s["slot_id"] for s in batches[0]] == ["001", "002", "003"]


# ---------------------------------------------------------------------------
# format_cycle_siblings + build_user_prompt threading
# ---------------------------------------------------------------------------


def _sibling_card(name: str, oracle: str, *, cost: str = "{1}{W}", pt: tuple | None = None) -> dict:
    out = {
        "name": name,
        "mana_cost": cost,
        "type_line": "Land",
        "oracle_text": oracle,
    }
    if pt is not None:
        out["power"], out["toughness"] = pt
    return out


def test_format_cycle_siblings_renders_full_oracle_text() -> None:
    out = format_cycle_siblings(
        [
            _sibling_card(
                "Azorius Gate",
                "Azorius Gate enters the battlefield tapped.\n{T}: Add {W} or {U}.",
            )
        ]
    )
    assert "SIBLING CYCLE MEMBERS" in out
    assert "mirror their structure and wording" in out
    assert "Azorius Gate" in out
    # Full oracle text is included, not truncated.
    assert "Azorius Gate enters the battlefield tapped." in out
    assert "{T}: Add {W} or {U}." in out


def test_format_cycle_siblings_empty_returns_empty_string() -> None:
    assert format_cycle_siblings(None) == ""
    assert format_cycle_siblings([]) == ""


def test_build_user_prompt_threads_cycle_siblings_when_passed() -> None:
    """The siblings block appears in build_user_prompt when a list is passed,
    and not otherwise."""
    slots = [_slot("002", cycle_id="gates", tweaked_text="WB gate")]
    siblings = [
        _sibling_card(
            "Azorius Gate",
            "Azorius Gate enters the battlefield tapped.\n{T}: Add {W} or {U}.",
        )
    ]

    with_siblings = build_user_prompt(
        slots,
        mechanics=[],
        existing_cards=[],
        theme={"name": "T", "setting": "s"},
        archetypes=None,
        cycle_siblings=siblings,
    )
    without = build_user_prompt(
        slots,
        mechanics=[],
        existing_cards=[],
        theme={"name": "T", "setting": "s"},
        archetypes=None,
    )

    assert "SIBLING CYCLE MEMBERS" in with_siblings
    assert "Azorius Gate enters the battlefield tapped." in with_siblings
    assert "SIBLING CYCLE MEMBERS" not in without


# ---------------------------------------------------------------------------
# _card_one_liner — log helper, must never raise
# ---------------------------------------------------------------------------


def test_card_one_liner_tolerates_none_oracle_text() -> None:
    """An LLM retry once returned ``oracle_text: null`` and the unguarded
    ``oracle[:60]`` crashed the whole card_gen stage with ``'NoneType' object
    is not subscriptable``. This helper is just a log line — never raise."""
    # The original crash repro: oracle_text is explicitly None.
    out = _card_one_liner({"name": "Autobot Defender", "oracle_text": None})
    assert "Autobot Defender" in out
    # An entirely empty dict shouldn't raise either (missing every field).
    assert _card_one_liner({}) is not None
    # P/T defends against half-set fields (power without toughness, etc.).
    assert "1/" not in _card_one_liner({"name": "X", "power": "1"})


def test_card_one_liner_preserves_full_card_shape() -> None:
    """Sanity check that the happy-path output didn't regress after the
    defensive coercion (None → "" for every str field)."""
    out = _card_one_liner(
        {
            "name": "Lightning Bolt",
            "mana_cost": "{R}",
            "type_line": "Instant",
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        }
    )
    assert "Lightning Bolt" in out
    assert "{R}" in out
    assert "Instant" in out
    assert "deals 3 damage" in out
