"""Tests for the algorithmic resource-economy / enablement-coverage check.

The check (``mtgai.analysis.resource_economy``) is the third no-LLM surface of the
conformance gate: for each consumable token resource (Food, Treasure, custom
mechanic tokens) it counts makers vs consumers, tallies per color + rarity, joins
keyword mechanics, and warns on critical coverage gaps. Synthetic fixtures only —
the MLP witness set is eyeballed but never depended on.
"""

from __future__ import annotations

from mtgai.analysis.resource_economy import (
    analyze_resource_economy,
    discover_resources,
    scan_card,
)
from mtgai.models.card import Card
from mtgai.models.enums import Color, Rarity


def _make_card(**overrides) -> Card:
    defaults = {
        "name": "Test Card",
        "mana_cost": "{1}{G}",
        "cmc": 2.0,
        "type_line": "Creature — Pony",
        "oracle_text": "",
        "rarity": Rarity.COMMON,
        "colors": [Color.GREEN],
        "color_identity": [Color.GREEN],
        "collector_number": "001",
        "set_code": "TST",
        "card_types": ["Creature"],
        "subtypes": ["Pony"],
    }
    defaults.update(overrides)
    return Card(**defaults)


def _mechanic(name: str, reminder: str, colors=None) -> dict:
    return {"name": name, "reminder_text": reminder, "colors": colors or []}


# ---------------------------------------------------------------------------
# Resource discovery
# ---------------------------------------------------------------------------


class TestDiscoverResources:
    def test_predefined_tokens_always_present(self):
        res = discover_resources([], [])
        assert "Food" in res
        assert "Treasure" in res
        assert "Clue" in res

    def test_custom_token_from_mechanic_reminder(self):
        # Squall's reminder text creates "Cloud tokens".
        mech = _mechanic(
            "Squall",
            "(Whenever this creature attacks, create N colorless enchantment Cloud tokens "
            "that have '{T}: Add {C}'.)",
        )
        res = discover_resources([], [mech])
        assert "Cloud" in res

    def test_custom_token_mined_from_pool(self):
        card = _make_card(oracle_text="When this enters, create a Spark token.")
        res = discover_resources([card], [])
        assert "Spark" in res

    def test_case_insensitive_dedup(self):
        # A pool "Food" and the predefined "Food" must not double-list.
        card = _make_card(oracle_text="Create a Food token.")
        res = discover_resources([card], [])
        assert res.count("Food") == 1


# ---------------------------------------------------------------------------
# Per-card maker / consumer extraction
# ---------------------------------------------------------------------------


class TestScanCard:
    def test_maker_create_a(self):
        card = _make_card(oracle_text="When this enters, create a Food token.")
        makes, uses = scan_card(card, ["Food"])
        assert makes == {"Food"}
        assert uses == set()

    def test_maker_create_two(self):
        card = _make_card(oracle_text="When this enters, create two Food tokens.")
        makes, _ = scan_card(card, ["Food"])
        assert makes == {"Food"}

    def test_maker_create_with_adjectives(self):
        card = _make_card(oracle_text="Create three tapped Treasure tokens.")
        makes, _ = scan_card(card, ["Treasure"])
        assert makes == {"Treasure"}

    def test_consumer_sacrifice_a_token(self):
        card = _make_card(oracle_text="{T}, Sacrifice a Food token: Add {G}.")
        makes, uses = scan_card(card, ["Food"])
        assert uses == {"Food"}
        assert makes == set()

    def test_consumer_sacrifice_without_token_word(self):
        card = _make_card(oracle_text="Sacrifice a Treasure: Draw a card.")
        _, uses = scan_card(card, ["Treasure"])
        assert uses == {"Treasure"}

    def test_card_that_both_makes_and_consumes(self):
        card = _make_card(
            oracle_text="When this enters, create two Food tokens.\n"
            "{T}, Sacrifice a Food token: Add {G}."
        )
        makes, uses = scan_card(card, ["Food"])
        assert makes == {"Food"}
        assert uses == {"Food"}

    def test_reminder_text_stripped(self):
        # Injected reminder text mentioning a sacrifice must not register as a
        # body consumer — the mechanic-coverage join owns that.
        card = _make_card(
            oracle_text="Provision 1 (Whenever you sacrifice a Food token, put a +1/+1 "
            "counter on target creature.)\nWhen this enters, create a Food token."
        )
        makes, uses = scan_card(card, ["Food"])
        assert makes == {"Food"}
        assert uses == set()

    def test_unrelated_text_no_match(self):
        card = _make_card(oracle_text="Flying, vigilance. Draw a card.")
        makes, uses = scan_card(card, ["Food", "Treasure"])
        assert makes == set()
        assert uses == set()

    def test_create_does_not_cross_clause_to_other_resource(self):
        # "create a Treasure token, then sacrifice a Food" must NOT count Food as a
        # maker — the create verb belongs to the Treasure clause.
        card = _make_card(oracle_text="Create a Treasure token, then sacrifice a Food.")
        makes, uses = scan_card(card, ["Food", "Treasure"])
        assert makes == {"Treasure"}
        assert uses == {"Food"}


# ---------------------------------------------------------------------------
# Whole-set analysis + warnings
# ---------------------------------------------------------------------------


class TestAnalyzeResourceEconomy:
    def test_healthy_economy_no_warnings(self):
        # 3 makers + 3 consumers, all green — balanced.
        cards = []
        for i in range(3):
            cards.append(
                _make_card(
                    name=f"Maker {i}",
                    collector_number=f"00{i + 1}",
                    oracle_text="Create a Food token.",
                )
            )
        for i in range(3):
            cards.append(
                _make_card(
                    name=f"Eater {i}",
                    collector_number=f"01{i}",
                    oracle_text="Sacrifice a Food token: Draw a card.",
                )
            )
        report, warnings = analyze_resource_economy(cards, [])
        assert warnings == []
        food = next(r for r in report["resources"] if r["name"] == "Food")
        assert food["makers"] == 3
        assert food["consumers"] == 3

    def test_zero_maker_warns(self):
        cards = [
            _make_card(
                name=f"Eater {i}",
                collector_number=f"00{i + 1}",
                oracle_text="Sacrifice a Food token: Draw a card.",
            )
            for i in range(3)
        ]
        report, warnings = analyze_resource_economy(cards, [])
        assert any("Food" in w and "consume" in w for w in warnings)
        food = next(r for r in report["resources"] if r["name"] == "Food")
        assert food["makers"] == 0
        assert food["consumers"] == 3

    def test_single_maker_three_consumers_warns(self):
        cards = [
            _make_card(name="Maker", collector_number="001", oracle_text="Create a Food token.")
        ]
        cards += [
            _make_card(
                name=f"Eater {i}",
                collector_number=f"01{i}",
                oracle_text="Sacrifice a Food token: Draw a card.",
            )
            for i in range(3)
        ]
        _, warnings = analyze_resource_economy(cards, [])
        assert any("Food" in w for w in warnings)

    def test_color_mismatch_warns(self):
        # Two black/blue consumers, the only maker is red — produced where it
        # can't be used.
        cards = [
            _make_card(
                name="Red Maker",
                collector_number="001",
                colors=[Color.RED],
                color_identity=[Color.RED],
                oracle_text="Create a Treasure token.",
            ),
            _make_card(
                name="Black Eater",
                collector_number="002",
                colors=[Color.BLACK],
                color_identity=[Color.BLACK],
                oracle_text="Sacrifice a Treasure: Draw a card.",
            ),
            _make_card(
                name="Blue Eater",
                collector_number="003",
                colors=[Color.BLUE],
                color_identity=[Color.BLUE],
                oracle_text="Sacrifice a Treasure: Draw a card.",
            ),
        ]
        _, warnings = analyze_resource_economy(cards, [])
        assert any("Treasure" in w and "outside the consumers' colors" in w for w in warnings)

    def test_colorless_maker_satisfies_any_color(self):
        # A colorless maker fixes any color's gap → no mismatch warning.
        cards = [
            _make_card(
                name="Artifact Maker",
                collector_number="001",
                colors=[],
                color_identity=[],
                type_line="Artifact",
                card_types=["Artifact"],
                subtypes=[],
                oracle_text="Create a Treasure token.",
            ),
            _make_card(
                name="Black Eater",
                collector_number="002",
                colors=[Color.BLACK],
                color_identity=[Color.BLACK],
                oracle_text="Sacrifice a Treasure: Draw a card.",
            ),
            _make_card(
                name="Blue Eater",
                collector_number="003",
                colors=[Color.BLUE],
                color_identity=[Color.BLUE],
                oracle_text="Sacrifice a Treasure: Draw a card.",
            ),
        ]
        _, warnings = analyze_resource_economy(cards, [])
        assert not any("Treasure" in w for w in warnings)

    def test_mechanic_maker_prevents_starvation_warning(self):
        # No card body creates Cloud, but the Squall mechanic does → not flagged dry.
        squall = _mechanic(
            "Squall",
            "(Whenever this creature attacks, create N colorless Cloud tokens.)",
        )
        cards = [
            _make_card(name="Squaller", collector_number="001", oracle_text="Squall 1"),
        ]
        cards += [
            _make_card(
                name=f"Cloud Eater {i}",
                collector_number=f"01{i}",
                oracle_text="Sacrifice a Cloud token: Add {C}.",
            )
            for i in range(3)
        ]
        report, warnings = analyze_resource_economy(cards, [squall])
        assert not any("Cloud" in w for w in warnings)
        cloud = next(r for r in report["resources"] if r["name"] == "Cloud")
        assert any(m["name"] == "Squall" and "maker" in m["role"] for m in cloud["mechanics"])

    def test_mechanic_consumer_joined(self):
        # Provision consumes Food; the join records its carrier count + role.
        provision = _mechanic(
            "Provision",
            "(Whenever you sacrifice a Food token, put a +1/+1 counter on target creature.)",
        )
        cards = [
            _make_card(name="Maker", collector_number="001", oracle_text="Create a Food token."),
            _make_card(name="Provider", collector_number="002", oracle_text="Provision 1"),
        ]
        report, _ = analyze_resource_economy(cards, [provision])
        food = next(r for r in report["resources"] if r["name"] == "Food")
        joined = next((m for m in food["mechanics"] if m["name"] == "Provision"), None)
        assert joined is not None
        assert "consumer" in joined["role"]
        assert joined["carriers"] == 1

    def test_basics_and_reprints_skipped(self):
        cards = [
            _make_card(
                name="Forest",
                collector_number="L-01",
                type_line="Basic Land — Forest",
                card_types=["Land"],
                supertypes=["Basic"],
                subtypes=["Forest"],
                colors=[],
                color_identity=[],
                oracle_text="Create a Food token.",  # would be a maker if scanned
            ),
            _make_card(
                name="Famous Reprint",
                collector_number="010",
                is_reprint=True,
                oracle_text="Create a Food token.",
            ),
            _make_card(
                name="Real Maker", collector_number="002", oracle_text="Create a Food token."
            ),
        ]
        report, _ = analyze_resource_economy(cards, [])
        food = next(r for r in report["resources"] if r["name"] == "Food")
        # Only the non-basic, non-reprint card counts.
        assert food["makers"] == 1

    def test_untouched_predefined_tokens_excluded_from_report(self):
        # A set that only touches Food shouldn't list Clue/Blood/etc.
        cards = [_make_card(oracle_text="Create a Food token.")]
        report, _ = analyze_resource_economy(cards, [])
        names = {r["name"] for r in report["resources"]}
        assert names == {"Food"}

    def test_per_color_and_rarity_tally(self):
        cards = [
            _make_card(
                name="Green Maker",
                collector_number="001",
                colors=[Color.GREEN],
                rarity=Rarity.COMMON,
                oracle_text="Create a Food token.",
            ),
            _make_card(
                name="White Maker",
                collector_number="002",
                colors=[Color.WHITE],
                rarity=Rarity.UNCOMMON,
                oracle_text="Create a Food token.",
            ),
        ]
        report, _ = analyze_resource_economy(cards, [])
        food = next(r for r in report["resources"] if r["name"] == "Food")
        assert food["makers_by_color"] == {"G": 1, "W": 1}
        assert food["makers_by_rarity"] == {"common": 1, "uncommon": 1}
