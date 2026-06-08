"""Thin supervisor that runs the review server as a child process.

Motivation: during ``art_gen`` Flux generation the server is silently killed by
the OS / a native CUDA crash every ~18-20 images — a *clean* process death with
no Python traceback, because the killed process can't log its own death. Without
an outer observer a crash leaves zero trace and needs a manual reboot+resume.

``serve --supervised`` spawns the *real* server (plain ``serve``) as a child
with ``MTGAI_SUPERVISED_CHILD=1`` so the child runs its liveness heartbeat
(:mod:`mtgai.runtime.heartbeat`). When the child exits, the supervisor records
the exit code + timestamp + the last heartbeat (which names the stage that was
running and the VRAM trend at death) to ``output/supervisor/crash.log``, then —
on an abnormal exit — restarts the child so a long art run survives the silent
kills. A clean exit (code 0, e.g. Ctrl+C) stops the supervisor.

Resume after a restart is *not* automatic here: the user re-opens the project in
the wizard, where :func:`cleanup_orphan_running_stages` demotes the orphaned
RUNNING stage to FAILED and the existing "Retry this step" button resumes it
(resume-skip ⇒ no lost work). Full unattended server-side reopen+retry is a
tracked follow-up.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from datetime import UTC, datetime

from mtgai.runtime import heartbeat

logger = logging.getLogger(__name__)

# A child that dies within this many seconds of starting is treated as a boot
# failure (bad config, port in use, import error), not a mid-run crash — so we
# don't spin in a tight restart loop on something a restart can't fix.
_FAST_FAILURE_S = 30
# Give up after this many *consecutive* fast failures.
_MAX_FAST_FAILURES = 3
# Pause before each restart so a flapping child doesn't hammer the GPU.
_RESTART_BACKOFF_S = 5


def _child_command(port: int, debug: bool) -> list[str]:
    """The argv for the real (un-supervised) server child."""
    cmd = [sys.executable, "-m", "mtgai.review", "serve", "--port", str(port)]
    if debug:
        cmd.append("--debug")
    # ``--open`` is intentionally NOT propagated: the supervisor opens the
    # browser once itself, so a restart doesn't pop a new tab every crash.
    return cmd


def _record_crash(exit_code: int, started_at: datetime, will_restart: bool) -> None:
    """Append a crash record (exit code + last heartbeat) to the crash log."""
    now = datetime.now(UTC)
    uptime_s = (now - started_at).total_seconds()
    last = heartbeat.read_heartbeat()
    record = {
        "crash_detected_at": now.isoformat(),
        "child_started_at": started_at.isoformat(),
        "uptime_seconds": round(uptime_s, 1),
        "exit_code": exit_code,
        "will_restart": will_restart,
        "last_heartbeat": last,
    }
    line = (
        f"[{record['crash_detected_at']}] child exited code={exit_code} "
        f"uptime={record['uptime_seconds']}s restart={will_restart} "
        f"last_alive={last.get('timestamp') if last else 'never'} "
        f"running_stages={last.get('running_stages') if last else '?'} "
        f"vram={last.get('vram') if last else '?'}"
    )
    try:
        path = heartbeat.crash_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        logger.warning("Failed to write crash log", exc_info=True)
    logger.warning("SERVER CRASH: %s", line)


def _open_browser_later(port: int) -> None:
    import threading
    import webbrowser

    timer = threading.Timer(2.0, lambda: webbrowser.open(f"http://localhost:{port}"))
    timer.daemon = True  # never delay a fast supervisor exit (e.g. the give-up path)
    timer.start()


def run_supervised(port: int = 8080, open_browser: bool = False, debug: bool = False) -> int:
    """Run the server under supervision; restart it on abnormal exit.

    Blocks until a clean exit (code 0 — e.g. the user presses Ctrl+C) or the
    crash-loop guard trips. Returns a process exit code (0 = clean stop, 1 =
    gave up after repeated fast failures).
    """
    cmd = _child_command(port, debug)
    env = {**os.environ, heartbeat.ENV_SUPERVISED_CHILD: "1"}

    logger.info("Supervisor starting child: %s", " ".join(cmd))
    print(f"[supervisor] watching server on port {port}; crash log → {heartbeat.crash_log_path()}")
    if open_browser:
        _open_browser_later(port)

    fast_failures = 0
    while True:
        started_at = datetime.now(UTC)
        proc = subprocess.Popen(cmd, env=env)
        try:
            exit_code = proc.wait()
        except KeyboardInterrupt:
            # Ctrl+C reaches both processes; stop the child and exit cleanly.
            logger.info("Supervisor interrupted — stopping child.")
            _terminate(proc)
            return 0

        if exit_code == 0:
            logger.info("Child exited cleanly (code 0) — supervisor done.")
            return 0

        uptime_s = (datetime.now(UTC) - started_at).total_seconds()
        # Only a *fast* death (within _FAST_FAILURE_S of spawn) counts toward the
        # give-up guard — that pattern is a boot failure a restart can't fix. A
        # crash after the server has been up a while resets the counter and is
        # restarted *without bound*: that's the whole point — the motivating
        # art_gen kill lands minutes into a long run (server up well past the
        # window), and we want the supervisor to keep nursing it back through a
        # 180-image run, not cap out. The guard exists only to stop a tight
        # boot-crash loop, not to limit healthy-then-crashed restarts.
        is_fast = uptime_s < _FAST_FAILURE_S
        fast_failures = fast_failures + 1 if is_fast else 0
        give_up = fast_failures >= _MAX_FAST_FAILURES

        _record_crash(exit_code, started_at, will_restart=not give_up)

        if give_up:
            logger.error(
                "Child failed %d times within %ds of start — not restarting "
                "(likely a boot failure, not a mid-run crash).",
                fast_failures,
                _FAST_FAILURE_S,
            )
            print(
                f"[supervisor] giving up after {fast_failures} fast failures; "
                "fix the boot error and relaunch."
            )
            return 1

        print(
            f"[supervisor] server died (code {exit_code} after {uptime_s:.0f}s); "
            f"restarting in {_RESTART_BACKOFF_S}s. Re-open your project + "
            "'Retry this step' to resume."
        )
        time.sleep(_RESTART_BACKOFF_S)


def _terminate(proc: subprocess.Popen) -> None:
    """Best-effort graceful stop of the child, escalating to kill."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    except KeyboardInterrupt:
        # A second Ctrl+C while we're waiting on the graceful stop — don't let
        # it escape and leave the child orphaned; hard-kill and move on.
        proc.kill()
