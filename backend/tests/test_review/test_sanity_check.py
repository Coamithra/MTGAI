"""The finalize sanity gate — the batched/streamed LLM check + the 5% cap.

Covers ``review.sanity_check.check_sanity`` (one streamed flag-only call per
batch; basics/reprints skipped; truncation tail left unknown) and the cap +
marking logic in ``review.finalize._apply_sanity_check`` (≤cap → cards marked
``sanity_excluded``; >cap → none marked + warning; idempotent re-runs clear
stale flags). The LLM stream is mocked exactly like the conformance gate's tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mtgai.analysis import gate_common
from mtgai.models.card import Card
from mtgai.models.enums import Rarity
from mtgai.runtime import active_project
from mtgai.settings.model_settings import ModelSettings


@pytest.fixture
def project(tmp_path: Path):
    asset_dir = tmp_path / "asset"
    asset_dir.mkdir()
    active_project.write_active_project(
        active_project.ProjectState(
            set_code="ABC", settings=ModelSettings(asset_folder=str(asset_dir))
        )
    )
    yield asset_dir
    active_project.clear_active_project()


def _make_card(cn: str, **overrides) -> Card:
    defaults = {
        "name": f"Card {cn}",
        "collector_number": cn,
        "type_line": "Creature — Test",
        "oracle_text": f"Ability {cn}.",
        "power": "2",
        "toughness": "2",
        "rarity": Rarity.COMMON,
    }
    defaults.update(overrides)
    return Card(**defaults)


def _fake_stream(flag_map: dict[str, str], *, stop_reason: str = "stop"):
    """A ``stream_text`` stand-in: emit a ``--CARD <id>--`` block for each id in
    ``flag_map`` that appears in the batch's user prompt, then a ``complete`` event
    carrying ``stop_reason`` (``"length"`` simulates truncation)."""

    def stream_text(**kwargs):
        user_prompt = kwargs.get("user_prompt", "")
        stream_text.calls += 1
        text = "".join(
            f"--CARD {cn}--\n{reason}\n"
            for cn, reason in flag_map.items()
            if f"--CARD-ID {cn}--" in user_prompt
        )
        if text:
            yield {"type": "text_delta", "text": text}
        yield {
            "type": "complete",
            "text": text,
            "stop_reason": stop_reason,
            "input_tokens": 5,
            "output_tokens": 5,
            "model": kwargs.get("model", "m"),
        }

    stream_text.calls = 0
    return stream_text


# ---------------------------------------------------------------------------
# check_sanity
# ---------------------------------------------------------------------------


def test_check_sanity_batches_and_streams(project, monkeypatch):
    from mtgai.review import sanity_check as sc

    cards = [_make_card("001"), _make_card("002"), _make_card("003")]
    fake = _fake_stream({"002": "creature has no power/toughness"})
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.01)

    started: list[list[dict]] = []
    streamed: list[dict] = []
    flagged, analysis, cost = sc.check_sanity(
        cards,
        on_start=lambda lst: started.append(lst),
        on_card=lambda rec: streamed.append(rec),
    )

    # One streamed call for the whole batch (not one per card).
    assert fake.calls == 1
    assert [c["collector_number"] for c in started[0]] == ["001", "002", "003"]
    # on_card fires per card in listing order: 001 ✓, 002 ✗ (flag), 003 ✓.
    assert [(r["collector_number"], r["ok"]) for r in streamed] == [
        ("001", True),
        ("002", False),
        ("003", True),
    ]
    assert flagged == {"002": "creature has no power/toughness"}
    assert cost == pytest.approx(0.01)
    assert "2/3" in analysis


def test_check_sanity_skips_basics_and_reprints(project, monkeypatch):
    from mtgai.review import sanity_check as sc

    cards = [
        _make_card("001"),
        _make_card(
            "L-01",
            name="Plains",
            type_line="Basic Land — Plains",
            supertypes=["Basic"],
            card_types=["Land"],
            power=None,
            toughness=None,
            oracle_text="",
        ),
        _make_card("R-01", is_reprint=True),
    ]
    fake = _fake_stream({})  # nothing flagged
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    started: list[list[dict]] = []
    flagged, _analysis, _cost = sc.check_sanity(cards, on_start=lambda lst: started.append(lst))

    # Only the ordinary card is checked — the basic land + reprint are filtered out.
    assert [c["collector_number"] for c in started[0]] == ["001"]
    assert flagged == {}


def test_check_sanity_truncation_marks_unknown(project, monkeypatch):
    from mtgai.review import sanity_check as sc

    cards = [_make_card("001"), _make_card("002")]
    fake = _fake_stream({}, stop_reason="length")  # every attempt truncates
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    streamed: list[dict] = []
    flagged, analysis, _cost = sc.check_sanity(cards, on_card=lambda rec: streamed.append(rec))

    assert fake.calls == gate_common.MAX_BATCH_ATTEMPTS
    assert all(r["ok"] is None for r in streamed)  # unknown, not flagged
    assert flagged == {}
    assert "could not be checked" in analysis


# ---------------------------------------------------------------------------
# _apply_sanity_check — the 5% cap + reversible marking
# ---------------------------------------------------------------------------


def _apply(cards, asset, flagged, monkeypatch):
    """Run _apply_sanity_check with check_sanity stubbed to return ``flagged``."""
    from mtgai.review import finalize as fin

    monkeypatch.setattr(
        "mtgai.review.sanity_check.check_sanity",
        lambda cards, **kw: (flagged, "stub", 0.0),
    )
    return fin._apply_sanity_check(
        cards,
        asset,
        dry_run=False,
        on_start=None,
        on_card=None,
        on_progress=None,
        should_cancel=None,
    )


def test_apply_marks_flagged_under_cap(project, monkeypatch):
    from mtgai.io.card_io import load_card, save_card

    # 40 cards, 1 flagged = 2.5% < 5% cap → excluded.
    cards = [_make_card(f"{i:03d}") for i in range(1, 41)]
    for c in cards:
        save_card(c, set_dir=project)

    result = _apply(cards, project, {"005": "garbled text"}, monkeypatch)

    assert result["sanity_cap_breached"] is False
    assert result["sanity_checked_count"] == 40
    assert [e["collector_number"] for e in result["excluded_cards"]] == ["005"]
    # Persisted, reversibly.
    reloaded = load_card(project / "cards" / "005_card_005.json")
    assert reloaded.sanity_excluded is True
    assert reloaded.sanity_exclusion_reason == "garbled text"


def test_apply_cap_breach_excludes_none(project, monkeypatch):
    from mtgai.io.card_io import load_card, save_card

    # 10 cards, 2 flagged = 20% > 5% cap → exclude NONE + warn.
    cards = [_make_card(f"{i:03d}") for i in range(1, 11)]
    for c in cards:
        save_card(c, set_dir=project)

    result = _apply(cards, project, {"003": "bad", "007": "bad"}, monkeypatch)

    assert result["sanity_cap_breached"] is True
    assert result["sanity_flagged_count"] == 2
    assert result["excluded_cards"] == []
    assert result["sanity_warning"]
    assert load_card(project / "cards" / "003_card_003.json").sanity_excluded is False


def test_apply_clears_stale_flags_on_rerun(project, monkeypatch):
    from mtgai.io.card_io import load_card, save_card

    # A card carrying a stale exclusion from a prior run.
    cards = [_make_card(f"{i:03d}") for i in range(1, 41)]
    cards[4] = cards[4].model_copy(
        update={"sanity_excluded": True, "sanity_exclusion_reason": "old"}
    )
    for c in cards:
        save_card(c, set_dir=project)

    # This run flags nothing → the stale flag must be cleared.
    result = _apply(cards, project, {}, monkeypatch)

    assert result["excluded_cards"] == []
    assert load_card(project / "cards" / "005_card_005.json").sanity_excluded is False
