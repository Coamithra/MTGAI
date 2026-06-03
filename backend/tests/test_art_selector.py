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
