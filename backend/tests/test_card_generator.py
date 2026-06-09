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
from mtgai.models.card import Card, Rarity
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
# End-to-end sibling-threading at BATCH_SIZE=1 (card 6a285a83)
#
# The card claimed two gaps in how generate_set's per-cycle sibling
# lookup/append (keyed on the slot's cycle_id) interacts with the audit's
# confirmed-family keys:
#   (1) an emergent (synthetic cycle_N) cycle got NO sibling threading at
#       BATCH_SIZE=1, because the lookup used the slot's SEED cycle_id (None /
#       mixed) which never matched the cycle_N key in cycle_siblings_by_id;
#   (2) two confirmed groups sharing one over-broad seed CROSS-threaded — the
#       second group's slots still carried the first group's seed key, so the
#       second family read+extended the FIRST family's sibling list.
#
# PR #110's reconcile_cycle_membership re-stamps each slot's cycle_id to its
# confirmed family key BEFORE batching/threading, which closes both gaps. The
# helper below mirrors generate_set's exact sibling state machine (init keyed
# by confirmed_cycles, per-batch lookup on the slot's cycle_id, per-batch
# append) so these regressions are asserted end-to-end against that flow.
# ---------------------------------------------------------------------------


def _thread_siblings_through_batches(
    batches: list[list[dict]],
    confirmed_cycles: dict[str, list[str]],
) -> list[list[str] | None]:
    """Replay generate_set's per-cycle sibling lookup+append over batches.

    Mirrors card_generator.generate_set lines ~1453 / ~1502-1507 / ~1668-1673:
    ``cycle_siblings_by_id`` is initialised from ``confirmed_cycles``; each batch
    threads the prior members of its shared ``cycle_id`` and then appends its own
    saved cards under that same id. Returns, per batch, the list of sibling
    *slot_ids* that were threaded in (or ``None`` when no siblings applied) — the
    observable the real loop hands to ``build_user_prompt(cycle_siblings=...)``.

    Each slot stands in for the card it generates, identified by its slot_id, so
    the test can assert which family's members reached which batch.
    """
    cycle_siblings_by_id: dict[str, list[str]] = {cid: [] for cid in confirmed_cycles}
    threaded_per_batch: list[list[str] | None] = []
    for batch in batches:
        batch_cycle_ids = {s.get("cycle_id") for s in batch}
        siblings_for_batch: list[str] | None = None
        if len(batch_cycle_ids) == 1:
            cid = next(iter(batch_cycle_ids))
            if cid and cycle_siblings_by_id.get(cid):
                siblings_for_batch = list(cycle_siblings_by_id[cid])
        threaded_per_batch.append(siblings_for_batch)

        # Append this batch's saved cards (stand-in: their slot_ids) under the
        # batch's shared cycle_id, exactly as the real loop does.
        if siblings_for_batch is not None or (
            len(batch_cycle_ids) == 1 and next(iter(batch_cycle_ids)) in cycle_siblings_by_id
        ):
            cid = next(iter(batch_cycle_ids))
            if cid:
                cycle_siblings_by_id.setdefault(cid, []).extend(s["slot_id"] for s in batch)
    return threaded_per_batch


def test_emergent_cycle_threads_siblings_at_batch_size_one() -> None:
    """Claim (1): an emergent (synthetic cycle_N) family DOES get sibling
    threading at BATCH_SIZE=1 after reconciliation.

    The members carry mixed/absent seed cycle_ids; the audit groups them under
    ``cycle_0``. Reconciliation re-stamps every member to ``cycle_0``, so the
    BATCH_SIZE=1 sub-batches each share that key — the lookup matches and later
    members see the earlier ones. Pre-#110 the lookup used the seed id and never
    matched, so each single-slot batch threaded nothing."""
    a = _slot("005", cycle_id=None)
    b = _slot("006", cycle_id="some_seed")
    c = _slot("007", cycle_id=None)
    slots = [a, b, c]
    confirmed = {"cycle_0": ["005", "006", "007"]}

    reconcile_cycle_membership(slots, confirmed)
    # Every member now keys on the synthetic cycle_0.
    assert [s["cycle_id"] for s in slots] == ["cycle_0", "cycle_0", "cycle_0"]

    batches = group_slots_into_batches(slots, confirmed_cycles=confirmed, batch_size=1)
    assert [[s["slot_id"] for s in b] for b in batches] == [["005"], ["006"], ["007"]]

    threaded = _thread_siblings_through_batches(batches, confirmed)
    # First member: nothing earlier. Second: sees the first. Third: sees both.
    assert threaded == [None, ["005"], ["005", "006"]]


def test_two_groups_sharing_one_seed_do_not_cross_thread() -> None:
    """Claim (2): two confirmed families that shared one over-broad seed do NOT
    cross-thread — each reads and extends only its OWN sibling list.

    slot_grouper.find_cycle_families uniquifies the second same-seed family's key
    to ``<seed>_<n>``; reconciliation stamps that distinct key onto its members.
    So at BATCH_SIZE=1 the second family's batches look up ``broad_0``, find their
    own (initially empty) list, and never touch the first family's ``broad`` list.
    Pre-#110 the second family's slots kept the seed ``broad`` key, so they read +
    extended the FIRST family's list, merging the two deliberately-separated
    families."""
    from mtgai.generation.slot_grouper import _key_by_seed_cycle_id

    # Both groups carry the same over-broad seed "broad"; the audit identified
    # them as two distinct families.
    slots = [_slot(sid, cycle_id="broad") for sid in ("001", "002", "003", "004")]
    slot_by_id = {s["slot_id"]: s for s in slots}
    confirmed = _key_by_seed_cycle_id(
        [["001", "002"], ["003", "004"]],
        slot_by_id,
    )
    # First family keeps the seed; the second is uniquified.
    assert confirmed == {"broad": ["001", "002"], "broad_0": ["003", "004"]}

    reconcile_cycle_membership(slots, confirmed)
    assert slot_by_id["001"]["cycle_id"] == "broad"
    assert slot_by_id["002"]["cycle_id"] == "broad"
    assert slot_by_id["003"]["cycle_id"] == "broad_0"
    assert slot_by_id["004"]["cycle_id"] == "broad_0"

    batches = group_slots_into_batches(slots, confirmed_cycles=confirmed, batch_size=1)
    threaded = _thread_siblings_through_batches(batches, confirmed)
    # Order: family "broad" first (sorted before "broad_0"): 001, 002 then 003, 004.
    # Family broad: 001 sees nothing, 002 sees 001.
    # Family broad_0: 003 sees nothing (NOT 001/002), 004 sees only 003.
    assert threaded == [None, ["001"], None, ["003"]]


# ---------------------------------------------------------------------------
# seed_cycle_siblings + the partial-cycle regen path (card 6a286120)
#
# On a review->regen bounce only a subset of a cycle's members re-enters the
# batch loop. generate_set now audits the FULL slot listing (filled +
# unfilled) so the family stays confirmable, and pre-seeds the per-cycle
# sibling lists with the filled members' on-disk cards — so the lone
# regenerated member keeps its cycle_id/template AND designs against its real
# siblings.
# ---------------------------------------------------------------------------


def _filled_card(sid: str, name: str, **overrides) -> Card:
    base = dict(
        name=name,
        mana_cost="",
        cmc=0.0,
        type_line="Land — Gate",
        oracle_text=f"~ enters tapped.\n{{T}}: Add one mana ({name}).",
        rarity=Rarity.COMMON,
        colors=[],
        color_identity=[],
        collector_number=sid,
        slot_id=sid,
        set_code="TST",
        card_types=["Land"],
        subtypes=["Gate"],
    )
    base.update(overrides)
    return Card(**base)


def test_seed_cycle_siblings_preseeds_filled_members_in_member_order() -> None:
    """Filled members' cards seed the family's sibling list in confirmed-member
    order; the unfilled (regen) member itself is excluded."""
    filled_a = _filled_card("001", "Azorius Gate")
    filled_c = _filled_card("003", "Dimir Gate")
    confirmed = {"gates": ["001", "002", "003"]}

    seeded = cg.seed_cycle_siblings(confirmed, {"002"}, [filled_c, filled_a])

    assert list(seeded) == ["gates"]
    assert [c["name"] for c in seeded["gates"]] == ["Azorius Gate", "Dimir Gate"]
    # The seeded dicts are full card dumps — the prompt renders oracle_text.
    assert "enters tapped" in seeded["gates"][0]["oracle_text"]


def test_seed_cycle_siblings_first_run_seeds_empty_lists() -> None:
    """On a first run every member is unfilled, so every family seeds empty —
    byte-identical to the previous ``{cid: []}`` initialisation."""
    confirmed = {"gates": ["001", "002"], "cycle_0": ["005", "006"]}
    seeded = cg.seed_cycle_siblings(confirmed, {"001", "002", "005", "006"}, [])
    assert seeded == {"gates": [], "cycle_0": []}


def test_seed_cycle_siblings_skips_members_without_card_on_disk() -> None:
    """A filled-by-the-ledger member whose card isn't loadable (e.g. a failed
    slot) is skipped rather than crashing or seeding a hole."""
    filled = _filled_card("001", "Azorius Gate")
    confirmed = {"gates": ["001", "002", "003"]}
    # 003 is neither unfilled nor on disk.
    seeded = cg.seed_cycle_siblings(confirmed, {"002"}, [filled])
    assert [c["name"] for c in seeded["gates"]] == ["Azorius Gate"]


def test_seed_cycle_siblings_matches_by_collector_number_when_slot_id_missing() -> None:
    """An older card without ``slot_id`` still matches via collector_number."""
    legacy = _filled_card("001", "Azorius Gate", slot_id=None)
    seeded = cg.seed_cycle_siblings({"gates": ["001", "002"]}, {"002"}, [legacy])
    assert [c["name"] for c in seeded["gates"]] == ["Azorius Gate"]


def test_partial_cycle_regen_lone_member_keeps_cycle_and_threads_filled_siblings() -> None:
    """End-to-end mirror of the regen-bounce flow: a 3-member family with one
    flagged member. The full-listing audit confirms the whole family, so the
    lone unfilled member keeps its cycle_id + template (CYCLE MEMBER fires),
    batches under the family key, and its prompt threads the two filled
    siblings' actual cards. Fails before the fix: the unfilled-only audit saw
    one member, couldn't confirm the family, and reconcile cleared the slot's
    cycle_id — ordinary generation, no template, no siblings."""
    flagged = _slot("002", cycle_id="gates", regen_reason="too strong")
    unfilled = [flagged]
    # The audit read the FULL listing (001-003), so the family confirmed whole.
    confirmed = {"gates": ["001", "002", "003"]}

    reconcile_cycle_membership(unfilled, confirmed)
    _stamp_cycle_templates(unfilled, {"gates": "A guild gate."})
    assert flagged["cycle_id"] == "gates"
    assert flagged["cycle_template"] == "A guild gate."
    assert "CYCLE MEMBER" in _cycle_note(flagged)

    # Batching: filled member ids absent from the unfilled list are skipped;
    # the lone member still batches under its family.
    batches = group_slots_into_batches(unfilled, confirmed_cycles=confirmed, batch_size=1)
    assert [[s["slot_id"] for s in b] for b in batches] == [["002"]]

    # Sibling pre-seed + the loop's lookup (same condition as generate_set).
    seeded = cg.seed_cycle_siblings(
        confirmed,
        {s["slot_id"] for s in unfilled},
        [_filled_card("001", "Azorius Gate"), _filled_card("003", "Dimir Gate")],
    )
    batch_cycle_ids = {s.get("cycle_id") for s in batches[0]}
    assert batch_cycle_ids == {"gates"}
    siblings_for_batch = list(seeded["gates"])
    assert [c["name"] for c in siblings_for_batch] == ["Azorius Gate", "Dimir Gate"]

    # And the prompt actually renders them as the mirroring block.
    block = format_cycle_siblings(siblings_for_batch)
    assert "SIBLING CYCLE MEMBERS" in block
    assert "Azorius Gate" in block and "Dimir Gate" in block


def test_dropped_slot_guarantee_holds_with_full_listing_audit() -> None:
    """The 6a285a7e guarantee survives the full-listing audit: a flagged slot
    the audit dropped from every family (its filled siblings confirmed without
    it) is generated as ordinary — cycle_id cleared, no template, no note."""
    flagged = _slot("002", cycle_id="gates", cycle_template="A guild gate.")
    unfilled = [flagged]
    # Audit saw 001-003 but confirmed the family WITHOUT the flagged member.
    confirmed = {"gates": ["001", "003"]}

    reconcile_cycle_membership(unfilled, confirmed)
    _stamp_cycle_templates(unfilled, {"gates": "A guild gate."})

    assert flagged["cycle_id"] is None
    assert "cycle_template" not in flagged
    assert _cycle_note(flagged) == ""
    # It batches as ordinary, and the family's sibling list never receives it.
    batches = group_slots_into_batches(unfilled, confirmed_cycles=confirmed, batch_size=1)
    assert [[s["slot_id"] for s in b] for b in batches] == [["002"]]
    assert {s.get("cycle_id") for s in batches[0]} == {None}


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

    clean, best, attempts = _retry_card(
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
    # One provenance entry per retry attempt, none marked success.
    assert [a.attempt_number for a in attempts] == list(range(2, cg.MAX_RETRIES + 1))
    assert all(not a.success for a in attempts)


def test_retry_card_returns_none_best_effort_when_unparsable(tmp_path, monkeypatch) -> None:
    """If no attempt even parses into a Card, best-effort is None and the caller
    must treat the slot as a hard failure (no card to ship)."""

    def fake_retry_single(slot, error_msg, *a, **k):
        return _fake_result({"name": "X"})  # no type_line → unparsable

    monkeypatch.setattr(cg, "_retry_single_card", fake_retry_single)
    monkeypatch.setattr(cg, "_save_generation_log", lambda *a, **k: None)
    progress = GenerationProgress(path=tmp_path / "progress.json")
    slot = {"slot_id": "009", "color": "B", "rarity": "mythic", "card_type": "creature"}

    clean, best, attempts = _retry_card(
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
    # Unparsable retries still record provenance (success=False, no errors stamped
    # from a card that never parsed).
    assert all(not a.success for a in attempts)


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

    clean, best, attempts = _retry_card(
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
    # The winning attempt is recorded as attempt 2, success.
    assert len(attempts) == 1
    assert attempts[0].attempt_number == 2
    assert attempts[0].success is True


# ---------------------------------------------------------------------------
# _retry_single_card threads cycle_siblings into the rebuilt retry prompt
# ---------------------------------------------------------------------------


def _capture_retry_prompt(monkeypatch) -> dict:
    """Stub _retry_single_card's collaborators and capture the rebuilt user
    prompt. Returns a dict that fills in ``user_prompt`` after the call."""
    captured: dict = {}

    def fake_generate_with_tool(*a, user_prompt: str = "", **k):
        captured["user_prompt"] = user_prompt
        return _fake_result(
            {
                "name": "Boros Gate",
                "mana_cost": "",
                "type_line": "Land",
                "oracle_text": "Boros Gate enters the battlefield tapped.\n{T}: Add {R} or {W}.",
                "rarity": "common",
            }
        )

    monkeypatch.setattr(cg, "generate_with_tool", fake_generate_with_tool)
    monkeypatch.setattr(cg, "load_system_prompt", lambda: "SYS")
    monkeypatch.setattr(cg, "build_static_set_context", lambda *a, **k: "CTX")
    monkeypatch.setattr(cg, "_card_gen_log_dir", lambda: None)
    return captured


def test_retry_single_card_threads_cycle_siblings_into_prompt(monkeypatch) -> None:
    """A cycle member retried via the regen path must rebuild its prompt with
    the explicit SIBLING CYCLE MEMBERS block — the same context its original
    batch call had — so the regenerated member keeps the family's parallel
    structure instead of seeing siblings only as generic existing-cards context.

    Without the ``cycle_siblings=`` thread-through this block is silently dropped
    on every retry (card 6a285a87)."""
    captured = _capture_retry_prompt(monkeypatch)
    slot = _slot("002", cycle_id="gates", tweaked_text="WB gate")
    siblings = [
        _sibling_card(
            "Azorius Gate",
            "Azorius Gate enters the battlefield tapped.\n{T}: Add {W} or {U}.",
        )
    ]

    result = cg._retry_single_card(
        slot,
        "overflow",
        [],
        [],
        {"name": "T", "setting": "s"},
        "m",
        2,
        cycle_siblings=siblings,
    )

    assert result is not None
    assert "SIBLING CYCLE MEMBERS" in captured["user_prompt"]
    assert "Azorius Gate enters the battlefield tapped." in captured["user_prompt"]


def test_retry_single_card_non_cycle_has_no_sibling_block(monkeypatch) -> None:
    """A non-cycle retry (no ``cycle_siblings``) leaves the prompt unchanged —
    the new parameter defaults to None so the common path never grows a block."""
    captured = _capture_retry_prompt(monkeypatch)
    slot = _slot("002", tweaked_text="plain creature")

    result = cg._retry_single_card(
        slot,
        "overflow",
        [],
        [],
        {"name": "T", "setting": "s"},
        "m",
        2,
    )

    assert result is not None
    assert "SIBLING CYCLE MEMBERS" not in captured["user_prompt"]


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


# ---------------------------------------------------------------------------
# Provenance: a retried card records the true attempt history, not the first
# attempt's errors stamped attempt_number=1 (card 6a285a95)
# ---------------------------------------------------------------------------


def test_retried_card_records_winning_attempt_provenance(tmp_path, monkeypatch) -> None:
    """A card that trips a regen trigger on attempt 1 and succeeds on retry must
    persist generation_attempts reflecting the TRUE history: attempt 1 (failed,
    its own validation errors) followed by the winning retry (attempt 2, success,
    no errors). Before the fix the saved card carried a single
    attempt_number=1 entry built from the first attempt's stale errors even
    though the retry's clean card is what shipped."""
    clean_card = {
        "name": "Optimus Prime",
        "mana_cost": "{2}{W}",
        "type_line": "Creature — Robot",
        "oracle_text": "Vigilance",
        "power": "4",
        "toughness": "5",
        "rarity": "rare",
    }

    def fake_retry_single(slot, error_msg, *a, **k):
        return _fake_result(clean_card)

    monkeypatch.setattr(cg, "_retry_single_card", fake_retry_single)
    monkeypatch.setattr(cg, "_save_generation_log", lambda *a, **k: None)

    progress = GenerationProgress(path=tmp_path / "progress.json")
    slot = {"slot_id": "009", "color": "G", "rarity": "common", "card_type": "creature"}

    # Attempt 1's raw card overflows the rules box (>300 chars) — a genuine,
    # unfixable regen trigger that drives the regen path into _retry_card.
    saved = cg._process_batch_result(
        raw_cards=[_overflowing_creature("Megatron")],
        slots=[slot],
        existing_cards=[],
        mechanics=[],
        theme=None,
        model="claude-test",
        input_tokens=100,
        output_tokens=200,
        progress=progress,
        set_code="TST",
        set_dir=tmp_path,
    )

    assert len(saved) == 1
    card = saved[0]
    assert card.name == "Optimus Prime"  # the winning retry's card shipped

    attempts = card.generation_attempts
    # Full history: the first (failed) attempt + the winning retry.
    assert [a.attempt_number for a in attempts] == [1, 2]

    first, winner = attempts
    # Attempt 1 failed validation and carries ITS OWN errors.
    assert first.attempt_number == 1
    assert first.success is False
    assert first.validation_errors  # the overflow finding(s)

    # The winning attempt is recorded correctly — NOT attempt_number=1, and it
    # does not inherit the first attempt's error list.
    assert winner.attempt_number == 2
    assert winner.success is True
    assert winner.validation_errors == []
    assert winner.input_tokens == 10  # the retry call's own tokens, not the batch's
    assert winner.output_tokens == 20
