"""Config guards for models.toml — assertions that the shipped registry entries
decode with the launch knobs downstream code (``_llamacpp_new_model``) expects."""

from mtgai.settings.model_registry import get_registry
from mtgai.settings.model_settings import (
    DEFAULT_LLM_ASSIGNMENTS,
    PRESETS,
    ModelSettings,
)


def test_local_default_entry():
    """The local-default Gemma 4 26B Vlad-Updated entry must load with thinking
    on and the all-GPU placement (Vlad's fast K-quant mix + the fixed template)."""
    info = get_registry().get_llm("gemma4-26b-vlad-updated")
    assert info is not None
    assert info.provider == "llamacpp"
    assert info.thinking == "adaptive"
    # thinking_style left unset so llmfacade auto-detects it from the GGUF.
    assert info.thinking_style is None
    assert info.n_gpu_layers == -1
    assert info.cache_type_k == "q8_0"
    assert info.cache_type_v == "q8_0"
    assert info.context_window == 128000
    # fit defaults on → launches --fit on, so llama-server autofits to VRAM at
    # spawn (the registry-load VRAM check logs only an INFO note for this entry).
    assert info.fit is True
    assert info.gguf_path is not None
    assert info.gguf_path.endswith("vlad-updated-gemma4-26b.gguf")


def test_local_default_assignments_point_at_vlad_updated():
    """DEFAULT_LLM_ASSIGNMENTS (every fresh project's local default) resolves to
    the vlad-updated entry (the local default after the model-registry prune)."""
    assert set(DEFAULT_LLM_ASSIGNMENTS.values()) == {"gemma4-26b-vlad-updated"}


def test_ctx_tier_twin_is_a_48k_clone_of_the_carrier():
    """The DOWNSTREAM-tier twin is the same GGUF as the 128k carrier but at a 48k
    --ctx-size, with every other launch knob identical (so only the KV budget
    differs). This is what the all-local-tiered preset assigns downstream."""
    reg = get_registry()
    carrier = reg.get_llm("gemma4-26b-vlad-updated")
    twin = reg.get_llm("gemma4-26b-vlad-updated-48k")
    assert twin is not None and carrier is not None
    # Distinct llama-swap model id so same-gguf/different-ctx entries coexist.
    assert twin.model_id == "gemma4-26b-vlad-updated-48k"
    assert twin.context_window == 48000
    assert carrier.context_window == 128000
    # Same GGUF + identical placement/quant/thinking — only context_window differs.
    assert twin.gguf_path == carrier.gguf_path
    assert twin.provider == carrier.provider == "llamacpp"
    assert twin.n_gpu_layers == carrier.n_gpu_layers == -1
    assert twin.cache_type_k == carrier.cache_type_k == "q8_0"
    assert twin.cache_type_v == carrier.cache_type_v == "q8_0"
    assert twin.thinking == carrier.thinking == "adaptive"
    # The iq2m residency-win twin is also registered at 48k.
    iq2m = reg.get_llm("gemma4-26b-iq2m-48k")
    assert iq2m is not None and iq2m.context_window == 48000


def test_all_local_tiered_preset_keeps_theme_at_128k_and_drops_the_rest_to_48k():
    """all-local-tiered: only theme_extract (the large-document stage) stays on the
    128k carrier; every other stage runs the 48k twin of the same GGUF."""
    assert "all-local-tiered" in PRESETS
    reg = get_registry()
    settings = ModelSettings.from_preset("all-local-tiered")
    theme_key = settings.llm_assignments["theme_extract"]
    assert theme_key == "gemma4-26b-vlad-updated"
    theme_model = reg.get_llm(theme_key)
    assert theme_model is not None and theme_model.context_window == 128000

    downstream = {
        stage: key for stage, key in settings.llm_assignments.items() if stage != "theme_extract"
    }
    # Every non-theme stage is covered and on the 48k twin.
    assert set(downstream) == set(DEFAULT_LLM_ASSIGNMENTS) - {"theme_extract"}
    assert set(downstream.values()) == {"gemma4-26b-vlad-updated-48k"}
    twin = reg.get_llm("gemma4-26b-vlad-updated-48k")
    assert twin is not None and twin.context_window == 48000


def test_invalid_thinking_value_raises(tmp_path):
    """A typo'd thinking value must fail loudly at load rather than silently
    disabling reasoning (an unrecognised mode reaches llama.cpp as thinking-off)."""
    import pytest

    from mtgai.settings.model_registry import ModelRegistry

    toml = tmp_path / "bad.toml"
    toml.write_text(
        "[llm.x]\n"
        'name = "X"\n'
        'provider = "llamacpp"\n'
        'model_id = "x"\n'
        'gguf_path = "C:/Models/x.gguf"\n'
        'thinking = "adaptiv"\n'
    )
    with pytest.raises(ValueError, match="invalid thinking"):
        ModelRegistry.load(toml)
