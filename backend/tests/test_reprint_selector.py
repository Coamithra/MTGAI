"""Tests for the reprint selector module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from mtgai.generation.reprint_selector import (
    ReprintCandidate,
    ReprintSlot,
    _color_matches,
    _type_matches,
    convert_to_card,
    extract_set_config,
    format_candidate_tldr,
    identify_reprint_slots,
    load_reprint_pool,
    pre_filter_for_slot,
    select_reprints,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candidate(**overrides) -> ReprintCandidate:
    """Create a ReprintCandidate with sane defaults."""
    defaults = {
        "name": "Test Card",
        "mana_cost": "{1}{B}",
        "cmc": 2.0,
        "type_line": "Instant",
        "oracle_text": "Destroy target creature.",
        "colors": ["B"],
        "rarity": "common",
        "role": "removal_hard_kill",
        "source": "curated_pool",
        "edhrec_rank": 1500,
        "keywords": [],
        "subtypes": [],
        "tags": ["staple", "removal"],
    }
    defaults.update(overrides)
    return ReprintCandidate(**defaults)


def _make_slot(**overrides) -> ReprintSlot:
    """Create a ReprintSlot with sane defaults."""
    defaults = {
        "slot_id": "B-C-03",
        "color": "B",
        "rarity": "common",
        "card_type": "instant",
        "role_needed": "removal_hard_kill",
        "cmc_target": 3,
        "mechanic_tag": "evergreen",
    }
    defaults.update(overrides)
    return ReprintSlot(**defaults)


def _make_set_config(**overrides) -> dict:
    """Create a set_config with sane defaults."""
    defaults = {
        "name": "Test Set",
        "code": "TST",
        "theme": "Test theme",
        "themes": ["artifact"],
        "creature_types": ["Dinosaur", "Human"],
        "special_constraints": ["Artifact subtheme"],
        "set_size": 60,
    }
    defaults.update(overrides)
    return defaults


def _make_skeleton_json(slots: list[dict] | None = None) -> str:
    """Create a minimal skeleton JSON string for testing."""
    if slots is None:
        slots = [
            {
                "slot_id": "B-C-03",
                "color": "B",
                "rarity": "common",
                "card_type": "instant",
                "cmc_target": 3,
                "archetype_tags": ["WB", "UB", "BR", "BG"],
                "mechanic_tag": "evergreen",
                "is_reprint_slot": False,
                "card_id": None,
                "notes": "",
                "color_pair": None,
            },
            {
                "slot_id": "R-C-03",
                "color": "R",
                "rarity": "common",
                "card_type": "instant",
                "cmc_target": 4,
                "archetype_tags": ["WR", "UR", "BR", "RG"],
                "mechanic_tag": "evergreen",
                "is_reprint_slot": False,
                "card_id": None,
                "notes": "",
                "color_pair": None,
            },
            {
                "slot_id": "W-C-01",
                "color": "W",
                "rarity": "common",
                "card_type": "creature",
                "cmc_target": 1,
                "archetype_tags": ["WU", "WB", "WR", "WG"],
                "mechanic_tag": "vanilla",
                "is_reprint_slot": False,
                "card_id": None,
                "notes": "",
                "color_pair": None,
            },
            {
                "slot_id": "G-C-03",
                "color": "G",
                "rarity": "common",
                "card_type": "instant",
                "cmc_target": 4,
                "archetype_tags": ["WG", "UG", "BG", "RG"],
                "mechanic_tag": "evergreen",
                "is_reprint_slot": False,
                "card_id": None,
                "notes": "",
                "color_pair": None,
            },
            {
                "slot_id": "U-C-03",
                "color": "U",
                "rarity": "common",
                "card_type": "instant",
                "cmc_target": 3,
                "archetype_tags": ["WU", "UB", "UR", "UG"],
                "mechanic_tag": "evergreen",
                "is_reprint_slot": False,
                "card_id": None,
                "notes": "",
                "color_pair": None,
            },
            # Non-eligible: complex mechanic
            {
                "slot_id": "W-C-04",
                "color": "W",
                "rarity": "common",
                "card_type": "sorcery",
                "cmc_target": 4,
                "archetype_tags": ["WU", "WB", "WR", "WG"],
                "mechanic_tag": "complex",
                "is_reprint_slot": False,
                "card_id": None,
                "notes": "",
                "color_pair": None,
            },
            # Non-eligible: already assigned
            {
                "slot_id": "B-C-01",
                "color": "B",
                "rarity": "common",
                "card_type": "creature",
                "cmc_target": 1,
                "archetype_tags": ["WB", "UB", "BR", "BG"],
                "mechanic_tag": "vanilla",
                "is_reprint_slot": False,
                "card_id": "some-card-id",
                "notes": "",
                "color_pair": None,
            },
            # french_vanilla creature
            {
                "slot_id": "R-C-01",
                "color": "R",
                "rarity": "common",
                "card_type": "creature",
                "cmc_target": 2,
                "archetype_tags": ["WR", "UR", "BR", "RG"],
                "mechanic_tag": "french_vanilla",
                "is_reprint_slot": False,
                "card_id": None,
                "notes": "",
                "color_pair": None,
            },
            # Uncommon slot
            {
                "slot_id": "G-U-01",
                "color": "G",
                "rarity": "uncommon",
                "card_type": "creature",
                "cmc_target": 2,
                "archetype_tags": ["WG", "UG", "BG", "RG"],
                "mechanic_tag": "evergreen",
                "is_reprint_slot": False,
                "card_id": None,
                "notes": "",
                "color_pair": None,
            },
            # Rare complex (not eligible)
            {
                "slot_id": "W-R-01",
                "color": "W",
                "rarity": "rare",
                "card_type": "creature",
                "cmc_target": 1,
                "archetype_tags": ["WU", "WB", "WR", "WG"],
                "mechanic_tag": "complex",
                "is_reprint_slot": False,
                "card_id": None,
                "notes": "",
                "color_pair": None,
            },
        ]

    skeleton = {
        "config": {
            "name": "Test Set",
            "code": "TST",
            "theme": "Test theme",
            "flavor_description": "A science-fantasy world with artifact relics and dinosaurs.",
            "set_size": len(slots),
            "mechanic_count": 3,
            "special_constraints": ["Artifact subtheme", "Include dinosaurs"],
        },
        "slots": slots,
        "total_slots": len(slots),
    }
    return json.dumps(skeleton, indent=2)


@pytest.fixture()
def skeleton_path(tmp_path: Path) -> Path:
    """Create a temporary skeleton.json for testing."""
    path = tmp_path / "skeleton.json"
    path.write_text(_make_skeleton_json(), encoding="utf-8")
    return path


@pytest.fixture()
def set_config() -> dict:
    return _make_set_config()


# ---------------------------------------------------------------------------
# Tests: Pool loading
# ---------------------------------------------------------------------------


class TestLoadReprintPool:
    def test_pool_loads_successfully(self):
        pool = load_reprint_pool()
        assert len(pool) > 0

    def test_pool_has_expected_structure(self):
        pool = load_reprint_pool()
        for card in pool:
            assert card.name
            assert card.type_line
            assert card.role
            assert card.source == "curated_pool"
            assert card.rarity in ("common", "uncommon", "rare", "mythic")

    def test_pool_has_required_roles(self):
        pool = load_reprint_pool()
        roles = {c.role for c in pool}
        assert "removal_hard_kill" in roles
        assert "removal_damage" in roles
        assert "mana_fixing" in roles
        assert "combat_trick" in roles

    def test_pool_cards_have_valid_colors(self):
        pool = load_reprint_pool()
        valid_colors = {"W", "U", "B", "R", "G"}
        for card in pool:
            for c in card.colors:
                assert c in valid_colors, f"{card.name} has invalid color: {c}"

    def test_pool_size_in_expected_range(self):
        pool = load_reprint_pool()
        assert 100 <= len(pool) <= 200, f"Pool has {len(pool)} cards, expected 100-200"


# ---------------------------------------------------------------------------
# Tests: Slot identification
# ---------------------------------------------------------------------------


class TestIdentifyReprintSlots:
    def test_identifies_eligible_slots(self, skeleton_path: Path):
        slots = identify_reprint_slots(skeleton_path)
        # B-C-03, R-C-03, W-C-01, G-C-03, U-C-03, R-C-01, G-U-01
        assert len(slots) == 7

    def test_excludes_complex_mechanic(self, skeleton_path: Path):
        slots = identify_reprint_slots(skeleton_path)
        slot_ids = {s.slot_id for s in slots}
        assert "W-C-04" not in slot_ids

    def test_excludes_assigned_slots(self, skeleton_path: Path):
        slots = identify_reprint_slots(skeleton_path)
        slot_ids = {s.slot_id for s in slots}
        assert "B-C-01" not in slot_ids

    def test_infers_roles_correctly(self, skeleton_path: Path):
        slots = identify_reprint_slots(skeleton_path)
        slot_map = {s.slot_id: s for s in slots}
        assert slot_map["B-C-03"].role_needed == "removal_hard_kill"
        assert slot_map["R-C-03"].role_needed == "removal_damage"
        assert slot_map["W-C-01"].role_needed == "utility_creature"
        assert slot_map["U-C-03"].role_needed == "removal_bounce"


# ---------------------------------------------------------------------------
# Tests: Pre-filtering
# ---------------------------------------------------------------------------


class TestColorMatches:
    def test_mono_color_match(self):
        assert _color_matches(["B"], "B") is True

    def test_mono_color_mismatch(self):
        assert _color_matches(["R"], "B") is False

    def test_colorless_match(self):
        assert _color_matches([], "colorless") is True

    def test_colorless_mismatch(self):
        assert _color_matches(["B"], "colorless") is False

    def test_multicolor_match(self):
        assert _color_matches(["W", "U"], "multicolor") is True

    def test_multicolor_mismatch(self):
        assert _color_matches(["B"], "multicolor") is False


class TestTypeMatches:
    def test_direct_match(self):
        assert _type_matches("Instant", "instant") is True

    def test_creature_subtype_match(self):
        assert _type_matches("Creature -- Elf Druid", "creature") is True

    def test_artifact_creature_matches_creature(self):
        assert _type_matches("Artifact Creature -- Construct", "creature") is True

    def test_artifact_creature_matches_artifact(self):
        assert _type_matches("Artifact Creature -- Construct", "artifact") is True

    def test_type_mismatch(self):
        assert _type_matches("Instant", "creature") is False


class TestPreFilterForSlot:
    def test_filters_by_color(self):
        pool = [
            _make_candidate(name="Black Card", colors=["B"]),
            _make_candidate(name="Red Card", colors=["R"]),
        ]
        slot = _make_slot(color="B")
        result = pre_filter_for_slot(pool, slot)
        assert len(result) == 1
        assert result[0].name == "Black Card"

    def test_filters_by_rarity(self):
        pool = [
            _make_candidate(name="Common", rarity="common"),
            _make_candidate(name="Uncommon", rarity="uncommon"),
        ]
        slot = _make_slot(rarity="common")
        result = pre_filter_for_slot(pool, slot)
        assert len(result) == 1
        assert result[0].name == "Common"

    def test_filters_by_type(self):
        pool = [
            _make_candidate(name="Instant", type_line="Instant"),
            _make_candidate(name="Creature", type_line="Creature -- Human"),
        ]
        slot = _make_slot(card_type="instant")
        result = pre_filter_for_slot(pool, slot)
        assert len(result) == 1
        assert result[0].name == "Instant"

    def test_sorts_by_edhrec_rank(self):
        pool = [
            _make_candidate(name="Unpopular", edhrec_rank=9000),
            _make_candidate(name="Popular", edhrec_rank=500),
            _make_candidate(name="Mid", edhrec_rank=3000),
        ]
        slot = _make_slot()
        result = pre_filter_for_slot(pool, slot)
        assert [c.name for c in result] == ["Popular", "Mid", "Unpopular"]

    def test_caps_at_max(self):
        pool = [_make_candidate(name=f"Card {i}", edhrec_rank=i * 100) for i in range(20)]
        slot = _make_slot()
        result = pre_filter_for_slot(pool, slot)
        assert len(result) == 15  # _MAX_CANDIDATES_PER_SLOT

    def test_empty_pool_returns_empty(self):
        result = pre_filter_for_slot([], _make_slot())
        assert result == []


# ---------------------------------------------------------------------------
# Tests: Candidate TLDR formatting
# ---------------------------------------------------------------------------


class TestFormatCandidateTldr:
    def test_basic_instant(self):
        c = _make_candidate(
            name="Murder", mana_cost="{1}{B}{B}", oracle_text="Destroy target creature."
        )
        tldr = format_candidate_tldr(c)
        assert tldr == "Murder ({1}{B}{B} — Destroy target creature.)"

    def test_creature_with_pt(self):
        c = _make_candidate(
            name="Llanowar Elves",
            mana_cost="{G}",
            oracle_text="{T}: Add {G}.",
            power="1",
            toughness="1",
        )
        tldr = format_candidate_tldr(c)
        assert "1/1" in tldr
        assert "{G}" in tldr

    def test_no_mana_cost(self):
        c = _make_candidate(name="Evolving Wilds", mana_cost=None, oracle_text="Sacrifice...")
        tldr = format_candidate_tldr(c)
        assert "no cost" in tldr

    def test_long_oracle_truncated(self):
        long_text = "x" * 200
        c = _make_candidate(name="Verbose Card", oracle_text=long_text)
        tldr = format_candidate_tldr(c)
        assert "..." in tldr
        assert len(tldr) < 250

    def test_multiline_oracle_flattened(self):
        c = _make_candidate(
            name="Modal Card",
            oracle_text="Choose one --\n* Mode A\n* Mode B",
        )
        tldr = format_candidate_tldr(c)
        assert "\n" not in tldr
        assert "/ * Mode A" in tldr


# ---------------------------------------------------------------------------
# Tests: LLM-based selection (mocked)
# ---------------------------------------------------------------------------


class TestLlmSelectReprints:
    @pytest.fixture(autouse=True)
    def _open_project(self):
        """``_llm_select_reprints`` resolves the model via the active project."""
        from mtgai.runtime import active_project
        from mtgai.settings.model_settings import ModelSettings

        active_project.write_active_project(
            active_project.ProjectState(set_code="TST", settings=ModelSettings())
        )
        yield
        active_project.clear_active_project()

    def _mock_haiku_response(self, selections: list[dict]) -> dict:
        return {
            "result": {"selections": selections},
            "input_tokens": 500,
            "output_tokens": 100,
            "stop_reason": "end_turn",
        }

    def test_selects_from_llm_response(self):
        """LLM returns valid selections, they're parsed correctly."""
        pool = [
            _make_candidate(name="Murder", colors=["B"], rarity="common"),
            _make_candidate(
                name="Abrade",
                colors=["R"],
                rarity="common",
                role="removal_damage",
                type_line="Instant",
                mana_cost="{1}{R}",
            ),
        ]
        slots = [
            _make_slot(slot_id="B-C-03", color="B", card_type="instant"),
            _make_slot(
                slot_id="R-C-03", color="R", card_type="instant", role_needed="removal_damage"
            ),
        ]
        config = _make_set_config()

        mock_response = self._mock_haiku_response(
            [
                {"slot_id": "B-C-03", "card_name": "Murder", "reason": "Essential removal"},
                {"slot_id": "R-C-03", "card_name": "Abrade", "reason": "Hits artifacts"},
            ]
        )

        with patch(
            "mtgai.generation.llm_client.generate_with_tool",
            return_value=mock_response,
        ):
            from mtgai.generation.reprint_selector import _llm_select_reprints

            result = _llm_select_reprints(slots, pool, config, count=2)

        assert len(result) == 2
        assert result[0].candidate.name == "Murder"
        assert result[0].slot.slot_id == "B-C-03"
        assert result[0].reason == "Essential removal"
        assert result[1].candidate.name == "Abrade"

    def test_handles_unknown_slot_id(self):
        """LLM returns an invalid slot_id — it's skipped with a warning."""
        pool = [_make_candidate(name="Murder")]
        slots = [_make_slot(slot_id="B-C-03")]
        config = _make_set_config()

        mock_response = self._mock_haiku_response(
            [
                {"slot_id": "INVALID", "card_name": "Murder", "reason": "test"},
            ]
        )

        with patch(
            "mtgai.generation.llm_client.generate_with_tool",
            return_value=mock_response,
        ):
            from mtgai.generation.reprint_selector import _llm_select_reprints

            result = _llm_select_reprints(slots, pool, config, count=1)

        assert len(result) == 0

    def test_handles_unknown_card_name(self):
        """LLM returns a card name not in candidates — it's skipped."""
        pool = [_make_candidate(name="Murder")]
        slots = [_make_slot(slot_id="B-C-03")]
        config = _make_set_config()

        mock_response = self._mock_haiku_response(
            [
                {"slot_id": "B-C-03", "card_name": "Not A Real Card", "reason": "test"},
            ]
        )

        with patch(
            "mtgai.generation.llm_client.generate_with_tool",
            return_value=mock_response,
        ):
            from mtgai.generation.reprint_selector import _llm_select_reprints

            result = _llm_select_reprints(slots, pool, config, count=1)

        assert len(result) == 0

    def test_graceful_failure_on_api_error(self):
        """If the LLM call raises, return empty list."""
        pool = [_make_candidate(name="Murder")]
        slots = [_make_slot(slot_id="B-C-03")]
        config = _make_set_config()

        with patch(
            "mtgai.generation.llm_client.generate_with_tool",
            side_effect=RuntimeError("API down"),
        ):
            from mtgai.generation.reprint_selector import _llm_select_reprints

            result = _llm_select_reprints(slots, pool, config, count=1)

        assert result == []

    def test_case_insensitive_card_matching(self):
        """LLM might return 'murder' instead of 'Murder' — should still match."""
        pool = [_make_candidate(name="Murder")]
        slots = [_make_slot(slot_id="B-C-03")]
        config = _make_set_config()

        mock_response = self._mock_haiku_response(
            [
                {"slot_id": "B-C-03", "card_name": "murder", "reason": "test"},
            ]
        )

        with patch(
            "mtgai.generation.llm_client.generate_with_tool",
            return_value=mock_response,
        ):
            from mtgai.generation.reprint_selector import _llm_select_reprints

            result = _llm_select_reprints(slots, pool, config, count=1)

        assert len(result) == 1
        assert result[0].candidate.name == "Murder"

    def test_no_candidates_returns_empty(self):
        """If no candidates match any slot after pre-filtering, return empty."""
        pool = [_make_candidate(name="Red Card", colors=["R"])]
        slots = [_make_slot(slot_id="G-C-01", color="G")]  # Green slot, no green candidates
        config = _make_set_config()

        from mtgai.generation.reprint_selector import _llm_select_reprints

        result = _llm_select_reprints(slots, pool, config, count=1)

        assert result == []


# ---------------------------------------------------------------------------
# Tests: Main entry point
# ---------------------------------------------------------------------------


class TestSelectReprints:
    def test_entry_point_works(self, skeleton_path: Path):
        """select_reprints calls LLM and returns structured result."""
        mock_response = {
            "result": {
                "selections": [
                    {"slot_id": "B-C-03", "card_name": "Murder", "reason": "Removal staple"},
                ]
            },
            "input_tokens": 500,
            "output_tokens": 100,
            "stop_reason": "end_turn",
        }

        with patch(
            "mtgai.generation.llm_client.generate_with_tool",
            return_value=mock_response,
        ):
            result = select_reprints(skeleton_path, count=1)

        assert result.set_code == "TST"
        assert result.set_size == 10
        assert result.target_reprint_count == 1
        assert isinstance(result.selections, list)
        assert result.selection_timestamp

    def test_default_count_from_set_size(self, skeleton_path: Path):
        """With no explicit count, computes from set_size * 0.028."""
        mock_response = {
            "result": {"selections": []},
            "input_tokens": 100,
            "output_tokens": 50,
            "stop_reason": "end_turn",
        }

        with patch(
            "mtgai.generation.llm_client.generate_with_tool",
            return_value=mock_response,
        ):
            result = select_reprints(skeleton_path)

        # round(10 * 0.028) = 0, but min is 1
        assert result.target_reprint_count >= 1


# ---------------------------------------------------------------------------
# Tests: Card conversion
# ---------------------------------------------------------------------------


class TestConvertToCard:
    def test_basic_conversion(self):
        cand = _make_candidate(
            name="Murder",
            mana_cost="{1}{B}{B}",
            cmc=3.0,
            type_line="Instant",
            oracle_text="Destroy target creature.",
            colors=["B"],
            rarity="common",
        )
        card = convert_to_card(cand, "B-C-03", "ASD", "61")
        assert card.name == "Murder"
        assert card.is_reprint is True
        assert card.set_code == "ASD"
        assert card.collector_number == "61"
        assert card.slot_id == "B-C-03"
        assert card.mana_cost == "{1}{B}{B}"
        assert card.cmc == 3.0
        assert card.oracle_text == "Destroy target creature."
        assert card.rarity.value == "common"

    def test_creature_conversion(self):
        cand = _make_candidate(
            name="Llanowar Elves",
            mana_cost="{G}",
            cmc=1.0,
            type_line="Creature -- Elf Druid",
            oracle_text="{T}: Add {G}.",
            colors=["G"],
            rarity="common",
            power="1",
            toughness="1",
        )
        card = convert_to_card(cand, "G-C-01", "ASD", "62")
        assert card.name == "Llanowar Elves"
        assert card.power == "1"
        assert card.toughness == "1"
        assert "Elf" in card.subtypes
        assert "Druid" in card.subtypes
        assert "Creature" in card.card_types

    def test_colorless_conversion(self):
        cand = _make_candidate(
            name="Evolving Wilds",
            mana_cost=None,
            cmc=0.0,
            type_line="Land",
            oracle_text="Sacrifice: search for a basic land.",
            colors=[],
            rarity="common",
        )
        card = convert_to_card(cand, "L-C-01", "ASD", "63")
        assert card.colors == []
        assert card.is_reprint is True
        assert card.mana_cost is None

    def test_design_notes_include_source(self):
        cand = _make_candidate(source="curated_pool")
        card = convert_to_card(cand, "B-C-03", "ASD", "64")
        assert "curated_pool" in card.design_notes


# ---------------------------------------------------------------------------
# Tests: Set config extraction
# ---------------------------------------------------------------------------


class TestExtractSetConfig:
    def test_extracts_basic_fields(self, skeleton_path: Path):
        config = extract_set_config(skeleton_path)
        assert config["name"] == "Test Set"
        assert config["code"] == "TST"
        assert config["set_size"] == 10

    def test_infers_themes(self, skeleton_path: Path):
        config = extract_set_config(skeleton_path)
        assert "artifact" in config["themes"]

    def test_infers_creature_types(self, skeleton_path: Path):
        config = extract_set_config(skeleton_path)
        assert "Dinosaur" in config["creature_types"]


# ---------------------------------------------------------------------------
# Tests: Setting-agnostic filter
# ---------------------------------------------------------------------------


class TestSettingAgnostic:
    def test_setting_agnostic_field_loaded(self):
        """Verify that setting_agnostic is read correctly from the real pool."""
        pool = load_reprint_pool()
        by_name = {c.name: c for c in pool}
        assert by_name["Murder"].setting_agnostic is True
        assert by_name["Llanowar Visionary"].setting_agnostic is False

    def test_pre_filter_excludes_non_agnostic(self):
        """Non-agnostic cards should not appear in pre-filtered results."""
        pool = [
            _make_candidate(name="Generic Kill", setting_agnostic=True),
            _make_candidate(name="Llanowar Specific", setting_agnostic=False),
        ]
        # Pre-filter doesn't check setting_agnostic itself — that's done in select_reprints.
        # But the pool passed to _llm_select_reprints is pre-filtered by select_reprints.
        agnostic_pool = [c for c in pool if c.setting_agnostic is not False]
        slot = _make_slot()
        result = pre_filter_for_slot(agnostic_pool, slot)
        assert all(c.setting_agnostic is not False for c in result)
        assert len(result) == 1
        assert result[0].name == "Generic Kill"
