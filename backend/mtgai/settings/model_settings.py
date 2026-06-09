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
from typing import TYPE_CHECKING, Literal, get_args

from pydantic import BaseModel, Field

from mtgai.io.atomic import atomic_write_text
from mtgai.io.paths import output_root
from mtgai.settings.model_registry import get_registry

if TYPE_CHECKING:
    from tomlkit import TOMLDocument

logger = logging.getLogger(__name__)

OUTPUT_ROOT = output_root()
SETTINGS_DIR = OUTPUT_ROOT / "settings"

GLOBAL_TOML = SETTINGS_DIR / "global.toml"
LEGACY_CURRENT_TOML = SETTINGS_DIR / "current.toml"

# ---------------------------------------------------------------------------
# Stage definitions — which stages use LLMs / image-gen
# ---------------------------------------------------------------------------

# stage_id -> human-readable name (only stages that use models). Ordered to
# match the pipeline (STAGE_DEFINITIONS, with theme_extract first since it runs
# before the engine) so every model-picker that iterates this dict renders the
# rows in run order. This is the single source of truth for the per-stage LLM
# picker in BOTH the cross-set /settings page and the wizard's Project Settings
# tab (served verbatim in the /api/wizard/project payload); keep it complete so
# new stages can't drift out of the picker.
LLM_STAGE_NAMES: dict[str, str] = {
    "theme_extract": "Theme Extraction",
    "mechanics": "Mechanic Generation",
    "archetypes": "Archetype Generation",
    "skeleton": "Skeleton Generation",
    "reprints": "Reprint Selection",
    "lands": "Land Generation",
    "card_gen": "Card Generation",
    "conformance": "Conformance & Interactions",
    "ai_review": "AI Design Review",
    # Finalization runs a light LLM sanity check (review/sanity_check.py) over the
    # finished pool, so it resolves an LLM model like the gates do.
    "finalize": "Finalization",
    "visual_refs": "Visual References & Artists",
    # set_symbol needs BOTH an LLM (the glyph concept) and an image model (the
    # candidate silhouettes) — it appears in IMAGE_STAGE_NAMES too. The LLM key
    # drives the concept call's model resolution (get_llm_model_id) + picker.
    "set_symbol": "Set Symbol (concept)",
    "art_prompts": "Art Prompt Generation",
    # char_portraits ("Character References") needs BOTH an LLM (recurring-entity
    # detection) and an image model (the neutral reference gen) — it appears in
    # IMAGE_STAGE_NAMES too. The LLM key drives the detection call's model
    # resolution (get_llm_model_id) + its per-stage Settings picker.
    "char_portraits": "Character References (entity detection)",
    # art_select is no longer a standalone STAGE_DEFINITIONS stage (folded into
    # the merged art_gen). Its model-assignment key is intentionally KEPT so the
    # best-of-N selection sub-step inside run_art_gen still resolves a model and
    # appears in the per-stage Settings picker (the Art Generation rework card
    # decides its final shape).
    "art_select": "Art Selection",
}

IMAGE_STAGE_NAMES: dict[str, str] = {
    "set_symbol": "Set Symbol",
    "char_portraits": "Character References",
    "art_gen": "Art Generation & Review",
}

# LLM stages whose work is a *vision* task — they judge generated images, so a
# text-only model can't do the job. The Project Settings picker filters these
# stages' model dropdown to vision-capable models, and the save-model endpoint
# rejects a non-vision assignment for them. ``art_select`` (the best-of-N art
# judge folded into art_gen) is the only one today; image-generation stages
# aren't here because they use the image registry, which has no text-only
# entries.
#
# This picker filter only guards the *wizard* path — presets/defaults bypass it,
# and the local-by-default ``art_select`` assignment IS text-only. The runtime
# backstop lives in ``art_selector.select_art_for_set``: it pre-flights the
# resolved model's ``supports_vision`` flag and, when text-only, skips best-of-N
# entirely (auto-picks v1) with a loud WARN + ``judge_skipped`` summary signal
# instead of attempting — and silently failing — one image request per card. The
# judge also resolves its provider from the registry (no longer hard-pinned to
# Anthropic), so a future non-Anthropic / local vision model routes correctly.
VISION_REQUIRED_STAGES: frozenset[str] = frozenset({"art_select"})

# ---------------------------------------------------------------------------
# Default assignments (matching current hardcoded behaviour)
# ---------------------------------------------------------------------------

# Local-by-default (user policy): every stage defaults to the local Gemma model
# so a fresh project — or any stage an older project hasn't pinned (e.g.
# Skeleton Generation's LLM relabel, absent from .mtg files predating it) —
# never silently hits a paid cloud API. Opt into cloud per-stage in Settings,
# or apply the ``recommended`` preset wholesale.
_LOCAL_DEFAULT = "gemma4-26b-vlad-updated"

# Per-stage context-length tiering (see learnings/ctx-tier-sweet-spots.md).
# Stages NOT listed here resolve a base model to its smaller --ctx-size
# downstream twin (when one exists) so they pre-allocate less KV VRAM. Only
# theme_extract ingests a large document (~58.7k tokens) and needs the base's
# full window; every other stage's measured worst case is under ~24k, which the
# 48k twin holds with headroom. Applied transparently in get_llm_model_id(): the
# user picks a base model, the right tier is chosen per stage. A base with no
# twin (cloud models, untiered locals) is unaffected.
_FULL_CONTEXT_STAGES: frozenset[str] = frozenset({"theme_extract"})

# The conformance gate's interaction step builds a CUMULATIVE-context prompt:
# each batch is shown every previously-reviewed card plus its ~40 new cards, so
# its largest batch grows with set size and on a very large set outgrows the 48k
# downstream twin. At/above this set_size the conformance stage stays on the
# base's FULL window (128k for Gemma) instead of the twin; normal sets keep the
# lean 48k fast path. ~400 cards lands the largest batch near ~28-32k tokens —
# comfortably under the 48k twin's ~40k usable input — so this is the headroom
# cushion, not the cliff. NOTE: assumes the assigned base actually has a large
# window; a low-context local base can't honour this (tracked on Trello).
_CONFORMANCE_FULL_CONTEXT_SET_SIZE = 400
DEFAULT_LLM_ASSIGNMENTS: dict[str, str] = {
    "theme_extract": _LOCAL_DEFAULT,
    "mechanics": _LOCAL_DEFAULT,
    "archetypes": _LOCAL_DEFAULT,
    "skeleton": _LOCAL_DEFAULT,
    "visual_refs": _LOCAL_DEFAULT,
    # set_symbol's LLM key drives its glyph-concept call (get_llm_model_id).
    "set_symbol": _LOCAL_DEFAULT,
    "reprints": _LOCAL_DEFAULT,
    "lands": _LOCAL_DEFAULT,
    "card_gen": _LOCAL_DEFAULT,
    "conformance": _LOCAL_DEFAULT,
    "ai_review": _LOCAL_DEFAULT,
    "finalize": _LOCAL_DEFAULT,
    "art_prompts": _LOCAL_DEFAULT,
    # char_portraits' LLM key drives its recurring-entity detection call
    # (get_llm_model_id("char_portraits")); without a default it fell back to
    # cloud sonnet, silently breaking the local-by-default policy.
    "char_portraits": _LOCAL_DEFAULT,
    "art_select": _LOCAL_DEFAULT,
}

DEFAULT_IMAGE_ASSIGNMENTS: dict[str, str] = {
    "set_symbol": "flux-local",
    "char_portraits": "flux-local",
    "art_gen": "flux-local",
}

DEFAULT_EFFORT: dict[str, str] = {
    "card_gen": "max",
    "ai_review": "max",
}

# Stages that default to "review" (pause for human input) when a set has no
# explicit override saved.
DEFAULT_BREAK_POINTS: dict[str, str] = {
    "theme_extract": "review",
    "mechanics": "review",
    # Pause after Skeleton Generation so the user reviews the relabeled skeleton
    # (default vs tweaked) before reprints/card-gen consume it. Auto-toggleable.
    "skeleton": "review",
    # Merged art/render stages pause for human review by default (was the retired
    # human_art_review + human_final_review). art_gen = generation + best-of-N
    # select + human art review; rendering = render + final review.
    "art_gen": "review",
    "rendering": "review",
}

# Stages whose ``review`` break-point is *structural* — the wizard tab is
# the only path that produces the stage's output, so skipping the pause
# would mark the stage COMPLETED without the artifacts downstream stages
# depend on. The break-point endpoint refuses to unset these so a user
# can't accidentally break their pipeline.
#
# ``mechanics`` used to be here (its Save endpoint was the only writer of
# ``approved.json``), but the stage now auto-picks the best candidates and
# writes ``approved.json`` + sidecars itself (see ``run_mechanics`` +
# ``pick_best_mechanics``). It can therefore auto-continue safely, so its
# pause is a normal (default-on, user-toggleable) review break-point. No
# stage is structural today; the constant + enforcement stay for future use.
STRUCTURAL_BREAK_POINTS: frozenset[str] = frozenset()

# ---------------------------------------------------------------------------
# Built-in presets
# ---------------------------------------------------------------------------

PRESETS: dict[str, dict] = {
    "recommended": {
        "llm": {
            "theme_extract": "haiku",
            "mechanics": "sonnet",
            "archetypes": "sonnet",
            "skeleton": "sonnet",
            "visual_refs": "sonnet",
            "set_symbol": "haiku",
            "reprints": "haiku",
            "lands": "haiku",
            "card_gen": "opus",
            "conformance": "sonnet",
            "ai_review": "opus",
            "finalize": "haiku",
            "art_prompts": "haiku",
            "char_portraits": "haiku",
            "art_select": "haiku",
        },
        "image": {
            "set_symbol": "flux-local",
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
        # Every stage on the local Gemma default (vlad-updated: Vlad's fast
        # ~14.2 GB K-quant mix + the fixed Apr-11+ chat template, thinking on).
        # Mirrors DEFAULT_LLM_ASSIGNMENTS -- exists so a user who applied the
        # cloud `recommended` preset can switch wholesale back to local.
        # Context-length tiering is automatic (get_llm_model_id consulting
        # _FULL_CONTEXT_STAGES): theme_extract runs the base's 128k window, every
        # other stage its 48k twin. There is no separate "tiered" preset to apply.
        "llm": {k: _LOCAL_DEFAULT for k in DEFAULT_LLM_ASSIGNMENTS},
        "image": dict(DEFAULT_IMAGE_ASSIGNMENTS),
        "effort": {},
    },
    "qa": {
        # The QA-harness preset (card "QA Bot"): every LLM stage on the cheapest
        # 2-bit Gemma with thinking DISABLED everywhere. The point is raw speed for
        # self-driving QA runs -- cards may come out janky, but QA exercises the app
        # *plumbing*, not card quality. Applied via /api/wizard/project/preset/apply
        # (or the --debug quick-project helper) so a QA bot never pays full freight.
        "llm": {k: "gemma4-26b-iq2m" for k in DEFAULT_LLM_ASSIGNMENTS},
        "image": dict(DEFAULT_IMAGE_ASSIGNMENTS),
        "effort": {},
        "thinking": {k: "disabled" for k in DEFAULT_LLM_ASSIGNMENTS},
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


# Best-of-N art versions: how many candidate images the Art Generation stage
# produces per card before the judge picks. Bounded so a set art run stays
# tractable on local Flux (each version is a full ~30-step diffusion pass).
MIN_ART_VERSIONS = 1
MAX_ART_VERSIONS = 6

# Upper bound on a set's target card count. A premier set is ~277 cards; this
# ceiling is a generous backstop against an absurd value (e.g. 50000) that would
# spawn a runaway pipeline run. Mirrors the Project Settings UI field's max.
MAX_SET_SIZE = 500

# Two-colour frame treatment: "split" renders every two-colour card on the
# hybrid-derived left/right split frame (house style); "gold" uses the flat
# gold M frame — the real-Magic convention for non-hybrid two-colour costs.
TwoColorFrameMode = Literal["split", "gold"]
TWO_COLOR_FRAME_MODES: tuple[str, ...] = get_args(TwoColorFrameMode)


class SetParams(BaseModel):
    """Numeric / structural parameters for a set.

    Lifted out of theme.json — theme.json now owns content-extracted fields
    only (constraints, card requests, setting prose). These numbers guide
    extraction prompts but are not extracted from prose.
    """

    set_name: str = ""
    # Standard MTG premier-set size (the skeleton's rarity-weight baseline).
    # Smaller dev runs override this in the wizard.
    set_size: int = 277
    mechanic_count: int = 3
    # Best-of-N art generation: how many candidate art versions the Art
    # Generation stage produces per card before the LLM judge picks the best.
    # 1 disables judging (the single version is auto-picked). Capped low so a
    # set's art run stays tractable on local Flux. Surfaced on Project Settings.
    art_versions_per_card: int = 3
    # Two-colour frame treatment (see TwoColorFrameMode). "split" is the house
    # style; "gold" is strict canon fidelity. Read by the renderer at frame-key
    # time, so it governs cards as they are (re-)rendered — no cascade-clear;
    # already-rendered cards keep their frame until re-rendered.
    two_color_frame: TwoColorFrameMode = "split"


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


class DebugSettings(BaseModel):
    """Per-project debug toggles surfaced on the Project Settings tab.

    The first entry is :attr:`response_cache` — when on, llmfacade's
    fingerprint-keyed response cache is enabled for every LLM call in
    this project (cache files land under ``<asset_folder>/.llm-cache/``;
    see :func:`mtgai.generation.llm_client._active_cache_dir`). Subsequent
    calls with an identical request fingerprint replay the cached response
    instead of hitting the provider, which speeds up debugging dramatically.

    Defaults are all-off so production runs are unaffected; the block is
    omitted from saved profiles (``profile_only=True``) because debug
    state is per-project, not template-able. Off by default keeps the
    Anthropic-bill-vs-cache-hit semantics predictable.

    :attr:`use_prefab_cards` / :attr:`use_prefab_mechanics` short-circuit the
    ``card_gen`` / ``mechanics`` stages: instead of calling the LLM they
    install the hand-made pool under ``<repo-root>/prefab_data/`` (see
    :mod:`mtgai.generation.prefab`), so downstream stages can be exercised
    instantly. Both no-op gracefully when the prefab folder is empty/missing.
    """

    response_cache: bool = False
    use_prefab_cards: bool = False
    use_prefab_mechanics: bool = False


class ModelSettings(BaseModel):
    """Per-stage model assignments — the active configuration for one set."""

    llm_assignments: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_LLM_ASSIGNMENTS))
    image_assignments: dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_IMAGE_ASSIGNMENTS)
    )
    effort_overrides: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_EFFORT))
    # Per-stage "disable thinking" overrides (stage_id -> "disabled"). Only
    # meaningful for a stage whose assigned model is a local reasoning model
    # (registry ``thinking`` = "adaptive"/"adaptive_summarized"); absent = use the
    # model's registry default (thinking ON). Mirrors ``effort_overrides`` — a
    # separate per-stage dict, persisted the same way — and lets the user trade
    # reasoning depth for speed on a per-phase basis (a thinking model can spend
    # its whole output budget on chain-of-thought). Resolved by ``get_thinking``.
    thinking_overrides: dict[str, str] = Field(default_factory=dict)
    # Per-stage break-point overrides (stage_id -> "auto" | "review").
    # Stays empty until the Project Settings tab toggles a checkbox.
    # Locked-on `human_*` stages are NOT written here — the engine
    # enforces those at pipeline-create time via STAGE_DEFINITIONS.
    break_points: dict[str, str] = Field(default_factory=dict)
    # Set parameters + theme input both live here so settings.toml is the
    # single source of truth for everything Project Settings owns.
    set_params: SetParams = Field(default_factory=SetParams)
    theme_input: ThemeInputSource = Field(default_factory=ThemeInputSource)
    # Per-project debug toggles (response caching, ...). Off by default
    # and excluded from saved profiles — see :class:`DebugSettings`.
    debug: DebugSettings = Field(default_factory=DebugSettings)
    # User-chosen folder for generated artifacts (cards/, theme.json,
    # pipeline-state.json, art, renders). Empty string until the user picks
    # one on Project Settings. In Phase 1 the field is captured + persisted
    # but not yet wired through stage runners — those still write under
    # ``output/sets/<CODE>/``. Phase 2 routes outputs into this folder.
    asset_folder: str = ""

    def get_assigned_model_id(self, stage_id: str) -> str:
        """The *base* model_id the user assigned to a stage, for display and
        provenance. Unlike :meth:`get_llm_model_id` this does NOT apply
        context-length tiering, so it never returns an internal twin id.
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

    def get_llm_model_id(self, stage_id: str) -> str:
        """Resolve the *effective* API model_id a stage actually runs on.

        This is what ``generate_with_tool`` launches and what the tok/s poller
        polls. The user assigns a base model (see :meth:`get_assigned_model_id`);
        this layers per-stage context-length tiering on top: for a stage not in
        ``_FULL_CONTEXT_STAGES``, the base is swapped for its smaller
        ``--ctx-size`` downstream twin when one exists, so the stage launches a
        leaner llama-server and budgets against the right window. A base with no
        twin (cloud models, untiered locals) is returned unchanged.

        Exception: the ``conformance`` gate keeps the base's full window once the
        set reaches ``_CONFORMANCE_FULL_CONTEXT_SET_SIZE`` cards, because its
        interaction step's cumulative-context prompt grows with set size and can
        outgrow the 48k twin on a large set.
        """
        base_id = self.get_assigned_model_id(stage_id)
        if stage_id in _FULL_CONTEXT_STAGES:
            return base_id
        # The conformance gate (conformance + interaction steps) can build a
        # cumulative-context prompt that outgrows the 48k twin on a very large
        # set; keep such a set on the base's full window. Normal sets stay lean.
        if (
            stage_id == "conformance"
            and (self.set_params.set_size or 0) >= _CONFORMANCE_FULL_CONTEXT_SET_SIZE
        ):
            return base_id
        registry = get_registry()
        base = registry.get_llm_by_model_id(base_id)
        if base is not None:
            twin = registry.downstream_twin(base.key)
            if twin is not None:
                return twin.model_id
        return base_id

    def conformance_context_status(self) -> dict:
        """Whether the conformance gate's assigned model can hold the interaction
        scan's largest cumulative batch for this set's ``set_size``.

        The interaction step builds a cumulative-context prompt that grows with set
        size; on a model whose window is too small,
        :func:`mtgai.analysis.interactions._bound_existing_context` silently drops
        existing-context cards (reducing cross-batch coverage) and logs a WARN the
        wizard user never sees. This surfaces the same fact in the Project Settings
        model picker, mirroring the ``VISION_REQUIRED_STAGES`` warning.

        The estimate compares the projected largest-batch prompt against the SAME
        budget ``check_pre_call`` enforces (``int(ctx*(1-SAFETY_MARGIN)) -
        MAX_TOKENS``), against the conformance stage's **effective** window — the
        resolved twin or, at/above ``_CONFORMANCE_FULL_CONTEXT_SET_SIZE``, the
        base's full window (via :meth:`get_llm_model_id`). ``fits`` is ``False``
        only when context would actually be dropped.

        Returns ``{model_name, context_window, set_size, projected_tokens,
        budget_tokens, fits}``.
        """
        from mtgai.analysis.interactions import MAX_TOKENS, project_largest_batch_tokens
        from mtgai.generation.token_utils import SAFETY_MARGIN, get_context_window

        set_size = self.set_params.set_size or 0
        mechanic_count = self.set_params.mechanic_count or 0
        base_id = self.get_assigned_model_id("conformance")
        effective_id = self.get_llm_model_id("conformance")
        registry = get_registry()
        base = registry.get_llm_by_model_id(base_id)
        model_name = base.name if base is not None else base_id

        ctx = get_context_window(effective_id)
        projected = project_largest_batch_tokens(set_size, mechanic_count)
        budget = int(ctx * (1 - SAFETY_MARGIN)) - MAX_TOKENS
        return {
            "model_name": model_name,
            "context_window": ctx,
            "set_size": set_size,
            "projected_tokens": projected,
            "budget_tokens": max(budget, 0),
            "fits": projected <= budget,
        }

    def get_image_model_key(self, stage_id: str) -> str:
        """Get the image model key for a stage."""
        return self.image_assignments.get(
            stage_id, DEFAULT_IMAGE_ASSIGNMENTS.get(stage_id, "flux-local")
        )

    def get_effort(self, stage_id: str) -> str | None:
        """Resolve the effort level for a stage, or None.

        Returns None when no effort is set or the assigned model takes no effort
        parameter at all. If a level is stored that the assigned model doesn't
        accept (e.g. a profile carries ``max`` but the stage is now on Sonnet,
        which caps at ``high``), it's clamped down to the model's ceiling rather
        than passed through — sending an unsupported level would 400.
        """
        effort = self.effort_overrides.get(stage_id)
        if not effort:
            return None
        key = self.llm_assignments.get(stage_id, DEFAULT_LLM_ASSIGNMENTS.get(stage_id))
        if not key:
            return effort
        model = get_registry().get_llm(key)
        if model is None or not model.effort_levels:
            return None
        if effort in model.effort_levels:
            return effort
        # Unsupported level for this model — clamp to its highest (last) level.
        return model.effort_levels[-1]

    def get_thinking(self, stage_id: str) -> str | None:
        """Resolve the ``thinking`` value to pass to the LLM call, or None.

        Returns ``"disabled"`` ONLY when the user has toggled thinking off for
        this stage AND the assigned model is a thinking-capable local reasoning
        model (registry ``thinking`` in adaptive / adaptive_summarized). In every
        other case returns None, meaning "send no thinking override — use the
        model's registry default" — so a stage on an Anthropic model (no thinking
        concept), a non-reasoning local model, or simply an un-toggled stage keeps
        its default behaviour (reasoning on). Mirrors :meth:`get_effort`; callers
        pass the result as ``generate_with_tool(..., thinking=...)`` (a no-op on
        the Anthropic path and on a model whose template doesn't gate thinking).
        """
        if self.thinking_overrides.get(stage_id) != "disabled":
            return None
        key = self.llm_assignments.get(stage_id, DEFAULT_LLM_ASSIGNMENTS.get(stage_id))
        if not key:
            return None
        model = get_registry().get_llm(key)
        if model is None or model.thinking not in ("adaptive", "adaptive_summarized"):
            return None
        return "disabled"

    def to_toml_doc(self, *, profile_only: bool = False) -> TOMLDocument:
        """Build a tomlkit document for this settings instance.

        ``profile_only`` strips per-set / per-project fields (``set_params``,
        ``theme_input``, ``debug``, ``break_points``) so the document is a
        portable template — used when saving a profile to the global
        library. Break points stay out because they're a per-project
        workflow choice (where to pause for review on *this* run), not a
        model-assignment template; the model + effort + thinking
        assignments are the reusable part.
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
        if any(self.thinking_overrides.values()):
            doc.add(tomlkit.nl())
            doc.add(
                "thinking_overrides",
                {k: v for k, v in self.thinking_overrides.items() if v},
            )
        if not profile_only:
            if self.break_points:
                doc.add(tomlkit.nl())
                doc.add("break_points", dict(self.break_points))
            if self.asset_folder:
                doc.add(tomlkit.nl())
                doc.add("asset_folder", self.asset_folder)
            # Only emit ``[debug]`` when it diverges from defaults so a
            # fresh project's .mtg stays lean (and diffs stay readable).
            debug_dict = self.debug.model_dump()
            if debug_dict != DebugSettings().model_dump():
                doc.add(tomlkit.nl())
                doc.add("debug", debug_dict)
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
        atomic_write_text(path, tomlkit.dumps(self.to_toml_doc()))
        return path

    def save_profile(self, name: str) -> Path:
        """Save these settings as a named profile in the global library.

        Profiles capture model assignments + effort + thinking overrides
        but exclude per-project values (set parameters, theme input,
        debug toggles, and break points).
        """
        import tomlkit

        name = validate_profile_name(name)
        path = SETTINGS_DIR / f"{name}.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, tomlkit.dumps(self.to_toml_doc(profile_only=True)))
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
            thinking_overrides=data.get("thinking_overrides", {}),
            break_points=data.get("break_points", {}),
            set_params=SetParams(**data.get("set_params", {})),
            theme_input=ThemeInputSource(**data.get("theme_input", {})),
            debug=DebugSettings(**data.get("debug", {})),
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
                thinking_overrides=dict(preset.get("thinking", {})),
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
                    "thinking": self.thinking_overrides.get(stage_id, ""),
                    # Whether this stage's assigned model is a thinking-capable
                    # local reasoning model — the toggle only applies when True.
                    "supports_thinking": bool(
                        model and model.thinking in ("adaptive", "adaptive_summarized")
                    ),
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
            "thinking_overrides": dict(self.thinking_overrides),
            "break_points": dict(self.break_points),
            "set_params": self.set_params.model_dump(),
            "theme_input": self.theme_input.model_dump(mode="json"),
            "debug": self.debug.model_dump(),
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
        atomic_write_text(path, tomlkit.dumps(doc))
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

    if not isinstance(set_code, str):
        raise ValueError(f"set_code must be a string, got {type(set_code).__name__}")
    set_code = set_code.strip()
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

    ``set_code`` is purely cosmetic (the printed label on the card
    frame); missing/empty is fine and yields an empty string. Raises
    ``ValueError`` only on type errors or a future ``mtg_file_version``
    we don't know how to read.
    """
    import tomllib

    data = tomllib.loads(text)
    version = data.get("mtg_file_version", 1)
    if not isinstance(version, int) or version > MTG_FILE_VERSION:
        raise ValueError(
            f"Unsupported .mtg file version {version!r} "
            f"(this build understands up to {MTG_FILE_VERSION})"
        )
    raw_code = data.get("set_code", "")
    if not isinstance(raw_code, str):
        raise ValueError(".mtg file 'set_code' must be a string")
    set_code = raw_code.strip()
    settings = ModelSettings(
        llm_assignments=data.get("llm_assignments", {}),
        image_assignments=data.get("image_assignments", {}),
        effort_overrides=data.get("effort_overrides", {}),
        thinking_overrides=data.get("thinking_overrides", {}),
        break_points=data.get("break_points", {}),
        set_params=SetParams(**data.get("set_params", {})),
        theme_input=ThemeInputSource(**data.get("theme_input", {})),
        debug=DebugSettings(**data.get("debug", {})),
        asset_folder=data.get("asset_folder", "") or "",
    )
    return set_code, settings
