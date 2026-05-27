"""Shared prompt-context block formatters for the skeleton stage's LLM passes.

The relabel (``skeleton_relabel``) and the phase-0 knob tuner
(``skeleton_knobs_tuner``) both frame the same set context — setting prose,
approved mechanics, draft archetypes, constraints, card requests — for the model.
These formatters are the single source of that framing so the two passes stay
consistent. Pure functions over the raw ``theme.json`` / ``approved.json`` /
``archetypes.json`` shapes; no I/O.
"""

from __future__ import annotations

from typing import Any


def format_setting_block(theme: dict) -> str:
    one_liner = (theme.get("theme") or "").strip()
    prose = (theme.get("flavor_description") or theme.get("setting") or "").strip()
    parts = [p for p in (one_liner, prose) if p]
    return "\n\n".join(parts) if parts else "(no setting provided)"


def format_mechanics_block(approved: list[Any]) -> str:
    """Render approved mechanics with their effect, framed as floors/caps."""
    if not approved:
        return "(no named mechanics — work from the set's flavor only)"
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


def format_archetypes_block(archetypes: list[Any]) -> str:
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


def format_constraints_block(constraints: list[Any]) -> str:
    if not constraints:
        return "(no special constraints — keep the default's standard shape)"
    lines: list[str] = []
    for c in constraints:
        text = c.get("text") if isinstance(c, dict) else c
        if text:
            lines.append(f"- {text}")
    return "\n".join(lines) if lines else "(no special constraints)"


def format_card_requests(requests: list[Any]) -> str:
    lines: list[str] = []
    for i, req in enumerate(requests, 1):
        text = req.get("text") if isinstance(req, dict) else req
        if text:
            lines.append(f"{i}. {text}")
    return "\n".join(lines) if lines else "(none)"
