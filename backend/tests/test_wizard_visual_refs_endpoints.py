"""Unit tests for the Visual References tab's server-side coercion helpers.

These exercise the pure shaping logic in ``pipeline/server.py`` that turns the
editable-tab payload into the on-disk ``visual-references.json`` shape (and the
inverse row-shaping) without spinning up the FastAPI app or any LLM.
"""

from __future__ import annotations

from mtgai.pipeline import server


def test_coerce_vr_payload_assembles_and_slugifies() -> None:
    body = {
        "entities": {
            "legendary_characters": [
                {"key": "Kalak!", "description": "  Old sorcerer king.  "},
                {"key": "", "description": "dropped — empty key"},
                {"key": "blank", "description": "   "},  # dropped — empty desc
            ],
            "creature_types": [{"key": "moktar", "description": "lion-headed"}],
            "factions": [],
            "landmarks": [],
        },
        "flux_term_replacements": {"moktar": "lion-headed humanoid", "": "dropped"},
        "visual_motifs": ["rust", "  ", "verdigris"],
        "set_art_direction": "  Sickly contrast.  ",
        "artists": [{"name": "Lira Vance", "style_prompt": "watercolor"}],
    }
    refs, artists = server._coerce_vr_payload(body)

    # Keys are slugified (edge punctuation stripped, lowercased) so they still
    # match card text downstream; empty rows dropped; description trimmed.
    assert refs["legendary_characters"] == {"kalak": "Old sorcerer king."}
    assert refs["creature_types"] == {"moktar": "lion-headed"}
    assert refs["factions"] == {}
    assert refs["landmarks"] == {}
    assert refs["flux_term_replacements"] == {"moktar": "lion-headed humanoid"}
    assert refs["visual_motifs"] == ["rust", "verdigris"]
    assert refs["set_art_direction"] == "Sickly contrast."
    assert artists == [{"name": "Lira Vance", "style_prompt": "watercolor"}]


def test_coerce_vr_payload_handles_empty_body() -> None:
    refs, artists = server._coerce_vr_payload({})
    for cat in server._VR_ENTITY_KEYS:
        assert refs[cat] == {}
    assert refs["flux_term_replacements"] == {}
    assert refs["visual_motifs"] == []
    assert refs["set_art_direction"] == ""
    assert artists == []


def test_coerce_vr_payload_rejects_bad_entities_shape() -> None:
    assert server._coerce_vr_payload({"entities": "nope"}) == (
        "entities must be an object keyed by category"
    )
    assert server._coerce_vr_payload({"entities": {"factions": ["not a dict"]}}) == (
        "factions rows must be objects"
    )


def test_vr_entity_rows_shapes_dicts_into_rows() -> None:
    refs = {
        "legendary_characters": {"kalak": "king"},
        "creature_types": {},
        "factions": {"choir": "monks", "bad": 5},  # non-str value dropped
        "landmarks": {},
    }
    rows = server._vr_entity_rows(refs)
    assert rows["legendary_characters"] == [{"key": "kalak", "description": "king"}]
    assert rows["factions"] == [{"key": "choir", "description": "monks"}]
    assert rows["creature_types"] == []
