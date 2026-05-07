"""Tests for the trimmed /settings page + cross-set defaults endpoints.

The page is now a read-only model registry view; per-stage assignments
live on each project's Project Settings tab. The default-preset and
saved-profiles surfaces moved off this page entirely (the underlying
endpoints under ``/api/settings/*`` still exist for the per-project
preset picker)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mtgai.review.server import app
from mtgai.settings import model_settings as ms


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_settings_paths(tmp_path, monkeypatch):
    """Redirect every model_settings read/write to a tmp tree.

    The endpoints under /api/settings touch SETTINGS_DIR / GLOBAL_TOML
    directly, so we patch the constants on the module.
    """
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir(parents=True)

    monkeypatch.setattr(ms, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(ms, "SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(ms, "GLOBAL_TOML", settings_dir / "global.toml")
    monkeypatch.setattr(ms, "LEGACY_CURRENT_TOML", settings_dir / "current.toml")
    monkeypatch.setattr(ms, "_global_cache", None, raising=False)
    yield
    monkeypatch.setattr(ms, "_global_cache", None, raising=False)


# ---------------------------------------------------------------------------
# Page render
# ---------------------------------------------------------------------------


class TestSettingsPage:
    def test_renders_model_registry(self, client):
        resp = client.get("/settings")
        assert resp.status_code == 200
        body = resp.text
        # Page title + the two registry sections (LLM + Image).
        assert "Model Registry" in body
        assert 'id="llm-registry-body"' in body

    def test_no_per_stage_assignment_table(self, client):
        """The legacy per-stage table is gone; that lives on the project tab now."""
        resp = client.get("/settings")
        assert resp.status_code == 200
        body = resp.text
        # Legacy markers from the old template.
        assert 'id="llm-assignments-body"' not in body
        assert 'id="image-assignments-body"' not in body
        assert "Apply preset" not in body


# ---------------------------------------------------------------------------
# /api/settings/global
# ---------------------------------------------------------------------------


class TestGlobalSettingsApi:
    def test_get_returns_default_and_lists(self, client):
        resp = client.get("/api/settings/global")
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_preset"] == "recommended"
        assert "recommended" in data["builtin_presets"]
        assert isinstance(data["saved_profiles"], list)

    def test_post_updates_to_known_preset(self, client):
        resp = client.post("/api/settings/global", json={"default_preset": "all-haiku"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Round-trip through GET.
        resp = client.get("/api/settings/global")
        assert resp.json()["default_preset"] == "all-haiku"

    def test_post_rejects_unknown_preset(self, client):
        resp = client.post("/api/settings/global", json={"default_preset": "typo-preset"})
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_post_rejects_reserved_name(self, client):
        resp = client.post("/api/settings/global", json={"default_preset": "global"})
        assert resp.status_code == 400

    def test_post_rejects_empty_string(self, client):
        resp = client.post("/api/settings/global", json={"default_preset": ""})
        assert resp.status_code == 400

    def test_post_accepts_saved_profile(self, client):
        # Drop a saved profile on disk first.
        ms.ModelSettings().save_profile("my-preset")

        resp = client.post("/api/settings/global", json={"default_preset": "my-preset"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# DELETE /api/settings/profile/{name}
# ---------------------------------------------------------------------------


class TestDeleteProfileApi:
    def test_delete_removes_profile_file(self, client):
        ms.ModelSettings().save_profile("scratch-preset")
        path = ms.SETTINGS_DIR / "scratch-preset.toml"
        assert path.exists()

        resp = client.delete("/api/settings/profile/scratch-preset")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert not path.exists()

    def test_delete_rejects_reserved_names(self, client):
        for name in ("global", "current", "Global", "CURRENT"):
            resp = client.delete(f"/api/settings/profile/{name}")
            assert resp.status_code == 400, name

    def test_delete_rejects_path_traversal(self, client):
        # Backslash on Windows is the real concern — FastAPI's `{name}`
        # doesn't match `/`, but `\` passes straight through. (`..` on its
        # own gets collapsed at the HTTP layer before our handler runs;
        # the route 404s, which is safe by accident.)
        for name in ("..%5Cfoo", "foo%5Cbar"):
            resp = client.delete(f"/api/settings/profile/{name}")
            assert resp.status_code == 400, name

    def test_delete_refuses_active_default_preset(self, client):
        ms.ModelSettings().save_profile("active-default")
        ms.apply_global_settings(ms.GlobalSettings(default_preset="active-default"))

        resp = client.delete("/api/settings/profile/active-default")
        assert resp.status_code == 409
        # File is still on disk.
        assert (ms.SETTINGS_DIR / "active-default.toml").exists()

    def test_delete_unknown_returns_404(self, client):
        resp = client.delete("/api/settings/profile/not-a-real-profile")
        assert resp.status_code == 404


class TestSaveProfileValidation:
    """`/api/settings/save` writes to disk; reject names that aren't safe."""

    def test_save_rejects_path_traversal(self, client):
        body = {
            "name": "..\\evil",
            "settings": {"llm_assignments": {}, "image_assignments": {}, "effort_overrides": {}},
        }
        resp = client.post("/api/settings/save", json=body)
        assert resp.status_code == 400
        # Nothing escaped to a parent dir.
        assert not (ms.SETTINGS_DIR.parent / "evil.toml").exists()

    def test_save_rejects_reserved_case_insensitive(self, client):
        body = {
            "name": "Global",
            "settings": {"llm_assignments": {}, "image_assignments": {}, "effort_overrides": {}},
        }
        resp = client.post("/api/settings/save", json=body)
        assert resp.status_code == 400

    def test_save_rejects_empty(self, client):
        body = {
            "name": "",
            "settings": {"llm_assignments": {}, "image_assignments": {}, "effort_overrides": {}},
        }
        resp = client.post("/api/settings/save", json=body)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /api/settings/load — view profile contents
# ---------------------------------------------------------------------------


class TestLoadProfileApi:
    def test_load_returns_settings(self, client):
        custom = ms.ModelSettings(
            llm_assignments={"card_gen": "haiku"},
            image_assignments={},
            effort_overrides={},
        )
        custom.save_profile("scratch-load")

        resp = client.get("/api/settings/load?name=scratch-load")
        assert resp.status_code == 200
        data = resp.json()
        assert data["settings"]["llm_assignments"]["card_gen"] == "haiku"

    def test_load_rejects_reserved(self, client):
        resp = client.get("/api/settings/load?name=global")
        assert resp.status_code == 400
