"""Tests for the skeleton revision pipeline (Phase 4A-rev)."""

from __future__ import annotations

from mtgai.generation.skeleton_reviser import (
    RevisionPlan,
    RevisionReport,
    RevisionRound,
    SlotChange,
    apply_revision_plan,
    archive_card,
    extract_metrics,
    serialize_all_cards,
    serialize_card_compact,
    update_skeleton_slot,
    write_revision_report,
)
from mtgai.models.card import Card
from mtgai.models.enums import Color, Rarity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_card(**overrides) -> Card:
    """Create a test card with sane defaults."""
    defaults = {
        "name": "Test Card",
        "mana_cost": "{2}{W}",
        "cmc": 3.0,
        "type_line": "Creature — Human Soldier",
        "oracle_text": "Vigilance",
        "power": "2",
        "toughness": "3",
        "rarity": Rarity.COMMON,
        "colors": [Color.WHITE],
        "color_identity": [Color.WHITE],
        "collector_number": "W-C-01",
        "slot_id": "W-C-01",
        "set_code": "TST",
        "card_types": ["Creature"],
        "subtypes": ["Human", "Soldier"],
    }
    defaults.update(overrides)
    return Card(**defaults)


def _make_skeleton(*slot_defs) -> dict:
    """Build a minimal skeleton dict from slot tuples.

    Each slot_def: (slot_id, color, rarity, card_type, cmc_target, mechanic_tag, notes)
    """
    slots = []
    for sd in slot_defs:
        slot = {
            "slot_id": sd[0],
            "color": sd[1],
            "rarity": sd[2],
            "card_type": sd[3],
            "cmc_target": sd[4],
            "archetype_tags": [],
            "mechanic_tag": sd[5] if len(sd) > 5 else "evergreen",
            "is_reprint_slot": False,
            "card_id": None,
            "notes": sd[6] if len(sd) > 6 else "",
            "color_pair": None,
        }
        slots.append(slot)
    return {"config": {"name": "Test", "code": "TST"}, "slots": slots}


# ---------------------------------------------------------------------------
# serialize_card_compact
# ---------------------------------------------------------------------------


class TestSerializeCardCompact:
    def test_basic_creature(self):
        card = _make_card()
        result = serialize_card_compact(card)
        assert "W-C-01" in result
        assert "Test Card" in result
        assert "{2}{W}" in result
        assert "Creature" in result
        assert "2/3" in result
        assert "Vigilance" in result

    def test_planeswalker_shows_loyalty(self):
        card = _make_card(
            name="Jace, Test",
            type_line="Legendary Planeswalker — Jace",
            oracle_text="+1: Draw a card.\n-3: Return target creature.",
            power=None,
            toughness=None,
            loyalty="3",
            card_types=["Planeswalker"],
            subtypes=["Jace"],
        )
        result = serialize_card_compact(card)
        assert "[3]" in result

    def test_long_oracle_truncated(self):
        card = _make_card(oracle_text="A" * 200)
        result = serialize_card_compact(card)
        assert "..." in result
        # Truncated to ~80 chars
        oracle_part = result.split("|")[-1].strip()
        assert len(oracle_part) <= 85

    def test_reminder_text_stripped(self):
        card = _make_card(oracle_text="Salvage 2 (Look at the top 2 cards of your library.)")
        result = serialize_card_compact(card)
        assert "Look at" not in result
        assert "Salvage 2" in result

    def test_land_no_mana_cost(self):
        card = _make_card(
            name="Test Land",
            mana_cost=None,
            cmc=0.0,
            type_line="Land",
            oracle_text="{T}: Add {G}.",
            power=None,
            toughness=None,
            colors=[],
            color_identity=[Color.GREEN],
            card_types=["Land"],
            subtypes=[],
        )
        result = serialize_card_compact(card)
        assert "Test Land" in result
        # Mana cost field should be empty
        parts = result.split("|")
        assert parts[2].strip() == ""

    def test_slot_id_preferred_over_collector_number(self):
        card = _make_card(slot_id="W-C-02", collector_number="001")
        result = serialize_card_compact(card)
        assert result.startswith("W-C-02")


class TestSerializeAllCards:
    def test_multiple_cards(self):
        cards = [
            _make_card(name="Card A", slot_id="W-C-01"),
            _make_card(name="Card B", slot_id="W-C-02"),
            _make_card(name="Card C", slot_id="U-C-01"),
        ]
        result = serialize_all_cards(cards)
        lines = result.strip().split("\n")
        assert len(lines) == 3
        assert "Card A" in lines[0]
        assert "Card B" in lines[1]
        assert "Card C" in lines[2]


# ---------------------------------------------------------------------------
# SlotChange / RevisionPlan models
# ---------------------------------------------------------------------------


class TestDataModels:
    def test_slot_change_regenerate(self):
        change = SlotChange(
            slot_id="W-C-01",
            current_card_name="Test Card",
            action="regenerate",
            reasoning="Too generic",
        )
        assert change.action == "regenerate"
        assert change.new_constraints is None

    def test_slot_change_modify_slot(self):
        change = SlotChange(
            slot_id="U-C-04",
            current_card_name="Excavate",
            action="modify_slot",
            new_constraints={
                "card_type": "artifact_creature",
                "mechanic_tag": "complex",
                "notes": "Must use Malfunction 1",
            },
            reasoning="Need more Malfunction cards",
        )
        assert change.action == "modify_slot"
        assert change.new_constraints["mechanic_tag"] == "complex"

    def test_revision_plan_round_trip(self):
        plan = RevisionPlan(
            analysis="Salvage over-represented",
            changes=[
                SlotChange(
                    slot_id="W-C-01",
                    current_card_name="Test",
                    action="regenerate",
                    reasoning="Generic",
                ),
            ],
            expected_improvements={
                "salvage_count": 8,
                "malfunction_count": 5,
            },
        )
        dumped = plan.model_dump()
        restored = RevisionPlan.model_validate(dumped)
        assert len(restored.changes) == 1
        assert restored.expected_improvements["salvage_count"] == 8


# ---------------------------------------------------------------------------
# update_skeleton_slot
# ---------------------------------------------------------------------------


class TestUpdateSkeletonSlot:
    def test_update_existing_fields(self):
        skeleton = _make_skeleton(("W-C-01", "W", "common", "creature", 2))
        update_skeleton_slot(
            skeleton,
            "W-C-01",
            {"card_type": "artifact", "cmc_target": 3},
        )
        slot = skeleton["slots"][0]
        assert slot["card_type"] == "artifact"
        assert slot["cmc_target"] == 3

    def test_update_notes(self):
        skeleton = _make_skeleton(("U-C-04", "U", "common", "sorcery", 4))
        update_skeleton_slot(
            skeleton,
            "U-C-04",
            {"notes": "Must use Malfunction 1"},
        )
        assert skeleton["slots"][0]["notes"] == "Must use Malfunction 1"

    def test_update_nonexistent_slot_warns(self, caplog):
        skeleton = _make_skeleton(("W-C-01", "W", "common", "creature", 2))
        update_skeleton_slot(skeleton, "FAKE-01", {"notes": "test"})
        assert "not found" in caplog.text

    def test_update_mechanic_tag(self):
        skeleton = _make_skeleton(("R-U-01", "R", "uncommon", "creature", 3, "evergreen"))
        update_skeleton_slot(skeleton, "R-U-01", {"mechanic_tag": "complex"})
        assert skeleton["slots"][0]["mechanic_tag"] == "complex"


# ---------------------------------------------------------------------------
# archive_card
# ---------------------------------------------------------------------------


class TestArchiveCard:
    def test_archive_moves_file(self, tmp_path):
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        archive_dir = tmp_path / "cards" / "archive"

        # Create a card file
        card = _make_card(name="Doomed Card", collector_number="W-C-01")
        card_file = cards_dir / "W-C-01_doomed_card.json"
        card_file.write_text(card.model_dump_json(indent=2), encoding="utf-8")

        result = archive_card("W-C-01", cards_dir, archive_dir)
        assert result is not None
        assert not card_file.exists()
        assert (archive_dir / "W-C-01_doomed_card.json").exists()

    def test_archive_nonexistent_returns_none(self, tmp_path):
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        archive_dir = tmp_path / "cards" / "archive"

        result = archive_card("FAKE-01", cards_dir, archive_dir)
        assert result is None

    def test_archive_handles_collision(self, tmp_path):
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        archive_dir = tmp_path / "cards" / "archive"
        archive_dir.mkdir(parents=True)

        card = _make_card(name="Doomed Card", collector_number="W-C-01")
        card_file = cards_dir / "W-C-01_doomed_card.json"
        card_file.write_text(card.model_dump_json(indent=2), encoding="utf-8")

        # Pre-populate archive with same filename
        existing = archive_dir / "W-C-01_doomed_card.json"
        existing.write_text("{}", encoding="utf-8")

        result = archive_card("W-C-01", cards_dir, archive_dir)
        assert result is not None
        # Original archive file untouched
        assert existing.exists()
        # New file has timestamp suffix
        archived_files = list(archive_dir.glob("W-C-01_doomed_card*.json"))
        assert len(archived_files) == 2


# ---------------------------------------------------------------------------
# apply_revision_plan
# ---------------------------------------------------------------------------


class TestApplyRevisionPlan:
    def test_regenerate_action(self, tmp_path):
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        archive_dir = tmp_path / "cards" / "archive"

        # Create card file
        card = _make_card(name="Old Card", collector_number="W-C-01")
        card_file = cards_dir / "W-C-01_old_card.json"
        card_file.write_text(card.model_dump_json(indent=2), encoding="utf-8")

        skeleton = _make_skeleton(("W-C-01", "W", "common", "creature", 2))
        plan = RevisionPlan(
            analysis="Test",
            changes=[
                SlotChange(
                    slot_id="W-C-01",
                    current_card_name="Old Card",
                    action="regenerate",
                    reasoning="Too generic",
                ),
            ],
            expected_improvements={},
        )

        result = apply_revision_plan(plan, skeleton, cards_dir, archive_dir)
        assert result == ["W-C-01"]
        assert not card_file.exists()
        assert (archive_dir / "W-C-01_old_card.json").exists()

    def test_modify_slot_updates_skeleton(self, tmp_path):
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        archive_dir = tmp_path / "cards" / "archive"

        card = _make_card(name="Old Card", collector_number="U-C-04")
        card_file = cards_dir / "U-C-04_old_card.json"
        card_file.write_text(card.model_dump_json(indent=2), encoding="utf-8")

        skeleton = _make_skeleton(("U-C-04", "U", "common", "sorcery", 4, "complex"))
        plan = RevisionPlan(
            analysis="Test",
            changes=[
                SlotChange(
                    slot_id="U-C-04",
                    current_card_name="Old Card",
                    action="modify_slot",
                    new_constraints={
                        "card_type": "artifact",
                        "mechanic_tag": "complex",
                        "notes": "Must use Malfunction 1",
                    },
                    reasoning="Need artifact + Malfunction",
                ),
            ],
            expected_improvements={},
        )

        result = apply_revision_plan(plan, skeleton, cards_dir, archive_dir)
        assert result == ["U-C-04"]
        slot = skeleton["slots"][0]
        assert slot["card_type"] == "artifact"
        assert slot["notes"] == "Must use Malfunction 1"


# ---------------------------------------------------------------------------
# extract_metrics
# ---------------------------------------------------------------------------


class TestExtractMetrics:
    def test_extracts_mechanic_counts(self):
        balance = {
            "mechanic_distribution": [
                {"mechanic_name": "Salvage", "total_actual": 12},
                {"mechanic_name": "Malfunction", "total_actual": 3},
                {"mechanic_name": "Overclock", "total_actual": 1},
            ],
            "issues": [],
            "summary": {"PASS": 49, "WARN": 0, "FAIL": 0},
        }
        metrics = extract_metrics(balance)
        assert metrics["salvage_count"] == 12
        assert metrics["malfunction_count"] == 3
        assert metrics["overclock_count"] == 1

    def test_counts_tier_mismatches(self):
        balance = {
            "mechanic_distribution": [],
            "issues": [
                {"check": "conformance.mechanic_tier", "severity": "WARN"},
                {"check": "conformance.mechanic_tier", "severity": "WARN"},
                {"check": "coverage.cmc_gap", "severity": "WARN"},
            ],
            "summary": {"PASS": 40, "WARN": 3, "FAIL": 0},
        }
        metrics = extract_metrics(balance)
        assert metrics["tier_mismatches"] == 2
        assert metrics["total_issues"] == 3


# ---------------------------------------------------------------------------
# write_revision_report
# ---------------------------------------------------------------------------


class TestWriteRevisionReport:
    def test_writes_markdown(self, tmp_path):
        report = RevisionReport(
            set_code="TST",
            rounds=[
                RevisionRound(
                    round_number=1,
                    timestamp="2026-03-14T00:00:00Z",
                    plan=RevisionPlan(
                        analysis="Salvage too high",
                        changes=[
                            SlotChange(
                                slot_id="W-C-01",
                                current_card_name="Old Card",
                                action="regenerate",
                                reasoning="Generic filler",
                            ),
                        ],
                        expected_improvements={"salvage_count": 8},
                    ),
                    slots_changed=["W-C-01"],
                    cards_archived=["Old Card"],
                    cards_regenerated=["New Card"],
                    cost_usd=0.50,
                    pre_metrics={"salvage_count": 12},
                    post_metrics={"salvage_count": 8},
                ),
            ],
            total_cost_usd=0.50,
            total_cards_replaced=1,
        )

        path = tmp_path / "reports" / "revision-report.md"
        write_revision_report(report, path)

        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "# Skeleton Revision Report" in content
        assert "Round 1" in content
        assert "Salvage too high" in content
        assert "W-C-01" in content
        assert "Old Card" in content
        assert "New Card" in content
        assert "$0.5000" in content

    def test_empty_report(self, tmp_path):
        report = RevisionReport(set_code="TST")
        path = tmp_path / "report.md"
        write_revision_report(report, path)

        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "Total rounds: 0" in content
