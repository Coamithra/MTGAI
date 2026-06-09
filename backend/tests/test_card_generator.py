"""Unit tests for the card-generator's pure pieces.

The full ``generate_set`` orchestrator is exercised through the wizard
endpoint tests (``test_wizard_card_gen.py``). Here we cover the pure
helpers the cycle-sort redesign introduced:

* ``group_slots_into_batches`` — drives batching off the cycle-sort result
  instead of swingable structured seeds (no colour batching, oversized
  cycles split into ordered sub-batches all tagged to the same cycle).
* ``build_user_prompt`` with ``cycle_siblings`` — later sub-batches of an
  oversized cycle see prior members' full oracle text.
"""

from __future__ import annotations

from mtgai.generation import card_generator as cg
from mtgai.generation.card_generator import (
    GenerationProgress,
    _card_one_liner,
    _retry_card,
    group_slots_into_batches,
    reconcile_cycle_membership,
)
from mtgai.generation.prompts import _cycle_note, build_user_prompt, format_cycle_siblings
from mtgai.validation import (
    ValidationError,
    ValidationSeverity,
    _is_regen_trigger,
    format_validation_feedback,
)


def _slot(slot_id: str, *, cycle_id: str | None = None, **extra) -> dict:
    return {
        "slot_id": slot_id,
        "color": extra.pop("color", "W"),
        "rarity": "common",
        "card_type": "creature",
        "cmc_target": 2,
        "mechanic_tag": "evergreen",
        "cycle_id": cycle_id,
        "tweaked_text": extra.pop("tweaked_text", None),
        **extra,
    }


# ---------------------------------------------------------------------------
# group_slots_into_batches
# ---------------------------------------------------------------------------


def test_no_confirmed_cycles_chunks_in_slot_id_order() -> None:
    """No colour batching: pure slot_id order at batch_size."""
    slots = [
        _slot("003", color="R"),
        _slot("001", color="W"),
        _slot("002", color="U"),
        _slot("004", color="B"),
    ]
    batches = group_slots_into_batches(slots, confirmed_cycles={}, batch_size=2)
    assert [[s["slot_id"] for s in b] for b in batches] == [["001", "002"], ["003", "004"]]


def test_confirmed_cycle_becomes_own_batch_then_ordinary() -> None:
    """A confirmed family is pulled out as its own batch; remaining slots
    chunk in slot_id order."""
    slots = [
        _slot("001", cycle_id="gates"),
        _slot("002"),
        _slot("003", cycle_id="gates"),
        _slot("004"),
    ]
    batches = group_slots_into_batches(
        slots,
        confirmed_cycles={"gates": ["001", "003"]},
        batch_size=2,
    )
    # Family first (both members in one batch since batch_size=2), then ordinary.
    assert [s["slot_id"] for s in batches[0]] == ["001", "003"]
    assert [s["slot_id"] for s in batches[1]] == ["002", "004"]


def test_oversized_cycle_splits_into_ordered_subbatches_tagged_to_cycle() -> None:
    """A 10-member pairs10 cycle at batch_size=3 splits into 4 ordered sub-batches,
    all carrying the same cycle_id so the loop's sibling logic can thread prior
    members in."""
    cycle = [_slot(f"{i:03d}", cycle_id="pairs10") for i in range(1, 11)]
    confirmed = {"pairs10": [s["slot_id"] for s in cycle]}
    batches = group_slots_into_batches(cycle, confirmed_cycles=confirmed, batch_size=3)
    assert len(batches) == 4
    # Order is preserved.
    flat_ids = [s["slot_id"] for b in batches for s in b]
    assert flat_ids == [f"{i:03d}" for i in range(1, 11)]
    # Every sub-batch is tagged to the same cycle (the loop reads this to
    # decide whether to thread siblings).
    for b in batches:
        cids = {s["cycle_id"] for s in b}
        assert cids == {"pairs10"}


def test_audit_pruned_slot_lands_in_ordinary_pile_in_slot_id_order() -> None:
    """A slot whose seed cycle_id is "gates" but which the audit dropped (not
    in confirmed_cycles["gates"]) batches as ordinary, sorted by slot_id with
    the rest — its stale seed cycle_id is not used as a grouping key."""
    slots = [
        _slot("001", cycle_id="gates"),
        _slot("002", cycle_id="gates"),  # pruned by the audit
        _slot("003", cycle_id="gates"),
        _slot("009"),  # ordinary
    ]
    batches = group_slots_into_batches(
        slots,
        confirmed_cycles={"gates": ["001", "003"]},
        batch_size=10,  # one big batch for the ordinary pile
    )
    # Family batch (audit-confirmed members only):
    assert [s["slot_id"] for s in batches[0]] == ["001", "003"]
    # Ordinary batch: 002 (pruned) and 009 in slot_id order.
    assert [s["slot_id"] for s in batches[1]] == ["002", "009"]


def test_none_confirmed_cycles_skips_cycle_batching_for_dry_runs() -> None:
    """``confirmed_cycles=None`` (the dry-run / no-LLM path) batches everything
    as ordinary slots in slot_id order — no cycle batches."""
    slots = [
        _slot("001", cycle_id="gates"),
        _slot("002", cycle_id="gates"),
        _slot("003"),
    ]
    batches = group_slots_into_batches(slots, confirmed_cycles=None, batch_size=10)
    assert len(batches) == 1
    assert [s["slot_id"] for s in batches[0]] == ["001", "002", "003"]


# ---------------------------------------------------------------------------
# reconcile_cycle_membership — the audit's confirmed membership is the single
# source of truth for the cycle template / _cycle_note / sibling machinery
# ---------------------------------------------------------------------------


def _stamp_cycle_templates(slots: list[dict], cycle_templates: dict[str, str]) -> None:
    """Mirror generate_set's post-audit template stamp (off the reconciled
    cycle_id) so a test can assert end-to-end cycle-prompt behaviour."""
    for s in slots:
        cid = s.get("cycle_id")
        if cid and cycle_templates.get(cid):
            s["cycle_template"] = cycle_templates[cid]
        else:
            s.pop("cycle_template", None)


def test_reconcile_drops_pruned_slot_from_cycle_so_it_gets_no_cycle_prompt() -> None:
    """A slot whose seed cycle_id is "gates" but which the audit DROPPED (not in
    confirmed_cycles["gates"]) has its cycle_id cleared, so ``_cycle_note`` emits
    NO CYCLE MEMBER instruction for it. The confirmed member keeps its cycle_id +
    template. Fails before the fix: the dropped slot kept its seed cycle_id and
    was generated as a contradictory cycle member."""
    confirmed_member = _slot("001", cycle_id="gates", cycle_template="A guild gate.")
    dropped = _slot("002", cycle_id="gates", cycle_template="A guild gate.")  # audit dropped it
    ordinary = _slot("009")
    slots = [confirmed_member, dropped, ordinary]

    reconcile_cycle_membership(slots, {"gates": ["001"]})
    _stamp_cycle_templates(slots, {"gates": "A guild gate."})

    # Confirmed member keeps its family membership + template -> CYCLE MEMBER fires.
    assert confirmed_member["cycle_id"] == "gates"
    assert "CYCLE MEMBER" in _cycle_note(confirmed_member)
    # Dropped slot is cleared -> generated as ordinary, no cycle prompt, no template.
    assert dropped["cycle_id"] is None
    assert "cycle_template" not in dropped
    assert _cycle_note(dropped) == ""
    # An always-ordinary slot is untouched.
    assert ordinary["cycle_id"] is None
    assert _cycle_note(ordinary) == ""


def test_reconcile_dropped_slot_never_joins_real_familys_sibling_batch() -> None:
    """After reconciliation the dropped slot's cycle_id no longer matches the
    confirmed family, so the per-cycle sibling lookup/append (keyed on cycle_id)
    can't thread it into — or pollute — the real family's mirroring context. We
    assert membership keys directly: the dropped slot shares no cycle_id with the
    family, and only confirmed members carry the family key."""
    family_a = _slot("001", cycle_id="gates")
    family_b = _slot("003", cycle_id="gates")
    dropped = _slot("002", cycle_id="gates")  # audit dropped it
    slots = [family_a, family_b, dropped]

    reconcile_cycle_membership(slots, {"gates": ["001", "003"]})

    family_keys = {s["cycle_id"] for s in (family_a, family_b)}
    assert family_keys == {"gates"}
    # The dropped slot carries NO cycle_id, so it can never be looked up under
    # "gates" for siblings, nor appended into cycle_siblings_by_id["gates"].
    assert dropped["cycle_id"] is None
    assert dropped["cycle_id"] not in {"gates"}


def test_reconcile_emergent_family_uses_synthetic_key_and_no_template() -> None:
    """An emergent / cross-seed family the audit identified gets its synthetic
    ``cycle_N`` key stamped onto every member; none resolves a seed template, so
    the family batches+threads together but with no shared-template hint."""
    a = _slot("005", cycle_id=None)
    b = _slot("006", cycle_id="some_seed", cycle_template="stale")
    slots = [a, b]

    reconcile_cycle_membership(slots, {"cycle_0": ["005", "006"]})
    # The seed-keyed template registry has no "cycle_0" entry, so the stamp step
    # clears b's stale seed template.
    _stamp_cycle_templates(slots, {"some_seed": "stale"})

    assert a["cycle_id"] == "cycle_0"
    assert b["cycle_id"] == "cycle_0"
    assert "cycle_template" not in b
    # Both still read as cycle members (parallel structure), just template-less.
    assert "CYCLE MEMBER" in _cycle_note(a)
    assert "Cycle template" not in _cycle_note(a)


# ---------------------------------------------------------------------------
# format_cycle_siblings + build_user_prompt threading
# ---------------------------------------------------------------------------


def _sibling_card(name: str, oracle: str, *, cost: str = "{1}{W}", pt: tuple | None = None) -> dict:
    out = {
        "name": name,
        "mana_cost": cost,
        "type_line": "Land",
        "oracle_text": oracle,
    }
    if pt is not None:
        out["power"], out["toughness"] = pt
    return out


def test_format_cycle_siblings_renders_full_oracle_text() -> None:
    out = format_cycle_siblings(
        [
            _sibling_card(
                "Azorius Gate",
                "Azorius Gate enters the battlefield tapped.\n{T}: Add {W} or {U}.",
            )
        ]
    )
    assert "SIBLING CYCLE MEMBERS" in out
    assert "mirror their structure and wording" in out
    assert "Azorius Gate" in out
    # Full oracle text is included, not truncated.
    assert "Azorius Gate enters the battlefield tapped." in out
    assert "{T}: Add {W} or {U}." in out


def test_format_cycle_siblings_empty_returns_empty_string() -> None:
    assert format_cycle_siblings(None) == ""
    assert format_cycle_siblings([]) == ""


def test_build_user_prompt_threads_cycle_siblings_when_passed() -> None:
    """The siblings block appears in build_user_prompt when a list is passed,
    and not otherwise."""
    slots = [_slot("002", cycle_id="gates", tweaked_text="WB gate")]
    siblings = [
        _sibling_card(
            "Azorius Gate",
            "Azorius Gate enters the battlefield tapped.\n{T}: Add {W} or {U}.",
        )
    ]

    with_siblings = build_user_prompt(
        slots,
        mechanics=[],
        existing_cards=[],
        theme={"name": "T", "setting": "s"},
        archetypes=None,
        cycle_siblings=siblings,
    )
    without = build_user_prompt(
        slots,
        mechanics=[],
        existing_cards=[],
        theme={"name": "T", "setting": "s"},
        archetypes=None,
    )

    assert "SIBLING CYCLE MEMBERS" in with_siblings
    assert "Azorius Gate enters the battlefield tapped." in with_siblings
    assert "SIBLING CYCLE MEMBERS" not in without


# ---------------------------------------------------------------------------
# _card_one_liner — log helper, must never raise
# ---------------------------------------------------------------------------


def test_card_one_liner_tolerates_none_oracle_text() -> None:
    """An LLM retry once returned ``oracle_text: null`` and the unguarded
    ``oracle[:60]`` crashed the whole card_gen stage with ``'NoneType' object
    is not subscriptable``. This helper is just a log line — never raise."""
    # The original crash repro: oracle_text is explicitly None.
    out = _card_one_liner({"name": "Autobot Defender", "oracle_text": None})
    assert "Autobot Defender" in out
    # An entirely empty dict shouldn't raise either (missing every field).
    assert _card_one_liner({}) is not None
    # P/T defends against half-set fields (power without toughness, etc.).
    assert "1/" not in _card_one_liner({"name": "X", "power": "1"})


def test_card_one_liner_preserves_full_card_shape() -> None:
    """Sanity check that the happy-path output didn't regress after the
    defensive coercion (None → "" for every str field)."""
    out = _card_one_liner(
        {
            "name": "Lightning Bolt",
            "mana_cost": "{R}",
            "type_line": "Instant",
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        }
    )
    assert "Lightning Bolt" in out
    assert "{R}" in out
    assert "Instant" in out
    assert "deals 3 damage" in out


def _verr(code: str, message: str) -> ValidationError:
    return ValidationError(
        validator="t",
        severity=ValidationSeverity.MANUAL,
        field="f",
        message=message,
        error_code=code,
    )


# ---------------------------------------------------------------------------
# _retry_card best-effort fallback — a slot is never silently dropped
# ---------------------------------------------------------------------------


def _fake_result(card_dict: dict) -> dict:
    """A minimal ``generate_with_tool`` result shape (the keys card_gen reads)."""
    return {
        "result": card_dict,
        "model": "claude-test",
        "input_tokens": 10,
        "output_tokens": 20,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }


def _overflowing_creature(name: str) -> dict:
    """A parsable creature whose oracle text is past the 300-char limit — a
    genuine, unfixable regen trigger (unlike type-line overflow, which now
    auto-fixes). Used to exercise the never-fully-conforms path."""
    return {
        "name": name,
        "mana_cost": "{2}{G}",
        "type_line": "Creature — Beast",
        "oracle_text": "Whenever this attacks, draw a card. " * 12,  # >300 chars
        "power": "3",
        "toughness": "3",
        "rarity": "common",
    }


def test_retry_card_returns_best_effort_when_never_conforms(tmp_path, monkeypatch) -> None:
    """When every retry still trips a regen trigger, ``_retry_card`` returns
    ``(None, best_effort_card)`` so the caller can save the slot flagged rather
    than drop it — the slot-009 "missing a card is not acceptable" fix."""
    calls = {"n": 0}

    def fake_retry_single(slot, error_msg, *a, **k):
        calls["n"] += 1
        return _fake_result(_overflowing_creature(f"Megatron {calls['n']}"))

    monkeypatch.setattr(cg, "_retry_single_card", fake_retry_single)
    monkeypatch.setattr(cg, "_save_generation_log", lambda *a, **k: None)
    progress = GenerationProgress(path=tmp_path / "progress.json")
    slot = {"slot_id": "009", "color": "B", "rarity": "mythic", "card_type": "creature"}

    clean, best = _retry_card(
        slot,
        "overflow",
        mechanics=[],
        existing_cards=[],
        theme=None,
        model="m",
        progress=progress,
        set_code="TST",
    )

    assert clean is None  # never fully conformed
    assert best is not None  # but a parsable best-effort survived
    assert best.name.startswith("Megatron")
    # It exhausted the retry budget (attempts 2..MAX_RETRIES).
    assert calls["n"] == cg.MAX_RETRIES - 1


def test_retry_card_returns_none_best_effort_when_unparsable(tmp_path, monkeypatch) -> None:
    """If no attempt even parses into a Card, best-effort is None and the caller
    must treat the slot as a hard failure (no card to ship)."""

    def fake_retry_single(slot, error_msg, *a, **k):
        return _fake_result({"name": "X"})  # no type_line → unparsable

    monkeypatch.setattr(cg, "_retry_single_card", fake_retry_single)
    monkeypatch.setattr(cg, "_save_generation_log", lambda *a, **k: None)
    progress = GenerationProgress(path=tmp_path / "progress.json")
    slot = {"slot_id": "009", "color": "B", "rarity": "mythic", "card_type": "creature"}

    clean, best = _retry_card(
        slot,
        "parse fail",
        mechanics=[],
        existing_cards=[],
        theme=None,
        model="m",
        progress=progress,
        set_code="TST",
    )
    assert clean is None
    assert best is None


def test_retry_card_returns_clean_card_on_success(tmp_path, monkeypatch) -> None:
    """A retry that fully conforms returns ``(card, card)``."""

    def fake_retry_single(slot, error_msg, *a, **k):
        return _fake_result(
            {
                "name": "Optimus Prime",
                "mana_cost": "{2}{W}",
                "type_line": "Creature — Robot",
                "oracle_text": "Vigilance",
                "power": "4",
                "toughness": "5",
                "rarity": "rare",
            }
        )

    monkeypatch.setattr(cg, "_retry_single_card", fake_retry_single)
    monkeypatch.setattr(cg, "_save_generation_log", lambda *a, **k: None)
    progress = GenerationProgress(path=tmp_path / "progress.json")
    slot = {"slot_id": "010", "color": "W", "rarity": "rare", "card_type": "creature"}

    clean, best = _retry_card(
        slot,
        "feedback",
        mechanics=[],
        existing_cards=[],
        theme=None,
        model="m",
        progress=progress,
        set_code="TST",
    )
    assert clean is not None
    assert clean is best
    assert clean.name == "Optimus Prime"


def test_regen_feedback_includes_all_regen_triggers_not_just_overflow() -> None:
    """Card-gen's retry feedback must carry EVERY regen-trigger error, not only
    ``text_overflow.*``. A non-overflow trigger (e.g. ``nonland_missing_cost``)
    used to be filtered out, handing ``format_validation_feedback`` zero errors so
    the LLM retried blind. Mirrors card_generator's inline filter idiom."""
    errors = [
        _verr("type_check.nonland_missing_cost", "Non-land has no mana cost"),
        _verr("type_check.pt_slash", "Power and toughness in one field"),
        _verr("color_pie.off_color", "Off-color effect"),  # NOT a regen trigger
    ]

    regen_errors = [e for e in errors if _is_regen_trigger(e)]

    # The non-overflow triggers survive; the non-trigger finding is dropped.
    codes = {e.error_code for e in regen_errors}
    assert codes == {"type_check.nonland_missing_cost", "type_check.pt_slash"}

    feedback = format_validation_feedback("Test Card", regen_errors)
    assert "no mana cost" in feedback
    assert "Power and toughness" in feedback

    # The old overflow-only filter would have produced empty feedback here.
    overflow_only = [
        e for e in errors if e.error_code and e.error_code.startswith("text_overflow.")
    ]
    assert overflow_only == []
