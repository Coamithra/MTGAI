"""Server-side liveness heartbeat for the supervised-server mode.

When the server runs under the supervisor (``serve --supervised`` spawns it as
a child with ``MTGAI_SUPERVISED_CHILD=1``), a daemon thread writes a small
``heartbeat.json`` to disk every few seconds recording *when* the server was
last alive, *what* it was doing (the AI-lock action + any RUNNING pipeline
stage), and a host RAM / GPU VRAM sample. The point is observability for the
silent OS/native kills that take the server down with no traceback (the
``art_gen`` Flux crash): the heartbeat is the only record of *when* death
happened and whether VRAM was climbing toward it, since the killed process
can't log its own death — the outer supervisor reads the last heartbeat to
attribute the crash.

This module writes nothing unless :func:`start_heartbeat` is called, so a
normal (un-supervised) run is completely unaffected.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path

from mtgai.io.paths import output_root

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_S = 15
# Set by the supervisor on the child it spawns; flags the child to run the
# heartbeat thread (a normal, un-supervised run leaves it unset → no heartbeat).
ENV_SUPERVISED_CHILD = "MTGAI_SUPERVISED_CHILD"

_thread: threading.Thread | None = None
_stop = threading.Event()
_lock = threading.Lock()


def supervisor_dir() -> Path:
    """Directory holding the heartbeat + crash log (gitignored ``output/``)."""
    return output_root() / "supervisor"


def heartbeat_path() -> Path:
    """Path of the JSON file the heartbeat thread rewrites each tick."""
    return supervisor_dir() / "heartbeat.json"


def crash_log_path() -> Path:
    """Append-only log the supervisor writes a record to on each child death."""
    return supervisor_dir() / "crash.log"


def is_supervised_child() -> bool:
    """True when this process was spawned by the supervisor (env flag set)."""
    return os.environ.get(ENV_SUPERVISED_CHILD) == "1"


def _query_vram_mb() -> dict[str, int] | None:
    """GPU VRAM (total / used / free MB) via nvidia-smi; ``None`` if unavailable.

    Kept self-contained (a tiny copy of ``art.image_generator.get_vram_info``)
    so the runtime layer doesn't import the art layer just to sample memory.
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        # First GPU only — single-GPU is the assumption everywhere else here.
        parts = result.stdout.strip().splitlines()[0].split(", ")
        return {
            "total_mb": int(parts[0]),
            "used_mb": int(parts[1]),
            "free_mb": int(parts[2]),
        }
    except Exception:
        return None


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _query_host_ram_mb() -> dict[str, int] | None:
    """Host RAM (total / used / free MB); ``None`` off Windows or on failure.

    Uses the Win32 ``GlobalMemoryStatusEx`` via ctypes so we add no dependency
    (psutil isn't in the project). Best-effort — any failure returns ``None``.
    """
    try:
        stat = _MemoryStatusEx()
        stat.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):  # type: ignore[attr-defined]
            return None
        total = stat.ullTotalPhys // (1024 * 1024)
        free = stat.ullAvailPhys // (1024 * 1024)
        return {"total_mb": total, "used_mb": total - free, "free_mb": free}
    except Exception:
        return None


def _running_stages() -> list[str]:
    """Instance ids of any pipeline stage currently RUNNING, best-effort."""
    try:
        from mtgai.pipeline.engine import load_state
        from mtgai.pipeline.models import StageStatus

        state = load_state()
        if state is None:
            return []
        return [s.instance_id for s in state.stages if s.status == StageStatus.RUNNING]
    except Exception:
        return []


def _active_action() -> str | None:
    """Name of the AI-lock action in flight (e.g. ``"pipeline"``), or ``None``."""
    try:
        from mtgai.runtime import ai_lock

        action = ai_lock.current_action()
        return action.name if action is not None else None
    except Exception:
        return None


def sample() -> dict:
    """Build one heartbeat record (cheap enough to call every tick)."""
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "pid": os.getpid(),
        "active_action": _active_action(),
        "running_stages": _running_stages(),
        "vram": _query_vram_mb(),
        "host_ram": _query_host_ram_mb(),
    }


def write_heartbeat_now() -> None:
    """Write a single heartbeat sample immediately (best-effort)."""
    try:
        path = heartbeat_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sample(), indent=2), encoding="utf-8")
    except Exception:
        logger.debug("heartbeat write failed", exc_info=True)


def read_heartbeat() -> dict | None:
    """Read the last heartbeat record, or ``None`` if absent/unreadable."""
    try:
        return json.loads(heartbeat_path().read_text(encoding="utf-8"))
    except Exception:
        return None


def _loop(interval_s: int) -> None:
    write_heartbeat_now()
    while not _stop.wait(interval_s):
        write_heartbeat_now()


def start_heartbeat(interval_s: int = DEFAULT_INTERVAL_S) -> bool:
    """Start the background heartbeat thread (idempotent). Returns True if started.

    A no-op (returns False) if a heartbeat thread is already running. The thread
    is a daemon so it never blocks process exit, and the VRAM sample naturally
    captures the ``art_gen`` climb because the thread ticks the whole time the
    stage runs.
    """
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return False
        _stop.clear()
        _thread = threading.Thread(
            target=_loop, args=(interval_s,), name="mtgai-heartbeat", daemon=True
        )
        _thread.start()
    logger.info("Heartbeat started → %s (every %ds)", heartbeat_path(), interval_s)
    return True


def stop_heartbeat() -> None:
    """Signal the heartbeat thread to stop (best-effort; mainly for tests)."""
    _stop.set()
