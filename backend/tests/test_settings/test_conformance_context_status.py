"""Tests for ``ModelSettings.conformance_context_status`` — the projection that
drives the Project Settings "conformance model too small for the set size"
warning.

The status compares the interaction scan's projected largest batch against the
conformance stage's *effective* context window (the downstream twin, or the
base's full window at/above the >=400-set_size exception) and the same budget
``check_pre_call`` enforces.
"""

from __future__ import annotations

from mtgai.generation import token_utils
from mtgai.settings.model_settings import ModelSettings, SetParams

# The local-default Gemma resolves to its 48k downstream twin for normal sets and
# keeps its 128k base window once a set reaches the full-window exception size.
_TWIN_WINDOW = 48000
_BASE_WINDOW = 128000


def _settings(set_size: int, **kw) -> ModelSettings:
    return ModelSettings(
        set_params=SetParams(set_name="Test", set_size=set_size, mechanic_count=3), **kw
    )


def test_status_shape():
    status = _settings(277).conformance_context_status()
    assert set(status) == {
        "model_name",
        "context_window",
        "set_size",
        "projected_tokens",
        "budget_tokens",
        "fits",
    }
    assert status["set_size"] == 277
    assert isinstance(status["fits"], bool)


def test_normal_set_uses_downstream_twin_window():
    status = _settings(277).conformance_context_status()
    assert status["context_window"] == _TWIN_WINDOW
    # Roomy enough for a normal set on the local default — no warning.
    assert status["fits"] is True


def test_large_set_keeps_base_full_window():
    # At/above the >=400-set_size exception the conformance stage stays on the
    # base's full window, so a big set still fits on the local default.
    status = _settings(600).conformance_context_status()
    assert status["context_window"] == _BASE_WINDOW
    assert status["fits"] is True


def test_empty_set_fits():
    status = _settings(0).conformance_context_status()
    assert status["projected_tokens"] == 0
    assert status["fits"] is True


def test_small_window_does_not_fit(monkeypatch):
    # Simulate a genuinely low-context base: a tiny window can't hold even a
    # modest set's interaction batch, so the warning fires.
    monkeypatch.setattr(token_utils, "get_context_window", lambda _model: 8000)
    status = _settings(277).conformance_context_status()
    assert status["context_window"] == 8000
    assert status["fits"] is False
    assert status["projected_tokens"] > status["budget_tokens"]
