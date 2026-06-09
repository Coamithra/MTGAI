"""Pins that every stage runner emits a terminal ``phase("done", ...)``.

Without this, the global progress strip (``#wiz-progress-strip``, driven by SSE
``phase`` events and replayed to late subscribers via the per-run event log)
stays stuck on the last ``phase("running", ...)`` whenever a stage finishes
into PAUSED_FOR_REVIEW — the ``pipeline_status`` terminal events the client
also listens to only hide the strip on ``completed | cancelled | failed``, not
``paused``.

The bug this regression-tests: ``run_card_gen`` used to skip the done emission,
so a successful card-gen pause left the strip showing "Generating cards from
skeleton slots" forever.
"""

from __future__ import annotations

import pytest

from mtgai.pipeline import stages
from mtgai.pipeline.events import StageEmitter


class _SpyEmitter(StageEmitter):
    """``StageEmitter`` subclass that records every ``.phase()`` + ``.event()``.

    Subclasses (rather than duck-types) so the runner's typed signature is
    happy and any sibling helpers keep their bus-less no-op behavior from
    the base class.
    """

    def __init__(self) -> None:
        super().__init__(None, "card_gen", 0.0)
        self.calls: list[tuple[str, str]] = []
        self.events: list[tuple[str, dict]] = []

    def phase(self, phase: str, activity: str, **_extra) -> None:
        self.calls.append((phase, activity))

    def event(self, event_type: str, **data) -> None:
        self.events.append((event_type, data))


@pytest.fixture(autouse=True)
def _reset_ai_lock():
    from mtgai.runtime import ai_lock

    ai_lock.reset_for_tests()
    yield
    ai_lock.reset_for_tests()


def _stub_generate_set_factory(result: dict):
    def stub(**_kwargs):
        return result

    return stub


def test_run_card_gen_emits_done_on_success(monkeypatch) -> None:
    """A normal (or cap-truncated) successful run must close out with
    ``phase("done", ...)`` so the global progress strip clears."""
    monkeypatch.setattr(
        "mtgai.generation.card_generator.generate_set",
        _stub_generate_set_factory(
            {
                "total_slots": 272,
                "filled": 15,
                "failed": 0,
                "cost_usd": 0.0,
                "summary": "Generated 15 cards in 141s ($0.0000)",
                "cancelled": False,
            }
        ),
    )

    spy = _SpyEmitter()
    result = stages.run_card_gen(progress_cb=None, emitter=spy)

    assert result.success is True
    phase_names = [name for name, _ in spy.calls]
    assert "done" in phase_names, f"missing terminal phase('done'); got {spy.calls}"
    # And the done activity carries the run summary (so the replay buffer
    # has a meaningful terminal message even though the client only reads
    # the phase name to clear the strip).
    done_activity = next(activity for name, activity in spy.calls if name == "done")
    assert "Generated 15" in done_activity


def test_run_card_gen_streams_card_event_per_save(monkeypatch) -> None:
    """The engine path must call ``emitter.event("card_gen_card", ...)`` per
    saved card so the Card Generation tab pops each card in live (the same
    streaming UX the manual /refresh endpoint provides). No reset event from
    the engine path — first runs start on an empty cards/ dir and a resume
    must keep existing cards on screen."""
    from mtgai.models.card import Card
    from mtgai.models.enums import Color, Rarity

    saved_cards = [
        Card(
            name=f"Card {i}",
            mana_cost="{1}{W}",
            cmc=2.0,
            type_line="Creature",
            oracle_text="",
            rarity=Rarity.COMMON,
            colors=[Color.WHITE],
            color_identity=[Color.WHITE],
            collector_number=f"{i:03d}",
            set_code="TST",
            card_types=["Creature"],
        )
        for i in (1, 2, 3)
    ]

    def stub(**kwargs):
        cb = kwargs.get("card_saved_callback")
        if cb is not None:
            for c in saved_cards:
                cb(c)
        return {
            "total_slots": 3,
            "filled": 3,
            "failed": 0,
            "cost_usd": 0.0,
            "summary": "Generated 3 cards",
            "cancelled": False,
        }

    monkeypatch.setattr("mtgai.generation.card_generator.generate_set", stub)

    spy = _SpyEmitter()
    result = stages.run_card_gen(progress_cb=None, emitter=spy)

    assert result.success is True
    card_events = [data for name, data in spy.events if name == "card_gen_card"]
    assert len(card_events) == 3
    assert [e["card"]["collector_number"] for e in card_events] == ["001", "002", "003"]
    # Tile shape is what /state would return — same source-of-truth helper.
    assert card_events[0]["card"]["name"] == "Card 1"
    assert card_events[0]["card"]["rarity"] == "common"
    assert card_events[0]["card"]["colors"] == ["W"]

    # And no card_gen_reset — engine path must never wipe a resume's cards.
    assert not any(name == "card_gen_reset" for name, _ in spy.events)


def test_run_card_gen_emits_done_on_cancelled(monkeypatch) -> None:
    """A user-cancel exit must also close the strip — otherwise a cancel that
    leaves the run mid-flight leaves the strip stuck the same way."""
    monkeypatch.setattr(
        "mtgai.generation.card_generator.generate_set",
        _stub_generate_set_factory(
            {
                "total_slots": 272,
                "filled": 3,
                "failed": 0,
                "cost_usd": 0.0,
                "summary": "Cancelled after 3 cards",
                "cancelled": True,
            }
        ),
    )

    spy = _SpyEmitter()
    result = stages.run_card_gen(progress_cb=None, emitter=spy)

    assert result.success is False
    assert result.error_message == "Cancelled after 3 cards"
    phase_names = [name for name, _ in spy.calls]
    assert "done" in phase_names, f"missing terminal phase('done'); got {spy.calls}"


def _stub_renderer_factory(result: dict):
    class _FakeRenderer:
        def render_set(self, **_kwargs):
            return result

    return lambda *_a, **_k: _FakeRenderer()


def test_run_rendering_emits_done_on_success(monkeypatch) -> None:
    """``run_rendering`` finishes into PAUSED_FOR_REVIEW (the terminal stage), so
    it never advances into a next stage that would emit its own phase. Without a
    terminal ``phase('done', ...)`` the global progress strip stays stuck on the
    last ``phase('running', 'Rendered <card>')`` forever (the reported bug)."""
    monkeypatch.setattr(
        "mtgai.rendering.card_renderer.CardRenderer",
        _stub_renderer_factory(
            {"rendered": 12, "skipped": 0, "failed": 0, "elapsed_seconds": 29.1}
        ),
    )

    spy = _SpyEmitter()
    result = stages.run_rendering(progress_cb=None, emitter=spy)

    assert result.success is True
    phase_names = [name for name, _ in spy.calls]
    assert "done" in phase_names, f"missing terminal phase('done'); got {spy.calls}"
    done_activity = next(activity for name, activity in spy.calls if name == "done")
    assert "Rendered 12 cards" in done_activity


def test_run_rendering_emits_done_on_cancel(monkeypatch) -> None:
    """A user Cancel mid-render must also close the strip."""
    monkeypatch.setattr(
        "mtgai.rendering.card_renderer.CardRenderer",
        _stub_renderer_factory(
            {"rendered": 3, "skipped": 0, "failed": 0, "elapsed_seconds": 0.0, "cancelled": True}
        ),
    )

    spy = _SpyEmitter()
    result = stages.run_rendering(progress_cb=None, emitter=spy)

    assert result.success is False
    assert "done" in [name for name, _ in spy.calls]


def test_run_ai_review_emits_done(monkeypatch) -> None:
    """``run_ai_review`` makes many small LLM calls with no per-item phase of
    its own; it must still bracket the run with a terminal ``phase('done', ...)``
    so the poller-driven strip clears (it previously emitted no done at all)."""
    monkeypatch.setattr(
        "mtgai.review.ai_review.review_all_cards",
        lambda **_kwargs: {"reviewed": 8, "revised": 2, "unfixable": [], "cost_usd": 0.0},
    )
    # No asset folder in the test harness → stub the flag-and-save side so the
    # runner doesn't touch disk; an empty unfixable list means nothing to flag.
    monkeypatch.setattr(stages, "_flag_cards_for_regen", lambda *_a, **_k: [])

    spy = _SpyEmitter()
    result = stages.run_ai_review(progress_cb=None, emitter=spy)

    assert result.success is True
    phase_names = [name for name, _ in spy.calls]
    assert "done" in phase_names, f"missing terminal phase('done'); got {spy.calls}"


def test_run_art_prompts_emits_done(monkeypatch) -> None:
    """``run_art_prompts`` likewise had no terminal done before this change."""
    monkeypatch.setattr(
        "mtgai.art.prompt_builder.generate_prompts_for_set",
        lambda **_kwargs: {"processed": 5, "skipped": 0, "cost_usd": 0.0},
    )

    spy = _SpyEmitter()
    result = stages.run_art_prompts(progress_cb=None, emitter=spy)

    assert result.success is True
    phase_names = [name for name, _ in spy.calls]
    assert "done" in phase_names, f"missing terminal phase('done'); got {spy.calls}"


# ---------------------------------------------------------------------------
# AI-lock holding for the reprints + lands engine stages.
#
# Both runners must wrap their LLM work in ``ai_lock.hold(...)`` like every
# other AI stage: (1) so a second AI action can't start concurrently while
# they run, and (2) so the UI Cancel button (which only signals when the lock
# is held) actually halts them. These pin the busy-guard + cancel-halt paths.
# ---------------------------------------------------------------------------


def test_run_reprints_returns_busy_when_lock_held(monkeypatch, tmp_path) -> None:
    """When another AI action already holds the lock, ``run_reprints`` must bail
    with a busy ``StageResult`` and never invoke the selector."""
    from mtgai.runtime import ai_lock

    (tmp_path / "skeleton.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(stages, "_set_dir", lambda: tmp_path)
    monkeypatch.setattr("mtgai.generation.reprint_selector.load_reprint_pool", lambda: [])
    monkeypatch.setattr("mtgai.generation.reprint_selector._load_slot_texts", lambda *_a, **_k: [])
    called: list[int] = []
    monkeypatch.setattr(
        "mtgai.generation.reprint_selector.select_reprints",
        lambda **_k: called.append(1),
    )

    assert ai_lock.try_acquire("Other action") is not None
    spy = _SpyEmitter()
    result = stages.run_reprints(progress_cb=None, emitter=spy)

    assert result.success is False
    assert "holds the lock" in (result.error_message or "")
    assert called == [], "selector ran despite the lock being held"


def test_run_reprints_halts_on_cancel(monkeypatch, tmp_path) -> None:
    """A user Cancel during selection must fail the stage and skip persistence."""
    from mtgai.runtime import ai_lock

    (tmp_path / "skeleton.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(stages, "_set_dir", lambda: tmp_path)
    monkeypatch.setattr("mtgai.generation.reprint_selector.load_reprint_pool", lambda: [])
    monkeypatch.setattr("mtgai.generation.reprint_selector._load_slot_texts", lambda *_a, **_k: [])

    persisted: list[str] = []
    monkeypatch.setattr(
        "mtgai.generation.reprint_selector.apply_selection_to_skeleton",
        lambda *_a, **_k: persisted.append("skeleton"),
    )
    monkeypatch.setattr(stages, "atomic_write_text", lambda *_a, **_k: persisted.append("file"))

    def fake_select(**_kwargs):
        # The user hits Cancel mid-call; select_reprints returns a partial result.
        ai_lock.request_cancel()
        return object()

    monkeypatch.setattr("mtgai.generation.reprint_selector.select_reprints", fake_select)

    spy = _SpyEmitter()
    result = stages.run_reprints(progress_cb=None, emitter=spy)

    assert result.success is False
    assert "cancelled" in (result.error_message or "").lower()
    assert persisted == [], "partial selection was persisted despite cancel"


def test_run_lands_returns_busy_when_lock_held(monkeypatch) -> None:
    """When another AI action already holds the lock, ``run_lands`` must bail
    with a busy ``StageResult`` and never invoke the land generator."""
    from mtgai.runtime import ai_lock

    called: list[int] = []
    monkeypatch.setattr(
        "mtgai.generation.land_generator.generate_lands",
        lambda **_k: called.append(1),
    )

    assert ai_lock.try_acquire("Other action") is not None
    spy = _SpyEmitter()
    result = stages.run_lands(progress_cb=None, emitter=spy)

    assert result.success is False
    assert "holds the lock" in (result.error_message or "")
    assert called == [], "land generator ran despite the lock being held"


def test_run_lands_halts_on_cancel(monkeypatch) -> None:
    """A user Cancel returns the ``cancelled`` shape; the stage must fail so the
    engine halts instead of marching on with a partial land set."""
    monkeypatch.setattr(
        "mtgai.generation.land_generator.generate_lands",
        lambda **_k: {"total_cards": 2, "cost_usd": 0.0, "cancelled": True},
    )

    spy = _SpyEmitter()
    result = stages.run_lands(progress_cb=None, emitter=spy)

    assert result.success is False
    assert "cancelled" in (result.error_message or "").lower()


# ---------------------------------------------------------------------------
# AI-lock holding + cancel for the ai_review + art LLM engine stages.
#
# Same contract as reprints/lands above: each must wrap its LLM work in
# ``ai_lock.hold(...)`` (so a second AI action can't start concurrently and so
# the UI Cancel button, which only signals when the lock is held, actually
# halts the loop) and bail/halt cleanly without flagging or persisting a
# partial pass.
# ---------------------------------------------------------------------------


def test_run_ai_review_returns_busy_when_lock_held(monkeypatch) -> None:
    """When another AI action holds the lock, ``run_ai_review`` must bail busy
    and never invoke the review loop."""
    from mtgai.runtime import ai_lock

    called: list[int] = []
    monkeypatch.setattr(
        "mtgai.review.ai_review.review_all_cards",
        lambda **_k: called.append(1),
    )

    assert ai_lock.try_acquire("Other action") is not None
    spy = _SpyEmitter()
    result = stages.run_ai_review(progress_cb=None, emitter=spy)

    assert result.success is False
    assert "holds the lock" in (result.error_message or "")
    assert called == [], "review loop ran despite the lock being held"


def test_run_ai_review_threads_cancel_hook(monkeypatch) -> None:
    """The runner must thread a cancel hook into ``review_all_cards`` so the
    loop can poll it — and that hook is ``ai_lock.is_cancelled``."""
    from mtgai.runtime import ai_lock

    seen: dict[str, object] = {}

    def fake_review(**kwargs):
        seen["should_cancel"] = kwargs.get("should_cancel")
        return {"reviewed": 1, "revised": 0, "unfixable": [], "cost_usd": 0.0, "cancelled": False}

    monkeypatch.setattr("mtgai.review.ai_review.review_all_cards", fake_review)
    monkeypatch.setattr(stages, "_flag_cards_for_regen", lambda *_a, **_k: [])

    spy = _SpyEmitter()
    result = stages.run_ai_review(progress_cb=None, emitter=spy)

    assert result.success is True
    assert seen["should_cancel"] is ai_lock.is_cancelled


def test_run_ai_review_halts_on_cancel(monkeypatch) -> None:
    """A user Cancel mid-review (partial ``unfixable``) must fail the stage and
    skip flagging — otherwise a partial pass stamps regen flags."""
    flagged: list[int] = []
    monkeypatch.setattr(
        "mtgai.review.ai_review.review_all_cards",
        lambda **_k: {
            "reviewed": 3,
            "revised": 1,
            "unfixable": [{"slot_id": "001", "reason": "x"}],
            "cost_usd": 0.0,
            "cancelled": True,
        },
    )
    monkeypatch.setattr(stages, "_flag_cards_for_regen", lambda *_a, **_k: flagged.append(1) or [])

    spy = _SpyEmitter()
    result = stages.run_ai_review(progress_cb=None, emitter=spy)

    assert result.success is False
    assert "cancelled" in (result.error_message or "").lower()
    assert flagged == [], "cards were flagged from a partial (cancelled) review"
    assert "done" in [name for name, _ in spy.calls]


def test_run_art_prompts_returns_busy_when_lock_held(monkeypatch) -> None:
    from mtgai.runtime import ai_lock

    called: list[int] = []
    monkeypatch.setattr(
        "mtgai.art.prompt_builder.generate_prompts_for_set",
        lambda **_k: called.append(1),
    )

    assert ai_lock.try_acquire("Other action") is not None
    spy = _SpyEmitter()
    result = stages.run_art_prompts(progress_cb=None, emitter=spy)

    assert result.success is False
    assert "holds the lock" in (result.error_message or "")
    assert called == [], "art-prompt generator ran despite the lock being held"


def test_run_art_prompts_halts_on_cancel(monkeypatch) -> None:
    monkeypatch.setattr(
        "mtgai.art.prompt_builder.generate_prompts_for_set",
        lambda **_k: {"processed": 2, "skipped": 0, "cost_usd": 0.0, "cancelled": True},
    )

    spy = _SpyEmitter()
    result = stages.run_art_prompts(progress_cb=None, emitter=spy)

    assert result.success is False
    assert "cancelled" in (result.error_message or "").lower()
    assert "done" in [name for name, _ in spy.calls]


# art_select folded into the merged art_gen runner: the best-of-N selection
# sub-step's lock/cancel behavior now lives inside run_art_gen.
def test_run_art_gen_select_returns_busy_when_lock_held(monkeypatch) -> None:
    from mtgai.runtime import ai_lock

    monkeypatch.setattr(
        "mtgai.art.image_generator.generate_art_for_set",
        lambda **_k: {"generated": 0, "skipped": 0, "failed": 0},
    )
    called: list[int] = []
    monkeypatch.setattr(
        "mtgai.art.art_selector.select_art_for_set",
        lambda **_k: called.append(1),
    )

    assert ai_lock.try_acquire("Other action") is not None
    spy = _SpyEmitter()
    result = stages.run_art_gen(progress_cb=None, emitter=spy)

    assert result.success is False
    assert "holds the lock" in (result.error_message or "")
    assert called == [], "art selector ran despite the lock being held"


def test_run_art_gen_halts_on_select_cancel(monkeypatch) -> None:
    monkeypatch.setattr(
        "mtgai.art.image_generator.generate_art_for_set",
        lambda **_k: {"generated": 1, "skipped": 0, "failed": 0},
    )
    monkeypatch.setattr(
        "mtgai.art.art_selector.select_art_for_set",
        lambda **_k: {"reviewed": 1, "estimated_cost_usd": 0.0, "cancelled": True},
    )

    spy = _SpyEmitter()
    result = stages.run_art_gen(progress_cb=None, emitter=spy)

    assert result.success is False
    assert "cancelled" in (result.error_message or "").lower()
    assert "done" in [name for name, _ in spy.calls]


# ---------------------------------------------------------------------------
# The LLM tok/s poller must NEVER wrap the ComfyUI image-generation phase of an
# art stage (card 6a25497b). The poller probes a model-specific llama-swap
# endpoint, which forces a (re)load of the model that was deliberately unloaded
# before ComfyUI — re-contending VRAM with Flux and crushing the step rate.
# These pin: (1) char_portraits scopes its poller to step-1 detection only, and
# (2) art_gen runs the pure-ComfyUI generate phase with NO poller while keeping
#     the LLM judge phase polled (so LLM-phase telemetry doesn't regress).
# ---------------------------------------------------------------------------


class _TrackingPoller:
    """Stand-in poller recording whether it's currently active (entered).

    Used to prove the poller's ``with`` span does not overlap the ComfyUI
    image-generation call: the image-gen stub asserts the poller is NOT active
    while it runs.
    """

    def __init__(self) -> None:
        self.active = False
        self.entered = False

    def __enter__(self):
        self.active = True
        self.entered = True
        return self

    def __exit__(self, *_exc) -> None:
        self.active = False


def test_char_portraits_poller_excludes_image_gen(monkeypatch, tmp_path) -> None:
    """``run_char_portraits`` must wrap its tok/s poller around ONLY the step-1
    LLM detection, never the ComfyUI image-gen phase. We assert the real
    ``generate_character_refs`` enters the passed ``detect_poller`` while the
    image-generation function (``generate_image_comfyui``) runs with the poller
    inactive."""
    pollers: list[_TrackingPoller] = []

    def fake_make_poller(stage, _emit, **_kw):
        assert stage == "char_portraits"
        p = _TrackingPoller()
        pollers.append(p)
        return p

    monkeypatch.setattr(stages, "make_poller", fake_make_poller)

    # Drive the real generate_character_refs against a 2-card pool with one
    # recurring entity so it reaches the image loop. Stub the LLM detection
    # (asserting the poller is active during it) and ComfyUI (asserting it is
    # NOT). Image gen runs out-of-band of the poller span = the fix.
    cp = "mtgai.art.character_portraits"
    poller_state: dict[str, bool] = {}

    def fake_detect(*_a, **_k):
        # The poller wraps this call — it must be active here.
        poller_state["active_during_detect"] = pollers[0].active
        return [
            {"entity_key": "hero", "name": "Hero", "kind": "character", "cards": ["1", "2"]}
        ], 0.0

    def fake_ensure_comfyui(**_k):
        return None

    def fake_image(*_a, **_k):
        # The poller must NOT be active during the ComfyUI image-generation call.
        poller_state["active_during_image"] = pollers[0].active
        return (b"png-bytes", {})

    monkeypatch.setattr(f"{cp}.detect_recurring_entities", fake_detect)
    monkeypatch.setattr(f"{cp}.ensure_comfyui", fake_ensure_comfyui)
    monkeypatch.setattr(f"{cp}.is_comfyui_running", lambda: True)
    monkeypatch.setattr(f"{cp}.kill_comfyui", lambda *_a, **_k: None)
    monkeypatch.setattr(f"{cp}.generate_image_comfyui", fake_image)
    monkeypatch.setattr(f"{cp}.attach_refs_to_cards", lambda *_a, **_k: 0)

    # Stub the project/asset-folder plumbing generate_character_refs needs.
    tmp = tmp_path
    cards_dir = tmp / "cards"
    cards_dir.mkdir()
    for i in (1, 2):
        (cards_dir / f"00{i}.json").write_text(
            f'{{"collector_number": "{i}", "name": "C{i}"}}', encoding="utf-8"
        )

    class _FakeSettings:
        def get_llm_model_id(self, _stage):
            return "fake-model"

        def get_thinking(self, _stage):
            return None

    class _FakeProject:
        set_code = "TST"
        settings = _FakeSettings()

    # These are imported inside generate_character_refs, so patch them at source.
    monkeypatch.setattr(
        "mtgai.runtime.active_project.require_active_project", lambda: _FakeProject()
    )
    monkeypatch.setattr("mtgai.io.asset_paths.set_artifact_dir", lambda: tmp)

    spy = _SpyEmitter()
    result = stages.run_char_portraits(progress_cb=None, emitter=spy)

    assert result.success is True
    assert pollers and pollers[0].entered, "detection poller was never entered"
    assert poller_state.get("active_during_detect") is True, (
        "poller must be active during step-1 LLM detection"
    )
    assert poller_state.get("active_during_image") is False, (
        "poller must NOT be active during the ComfyUI image-generation phase"
    )


def test_art_gen_no_poller_around_image_gen_but_judge_polled(monkeypatch) -> None:
    """``run_art_gen`` must run the pure-ComfyUI generate phase with NO poller
    (so it can't reload the unloaded LLM), while the LLM judge phase keeps its
    poller (LLM-phase telemetry must not regress)."""
    pollers: dict[str, _TrackingPoller] = {}

    def fake_make_poller(stage, _emit, **_kw):
        p = _TrackingPoller()
        pollers[stage] = p
        return p

    monkeypatch.setattr(stages, "make_poller", fake_make_poller)

    state: dict[str, object] = {}

    def fake_gen(**_k):
        # No poller may exist/be active during the ComfyUI generate phase.
        state["judge_poller_exists_during_gen"] = "art_select" in pollers
        state["gen_poller_made"] = "art_gen" in pollers
        return {"generated": 2, "skipped": 0, "failed": 0}

    def fake_select(**_k):
        state["judge_poller_active"] = pollers["art_select"].active
        return {"reviewed": 2, "estimated_cost_usd": 0.0, "cancelled": False}

    monkeypatch.setattr("mtgai.art.image_generator.generate_art_for_set", fake_gen)
    monkeypatch.setattr("mtgai.art.art_selector.select_art_for_set", fake_select)

    spy = _SpyEmitter()
    result = stages.run_art_gen(progress_cb=None, emitter=spy)

    assert result.success is True
    # The image-gen phase makes NO poller at all (no "art_gen" poller built).
    assert state.get("gen_poller_made") is False, (
        "image-generation phase must not build an LLM poller"
    )
    # The judge poller isn't even constructed until after image gen.
    assert state.get("judge_poller_exists_during_gen") is False
    # But the judge phase IS polled — telemetry preserved.
    assert "art_select" in pollers and pollers["art_select"].entered
    assert state.get("judge_poller_active") is True


def test_art_gen_card_event_carries_versions(monkeypatch) -> None:
    """Each ``art_gen_card`` 'generated' event must carry a ``versions`` payload
    so the tab can render art live (not only on stage-finish / F5). With no open
    project the list degrades to empty, but the key is always present + wired."""

    def fake_gen(*, progress_callback=None, **_k):
        if progress_callback is not None:
            progress_callback("1", 1, 2, "Generated 3 version(s) for X", 0.0)
        return {"generated": 1, "skipped": 0, "failed": 0}

    def fake_select(**_k):
        return {"reviewed": 1, "estimated_cost_usd": 0.0, "cancelled": False}

    monkeypatch.setattr("mtgai.art.image_generator.generate_art_for_set", fake_gen)
    monkeypatch.setattr("mtgai.art.art_selector.select_art_for_set", fake_select)

    spy = _SpyEmitter()
    stages.run_art_gen(progress_cb=None, emitter=spy)

    generated = [
        data
        for name, data in spy.events
        if name == "art_gen_card" and data.get("phase") == "generated"
    ]
    assert generated, "a per-card 'generated' art_gen_card event must be emitted"
    assert "versions" in generated[0], "the event must carry a versions payload for live render"
    assert isinstance(generated[0]["versions"], list)
