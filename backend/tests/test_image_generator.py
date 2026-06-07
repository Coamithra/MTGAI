"""Tests for the merged Art Generation stage's generation seams.

Covers the unit-testable decisions (no live ComfyUI / provider): best-of-N knob
resolution + clamping, provider dispatch + the hosted-provider stub raising,
and the character-reference conditioning wiring decision.
"""

import json

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


# ---------------------------------------------------------------------------
# ensure_comfyui frees local LLM VRAM before the VRAM check (single-GPU art tail)
# ---------------------------------------------------------------------------


def test_ensure_comfyui_unloads_local_models_before_check_vram(monkeypatch):
    """On a single GPU the resident local LLM must be unloaded BEFORE check_vram,
    so the check sees the freed VRAM and ComfyUI/Flux can start."""
    calls = []
    monkeypatch.setattr(ig, "is_comfyui_running", lambda: False)
    monkeypatch.setattr(ig, "check_vram", lambda: calls.append("check_vram"))
    monkeypatch.setattr(ig, "start_comfyui", lambda log_dir=None: calls.append("start_comfyui"))

    import mtgai.generation.llm_client as llm_client

    monkeypatch.setattr(
        llm_client, "unload_local_models", lambda: calls.append("unload_local_models") or True
    )

    ig.ensure_comfyui()

    assert calls == ["unload_local_models", "check_vram", "start_comfyui"]


def test_ensure_comfyui_skips_unload_when_already_running(monkeypatch):
    """ComfyUI already up -> no VRAM check, no unload (the LLM can stay resident
    because Flux is already loaded / running its own process)."""
    called = []
    monkeypatch.setattr(ig, "is_comfyui_running", lambda: True)

    import mtgai.generation.llm_client as llm_client

    monkeypatch.setattr(llm_client, "unload_local_models", lambda: called.append("unload") or True)

    assert ig.ensure_comfyui() is None
    assert called == []


def test_ensure_comfyui_fast_fails_when_nothing_unloaded(monkeypatch):
    """Nothing unloaded (cloud-only / another app holds the VRAM) -> a single
    check_vram, no retry poll, so the actionable error surfaces immediately."""
    n_checks = []

    def _boom():
        n_checks.append(1)
        raise RuntimeError("Insufficient VRAM")

    monkeypatch.setattr(ig, "is_comfyui_running", lambda: False)
    monkeypatch.setattr(ig, "check_vram", _boom)

    import mtgai.generation.llm_client as llm_client

    monkeypatch.setattr(llm_client, "unload_local_models", lambda: False)

    with pytest.raises(RuntimeError):
        ig.ensure_comfyui()
    assert len(n_checks) == 1  # no retry when nothing was unloaded


def test_check_vram_with_retry_succeeds_after_lag(monkeypatch):
    """VRAM reclamation lags one beat: the first check_vram raises, the second
    succeeds -> _check_vram_with_retry returns without raising."""
    attempts = []

    def _flaky():
        attempts.append(1)
        if len(attempts) < 2:
            raise RuntimeError("Insufficient VRAM")

    monkeypatch.setattr(ig, "check_vram", _flaky)
    monkeypatch.setattr(ig.time, "sleep", lambda _s: None)

    ig._check_vram_with_retry(attempts=3, delay_s=0.0)
    assert len(attempts) == 2


def test_check_vram_with_retry_reraises_after_budget(monkeypatch):
    """VRAM never frees: the final attempt re-raises so the actionable message
    still surfaces."""
    attempts = []

    def _never():
        attempts.append(1)
        raise RuntimeError("Insufficient VRAM")

    monkeypatch.setattr(ig, "check_vram", _never)
    monkeypatch.setattr(ig.time, "sleep", lambda _s: None)

    with pytest.raises(RuntimeError):
        ig._check_vram_with_retry(attempts=3, delay_s=0.0)
    assert len(attempts) == 3


# ---------------------------------------------------------------------------
# VRAM-aware Flux quant selection
# ---------------------------------------------------------------------------


def test_select_flux_quant_uses_q5_on_12gb_card():
    """A 12GB-class card (~10GB free) gets the safe Q5_K_S floor — Q8 partially
    offloads to CPU under the current ComfyUI and runs ~12x slower."""
    assert ig.select_flux_quant(free_mb=10_000) == ig.FLUX_QUANT_DEFAULT
    assert ig.select_flux_quant(free_mb=10_000) == "flux1-dev-Q5_K_S.gguf"


def test_select_flux_quant_uses_q8_on_high_vram_card():
    """A 16GB+ card with comfortable headroom gets the higher-quality Q8_0."""
    assert ig.select_flux_quant(free_mb=16_000) == ig.FLUX_QUANT_HIGH_VRAM
    assert ig.select_flux_quant(free_mb=16_000) == "flux1-dev-Q8_0.gguf"


def test_select_flux_quant_boundary():
    """Exactly at the Q8 threshold picks Q8; one MB below falls to Q5."""
    assert ig.select_flux_quant(free_mb=ig.FLUX_Q8_MIN_FREE_MB) == ig.FLUX_QUANT_HIGH_VRAM
    assert ig.select_flux_quant(free_mb=ig.FLUX_Q8_MIN_FREE_MB - 1) == ig.FLUX_QUANT_DEFAULT


def test_select_flux_quant_queries_vram_when_unset(monkeypatch):
    """No free_mb arg -> query nvidia-smi via get_vram_info."""
    ig.reset_flux_quant()
    monkeypatch.setattr(ig, "get_vram_info", lambda: {"free_mb": 10_000})
    assert ig.select_flux_quant() == ig.FLUX_QUANT_DEFAULT
    ig.reset_flux_quant()


def test_select_flux_quant_degrades_to_safe_default_on_query_failure(monkeypatch):
    """A VRAM query failure must not risk the partial-offload slowdown — fall back
    to the safe Q5 floor, never Q8."""
    ig.reset_flux_quant()

    def _boom():
        raise RuntimeError("nvidia-smi not found")

    monkeypatch.setattr(ig, "get_vram_info", _boom)
    assert ig.select_flux_quant() == ig.FLUX_QUANT_DEFAULT
    ig.reset_flux_quant()


def test_select_flux_quant_caches_choice_for_the_session(monkeypatch):
    """The no-arg choice is decided ONCE from the pre-load VRAM and reused: once
    Flux is resident free VRAM drops below the Q8 threshold, so a per-image
    re-query would flip Q8->Q5 and force a reload. The cache prevents that."""
    ig.reset_flux_quant()
    free = {"free_mb": 16_000}
    monkeypatch.setattr(ig, "get_vram_info", lambda: dict(free))

    assert ig.select_flux_quant() == ig.FLUX_QUANT_HIGH_VRAM  # first read: lots free
    free["free_mb"] = 3_000  # Flux now resident -> would pick Q5 if re-queried
    assert ig.select_flux_quant() == ig.FLUX_QUANT_HIGH_VRAM  # cached, no flip-flop

    ig.reset_flux_quant()
    assert ig.select_flux_quant() == ig.FLUX_QUANT_DEFAULT  # reset -> re-decides
    ig.reset_flux_quant()


def test_explicit_free_mb_never_touches_cache(monkeypatch):
    """Passing free_mb is the pure-decision path: it must not read or write the
    session cache."""
    ig.reset_flux_quant()
    monkeypatch.setattr(ig, "get_vram_info", lambda: {"free_mb": 3_000})
    assert ig.select_flux_quant(free_mb=16_000) == ig.FLUX_QUANT_HIGH_VRAM
    assert ig._SELECTED_FLUX_QUANT is None  # unchanged
    # The cached no-arg path still reads the real (low) VRAM, not the explicit arg.
    assert ig.select_flux_quant() == ig.FLUX_QUANT_DEFAULT
    ig.reset_flux_quant()


def test_min_vram_free_mb_fits_q5():
    """The VRAM gate must be low enough that a 12GB card running Q5 passes it."""
    assert ig.MIN_VRAM_FREE_MB <= 9_000


def test_workflow_json_default_is_q5():
    """The bundled workflow's UnetLoaderGGUF default must be the safe Q5 floor, so
    a from-JSON load (no VRAM query) never names the partial-offload Q8."""
    workflow = json.loads(ig.WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert workflow["1"]["class_type"] == "UnetLoaderGGUF"
    assert workflow["1"]["inputs"]["unet_name"] == "flux1-dev-Q5_K_S.gguf"
    assert workflow["1"]["inputs"]["unet_name"] == ig.FLUX_QUANT_DEFAULT


def test_generate_image_comfyui_injects_vram_chosen_quant(monkeypatch):
    """generate_image_comfyui rewrites the workflow's unet_name from the VRAM-aware
    selection at submit time (overriding the JSON default)."""
    captured = {}

    def _fake_queue(workflow):
        captured["unet_name"] = workflow["1"]["inputs"]["unet_name"]
        return "promptid"

    monkeypatch.setattr(ig, "select_flux_quant", lambda: "flux1-dev-Q8_0.gguf")
    monkeypatch.setattr(ig, "_queue_prompt", _fake_queue)
    monkeypatch.setattr(
        ig, "_poll_completion", lambda pid: {"filename": "x.png", "subfolder": "", "elapsed": 1.0}
    )
    monkeypatch.setattr(ig, "_download_image", lambda f, s: b"img")
    monkeypatch.setattr(ig, "flush_comfyui", lambda: None)

    _data, meta = ig.generate_image_comfyui("a cat")
    assert captured["unet_name"] == "flux1-dev-Q8_0.gguf"
    assert meta["model"] == "flux1-dev-Q8_0"


def test_generate_image_comfyui_uses_safe_default_when_low_vram(monkeypatch):
    """Low VRAM -> the submitted workflow names Q5 even though Q8 might be on disk."""
    captured = {}

    monkeypatch.setattr(ig, "select_flux_quant", lambda: "flux1-dev-Q5_K_S.gguf")
    monkeypatch.setattr(
        ig, "_queue_prompt", lambda wf: captured.update(unet=wf["1"]["inputs"]["unet_name"]) or "id"
    )
    monkeypatch.setattr(
        ig, "_poll_completion", lambda pid: {"filename": "x.png", "subfolder": "", "elapsed": 1.0}
    )
    monkeypatch.setattr(ig, "_download_image", lambda f, s: b"img")
    monkeypatch.setattr(ig, "flush_comfyui", lambda: None)

    _data, meta = ig.generate_image_comfyui("a cat")
    assert captured["unet"] == "flux1-dev-Q5_K_S.gguf"
    assert meta["model"] == "flux1-dev-Q5_K_S"
