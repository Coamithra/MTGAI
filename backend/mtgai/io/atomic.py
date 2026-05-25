"""Atomic, retry-resilient file writes.

Two problems this module solves, both of which plain ``Path.write_text``
leaves open:

1. **Torn reads.** ``write_text`` truncates the destination, then writes.
   A concurrent reader (e.g. a wizard route calling ``load_state`` while a
   background stage saves) can observe the empty/partial window and raise
   ``JSONDecodeError``. Writing to a sibling temp file and then
   :func:`os.replace`-ing it into place makes the swap atomic — readers see
   either the old file or the new one, never a half-written one.

2. **Transient Windows locks.** ``os.replace`` is ``MoveFileEx`` on Windows,
   which returns ``ERROR_ACCESS_DENIED`` (WinError 5) or
   ``ERROR_SHARING_VIOLATION`` (WinError 32) if *any* process holds the source
   or destination open. Windows Defender's on-access scanner opens
   freshly-created files to scan them, so in the split second between creating
   the temp file and replacing the destination, the move can be denied. The
   search indexer and file-sync clients (OneDrive/Dropbox) do the same. These
   locks clear in milliseconds, so a short exponential-backoff retry absorbs
   them; only genuinely fatal errors (no space, is-a-directory, …) propagate.

Text writes preserve ``Path.write_text`` semantics exactly (text mode,
``newline=None`` → ``\\n`` translated to ``os.linesep``), so swapping a call
over changes nothing on disk except the atomicity + retry guarantees — no
spurious line-ending churn in version-controlled JSON.
"""

from __future__ import annotations

import contextlib
import errno
import logging
import os
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Windows error codes the scanner/indexer/sync race surfaces as. ``errno`` is
# unreliable here (both can map to EACCES), so we match ``winerror`` first.
_TRANSIENT_WINERRORS = frozenset({5, 32})  # ACCESS_DENIED, SHARING_VIOLATION
# POSIX fallbacks: an AV/locker on some mounts can momentarily deny access too.
_TRANSIENT_ERRNOS = frozenset({errno.EACCES, errno.EPERM})

_DEFAULT_RETRIES = 5
_DEFAULT_BASE_DELAY = 0.05  # seconds; doubles each retry → ≤1.55s total worst case


def _is_transient(exc: OSError) -> bool:
    """True if ``exc`` looks like a momentary lock worth retrying."""
    winerror = getattr(exc, "winerror", None)
    if winerror is not None:
        return winerror in _TRANSIENT_WINERRORS
    return exc.errno in _TRANSIENT_ERRNOS


def replace_with_retry(
    src: str | os.PathLike[str],
    dst: str | os.PathLike[str],
    *,
    retries: int = _DEFAULT_RETRIES,
    base_delay: float = _DEFAULT_BASE_DELAY,
) -> None:
    """``os.replace(src, dst)`` with exponential-backoff retry on transient locks.

    Use this directly when you already produced a temp file you want to swap
    into place atomically — e.g. rendering an image to ``foo.png.tmp`` then
    promoting it. For the common write-a-string case, prefer
    :func:`atomic_write_text` / :func:`atomic_write_bytes`.
    """
    delay = base_delay
    for attempt in range(retries + 1):
        try:
            os.replace(src, dst)
            return
        except OSError as exc:
            if attempt >= retries or not _is_transient(exc):
                raise
            logger.debug(
                "os.replace(%s -> %s) blocked (%s); retry %d/%d in %.0fms",
                src,
                dst,
                exc,
                attempt + 1,
                retries,
                delay * 1000,
            )
            time.sleep(delay)
            delay *= 2


def _atomic_write(
    path: Path,
    write_payload,
    *,
    retries: int,
    base_delay: float,
) -> Path:
    """Shared core: open a sibling temp file, hand its fd to ``write_payload``,
    then atomically replace ``path`` with retry. Cleans up the temp on failure.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Leading dot + .tmp suffix keeps the temp out of ``*.json`` globs and only
    # exists for the instant between write and replace.
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        write_payload(fd)
        replace_with_retry(tmp_path, path, retries=retries, base_delay=base_delay)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
    return Path(path)


def atomic_write_text(
    path: str | os.PathLike[str],
    data: str,
    *,
    encoding: str = "utf-8",
    retries: int = _DEFAULT_RETRIES,
    base_delay: float = _DEFAULT_BASE_DELAY,
) -> Path:
    """Atomically write ``data`` to ``path``. Drop-in for ``path.write_text(...)``.

    Returns the path written, for chaining. Parent dirs are created as needed.
    """
    path = Path(path)

    def _write(fd: int) -> None:
        # Text mode, default newline=None → matches Path.write_text exactly.
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(data)

    return _atomic_write(path, _write, retries=retries, base_delay=base_delay)


def atomic_write_bytes(
    path: str | os.PathLike[str],
    data: bytes,
    *,
    retries: int = _DEFAULT_RETRIES,
    base_delay: float = _DEFAULT_BASE_DELAY,
) -> Path:
    """Atomically write ``data`` to ``path``. Drop-in for ``path.write_bytes(...)``."""
    path = Path(path)

    def _write(fd: int) -> None:
        with os.fdopen(fd, "wb") as f:
            f.write(data)

    return _atomic_write(path, _write, retries=retries, base_delay=base_delay)
