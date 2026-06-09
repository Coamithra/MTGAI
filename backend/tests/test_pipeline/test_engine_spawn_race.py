"""Regression tests for the engine-spawn TOCTOU (card 6a285a09).

The bug: the spawn guard was ``_engine is not None and _engine.is_running``, but
``PipelineEngine._running`` only flips True once the spawned thread starts
executing ``run()``. ``_kickoff_pipeline_engine`` is reachable from BOTH the
theme-extraction worker thread (auto-advance) and the event loop (the wizard
Next-step button) with no shared lock around the check-then-spawn. In the window
between ``Thread.start()`` and ``run()`` executing, a second caller passed both
checks and spawned a SECOND engine over the same ``pipeline-state.json`` — the
two interleaved ``save_state`` writes and the loser's stage failed on the AI-lock
busy error.

The fix serializes the check + construct + start window across every spawn path
with ``_engine_spawn_lock`` + the ``_engine_spawning`` flag, and pre-arms the
engine (``_running=True``) under that lock before the thread starts so there is
no observable gap. These tests prove exactly one engine wins a concurrent race.
"""

from __future__ import annotations

import threading

import pytest

from mtgai.pipeline import server as pipeline_server
from mtgai.pipeline.models import (
    PipelineConfig,
    PipelineStatus,
    create_pipeline_state,
)
from mtgai.runtime import active_project, ai_lock, extraction_run
from mtgai.settings import model_settings as ms


@pytest.fixture(autouse=True)
def _reset(isolated_output):
    ai_lock.reset_for_tests()
    extraction_run.reset()
    pipeline_server._engine = None
    pipeline_server._engine_task = None
    with pipeline_server._engine_spawn_lock:
        pipeline_server._engine_spawning = False
    yield
    ai_lock.reset_for_tests()
    extraction_run.reset()
    pipeline_server._engine = None
    pipeline_server._engine_task = None
    with pipeline_server._engine_spawn_lock:
        pipeline_server._engine_spawning = False


def _make_set(code: str) -> None:
    set_dir = ms.OUTPUT_ROOT / "sets" / code
    set_dir.mkdir(parents=True, exist_ok=True)
    active_project.write_active_project(
        active_project.ProjectState(
            set_code=code, settings=ms.ModelSettings(asset_folder=str(set_dir))
        )
    )


@pytest.fixture
def no_thread_start(monkeypatch):
    """Stub ``threading.Thread`` so the engine never actually runs.

    Crucially the engine's ``run()`` body never executes, so ``_running`` is NOT
    set by the engine itself — it is set only by ``_arm_engine`` (the fix). This
    is exactly the original TOCTOU window: the engine has been spawned but its
    thread body hasn't run. A second caller racing in must still be refused.
    """
    started: list[object] = []
    real_thread = threading.Thread

    class FakeThread:
        def __init__(self, *_a, **kwargs):
            self._target = kwargs.get("target")
            self._name = kwargs.get("name", "")

        def start(self):
            # Only intercept the engine's daemon threads (named "pipeline-*"),
            # so the test's own worker threads still run for real.
            if self._name.startswith("pipeline-"):
                started.append(self)
            else:  # pragma: no cover - defensive, tests name their workers plainly
                raise RuntimeError("unexpected non-engine Thread under the stub")

        def join(self, *_a, **_kw):
            return None

    def _dispatch(*a, **kw):
        if str(kw.get("name", "")).startswith("pipeline-"):
            return FakeThread(*a, **kw)
        return real_thread(*a, **kw)

    monkeypatch.setattr(pipeline_server.threading, "Thread", _dispatch)
    return started


def test_concurrent_kickoff_spawns_exactly_one_engine(no_thread_start):
    """Two threads race ``_kickoff_pipeline_engine`` from a barrier; exactly one
    spawns an engine, the other is refused with 'already running'."""
    _make_set("RCE")

    barrier = threading.Barrier(2)
    results: list[tuple] = []
    errors: list[BaseException] = []
    results_lock = threading.Lock()

    def worker():
        try:
            barrier.wait(timeout=10)
            state, err = pipeline_server._kickoff_pipeline_engine("RCE")
            with results_lock:
                results.append((state, err))
        except BaseException as exc:  # surface thread-death in the assert
            with results_lock:
                errors.append(exc)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert not errors, f"worker raised: {errors!r}"
    assert len(results) == 2, f"workers did not both finish: {results}"
    winners = [r for r in results if r[1] is None]
    losers = [r for r in results if r[1] is not None]
    assert len(winners) == 1, f"expected exactly one winner, got {results}"
    assert len(losers) == 1
    assert winners[0][0] is not None
    assert "already running" in losers[0][1].lower()
    # Only ONE engine thread was ever started.
    assert len(no_thread_start) == 1


def test_second_kickoff_refused_while_first_is_mid_spawn(no_thread_start):
    """A second kickoff during the start()->run() window is refused — proving the
    spawn slot + pre-arm (not the lagging ``is_running``) closes the TOCTOU gap.

    With the stubbed thread the engine's ``run()`` body never runs, so the only
    thing marking it busy is ``_arm_engine``; without the fix the second caller
    would pass the old ``is_running`` check and spawn a second engine."""
    _make_set("MID")

    state1, err1 = pipeline_server._kickoff_pipeline_engine("MID")
    assert err1 is None
    assert state1 is not None
    assert len(no_thread_start) == 1

    state2, err2 = pipeline_server._kickoff_pipeline_engine("MID")
    assert state2 is None
    assert "already running" in err2.lower()
    # No second engine thread spawned.
    assert len(no_thread_start) == 1


def test_refused_kickoff_does_not_leave_spawn_slot_stuck(no_thread_start):
    """An early-return refusal (PAUSED state) must release the spawn slot so a
    later legitimate spawn isn't permanently blocked."""
    _make_set("PSE")
    state = create_pipeline_state(PipelineConfig(set_code="PSE", set_name="PSE", set_size=20))
    state.overall_status = PipelineStatus.PAUSED
    pipeline_server.save_state(state)

    st, err = pipeline_server._kickoff_pipeline_engine("PSE")
    assert st is None
    assert "paused" in err.lower()
    # The slot was released on the early return — not left stuck True.
    with pipeline_server._engine_spawn_lock:
        assert pipeline_server._engine_spawning is False
    assert len(no_thread_start) == 0


def test_failed_thread_start_does_not_wedge_the_spawn_slot(monkeypatch):
    """A ``Thread.start()`` that raises AFTER the engine is armed must unwind:
    the dead engine is demoted to not-running and the slot is released, so the
    next legitimate kickoff isn't permanently blocked by a phantom busy engine."""
    _make_set("BAD")

    def _boom(*_a, **_kw):
        class _Exploding:
            def __init__(self, *_aa, **_kk):
                pass

            def start(self):
                raise RuntimeError("can't start a new thread")

            def join(self, *_aa, **_kk):
                return None

        return _Exploding()

    monkeypatch.setattr(pipeline_server.threading, "Thread", _boom)

    with pytest.raises(RuntimeError):
        pipeline_server._kickoff_pipeline_engine("BAD")

    # The armed-but-never-run engine must not leave the slot/is_running wedged.
    with pipeline_server._engine_spawn_lock:
        assert pipeline_server._engine_spawning is False
        assert not pipeline_server._engine_busy()
