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
    differs). get_llm_model_id swaps it in per stage; it's flagged internal."""
    reg = get_registry()
    carrier = reg.get_llm("gemma4-26b-vlad-updated")
    twin = reg.get_llm("gemma4-26b-vlad-updated-48k")
    assert twin is not None and carrier is not None
    # Distinct llama-swap model id so same-gguf/different-ctx entries coexist.
    assert twin.model_id == "gemma4-26b-vlad-updated-48k"
    assert twin.context_window == 48000
    assert carrier.context_window == 128000
    # The twin is internal (hidden from the UI); its base is not.
    assert twin.internal is True and carrier.internal is False
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


def test_tiering_is_automatic_no_separate_tiered_preset():
    """The context-length tiering is applied per stage in get_llm_model_id, so
    there is no user-facing 'tiered' preset to choose (and never an -48k twin in
    an assignment)."""
    assert "all-local-tiered" not in PRESETS


def test_get_llm_model_id_swaps_base_for_48k_twin_on_downstream_stages():
    """The user assigns a *base* model (all-local); get_llm_model_id keeps the
    full 128k window only for theme_extract and resolves every other stage to the
    base's 48k downstream twin -- automatically, the same id the poller polls."""
    settings = ModelSettings.from_preset("all-local")
    # The stored assignment is always the base the user picked (no twins leak in).
    assert set(settings.llm_assignments.values()) == {"gemma4-26b-vlad-updated"}
    # theme_extract keeps the full window; everything else drops to the twin.
    assert settings.get_llm_model_id("theme_extract") == "gemma4-26b-vlad-updated"
    for stage in DEFAULT_LLM_ASSIGNMENTS:
        expected = (
            "gemma4-26b-vlad-updated" if stage == "theme_extract" else "gemma4-26b-vlad-updated-48k"
        )
        assert settings.get_llm_model_id(stage) == expected


def test_conformance_uses_full_context_on_large_sets():
    """The conformance gate's cumulative-context interaction prompt grows with set
    size, so at/above the threshold the stage stays on the base's FULL window
    instead of the 48k twin. Normal-size sets keep the lean twin."""
    from mtgai.settings.model_settings import _CONFORMANCE_FULL_CONTEXT_SET_SIZE

    settings = ModelSettings.from_preset("all-local")

    # Normal set: conformance tiers down to the 48k twin like every other stage.
    settings.set_params = settings.set_params.model_copy(update={"set_size": 277})
    assert settings.get_llm_model_id("conformance") == "gemma4-26b-vlad-updated-48k"

    # Large set: conformance keeps the full 128k base; other stages still tier down.
    settings.set_params = settings.set_params.model_copy(
        update={"set_size": _CONFORMANCE_FULL_CONTEXT_SET_SIZE}
    )
    assert settings.get_llm_model_id("conformance") == "gemma4-26b-vlad-updated"
    assert settings.get_llm_model_id("card_gen") == "gemma4-26b-vlad-updated-48k"


def test_get_llm_model_id_leaves_models_without_a_twin_untouched():
    """A base with no downstream twin (cloud models) resolves to itself on every
    stage -- the tiering only kicks in where a twin exists."""
    settings = ModelSettings.from_preset("recommended")
    for stage in ("theme_extract", "card_gen", "ai_review"):
        model_id = settings.get_llm_model_id(stage)
        assert not model_id.endswith("-48k")
        # And it round-trips to a real, non-internal registry entry.
        info = get_registry().get_llm_by_model_id(model_id)
        assert info is not None and info.internal is False


def test_twins_are_hidden_from_user_facing_lists_but_resolvable_by_id():
    """list_llm + to_dict (the settings UI sources) must exclude internal twins,
    while get_llm / get_llm_by_model_id still resolve them for launch + budget +
    the tok/s poller."""
    reg = get_registry()
    twin_id = "gemma4-26b-vlad-updated-48k"
    assert all(m.key != twin_id for m in reg.list_llm())
    assert twin_id not in reg.to_dict()["llm"]
    # Still resolvable internally.
    assert reg.get_llm(twin_id) is not None
    assert reg.get_llm_by_model_id(twin_id) is not None


def test_get_assigned_model_id_never_returns_a_twin():
    """The provenance/display resolver returns the base the user assigned on
    every stage -- it must never surface the internal ctx twin (unlike the
    runtime get_llm_model_id)."""
    settings = ModelSettings.from_preset("all-local")
    for stage in DEFAULT_LLM_ASSIGNMENTS:
        assert settings.get_assigned_model_id(stage) == "gemma4-26b-vlad-updated"
    # The runtime resolver, by contrast, DOES return the twin downstream.
    assert settings.get_llm_model_id("card_gen") == "gemma4-26b-vlad-updated-48k"


def test_public_model_id_maps_twin_to_base_else_identity():
    """public_model_id turns an internal twin id back into its base (for
    provenance), and is the identity for any non-twin id."""
    reg = get_registry()
    assert reg.public_model_id("gemma4-26b-vlad-updated-48k") == "gemma4-26b-vlad-updated"
    assert reg.public_model_id("gemma4-26b-iq2m-48k") == "gemma4-26b-iq2m"
    # Identity for bases, cloud models, and unknown ids.
    assert reg.public_model_id("gemma4-26b-vlad-updated") == "gemma4-26b-vlad-updated"
    assert reg.public_model_id("claude-opus-4-8") == "claude-opus-4-8"
    assert reg.public_model_id("nonsense") == "nonsense"


def test_tier_twins_are_synthesized_in_code_not_declared_in_toml():
    """The 48k twins must NOT be TOML entries -- model_registry clones them in
    code from the bases, so the gguf path + quant settings live in exactly one
    place. Guards against someone re-adding a hand-typed twin block to the TOML."""
    import tomllib

    from mtgai.settings.model_registry import _MODELS_TOML

    with open(_MODELS_TOML, "rb") as f:
        raw_llm = tomllib.load(f)["llm"]
    for twin_id in ("gemma4-26b-vlad-updated-48k", "gemma4-26b-iq2m-48k"):
        assert twin_id not in raw_llm, f"{twin_id} should be code-synthesized, not in TOML"
        assert get_registry().get_llm(twin_id) is not None


def test_synthesized_twin_is_a_clone_of_its_base_with_only_ctx_changed():
    """Each synthesized twin shares every launch knob with its base except the
    fields the clone overrides: key, model_id, context_window, name, internal."""
    from dataclasses import asdict

    from mtgai.settings.model_registry import _CONTEXT_TIER_TWINS, get_registry

    reg = get_registry()
    for spec in _CONTEXT_TIER_TWINS:
        base = reg.get_llm(spec.base)
        twin = reg.get_llm(f"{spec.base}-{spec.suffix}")
        assert base is not None and twin is not None
        differing = {f for f in asdict(base) if getattr(base, f) != getattr(twin, f)}
        assert differing == {"key", "model_id", "context_window", "name", "internal"}
        assert twin.context_window == spec.context_window
        assert twin.model_id == f"{spec.base}-{spec.suffix}"


def test_synthesize_tier_twins_unknown_base_raises(monkeypatch):
    """A _CONTEXT_TIER_TWINS spec pointing at an unregistered base is a
    programming error and must fail loudly at registry load."""
    import pytest

    from mtgai.settings import model_registry as mr

    monkeypatch.setattr(
        mr,
        "_CONTEXT_TIER_TWINS",
        (mr._TierTwin(base="does-not-exist", suffix="48k", context_window=48000),),
    )
    with pytest.raises(ValueError, match="not a registered model"):
        mr.ModelRegistry.load()


def test_synthesized_twin_auto_names_when_spec_omits_name(monkeypatch):
    """A twin spec with name=None auto-tags the base name with its ctx size."""
    from mtgai.settings import model_registry as mr

    monkeypatch.setattr(
        mr,
        "_CONTEXT_TIER_TWINS",
        (mr._TierTwin(base="gemma4-26b-iq2m", suffix="24k", context_window=24000),),
    )
    reg = mr.ModelRegistry.load()
    base = reg.get_llm("gemma4-26b-iq2m")
    twin = reg.get_llm("gemma4-26b-iq2m-24k")
    assert base is not None and twin is not None
    assert twin.name == f"{base.name} (24k ctx)"


def test_anthropic_entries_are_current():
    """The Anthropic entries track the shipped models: Opus is 4.8 (the latest),
    Sonnet 4.6 and Haiku 4.5 stay current. Guards against a stale model_id
    silently pinning an older generation."""
    reg = get_registry()
    opus = reg.get_llm("opus")
    sonnet = reg.get_llm("sonnet")
    haiku = reg.get_llm("haiku")
    assert opus is not None and opus.model_id == "claude-opus-4-8"
    assert sonnet is not None and sonnet.model_id == "claude-sonnet-4-6"
    assert haiku is not None and haiku.model_id == "claude-haiku-4-5-20251001"
    # Opus 4.8 pricing (no long-context premium).
    assert (opus.input_price, opus.output_price) == (5.00, 25.00)


def test_effort_levels_drive_supports_effort_and_tier_gating():
    """effort_levels is the single source of truth: supports_effort is derived
    from it, xhigh/max are Opus-only, Sonnet caps at high, Haiku/local take none."""
    reg = get_registry()
    opus = reg.get_llm("opus")
    sonnet = reg.get_llm("sonnet")
    haiku = reg.get_llm("haiku")
    local = reg.get_llm("gemma4-26b-vlad-updated")
    assert opus is not None and sonnet is not None and haiku is not None and local is not None
    assert opus.effort_levels == ("low", "medium", "high", "xhigh", "max")
    assert sonnet.effort_levels == ("low", "medium", "high")
    assert haiku.effort_levels == ()
    assert local.effort_levels == ()
    # supports_effort is derived, never hand-set in TOML.
    assert opus.supports_effort is True
    assert sonnet.supports_effort is True
    assert haiku.supports_effort is False
    assert local.supports_effort is False


def test_invalid_effort_level_raises(tmp_path):
    """A typo'd effort level must fail loudly at load rather than silently
    offering a level the API would 400 on."""
    import pytest

    from mtgai.settings.model_registry import ModelRegistry

    toml = tmp_path / "bad.toml"
    toml.write_text(
        "[llm.x]\n"
        'name = "X"\n'
        'provider = "anthropic"\n'
        'model_id = "x"\n'
        'effort_levels = ["low", "ultra"]\n'
    )
    with pytest.raises(ValueError, match="invalid effort_levels"):
        ModelRegistry.load(toml)


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
