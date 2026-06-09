"""The AI design-review stage's "already reviewed" tracking.

A later review instance must review only the cards it hasn't already seen *at
their current content* — a card regenerated since an earlier review pass gets
re-reviewed (new content -> new signature), while an untouched already-reviewed
card is skipped. This is tracked separately from the per-card ``reviews/<cn>.json``
logs because several card_gen/conformance regen passes can happen before the
first review pass even starts. ``generate_with_tool`` is monkeypatched so no real
model loads.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mtgai.review import ai_review
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
    # review_set reads these two inputs up front.
    (asset_dir / "mechanics").mkdir()
    (asset_dir / "mechanics" / "approved.json").write_text("[]", encoding="utf-8")
    (asset_dir / "mechanics" / "pointed-questions.json").write_text("[]", encoding="utf-8")
    yield asset_dir
    active_project.clear_active_project()


def _make_card(cn: str, oracle: str = "Vanilla."):
    from mtgai.models.card import Card

    return Card(
        name=f"Card {cn}",
        slot_id=cn,
        collector_number=cn,
        type_line="Creature — Test",
        rarity="common",
        colors=["W"],
        power="2",
        toughness="2",
        oracle_text=oracle,
    )


def _ok_result(**_kwargs) -> dict:
    """A successful generate_with_tool payload: OK verdict, no revision."""
    return {
        "result": {"verdict": "OK", "issues": [], "revised_card": None},
        "input_tokens": 10,
        "output_tokens": 5,
        "model": "test-model",
    }


@pytest.fixture(autouse=True)
def _stub_llm(monkeypatch):
    monkeypatch.setattr(ai_review, "generate_with_tool", _ok_result)
    monkeypatch.setattr(ai_review, "cost_from_result", lambda _r: 0.0)
    monkeypatch.setattr(ai_review, "_review_model", lambda: "test-model")
    monkeypatch.setattr(ai_review, "_review_effort", lambda: None)


# ----------------------------------------------------------------------
# card_signature
# ----------------------------------------------------------------------


def test_card_signature_ignores_volatile_metadata():
    base = {"name": "A", "oracle_text": "Draw a card.", "rarity": "common"}
    # Same design fields + different pipeline metadata -> identical signature.
    a = {**base, "status": "draft", "updated_at": "t1", "flagged_by": None}
    b = {**base, "status": "approved", "updated_at": "t2", "flagged_by": "conformance"}
    assert ai_review.card_signature(a) == ai_review.card_signature(b)


def test_card_signature_tracks_design_change():
    a = {"name": "A", "oracle_text": "Draw a card."}
    b = {"name": "A", "oracle_text": "Draw two cards."}
    assert ai_review.card_signature(a) != ai_review.card_signature(b)


def test_reviewed_sidecar_round_trip(project: Path):
    ai_review.record_reviewed(project, "W-C-01", "sig1")
    ai_review.record_reviewed(project, "W-C-02", "sig2")
    assert ai_review.load_reviewed(project) == {"W-C-01": "sig1", "W-C-02": "sig2"}


# ----------------------------------------------------------------------
# review_set scoping
# ----------------------------------------------------------------------


def test_first_pass_reviews_all_and_records_signatures(project: Path):
    from mtgai.io.card_io import save_card

    for cn in ("W-C-01", "W-C-02", "W-C-03"):
        save_card(_make_card(cn), set_dir=project)

    reviews = ai_review.review_set()

    assert {r.collector_number for r in reviews} == {"W-C-01", "W-C-02", "W-C-03"}
    # Every reviewed card now has a recorded signature.
    assert set(ai_review.load_reviewed(project)) == {"W-C-01", "W-C-02", "W-C-03"}


def test_second_pass_skips_unchanged_cards(project: Path):
    from mtgai.io.card_io import save_card

    for cn in ("W-C-01", "W-C-02"):
        save_card(_make_card(cn), set_dir=project)

    assert len(ai_review.review_set()) == 2  # first pass reviews both
    # Nothing changed on disk -> a second pass reviews nothing.
    assert ai_review.review_set() == []


def test_regenerated_card_is_rereviewed(project: Path):
    from mtgai.io.card_io import save_card

    save_card(_make_card("W-C-01"), set_dir=project)
    save_card(_make_card("W-C-02"), set_dir=project)
    ai_review.review_set()  # first pass sees both

    # card_gen regenerates only W-C-02 (new oracle text -> new signature).
    save_card(_make_card("W-C-02", oracle="Draw a card, then discard a card."), set_dir=project)

    reviews = ai_review.review_set()
    assert [r.collector_number for r in reviews] == ["W-C-02"]


def test_pre_signature_project_rereviews_pool_once_then_scopes(project: Path):
    """A pre-signature project (reviews/<cn>.json but no reviewed.json) cannot
    trust the content-blind logs, so it re-reviews the whole pool once — which
    re-establishes signatures — and scopes correctly from then on."""
    from mtgai.io.card_io import save_card

    save_card(_make_card("W-C-01"), set_dir=project)
    save_card(_make_card("W-C-02"), set_dir=project)
    ai_review.review_set()

    # Simulate a pre-signature project: drop the signatures sidecar, keep the logs.
    ai_review.reviewed_path(project).unlink()
    assert ai_review.load_reviewed(project) == {}

    # W-C-02 was regenerated before this run; with no signatures to trust, the
    # whole pool is re-reviewed (the regenerated card is never wrongly skipped).
    save_card(_make_card("W-C-02", oracle="Gain 3 life."), set_dir=project)
    reviews = ai_review.review_set()
    assert {r.collector_number for r in reviews} == {"W-C-01", "W-C-02"}

    # Signatures are now re-established -> the next pass scopes to nothing changed.
    assert ai_review.review_set() == []


def test_card_filter_bypasses_the_skip(project: Path):
    from mtgai.io.card_io import save_card

    save_card(_make_card("W-C-01"), set_dir=project)
    ai_review.review_set()  # records W-C-01 as seen

    # An explicit single-card review runs even though the card is unchanged.
    reviews = ai_review.review_set(card_filter="W-C-01")
    assert [r.collector_number for r in reviews] == ["W-C-01"]


# ----------------------------------------------------------------------
# Resume recovery of persisted-REVISE cards (card 6a285a62)
# ----------------------------------------------------------------------


def _seed_partial_revise_run(set_dir: Path, cn: str) -> None:
    """Simulate a cancelled/crashed partial run that rated ``cn`` final REVISE.

    The earlier run reviewed the card (persisting ``reviews/<cn>.json`` with a
    REVISE verdict) and recorded its content signature — so a resume's skip filter
    will pass over it. The card sits on disk at that exact signature.
    """
    import json

    from mtgai.io.card_io import save_card

    card = _make_card(cn)
    save_card(card, set_dir=set_dir)
    # Sign the on-disk content (what the resume filter + recovery both read) so
    # the recorded signature matches byte-for-byte regardless of save-time
    # normalization.
    on_disk = next((set_dir / "cards").glob(f"{cn}_*.json"))
    sig = ai_review.card_signature(json.loads(on_disk.read_text(encoding="utf-8")))

    result = ai_review.CardReviewResult(
        collector_number=cn,
        card_name=card.name,
        rarity=card.rarity,
        review_tier="single",
        original_card=card.model_dump(mode="json"),
        final_verdict="REVISE",
        final_issues=[
            ai_review.ReviewIssue(
                category="playability", severity="major", description="unfixable nonsense"
            )
        ],
    )
    reviews_dir = set_dir / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    (reviews_dir / f"{cn}.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    ai_review.record_reviewed(set_dir, cn, sig)


def test_resume_flags_persisted_revise_card_skipped_by_filter(project: Path):
    """A card the earlier partial run rated final REVISE — skipped by the resume
    filter, so never re-entering this run's ``reviews`` — must still surface in the
    runner's ``unfixable`` list so it gets flagged for regen instead of shipping as
    if approved. Without the recovery this list is empty (the bug)."""
    # Earlier run: W-C-01 rated REVISE (recorded + persisted). Fresh cards added.
    _seed_partial_revise_run(project, "W-C-01")
    from mtgai.io.card_io import save_card

    save_card(_make_card("W-C-02"), set_dir=project)

    result = ai_review.review_all_cards()

    # The resume reviews only the not-yet-seen card; W-C-01 is skipped.
    assert result["reviewed"] == 1
    # ...but its persisted REVISE is recovered into unfixable for flagging.
    assert {u["slot_id"] for u in result["unfixable"]} == {"W-C-01"}
    assert "unfixable nonsense" in result["unfixable"][0]["reason"]


def test_resume_does_not_flag_persisted_revise_for_changed_card(project: Path):
    """A persisted REVISE is recovered only when the card is still on disk at the
    signature it was reviewed under. If the card was regenerated since (new
    signature), the resume re-reviews it (here -> OK) and the stale persisted
    verdict must NOT be flagged."""
    _seed_partial_revise_run(project, "W-C-01")
    from mtgai.io.card_io import save_card

    # card_gen regenerated W-C-01 since the partial run -> new content/signature.
    save_card(_make_card("W-C-01", oracle="Draw a card."), set_dir=project)

    result = ai_review.review_all_cards()

    # The regenerated card is re-reviewed this run (stub -> OK), not flagged from
    # the stale persisted REVISE.
    assert result["reviewed"] == 1
    assert result["unfixable"] == []


def test_resume_does_not_flag_persisted_revise_on_cancel(project: Path):
    """On a cancelled run the unfixable list is partial and the runner ignores it,
    so the recovery is suppressed too (no flagging from a half-finished resume)."""
    _seed_partial_revise_run(project, "W-C-01")

    result = ai_review.review_all_cards(should_cancel=lambda: True)

    assert result["cancelled"] is True
    assert result["unfixable"] == []
