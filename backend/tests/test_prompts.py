"""Unit tests for the TC-6 prompt-assembly migration to setting prose + archetypes.

Covers the pure prompt-building functions in ``mtgai.generation.prompts``:

* ``format_setting_prose`` — robust, any-setting consumption of theme.json prose
  (no hardcoded ASD structure, no required keys).
* ``format_slot_specs`` — archetype override (TC-3 ``archetypes.json``) vs.
  theme ``draft_archetypes`` fallback.
* ``build_user_prompt`` — regression: an ASD-shaped theme still produces the
  same set-flavor content, and the ``archetypes`` override threads through.

No LLM is ever loaded — every function here is pure string assembly.
"""

from __future__ import annotations

from mtgai.generation import prompts

# ---------------------------------------------------------------------------
# Fixtures (plain dicts — the prompt functions consume JSON-shaped dicts)
# ---------------------------------------------------------------------------


def _asd_theme() -> dict:
    """An ASD-shaped theme.json (structured keys the old code subscripted)."""
    return {
        "name": "Anomalous Descent",
        "code": "ASD",
        "theme": "Science-fantasy megadungeon in far-future post-apocalyptic Earth",
        "flavor_description": (
            "Thousands of years after civilization collapsed, the city of "
            "Denethix clings to order at the edge of a wilderness."
        ),
        "flavor_text_guidelines": {"tone": "Deadpan, darkly humorous."},
        "draft_archetypes": [
            {
                "color_pair": "WU",
                "name": "Theme Skies",
                "description": "from the theme file",
            }
        ],
    }


def _mechanics() -> list[dict]:
    return [
        {
            "name": "Salvage",
            "keyword_type": "keyword_action",
            "reminder_text": "(reminder)",
            "colors": ["W", "U", "G"],
            "complexity": 1,
            "rarity_range": ["common", "uncommon"],
            "design_notes": "Filter the top of your library.",
        }
    ]


def _wu_slot() -> dict:
    return {
        "slot_id": "001",
        "color": "multicolor",
        "rarity": "uncommon",
        "card_type": "creature",
        "cmc_target": 3,
        "mechanic_tag": "salvage",
        "color_pair": "WU",
    }


# ---------------------------------------------------------------------------
# format_setting_prose
# ---------------------------------------------------------------------------


def test_format_setting_prose_asd_shape() -> None:
    block = prompts.format_setting_prose(_asd_theme())
    assert "## Set: Anomalous Descent" in block
    assert "Theme: Science-fantasy megadungeon" in block
    assert "Denethix clings to order" in block
    assert "Flavor text tone: Deadpan, darkly humorous." in block


def test_format_setting_prose_accepts_setting_key() -> None:
    # A setting that uses the alternate "setting" key (not "theme").
    block = prompts.format_setting_prose(
        {
            "name": "Brass Sky",
            "setting": "Steampunk dragons in a clockwork sky.",
            "flavor_description": "Floating cities tethered by brass chains.",
        }
    )
    assert "## Set: Brass Sky" in block
    assert "Theme: Steampunk dragons in a clockwork sky." in block
    assert "Floating cities" in block


def test_format_setting_prose_tolerates_missing_fields() -> None:
    # No name, no tone, only the prose blob — must not KeyError.
    block = prompts.format_setting_prose(
        {"flavor_description": "Just some prose, no structured fields."}
    )
    assert "## Setting" in block  # falls back to a generic header
    assert "Just some prose" in block
    assert "Theme:" not in block
    assert "Flavor text tone:" not in block


def test_format_setting_prose_empty_when_no_prose() -> None:
    assert prompts.format_setting_prose({}) == ""
    assert prompts.format_setting_prose({"name": "Nameless", "draft_archetypes": []}) == ""


def test_format_setting_prose_tolerates_non_dict_guidelines() -> None:
    # flavor_text_guidelines could be malformed (a string) — don't crash.
    block = prompts.format_setting_prose(
        {"theme": "A theme", "flavor_text_guidelines": "oops a string"}
    )
    assert "Theme: A theme" in block
    assert "Flavor text tone:" not in block


# ---------------------------------------------------------------------------
# format_slot_specs — archetype override vs theme fallback
# ---------------------------------------------------------------------------


def test_format_slot_specs_uses_archetypes_override() -> None:
    archetypes = [
        {"color_pair": "WU", "name": "Override Skies", "description": "from archetypes.json"}
    ]
    spec = prompts.format_slot_specs([_wu_slot()], _asd_theme(), archetypes)
    assert "Override Skies: from archetypes.json" in spec
    # The theme's own draft_archetypes must NOT win when archetypes is provided.
    assert "from the theme file" not in spec


def test_format_slot_specs_falls_back_to_theme_when_archetypes_none() -> None:
    spec = prompts.format_slot_specs([_wu_slot()], _asd_theme(), None)
    assert "Theme Skies: from the theme file" in spec


def test_format_slot_specs_empty_list_overrides_theme() -> None:
    # An explicit empty list is "no archetypes", distinct from None — it must
    # suppress the theme fallback (this is why callers pass `load_archetypes() or None`).
    spec = prompts.format_slot_specs([_wu_slot()], _asd_theme(), [])
    assert "from the theme file" not in spec
    assert "Archetype —" not in spec


def test_format_slot_specs_monocolor_archetype_tags() -> None:
    slot = {
        "slot_id": "010",
        "color": "W",
        "rarity": "common",
        "card_type": "creature",
        "cmc_target": 2,
        "mechanic_tag": "evergreen",
        "archetype_tags": ["WU"],
    }
    archetypes = [{"color_pair": "WU", "name": "Skies", "description": "go wide in the air"}]
    spec = prompts.format_slot_specs([slot], None, archetypes)
    assert "Supports archetypes: Skies: go wide in the air" in spec


# ---------------------------------------------------------------------------
# build_user_prompt — regression + override threading
# ---------------------------------------------------------------------------


def test_build_user_prompt_asd_regression() -> None:
    prompt = prompts.build_user_prompt(
        [_wu_slot()],
        _mechanics(),
        existing_cards=[],
        theme=_asd_theme(),
    )
    # Set-flavor section survives the migration.
    assert "## Set: Anomalous Descent" in prompt
    assert "Theme: Science-fantasy megadungeon" in prompt
    assert "Denethix clings to order" in prompt
    assert "Flavor text tone: Deadpan, darkly humorous." in prompt
    # Mechanics + preventive guidance + slot spec all present.
    assert "Custom Mechanics for This Set" in prompt
    assert "Salvage" in prompt
    assert "Preventive Design Checklist" in prompt
    assert "Generate exactly 1 card(s)" in prompt
    # With no override, the theme's own archetype annotates the WU slot.
    assert "Theme Skies: from the theme file" in prompt


def test_build_user_prompt_archetypes_override_threads_through() -> None:
    archetypes = [
        {"color_pair": "WU", "name": "Override Skies", "description": "from archetypes.json"}
    ]
    prompt = prompts.build_user_prompt(
        [_wu_slot()],
        _mechanics(),
        existing_cards=[],
        theme=_asd_theme(),
        archetypes=archetypes,
    )
    assert "Override Skies: from archetypes.json" in prompt
    assert "from the theme file" not in prompt


def test_build_user_prompt_no_theme_omits_flavor() -> None:
    # No theme at all — must not crash, just no set-flavor section.
    prompt = prompts.build_user_prompt([_wu_slot()], _mechanics(), existing_cards=[], theme=None)
    assert "## Set:" not in prompt
    assert "## Setting" not in prompt
    assert "Generate exactly 1 card(s)" in prompt


def test_build_user_prompt_proseless_theme_omits_flavor() -> None:
    # A truthy-but-prose-less theme (only metadata, no theme/flavor) must
    # still skip the flavor section — exercises the `if prose_block:` guard.
    prompt = prompts.build_user_prompt(
        [_wu_slot()],
        _mechanics(),
        existing_cards=[],
        theme={"name": "Nameless", "code": "NUL"},
    )
    assert "## Set:" not in prompt
    assert "## Setting" not in prompt
    assert "Generate exactly 1 card(s)" in prompt
