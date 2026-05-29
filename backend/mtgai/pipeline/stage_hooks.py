"""Shared SSE stream hooks for the streaming pipeline stages.

The three streaming stages — ``mechanics``, ``skeleton``, ``card_gen`` — each
push live progress to their wizard tab over the SSE bus via per-event hook
callbacks. Those callbacks were written **twice**: once on the engine path
(:mod:`mtgai.pipeline.stages` runners, via :meth:`StageEmitter.event`) and once
on the manual-refresh path (:mod:`mtgai.pipeline.server` endpoints, via
``event_bus.publish``). The two copies could silently drift in payload shape —
and the tab merges streamed items into a list it eventually repaints from
``/state``, so any drift surfaces as layout flicker.

This module is the single source of those hooks. Both paths construct a real
:class:`~mtgai.pipeline.events.StageEmitter` (the engine already has one; the
refresh endpoints build one via ``server._refresh_emitter(stage_id)``) and call
the same builder here, so the event payloads are identical by construction.
The genuine differences between the paths (position remapping, whether the reset
event fires, engine-only phase telemetry) are explicit parameters, not forks.

``card_tile_dict`` lives here (rather than in :mod:`stages`) because the card_gen
hook needs it and ``stages`` imports the builders from this module — keeping it
here breaks the import cycle. ``stages`` no longer references it directly.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from mtgai.io.atomic import atomic_write_text

if TYPE_CHECKING:
    from mtgai.pipeline.events import StageEmitter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Card tile shape (card_gen)
# ---------------------------------------------------------------------------


def card_tile_dict(card: object, slots_by_id: dict[str, dict] | None = None) -> dict:
    """Render a Card (or its disk-JSON dict) into the Card-Generation tab's
    tile shape — the same payload :func:`server.wizard_card_gen_state` emits.

    Single source of the tile shape so the engine's per-card SSE stream and
    the manual ``/refresh`` endpoint stay byte-identical to the canonical
    ``/state`` response — the tab merges streamed cards into a list that
    eventually gets repainted from ``/state``, so any drift would surface as
    layout flicker.

    Accepts either a ``Card`` model instance (calls ``model_dump(mode="json")``
    so enums become strings) or a plain dict already loaded from disk.

    ``slots_by_id`` (optional) is a ``{slot_id: slot_dict}`` map from the
    project's ``skeleton.json``. When provided, the tile gains a ``slot_text``
    field carrying the final relabeled descriptor for the card's slot — the
    same string :func:`mtgai.generation.prompts.format_slot_specs` uses
    (``tweaked_text`` when present, else :func:`render_slot_string` on the
    default seeds). Reserved-card slots already land their request text into
    ``tweaked_text`` via the relabel's Pass 2, so this covers them too.
    Reprint slots don't appear on the card-gen tab, so they're a no-op here.
    """
    if hasattr(card, "model_dump"):
        c: dict = card.model_dump(mode="json")  # type: ignore[attr-defined]
    elif isinstance(card, dict):
        c = card
    else:
        raise TypeError(f"card_tile_dict expects Card or dict, got {type(card).__name__}")

    slot_text = ""
    if slots_by_id:
        slot = slots_by_id.get(c.get("collector_number") or "")
        if slot:
            from mtgai.skeleton.generator import render_slot_string

            slot_text = (slot.get("tweaked_text") or "").strip() or render_slot_string(slot)

    return {
        "name": c.get("name") or "",
        "mana_cost": c.get("mana_cost") or "",
        "type_line": c.get("type_line") or "",
        "oracle_text": c.get("oracle_text") or "",
        "flavor_text": c.get("flavor_text") or "",
        "rarity": c.get("rarity") or "common",
        "power": c.get("power"),
        "toughness": c.get("toughness"),
        "loyalty": c.get("loyalty"),
        "colors": c.get("colors") or [],
        "collector_number": c.get("collector_number") or "",
        "status": c.get("status") or "",
        "slot_text": slot_text,
    }


def slots_by_id_from_skeleton(skeleton_path: Path) -> dict[str, dict]:
    """Build the ``{slot_id: slot_dict}`` map card tiles look up for ``slot_text``.

    Reads ``skeleton.json`` and indexes its slots by id. A missing or malformed
    file yields an empty map — the lookup is a strict enhancement (the tile's
    ``slot_text`` just stays ``""``), never a blocker, so callers that run
    without a skeleton (tests, edge runs) still work.
    """
    try:
        if not skeleton_path.exists():
            return {}
        data = json.loads(skeleton_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read %s for slot_text lookup", skeleton_path)
        return {}
    raw = data.get("slots") if isinstance(data, dict) else None
    return {s["slot_id"]: s for s in (raw or []) if isinstance(s, dict) and s.get("slot_id")}


# ---------------------------------------------------------------------------
# Mechanics stream hooks
# ---------------------------------------------------------------------------


@dataclass
class MechanicStreamHooks:
    """The three ``generate_mechanic_candidates`` streaming callbacks."""

    on_reset: Callable[[], None]
    on_draft: Callable[[int, dict], None]
    on_finalized: Callable[[int, dict, str], None]


def build_mechanic_hooks(
    emitter: StageEmitter,
    *,
    pool: int,
    merged: list[dict],
    candidates_path: Path,
    known_keywords: set[str],
    slot_for: Callable[[int], int] | None = None,
    fire_reset: bool = True,
    emit_phase: bool = False,
) -> MechanicStreamHooks:
    """Build the mechanic candidate streaming hooks shared by the engine
    (``run_mechanics``) and the refresh endpoints (refresh-card / refresh-all).

    Owns the canonical ``mechanic_candidates_reset`` / ``mechanic_candidate_drafted``
    / ``mechanic_candidate_finalized`` payloads, the ``_ai_generated`` provenance
    tag, the keyword-collision check, and the incremental persist of ``merged``
    to ``candidates.json`` (so a mid-run browser F5 reads a snapshot matching the
    last event the client received).

    The path-specific bits are parameters, not forks:

    * ``slot_for(position)`` maps the generator's 1-based loop ``position`` to a
      0-based slot index — identity (``position - 1``) on the engine, a constant
      for refresh-card, ``_slot_for`` for refresh-all. The emitted ``position``
      is ``slot + 1`` so the tab updates the right row.
    * ``fire_reset`` gates the reset event (the full-pool runs reset the strip; a
      targeted refresh leaves untouched rows alone). refresh-card simply doesn't
      wire ``on_reset`` at all.
    * ``emit_phase`` adds the engine's per-candidate progress-strip phase ticks.
      The refresh path drives the strip with an indeterminate ``showBusy`` bar
      client-side, so it leaves phase off.
    """
    slot_for = slot_for or (lambda position: position - 1)

    def on_reset() -> None:
        if not fire_reset:
            return
        emitter.event("mechanic_candidates_reset", target=pool)
        if emit_phase:
            emitter.phase("running", f"Generating candidate 1/{pool}")

    def on_draft(position: int, draft: dict) -> None:
        tagged = dict(draft)
        tagged["_ai_generated"] = True
        slot = slot_for(position)
        emitter.event(
            "mechanic_candidate_drafted",
            position=slot + 1,
            target=pool,
            candidate=tagged,
        )
        if emit_phase:
            emitter.phase("running", f"Reviewing candidate {position}/{pool}")

    def on_finalized(position: int, mech: dict, review_notes: str) -> None:
        name = (mech.get("name") or "").strip()
        collision = name if name and name.lower() in known_keywords else None
        tagged = dict(mech)
        tagged["_ai_generated"] = True
        slot = slot_for(position)
        # Persist incrementally BEFORE publishing the event so a mid-event F5
        # reads a candidates.json that matches the event the client just got.
        if 0 <= slot < pool:
            merged[slot] = tagged
            atomic_write_text(
                candidates_path,
                json.dumps(merged, indent=2, ensure_ascii=False),
            )
        emitter.event(
            "mechanic_candidate_finalized",
            position=slot + 1,
            target=pool,
            candidate=tagged,
            review_notes=review_notes or "",
            collision_with=collision,
        )
        if emit_phase and position < pool:
            emitter.phase("running", f"Generating candidate {position + 1}/{pool}")

    return MechanicStreamHooks(on_reset, on_draft, on_finalized)


# ---------------------------------------------------------------------------
# Skeleton relabel stream hooks
# ---------------------------------------------------------------------------


@dataclass
class SkeletonStreamHooks:
    """The ``relabel_skeleton`` per-slot streaming callbacks."""

    on_slot: Callable[..., None]
    on_reset: Callable[[], None]


def build_skeleton_hooks(emitter: StageEmitter) -> SkeletonStreamHooks:
    """Build the skeleton relabel streaming hooks shared by the engine
    (``run_skeleton``) and the refresh endpoint.

    ``on_slot(slot_id, tweaked_text, reserved_card=None)`` streams one relabeled
    or placed slot; ``on_reset()`` clears the tab's provisional rows at the start
    of each attempt. Pair with :func:`emit_skeleton_done` for the terminal event.
    """

    def on_slot(slot_id: str, tweaked_text: str, reserved_card: str | None = None) -> None:
        emitter.event(
            "skeleton_slot",
            slot_id=slot_id,
            tweaked_text=tweaked_text,
            reserved_card=reserved_card,
        )

    def on_reset() -> None:
        emitter.event("skeleton_relabel_reset")

    return SkeletonStreamHooks(on_slot, on_reset)


def emit_skeleton_done(emitter: StageEmitter, *, incomplete: bool, relabeled: int) -> None:
    """Terminal ``skeleton_relabel_done`` event so the tab settles its live view
    (drops the streaming dim, shows the incomplete warning) without waiting for
    the stage to fully complete."""
    emitter.event("skeleton_relabel_done", incomplete=incomplete, relabeled=relabeled)


# ---------------------------------------------------------------------------
# Card generation stream hooks
# ---------------------------------------------------------------------------


@dataclass
class CardGenStreamHooks:
    """The ``generate_set`` per-card streaming callback."""

    on_card_saved: Callable[[object], None]


def build_card_gen_hooks(
    emitter: StageEmitter, *, slots_by_id: dict[str, dict]
) -> CardGenStreamHooks:
    """Build the card-gen streaming hook shared by the engine (``run_card_gen``)
    and the refresh endpoint.

    ``on_card_saved(card)`` streams one freshly-saved card as the canonical
    ``card_gen_card`` tile (via :func:`card_tile_dict`) so the grid fills in live.
    The reset event is *not* part of this — see :func:`emit_card_gen_reset`.
    """

    def on_card_saved(card: object) -> None:
        emitter.event("card_gen_card", card=card_tile_dict(card, slots_by_id))

    return CardGenStreamHooks(on_card_saved)


def emit_card_gen_reset(emitter: StageEmitter) -> None:
    """Tell the tab to drop its local card list before a from-scratch refresh
    streams in (the ``cards/`` dir was just wiped).

    The engine path deliberately does **not** call this: a first run already
    starts on an empty grid, and a resume must keep existing cards visible.
    Only the refresh endpoint (which wiped ``cards/``) fires it.
    """
    emitter.event("card_gen_reset")
