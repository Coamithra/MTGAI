"""The Card Generation tab's old/new distinction: a regen instance highlights
the cards it (re)generated vs those carried over from the prior instance.

Covers the two pure pieces of the ``/api/wizard/card_gen/state`` logic:
``_load_card_gen_cards`` (read a pool's card-gen cards, lands excluded, keyed by
collector number) and ``_diff_regenerated`` (classify carried-over vs regenerated
by diffing against the entry snapshot).
"""

from __future__ import annotations

import json
from pathlib import Path

from mtgai.pipeline.server import _diff_regenerated, _load_card_gen_cards


def _card(cn: str, name: str, **extra: object) -> dict:
    return {"collector_number": cn, "name": name, **extra}


# ---------------------------------------------------------------------------
# _diff_regenerated
# ---------------------------------------------------------------------------


def test_diff_no_entry_cards_is_not_a_regen_instance() -> None:
    """The first card_gen's entry is the lands snapshot (no card-gen cards) — so
    'everything is new' is not a useful distinction and nothing is highlighted."""
    view = {"001": _card("001", "A"), "002": _card("002", "B")}
    is_regen, regenerated = _diff_regenerated(view, {})
    assert is_regen is False
    assert regenerated == set()


def test_diff_flags_changed_and_added_cards() -> None:
    """On a regen instance a card is 'new' iff it differs from / is absent in the
    entry pool. Carried-over cards are byte-identical copies, so they're equal."""
    entry = {
        "001": _card("001", "Carried Over"),
        "002": _card("002", "Old Name", regen_reason="too strong"),
    }
    view = {
        "001": _card("001", "Carried Over"),  # unchanged -> carried over
        "002": _card("002", "Fresh Name"),  # regenerated (content + flag cleared)
        "003": _card("003", "Brand New"),  # absent in entry -> new
    }
    is_regen, regenerated = _diff_regenerated(view, entry)
    assert is_regen is True
    assert regenerated == {"002", "003"}


def test_diff_all_carried_over_yields_empty_set() -> None:
    entry = {"001": _card("001", "A"), "002": _card("002", "B")}
    view = {"001": _card("001", "A"), "002": _card("002", "B")}
    is_regen, regenerated = _diff_regenerated(view, entry)
    assert is_regen is True
    assert regenerated == set()


# ---------------------------------------------------------------------------
# _load_card_gen_cards
# ---------------------------------------------------------------------------


def _write(cards_dir: Path, cn: str, **fields: object) -> None:
    (cards_dir / f"{cn}.json").write_text(
        json.dumps({"collector_number": cn, **fields}), encoding="utf-8"
    )


def test_load_card_gen_cards_excludes_lands_and_keys_by_collector_number(tmp_path: Path) -> None:
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    _write(cards_dir, "001", name="Goblin")
    _write(cards_dir, "L-01a", name="Plains")  # lands-stage card -> excluded
    out = _load_card_gen_cards(cards_dir)
    assert set(out) == {"001"}
    assert out["001"]["name"] == "Goblin"


def test_load_card_gen_cards_missing_dir_is_empty(tmp_path: Path) -> None:
    assert _load_card_gen_cards(tmp_path / "nope") == {}
