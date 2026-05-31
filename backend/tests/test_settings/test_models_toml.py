"""Config guards for models.toml — assertions that the shipped registry entries
decode with the launch knobs downstream code (``_llamacpp_new_model``) expects."""

from mtgai.settings.model_registry import get_registry
from mtgai.settings.model_settings import DEFAULT_LLM_ASSIGNMENTS


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
