"""Tests for the reprint selector module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from mtgai.generation.reprint_selector import (
    ReprintCandidate,
    ReprintSlot,
    SelectionPair,
    _llm_check_splashy_fit,
    convert_to_card,
    extract_set_config,
    identify_reprint_slots,
    load_reprint_pool,
    score_splashy_candidate,
    score_staple_candidate,
    select_reprints,
    select_splashy_reprints,
    select_staple_reprints,
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
            # Reprint-eligible slots
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
            # Non-eligible slot (complex mechanic)
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
            # Non-eligible slot (already assigned)
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
        # Must have at least these core roles
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
        # Should find: B-C-03, R-C-03, W-C-01, G-C-03, U-C-03, R-C-01, G-U-01
        # Should NOT find: W-C-04 (complex), B-C-01 (assigned), W-R-01 (complex)
        assert len(slots) == 7

    def test_excludes_complex_mechanic(self, skeleton_path: Path):
        slots = identify_reprint_slots(skeleton_path)
        slot_ids = {s.slot_id for s in slots}
        assert "W-C-04" not in slot_ids  # complex mechanic

    def test_excludes_assigned_slots(self, skeleton_path: Path):
        slots = identify_reprint_slots(skeleton_path)
        slot_ids = {s.slot_id for s in slots}
        assert "B-C-01" not in slot_ids  # already has card_id

    def test_infers_roles_correctly(self, skeleton_path: Path):
        slots = identify_reprint_slots(skeleton_path)
        slot_map = {s.slot_id: s for s in slots}

        # B instant -> removal_hard_kill
        assert slot_map["B-C-03"].role_needed == "removal_hard_kill"
        # R instant -> removal_damage
        assert slot_map["R-C-03"].role_needed == "removal_damage"
        # W creature vanilla -> utility_creature
        assert slot_map["W-C-01"].role_needed == "utility_creature"
        # U instant cmc=3 -> removal_bounce
        assert slot_map["U-C-03"].role_needed == "removal_bounce"

    def test_slots_sorted_by_role_priority(self, skeleton_path: Path):
        slots = identify_reprint_slots(skeleton_path)
        # Removal should come before utility creatures
        removal_indices = [i for i, s in enumerate(slots) if s.role_needed.startswith("removal")]
        utility_indices = [i for i, s in enumerate(slots) if s.role_needed == "utility_creature"]
        if removal_indices and utility_indices:
            assert max(removal_indices) < min(utility_indices)


# ---------------------------------------------------------------------------
# Tests: Staple scoring
# ---------------------------------------------------------------------------


class TestScoreStapleCandidate:
    def test_color_match_required(self, set_config: dict):
        cand = _make_candidate(colors=["R"])  # Red candidate
        slot = _make_slot(color="B")  # Black slot
        score = score_staple_candidate(cand, slot, set_config)
        assert score == 0.0

    def test_rarity_match_required(self, set_config: dict):
        cand = _make_candidate(rarity="uncommon")
        slot = _make_slot(rarity="common")
        score = score_staple_candidate(cand, slot, set_config)
        assert score == 0.0

    def test_type_match_required(self, set_config: dict):
        cand = _make_candidate(type_line="Creature -- Human")
        slot = _make_slot(card_type="instant")
        score = score_staple_candidate(cand, slot, set_config)
        assert score == 0.0

    def test_perfect_match_scores_high(self, set_config: dict):
        cand = _make_candidate(
            colors=["B"],
            rarity="common",
            role="removal_hard_kill",
            cmc=3.0,
            edhrec_rank=500,
        )
        slot = _make_slot(
            color="B",
            rarity="common",
            role_needed="removal_hard_kill",
            cmc_target=3,
            card_type="instant",
        )
        score = score_staple_candidate(cand, slot, set_config)
        assert score > 0.7

    def test_role_match_scores_higher(self, set_config: dict):
        matching = _make_candidate(role="removal_hard_kill")
        non_matching = _make_candidate(role="lifegain")
        slot = _make_slot(role_needed="removal_hard_kill")

        score_match = score_staple_candidate(matching, slot, set_config)
        score_no_match = score_staple_candidate(non_matching, slot, set_config)
        assert score_match > score_no_match

    def test_cmc_proximity_affects_score(self, set_config: dict):
        exact_cmc = _make_candidate(cmc=3.0)
        far_cmc = _make_candidate(cmc=6.0)
        slot = _make_slot(cmc_target=3)

        score_exact = score_staple_candidate(exact_cmc, slot, set_config)
        score_far = score_staple_candidate(far_cmc, slot, set_config)
        assert score_exact > score_far

    def test_colorless_matches_colorless_slot(self, set_config: dict):
        cand = _make_candidate(
            colors=[],
            type_line="Land",
            role="mana_fixing",
            mana_cost="",
            cmc=0.0,
        )
        slot = _make_slot(color="colorless", card_type="land", role_needed="mana_fixing")
        score = score_staple_candidate(cand, slot, set_config)
        assert score > 0.0

    def test_artifact_theme_bonus(self):
        config_with_artifact = _make_set_config(themes=["artifact"])
        config_without = _make_set_config(themes=[])

        cand = _make_candidate(tags=["artifact", "removal"])
        slot = _make_slot()

        score_with = score_staple_candidate(cand.model_copy(), slot, config_with_artifact)
        score_without = score_staple_candidate(cand.model_copy(), slot, config_without)
        assert score_with >= score_without


# ---------------------------------------------------------------------------
# Tests: Splashy scoring
# ---------------------------------------------------------------------------


class TestScoreSplashyCandidate:
    def test_popularity_scores_higher_for_low_edhrec(self):
        config = _make_set_config()
        popular = {"edhrec_rank": 500, "released_at": "2020-01-01", "rarity": "rare"}
        unpopular = {"edhrec_rank": 8000, "released_at": "2020-01-01", "rarity": "rare"}

        score_pop, _ = score_splashy_candidate(popular, config, "2026-03-13")
        score_unpop, _ = score_splashy_candidate(unpopular, config, "2026-03-13")
        assert score_pop > score_unpop

    def test_age_scores_higher_for_older_cards(self):
        config = _make_set_config()
        old = {"edhrec_rank": 2000, "released_at": "2018-01-01", "rarity": "rare"}
        new = {"edhrec_rank": 2000, "released_at": "2025-01-01", "rarity": "rare"}

        score_old, _ = score_splashy_candidate(old, config, "2026-03-13")
        score_new, _ = score_splashy_candidate(new, config, "2026-03-13")
        assert score_old > score_new

    def test_mythic_scores_higher_than_rare(self):
        config = _make_set_config()
        mythic = {"edhrec_rank": 2000, "released_at": "2020-01-01", "rarity": "mythic"}
        rare = {"edhrec_rank": 2000, "released_at": "2020-01-01", "rarity": "rare"}

        score_m, _ = score_splashy_candidate(mythic, config, "2026-03-13")
        score_r, _ = score_splashy_candidate(rare, config, "2026-03-13")
        assert score_m > score_r

    def test_thematic_fit_artifact(self):
        config = _make_set_config(themes=["artifact"])
        artifact_card = {
            "edhrec_rank": 2000,
            "released_at": "2020-01-01",
            "rarity": "rare",
            "type_line": "Artifact Creature -- Construct",
            "oracle_text": "artifact synergy",
        }
        non_artifact = {
            "edhrec_rank": 2000,
            "released_at": "2020-01-01",
            "rarity": "rare",
            "type_line": "Creature -- Elf",
            "oracle_text": "gains +1/+1",
        }

        score_a, _ = score_splashy_candidate(artifact_card, config, "2026-03-13")
        score_n, _ = score_splashy_candidate(non_artifact, config, "2026-03-13")
        assert score_a > score_n

    def test_price_boosts_splashy_score(self):
        config = _make_set_config()
        expensive = {
            "edhrec_rank": 2000,
            "released_at": "2020-01-01",
            "rarity": "rare",
            "prices": {"usd": "15.00"},
        }
        cheap = {
            "edhrec_rank": 2000,
            "released_at": "2020-01-01",
            "rarity": "rare",
            "prices": {"usd": "0.50"},
        }
        score_exp, _ = score_splashy_candidate(expensive, config, "2026-03-13")
        score_cheap, _ = score_splashy_candidate(cheap, config, "2026-03-13")
        assert score_exp > score_cheap

    def test_missing_edhrec_scores_zero_popularity(self):
        config = _make_set_config()
        card = {"released_at": "2020-01-01", "rarity": "rare"}
        score, _ = score_splashy_candidate(card, config, "2026-03-13")
        # Should still get age + rarity, but not popularity
        assert score > 0.0  # age + rarity contribute
        # But less than a card with good edhrec
        card_with_edhrec = {
            "edhrec_rank": 500,
            "released_at": "2020-01-01",
            "rarity": "rare",
        }
        score_with, _ = score_splashy_candidate(card_with_edhrec, config, "2026-03-13")
        assert score < score_with


# ---------------------------------------------------------------------------
# Tests: Staple selection end-to-end
# ---------------------------------------------------------------------------


class TestSelectStapleReprints:
    def test_basic_selection(self, skeleton_path: Path, set_config: dict):
        selections = select_staple_reprints(skeleton_path, set_config, count=2)
        assert len(selections) <= 2
        for pair in selections:
            assert isinstance(pair, SelectionPair)
            assert pair.candidate.score > 0

    def test_no_duplicate_candidates(self, skeleton_path: Path, set_config: dict):
        selections = select_staple_reprints(skeleton_path, set_config, count=5)
        names = [s.candidate.name for s in selections]
        assert len(names) == len(set(names)), "Duplicate candidate selected"

    def test_no_duplicate_slots(self, skeleton_path: Path, set_config: dict):
        selections = select_staple_reprints(skeleton_path, set_config, count=5)
        slot_ids = [s.slot.slot_id for s in selections]
        assert len(slot_ids) == len(set(slot_ids)), "Duplicate slot used"


# ---------------------------------------------------------------------------
# Tests: Main entry point
# ---------------------------------------------------------------------------


class TestSelectReprints:
    def test_entry_point_works(self, skeleton_path: Path, tmp_path: Path):
        # Create empty scryfall dir (no splashy candidates)
        scryfall_dir = tmp_path / "scryfall"
        scryfall_dir.mkdir()

        result = select_reprints(skeleton_path, scryfall_dir)
        assert result.set_code == "TST"
        assert result.set_size == 10
        assert result.target_reprint_count >= 1
        assert isinstance(result.staple_selections, list)
        assert isinstance(result.splashy_selections, list)
        assert result.selection_timestamp

    def test_custom_counts(self, skeleton_path: Path, tmp_path: Path):
        scryfall_dir = tmp_path / "scryfall"
        scryfall_dir.mkdir()

        result = select_reprints(
            skeleton_path,
            scryfall_dir,
            staple_count=1,
            splashy_count=0,
        )
        assert len(result.staple_selections) <= 1
        assert len(result.splashy_selections) == 0


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
            oracle_text=(
                "{T}, Sacrifice Evolving Wilds: Search your library for a"
                " basic land card, put it onto the battlefield tapped,"
                " then shuffle."
            ),
            colors=[],
            rarity="common",
        )
        card = convert_to_card(cand, "L-C-01", "ASD", "63")
        assert card.colors == []
        assert card.is_reprint is True
        assert card.mana_cost is None

    def test_design_notes_include_source(self):
        cand = _make_candidate(source="curated_pool", score=0.85)
        cand.score = 0.85
        card = convert_to_card(cand, "B-C-03", "ASD", "64")
        assert "curated_pool" in card.design_notes
        assert "0.850" in card.design_notes


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
        # flavor_description mentions artifact and dinosaurs
        assert "artifact" in config["themes"]

    def test_infers_creature_types(self, skeleton_path: Path):
        config = extract_set_config(skeleton_path)
        # flavor mentions dinosaurs
        assert "Dinosaur" in config["creature_types"]


# ---------------------------------------------------------------------------
# Tests: Setting-agnostic filter
# ---------------------------------------------------------------------------


class TestSettingAgnostic:
    def test_setting_agnostic_field_loaded(self):
        """Verify that setting_agnostic is read correctly from the real pool."""
        pool = load_reprint_pool()
        by_name = {c.name: c for c in pool}

        # Murder is flavor-neutral -> True
        assert by_name["Murder"].setting_agnostic is True
        # Llanowar Visionary has a setting-specific name -> False
        assert by_name["Llanowar Visionary"].setting_agnostic is False

    def test_staple_selection_filters_non_agnostic(self, skeleton_path: Path, tmp_path: Path):
        """A non-agnostic card that would otherwise score highest is excluded."""
        # Build a tiny curated pool where the non-agnostic card is strictly
        # better (lower cmc, better edhrec) than the agnostic one.
        pool_data = {
            "cards": [
                {
                    "name": "Llanowar Specific",
                    "mana_cost": "{1}{B}",
                    "cmc": 2,
                    "type_line": "Instant",
                    "oracle_text": "Destroy target creature.",
                    "colors": ["B"],
                    "rarity": "common",
                    "role": "removal_hard_kill",
                    "keywords": [],
                    "subtypes": [],
                    "edhrec_rank_approx": 100,
                    "tags": ["staple", "removal"],
                    "setting_agnostic": False,
                },
                {
                    "name": "Generic Kill",
                    "mana_cost": "{2}{B}",
                    "cmc": 3,
                    "type_line": "Instant",
                    "oracle_text": "Destroy target creature.",
                    "colors": ["B"],
                    "rarity": "common",
                    "role": "removal_hard_kill",
                    "keywords": [],
                    "subtypes": [],
                    "edhrec_rank_approx": 5000,
                    "tags": ["staple", "removal"],
                    "setting_agnostic": True,
                },
            ]
        }
        pool_path = tmp_path / "test_pool.json"
        pool_path.write_text(json.dumps(pool_data), encoding="utf-8")

        config = _make_set_config()
        selections = select_staple_reprints(skeleton_path, config, count=1, pool_path=pool_path)

        # The non-agnostic card should NOT appear
        selected_names = {s.candidate.name for s in selections}
        assert "Llanowar Specific" not in selected_names
        # The agnostic card should be selected instead (if it matched a slot)
        if selections:
            assert selections[0].candidate.name == "Generic Kill"


# ---------------------------------------------------------------------------
# Tests: LLM splashy filter
# ---------------------------------------------------------------------------


class TestLlmSplashyFilter:
    def test_llm_filter_skipped_when_disabled(self, tmp_path: Path):
        """With use_llm_filter=False, splashy selection returns without LLM call."""
        # Create a scryfall dir with cards that pass all filters
        scryfall_dir = tmp_path / "scryfall" / "set1"
        scryfall_dir.mkdir(parents=True)
        cards = [
            {
                "name": f"Splashy Card {i}",
                "mana_cost": "{3}{R}",
                "cmc": 4,
                "type_line": "Creature -- Dragon",
                "oracle_text": "Flying",
                "colors": ["R"],
                "rarity": "rare",
                "edhrec_rank": 1000,
                "released_at": "2020-01-01",
                "reprint": True,
                "layout": "normal",
                "set": "TST",
                "keywords": ["Flying"],
            }
            for i in range(3)
        ]
        (scryfall_dir / "cards.json").write_text(json.dumps(cards), encoding="utf-8")

        config = _make_set_config()
        # With LLM filter disabled, should NOT call generate_with_tool
        with patch("mtgai.generation.llm_client.generate_with_tool") as mock_llm:
            results = select_splashy_reprints(
                tmp_path / "scryfall",
                config,
                count=2,
                use_llm_filter=False,
            )
            mock_llm.assert_not_called()

        # Should still return results (up to count, deduplicated by name = 1)
        assert len(results) <= 2

    def test_llm_check_splashy_fit_graceful_failure(self):
        """If the API call raises, return candidates unchanged."""
        candidates = [
            _make_candidate(name="Card A", source="scryfall"),
            _make_candidate(name="Card B", source="scryfall"),
        ]
        config = _make_set_config()

        with patch(
            "mtgai.generation.llm_client.generate_with_tool",
            side_effect=RuntimeError("API down"),
        ):
            result = _llm_check_splashy_fit(candidates, config)

        assert len(result) == 2
        assert result[0].name == "Card A"
        assert result[1].name == "Card B"

    def test_llm_check_splashy_fit_filters_correctly(self):
        """Mock Haiku response: one card fits, one does not."""
        candidates = [
            _make_candidate(name="Ancient Golem", source="scryfall"),
            _make_candidate(name="Sylvan Elf Lord", source="scryfall"),
        ]
        config = _make_set_config(
            name="Anomalous Descent",
            theme="science-fantasy megadungeon",
            flavor_description="A post-apocalyptic megadungeon full of relics.",
        )

        mock_response = {
            "result": {
                "evaluations": [
                    {
                        "card_number": 1,
                        "fits": True,
                        "reason": "Golem fits artifact/relic theme",
                    },
                    {
                        "card_number": 2,
                        "fits": False,
                        "reason": "Sylvan Elf doesn't fit post-apocalyptic setting",
                    },
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
            result = _llm_check_splashy_fit(candidates, config)

        assert len(result) == 1
        assert result[0].name == "Ancient Golem"
