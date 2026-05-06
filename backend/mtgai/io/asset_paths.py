"""Project-aware artifact paths.

Stage outputs (theme.json, skeleton.json, cards/, art/, renders/,
reports/, ...) live under the active project's ``asset_folder`` chosen
on the Project Settings tab. There's no longer a fallback to
``output/sets/<CODE>/`` — when no project is open or ``asset_folder``
is empty, :func:`set_artifact_dir` raises :class:`NoAssetFolderError`
and endpoint-level callers translate that into a 409 that forces the
user back to Project Settings.

``mtgai.io.paths`` keeps its low-level "given an output_root, build a
path" helpers. This module is the higher-level "where do the active
project's artifacts live" entry point and is what stage runners + read
endpoints should call.
"""

from __future__ import annotations

from pathlib import Path


class NoAssetFolderError(RuntimeError):
    """No asset folder is configured.

    Raised by :func:`set_artifact_dir` when there's either no active
    project or the active project's ``asset_folder`` is empty. Endpoint
    handlers catch this and return a 409 so the UI can prompt the user
    to pick an asset folder on Project Settings.
    """


def set_artifact_dir() -> Path:
    """Return the directory where the active project's artifacts live.

    Reads from the active project's :class:`ProjectState`:

    * No project open → raises :class:`NoAssetFolderError`.
    * Project open but ``asset_folder`` empty → raises
      :class:`NoAssetFolderError`.
    * Project open with non-empty ``asset_folder`` → returns it as a
      :class:`Path` (no mkdir; writers stay responsible for
      ``parent.mkdir(parents=True, exist_ok=True)``).

    Lazy-imports :mod:`mtgai.runtime.active_project` so this module
    stays cheap to import from low-level paths.
    """
    from mtgai.runtime.active_project import read_active_project

    project = read_active_project()
    if project is None:
        raise NoAssetFolderError("No project is open")
    folder = project.settings.asset_folder
    if not folder:
        raise NoAssetFolderError("Asset folder required — pick one on the Project Settings tab")
    return Path(folder)
