"""Reprint selection for MTG set generation.

Two LLM passes, mirroring the skeleton's relabel/assign split:

* **Select** (``_select_from_pool``) — given the set's theme + mechanics +
  archetypes + constraints and the curated, setting-agnostic reprint pool, the
  model picks the ``count`` staples that best fit the set. Pool fit only — no
  placement.
* **Place** (``_place_reprints``) — given the chosen cards and the skeleton's
  *plain-text* slot list, the model assigns each reprint to the best-fitting
  ordinary slot. Slots are free text after the skeleton stage, so "don't put a
  reprint on a named character / signpost / cycle slot" is enforced by prompt
  engineering, not structured filtering. Retry/dedup like the relabel's Pass 2.

The count is a single total (see ``reprint_knobs``); rarity-per-slot no longer
exists as structured data. Cost: a couple of cheap calls on the ``reprints``
model (local Gemma by default). Runs BEFORE card generation so reprint slots
aren't spent on generated cards.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from mtgai.generation import temperatures as temps
from mtgai.generation.reprint_knobs import (
    RARITIES,
    ReprintKnobs,
    default_knobs,
    from_payload,
    resolve_targets,
)
from mtgai.generation.skeleton_prompt_blocks import (
    format_archetypes_block,
    format_constraints_block,
    format_mechanics_block,
    format_setting_block,
)
from mtgai.generation.token_utils import OutputTruncatedError
from mtgai.io.atomic import atomic_write_text
from mtgai.models.card import Card
from mtgai.models.enums import Color, Rarity
from mtgai.runtime import ai_lock

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_POOL_PATH = Path(__file__).parent / "reprint_pool.json"

# Pass 2 (placement) is flaky on local models — a call may place only some of the
# chosen cards. Retry, accumulating placements (dedup by card + slot).
_PLACE_MAX_ATTEMPTS = 3

# Pass 1 (select) retries only on a truncation/repetition loop; bump temperature
# per retry to escape it (see temperatures.RETRY_TEMP_STEP). Same budget as the
# placement pass today, but a separate constant so the two retry policies can
# diverge without one silently changing the other.
_SELECT_MAX_ATTEMPTS = 3


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class ReprintCandidate(BaseModel):
    """A card being considered for reprint."""

    name: str
    mana_cost: str | None = None
    cmc: float
    type_line: str
    oracle_text: str = ""
    colors: list[str] = Field(default_factory=list)
    rarity: str
    role: str
    setting_agnostic: bool | None = True
    source: str = "curated_pool"
    edhrec_rank: int | None = None
    keywords: list[str] = Field(default_factory=list)
    subtypes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    power: str | None = None
    toughness: str | None = None


class ReprintSlot(BaseModel):
    """The slot a reprint was placed on — its id + the plain-text spec it had."""

    slot_id: str
    descriptor: str = ""


class SelectionPair(BaseModel):
    """A chosen reprint + the slot it was placed on, with the LLM's reasoning."""

    slot: ReprintSlot
    candidate: ReprintCandidate
    reason: str = ""
    # True when the user hand-picked / hand-placed this reprint on the Reprints
    # tab. A manual Refresh keeps pinned pairs verbatim and re-rolls only the
    # unpinned (AI-chosen) ones around them. The engine path produces all-unpinned.
    pinned: bool = False


class ReprintSelection(BaseModel):
    """Complete reprint selection result for a set."""

    set_code: str
    set_size: int
    target_reprint_count: int
    # The per-rarity targets the select pass was asked for (soft guidance, not
    # enforced). None for the legacy flat-count path. Sum ~= target_reprint_count.
    per_rarity_targets: dict[str, int] | None = None
    selections: list[SelectionPair]
    all_candidates_considered: int
    selection_timestamp: str


# ---------------------------------------------------------------------------
# Pool loading
# ---------------------------------------------------------------------------


def load_reprint_pool(pool_path: Path | None = None) -> list[ReprintCandidate]:
    """Load the curated reprint pool from JSON and return as candidate list."""
    path = pool_path or _POOL_PATH
    logger.info("Loading reprint pool from %s", path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    candidates: list[ReprintCandidate] = []
    for entry in data["cards"]:
        candidates.append(
            ReprintCandidate(
                name=entry["name"],
                mana_cost=entry.get("mana_cost") or None,
                cmc=float(entry["cmc"]),
                type_line=entry["type_line"],
                oracle_text=entry.get("oracle_text", ""),
                colors=entry.get("colors", []),
                rarity=entry["rarity"],
                role=entry["role"],
                setting_agnostic=entry.get("setting_agnostic", True),
                source="curated_pool",
                edhrec_rank=entry.get("edhrec_rank_approx"),
                keywords=entry.get("keywords", []),
                subtypes=entry.get("subtypes", []),
                tags=entry.get("tags", []),
                power=entry.get("power"),
                toughness=entry.get("toughness"),
            )
        )
    logger.info("Loaded %d candidates from curated pool", len(candidates))
    return candidates


def format_candidate_tldr(c: ReprintCandidate) -> str:
    """Format a candidate as a one-liner for the LLM prompt.

    Full oracle text (newlines flattened) — the pool is sent once now, so there's
    no need to clip. Examples:
        "Murder (common · {1}{B}{B} — Destroy target creature.)"
        "Firebrand Archer (common · {1}{R} 2/1 — Whenever you cast a noncreature spell, ...)"
    """
    parts = [c.name, " (", c.rarity, " · "]
    if c.mana_cost:
        parts.append(c.mana_cost)
    else:
        parts.append("no cost")
    if c.power is not None and c.toughness is not None:
        parts.append(f" {c.power}/{c.toughness}")
    oracle = c.oracle_text.replace("\n", " / ")
    if oracle:
        parts.append(f" — {oracle}")
    parts.append(")")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Set context + slots
# ---------------------------------------------------------------------------


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Unreadable JSON at %s; using default", path)
        return default


def extract_set_config(skeleton_path: Path) -> dict:
    """Read ``skeleton.json``'s config block (name / code / set_size / flavor)."""
    skeleton = _read_json(skeleton_path, {})
    config = skeleton.get("config", {}) if isinstance(skeleton, dict) else {}
    return {
        "name": config.get("name", ""),
        "code": config.get("code", "???"),
        "theme": config.get("theme", ""),
        "flavor_description": config.get("flavor_description", ""),
        "special_constraints": config.get("special_constraints", []),
        "set_size": config.get("set_size", 60),
    }


def _load_set_context(asset: Path, cfg: dict) -> dict[str, str]:
    """Format the set-context blocks (setting / mechanics / archetypes / constraints).

    Reads ``theme.json`` + ``mechanics/approved.json`` + ``archetypes.json`` from
    *asset*; falls back to the skeleton config's flavor when there is no
    ``theme.json``. Reuses the shared skeleton block formatters so the reprint
    selection sees the same set framing as the relabel/tuner.
    """
    theme = _read_json(asset / "theme.json", {})
    if not isinstance(theme, dict) or not theme:
        theme = {
            "theme": cfg.get("theme", ""),
            "flavor_description": cfg.get("flavor_description", ""),
        }
    approved = _read_json(asset / "mechanics" / "approved.json", [])
    archetypes = _read_json(asset / "archetypes.json", [])
    constraints = theme.get("constraints") or cfg.get("special_constraints") or []
    return {
        "setting": format_setting_block(theme),
        "mechanics": format_mechanics_block(approved if isinstance(approved, list) else []),
        "archetypes": format_archetypes_block(archetypes if isinstance(archetypes, list) else []),
        "constraints": format_constraints_block(
            constraints if isinstance(constraints, list) else []
        ),
    }


def _load_slot_texts(skeleton_path: Path, *, include_reprints: bool = True) -> list[dict[str, str]]:
    """Each unfilled slot as ``{slot_id, text}`` — its relabeled ``tweaked_text``
    (the slot's plain-text spec), or the default descriptor as a fallback.

    By default reprint-stamped slots are *included* (the reprint placement pass
    needs every ordinary slot, and re-rolls re-place over them). Pass
    ``include_reprints=False`` for readers that treat a placed reprint as a filled
    card — e.g. the lands fixing investigation, whose "unfilled slots" view must
    not double-count slots the reprint stage already claimed.
    """
    from mtgai.skeleton.generator import render_slot_string

    skeleton = _read_json(skeleton_path, {})
    out: list[dict[str, str]] = []
    for slot in skeleton.get("slots", []) if isinstance(skeleton, dict) else []:
        if not isinstance(slot, dict) or slot.get("card_id") is not None:
            continue
        if not include_reprints and slot.get("is_reprint_slot"):
            continue
        sid = str(slot.get("slot_id") or "").strip()
        if not sid:
            continue
        text = (slot.get("tweaked_text") or "").strip() or render_slot_string(slot)
        out.append({"slot_id": sid, "text": text})
    return out


# ---------------------------------------------------------------------------
# Prompts (built inline — pool TLDRs carry `{mana}` braces that break str.format)
# ---------------------------------------------------------------------------

_SELECT_SYSTEM = (
    "You are an expert Magic: The Gathering set designer choosing REPRINTS for a "
    "new set.\n\n"
    "You are given the set's theme, mechanics, and draft archetypes, plus a pool "
    "of well-known, setting-agnostic staple cards. Choose exactly the requested "
    "number of cards from the pool to reprint.\n\n"
    "## What makes a good reprint here\n"
    "- Fills an essential Limited role the set needs (removal and mana fixing "
    "first, then combat tricks / card advantage).\n"
    "- Synergizes with the set's mechanics and archetypes where it can.\n"
    "- Is a recognizable staple with a setting-agnostic name that fits this world.\n\n"
    "## Rules\n"
    "- Choose all picks from the pool below, using each card's exact name. No "
    "duplicates.\n"
    "- Aim for the requested per-rarity mix (the pool one-liners show each card's "
    "rarity). Get as close as you can; a near miss is fine if the right-rarity "
    "staples don't fit the set.\n"
    "- Return your picks through the tool only — no preamble."
)

_PLACE_SYSTEM = (
    "You are a Magic: The Gathering set designer slotting a set's chosen REPRINTS "
    "into its card skeleton.\n\n"
    "You are given a list of already-chosen reprint cards and the set's slot list "
    "— each slot is a one-line plain-text descriptor addressed by `slot_id`. "
    "Assign each reprint to the single best-fitting slot; that slot then becomes "
    "the reprint.\n\n"
    "## Rules\n"
    "- Each reprint goes to exactly one slot_id; place every reprint; no two "
    "reprints share a slot.\n"
    "- ONLY replace ordinary, generic slots. A reprint is an existing filler/"
    "staple, so it must land on a plain slot (a vanilla creature, a basic "
    "removal/trick). NEVER place a reprint on a slot that describes:\n"
    "    - a named character or legend,\n"
    "    - a signature / build-around / signpost card (often tagged `signpost:` "
    "or dense with mechanic text),\n"
    "    - a member of a card cycle (often tagged `cycle:`),\n"
    "    - or anything that reads like a bespoke, high-text design.\n"
    "  Replacing such a slot would delete a designed card — do not. When unsure, "
    "pick the plainest slot whose colour and role the reprint matches.\n"
    "- Return your assignments through the tool only — no preamble."
)


def _build_select_context(context: dict[str, str], pool: list[ReprintCandidate]) -> str:
    """The static cached system block for the select pass: set framing + the full
    ~350-card reprint pool. Byte-stable across this run's retries / re-rolls (the
    only dynamic bit — count + rarity mix — rides in :func:`_build_select_trigger`),
    so it reads from cache at ~0.1x within the 5-min TTL."""
    lines = [
        "## Set theme",
        context["setting"],
        "",
        "## Mechanics",
        context["mechanics"],
        "",
        "## Draft archetypes",
        context["archetypes"],
        "",
        "## Constraints",
        context["constraints"],
        "",
        f"## Reprint pool ({len(pool)} cards)",
    ]
    lines += [f"- {format_candidate_tldr(c)}" for c in pool]
    return "\n".join(lines)


def _build_select_trigger(count: int, per_rarity: dict[str, int] | None = None) -> str:
    """The dynamic user turn for the select pass — the only per-call-varying part."""
    if per_rarity and any(v > 0 for v in per_rarity.values()):
        mix = ", ".join(f"{per_rarity[r]} {r}" for r in RARITIES if per_rarity.get(r, 0) > 0)
        return (
            f"Choose {count} reprints from the pool above for this set, aiming for "
            f"this rarity mix: {mix}. Use each card's exact name; no duplicates. "
            "Return your picks through the select_reprints tool."
        )
    return (
        f"Choose exactly {count} reprints from the pool above for this set. Use each "
        "card's exact name; no duplicates. Return your picks through the "
        "select_reprints tool."
    )


def _build_place_context(
    selected: list[tuple[ReprintCandidate, str]], slot_texts: list[dict[str, str]]
) -> str:
    """The cached system block for the place pass: the chosen reprints + the slot
    list. Rebuilt per placement attempt from only the still-unplaced cards and
    still-open slots, so a retry never re-sends already-placed work."""
    lines = [f"## Chosen reprints ({len(selected)})"]
    lines += [f"- {format_candidate_tldr(c)}" for c, _ in selected]
    lines += ["", f"## Skeleton slots ({len(slot_texts)})"]
    lines += [f"{s['slot_id']}: {s['text']}" for s in slot_texts]
    return "\n".join(lines)


def _build_place_trigger(selected: list[tuple[ReprintCandidate, str]]) -> str:
    """The dynamic user turn for the place pass."""
    return (
        f"Place each chosen reprint listed above onto the single best-fitting ordinary "
        f"slot. Return all {len(selected)} assignments through the place_reprints tool."
    )


_SELECT_TOOL = {
    "name": "select_reprints",
    "description": "Choose which pool cards to reprint in this set",
    "input_schema": {
        "type": "object",
        "properties": {
            "selections": {
                "type": "array",
                "description": "The chosen reprints (exactly the requested count)",
                "items": {
                    "type": "object",
                    "properties": {
                        "card_name": {"type": "string", "description": "Exact name from the pool"},
                        "reason": {"type": "string", "description": "Why it fits this set"},
                    },
                    "required": ["card_name", "reason"],
                },
            }
        },
        "required": ["selections"],
    },
}

_PLACE_TOOL = {
    "name": "place_reprints",
    "description": "Assign each chosen reprint to the slot it best fits",
    "input_schema": {
        "type": "object",
        "properties": {
            "assignments": {
                "type": "array",
                "description": "One entry per reprint: the card and the slot_id it fills",
                "items": {
                    "type": "object",
                    "properties": {
                        "card_name": {"type": "string", "description": "Exact chosen card name"},
                        "slot_id": {"type": "string", "description": "The slot_id to fill"},
                        "reason": {"type": "string", "description": "Why this slot fits"},
                    },
                    "required": ["card_name", "slot_id"],
                },
            }
        },
        "required": ["assignments"],
    },
}


# ---------------------------------------------------------------------------
# Pass 1: select reprints from the pool (set-fit)
# ---------------------------------------------------------------------------


def _select_from_pool(
    context: dict[str, str],
    pool: list[ReprintCandidate],
    count: int,
    model: str,
    log_dir: Path | None,
    temperature: float,
    per_rarity: dict[str, int] | None = None,
    thinking: str | None = None,
) -> list[tuple[ReprintCandidate, str]]:
    """Pick ``count`` pool cards that fit the set (aiming for the per-rarity mix
    when given). Returns (candidate, reason). The mix is soft — capped at the
    total, not per rarity."""
    from mtgai.generation.llm_client import generate_with_tool
    from mtgai.generation.token_budgets import STANDARD

    if count <= 0 or not pool:
        return []
    by_name = {c.name.lower(): c for c in pool}
    # Static set framing + the full pool ride in a cached system block (byte-stable
    # across retries / re-rolls); only the count + rarity-mix trigger stays dynamic.
    context_block = _build_select_context(context, pool)
    trigger = _build_select_trigger(count, per_rarity)
    # A truncated local response is usually a repetition loop; a plain re-roll at
    # the same low temp reproduces it, so bump the temperature per retry (the
    # verified escape — see temperatures.RETRY_TEMP_STEP / gate_common).
    response = None
    for attempt in range(_SELECT_MAX_ATTEMPTS):
        if attempt and ai_lock.is_cancelled():
            break
        try:
            response = generate_with_tool(
                system_blocks=[(_SELECT_SYSTEM, True), (context_block, True)],
                user_prompt=trigger,
                tool_schema=_SELECT_TOOL,
                model=model,
                temperature=temperature + temps.RETRY_TEMP_STEP * attempt,
                max_tokens=STANDARD,
                log_dir=log_dir,
                thinking=thinking,
            )
            break
        except OutputTruncatedError as exc:
            logger.warning("Reprint selection truncated (attempt %d): %s", attempt + 1, exc)
        except Exception:
            # Only a loop/truncation is worth re-rolling. A non-truncation error
            # (bad prompt, transport) recurs identically, and with nothing picked
            # there's nothing to place — so bail (placement retries instead, as a
            # partial place is still useful).
            logger.error("Reprint selection (pick) failed", exc_info=True)
            return []
    if response is None:
        return []

    chosen: list[tuple[ReprintCandidate, str]] = []
    seen: set[str] = set()
    for raw in response.get("result", {}).get("selections") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("card_name") or "").strip().lower()
        cand = by_name.get(name)
        if cand is None:
            logger.warning("Select returned unknown card name: %s", raw.get("card_name"))
            continue
        if name in seen:
            continue
        chosen.append((cand, str(raw.get("reason") or "").strip()))
        seen.add(name)
        if len(chosen) >= count:
            break
    if len(chosen) != count:
        logger.warning("Selected %d reprints, expected %d", len(chosen), count)
    return chosen


# ---------------------------------------------------------------------------
# Pass 2: place chosen reprints onto slots (avoid special slots via the prompt)
# ---------------------------------------------------------------------------


def _place_reprints(
    selected: list[tuple[ReprintCandidate, str]],
    slot_texts: list[dict[str, str]],
    model: str,
    log_dir: Path | None,
    temperature: float,
    thinking: str | None = None,
) -> list[SelectionPair]:
    """Assign each chosen reprint to a slot. Retries, dedups by card + slot."""
    from mtgai.generation.llm_client import generate_with_tool
    from mtgai.generation.token_budgets import STANDARD

    if not selected or not slot_texts:
        return []
    by_name = {c.name.lower(): (c, reason) for c, reason in selected}
    text_by_id = {s["slot_id"]: s["text"] for s in slot_texts}
    valid = set(text_by_id)

    pairs: list[SelectionPair] = []
    placed: set[str] = set()  # card names (lower) already placed
    used: set[str] = set()  # slot_ids already taken

    for attempt in range(1, _PLACE_MAX_ATTEMPTS + 1):
        if len(placed) >= len(selected):
            break
        # Honor a Cancel between placement attempts (an in-flight call can't be
        # interrupted) — keep whatever placed so far.
        if ai_lock.is_cancelled():
            logger.warning("Reprint placement CANCELLED by user after %d placed", len(placed))
            break
        # Rebuild the prompt each attempt from ONLY the still-unplaced cards and the
        # still-open slots, so a retry asks for exactly the remaining work instead of
        # re-sending already-placed cards or re-offering taken slots. (Costs the
        # system block's cache reuse across retries, but the retry path is the rare
        # case and the correctness/leanness win dominates.)
        remaining = [(c, reason) for c, reason in selected if c.name.lower() not in placed]
        open_slots = [s for s in slot_texts if s["slot_id"] not in used]
        context_block = _build_place_context(remaining, open_slots)
        trigger = _build_place_trigger(remaining)
        try:
            # Each re-ask is also perturbed off the base: it both fills the
            # remaining slots and escapes a same-temp repetition loop on local.
            response = generate_with_tool(
                system_blocks=[(_PLACE_SYSTEM, True), (context_block, True)],
                user_prompt=trigger,
                tool_schema=_PLACE_TOOL,
                model=model,
                temperature=temperature + temps.RETRY_TEMP_STEP * (attempt - 1),
                max_tokens=STANDARD,
                log_dir=log_dir,
                thinking=thinking,
            )
        except Exception:
            logger.error("Reprint placement attempt %d failed", attempt, exc_info=True)
            continue
        for raw in response.get("result", {}).get("assignments") or []:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("card_name") or "").strip().lower()
            sid = str(raw.get("slot_id") or "").strip()
            entry = by_name.get(name)
            if entry is None or name in placed:
                continue
            if sid not in valid or sid in used:
                logger.warning("Placement skipped (bad/taken slot=%r for %r)", sid, name)
                continue
            cand, sel_reason = entry
            place_reason = str(raw.get("reason") or "").strip()
            pairs.append(
                SelectionPair(
                    slot=ReprintSlot(slot_id=sid, descriptor=text_by_id.get(sid, "")),
                    candidate=cand,
                    reason=sel_reason or place_reason,
                )
            )
            placed.add(name)
            used.add(sid)
            logger.info("  Placed %s -> %s", cand.name, sid)

    if len(pairs) < len(selected):
        logger.warning(
            "Placed %d/%d reprints after %d attempts",
            len(pairs),
            len(selected),
            _PLACE_MAX_ATTEMPTS,
        )
    return pairs


# ---------------------------------------------------------------------------
# Knobs persistence
# ---------------------------------------------------------------------------


def load_reprint_knobs(asset_dir: Path) -> ReprintKnobs:
    """Read ``<asset>/reprints/knobs.json`` (defaults when absent/unreadable)."""
    raw = _read_json(asset_dir / "reprints" / "knobs.json", None)
    return from_payload(raw) if raw is not None else default_knobs()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def select_reprints(
    skeleton_path: Path,
    *,
    set_config: dict | None = None,
    count: int | None = None,
    pool_path: Path | None = None,
    log_dir: Path | None = None,
    knobs: ReprintKnobs | None = None,
    temperature: float = temps.ANALYTICAL,
    pinned: list[SelectionPair] | None = None,
) -> ReprintSelection:
    """Select + place reprints for a set — main entry point.

    Two LLM passes (select-from-pool, then place-on-slots). The count is decided
    per rarity from :class:`ReprintKnobs` (auto from the lean per-rarity rates x
    the set's estimated rarity counts + jitter, or pinned), summed to a total and
    stated to the select pass as a soft rarity mix. An explicit ``count`` bypasses
    the knobs (flat total — scripts/tests). The model is the active project's
    ``reprints`` assignment (local Gemma by default). ``temperature`` defaults to
    a low :data:`temperatures.ANALYTICAL` base (NOT 0 — greedy decode loops on the
    local default and isn't actually deterministic anyway); both passes bump it by
    :data:`temperatures.RETRY_TEMP_STEP` per retry to escape a Gemma repetition
    loop. A manual Refresh passes a higher value. Files
    (theme/knobs/logs) resolve relative to ``skeleton_path``'s directory; the LLM
    transcript lands in ``<asset>/reprints/logs``.

    ``pinned`` are user-locked selections (from the Reprints tab) kept verbatim:
    the AI re-rolls only the remaining ``total - len(pinned)`` picks, with the
    pinned cards + slots withheld from both AI passes so there are no duplicate
    picks or slot collisions. The result is ``pinned + ai_selections``.
    """
    asset = skeleton_path.parent
    pinned = pinned or []
    cfg = set_config or extract_set_config(skeleton_path)
    set_size = int(cfg.get("set_size", 60))
    set_code = cfg.get("code", "???")

    slot_texts = _load_slot_texts(skeleton_path)
    full_pool = load_reprint_pool(pool_path)
    pool = [c for c in full_pool if c.setting_agnostic is not False]

    # Withhold pinned cards + slots from the AI passes so a re-roll can't pick a
    # pinned card again or collide with a pinned slot.
    pinned_names = {p.candidate.name.lower() for p in pinned}
    pinned_slot_ids = {p.slot.slot_id for p in pinned}
    if pinned_names:
        pool = [c for c in pool if c.name.lower() not in pinned_names]
    if pinned_slot_ids:
        slot_texts = [s for s in slot_texts if s["slot_id"] not in pinned_slot_ids]

    per_rarity: dict[str, int] | None = None
    if count is None:
        if knobs is None:
            knobs = load_reprint_knobs(asset)
        resolved = resolve_targets(knobs, set_size)
        per_rarity = resolved
        total: int = sum(resolved.values())
    else:
        total = count

    # The AI fills only the picks the pins don't already cover; subtract the
    # pinned per-rarity counts from the soft mix told to the select pass.
    ai_target = max(0, total - len(pinned))
    ai_per_rarity = per_rarity
    if per_rarity is not None and pinned:
        ai_per_rarity = dict(per_rarity)
        for p in pinned:
            r = p.candidate.rarity
            if r in ai_per_rarity:
                ai_per_rarity[r] = max(0, ai_per_rarity[r] - 1)

    if log_dir is None:
        log_dir = asset / "reprints" / "logs"

    logger.info(
        "Selecting %d reprints for %s (%d-card set); per-rarity=%s; %d pinned, %d from AI",
        total,
        set_code,
        set_size,
        per_rarity,
        len(pinned),
        ai_target,
    )

    selections: list[SelectionPair] = list(pinned)
    if ai_target > 0:
        try:
            from mtgai.runtime.active_project import require_active_project

            model = require_active_project().settings.get_llm_model_id("reprints")
            thinking = require_active_project().settings.get_thinking("reprints")
        except Exception:
            logger.error("Cannot resolve reprints model (no active project?)", exc_info=True)
            model = None
            thinking = None
        if model is not None:
            # Lift the base off the near-greedy floor for a local reasoning model
            # so both passes terminate; each pass's per-retry bump stacks on top
            # of the floored base (see temperatures.floor_for_local).
            temperature = temps.floor_for_local(temperature, model)
            context = _load_set_context(asset, cfg)
            chosen = _select_from_pool(
                context,
                pool,
                ai_target,
                model,
                log_dir,
                temperature,
                per_rarity=ai_per_rarity,
                thinking=thinking,
            )
            # Honor a Cancel between the select and place passes (an in-flight
            # call can't be interrupted) — skip placement, keep no selections.
            if ai_lock.is_cancelled():
                logger.warning("Reprint selection CANCELLED by user before placement")
            else:
                selections += _place_reprints(
                    chosen, slot_texts, model, log_dir, temperature, thinking=thinking
                )

    result = ReprintSelection(
        set_code=set_code,
        set_size=set_size,
        # Pins can exceed the resolved auto target; never report fewer than placed.
        target_reprint_count=max(total, len(selections)),
        per_rarity_targets=per_rarity,
        selections=selections,
        all_candidates_considered=len(full_pool),
        selection_timestamp=datetime.now(UTC).isoformat(),
    )
    logger.info(
        "Reprint selection complete: %d placed (target %d, pool %d)",
        len(selections),
        total,
        len(full_pool),
    )
    return result


# ---------------------------------------------------------------------------
# Skeleton write-back — incorporate the chosen reprints into the skeleton
# ---------------------------------------------------------------------------


def reset_reprint_stamps(skeleton: dict) -> bool:
    """Clear every slot's reprint stamp in-place. Returns True if anything changed.

    The inverse of stamping: a re-roll or ``clear_reprints`` un-marks the slots so
    they return to ordinary, generatable slots. ``tweaked_text`` was never touched,
    so each slot's themed descriptor survives intact.
    """
    changed = False
    for slot in skeleton.get("slots", []) if isinstance(skeleton, dict) else []:
        if not isinstance(slot, dict):
            continue
        if slot.get("is_reprint_slot") or slot.get("reprint_card") is not None:
            slot["is_reprint_slot"] = False
            slot["reprint_card"] = None
            changed = True
    return changed


def _reprint_identity(c: ReprintCandidate) -> str:
    """One-line identity for a placed reprint, stamped onto its skeleton slot."""
    return f"{c.name} · {c.type_line} · {c.mana_cost or 'no cost'}"


def apply_selection_to_skeleton(skeleton_path: Path, selection: ReprintSelection) -> int:
    """Write the chosen reprints back into ``skeleton.json`` (reset, then stamp).

    For each placed reprint, find its slot by ``slot_id`` and mark
    ``is_reprint_slot=True`` + ``reprint_card=<identity>``. Resets any prior reprint
    stamps first, so this is idempotent and safe after a re-roll (the previous run's
    stamps are wiped; only the current selection's remain). Leaves ``tweaked_text``
    untouched. Returns the number of slots stamped.

    Downstream effect: card-gen skips reprint slots (no double-generation), and the
    lands fixing investigation drops them from its unfilled-slot view — the reprint
    is the slot's card now.
    """
    skeleton = _read_json(skeleton_path, None)
    if not isinstance(skeleton, dict) or not isinstance(skeleton.get("slots"), list):
        logger.warning("apply_selection_to_skeleton: no usable skeleton at %s", skeleton_path)
        return 0

    reset_reprint_stamps(skeleton)
    by_id = {
        str(s.get("slot_id")): s
        for s in skeleton["slots"]
        if isinstance(s, dict) and s.get("slot_id")
    }
    stamped = 0
    for pair in selection.selections:
        slot = by_id.get(str(pair.slot.slot_id))
        if slot is None:
            logger.warning("Reprint slot %s not in skeleton; skipping stamp", pair.slot.slot_id)
            continue
        slot["is_reprint_slot"] = True
        slot["reprint_card"] = _reprint_identity(pair.candidate)
        stamped += 1

    atomic_write_text(skeleton_path, json.dumps(skeleton, indent=2, ensure_ascii=False))
    logger.info("Stamped %d reprint slots into %s", stamped, skeleton_path.name)
    return stamped


# ---------------------------------------------------------------------------
# Card conversion
# ---------------------------------------------------------------------------

_COLOR_MAP: dict[str, Color] = {
    "W": Color.WHITE,
    "U": Color.BLUE,
    "B": Color.BLACK,
    "R": Color.RED,
    "G": Color.GREEN,
}

_RARITY_MAP: dict[str, Rarity] = {
    "common": Rarity.COMMON,
    "uncommon": Rarity.UNCOMMON,
    "rare": Rarity.RARE,
    "mythic": Rarity.MYTHIC,
}


def _parse_card_types(type_line: str) -> tuple[list[str], list[str], list[str]]:
    """Parse a type line into (supertypes, card_types, subtypes)."""
    supertypes_set = {"Legendary", "Basic", "Snow", "World"}
    card_types_set = {
        "Creature",
        "Instant",
        "Sorcery",
        "Enchantment",
        "Artifact",
        "Planeswalker",
        "Land",
    }

    if " — " in type_line:
        main_part, sub_part = type_line.split(" — ", 1)
    elif " -- " in type_line:
        main_part, sub_part = type_line.split(" -- ", 1)
    else:
        main_part = type_line
        sub_part = ""

    words = main_part.strip().split()
    supertypes = [w for w in words if w in supertypes_set]
    card_types = [w for w in words if w in card_types_set]
    subtypes = sub_part.strip().split() if sub_part.strip() else []

    return supertypes, card_types, subtypes


def convert_to_card(
    candidate: ReprintCandidate,
    slot_id: str,
    set_code: str,
    collector_number: str,
) -> Card:
    """Convert a ReprintCandidate to a Card model instance.

    Sets is_reprint=True and fills all required Card fields.
    """
    colors = [_COLOR_MAP[c] for c in candidate.colors if c in _COLOR_MAP]
    rarity = _RARITY_MAP.get(candidate.rarity, Rarity.COMMON)
    supertypes, card_types, subtypes = _parse_card_types(candidate.type_line)

    return Card(
        name=candidate.name,
        mana_cost=candidate.mana_cost,
        cmc=candidate.cmc,
        colors=colors,
        color_identity=colors,
        type_line=candidate.type_line,
        supertypes=supertypes,
        card_types=card_types,
        subtypes=subtypes,
        oracle_text=candidate.oracle_text,
        power=candidate.power,
        toughness=candidate.toughness,
        collector_number=collector_number,
        rarity=rarity,
        set_code=set_code,
        is_reprint=True,
        slot_id=slot_id,
        design_notes=f"Reprint selected from {candidate.source} pool",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
