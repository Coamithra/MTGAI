"""Unit tests for ``mtgai.pipeline.stage_hooks`` — the single source of the
streaming-stage SSE hooks shared by the engine runners and the refresh endpoints.

The headline guarantee these pin: the engine path and the manual-refresh path
emit **byte-identical** stream payloads (they build the same hooks against a real
``StageEmitter``), so the wizard tab's merge-then-repaint-from-/state never
flickers. The path-specific bits (slot remapping, reset gating, engine-only phase
ticks) are explicit parameters, verified here, not silent forks.
"""

from __future__ import annotations

import json

from mtgai.pipeline.events import EventBus, StageEmitter
from mtgai.pipeline.stage_hooks import (
    build_ai_review_hooks,
    build_card_gen_hooks,
    build_char_refs_hooks,
    build_mechanic_hooks,
    build_skeleton_hooks,
    card_tile_dict,
    emit_card_gen_reset,
    emit_skeleton_done,
    slots_by_id_from_skeleton,
)

# A real EventBus is used (not a fake) so the tests exercise the production
# publish + stage_phase path — including StageEmitter folding stage_id /
# instance_id into every payload. Its replay ``_buffer`` records every event in
# order, which is exactly what a late-attaching SSE subscriber would replay.


def _emitter(bus: EventBus, stage_id: str) -> StageEmitter:
    return StageEmitter(bus, stage_id, 0.0)


def _only(bus: EventBus, event_type: str) -> list[dict]:
    return [e["data"] for e in bus._buffer if e["type"] == event_type]


# ---------------------------------------------------------------------------
# Mechanics
# ---------------------------------------------------------------------------


def test_mechanic_hooks_emit_canonical_payloads_and_persist(tmp_path) -> None:
    bus = EventBus()
    merged: list[dict] = [{} for _ in range(3)]
    path = tmp_path / "candidates.json"
    hooks = build_mechanic_hooks(
        _emitter(bus, "mechanics"),
        pool=3,
        merged=merged,
        candidates_path=path,
        known_keywords={"flying"},
        emit_phase=True,
    )

    hooks.on_reset()
    hooks.on_draft(1, {"name": "Foo"})
    hooks.on_finalized(1, {"name": "Flying"}, "tightened the reminder")

    reset = _only(bus, "mechanic_candidates_reset")
    assert reset == [{"stage_id": "mechanics", "instance_id": "mechanics", "target": 3}]

    drafted = _only(bus, "mechanic_candidate_drafted")[0]
    assert drafted["position"] == 1
    assert drafted["target"] == 3
    assert drafted["candidate"]["name"] == "Foo"
    assert drafted["candidate"]["_ai_generated"] is True

    fin = _only(bus, "mechanic_candidate_finalized")[0]
    assert fin["position"] == 1
    assert fin["candidate"]["_ai_generated"] is True
    assert fin["review_notes"] == "tightened the reminder"
    # Collision: the finalized name matches a known keyword (case-insensitive).
    assert fin["collision_with"] == "Flying"

    # emit_phase=True adds per-candidate progress ticks on the same bus.
    assert any(e["type"] == "phase" for e in bus._buffer)

    # Incremental persist landed the finalized mechanic in merged[0] on disk.
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk[0]["name"] == "Flying"
    assert on_disk[0]["_ai_generated"] is True


def test_mechanic_hooks_no_collision_when_name_unknown(tmp_path) -> None:
    bus = EventBus()
    hooks = build_mechanic_hooks(
        _emitter(bus, "mechanics"),
        pool=2,
        merged=[{}, {}],
        candidates_path=tmp_path / "c.json",
        known_keywords={"flying"},
    )
    hooks.on_finalized(1, {"name": "Sparkweave"}, "")
    assert _only(bus, "mechanic_candidate_finalized")[0]["collision_with"] is None


def test_mechanic_hooks_slot_for_remaps_position_and_persist(tmp_path) -> None:
    """refresh-card pins every loop position to a single slot (idx)."""
    bus = EventBus()
    merged: list[dict] = [{"name": "Keep0"}, {"name": "Keep1"}, {}]
    path = tmp_path / "c.json"
    hooks = build_mechanic_hooks(
        _emitter(bus, "mechanics"),
        pool=3,
        merged=merged,
        candidates_path=path,
        known_keywords=set(),
        slot_for=lambda _position: 2,
    )
    hooks.on_draft(1, {"name": "New"})
    hooks.on_finalized(1, {"name": "New"}, "")

    assert _only(bus, "mechanic_candidate_drafted")[0]["position"] == 3  # slot 2 + 1
    assert _only(bus, "mechanic_candidate_finalized")[0]["position"] == 3
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert [m.get("name") for m in on_disk] == ["Keep0", "Keep1", "New"]


def test_mechanic_hooks_fire_reset_false_suppresses_reset(tmp_path) -> None:
    bus = EventBus()
    hooks = build_mechanic_hooks(
        _emitter(bus, "mechanics"),
        pool=2,
        merged=[{}, {}],
        candidates_path=tmp_path / "c.json",
        known_keywords=set(),
        fire_reset=False,
    )
    hooks.on_reset()
    assert _only(bus, "mechanic_candidates_reset") == []


def test_mechanic_hooks_out_of_range_slot_skips_persist(tmp_path) -> None:
    """A slot index outside [0, pool) must not raise or write — the event still
    fires (the engine path's historical guard, now uniform)."""
    bus = EventBus()
    path = tmp_path / "c.json"
    hooks = build_mechanic_hooks(
        _emitter(bus, "mechanics"),
        pool=2,
        merged=[{}, {}],
        candidates_path=path,
        known_keywords=set(),
        slot_for=lambda _position: 5,
    )
    hooks.on_finalized(1, {"name": "X"}, "")
    assert not path.exists()  # nothing persisted
    assert _only(bus, "mechanic_candidate_finalized")  # but the event still fired


def test_mechanic_hooks_engine_and_refresh_payloads_are_identical(tmp_path) -> None:
    """The anti-drift guarantee: with the same inputs, the engine config
    (emit_phase=True) and a refresh config (emit_phase=False) emit an identical
    ``mechanic_candidate_finalized`` payload — only the engine's extra phase
    ticks differ."""
    engine_bus, refresh_bus = EventBus(), EventBus()
    engine = build_mechanic_hooks(
        _emitter(engine_bus, "mechanics"),
        pool=3,
        merged=[{} for _ in range(3)],
        candidates_path=tmp_path / "engine.json",
        known_keywords={"trample"},
        emit_phase=True,
    )
    refresh = build_mechanic_hooks(
        _emitter(refresh_bus, "mechanics"),
        pool=3,
        merged=[{} for _ in range(3)],
        candidates_path=tmp_path / "refresh.json",
        known_keywords={"trample"},
        emit_phase=False,
    )
    mech = {"name": "Trample", "reminder_text": "(stomp)"}
    engine.on_finalized(2, dict(mech), "note")
    refresh.on_finalized(2, dict(mech), "note")

    assert _only(engine_bus, "mechanic_candidate_finalized") == _only(
        refresh_bus, "mechanic_candidate_finalized"
    )


# ---------------------------------------------------------------------------
# Skeleton
# ---------------------------------------------------------------------------


def test_skeleton_hooks_emit_slot_reset_and_done() -> None:
    bus = EventBus()
    emitter = _emitter(bus, "skeleton")
    hooks = build_skeleton_hooks(emitter)

    hooks.on_reset()
    hooks.on_slot("S-001", "White · common · creature", "Hero of the Vale")
    emit_skeleton_done(emitter, incomplete=True, relabeled=42)

    assert _only(bus, "skeleton_relabel_reset") == [
        {"stage_id": "skeleton", "instance_id": "skeleton"}
    ]
    slot = _only(bus, "skeleton_slot")[0]
    assert slot["slot_id"] == "S-001"
    assert slot["tweaked_text"] == "White · common · creature"
    assert slot["reserved_card"] == "Hero of the Vale"
    done = _only(bus, "skeleton_relabel_done")[0]
    assert done["incomplete"] is True
    assert done["relabeled"] == 42


def test_skeleton_on_slot_defaults_reserved_to_none() -> None:
    bus = EventBus()
    build_skeleton_hooks(_emitter(bus, "skeleton")).on_slot("S-2", "Blue draw spell")
    assert _only(bus, "skeleton_slot")[0]["reserved_card"] is None


# ---------------------------------------------------------------------------
# Card generation
# ---------------------------------------------------------------------------


def test_card_gen_hooks_emit_tile_and_reset() -> None:
    bus = EventBus()
    emitter = _emitter(bus, "card_gen")
    slots_by_id = {"001": {"slot_id": "001", "tweaked_text": "White CMC1 creature"}}
    hooks = build_card_gen_hooks(emitter, slots_by_id=slots_by_id)

    card = {
        "name": "Sentinel",
        "collector_number": "001",
        "rarity": "common",
        "colors": ["W"],
        "type_line": "Creature — Soldier",
    }
    hooks.on_card_saved(card)
    emit_card_gen_reset(emitter)

    evt = _only(bus, "card_gen_card")[0]
    # The SSE stream marks every streamed card is_new=True (it was just generated).
    assert evt["card"] == card_tile_dict(card, slots_by_id, is_new=True)
    assert evt["card"]["is_new"] is True
    assert evt["card"]["slot_text"] == "White CMC1 creature"
    assert _only(bus, "card_gen_reset") == [{"stage_id": "card_gen", "instance_id": "card_gen"}]


def test_card_gen_engine_and_refresh_tiles_are_identical() -> None:
    """Both paths run the same card through ``card_tile_dict``, so the streamed
    tile is identical regardless of which emitter fired it."""
    engine_bus, refresh_bus = EventBus(), EventBus()
    slots_by_id = {"007": {"slot_id": "007", "tweaked_text": "Red burn"}}
    card = {"name": "Bolt", "collector_number": "007", "rarity": "common", "colors": ["R"]}

    build_card_gen_hooks(_emitter(engine_bus, "card_gen"), slots_by_id=slots_by_id).on_card_saved(
        card
    )
    build_card_gen_hooks(_emitter(refresh_bus, "card_gen"), slots_by_id=slots_by_id).on_card_saved(
        card
    )

    assert (
        _only(engine_bus, "card_gen_card")[0]["card"]
        == _only(refresh_bus, "card_gen_card")[0]["card"]
    )


# ---------------------------------------------------------------------------
# slots_by_id_from_skeleton
# ---------------------------------------------------------------------------


def test_slots_by_id_from_skeleton_indexes_slots(tmp_path) -> None:
    path = tmp_path / "skeleton.json"
    path.write_text(
        json.dumps({"slots": [{"slot_id": "A", "tweaked_text": "x"}, {"slot_id": "B"}]}),
        encoding="utf-8",
    )
    m = slots_by_id_from_skeleton(path)
    assert set(m) == {"A", "B"}
    assert m["A"]["tweaked_text"] == "x"


def test_slots_by_id_from_skeleton_missing_or_bad_returns_empty(tmp_path) -> None:
    assert slots_by_id_from_skeleton(tmp_path / "nope.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert slots_by_id_from_skeleton(bad) == {}
    # A non-dict top level (e.g. a bare list) yields no slots, not a crash.
    arr = tmp_path / "arr.json"
    arr.write_text("[]", encoding="utf-8")
    assert slots_by_id_from_skeleton(arr) == {}


# ---------------------------------------------------------------------------
# AI design review
# ---------------------------------------------------------------------------


def test_ai_review_hooks_emit_canonical_payloads() -> None:
    bus = EventBus()
    hooks = build_ai_review_hooks(_emitter(bus, "ai_review"))

    hooks.on_reset()
    hooks.on_card_start(
        {
            "collector_number": "W-C-01",
            "card_name": "Bear",
            "rarity": "common",
            "review_tier": "single",
        }
    )
    hooks.on_council("W-C-01", {"kind": "round", "round": 1, "verdicts": ["ok"]})
    hooks.on_card_done({"collector_number": "W-C-01", "verdict": "OK"})

    assert _only(bus, "ai_review_reset")
    start = _only(bus, "ai_review_card_start")[0]
    assert start["collector_number"] == "W-C-01"
    assert start["review_tier"] == "single"
    council = _only(bus, "ai_review_council")[0]
    assert council["collector_number"] == "W-C-01"
    assert council["event"]["verdicts"] == ["ok"]
    done = _only(bus, "ai_review_card_done")[0]
    assert done["tile"]["verdict"] == "OK"


# ---------------------------------------------------------------------------
# Character References
# ---------------------------------------------------------------------------


def test_char_refs_on_entity_start_emits_phase_tick_to_keep_strip_alive() -> None:
    """``on_entity_start`` fires during the ComfyUI/Flux image phase. It must emit
    an indeterminate ``phase:"running"`` strip tick so the global progress strip +
    its Cancel button stay visible through the long image phase (card 6a256732),
    alongside the canonical ``char_refs_entity`` tile event."""
    bus = EventBus()
    hooks = build_char_refs_hooks(_emitter(bus, "char_portraits"))

    hooks.on_reset()
    hooks.on_entity_start({"entity_key": "decepticon", "name": "Decepticon", "cards": []})
    hooks.on_entity_image("decepticon", "art-direction/character-refs/decepticon_v1.png")

    assert _only(bus, "char_refs_reset")
    entity = _only(bus, "char_refs_entity")[0]
    assert entity["entity"]["entity_key"] == "decepticon"
    img = _only(bus, "char_refs_image")[0]
    assert img["entity_key"] == "decepticon"

    # The image-phase strip tick: an indeterminate (no live-stats) running phase.
    phases = [e["data"] for e in bus._buffer if e["type"] == "phase"]
    running = [p for p in phases if p["phase"] == "running"]
    assert running, "on_entity_start must emit a phase:'running' tick"
    assert running[0]["activity"] == "Generating reference images…"
    assert running[0]["stage_id"] == "char_portraits"
    # No fake live stats — the client must render an honest indeterminate bar.
    assert "prompt_eval" not in running[0]
    assert "generation" not in running[0]
