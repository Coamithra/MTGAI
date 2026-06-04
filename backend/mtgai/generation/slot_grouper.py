"""Cycle-sort LLM pass for card generation.

After the skeleton relabel, each slot carries free-text ``tweaked_text`` plus
its (now stale) structural ``cycle_id`` seed. The relabel can have textually
pulled a slot out of a seeded cycle — or, less commonly, made a non-seeded slot
read as a cycle member — so the seed alone is not a reliable batching signal.

This module runs a single small LLM pass: it shows the model **every unfilled
slot's tweaked_text** as ``slot_id: <descriptor>`` and asks it to identify the
cycles. No theme, mechanics, archetypes, or constraints are threaded in — the
slot descriptors are self-describing post-relabel, and extra context only
distracts the model on what is, at its core, a clustering task.

The returned cycles drive batch grouping in
:mod:`mtgai.generation.card_generator`. Each cycle's key is the members' shared
seed ``cycle_id`` when they all carry the same one (so the existing
``cycle_template`` threading flows naturally), or a synthetic ``cycle_N`` key
when the model identified an emergent / cross-seed grouping. Falls back to the
structural seed grouping on total LLM failure so card-gen never breaks because
of this pass.

The card_gen model assignment is reused — no new registry key.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from mtgai.generation import temperatures as temps
from mtgai.generation.llm_client import generate_with_tool
from mtgai.generation.token_budgets import BATCH
from mtgai.skeleton.generator import render_slot_string

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "pipeline" / "prompts"

# The model can occasionally return a partial listing; retry, accumulating any
# cycles a later attempt newly identified. Three attempts mirrors RELABEL /
# ASSIGN — past that, the fallback is more useful than another retry.
_FIND_MAX_ATTEMPTS = 3

# Whole-set cycle clustering is a reasoning-heavy pass: the local model thinks
# through every slot before emitting the tool call, so its CoT alone can run
# several thousand tokens (BATCH headroom, not a single-item STANDARD budget).
#
# Temperature is NOT 0 here, despite this being a clustering task. At greedy
# decode the local model deterministically falls into a repetition loop —
# re-reasoning the same slot groups verbatim until it exhausts the budget
# mid-CoT and never reaches the tool call (finish_reason=length, empty args).
# A flat re-roll reproduces the identical loop, so mirroring the review gates'
# generate_gate_tool, each attempt is perturbed off a low base by a fixed
# step, the verified lever out of the loop (see learnings/gemma-repetition-loops.md).
_BASE_TEMPERATURE = temps.ANALYTICAL
_TEMPERATURE_STEP = temps.RETRY_TEMP_STEP

_FIND_TOOL_SCHEMA: dict[str, Any] = {
    "name": "identify_cycles",
    "description": (
        "Return the cycles in the skeleton. Each cycle is a list of slot_ids "
        "whose descriptor text reads as variants of a shared template."
    ),
    "input_schema": {
        "type": "object",
        "required": ["cycles"],
        "properties": {
            "cycles": {
                "type": "array",
                "description": (
                    "One entry per cycle. An empty array is the correct answer "
                    "when the skeleton contains no cycles."
                ),
                "items": {
                    "type": "object",
                    "required": ["slot_ids"],
                    "properties": {
                        "slot_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "The slot_ids of this cycle's members, taken "
                                "verbatim from the input listing. At least two."
                            ),
                        },
                    },
                },
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


def _read_template(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def _format_slot_listing(slots: list[dict]) -> str:
    """Render every input slot as ``slot_id: <descriptor>`` on its own line.

    The descriptor is the slot's ``tweaked_text`` when present (the
    authoritative post-relabel signal); else the deterministic default — same
    fallback :func:`format_slot_specs` uses.
    """
    lines: list[str] = []
    for slot in slots:
        text = (slot.get("tweaked_text") or render_slot_string(slot)).strip()
        lines.append(f"{slot['slot_id']}: {text}")
    return "\n".join(lines)


def _build_user_prompt(slots: list[dict]) -> str:
    template = _read_template("card_gen_cycle_sort_user.txt")
    return template.format(
        slot_count=len(slots),
        slot_listing=_format_slot_listing(slots),
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_response(
    response: dict,
    valid_slot_ids: set[str],
    already_placed: set[str],
) -> list[list[str]]:
    """Extract a list of cycles (each a list of slot_ids) from the LLM response.

    Validation rules (silent skip, warn):
    - Each slot_id must appear in the input listing.
    - A slot_id appears in at most one cycle (across this response *and* any
      cycles confirmed by earlier attempts via ``already_placed``).
    - A cycle with fewer than two surviving members is dropped.
    """
    out: list[list[str]] = []
    seen_this_pass: set[str] = set()
    for entry in response.get("result", {}).get("cycles") or []:
        if not isinstance(entry, dict):
            continue
        kept: list[str] = []
        for raw in entry.get("slot_ids") or []:
            sid = str(raw or "").strip()
            if not sid:
                continue
            if sid not in valid_slot_ids:
                logger.warning("Cycle-sort skipped slot_id=%r — not in input listing", sid)
                continue
            if sid in already_placed or sid in seen_this_pass:
                logger.warning("Cycle-sort skipped slot_id=%r — already placed", sid)
                continue
            kept.append(sid)
            seen_this_pass.add(sid)
        if len(kept) >= 2:
            out.append(kept)
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def find_cycle_families(
    *,
    slots: list[dict],
    model: str,
    log_dir: Path | None = None,
) -> dict[str, list[str]]:
    """Ask the LLM to identify cycles in the relabeled slot listing.

    Args:
        slots: the unfilled slots being card-gen'd this run (card-gen has
            already filtered out lands + reprint slots). All slots are shown
            to the model — non-cycle slots included — so the model judges
            membership purely from text rather than relying on a seed tag.
        model: the active project's card_gen model id.
        log_dir: directory for llmfacade's per-conversation transcript.

    Returns:
        ``{cycle_key -> [slot_id, ...]}``. ``cycle_key`` is the members' shared
        seed ``cycle_id`` when they all carry the same one (so the existing
        ``cycle_template`` threading flows through unchanged) — otherwise a
        synthetic ``cycle_N`` key. On total LLM failure the function falls
        back to grouping slots by their structural seed ``cycle_id`` (dropping
        any singleton groups), so card-gen never breaks because of this pass.
    """
    if not slots:
        return {}

    valid_slot_ids = {s["slot_id"] for s in slots}
    slot_by_id = {s["slot_id"]: s for s in slots}

    system_prompt = _read_template("card_gen_cycle_sort_system.txt")
    user_prompt = _build_user_prompt(slots)

    discovered: list[list[str]] = []  # accumulated across attempts
    already_placed: set[str] = set()
    any_response = False
    last_error: Exception | None = None

    # Lift the base off the near-greedy floor for a local reasoning model so the
    # decode terminates; the per-attempt bump still stacks on top of the floored
    # base (see temperatures.floor_for_local).
    base_temperature = temps.floor_for_local(_BASE_TEMPERATURE, model)
    for attempt in range(1, _FIND_MAX_ATTEMPTS + 1):
        # Perturb the decode off the low base each attempt so a retry doesn't
        # re-derive the same repetition loop a flat re-roll would (see above).
        temperature = base_temperature + _TEMPERATURE_STEP * (attempt - 1)
        try:
            response = generate_with_tool(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tool_schema=_FIND_TOOL_SCHEMA,
                model=model,
                temperature=temperature,
                max_tokens=BATCH,
                log_dir=log_dir,
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Cycle-sort attempt %d/%d failed: %s",
                attempt,
                _FIND_MAX_ATTEMPTS,
                exc,
            )
            continue
        any_response = True
        attempt_out = _parse_response(response, valid_slot_ids, already_placed)
        # A complete-looking response (>=1 cycle returned, or the model
        # explicitly returned an empty array) ends the retry loop; otherwise
        # accumulate what we got and try once more.
        if attempt_out or _response_was_empty(response):
            for grp in attempt_out:
                discovered.append(grp)
                already_placed.update(grp)
            break
        # Partial: accumulate and retry
        for grp in attempt_out:
            discovered.append(grp)
            already_placed.update(grp)

    if not any_response:
        logger.warning(
            "Cycle-sort produced no usable output after %d attempts (last error: %s) — "
            "falling back to structural cycle_id grouping",
            _FIND_MAX_ATTEMPTS,
            last_error,
        )
        return _fallback_grouping(slots)

    result = _key_by_seed_cycle_id(discovered, slot_by_id)
    logger.info(
        "Cycle-sort identified %d cycle(s) covering %d slot_ids",
        len(result),
        sum(len(v) for v in result.values()),
    )
    return result


def _response_was_empty(response: dict) -> bool:
    """True when the model explicitly returned ``cycles: []`` (a valid answer).

    Used to distinguish "no cycles in this skeleton" from "the model partially
    answered and we should retry".
    """
    cycles = response.get("result", {}).get("cycles")
    return isinstance(cycles, list) and len(cycles) == 0


def _key_by_seed_cycle_id(
    discovered: list[list[str]],
    slot_by_id: dict[str, dict],
) -> dict[str, list[str]]:
    """Pick a stable key for each identified cycle.

    When every member of an identified cycle carries the same seed
    ``cycle_id``, use that as the key — the slots already have their
    ``cycle_template`` stamped from that seed, so the card-gen prompt's cycle
    note flows through unchanged. Otherwise the cycle is emergent (or crosses
    seeds), so we assign a synthetic ``cycle_N`` key; those slots batch
    together but get no shared-template hint in the prompt.
    """
    out: dict[str, list[str]] = {}
    synthetic_idx = 0
    used_keys: set[str] = set()
    for group in discovered:
        seeds: set[str] = {
            sid_seed for sid in group if (sid_seed := slot_by_id[sid].get("cycle_id"))
        }
        if len(seeds) == 1:
            key = seeds.pop()
            # Two LLM-identified cycles could share the same seed if the seed
            # was over-broad; uniquify the second with a suffix so they
            # remain distinct batches.
            if key in used_keys:
                key = f"{key}_{synthetic_idx}"
                synthetic_idx += 1
        else:
            key = f"cycle_{synthetic_idx}"
            synthetic_idx += 1
        used_keys.add(key)
        out[key] = group
    return out


def _fallback_grouping(slots: list[dict]) -> dict[str, list[str]]:
    """Fallback when every LLM attempt errored: group by structural ``cycle_id``.

    Slots without a seed cycle_id are excluded. Groups with fewer than two
    members are dropped (a one-card "family" is just a card).
    """
    by_seed: dict[str, list[str]] = {}
    for s in slots:
        cid = s.get("cycle_id")
        if not cid:
            continue
        by_seed.setdefault(cid, []).append(s["slot_id"])
    return {cid: sids for cid, sids in by_seed.items() if len(sids) >= 2}
