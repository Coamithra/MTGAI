"""Tests for the live-progress phase telemetry contract.

Locks the shape of phase events the SSE sink + UI banner depend on.
The streaming code itself is exercised by manual smoke (it needs a
live llama-server / Anthropic call to be useful) — these tests cover
the wiring around the emit helper.
"""

from __future__ import annotations

import logging

import pytest

from mtgai.generation import phase_poller as pp
from mtgai.pipeline import theme_extractor as te


@pytest.fixture(autouse=True)
def _reset_telemetry():
    """Each test runs against a clean structural slot + emitter.

    The module-level state outlives a single test otherwise — a
    leftover emitter from a prior test would leak phase events into
    the next test's captured list.
    """
    te.clear_phase_emitter()
    te._structural.reset()
    # _run_stats backs `elapsed_s`; create a fresh one so elapsed_s is
    # nonzero in a deterministic way.
    te._run_stats = te._RunStats()
    yield
    te.clear_phase_emitter()
    te._structural.reset()


def test_emit_phase_no_op_when_no_emitter():
    """No emitter registered → silent. Used by section-refresh path."""
    # Doesn't raise even though no fn is set.
    te._emit_phase(phase="loading", activity="Loading document")


def test_emit_phase_publishes_minimal_event():
    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    te._emit_phase(phase="loading", activity="Loading document")

    assert len(seen) == 1
    ev = seen[0]
    assert ev["type"] == "phase"
    assert ev["phase"] == "loading"
    assert ev["activity"] == "Loading document"
    assert "elapsed_s" in ev
    assert isinstance(ev["elapsed_s"], (int, float))
    # No structural data set → no structural key.
    assert "structural" not in ev
    assert "prompt_eval" not in ev
    assert "generation" not in ev


def test_emit_phase_includes_structural_when_set():
    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    te._structural.section_index = 3
    te._structural.section_name = "Creature Types"
    te._structural.section_total = 7
    te._structural.chunk_index = 2
    te._structural.chunk_total = 4
    te._emit_phase(phase="extracting", activity="Creature Types chunk 2/4")

    assert seen[0]["structural"] == {
        "section_index": 3,
        "section_name": "Creature Types",
        "section_total": 7,
        "chunk_index": 2,
        "chunk_total": 4,
    }


def test_emit_phase_structural_override_ignores_module_state():
    """JSON subcalls run outside the section/chunk grid — override wins."""
    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    te._structural.section_index = 3
    te._structural.chunk_total = 4
    te._emit_phase(
        phase="json_subcall",
        activity="Constraints",
        structural_override={"section_name": "Constraints", "attempt": 2, "attempt_total": 3},
    )

    assert seen[0]["structural"] == {
        "section_name": "Constraints",
        "attempt": 2,
        "attempt_total": 3,
    }
    assert "section_index" not in seen[0]["structural"]


def test_emit_phase_includes_prompt_eval_and_generation():
    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    te._emit_phase(
        phase="extracting",
        activity="Prompt eval",
        prompt_eval={"processed": 1000, "total": 5000},
    )
    te._emit_phase(
        phase="generation",
        activity="Generating",
        generation={"tokens": 256, "tok_per_sec": 41.5, "elapsed_s": 6.17},
    )

    assert seen[0]["prompt_eval"] == {"processed": 1000, "total": 5000}
    assert seen[1]["generation"] == {"tokens": 256, "tok_per_sec": 41.5, "elapsed_s": 6.17}


def test_emit_phase_swallows_emitter_errors():
    """A throwing emitter must NOT crash the run — telemetry is best-effort."""

    def angry(_event):
        raise RuntimeError("emitter exploded")

    te.set_phase_emitter(angry)
    # If this raised, the streaming generator would unwind and the user
    # would see a broken extraction.
    te._emit_phase(phase="loading", activity="boom test")


def test_structural_state_reset_clears_all_fields():
    te._structural.section_index = 5
    te._structural.section_name = "Themes"
    te._structural.section_total = 7
    te._structural.chunk_index = 3
    te._structural.chunk_total = 4
    te._structural.reset()

    assert te._structural.section_index is None
    assert te._structural.section_name is None
    assert te._structural.section_total is None
    assert te._structural.chunk_index is None
    assert te._structural.chunk_total is None
    assert te._structural.snapshot() is None


def test_structural_state_snapshot_returns_only_set_fields():
    te._structural.reset()
    te._structural.section_index = 2
    te._structural.section_total = 7
    snap = te._structural.snapshot()

    assert snap == {"section_index": 2, "section_total": 7}


def test_clear_phase_emitter_after_set():
    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    te._emit_phase(phase="loading", activity="visible")
    te.clear_phase_emitter()
    te._emit_phase(phase="loading", activity="invisible")

    assert len(seen) == 1
    assert seen[0]["activity"] == "visible"


# ---------------------------------------------------------------------------
# Shared PromptEvalPoller (mtgai.generation.phase_poller)
# ---------------------------------------------------------------------------


class _DummyProvider:
    """Stand-in passed to ``PromptEvalPoller`` — never invoked because the
    unit tests call ``_publish`` directly to skip the HTTP probe.

    ``_http_base`` is the private attr the poller reads to build the resolved
    ``/slots`` URL for its diagnostic WARN.
    """

    _http_base = "http://127.0.0.1:9000"


def _new_poller(activity_prefix: str = "Test") -> pp.PromptEvalPoller:
    """A shared :class:`PromptEvalPoller` that routes ticks through theme's
    ``_emit_phase`` so the captured-event shape matches the SSE contract the
    assertions lock."""
    return pp.PromptEvalPoller(
        provider=_DummyProvider(),
        model_id="dummy",
        emit=te._emit_phase,
        phase_kind="extracting",
        activity_prefix=activity_prefix,
    )


def test_poller_publishes_prompt_eval_above_min_delta():
    """Prompt-eval ticks above the min-delta threshold are emitted.

    Suppressed: 110 (delta=10, below both _MIN_DELTA_TOKENS=200 and
    _MIN_DELTA_FRACTION=0.01 of 10000 = 100). Emitted: 100 (first
    sighting), 400 (delta=300 > 200), 10000 (final tick).
    """
    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    poller = _new_poller()
    poller._publish(
        {"is_processing": True, "n_prompt_tokens_processed": 100, "n_prompt_tokens": 10000}
    )
    poller._publish(
        {"is_processing": True, "n_prompt_tokens_processed": 110, "n_prompt_tokens": 10000}
    )
    poller._publish(
        {"is_processing": True, "n_prompt_tokens_processed": 400, "n_prompt_tokens": 10000}
    )
    poller._publish(
        {"is_processing": True, "n_prompt_tokens_processed": 10000, "n_prompt_tokens": 10000}
    )

    prompt_eval_events = [e for e in seen if "prompt_eval" in e]
    assert len(prompt_eval_events) == 3
    assert prompt_eval_events[0]["prompt_eval"]["processed"] == 100
    assert prompt_eval_events[-1]["prompt_eval"]["processed"] == 10000


def test_poller_suppresses_unchanged_prompt_eval_after_full():
    """Once processed == total, additional ticks at the same value
    must not re-emit. Otherwise the 'fully evaluated, waiting for
    decode' steady state floods the buffer with identical events."""
    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    poller = _new_poller()
    full = {"is_processing": True, "n_prompt_tokens_processed": 5000, "n_prompt_tokens": 5000}
    poller._publish(full)
    poller._publish(full)
    poller._publish(full)

    prompt_eval_events = [e for e in seen if "prompt_eval" in e]
    assert len(prompt_eval_events) == 1


def test_poller_switches_to_generation_when_decoded_positive():
    """Once n_decoded > 0 we report generation tokens, not prompt-eval.

    The min-interval rate cap (1s) means consecutive _publish calls
    inside a test only emit once unless we monkeypatch _last_gen_emit_at.
    """
    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    poller = _new_poller()
    poller._publish(
        {
            "is_processing": True,
            "n_prompt_tokens_processed": 5000,
            "n_prompt_tokens": 5000,
            "n_decoded": 10,
        }
    )
    # Force the rate cap window to the past so the next tick fires.
    poller._last_gen_emit_at = 0.0
    poller._publish(
        {
            "is_processing": True,
            "n_prompt_tokens_processed": 5000,
            "n_prompt_tokens": 5000,
            "n_decoded": 50,
        }
    )

    gen_events = [e for e in seen if "generation" in e]
    assert len(gen_events) == 2
    assert gen_events[0]["generation"]["tokens"] == 10
    assert gen_events[1]["generation"]["tokens"] == 50
    assert gen_events[0]["phase"] == "generation"


def test_poller_generation_rate_cap_suppresses_close_ticks():
    """Two _publish calls within _GEN_MIN_INTERVAL_S of each other
    must collapse to one emission."""
    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    poller = _new_poller()
    poller._publish(
        {
            "is_processing": True,
            "n_prompt_tokens_processed": 5000,
            "n_prompt_tokens": 5000,
            "n_decoded": 10,
        }
    )
    # Don't advance _last_gen_emit_at — the second call should hit the cap.
    poller._publish(
        {
            "is_processing": True,
            "n_prompt_tokens_processed": 5000,
            "n_prompt_tokens": 5000,
            "n_decoded": 50,
        }
    )

    gen_events = [e for e in seen if "generation" in e]
    assert len(gen_events) == 1
    assert gen_events[0]["generation"]["tokens"] == 10


def test_null_poller_is_a_silent_context_manager():
    """The non-streaming section-refresh path uses a ``NullPoller`` so the
    streaming-loop's ``with`` shape works unchanged. It must enter, exit, and
    emit nothing."""
    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    null = pp.NullPoller()
    with null as ctx:
        assert ctx is null

    assert seen == []


def test_poller_omits_dash_when_activity_prefix_empty():
    """Empty activity_prefix used to render a leading separator in the
    activity string. Verify the separator is suppressed."""
    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    poller = _new_poller(activity_prefix="")
    poller._publish(
        {"is_processing": True, "n_prompt_tokens_processed": 1000, "n_prompt_tokens": 5000}
    )

    assert seen[0]["activity"] == "processing prompt 1,000/5,000"


def test_poller_heartbeats_in_dark_window():
    """No counters at all (cold load / build-9010 prompt-eval) → a time-based
    heartbeat keeps the banner alive instead of freezing on a static label."""
    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    poller = _new_poller()
    # is_processing slot with neither prompt-token counters nor n_decoded.
    poller._publish({"is_processing": True})

    assert len(seen) == 1
    assert "evaluating prompt" in seen[0]["activity"]
    assert "prompt_eval" not in seen[0]
    assert "generation" not in seen[0]


def test_poller_heartbeat_rate_limited():
    """Back-to-back dark-window polls collapse to one heartbeat (the 1s gate)."""
    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    poller = _new_poller()
    poller._publish({"is_processing": True})
    poller._publish({"is_processing": True})

    assert len(seen) == 1


def test_poller_restarts_gen_clock_on_next_call(monkeypatch):
    """A span can wrap several LLM calls; the slot's decode counter resets to
    ~0 on each new request. When it drops, the gen clock must restart so tok/s
    reflects the current call rather than a cumulative cross-call average."""
    clock = [1000.0]
    monkeypatch.setattr(pp.time, "monotonic", lambda: clock[0])

    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    poller = _new_poller()

    # Call 1: decode 10 -> 200 over 5s (gen clock anchored at t=1000).
    poller._publish({"is_processing": True, "n_decoded": 10})
    clock[0] = 1005.0
    poller._last_gen_emit_at = 0.0
    poller._publish({"is_processing": True, "n_decoded": 200})

    # Call 2 rolls in: the counter drops to 5 → the clock restarts at t=1006,
    # so this tick's elapsed is ~0 (not 6s) and tok/s isn't a cross-call average.
    clock[0] = 1006.0
    poller._last_gen_emit_at = 0.0
    poller._publish({"is_processing": True, "n_decoded": 5})

    gen_events = [e for e in seen if "generation" in e]
    assert gen_events[-1]["generation"]["tokens"] == 5
    assert gen_events[-1]["generation"]["elapsed_s"] == 0.0


def test_poller_generation_to_prompt_eval_resets_per_call_state():
    """After a call's generation, the next call's prompt-eval (decode back to
    0) flips out of generation so the heartbeat gate + a fresh clock apply."""
    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    poller = _new_poller()
    poller._publish({"is_processing": True, "n_decoded": 100})
    assert poller._switched_to_generation is True

    # Next call begins with prompt-eval (no decode yet) → reset.
    poller._publish({"is_processing": True})
    assert poller._switched_to_generation is False
    assert poller._last_decoded == -1


def test_poller_warns_once_on_slots_failure(caplog):
    """The swallowed /slots failure surfaces once at WARN (with the resolved
    URL) so a genuine drop is catchable; later failures stay at DEBUG."""
    poller = _new_poller()
    with caplog.at_level(logging.WARNING, logger="mtgai.generation.phase_poller"):
        poller._note_slots_failure(RuntimeError("connection refused"))
        poller._note_slots_failure(RuntimeError("connection refused again"))

    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warns) == 1
    assert "/slots probe failed" in warns[0].getMessage()
    assert "http://127.0.0.1:9000/upstream/dummy/slots" in warns[0].getMessage()
    assert poller._warned_slots_failure is True


def test_poller_slots_url_falls_back_without_http_base():
    """A provider with no ``_http_base`` still yields a usable upstream path."""

    class _BareProvider:
        pass

    poller = pp.PromptEvalPoller(provider=_BareProvider(), model_id="m", emit=lambda **_kw: None)
    assert poller._slots_url() == "/upstream/m/slots"


def test_make_poller_null_when_no_project(monkeypatch):
    """No open project → telemetry no-ops rather than raising."""
    import mtgai.runtime.active_project as ap

    def _boom():
        raise RuntimeError("no project open")

    monkeypatch.setattr(ap, "require_active_project", _boom)
    assert isinstance(pp.make_poller("card_gen", lambda **_kw: None), pp.NullPoller)


def test_make_poller_null_for_cloud_model(monkeypatch):
    """A cloud model has no /slots → NullPoller (the showBusy bar drives it)."""
    import mtgai.generation.llm_client as lc
    import mtgai.runtime.active_project as ap

    class _Settings:
        def get_llm_model_id(self, _stage):
            return "claude-sonnet-4-6"

    class _Project:
        settings = _Settings()

    monkeypatch.setattr(ap, "require_active_project", lambda: _Project())
    monkeypatch.setattr(lc, "_resolve_provider", lambda _m: "anthropic")
    assert isinstance(pp.make_poller("card_gen", lambda **_kw: None), pp.NullPoller)


def test_make_poller_live_for_llamacpp_model(monkeypatch):
    """A local model resolves to a real poller bound to that exact model id."""
    import mtgai.generation.llm_client as lc
    import mtgai.runtime.active_project as ap

    class _Settings:
        def get_llm_model_id(self, _stage):
            return "gemma-local-48k"

    class _Project:
        settings = _Settings()

    monkeypatch.setattr(ap, "require_active_project", lambda: _Project())
    monkeypatch.setattr(lc, "_resolve_provider", lambda _m: "llamacpp")
    monkeypatch.setattr(lc, "_get_provider", lambda _name: _DummyProvider())

    poller = pp.make_poller("card_gen", lambda **_kw: None, activity_prefix="Generating cards")
    assert isinstance(poller, pp.PromptEvalPoller)
    assert poller._model_id == "gemma-local-48k"
    assert poller._activity_prefix == "Generating cards"
