"""Pins the ``card_tile_dict`` shape — single source of truth for the
Card-Generation tab's tile shape, consumed by both ``/api/wizard/card_gen/state``
and the per-card SSE stream (``card_gen_card`` events). Drift between the two
would surface as layout flicker when the tab repaints from /state after a run.
"""

from __future__ import annotations

from mtgai.models.card import Card
from mtgai.models.enums import CardStatus, Color, Rarity
from mtgai.pipeline.stages import card_tile_dict


def _full_card() -> Card:
    return Card(
        name="Bumblebee, Autobot Scout",
        mana_cost="{1}{W}{U}",
        cmc=3.0,
        type_line="Legendary Creature — Transformer Scout",
        oracle_text="Flying.\nWhen Bumblebee enters, scry 1.",
        flavor_text='"Do not underestimate me."',
        rarity=Rarity.MYTHIC,
        colors=[Color.WHITE, Color.BLUE],
        color_identity=[Color.WHITE, Color.BLUE],
        collector_number="042",
        set_code="TF",
        power="2",
        toughness="2",
        supertypes=["Legendary"],
        card_types=["Creature"],
        subtypes=["Transformer", "Scout"],
        status=CardStatus.DRAFT,
    )


def test_card_tile_dict_from_card_model() -> None:
    tile = card_tile_dict(_full_card())
    assert tile == {
        "name": "Bumblebee, Autobot Scout",
        "mana_cost": "{1}{W}{U}",
        "type_line": "Legendary Creature — Transformer Scout",
        "oracle_text": "Flying.\nWhen Bumblebee enters, scry 1.",
        "flavor_text": '"Do not underestimate me."',
        "rarity": "mythic",
        "power": "2",
        "toughness": "2",
        "loyalty": None,
        "colors": ["W", "U"],
        "collector_number": "042",
        "status": "draft",
        # No slots_by_id passed → slot_text is empty (the client renders nothing).
        "slot_text": "",
    }


def test_card_tile_dict_from_disk_dict() -> None:
    """The /state endpoint reads cards as raw dicts from disk; same helper must
    handle that path identically so /state and the SSE stream emit identical
    payloads."""
    disk_dict = {
        "name": "Lightning Bolt",
        "mana_cost": "{R}",
        "type_line": "Instant",
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        "rarity": "common",
        "colors": ["R"],
        "collector_number": "141",
        "status": "draft",
        # Many real cards omit power/toughness/loyalty — must come back as None.
    }
    tile = card_tile_dict(disk_dict)
    assert tile["name"] == "Lightning Bolt"
    assert tile["mana_cost"] == "{R}"
    assert tile["colors"] == ["R"]
    assert tile["power"] is None
    assert tile["toughness"] is None
    assert tile["loyalty"] is None
    assert tile["flavor_text"] == ""  # missing fields default to empty strings


def test_card_tile_dict_missing_fields_get_safe_defaults() -> None:
    """A near-empty dict must still produce a usable tile — the client falls
    back to ``'common'`` rarity and empty arrays for ``colors``, so the helper
    matches those defaults."""
    tile = card_tile_dict({})
    assert tile["name"] == ""
    assert tile["rarity"] == "common"
    assert tile["colors"] == []
    assert tile["status"] == ""


def test_card_tile_dict_rejects_unsupported_type() -> None:
    """A guardrail — passing the wrong type should fail loudly, not silently
    swallow into an empty tile (which would mask real wiring bugs)."""
    import pytest

    with pytest.raises(TypeError):
        card_tile_dict("not a card")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# slot_text — the skeleton slot's final relabeled descriptor shown under the
# card on the Card Generation tab.
# ---------------------------------------------------------------------------


def test_slot_text_from_tweaked_text() -> None:
    """When the slot has tweaked_text (the relabel ran), that wins — same
    resolver format_slot_specs uses."""
    card = _full_card().model_copy(update={"collector_number": "017"})
    slots_by_id = {
        "017": {
            "slot_id": "017",
            "color": "W",
            "rarity": "common",
            "card_type": "artifact",
            "cmc_target": 3,
            "mechanic_tag": "evergreen",
            "tweaked_text": (
                "White · common · artifact · CMC3 · Energize · cycle:Energon Generators (W)"
            ),
        }
    }
    tile = card_tile_dict(card, slots_by_id)
    assert tile["slot_text"] == (
        "White · common · artifact · CMC3 · Energize · cycle:Energon Generators (W)"
    )


def test_slot_text_falls_back_to_render_slot_string() -> None:
    """No tweaked_text → render_slot_string on the deterministic seeds."""
    card = _full_card().model_copy(update={"collector_number": "042"})
    slots_by_id = {
        "042": {
            "slot_id": "042",
            "color": "W",
            "rarity": "common",
            "card_type": "creature",
            "cmc_target": 2,
            "mechanic_tag": "vanilla",
            # No tweaked_text → fall through to render_slot_string.
        }
    }
    tile = card_tile_dict(card, slots_by_id)
    # render_slot_string format: "White · common · creature · CMC2 · vanilla"
    assert "White" in tile["slot_text"]
    assert "common" in tile["slot_text"]
    assert "creature" in tile["slot_text"]
    assert "CMC2" in tile["slot_text"]
    assert "vanilla" in tile["slot_text"]


def test_slot_text_empty_when_no_skeleton_map() -> None:
    """No slots_by_id (or unmatched collector_number) → empty string. The
    client falls back gracefully; nothing rendered under the tile."""
    card = _full_card()
    assert card_tile_dict(card)["slot_text"] == ""
    assert card_tile_dict(card, {})["slot_text"] == ""
    # collector_number "042" not in the map → empty.
    tile = card_tile_dict(
        card.model_copy(update={"collector_number": "042"}),
        {"017": {"slot_id": "017"}},
    )
    assert tile["slot_text"] == ""
