"""Unit tests for the Finalization tab's per-card edit helper.

The ``/api/wizard/finalize/save-card`` and ``/save`` endpoints both apply edits
through the pure :func:`_apply_finalize_card_edits`, which is where the
allowed-field gating and Pydantic re-validation live — so testing it covers the
risky logic without standing up an active project / asset dir.
"""

from __future__ import annotations

import pytest

from mtgai.pipeline.server import _apply_finalize_card_edits


def _card_json(**overrides) -> dict:
    base = {
        "name": "Old Name",
        "mana_cost": "{1}{G}",
        "cmc": 2.0,
        "colors": ["G"],
        "type_line": "Creature — Beast",
        "oracle_text": "Trample",
        "flavor_text": None,
        "power": "2",
        "toughness": "2",
        "loyalty": None,
        "rarity": "common",
        "collector_number": "001",
        "set_code": "TST",
        "card_types": ["Creature"],
        "subtypes": ["Beast"],
    }
    base.update(overrides)
    return base


def test_applies_editable_fields():
    out = _apply_finalize_card_edits(
        _card_json(),
        {"name": "New Name", "oracle_text": "Flying\n{T}: Draw a card."},
    )
    assert out["name"] == "New Name"
    assert out["oracle_text"] == "Flying\n{T}: Draw a card."
    # Untouched fields survive.
    assert out["type_line"] == "Creature — Beast"
    assert out["collector_number"] == "001"


def test_empty_optional_text_becomes_none():
    out = _apply_finalize_card_edits(
        _card_json(power="3", toughness="3", flavor_text="x"),
        {"flavor_text": "", "power": "", "toughness": ""},
    )
    assert out["flavor_text"] is None
    assert out["power"] is None
    assert out["toughness"] is None


def test_rejects_non_editable_field():
    with pytest.raises(ValueError, match="Not editable"):
        _apply_finalize_card_edits(_card_json(), {"set_code": "HAX", "id": "evil"})


def test_validates_through_card_model():
    # ``colors`` is not an editable field, so an attempt to smuggle a bad value
    # is rejected as non-editable; a legal edit round-trips cleanly.
    out = _apply_finalize_card_edits(_card_json(), {"mana_cost": "{2}{U}{U}"})
    assert out["mana_cost"] == "{2}{U}{U}"
