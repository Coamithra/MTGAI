"""Project-aware artifact paths.

Stage outputs (theme.json, skeleton.json, cards/, art/, renders/,
reports/, ...) live under the project's ``asset_folder`` when the user
has chosen one on the Project Settings tab. Until then they fall back
to ``output/sets/<CODE>/`` — the legacy "everything-under-output"
layout.

``settings.toml`` itself is the *registry* of known projects and stays
at ``output/sets/<CODE>/settings.toml`` regardless of ``asset_folder``.
That lets :func:`set_artifact_dir` read the asset folder from disk
without circular bootstrapping: load settings.toml from the canonical
location, then route artifacts wherever the user pointed.

``mtgai.io.paths`` keeps its low-level "given an output_root, build a
path" helpers. This module is the higher-level "given a set_code, where
do its artifacts live" entry point and is what stage runners + read
endpoints should call.

Two read variants on purpose:

* :func:`set_artifact_dir` — the writer-facing call. Triggers
  ``get_settings``, which seeds a default ``settings.toml`` for any
  unseen code so subsequent reads are stable. Use from runners + the
  endpoints they back.
* :func:`set_artifact_dir_if_known` — the scanner-facing call. Returns
  ``None`` (no seeding) when the code has no settings.toml yet. Use
  when iterating ``output/sets/*`` from a discovery / cleanup loop so
  a stray scratch dir can't materialise a settings.toml as a side
  effect of being looked at.
"""

from __future__ import annotations

from pathlib import Path

OUTPUT_ROOT = Path("C:/Programming/MTGAI/output")
SETS_ROOT = OUTPUT_ROOT / "sets"


def set_artifact_dir(set_code: str) -> Path:
    """Return the directory where ``set_code``'s artifacts live.

    Resolution:

    1. ``settings.toml``'s ``asset_folder`` if non-empty — the user-chosen
       folder from the Project Settings tab. Returned verbatim (no mkdir);
       writers are responsible for ``parent.mkdir(parents=True,
       exist_ok=True)`` the same way they were under the legacy layout.
    2. ``output/sets/<CODE>/`` — the legacy default.

    Side effect: when no ``settings.toml`` exists for ``set_code`` yet,
    ``get_settings`` seeds one at the canonical location. That makes
    this call safe for runners (which always operate on a real project)
    but unsafe for filesystem scans where a stray dir name could
    accidentally materialise a project. Use
    :func:`set_artifact_dir_if_known` from scanners.

    Lazy-imports :mod:`mtgai.settings.model_settings` because that module
    in turn touches a TOML library and a model registry — keeping the
    import light makes this helper safe to call from low-level paths.
    """
    from mtgai.settings.model_settings import get_settings

    folder = get_settings(set_code).asset_folder
    if folder:
        return Path(folder)
    return SETS_ROOT / set_code


def set_artifact_dir_if_known(set_code: str) -> Path | None:
    """Return the artifact dir for ``set_code`` *only* if it's a known project.

    A "known project" is one that already has
    ``output/sets/<set_code>/settings.toml`` on disk. Returns ``None``
    otherwise (without seeding) — that's the contract scanners need to
    walk ``output/sets/`` without materialising settings.toml for every
    directory they encounter.

    For known projects the resolution is the same as
    :func:`set_artifact_dir`: configured ``asset_folder`` if non-empty,
    else the legacy path.
    """
    from mtgai.settings.model_settings import get_settings

    if not (SETS_ROOT / set_code / "settings.toml").exists():
        return None
    folder = get_settings(set_code).asset_folder
    if folder:
        return Path(folder)
    return SETS_ROOT / set_code
