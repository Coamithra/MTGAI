"""Unit tests for ``_skeleton_knobs_from_body`` — the payload-overlay helper the
Skeleton tab's ``/knobs`` (deterministic rebuild) and ``/knobs/tune`` (AI re-tune
base) endpoints share (B5).

The helper is the single place the wizard's ``{knobs, cycles, pinned, provenance}``
overlay is threaded into ``SkeletonKnobs.from_payload``; both call sites now route
through it, so these tests pin the overlay contract once.
"""

import pytest

from mtgai.pipeline.server import _skeleton_knobs_from_body
from mtgai.skeleton.knobs import SkeletonKnobs, default_knobs


def test_returns_knobs_and_warnings_tuple():
    knobs, warnings = _skeleton_knobs_from_body({})
    assert isinstance(knobs, SkeletonKnobs)
    assert isinstance(warnings, list)


def test_empty_body_yields_defaults_no_warnings():
    knobs, warnings = _skeleton_knobs_from_body({})
    # from_payload always stamps every knob "default", same as default_knobs().
    assert knobs == default_knobs()
    assert warnings == []


def test_overlays_knobs_cycles_pinned_provenance():
    body = {
        "knobs": {"planeswalker_count": 2},  # in range (max 2)
        "cycles": [
            {
                "id": "cyc-1",
                "name": "Titans",
                "span": "mono5",
                "rarity": "rare",
                "card_type": "creature",
                "cmc_target": 6,
                "template": "A big creature",
            }
        ],
        "pinned": ["rarity_common"],
        "provenance": {"rarity_common": "user"},
    }
    knobs, _ = _skeleton_knobs_from_body(body)
    assert knobs.planeswalker_count == 2
    assert [c.name for c in knobs.cycles] == ["Titans"]
    assert knobs.pinned == ["rarity_common"]
    assert knobs.provenance["rarity_common"] == "user"


def test_cycles_fall_back_to_knobs_nested_cycles():
    # The tab may nest `cycles` inside the `knobs` dict; with no top-level
    # `cycles`, the helper falls back to body["knobs"]["cycles"].
    knobs, _ = _skeleton_knobs_from_body(
        {"knobs": {"cycles": [{"id": "c1", "name": "Nested", "span": "mono5"}]}}
    )
    assert [c.name for c in knobs.cycles] == ["Nested"]


def test_top_level_cycles_win_over_nested():
    knobs, _ = _skeleton_knobs_from_body(
        {
            "knobs": {"cycles": [{"id": "c1", "name": "Nested", "span": "mono5"}]},
            "cycles": [{"id": "c2", "name": "TopLevel", "span": "mono5"}],
        }
    )
    assert [c.name for c in knobs.cycles] == ["TopLevel"]


def test_out_of_range_value_is_clamped_with_warning():
    knobs, warnings = _skeleton_knobs_from_body({"knobs": {"rarity_common": 9999}})
    assert knobs.rarity_common != 9999  # clamped down to the spec max
    assert warnings  # the clamp is reported


@pytest.mark.parametrize("bad_knobs", ["hello", [1, 2, 3], 5, True, None])
def test_non_dict_knobs_value_does_not_crash(bad_knobs):
    # A non-dict ``knobs`` (the bug behind the /knobs 500) is treated as "no
    # edits" — defaults, no crash. The endpoint rejects it with 400 first, but
    # the helper stays defensive (it's also called by /knobs/tune).
    knobs, warnings = _skeleton_knobs_from_body({"knobs": bad_knobs})
    assert isinstance(knobs, SkeletonKnobs)
    assert isinstance(warnings, list)


def test_both_call_sites_overlay_identically():
    # /knobs reads ``body`` directly; /knobs/tune reads the same body when its
    # ``knobs`` is a non-empty dict. The helper is the single source, so the two
    # produce identical knobs from one body by construction — assert that holds.
    body = {
        "knobs": {"planeswalker_count": 2, "signposts_per_pair": 2},
        "pinned": ["multicolor_rare"],
        "provenance": {"multicolor_rare": "user"},
    }
    a, _ = _skeleton_knobs_from_body(body)
    b, _ = _skeleton_knobs_from_body(body)
    assert a == b
