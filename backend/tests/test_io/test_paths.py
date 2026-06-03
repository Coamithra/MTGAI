"""Tests for the repo-relative path helpers in :mod:`mtgai.io.paths`.

These guard the ``parents[N]`` count: a wrong count silently resolves to the
wrong directory (or a non-existent one), which is exactly the portability bug
the helpers exist to prevent. We assert the roots are real directories and that
``repo_root()`` contains the ``backend/`` sentinel, proving the count is right.
"""

from pathlib import Path

import mtgai
from mtgai.io.paths import output_root, repo_root


def test_repo_root_is_existing_directory() -> None:
    root = repo_root()
    assert root.is_dir()


def test_repo_root_contains_backend_sentinel() -> None:
    # ``backend/`` sitting directly under the resolved root proves parents[N]
    # landed on the repo root, not one level too high or too low.
    root = repo_root()
    assert (root / "backend").is_dir()


def test_repo_root_is_ancestor_of_package() -> None:
    # The installed ``mtgai`` package lives at <repo>/backend/mtgai, so the
    # resolved repo root must be an ancestor of the package directory.
    package_dir = Path(next(iter(mtgai.__path__))).resolve()
    assert repo_root() in package_dir.parents


def test_output_root_is_under_repo_root() -> None:
    out = output_root()
    assert out == repo_root() / "output"
    assert out.parent == repo_root()


def test_output_root_exists() -> None:
    assert output_root().is_dir()
