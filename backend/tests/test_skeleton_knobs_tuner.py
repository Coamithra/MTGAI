"""Tests for the phase-0 skeleton knob tuner (card 6a16d8ff).

``generate_with_tool`` is monkeypatched — no real model is loaded. Covers tool-
schema generation, clamp + provenance on the parsed result, pin restoration, and
default-on-failure.
"""

from __future__ import annotations

import mtgai.generation.skeleton_knobs_tuner as tuner
from mtgai.skeleton.knobs import KNOB_SPECS, SkeletonKnobs


def _tool_stub(result: dict | None):
    def stub(**kwargs):
        return {"result": result, "input_tokens": 10, "output_tokens": 20}

    return stub


def _tune(monkeypatch, result, **kw):
    monkeypatch.setattr(tuner, "generate_with_tool", _tool_stub(result))
    monkeypatch.setattr(tuner, "cost_from_result", lambda _r: 0.001)
    return tuner.tune_knobs(
        theme={"setting": "A guild-war city."},
        approved=[],
        archetypes=[],
        set_name="Test",
        set_size=277,
        model="stub-model",
        **kw,
    )


# ---------------------------------------------------------------------------
# Tool schema
# ---------------------------------------------------------------------------


class TestToolSchema:
    def test_every_knob_is_a_property(self):
        schema = tuner.build_tool_schema()
        props = schema["input_schema"]["properties"]
        for spec in KNOB_SPECS:
            assert spec.key in props
        assert "cycles" in props

    def test_int_knobs_are_integer_typed(self):
        props = tuner.build_tool_schema()["input_schema"]["properties"]
        assert props["signposts_per_pair"]["type"] == "integer"
        assert props["multicolor_rare"]["type"] == "number"

    def test_cycle_span_enum_present(self):
        cycles = tuner.build_tool_schema()["input_schema"]["properties"]["cycles"]
        span_enum = cycles["items"]["properties"]["span"]["enum"]
        assert "pairs10" in span_enum and "mono5" in span_enum


# ---------------------------------------------------------------------------
# tune_knobs
# ---------------------------------------------------------------------------


class TestTuneKnobs:
    def test_parses_and_marks_ai_provenance(self, monkeypatch):
        knobs, meta = _tune(monkeypatch, {"multicolor_rare": 0.40, "signposts_per_pair": 2})
        assert knobs.multicolor_rare == 0.40
        assert knobs.signposts_per_pair == 2
        assert knobs.provenance["multicolor_rare"] == "ai"
        assert meta["defaulted"] is False
        assert meta["cost_usd"] == 0.001

    def test_clamps_out_of_range(self, monkeypatch):
        knobs, _ = _tune(monkeypatch, {"multicolor_rare": 9.0})
        assert knobs.multicolor_rare == 0.45  # spec max

    def test_parses_cycles(self, monkeypatch):
        knobs, _ = _tune(
            monkeypatch,
            {
                "cycles": [
                    {
                        "id": "gates",
                        "name": "Gates",
                        "rarity": "common",
                        "span": "pairs10",
                        "card_type": "land",
                    }
                ]
            },
        )
        assert len(knobs.cycles) == 1
        assert knobs.cycles[0].card_type == "land"

    def test_respects_pins(self, monkeypatch):
        base = SkeletonKnobs(multicolor_rare=0.40, pinned=["multicolor_rare"])
        base = base.model_copy(update={"provenance": {"multicolor_rare": "user"}})
        # AI tries to move the pinned knob — it must be restored.
        knobs, _ = _tune(monkeypatch, {"multicolor_rare": 0.10}, base=base)
        assert knobs.multicolor_rare == 0.40
        assert knobs.provenance["multicolor_rare"] == "user"

    def test_exception_falls_back_to_defaults(self, monkeypatch):
        def boom(**kwargs):
            raise RuntimeError("model down")

        monkeypatch.setattr(tuner, "generate_with_tool", boom)
        knobs, meta = tuner.tune_knobs(
            theme={}, approved=[], archetypes=[], set_name="T", set_size=277, model="m"
        )
        assert meta["defaulted"] is True
        assert knobs.multicolor_rare == SkeletonKnobs().multicolor_rare

    def test_no_tool_result_falls_back(self, monkeypatch):
        _, meta = _tune(monkeypatch, None)
        assert meta["defaulted"] is True

    def test_failure_preserves_pinned_base(self, monkeypatch):
        def boom(**kwargs):
            raise RuntimeError("down")

        monkeypatch.setattr(tuner, "generate_with_tool", boom)
        base = SkeletonKnobs(multicolor_rare=0.40, pinned=["multicolor_rare"])
        knobs, meta = tuner.tune_knobs(
            theme={}, approved=[], archetypes=[], set_name="T", set_size=277, model="m", base=base
        )
        assert meta["defaulted"] is True
        assert knobs.multicolor_rare == 0.40  # pinned base kept on failure


# ---------------------------------------------------------------------------
# Prompt caching: static context -> one cached system block, dynamic -> user turn
# ---------------------------------------------------------------------------


class TestPromptCaching:
    def _capture(self, monkeypatch) -> dict:
        captured: dict = {}

        def stub(**kwargs):
            captured.update(kwargs)
            return {"result": {"multicolor_rare": 0.3}, "input_tokens": 1, "output_tokens": 1}

        monkeypatch.setattr(tuner, "generate_with_tool", stub)
        monkeypatch.setattr(tuner, "cost_from_result", lambda _r: 0.0)
        tuner.tune_knobs(
            theme={"setting": "A guild-war city.", "card_requests": ["a legendary spider"]},
            approved=[{"name": "Convoke", "colors": ["G"], "reminder_text": "tap creatures"}],
            archetypes=[{"color_pair": "WU", "name": "Tempo", "description": "fly and counter"}],
            set_name="Ravnica",
            set_size=277,
            model="stub",
        )
        return captured

    def test_static_context_rides_in_cached_system_block(self, monkeypatch):
        captured = self._capture(monkeypatch)
        # No legacy single system_prompt; two cached system blocks instead.
        assert not captured.get("system_prompt")
        blocks = captured["system_blocks"]
        assert len(blocks) == 2
        assert all(cache is True for _text, cache in blocks)
        base_text, context_text = blocks[0][0], blocks[1][0]
        assert "set designer" in base_text.lower()
        # The bulk static set context rides in the second (cached) block.
        assert "A guild-war city." in context_text
        assert "Convoke" in context_text
        assert "Tempo" in context_text

    def test_user_turn_is_short_trigger_not_bulk(self, monkeypatch):
        captured = self._capture(monkeypatch)
        user = captured["user_prompt"]
        assert "submit_skeleton_knobs" in user
        # The bulk context is not duplicated in the user turn.
        assert "A guild-war city." not in user
        assert "Convoke" not in user
