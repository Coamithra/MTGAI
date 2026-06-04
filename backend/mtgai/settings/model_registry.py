"""Model registry — loads available models from models.toml.

The registry is a singleton loaded once from the TOML file shipped alongside
this module.  Users can add custom models by editing models.toml directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from pathlib import Path

logger = logging.getLogger(__name__)

_MODELS_TOML = Path(__file__).resolve().parent / "models.toml"

# Valid ``thinking`` values for a llamacpp entry — mirror llmfacade's
# ThinkingMode values. Validated at load so a TOML typo fails loudly instead of
# silently disabling reasoning (an unrecognised value reaches llama.cpp as "no
# enable_thinking kwarg", i.e. thinking quietly off, with no error).
_VALID_THINKING_MODES = frozenset({"adaptive", "adaptive_summarized", "disabled"})

# Valid ``effort_levels`` entries (low→high), mirroring the Anthropic effort
# parameter. ``xhigh``/``max`` are Opus-tier only; the per-model TOML list says
# which a given model actually accepts. Validated at load so a typo fails loudly
# instead of silently offering a level the API would 400 on.
_VALID_EFFORT_LEVELS = frozenset({"low", "medium", "high", "xhigh", "max"})


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMModel:
    """An available LLM model."""

    key: str  # short identifier, e.g. "opus"
    name: str  # display name
    provider: str  # "anthropic" or "llamacpp"
    model_id: str  # API model identifier (llama-swap YAML key for llamacpp)
    tier: int = 0  # quality ranking (higher = better)
    input_price: float = 0.0  # per 1M tokens
    output_price: float = 0.0
    # Effort parameter levels this model accepts, ordered low→high (last is the
    # ceiling). Empty = no effort support. Single source of truth: the registry
    # derives ``supports_effort`` from this, and the wizard builds the effort
    # dropdown from it so a model is never offered a level it would 400 on.
    effort_levels: tuple[str, ...] = ()
    # Derived from ``effort_levels`` at load (non-empty → True); not set in TOML.
    supports_effort: bool = False
    supports_vision: bool = False
    supports_caching: bool = False
    context_window: int = 200_000
    # llamacpp launch knobs (managed-mode only). Ignored by other providers.
    gguf_path: str | None = None
    cache_type_k: str | None = None
    cache_type_v: str | None = None
    n_gpu_layers: int | None = None
    # llama-server autofit (managed-mode only). ``True`` (the default, matching
    # llmfacade) launches with ``--fit on``, so llama-server trims offload /
    # context at spawn to fit available VRAM — an over-budget ``n_gpu_layers=-1``
    # entry then spills to CPU/RAM rather than OOMing. Set ``false`` to launch
    # ``--fit off`` (no autofit), which also restores the hard VRAM-risk warning
    # at registry load (see ``vram_estimate.check_vram_risk``).
    fit: bool = True
    # llamacpp thinking/reasoning knobs (managed-mode only). ``thinking`` takes
    # an llmfacade ThinkingMode value — "adaptive" (reason) or "disabled".
    # ``thinking_style`` is an optional override (a ThinkingStyle value, e.g.
    # "template_kwarg"); left unset, llmfacade auto-detects it from the GGUF.
    thinking: str | None = None
    thinking_style: str | None = None
    # True for context-length tier twins synthesized in code (see
    # _synthesize_tier_twins). Internal models resolve by key/model_id for
    # launch + token-budget + the tok/s poller, but are hidden from every
    # user-facing list (list_llm / to_dict) — the user picks a base model and
    # get_llm_model_id() swaps in the right tier per stage.
    internal: bool = False


@dataclass(frozen=True)
class ImageModel:
    """An available image-generation model."""

    key: str
    name: str
    provider: str  # "comfyui", "gemini", "openai"
    # Provider-side model id passed to llmfacade's generate_image (e.g.
    # "gpt-image-1", "gemini-2.5-flash-image"). None for the local ComfyUI
    # path, which loads its model from the bundled workflow, not by id.
    model_id: str | None = None
    cost_per_image: float = 0.0
    implemented: bool = False


# ---------------------------------------------------------------------------
# Context-length tier twins (synthesized in code, not declared in models.toml)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _TierTwin:
    """A context-length tier twin to synthesize from a base ``[llm.*]`` entry.

    A twin is the *same* GGUF/quant/offload/thinking as its base — only the
    llama-server ``--ctx-size`` (``context_window``) shrinks, so a downstream
    stage that never sees a big input gets a smaller KV pre-allocation and frees
    VRAM. See the context-length-tiers note in models.toml and
    learnings/ctx-tier-sweet-spots.md.

    Kept in code rather than config because it carries no real design decision
    beyond "which base, what window": ``model_registry`` clones the base entry
    via ``dataclasses.replace``, so the gguf path + quant knobs live in exactly
    one place and can never drift. The twin's key/model_id is ``<base>-<suffix>``
    (distinct, because two ``--ctx-size`` servers must be distinct llama-swap
    backends); ``name`` defaults to the base name tagged with the new window.
    """

    base: str  # base registry key to clone
    suffix: str  # appended to the base key/model_id, e.g. "48k"
    context_window: int
    name: str | None = None


# The 48k DOWNSTREAM tier. These are internal: get_llm_model_id() swaps a base
# model for its twin on every stage except theme_extract (_FULL_CONTEXT_STAGES),
# so the user never picks one. One per tier-able base model.
_CONTEXT_TIER_TWINS: tuple[_TierTwin, ...] = (
    _TierTwin(
        base="gemma4-26b-vlad-updated",
        suffix="48k",
        context_window=48000,
        name="Gemma 4 26B Vlad-Updated (Local, 48k downstream tier)",
    ),
    _TierTwin(
        base="gemma4-26b-iq2m",
        suffix="48k",
        context_window=48000,
        name="Gemma 4 26B Unsloth UD-IQ2_M (Local, 48k — fully GPU-resident)",
    ),
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass
class ModelRegistry:
    """Container for all available models, loaded from TOML."""

    llm_models: dict[str, LLMModel] = field(default_factory=dict)
    image_models: dict[str, ImageModel] = field(default_factory=dict)
    # Reverse lookup: API model_id -> registry key
    _model_id_to_key: dict[str, str] = field(default_factory=dict)
    # base registry key -> its downstream context-tier twin key (see
    # _synthesize_tier_twins / downstream_twin).
    _base_twin_key: dict[str, str] = field(default_factory=dict)
    # internal twin model_id -> its public base model_id (see public_model_id).
    _twin_to_base_model_id: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> ModelRegistry:
        """Load model definitions from a TOML file."""
        import tomllib

        path = path or _MODELS_TOML
        with open(path, "rb") as f:
            data = tomllib.load(f)

        registry = cls()

        for key, raw in data.get("llm", {}).items():
            thinking = raw.get("thinking")
            if thinking is not None and thinking not in _VALID_THINKING_MODES:
                raise ValueError(
                    f"models.toml [llm.{key}]: invalid thinking={thinking!r}; "
                    f"expected one of {sorted(_VALID_THINKING_MODES)} or omit it"
                )
            effort_levels = tuple(raw.get("effort_levels", ()))
            bad_levels = [lvl for lvl in effort_levels if lvl not in _VALID_EFFORT_LEVELS]
            if bad_levels:
                raise ValueError(
                    f"models.toml [llm.{key}]: invalid effort_levels {bad_levels}; "
                    f"expected a subset of {sorted(_VALID_EFFORT_LEVELS)} or omit it"
                )
            model = LLMModel(
                key=key,
                name=raw["name"],
                provider=raw["provider"],
                model_id=raw["model_id"],
                tier=raw.get("tier", 0),
                input_price=raw.get("input_price", 0.0),
                output_price=raw.get("output_price", 0.0),
                effort_levels=effort_levels,
                # Derived, not read from TOML — keeps effort capability in one place.
                supports_effort=bool(effort_levels),
                supports_vision=raw.get("supports_vision", False),
                supports_caching=raw.get("supports_caching", False),
                context_window=raw.get("context_window", 200_000),
                gguf_path=raw.get("gguf_path"),
                cache_type_k=raw.get("cache_type_k"),
                cache_type_v=raw.get("cache_type_v"),
                n_gpu_layers=raw.get("n_gpu_layers"),
                fit=raw.get("fit", True),
                thinking=thinking,
                thinking_style=raw.get("thinking_style"),
            )
            registry.llm_models[key] = model
            registry._model_id_to_key[model.model_id] = key

        for key, raw in data.get("image", {}).items():
            model = ImageModel(
                key=key,
                name=raw["name"],
                provider=raw["provider"],
                model_id=raw.get("model_id"),
                cost_per_image=raw.get("cost_per_image", 0.0),
                implemented=raw.get("implemented", False),
            )
            registry.image_models[key] = model

        # Context-length tier twins are derived in code from the entries above
        # (same GGUF, smaller --ctx-size) rather than re-declared in the TOML.
        registry._synthesize_tier_twins()

        logger.info(
            "Loaded model registry: %d LLM models, %d image models",
            len(registry.llm_models),
            len(registry.image_models),
        )

        # Flag any all-GPU (n_gpu_layers=-1) llamacpp entry whose weights + KV
        # cache would overrun VRAM: WARN above 85% of free VRAM, over-budget
        # (>100% of total VRAM) logs an ERROR and — only under
        # MTGAI_VRAM_CHECK_STRICT — raises VramRiskError. Silently skipped where
        # it can't measure (gguf absent / no GPU) so it never bricks load.
        from mtgai.settings.vram_estimate import check_vram_risk

        check_vram_risk(registry.llm_models)

        return registry

    def _synthesize_tier_twins(self) -> None:
        """Materialize the ``_CONTEXT_TIER_TWINS`` into the registry.

        Each twin is a ``dataclasses.replace`` clone of its base LLMModel — so
        it inherits every launch knob automatically — with only its
        ``key``/``model_id`` (``<base>-<suffix>``, distinct so the two
        ``--ctx-size`` servers are distinct llama-swap backends),
        ``context_window``, and display ``name`` overridden. Runs after the TOML
        entries are loaded so the bases exist to clone. A spec pointing at an
        unknown base is a programming error and raises.
        """
        for spec in _CONTEXT_TIER_TWINS:
            base = self.llm_models.get(spec.base)
            if base is None:
                raise ValueError(
                    f"context-tier twin base {spec.base!r} is not a registered model "
                    f"(check _CONTEXT_TIER_TWINS against models.toml)"
                )
            twin_id = f"{spec.base}-{spec.suffix}"
            name = spec.name or f"{base.name} ({spec.context_window // 1000}k ctx)"
            twin = replace(
                base,
                key=twin_id,
                model_id=twin_id,
                context_window=spec.context_window,
                name=name,
                internal=True,
            )
            self.llm_models[twin_id] = twin
            self._model_id_to_key[twin_id] = twin_id
            self._base_twin_key[spec.base] = twin_id
            self._twin_to_base_model_id[twin_id] = base.model_id

    def public_model_id(self, model_id: str) -> str:
        """Map an internal context-tier twin id back to its public base id.

        Identity for any non-twin id. Use this wherever a model id is *stored as
        provenance or shown in the UI* (card ``model_used``, the per-stage
        rationale/response ``model_id``) so the internal ``-48k`` twin never
        surfaces — the user picked the base, and the twin is the same model at a
        smaller window. Runtime callers (launch, poller) want the twin and use
        ``get_llm_model_id`` instead.
        """
        return self._twin_to_base_model_id.get(model_id, model_id)

    def get_llm(self, key: str) -> LLMModel | None:
        """Look up an LLM model by its short key (e.g. 'opus')."""
        return self.llm_models.get(key)

    def get_llm_by_model_id(self, model_id: str) -> LLMModel | None:
        """Look up an LLM model by its API model_id (e.g. 'claude-opus-4-8')."""
        key = self._model_id_to_key.get(model_id)
        if key:
            return self.llm_models.get(key)
        return None

    def get_image(self, key: str) -> ImageModel | None:
        """Look up an image model by its short key (e.g. 'flux-local')."""
        return self.image_models.get(key)

    def downstream_twin(self, base_key: str) -> LLMModel | None:
        """The downstream context-tier twin for a base model key, or None.

        Used by ``ModelSettings.get_llm_model_id`` to swap a base model for its
        smaller-``--ctx-size`` twin on stages that don't need the full window.
        """
        twin_key = self._base_twin_key.get(base_key)
        return self.llm_models.get(twin_key) if twin_key else None

    def list_llm(self) -> list[LLMModel]:
        """User-facing LLM models, sorted by tier (highest first).

        Excludes ``internal`` context-tier twins — the user picks a base model
        and the per-stage tiering happens automatically (see ``internal``)."""
        return sorted(
            (m for m in self.llm_models.values() if not m.internal),
            key=lambda m: -m.tier,
        )

    def list_image(self) -> list[ImageModel]:
        """All image models, implemented first."""
        return sorted(
            self.image_models.values(),
            key=lambda m: (not m.implemented, m.name),
        )

    def to_dict(self) -> dict:
        """Serialize for JSON (used by the settings UI). Excludes internal
        context-tier twins so they never surface as a selectable model."""
        from dataclasses import asdict

        return {
            "llm": {k: asdict(v) for k, v in self.llm_models.items() if not v.internal},
            "image": {k: asdict(v) for k, v in self.image_models.items()},
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_registry: ModelRegistry | None = None


def get_registry() -> ModelRegistry:
    """Return the global model registry (loaded on first call)."""
    global _registry
    if _registry is None:
        _registry = ModelRegistry.load()
    return _registry


def reload_registry(path: Path | None = None) -> ModelRegistry:
    """Force-reload the registry from disk."""
    global _registry
    _registry = ModelRegistry.load(path)
    return _registry
