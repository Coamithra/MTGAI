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


class _FakePoller:
    """Minimal stand-in for slot_poller integration tests."""


def test_poller_publishes_prompt_eval_above_min_delta():
    """Prompt-eval ticks above the min-delta threshold are emitted."""
    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    poller = te._PromptEvalPoller(
        provider=_FakePoller(),
        model_id="dummy",
        phase_kind="extracting",
        activity_prefix="Test",
    )
    # First sighting always emits.
    poller._publish(
        {"is_processing": True, "n_prompt_tokens_processed": 100, "n_prompt_tokens": 10000}
    )
    # Below min-delta — suppressed.
    poller._publish(
        {"is_processing": True, "n_prompt_tokens_processed": 110, "n_prompt_tokens": 10000}
    )
    # Above min-delta (>= 200 tokens) — emitted.
    poller._publish(
        {"is_processing": True, "n_prompt_tokens_processed": 400, "n_prompt_tokens": 10000}
    )
    # Final tick (processed == total) — always emitted.
    poller._publish(
        {"is_processing": True, "n_prompt_tokens_processed": 10000, "n_prompt_tokens": 10000}
    )

    prompt_eval_events = [e for e in seen if "prompt_eval" in e]
    assert len(prompt_eval_events) == 3  # 100, 400, 10000 — 110 was below threshold
    assert prompt_eval_events[0]["prompt_eval"]["processed"] == 100
    assert prompt_eval_events[-1]["prompt_eval"]["processed"] == 10000


def test_poller_switches_to_generation_when_decoded_positive():
    """Once n_decoded > 0 we report generation tokens, not prompt-eval."""
    seen: list[dict] = []
    te.set_phase_emitter(seen.append)
    poller = te._PromptEvalPoller(
        provider=_FakePoller(),
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
