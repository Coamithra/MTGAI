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


def test_format_setting_prose_real_pipeline_shape() -> None:
    # The shape _persist_extraction_to_theme_json actually writes: the full
    # world document lives in "setting", with no "theme" one-liner and no
    # "flavor_description". The prose must render as the body — NOT be
    # crammed into the one-line "Theme:" premise slot.
    block = prompts.format_setting_prose(
        {
            "code": "TRN",
            "name": "Transformers",
            "setting": (
                "# World Overview\n\n"
                "Cybertron is a metal world of sentient machines.\n\n"
                "Two factions war over the AllSpark."
            ),
            "constraints": [{"text": "No humans", "source": "ai"}],
            "card_requests": [{"text": "Optimus Prime", "source": "ai"}],
        }
    )
    assert "## Set: Transformers" in block
    assert "Cybertron is a metal world of sentient machines." in block
    assert "Two factions war over the AllSpark." in block
    # The multi-paragraph prose must not be mislabeled as a one-liner.
    assert "Theme:" not in block


def test_format_setting_prose_flavor_description_preferred_over_setting() -> None:
    # When both are present, flavor_description is the prose body and the bare
    # "setting" is not duplicated; only an explicit "theme" becomes the one-liner.
    block = prompts.format_setting_prose(
        {
            "name": "Brass Sky",
            "theme": "Steampunk dragons in a clockwork sky.",
            "setting": "Long-form setting text that should be superseded.",
            "flavor_description": "Floating cities tethered by brass chains.",
        }
    )
    assert "## Set: Brass Sky" in block
    assert "Theme: Steampunk dragons in a clockwork sky." in block
    assert "Floating cities tethered by brass chains." in block
    assert "should be superseded" not in block


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


def test_format_slot_specs_surfaces_reserved_card() -> None:
    # A reserved slot (from theme.json card_requests) must reach the card-gen
    # prompt so the LLM designs the requested card on that slot.
    slot = {**_wu_slot(), "reserved_card": "Feretha, the Undying — dead wizard-ruler"}
    spec = prompts.format_slot_specs([slot], None, None)
    assert "REQUESTED CARD — design this slot as: Feretha, the Undying — dead wizard-ruler" in spec


def test_format_slot_specs_no_reserved_marker_when_absent() -> None:
    spec = prompts.format_slot_specs([_wu_slot()], None, None)
    assert "REQUESTED CARD" not in spec


def test_format_slot_specs_surfaces_signpost_with_archetype_intent() -> None:
    # A slot flagged signpost_for must tell card-gen to design the gold
    # uncommon for that pair, threading the archetype's intent.
    slot = {**_wu_slot(), "signpost_for": "WU"}
    archetypes = [{"color_pair": "WU", "name": "Sky Patrol", "description": "win in the air"}]
    spec = prompts.format_slot_specs([slot], None, archetypes)
    assert "SIGNPOST UNCOMMON for the WU archetype" in spec
    assert "Sky Patrol: win in the air" in spec


def test_format_slot_specs_signpost_without_archetype_still_flags() -> None:
    # No archetype entry for the pair: still flag the slot as the signpost,
    # just without the intent suffix (card-gen designs a fitting gold uncommon).
    slot = {**_wu_slot(), "signpost_for": "WU"}
    spec = prompts.format_slot_specs([slot], None, [])
    assert "SIGNPOST UNCOMMON for the WU archetype" in spec


def test_format_slot_specs_no_signpost_marker_when_absent() -> None:
    spec = prompts.format_slot_specs([_wu_slot()], None, None)
    assert "SIGNPOST UNCOMMON" not in spec


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


# ---------------------------------------------------------------------------
# format_set_context — existing-card summaries (P/T for creatures)
# ---------------------------------------------------------------------------


def test_format_set_context_includes_pt_for_creatures() -> None:
    cards = [
        {
            "name": "Brass Sentinel",
            "mana_cost": "{2}{W}",
            "type_line": "Creature — Construct",
            "oracle_text": "Vigilance",
            "colors": ["W"],
            "power": "2",
            "toughness": "4",
        },
        {
            "name": "Precision Strike",
            "mana_cost": "{1}{W}{W}",
            "type_line": "Instant",
            "oracle_text": "Exile target creature.",
            "colors": ["W"],
        },
    ]
    ctx = prompts.format_set_context(cards)
    assert "Creature — Construct 2/4 —" in ctx  # P/T shown for the creature
    assert "Instant — Exile" in ctx  # no P/T for the noncreature
    assert "2/4" not in ctx.split("Precision Strike")[1]  # ...and not bleeding onto it


def test_format_set_context_handles_star_power_toughness() -> None:
    cards = [
        {
            "name": "Star Saber",
            "mana_cost": "{X}{R}",
            "type_line": "Creature — Transformer",
            "oracle_text": "Haste",
            "colors": ["R"],
            "power": "*",
            "toughness": "*",
        },
    ]
    assert "Creature — Transformer */* —" in prompts.format_set_context(cards)


# ---------------------------------------------------------------------------
# format_preventive_guidance — set-agnostic, derived from the set's mechanics
# ---------------------------------------------------------------------------


def test_preventive_guidance_names_the_sets_mechanics() -> None:
    guidance = prompts.format_preventive_guidance(_mechanics())  # one mechanic: Salvage
    assert "Preventive Design Checklist" in guidance
    assert "Salvage" in guidance  # derived from approved.json, not hardcoded
    # The old static block hardcoded ASD mechanics — none of those may leak in.
    assert "Malfunction" not in guidance
    assert "Overclock" not in guidance
    assert "Scavenge" not in guidance


def test_preventive_guidance_handles_no_mechanics() -> None:
    guidance = prompts.format_preventive_guidance([])
    assert "Preventive Design Checklist" in guidance
    assert "none" in guidance.lower()  # graceful when the set has no custom keywords


# ---------------------------------------------------------------------------
# Context injection — all mechanics included; archetypes surfaced as a section
# ---------------------------------------------------------------------------


def test_build_user_prompt_includes_off_color_mechanics() -> None:
    # A Black/Red mechanic must still appear in an all-White batch — the color
    # filter that used to drop it (the "Seize Control" bug) is gone.
    mechanics = [
        {
            "name": "Seize Control",
            "keyword_type": "keyword",
            "reminder_text": "(reminder)",
            "colors": ["B", "R"],
            "complexity": 2,
            "rarity_range": ["rare"],
            "design_notes": "Take control of target permanent.",
        }
    ]
    white_slot = {
        "slot_id": "001",
        "color": "W",
        "rarity": "common",
        "card_type": "creature",
        "cmc_target": 2,
        "mechanic_tag": "evergreen",
    }
    prompt = prompts.build_user_prompt([white_slot], mechanics, existing_cards=[], theme=None)
    # design_notes only appears in the mechanic block, so this proves the block
    # (not just the preventive-guidance name list) included the off-color mechanic.
    assert "Take control of target permanent." in prompt


def test_build_user_prompt_has_archetypes_section() -> None:
    archetypes = [
        {"color_pair": "WU", "name": "Sky Patrol", "description": "win in the air"},
        {"color_pair": "BR", "name": "Aggro Sac", "description": "throw bodies at them"},
    ]
    prompt = prompts.build_user_prompt(
        [_wu_slot()], _mechanics(), existing_cards=[], theme=None, archetypes=archetypes
    )
    assert "## Draft Archetypes" in prompt
    assert "WU — Sky Patrol: win in the air" in prompt
    assert "BR — Aggro Sac: throw bodies at them" in prompt


def test_format_archetypes_section_empty_when_none() -> None:
    assert prompts.format_archetypes_section(None, None) == ""
    assert prompts.format_archetypes_section([], None) == ""


def test_format_slot_specs_tweaked_gold_gets_archetype() -> None:
    # Relabeled (tweaked_text) gold slot must point at its archetype — the gap
    # where the tweaked path only annotated signpost slots.
    slot = {
        "slot_id": "001",
        "color": "multicolor",
        "color_pair": "WU",
        "rarity": "uncommon",
        "card_type": "creature",
        "cmc_target": 3,
        "tweaked_text": "White-Blue flier that draws a card when it attacks",
    }
    archetypes = [{"color_pair": "WU", "name": "Sky Patrol", "description": "win in the air"}]
    spec = prompts.format_slot_specs([slot], None, archetypes)
    assert "White-Blue flier" in spec  # tweaked descriptor emitted verbatim
    assert "Archetype — Sky Patrol: win in the air" in spec


def test_format_slot_specs_tweaked_signpost_not_double_annotated() -> None:
    # A signpost gold slot states its archetype via the SIGNPOST line and must
    # NOT also get the generic "Archetype —" pointer.
    slot = {
        "slot_id": "001",
        "color": "multicolor",
        "color_pair": "WU",
        "rarity": "uncommon",
        "card_type": "creature",
        "cmc_target": 3,
        "signpost_for": "WU",
        "tweaked_text": "The WU signpost uncommon",
    }
    archetypes = [{"color_pair": "WU", "name": "Sky Patrol", "description": "win in the air"}]
    spec = prompts.format_slot_specs([slot], None, archetypes)
    assert "SIGNPOST UNCOMMON for the WU archetype" in spec
    assert spec.count("Sky Patrol") == 1  # only via the signpost line
