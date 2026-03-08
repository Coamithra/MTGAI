"""Tests for pipeline status values, transitions, and card status tracking."""

from datetime import UTC, datetime

import pytest

from mtgai.models.card import Card, GenerationAttempt
from mtgai.models.enums import CardStatus

# ---------------------------------------------------------------------------
# Basic status values
# ---------------------------------------------------------------------------


def test_status_values():
    """All expected statuses exist."""
    assert CardStatus.DRAFT == "draft"
    assert CardStatus.VALIDATED == "validated"
    assert CardStatus.APPROVED == "approved"
    assert CardStatus.ART_GENERATED == "art_generated"
    assert CardStatus.RENDERED == "rendered"
    assert CardStatus.PRINT_READY == "print_ready"


def test_default_status_is_draft():
    """New cards start in DRAFT status."""
    card = Card(name="Test", type_line="Instant")
    assert card.status == CardStatus.DRAFT


def test_status_can_be_set():
    """Card status can be set to any valid value."""
    card = Card(name="Test", type_line="Instant", status=CardStatus.APPROVED)
    assert card.status == CardStatus.APPROVED


def test_status_update_via_copy():
    """Status can be updated via model_copy."""
    card = Card(name="Test", type_line="Instant")
    updated = card.model_copy(update={"status": CardStatus.VALIDATED})
    assert updated.status == CardStatus.VALIDATED
    assert card.status == CardStatus.DRAFT  # original unchanged


# ---------------------------------------------------------------------------
# All valid forward transitions
# ---------------------------------------------------------------------------

FORWARD_TRANSITIONS = [
    (CardStatus.DRAFT, CardStatus.VALIDATED),
    (CardStatus.VALIDATED, CardStatus.APPROVED),
    (CardStatus.APPROVED, CardStatus.ART_GENERATED),
    (CardStatus.ART_GENERATED, CardStatus.RENDERED),
    (CardStatus.RENDERED, CardStatus.PRINT_READY),
]


@pytest.mark.parametrize("from_status,to_status", FORWARD_TRANSITIONS)
def test_forward_status_transitions(from_status, to_status):
    """Each forward transition produces the expected status."""
    card = Card(name="Pipeline Card", type_line="Creature", status=from_status)
    updated = card.model_copy(update={"status": to_status})
    assert updated.status == to_status
    assert card.status == from_status


def test_full_pipeline_forward():
    """A card can be advanced through the entire pipeline."""
    card = Card(name="Journey Card", type_line="Creature")
    assert card.status == CardStatus.DRAFT

    statuses = [
        CardStatus.VALIDATED,
        CardStatus.APPROVED,
        CardStatus.ART_GENERATED,
        CardStatus.RENDERED,
        CardStatus.PRINT_READY,
    ]
    for status in statuses:
        card = card.model_copy(update={"status": status})
    assert card.status == CardStatus.PRINT_READY


# ---------------------------------------------------------------------------
# Rejection / reset transitions
# ---------------------------------------------------------------------------


REJECTION_TRANSITIONS = [
    (CardStatus.APPROVED, CardStatus.DRAFT),
    (CardStatus.ART_GENERATED, CardStatus.APPROVED),
    (CardStatus.RENDERED, CardStatus.ART_GENERATED),
    (CardStatus.PRINT_READY, CardStatus.RENDERED),
    (CardStatus.VALIDATED, CardStatus.DRAFT),
]


@pytest.mark.parametrize("from_status,to_status", REJECTION_TRANSITIONS)
def test_rejection_transitions(from_status, to_status):
    """Rejection transitions reset the card to an earlier status."""
    card = Card(name="Rejected Card", type_line="Creature", status=from_status)
    updated = card.model_copy(update={"status": to_status})
    assert updated.status == to_status
    assert card.status == from_status


def test_reject_to_draft_from_print_ready():
    """A print_ready card can be sent all the way back to draft."""
    card = Card(name="Rework Card", type_line="Creature", status=CardStatus.PRINT_READY)
    reset = card.model_copy(update={"status": CardStatus.DRAFT})
    assert reset.status == CardStatus.DRAFT


# ---------------------------------------------------------------------------
# Status with generation attempts
# ---------------------------------------------------------------------------


def test_card_with_failed_attempts_in_draft():
    """A card with only failed generation attempts stays in draft."""
    attempts = [
        GenerationAttempt(
            attempt_number=1,
            timestamp=datetime.now(tz=UTC),
            success=False,
            error_message="Bad output",
        ),
        GenerationAttempt(
            attempt_number=2,
            timestamp=datetime.now(tz=UTC),
            success=False,
            error_message="Rate limited",
        ),
    ]
    card = Card(
        name="Failing Card",
        type_line="Creature",
        status=CardStatus.DRAFT,
        generation_attempts=attempts,
    )
    assert card.status == CardStatus.DRAFT
    assert len(card.generation_attempts) == 2
    assert all(not a.success for a in card.generation_attempts)


def test_card_with_successful_attempt_can_be_validated():
    """A card with a successful generation attempt can move to validated."""
    attempts = [
        GenerationAttempt(
            attempt_number=1,
            timestamp=datetime.now(tz=UTC),
            success=False,
            error_message="Bad output",
        ),
        GenerationAttempt(
            attempt_number=2,
            timestamp=datetime.now(tz=UTC),
            success=True,
            input_tokens=200,
            output_tokens=100,
            cost_usd=0.002,
        ),
    ]
    card = Card(
        name="Success Card",
        type_line="Creature",
        generation_attempts=attempts,
    )
    validated = card.model_copy(update={"status": CardStatus.VALIDATED})
    assert validated.status == CardStatus.VALIDATED
    assert validated.generation_attempts[-1].success is True


def test_card_tracks_art_and_render_attempts():
    """A card tracks separate attempt lists for generation, art, and render."""
    card = Card(
        name="Full Pipeline",
        type_line="Creature",
        generation_attempts=[
            GenerationAttempt(
                attempt_number=1,
                timestamp=datetime.now(tz=UTC),
                success=True,
            ),
        ],
        art_generation_attempts=[
            GenerationAttempt(
                attempt_number=1,
                timestamp=datetime.now(tz=UTC),
                success=True,
            ),
        ],
        render_attempts=[
            GenerationAttempt(
                attempt_number=1,
                timestamp=datetime.now(tz=UTC),
                success=True,
            ),
        ],
    )
    assert len(card.generation_attempts) == 1
    assert len(card.art_generation_attempts) == 1
    assert len(card.render_attempts) == 1


# ---------------------------------------------------------------------------
# Batch status update
# ---------------------------------------------------------------------------


def test_batch_status_update():
    """Multiple cards can have their statuses updated in a batch."""
    cards = [
        Card(name=f"Card {i}", type_line="Creature", status=CardStatus.DRAFT) for i in range(5)
    ]
    updated_cards = [c.model_copy(update={"status": CardStatus.VALIDATED}) for c in cards]
    assert all(c.status == CardStatus.VALIDATED for c in updated_cards)
    assert all(c.status == CardStatus.DRAFT for c in cards)


def test_batch_mixed_status_update():
    """Different cards can be advanced to different statuses."""
    cards = [
        Card(name="Card A", type_line="Creature", status=CardStatus.DRAFT),
        Card(name="Card B", type_line="Instant", status=CardStatus.VALIDATED),
        Card(name="Card C", type_line="Sorcery", status=CardStatus.APPROVED),
    ]
    targets = [CardStatus.VALIDATED, CardStatus.APPROVED, CardStatus.ART_GENERATED]
    updated = [
        card.model_copy(update={"status": target})
        for card, target in zip(cards, targets, strict=True)
    ]
    assert updated[0].status == CardStatus.VALIDATED
    assert updated[1].status == CardStatus.APPROVED
    assert updated[2].status == CardStatus.ART_GENERATED


# ---------------------------------------------------------------------------
# All status values via parametrize
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [
        CardStatus.DRAFT,
        CardStatus.VALIDATED,
        CardStatus.APPROVED,
        CardStatus.ART_GENERATED,
        CardStatus.RENDERED,
        CardStatus.PRINT_READY,
    ],
)
def test_all_statuses_assignable(status):
    """Every status enum member can be assigned to a card."""
    card = Card(name="Test", type_line="Instant", status=status)
    assert card.status == status
