"""Unit tests for the runtime-state aggregator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mtgai.runtime import ai_lock, extraction_run, runtime_state


@pytest.fixture(autouse=True)
def _reset(tmp_path, monkeypatch):
    """Isolate every test from on-disk pipeline / theme files.

    The aggregator scans ``output/sets`` for the most-recent set; we
    redirect it to a per-test tmp dir so a real ASD checkout in the
    repo doesn't bleed into assertions.
    """
    sets_root = tmp_path / "sets"
    settings_dir = tmp_path / "settings"
    sets_root.mkdir(parents=True)
    monkeypatch.setattr(runtime_state, "SETS_ROOT", sets_root)
    monkeypatch.setattr(runtime_state, "OUTPUT_ROOT", tmp_path)
    # Also patch the engine module's OUTPUT_ROOT so the lazy
    # _load_pipeline_summary import resolves to our tmp dir.
    from mtgai.pipeline import engine

    monkeypatch.setattr(engine, "OUTPUT_ROOT", tmp_path)

    # active_set captures OUTPUT_ROOT/SETS_ROOT at import time; redirect
    # those too so the persisted-set step in the resolver chain is
    # isolated per-test rather than reading the real on-disk
    # last_set.toml.
    from mtgai.runtime import active_set

    monkeypatch.setattr(active_set, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(active_set, "SETS_ROOT", sets_root)
    monkeypatch.setattr(active_set, "_SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(active_set, "_LAST_SET_PATH", settings_dir / "last_set.toml")

    ai_lock.reset_for_tests()
    extraction_run.reset()
    yield
    ai_lock.reset_for_tests()
    extraction_run.reset()


def _write_theme(set_dir: Path, theme: dict) -> None:
    set_dir.mkdir(parents=True, exist_ok=True)
    (set_dir / "theme.json").write_text(json.dumps(theme), encoding="utf-8")


def _empty_state_shape(payload: dict) -> None:
    assert payload["ai_lock"]["running"] is False
    assert payload["active_runs"] == {}
    assert payload["pipeline"] is None


def test_compute_returns_default_set_when_disk_is_empty(monkeypatch):
    """No sets on disk -> falls back to MTGAI_REVIEW_SET (default ASD)."""
    monkeypatch.delenv("MTGAI_REVIEW_SET", raising=False)
    payload = runtime_state.compute_runtime_state()
    assert payload["active_set"] == "ASD"
    _empty_state_shape(payload)
    assert payload["theme"] is None


def test_compute_resolves_set_from_disk(tmp_path, monkeypatch):
    """A theme.json on disk picks the active set."""
    monkeypatch.delenv("MTGAI_REVIEW_SET", raising=False)
    sets_root = runtime_state.SETS_ROOT
    _write_theme(sets_root / "ABC", {"code": "ABC", "name": "Test"})
    payload = runtime_state.compute_runtime_state()
    assert payload["active_set"] == "ABC"
    assert payload["theme"] == {"code": "ABC", "name": "Test"}


def test_explicit_set_code_override_wins():
    """Caller-provided set_code wins over disk and env."""
    sets_root = runtime_state.SETS_ROOT
    _write_theme(sets_root / "AAA", {"code": "AAA"})
    _write_theme(sets_root / "BBB", {"code": "BBB", "name": "B"})

    payload = runtime_state.compute_runtime_state("BBB")
    assert payload["active_set"] == "BBB"
    assert payload["theme"]["code"] == "BBB"


def test_compute_includes_ai_lock_running_payload():
    """When the lock is held, the payload reflects it."""
    assert ai_lock.try_acquire("Test action") is True
    try:
        payload = runtime_state.compute_runtime_state()
        assert payload["ai_lock"]["running"] is True
        assert payload["ai_lock"]["running_action"] == "Test action"
    finally:
        ai_lock.release()


def test_compute_includes_active_extraction_run():
    """A live extraction run shows up under active_runs."""
    extraction_run.start_run("upload-xyz")
    extraction_run.append_event({"type": "theme_chunk", "text": "hi"})
    payload = runtime_state.compute_runtime_state()
    assert "theme_extraction" in payload["active_runs"]
    er = payload["active_runs"]["theme_extraction"]
    assert er["upload_id"] == "upload-xyz"
    assert er["events_count"] == 1
    assert isinstance(er["started_at"], str)


def test_compute_omits_completed_extraction_run():
    """Once the run is marked done, it disappears from active_runs."""
    extraction_run.start_run("upload-xyz")
    extraction_run.mark_done("completed")
    payload = runtime_state.compute_runtime_state()
    assert payload["active_runs"] == {}


def test_compute_loads_theme_when_present():
    sets_root = runtime_state.SETS_ROOT
    _write_theme(
        sets_root / "TST",
        {
            "code": "TST",
            "name": "Test Set",
            "constraints": ["c1", "c2"],
            "card_requests": ["r1"],
            "set_size": 60,
        },
    )
    payload = runtime_state.compute_runtime_state("TST")
    assert payload["theme"]["name"] == "Test Set"
    assert payload["theme"]["constraints"] == ["c1", "c2"]


def test_compute_returns_none_theme_for_unknown_set():
    payload = runtime_state.compute_runtime_state("NONE")
    assert payload["theme"] is None


def test_persisted_set_wins_over_mtime_fallback(monkeypatch):
    """If last_set.toml points at an existing set, that wins over the
    legacy "most recently touched theme.json/pipeline-state.json"
    heuristic."""
    monkeypatch.delenv("MTGAI_REVIEW_SET", raising=False)
    sets_root = runtime_state.SETS_ROOT
    _write_theme(sets_root / "OLD", {"code": "OLD"})
    _write_theme(sets_root / "PIN", {"code": "PIN", "name": "Pinned"})

    from mtgai.runtime import active_set as active_set_mod

    active_set_mod.write_active_set("PIN")

    payload = runtime_state.compute_runtime_state()
    assert payload["active_set"] == "PIN"
    assert payload["theme"]["name"] == "Pinned"


def test_persisted_set_skipped_when_dir_missing(monkeypatch):
    """A stale persisted code (set deleted on disk) falls through to
    the mtime fallback rather than silently keeping the dead pointer."""
    monkeypatch.delenv("MTGAI_REVIEW_SET", raising=False)
    sets_root = runtime_state.SETS_ROOT
    _write_theme(sets_root / "ALIVE", {"code": "ALIVE"})

    # Hand-roll the toml since write_active_set checks the dir exists.
    from mtgai.runtime import active_set as active_set_mod

    active_set_mod._LAST_SET_PATH.parent.mkdir(parents=True, exist_ok=True)
    active_set_mod._LAST_SET_PATH.write_text('[runtime]\nactive_set = "GHOST"\n', encoding="utf-8")

    payload = runtime_state.compute_runtime_state()
    assert payload["active_set"] == "ALIVE"


def test_compute_swallows_corrupt_theme_json(tmp_path):
    """A malformed theme.json doesn't blow up the endpoint."""
    sets_root = runtime_state.SETS_ROOT
    bad = sets_root / "BAD"
    bad.mkdir(parents=True)
    (bad / "theme.json").write_text("{ not valid json", encoding="utf-8")
    payload = runtime_state.compute_runtime_state("BAD")
    assert payload["theme"] is None
