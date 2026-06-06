"""Unit tests for the TC-3 archetype-generator pure functions + mocked round-trip.

The LLM call (``generate_archetypes``) is exercised here with a
monkeypatched ``generate_with_tool`` — no real model is ever loaded. The
no-network helpers (prompt assembly, color-pair normalization, dedupe)
are covered directly.
"""

from __future__ import annotations

import json

import pytest

from mtgai.generation import archetype_generator as ag


def _theme_fixture() -> dict:
    return {
        "code": "TST",
        "name": "Test Set",
        "theme": "Steampunk dragons in a clockwork sky.",
        "flavor_description": (
            "Floating cities tethered by brass chains. Dragons roost in steeple-spires "
            "and are courted by tinker-knights."
        ),
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


def _approved_fixture() -> list[dict]:
    return [
        {
            "name": "Salvage",
            "colors": ["W", "U", "G"],
            "complexity": 1,
            "reminder_text": "(Exile the top two cards; you may play artifacts from among them.)",
            "design_notes": "Filter the top of your library for artifacts.",
        },
        {
            "name": "Malfunction",
            "colors": ["W", "U", "R"],
            "complexity": 2,
            "reminder_text": "(This enters with two stun counters; remove one each upkeep.)",
            "design_notes": "Enters tapped with counters that tick down.",
        },
    ]


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


def test_build_archetype_prompts_substitutes_fields() -> None:
    sys_prompt, user_prompt = ag.build_archetype_prompts(
        theme=_theme_fixture(),
        approved=_approved_fixture(),
        set_name="Brass Sky",
        set_size=120,
    )

    assert "Brass Sky" in sys_prompt
    assert "Steampunk dragons" in sys_prompt
    assert "Floating cities" in sys_prompt
    # Approved-mechanic names + their oracle (reminder) text thread into the
    # mechanics block; the fluffy design_notes do NOT.
    assert "Salvage" in sys_prompt and "Malfunction" in sys_prompt
    assert "you may play artifacts from among them" in sys_prompt
    assert "Filter the top of your library" not in sys_prompt
    # Setting constraints thread through.
    assert "At least 6 artifact creatures" in sys_prompt
    # The ten color pairs are listed.
    for pair in ag.COLOR_PAIRS:
        assert pair in sys_prompt
    # Set size threads into the system prompt (the default user prompt no
    # longer references it).
    assert "120" in sys_prompt
    assert user_prompt  # user prompt still renders (no set_size placeholder now)


def test_build_archetype_prompts_handles_missing_blocks() -> None:
    sys_prompt, _user_prompt = ag.build_archetype_prompts(
        theme={"theme": "Bare bones theme."},
        approved=[],
        set_name="",
        set_size=60,
    )

    assert "Bare bones theme." in sys_prompt
    assert "(unnamed set)" in sys_prompt
    # Optional blocks fall back to placeholders, not KeyError.
    assert "no approved mechanics" in sys_prompt
    assert "no special constraints" in sys_prompt


# ---------------------------------------------------------------------------
# Color-pair normalization
# ---------------------------------------------------------------------------


def test_normalize_color_pair_reorders_to_wubrg() -> None:
    assert ag.normalize_color_pair("UW") == "WU"
    assert ag.normalize_color_pair("wu") == "WU"
    assert ag.normalize_color_pair("WU") == "WU"
    assert ag.normalize_color_pair("rg") == "RG"
    assert ag.normalize_color_pair("GR") == "RG"
    assert ag.normalize_color_pair("bU") == "UB"


def test_normalize_color_pair_rejects_invalid() -> None:
    assert ag.normalize_color_pair("WW") is None  # mono / duplicate
    assert ag.normalize_color_pair("X") is None
    assert ag.normalize_color_pair("WUB") is None  # three colors
    assert ag.normalize_color_pair("") is None
    assert ag.normalize_color_pair(None) is None
    assert ag.normalize_color_pair(42) is None


# ---------------------------------------------------------------------------
# Dedupe + ordering
# ---------------------------------------------------------------------------


def test_dedupe_and_complete_keeps_one_per_pair_in_order() -> None:
    raw = [
        {"color_pair": "RG", "name": "Late"},
        {"color_pair": "UW", "name": "First WU (unordered code)"},
        {"color_pair": "WU", "name": "Duplicate WU"},  # collapses
        {"color_pair": "WW", "name": "Invalid"},  # dropped
        "not a dict",  # dropped
        {"color_pair": "BG", "name": "Golgari"},
    ]
    out = ag.dedupe_and_complete(raw)
    pairs = [a["color_pair"] for a in out]
    # Canonical WUBRG ordering, deduped, invalid dropped.
    assert pairs == ["WU", "BG", "RG"]
    # The "UW" entry won the WU slot (first seen) and was normalized.
    wu = next(a for a in out if a["color_pair"] == "WU")
    assert wu["name"] == "First WU (unordered code)"


def test_sanitize_archetype_name_passes_clean_name() -> None:
    assert ag.sanitize_archetype_name("Sky Wardens", "WU") == "Sky Wardens"
    # A name with ordinary punctuation (apostrophe, comma, hyphen, ampersand)
    # survives — only markup/JSON characters are rejected.
    assert ag.sanitize_archetype_name("Yenna's Aether-Brigade & Co", "WU") == (
        "Yenna's Aether-Brigade & Co"
    )


def test_sanitize_archetype_name_rejects_blob_from_card() -> None:
    # The exact failure from card 6a23fa75: the UG name absorbed a chat special
    # token, JSON punctuation, and the start of the next entry's content.
    blob = "'Predacon' Ambush<|\"|>],[color_pair': 'RG', 'description': \"Win by ..."
    out = ag.sanitize_archetype_name(blob, "UG")
    assert out == "Blue-Green"  # clean derived label for the UG pair
    # The garbage is gone.
    assert "color_pair" not in out
    assert "<|" not in out and "],[" not in out


def test_sanitize_archetype_name_rejects_markup_chars() -> None:
    for bad in ("Name {with brace", "Name [bracket", "Name <tag>", "Name |pipe"):
        assert ag.sanitize_archetype_name(bad, "WB") == "White-Black"


def test_sanitize_archetype_name_rejects_overlong() -> None:
    overlong = "A" * (ag._MAX_NAME_LEN + 1)
    assert ag.sanitize_archetype_name(overlong, "RG") == "Red-Green"
    # Right at the cap is fine.
    at_cap = "B" * ag._MAX_NAME_LEN
    assert ag.sanitize_archetype_name(at_cap, "RG") == at_cap


def test_sanitize_archetype_name_handles_empty_and_non_string() -> None:
    assert ag.sanitize_archetype_name("", "UG") == "Blue-Green"
    assert ag.sanitize_archetype_name("   ", "UG") == "Blue-Green"
    assert ag.sanitize_archetype_name(None, "UG") == "Blue-Green"
    assert ag.sanitize_archetype_name(42, "UG") == "Blue-Green"


def test_sanitize_archetype_name_unknown_pair_falls_back_to_unnamed() -> None:
    # A bad/unknown pair has no clean derived label, so degrade to "(unnamed)".
    assert ag.sanitize_archetype_name("bad{name", "ZZ") == "(unnamed)"


def test_dedupe_and_complete_sanitizes_leaked_name() -> None:
    # The card's bug end-to-end: a malformed local-model payload where the UG
    # entry's name absorbed the next entry. dedupe_and_complete must persist a
    # clean derived name, not the raw blob.
    raw = [
        {"color_pair": "WU", "name": "Sky Wardens", "description": "win in the air"},
        {
            "color_pair": "UG",
            "name": "'Predacon' Ambush<|\"|>],[color_pair': 'RG', 'description': \"Win by ...",
            "description": "ramp into giant threats",
        },
    ]
    out = ag.dedupe_and_complete(raw)
    by_pair = {a["color_pair"]: a for a in out}
    assert by_pair["WU"]["name"] == "Sky Wardens"  # clean name untouched
    assert by_pair["UG"]["name"] == "Blue-Green"  # blob rejected -> derived label
    # The description (a free-text field, not sanitized as a label) is preserved.
    assert by_pair["UG"]["description"] == "ramp into giant threats"


def test_dedupe_and_complete_drops_stray_keys() -> None:
    # A model (especially a local one) can emit extra fields the slimmed
    # schema doesn't define; dedupe projects to exactly color_pair/name/
    # description so the on-disk archetype is strictly name + intent.
    raw = [
        {
            "color_pair": "WU",
            "name": "Skies",
            "description": "win in the air",
            "speed": "tempo",
            "signpost_uncommon": "Some Bird",
            "signpost_uncommon_description": "a 2/2 flier",
            "primary_mechanics": ["Salvage"],
        }
    ]
    out = ag.dedupe_and_complete(raw)
    assert out == [{"color_pair": "WU", "name": "Skies", "description": "win in the air"}]


# ---------------------------------------------------------------------------
# load_archetypes
# ---------------------------------------------------------------------------


def test_load_archetypes_returns_empty_when_missing(tmp_path) -> None:
    assert ag.load_archetypes(tmp_path) == []


def test_load_archetypes_reads_list(tmp_path) -> None:
    data = [{"color_pair": "WU", "name": "Skies"}]
    (tmp_path / "archetypes.json").write_text(json.dumps(data), encoding="utf-8")
    assert ag.load_archetypes(tmp_path) == data


# ---------------------------------------------------------------------------
# generate_archetypes contract (mocked LLM)
# ---------------------------------------------------------------------------


@pytest.fixture
def _project(isolated_output, monkeypatch) -> None:
    """Pin a minimal active project + write theme.json and approved.json."""
    from mtgai.runtime import active_project
    from mtgai.settings import model_settings as ms

    asset = isolated_output / "sets" / "TST"
    (asset / "mechanics").mkdir(parents=True, exist_ok=True)
    (asset / "theme.json").write_text(json.dumps(_theme_fixture()), encoding="utf-8")
    (asset / "mechanics" / "approved.json").write_text(
        json.dumps(_approved_fixture()), encoding="utf-8"
    )

    settings = ms.ModelSettings(
        asset_folder=str(asset),
        set_params=ms.SetParams(set_name="Brass Sky", set_size=120, mechanic_count=3),
    )
    active_project.write_active_project(
        active_project.ProjectState(set_code="TST", settings=settings)
    )


def _stub_generate_with_tool(pairs):
    def stub(*args, **kwargs):
        archetypes = [
            {
                "color_pair": p,
                "name": f"Archetype {p}",
                "description": "win by attacking with evasive fliers",
            }
            for p in pairs
        ]
        return {
            "result": {"archetypes": archetypes},
            "input_tokens": 11,
            "output_tokens": 22,
        }

    return stub


def test_generate_archetypes_returns_normalized(_project, monkeypatch) -> None:
    # Feed pairs in scrambled / unordered-code form; expect canonical order.
    monkeypatch.setattr(
        ag,
        "generate_with_tool",
        _stub_generate_with_tool(["RG", "UW", "WB", "WR", "WG", "UB", "UR", "UG", "BR", "BG"]),
    )
    result = ag.generate_archetypes()
    pairs = [a["color_pair"] for a in result["archetypes"]]
    assert pairs == ag.COLOR_PAIRS
    assert result["input_tokens"] == 11
    assert result["output_tokens"] == 22


def test_generate_archetypes_routes_log_dir(_project, monkeypatch) -> None:
    from mtgai.io.asset_paths import set_artifact_dir

    # The bespoke per-call logger is gone; instead llmfacade's JSONL+HTML
    # transcript is routed to the per-stage logs dir via ``log_dir``.
    inner = _stub_generate_with_tool(ag.COLOR_PAIRS)
    captured: dict = {}

    def stub(*args, **kwargs):
        captured.update(kwargs)
        return inner(*args, **kwargs)

    monkeypatch.setattr(ag, "generate_with_tool", stub)
    result = ag.generate_archetypes()
    assert len(result["archetypes"]) == 10
    assert captured.get("log_dir") == set_artifact_dir() / "archetypes" / "logs"


def test_generate_archetypes_raises_when_undercounted(_project, monkeypatch) -> None:
    monkeypatch.setattr(
        ag,
        "generate_with_tool",
        _stub_generate_with_tool(["WU", "WB", "WR"]),  # only 3 < MIN_ARCHETYPES
    )
    with pytest.raises(RuntimeError, match="valid archetypes"):
        ag.generate_archetypes()


# ---------------------------------------------------------------------------
# Focused regeneration (per-card / partial Refresh AI path)
# ---------------------------------------------------------------------------


def test_pair_label() -> None:
    assert ag.pair_label("WU") == "WU (White-Blue)"
    assert ag.pair_label("RG") == "RG (Red-Green)"


def test_build_prompts_focus_uses_focus_template_and_existing_block() -> None:
    existing = [
        {"color_pair": "WU", "name": "Sky Wardens", "description": "win in the air"},
        {"color_pair": "UB", "name": "Cogthieves", "description": "grind value"},
    ]
    _system, user = ag.build_archetype_prompts(
        theme=_theme_fixture(),
        approved=_approved_fixture(),
        set_name="Brass Sky",
        set_size=120,
        focus_pairs=["WU"],
        existing=existing,
    )
    # Asks to redesign only WU, and shows the OTHER kept pair (UB) for context
    # while excluding the focus pair itself.
    assert "WU (White-Blue)" in user
    assert "Redesign 1" in user
    assert "Cogthieves" in user
    assert "Sky Wardens" not in user


def test_generate_archetypes_focus_filters_to_requested_pair(_project, monkeypatch) -> None:
    # Model returns all ten; a focused call keeps only the requested pair.
    monkeypatch.setattr(ag, "generate_with_tool", _stub_generate_with_tool(ag.COLOR_PAIRS))
    result = ag.generate_archetypes(focus_pairs=["UG"])
    assert [a["color_pair"] for a in result["archetypes"]] == ["UG"]


def test_generate_archetypes_focus_raises_when_pair_absent(_project, monkeypatch) -> None:
    # Model returns pairs that don't include the requested one.
    monkeypatch.setattr(ag, "generate_with_tool", _stub_generate_with_tool(["WU", "WB"]))
    with pytest.raises(RuntimeError, match="none of the requested pairs"):
        ag.generate_archetypes(focus_pairs=["RG"])
