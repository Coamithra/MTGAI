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
  best-fitting slot and fold it into that slot's descriptor + ``reserved_card``.

The structured slot fields stay the deterministic default (so ``reprints`` /
``lands`` read them unchanged); only ``tweaked_text`` + ``reserved_card`` carry
the relabel. Mirrors ``archetype_generator.py`` in shape; templates live in
``mtgai/pipeline/prompts/skeleton_{relabel,assign}_{system,user}.txt``.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

from mtgai.generation.llm_client import cost_from_result, generate_with_tool
from mtgai.skeleton.generator import render_slot_string

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "pipeline" / "prompts"

# Relabel robustness. Local models routinely stop partway through the slot
# array — returning a parseable but PARTIAL tool call (occasionally with
# malformed trailing JSON the parser drops) — without tripping the max_tokens
# truncation guard. So a single call can't be trusted: we resend the whole
# prompt and retry up to RELABEL_MAX_ATTEMPTS, keeping the most-complete
# response, and treat a result still missing too many slots as a hard error so
# the caller surfaces it instead of shipping a near-default skeleton.
RELABEL_MAX_ATTEMPTS = 3
RELABEL_MIN_COVERAGE = 0.9
# A few dropped slots are fine — they keep their default descriptor. The hard
# error only fires past this many, so it scales: max(this, 10% of the set).
RELABEL_MAX_STRAGGLERS = 3


class RelabelIncompleteError(RuntimeError):
    """Relabel returned descriptors for too few slots, even after retries."""


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

RELABEL_TOOL_SCHEMA: dict = {
    "name": "submit_relabeled_slots",
    "description": (
        "Submit the relabeled skeleton — exactly one entry per slot, addressed "
        "by its slot_id, each a rewritten one-line descriptor."
    ),
    "input_schema": {
        "type": "object",
        "required": ["slots"],
        "properties": {
            "slots": {
                "type": "array",
                "description": "One relabeled slot per input slot, same slot_ids.",
                "items": {
                    "type": "object",
                    "required": ["slot_id", "text"],
                    "properties": {
                        "slot_id": {
                            "type": "string",
                            "description": "The slot's id, unchanged (e.g. 'U-C-04').",
                        },
                        "text": {
                            "type": "string",
                            "description": (
                                "The rewritten one-line descriptor — color, rarity, type, "
                                "rough CMC, mechanic, and any short role note. Keep it a "
                                "single line; no ability text or stats."
                            ),
                        },
                    },
                },
            },
        },
    },
}

ASSIGN_TOOL_SCHEMA: dict = {
    "name": "submit_request_assignments",
    "description": (
        "Submit the placement of each requested card onto a slot — one entry "
        "per request, naming the chosen slot_id and its rewritten descriptor."
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
                    "required": ["request", "slot_id", "text"],
                    "properties": {
                        "request": {"type": "string", "description": "The request text, verbatim."},
                        "slot_id": {
                            "type": "string",
                            "description": "The slot this request is placed in.",
                        },
                        "text": {
                            "type": "string",
                            "description": "The slot's descriptor, rewritten to be this card.",
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


def _collect_relabeled(response: dict, valid_ids: set[str], by_id: dict[str, str]) -> int:
    """Fold a relabel response's slots into ``by_id`` in place.

    Accepts only entries whose ``slot_id`` is a real, not-yet-filled slot with
    non-empty text — so a partial response, a hallucinated id, or a duplicate is
    ignored rather than trusted. Returns how many NEW descriptors were added.
    """
    added = 0
    for item in response.get("result", {}).get("slots") or []:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("slot_id") or "").strip()
        text = str(item.get("text") or "").strip()
        if sid in valid_ids and text and sid not in by_id:
            by_id[sid] = text
            added += 1
    return added


def _merge_relabel_responses(responses: list[dict], by_id: dict[str, str], model: str) -> dict:
    """Collapse per-attempt responses into one, summing token usage.

    ``relabel_skeleton`` reads token counts + ``cost_from_result`` off the
    returned dict, so the merged dict must carry summed ``input_tokens`` /
    ``output_tokens`` and the model id.
    """
    return {
        "result": {"slots": [{"slot_id": sid, "text": text} for sid, text in by_id.items()]},
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
) -> tuple[dict[str, str], dict]:
    """Run Pass 1. Returns (tweaked, response) where tweaked maps every
    slot_id to its rewritten descriptor.

    Robust to partial responses: each attempt resends the whole prompt; if it
    comes back missing more than the straggler tolerance, we retry from scratch
    up to ``RELABEL_MAX_ATTEMPTS`` and keep the most-complete attempt. If even
    the best is still too incomplete we raise ``RelabelIncompleteError`` so the
    caller surfaces it rather than silently shipping mostly-default slots.
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
        try:
            response = generate_with_tool(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tool_schema=RELABEL_TOOL_SCHEMA,
                model=model,
                temperature=1.0,
                max_tokens=16384,
                log_dir=log_dir,
            )
        except Exception as exc:  # transport / truncation / no-valid-tool-output
            last_error = exc
            logger.warning(
                "Relabel attempt %d/%d failed: %s", attempt, RELABEL_MAX_ATTEMPTS, exc
            )
            continue
        responses.append(response)
        by_id: dict[str, str] = {}
        _collect_relabeled(response, valid_ids, by_id)
        logger.info(
            "Relabel attempt %d/%d: %d/%d slots covered",
            attempt,
            RELABEL_MAX_ATTEMPTS,
            len(by_id),
            len(slots),
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
    return tweaked, _merge_relabel_responses(responses, best, model)


# ---------------------------------------------------------------------------
# Pass 2: assign card requests to slots
# ---------------------------------------------------------------------------


def assign_requests(
    *,
    slots: list[dict],
    tweaked: dict[str, str],
    card_requests: list[Any],
    model: str,
    log_dir: Path | None = None,
) -> tuple[dict[str, str], dict[str, str], dict | None]:
    """Run Pass 2. Returns (tweaked, reserved, response): the (possibly updated)
    per-slot descriptors, a slot_id→request map for placed cards, and the raw
    response (None when there are no requests, so no LLM call)."""
    reqs = [r for r in (card_requests or []) if (r.get("text") if isinstance(r, dict) else r)]
    reserved: dict[str, str] = {}
    if not reqs:
        return tweaked, reserved, None

    system_prompt = _read_template("skeleton_assign_system.txt")
    user_prompt = _read_template("skeleton_assign_user.txt").format(
        request_count=len(reqs),
        slot_count=len(slots),
        card_requests=_format_card_requests(reqs),
        slot_listing=_format_assign_listing(slots, tweaked),
    )

    response = generate_with_tool(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_schema=ASSIGN_TOOL_SCHEMA,
        model=model,
        temperature=1.0,
        max_tokens=8192,
        log_dir=log_dir,
    )
    valid = set(tweaked)
    for a in response["result"].get("assignments") or []:
        if not isinstance(a, dict):
            continue
        sid = str(a.get("slot_id") or "").strip()
        req = str(a.get("request") or "").strip()
        text = str(a.get("text") or "").strip()
        if sid not in valid or sid in reserved or not req:
            logger.warning("Request assignment skipped (slot=%r, request=%r)", sid, req[:40])
            continue
        reserved[sid] = req
        if text:
            tweaked[sid] = text
    if len(reserved) < len(reqs):
        logger.warning(
            "Placed %d/%d card requests; %d unplaced",
            len(reserved),
            len(reqs),
            len(reqs) - len(reserved),
        )
    return tweaked, reserved, response


# ---------------------------------------------------------------------------
# Orchestrator — called by the skeleton stage + the tab's refresh endpoint
# ---------------------------------------------------------------------------


def relabel_skeleton(
    *,
    slots: list[dict],
    theme: dict | None = None,
    approved: list[dict] | None = None,
    archetypes: list[dict] | None = None,
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
    )
    tweaked, reserved, assign_resp = assign_requests(
        slots=slots,
        tweaked=tweaked,
        card_requests=theme.get("card_requests") or [],
        model=model_id,
        log_dir=log_dir,
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
