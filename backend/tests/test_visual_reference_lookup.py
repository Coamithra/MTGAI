"""Tests for the tag-driven dictionary lookup in ``mtgai.art.visual_reference``.

The unify (card 6a27581d) replaced the brittle substring matcher with a
normalized-key lookup so a tag and a dictionary entry whose surface forms differ
(``optimus_prime`` vs ``optimus prime``) still resolve.
"""

from __future__ import annotations

import mtgai.art.visual_reference as vr

_REFS = {
    "legendary_characters": {"optimus prime": "a towering red-and-blue robot leader"},
    "creature_types": {"autoroopers": "small scuttling drone bots"},
    "landmarks": {"the_spire": "a colossal obelisk over the sea"},
}


def test_normalize_entity_key() -> None:
    assert vr.normalize_entity_key("Optimus Prime") == "optimus_prime"
    assert vr.normalize_entity_key("  The Spire!  ") == "the_spire"
    assert vr.normalize_entity_key("autoroopers") == "autoroopers"


def test_lookup_matches_across_surface_forms(monkeypatch) -> None:
    monkeypatch.setattr(vr, "get_refs", lambda: _REFS)
    # underscore tag -> spaced dict key
    out = vr.get_visual_references_for_keys(["optimus_prime"])
    assert "towering red-and-blue robot leader" in out
    assert "[Character: Optimus Prime]" in out
    # spaced dict key matched by the same normalized form
    out2 = vr.get_visual_references_for_keys(["the spire"])
    assert "colossal obelisk" in out2


def test_lookup_dedups_and_skips_unknown(monkeypatch) -> None:
    monkeypatch.setattr(vr, "get_refs", lambda: _REFS)
    out = vr.get_visual_references_for_keys(["autoroopers", "autoroopers", "nonexistent"])
    assert out.count("scuttling drone bots") == 1
    assert "nonexistent" not in out.lower()


def test_lookup_empty_keys(monkeypatch) -> None:
    monkeypatch.setattr(vr, "get_refs", lambda: _REFS)
    assert vr.get_visual_references_for_keys([]) == ""


def test_entity_catalog_flattens_with_tag_kinds(monkeypatch) -> None:
    monkeypatch.setattr(vr, "get_refs", lambda: _REFS)
    cat = vr.get_entity_catalog()
    by_key = {e["entity_key"]: e for e in cat}
    assert by_key["optimus_prime"]["kind"] == "character"
    assert by_key["autoroopers"]["kind"] == "creature"
    assert by_key["the_spire"]["kind"] == "location"
