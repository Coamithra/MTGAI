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

from mtgai.generation.llm_client import cost_from_result, generate_text, generate_with_tool
from mtgai.skeleton.generator import render_slot_string

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "pipeline" / "prompts"

# Relabel robustness. Pass 1 emits FREE TEXT, not a JSON tool call: a giant
# structured array is exactly what local models break on (truncation mangles the
# whole array; the repeated `{"slot_id":` scaffolding fights the sampler). Plain
# `--CARD <id>--` blocks degrade gracefully instead — a truncated reply still
# parses line-by-line. We still can't trust one call, so we resend the whole
# prompt and retry up to RELABEL_MAX_ATTEMPTS, keep the most-complete parse, and
# raise past the straggler tolerance rather than ship a near-default skeleton.
RELABEL_MAX_ATTEMPTS = 3
RELABEL_MIN_COVERAGE = 0.9
# A few dropped slots are fine — they keep their default descriptor. The hard
# error only fires past this many, so it scales: max(this, 10% of the set).
RELABEL_MAX_STRAGGLERS = 3
# Pass 1's free-text output is hundreds of near-identical lines (every line
# repeats `·`, a colour word, a rarity word…). A repeat penalty accumulates over
# those mandatory repetitions and corrupts the format, so it's OFF (1.0).
RELABEL_TEXT_REPEAT_PENALTY = 1.0

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


def _note(on_progress: ProgressHook | None, message: str) -> None:
    """Fire the progress hook, swallowing any error (progress must never break
    the relabel)."""
    if on_progress is None:
        return
    try:
        on_progress(message)
    except Exception:  # pragma: no cover - progress is best-effort
        logger.debug("relabel progress hook raised", exc_info=True)


class RelabelIncompleteError(RuntimeError):
    """Relabel returned descriptors for too few slots, even after retries."""


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


def _format_setting_block(theme: dict) -> str:
    one_liner = (theme.get("theme") or "").strip()
    prose = (theme.get("flavor_description") or theme.get("setting") or "").strip()
    parts = [p for p in (one_liner, prose) if p]
    return "\n\n".join(parts) if parts else "(no setting provided)"


def _format_mechanics_block(approved: list[Any]) -> str:
    """Render approved mechanics with their effect, framed as floors/caps."""
    if not approved:
        return "(no named mechanics — relabel around the set's flavor only)"
    lines: list[str] = []
    for mech in approved:
        if not isinstance(mech, dict):
            continue
        name = mech.get("name") or "?"
        colors = mech.get("colors") or []
        colors_str = "".join(str(c) for c in colors) if colors else "any"
        lines.append(f"- {name} ({colors_str})")
        reminder = (mech.get("reminder_text") or mech.get("rules_text") or "").strip()
        if reminder:
            lines.append(f"    {reminder}")
    return "\n".join(lines) if lines else "(no named mechanics)"


def _format_archetypes_block(archetypes: list[Any]) -> str:
    if not archetypes:
        return "(no archetypes provided)"
    lines: list[str] = []
    for arch in archetypes:
        if not isinstance(arch, dict):
            continue
        pair = arch.get("color_pair") or "?"
        name = (arch.get("name") or "").strip()
        desc = (arch.get("description") or "").strip()
        lines.append(f"- {pair} {name}: {desc}")
    return "\n".join(lines) if lines else "(no archetypes provided)"


def _format_constraints_block(constraints: list[Any]) -> str:
    if not constraints:
        return "(no special constraints — keep the default's standard shape)"
    lines: list[str] = []
    for c in constraints:
        text = c.get("text") if isinstance(c, dict) else c
        if text:
            lines.append(f"- {text}")
    return "\n".join(lines) if lines else "(no special constraints)"


def _format_card_requests(requests: list[Any]) -> str:
    lines: list[str] = []
    for i, req in enumerate(requests, 1):
        text = req.get("text") if isinstance(req, dict) else req
        if text:
            lines.append(f"{i}. {text}")
    return "\n".join(lines) if lines else "(none)"


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
) -> tuple[dict[str, str], dict]:
    """Run Pass 1. Returns (tweaked, response) where tweaked maps every
    slot_id to its rewritten descriptor.

    The model emits FREE TEXT — ``--CARD <id>--`` blocks, not a JSON tool call —
    which we parse ourselves; a malformed/truncated reply degrades to "fewer
    parsed blocks" instead of "unparseable array". Robust to partial responses:
    each attempt resends the whole prompt; if it parses to fewer than the
    straggler tolerance allows, we retry up to ``RELABEL_MAX_ATTEMPTS`` and keep
    the most-complete attempt. If even the best is too incomplete we raise
    ``RelabelIncompleteError`` rather than silently shipping mostly-default slots.

    ``on_progress`` (optional) is called with an "attempt N/M" string before
    each attempt so the wizard progress strip can show which try is running.
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
    tolerable = max(RELABEL_MAX_STRAGGLERS, math.ceil(len(slots) * (1.0 - RELABEL_MIN_COVERAGE)))
    best: dict[str, str] = {}
    responses: list[dict] = []
    last_error: Exception | None = None

    for attempt in range(1, RELABEL_MAX_ATTEMPTS + 1):
        suffix = "" if attempt == 1 else " (retrying — last response was incomplete)"
        _note(
            on_progress,
            f"Relabeling skeleton — attempt {attempt}/{RELABEL_MAX_ATTEMPTS}{suffix}",
        )
        try:
            response = generate_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                temperature=1.0,
                max_tokens=16384,
                log_dir=log_dir,
                repeat_penalty=RELABEL_TEXT_REPEAT_PENALTY,
                name="relabel_skeleton",
            )
        except Exception as exc:  # transport / context overflow
            last_error = exc
            logger.warning(
                "Relabel attempt %d/%d failed: %s", attempt, RELABEL_MAX_ATTEMPTS, exc
            )
            continue
        responses.append(response)
        by_id: dict[str, str] = {}
        _parse_relabel_text(response.get("text", ""), valid_ids, by_id)
        logger.info(
            "Relabel attempt %d/%d: parsed %d/%d slots (stop=%s)",
            attempt,
            RELABEL_MAX_ATTEMPTS,
            len(by_id),
            len(slots),
            response.get("stop_reason"),
        )
        if len(by_id) > len(best):
            best = by_id
        if len(slots) - len(best) <= tolerable:
            break  # complete enough — stop retrying

    if not responses and last_error is not None:
        # Every attempt raised — nothing usable came back at all.
        raise RelabelIncompleteError(
            f"Relabel produced no usable output after {RELABEL_MAX_ATTEMPTS} attempts: {last_error}"
        ) from last_error

    missing = len(slots) - len(best)
    if missing > tolerable:
        raise RelabelIncompleteError(
            f"Relabel only covered {len(best)}/{len(slots)} slots after "
            f"{RELABEL_MAX_ATTEMPTS} attempts — the model kept returning a partial set. "
            "Re-roll from the Skeleton tab."
        )
    if missing:
        logger.warning("Relabel kept %d/%d slots on their defaults", missing, len(slots))

    tweaked = {str(s.get("slot_id")): best.get(str(s.get("slot_id"))) or render_slot_string(s)
               for s in slots}
    return tweaked, _merge_text_responses(responses, model)


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

    ``on_progress`` (optional) surfaces "attempt N/M" on the progress strip.
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
                temperature=1.0,
                max_tokens=8192,
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
) -> dict:
    """Relabel a (structured) default skeleton to fit the active project's set.

    Reads ``theme.json`` + ``mechanics/approved.json`` + ``archetypes.json``
    from the active project unless passed in, runs both passes, and returns::

        {
            "updates": { slot_id: {"tweaked_text": str, "reserved_card": str|None} },
            "model_id": str,
            "input_tokens": int, "output_tokens": int, "cost_usd": float,
        }

    The caller applies the updates onto its skeleton slots. ``updates`` covers
    every input slot (``tweaked_text`` always set, ``reserved_card`` only for
    placed requests).
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
    )
    tweaked, reserved, assign_resp = assign_requests(
        slots=slots,
        tweaked=tweaked,
        card_requests=theme.get("card_requests") or [],
        model=model_id,
        log_dir=log_dir,
        on_progress=on_progress,
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
        "model_id": model_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost,
    }
