"""Tests for the merged ``rendering`` stage's final-review logic.

Covers the two non-trivial behaviors that live in ``mtgai/review/render_review.py``:
the contiguous collector-number renumber after a card removal (the riskiest part —
gaps, last-card removal, cross-group isolation, zero-padding, the re-render set)
and the lightweight per-card finalize pass run on a manual edit.
"""

from __future__ import annotations

from mtgai.models.card import Card
from mtgai.models.enums import Color, Rarity
from mtgai.review.render_review import (
    finalize_one_card,
    format_collector_number,
    parse_collector_number,
    plan_renumber,
)

MECHANICS = [
    {
        "name": "Salvage",
        "reminder_text": (
            "(Look at the top X cards of your library. You may put an "
            "artifact card from among them into your hand. Put the rest "
            "on the bottom of your library in any order.)"
        ),
    },
]


def _make_card(**overrides) -> Card:
    defaults = {
        "name": "Test Creature",
        "mana_cost": "{2}{G}",
        "cmc": 3.0,
        "type_line": "Creature — Beast",
        "oracle_text": "Trample",
        "power": "3",
        "toughness": "3",
        "rarity": Rarity.COMMON,
        "colors": [Color.GREEN],
        "color_identity": [Color.GREEN],
        "collector_number": "G-C-01",
        "set_code": "TST",
        "card_types": ["Creature"],
        "subtypes": ["Beast"],
    }
    defaults.update(overrides)
    return Card(**defaults)


# ---------------------------------------------------------------------------
# parse / format collector numbers
# ---------------------------------------------------------------------------


class TestParseCollectorNumber:
    def test_color_rarity_index(self):
        assert parse_collector_number("B-C-02") == ("B-C", 2, 2)

    def test_single_prefix(self):
        assert parse_collector_number("L-03") == ("L", 3, 2)

    def test_single_digit_index(self):
        assert parse_collector_number("L-3") == ("L", 3, 1)

    def test_multiletter_prefix(self):
        assert parse_collector_number("BLOG-01") == ("BLOG", 1, 2)

    def test_three_color_prefix(self):
        assert parse_collector_number("WUB-U-01") == ("WUB-U", 1, 2)

    def test_bare_numeric_is_prefixless_group(self):
        # The form every ordinary card carries: a plain zero-padded slot id.
        assert parse_collector_number("002") == ("", 2, 3)
        assert parse_collector_number("001") == ("", 1, 3)

    def test_bare_numeric_wide_padding(self):
        # A 4-digit set (id_width 4) stamps "0042".
        assert parse_collector_number("0042") == ("", 42, 4)

    def test_bare_numeric_single_digit(self):
        assert parse_collector_number("7") == ("", 7, 1)

    def test_no_index_suffix_is_none(self):
        assert parse_collector_number("PROMO") is None
        assert parse_collector_number("") is None
        assert parse_collector_number("L-") is None  # dash but no trailing digits

    def test_round_trip(self):
        for cn in ("B-C-02", "L-3", "BLOG-01", "WG-R-05", "002", "0042", "7"):
            prefix, index, pad = parse_collector_number(cn)
            assert format_collector_number(prefix, index, pad) == cn


# ---------------------------------------------------------------------------
# plan_renumber — the contiguous-renumber remap
# ---------------------------------------------------------------------------


class TestPlanRenumber:
    def test_middle_removal_shifts_trailing(self):
        # Remove B-C-02 → 03→02, 04→03; 01 untouched.
        remaining = ["B-C-01", "B-C-03", "B-C-04"]
        remap = plan_renumber(remaining, "B-C-02")
        assert remap == {"B-C-03": "B-C-02", "B-C-04": "B-C-03"}

    def test_last_card_removal_no_shift(self):
        # Remove the highest-indexed card → nothing shifts (already contiguous).
        remaining = ["B-C-01", "B-C-02", "B-C-03"]
        remap = plan_renumber(remaining, "B-C-04")
        assert remap == {}

    def test_first_card_removal_shifts_all(self):
        remaining = ["B-C-02", "B-C-03", "B-C-04"]
        remap = plan_renumber(remaining, "B-C-01")
        assert remap == {
            "B-C-02": "B-C-01",
            "B-C-03": "B-C-02",
            "B-C-04": "B-C-03",
        }

    def test_only_removed_group_renumbers(self):
        # Other groups (different prefix) are left completely alone.
        remaining = ["B-C-01", "B-C-03", "G-C-01", "G-C-02", "W-R-05"]
        remap = plan_renumber(remaining, "B-C-02")
        assert remap == {"B-C-03": "B-C-02"}
        assert "G-C-01" not in remap
        assert "G-C-02" not in remap
        assert "W-R-05" not in remap

    def test_rarity_is_part_of_the_group(self):
        # B-C-* and B-U-* are distinct groups; removing a common doesn't touch
        # uncommons even though both start with "B".
        remaining = ["B-C-01", "B-C-03", "B-U-01", "B-U-02"]
        remap = plan_renumber(remaining, "B-C-02")
        assert remap == {"B-C-03": "B-C-02"}

    def test_preexisting_gap_also_closes(self):
        # Defensive: the whole group renumbers densely from 1, so any pre-existing
        # gap (e.g. 02 already missing) closes alongside the removal.
        remaining = ["B-C-01", "B-C-04", "B-C-05"]  # 02 and the removed 03 gone
        remap = plan_renumber(remaining, "B-C-03")
        assert remap == {"B-C-04": "B-C-02", "B-C-05": "B-C-03"}

    def test_zero_padding_preserved(self):
        # Dense-renumber-from-1 (the "no gaps" contract): with L-09 removed the
        # whole L group renumbers 08→07? No — there's a pre-existing gap (01..07
        # absent here), so this group of three becomes L-01/L-02/L-03, padding kept.
        remaining = ["L-08", "L-10", "L-11"]
        remap = plan_renumber(remaining, "L-09")
        assert remap == {"L-08": "L-01", "L-10": "L-02", "L-11": "L-03"}

    def test_contiguous_group_only_trailing_shifts(self):
        # The realistic case (no pre-existing gaps): removing L-09 from a contiguous
        # run shifts only L-10+ down; L-01..L-08 keep their numbers + padding.
        remaining = [f"L-{i:02d}" for i in range(1, 12) if i != 9]  # 01..11 minus 09
        remap = plan_renumber(remaining, "L-09")
        assert remap == {"L-10": "L-09", "L-11": "L-10"}

    def test_single_card_group_removal_empty_remap(self):
        remaining = ["B-C-01", "G-C-01"]
        remap = plan_renumber(remaining, "B-M-01")  # only member of its group
        assert remap == {}

    def test_unparseable_removed_cn_empty_remap(self):
        remaining = ["B-C-01", "B-C-02"]
        assert plan_renumber(remaining, "PROMO") == {}

    def test_remap_keys_are_the_rerender_set(self):
        # The endpoint re-renders exactly remap.keys(); a card that keeps its
        # number must NOT appear (so it isn't needlessly re-rendered).
        remaining = ["B-C-01", "B-C-02", "B-C-04"]
        remap = plan_renumber(remaining, "B-C-03")
        assert set(remap) == {"B-C-04"}  # only the trailing card shifts
        assert "B-C-01" not in remap
        assert "B-C-02" not in remap

    def test_bare_numeric_middle_removal_shifts_trailing(self):
        # The real bug: ordinary cards use plain "001"/"002"/… and must renumber
        # densely (003→002 after removing 002), not leave a permanent gap.
        remaining = ["001", "003", "004"]
        remap = plan_renumber(remaining, "002")
        assert remap == {"003": "002", "004": "003"}

    def test_bare_numeric_first_removal_shifts_all(self):
        remaining = ["002", "003", "004"]
        remap = plan_renumber(remaining, "001")
        assert remap == {"002": "001", "003": "002", "004": "003"}

    def test_bare_numeric_last_removal_no_shift(self):
        remaining = ["001", "002", "003"]
        remap = plan_renumber(remaining, "004")
        assert remap == {}

    def test_bare_numeric_does_not_touch_dashed_groups(self):
        # Plain-numeric (prefix "") and dashed land/special ids are distinct groups:
        # removing an ordinary card never renumbers the L-* lands and vice versa.
        remaining = ["001", "003", "L-01", "L-02"]
        remap = plan_renumber(remaining, "002")
        assert remap == {"003": "002"}
        assert "L-01" not in remap
        assert "L-02" not in remap

    def test_dashed_removal_does_not_touch_bare_numeric_group(self):
        remaining = ["001", "002", "L-01", "L-03"]
        remap = plan_renumber(remaining, "L-02")
        assert remap == {"L-03": "L-02"}
        assert "001" not in remap
        assert "002" not in remap

    def test_bare_numeric_padding_preserved_on_rollover(self):
        # 3-wide padding stays 3-wide through a double-digit shift.
        remaining = ["001", "002", "004", "005", "006", "007", "008", "009", "010"]
        remap = plan_renumber(remaining, "003")
        assert remap["004"] == "003"
        assert remap["010"] == "009"

    def test_double_digit_rollover(self):
        remaining = [
            "B-C-01",
            "B-C-02",
            "B-C-04",
            "B-C-05",
            "B-C-06",
            "B-C-07",
            "B-C-08",
            "B-C-09",
            "B-C-10",
        ]
        remap = plan_renumber(remaining, "B-C-03")
        # 04..10 each shift down one; the rollover 10→09 stays 2-wide.
        assert remap["B-C-10"] == "B-C-09"
        assert remap["B-C-04"] == "B-C-03"


# ---------------------------------------------------------------------------
# finalize_one_card — the per-card edit pass
# ---------------------------------------------------------------------------


class TestFinalizeOneCard:
    def test_reinjects_reminder_text(self):
        card = _make_card(oracle_text="When ~ enters, salvage 3.")
        finalized, _fixes, _manual = finalize_one_card(card, MECHANICS)
        assert "(Look at the top three cards" in finalized.oracle_text

    def test_auto_fix_applied(self):
        card = _make_card(oracle_text="When ~ enters the battlefield, salvage 3.")
        finalized, fixes, _manual = finalize_one_card(card, MECHANICS)
        assert "enters the battlefield" not in finalized.oracle_text
        assert any("etb" in f.lower() for f in fixes)

    def test_clean_card_unchanged(self):
        card = _make_card(oracle_text="Trample", power="2", toughness="2")
        finalized, fixes, manual = finalize_one_card(card, MECHANICS)
        assert finalized.oracle_text == "Trample"
        assert fixes == []
        assert manual == []

    def test_returns_new_instance_card_immutable(self):
        card = _make_card(oracle_text="When ~ enters, salvage 3.")
        finalized, _fixes, _manual = finalize_one_card(card, MECHANICS)
        # The original is untouched (cards are immutable; the pass returns a copy).
        assert "(Look at the top" not in card.oracle_text
        assert finalized is not card
