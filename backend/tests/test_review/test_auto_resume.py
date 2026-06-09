"""Tests for the supervised-server unattended auto-resume."""

import json

from mtgai.review import auto_resume

# --- env gate ----------------------------------------------------------------


def test_is_auto_resume_boot_reads_env(monkeypatch):
    monkeypatch.delenv(auto_resume.ENV_AUTO_RESUME, raising=False)
    assert auto_resume.is_auto_resume_boot() is False
    monkeypatch.setenv(auto_resume.ENV_AUTO_RESUME, "1")
    assert auto_resume.is_auto_resume_boot() is True
    monkeypatch.setenv(auto_resume.ENV_AUTO_RESUME, "0")
    assert auto_resume.is_auto_resume_boot() is False


# --- persistence round-trips -------------------------------------------------


def test_last_project_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(auto_resume.heartbeat, "output_root", lambda: tmp_path)
    assert auto_resume.read_last_project() is None  # absent
    auto_resume.write_last_project('set_code = "ZZZ"\n')
    assert auto_resume.read_last_project() == 'set_code = "ZZZ"\n'
    auto_resume.clear_last_project()
    assert auto_resume.read_last_project() is None
    # clearing an already-absent file is a no-op, not an error.
    auto_resume.clear_last_project()


def test_state_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(auto_resume.heartbeat, "output_root", lambda: tmp_path)
    assert auto_resume.read_state() is None
    auto_resume.write_state({"instance_id": "art_gen", "attempts": 2, "completed": 16})
    on_disk = json.loads(auto_resume.state_path().read_text(encoding="utf-8"))
    assert on_disk == {"instance_id": "art_gen", "attempts": 2, "completed": 16}
    assert auto_resume.read_state() == on_disk
    auto_resume.clear_state()
    assert auto_resume.read_state() is None


# --- the progress-aware retry ceiling (decide) -------------------------------


def test_decide_first_attempt_resumes():
    proceed, state = auto_resume.decide(None, "art_gen", completed=0)
    assert proceed is True
    assert state == {"instance_id": "art_gen", "attempts": 1, "completed": 0}


def test_decide_new_instance_resets_counter():
    prev = {"instance_id": "card_gen", "attempts": 3, "completed": 100}
    proceed, state = auto_resume.decide(prev, "art_gen", completed=0)
    assert proceed is True
    assert state["attempts"] == 1  # pipeline moved on → fresh counter


def test_decide_progress_resets_counter():
    # Same stage, but completed advanced since last attempt (the bounded art_gen
    # kill carried by resume-skip) → resume indefinitely, counter stays at 1.
    prev = {"instance_id": "art_gen", "attempts": 3, "completed": 16}
    proceed, state = auto_resume.decide(prev, "art_gen", completed=32)
    assert proceed is True
    assert state == {"instance_id": "art_gen", "attempts": 1, "completed": 32}


def test_decide_no_progress_counts_and_stops_at_ceiling():
    # A poison stage that crashes at the same completed count every time accrues
    # attempts and is cut off after RESUME_CEILING.
    prev = None
    completed = 5
    instance = "art_gen"
    outcomes = []
    for _ in range(auto_resume.RESUME_CEILING + 2):
        proceed, prev = auto_resume.decide(prev, instance, completed)
        outcomes.append(proceed)
    # First RESUME_CEILING attempts proceed; then it gives up.
    assert outcomes[: auto_resume.RESUME_CEILING] == [True] * auto_resume.RESUME_CEILING
    assert outcomes[auto_resume.RESUME_CEILING] is False
    # decide() still increments past the ceiling (the counter keeps climbing even
    # once we stop resuming), so after RESUME_CEILING + 2 calls attempts == that.
    assert prev["attempts"] == auto_resume.RESUME_CEILING + 2


def test_decide_progress_in_the_middle_extends_the_run():
    # Crash without progress twice, then a round that DID progress resets — the
    # stage is healthy again and keeps resuming.
    prev = None
    prev = auto_resume.decide(prev, "art_gen", 5)[1]  # attempt 1
    prev = auto_resume.decide(prev, "art_gen", 5)[1]  # attempt 2 (no progress)
    proceed, prev = auto_resume.decide(prev, "art_gen", 12)  # progress!
    assert proceed is True
    assert prev["attempts"] == 1


# --- the orchestrator gracefully no-ops when there's nothing to resume -------


def test_run_auto_resume_no_persisted_project(monkeypatch, tmp_path):
    monkeypatch.setattr(auto_resume.heartbeat, "output_root", lambda: tmp_path)
    # No last-project.mtg on disk → returns quietly, never raises.
    auto_resume.maybe_auto_resume()
