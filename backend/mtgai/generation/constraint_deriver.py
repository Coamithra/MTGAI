"""Constraint derivation — the pre-generation skeleton relabel pass.

Wired into the pipeline as the ``constraints`` stage (between ``skeleton``
and ``reprints`` in ``STAGE_RUNNERS``). The runner in
``mtgai.pipeline.stages`` does the orchestration; this module owns the
two LLM passes, their tool-schema contracts, the seed→matrix reconcile,
and the LLM color-batcher that card generation uses to group the fluffy
blobs.

Design: ``plans/constraints-stage.md``. The deterministic ``skeleton``
stage writes a generic, balanced seed (``skeleton.json``); this stage
RELABELS it into a *themed* matrix — each slot a free-text tag blob —
so the card generator's slots already carry the setting's structural +
flavor guidance. ``slot_id`` is the stable join key: ``skeleton.json``
stays the structured seed (``reprints`` / ``lands`` read it untouched),
while this stage writes a parallel **``constraints.json``**:

    { "model_id", "cost_usd", "seed_slot_count",
      "slots": [ {"slot_id", "blob", "reserved_card"}, … ] }

Two passes (kept separate — Pass 1 reasons about whole-set distribution,
Pass 2 is a cheaper matching problem over a finalized matrix):

* **Pass 1 (relabel)** — hand the model the seed as N tagged lines + the
  setting / mechanics / archetypes / constraints; it rewrites each slot's
  tags to fit the set. Count is invariant by construction (N in, N out,
  reconciled by ``slot_id``); the only hard check is "got every slot back".
* **Pass 2 (assign)** — place each ``theme.json`` ``card_request`` onto the
  best-fitting slot by ``slot_id`` and rewrite that slot's blob to embody it.

Mirrors ``archetype_generator.py`` in shape; templates live next door in
``mtgai/pipeline/prompts/``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from mtgai.generation.llm_client import cost_from_result, generate_with_tool

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "pipeline" / "prompts"

_COLOR_FULL: dict[str, str] = {
    "W": "White",
    "U": "Blue",
    "B": "Black",
    "R": "Red",
    "G": "Green",
    "multicolor": "Multicolor",
    "colorless": "Colorless",
}


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

RELABEL_TOOL_SCHEMA: dict = {
    "name": "submit_themed_matrix",
    "description": (
        "Submit the relabeled set skeleton — exactly one entry per seed slot, "
        "addressed by its slot_id, each a free-text tag blob."
    ),
    "input_schema": {
        "type": "object",
        "required": ["slots"],
        "properties": {
            "slots": {
                "type": "array",
                "description": "One relabeled slot per seed slot, same slot_ids.",
                "items": {
                    "type": "object",
                    "required": ["slot_id", "blob"],
                    "properties": {
                        "slot_id": {
                            "type": "string",
                            "description": "The seed slot's id, unchanged (e.g. 'U-C-04').",
                        },
                        "blob": {
                            "type": "string",
                            "description": (
                                "Free-text role tags for this slot: color, rarity, type, "
                                "rough CMC, mechanic menu, archetype/faction, a one-line "
                                "role, legendary/named when relevant. No ability text or stats."
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
        "Submit the placement of each requested card onto a matrix slot — one "
        "entry per request, each naming the chosen slot_id and the rewritten blob."
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
                    "required": ["request", "slot_id", "blob"],
                    "properties": {
                        "request": {
                            "type": "string",
                            "description": "The requested card text, verbatim.",
                        },
                        "slot_id": {
                            "type": "string",
                            "description": "The matrix slot this request is placed in.",
                        },
                        "blob": {
                            "type": "string",
                            "description": "The chosen slot's blob, rewritten to become this card.",
                        },
                    },
                },
            },
        },
    },
}

BATCH_TOOL_SCHEMA: dict = {
    "name": "submit_slot_groups",
    "description": (
        "Group the matrix slots for coherent batch card generation: same-color / "
        "same-archetype siblings together, every slot_id appearing exactly once."
    ),
    "input_schema": {
        "type": "object",
        "required": ["groups"],
        "properties": {
            "groups": {
                "type": "array",
                "description": "Each group is a list of slot_ids generated together.",
                "items": {"type": "array", "items": {"type": "string"}},
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
        return "(no special constraints — keep the seed's standard shape)"
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


def render_seed_matrix(slots: list[dict]) -> str:
    """Render the seed slots as one tagged line each (Pass-1 input)."""
    lines: list[str] = []
    for s in slots:
        color = _COLOR_FULL.get(s.get("color", ""), s.get("color", "?"))
        parts = [
            str(s.get("slot_id", "?")),
            color,
            str(s.get("rarity", "?")),
            str(s.get("card_type", "?")),
            f"CMC{s.get('cmc_target', '?')}",
            str(s.get("mechanic_tag", "")),
        ]
        line = " | ".join(parts)
        if s.get("signpost_for"):
            line += f" | signpost: {s['signpost_for']}"
        note = (s.get("reserved_card") or s.get("notes") or "").strip()
        if note:
            line += f" | seed-note: {note}"
        lines.append(line)
    return "\n".join(lines)


def _format_matrix_blobs(matrix: list[dict]) -> str:
    return "\n".join(f"{m['slot_id']}: {m['blob']}" for m in matrix)


# ---------------------------------------------------------------------------
# Pass 1: relabel the seed into a themed matrix
# ---------------------------------------------------------------------------


def relabel_matrix(
    *,
    seed_slots: list[dict],
    theme: dict,
    approved: list[dict],
    archetypes: list[dict],
    set_name: str,
    set_size: int,
    model: str,
    log_dir: Path | None = None,
) -> tuple[list[dict], dict]:
    """Run Pass 1. Returns (matrix, usage) where matrix is one {slot_id, blob}
    per seed slot (reconciled — every seed slot present, extras dropped)."""
    system_prompt = _read_template("constraints_relabel_system.txt").format(
        set_name=set_name or "(unnamed set)",
        set_size=set_size,
        setting_block=_format_setting_block(theme),
        mechanics_block=_format_mechanics_block(approved),
        archetypes_block=_format_archetypes_block(archetypes),
        constraints_block=_format_constraints_block(
            theme.get("constraints") or theme.get("special_constraints") or []
        ),
    )
    user_prompt = _read_template("constraints_relabel_user.txt").format(
        slot_count=len(seed_slots),
        seed_matrix=render_seed_matrix(seed_slots),
    )

    response = generate_with_tool(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_schema=RELABEL_TOOL_SCHEMA,
        model=model,
        temperature=1.0,
        max_tokens=16384,
        log_dir=log_dir,
    )
    raw = response["result"].get("slots") or []
    by_id: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("slot_id") or "").strip()
        blob = str(item.get("blob") or "").strip()
        if sid and blob and sid not in by_id:
            by_id[sid] = blob

    # Reconcile by slot_id: every seed slot gets a blob (fall back to its seed
    # line so the count guarantee holds even if the model drops a slot).
    matrix: list[dict] = []
    missing = 0
    for s in seed_slots:
        sid = str(s.get("slot_id"))
        blob = by_id.get(sid)
        if blob is None:
            missing += 1
            blob = render_seed_matrix([s]).split(" | ", 1)[-1]
        matrix.append({"slot_id": sid, "blob": blob, "reserved_card": None})
    if missing:
        logger.warning("Pass 1 dropped %d/%d slots; filled from seed", missing, len(seed_slots))
    return matrix, response


# ---------------------------------------------------------------------------
# Pass 2: assign card requests to slots
# ---------------------------------------------------------------------------


def assign_requests(
    *,
    matrix: list[dict],
    card_requests: list[Any],
    model: str,
    log_dir: Path | None = None,
) -> tuple[list[dict], dict | None]:
    """Run Pass 2 in place. Returns (matrix, usage); usage is None when there
    are no requests to place (no LLM call)."""
    reqs = [r for r in (card_requests or []) if (r.get("text") if isinstance(r, dict) else r)]
    if not reqs:
        return matrix, None

    system_prompt = _read_template("constraints_assign_system.txt")
    user_prompt = _read_template("constraints_assign_user.txt").format(
        request_count=len(reqs),
        slot_count=len(matrix),
        card_requests=_format_card_requests(reqs),
        matrix_blobs=_format_matrix_blobs(matrix),
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
    by_id = {m["slot_id"]: m for m in matrix}
    taken: set[str] = set()
    for a in response["result"].get("assignments") or []:
        if not isinstance(a, dict):
            continue
        sid = str(a.get("slot_id") or "").strip()
        req = str(a.get("request") or "").strip()
        blob = str(a.get("blob") or "").strip()
        slot = by_id.get(sid)
        if slot is None or sid in taken or not req:
            logger.warning("Pass 2 assignment skipped (slot=%r, request=%r)", sid, req[:40])
            continue
        taken.add(sid)
        slot["reserved_card"] = req
        if blob:
            slot["blob"] = blob
    return matrix, response


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def derive_constraints(
    *,
    theme: dict | None = None,
    approved: list[dict] | None = None,
    archetypes: list[dict] | None = None,
    seed: dict | None = None,
) -> dict:
    """Derive the themed constraint matrix for the active project.

    Reads ``skeleton.json`` (seed) + ``theme.json`` + ``mechanics/approved.json``
    + ``archetypes.json`` from the active project unless passed in. Returns::

        {
            "slots": [ {"slot_id", "blob", "reserved_card"}, … ],
            "seed_slot_count": int,
            "model_id": str,
            "input_tokens": int, "output_tokens": int,
            "cost_usd": float,
        }
    """
    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    settings = project.settings
    model_id = settings.get_llm_model_id("constraints")
    asset_dir = set_artifact_dir()
    log_dir = asset_dir / "constraints" / "logs"

    if seed is None:
        seed_path = asset_dir / "skeleton.json"
        if not seed_path.exists():
            raise RuntimeError(f"skeleton.json not found at {seed_path} — run skeleton first")
        seed = json.loads(seed_path.read_text(encoding="utf-8"))
    assert seed is not None
    seed_slots = seed.get("slots") or []
    if not seed_slots:
        raise RuntimeError("skeleton.json has no slots")

    if theme is None:
        theme_path = asset_dir / "theme.json"
        theme = json.loads(theme_path.read_text(encoding="utf-8")) if theme_path.exists() else {}
    assert theme is not None

    if approved is None:
        approved_path = asset_dir / "mechanics" / "approved.json"
        loaded = (
            json.loads(approved_path.read_text(encoding="utf-8"))
            if approved_path.exists()
            else []
        )
        approved = loaded if isinstance(loaded, list) else []

    if archetypes is None:
        from mtgai.generation.archetype_generator import load_archetypes

        archetypes = load_archetypes(asset_dir)

    sp = settings.set_params
    logger.info(
        "Deriving constraints (model=%s, seed=%d slots, mechanics=%d, requests=%d)",
        model_id,
        len(seed_slots),
        len(approved),
        len(theme.get("card_requests") or []),
    )

    matrix, relabel_resp = relabel_matrix(
        seed_slots=seed_slots,
        theme=theme,
        approved=approved,
        archetypes=archetypes,
        set_name=sp.set_name or project.set_code or "Custom Set",
        set_size=sp.set_size or len(seed_slots),
        model=model_id,
        log_dir=log_dir,
    )
    matrix, assign_resp = assign_requests(
        matrix=matrix,
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

    return {
        "slots": matrix,
        "seed_slot_count": len(seed_slots),
        "model_id": model_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost,
    }


# ---------------------------------------------------------------------------
# On-disk loader (card generation consumes this)
# ---------------------------------------------------------------------------


def load_constraints_matrix(asset_dir: Path | None = None) -> list[dict] | None:
    """Load the themed matrix slots from ``constraints.json``.

    Returns the ``slots`` list ([{slot_id, blob, reserved_card}]) or ``None``
    when the file is absent — card generation falls back to the structured
    skeleton path in that case (backward-compat for sets generated before this
    stage existed).
    """
    if asset_dir is None:
        from mtgai.io.asset_paths import set_artifact_dir

        asset_dir = set_artifact_dir()
    path = asset_dir / "constraints.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    slots = data.get("slots") if isinstance(data, dict) else None
    return slots if isinstance(slots, list) and slots else None


# ---------------------------------------------------------------------------
# LLM color-batcher — groups the fluffy blobs for coherent card generation
# ---------------------------------------------------------------------------


def llm_group_slots(
    matrix_slots: list[dict],
    *,
    batch_size: int,
    model: str,
    log_dir: Path | None = None,
) -> list[list[str]]:
    """Group matrix slot_ids into batches for card generation.

    The seed's programmatic color key is gone (color is prose in the blob now),
    so an LLM sorts the blobs into color/archetype-coherent groups of about
    ``batch_size``. Reconciled so every input slot_id appears exactly once;
    falls back to ordered chunking if the call fails or returns nothing.
    """
    ids = [m["slot_id"] for m in matrix_slots]
    if len(ids) <= batch_size:
        return [ids] if ids else []

    def _chunk(seq: list[str]) -> list[list[str]]:
        return [seq[i : i + batch_size] for i in range(0, len(seq), batch_size)]

    system_prompt = (
        "You group Magic: The Gathering card slots for batch generation. Put "
        "slots that share a color and draft archetype together so siblings are "
        f"designed in the same call. Aim for groups of about {batch_size} slots "
        "(never more). Every slot_id must appear in exactly one group; do not "
        "invent slot_ids. Return only the groups through the tool."
    )
    user_prompt = "Slots to group:\n" + _format_matrix_blobs(matrix_slots)

    try:
        response = generate_with_tool(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tool_schema=BATCH_TOOL_SCHEMA,
            model=model,
            temperature=0.3,
            max_tokens=8192,
            log_dir=log_dir,
        )
        raw_groups = response["result"].get("groups") or []
    except Exception as exc:  # batching is an optimization — never block card-gen
        logger.warning("LLM slot-grouping failed (%s); falling back to ordered chunks", exc)
        return _chunk(ids)

    valid = set(ids)
    seen: set[str] = set()
    groups: list[list[str]] = []
    for g in raw_groups:
        if not isinstance(g, list):
            continue
        members = [str(x) for x in g if str(x) in valid and str(x) not in seen]
        if not members:
            continue
        for i in range(0, len(members), batch_size):
            chunk = members[i : i + batch_size]
            groups.append(chunk)
            seen.update(chunk)
    leftover = [sid for sid in ids if sid not in seen]
    groups.extend(_chunk(leftover))
    return groups or _chunk(ids)
