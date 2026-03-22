"""Per-stage model assignments with presets and profile save/load.

The settings module is the bridge between the model registry (what's available)
and the pipeline modules (what they actually use).  Each LLM-using stage gets
a model key, and convenience functions translate that into the API model_id
that ``generate_with_tool`` expects.

Settings are saved as TOML profiles in ``output/settings/``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from mtgai.settings.model_registry import get_registry

logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path("C:/Programming/MTGAI/output")
SETTINGS_DIR = OUTPUT_ROOT / "settings"

# ---------------------------------------------------------------------------
# Stage definitions — which stages use LLMs / image-gen
# ---------------------------------------------------------------------------

# stage_id -> human-readable name (only stages that use models)
LLM_STAGE_NAMES: dict[str, str] = {
    "theme_extract": "Theme Extraction",
    "mechanics": "Mechanic Generation",
    "archetypes": "Archetype Generation",
    "reprints": "Reprint Selection",
    "card_gen": "Card Generation",
    "balance": "Balance Analysis",
    "skeleton_rev": "Skeleton Revision",
    "ai_review": "AI Design Review",
    "art_prompts": "Art Prompt Generation",
    "art_select": "Art Selection",
}

IMAGE_STAGE_NAMES: dict[str, str] = {
    "char_portraits": "Character Portraits",
    "art_gen": "Art Generation",
}

# ---------------------------------------------------------------------------
# Default assignments (matching current hardcoded behaviour)
# ---------------------------------------------------------------------------

DEFAULT_LLM_ASSIGNMENTS: dict[str, str] = {
    "theme_extract": "haiku",
    "mechanics": "sonnet",
    "archetypes": "sonnet",
    "reprints": "haiku",
    "card_gen": "opus",
    "balance": "sonnet",
    "skeleton_rev": "opus",
    "ai_review": "opus",
    "art_prompts": "haiku",
    "art_select": "haiku",
}

DEFAULT_IMAGE_ASSIGNMENTS: dict[str, str] = {
    "char_portraits": "flux-local",
    "art_gen": "flux-local",
}

DEFAULT_EFFORT: dict[str, str] = {
    "card_gen": "max",
    "ai_review": "max",
}

# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

PRESETS: dict[str, dict] = {
    "recommended": {
        "llm": {
            "theme_extract": "haiku",
            "mechanics": "sonnet",
            "archetypes": "sonnet",
            "reprints": "haiku",
            "card_gen": "opus",
            "balance": "sonnet",
            "skeleton_rev": "opus",
            "ai_review": "opus",
            "art_prompts": "haiku",
            "art_select": "haiku",
        },
        "image": {
            "char_portraits": "flux-local",
            "art_gen": "flux-local",
        },
        "effort": {
            "card_gen": "max",
            "ai_review": "max",
        },
    },
    "all-haiku": {
        "llm": {k: "haiku" for k in DEFAULT_LLM_ASSIGNMENTS},
        "image": dict(DEFAULT_IMAGE_ASSIGNMENTS),
        "effort": {},
    },
    "all-local": {
        "llm": {
            **{k: "qwen-14b" for k in DEFAULT_LLM_ASSIGNMENTS},
            "art_select": "qwen3-vl-8b",  # vision-capable local model
        },
        "image": dict(DEFAULT_IMAGE_ASSIGNMENTS),
        "effort": {},
    },
}

# ---------------------------------------------------------------------------
# Settings model
# ---------------------------------------------------------------------------


class ModelSettings(BaseModel):
    """Per-stage model assignments — the active configuration."""

    llm_assignments: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_LLM_ASSIGNMENTS))
    image_assignments: dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_IMAGE_ASSIGNMENTS)
    )
    effort_overrides: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_EFFORT))

    def get_llm_model_id(self, stage_id: str) -> str:
        """Resolve the API model_id for a pipeline stage.

        Returns the model_id string that ``generate_with_tool`` expects.
        Falls back to the default assignment if the stage isn't configured.
        """
        key = self.llm_assignments.get(stage_id, DEFAULT_LLM_ASSIGNMENTS.get(stage_id, "sonnet"))
        registry = get_registry()
        model = registry.get_llm(key)
        if model is None:
            logger.warning(
                "Unknown model key %r for stage %s, falling back to sonnet", key, stage_id
            )
            model = registry.get_llm("sonnet")
            if model is None:
                return "claude-sonnet-4-6"
        return model.model_id

    def get_image_model_key(self, stage_id: str) -> str:
        """Get the image model key for a stage."""
        return self.image_assignments.get(
            stage_id, DEFAULT_IMAGE_ASSIGNMENTS.get(stage_id, "flux-local")
        )

    def get_effort(self, stage_id: str) -> str | None:
        """Get the effort level for a stage (None if not set or unsupported)."""
        effort = self.effort_overrides.get(stage_id)
        if not effort:
            return None
        # Only return effort if the assigned model supports it
        key = self.llm_assignments.get(stage_id)
        if key:
            registry = get_registry()
            model = registry.get_llm(key)
            if model and not model.supports_effort:
                return None
        return effort

    def save(self, path: Path | None = None, name: str = "current") -> Path:
        """Save settings to a TOML file."""
        import tomlkit

        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        path = path or SETTINGS_DIR / f"{name}.toml"

        doc = tomlkit.document()
        doc.add(tomlkit.comment("MTGAI model settings profile"))
        doc.add(tomlkit.nl())
        doc.add("llm_assignments", dict(self.llm_assignments))
        doc.add(tomlkit.nl())
        doc.add("image_assignments", dict(self.image_assignments))
        if any(self.effort_overrides.values()):
            doc.add(tomlkit.nl())
            doc.add("effort_overrides", {k: v for k, v in self.effort_overrides.items() if v})

        path.write_text(tomlkit.dumps(doc), encoding="utf-8")
        logger.info("Saved model settings to %s", path)
        return path

    @classmethod
    def load_from_file(cls, path: Path) -> ModelSettings:
        """Load settings from a TOML file."""
        import tomllib

        with open(path, "rb") as f:
            data = tomllib.load(f)

        return cls(
            llm_assignments=data.get("llm_assignments", {}),
            image_assignments=data.get("image_assignments", {}),
            effort_overrides=data.get("effort_overrides", {}),
        )

    @classmethod
    def from_preset(cls, preset_name: str) -> ModelSettings:
        """Create settings from a named preset."""
        preset = PRESETS.get(preset_name)
        if preset is None:
            raise ValueError(f"Unknown preset: {preset_name!r}. Available: {list(PRESETS)}")
        return cls(
            llm_assignments=dict(preset["llm"]),
            image_assignments=dict(preset["image"]),
            effort_overrides=dict(preset.get("effort", {})),
        )

    def to_ui_dict(self) -> dict:
        """Serialize for the settings UI (includes resolved model info)."""
        registry = get_registry()
        llm_stages = []
        for stage_id, stage_name in LLM_STAGE_NAMES.items():
            key = self.llm_assignments.get(stage_id, DEFAULT_LLM_ASSIGNMENTS.get(stage_id))
            model = registry.get_llm(key) if key else None
            llm_stages.append(
                {
                    "stage_id": stage_id,
                    "stage_name": stage_name,
                    "model_key": key or "",
                    "model_name": model.name if model else "Unknown",
                    "effort": self.effort_overrides.get(stage_id, ""),
                }
            )

        image_stages = []
        for stage_id, stage_name in IMAGE_STAGE_NAMES.items():
            key = self.image_assignments.get(stage_id, DEFAULT_IMAGE_ASSIGNMENTS.get(stage_id))
            model = registry.get_image(key) if key else None
            image_stages.append(
                {
                    "stage_id": stage_id,
                    "stage_name": stage_name,
                    "model_key": key or "",
                    "model_name": model.name if model else "Unknown",
                }
            )

        return {
            "llm_stages": llm_stages,
            "image_stages": image_stages,
            "effort_overrides": dict(self.effort_overrides),
        }


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_current: ModelSettings | None = None


def get_settings() -> ModelSettings:
    """Return the active model settings.

    Loads from ``output/settings/current.toml`` on first call.
    Falls back to defaults if no saved settings exist.
    """
    global _current
    if _current is None:
        current_path = SETTINGS_DIR / "current.toml"
        if current_path.exists():
            try:
                _current = ModelSettings.load_from_file(current_path)
                logger.info("Loaded model settings from %s", current_path)
            except Exception:
                logger.warning("Failed to load settings, using defaults", exc_info=True)
                _current = ModelSettings()
        else:
            _current = ModelSettings()
    return _current


def apply_settings(settings: ModelSettings) -> None:
    """Set new active settings and persist to disk."""
    global _current
    _current = settings
    settings.save(name="current")


def list_profiles() -> list[str]:
    """List saved profile names (without extension)."""
    if not SETTINGS_DIR.exists():
        return []
    return sorted(p.stem for p in SETTINGS_DIR.glob("*.toml") if p.stem != "current")


# ---------------------------------------------------------------------------
# Convenience functions used by pipeline modules
# ---------------------------------------------------------------------------


def get_llm_model(stage_id: str) -> str:
    """Get the API model_id for a pipeline stage. Shorthand for modules."""
    return get_settings().get_llm_model_id(stage_id)


def get_image_model(stage_id: str) -> str:
    """Get the image model key for a pipeline stage."""
    return get_settings().get_image_model_key(stage_id)


def get_effort(stage_id: str) -> str | None:
    """Get the effort level for a pipeline stage."""
    return get_settings().get_effort(stage_id)
