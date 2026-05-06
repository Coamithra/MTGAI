"""Per-stage model assignments — in-memory state plus a small global file.

The active project's :class:`ModelSettings` lives in process memory on the
:class:`~mtgai.runtime.active_project.ProjectState` pointer; the .mtg file
the user opens (managed via the browser File System Access API) is the
persistent artifact. Server endpoints read + mutate the active project's
settings via :func:`get_active_settings` / :func:`apply_settings`.

A separate ``output/settings/global.toml`` carries cross-set defaults
(currently just the *default preset* used to seed new projects). Profiles
(reusable assignment templates) live alongside as
``output/settings/<name>.toml``; the legacy ``output/settings/current.toml``
is read once on first boot to bootstrap a default profile and is then
ignored.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from mtgai.settings.model_registry import get_registry

if TYPE_CHECKING:
    from tomlkit import TOMLDocument

logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path("C:/Programming/MTGAI/output")
SETTINGS_DIR = OUTPUT_ROOT / "settings"

GLOBAL_TOML = SETTINGS_DIR / "global.toml"
LEGACY_CURRENT_TOML = SETTINGS_DIR / "current.toml"

# ---------------------------------------------------------------------------
# Stage definitions — which stages use LLMs / image-gen
# ---------------------------------------------------------------------------

# stage_id -> human-readable name (only stages that use models)
LLM_STAGE_NAMES: dict[str, str] = {
    "theme_extract": "Theme Extraction",
    "mechanics": "Mechanic Generation",
    "archetypes": "Archetype Generation",
    "reprints": "Reprint Selection",
    "lands": "Land Generation",
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
    "lands": "haiku",
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

# Stages that default to "review" (pause for human input) when a set has no
# explicit override saved. Users can still uncheck them on Project Settings.
DEFAULT_BREAK_POINTS: dict[str, str] = {
    "human_card_review": "review",
    "human_art_review": "review",
    "human_final_review": "review",
}

# ---------------------------------------------------------------------------
# Built-in presets
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
            # Vlad IQ4_XS is the long-context winner on 12 GB VRAM (TC-1f).
            # llamacpp managed mode handles per-server KV-cache quantization,
            # so cache_type_k=q8_0 is set on the model entry directly — no
            # global env var needed.
            "theme_extract": "gemma4-26b-vram-dynamic",
            "mechanics": "gemma4-26b-vram-dynamic",
            "archetypes": "gemma4-26b-vram-dynamic",
            "reprints": "gemma4-26b-vram-dynamic",
            "lands": "gemma4-26b-vram-dynamic",
            "card_gen": "gemma4-26b-vram-dynamic",
            "balance": "gemma4-26b-vram-dynamic",
            "skeleton_rev": "gemma4-26b-vram-dynamic",
            "ai_review": "gemma4-26b-vram-dynamic",
            "art_prompts": "gemma4-26b-vram-dynamic",
            "art_select": "gemma4-26b-vram-dynamic",
        },
        "image": dict(DEFAULT_IMAGE_ASSIGNMENTS),
        "effort": {},
    },
}

BUILTIN_PRESET_NAMES = frozenset(PRESETS)
RESERVED_PROFILE_NAMES = frozenset({"global", "current"})

_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def validate_profile_name(name: str) -> str:
    """Sanity-check a user-supplied profile name.

    Names round-trip through ``<SETTINGS_DIR>/<name>.toml`` so anything
    outside ``[a-zA-Z0-9_-]+`` is rejected up front — that closes path
    traversal on every endpoint that takes a name.

    Reserved names are checked case-insensitively because Windows is
    case-insensitive on disk: a profile named ``Global`` would otherwise
    overwrite ``global.toml`` (the default-preset file).
    """
    if not isinstance(name, str):
        raise ValueError("Profile name must be a string")
    if not _PROFILE_NAME_RE.fullmatch(name):
        raise ValueError(f"Invalid profile name {name!r}: must match [a-zA-Z0-9_-]+")
    if name.lower() in RESERVED_PROFILE_NAMES:
        raise ValueError(f"Profile name {name!r} is reserved")
    return name


# ---------------------------------------------------------------------------
# Settings model
# ---------------------------------------------------------------------------


# Theme input source kinds. ``"none"`` is the brand-new state (no input
# chosen yet — the Project Settings Start button stays disabled).
# ``"existing"`` means the set already has a theme.json that was written
# previously (no upload needed). ``"pdf"`` and ``"text"`` reference the
# in-memory upload cache via ``upload_id``.
ThemeInputKind = Literal["none", "pdf", "text", "existing"]


class SetParams(BaseModel):
    """Numeric / structural parameters for a set.

    Lifted out of theme.json — theme.json now owns content-extracted fields
    only (constraints, card requests, setting prose). These numbers guide
    extraction prompts but are not extracted from prose.
    """

    set_name: str = ""
    set_size: int = 60
    mechanic_count: int = 3


class ThemeInputSource(BaseModel):
    """Bookmark for the upload that seeded this set's theme extraction.

    The actual file content lives in the server's in-memory upload cache
    (``_upload_cache`` in ``pipeline.server``). This block records *what*
    was chosen for resumability + audit. Its fields are populated in
    response to the Project Settings tab's upload widget; ``"existing"``
    is the bootstrap state for sets whose theme.json predates this card.
    """

    kind: ThemeInputKind = "none"
    filename: str | None = None
    upload_id: str | None = None
    char_count: int | None = None
    uploaded_at: datetime | None = None


class ModelSettings(BaseModel):
    """Per-stage model assignments — the active configuration for one set."""

    llm_assignments: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_LLM_ASSIGNMENTS))
    image_assignments: dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_IMAGE_ASSIGNMENTS)
    )
    effort_overrides: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_EFFORT))
    # Per-stage break-point overrides (stage_id -> "auto" | "review").
    # Stays empty until the Project Settings tab toggles a checkbox.
    # Locked-on `human_*` stages are NOT written here — the engine
    # enforces those at pipeline-create time via STAGE_DEFINITIONS.
    break_points: dict[str, str] = Field(default_factory=dict)
    # Set parameters + theme input both live here so settings.toml is the
    # single source of truth for everything Project Settings owns.
    set_params: SetParams = Field(default_factory=SetParams)
    theme_input: ThemeInputSource = Field(default_factory=ThemeInputSource)
    # User-chosen folder for generated artifacts (cards/, theme.json,
    # pipeline-state.json, art, renders). Empty string until the user picks
    # one on Project Settings. In Phase 1 the field is captured + persisted
    # but not yet wired through stage runners — those still write under
    # ``output/sets/<CODE>/``. Phase 2 routes outputs into this folder.
    asset_folder: str = ""

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

    def to_toml_doc(self, *, profile_only: bool = False) -> TOMLDocument:
        """Build a tomlkit document for this settings instance.

        ``profile_only`` strips per-set fields (``set_params``,
        ``theme_input``) so the document is a portable template — used
        when saving a profile to the global library. Break points stay
        because they're a meaningful part of a workflow profile (§6.8).
        """
        import tomlkit

        doc = tomlkit.document()
        doc.add(tomlkit.comment("MTGAI model settings"))
        doc.add(tomlkit.nl())
        doc.add("llm_assignments", dict(self.llm_assignments))
        doc.add(tomlkit.nl())
        doc.add("image_assignments", dict(self.image_assignments))
        if any(self.effort_overrides.values()):
            doc.add(tomlkit.nl())
            doc.add("effort_overrides", {k: v for k, v in self.effort_overrides.items() if v})
        if self.break_points:
            doc.add(tomlkit.nl())
            doc.add("break_points", dict(self.break_points))
        if not profile_only:
            if self.asset_folder:
                doc.add(tomlkit.nl())
                doc.add("asset_folder", self.asset_folder)
            doc.add(tomlkit.nl())
            doc.add("set_params", self.set_params.model_dump())
            if self.theme_input.kind != "none":
                # ThemeInputSource carries a datetime which tomlkit serialises
                # natively; ``mode="json"`` would coerce to ISO string and
                # tomlkit would re-parse it back to datetime on read, but
                # going through the native path keeps the file readable.
                ti = self.theme_input.model_dump()
                # Drop None values so they don't show as `key = nil` (tomlkit
                # rejects None) — load_from_file's getattr defaults handle
                # the absence cleanly.
                ti = {k: v for k, v in ti.items() if v is not None}
                doc.add(tomlkit.nl())
                doc.add("theme_input", ti)
        return doc

    def write_toml(self, path: Path) -> Path:
        """Write the settings to a TOML file (parent dirs are created)."""
        import tomlkit

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tomlkit.dumps(self.to_toml_doc()), encoding="utf-8")
        return path

    def save_profile(self, name: str) -> Path:
        """Save these settings as a named profile in the global library.

        Per design §6.8, profiles capture model assignments + break
        points but exclude per-set values (set parameters, theme input).
        """
        import tomlkit

        name = validate_profile_name(name)
        path = SETTINGS_DIR / f"{name}.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tomlkit.dumps(self.to_toml_doc(profile_only=True)), encoding="utf-8")
        logger.info("Saved profile %r to %s", name, path)
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
            break_points=data.get("break_points", {}),
            set_params=SetParams(**data.get("set_params", {})),
            theme_input=ThemeInputSource(**data.get("theme_input", {})),
            asset_folder=data.get("asset_folder", "") or "",
        )

    @classmethod
    def from_preset(cls, preset_name: str) -> ModelSettings:
        """Create settings from a named built-in preset or saved profile.

        Reserved names (``global``, ``current``) are rejected — those files
        are not user profiles, and resolving them would silently produce
        an empty ``ModelSettings`` (every field falling through to its
        default factory) which hides configuration mistakes.
        """
        if preset_name in RESERVED_PROFILE_NAMES:
            raise ValueError(
                f"Preset name {preset_name!r} is reserved (global.toml / current.toml "
                "are not user-facing profiles)"
            )
        if preset_name in PRESETS:
            preset = PRESETS[preset_name]
            return cls(
                llm_assignments=dict(preset["llm"]),
                image_assignments=dict(preset["image"]),
                effort_overrides=dict(preset.get("effort", {})),
            )
        # Fall back to saved profile
        profile_path = SETTINGS_DIR / f"{preset_name}.toml"
        if profile_path.exists():
            return cls.load_from_file(profile_path)
        raise ValueError(
            f"Unknown preset {preset_name!r}. Built-ins: {sorted(PRESETS)}; "
            f"saved profiles: {list_profiles()}"
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
            "break_points": dict(self.break_points),
            "set_params": self.set_params.model_dump(),
            "theme_input": self.theme_input.model_dump(mode="json"),
            "asset_folder": self.asset_folder,
        }


# ---------------------------------------------------------------------------
# Global settings (cross-set defaults)
# ---------------------------------------------------------------------------


class GlobalSettings(BaseModel):
    """Cross-set defaults persisted to ``output/settings/global.toml``.

    Currently only carries the *default preset* used to seed new sets.
    """

    default_preset: str = "recommended"

    def write(self, path: Path | None = None) -> Path:
        """Persist this global-settings instance to disk."""
        import tomlkit

        # Resolve default at call time so test monkeypatches of GLOBAL_TOML
        # are honoured.
        if path is None:
            path = GLOBAL_TOML
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = tomlkit.document()
        doc.add(tomlkit.comment("MTGAI cross-set defaults"))
        doc.add(tomlkit.nl())
        doc.add("default_preset", self.default_preset)
        path.write_text(tomlkit.dumps(doc), encoding="utf-8")
        return path

    @classmethod
    def load_from_file(cls, path: Path | None = None) -> GlobalSettings:
        import tomllib

        if path is None:
            path = GLOBAL_TOML
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(default_preset=data.get("default_preset", "recommended"))


# ---------------------------------------------------------------------------
# Caches
# ---------------------------------------------------------------------------

# Global settings, lazy-loaded.
_global_cache: GlobalSettings | None = None


def _ensure_global_settings() -> GlobalSettings:
    """Load (or create) the global settings file.

    On first creation: if the legacy ``current.toml`` exists, copy it into
    ``imported.toml`` and point ``default_preset`` at it. Otherwise default
    to ``"recommended"``.
    """
    global _global_cache
    if _global_cache is not None:
        return _global_cache

    if GLOBAL_TOML.exists():
        try:
            _global_cache = GlobalSettings.load_from_file(GLOBAL_TOML)
            return _global_cache
        except Exception:
            logger.warning("Failed to load %s, recreating", GLOBAL_TOML, exc_info=True)

    if LEGACY_CURRENT_TOML.exists():
        try:
            imported = ModelSettings.load_from_file(LEGACY_CURRENT_TOML)
            imported_path = SETTINGS_DIR / "imported.toml"
            if not imported_path.exists():
                imported.write_toml(imported_path)
                logger.info(
                    "Bootstrapped global default from %s -> %s",
                    LEGACY_CURRENT_TOML,
                    imported_path,
                )
            _global_cache = GlobalSettings(default_preset="imported")
        except Exception:
            logger.warning(
                "Could not import legacy current.toml; falling back to 'recommended'",
                exc_info=True,
            )
            _global_cache = GlobalSettings()
    else:
        _global_cache = GlobalSettings()

    _global_cache.write()
    return _global_cache


def get_global_settings() -> GlobalSettings:
    """Return the cross-set default settings (lazy-loaded, cached)."""
    return _ensure_global_settings()


def apply_global_settings(settings: GlobalSettings) -> None:
    """Replace the cached global settings and persist to disk.

    The ``default_preset`` is checked against built-in presets and the
    saved-profile library; an unknown name would silently fall back to
    defaults on every new set, so we surface it loudly here.
    """
    name = settings.default_preset
    if name in RESERVED_PROFILE_NAMES:
        raise ValueError(f"default_preset {name!r} is reserved; pick a built-in or saved profile")
    if name not in PRESETS and name not in list_profiles():
        raise ValueError(
            f"Unknown default_preset {name!r}. Built-ins: {sorted(PRESETS)}; "
            f"saved profiles: {list_profiles()}"
        )

    global _global_cache
    _global_cache = settings
    settings.write()


# ---------------------------------------------------------------------------
# Active-project settings
# ---------------------------------------------------------------------------


def get_active_settings() -> ModelSettings:
    """Return the open project's :class:`ModelSettings`.

    Thin wrapper over :func:`mtgai.runtime.active_project.require_active_project`
    so callers that only need the settings (not the surrounding
    ``ProjectState``) don't have to import the runtime helper directly.
    Raises :class:`mtgai.io.asset_paths.NoAssetFolderError` when no
    project is open — endpoint handlers translate that to a 409.
    """
    from mtgai.runtime.active_project import require_active_project

    return require_active_project().settings


def apply_settings(settings: ModelSettings) -> None:
    """Update the active project's :class:`ModelSettings` to ``settings``.

    Replaces the pointer's settings wholesale so subsequent
    :func:`set_artifact_dir` / :func:`get_active_settings` calls see the
    new values immediately. Persistence is the user's responsibility —
    they save the .mtg file via the browser File System Access API; this
    module no longer writes per-project TOML to disk. Raises if no
    project is open.
    """
    from mtgai.runtime import active_project

    proj = active_project.require_active_project()
    active_project.write_active_project(proj.model_copy(update={"settings": settings}))


def list_profiles() -> list[str]:
    """List saved profile names (without extension).

    Excludes ``global.toml`` and the legacy ``current.toml`` — those are
    not user-facing profiles.
    """
    if not SETTINGS_DIR.exists():
        return []
    return sorted(
        p.stem for p in SETTINGS_DIR.glob("*.toml") if p.stem not in RESERVED_PROFILE_NAMES
    )


# ---------------------------------------------------------------------------
# Project file (.mtg) serialization
# ---------------------------------------------------------------------------
#
# The .mtg file is the persistent project artifact: ``set_code`` +
# ``mtg_file_version`` headers wrapping the settings.toml body. The
# browser reads/writes it via the File System Access API; the server
# parses it on ``/api/project/open`` and pins the result on the
# active-project pointer.


MTG_FILE_VERSION = 1


def dump_project_toml(set_code: str, settings: ModelSettings) -> str:
    """Serialize a ``set_code`` + settings pair as a .mtg TOML document.

    Adds ``set_code`` and ``mtg_file_version`` as top-level keys above the
    standard settings.toml shape. The version field is a forward-compat
    hook — readers can refuse / migrate when the format changes.
    """
    import tomlkit

    set_code = set_code.strip()
    if not set_code:
        raise ValueError("set_code is required")
    doc = tomlkit.document()
    doc.add(tomlkit.comment("MTGAI project file"))
    doc.add(tomlkit.nl())
    doc.add("mtg_file_version", MTG_FILE_VERSION)
    doc.add("set_code", set_code)
    # Body of settings.toml: blank-line separator first, then merge keys.
    body = settings.to_toml_doc()
    doc.add(tomlkit.nl())
    for key, value in body.body:
        if key is None:
            continue  # whitespace / comments
        doc.add(key, value)
    return tomlkit.dumps(doc)


def parse_project_toml(text: str) -> tuple[str, ModelSettings]:
    """Parse a .mtg TOML body into ``(set_code, ModelSettings)``.

    Raises ``ValueError`` on missing ``set_code`` or a future
    ``mtg_file_version`` we don't know how to read.
    """
    import tomllib

    data = tomllib.loads(text)
    version = data.get("mtg_file_version", 1)
    if not isinstance(version, int) or version > MTG_FILE_VERSION:
        raise ValueError(
            f"Unsupported .mtg file version {version!r} "
            f"(this build understands up to {MTG_FILE_VERSION})"
        )
    raw_code = data.get("set_code")
    if not isinstance(raw_code, str):
        raise ValueError(".mtg file missing 'set_code'")
    set_code = raw_code.strip()
    if not set_code:
        raise ValueError(".mtg file 'set_code' is empty")
    settings = ModelSettings(
        llm_assignments=data.get("llm_assignments", {}),
        image_assignments=data.get("image_assignments", {}),
        effort_overrides=data.get("effort_overrides", {}),
        break_points=data.get("break_points", {}),
        set_params=SetParams(**data.get("set_params", {})),
        theme_input=ThemeInputSource(**data.get("theme_input", {})),
        asset_folder=data.get("asset_folder", "") or "",
    )
    return set_code, settings
