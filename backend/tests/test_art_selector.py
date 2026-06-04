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
