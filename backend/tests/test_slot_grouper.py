"""Unit tests for the card-gen cycle-sort LLM pass.

Drives ``slot_grouper.find_cycle_families`` with a monkeypatched
``generate_with_tool`` — no real model is ever loaded. Pins the contracts the
simplified design relies on: the LLM identifies cycles from the full slot
listing without any extra context, singleton "cycles" are dropped,
hallucinated slot_ids are rejected, and total LLM failure falls back to the
structural seed grouping so card-gen never breaks because of this pass.
"""

from __future__ import annotations

from typing import Any

import pytest

from mtgai.generation import slot_grouper as sg

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _slot(
    slot_id: str, *, cycle_id: str | None = None, tweaked: str | None = None, **extra
) -> dict:
    """Build a slot dict like the on-disk skeleton.json shape."""
    return {
        "slot_id": slot_id,
        "color": "W",
        "rarity": "common",
        "card_type": "creature",
        "cmc_target": 2,
        "mechanic_tag": "evergreen",
        "cycle_id": cycle_id,
        "cycle_name": None,
        "cycle_member": None,
        "tweaked_text": tweaked,
        **extra,
    }


def _stub_response(cycles: list[dict]) -> dict[str, Any]:
    return {
        "result": {"cycles": cycles},
        "input_tokens": 11,
        "output_tokens": 22,
    }


def _stub(cycles: list[dict]):
    def fn(*args, **kwargs):
        return _stub_response(cycles)

    return fn


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


def test_format_slot_listing_renders_every_slot() -> None:
    """Every input slot — cycle-seeded or not — appears in the listing as
    ``slot_id: <descriptor>``. The model gets the whole skeleton to look at."""
    slots = [
        _slot("001", cycle_id="gates", tweaked="WU gate, taps for {W}{U}"),
        _slot("002", cycle_id="gates", tweaked="WB gate, taps for {W}{B}"),
        _slot("003", cycle_id=None, tweaked="Solo White uncommon Spirit"),
    ]
    out = sg._format_slot_listing(slots)
    assert "001: WU gate, taps for {W}{U}" in out
    assert "002: WB gate, taps for {W}{B}" in out
    assert "003: Solo White uncommon Spirit" in out


def test_user_prompt_renders_count_and_listing() -> None:
    """The user prompt body contains only the slot count + listing — no
    set context (theme/mechanics/archetypes) is threaded in any more."""
    slots = [
        _slot("001", tweaked="WU gate"),
        _slot("002", tweaked="WB gate"),
    ]
    out = sg._build_user_prompt(slots)
    assert "2 slots" in out
    assert "001: WU gate" in out
    assert "002: WB gate" in out


# ---------------------------------------------------------------------------
# find_cycle_families — happy paths
# ---------------------------------------------------------------------------


def test_identifies_a_cycle(monkeypatch) -> None:
    """The model returns a cycle's slot_ids; we key it by the shared seed
    cycle_id so the existing cycle_template threading still flows."""
    slots = [
        _slot("001", cycle_id="gates", tweaked="WU gate"),
        _slot("002", cycle_id="gates", tweaked="WB gate"),
        _slot("003", cycle_id="gates", tweaked="UB gate"),
    ]
    monkeypatch.setattr(
        sg,
        "generate_with_tool",
        _stub([{"slot_ids": ["001", "002", "003"]}]),
    )
    result = sg.find_cycle_families(slots=slots, model="m")
    assert result == {"gates": ["001", "002", "003"]}


def test_emergent_cycle_with_no_shared_seed_gets_synthetic_key(monkeypatch) -> None:
    """If the LLM identifies a cycle whose members don't all share a seed
    cycle_id (e.g. an emergent cycle the skeleton generator didn't seed), the
    cycle gets a synthetic key so it still batches together."""
    slots = [
        _slot("001", cycle_id=None, tweaked="White titan that doubles +1/+1 counters"),
        _slot("002", cycle_id=None, tweaked="Blue titan that bounces and draws"),
        _slot("003", cycle_id=None, tweaked="Black titan that drains and discards"),
    ]
    monkeypatch.setattr(
        sg,
        "generate_with_tool",
        _stub([{"slot_ids": ["001", "002", "003"]}]),
    )
    result = sg.find_cycle_families(slots=slots, model="m")
    assert list(result.values()) == [["001", "002", "003"]]
    assert next(iter(result.keys())).startswith("cycle_")


def test_no_cycles_returned_is_a_valid_answer(monkeypatch) -> None:
    """An empty cycles array means the model saw the skeleton and decided
    there were no cycles — that's a legitimate result, not an error."""
    slots = [
        _slot("001", tweaked="White uncommon Spirit with flying"),
        _slot("002", tweaked="Red rare burn spell"),
    ]
    monkeypatch.setattr(sg, "generate_with_tool", _stub([]))
    result = sg.find_cycle_families(slots=slots, model="m")
    assert result == {}


def test_multiple_cycles_in_one_response(monkeypatch) -> None:
    """The LLM can identify multiple distinct cycles in one shot."""
    slots = [
        _slot("001", cycle_id="gates", tweaked="WU gate"),
        _slot("002", cycle_id="gates", tweaked="WB gate"),
        _slot("003", cycle_id="signs", tweaked="W signpost"),
        _slot("004", cycle_id="signs", tweaked="U signpost"),
    ]
    monkeypatch.setattr(
        sg,
        "generate_with_tool",
        _stub(
            [
                {"slot_ids": ["001", "002"]},
                {"slot_ids": ["003", "004"]},
            ]
        ),
    )
    result = sg.find_cycle_families(slots=slots, model="m")
    assert result == {"gates": ["001", "002"], "signs": ["003", "004"]}


# ---------------------------------------------------------------------------
# find_cycle_families — defensive validation
# ---------------------------------------------------------------------------


def test_drops_singleton_cycle(monkeypatch) -> None:
    """A cycle with only one member is just a card — drop it from the result."""
    slots = [
        _slot("001", cycle_id="gates", tweaked="WU gate"),
        _slot("002", cycle_id="gates", tweaked="A creature that no longer fits"),
    ]
    monkeypatch.setattr(
        sg,
        "generate_with_tool",
        _stub([{"slot_ids": ["001"]}]),
    )
    result = sg.find_cycle_families(slots=slots, model="m")
    assert result == {}


def test_rejects_hallucinated_slot_ids(monkeypatch) -> None:
    """A slot_id not present in the input listing is silently dropped."""
    slots = [
        _slot("001", cycle_id="gates", tweaked="WU gate"),
        _slot("002", cycle_id="gates", tweaked="WB gate"),
    ]
    monkeypatch.setattr(
        sg,
        "generate_with_tool",
        _stub([{"slot_ids": ["001", "002", "999"]}]),
    )
    result = sg.find_cycle_families(slots=slots, model="m")
    assert result == {"gates": ["001", "002"]}


def test_slot_id_in_multiple_cycles_is_kept_in_first(monkeypatch) -> None:
    """If the model returns the same slot_id under two cycles, the first
    wins and later occurrences are silently dropped."""
    slots = [
        _slot("001", cycle_id="gates", tweaked="WU gate"),
        _slot("002", cycle_id="gates", tweaked="WB gate"),
        _slot("003", cycle_id="signs", tweaked="W signpost"),
    ]
    monkeypatch.setattr(
        sg,
        "generate_with_tool",
        _stub(
            [
                {"slot_ids": ["001", "002"]},
                # Second cycle reuses 002 alongside 003 — 002 was already placed.
                {"slot_ids": ["002", "003"]},
            ]
        ),
    )
    result = sg.find_cycle_families(slots=slots, model="m")
    # First cycle is kept whole. Second has only 003 left after the dedupe,
    # which fails the >=2 check, so it's dropped.
    assert result == {"gates": ["001", "002"]}


# ---------------------------------------------------------------------------
# find_cycle_families — failure modes
# ---------------------------------------------------------------------------


def test_falls_back_to_structural_grouping_on_total_failure(monkeypatch) -> None:
    """When every attempt raises, fall back to grouping by seed cycle_id —
    card-gen never breaks because the audit failed."""

    def boom(*args, **kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(sg, "generate_with_tool", boom)
    slots = [
        _slot("001", cycle_id="gates", tweaked="WU gate"),
        _slot("002", cycle_id="gates", tweaked="WB gate"),
        _slot("003", cycle_id=None, tweaked="Solo card"),
    ]
    result = sg.find_cycle_families(slots=slots, model="m")
    assert result == {"gates": ["001", "002"]}  # 003 has no seed → excluded


def test_fallback_drops_singleton_seeds(monkeypatch) -> None:
    """Fallback grouping drops a structural seed with only one surviving slot."""

    def boom(*args, **kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(sg, "generate_with_tool", boom)
    slots = [
        _slot("001", cycle_id="gates", tweaked="WU gate"),
        _slot("002", cycle_id="solo", tweaked="The only solo-seeded card"),
    ]
    result = sg.find_cycle_families(slots=slots, model="m")
    assert result == {}


def test_empty_slots_short_circuits(monkeypatch) -> None:
    """No slots → no LLM call, empty result."""

    called: list[Any] = []

    def boom(*args, **kwargs):
        called.append(1)
        raise AssertionError("should not be called")

    monkeypatch.setattr(sg, "generate_with_tool", boom)
    assert sg.find_cycle_families(slots=[], model="m") == {}
    assert called == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
