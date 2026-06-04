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


def _fake_image_result(media_type="image/png"):
    """A minimal stand-in for llmfacade's ImageResult."""
    from llmfacade.models import ImageBlock, ImageResult, ImageUsage

    return ImageResult(
        images=[ImageBlock(data=b"hostedimg", media_type=media_type)],
        usage=ImageUsage(input_tokens=10, output_tokens=20, image_count=1),
        model="resolved-model",
        provider="test",
    )


def test_hosted_openai_routes_through_llmfacade(monkeypatch):
    """openai dispatch calls LLM.default().generate_image with a *valid* OpenAI
    size (our 1024x768 art window is illegal for OpenAI) and returns bytes."""
    captured = {}

    class _FakeLLM:
        def generate_image(self, prompt, **kwargs):
            captured["prompt"] = prompt
            captured.update(kwargs)
            return _fake_image_result()

    monkeypatch.setattr("llmfacade.LLM.default", classmethod(lambda cls: _FakeLLM()))

    data, meta = ig.generate_image("a dragon", provider="openai", model_id="gpt-image-1")
    assert data == b"hostedimg"
    assert captured["provider"] == "openai"
    assert captured["model"] == "gpt-image-1"
    # 1024x768 is landscape -> nearest supported gpt-image-1 size.
    assert captured["size"] == "1536x1024"
    assert "aspect_ratio" not in captured
    assert meta["backend"] == "llmfacade_openai"
    assert meta["provider"] == "openai"


def test_hosted_gemini_uses_aspect_ratio(monkeypatch):
    """gemini dispatch passes aspect_ratio (Gemini ignores size) and aliases the
    provider name to llmfacade's 'google'."""
    captured = {}

    class _FakeLLM:
        def generate_image(self, prompt, **kwargs):
            captured.update(kwargs)
            return _fake_image_result()

    monkeypatch.setattr("llmfacade.LLM.default", classmethod(lambda cls: _FakeLLM()))

    ig.generate_image("a forest", provider="gemini")
    assert captured["provider"] == "google"  # gemini -> google alias
    # No model_id passed -> the provider default.
    assert captured["model"] == "gemini-2.5-flash-image"
    assert captured["aspect_ratio"] == "4:3"  # 1024x768 reduced
    assert "size" not in captured


def test_hosted_threads_existing_refs_as_reference_images(monkeypatch, tmp_path):
    """ref_paths that exist on disk become ImageBlock reference_images; missing
    ones are dropped (no conditioning)."""
    ref = tmp_path / "hero.png"
    ref.write_bytes(b"fakepng")
    missing = str(tmp_path / "nope.png")
    captured = {}

    class _FakeLLM:
        def generate_image(self, prompt, **kwargs):
            captured.update(kwargs)
            return _fake_image_result()

    monkeypatch.setattr("llmfacade.LLM.default", classmethod(lambda cls: _FakeLLM()))

    _data, meta = ig.generate_image(
        "a hero", provider="openai", model_id="gpt-image-1", ref_paths=[str(ref), missing]
    )
    refs = captured["reference_images"]
    assert refs is not None and len(refs) == 1  # only the existing one
    assert refs[0].data == b"fakepng"
    assert meta["character_refs_applied"] is True


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        ig.generate_image("a cat", provider="midjourney")


def test_openai_size_snaps_to_supported():
    # gpt-image-1 family
    assert ig._openai_size(1024, 768, "gpt-image-1") == "1536x1024"
    assert ig._openai_size(768, 1024, "gpt-image-1") == "1024x1536"
    # dall-e-3 family
    assert ig._openai_size(1024, 768, "dall-e-3") == "1792x1024"
    assert ig._openai_size(768, 1024, "dall-e-3") == "1024x1792"


def test_aspect_ratio_reduces():
    assert ig._aspect_ratio(1024, 768) == "4:3"
    assert ig._aspect_ratio(1024, 1024) == "1:1"
    assert ig._aspect_ratio(1920, 1080) == "16:9"


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
