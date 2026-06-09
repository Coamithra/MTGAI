"""Tests for the unified per-card entity tagging (``mtgai.art.entity_tags``).

The single LLM detection pass both the appearance-TEXT path (art_prompts) and the
reference-IMAGE path (char_portraits) consume (card 6a27581d). Covers the
LLM-free logic: detection parsing (single-card entities kept), the per-card /
recurring derivations, sidecar reuse + manual-override preservation, and the
manual-tag write. The LLM call is mocked.
"""

from __future__ import annotations

import json
from pathlib import Path

import mtgai.art.entity_tags as et


def _cards_fixture() -> list[dict]:
    return [
        {"collector_number": "001", "name": "Aria's Charge"},
        {"collector_number": "002", "name": "Aria, Storm Knight"},
        {"collector_number": "003", "name": "Lone Wolf"},
    ]


def _patch_llm(monkeypatch, entities: list[dict]) -> None:
    def fake_generate_with_tool(*_args, **_kwargs):
        return {"result": {"entities": entities}, "input_tokens": 10, "output_tokens": 10}

    monkeypatch.setattr(et, "generate_with_tool", fake_generate_with_tool)
    monkeypatch.setattr(et, "cost_from_result", lambda _r: 0.0)


# ---------------------------------------------------------------------------
# detect_entity_tags
# ---------------------------------------------------------------------------


def test_detect_keeps_single_card_entities(monkeypatch) -> None:
    """Unlike the old recurring detector, single-card entities are KEPT (the text
    path needs their appearance prose)."""
    _patch_llm(
        monkeypatch,
        [
            {"entity_key": "aria", "name": "Aria", "kind": "character", "cards": ["001", "002"]},
            {"entity_key": "lone_wolf", "name": "Lone Wolf", "kind": "creature", "cards": ["003"]},
        ],
    )
    entities, cost = et.detect_entity_tags(_cards_fixture(), {}, model_id="m")
    keys = {e["entity_key"] for e in entities}
    assert keys == {"aria", "lone_wolf"}
    assert cost == 0.0


def test_detect_drops_unknown_collector_numbers(monkeypatch) -> None:
    """Hallucinated collector numbers are filtered; an entity left with none drops."""
    _patch_llm(
        monkeypatch,
        [
            {"entity_key": "ghost", "name": "Ghost", "kind": "character", "cards": ["001", "999"]},
            {"entity_key": "void", "name": "Void", "kind": "element", "cards": ["999"]},
        ],
    )
    entities, _ = et.detect_entity_tags(_cards_fixture(), {}, model_id="m")
    by_key = {e["entity_key"]: e for e in entities}
    assert "void" not in by_key  # all CNs hallucinated -> dropped
    assert by_key["ghost"]["cards"] == ["001"]  # 999 filtered, 001 kept


def test_detect_dedups_keys_and_cards(monkeypatch) -> None:
    _patch_llm(
        monkeypatch,
        [
            {
                "entity_key": "Aria",
                "name": "Aria",
                "kind": "character",
                "cards": ["001", "001", "002"],
            },
            {
                "entity_key": "aria",
                "name": "Aria dup",
                "kind": "character",
                "cards": ["001", "002"],
            },
        ],
    )
    entities, _ = et.detect_entity_tags(_cards_fixture(), {}, model_id="m")
    assert len(entities) == 1
    assert entities[0]["entity_key"] == "aria"  # normalized slug
    assert entities[0]["cards"] == ["001", "002"]  # deduped, order-preserving


def test_detect_empty_cards_is_noop(monkeypatch) -> None:
    _patch_llm(monkeypatch, [{"entity_key": "x", "name": "X", "kind": "c", "cards": ["a"]}])
    assert et.detect_entity_tags([], {}, model_id="m") == ([], 0.0)


# ---------------------------------------------------------------------------
# Derivations: per-card tags + recurring
# ---------------------------------------------------------------------------


def _sidecar() -> dict:
    return {
        "cards": {
            "001": {"tags": [{"entity_key": "aria", "kind": "character"}], "source": "ai"},
            "002": {
                "tags": [
                    {"entity_key": "aria", "kind": "character"},
                    {"entity_key": "lone_wolf", "kind": "creature"},
                ],
                "source": "ai",
            },
            "003": {"tags": [{"entity_key": "lone_wolf", "kind": "creature"}], "source": "ai"},
        },
        "entities_meta": {
            "aria": {"name": "Aria", "kind": "character", "note": ""},
            "lone_wolf": {"name": "Lone Wolf", "kind": "creature", "note": "a wolf"},
        },
    }


def test_effective_card_tags() -> None:
    data = _sidecar()
    assert et.effective_card_tags(data, "002") == [
        {"entity_key": "aria", "kind": "character"},
        {"entity_key": "lone_wolf", "kind": "creature"},
    ]
    assert et.effective_card_tags(data, "missing") == []


def test_recurring_from_tags_applies_2plus_filter() -> None:
    out = et.recurring_from_tags(_sidecar(), min_cards=2)
    by_key = {e["entity_key"]: e for e in out}
    # aria on 001+002 (2) and lone_wolf on 002+003 (2) both recur.
    assert set(by_key) == {"aria", "lone_wolf"}
    assert by_key["aria"]["cards"] == ["001", "002"]
    assert by_key["lone_wolf"]["name"] == "Lone Wolf"  # meta carried through


def test_recurring_from_tags_drops_single_card() -> None:
    data = {
        "cards": {"001": {"tags": [{"entity_key": "solo", "kind": "character"}], "source": "ai"}},
        "entities_meta": {"solo": {"name": "Solo", "kind": "character", "note": ""}},
    }
    assert et.recurring_from_tags(data) == []


# ---------------------------------------------------------------------------
# ensure_entity_tags — detect / reuse / force + manual preservation
# ---------------------------------------------------------------------------


def test_ensure_detects_and_persists_when_absent(monkeypatch, tmp_path: Path) -> None:
    _patch_llm(
        monkeypatch,
        [{"entity_key": "aria", "name": "Aria", "kind": "character", "cards": ["001", "002"]}],
    )
    data, cost = et.ensure_entity_tags(tmp_path, _cards_fixture(), {}, model_id="m")
    assert cost == 0.0  # mocked
    assert data["cards"]["001"]["tags"] == [{"entity_key": "aria", "kind": "character"}]
    assert data["cards"]["003"]["tags"] == []  # not featured -> empty, source ai
    assert et.entity_tags_path(tmp_path).exists()


def test_ensure_reuses_sidecar_without_llm(monkeypatch, tmp_path: Path) -> None:
    et.save_entity_tags(tmp_path, _sidecar())

    def _boom(*_a, **_k):
        raise AssertionError("LLM must not be called when the sidecar exists")

    monkeypatch.setattr(et, "generate_with_tool", _boom)
    data, cost = et.ensure_entity_tags(tmp_path, _cards_fixture(), {}, model_id="m")
    assert cost == 0.0
    assert data["cards"]["002"]["source"] == "ai"


def test_ensure_force_redetects_but_preserves_manual(monkeypatch, tmp_path: Path) -> None:
    # Seed a sidecar where 001 was manually tagged.
    seed = _sidecar()
    seed["cards"]["001"] = {
        "tags": [{"entity_key": "hand_pick", "kind": "faction"}],
        "source": "manual",
    }
    et.save_entity_tags(tmp_path, seed)

    # A fresh detection that would re-tag 001 with 'aria'.
    _patch_llm(
        monkeypatch,
        [{"entity_key": "aria", "name": "Aria", "kind": "character", "cards": ["001", "002"]}],
    )
    data, _ = et.ensure_entity_tags(tmp_path, _cards_fixture(), {}, model_id="m", force=True)
    # 001 keeps the manual tags; 002 gets the AI tags.
    assert data["cards"]["001"]["source"] == "manual"
    assert data["cards"]["001"]["tags"] == [{"entity_key": "hand_pick", "kind": "faction"}]
    assert data["cards"]["002"]["tags"] == [{"entity_key": "aria", "kind": "character"}]


# ---------------------------------------------------------------------------
# set_card_tags — manual override write
# ---------------------------------------------------------------------------


def test_set_card_tags_marks_manual_and_dedups(tmp_path: Path) -> None:
    data = et.set_card_tags(
        tmp_path,
        "005",
        [
            {"entity_key": "Optimus Prime", "kind": "character"},
            {"entity_key": "optimus_prime", "kind": "character"},  # dup after normalize
            {"entity_key": "energon", "kind": "element"},
        ],
    )
    entry = data["cards"]["005"]
    assert entry["source"] == "manual"
    assert entry["tags"] == [
        {"entity_key": "optimus_prime", "kind": "character"},
        {"entity_key": "energon", "kind": "element"},
    ]
    # Persisted + reloadable.
    on_disk = json.loads(et.entity_tags_path(tmp_path).read_text(encoding="utf-8"))
    assert on_disk["cards"]["005"]["source"] == "manual"


# ---------------------------------------------------------------------------
# Sidecar resilience (absent / corrupt / malformed)
# ---------------------------------------------------------------------------


def test_load_returns_skeleton_when_absent(tmp_path: Path) -> None:
    assert et.load_entity_tags(tmp_path) == {"cards": {}, "entities_meta": {}}


def test_load_returns_skeleton_on_corrupt_json(tmp_path: Path) -> None:
    path = et.entity_tags_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")
    assert et.load_entity_tags(tmp_path) == {"cards": {}, "entities_meta": {}}


def test_load_coerces_non_dict_root_and_sections(tmp_path: Path) -> None:
    path = et.entity_tags_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[1, 2, 3]", encoding="utf-8")  # list, not dict
    assert et.load_entity_tags(tmp_path) == {"cards": {}, "entities_meta": {}}
    # A dict root but with a non-dict "cards" section also degrades cleanly.
    path.write_text(json.dumps({"cards": ["nope"], "entities_meta": 5}), encoding="utf-8")
    assert et.load_entity_tags(tmp_path) == {"cards": {}, "entities_meta": {}}


def test_effective_card_tags_skips_malformed_entries() -> None:
    data = {
        "cards": {
            "001": {
                "tags": [
                    {"entity_key": "good", "kind": "character"},
                    {"kind": "character"},  # missing entity_key -> skipped
                    "not-a-dict",  # skipped
                ],
                "source": "ai",
            },
            "002": {"tags": "not-a-list"},  # skipped -> []
        }
    }
    assert et.effective_card_tags(data, "001") == [{"entity_key": "good", "kind": "character"}]
    assert et.effective_card_tags(data, "002") == []
