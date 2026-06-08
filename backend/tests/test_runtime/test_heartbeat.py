"""Tests for the supervised-server liveness heartbeat."""

import json

from mtgai.runtime import heartbeat


def test_is_supervised_child_reads_env(monkeypatch):
    monkeypatch.delenv(heartbeat.ENV_SUPERVISED_CHILD, raising=False)
    assert heartbeat.is_supervised_child() is False
    monkeypatch.setenv(heartbeat.ENV_SUPERVISED_CHILD, "1")
    assert heartbeat.is_supervised_child() is True
    monkeypatch.setenv(heartbeat.ENV_SUPERVISED_CHILD, "0")
    assert heartbeat.is_supervised_child() is False


def test_sample_has_expected_shape(monkeypatch):
    # No GPU / no project in CI — both samplers degrade to None / [].
    monkeypatch.setattr(heartbeat, "_query_vram_mb", lambda: None)
    monkeypatch.setattr(heartbeat, "_query_host_ram_mb", lambda: None)
    monkeypatch.setattr(heartbeat, "_running_stages", lambda: [])
    monkeypatch.setattr(heartbeat, "_active_action", lambda: None)

    rec = heartbeat.sample()
    assert set(rec) == {
        "timestamp",
        "pid",
        "active_action",
        "running_stages",
        "vram",
        "host_ram",
    }
    assert isinstance(rec["pid"], int)
    assert rec["running_stages"] == []


def test_write_then_read_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(heartbeat, "output_root", lambda: tmp_path)
    monkeypatch.setattr(heartbeat, "_query_vram_mb", lambda: {"used_mb": 5000, "free_mb": 7000})
    monkeypatch.setattr(heartbeat, "_query_host_ram_mb", lambda: None)
    monkeypatch.setattr(heartbeat, "_running_stages", lambda: ["art_gen"])
    monkeypatch.setattr(heartbeat, "_active_action", lambda: "pipeline")

    heartbeat.write_heartbeat_now()

    on_disk = json.loads(heartbeat.heartbeat_path().read_text(encoding="utf-8"))
    assert on_disk["running_stages"] == ["art_gen"]
    assert on_disk["active_action"] == "pipeline"
    assert on_disk["vram"]["free_mb"] == 7000

    # read_heartbeat returns the same record.
    assert heartbeat.read_heartbeat() == on_disk


def test_read_heartbeat_missing_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(heartbeat, "output_root", lambda: tmp_path)
    assert heartbeat.read_heartbeat() is None


def test_running_stages_best_effort_no_project():
    """No active project → load_state raises → returns [] (never propagates)."""
    # isolated env: no project is open, so the real _running_stages must swallow.
    assert heartbeat._running_stages() == []


def test_start_heartbeat_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(heartbeat, "output_root", lambda: tmp_path)
    monkeypatch.setattr(heartbeat, "_query_vram_mb", lambda: None)
    monkeypatch.setattr(heartbeat, "_query_host_ram_mb", lambda: None)
    monkeypatch.setattr(heartbeat, "_running_stages", lambda: [])
    monkeypatch.setattr(heartbeat, "_active_action", lambda: None)
    try:
        assert heartbeat.start_heartbeat(interval_s=3600) is True
        assert heartbeat.start_heartbeat(interval_s=3600) is False  # already running
    finally:
        heartbeat.stop_heartbeat()
