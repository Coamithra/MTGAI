"""HTTP-level tests for the Project Settings wizard endpoints.

Covers the eight ``/api/wizard/project*`` routes the kickoff tab calls
on first paint and on every form change. Underlying ``ModelSettings``
schema is unit-tested in ``test_settings/test_per_set_settings.py``;
these tests pin the FastAPI contract — payload shape, status codes, and
the cascade-clear gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mtgai.review.server import app
from mtgai.runtime import active_project, ai_lock, extraction_run
from mtgai.settings import model_settings as ms


@pytest.fixture(autouse=True)
def _reset(isolated_output):
    ai_lock.reset_for_tests()
    extraction_run.reset()
    yield
    ai_lock.reset_for_tests()
    extraction_run.reset()


@pytest.fixture
def client():
    return TestClient(app)


def _open_project(
    code: str,
    *,
    asset_dir: str | Path | None = None,
    no_asset_folder: bool = False,
    set_params: ms.SetParams | None = None,
    theme_input: ms.ThemeInputSource | None = None,
) -> None:
    """Pin ``code`` as the active project with the given settings overrides.

    Defaults to seeding an asset_folder under the patched ``OUTPUT_ROOT``
    so endpoints resolving ``set_artifact_dir`` for the cascade-clear
    gate find a real directory. Pass ``no_asset_folder=True`` to leave
    ``asset_folder`` empty for tests that exercise the missing-folder
    path.
    """
    settings = ms.ModelSettings.from_preset("recommended")
    if set_params is not None:
        settings = settings.model_copy(update={"set_params": set_params})
    if theme_input is not None:
        settings = settings.model_copy(update={"theme_input": theme_input})
    if not no_asset_folder:
        if asset_dir is None:
            asset_dir = ms.OUTPUT_ROOT / "sets" / code
        Path(asset_dir).mkdir(parents=True, exist_ok=True)
        settings = settings.model_copy(update={"asset_folder": str(asset_dir)})
    active_project.write_active_project(
        active_project.ProjectState(set_code=code, settings=settings)
    )


# ---------------------------------------------------------------------------
# GET /api/wizard/project
# ---------------------------------------------------------------------------


def test_get_project_payload_shape(client):
    _open_project("TST")
    resp = client.get("/api/wizard/project?set_code=ZZZ")
    assert resp.status_code == 200
    data = resp.json()
    assert data["set_code"] == "TST"
    # Default seed: empty name, default size (277, the standard MTG
    # set), theme_input=none.
    assert data["set_params"]["set_size"] == 277
    assert data["theme_input"]["kind"] == "none"
    # Break points: every stage rendered; merged art/render stages default to checked-on.
    by_id = {bp["stage_id"]: bp for bp in data["break_points"]}
    for sid in ("art_gen", "rendering"):
        assert by_id[sid]["review"] is True
    # No always_review field is exposed any more.
    assert "always_review" not in data["break_points"][0]
    # Registry slice is included so the dropdowns can render.
    assert any(m["key"] == "opus" for m in data["llm_models"])
    assert any(m["key"] == "flux-local" for m in data["image_models"])
    assert "recommended" in data["builtin_presets"]
    assert data["pipeline_started"] is False
    assert data["extraction_active"] is False


def test_project_payload_serves_full_per_stage_model_lists(client):
    """The model-assignment table is server-driven (llm_stages / image_stages),
    mirroring LLM_STAGE_NAMES / IMAGE_STAGE_NAMES so the picker can't drift out
    of sync with the stage registry. Both lists carry {id, label} rows, and the
    formerly-missing stages (visual_refs, char_portraits) are present."""
    from mtgai.settings.model_settings import IMAGE_STAGE_NAMES, LLM_STAGE_NAMES

    _open_project("TST")
    data = client.get("/api/wizard/project").json()

    llm_ids = [row["id"] for row in data["llm_stages"]]
    image_ids = [row["id"] for row in data["image_stages"]]
    assert llm_ids == list(LLM_STAGE_NAMES)
    assert image_ids == list(IMAGE_STAGE_NAMES)
    # The bug this card fixed: these were absent from the picker.
    assert "visual_refs" in llm_ids
    assert "char_portraits" in llm_ids
    # Every row has a non-empty label.
    assert all(row["label"] for row in data["llm_stages"] + data["image_stages"])


def test_new_draft_and_full_payload_agree_on_model_and_override_shape(client):
    """The blank ``/api/project/new`` draft and the full ``/api/wizard/project``
    payload must carry the same model-registry slice + per-stage override channels.

    These two payloads are served by separate handlers but feed the SAME
    Project Settings form, so any divergence crashes the model-assignment
    table. Regression guard for the ``thinking_overrides`` /
    ``supports_thinking`` drift: the New draft lacked both, so the table's
    ``data.thinking_overrides[stage.id]`` read blew up on the first LLM
    stage (``theme_extract``). Both now flow from the shared
    ``_registry_model_lists`` / ``_assignment_overrides_payload`` helpers.
    """
    new_draft = client.post("/api/project/new", json={}).json()["draft"]
    # /new pins the seeded settings as the active project, so the full
    # payload resolves without a second open.
    full = client.get("/api/wizard/project").json()

    # The four per-stage override channels are present in both.
    override_keys = (
        "llm_assignments",
        "image_assignments",
        "effort_overrides",
        "thinking_overrides",
    )
    for key in override_keys:
        assert key in new_draft, f"New draft missing {key}"
        assert key in full, f"Full payload missing {key}"

    # The registry slice is byte-identical (same helper), and every LLM
    # model carries the flags the model table reads — supports_thinking is
    # the one that drifted.
    assert new_draft["llm_models"] == full["llm_models"]
    assert new_draft["image_models"] == full["image_models"]
    assert all("supports_thinking" in m for m in new_draft["llm_models"])

    # The stage rows match too (already shared via _model_stage_lists).
    assert new_draft["llm_stages"] == full["llm_stages"]
    assert new_draft["image_stages"] == full["image_stages"]


def test_get_project_payload_409_when_no_project_open(client):
    """Endpoint reads from the active project — 409 ``no_active_project`` when none is open.

    Set_code is no longer a query/body param: the server uses the
    in-memory pointer (set by /api/project/{open,materialize}) and
    bounces the client to New / Open via the 409.
    """
    resp = client.get("/api/wizard/project")
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_active_project"


# ---------------------------------------------------------------------------
# POST /api/wizard/project/params
# ---------------------------------------------------------------------------


def test_save_params_live_applies_name_and_mechanic_count(client):
    _open_project("TST")
    resp = client.post(
        "/api/wizard/project/params",
        json={"set_code": "TST", "set_name": "Avoria", "mechanic_count": 4},
    )
    assert resp.status_code == 200
    settings = active_project.require_active_project().settings
    assert settings.set_params.set_name == "Avoria"
    assert settings.set_params.mechanic_count == 4


def test_save_params_rejects_negative_mechanic_count(client):
    _open_project("TST")
    resp = client.post(
        "/api/wizard/project/params",
        json={"set_code": "TST", "mechanic_count": -1},
    )
    assert resp.status_code == 400


def test_save_params_live_applies_art_versions(client):
    """The best-of-N knob (art_versions_per_card) applies live and is clamped."""
    from mtgai.settings.model_settings import MAX_ART_VERSIONS

    _open_project("TST")
    resp = client.post(
        "/api/wizard/project/params",
        json={"set_code": "TST", "art_versions_per_card": 4},
    )
    assert resp.status_code == 200
    settings = active_project.require_active_project().settings
    assert settings.set_params.art_versions_per_card == 4

    # Out of range -> 400.
    resp = client.post(
        "/api/wizard/project/params",
        json={"set_code": "TST", "art_versions_per_card": MAX_ART_VERSIONS + 1},
    )
    assert resp.status_code == 400
    resp = client.post(
        "/api/wizard/project/params",
        json={"set_code": "TST", "art_versions_per_card": 0},
    )
    assert resp.status_code == 400


def test_save_params_rejects_mechanic_count_above_max(client):
    """``mechanic_count`` is capped at ``MAX_MECHANIC_COUNT``.

    The candidate pool scales as twice the count, so the pool always
    satisfies the save-and-continue gate; the cap just keeps the count
    (and thus generation cost) from running away.
    """
    from mtgai.generation.mechanic_generator import MAX_MECHANIC_COUNT

    _open_project("TST")
    resp = client.post(
        "/api/wizard/project/params",
        json={"set_code": "TST", "mechanic_count": MAX_MECHANIC_COUNT + 1},
    )
    assert resp.status_code == 400
    assert "maximum mechanics" in resp.json()["error"]
    # Boundary: exactly MAX_MECHANIC_COUNT is allowed.
    resp = client.post(
        "/api/wizard/project/params",
        json={"set_code": "TST", "mechanic_count": MAX_MECHANIC_COUNT},
    )
    assert resp.status_code == 200


def test_save_params_rejects_set_size_above_max(client):
    """``set_size`` is capped at ``MAX_SET_SIZE``.

    Without this backstop an absurd value (e.g. 50000) is accepted and
    persisted, which would spawn a runaway pipeline run. Mirrors the
    mechanic_count cap and the Project Settings UI field's max attribute.
    """
    from mtgai.settings.model_settings import MAX_SET_SIZE

    _open_project("TST")
    resp = client.post(
        "/api/wizard/project/params",
        json={"set_code": "TST", "set_size": MAX_SET_SIZE + 1},
    )
    assert resp.status_code == 400
    assert "maximum set size" in resp.json()["error"]
    # Boundary: exactly MAX_SET_SIZE is allowed.
    resp = client.post(
        "/api/wizard/project/params",
        json={"set_code": "TST", "set_size": MAX_SET_SIZE},
    )
    assert resp.status_code == 200
    settings = active_project.require_active_project().settings
    assert settings.set_params.set_size == MAX_SET_SIZE


def test_save_params_blocks_set_size_change_post_pipeline(client):
    """set_size lives behind the cascade-clear gate once a pipeline-state.json exists."""
    _open_project("TST")
    asset_dir = active_project.require_active_project().settings.asset_folder
    (Path(asset_dir) / "pipeline-state.json").write_text("{}", encoding="utf-8")

    resp = client.post(
        "/api/wizard/project/params",
        json={"set_code": "TST", "set_size": 99},
    )
    assert resp.status_code == 409
    # set_name change is still allowed in the same call.
    resp_ok = client.post(
        "/api/wizard/project/params",
        json={"set_code": "TST", "set_name": "Updated"},
    )
    assert resp_ok.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/wizard/project/theme-input
# ---------------------------------------------------------------------------


def test_save_theme_input_pdf(client):
    _open_project("TST")
    resp = client.post(
        "/api/wizard/project/theme-input",
        json={
            "set_code": "TST",
            "kind": "pdf",
            "upload_id": "abcd1234",
            "filename": "pitch.pdf",
            "char_count": 12345,
        },
    )
    assert resp.status_code == 200
    ti = active_project.require_active_project().settings.theme_input
    assert ti.kind == "pdf"
    assert ti.upload_id == "abcd1234"
    assert ti.uploaded_at is not None  # server stamps this


def test_save_theme_input_blocks_kind_change_post_pipeline(client):
    _open_project("TST")
    asset_dir = active_project.require_active_project().settings.asset_folder
    (Path(asset_dir) / "pipeline-state.json").write_text("{}", encoding="utf-8")
    # First commit: existing — works (matches seeded default).
    client.post(
        "/api/wizard/project/theme-input",
        json={"set_code": "TST", "kind": "none"},
    )
    # Now try to swap kinds — gated.
    resp = client.post(
        "/api/wizard/project/theme-input",
        json={"set_code": "TST", "kind": "existing"},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# POST /api/wizard/project/breaks
# ---------------------------------------------------------------------------


def test_save_break_toggles_on_and_off(client):
    _open_project("TST")
    resp_on = client.post(
        "/api/wizard/project/breaks",
        json={"set_code": "TST", "stage_id": "card_gen", "review": True},
    )
    assert resp_on.status_code == 200
    assert active_project.require_active_project().settings.break_points == {"card_gen": "review"}

    resp_off = client.post(
        "/api/wizard/project/breaks",
        json={"set_code": "TST", "stage_id": "card_gen", "review": False},
    )
    assert resp_off.status_code == 200
    assert active_project.require_active_project().settings.break_points == {}


def test_save_break_human_review_stage_can_be_unchecked(client):
    _open_project("TST")
    resp = client.post(
        "/api/wizard/project/breaks",
        json={"set_code": "TST", "stage_id": "art_gen", "review": False},
    )
    assert resp.status_code == 200
    assert active_project.require_active_project().settings.break_points["art_gen"] == "auto"


def test_save_break_mechanics_can_be_unchecked(client):
    """``mechanics`` is no longer structural — the stage now auto-picks the
    best candidates and writes ``approved.json`` itself, so it can
    auto-continue. Unchecking its pause is allowed.
    """
    _open_project("TST")
    # Setting it back to review is fine (it's the default).
    resp_on = client.post(
        "/api/wizard/project/breaks",
        json={"set_code": "TST", "stage_id": "mechanics", "review": True},
    )
    assert resp_on.status_code == 200
    # Unchecking now succeeds — the AI picker makes the stage self-sufficient.
    resp_off = client.post(
        "/api/wizard/project/breaks",
        json={"set_code": "TST", "stage_id": "mechanics", "review": False},
    )
    assert resp_off.status_code == 200
    assert active_project.require_active_project().settings.break_points["mechanics"] == "auto"


def test_break_points_payload_marks_no_structural_rows(client):
    """No stage is structural today — the AI picker freed ``mechanics``."""
    _open_project("TST")
    resp = client.get("/api/wizard/project")
    by_id = {bp["stage_id"]: bp for bp in resp.json()["break_points"]}
    assert by_id["mechanics"]["structural"] is False
    assert by_id["skeleton"]["structural"] is False


# ---------------------------------------------------------------------------
# POST /api/wizard/project/models
# ---------------------------------------------------------------------------


def test_save_model_llm(client):
    _open_project("TST")
    resp = client.post(
        "/api/wizard/project/models",
        json={"set_code": "TST", "kind": "llm", "stage_id": "card_gen", "value": "haiku"},
    )
    assert resp.status_code == 200
    assert active_project.require_active_project().settings.llm_assignments["card_gen"] == "haiku"


def test_save_model_rejects_unknown_model_id(client):
    """An LLM value not in the registry is a 400 (not silently persisted)."""
    _open_project("TST")
    resp = client.post(
        "/api/wizard/project/models",
        json={
            "set_code": "TST",
            "kind": "llm",
            "stage_id": "card_gen",
            "value": "totally-fake-model-zzz",
        },
    )
    assert resp.status_code == 400
    assert "totally-fake-model-zzz" in resp.json()["error"]
    # Unchanged: the bad value never reaches the assignments map.
    settings = active_project.require_active_project().settings
    assert settings.llm_assignments.get("card_gen") != "totally-fake-model-zzz"


def test_save_model_rejects_unknown_stage_id(client):
    """A stage_id not in the LLM stage registry is a 400."""
    _open_project("TST")
    resp = client.post(
        "/api/wizard/project/models",
        json={
            "set_code": "TST",
            "kind": "llm",
            "stage_id": "not_a_real_stage",
            "value": "haiku",
        },
    )
    assert resp.status_code == 400
    assert "not_a_real_stage" in resp.json()["error"]
    settings = active_project.require_active_project().settings
    assert "not_a_real_stage" not in settings.llm_assignments


def test_save_model_rejects_unknown_image_model_id(client):
    """An image value not in the registry is a 400."""
    _open_project("TST")
    resp = client.post(
        "/api/wizard/project/models",
        json={
            "set_code": "TST",
            "kind": "image",
            "stage_id": "art_gen",
            "value": "not-a-real-image-model",
        },
    )
    assert resp.status_code == 400
    assert "not-a-real-image-model" in resp.json()["error"]


def test_save_model_image_valid_pairing_persists(client):
    """A valid image stage + image model id round-trips with 200."""
    _open_project("TST")
    resp = client.post(
        "/api/wizard/project/models",
        json={"set_code": "TST", "kind": "image", "stage_id": "art_gen", "value": "flux-local"},
    )
    assert resp.status_code == 200
    settings = active_project.require_active_project().settings
    assert settings.image_assignments["art_gen"] == "flux-local"


def test_save_model_effort_clears_on_empty_value(client):
    _open_project("TST")
    # Default has card_gen effort = max
    assert (
        active_project.require_active_project().settings.effort_overrides.get("card_gen") == "max"
    )
    resp = client.post(
        "/api/wizard/project/models",
        json={"set_code": "TST", "kind": "effort", "stage_id": "card_gen", "value": ""},
    )
    assert resp.status_code == 200
    assert "card_gen" not in active_project.require_active_project().settings.effort_overrides


def _seed_running_stage(code: str, stage_id: str) -> None:
    """Seed pipeline-state.json with ``stage_id`` RUNNING for the active set."""
    from mtgai.pipeline.engine import save_state
    from mtgai.pipeline.models import PipelineConfig, StageStatus, create_pipeline_state

    state = create_pipeline_state(PipelineConfig(set_code=code, set_name=code, set_size=20))
    for s in state.stages:
        if s.stage_id == stage_id:
            s.status = StageStatus.RUNNING
    save_state(state)


def test_save_model_409_for_currently_running_stage(client, monkeypatch):
    """A model change for the stage in flight is blocked (the card's
    'unless that stage is already running' exception)."""
    from mtgai.pipeline import server as pipeline_server

    _open_project("TST")
    _seed_running_stage("TST", "skeleton")

    class _BusyEngine:
        is_running = True

        def __init__(self) -> None:
            from mtgai.pipeline.models import PipelineConfig, create_pipeline_state

            self.state = create_pipeline_state(
                PipelineConfig(set_code="TST", set_name="TST", set_size=20),
            )

    monkeypatch.setattr(pipeline_server, "_engine", _BusyEngine())

    resp = client.post(
        "/api/wizard/project/models",
        json={"set_code": "TST", "kind": "llm", "stage_id": "skeleton", "value": "haiku"},
    )
    assert resp.status_code == 409
    assert "running" in resp.json()["error"].lower()
    # The assignment was NOT applied.
    assert (
        active_project.require_active_project().settings.llm_assignments.get("skeleton") != "haiku"
    )


def test_save_model_ok_for_other_stage_while_one_runs(client, monkeypatch):
    """Another stage's model stays freely re-assignable mid-run."""
    from mtgai.pipeline import server as pipeline_server

    _open_project("TST")
    _seed_running_stage("TST", "skeleton")

    class _BusyEngine:
        is_running = True

        def __init__(self) -> None:
            from mtgai.pipeline.models import PipelineConfig, create_pipeline_state

            self.state = create_pipeline_state(
                PipelineConfig(set_code="TST", set_name="TST", set_size=20),
            )

    monkeypatch.setattr(pipeline_server, "_engine", _BusyEngine())

    resp = client.post(
        "/api/wizard/project/models",
        json={"set_code": "TST", "kind": "llm", "stage_id": "card_gen", "value": "haiku"},
    )
    assert resp.status_code == 200
    assert active_project.require_active_project().settings.llm_assignments["card_gen"] == "haiku"


def test_save_model_409_for_theme_extract_while_extracting(client):
    """theme_extract is virtual (runs before the engine), so its 'running'
    signal is the theme extractor worker, not a pipeline stage."""
    _open_project("TST")
    extraction_run.start_run("upload-xyz")
    resp = client.post(
        "/api/wizard/project/models",
        json={"set_code": "TST", "kind": "llm", "stage_id": "theme_extract", "value": "haiku"},
    )
    assert resp.status_code == 409
    assert "running" in resp.json()["error"].lower()


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------


def test_apply_preset_replaces_models_only(client):
    """Applying a preset swaps model assignments; per-project values
    (set_params, theme_input, break_points) are kept."""
    _open_project(
        "TST",
        set_params=ms.SetParams(set_name="MySet", set_size=80),
        theme_input=ms.ThemeInputSource(kind="pdf", filename="x.pdf"),
    )
    # Layer a per-project break point on top after open.
    settings = active_project.require_active_project().settings
    ms.apply_settings(settings.model_copy(update={"break_points": {"card_gen": "review"}}))

    resp = client.post(
        "/api/wizard/project/preset/apply",
        json={"set_code": "TST", "name": "all-haiku"},
    )
    assert resp.status_code == 200
    after = active_project.require_active_project().settings
    # Models swapped.
    assert after.llm_assignments["card_gen"] == "haiku"
    # Per-project fields preserved — break points are NOT part of a preset.
    assert after.set_params.set_name == "MySet"
    assert after.theme_input.kind == "pdf"
    assert after.break_points == {"card_gen": "review"}


def test_apply_preset_rejects_unknown_name(client):
    _open_project("TST")
    resp = client.post(
        "/api/wizard/project/preset/apply",
        json={"set_code": "TST", "name": "does-not-exist"},
    )
    assert resp.status_code == 400


def test_save_profile_excludes_set_params_theme_input_and_break_points(client):
    _open_project(
        "TST",
        set_params=ms.SetParams(set_name="MySet", set_size=80),
        theme_input=ms.ThemeInputSource(kind="pdf", filename="x.pdf"),
    )
    # Layer break_points + thinking on top after open.
    settings = active_project.require_active_project().settings
    ms.apply_settings(
        settings.model_copy(
            update={
                "break_points": {"card_gen": "review"},
                "thinking_overrides": {"mechanics": "disabled"},
            }
        )
    )

    resp = client.post(
        "/api/wizard/project/preset/save",
        json={"set_code": "TST", "name": "my-template"},
    )
    assert resp.status_code == 200
    import tomllib

    profile_path = ms.SETTINGS_DIR / "my-template.toml"
    with open(profile_path, "rb") as f:
        data = tomllib.load(f)
    assert "set_params" not in data
    assert "theme_input" not in data
    # Break points are per-project — they must NOT travel with the profile.
    assert "break_points" not in data
    # Thinking overrides DO travel with the profile.
    assert data.get("thinking_overrides") == {"mechanics": "disabled"}


# ---------------------------------------------------------------------------
# POST /api/wizard/project/start
# ---------------------------------------------------------------------------


def test_start_with_no_input_returns_400(client):
    _open_project("TST")
    resp = client.post("/api/wizard/project/start", json={"set_code": "TST"})
    assert resp.status_code == 400


def test_start_with_existing_skips_extraction(client):
    """kind=existing already has theme.json on disk — Start just navigates."""
    _open_project("TST", theme_input=ms.ThemeInputSource(kind="existing"))
    resp = client.post("/api/wizard/project/start", json={"set_code": "TST"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["extraction_started"] is False
    assert body["navigate_to"] == "/pipeline/theme"


def test_start_with_pdf_needs_live_upload(client):
    """If theme_input.upload_id has expired from cache, return 410."""
    _open_project("TST")
    # Save a theme-input pointing at a non-existent upload_id.
    client.post(
        "/api/wizard/project/theme-input",
        json={
            "set_code": "TST",
            "kind": "pdf",
            "upload_id": "ghosted0",
            "filename": "x.pdf",
            "char_count": 100,
        },
    )
    resp = client.post("/api/wizard/project/start", json={"set_code": "TST"})
    assert resp.status_code == 410


def test_malformed_body_returns_400_not_500(client):
    """A non-JSON body is a clean 400 via the shared ``_read_request_json`` gate.

    Pins the B1 contract: the guard prologue (active-project check) runs first,
    then the body parse — a malformed payload short-circuits with 400 instead of
    bubbling up as a 500.
    """
    _open_project("TST")
    resp = client.post("/api/wizard/project/breaks", content=b"this is not json")
    assert resp.status_code == 400
    assert "valid JSON" in resp.json()["error"]


def test_malformed_body_still_409s_when_no_project_open(client):
    """The active-project guard precedes the body parse: no project -> 409, not 400."""
    active_project.clear_active_project()
    resp = client.post("/api/wizard/project/breaks", content=b"this is not json")
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_active_project"


# ---------------------------------------------------------------------------
# Project-switch drops the SSE replay buffer (no stale FAILED/PENDING leak)
# ---------------------------------------------------------------------------


def _seed_buffer() -> None:
    """Push a terminal failed-status event into the replay buffer.

    Reproduces the leak source: a prior project's run leaves a
    ``pipeline_status: failed`` event in the per-run buffer that would
    otherwise replay onto the next project's fresh page.
    """
    from mtgai.pipeline.server import event_bus

    event_bus.publish("pipeline_status", {"overall_status": "failed"})
    assert event_bus._buffer, "buffer should hold the seeded event"


def _buffer_len() -> int:
    from mtgai.pipeline.server import event_bus

    return len(event_bus._buffer)


def test_project_new_clears_replay_buffer(client):
    """``/api/project/new`` drops the prior run's SSE replay buffer."""
    _open_project("TST")
    _seed_buffer()
    resp = client.post("/api/project/new", json={})
    assert resp.status_code == 200
    assert _buffer_len() == 0


def test_project_open_clears_replay_buffer(client):
    """``/api/project/open`` drops the prior run's SSE replay buffer."""
    _open_project("AAA")
    _seed_buffer()
    toml = ms.dump_project_toml("BBB", ms.ModelSettings.from_preset("recommended"))
    resp = client.post("/api/project/open", json={"toml": toml})
    assert resp.status_code == 200
    assert _buffer_len() == 0


def test_project_materialize_clears_replay_buffer(client):
    """``/api/project/materialize`` drops the prior run's SSE replay buffer."""
    _open_project("TST")
    _seed_buffer()
    resp = client.post("/api/project/materialize", json={"set_code": "NEW"})
    assert resp.status_code == 200
    assert _buffer_len() == 0


def test_busy_switch_without_force_keeps_buffer(client, monkeypatch):
    """A busy 409 (no ``force``) is a *rejected* switch — the buffer stays.

    The reset only fires on the proceed paths, so an interrupted switch
    request can't wipe the in-flight run's replay buffer.
    """
    _open_project("TST")
    _seed_buffer()
    monkeypatch.setattr(ai_lock, "is_running", lambda: True)
    resp = client.post("/api/project/new", json={})
    assert resp.status_code == 409
    assert _buffer_len() > 0
