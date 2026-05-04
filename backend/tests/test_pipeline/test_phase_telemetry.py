"""Tests for the live-progress phase telemetry contract.

Locks the shape of phase events the SSE sink + UI banner depend on.
The streaming code itself is exercised by manual smoke (it needs a
live llama-server / Anthropic call to be useful) — these tests cover
the wiring around the emit helper.
"""

from __future__ import annotations

import pytest

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


class _DummyProvider:
    """Stand-in passed to ``_PromptEvalPoller`` — never invoked because
    the unit tests call ``_publish`` directly to skip the HTTP probe."""


def test_poller_publishes_prompt_eval_above_min_delta():
    """Prompt-eval ticks above the min-delta threshold are emitted.

    Suppressed: 110 (delta=10, below both _MIN_DELTA_TOKENS=200 and
    _MIN_DELTA_FRACTION=0.01 of 10000 = 100). Emitted: 100 (first
    sighting), 400 (delta=300 > 200), 10000 (final tick).
    """
    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    poller = te._PromptEvalPoller(
        provider=_DummyProvider(),
        model_id="dummy",
        phase_kind="extracting",
        activity_prefix="Test",
    )
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
    poller = te._PromptEvalPoller(
        provider=_DummyProvider(),
        model_id="dummy",
        phase_kind="extracting",
        activity_prefix="Test",
    )
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
    poller = te._PromptEvalPoller(
        provider=_DummyProvider(),
        model_id="dummy",
        phase_kind="extracting",
        activity_prefix="Test",
    )
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
    poller = te._PromptEvalPoller(
        provider=_DummyProvider(),
        model_id="dummy",
        phase_kind="extracting",
        activity_prefix="Test",
    )
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
    """The non-streaming section-refresh path uses ``_NULL_POLLER`` so
    the streaming-loop's ``with`` shape works unchanged. It must enter,
    exit, and emit nothing."""
    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    with te._NULL_POLLER as ctx:
        assert ctx is te._NULL_POLLER

    assert seen == []


def test_poller_omits_dash_when_activity_prefix_empty():
    """Empty activity_prefix used to render a leading ' — ' in the
    activity string. Verify the separator is suppressed."""
    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    poller = te._PromptEvalPoller(
        provider=_DummyProvider(),
        model_id="dummy",
        phase_kind="extracting",
        activity_prefix="",
    )
    poller._publish(
        {"is_processing": True, "n_prompt_tokens_processed": 1000, "n_prompt_tokens": 5000}
    )

    assert seen[0]["activity"] == "processing prompt 1,000/5,000"
    assert not seen[0]["activity"].startswith(" — ")
