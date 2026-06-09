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
