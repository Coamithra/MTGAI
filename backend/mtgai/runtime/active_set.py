"""Persistent app-wide active-set selector.

The active set is which MTG set the UI is currently working on. It used
to be inferred from the most-recently-touched ``pipeline-state.json`` /
``theme.json`` mtime, plus a ``MTGAI_REVIEW_SET`` env-var fallback,
plus a per-page ``set_code`` form field on every wizard. That made set
identity surprising to switch and easy to lose between sessions.

This module promotes it to a single explicit preference persisted in
``output/settings/last_set.toml``. The top-bar set picker reads/writes
this file via the ``/api/runtime/active-set`` endpoint; the runtime
state aggregator consults it before the legacy mtime fallback.

The code shape (``[A-Z0-9]{2,5}``) is the same regex enforced by
``pipeline.server._theme_path`` — kept consistent so a new-set scaffold
here can't produce paths the theme endpoints would reject.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import tempfile
import tomllib
from pathlib import Path

from mtgai.runtime.runtime_state import OUTPUT_ROOT, SETS_ROOT

logger = logging.getLogger(__name__)

SET_CODE_RE = re.compile(r"^[A-Z0-9]{2,5}$")

_SETTINGS_DIR = OUTPUT_ROOT / "settings"
_LAST_SET_PATH = _SETTINGS_DIR / "last_set.toml"


def is_valid_set_code(code: str | None) -> bool:
    """Return True if ``code`` matches the [A-Z0-9]{2,5} shape after
    trimming + uppercasing. Used as the gate on every endpoint so a
    bogus code can't slip through to disk-touching helpers."""
    if not code:
        return False
    return bool(SET_CODE_RE.fullmatch(code.strip().upper()))


def normalize_code(code: str) -> str:
    """Trim and uppercase a set code. Pair with :func:`is_valid_set_code`
    before using the result on disk; this helper does no validation."""
    return code.strip().upper()


def read_active_set() -> str | None:
    """Return the persisted active-set code, or None if missing/stale.

    "Stale" means the file points to a code whose ``output/sets/<CODE>/``
    directory no longer exists — we treat that as no preference rather
    than silently picking it, so the caller can fall back to the mtime
    heuristic or prompt the user to pick.
    """
    if not _LAST_SET_PATH.exists():
        return None
    try:
        data = tomllib.loads(_LAST_SET_PATH.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        logger.warning("Failed to read %s: %s", _LAST_SET_PATH, e)
        return None
    code = (data.get("runtime") or {}).get("active_set")
    if not isinstance(code, str) or not is_valid_set_code(code):
        return None
    code = normalize_code(code)
    if not (SETS_ROOT / code).is_dir():
        return None
    return code


def write_active_set(code: str) -> None:
    """Atomically persist ``code`` as the new active set."""
    if not is_valid_set_code(code):
        raise ValueError(f"Invalid set code: {code!r}")
    code = normalize_code(code)
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    payload = f'[runtime]\nactive_set = "{code}"\n'
    # Same dir for the temp file so os.replace stays atomic across the
    # final rename (cross-device renames would fall back to a copy).
    fd, tmp_path = tempfile.mkstemp(prefix=".last_set-", suffix=".toml.tmp", dir=str(_SETTINGS_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_path, _LAST_SET_PATH)
    except Exception:
        # Clean up the temp file if the replace failed; nothing else
        # would have pointed at it.
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def list_sets() -> list[dict[str, str | None]]:
    """Enumerate every set directory, with display name when known.

    Each entry is ``{"code": <CODE>, "name": <name | None>}``. ``name``
    comes from the set's ``theme.json`` if present; otherwise None so
    the UI can decide between "ASD" and "ASD — Anomalous Descent".
    Only directories whose names match :data:`SET_CODE_RE` are listed,
    so stray scratch dirs under ``output/sets/`` don't pollute the
    picker.
    """
    if not SETS_ROOT.exists():
        return []
    out: list[dict[str, str | None]] = []
    for child in sorted(SETS_ROOT.iterdir()):
        if not child.is_dir():
            continue
        if not SET_CODE_RE.fullmatch(child.name):
            continue
        name = _read_theme_name(child / "theme.json")
        out.append({"code": child.name, "name": name})
    return out


def _read_theme_name(theme_path: Path) -> str | None:
    if not theme_path.exists():
        return None
    try:
        data = json.loads(theme_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    name = data.get("name") if isinstance(data, dict) else None
    return name if isinstance(name, str) and name.strip() else None


def create_set(code: str, name: str | None = None) -> None:
    """Scaffold ``output/sets/<CODE>/`` for a brand-new set.

    Writes a minimal ``theme.json`` stub when ``name`` is provided so
    the picker can show "CODE — Name" immediately; otherwise just
    creates the directory and lets the theme wizard fill in theme.json
    on first save. Raises ``FileExistsError`` if the directory is
    already present so callers can return 409 instead of clobbering.
    """
    if not is_valid_set_code(code):
        raise ValueError(f"Invalid set code: {code!r}")
    code = normalize_code(code)
    set_dir = SETS_ROOT / code
    # mkdir(parents=True) without exist_ok raises FileExistsError natively,
    # so we don't add a redundant pre-check (which would also admit a
    # TOCTOU window).
    set_dir.mkdir(parents=True)
    if name and name.strip():
        theme_path = set_dir / "theme.json"
        theme_path.write_text(
            json.dumps({"code": code, "name": name.strip()}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
