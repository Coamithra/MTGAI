"""Integration coverage for the Rendering & Final Review tab's wizard endpoints.

Drives ``/api/wizard/rendering/{state,image,save-card,remove-card,approve}``
against a real active project + asset dir. The actual Pillow render is monkey-
patched out (it needs the frame/font assets + is slow + visual) — these tests pin
the *wiring*: which cards appear, that a manual edit re-renders + finalizes the
card, and especially that a removal hard-deletes + renumbers the survivors'
collector numbers contiguously (files renamed, JSON rewritten,
generation_progress repointed, the right cards re-rendered). The pure renumber +
finalize logic is unit-tested in tests/test_render_review.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mtgai.review.server import app
from mtgai.runtime import active_project
from mtgai.settings.model_settings import ModelSettings


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Path subclass so the render-call log can be stashed as an attribute for
    # assertions (plain WindowsPath/PosixPath use __slots__ and reject this).
    class _AssetDir(type(tmp_path)):
        pass

    asset_dir = _AssetDir(tmp_path / "asset")
    (asset_dir / "cards").mkdir(parents=True)
    active_project.write_active_project(
        active_project.ProjectState(
            set_code="ABC", settings=ModelSettings(asset_folder=str(asset_dir))
        )
    )
    # Stub the heavy Pillow render: record (cn, total) calls + drop a stub PNG so
    # has_render flips True, without loading frames/fonts/art.
    rendered: list[tuple[str, int]] = []

    def _fake_render(card_json: dict, total: int) -> None:
        from mtgai.io.paths import card_slug

        rendered.append((card_json["collector_number"], total))
        renders = asset_dir / "renders"
        renders.mkdir(parents=True, exist_ok=True)
        slug = card_slug(card_json["collector_number"], card_json.get("name") or "")
        (renders / f"{slug}.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    monkeypatch.setattr("mtgai.pipeline.server._render_one_card", _fake_render)
    asset_dir._rendered = rendered  # type: ignore[attr-defined]
    yield asset_dir
    active_project.clear_active_project()


def _write_card(asset: Path, fname: str, body: dict) -> None:
    (asset / "cards" / fname).write_text(json.dumps(body), encoding="utf-8")


def _card_body(cn: str, name: str, **extra) -> dict:
    base = {
        "name": name,
        "mana_cost": "{1}{G}",
        "cmc": 2.0,
        "colors": ["G"],
        "type_line": "Creature — Beast",
        "oracle_text": "Trample",
        "power": "2",
        "toughness": "2",
        "rarity": "common",
        "collector_number": cn,
        "set_code": "ABC",
        "card_types": ["Creature"],
        "subtypes": ["Beast"],
        "slot_id": cn,
    }
    base.update(extra)
    return base


def _slug(cn: str, name: str) -> str:
    from mtgai.io.paths import card_slug

    return card_slug(cn, name)


def _files(asset: Path) -> list[str]:
    return sorted(p.name for p in (asset / "cards").glob("*.json"))


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------


def test_state_lists_all_cards_including_lands(client, project: Path) -> None:
    _write_card(project, "B-C-01_alpha.json", _card_body("B-C-01", "Alpha"))
    _write_card(
        project,
        "L-01_plains.json",
        _card_body("L-01", "Plains", type_line="Basic Land — Plains", supertypes=["Basic"]),
    )
    resp = client.get("/api/wizard/rendering/state")
    assert resp.status_code == 200
    data = resp.json()
    cns = sorted(c["collector_number"] for c in data["cards"])
    # Unlike the finalize tab, lands ARE shown (the whole printed set renders).
    assert cns == ["B-C-01", "L-01"]
    assert data["has_content"] is True


def test_state_reports_has_render(client, project: Path) -> None:
    _write_card(project, "B-C-01_alpha.json", _card_body("B-C-01", "Alpha"))
    (project / "renders").mkdir()
    (project / "renders" / f"{_slug('B-C-01', 'Alpha')}.png").write_bytes(b"x")
    data = client.get("/api/wizard/rendering/state").json()
    card = next(c for c in data["cards"] if c["collector_number"] == "B-C-01")
    assert card["has_render"] is True


def test_state_editor_field_strips_injected_reminder(client, project: Path) -> None:
    # The editor textarea binds to `oracle_text_editor` (canonical, reminder-free)
    # while the preview/render keep the injected `oracle_text` — reminder text is
    # auto-injected and never hand-authored, so editing it is discarded on save.
    oracle = (
        "Energize 1 (Whenever this creature attacks, put one Energon counter on it.)\n"
        "Remove an Energon counter: Draw a card."
    )
    _write_card(project, "B-C-01_alpha.json", _card_body("B-C-01", "Alpha", oracle_text=oracle))
    data = client.get("/api/wizard/rendering/state").json()
    card = next(c for c in data["cards"] if c["collector_number"] == "B-C-01")
    assert card["oracle_text"] == oracle  # preview/render keep the injected form
    assert card["oracle_text_editor"] == (
        "Energize 1\nRemove an Energon counter: Draw a card."
    )  # editor gets canonical rules text only


# ---------------------------------------------------------------------------
# image
# ---------------------------------------------------------------------------


def test_image_served_when_present(client, project: Path) -> None:
    _write_card(project, "B-C-01_alpha.json", _card_body("B-C-01", "Alpha"))
    (project / "renders").mkdir()
    (project / "renders" / f"{_slug('B-C-01', 'Alpha')}.png").write_bytes(b"\x89PNG")
    resp = client.get("/api/wizard/rendering/image/B-C-01")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"


def test_image_404_when_not_rendered(client, project: Path) -> None:
    _write_card(project, "B-C-01_alpha.json", _card_body("B-C-01", "Alpha"))
    assert client.get("/api/wizard/rendering/image/B-C-01").status_code == 404


def test_image_404_unknown_card(client, project: Path) -> None:
    assert client.get("/api/wizard/rendering/image/ZZZ").status_code == 404


# ---------------------------------------------------------------------------
# save-card (edit + re-render)
# ---------------------------------------------------------------------------


def _seed_mechanics(asset: Path) -> None:
    """The per-card finalize pass reads mechanics/approved.json."""
    (asset / "mechanics").mkdir(parents=True, exist_ok=True)
    (asset / "mechanics" / "approved.json").write_text("[]", encoding="utf-8")


def test_save_card_finalizes_and_rerenders(client, project: Path) -> None:
    _seed_mechanics(project)
    _write_card(project, "B-C-01_alpha.json", _card_body("B-C-01", "Alpha"))
    resp = client.post(
        "/api/wizard/rendering/save-card",
        json={"collector_number": "B-C-01", "fields": {"oracle_text": "Flying\n{T}: Draw a card."}},
    )
    assert resp.status_code == 200
    saved = json.loads((project / "cards" / "B-C-01_alpha.json").read_text(encoding="utf-8"))
    assert saved["oracle_text"] == "Flying\n{T}: Draw a card."
    # The card was re-rendered (our stub recorded the call).
    assert ("B-C-01", 1) in project._rendered  # type: ignore[attr-defined]


def test_save_card_reinjects_stripped_editor_oracle(client, project: Path) -> None:
    # The safety property behind showing stripped text in the editor: saving the
    # canonical (reminder-free) editor value re-injects the reminder, landing on the
    # exact same injected form — so editing reminder text is a harmless no-op, not data
    # loss. Lock in the strip(view) -> save -> reinject round-trip.
    mech = {
        "name": "Energize",
        "keyword_type": "keyword_ability",
        "reminder_text": "(Whenever this creature attacks, put N Energon counters on it.)",
    }
    (project / "mechanics").mkdir(parents=True, exist_ok=True)
    (project / "mechanics" / "approved.json").write_text(json.dumps([mech]), encoding="utf-8")
    injected = (
        "Energize 1 (Whenever this creature attacks, put one Energon counter on it.)\n"
        "Remove an Energon counter: Draw a card."
    )
    stripped = "Energize 1\nRemove an Energon counter: Draw a card."
    _write_card(project, "B-C-01_alpha.json", _card_body("B-C-01", "Alpha", oracle_text=injected))

    # The editor surfaces the stripped form...
    state = client.get("/api/wizard/rendering/state").json()
    card = next(c for c in state["cards"] if c["collector_number"] == "B-C-01")
    assert card["oracle_text_editor"] == stripped

    # ...and saving it back re-injects to the original injected form (idempotent).
    resp = client.post(
        "/api/wizard/rendering/save-card",
        json={"collector_number": "B-C-01", "fields": {"oracle_text": stripped}},
    )
    assert resp.status_code == 200
    saved = json.loads((project / "cards" / "B-C-01_alpha.json").read_text(encoding="utf-8"))
    assert saved["oracle_text"] == injected
    # The response carries the server-recomputed oracle pair so the tab can apply it
    # back onto its local card and keep the textarea's render source
    # (oracle_text_editor) fresh — otherwise a repaint reverts the edit. The
    # reminder-free editor value round-trips back to exactly what the user saved.
    payload = resp.json()
    assert payload["oracle_text"] == injected
    assert payload["oracle_text_editor"] == stripped


def test_save_card_rename_on_name_change(client, project: Path) -> None:
    _seed_mechanics(project)
    _write_card(project, "B-C-01_alpha.json", _card_body("B-C-01", "Alpha"))
    resp = client.post(
        "/api/wizard/rendering/save-card",
        json={"collector_number": "B-C-01", "fields": {"name": "Alpha Prime"}},
    )
    assert resp.status_code == 200
    assert _files(project) == ["B-C-01_alpha_prime.json"]


def test_save_card_unknown_404(client, project: Path) -> None:
    resp = client.post(
        "/api/wizard/rendering/save-card",
        json={"collector_number": "ZZZ", "fields": {"name": "Ghost"}},
    )
    assert resp.status_code == 404


def test_save_card_rejects_non_editable_field(client, project: Path) -> None:
    _write_card(project, "B-C-01_alpha.json", _card_body("B-C-01", "Alpha"))
    resp = client.post(
        "/api/wizard/rendering/save-card",
        json={"collector_number": "B-C-01", "fields": {"set_code": "HAX"}},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# remove-card (delete + renumber + re-render) — the riskiest path
# ---------------------------------------------------------------------------


def _seed_group(project: Path) -> None:
    _write_card(project, "B-C-01_alpha.json", _card_body("B-C-01", "Alpha"))
    _write_card(project, "B-C-02_beta.json", _card_body("B-C-02", "Beta"))
    _write_card(project, "B-C-03_gamma.json", _card_body("B-C-03", "Gamma"))
    _write_card(project, "G-C-01_delta.json", _card_body("G-C-01", "Delta"))  # other group


def test_remove_middle_renumbers_trailing(client, project: Path) -> None:
    _seed_group(project)
    # Seed renders so we can assert the removed card's render is deleted.
    (project / "renders").mkdir()
    for cn, nm in [("B-C-01", "Alpha"), ("B-C-02", "Beta"), ("B-C-03", "Gamma")]:
        (project / "renders" / f"{_slug(cn, nm)}.png").write_bytes(b"x")

    resp = client.post("/api/wizard/rendering/remove-card", json={"collector_number": "B-C-02"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["removed"] == "B-C-02"
    assert {(r["old"], r["new"]) for r in data["renumbered"]} == {("B-C-03", "B-C-02")}
    assert data["re_rendered"] == ["B-C-02"]

    # Files: Beta gone, Gamma renamed to B-C-02, Alpha + Delta untouched.
    assert _files(project) == ["B-C-01_alpha.json", "B-C-02_gamma.json", "G-C-01_delta.json"]
    gamma = json.loads((project / "cards" / "B-C-02_gamma.json").read_text(encoding="utf-8"))
    assert gamma["collector_number"] == "B-C-02"
    # slot_id stays pinned to the originating skeleton slot (NOT renumbered).
    assert gamma["slot_id"] == "B-C-03"

    # The removed card's render is gone; the old Gamma render is gone too.
    renders = {p.name for p in (project / "renders").glob("*.png")}
    assert f"{_slug('B-C-02', 'Beta')}.png" not in renders
    assert f"{_slug('B-C-03', 'Gamma')}.png" not in renders


def test_remove_last_card_no_renumber(client, project: Path) -> None:
    _seed_group(project)
    resp = client.post("/api/wizard/rendering/remove-card", json={"collector_number": "B-C-03"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["renumbered"] == []
    assert data["re_rendered"] == []
    assert _files(project) == ["B-C-01_alpha.json", "B-C-02_beta.json", "G-C-01_delta.json"]


def test_remove_first_card_shifts_all(client, project: Path) -> None:
    _seed_group(project)
    resp = client.post("/api/wizard/rendering/remove-card", json={"collector_number": "B-C-01"})
    assert resp.status_code == 200
    files = _files(project)
    assert "B-C-01_beta.json" in files  # Beta shifted 02 → 01
    assert "B-C-02_gamma.json" in files  # Gamma shifted 03 → 02
    assert "G-C-01_delta.json" in files  # other group untouched
    beta = json.loads((project / "cards" / "B-C-01_beta.json").read_text(encoding="utf-8"))
    assert beta["collector_number"] == "B-C-01"


def test_remove_other_group_untouched(client, project: Path) -> None:
    _seed_group(project)
    client.post("/api/wizard/rendering/remove-card", json={"collector_number": "B-C-01"})
    # G-C-01 (a different prefix) keeps its number + filename.
    delta = json.loads((project / "cards" / "G-C-01_delta.json").read_text(encoding="utf-8"))
    assert delta["collector_number"] == "G-C-01"


def test_remove_updates_generation_progress(client, project: Path) -> None:
    _seed_group(project)
    cards_dir = project / "cards"
    progress = {
        "filled_slots": {
            "B-C-01": str(cards_dir / "B-C-01_alpha.json"),
            "B-C-02": str(cards_dir / "B-C-02_beta.json"),
            "B-C-03": str(cards_dir / "B-C-03_gamma.json"),
            "G-C-01": str(cards_dir / "G-C-01_delta.json"),
        }
    }
    (project / "generation_progress.json").write_text(json.dumps(progress), encoding="utf-8")

    client.post("/api/wizard/rendering/remove-card", json={"collector_number": "B-C-02"})

    updated = json.loads((project / "generation_progress.json").read_text(encoding="utf-8"))
    filled = updated["filled_slots"]
    # Removed card's slot_id key dropped.
    assert "B-C-02" not in filled
    # Gamma's slot_id key (B-C-03, stable) stays, but its path repoints to the
    # renamed file (collector number B-C-02 now).
    assert filled["B-C-03"].endswith("B-C-02_gamma.json")
    # Untouched entries keep their paths.
    assert filled["B-C-01"].endswith("B-C-01_alpha.json")
    assert filled["G-C-01"].endswith("G-C-01_delta.json")


def test_remove_unknown_404(client, project: Path) -> None:
    _write_card(project, "B-C-01_alpha.json", _card_body("B-C-01", "Alpha"))
    resp = client.post("/api/wizard/rendering/remove-card", json={"collector_number": "ZZZ"})
    assert resp.status_code == 404


def test_remove_swap_no_filename_collision(client, project: Path) -> None:
    """Two cards whose new name == another's old name must not collide mid-rename.

    Removing 01 shifts 02→01 and 03→02. If 03's new file (02) were written before
    02's old file (02) was deleted, they'd collide — the two-phase temp write
    guards this.
    """
    _write_card(project, "B-C-01_a.json", _card_body("B-C-01", "A"))
    _write_card(project, "B-C-02_b.json", _card_body("B-C-02", "B"))
    _write_card(project, "B-C-03_c.json", _card_body("B-C-03", "C"))
    resp = client.post("/api/wizard/rendering/remove-card", json={"collector_number": "B-C-01"})
    assert resp.status_code == 200
    assert _files(project) == ["B-C-01_b.json", "B-C-02_c.json"]


# ---------------------------------------------------------------------------
# approve
# ---------------------------------------------------------------------------


def test_approve_returns_pipeline_nav(client, project: Path) -> None:
    resp = client.post("/api/wizard/rendering/approve")
    assert resp.status_code == 200
    # rendering is the LAST stage → nav falls back to /pipeline.
    assert resp.json()["navigate_to"] == "/pipeline"
