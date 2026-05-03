"""Model registry — loads available models from models.toml.

The registry is a singleton loaded once from the TOML file shipped alongside
this module.  Users can add custom models by editing models.toml directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_MODELS_TOML = Path(__file__).resolve().parent / "models.toml"


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
    supports_effort: bool = False
    supports_vision: bool = False
    supports_caching: bool = False
    context_window: int = 200_000
    # llamacpp launch knobs (managed-mode only). Ignored by other providers.
    gguf_path: str | None = None
    cache_type_k: str | None = None
    cache_type_v: str | None = None
    n_gpu_layers: int | None = None


@dataclass(frozen=True)
class ImageModel:
    """An available image-generation model."""

    key: str
    name: str
    provider: str  # "comfyui", "gemini", "openai"
    cost_per_image: float = 0.0
    implemented: bool = False


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

    @classmethod
    def load(cls, path: Path | None = None) -> ModelRegistry:
        """Load model definitions from a TOML file."""
        import tomllib

        path = path or _MODELS_TOML
        with open(path, "rb") as f:
            data = tomllib.load(f)

        registry = cls()

        for key, raw in data.get("llm", {}).items():
            model = LLMModel(
                key=key,
                name=raw["name"],
                provider=raw["provider"],
                model_id=raw["model_id"],
                tier=raw.get("tier", 0),
                input_price=raw.get("input_price", 0.0),
                output_price=raw.get("output_price", 0.0),
                supports_effort=raw.get("supports_effort", False),
                supports_vision=raw.get("supports_vision", False),
                supports_caching=raw.get("supports_caching", False),
                context_window=raw.get("context_window", 200_000),
                gguf_path=raw.get("gguf_path"),
                cache_type_k=raw.get("cache_type_k"),
                cache_type_v=raw.get("cache_type_v"),
                n_gpu_layers=raw.get("n_gpu_layers"),
            )
            registry.llm_models[key] = model
            registry._model_id_to_key[model.model_id] = key

        for key, raw in data.get("image", {}).items():
            model = ImageModel(
                key=key,
                name=raw["name"],
                provider=raw["provider"],
                cost_per_image=raw.get("cost_per_image", 0.0),
                implemented=raw.get("implemented", False),
            )
            registry.image_models[key] = model

        logger.info(
            "Loaded model registry: %d LLM models, %d image models",
            len(registry.llm_models),
            len(registry.image_models),
        )
        return registry

    def get_llm(self, key: str) -> LLMModel | None:
        """Look up an LLM model by its short key (e.g. 'opus')."""
        return self.llm_models.get(key)

    def get_llm_by_model_id(self, model_id: str) -> LLMModel | None:
        """Look up an LLM model by its API model_id (e.g. 'claude-opus-4-6')."""
        key = self._model_id_to_key.get(model_id)
        if key:
            return self.llm_models.get(key)
        return None

    def get_image(self, key: str) -> ImageModel | None:
        """Look up an image model by its short key (e.g. 'flux-local')."""
        return self.image_models.get(key)

    def list_llm(self) -> list[LLMModel]:
        """All LLM models sorted by tier (highest first)."""
        return sorted(self.llm_models.values(), key=lambda m: -m.tier)

    def list_image(self) -> list[ImageModel]:
        """All image models, implemented first."""
        return sorted(
            self.image_models.values(),
            key=lambda m: (not m.implemented, m.name),
        )

    def to_dict(self) -> dict:
        """Serialize for JSON (used by the settings UI)."""
        from dataclasses import asdict

        return {
            "llm": {k: asdict(v) for k, v in self.llm_models.items()},
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
