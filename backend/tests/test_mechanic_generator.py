"""Unit tests for the TC-2 mechanic-generator pure functions.

The LLM round-trip (``generate_mechanic_candidates``) is exercised by the
endpoint tests in ``test_pipeline/test_wizard_mechanics.py`` with a
monkeypatched ``generate_with_tool``. This module covers the helpers
that don't touch the network: prompt assembly, schema projection,
collision detection, and template loaders.
"""

from __future__ import annotations

import pytest

from mtgai.generation import mechanic_generator as mg


def _theme_fixture() -> dict:
    return {
        "code": "TST",
        "name": "Test Set",
        "theme": "Steampunk dragons in a clockwork sky.",
        "flavor_description": (
            "Floating cities tethered by brass chains. Dragons roost in steeple-spires "
            "and are courted by tinker-knights. Beneath the cloud line lies the wreck "
            "of an older world."
        ),
        "draft_archetypes": [
            {"color_pair": "WU", "name": "Aether Knights", "description": "skies-matter tempo"},
            {"color_pair": "BR", "name": "Boilerworks", "description": "discard + fling aggro"},
        ],
        "creature_types": ["Dragon", "Tinker-Knight", "Squire"],
        "constraints": [
            {"text": "At least 6 artifact creatures."},
            {"text": "No graveyard recursion."},
        ],
        "legendary_characters": [
            {"name": "Yenna of Ten Spires"},
            {"name": "Maglith the Boilermaker"},
        ],
        "notable_cards": [{"name": "Yenna's Boilerplate"}],
    }


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


def test_build_mechanic_prompts_substitutes_theme_fields() -> None:
    theme = _theme_fixture()
    sys_prompt, user_prompt = mg.build_mechanic_prompts(
        theme=theme,
        set_name="Brass Sky",
        set_size=120,
        mechanic_count=3,
    )

    assert "Brass Sky" in sys_prompt
    assert "Steampunk dragons" in sys_prompt
    assert "Floating cities" in sys_prompt
    assert "Aether Knights" in sys_prompt and "Boilerworks" in sys_prompt
    assert "Dragon" in sys_prompt and "Tinker-Knight" in sys_prompt
    assert "At least 6 artifact creatures" in sys_prompt
    assert "Yenna of Ten Spires" in sys_prompt
    assert "Maglith the Boilermaker" in sys_prompt
    # Mechanic count threads through.
    assert "3" in sys_prompt
    assert "3" in user_prompt
    # Excluded keywords block surfaces real printed keywords.
    assert "investigate" in sys_prompt.lower()


def test_build_mechanic_prompts_handles_missing_optional_blocks() -> None:
    sys_prompt, _user_prompt = mg.build_mechanic_prompts(
        theme={"theme": "Bare bones theme."},
        set_name="",
        set_size=60,
        mechanic_count=2,
    )

    assert "Bare bones theme." in sys_prompt
    # Empty set_name still renders something rather than KeyError.
    assert "(unnamed set)" in sys_prompt or "set_name" not in sys_prompt
    # Optional blocks fall back to placeholder strings, not KeyError.
    assert "no archetypes specified" in sys_prompt
    assert "no specific creature types" in sys_prompt
    assert "no special constraints" in sys_prompt


def test_expected_mechanic_density_lands_in_prompts() -> None:
    """Density math threads into both prompts as a min-max range string."""
    # 60 cards / (3 * 2) = 10 → "10-20"
    sys_p, user_p = mg.build_mechanic_prompts(
        theme={"theme": "x"}, set_name="X", set_size=60, mechanic_count=3
    )
    assert "10-20" in sys_p and "10-20" in user_p

    # 120 cards / (4 * 2) = 15 → "15-30"
    sys_p, user_p = mg.build_mechanic_prompts(
        theme={"theme": "x"}, set_name="X", set_size=120, mechanic_count=4
    )
    assert "15-30" in sys_p and "15-30" in user_p

    # Zero mechanic_count falls back to a default range — divide-by-zero
    # would otherwise crash the user prompt template.
    sys_p, user_p = mg.build_mechanic_prompts(
        theme={"theme": "x"}, set_name="X", set_size=60, mechanic_count=0
    )
    assert "6-10" in sys_p and "6-10" in user_p


# ---------------------------------------------------------------------------
# Sidecar template loaders
# ---------------------------------------------------------------------------


def test_load_evergreen_defaults_has_all_five_colors() -> None:
    defaults = mg.load_evergreen_defaults()
    assert set(defaults) == {"W", "U", "B", "R", "G"}
    for color, kws in defaults.items():
        assert isinstance(kws, list) and kws, f"{color} should have at least one keyword"


def test_load_pointed_questions_template_has_canonical_set() -> None:
    qs = mg.load_pointed_questions_template()
    # Every entry has the four expected fields.
    for q in qs:
        assert "id" in q and "question" in q and "category" in q and "source" in q
    # The two questions that should carry the placeholder.
    by_id = {q["id"]: q for q in qs}
    assert "{mechanic_names}" in by_id["reminder_text"]["question"]
    assert "{mechanic_names}" in by_id["keyword_collision"]["question"]


def test_render_pointed_questions_substitutes_mechanic_names() -> None:
    approved = [
        {"name": "Salvage"},
        {"name": "Malfunction"},
        {"name": "Overclock"},
    ]
    rendered = mg.render_pointed_questions(approved)
    by_id = {q["id"]: q for q in rendered}
    rendered_text = by_id["reminder_text"]["question"]
    collision_text = by_id["keyword_collision"]["question"]
    assert "Salvage, Malfunction, Overclock" in rendered_text
    assert "{mechanic_names}" not in rendered_text
    assert "Salvage, Malfunction, Overclock" in collision_text
    assert "{mechanic_names}" not in collision_text
    # Non-placeholder questions pass through untouched.
    assert by_id["keyword_nonbo"]["question"].startswith("Does this card")


def test_known_keyword_set_is_lowercase_and_includes_evergreens() -> None:
    kws = mg.known_keyword_set()
    assert "flying" in kws and "vigilance" in kws and "deathtouch" in kws
    assert "scavenge" in kws and "overload" in kws  # ASD's ground-truth collisions.
    # Lowercased, no leading/trailing whitespace.
    for k in kws:
        assert k == k.strip().lower()


# ---------------------------------------------------------------------------
# candidate_to_approved projection
# ---------------------------------------------------------------------------


def test_candidate_to_approved_renames_design_rationale_and_drops_examples() -> None:
    candidate = {
        "name": "Test",
        "keyword_type": "keyword_ability",
        "reminder_text": "(test)",
        "colors": ["W"],
        "complexity": 1,
        "flavor_connection": "fits the world",
        "design_rationale": "rationale goes here",
        "common_patterns": ["pattern A"],
        "uncommon_patterns": [],
        "rare_patterns": [],
        "example_cards": [{"name": "Example"}],
        "distribution": {"common": 3, "uncommon": 2, "rare": 1, "mythic": 0},
    }
    approved = mg.candidate_to_approved(candidate)
    assert approved["design_notes"] == "rationale goes here"
    assert "design_rationale" not in approved
    assert "example_cards" not in approved
    # rarity_range derives from non-zero distribution rarities.
    assert approved["rarity_range"] == ["common", "uncommon", "rare"]
    # Distribution survives.
    assert approved["distribution"]["common"] == 3


def test_candidate_to_approved_falls_back_when_distribution_is_empty() -> None:
    candidate = {
        "name": "Test",
        "complexity": 3,
        "design_rationale": "x",
    }
    approved = mg.candidate_to_approved(candidate)
    # Complexity 3 → no common (rare+ only).
    assert approved["rarity_range"] == ["uncommon", "rare", "mythic"]


# ---------------------------------------------------------------------------
# Collision detection
# ---------------------------------------------------------------------------


def test_detect_keyword_collisions_flags_printed_keywords() -> None:
    candidates = [
        {"name": "Salvage"},  # custom — ok
        {"name": "Scavenge"},  # printed — flag
        {"name": "Flying"},  # evergreen — flag
        {"name": ""},  # no name — skip
    ]
    collisions = mg.detect_keyword_collisions(candidates)
    assert collisions == {1: "Scavenge", 2: "Flying"}


def test_detect_keyword_collisions_is_case_insensitive() -> None:
    collisions = mg.detect_keyword_collisions([{"name": "scavenge"}])
    assert collisions == {0: "scavenge"}


# ---------------------------------------------------------------------------
# generate_mechanic_candidates contract: count enforcement
# ---------------------------------------------------------------------------


@pytest.fixture
def _project(isolated_output, monkeypatch) -> None:
    """Pin a minimal active project + write a theme.json under its asset folder."""
    import json

    from mtgai.runtime import active_project
    from mtgai.settings import model_settings as ms

    asset = isolated_output / "sets" / "TST"
    asset.mkdir(parents=True, exist_ok=True)
    (asset / "theme.json").write_text(
        json.dumps(_theme_fixture(), indent=2),
        encoding="utf-8",
    )

    settings = ms.ModelSettings(
        asset_folder=str(asset),
        set_params=ms.SetParams(set_name="Brass Sky", set_size=120, mechanic_count=3),
    )
    active_project.write_active_project(
        active_project.ProjectState(set_code="TST", settings=settings)
    )


def _stub_generate_with_tool(count: int):
    def stub(*args, **kwargs):
        mechanics = [
            {
                "name": f"Mechanic{i}",
                "keyword_type": "keyword_ability",
                "reminder_text": "(...)",
                "colors": ["W"],
                "complexity": 1,
                "flavor_connection": "fits",
                "design_rationale": "good",
                "common_patterns": ["x"],
                "uncommon_patterns": [],
                "rare_patterns": [],
                "example_cards": [],
                "distribution": {"common": 1, "uncommon": 0, "rare": 0, "mythic": 0},
            }
            for i in range(count)
        ]
        return {
            "result": {"mechanics": mechanics},
            "input_tokens": 10,
            "output_tokens": 20,
        }

    return stub


def test_generate_mechanic_candidates_returns_capped_six(_project, monkeypatch) -> None:
    monkeypatch.setattr(mg, "generate_with_tool", _stub_generate_with_tool(8))
    result = mg.generate_mechanic_candidates()
    assert len(result["mechanics"]) == 6
    assert result["input_tokens"] == 10
    assert result["output_tokens"] == 20


def test_generate_mechanic_candidates_raises_when_undercounted(_project, monkeypatch) -> None:
    monkeypatch.setattr(mg, "generate_with_tool", _stub_generate_with_tool(3))
    with pytest.raises(RuntimeError, match="3 candidates"):
        mg.generate_mechanic_candidates()
