"""Tests for the crash-observing server supervisor."""

import sys

from mtgai.review import supervisor


def test_child_command_shape():
    cmd = supervisor._child_command(port=8123, debug=False)
    assert cmd == [sys.executable, "-m", "mtgai.review", "serve", "--port", "8123"]
    assert "--open" not in cmd  # never propagated — supervisor opens the browser once
    assert "--supervised" not in cmd  # the child is the *real* server, not another supervisor


def test_child_command_propagates_debug():
    assert "--debug" in supervisor._child_command(port=8080, debug=True)


def test_record_crash_writes_log_with_heartbeat(monkeypatch, tmp_path):
    from datetime import UTC, datetime

    monkeypatch.setattr(supervisor.heartbeat, "crash_log_path", lambda: tmp_path / "crash.log")
    monkeypatch.setattr(
        supervisor.heartbeat,
        "read_heartbeat",
        lambda: {"timestamp": "2026-06-08T00:00:00", "running_stages": ["art_gen"], "vram": None},
    )

    supervisor._record_crash(exit_code=-9, started_at=datetime.now(UTC), will_restart=True)

    text = (tmp_path / "crash.log").read_text(encoding="utf-8")
    assert "code=-9" in text
    assert "art_gen" in text
    assert "restart=True" in text


class _FakeProc:
    """Stand-in for subprocess.Popen that returns a queued exit code."""

    def __init__(self, exit_code: int):
        self._exit_code = exit_code
        self.terminated = False

    def wait(self):
        return self._exit_code

    def poll(self):
        return self._exit_code

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.terminated = True


def _patch_common(monkeypatch, tmp_path, exit_codes):
    """Wire run_supervised with a sequence of child exit codes."""
    monkeypatch.setattr(supervisor.heartbeat, "crash_log_path", lambda: tmp_path / "crash.log")
    monkeypatch.setattr(supervisor.heartbeat, "read_heartbeat", lambda: None)
    monkeypatch.setattr(supervisor.time, "sleep", lambda _s: None)

    spawned = []
    codes = list(exit_codes)

    def _fake_popen(cmd, env=None):
        proc = _FakeProc(codes.pop(0))
        spawned.append((cmd, env))
        return proc

    monkeypatch.setattr(supervisor.subprocess, "Popen", _fake_popen)
    return spawned


def test_clean_exit_does_not_restart(monkeypatch, tmp_path):
    spawned = _patch_common(monkeypatch, tmp_path, [0])
    rc = supervisor.run_supervised(port=8080)
    assert rc == 0
    assert len(spawned) == 1  # spawned once, clean exit, done


def test_child_marks_supervised_env(monkeypatch, tmp_path):
    spawned = _patch_common(monkeypatch, tmp_path, [0])
    supervisor.run_supervised(port=8080)
    _cmd, env = spawned[0]
    assert env[supervisor.heartbeat.ENV_SUPERVISED_CHILD] == "1"


def test_auto_resume_off_by_default(monkeypatch, tmp_path):
    """Without --auto-resume no child is ever flagged for resume."""
    spawned = _patch_common(monkeypatch, tmp_path, [0])
    supervisor.run_supervised(port=8080)
    _cmd, env = spawned[0]
    assert supervisor.auto_resume.ENV_AUTO_RESUME not in env


def test_auto_resume_flags_restart_not_first_spawn(monkeypatch, tmp_path):
    """With auto-resume on, the first spawn is NOT flagged but a restart IS."""
    times = iter(_slow_uptime_clock())
    monkeypatch.setattr(supervisor, "datetime", _FrozenClock(times))
    # Don't touch the real output dir when the supervisor clears session state.
    monkeypatch.setattr(supervisor.auto_resume, "clear_last_project", lambda: None)
    monkeypatch.setattr(supervisor.auto_resume, "clear_state", lambda: None)
    spawned = _patch_common(monkeypatch, tmp_path, [-9, 0])

    rc = supervisor.run_supervised(port=8080, auto_resume_enabled=True)

    assert rc == 0
    assert len(spawned) == 2
    _, first_env = spawned[0]
    _, restart_env = spawned[1]
    assert supervisor.auto_resume.ENV_AUTO_RESUME not in first_env  # fresh launch
    assert restart_env[supervisor.auto_resume.ENV_AUTO_RESUME] == "1"  # restart resumes


def test_auto_resume_clears_session_state_on_start(monkeypatch, tmp_path):
    """A fresh supervised session forgets a prior session's persisted project."""
    cleared = []
    monkeypatch.setattr(
        supervisor.auto_resume, "clear_last_project", lambda: cleared.append("project")
    )
    monkeypatch.setattr(supervisor.auto_resume, "clear_state", lambda: cleared.append("state"))
    _patch_common(monkeypatch, tmp_path, [0])

    supervisor.run_supervised(port=8080, auto_resume_enabled=True)

    assert set(cleared) == {"project", "state"}


def test_crash_then_clean_exit_restarts_once(monkeypatch, tmp_path):
    # First child crashes (non-zero), gets restarted, second exits clean.
    # Both children "die slow" (uptime > _FAST_FAILURE_S) so it's not a boot loop.
    times = iter(_slow_uptime_clock())
    monkeypatch.setattr(supervisor, "datetime", _FrozenClock(times))
    spawned = _patch_common(monkeypatch, tmp_path, [-9, 0])

    rc = supervisor.run_supervised(port=8080)

    assert rc == 0
    assert len(spawned) == 2  # crash → restart → clean stop


class _CtrlCProc:
    """Child whose blocking wait() raises KeyboardInterrupt (Ctrl+C), then
    reports stopped once terminated."""

    def __init__(self):
        self.terminated = False

    def wait(self, timeout=None):
        if not self.terminated:
            raise KeyboardInterrupt
        return 0

    def poll(self):
        return 0 if self.terminated else None

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.terminated = True


def test_keyboard_interrupt_stops_cleanly(monkeypatch):
    """Ctrl+C during the child's wait() is a clean stop (rc 0), and the child
    is terminated rather than left orphaned."""
    monkeypatch.setattr(supervisor.time, "sleep", lambda _s: None)
    proc = _CtrlCProc()
    monkeypatch.setattr(supervisor.subprocess, "Popen", lambda cmd, env=None: proc)

    rc = supervisor.run_supervised(port=8080)

    assert rc == 0
    assert proc.terminated is True


def test_terminate_escalates_to_kill_on_timeout():
    """A child that ignores terminate() and never exits is hard-killed."""

    class _HangProc:
        def __init__(self):
            self.killed = False

        def poll(self):
            return None  # still running

        def terminate(self):
            pass  # ignores the graceful stop

        def wait(self, timeout=None):
            raise supervisor.subprocess.TimeoutExpired(cmd="x", timeout=timeout)

        def kill(self):
            self.killed = True

    proc = _HangProc()
    supervisor._terminate(proc)
    assert proc.killed is True


def test_terminate_noop_when_already_exited():
    """_terminate returns immediately (no kill) for an already-dead child."""

    class _DeadProc:
        def __init__(self):
            self.killed = False

        def poll(self):
            return 0  # already exited

        def kill(self):
            self.killed = True

    proc = _DeadProc()
    supervisor._terminate(proc)
    assert proc.killed is False


def test_fast_failure_loop_gives_up(monkeypatch, tmp_path):
    # Every child dies instantly (uptime 0 < _FAST_FAILURE_S) → boot-loop guard.
    monkeypatch.setattr(supervisor, "datetime", _FrozenClock(iter(_zero_uptime_clock())))
    spawned = _patch_common(monkeypatch, tmp_path, [1, 1, 1, 1, 1])

    rc = supervisor.run_supervised(port=8080)

    assert rc == 1  # gave up
    assert len(spawned) == supervisor._MAX_FAST_FAILURES


# --- tiny deterministic clock so uptime math is reproducible -----------------


def _slow_uptime_clock():
    """Pairs of (start, end) timestamps where end - start > _FAST_FAILURE_S."""
    from datetime import UTC, datetime, timedelta

    base = datetime(2026, 6, 8, tzinfo=UTC)
    t = base
    while True:
        yield t  # child start
        t = t + timedelta(seconds=supervisor._FAST_FAILURE_S + 60)
        yield t  # crash detected (slow)
        t = t + timedelta(seconds=1)


def _zero_uptime_clock():
    """start == end so every child looks like an instant boot failure."""
    from datetime import UTC, datetime

    base = datetime(2026, 6, 8, tzinfo=UTC)
    while True:
        yield base  # start
        yield base  # crash (same instant → uptime 0)


class _FrozenClock:
    """Minimal stand-in for the module's ``datetime`` exposing ``now(UTC)``."""

    def __init__(self, it):
        self._it = it

    def now(self, _tz=None):
        return next(self._it)
