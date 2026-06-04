"""Unit tests for the TC-4 visual-reference extractor.

The LLM call (``generate_visual_references``) is exercised with a
monkeypatched ``generate_with_tool`` — no real model is ever loaded. The
no-network helpers (prompt assembly, flat-entity assembly, on-disk loader)
are covered directly, plus a round-trip asserting the produced file is
consumable by the existing art-pipeline readers.
"""

from __future__ import annotations

import json

import pytest

from mtgai.art import visual_reference_extractor as vre


def _theme_fixture() -> dict:
    return {
        "code": "TST",
        "name": "Test Set",
        "theme": "Medieval scavengers atop dead-god machinery.",
        "flavor_description": (
            "A crumbling concrete megastructure repurposed by a sword-and-sorcery "
            "society. Lion-headed raiders prowl the wastes; a dead wizard-king rules "
            "from a humming server-throne."
        ),
        "creature_types": {
            "setting_specific": ["Moktar", "Automaton"],
            "standard_mtg": ["Human", "Wizard"],
        },
        "special_constraints": [
            {"text": "Firearms are sculpted with ceremonial insignia."},
        ],
        "legendary_characters": [
            {
                "name": "Feretha, the Hollow Founder",
                "colors": ["U", "B"],
                "role": "Dead wizard-ruler hooked to a machine.",
                "type": "Legendary Creature — Human Wizard",
            },
        ],
    }


def _entities_fixture() -> list[dict]:
    return [
        {
            "category": "legendary_character",
            "key": "feretha",
            "name": "Feretha, the Hollow Founder",
            "visual_description": (
                "Feretha, the Hollow Founder: A dead wizard-ruler on a "
                "technological throne, hollow skull wired into a server rack."
            ),
        },
        {
            "category": "creature_type",
            "key": "moktar",
            "name": "Moktar",
            "visual_description": "Seven-foot lion-headed humanoids with tawny fur.",
            "flux_replacement": "tawny-furred lion-headed humanoid",
        },
        {
            "category": "faction",
            "key": "unyielding fist",
            "name": "The Unyielding Fist",
            "visual_description": "Shock troopers in chain mail with revolver pistols.",
        },
        {
            "category": "landmark",
            "key": "denethix",
            "name": "Denethix",
            "visual_description": "A medieval city built inside ancient megastructures.",
        },
    ]


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


def test_build_visual_reference_prompts_substitutes_fields() -> None:
    sys_prompt, user_prompt = vre.build_visual_reference_prompts(
        theme=_theme_fixture(),
        set_name="Dead Gods",
    )

    assert "Dead Gods" in sys_prompt
    assert "Medieval scavengers" in sys_prompt
    assert "crumbling concrete megastructure" in sys_prompt
    # Named characters thread into the characters block.
    assert "Feretha, the Hollow Founder" in sys_prompt
    # Only setting-specific creature types are surfaced, not standard MTG ones.
    assert "Moktar" in sys_prompt and "Automaton" in sys_prompt
    # Constraints are intentionally NOT threaded into this prompt — visual
    # refs care about appearance, not mechanical constraints.
    assert "ceremonial insignia" not in sys_prompt
    # User prompt is the static template.
    assert "visual_motifs" in user_prompt


def test_build_visual_reference_prompts_handles_missing_blocks() -> None:
    sys_prompt, _user = vre.build_visual_reference_prompts(
        theme={"theme": "Bare bones theme."},
        set_name="",
    )
    assert "Bare bones theme." in sys_prompt
    assert "(unnamed set)" in sys_prompt
    # Optional blocks fall back to placeholders, not KeyError.
    assert "no structured named characters" in sys_prompt
    assert "none called out" in sys_prompt


def test_build_visual_reference_prompts_surfaces_full_setting_prose() -> None:
    # The transform reads the rich ``setting`` markdown (the source the old
    # stage discarded), preferred over the legacy short ``flavor_description``.
    theme = {
        "theme": "One-liner.",
        "setting": "# Factions\n\nThe Iron Choir, masked monks in copper habits.",
        "flavor_description": "ignored when setting is present",
    }
    sys_prompt, _user = vre.build_visual_reference_prompts(theme=theme, set_name="X")
    assert "Iron Choir" in sys_prompt
    assert "ignored when setting is present" not in sys_prompt


def test_notable_cards_block_threads_anchors() -> None:
    theme = {
        "notable_cards": [
            {"name": "Fereyn's Stone Head", "type": "Legendary Artifact", "notes": "flying head"},
        ]
    }
    block = vre._format_notable_cards_block(theme)
    assert "Fereyn's Stone Head" in block and "flying head" in block


def test_creature_types_block_accepts_flat_list() -> None:
    block = vre._format_creature_types_block(["Moktar", "Screechman"])
    assert "Moktar" in block and "Screechman" in block


# ---------------------------------------------------------------------------
# Flat-entity -> nested-category assembly
# ---------------------------------------------------------------------------


def test_assemble_visual_references_groups_by_category() -> None:
    out = vre.assemble_visual_references(_entities_fixture(), ["rust and verdigris"])
    assert set(out["legendary_characters"]) == {"feretha"}
    assert set(out["creature_types"]) == {"moktar"}
    assert set(out["factions"]) == {"unyielding fist"}
    assert set(out["landmarks"]) == {"denethix"}
    assert out["visual_motifs"] == ["rust and verdigris"]
    # Every category key is always present (even if empty in another run).
    for key in ("legendary_characters", "creature_types", "factions", "landmarks"):
        assert key in out


def test_assemble_visual_references_builds_flux_replacements() -> None:
    out = vre.assemble_visual_references(_entities_fixture(), [])
    assert out["flux_term_replacements"] == {"moktar": "tawny-furred lion-headed humanoid"}


def test_assemble_visual_references_slugifies_and_dedupes() -> None:
    entities = [
        {
            "category": "creature_type",
            "key": "Moktar!",
            "name": "Moktar",
            "visual_description": "first wins",
        },
        {
            "category": "creature_type",
            "key": "moktar",
            "name": "Moktar dup",
            "visual_description": "second loses",
        },
    ]
    out = vre.assemble_visual_references(entities, [])
    assert out["creature_types"] == {"moktar": "first wins"}


def test_assemble_visual_references_drops_malformed() -> None:
    entities = [
        "not a dict",
        {"category": "creature_type", "key": "ok", "visual_description": "fine"},
        {"category": "bogus", "key": "x", "visual_description": "unknown category"},
        {"category": "faction", "key": "", "visual_description": "empty key"},
        {"category": "landmark", "key": "noempty", "visual_description": "  "},
        {"category": "legendary_character", "key": "nodesc", "name": "X"},
    ]
    out = vre.assemble_visual_references(entities, "not a list")
    assert out["creature_types"] == {"ok": "fine"}
    assert out["factions"] == {}
    assert out["landmarks"] == {}
    assert out["legendary_characters"] == {}
    assert out["visual_motifs"] == []
    assert out["flux_term_replacements"] == {}


# ---------------------------------------------------------------------------
# load_visual_references
# ---------------------------------------------------------------------------


def test_load_visual_references_returns_empty_when_missing(tmp_path) -> None:
    assert vre.load_visual_references(tmp_path) == {}


def test_load_visual_references_reads_dict(tmp_path) -> None:
    art_dir = tmp_path / "art-direction"
    art_dir.mkdir()
    data = {"creature_types": {"moktar": "lion-headed"}}
    (art_dir / "visual-references.json").write_text(json.dumps(data), encoding="utf-8")
    assert vre.load_visual_references(tmp_path) == data


# ---------------------------------------------------------------------------
# generate_visual_references contract (mocked LLM)
# ---------------------------------------------------------------------------


@pytest.fixture
def _project(isolated_output, monkeypatch) -> None:
    """Pin a minimal active project + write theme.json."""
    from mtgai.runtime import active_project
    from mtgai.settings import model_settings as ms

    asset = isolated_output / "sets" / "TST"
    asset.mkdir(parents=True, exist_ok=True)
    (asset / "theme.json").write_text(json.dumps(_theme_fixture()), encoding="utf-8")

    settings = ms.ModelSettings(
        asset_folder=str(asset),
        set_params=ms.SetParams(set_name="Dead Gods", set_size=120, mechanic_count=3),
    )
    active_project.write_active_project(
        active_project.ProjectState(set_code="TST", settings=settings)
    )


def _stub_generate_with_tool(entities, motifs):
    def stub(*args, **kwargs):
        return {
            "result": {"entities": entities, "visual_motifs": motifs},
            "input_tokens": 11,
            "output_tokens": 22,
        }

    return stub


def test_generate_visual_references_returns_assembled(_project, monkeypatch) -> None:
    monkeypatch.setattr(
        vre,
        "generate_with_tool",
        _stub_generate_with_tool(_entities_fixture(), ["rust and verdigris"]),
    )
    result = vre.generate_visual_references()
    refs = result["references"]
    assert set(refs["creature_types"]) == {"moktar"}
    assert refs["flux_term_replacements"]["moktar"] == "tawny-furred lion-headed humanoid"
    assert result["input_tokens"] == 11
    assert result["output_tokens"] == 22


def test_generate_visual_references_routes_log_dir(_project, monkeypatch) -> None:
    from mtgai.io.asset_paths import set_artifact_dir

    # The bespoke per-call logger is gone; instead llmfacade's JSONL+HTML
    # transcript is routed to the per-stage logs dir via ``log_dir``.
    inner = _stub_generate_with_tool(_entities_fixture(), [])
    captured: dict = {}

    def stub(*args, **kwargs):
        captured.update(kwargs)
        return inner(*args, **kwargs)

    monkeypatch.setattr(vre, "generate_with_tool", stub)
    vre.generate_visual_references()
    assert captured.get("log_dir") == set_artifact_dir() / "art-direction" / "logs"


def test_generate_visual_references_raises_when_empty(_project, monkeypatch) -> None:
    monkeypatch.setattr(
        vre,
        "generate_with_tool",
        _stub_generate_with_tool([], []),
    )
    with pytest.raises(RuntimeError, match="no usable entities"):
        vre.generate_visual_references()


# ---------------------------------------------------------------------------
# Downstream-consumer round-trip
# ---------------------------------------------------------------------------


def test_output_is_consumable_by_art_pipeline() -> None:
    """The assembled schema must satisfy the existing art-pipeline readers.

    ``art/visual_reference.py`` and ``art/character_portraits.py`` read the
    category dicts + ``flux_term_replacements`` produced here. We assert the
    shape directly (those readers index ``refs.get(category, {})`` and parse
    a ``"Name: desc"`` value) without loading any model or ComfyUI.
    """
    from mtgai.art.character_portraits import build_neutral_prompt

    refs = vre.assemble_visual_references(_entities_fixture(), ["rust and verdigris"])

    # visual_reference.py reads these as dict[str, str] keyed by lowercase slug.
    assert isinstance(refs["legendary_characters"], dict)
    assert isinstance(refs["flux_term_replacements"], dict)

    # character_portraits.build_neutral_prompt pulls a recurring entity's
    # appearance from legendary_characters + applies flux_term_replacements; it
    # must not raise and must surface Feretha's appearance prose.
    entity = {"entity_key": "feretha", "name": "Feretha", "kind": "character"}
    prompt = build_neutral_prompt(entity, refs)
    assert isinstance(prompt, str) and prompt
    # The dictionary's "Name: desc" value is split, so the prompt carries the
    # appearance prose, not the bare name.
    assert refs["legendary_characters"]["feretha"].split(":", 1)[1].strip()[:20] in prompt


# ---------------------------------------------------------------------------
# Artist directory
# ---------------------------------------------------------------------------


def test_target_artist_count_leans_fewer_and_clamps() -> None:
    # ~277-card set -> round(277/18)=15 artists (~18 cards each, >=10/artist).
    assert vre.target_artist_count(277) == 15
    # Tiny / zero sets floor at MIN_ARTISTS; huge sets cap at MAX_ARTISTS.
    assert vre.target_artist_count(10) == vre.MIN_ARTISTS
    assert vre.target_artist_count(0) == vre.MIN_ARTISTS
    assert vre.target_artist_count(10000) == vre.MAX_ARTISTS


def test_assemble_artists_cleans_and_dedupes() -> None:
    raw = [
        {"name": "Lira Vance", "style_prompt": "soft watercolor"},
        "not a dict",
        {"name": "", "style_prompt": "empty name"},
        {"name": "No Style"},
        {"name": "lira vance", "style_prompt": "dup by lowercase name"},
        {"name": "  Ronan Skye  ", "style_prompt": "  gritty ink  "},
    ]
    out = vre.assemble_artists(raw)
    assert out == [
        {"name": "Lira Vance", "style_prompt": "soft watercolor"},
        {"name": "Ronan Skye", "style_prompt": "gritty ink"},
    ]


def test_assemble_artists_handles_non_list() -> None:
    assert vre.assemble_artists(None) == []
    assert vre.assemble_artists("nope") == []


def test_load_artists_reads_and_defaults(tmp_path) -> None:
    assert vre.load_artists(tmp_path) == []
    art_dir = tmp_path / "art-direction"
    art_dir.mkdir()
    (art_dir / "artists.json").write_text(
        json.dumps({"artists": [{"name": "A", "style_prompt": "s"}, {"bad": 1}]}),
        encoding="utf-8",
    )
    assert vre.load_artists(tmp_path) == [{"name": "A", "style_prompt": "s"}]


def test_build_artist_directory_prompts_substitutes_count() -> None:
    sys_prompt, user_prompt = vre.build_artist_directory_prompts(
        theme=_theme_fixture(), set_name="Dead Gods", count=12
    )
    assert "Dead Gods" in sys_prompt
    assert "12 artists" in sys_prompt
    assert "12" in user_prompt


def test_generate_artists_returns_clean_list(_project, monkeypatch) -> None:
    def stub(*args, **kwargs):
        return {
            "result": {"artists": [{"name": "Lira Vance", "style_prompt": "watercolor"}]},
            "input_tokens": 5,
            "output_tokens": 9,
        }

    monkeypatch.setattr(vre, "generate_with_tool", stub)
    result = vre.generate_artists()
    assert result["artists"] == [{"name": "Lira Vance", "style_prompt": "watercolor"}]
    assert result["input_tokens"] == 5


def test_generate_artists_raises_when_empty(_project, monkeypatch) -> None:
    def stub(*args, **kwargs):
        return {"result": {"artists": []}, "input_tokens": 0, "output_tokens": 0}

    monkeypatch.setattr(vre, "generate_with_tool", stub)
    with pytest.raises(RuntimeError, match="no usable artists"):
        vre.generate_artists()


def test_generate_artists_count_override(_project, monkeypatch) -> None:
    captured: dict = {}

    def stub(*args, **kwargs):
        captured["system_prompt"] = kwargs.get("system_prompt", "")
        return {
            "result": {"artists": [{"name": "X", "style_prompt": "y"}]},
            "input_tokens": 0,
            "output_tokens": 0,
        }

    monkeypatch.setattr(vre, "generate_with_tool", stub)
    vre.generate_artists(count=11)
    assert "11 artists" in captured["system_prompt"]


# ---------------------------------------------------------------------------
# Set-wide art direction
# ---------------------------------------------------------------------------


def test_generate_set_art_direction_returns_prose(_project, monkeypatch) -> None:
    def stub(*args, **kwargs):
        return {
            "result": {"set_art_direction": "  Sickly contrast, runny paint.  "},
            "input_tokens": 3,
            "output_tokens": 4,
        }

    monkeypatch.setattr(vre, "generate_with_tool", stub)
    result = vre.generate_set_art_direction()
    assert result["set_art_direction"] == "Sickly contrast, runny paint."


def test_generate_set_art_direction_raises_when_empty(_project, monkeypatch) -> None:
    def stub(*args, **kwargs):
        return {"result": {"set_art_direction": "   "}, "input_tokens": 0, "output_tokens": 0}

    monkeypatch.setattr(vre, "generate_with_tool", stub)
    with pytest.raises(RuntimeError, match="no usable prose"):
        vre.generate_set_art_direction()
