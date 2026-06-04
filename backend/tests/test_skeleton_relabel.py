"""Unit tests for skeleton relabel — the LLM half of Skeleton Generation.

The two passes (relabel / assign) are exercised with a monkeypatched
``generate_with_tool`` — no real model is ever loaded. The reconcile logic
(count guarantee, request placement) is the focus; cost math is stubbed where
it would otherwise need the price table.
"""

from __future__ import annotations

import json

import pytest

from mtgai.generation import skeleton_relabel as sr
from mtgai.generation.prompts import format_slot_specs
from mtgai.skeleton.generator import render_slot_string


def _seed_slots() -> list[dict]:
    return [
        {
            "slot_id": "W-C-01",
            "color": "W",
            "rarity": "common",
            "card_type": "creature",
            "cmc_target": 2,
            "mechanic_tag": "vanilla",
            "signpost_for": None,
            "reserved_card": None,
        },
        {
            "slot_id": "U-C-02",
            "color": "U",
            "rarity": "common",
            "card_type": "instant",
            "cmc_target": 2,
            "mechanic_tag": "complex",
            "signpost_for": None,
            "reserved_card": None,
        },
        {
            "slot_id": "M-U-03",
            "color": "multicolor",
            "rarity": "uncommon",
            "card_type": "creature",
            "cmc_target": 4,
            "mechanic_tag": "complex",
            "signpost_for": "WU",
            "reserved_card": None,
        },
        {
            "slot_id": "R-R-04",
            "color": "R",
            "rarity": "rare",
            "card_type": "sorcery",
            "cmc_target": 5,
            "mechanic_tag": "complex",
            "signpost_for": None,
            "reserved_card": None,
        },
    ]


def _theme() -> dict:
    return {
        "code": "TST",
        "setting": "A test world of clockwork warbeasts.",
        "constraints": [{"text": "lots of artifacts"}],
        "card_requests": [{"text": "Cogwarden, legendary artifact guardian"}],
    }


def _approved() -> list[dict]:
    return [{"name": "Salvage", "colors": ["U", "G"], "reminder_text": "(do salvage)"}]


def _blocks(pairs: list[tuple[str, str]]) -> str:
    """Render (slot_id, descriptor) pairs as the free-text `--CARD <id>--` format
    the relabel parser consumes."""
    return "\n".join(f"--CARD {sid}--\n{desc}" for sid, desc in pairs)


def _complete(text: str, *, input_tokens: int, output_tokens: int) -> dict:
    """A stub ``stream_text`` terminal 'complete' event."""
    return {
        "type": "complete",
        "text": text,
        "model": "m",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "stop_reason": "end_turn",
    }


def _stream_stub(text: str, *, input_tokens: int = 1, output_tokens: int = 1):
    """Build a stand-in for ``stream_text``: yields the whole reply as one
    text_delta (when non-empty) then a single 'complete' event with usage —
    the event contract ``relabel_slots`` consumes. Returns a callable that
    produces a fresh generator per attempt."""

    def _factory(*_a, **_k):
        def _gen():
            if text:
                yield {"type": "text_delta", "text": text}
            yield _complete(text, input_tokens=input_tokens, output_tokens=output_tokens)

        return _gen()

    return _factory


@pytest.fixture
def _project(isolated_output):
    """Pin a minimal active project with skeleton/theme/mechanics/archetypes on disk."""
    from mtgai.runtime import active_project
    from mtgai.settings import model_settings as ms

    asset = isolated_output / "sets" / "TST"
    (asset / "mechanics").mkdir(parents=True, exist_ok=True)
    (asset / "skeleton.json").write_text(json.dumps({"slots": _seed_slots()}), encoding="utf-8")
    (asset / "theme.json").write_text(json.dumps(_theme()), encoding="utf-8")
    (asset / "mechanics" / "approved.json").write_text(json.dumps(_approved()), encoding="utf-8")
    (asset / "archetypes.json").write_text(
        json.dumps([{"color_pair": "WU", "name": "Tempo", "description": "win with fliers"}]),
        encoding="utf-8",
    )
    settings = ms.ModelSettings(
        asset_folder=str(asset),
        set_params=ms.SetParams(set_name="Test", set_size=4, mechanic_count=1),
    )
    active_project.write_active_project(
        active_project.ProjectState(set_code="TST", settings=settings)
    )
    return asset


# ---------------------------------------------------------------------------
# Default descriptor rendering
# ---------------------------------------------------------------------------


def test_render_slot_string_format() -> None:
    s = _seed_slots()[0]
    assert render_slot_string(s) == "Mono White · common · creature · CMC2 · vanilla"
    # The multicolor uncommon carries its signpost marker.
    assert render_slot_string(_seed_slots()[2]).endswith("· signpost:WU")


# ---------------------------------------------------------------------------
# Pass 1 — relabel + reconcile
# ---------------------------------------------------------------------------


def test_relabel_reconciles_missing_and_drops_unknown(_project, monkeypatch) -> None:
    seed = _seed_slots()
    # Block-format rewrites for all but the last seed slot, plus a bogus id.
    pairs = [(s["slot_id"], f"themed {s['slot_id']}") for s in seed[:-1]]
    pairs.append(("BOGUS-99", "ignore me"))

    monkeypatch.setattr(sr, "stream_text", _stream_stub(_blocks(pairs), output_tokens=2))
    tweaked, _resp = sr.relabel_slots(
        slots=seed,
        theme=_theme(),
        approved=_approved(),
        archetypes=[],
        set_name="T",
        set_size=4,
        model="m",
    )
    # Count guarantee: every seed slot present; unknown dropped.
    assert set(tweaked) == {s["slot_id"] for s in seed}
    assert tweaked["W-C-01"] == "themed W-C-01"
    # The dropped slot keeps its default descriptor.
    assert tweaked["R-R-04"] == render_slot_string(seed[-1])


def test_relabel_resends_whole_prompt_until_complete(monkeypatch) -> None:
    """An insufficient attempt triggers a full resend; the next complete attempt
    wins, and token usage is summed across both calls."""
    seed = _seed_slots()
    calls = {"n": 0}
    full = _blocks([(s["slot_id"], f"themed {s['slot_id']}") for s in seed])

    def stub(*_a, **_k):
        calls["n"] += 1
        # First attempt comes back empty (truncated / garbage) → resend; the
        # second covers the whole set.
        text = "" if calls["n"] == 1 else full

        def _gen():
            if text:
                yield {"type": "text_delta", "text": text}
            yield _complete(text, input_tokens=3, output_tokens=4)

        return _gen()

    monkeypatch.setattr(sr, "stream_text", stub)
    tweaked, resp = sr.relabel_slots(
        slots=seed,
        theme=_theme(),
        approved=_approved(),
        archetypes=[],
        set_name="T",
        set_size=4,
        model="m",
    )
    assert calls["n"] == 2
    # Every slot relabeled (none on default); tokens summed across both attempts.
    assert all(v.startswith("themed ") for v in tweaked.values())
    assert resp["input_tokens"] == 6
    assert resp["output_tokens"] == 8
    assert resp["incomplete"] is False


def test_relabel_cancel_before_attempts_keeps_defaults(_project, monkeypatch) -> None:
    """A user Cancel signalled before any attempt produces output breaks the
    retry loop, never calls the model, and returns the all-default tweaked map
    (no RelabelIncompleteError) flagged incomplete — the uniform-cancellation
    contract (the relabel worker now polls ``ai_lock.is_cancelled()``)."""
    from mtgai.runtime import ai_lock

    seed = _seed_slots()
    calls = {"n": 0}

    def stub(*_a, **_k):
        calls["n"] += 1

        def _gen():
            yield _complete("", input_tokens=1, output_tokens=1)

        return _gen()

    monkeypatch.setattr(sr, "stream_text", stub)
    ai_lock.reset_for_tests()
    ai_lock.try_acquire("test")
    try:
        ai_lock.request_cancel()  # only sticks while a run holds the lock
        tweaked, resp = sr.relabel_slots(
            slots=seed,
            theme=_theme(),
            approved=_approved(),
            archetypes=[],
            set_name="T",
            set_size=4,
            model="m",
        )
    finally:
        ai_lock.reset_for_tests()

    assert calls["n"] == 0  # cancel broke the loop before the first model call
    assert set(tweaked) == {s["slot_id"] for s in seed}  # count guarantee holds
    assert tweaked["W-C-01"] == render_slot_string(seed[0])  # every slot on default
    assert resp["incomplete"] is True


def test_relabel_keeps_partial_when_persistently_incomplete(monkeypatch) -> None:
    """If the model never covers enough slots, the best partial is KEPT and
    flagged incomplete (the 'keep partial, mark incomplete' contract) rather
    than raised away — the missing slots fall back to their default descriptor."""
    # 20 slots → tolerance is max(3, ceil(20*0.1)=2) = 3. Cover 16, leave 4
    # missing (> 3) so the run is genuinely incomplete while keeping real work.
    base = _seed_slots()[0]
    seed = [dict(base, slot_id=f"X-{i:02d}") for i in range(20)]
    covered = _blocks([(f"X-{i:02d}", f"themed {i}") for i in range(16)])

    monkeypatch.setattr(sr, "stream_text", _stream_stub(covered))
    tweaked, resp = sr.relabel_slots(
        slots=seed,
        theme=_theme(),
        approved=_approved(),
        archetypes=[],
        set_name="T",
        set_size=20,
        model="m",
    )
    assert tweaked["X-00"] == "themed 0"
    # The four unreached slots keep their default descriptor (not discarded).
    assert tweaked["X-19"] == render_slot_string(seed[-1])
    assert resp["relabeled_count"] == 16
    assert resp["incomplete"] is True


def test_relabel_raises_when_every_attempt_errors(monkeypatch) -> None:
    """Transport errors on every attempt (no usable output at all) is the only
    hard failure — it surfaces as RelabelIncompleteError."""
    seed = _seed_slots()

    def stub(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(sr, "stream_text", stub)
    with pytest.raises(sr.RelabelIncompleteError):
        sr.relabel_slots(
            slots=seed,
            theme=_theme(),
            approved=_approved(),
            archetypes=[],
            set_name="T",
            set_size=4,
            model="m",
        )


def test_relabel_reports_progress_and_disables_repeat_penalty(monkeypatch) -> None:
    """Each attempt announces itself via on_progress, and the free-text relabel
    streams with the repeat penalty OFF (the line format is intentionally
    repetitive). A persistently-empty reply keeps a partial (incomplete), not
    a raise."""
    seed = _seed_slots()
    seen_kwargs: list[dict] = []

    def stub(*_a, **k):
        seen_kwargs.append(k)

        def _gen():  # always empty → forces all attempts to run
            yield _complete("", input_tokens=1, output_tokens=1)

        return _gen()

    monkeypatch.setattr(sr, "stream_text", stub)
    seen: list[str] = []
    _tweaked, resp = sr.relabel_slots(
        slots=seed,
        theme=_theme(),
        approved=_approved(),
        archetypes=[],
        set_name="T",
        set_size=4,
        model="m",
        on_progress=seen.append,
    )
    assert len(seen) == sr.RELABEL_MAX_ATTEMPTS
    assert all("attempt" in s.lower() for s in seen)
    assert seen_kwargs and all(
        k.get("repeat_penalty") == sr.RELABEL_TEXT_REPEAT_PENALTY for k in seen_kwargs
    )
    assert resp["incomplete"] is True


def test_relabel_streams_slots_and_fires_reset(monkeypatch) -> None:
    """on_reset fires once per attempt; on_slot fires once per parsed slot with
    reserved=None for a Pass-1 relabel. Each slot is pushed exactly once even
    though the live scan and the end-of-stream flush both run."""
    seed = _seed_slots()
    text = _blocks([(s["slot_id"], f"themed {s['slot_id']}") for s in seed])

    def stub(*_a, **_k):
        def _gen():
            # Stream line-by-line so blocks close mid-stream (exercises the live
            # per-slot push, not just the end-of-stream flush).
            for line in text.splitlines(keepends=True):
                yield {"type": "text_delta", "text": line}
            yield _complete(text, input_tokens=1, output_tokens=1)

        return _gen()

    monkeypatch.setattr(sr, "stream_text", stub)
    seen: list[tuple[str, str, str | None]] = []
    resets: list[int] = []
    _tweaked, resp = sr.relabel_slots(
        slots=seed,
        theme=_theme(),
        approved=_approved(),
        archetypes=[],
        set_name="T",
        set_size=4,
        model="m",
        on_slot=lambda sid, desc, reserved=None: seen.append((sid, desc, reserved)),
        on_reset=lambda: resets.append(1),
    )
    assert resets == [1]  # one attempt (it covered everything)
    assert len(seen) == len(seed)  # each slot pushed exactly once (deduped)
    assert {sid for sid, _d, _r in seen} == {s["slot_id"] for s in seed}
    assert all(reserved is None for _s, _d, reserved in seen)
    assert resp["incomplete"] is False


def test_parse_relabel_text_blocks_and_fallback() -> None:
    """The parser reads --CARD <id>-- blocks (int-normalized ids) and falls back
    to bare `<id>: descriptor` lines when no markers are present."""
    valid = {"001", "002", "003"}
    # Block format, with preamble, an int-shorthand id (2 → 002), and a bogus id.
    by_id: dict[str, str] = {}
    sr._parse_relabel_text(
        "blah blah\n--CARD 001--\nWhite vanilla\n--CARD 2--\nBlue draw\n--CARD 999--\nnope",
        valid,
        by_id,
    )
    assert by_id == {"001": "White vanilla", "002": "Blue draw"}
    # Fallback: no markers → `<id>: descriptor` lines.
    fb: dict[str, str] = {}
    sr._parse_relabel_text("001: White vanilla\n003: Green ramp", valid, fb)
    assert fb == {"001": "White vanilla", "003": "Green ramp"}


# ---------------------------------------------------------------------------
# Pass 2 — request assignment
# ---------------------------------------------------------------------------


def test_assign_requests_places_request_as_descriptor(monkeypatch) -> None:
    """A placed request becomes the slot's descriptor verbatim (the request text
    is the spec — we don't keep a separate model-rewritten line)."""
    tweaked = {"A": "x", "B": "y"}

    def stub(*_a, **_k):
        return {
            "result": {"assignments": [{"request": "Cogwarden", "slot_id": "B"}]},
            "model": "m",
            "input_tokens": 1,
            "output_tokens": 1,
        }

    monkeypatch.setattr(sr, "generate_with_tool", stub)
    out, reserved, resp = sr.assign_requests(
        slots=[{"slot_id": "A"}, {"slot_id": "B"}],
        tweaked=tweaked,
        card_requests=[{"text": "Cogwarden"}],
        model="m",
    )
    assert reserved == {"B": "Cogwarden"}
    assert out["B"] == "Cogwarden"  # descriptor replaced by the request text
    assert out["A"] == "x"  # untouched
    assert resp is not None


def test_assign_requests_no_requests_skips_call(monkeypatch) -> None:
    called = {"n": 0}

    def stub(*_a, **_k):
        called["n"] += 1
        return {"result": {}, "model": "m"}

    monkeypatch.setattr(sr, "generate_with_tool", stub)
    _out, reserved, resp = sr.assign_requests(
        slots=[{"slot_id": "A"}], tweaked={"A": "x"}, card_requests=[], model="m"
    )
    assert resp is None
    assert reserved == {}
    assert called["n"] == 0


def test_assign_requests_skips_duplicate_and_unknown(monkeypatch) -> None:
    def stub(*_a, **_k):
        return {
            "result": {
                "assignments": [
                    {"request": "First", "slot_id": "A"},
                    {"request": "Second", "slot_id": "A"},  # dup slot, skipped
                    {"request": "Third", "slot_id": "ZZ"},  # unknown slot, skipped
                ]
            },
            "model": "m",
            "input_tokens": 1,
            "output_tokens": 1,
        }

    monkeypatch.setattr(sr, "generate_with_tool", stub)
    out, reserved, _resp = sr.assign_requests(
        slots=[{"slot_id": "A"}],
        tweaked={"A": "x"},
        card_requests=[{"text": "First"}, {"text": "Second"}, {"text": "Third"}],
        model="m",
    )
    # Only the first valid (slot free + known request) placement is kept; the
    # taken-slot and unknown-slot assignments are dropped.
    assert reserved == {"A": "First"}
    assert out["A"] == "First"


def test_assign_requests_dedups_same_request_across_slots(monkeypatch) -> None:
    """The duplicate-card bug: a single request placed on several slots must be
    accepted exactly once, not once per slot."""

    def stub(*_a, **_k):
        return {
            "result": {
                "assignments": [
                    {"request": "Dragon", "slot_id": "A"},
                    {"request": "Dragon", "slot_id": "B"},  # dup request
                    {"request": "Dragon", "slot_id": "C"},  # dup request
                ]
            },
            "model": "m",
            "input_tokens": 1,
            "output_tokens": 1,
        }

    monkeypatch.setattr(sr, "generate_with_tool", stub)
    out, reserved, _resp = sr.assign_requests(
        slots=[{"slot_id": "A"}, {"slot_id": "B"}, {"slot_id": "C"}],
        tweaked={"A": "x", "B": "y", "C": "z"},
        card_requests=[{"text": "Dragon"}],
        model="m",
    )
    assert reserved == {"A": "Dragon"}  # placed once, on the first slot
    assert out["A"] == "Dragon"  # descriptor replaced by the request
    assert out["B"] == "y"  # untouched
    assert out["C"] == "z"


def test_assign_requests_retries_until_placed(monkeypatch) -> None:
    """A first attempt that places nothing triggers a resend; the next attempt
    places the request. Token usage is summed across attempts."""
    calls = {"n": 0}

    def stub(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "result": {"assignments": []},
                "model": "m",
                "input_tokens": 2,
                "output_tokens": 3,
            }
        return {
            "result": {"assignments": [{"request": "Sphinx", "slot_id": "A"}]},
            "model": "m",
            "input_tokens": 2,
            "output_tokens": 3,
        }

    monkeypatch.setattr(sr, "generate_with_tool", stub)
    out, reserved, resp = sr.assign_requests(
        slots=[{"slot_id": "A"}],
        tweaked={"A": "x"},
        card_requests=[{"text": "Sphinx"}],
        model="m",
    )
    assert calls["n"] == 2
    assert reserved == {"A": "Sphinx"}
    assert out["A"] == "Sphinx"
    assert resp is not None
    assert resp["input_tokens"] == 4  # summed across both attempts
    assert resp["output_tokens"] == 6


def test_assign_requests_reports_progress(monkeypatch) -> None:
    """on_progress fires once per attempt with an 'attempt N/M' string."""

    def stub(*_a, **_k):
        return {"result": {"assignments": []}, "model": "m", "input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(sr, "generate_with_tool", stub)
    seen: list[str] = []
    sr.assign_requests(
        slots=[{"slot_id": "A"}],
        tweaked={"A": "x"},
        card_requests=[{"text": "Never placed"}],
        model="m",
        on_progress=seen.append,
    )
    # Never placed → all attempts run, each announces itself.
    assert len(seen) == sr.ASSIGN_MAX_ATTEMPTS
    assert all("attempt" in s.lower() for s in seen)


# ---------------------------------------------------------------------------
# Orchestrator round-trip
# ---------------------------------------------------------------------------


def test_relabel_skeleton_round_trip(_project, monkeypatch) -> None:
    # Pass 1 streams free text (stream_text); Pass 2 is the JSON tool (generate_with_tool).
    text_stub = _stream_stub(
        _blocks([(s["slot_id"], f"themed {s['slot_id']}") for s in _seed_slots()]),
        input_tokens=10,
        output_tokens=20,
    )

    def tool_stub(*_a, **_k):
        return {
            "result": {
                "assignments": [
                    {
                        "request": "Cogwarden, legendary artifact guardian",
                        "slot_id": "R-R-04",
                    },
                ]
            },
            "model": "m",
            "input_tokens": 5,
            "output_tokens": 5,
        }

    monkeypatch.setattr(sr, "stream_text", text_stub)
    monkeypatch.setattr(sr, "generate_with_tool", tool_stub)
    monkeypatch.setattr(sr, "cost_from_result", lambda _r: 0.01)

    out = sr.relabel_skeleton(slots=_seed_slots())
    updates = out["updates"]
    assert set(updates) == {s["slot_id"] for s in _seed_slots()}
    assert updates["W-C-01"]["tweaked_text"] == "themed W-C-01"
    # The placed request becomes the slot's descriptor AND its reserved_card.
    assert updates["R-R-04"]["reserved_card"] == "Cogwarden, legendary artifact guardian"
    assert updates["R-R-04"]["tweaked_text"] == "Cogwarden, legendary artifact guardian"
    assert out["input_tokens"] == 15
    assert out["output_tokens"] == 25
    assert out["cost_usd"] == pytest.approx(0.02)
    assert out["model_id"]  # resolved from settings
    # All four slots relabeled — a complete, non-incomplete round trip.
    assert out["incomplete"] is False
    assert out["relabeled"] == 4


# ---------------------------------------------------------------------------
# Card-gen consumption — format_slot_specs tweaked_text branch
# ---------------------------------------------------------------------------


def test_format_slot_specs_uses_tweaked_text() -> None:
    slots = [
        {
            "slot_id": "A",
            "color": "W",
            "rarity": "common",
            "card_type": "creature",
            "cmc_target": 2,
            "tweaked_text": "Blue · common · instant · CMC2 · Salvage",
            "reserved_card": "Megatron",
        }
    ]
    out = format_slot_specs(slots)
    assert "Blue · common · instant · CMC2 · Salvage" in out
    assert "Megatron" in out  # reserved_card repeated explicitly
    # The structured fallback line is NOT emitted when tweaked_text is present.
    assert "White common creature" not in out


def test_format_slot_specs_structured_path_without_tweak() -> None:
    slots = [
        {
            "slot_id": "A",
            "color": "W",
            "rarity": "common",
            "card_type": "creature",
            "cmc_target": 2,
            "mechanic_tag": "vanilla",
        }
    ]
    out = format_slot_specs(slots)
    assert "White common creature" in out
