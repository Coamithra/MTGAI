"""Tests for the local-reasoning anti-loop temperature floor.

Covers ``temperatures.floor_for_local`` (the cross-stage policy) and its
application inside the review gates' shared ``gate_common.stream_flag_batch`` —
the demonstrated "Tame Gemma 4 local overthinking" failure site. Real registry
model ids are used (no mocking): a local llamacpp base must be floored, an
Anthropic model must be left at its precise low temperature.
"""

from __future__ import annotations

import pytest

from mtgai.analysis import conformance as conf_mod
from mtgai.analysis import gate_common
from mtgai.analysis import interactions as inter_mod
from mtgai.generation import temperatures as temps

LOCAL_MODEL = "gemma4-26b-vlad-updated"
CLOUD_MODEL = "claude-haiku-4-5-20251001"


def test_floor_lifts_low_temp_on_local():
    assert temps.floor_for_local(temps.PRECISE, LOCAL_MODEL) == temps.LOCAL_REASONING_FLOOR
    assert temps.floor_for_local(temps.ANALYTICAL, LOCAL_MODEL) == temps.LOCAL_REASONING_FLOOR
    assert temps.floor_for_local(temps.FOCUSED, LOCAL_MODEL) == temps.LOCAL_REASONING_FLOOR


def test_floor_leaves_at_or_above_floor_untouched():
    # A temp already at/above the floor is never lowered.
    assert temps.floor_for_local(temps.LOCAL_REASONING_FLOOR, LOCAL_MODEL) == (
        temps.LOCAL_REASONING_FLOOR
    )
    assert temps.floor_for_local(temps.CREATIVE, LOCAL_MODEL) == temps.CREATIVE


def test_floor_leaves_cloud_precise():
    # Cloud models have no loop pathology — keep the precise low temperature.
    assert temps.floor_for_local(temps.PRECISE, CLOUD_MODEL) == temps.PRECISE
    assert temps.floor_for_local(temps.ANALYTICAL, CLOUD_MODEL) == temps.ANALYTICAL


def test_floor_degrades_on_unknown_or_missing_model():
    assert temps.floor_for_local(temps.PRECISE, None) == temps.PRECISE
    assert temps.floor_for_local(temps.PRECISE, "") == temps.PRECISE
    assert temps.floor_for_local(temps.PRECISE, "no-such-model-xyz") == temps.PRECISE


def _capture_stream(captured: list[float]):
    """A ``stream_text`` stand-in that records the temperature it was called with
    and returns one clean (non-truncated) batch so the retry loop stops."""

    def stream_text(**kwargs):
        captured.append(kwargs.get("temperature"))
        yield {
            "type": "complete",
            "text": "",
            "stop_reason": "stop",
            "input_tokens": 1,
            "output_tokens": 1,
            "model": kwargs.get("model", "m"),
        }

    return stream_text


def _capture_stream_truncating(calls: list[dict], *, clean_after: int):
    """A ``stream_text`` stand-in that records every call's kwargs and reports
    truncation (``stop_reason="length"``) until ``clean_after`` calls have been
    made, forcing the gate's truncation-retry path to fire."""

    def stream_text(**kwargs):
        calls.append(dict(kwargs))
        stop = "stop" if len(calls) >= clean_after else "length"
        yield {
            "type": "complete",
            "text": "",
            "stop_reason": stop,
            "input_tokens": 1,
            "output_tokens": 1,
            "model": kwargs.get("model", "m"),
        }

    return stream_text


def test_stream_flag_batch_floors_base_on_local(monkeypatch):
    captured: list[float] = []
    monkeypatch.setattr(gate_common, "stream_text", _capture_stream(captured))
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    completed, _cost = gate_common.stream_flag_batch(
        system_prompt="sys",
        user_prompt="usr",
        model=LOCAL_MODEL,
        base_temperature=temps.PRECISE,  # 0.2 — would be near-greedy on local
        max_tokens=128,
        log_dir=None,
        name="t",
        valid_ids={"A"},
        on_block=lambda sid, block: None,
    )
    assert completed
    # First (and only) attempt runs at the floored base, not the 0.2 it was given.
    assert captured == [temps.LOCAL_REASONING_FLOOR]


def test_stream_flag_batch_keeps_cloud_base(monkeypatch):
    captured: list[float] = []
    monkeypatch.setattr(gate_common, "stream_text", _capture_stream(captured))
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    gate_common.stream_flag_batch(
        system_prompt="sys",
        user_prompt="usr",
        model=CLOUD_MODEL,
        base_temperature=temps.PRECISE,
        max_tokens=128,
        log_dir=None,
        name="t",
        valid_ids={"A"},
        on_block=lambda sid, block: None,
    )
    assert captured == [temps.PRECISE]


def test_generate_gate_tool_floors_base_on_local(monkeypatch):
    # The non-streaming gate wrapper floors its base the same way as the streamed
    # one (caller-less today, but kept symmetric for future tool-call gates).
    captured: list[float] = []

    def fake_generate(**kwargs):
        captured.append(kwargs.get("temperature"))
        return {"result": {}}

    monkeypatch.setattr(gate_common, "generate_with_tool", fake_generate)
    gate_common.generate_gate_tool(
        base_temperature=temps.PRECISE,
        retries=0,
        model=LOCAL_MODEL,
        system_prompt="s",
        user_prompt="u",
        tool_schema={"name": "t", "input_schema": {}},
    )
    assert captured == [temps.LOCAL_REASONING_FLOOR]


def test_gate_batch_sizes_are_small():
    # Small batches keep each call's reasoning space tractable so the local model
    # terminates instead of looping over a large combinatorial check.
    assert conf_mod.BATCH_SIZE == 20
    assert inter_mod.BATCH_SIZE == 20


# --- DRY sampler truncation-retry escalation ----------------------------------
#
# DRY is a llama.cpp-only sampler — sending it to a hosted model raises
# UnsupportedFeature in llmfacade — so the gate must enable it ONLY for a local
# model, and only on a retry (never the first attempt).


def test_local_retry_dry_helper_gates_on_backend():
    local = gate_common._local_retry_dry(LOCAL_MODEL)
    assert local is not None
    assert local.multiplier == gate_common.RETRY_DRY_MULTIPLIER
    # Hosted / unknown / missing → no DRY (would 400 on Anthropic).
    assert gate_common._local_retry_dry(CLOUD_MODEL) is None
    assert gate_common._local_retry_dry("no-such-model-xyz") is None
    assert gate_common._local_retry_dry(None) is None


def test_stream_flag_batch_enables_dry_only_on_local_retry(monkeypatch):
    calls: list[dict] = []
    # Truncate the first attempt so the retry (attempt 2) fires, then succeed.
    monkeypatch.setattr(
        gate_common, "stream_text", _capture_stream_truncating(calls, clean_after=2)
    )
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    completed, _cost = gate_common.stream_flag_batch(
        system_prompt="sys",
        user_prompt="usr",
        model=LOCAL_MODEL,
        base_temperature=temps.PRECISE,
        max_tokens=128,
        log_dir=None,
        name="t",
        valid_ids={"A"},
        on_block=lambda sid, block: None,
    )
    assert completed
    assert len(calls) == 2
    # First attempt: no DRY. Retry: DRY enabled at the configured multiplier.
    assert calls[0].get("dry") is None
    assert calls[1].get("dry") is not None
    assert calls[1]["dry"].multiplier == gate_common.RETRY_DRY_MULTIPLIER


def test_stream_flag_batch_never_sends_dry_on_cloud(monkeypatch):
    calls: list[dict] = []
    # Force every attempt to truncate so all MAX_BATCH_ATTEMPTS retries run.
    monkeypatch.setattr(
        gate_common, "stream_text", _capture_stream_truncating(calls, clean_after=99)
    )
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    completed, _cost = gate_common.stream_flag_batch(
        system_prompt="sys",
        user_prompt="usr",
        model=CLOUD_MODEL,
        base_temperature=temps.PRECISE,
        max_tokens=128,
        log_dir=None,
        name="t",
        valid_ids={"A"},
        on_block=lambda sid, block: None,
    )
    assert not completed
    assert len(calls) == gate_common.MAX_BATCH_ATTEMPTS
    # No attempt — including the retries — sends DRY to a hosted model.
    assert all(c.get("dry") is None for c in calls)


def test_generate_gate_tool_enables_dry_only_on_local_retry(monkeypatch):
    from mtgai.generation.token_utils import OutputTruncatedError

    calls: list[dict] = []

    def fake_generate(**kwargs):
        calls.append(dict(kwargs))
        if len(calls) == 1:
            raise OutputTruncatedError("truncated", 128, 128)
        return {"result": {}}

    monkeypatch.setattr(gate_common, "generate_with_tool", fake_generate)
    gate_common.generate_gate_tool(
        base_temperature=temps.PRECISE,
        retries=1,
        model=LOCAL_MODEL,
        system_prompt="s",
        user_prompt="u",
        tool_schema={"name": "t", "input_schema": {}},
    )
    assert len(calls) == 2
    assert calls[0].get("dry") is None
    assert calls[1].get("dry") is not None
    assert calls[1]["dry"].multiplier == gate_common.RETRY_DRY_MULTIPLIER


def test_generate_gate_tool_never_sends_dry_on_cloud(monkeypatch):
    from mtgai.generation.token_utils import OutputTruncatedError

    calls: list[dict] = []

    def fake_generate(**kwargs):
        calls.append(dict(kwargs))
        raise OutputTruncatedError("truncated", 128, 128)

    monkeypatch.setattr(gate_common, "generate_with_tool", fake_generate)
    with pytest.raises(OutputTruncatedError):
        gate_common.generate_gate_tool(
            base_temperature=temps.PRECISE,
            retries=2,
            model=CLOUD_MODEL,
            system_prompt="s",
            user_prompt="u",
            tool_schema={"name": "t", "input_schema": {}},
        )
    assert len(calls) == 3
    assert all(c.get("dry") is None for c in calls)
