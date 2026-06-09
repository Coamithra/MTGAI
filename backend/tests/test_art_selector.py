"""Tests for the art-selection tool schema."""

from mtgai.art.art_selector import _build_tool_schema


def _pick_enum(version_count: int) -> list[str]:
    schema = _build_tool_schema(version_count)
    return schema["input_schema"]["properties"]["pick"]["enum"]


def test_pick_enum_matches_version_count():
    """The pick enum lists exactly v1..vN plus 'none' for N versions."""
    assert _pick_enum(2) == ["v1", "v2", "none"]
    assert _pick_enum(3) == ["v1", "v2", "v3", "none"]


def test_pick_enum_supports_four_or_more_versions():
    """A card with 4+ versions must allow the higher picks (regression).

    The old hardcoded ``["v1","v2","v3","none"]`` enum rejected a ``v4`` pick
    even though all four images were shown to the model.
    """
    enum = _pick_enum(4)
    assert "v4" in enum
    assert enum == ["v1", "v2", "v3", "v4", "none"]

    enum6 = _pick_enum(6)
    assert enum6 == ["v1", "v2", "v3", "v4", "v5", "v6", "none"]


def test_tool_schema_shape_is_stable():
    """Non-pick fields keep their structure regardless of version count."""
    schema = _build_tool_schema(3)
    assert schema["name"] == "art_selection"
    props = schema["input_schema"]["properties"]
    assert set(props) == {"pick", "confidence", "reasoning", "artifacts_found"}
    assert schema["input_schema"]["required"] == [
        "pick",
        "confidence",
        "reasoning",
        "artifacts_found",
    ]


# ---------------------------------------------------------------------------
# Pick -> filename mapping (best-of-N pick resolution)
# ---------------------------------------------------------------------------

from mtgai.art.art_selector import (  # noqa: E402
    _pick_to_filename,
    load_art_decisions,
    save_art_decisions,
)


def test_pick_to_filename_maps_index():
    files = ["a_v1.png", "a_v2.png", "a_v3.png"]
    assert _pick_to_filename("v1", files) == "a_v1.png"
    assert _pick_to_filename("v3", files) == "a_v3.png"


def test_pick_to_filename_none_and_out_of_range():
    files = ["a_v1.png", "a_v2.png"]
    assert _pick_to_filename("none", files) is None
    assert _pick_to_filename("v9", files) is None
    assert _pick_to_filename("", files) is None
    assert _pick_to_filename("bogus", files) is None


# ---------------------------------------------------------------------------
# Decisions store round-trip
# ---------------------------------------------------------------------------


def test_decisions_store_round_trip(tmp_path):
    assert load_art_decisions(tmp_path) == {}
    decisions = {"W-C-01": {"pick": "v2", "source": "user"}}
    save_art_decisions(tmp_path, decisions)
    assert load_art_decisions(tmp_path) == decisions
    assert (tmp_path / "art_gen" / "decisions.json").exists()


# ---------------------------------------------------------------------------
# Judge model resolution (the art_select assignment)
# ---------------------------------------------------------------------------


def test_judge_model_resolves_from_art_select_assignment(monkeypatch, tmp_path):
    """select_best_version with no explicit model resolves the project's
    art_select LLM assignment (the user-selectable judge model)."""
    from mtgai.art import art_selector

    seen = {}

    class _Settings:
        def get_llm_model_id(self, stage_id):
            seen["stage_id"] = stage_id
            return "claude-haiku-judge"

    class _Proj:
        settings = _Settings()

    monkeypatch.setattr("mtgai.runtime.active_project.require_active_project", lambda: _Proj())

    # Stub the provider plumbing so no network call happens; we only assert the
    # model the judge resolved.
    from types import SimpleNamespace

    _tc_input = {"pick": "v1", "confidence": "high", "reasoning": "ok", "artifacts_found": []}
    resp = SimpleNamespace(
        tool_calls=[SimpleNamespace(input=_tc_input)],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )

    class _Convo:
        def add_user_message(self, content):
            pass

        def send(self, **kw):
            return resp

    class _FacadeModel:
        def new_conversation(self, **kw):
            return _Convo()

    class _Provider:
        def new_model(self, model):
            seen["model"] = model
            return _FacadeModel()

    monkeypatch.setattr("mtgai.generation.llm_client._get_provider", lambda p: _Provider())
    monkeypatch.setattr("mtgai.generation.llm_client._make_tool", lambda s: s)
    # ImageBlock.from_path reads the file; stub it so we don't need real PNGs.
    _ib = type("IB", (), {"from_path": staticmethod(lambda p: p)})
    monkeypatch.setattr("mtgai.art.art_selector.ImageBlock", _ib)

    v1 = tmp_path / "a_v1.png"
    v2 = tmp_path / "a_v2.png"
    v1.write_bytes(b"x")
    v2.write_bytes(b"x")

    result = art_selector.select_best_version(
        card_name="X",
        collector_number="W-C-01",
        colors=["W"],
        prompt="p",
        image_paths=[v1, v2],
    )
    assert seen["stage_id"] == "art_select"
    assert seen["model"] == "claude-haiku-judge"
    assert result["pick"] == "v1"


def test_judge_routes_transcript_to_given_log_dir(monkeypatch, tmp_path):
    """select_best_version forwards its ``log_dir`` to the llmfacade conversation.

    Regression guard for the fix that routed the best-of-N judge transcript to the
    set folder instead of pinning ``log_dir=False`` (which produced no HTML log).
    """
    from mtgai.art import art_selector

    seen = {}

    class _Settings:
        def get_llm_model_id(self, stage_id):
            return "claude-haiku-judge"

    class _Proj:
        settings = _Settings()

    monkeypatch.setattr("mtgai.runtime.active_project.require_active_project", lambda: _Proj())

    from types import SimpleNamespace

    _tc_input = {"pick": "v1", "confidence": "high", "reasoning": "ok", "artifacts_found": []}
    resp = SimpleNamespace(
        tool_calls=[SimpleNamespace(input=_tc_input)],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )

    class _Convo:
        def add_user_message(self, content):
            pass

        def send(self, **kw):
            return resp

    class _FacadeModel:
        def new_conversation(self, **kw):
            seen["log_dir"] = kw.get("log_dir")
            seen["name"] = kw.get("name")
            return _Convo()

    class _Provider:
        def new_model(self, model):
            return _FacadeModel()

    monkeypatch.setattr("mtgai.generation.llm_client._get_provider", lambda p: _Provider())
    monkeypatch.setattr("mtgai.generation.llm_client._make_tool", lambda s: s)
    _ib = type("IB", (), {"from_path": staticmethod(lambda p: p)})
    monkeypatch.setattr("mtgai.art.art_selector.ImageBlock", _ib)

    v1 = tmp_path / "a_v1.png"
    v2 = tmp_path / "a_v2.png"
    v1.write_bytes(b"x")
    v2.write_bytes(b"x")

    log_dir = tmp_path / "art-selection-logs"
    art_selector.select_best_version(
        card_name="X",
        collector_number="W-C-01",
        colors=["W"],
        prompt="p",
        image_paths=[v1, v2],
        log_dir=log_dir,
    )
    assert seen["log_dir"] == log_dir
    # Named after the tool so the transcript is identifiable (not the opaque fallback).
    assert seen["name"].startswith("art_selection-")


# ---------------------------------------------------------------------------
# Judge-unavailable fallback (no Anthropic credits / keyless / local env)
# ---------------------------------------------------------------------------


def _active_project(tmp_path, art_select: str | None = None):
    """Open a throwaway active project. ``art_select`` overrides the judge model
    assignment (default leaves the local-by-default text-only Gemma, so the
    best-of-N judge pre-flight skips); pass a vision key (e.g. ``"haiku"``) to
    exercise the judge path."""
    from mtgai.runtime import active_project
    from mtgai.settings.model_settings import DEFAULT_LLM_ASSIGNMENTS, ModelSettings

    settings = ModelSettings(asset_folder=str(tmp_path))
    if art_select is not None:
        settings = ModelSettings(
            asset_folder=str(tmp_path),
            llm_assignments={**DEFAULT_LLM_ASSIGNMENTS, "art_select": art_select},
        )
    active_project.write_active_project(
        active_project.ProjectState(set_code="TST", settings=settings)
    )


def _write_card(tmp_path, cn: str, name: str):
    """Write a minimal card JSON + 2 art version PNGs (so the judge path runs)."""
    from mtgai.io.card_io import save_card
    from mtgai.io.paths import card_slug
    from mtgai.models.card import Card

    card = Card(name=name, type_line="Creature", art_prompt="a knight")
    card = card.model_copy(update={"collector_number": cn})
    save_card(card, set_dir=tmp_path)

    art_dir = tmp_path / "art"
    art_dir.mkdir(parents=True, exist_ok=True)
    slug = card_slug(cn, name)
    files = []
    for v in (1, 2):
        f = art_dir / f"{slug}_v{v}.png"
        f.write_bytes(b"x")
        files.append(f.name)
    return files


def test_judge_failure_falls_back_to_v1(tmp_path, monkeypatch):
    """When the vision judge raises for a 2-version card, select_art_for_set
    must still stamp art_path to v1 and record an ``auto_fallback`` decision —
    mirroring the single-version auto-pick — so every card ends with art even
    in a keyless / out-of-credits env. The summary must reflect the fallback.
    """
    from mtgai.art import art_selector
    from mtgai.io.card_io import load_card
    from mtgai.runtime import active_project

    _active_project(tmp_path, art_select="haiku")
    try:
        v_files = _write_card(tmp_path, "W-C-01", "Test Card")

        def _boom(**kwargs):
            raise RuntimeError(
                "Error code: 400 - Your credit balance is too low to access the Anthropic API."
            )

        monkeypatch.setattr(art_selector, "select_best_version", _boom)

        summary = art_selector.select_art_for_set()

        # Every card still gets a stamped art_path -> v1.
        card = load_card(tmp_path / "cards" / "W-C-01_test_card.json")
        assert card.art_path == f"art/{v_files[0]}"

        # The decision records the fallback distinctly.
        decisions = art_selector.load_art_decisions(tmp_path)
        assert decisions["W-C-01"]["pick"] == "v1"
        assert decisions["W-C-01"]["source"] == "auto_fallback"
        assert "judge unavailable" in decisions["W-C-01"]["reasoning"].lower()

        # The summary surfaces the fallback and counts the card as selected
        # (reviewed), not as a hard error.
        assert summary["judge_failed"] == 1
        assert summary["reviewed"] == 1
        assert summary["errors"] == 0
        result = next(r for r in summary["results"] if r.get("collector_number") == "W-C-01")
        assert result["pick"] == "v1"
        assert result["judge_failed"] is True
    finally:
        active_project.clear_active_project()


def test_judge_success_path_unchanged(tmp_path, monkeypatch):
    """The happy path must be identical: a working judge yields a real pick with
    source 'auto' and NO judge_failed flag/count."""
    from mtgai.art import art_selector
    from mtgai.runtime import active_project

    _active_project(tmp_path, art_select="haiku")
    try:
        _write_card(tmp_path, "W-C-01", "Test Card")

        def _ok(**kwargs):
            return {
                "pick": "v2",
                "confidence": "high",
                "reasoning": "v2 is cleaner.",
                "artifacts_found": [],
                "input_tokens": 10,
                "output_tokens": 5,
                "model": "claude-haiku-judge",
            }

        monkeypatch.setattr(art_selector, "select_best_version", _ok)

        summary = art_selector.select_art_for_set()

        decisions = art_selector.load_art_decisions(tmp_path)
        assert decisions["W-C-01"]["source"] == "auto"
        assert decisions["W-C-01"]["pick"] == "v2"
        assert summary["judge_failed"] == 0
        assert summary["judge_skipped"] == 0
        assert summary["reviewed"] == 1
        assert summary["errors"] == 0
    finally:
        active_project.clear_active_project()


# ---------------------------------------------------------------------------
# Text-only judge pre-flight (the default-config bug: judge dead, v2..vN wasted)
# ---------------------------------------------------------------------------


def test_text_only_judge_skips_best_of_n(tmp_path, monkeypatch):
    """When the assigned ``art_select`` model is text-only (the local-by-default
    case), the best-of-N judge must be skipped WITHOUT calling select_best_version
    once per card — auto-picking v1 with an explicit ``judge_skipped`` signal so the
    dead-feature state is visible, not a silent per-card fallback.
    """
    from mtgai.art import art_selector
    from mtgai.io.card_io import load_card
    from mtgai.runtime import active_project

    # Default art_select assignment = local text-only Gemma (no override).
    _active_project(tmp_path)
    try:
        v_files = _write_card(tmp_path, "W-C-01", "Test Card")

        def _must_not_run(**kwargs):
            raise AssertionError("select_best_version must not be called for a text-only judge")

        monkeypatch.setattr(art_selector, "select_best_version", _must_not_run)

        summary = art_selector.select_art_for_set()

        # v1 is stamped, recorded as an auto_fallback (judge skipped).
        card = load_card(tmp_path / "cards" / "W-C-01_test_card.json")
        assert card.art_path == f"art/{v_files[0]}"
        decisions = art_selector.load_art_decisions(tmp_path)
        assert decisions["W-C-01"]["pick"] == "v1"
        assert decisions["W-C-01"]["source"] == "auto_fallback"
        assert "vision-capable" in decisions["W-C-01"]["reasoning"]

        # The summary surfaces the skip distinctly from a judge *failure*.
        assert summary["judge_skipped"] == 1
        assert summary["judge_failed"] == 0
        assert summary["judge_skipped_reason"]
        assert summary["art_select_model"]
        result = next(r for r in summary["results"] if r.get("collector_number") == "W-C-01")
        assert result["judge_skipped"] is True
    finally:
        active_project.clear_active_project()


def test_judge_is_vision_capable():
    """The vision pre-flight reads supports_vision off the registry: True for a
    vision model_id, False for a text-only one + an unknown id."""
    from mtgai.art.art_selector import _judge_is_vision_capable
    from mtgai.settings.model_registry import get_registry
    from mtgai.settings.model_settings import _LOCAL_DEFAULT

    registry = get_registry()
    haiku = registry.get_llm("haiku")
    gemma = registry.get_llm(_LOCAL_DEFAULT)

    assert _judge_is_vision_capable(haiku.model_id) is True
    assert _judge_is_vision_capable(gemma.model_id) is False
    assert _judge_is_vision_capable("no-such-model-xyz") is False
