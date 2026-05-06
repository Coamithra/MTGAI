"""CLI shim helpers.

Tiny helpers for the per-stage CLI entry points (``python -m
mtgai.rendering`` and friends). Each of those scripts boots a fresh
process with no active project, but the registry-keyed
``output/sets/<CODE>/`` pattern is gone — they have to be told which
.mtg file to operate on. :func:`activate_from_mtg` parses the file the
operator points at and pins it as the active project so
:func:`set_artifact_dir` resolves cleanly for the rest of the run.
"""

from __future__ import annotations

import logging
from pathlib import Path

from mtgai.runtime.active_project import ProjectState, write_active_project
from mtgai.settings.model_settings import parse_project_toml

logger = logging.getLogger(__name__)


def activate_from_mtg(mtg_path: str | Path) -> str:
    """Read a .mtg file and pin the parsed project as active.

    Returns the parsed ``set_code``. Raises ``FileNotFoundError`` if the
    path is missing, ``ValueError`` from :func:`parse_project_toml` if
    the body is unreadable, and ``ValueError`` if the parsed settings
    have an empty ``asset_folder`` (every stage needs one and the CLI
    can't help the user pick one — failing fast at the entry point
    saves a deeper, less helpful raise from a stage runner).
    """
    path = Path(mtg_path)
    text = path.read_text(encoding="utf-8")
    set_code, settings = parse_project_toml(text)
    if not settings.asset_folder:
        raise ValueError(
            f".mtg file {path} has no asset_folder configured. "
            "Open the project in the wizard and pick one on the Project "
            "Settings tab before running CLI stages."
        )
    write_active_project(ProjectState(set_code=set_code, settings=settings, mtg_path=path))
    logger.info(
        "Activated project %s from %s (asset_folder=%s)",
        set_code,
        path,
        settings.asset_folder,
    )
    return set_code
