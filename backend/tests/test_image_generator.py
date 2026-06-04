"""Tests for the merged Art Generation stage's generation seams.

Covers the unit-testable decisions (no live ComfyUI / provider): best-of-N knob
resolution + clamping, provider dispatch + the hosted-provider stub raising,
and the character-reference conditioning wiring decision.
"""

import pytest

from mtgai.art import image_generator as ig
from mtgai.models.card import ArtCharacterRef, Card
from mtgai.settings.model_settings import MAX_ART_VERSIONS, MIN_ART_VERSIONS

# ---------------------------------------------------------------------------
# Best-of-N knob
# ---------------------------------------------------------------------------


def test_resolve_versions_defaults_when_no_project():
    """No active project -> the default count, not an error."""
    # require_active_project raises when none is open; _resolve handles that.
    assert ig._resolve_versions_per_card() >= MIN_ART_VERSIONS


def test_resolve_versions_clamps_to_range(monkeypatch):
    class _SP:
        art_versions_per_card = 99

    class _Settings:
        set_params = _SP()

    class _Proj:
        settings = _Settings()

    monkeypatch.setattr("mtgai.runtime.active_project.require_active_project", lambda: _Proj())
    assert ig._resolve_versions_per_card() == MAX_ART_VERSIONS

    _SP.art_versions_per_card = 0
    assert ig._resolve_versions_per_card() == MIN_ART_VERSIONS

    _SP.art_versions_per_card = 4
    assert ig._resolve_versions_per_card() == 4


# ---------------------------------------------------------------------------
# Provider dispatch + hosted stub
# ---------------------------------------------------------------------------


def test_generate_image_dispatches_to_comfyui(monkeypatch):
    calls = {}

    def _fake_comfy(prompt, seed=None, ref_paths=None, width=0, height=0):
        calls["prompt"] = prompt
        calls["ref_paths"] = ref_paths
        return b"img", {"backend": "comfyui_local"}

    monkeypatch.setattr(ig, "generate_image_comfyui", _fake_comfy)
    data, _meta = ig.generate_image("a cat", provider="comfyui", ref_paths=["/x.png"])
    assert data == b"img"
    assert calls["prompt"] == "a cat"
    assert calls["ref_paths"] == ["/x.png"]


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_hosted_provider_is_stubbed(provider):
    """Hosted providers are wired to dispatch but raise NotImplementedError
    until llmfacade's generate_image lands."""
    with pytest.raises(NotImplementedError):
        ig.generate_image("a cat", provider=provider)


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        ig.generate_image("a cat", provider="midjourney")


# ---------------------------------------------------------------------------
# Character-reference conditioning wiring decision
# ---------------------------------------------------------------------------


def test_apply_character_refs_no_refs():
    assert ig._apply_character_refs({}, []) is False


def test_apply_character_refs_missing_files_falls_back(tmp_path):
    missing = str(tmp_path / "nope.png")
    assert ig._apply_character_refs({}, [missing]) is False


def test_apply_character_refs_present_returns_false_until_wired(tmp_path):
    """When refs exist on disk the decision is to condition — but the PuLID node
    injection is a tracked stub, so it returns False (plain gen) for now. This
    pins the contract: the *decision* path is exercised even though the wiring is
    deferred."""
    ref = tmp_path / "hero.png"
    ref.write_bytes(b"fakepng")
    assert ig._apply_character_refs({}, [str(ref)]) is False


def test_resolve_ref_paths_joins_relative(tmp_path):
    ref = ArtCharacterRef(entity_key="hero", ref_image_path="art-direction/x.png")
    card = Card(name="Hero", type_line="Legendary Creature", art_character_refs=[ref])
    resolved = ig._resolve_ref_paths(card, tmp_path)
    assert resolved == [str(tmp_path / "art-direction" / "x.png")]


def test_resolve_ref_paths_keeps_absolute(tmp_path):
    abs_path = str(tmp_path / "abs.png")
    card = Card(
        name="Hero",
        type_line="Creature",
        art_character_refs=[ArtCharacterRef(entity_key="hero", ref_image_path=abs_path)],
    )
    assert ig._resolve_ref_paths(card, tmp_path / "other") == [abs_path]


def test_resolve_ref_paths_empty_for_no_refs(tmp_path):
    card = Card(name="Plain", type_line="Creature")
    assert ig._resolve_ref_paths(card, tmp_path) == []
