"""Wizard state resolver.

Maps the on-disk ``pipeline-state.json`` + ``theme.json`` into the shape
the wizard shell template renders: the visible tabs, the latest tab,
and the active tab for a requested URL.

The wizard is a linear sequence of tabs:

* ``project`` — kickoff (always present; rich UI lands in a follow-up card).
* ``theme`` — content extraction (visible once a theme.json exists).
* ``<stage_id>`` — one tab per pipeline stage that has begun work
  (visible up through the latest non-pending stage).

Section 11 of ``plans/wizard-ui-redesign.md`` enumerates the six
startup states this resolver collapses to a single set of visible
tabs + a latest-tab pointer.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from mtgai.io.asset_paths import NoAssetFolderError
from mtgai.pipeline.engine import load_state
from mtgai.pipeline.models import (
    PipelineState,
    StageStatus,
    break_point_states,
)

logger = logging.getLogger(__name__)

PROJECT_TAB_ID = "project"
THEME_TAB_ID = "theme"


@dataclass
class WizardTab:
    """One entry in the wizard tab strip."""

    id: str
    title: str
    kind: str  # 'project' | 'content' | 'stage'
    status: str | None = None  # StageStatus value for kind=='stage'


@dataclass
class WizardState:
    """Resolved shape passed to the wizard template + bootstrap JSON.

    ``active_set`` is ``None`` when no project file is open — the wizard
    then renders only the Project Settings tab with the New / Open
    toolbar; every other tab is gated behind a loaded project.
    """

    active_set: str | None
    visible_tabs: list[WizardTab]
    latest_tab_id: str
    active_tab_id: str
    pipeline_state: PipelineState | None
    theme: dict[str, Any] | None
    # stage_id -> True if a break point is set after this stage. Mirrors
    # the Project Settings tab's break-point list so the per-tab "Stop
    # after this step" checkbox can show its initial value without a
    # second fetch. Defaults from ``DEFAULT_BREAK_POINTS`` apply when a
    # stage has no explicit override saved.
    break_points: dict[str, bool]
    # True when a theme extraction worker is currently running. The
    # Theme tab uses this on first mount to arm its SSE stream handler
    # so the kickoff path (Project Settings → Start, full page nav to
    # /pipeline/theme) actually paints streaming chunks instead of
    # silently dropping them — without this flag set, the handler
    # short-circuits because it was originally written for the manual
    # Refresh-AI button only.
    extraction_active: bool = False


def _load_active_theme() -> dict[str, Any] | None:
    """Read the active project's ``theme.json`` if present, else None.

    Tolerates a malformed file by logging + returning None — a corrupt
    theme.json shouldn't 500 the wizard route; the user sees the brand-new
    state and can reseed. Likewise, ``NoAssetFolderError`` (no project
    open / asset_folder unset) collapses to None: the wizard renders the
    no-project shell instead of bouncing off a 409.
    """
    from mtgai.io.asset_paths import set_artifact_dir

    try:
        path = set_artifact_dir() / "theme.json"
    except NoAssetFolderError:
        return None
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Failed to read theme.json: %s", e)
        return None


def compute_visible_tabs(
    state: PipelineState | None,
    theme: dict[str, Any] | None,
    extraction_active: bool = False,
) -> list[WizardTab]:
    """Build the visible-tab list per design §4.2 + §11.

    Project Settings is always visible. Theme appears once a
    ``theme.json`` exists, while an extraction is in progress (so the
    user can watch it stream), or once the pipeline has been started
    (since that implies a theme was authored). Stage tabs appear up
    through the latest stage that has left ``PENDING`` — running,
    paused, completed, failed, or skipped all qualify.
    """
    tabs: list[WizardTab] = [
        WizardTab(id=PROJECT_TAB_ID, title="Project Settings", kind="project"),
    ]
    if theme is not None or state is not None or extraction_active:
        tabs.append(WizardTab(id=THEME_TAB_ID, title="Theme", kind="content"))

    if state is not None:
        latest_idx = -1
        for idx, stage in enumerate(state.stages):
            if stage.status != StageStatus.PENDING:
                latest_idx = idx
        if latest_idx >= 0:
            for idx in range(latest_idx + 1):
                stage = state.stages[idx]
                tabs.append(
                    WizardTab(
                        id=stage.stage_id,
                        title=stage.display_name,
                        kind="stage",
                        status=stage.status.value,
                    )
                )
    return tabs


def compute_latest_tab(tabs: list[WizardTab]) -> str:
    """The wizard's "latest" pointer — the rightmost visible tab.

    For a brand-new project that's just ``project``; for a mid-run set
    it's the running/paused/failed stage tab.
    """
    return tabs[-1].id if tabs else PROJECT_TAB_ID


def resolve_tab(requested: str | None, tabs: list[WizardTab]) -> str:
    """Coerce a URL-fragment tab id to a real visible tab.

    Unknown / not-yet-visible / None all collapse to the latest tab.
    Callers decide whether to redirect (URL doesn't match) or render
    in place (URL matches) by comparing ``requested`` to the result.
    """
    visible_ids = {t.id for t in tabs}
    if requested and requested in visible_ids:
        return requested
    return compute_latest_tab(tabs)


def build_wizard_state(requested_tab: str | None) -> WizardState:
    """Resolve the full wizard state for the active project + URL fragment.

    Reads the active project from in-memory state. With no project
    loaded, returns the brand-new shell (Project Settings tab only,
    everything else empty).
    """
    from mtgai.runtime.active_project import read_active_project

    project = read_active_project()
    if project is None:
        tabs = [WizardTab(id=PROJECT_TAB_ID, title="Project Settings", kind="project")]
        return WizardState(
            active_set=None,
            visible_tabs=tabs,
            latest_tab_id=PROJECT_TAB_ID,
            active_tab_id=PROJECT_TAB_ID,
            pipeline_state=None,
            theme=None,
            break_points={},
        )
    try:
        state = load_state()
    except NoAssetFolderError:
        state = None
    theme = _load_active_theme()
    from mtgai.runtime import extraction_run

    er = extraction_run.current()
    extraction_active = er is not None and er.status == "running"
    tabs = compute_visible_tabs(state, theme, extraction_active=extraction_active)
    latest = compute_latest_tab(tabs)
    active = resolve_tab(requested_tab, tabs)
    return WizardState(
        active_set=project.set_code,
        visible_tabs=tabs,
        latest_tab_id=latest,
        active_tab_id=active,
        pipeline_state=state,
        theme=theme,
        break_points=break_point_states(project.settings.break_points),
        extraction_active=extraction_active,
    )


def serialize(ws: WizardState) -> dict[str, Any]:
    """JSON-safe snapshot for the wizard.html bootstrap payload."""
    return {
        "active_set": ws.active_set,
        "active_tab_id": ws.active_tab_id,
        "latest_tab_id": ws.latest_tab_id,
        "visible_tabs": [
            {"id": t.id, "title": t.title, "kind": t.kind, "status": t.status}
            for t in ws.visible_tabs
        ],
        "pipeline_state": (
            ws.pipeline_state.model_dump(mode="json") if ws.pipeline_state else None
        ),
        "theme": ws.theme,
        "break_points": dict(ws.break_points),
        "extraction_active": ws.extraction_active,
    }
