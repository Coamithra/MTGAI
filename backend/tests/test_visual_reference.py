"""Tests for the visual-reference accessors (``mtgai.art.visual_reference``).

Focus: ``get_visual_motifs`` — the cap, the malformed-input guard, the
whitespace cleaning, and the ``limit=0`` full-list escape hatch. The accessor
reads the active project's cached refs via ``get_refs``; the tests monkeypatch
that seam so no project / file is required.
"""

import mtgai.art.visual_reference as vr


def test_get_visual_motifs_caps_at_default_limit(monkeypatch):
    motifs = ["a", "b", "c", "d", "e"]
    monkeypatch.setattr(vr, "get_refs", lambda: {"visual_motifs": motifs})
    assert vr.get_visual_motifs() == ["a", "b", "c"]


def test_get_visual_motifs_limit_zero_returns_full_list(monkeypatch):
    motifs = ["a", "b", "c", "d", "e"]
    monkeypatch.setattr(vr, "get_refs", lambda: {"visual_motifs": motifs})
    assert vr.get_visual_motifs(limit=0) == motifs


def test_get_visual_motifs_strips_and_drops_blank_entries(monkeypatch):
    monkeypatch.setattr(
        vr, "get_refs", lambda: {"visual_motifs": ["  rust  ", "", "   ", "verdigris"]}
    )
    assert vr.get_visual_motifs() == ["rust", "verdigris"]


def test_get_visual_motifs_non_list_value_returns_empty(monkeypatch):
    monkeypatch.setattr(vr, "get_refs", lambda: {"visual_motifs": "not a list"})
    assert vr.get_visual_motifs() == []


def test_get_visual_motifs_missing_key_returns_empty(monkeypatch):
    monkeypatch.setattr(vr, "get_refs", lambda: {})
    assert vr.get_visual_motifs() == []


# ---------------------------------------------------------------------------
# Character-entity accessors (feed the local-Flux PuLID face-lock path)
# ---------------------------------------------------------------------------


def test_is_character_entity_reads_legendary_characters(monkeypatch):
    monkeypatch.setattr(vr, "get_refs", lambda: {"legendary_characters": {"hero": "a tall knight"}})
    assert vr.is_character_entity("hero") is True
    # A non-character category key is not a character.
    assert vr.is_character_entity("citadel") is False


def test_is_character_entity_missing_category(monkeypatch):
    monkeypatch.setattr(vr, "get_refs", lambda: {})
    assert vr.is_character_entity("hero") is False


def test_get_character_appearance_returns_prose(monkeypatch):
    monkeypatch.setattr(vr, "get_refs", lambda: {"legendary_characters": {"hero": "a tall knight"}})
    assert vr.get_character_appearance("hero") == "a tall knight"


def test_get_character_appearance_none_when_absent(monkeypatch):
    monkeypatch.setattr(vr, "get_refs", lambda: {"legendary_characters": {}})
    assert vr.get_character_appearance("hero") is None


def test_get_character_appearance_coerces_non_string(monkeypatch):
    """A malformed (non-string) value won't reach the prompt substitution."""
    monkeypatch.setattr(
        vr, "get_refs", lambda: {"legendary_characters": {"hero": {"nested": "obj"}}}
    )
    assert vr.get_character_appearance("hero") is None


def test_character_accessors_normalize_spaced_dict_keys(monkeypatch):
    """A space-slugged dict key matches an underscore-slugged entity_key.

    Regression: visual-references.json keys are space-slugged ("storm knight"),
    but ``art_character_refs`` entity_keys are underscore-slugged
    ("storm_knight"). The raw ``entity_key in get_refs()[...]`` lookup never
    matched a multi-word character, silently no-op'ing PuLID face-lock + the
    name->appearance substitution for every such entity. Both accessors now
    normalize through the same slug as the appearance-prose path.
    """
    monkeypatch.setattr(
        vr, "get_refs", lambda: {"legendary_characters": {"storm knight": "a tall knight in armor"}}
    )
    assert vr.is_character_entity("storm_knight") is True
    assert vr.get_character_appearance("storm_knight") == "a tall knight in armor"
    # The reverse surface-form variance resolves too (underscore key, spaced query).
    monkeypatch.setattr(
        vr, "get_refs", lambda: {"legendary_characters": {"storm_knight": "a tall knight in armor"}}
    )
    assert vr.is_character_entity("storm knight") is True
    assert vr.get_character_appearance("storm knight") == "a tall knight in armor"


# ---------------------------------------------------------------------------
# Named-entity helpers (name-based art-prompt binding)
# ---------------------------------------------------------------------------


def test_entity_display_name_titles_the_slug():
    assert vr.entity_display_name("storm_knight") == "Storm Knight"
    assert vr.entity_display_name("the_obsidian_spire") == "The Obsidian Spire"
    assert vr.entity_display_name("vorrik") == "Vorrik"


def test_get_named_entities_matches_spaced_multiword_name(monkeypatch):
    # A multi-word slug must match its spaced form in the card text — the bare
    # ``key in search_text`` used by get_visual_references misses this.
    monkeypatch.setattr(
        vr, "get_refs", lambda: {"legendary_characters": {"storm_knight": "appearance"}}
    )
    found = vr.get_named_entities("Storm Knight", "Legendary Creature", "", None)
    assert found == [{"key": "storm_knight", "name": "Storm Knight", "kind": "character"}]


def test_get_named_entities_dedupes_and_keeps_priority_order(monkeypatch):
    monkeypatch.setattr(
        vr,
        "get_refs",
        lambda: {
            "legendary_characters": {"vorrik": "x"},
            "landmarks": {"the_spire": "y"},
        },
    )
    found = vr.get_named_entities("Vorrik at the Spire", "Sorcery", "", None)
    keys = [e["key"] for e in found]
    assert keys == ["vorrik", "the_spire"]


def test_get_named_entities_empty_when_no_match(monkeypatch):
    monkeypatch.setattr(vr, "get_refs", lambda: {"legendary_characters": {"storm_knight": "x"}})
    assert vr.get_named_entities("Goblin Raider", "Creature", "", None) == []


def test_get_named_entities_word_boundary_avoids_substring_overmatch(monkeypatch):
    # "the order" must not fire on "the ordeal"; "vorrik" must not fire on "vorrikson".
    monkeypatch.setattr(
        vr,
        "get_refs",
        lambda: {"factions": {"the_order": "x"}, "legendary_characters": {"vorrik": "y"}},
    )
    assert vr.get_named_entities("Trial by Ordeal", "Sorcery", "Vorrikson flees.", None) == []
    found = vr.get_named_entities("The Order Marches", "Sorcery", "Vorrik leads.", None)
    assert {e["key"] for e in found} == {"the_order", "vorrik"}
