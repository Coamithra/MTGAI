"""Skeleton relabel — the LLM half of Skeleton Generation.

The ``skeleton`` stage first builds a deterministic, balanced *default*
skeleton (``skeleton/generator.generate_skeleton``), then this module rewrites
it to fit the set. Each slot's one-line descriptor — ``render_slot_string``,
e.g. ``"White · common · creature · CMC1 · vanilla"`` — is handed to the LLM,
which rewrites it to honor the theme / constraints / requests (a named mechanic
instead of a bare complexity tier, a colour/type swing the setting demands, a
legendary where one belongs). The rewritten string is stored as the slot's
``tweaked_text``; card generation reads it as the slot's spec, and the Skeleton
tab diffs it against the freshly-rendered default.

Two passes, kept separate (Pass 1 reasons about whole-set distribution; Pass 2
is a cheaper matching problem over the relabeled set):

* **Pass 1 (relabel)** — rewrite every slot's descriptor. Count is invariant
  by construction (N in, N out, reconciled by ``slot_id``); a dropped slot
  keeps its default descriptor.
* **Pass 2 (assign)** — place each ``theme.json`` ``card_request`` onto the
  best-fitting slot; that slot's ``tweaked_text`` becomes the request verbatim
  (the request is the card's spec) and its ``reserved_card`` is stamped.

The structured slot fields stay the deterministic default (so ``reprints`` /
``lands`` read them unchanged); only ``tweaked_text`` + ``reserved_card`` carry
the relabel. Mirrors ``archetype_generator.py`` in shape; templates live in
``mtgai/pipeline/prompts/skeleton_{relabel,assign}_{system,user}.txt``.
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mtgai.generation import temperatures as temps
from mtgai.generation.llm_client import cost_from_result, generate_with_tool, stream_text
from mtgai.generation.skeleton_prompt_blocks import (
    format_archetypes_block,
    format_card_requests,
    format_constraints_block,
    format_mechanics_block,
    format_setting_block,
)
from mtgai.generation.token_budgets import BATCH, HEAVY
from mtgai.runtime import ai_lock
from mtgai.skeleton.generator import render_slot_string

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "pipeline" / "prompts"

# Relabel robustness. Pass 1 emits FREE TEXT, not a JSON tool call: a giant
# structured array is exactly what local models break on (truncation mangles the
# whole array; the repeated `{"slot_id":` scaffolding fights the sampler). Plain
# `--CARD <id>--` blocks degrade gracefully instead — a truncated reply still
# parses line-by-line. We still can't trust one call, so we re-stream the whole
# prompt and retry up to RELABEL_MAX_ATTEMPTS, keeping the most-complete parse.
# A run that covers fewer than the straggler tolerance is KEPT (the missing
# slots fall back to their default descriptor) and flagged `incomplete` so the
# caller can persist + warn; only a run that produced nothing usable at all is a
# hard error (RelabelIncompleteError).
RELABEL_MAX_ATTEMPTS = 3
RELABEL_MIN_COVERAGE = 0.9
# A few dropped slots are fine — they keep their default descriptor without any
# warning. Past this many the run is flagged incomplete (not errored), so it
# scales: max(this, 10% of the set).
RELABEL_MAX_STRAGGLERS = 3
# Pass 1's free-text output is hundreds of near-identical lines (every line
# repeats `·`, a colour word, a rarity word…). A repeat penalty accumulates over
# those mandatory repetitions and corrupts the format, so it's OFF (1.0).
RELABEL_TEXT_REPEAT_PENALTY = 1.0

# Pass 1 streams its reply. We re-scan the buffer for newly-closed `--CARD`
# blocks every this-many new chars (not on every token) so the per-slot UI
# push stays O(slots) rather than O(stream²). A descriptor line is ~50 chars,
# so 80 lands roughly one scan per slot without thrashing.
_LIVE_SCAN_STRIDE = 80

# Pass 2 is just as flaky as Pass 1: a single call routinely places only some
# requests, or places the same request on several slots. So we retry up to this
# many times, accumulating placements across attempts (dedup by request + slot),
# and stop early once every request is placed.
ASSIGN_MAX_ATTEMPTS = 3

# Per-attempt repeat penalty for the assign pass (still a JSON tool call),
# indexed by (attempt - 1) and clamped to the tail. Starts at the prose default
# (1.1) for a little loop protection, then backs OFF on retry since the failure
# that triggers a retry is usually malformed JSON the penalty made worse.
ASSIGN_REPEAT_PENALTIES = [1.1, 1.05, 1.0]


def _repeat_penalty_for(attempt: int) -> float:
    """Assign-pass repeat penalty for a 1-based attempt (clamped to the tail)."""
    i = min(max(attempt, 1), len(ASSIGN_REPEAT_PENALTIES)) - 1
    return ASSIGN_REPEAT_PENALTIES[i]


# A progress hook: called with a short human-readable activity string before
# each attempt so callers can surface "attempt N/M" on the wizard progress
# strip. Engine path wires it to StageEmitter.phase; the refresh endpoint wires
# it to the SSE event bus.
ProgressHook = Callable[[str], None]

# A per-slot hook: called ``(slot_id, descriptor, reserved)`` the moment a
# slot's relabel is final, so callers can stream the card into the UI one at a
# time. ``reserved`` is None for a Pass-1 relabel and the request text for a
# Pass-2 placement (where the slot becomes a reserved card). Both call sites
# wire it to a ``skeleton_slot`` SSE event.
SlotHook = Callable[..., None]

# A reset hook: called once at the start of each relabel attempt so the UI can
# drop the previous (failed/incomplete) attempt's provisional rows before the
# fresh stream starts — the visible half of the "elegant rollback".
ResetHook = Callable[[], None]


def _note(on_progress: ProgressHook | None, message: str) -> None:
    """Fire the progress hook, swallowing any error (progress must never break
    the relabel)."""
    if on_progress is None:
        return
    try:
        on_progress(message)
    except Exception:  # pragma: no cover - progress is best-effort
        logger.debug("relabel progress hook raised", exc_info=True)


def _fire_reset(on_reset: ResetHook | None) -> None:
    """Fire the reset hook, swallowing any error."""
    if on_reset is None:
        return
    try:
        on_reset()
    except Exception:  # pragma: no cover - best-effort
        logger.debug("relabel reset hook raised", exc_info=True)


def _fire_slot(
    on_slot: SlotHook | None, slot_id: str, descriptor: str, reserved: str | None
) -> None:
    """Fire the per-slot hook, swallowing any error (UI streaming must never
    break the relabel)."""
    if on_slot is None:
        return
    try:
        on_slot(slot_id, descriptor, reserved)
    except Exception:  # pragma: no cover - best-effort
        logger.debug("relabel slot hook raised", exc_info=True)


class RelabelIncompleteError(RuntimeError):
    """Relabel produced nothing usable at all (every attempt errored before any
    block parsed). A merely-partial parse is kept + flagged incomplete, not
    raised — only a total failure raises this."""


# ---------------------------------------------------------------------------
# Tool schema (Pass 2 only — Pass 1 is free text, parsed by hand)
# ---------------------------------------------------------------------------

ASSIGN_TOOL_SCHEMA: dict = {
    "name": "submit_request_assignments",
    "description": (
        "Submit the placement of each requested card onto a slot — one entry "
        "per request, naming the requested card and the chosen slot_id."
    ),
    "input_schema": {
        "type": "object",
        "required": ["assignments"],
        "properties": {
            "assignments": {
                "type": "array",
                "description": "One entry per requested card.",
                "items": {
                    "type": "object",
                    "required": ["request", "slot_id"],
                    "properties": {
                        "request": {"type": "string", "description": "The request text, verbatim."},
                        "slot_id": {
                            "type": "string",
                            "description": "The slot this request is placed in.",
                        },
                    },
                },
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Prompt-block formatting
# ---------------------------------------------------------------------------


def _read_template(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


# The set-context block formatters are shared with the phase-0 knob tuner; they
# live in ``skeleton_prompt_blocks`` so the two passes frame the set identically.
_format_setting_block = format_setting_block
_format_mechanics_block = format_mechanics_block
_format_archetypes_block = format_archetypes_block
_format_constraints_block = format_constraints_block
_format_card_requests = format_card_requests


def _render_default_listing(slots: list[dict]) -> str:
    """List each slot as ``slot_id: <default descriptor>`` for the LLM input."""
    return "\n".join(f"{s.get('slot_id')}: {render_slot_string(s)}" for s in slots)


def _format_assign_listing(slots: list[dict], tweaked: dict[str, str]) -> str:
    """List each (already-relabeled) slot for the request-assignment pass."""
    return "\n".join(
        f"{s.get('slot_id')}: {tweaked.get(str(s.get('slot_id')), render_slot_string(s))}"
        for s in slots
    )


# ---------------------------------------------------------------------------
# Pass 1: relabel every slot descriptor
# ---------------------------------------------------------------------------


# A relabel block: a `--CARD <id>--` marker (2+ dashes either side, case-
# insensitive). The id is captured; the descriptor is whatever follows up to the
# next marker. A bare `<id>: descriptor` line is the fallback when the model
# mirrors the input format instead of emitting markers.
_CARD_MARKER = re.compile(r"-{2,}\s*CARD\s+(\S+?)\s*-{2,}", re.IGNORECASE)
_ID_LINE = re.compile(r"^\s*(\d+)\s*[:.)\-]\s+(.+?)\s*$")


def _resolve_slot_id(tok: str, valid_ids: set[str], by_int: dict[int, str]) -> str | None:
    """Reconcile a returned id token to a real slot id — exact, then int-
    normalized so a dropped leading zero (``42`` → ``0042``) still lands."""
    tok = tok.strip()
    if tok in valid_ids:
        return tok
    if tok.isdigit() and int(tok) in by_int:
        return by_int[int(tok)]
    return None


def _parse_relabel_text(text: str, valid_ids: set[str], by_id: dict[str, str]) -> int:
    """Parse a free-text relabel reply into ``by_id`` in place.

    The model returns blocks::

        --CARD 0042--
        White · common · creature · CMC2 · vanilla (notes…)

    We split on the ``--CARD <id>--`` markers and take the first non-empty line
    after each as the descriptor. If the model emitted no markers at all we fall
    back to bare ``<id>: descriptor`` lines (the input format it may mirror).
    Only real, not-yet-filled ids with non-empty text are accepted, so preamble
    / garbage / duplicates are ignored. Returns how many NEW descriptors landed.
    """
    text = text or ""
    by_int = {int(s): s for s in valid_ids if s.isdigit()}
    added = 0

    markers = list(_CARD_MARKER.finditer(text))
    if markers:
        for i, m in enumerate(markers):
            end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
            block = text[m.end() : end]
            desc = next((ln.strip() for ln in block.splitlines() if ln.strip()), "")
            sid = _resolve_slot_id(m.group(1), valid_ids, by_int)
            if sid and desc and sid not in by_id:
                by_id[sid] = desc
                added += 1
        return added

    # Fallback: no markers — accept bare `<id>: descriptor` lines.
    for line in text.splitlines():
        mm = _ID_LINE.match(line)
        if not mm:
            continue
        sid = _resolve_slot_id(mm.group(1), valid_ids, by_int)
        desc = mm.group(2).strip()
        if sid and desc and sid not in by_id:
            by_id[sid] = desc
            added += 1
    return added


def _emit_new_blocks(
    text: str,
    valid_ids: set[str],
    by_int: dict[int, str],
    emitted: set[str],
    on_slot: SlotHook | None,
) -> None:
    """Push every *closed* ``--CARD`` block in ``text`` to ``on_slot`` once.

    A block has closed (its descriptor is final) only once a later marker
    appears, so the trailing block is always skipped here — the end-of-stream
    flush in :func:`relabel_slots` handles it. ``emitted`` tracks which slot ids
    have already been pushed so a re-scan of the growing buffer never
    double-fires. No-op when ``on_slot`` is None."""
    if on_slot is None:
        return
    markers = list(_CARD_MARKER.finditer(text))
    for i in range(len(markers) - 1):  # skip the last (still-open) block
        m = markers[i]
        sid = _resolve_slot_id(m.group(1), valid_ids, by_int)
        if not sid or sid in emitted:
            continue
        block = text[m.end() : markers[i + 1].start()]
        desc = next((ln.strip() for ln in block.splitlines() if ln.strip()), "")
        if desc:
            emitted.add(sid)
            _fire_slot(on_slot, sid, desc, None)


def _merge_text_responses(responses: list[dict], model: str) -> dict:
    """Collapse per-attempt text responses into one, summing token usage.

    ``relabel_skeleton`` reads token counts + ``cost_from_result`` off the
    returned dict, so it must carry summed ``input_tokens`` / ``output_tokens``
    and the model id (the parsed descriptors live in ``tweaked``, not here)."""
    return {
        "input_tokens": sum(r.get("input_tokens", 0) for r in responses),
        "output_tokens": sum(r.get("output_tokens", 0) for r in responses),
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "stop_reason": responses[-1].get("stop_reason", "") if responses else "",
        "model": responses[-1].get("model", model) if responses else model,
    }


def relabel_slots(
    *,
    slots: list[dict],
    theme: dict,
    approved: list[dict],
    archetypes: list[dict],
    set_name: str,
    set_size: int,
    model: str,
    log_dir: Path | None = None,
    on_progress: ProgressHook | None = None,
    on_slot: SlotHook | None = None,
    on_reset: ResetHook | None = None,
) -> tuple[dict[str, str], dict]:
    """Run Pass 1. Returns (tweaked, response) where tweaked maps every
    slot_id to its rewritten descriptor, and ``response`` carries summed token
    usage plus ``relabeled_count`` and an ``incomplete`` flag.

    The model emits FREE TEXT — ``--CARD <id>--`` blocks, not a JSON tool call —
    streamed back token-by-token. We parse each block the moment it closes and
    push it to ``on_slot`` so the wizard fills in cards one at a time; a
    malformed/truncated reply degrades to "fewer parsed blocks" instead of
    "unparseable array". Robust to partial responses: each attempt re-streams the
    whole prompt (firing ``on_reset`` first so the UI drops the prior attempt's
    provisional rows), and we keep the most-complete attempt across
    ``RELABEL_MAX_ATTEMPTS``.

    Failure handling (the "keep partial, mark incomplete" contract): a hard
    error is raised **only** when nothing usable came back at all (every attempt
    errored before producing any parseable block). Otherwise the best partial
    parse is kept — slots the model never covered fall back to their default
    descriptor — and ``response["incomplete"]`` is set True when coverage fell
    below the straggler tolerance, so the caller can persist progress and flag
    it rather than discard it.

    ``on_progress`` surfaces "attempt N/M" on the progress strip; ``on_slot`` /
    ``on_reset`` drive the live per-slot streaming. All three are optional and
    best-effort (a raising hook never breaks the relabel).
    """
    system_prompt = _read_template("skeleton_relabel_system.txt").format(
        set_name=set_name or "(unnamed set)",
        set_size=set_size,
        setting_block=_format_setting_block(theme),
        mechanics_block=_format_mechanics_block(approved),
        archetypes_block=_format_archetypes_block(archetypes),
        constraints_block=_format_constraints_block(
            theme.get("constraints") or theme.get("special_constraints") or []
        ),
    )
    user_prompt = _read_template("skeleton_relabel_user.txt").format(
        slot_count=len(slots),
        default_listing=_render_default_listing(slots),
    )

    valid_ids = {str(s.get("slot_id")) for s in slots}
    by_int = {int(s): s for s in valid_ids if s.isdigit()}
    tolerable = max(RELABEL_MAX_STRAGGLERS, math.ceil(len(slots) * (1.0 - RELABEL_MIN_COVERAGE)))
    best: dict[str, str] = {}
    responses: list[dict] = []
    last_error: Exception | None = None

    for attempt in range(1, RELABEL_MAX_ATTEMPTS + 1):
        # Honor a Cancel between attempts (an in-flight stream can't be cleanly
        # interrupted) — keep the best partial parse so far.
        if ai_lock.is_cancelled():
            logger.warning("Skeleton relabel CANCELLED by user before attempt %d", attempt)
            break
        suffix = "" if attempt == 1 else " (retrying — last response was incomplete)"
        _note(
            on_progress,
            f"Relabeling skeleton — attempt {attempt}/{RELABEL_MAX_ATTEMPTS}{suffix}",
        )
        # Each attempt re-streams the whole prompt — tell the UI to drop the
        # previous attempt's provisional rows before fresh slots arrive.
        _fire_reset(on_reset)

        buf = ""
        response: dict | None = None
        emitted: set[str] = set()  # slot ids already pushed to the UI this attempt
        scanned_len = 0
        try:
            for ev in stream_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                temperature=temps.CREATIVE,
                max_tokens=HEAVY,
                log_dir=log_dir,
                repeat_penalty=RELABEL_TEXT_REPEAT_PENALTY,
                name="relabel_skeleton",
            ):
                if ev.get("type") == "text_delta":
                    buf += ev.get("text", "")
                    if on_slot is not None and len(buf) - scanned_len >= _LIVE_SCAN_STRIDE:
                        scanned_len = len(buf)
                        _emit_new_blocks(buf, valid_ids, by_int, emitted, on_slot)
                elif ev.get("type") == "complete":
                    response = ev
        except Exception as exc:  # transport / context overflow (possibly mid-stream)
            last_error = exc
            logger.warning("Relabel attempt %d/%d failed: %s", attempt, RELABEL_MAX_ATTEMPTS, exc)
            # Fall through: salvage whatever streamed in before the failure.

        # Authoritative parse of the full buffer (covers the trailing block the
        # live scan deliberately leaves open, and anything the stride skipped).
        by_id: dict[str, str] = {}
        _parse_relabel_text(buf, valid_ids, by_id)
        for sid, desc in by_id.items():
            if sid not in emitted:
                emitted.add(sid)
                _fire_slot(on_slot, sid, desc, None)
        if response is not None:
            responses.append(response)
        logger.info(
            "Relabel attempt %d/%d: parsed %d/%d slots (stop=%s)",
            attempt,
            RELABEL_MAX_ATTEMPTS,
            len(by_id),
            len(slots),
            response.get("stop_reason") if response else "error",
        )
        if len(by_id) > len(best):
            best = by_id
        if len(slots) - len(best) <= tolerable:
            break  # complete enough — stop retrying

    if not best and not responses and not ai_lock.is_cancelled():
        # Nothing usable came back at all (every attempt raised before producing
        # any parseable block). This is the only hard failure — but a user Cancel
        # before any output isn't one: fall through to the all-default tweaked map
        # (each slot keeps its default descriptor), flagged incomplete below.
        raise RelabelIncompleteError(
            f"Relabel produced no usable output after {RELABEL_MAX_ATTEMPTS} attempts"
            + (f": {last_error}" if last_error is not None else "")
        ) from last_error

    missing = len(slots) - len(best)
    incomplete = missing > tolerable
    if incomplete:
        logger.warning(
            "Relabel covered only %d/%d slots after %d attempts — keeping partial, "
            "flagged incomplete (caller persists + warns)",
            len(best),
            len(slots),
            RELABEL_MAX_ATTEMPTS,
        )
    elif missing:
        logger.warning("Relabel kept %d/%d slots on their defaults", missing, len(slots))

    tweaked = {
        str(s.get("slot_id")): best.get(str(s.get("slot_id"))) or render_slot_string(s)
        for s in slots
    }
    response_out = _merge_text_responses(responses, model)
    response_out["relabeled_count"] = len(best)
    response_out["incomplete"] = incomplete
    return tweaked, response_out


# ---------------------------------------------------------------------------
# Pass 2: assign card requests to slots
# ---------------------------------------------------------------------------


def _normalize_request(text: str) -> str:
    """Canonical form for matching a returned ``request`` against the known
    requests — lowercased, whitespace-collapsed."""
    return " ".join(str(text or "").lower().split())


def _match_request(req: str, expected: dict[str, str], placed: set[str]) -> str | None:
    """Resolve a returned request string to an *unplaced* known request key.

    ``expected`` maps normalized-text → original-text. Returns the matching
    normalized key (still unplaced), or None if the model named a request we
    don't recognise or one already placed. Exact normalized match first, then a
    lenient substring match (the model sometimes echoes a prefix/paraphrase).
    """
    norm = _normalize_request(req)
    if not norm:
        return None
    if norm in expected and norm not in placed:
        return norm
    for key in expected:
        if key in placed:
            continue
        if key in norm or norm in key:
            return key
    return None


def _merge_assign_responses(responses: list[dict], assignments: list[dict], model: str) -> dict:
    """Collapse per-attempt assign responses into one, summing token usage so
    ``relabel_skeleton`` can read counts + ``cost_from_result`` off it."""
    return {
        "result": {"assignments": assignments},
        "input_tokens": sum(r.get("input_tokens", 0) for r in responses),
        "output_tokens": sum(r.get("output_tokens", 0) for r in responses),
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "stop_reason": responses[-1].get("stop_reason", "") if responses else "",
        "model": responses[-1].get("model", model) if responses else model,
    }


def assign_requests(
    *,
    slots: list[dict],
    tweaked: dict[str, str],
    card_requests: list[Any],
    model: str,
    log_dir: Path | None = None,
    on_progress: ProgressHook | None = None,
    on_slot: SlotHook | None = None,
) -> tuple[dict[str, str], dict[str, str], dict | None]:
    """Run Pass 2. Returns (tweaked, reserved, response): the (possibly updated)
    per-slot descriptors, a slot_id→request map for placed cards, and the merged
    response (None when there are no requests, so no LLM call).

    Each placement is validated and deduplicated so the same request can't land
    on multiple slots (the duplicate-card bug) and no slot takes two requests:
    a returned assignment is kept only if its slot is real + still free and its
    request matches a known, not-yet-placed request. Like Pass 1 this is flaky,
    so we retry up to ``ASSIGN_MAX_ATTEMPTS``, accumulating placements across
    attempts and stopping once every request is placed.

    ``on_progress`` (optional) surfaces "attempt N/M" on the progress strip;
    ``on_slot`` (optional) fires ``(slot_id, request_text, request_text)`` as
    each request is placed, so the wizard repaints that slot as a gold reserved
    card live (the relabel stream already drew its Pass-1 descriptor).
    """
    reqs = [r for r in (card_requests or []) if (r.get("text") if isinstance(r, dict) else r)]
    reserved: dict[str, str] = {}
    if not reqs:
        return tweaked, reserved, None

    # Map each request's normalized form → its original text (the reserved
    # value). A normalized collision (two requests that canonicalize the same)
    # collapses to one entry — harmless, they'd be indistinguishable anyway.
    expected: dict[str, str] = {}
    for r in reqs:
        original = (r.get("text") if isinstance(r, dict) else r) or ""
        expected.setdefault(_normalize_request(original), str(original).strip())

    system_prompt = _read_template("skeleton_assign_system.txt")
    user_prompt = _read_template("skeleton_assign_user.txt").format(
        request_count=len(reqs),
        slot_count=len(slots),
        card_requests=_format_card_requests(reqs),
        slot_listing=_format_assign_listing(slots, tweaked),
    )

    valid = set(tweaked)
    placed: set[str] = set()  # normalized request keys already placed
    kept: list[dict] = []  # accepted assignments across all attempts (for logging/merge)
    responses: list[dict] = []

    for attempt in range(1, ASSIGN_MAX_ATTEMPTS + 1):
        if len(placed) >= len(expected):
            break
        # Honor a Cancel between attempts — keep whatever placed so far.
        if ai_lock.is_cancelled():
            logger.warning("Skeleton request-assign CANCELLED by user before attempt %d", attempt)
            break
        suffix = "" if attempt == 1 else " (retrying — requests still unplaced)"
        _note(
            on_progress,
            f"Placing requested cards — attempt {attempt}/{ASSIGN_MAX_ATTEMPTS}{suffix}",
        )
        try:
            response = generate_with_tool(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tool_schema=ASSIGN_TOOL_SCHEMA,
                model=model,
                temperature=temps.CREATIVE,
                max_tokens=BATCH,
                log_dir=log_dir,
                repeat_penalty=_repeat_penalty_for(attempt),
            )
        except Exception as exc:
            logger.warning("Assign attempt %d/%d failed: %s", attempt, ASSIGN_MAX_ATTEMPTS, exc)
            continue
        responses.append(response)
        for a in response.get("result", {}).get("assignments") or []:
            if not isinstance(a, dict):
                continue
            sid = str(a.get("slot_id") or "").strip()
            req = str(a.get("request") or "").strip()
            if sid not in valid or sid in reserved:
                logger.warning("Assignment skipped (bad/taken slot=%r, request=%r)", sid, req[:40])
                continue
            key = _match_request(req, expected, placed)
            if key is None:
                logger.warning("Assignment skipped (unknown/duplicate request=%r)", req[:60])
                continue
            # The request text IS the slot's spec — it's the richest description
            # of the card we have. The card generator designs from it; we don't
            # distill it to a one-line descriptor (that only lost information).
            reserved[sid] = expected[key]
            tweaked[sid] = expected[key]
            placed.add(key)
            kept.append({"request": expected[key], "slot_id": sid})
            _fire_slot(on_slot, sid, expected[key], expected[key])

    if not responses:
        logger.warning("Assign produced no usable output after %d attempts", ASSIGN_MAX_ATTEMPTS)
        return tweaked, reserved, None
    if len(placed) < len(expected):
        logger.warning(
            "Placed %d/%d card requests; %d unplaced after %d attempts",
            len(placed),
            len(expected),
            len(expected) - len(placed),
            ASSIGN_MAX_ATTEMPTS,
        )
    return tweaked, reserved, _merge_assign_responses(responses, kept, model)


# ---------------------------------------------------------------------------
# Orchestrator — called by the skeleton stage + the tab's refresh endpoint
# ---------------------------------------------------------------------------


def relabel_skeleton(
    *,
    slots: list[dict],
    theme: dict | None = None,
    approved: list[dict] | None = None,
    archetypes: list[dict] | None = None,
    on_progress: ProgressHook | None = None,
    on_slot: SlotHook | None = None,
    on_reset: ResetHook | None = None,
) -> dict:
    """Relabel a (structured) default skeleton to fit the active project's set.

    Reads ``theme.json`` + ``mechanics/approved.json`` + ``archetypes.json``
    from the active project unless passed in, runs both passes, and returns::

        {
            "updates": { slot_id: {"tweaked_text": str, "reserved_card": str|None} },
            "model_id": str,
            "input_tokens": int, "output_tokens": int, "cost_usd": float,
            "incomplete": bool, "relabeled": int,
        }

    The caller applies the updates onto its skeleton slots. ``updates`` covers
    every input slot (``tweaked_text`` always set, ``reserved_card`` only for
    placed requests). ``incomplete`` is True when Pass 1 fell below coverage
    tolerance — the caller still persists the (partial) updates but flags the
    skeleton so the tab can warn.

    ``on_slot`` / ``on_reset`` (optional) drive live per-slot streaming into the
    wizard; ``on_progress`` drives the "attempt N/M" progress line. All are
    threaded into both passes.
    """
    import json

    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    settings = project.settings
    model_id = settings.get_llm_model_id("skeleton")
    asset_dir = set_artifact_dir()
    log_dir = asset_dir / "skeleton" / "logs"

    if not slots:
        raise RuntimeError("relabel_skeleton called with no slots")

    if theme is None:
        theme_path = asset_dir / "theme.json"
        theme = json.loads(theme_path.read_text(encoding="utf-8")) if theme_path.exists() else {}
    assert theme is not None

    if approved is None:
        approved_path = asset_dir / "mechanics" / "approved.json"
        loaded = (
            json.loads(approved_path.read_text(encoding="utf-8")) if approved_path.exists() else []
        )
        approved = loaded if isinstance(loaded, list) else []

    if archetypes is None:
        from mtgai.generation.archetype_generator import load_archetypes

        archetypes = load_archetypes(asset_dir)

    sp = settings.set_params
    logger.info(
        "Relabeling skeleton (model=%s, slots=%d, mechanics=%d, requests=%d)",
        model_id,
        len(slots),
        len(approved),
        len(theme.get("card_requests") or []),
    )

    tweaked, relabel_resp = relabel_slots(
        slots=slots,
        theme=theme,
        approved=approved,
        archetypes=archetypes,
        set_name=sp.set_name or project.set_code or "Custom Set",
        set_size=sp.set_size or len(slots),
        model=model_id,
        log_dir=log_dir,
        on_progress=on_progress,
        on_slot=on_slot,
        on_reset=on_reset,
    )
    tweaked, reserved, assign_resp = assign_requests(
        slots=slots,
        tweaked=tweaked,
        card_requests=theme.get("card_requests") or [],
        model=model_id,
        log_dir=log_dir,
        on_progress=on_progress,
        on_slot=on_slot,
    )

    input_tokens = relabel_resp.get("input_tokens", 0)
    output_tokens = relabel_resp.get("output_tokens", 0)
    cost = cost_from_result(relabel_resp)
    if assign_resp is not None:
        input_tokens += assign_resp.get("input_tokens", 0)
        output_tokens += assign_resp.get("output_tokens", 0)
        cost += cost_from_result(assign_resp)

    updates = {
        sid: {"tweaked_text": text, "reserved_card": reserved.get(sid)}
        for sid, text in tweaked.items()
    }
    requested = len(
        [
            r
            for r in (theme.get("card_requests") or [])
            if (r.get("text") if isinstance(r, dict) else r)
        ]
    )
    return {
        "updates": updates,
        "requests_total": requested,
        "requests_placed": len(reserved),
        # Base id for provenance/display (model_id is the effective ctx twin).
        "model_id": settings.get_assigned_model_id("skeleton"),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost,
        "incomplete": bool(relabel_resp.get("incomplete")),
        "relabeled": relabel_resp.get("relabeled_count", 0),
    }
