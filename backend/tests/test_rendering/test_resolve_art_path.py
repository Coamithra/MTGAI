"""Tests for ``CardRenderer.resolve_art_path`` pick resolution.

The renderer must trust ``card.art_path`` — the authoritative pick stamped by
BOTH the best-of-N auto-pick AND the user's manual re-pick / upload override —
over the per-card ``art-selection-logs/<CN>.json`` (which the override endpoints
do NOT rewrite). Trusting the log first silently rendered the judge's stale pick
over the user's override.
"""

import json


def _open_project(tmp_path):
    from mtgai.runtime import active_project
    from mtgai.settings.model_settings import ModelSettings

    settings = ModelSettings(asset_folder=str(tmp_path))
    active_project.write_active_project(
        active_project.ProjectState(set_code="TST", settings=settings)
    )


def _make_card(cn: str, name: str, art_path: str | None = None):
    from mtgai.models.card import Card

    card = Card(name=name, type_line="Creature", art_prompt="a knight")
    update = {"collector_number": cn}
    if art_path is not None:
        update["art_path"] = art_path
    return card.model_copy(update=update)


def _make_art(tmp_path, slug: str, versions: tuple[int, ...]) -> list[str]:
    art_dir = tmp_path / "art"
    art_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for v in versions:
        f = art_dir / f"{slug}_v{v}.png"
        f.write_bytes(b"x")
        files.append(f.name)
    return files


def test_resolve_art_path_prefers_card_art_path_over_selection_log(tmp_path):
    """Regression: user re-picked v2; ``card.art_path`` points at the user's pick
    while the stale selection log still records the judge's old v1 pick. The
    renderer MUST return the user's pick (v2), not the log's v1.
    """
    from mtgai.io.paths import card_slug
    from mtgai.rendering.card_renderer import CardRenderer
    from mtgai.runtime import active_project

    _open_project(tmp_path)
    try:
        cn = "001"
        name = "Storm Knight"
        slug = card_slug(cn, name)
        version_files = _make_art(tmp_path, slug, (1, 2))

        # Stale selection log: the judge's original pick was v1.
        log_dir = tmp_path / "art-selection-logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"{cn}.json").write_text(
            json.dumps({"pick": "v1", "version_files": version_files}),
            encoding="utf-8",
        )

        # User overrode to v2 — stamped onto art_path, but the log was NOT rewritten.
        card = _make_card(cn, name, art_path=f"art/{slug}_v2.png")

        resolved = CardRenderer().resolve_art_path(card)
        assert resolved is not None
        assert resolved == tmp_path / "art" / f"{slug}_v2.png"
    finally:
        active_project.clear_active_project()


def test_resolve_art_path_falls_back_to_selection_log_without_art_path(tmp_path):
    """When no ``art_path`` is stamped, the selection log still resolves the pick."""
    from mtgai.io.paths import card_slug
    from mtgai.rendering.card_renderer import CardRenderer
    from mtgai.runtime import active_project

    _open_project(tmp_path)
    try:
        cn = "002"
        name = "Wandering Mage"
        slug = card_slug(cn, name)
        version_files = _make_art(tmp_path, slug, (1, 2))

        log_dir = tmp_path / "art-selection-logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"{cn}.json").write_text(
            json.dumps({"pick": "v2", "version_files": version_files}),
            encoding="utf-8",
        )

        card = _make_card(cn, name)  # no art_path stamped

        resolved = CardRenderer().resolve_art_path(card)
        assert resolved == tmp_path / "art" / f"{slug}_v2.png"
    finally:
        active_project.clear_active_project()
