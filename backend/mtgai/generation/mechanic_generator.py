"""Mechanic candidate generation — driven by ``theme.json`` + ``set_params``.

Wired into the pipeline as the ``mechanics`` stage (first entry in
``STAGE_RUNNERS``). The runner in ``mtgai.pipeline.stages`` does the
orchestration; this module owns the prompt assembly, tool-schema
contract, post-processing (color pie + known-keyword collision check),
and the sidecar generators that the wizard's save handler invokes.

Templates live next door:

* ``mtgai/pipeline/prompts/mechanic_system.txt`` — system prompt
* ``mtgai/pipeline/prompts/mechanic_user_single.txt`` — per-call user prompt
  (one mechanic at a time, threading the already-accepted ones)
* ``mtgai/pipeline/templates/mtg_known_keywords.json`` — collision list
* ``mtgai/pipeline/templates/evergreen_keywords.json`` — per-color defaults
* ``mtgai/pipeline/templates/pointed_questions.json``  — review questions
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeGuard

from mtgai.generation.llm_client import generate_with_tool
from mtgai.generation.token_budgets import HEAVY, STANDARD
from mtgai.generation.token_utils import OutputTruncatedError
from mtgai.io.atomic import atomic_write_text

# Per-mechanic streaming hook signatures. Engine path wires these to
# ``StageEmitter.event`` (SSE), the wizard's refresh endpoints wire them to
# ``event_bus.publish`` directly. All are optional — None means no-op.
ResetHook = Callable[[], None]
DraftHook = Callable[[int, dict], None]
FinalizedHook = Callable[[int, dict, str], None]  # (position, mechanic, review_notes)
# Fine-grained council progress, so the wizard can show the review happening
# (reviewer thumbs appearing, synth revisions popping in) instead of a card
# sitting on "Reviewing…" for the whole multi-round loop. ``CouncilHook`` is
# what ``council_review`` calls with a bare event payload (it has no slot
# context); ``CouncilProgressHook`` is the ``generate_mechanic_candidates``
# variant that prepends the 1-based slot ``position``.
CouncilHook = Callable[[dict], None]
CouncilProgressHook = Callable[[int, dict], None]  # (position, event)

logger = logging.getLogger(__name__)

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent / "pipeline"
_PROMPTS_DIR = _PIPELINE_ROOT / "prompts"
_TEMPLATES_DIR = _PIPELINE_ROOT / "templates"

# Maximum number of mechanics a user may select for a single set — a sanity
# cap so the candidate pool (twice this, see ``candidate_count``) stays bounded.
MAX_MECHANIC_COUNT = 6

# ---------------------------------------------------------------------------
# Council review tuning (the per-candidate quality gate; see council_review)
# ---------------------------------------------------------------------------

# Reviewers per round. Always-full-council (no tiering) — every candidate gets
# all three independent critiques + synthesis. Mirrors the card council
# (``review.ai_review._review_council``), theme-free here.
MECHANIC_COUNCIL_SIZE = 3

# Revise-in-place rounds (synth → council re-review) before a still-REVISE
# mechanic is discarded and regenerated from scratch. Matches the validated lab
# default (``mtg-mech-lab`` --iterations 3).
MAX_MECHANIC_REVIEW_ITERATIONS = 3

# From-scratch regenerations of one slot (threading the council's reasons) after
# the revise loop gives up, before the best-effort mechanic is accepted flagged.
# Kept low — each regen is a full fresh council, the stage's dominant cost.
MAX_MECHANIC_REGEN_ATTEMPTS = 1

# Sampling temperatures. Generation at 0.9 (the lab found 0.9 beats 1.1 — 1.1
# clustered designs + degraded templating without adding novelty). Reviewers at
# 0.4 so the three critiques are not identical; synth at 0.2 (a careful edit).
MECHANIC_GEN_TEMP = 0.9
MECHANIC_REVIEW_TEMP = 0.4
MECHANIC_SYNTH_TEMP = 0.2


class _EscalatingBudget:
    """A ``max_tokens`` budget that ratchets up to a ceiling on the first
    output-truncation and then *stays there* for the rest of the run.

    Local reasoning models — especially aggressive quants like UD-IQ2_M — can
    spend the whole ``STANDARD`` budget on chain-of-thought and never emit the
    tool call (``finish_reason=length`` with empty output; see
    ``learnings/reasoning-budget-overrun.md``). Retrying at the *same* budget
    just hits the same wall, and starting every later candidate slot back at
    ``STANDARD`` re-pays the fail-then-bump tax once per slot (and again per
    council reviewer). This holder makes the bump **sticky for the whole
    phase**: the first overrun anywhere in one ``generate_mechanic_candidates``
    run raises the budget to the ceiling for every subsequent LLM call in that
    run, so we pay the overrun-then-retry cost at most once.
    """

    def __init__(self, base: int = HEAVY, ceiling: int = HEAVY) -> None:
        # Default base == ceiling: every mechanic-stage call (gen + each council
        # reviewer) was overrunning the STANDARD budget in practice, so we start
        # at the ceiling and skip the fail-then-bump tax. `escalate` is then a
        # no-op for a default-constructed budget; the ratchet machinery survives
        # only for callers that explicitly pass a lower `base`.
        self.current = base
        self.ceiling = ceiling

    def escalate(self) -> bool:
        """Raise the budget to the ceiling. Returns ``True`` if this actually
        changed it (so retrying is worthwhile), ``False`` if already capped."""
        if self.current >= self.ceiling:
            return False
        self.current = self.ceiling
        return True


def _generate_with_escalation(budget: _EscalatingBudget, **kwargs: Any) -> dict:
    """:func:`generate_with_tool` at ``budget.current``; on a reasoning overrun,
    escalate the (shared) budget and retry once at the ceiling.

    Re-raises :class:`OutputTruncatedError` if the call still truncates at the
    ceiling, or if the budget was already there — the caller's own retry/skip
    logic then takes over. Any non-truncation error propagates unchanged.
    Only the llamacpp path raises ``OutputTruncatedError`` (the failure mode
    this guards); the Anthropic path is unaffected.
    """
    base = budget.current
    try:
        return generate_with_tool(max_tokens=base, **kwargs)
    except OutputTruncatedError:
        if not budget.escalate():
            raise
        logger.warning(
            "Mechanic LLM call overran its %d-token budget on reasoning; "
            "escalating to %d for the rest of this run",
            base,
            budget.current,
        )
        return generate_with_tool(max_tokens=budget.current, **kwargs)


# Issue categories the reviewers + synth tag findings with — the concrete-defect
# standards plus an escape hatch. Drives the reviewer/synth tool schemas. The
# old taste categories `interesting` / `unique` are deliberately gone: the
# council gates on "is it broken?", not "is it excellent?", so it never rejects
# a mechanic merely for being simple, familiar, or unoriginal.
MECHANIC_ISSUE_CATEGORIES = [
    "playable",
    "wording",
    "self_consistent",
    "elegant",
    "other",
]

# The subset of categories whose presence makes a REVISE actually block. These
# are concrete, fixable faults that leave a mechanic unworkable or rules-wrong.
# `elegant` is intentionally absent -- mild bloat / wordiness is advisory, not a
# fail. A reviewer that votes REVISE but cites only `elegant` (or no issue at
# all) is treated as a soft pass. See `_effective_verdict` / `council_review`.
MECHANIC_BLOCKING_CATEGORIES: frozenset[str] = frozenset(
    {"playable", "wording", "self_consistent", "other"}
)


def candidate_count(mechanic_count: int) -> int:
    """Size of the candidate pool to generate for a given selection count.

    Twice the number the user will pick — enough slack for genuine choice
    and for dropping the occasional malformed local-model candidate.
    """
    return max(1, mechanic_count * 2)


# ---------------------------------------------------------------------------
# Tool schema: defines the structured output the LLM must return
# ---------------------------------------------------------------------------

# A single mechanic object — extracted so the review tool can reuse the exact
# same shape the generator emits. Keep ``MECHANIC_ITEM_SCHEMA`` and the
# generator's array-item schema in lockstep; if either drifts the review pass
# can produce mechanics card-gen can't read.
MECHANIC_ITEM_SCHEMA: dict = {
    "type": "object",
    "required": [
        "name",
        "keyword_type",
        "reminder_text",
        "colors",
        "complexity",
        "design_rationale",
        "example_cards",
    ],
    "properties": {},  # filled in below after we've defined the field shapes
}


MECHANIC_TOOL_SCHEMA: dict = {
    "name": "submit_mechanic_candidates",
    "description": (
        "Submit a list of mechanic candidates for the custom MTG set. "
        "Each mechanic must include all required fields."
    ),
    "input_schema": {
        "type": "object",
        "required": ["mechanics"],
        "properties": {
            "mechanics": {
                "type": "array",
                "description": "List of mechanic candidates",
                "items": {
                    "type": "object",
                    "required": [
                        "name",
                        "keyword_type",
                        "reminder_text",
                        "colors",
                        "complexity",
                        "design_rationale",
                        "example_cards",
                    ],
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The mechanic keyword name",
                        },
                        "keyword_type": {
                            "type": "string",
                            "enum": [
                                "keyword_ability",
                                "ability_word",
                                "keyword_action",
                            ],
                            "description": "Type of keyword",
                        },
                        "reminder_text": {
                            "type": "string",
                            "description": "Reminder text in parentheses, under 100 chars",
                        },
                        "colors": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["W", "U", "B", "R", "G"],
                            },
                            "description": "Colors this mechanic appears in",
                        },
                        "complexity": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 3,
                            "description": "1=common-viable, 2=uncommon+, 3=rare+",
                        },
                        "design_rationale": {
                            "type": "string",
                            "description": "Why this mechanic is good for the set",
                        },
                        "example_cards": {
                            "type": "array",
                            "minItems": 2,
                            "maxItems": 2,
                            "description": (
                                "EXACTLY TWO concrete example cards that use this mechanic, "
                                "showcasing how it appears on real cards. Pick contrasting "
                                "rarities (e.g. one common showing the simple version, and one "
                                "rare/mythic showing a richer expression) so card generation "
                                "has reference designs across the rarity range. Each example "
                                "must have complete, valid MTG templating."
                            ),
                            "items": {
                                "type": "object",
                                "required": [
                                    "name",
                                    "mana_cost",
                                    "type_line",
                                    "rarity",
                                    "oracle_text",
                                ],
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "description": "Card name.",
                                    },
                                    "mana_cost": {
                                        "type": "string",
                                        "description": (
                                            "MTG mana cost with braces, e.g. '{2}{G}' "
                                            "or '' for lands."
                                        ),
                                    },
                                    "type_line": {
                                        "type": "string",
                                        "description": (
                                            "Full type line, e.g. 'Creature — Human Wizard' "
                                            "or 'Instant'."
                                        ),
                                    },
                                    "rarity": {
                                        "type": "string",
                                        "enum": [
                                            "common",
                                            "uncommon",
                                            "rare",
                                            "mythic",
                                        ],
                                    },
                                    "oracle_text": {
                                        "type": "string",
                                        "description": (
                                            "Complete oracle text with proper MTG templating. "
                                            "Include the mechanic keyword and any other abilities. "
                                            "Do NOT include reminder text in parentheses — it is "
                                            "injected automatically downstream."
                                        ),
                                    },
                                    "power": {
                                        "type": "string",
                                        "description": "Power, creatures only (e.g. '2', '*').",
                                    },
                                    "toughness": {
                                        "type": "string",
                                        "description": "Toughness, creatures only.",
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}


# Populate the single-item schema from the generator's array-item shape so the
# two stay locked together by construction. (Done lazily here so we don't have
# to define every field twice.)
MECHANIC_ITEM_SCHEMA["properties"] = MECHANIC_TOOL_SCHEMA["input_schema"]["properties"][
    "mechanics"
]["items"]["properties"]


# One critique entry from a single council reviewer — the problem, its
# category (a concrete-defect standard or the "other" escape hatch), and severity.
_MECHANIC_ISSUE_SCHEMA: dict = {
    "type": "object",
    "required": ["category", "severity", "scope", "description"],
    "properties": {
        "category": {"type": "string", "enum": MECHANIC_ISSUE_CATEGORIES},
        "severity": {"type": "string", "enum": ["minor", "major"]},
        "scope": {
            "type": "string",
            "enum": ["example", "mechanic"],
            "description": (
                'Where the defect lives. "example" = one example CARD is '
                "implemented wrong while the keyword's rule and wording are fine "
                '(fixable by rewriting that card alone). "mechanic" = the '
                "keyword's rule, reminder text, cost/trigger, colors, or "
                "complexity is wrong (the definition itself must change). When "
                'unsure, choose "mechanic".'
            ),
        },
        "description": {
            "type": "string",
            "description": "One sentence: the problem, concretely.",
        },
    },
}


# Tool schema for ONE council reviewer (Phase 1). Each member independently
# returns a verdict + a list of concrete issues — no mechanic re-emit, so the
# output stays bounded (the heavy re-emit lives in the synth tool below).
MECHANIC_REVIEWER_TOOL_SCHEMA: dict = {
    "name": "submit_mechanic_review",
    "description": "Submit your independent critique of one mechanic.",
    "input_schema": {
        "type": "object",
        "required": ["verdict", "issues"],
        "properties": {
            "verdict": {"type": "string", "enum": ["OK", "REVISE"]},
            "issues": {"type": "array", "items": _MECHANIC_ISSUE_SCHEMA},
        },
    },
}


# A consensus issue the synth chose to act on, with how many reviewers raised it.
_MECHANIC_CONSENSUS_ISSUE_SCHEMA: dict = {
    "type": "object",
    "required": ["category", "agreement", "description"],
    "properties": {
        "category": {"type": "string", "enum": MECHANIC_ISSUE_CATEGORIES},
        "agreement": {
            "type": "integer",
            "description": "How many of the council's reviewers raised this issue.",
        },
        "description": {"type": "string"},
    },
}


# Tool schema for the synthesizer (Phase 2). It applies a >=2-of-N consensus
# filter and re-emits the whole improved mechanic in one call — the heavy shape
# the synth runs at the HEAVY token budget (see council_review). ``verdict`` is
# the synth's self-assessment, but the loop trusts only the *reviewers'*
# consensus to exit OK, so a re-review always follows a revision.
MECHANIC_SYNTH_TOOL_SCHEMA: dict = {
    "name": "submit_mechanic_synthesis",
    "description": (
        "Synthesize the council's reviews into one consensus decision and an improved mechanic."
    ),
    "input_schema": {
        "type": "object",
        "required": [
            "synthesis",
            "consensus_issues",
            "revised_mechanic",
            "verdict",
            "review_notes",
        ],
        "properties": {
            "synthesis": {
                "type": "string",
                "description": "Brief: what the council agreed on.",
            },
            "consensus_issues": {
                "type": "array",
                "items": _MECHANIC_CONSENSUS_ISSUE_SCHEMA,
            },
            "revised_mechanic": MECHANIC_ITEM_SCHEMA,
            "verdict": {
                "type": "string",
                "enum": ["OK", "REVISE"],
                "description": (
                    "Is the REVISED mechanic now excellent (OK) or still wanting (REVISE)?"
                ),
            },
            "review_notes": {
                "type": "string",
                "description": (
                    "One or two sentences: what you changed and why. Empty if unchanged."
                ),
            },
        },
    },
}


# Tool schema for the narrow example-fix call (the examples-only branch of the
# council loop). When EVERY blocking defect a round is example-scoped — the
# keyword itself is sound, only an example card implements it wrong — we fix
# ONLY the examples instead of running the full synth re-emit. The model returns
# exactly two replacement example cards (the same shape the generator emits) and
# never sees or re-states the mechanic's definition, so the keyword's name /
# reminder_text / colors / etc. are pinned by construction (we splice the new
# examples onto the unchanged mechanic). This kills the regression where a synth,
# asked to fix a bad example, gratuitously rewrites a sound reminder.
MECHANIC_EXAMPLES_TOOL_SCHEMA: dict = {
    "name": "submit_mechanic_examples",
    "description": (
        "Submit two replacement example cards that fix the council's issues with "
        "the examples. Do not restate or change the mechanic itself."
    ),
    "input_schema": {
        "type": "object",
        "required": ["example_cards", "notes"],
        "properties": {
            "example_cards": MECHANIC_TOOL_SCHEMA["input_schema"]["properties"]["mechanics"][
                "items"
            ]["properties"]["example_cards"],
            "notes": {
                "type": "string",
                "description": (
                    "One sentence: what you changed in the examples and why. Empty if unchanged."
                ),
            },
        },
    },
}


# Tool schema for the AI picker: selects the best N from a candidate pool.
MECHANIC_PICK_TOOL_SCHEMA: dict = {
    "name": "select_best_mechanics",
    "description": (
        "Select the best mechanics from the candidate pool for this set, "
        "with a one-line reason per pick and an overall rationale for the slate."
    ),
    "input_schema": {
        "type": "object",
        "required": ["selections", "overall_rationale"],
        "properties": {
            "selections": {
                "type": "array",
                "description": "The chosen mechanics, by candidate number.",
                "items": {
                    "type": "object",
                    "required": ["candidate_number", "reason"],
                    "properties": {
                        "candidate_number": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "1-based number of the candidate from the list.",
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence on why this candidate earned a slot.",
                        },
                    },
                },
            },
            "overall_rationale": {
                "type": "string",
                "description": (
                    "Short rationale for the slate as a whole — color spread, "
                    "complexity mix, and how the picks work together."
                ),
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


def _read_template(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def _render(template: str, /, **mapping: object) -> str:
    """Literal ``{key}`` substitution (NOT ``str.format``).

    The mechanic prompts teach Magic templating, so they contain literal mana
    braces — ``{T}``, ``{2}{U}``, ``Equip {2}`` — that ``str.format`` would try
    to interpret as fields and crash on. This replaces only the keys we pass and
    leaves every other brace untouched. Mirrors ``mtg-mech-lab``'s ``render``.
    """
    out = template
    for key, val in mapping.items():
        out = out.replace("{" + key + "}", str(val))
    return out


def _format_setting_block(theme: dict) -> str:
    """The setting prose for the prompt's single 'Setting' field.

    Handles both schemas: the current toolchain writes the world document to
    ``setting``; legacy ASD themes use a short ``theme`` one-liner plus a
    ``flavor_description`` prose blob. We surface the one-liner (if any) then
    the prose, so neither schema loses content — and there's no dead
    "(no flavor description provided)" subsection when only ``setting`` exists.
    """
    one_liner = (theme.get("theme") or "").strip()
    prose = (theme.get("flavor_description") or theme.get("setting") or "").strip()
    parts = [p for p in (one_liner, prose) if p]
    return "\n\n".join(parts) if parts else "(no setting provided)"


def _format_archetypes_block(archetypes: list[Any]) -> str:
    """Render the draft-archetype list, or ``""`` when there are none.

    Returns empty so the builder can omit the whole "## Draft archetypes"
    section rather than print a misleading placeholder. In the toolchain
    pipeline mechanics are designed *before* archetypes exist (archetypes are
    derived from the mechanics downstream), so this is empty for new sets;
    legacy ASD themes that carry ``draft_archetypes`` still render here.
    """
    lines: list[str] = []
    for arch in archetypes or []:
        if not isinstance(arch, dict):
            continue
        colors = arch.get("color_pair") or arch.get("colors") or ""
        name = arch.get("name") or ""
        desc = arch.get("description") or ""
        if name and desc:
            lines.append(f"- {colors}: {name} — {desc}".lstrip())
        elif name:
            lines.append(f"- {colors}: {name}".lstrip())
    return "\n".join(lines)


def _archetypes_section(archetypes: list[Any]) -> str:
    """Wrap the archetype list in its section header, or ``""`` when empty."""
    block = _format_archetypes_block(archetypes)
    return f"\n## Draft archetypes\n\n{block}\n" if block else ""


def _format_constraints_block(constraints: list[Any]) -> str:
    if not constraints:
        return "(no special constraints)"
    lines: list[str] = []
    for c in constraints:
        text = c.get("text") if isinstance(c, dict) else c
        if text:
            lines.append(f"- {text}")
    return "\n".join(lines) if lines else "(no special constraints)"


def _expected_mechanic_density(set_size: int, mechanic_count: int) -> str:
    """Rough target for cards-per-mechanic in this set.

    Total set / (mechanic_count * 2) — about half the set carries
    custom mechanics, the rest is reprints + lands + non-mechanic
    designs. Returned as a "min-max" string the prompt drops into
    its design constraints.
    """
    if mechanic_count <= 0:
        return "6-10"
    per = max(1, set_size // (mechanic_count * 2))
    return f"{per}-{per * 2}"


def _format_excluded_keywords(known: dict) -> str:
    """Comma-separated list across every known-keyword bucket."""
    items: list[str] = []
    for bucket in ("evergreen", "deciduous", "set_keywords", "ability_words", "token_keywords"):
        items.extend(known.get(bucket, []))
    seen: set[str] = set()
    out: list[str] = []
    for k in items:
        kl = k.lower()
        if kl not in seen:
            seen.add(kl)
            out.append(k)
    return ", ".join(out)


def build_mechanic_system_prompt(
    theme: dict,
    set_name: str,
    set_size: int,
    mechanic_count: int,
) -> str:
    """Render the mechanic-generation system prompt from theme + params.

    The user prompt is built per-call by :func:`build_single_mechanic_user_prompt`
    (one mechanic at a time, threading the already-accepted ones); only the
    system prompt is shared across the loop and worth caching.
    """
    sys_template = _read_template("mechanic_system.txt")
    known = load_known_keywords()
    expected_density = _expected_mechanic_density(set_size, mechanic_count)

    # ``_render`` (literal replace), not ``.format`` — the template now teaches
    # Magic templating and carries literal braces (``Equip {2}``, ``{T}``).
    return _render(
        sys_template,
        set_name=set_name or "(unnamed set)",
        set_size=set_size,
        mechanic_count=mechanic_count,
        setting_block=_format_setting_block(theme),
        archetypes_block=_archetypes_section(theme.get("draft_archetypes") or []),
        constraints_block=_format_constraints_block(
            theme.get("constraints") or theme.get("special_constraints") or []
        ),
        excluded_keywords=_format_excluded_keywords(known),
        expected_mechanic_density=expected_density,
    )


def _format_candidate_digest(candidates: list[dict]) -> str:
    """Render the candidate pool as a numbered list for the picker prompt.

    One block per candidate — number, name, type, colors, complexity, plus
    reminder text and rationale — so the LLM can weigh the slate. The
    1-based numbering is what the pick tool's ``candidate_number`` field
    refers back to (mapped to a 0-based index in :func:`pick_best_mechanics`).
    """
    if not candidates:
        return "(no candidates)"
    lines: list[str] = []
    for i, m in enumerate(candidates, 1):
        m = m or {}
        name = (m.get("name") or "?").strip() or "?"
        colors = "".join(m.get("colors") or []) or "colorless"
        cx = m.get("complexity", "?")
        ktype = m.get("keyword_type") or "?"
        lines.append(f"{i}. {name} — type: {ktype}; colors: {colors}; complexity: {cx}")
        reminder = (m.get("reminder_text") or "").strip()
        if reminder:
            lines.append(f"   reminder: {reminder}")
        rationale = (m.get("design_rationale") or m.get("design_notes") or "").strip()
        if rationale:
            lines.append(f"   rationale: {rationale}")
    return "\n".join(lines)


def build_pick_prompts(
    theme: dict,
    set_name: str,
    set_size: int,
    mechanic_count: int,
    candidates: list[dict],
) -> tuple[str, str]:
    """Render the picker's system + user prompts from theme + the candidate pool.

    The system prompt carries the set context + the selection criteria;
    the user prompt carries the numbered candidate digest. Mirrors the
    generation prompts' split so the system block stays cache-friendly.
    """
    sys_template = _read_template("mechanic_pick_system.txt")
    user_template = _read_template("mechanic_pick_user.txt")

    system_prompt = sys_template.format(
        set_name=set_name or "(unnamed set)",
        set_size=set_size,
        mechanic_count=mechanic_count,
        setting_block=_format_setting_block(theme),
        archetypes_block=_archetypes_section(theme.get("draft_archetypes") or []),
        constraints_block=_format_constraints_block(
            theme.get("constraints") or theme.get("special_constraints") or []
        ),
    )
    user_prompt = user_template.format(
        mechanic_count=mechanic_count,
        candidate_digest=_format_candidate_digest(candidates),
    )
    return system_prompt, user_prompt


def _format_mechanic_for_review(mech: dict) -> str:
    """Render one draft mechanic as a labelled prose block for the reviewer.

    Deliberately verbose — the reviewer needs to *see* the mechanic the way a
    player or designer would, including the example cards' full text — so the
    block expands each field rather than dumping JSON. Example cards render
    with their mana cost, type line, rarity, oracle text, and P/T so the
    reviewer can judge whether each one actually uses the mechanic and is
    well-templated.
    """
    m = mech or {}
    colors = "".join(m.get("colors") or []) or "(colorless)"
    cx = m.get("complexity", "?")
    ktype = m.get("keyword_type") or "?"
    reminder = (m.get("reminder_text") or "").strip() or "(no reminder text)"
    rationale = (m.get("design_rationale") or "").strip() or "(no rationale)"
    examples = m.get("example_cards") or []
    lines = [
        f"Name: {m.get('name', '?')}",
        f"Keyword type: {ktype}",
        f"Colors: {colors}",
        f"Complexity: {cx}",
        f"Reminder text: {reminder}",
        f"Design rationale: {rationale}",
        "",
        "Example cards:",
    ]
    if not examples:
        lines.append("  (none provided — the schema requires exactly two)")
    for i, ex in enumerate(examples, 1):
        e = ex or {}
        name = e.get("name") or "(unnamed)"
        cost = e.get("mana_cost") or ""
        type_line = e.get("type_line") or "?"
        rarity = e.get("rarity") or "?"
        oracle = (e.get("oracle_text") or "").strip() or "(empty)"
        power = e.get("power")
        toughness = e.get("toughness")
        pt = (
            f" {power}/{toughness}"
            if power not in (None, "") and toughness not in (None, "")
            else ""
        )
        head = f"  {i}. {name}"
        if cost:
            head += f" {cost}"
        head += f"  —  {type_line}{pt}  ({rarity})"
        lines.append(head)
        # Indent oracle text so multi-line cards stay visually attached.
        for line in oracle.splitlines() or [oracle]:
            lines.append(f"     {line}")
    return "\n".join(lines)


def build_reviewer_prompts(mech: dict) -> tuple[str, str]:
    """System + user prompts for ONE council reviewer of ``mech``. Theme-free.

    The concrete-defect checklist lives in the (static) system prompt, shared
    with the synthesizer; the user prompt is just the rendered mechanic block, so the
    prompt cache stays warm across the council's calls and the reviewer never
    sees the setting — the deliberate anti-"but it fits the theme!" guard.
    """
    system_prompt = _read_template("mechanic_review_system.txt")
    user_prompt = _render(
        _read_template("mechanic_review_user.txt"),
        mechanic_block=_format_mechanic_for_review(mech),
    )
    return system_prompt, user_prompt


def _format_reviews_block(reviews: list[dict]) -> str:
    """Render the council's critiques as the synth prompt's ``reviews_block``."""
    lines: list[str] = []
    for i, r in enumerate(reviews, 1):
        lines.append(f"### Reviewer {i} — verdict: {r.get('verdict', '?')}")
        issues = r.get("issues") or []
        if not issues:
            lines.append("  (no issues raised)")
        for iss in issues:
            lines.append(
                f"  - [{iss.get('category', '?')}/{iss.get('severity', '?')}] "
                f"{iss.get('description', '')}"
            )
    return "\n".join(lines)


def build_synth_prompts(mech: dict, reviews: list[dict]) -> tuple[str, str]:
    """System + user prompts for the synthesizer.

    Shares the reviewer's system prompt (the concrete-defect standards); the
    user prompt carries the mechanic, the council's critiques, and the consensus-filter +
    revise-in-place instructions.
    """
    system_prompt = _read_template("mechanic_review_system.txt")
    user_prompt = _render(
        _read_template("mechanic_synth_user.txt"),
        mechanic_block=_format_mechanic_for_review(mech),
        reviews_block=_format_reviews_block(reviews),
        council_size=len(reviews),
    )
    return system_prompt, user_prompt


def _format_example_issues_block(issues: list[dict]) -> str:
    """Render the example-scoped blocking issues as the example-fix prompt's
    ``issues_block`` — a flat bullet list of what's wrong with the examples."""
    lines = [f"  - {iss.get('description', '')}" for iss in issues]
    return "\n".join(lines) or "  (none)"


def build_examples_prompts(mech: dict, issues: list[dict]) -> tuple[str, str]:
    """System + user prompts for the narrow example-fix call.

    Shares the reviewer/synth system prompt (the concrete-defect standards, the
    templating rules, and the card-defined-effect shape) so the new examples are
    held to the same bar. The user prompt shows the mechanic and its current
    examples for context plus the council's complaints, and asks ONLY for two
    replacement example cards — the mechanic definition is deliberately not
    requested, so it cannot be changed.
    """
    system_prompt = _read_template("mechanic_review_system.txt")
    user_prompt = _render(
        _read_template("mechanic_examples_user.txt"),
        mechanic_block=_format_mechanic_for_review(mech),
        issues_block=_format_example_issues_block(issues),
    )
    return system_prompt, user_prompt


def _tokens(resp: dict) -> tuple[int, int]:
    """``(input_tokens, output_tokens)`` from a ``generate_with_tool`` response."""
    return resp.get("input_tokens", 0) or 0, resp.get("output_tokens", 0) or 0


def _effective_verdict(review: dict) -> str:
    """One reviewer's *gating* verdict: ``"REVISE"`` only when it both voted
    REVISE and cited at least one **major** blocking defect (a blocking category
    — see :data:`MECHANIC_BLOCKING_CATEGORIES` — at ``severity == "major"``);
    otherwise ``"OK"``. ``minor`` issues are advisory and never gate.

    This is what makes the council an "is it broken?" gate rather than an "is it
    excellent?" one: a REVISE whose only complaints are advisory (``elegant``),
    or that lists no concrete issue at all, does not block. The taste categories
    that used to drive nearly every REVISE (``interesting`` / ``unique``) no
    longer exist, so a simple, familiar, or unexciting-but-workable mechanic
    passes.
    """
    if review.get("verdict") != "REVISE":
        return "OK"
    for iss in review.get("issues") or []:
        # Severity-weighted: only a MAJOR blocking defect gates. A `minor`
        # blocking issue (a nit — e.g. "omit the word 'token'") is advisory and
        # never blocks; it is surfaced but does not force a REVISE. This is what
        # stops a sound mechanic churning to death on trivial wording.
        if iss.get("category") in MECHANIC_BLOCKING_CATEGORIES and iss.get("severity") == "major":
            return "REVISE"
    return "OK"


def _open_issue_reasons(reviews: list[dict]) -> list[str]:
    """Distinct open-issue descriptions from one council round.

    Threaded into a from-scratch regenerate so the next draft avoids the same
    problems (the ``card_gen`` regenerate-with-reason pattern). Only blocking
    defects (see :data:`MECHANIC_BLOCKING_CATEGORIES`) steer a regen — advisory
    ``elegant`` nitpicks are dropped so the next draft isn't redesigned on taste.
    Major issues first, deduped, and capped so the gen prompt stays lean.
    """
    major: list[str] = []
    minor: list[str] = []
    seen: set[str] = set()
    for r in reviews:
        if _effective_verdict(r) == "OK":
            continue
        for iss in r.get("issues") or []:
            if iss.get("category") not in MECHANIC_BLOCKING_CATEGORIES:
                continue
            desc = (iss.get("description") or "").strip()
            if not desc or desc.lower() in seen:
                continue
            seen.add(desc.lower())
            (major if iss.get("severity") == "major" else minor).append(desc)
    return (major + minor)[:6]


def _blocking_issues(reviews: list[dict]) -> list[dict]:
    """The round's blocking defects — major-severity issues in a blocking category
    — across all reviewers, in the order raised.

    These are the issues that actually force a revise round (mirrors the
    ``open_major`` gate and :func:`_effective_verdict`). Their ``scope`` decides
    how the loop revises: see :func:`_all_example_scoped`.
    """
    out: list[dict] = []
    for r in reviews:
        for iss in r.get("issues") or []:
            if (
                iss.get("category") in MECHANIC_BLOCKING_CATEGORIES
                and iss.get("severity") == "major"
            ):
                out.append(iss)
    return out


def _all_example_scoped(issues: list[dict]) -> bool:
    """True iff every issue is explicitly ``scope == "example"`` (and there is at
    least one).

    A missing or unrecognised scope counts as *not* example-scoped — the safe
    default routes to the full synth, which can never *cause* a missed-fix (it
    just may rewrite more than strictly necessary). So the narrow example-only
    path is taken ONLY when the council is unanimous that the keyword itself is
    sound and only its example cards are at fault.
    """
    return bool(issues) and all(iss.get("scope") == "example" for iss in issues)


def _call_synth(
    mech: dict,
    reviews: list[dict],
    model_id: str,
    temperature: float,
    log_dir: Path | None,
) -> dict | None:
    """Up to two synthesis calls at the HEAVY budget; ``None`` on failure / empty output.

    No ``repeat_penalty`` escalation: per ``learnings/reasoning-budget-overrun.md``
    the synth's truncation was reasoning-budget overrun (mitigated by the HEAVY
    budget, ~2x the ~8k tokens it actually needs to re-emit the whole mechanic),
    NOT a token-level repetition loop, and is verified *not* fixed by
    ``repeat_penalty``. The provider default (1.1) still applies. We do retry the
    call once at the same budget/temp: a truncated/empty synth is sometimes a
    non-deterministic miss that a second attempt clears cheaply. A hard reasoning
    spiral reproduces and still returns ``None`` -> the council keeps the current
    mechanic at REVISE and the caller's regenerate-from-scratch fallback takes over.
    """
    from mtgai.runtime import ai_lock

    system_prompt, user_prompt = build_synth_prompts(mech, reviews)
    for attempt in range(2):  # one same-params retry; see docstring
        if attempt and ai_lock.is_cancelled():
            break
        try:
            resp = generate_with_tool(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tool_schema=MECHANIC_SYNTH_TOOL_SCHEMA,
                model=model_id,
                temperature=temperature,
                max_tokens=HEAVY,
                log_dir=log_dir,
            )
        except Exception as exc:
            logger.warning(
                "Council synth attempt %d failed: %s: %s",
                attempt + 1,
                type(exc).__name__,
                exc,
            )
            continue
        if not (resp.get("result") or {}).get("revised_mechanic"):
            logger.warning("Council synth attempt %d emitted no revised_mechanic", attempt + 1)
            continue
        return resp
    logger.warning("Council synth produced no usable revision; keeping current mechanic")
    return None


def _call_example_fix(
    mech: dict,
    issues: list[dict],
    model_id: str,
    temperature: float,
    log_dir: Path | None,
) -> dict | None:
    """One narrow example-fix call; ``None`` on failure / not exactly two examples.

    The examples-only branch of the council loop (taken when every blocking
    defect is example-scoped). Far cheaper than :func:`_call_synth` — it re-emits
    only two example cards, never the mechanic — and structurally cannot regress
    the keyword's definition, since that definition is not in the request. A
    malformed / wrong-count result returns ``None`` → the council keeps the
    current mechanic at REVISE, exactly like a failed synth.
    """
    system_prompt, user_prompt = build_examples_prompts(mech, issues)
    try:
        resp = generate_with_tool(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tool_schema=MECHANIC_EXAMPLES_TOOL_SCHEMA,
            model=model_id,
            temperature=temperature,
            max_tokens=HEAVY,
            log_dir=log_dir,
        )
    except Exception as exc:
        logger.warning("Council example-fix failed: %s: %s", type(exc).__name__, exc)
        return None
    examples = (resp.get("result") or {}).get("example_cards")
    if not isinstance(examples, list) or len(examples) != 2:
        logger.warning(
            "Council example-fix emitted %s example cards (need exactly 2); "
            "keeping current mechanic",
            len(examples) if isinstance(examples, list) else "no",
        )
        return None
    return resp


def _is_well_formed_revision(m: Any) -> TypeGuard[dict]:
    """Is a synth-revised mechanic usable, or did the re-emit drop/blank fields?

    The synth re-emits the whole mechanic in one heavy call, and a flaky local
    model (or JSON repair) can return a dict that parses but lost what matters.
    Require a non-blank ``name`` and a non-blank ``reminder_text`` — the keyword's
    definition, which ``reminder_injector`` stamps onto cards downstream, so a
    blank one is a hard regression. (Same name + definition bar the generator's
    ``_is_valid_candidate`` holds new drafts to.) A revision that fails is
    discarded so the prior mechanic is kept — a bad synth never degrades a draft
    below what the council already had.
    """
    if not isinstance(m, dict):
        return False
    name = m.get("name")
    reminder = m.get("reminder_text")
    if not isinstance(name, str) or not name.strip():
        return False
    return isinstance(reminder, str) and bool(reminder.strip())


def council_review(
    draft: dict,
    *,
    model_id: str,
    log_dir: Path | None = None,
    council_size: int = MECHANIC_COUNCIL_SIZE,
    max_iterations: int = MAX_MECHANIC_REVIEW_ITERATIONS,
    review_temp: float = MECHANIC_REVIEW_TEMP,
    synth_temp: float = MECHANIC_SYNTH_TEMP,
    on_event: CouncilHook | None = None,
    budget: _EscalatingBudget | None = None,
    skip_final_synth: bool = False,
) -> dict:
    """Council + revise-in-place loop for one draft mechanic (theme-free).

    Modelled on the card council (``review.ai_review._review_council``) and the
    validated ``mtg-mech-lab`` ``review_one`` (with one deliberate divergence: a
    failed reviewer is skipped rather than fatal, so the verdict is decided by the
    *surviving* reviewers — local models drop calls often enough that a strict
    all-N-succeed gate would stall):

      1. ``council_size`` independent reviewers critique the current mechanic.
      2. No open MAJOR blocking defect -> done; the mechanic stands (the cheap,
         common path). The council gates on "is it broken?", not "is it
         excellent?": only a *major* defect in a blocking category (see
         :func:`_effective_verdict`) gates; `minor` nits and advisory `elegant`
         are surfaced but never block, so a workable mechanic passes even if
         imperfectly worded. Conversely a single concrete major defect from any
         reviewer blocks -- it cannot be outvoted (objective defects, e.g. a
         dead-on-use example, must not lose to reviewers who missed them).
      3. Else the synthesizer applies a >=2-of-N consensus filter and re-emits an
         improved mechanic (a HEAVY-budget call, retried once on a truncated/empty
         miss — see :func:`_call_synth`).
      4. Re-review the revision; repeat until the *reviewers* agree OK or the
         iteration budget runs out. The synth's own verdict is NOT trusted to end
         the loop — it over-claims fixes (~1/3 regress) — so a revision always
         faces a fresh council before it can pass.

    Every call is best-effort: a failed reviewer is skipped; a failed synth keeps
    the current mechanic (left REVISE for the caller's regenerate fallback). A bad
    review pass never destroys a good draft, and the mechanic's name is never
    changed (anti-rename guard). Polls ``ai_lock.is_cancelled()`` between calls so
    the Cancel button halts a long council.

    ``on_event`` (optional, best-effort) fires fine-grained progress payloads so
    the UI can show the review happening live: ``round_start`` at the top of each
    round, ``reviewer`` as each reviewer returns (``verdict`` OK / REVISE / error),
    ``synth_start`` before the synthesizer runs, and ``synth_done`` with the revised
    mechanic when it lands. A hook exception is logged and swallowed.

    ``budget`` is the run-shared :class:`_EscalatingBudget` for the reviewer
    calls; ``generate_mechanic_candidates`` passes its own so a reasoning
    overrun escalates the *whole* run, not just this council. A standalone call
    (none given) gets a fresh one. The synth always runs at the HEAVY ceiling
    (:func:`_call_synth`), so it needs no budget threading.

    ``skip_final_synth`` (set by the caller when a from-scratch regen will follow
    a still-REVISE result): skip the Phase-2 synth on the *final* round, since its
    revision would be discarded by the regen (which re-drafts from the reviewers'
    ``reasons``). Left ``False`` on the last attempt — where the caller keeps this
    revision best-effort — so the synth still runs there.

    Returns::

        {
            "mechanic": dict,           # final (possibly revised) mechanic
            "verdict": "OK" | "REVISE",
            "review_notes": str,        # synth changelog(s), empty if unchanged
            "reasons": list[str],       # last round's open issues (for a regen)
            "input_tokens": int,
            "output_tokens": int,
        }
    """
    from mtgai.runtime import ai_lock

    # Standalone call gets its own budget; the generator passes its run-shared one.
    budget = budget or _EscalatingBudget()

    def _emit(payload: dict) -> None:
        """Fire a council-progress event, swallowing any hook error."""
        if on_event is None:
            return
        try:
            on_event(payload)
        except Exception:
            logger.exception("council on_event hook raised; continuing")

    original_name = (draft.get("name") or "").strip()
    mechanic = draft
    notes: list[str] = []
    reasons: list[str] = []
    total_in = total_out = 0
    verdict = "OK"

    for _round in range(1, max_iterations + 1):
        if ai_lock.is_cancelled():
            break
        _emit(
            {
                "kind": "round_start",
                "round": _round,
                "max_rounds": max_iterations,
                "council_size": council_size,
            }
        )

        # Phase 1 — independent reviewers (each best-effort; a failure is skipped).
        reviews: list[dict] = []
        for member in range(1, council_size + 1):
            if ai_lock.is_cancelled():
                break
            sys_p, user_p = build_reviewer_prompts(mechanic)
            try:
                resp = _generate_with_escalation(
                    budget,
                    system_prompt=sys_p,
                    user_prompt=user_p,
                    tool_schema=MECHANIC_REVIEWER_TOOL_SCHEMA,
                    model=model_id,
                    temperature=review_temp,
                    log_dir=log_dir,
                )
            except Exception as exc:
                logger.warning(
                    "Council reviewer %d failed: %s: %s", member, type(exc).__name__, exc
                )
                _emit(
                    {
                        "kind": "reviewer",
                        "round": _round,
                        "member": member,
                        "council_size": council_size,
                        "verdict": "error",
                    }
                )
                continue
            r = resp.get("result") or {}
            review = {"verdict": r.get("verdict", "OK"), "issues": r.get("issues") or []}
            reviews.append(review)
            # The UI thumb shows the *effective* (gating) verdict, so a passing
            # mechanic never displays a stray REVISE thumb for a taste-only or
            # empty nitpick that doesn't actually block.
            member_verdict = _effective_verdict(review)
            in_t, out_t = _tokens(resp)
            total_in += in_t
            total_out += out_t
            _emit(
                {
                    "kind": "reviewer",
                    "round": _round,
                    "member": member,
                    "council_size": council_size,
                    "verdict": member_verdict,
                }
            )

        # Open issues from this round, in case it ends still-REVISE and the
        # caller regenerates from scratch. These critique the mechanic as it
        # entered this round; if the round's synth then revises it without a
        # re-review (the budget-exhausted case), the reasons may be slightly
        # stale relative to the returned mechanic — fine as regen guidance.
        reasons = _open_issue_reasons(reviews)

        # Pass when NO surviving reviewer raises an open MAJOR blocking defect.
        # Severity-weighted (see `_effective_verdict`): `minor` nits and advisory
        # `elegant` never block, so a sound-but-imperfectly-worded mechanic passes
        # round 1 (this kills the trivial-wording churn). But a single concrete
        # MAJOR defect from ANY reviewer blocks -- it cannot be outvoted, because
        # such defects are objective/verifiable and a lone correct catch (e.g. a
        # dead-on-use example) must not lose to reviewers who missed it. The old
        # gate first required all-OK (unhittable at the ~0% taste-era OK rate),
        # then a simple majority (which silently outvoted real major defects);
        # this fixes both. A collapsed council (no usable reviews) keeps the
        # un-reviewable draft rather than destroying it (safe fallback).
        open_major = sum(1 for rv in reviews if _effective_verdict(rv) == "REVISE")
        if not reviews or open_major == 0:
            verdict = "OK"
            reasons = []
            break

        # Phase 2 — synthesis (consensus filter + revise-in-place).
        # Skip the synth on the FINAL round when the caller will regenerate from
        # scratch anyway (skip_final_synth): the regen re-drafts from the
        # reviewers' `reasons` and discards the synth's revision, so the HEAVY
        # synth call would be pure waste. On the last attempt (no regen left) the
        # caller keeps this revision best-effort, so skip_final_synth is False
        # and the synth still runs. `reasons` was already set above for the regen.
        if skip_final_synth and _round == max_iterations:
            verdict = "REVISE"
            break
        if ai_lock.is_cancelled():
            verdict = "REVISE"
            break

        # Route by the SCOPE of the blocking defects. When EVERY blocking issue
        # is example-scoped -- the council agrees the keyword itself is sound and
        # only an example card implements it wrong -- fix ONLY the examples: a
        # cheap call that re-emits two example cards spliced onto the unchanged
        # mechanic. The definition (name / reminder_text / colors / ...) is
        # pinned by construction, so a sound reminder can't be gratuitously
        # rewritten while "fixing" a bad example (the regression this guards).
        # Any mechanic-scoped defect (or a missing scope, which defaults to
        # mechanic) falls through to the full synth below.
        blocking = _blocking_issues(reviews)
        if _all_example_scoped(blocking):
            _emit({"kind": "synth_start", "round": _round})
            fresp = _call_example_fix(mechanic, blocking, model_id, synth_temp, log_dir)
            if fresp is None:
                verdict = "REVISE"
                break
            in_t, out_t = _tokens(fresp)
            total_in += in_t
            total_out += out_t
            f = fresp.get("result") or {}
            # Structural pin: splice the new examples onto the original mechanic;
            # every other field stays exactly as the council reviewed it.
            mechanic = {**mechanic, "example_cards": f.get("example_cards")}
            note = (f.get("notes") or "").strip()
            if note:
                notes.append(note)
            _emit(
                {
                    "kind": "synth_done",
                    "round": _round,
                    "mechanic": mechanic,
                    "review_notes": note,
                }
            )
            # Don't trust a self-verdict to exit; re-review next round.
            verdict = "REVISE"
            continue

        # Phase 2 -- synthesis (consensus filter + revise-in-place), for a
        # mechanic-scoped defect: re-emit the whole improved mechanic.
        _emit({"kind": "synth_start", "round": _round})
        sresp = _call_synth(mechanic, reviews, model_id, synth_temp, log_dir)
        if sresp is None:
            verdict = "REVISE"
            break
        in_t, out_t = _tokens(sresp)
        total_in += in_t
        total_out += out_t
        s = sresp.get("result") or {}
        revised = s.get("revised_mechanic")
        # Only take the revision if it's well-formed — a synth that dropped/blanked
        # fields must not degrade the draft below what the council already had.
        if _is_well_formed_revision(revised):
            rev_name = (revised.get("name") or "").strip()
            if original_name and rev_name and rev_name.lower() != original_name.lower():
                revised["name"] = original_name  # anti-rename guard
            mechanic = revised
        elif revised is not None:
            logger.warning(
                "Council synth revision was malformed (blank name or reminder_text); "
                "keeping the prior mechanic"
            )
        note = (s.get("review_notes") or "").strip()
        if note:
            notes.append(note)
        # Surface the (possibly) revised mechanic so the UI can pop the new text
        # in immediately — even though the loop won't trust the synth's verdict.
        _emit(
            {
                "kind": "synth_done",
                "round": _round,
                "mechanic": mechanic,
                "review_notes": note,
            }
        )
        # Don't trust the synth's self-verdict to exit — it over-claims. Mark
        # REVISE and let the next round's council re-review; if this was the last
        # round, the unconfirmed revision is honestly left REVISE.
        verdict = "REVISE"

    return {
        "mechanic": mechanic,
        "verdict": verdict,
        "review_notes": " ".join(notes),
        "reasons": reasons,
        "input_tokens": total_in,
        "output_tokens": total_out,
    }


def _format_already_designed(accepted: list[dict]) -> str:
    """Render the accepted-so-far mechanics as a rich 'vary from these' block.

    Since the trimmed output schema freed up the token budget, we surface
    the full picture of each prior mechanic — colors, complexity, type,
    reminder text, rationale — so the model can *see* the distribution so
    far (e.g. "all complexity 1, all UBR") and deliberately diverge instead
    of clustering.
    """
    if not accepted:
        return "No mechanics have been designed yet — this is the first candidate."
    lines = [
        "Mechanics already designed for this set so far. Your new mechanic must be "
        "clearly DISTINCT from all of these — deliberately vary the color identity, "
        "complexity, and mechanical space; do NOT cluster around what is already here:",
    ]
    for i, m in enumerate(accepted, 1):
        name = m.get("name") or "?"
        colors = "".join(m.get("colors") or []) or "colorless"
        cx = m.get("complexity", "?")
        ktype = m.get("keyword_type") or "?"
        lines.append(f"{i}. {name} — {colors}, complexity {cx}, {ktype}")
        reminder = (m.get("reminder_text") or "").strip()
        if reminder:
            lines.append(f"   text: {reminder}")
        rationale = (m.get("design_rationale") or "").strip()
        if rationale:
            lines.append(f"   rationale: {rationale}")
    return "\n".join(lines)


def _needed_hint(accepted: list[dict], remaining: int, enforce_simple_floor: bool) -> str:
    """Adaptive nudge to preserve the spread the batch prompt used to guarantee.

    The single strongest invariant from the old batch prompt was 'at least
    one complexity-1 (common-viable) mechanic'. If none exists yet and we're
    running low on remaining slots, force this one to fill that gap. Only
    applies when building a full pool (``enforce_simple_floor``) — a targeted
    refresh of one slot shouldn't be biased toward simple designs.
    """
    if not enforce_simple_floor:
        return ""
    has_simple = any(m.get("complexity") == 1 for m in accepted)
    if not has_simple and remaining <= 2:
        return (
            "- IMPORTANT: none of the mechanics so far are complexity 1, and the set "
            "needs at least one. Make THIS mechanic complexity 1 — simple enough to be "
            "viable at common with short reminder text."
        )
    return ""


def _format_regen_block(reasons: list[str]) -> str:
    """Render the council's reasons for discarding a prior attempt at this slot.

    Threaded into a from-scratch regenerate (the ``card_gen`` regenerate-with-
    reason pattern) so the next draft avoids the same problems. Empty when this
    is a first attempt (no prior council failure).
    """
    if not reasons:
        return ""
    bullets = "\n".join(f"  - {r}" for r in reasons)
    return (
        "\n\nA PREVIOUS attempt at this slot was rejected by the design council. "
        "Design a genuinely DIFFERENT mechanic that avoids these problems:\n" + bullets
    )


def build_single_mechanic_user_prompt(
    *,
    accepted: list[dict],
    position: int,
    target: int,
    mechanic_count: int,
    set_size: int,
    expected_density: str,
    enforce_simple_floor: bool = True,
    regen_reasons: list[str] | None = None,
) -> str:
    """Render the per-call user prompt asking for ONE distinct mechanic.

    The system prompt (theme/flavor/constraints) is unchanged and shared
    across every call in the loop; only this user prompt varies, threading
    the already-accepted mechanics so the model avoids repeats. ``regen_reasons``
    (when this slot is being regenerated from scratch after the council rejected
    a prior attempt) are surfaced so the new draft avoids the same failures.
    """
    template = _read_template("mechanic_user_single.txt")
    remaining = max(0, target - len(accepted))
    return template.format(
        position=position,
        target=target,
        mechanic_count=mechanic_count,
        set_size=set_size,
        expected_mechanic_density=expected_density,
        already_block=_format_already_designed(accepted),
        needed_hint=_needed_hint(accepted, remaining, enforce_simple_floor),
        regen_block=_format_regen_block(regen_reasons or []),
    )


# Bracket placeholders the prompts explicitly forbid in reminder text
# (`[effect]`, `[cost]`, `[target]`, `{cost}`, ...). Square brackets never appear
# in real Magic templating, so any `[...]` group is forbidden; for braces we match
# only a 2+-lowercase-letter run so genuine mana/loyalty symbols ({W}, {2}, {T},
# {W/U}, {X}, {C}, {E}) are never flagged while word placeholders ({cost},
# {effect}) are. See mechanic_system.txt:63 / mechanic_review_system.txt:41.
_PLACEHOLDER_RE = re.compile(r"\[[^\]]+\]|\{[^}]*[a-z]{2,}[^}]*\}")


def _add_reject_reason(reasons: list[str], reason: str) -> None:
    """Append a retry-feedback reason, de-duplicating so repeated rejections of
    the same kind don't pile identical lines into the next prompt."""
    if reason not in reasons:
        reasons.append(reason)


def _forbidden_placeholder(reminder_text: Any) -> str | None:
    """Return the first forbidden bracket placeholder in ``reminder_text``, else ``None``.

    The generator is told never to emit a `[effect]`/`[cost]` placeholder (the
    payoff of a card-defined-effect mechanic lives on the card, not as a reminder
    placeholder), but the weak local quant slips one in regularly. Catching it
    deterministically at draft validation re-rolls the slot immediately instead
    of spending a full council round + a spiral-prone synth on a defect the
    reviewer would (correctly) flag anyway.
    """
    if not isinstance(reminder_text, str):
        return None
    m = _PLACEHOLDER_RE.search(reminder_text)
    return m.group(0) if m else None


def _is_valid_candidate(m: Any, seen_names: set[str], known: set[str]) -> bool:
    """Accept only well-formed, non-duplicate, non-colliding mechanic objects.

    Guards against the local-model JSON degradation that motivated the
    one-at-a-time loop: malformed entries (null/blank ``name``) and
    example-card debris promoted to the top level by JSON repair (which
    lack mechanic-level metadata) are rejected, as are duplicates.

    A candidate whose name matches a printed MTG keyword (``known``,
    lowercased) is rejected too, so the loop regenerates a replacement
    instead of keeping it: the wizard has no inline rename, so a colliding
    candidate is dead weight. This promotes the keyword collision from a
    soft warning to a hard reject — the system prompt already excludes
    known keywords, this is the backstop for the occasional slip-through.
    """
    if not isinstance(m, dict):
        return False
    name = m.get("name")
    if not isinstance(name, str) or not name.strip():
        return False
    normalized = name.strip().lower()
    if normalized in seen_names:
        return False
    if normalized in known:
        return False
    # A real mechanic carries design metadata an example card never would;
    # this distinguishes it from promoted example-card debris.
    return bool(m.get("reminder_text") or m.get("design_rationale"))


# ---------------------------------------------------------------------------
# Template loaders
# ---------------------------------------------------------------------------


def load_known_keywords() -> dict[str, list[str]]:
    """Per-bucket list of MTG keywords + ability words.

    Buckets: ``evergreen``, ``deciduous``, ``set_keywords``,
    ``ability_words``, ``token_keywords``.
    """
    path = _TEMPLATES_DIR / "mtg_known_keywords.json"
    return json.loads(path.read_text(encoding="utf-8"))


def known_keyword_set() -> set[str]:
    """Lowercase set of every known printed keyword for collision checks."""
    out: set[str] = set()
    for bucket in load_known_keywords().values():
        for k in bucket:
            out.add(k.lower())
    return out


def load_evergreen_defaults() -> dict[str, list[str]]:
    """Per-color default evergreen keyword list — written as a sidecar."""
    path = _TEMPLATES_DIR / "evergreen_keywords.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_pointed_questions_template() -> list[dict]:
    """Canonical questions with ``{mechanic_names}`` placeholder."""
    path = _TEMPLATES_DIR / "pointed_questions.json"
    return json.loads(path.read_text(encoding="utf-8"))


def render_pointed_questions(approved: list[dict]) -> list[dict]:
    """Substitute ``{mechanic_names}`` with the joined approved-mechanic names.

    Output shape matches what ``review/ai_review.py`` expects from the
    on-disk file — same keys, same types, just with the placeholders
    resolved per project.
    """
    names = ", ".join(m.get("name", "?") for m in approved)
    out: list[dict] = []
    for q in load_pointed_questions_template():
        rendered = dict(q)
        text = rendered.get("question", "")
        if "{mechanic_names}" in text:
            rendered["question"] = text.replace("{mechanic_names}", names)
        out.append(rendered)
    return out


# ---------------------------------------------------------------------------
# Color pie validation (kept; still useful for the candidates strip)
# ---------------------------------------------------------------------------

# Maps effect keywords to their primary/secondary colors
COLOR_PIE: dict[str, dict[str, str]] = {
    "direct_damage": {"R": "P"},
    "destroy_creature": {"W": "P", "B": "P", "G": "S"},
    "card_draw": {"U": "P", "B": "S", "W": "T", "G": "T"},
    "counterspell": {"U": "P"},
    "graveyard_recursion": {"B": "P", "W": "S", "G": "S"},
    "counters": {"G": "P", "W": "S", "U": "T"},
    "tokens": {"W": "P", "G": "P", "U": "S", "B": "S", "R": "S"},
    "life_gain": {"W": "P", "B": "S", "G": "S"},
    "mill": {"U": "P", "B": "S"},
    "discard": {"B": "P", "R": "S"},
    "artifact_synergy": {"U": "P", "W": "S", "R": "S"},
    "sacrifice": {"B": "P", "R": "S"},
    "ramp": {"G": "P", "R": "T"},
    "pump": {"W": "P", "R": "P", "G": "P", "B": "S"},
    "evasion": {"W": "P", "U": "P", "B": "S", "R": "S", "G": "T"},
    "enchantment_synergy": {"W": "P", "U": "S", "G": "S"},
}

EFFECT_KEYWORDS: dict[str, list[str]] = {
    "direct_damage": ["damage", "deals damage"],
    "destroy_creature": ["destroy", "destroys"],
    "card_draw": ["draw", "draws", "card advantage"],
    "counterspell": ["counter", "counters a spell"],
    "graveyard_recursion": [
        "graveyard",
        "return from graveyard",
        "recursion",
        "reanimate",
    ],
    "counters": ["+1/+1 counter", "counter on", "counters on"],
    "tokens": ["token", "create a", "create tokens"],
    "life_gain": ["gain life", "life gain", "lifelink"],
    "mill": ["mill", "into graveyard from library"],
    "discard": ["discard"],
    "artifact_synergy": ["artifact", "artifacts"],
    "sacrifice": ["sacrifice"],
    "ramp": ["mana", "add {", "search for a land"],
    "pump": ["+1/+0", "+2/+2", "+1/+1 until", "gets +"],
    "evasion": [
        "flying",
        "menace",
        "trample",
        "can't be blocked",
        "unblockable",
    ],
    "enchantment_synergy": ["enchantment", "enchantments", "aura"],
}


def validate_mechanic_color_pie(mechanic: dict) -> list[str]:
    """Check a mechanic candidate against color pie rules.

    Returns a list of warning/error strings. Empty list means the mechanic
    passes validation.
    """
    warnings: list[str] = []
    colors = mechanic.get("colors", [])
    if not colors:
        warnings.append("ERROR: Mechanic has no assigned colors")
        return warnings

    all_text_parts = [
        mechanic.get("reminder_text", ""),
        mechanic.get("design_rationale", ""),
    ]
    for pattern_key in ("common_patterns", "uncommon_patterns", "rare_patterns"):
        all_text_parts.extend(mechanic.get(pattern_key, []))
    for card in mechanic.get("example_cards", []):
        all_text_parts.append(card.get("oracle_text", ""))
    all_text = " ".join(all_text_parts).lower()

    for effect_name, keywords in EFFECT_KEYWORDS.items():
        if any(kw in all_text for kw in keywords):
            pie = COLOR_PIE.get(effect_name, {})
            has_primary_or_secondary = any(pie.get(c) in ("P", "S") for c in colors)
            if not has_primary_or_secondary and pie:
                has_tertiary = any(pie.get(c) == "T" for c in colors)
                if has_tertiary:
                    warnings.append(
                        f"WARN: '{effect_name}' is only tertiary in {colors} — use sparingly"
                    )
                else:
                    warnings.append(
                        f"NOTE: '{effect_name}' detected in text but not "
                        f"primary/secondary in {colors} — verify intent"
                    )

    reminder = mechanic.get("reminder_text", "")
    if len(reminder) > 100:
        warnings.append(f"ERROR: Reminder text is {len(reminder)} chars (max 100)")

    complexity = mechanic.get("complexity", 1)
    if complexity == 1 and not mechanic.get("common_patterns"):
        warnings.append("WARN: Complexity 1 mechanic should have common patterns")

    return warnings


def detect_keyword_collisions(candidates: list[dict]) -> dict[int, str]:
    """Flag candidates whose name collides with a printed MTG keyword.

    Returns ``{candidate_index: collision_keyword}`` so the wizard can
    surface the warning per-card without filtering — the user might still
    want to keep the candidate and rename it inline.
    """
    known = known_keyword_set()
    out: dict[int, str] = {}
    for idx, mech in enumerate(candidates):
        name = (mech.get("name") or "").strip()
        if not name:
            continue
        if name.lower() in known:
            out[idx] = name
    return out


# ---------------------------------------------------------------------------
# approved.json projection
# ---------------------------------------------------------------------------


_APPROVED_FIELDS: tuple[str, ...] = (
    "name",
    "keyword_type",
    "reminder_text",
    "colors",
    "complexity",
    # Two concrete reference cards per mechanic — the LLM generates them
    # alongside the mechanic and they propagate through to card generation
    # (rendered in ``format_mechanic_block``) as templating examples. Without
    # them card-gen tends to mis-use custom mechanics.
    "example_cards",
)


def candidate_to_approved(candidate: dict) -> dict:
    """Project a candidate dict to the on-disk ``approved.json`` shape.

    * Copies the ``_APPROVED_FIELDS`` whitelist (name, keyword_type,
      reminder_text, colors, complexity) — anything else the candidate
      carries is dropped.
    * Renames ``design_rationale`` → ``design_notes`` (downstream
      consumers read ``design_notes``).
    * Derives ``rarity_range`` from ``complexity`` (a soft "appears at"
      hint for the card-gen prompt). Actual rarity allocation is the
      skeleton stage's job, not the mechanic's.
    """
    out: dict = {}
    for key in _APPROVED_FIELDS:
        if key in candidate:
            out[key] = candidate[key]
    # Prefer the LLM's tool-schema field (``design_rationale``) over a
    # hand-edited ``design_notes``; the candidate strip surfaces the
    # rationale as the editable copy and there's no separate
    # ``design_notes`` editor today. Falling back the other way is just
    # defensive in case a future caller flips the field name back.
    out["design_notes"] = candidate.get("design_rationale") or candidate.get("design_notes", "")
    # A complexity-3 build-around won't sit at common; everything else can span
    # the whole range. This is only a hint — the skeleton owns real rarity counts.
    complexity = candidate.get("complexity", 1)
    if complexity >= 3:
        out["rarity_range"] = ["uncommon", "rare", "mythic"]
    else:
        out["rarity_range"] = ["common", "uncommon", "rare", "mythic"]
    return out


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------


def generate_mechanic_candidates(
    *,
    theme: dict | None = None,
    count: int | None = None,
    on_reset: ResetHook | None = None,
    on_draft: DraftHook | None = None,
    on_finalized: FinalizedHook | None = None,
    on_council: CouncilProgressHook | None = None,
) -> dict:
    """Generate mechanic candidates for the active project via LLM.

    Reads ``theme.json`` and ``set_params`` from the active project,
    assembles the prompts, and calls ``generate_with_tool``. Returns
    the raw response shape for callers that want token usage too::

        {
            "mechanics": list[dict],
            "input_tokens": int,
            "output_tokens": int,
            "model_id": str,
        }

    Generates ONE mechanic per slot rather than the whole pool at once:
    local models degrade on long structured output (a single big tool call
    returned syntactically-valid but semantically-shredded JSON once the
    generation grew long — clean first mechanic, junk by the third). Each
    short call stays coherent; we validate the result and drop malformed,
    duplicate, or keyword-colliding entries, feeding the accepted names back
    so the model avoids repeats.

    Each draft is then **gated by the full council** (:func:`council_review`) —
    3 theme-free reviewers sanity-checking it for concrete defects (a majority
    of effective-OK votes passes), with the synthesizer revising in place and
    the council re-reviewing, up to
    ``MAX_MECHANIC_REVIEW_ITERATIONS`` rounds. A draft the council passes is
    accepted; one still REVISE after the revise budget is **regenerated from
    scratch** (threading the council's reasons into the gen prompt) up to
    ``MAX_MECHANIC_REGEN_ATTEMPTS`` times, then accepted best-effort flagged
    REVISE so the slot still fills. The pool ends up (near-)all council-passing,
    which is what gives the downstream theme-fit pick real choice. Each
    mechanic carries ``_review_verdict`` + ``_review_notes`` for the wizard.
    No call ever raises out of the council; a bad pass keeps the current draft.

    Streaming: ``on_reset`` fires once before the first slot;
    ``on_draft(position, draft)`` fires for each draft (re-firing on a
    regenerated slot) before its council runs; ``on_council(position, event)``
    fires for each fine-grained council step (reviewer verdicts, synth
    revisions — see :func:`council_review`) so the UI can show the review in
    flight; ``on_finalized(position, mechanic, review_notes)`` fires once when
    the slot is accepted. All are optional. The engine path wires them to
    ``StageEmitter.event`` so the wizard streams candidates in live; the refresh
    endpoints wire them to ``event_bus.publish`` for the same effect on manual
    re-runs.

    Succeeds as long as at least ``mechanic_count`` candidates are collected
    (that's all the user picks); raises ``RuntimeError`` only if the pool can't
    reach that floor, or if generation fails repeatedly with nothing accepted.
    """
    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime import ai_lock
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    settings = project.settings
    sp = settings.set_params
    model_id = settings.get_llm_model_id("mechanics")
    # Base id for provenance/display (model_id above is the effective ctx twin).
    display_model_id = settings.get_assigned_model_id("mechanics")
    # llmfacade writes each call's JSONL+HTML transcript here (named after the
    # tool); it's the canonical per-call log — no bespoke logger needed.
    log_dir = set_artifact_dir() / "mechanics" / "logs"

    if theme is None:
        theme_path = set_artifact_dir() / "theme.json"
        if not theme_path.exists():
            raise RuntimeError(f"theme.json not found at {theme_path} — run theme extraction first")
        theme = json.loads(theme_path.read_text(encoding="utf-8"))
    assert theme is not None

    # System prompt (theme/flavor/constraints) is stable across the whole
    # loop and prompt-cache-friendly; only the per-call user prompt varies,
    # threading the already-accepted mechanics.
    system_prompt = build_mechanic_system_prompt(
        theme=theme,
        set_name=sp.set_name or project.set_code or "Custom Set",
        set_size=sp.set_size,
        mechanic_count=sp.mechanic_count,
    )
    expected_density = _expected_mechanic_density(sp.set_size, sp.mechanic_count)
    # Callers ask for exactly what they need: the stage / initial generation
    # wants the full pool (twice mechanic_count); the refresh-one endpoint wants 1.
    target = candidate_count(sp.mechanic_count) if count is None else max(1, count)
    floor = max(1, min(sp.mechanic_count, target))
    # The "must include a complexity-1 mechanic" floor is a whole-pool concern;
    # don't impose it on a targeted single-slot refresh (count given).
    enforce_simple_floor = count is None

    logger.info(
        "Generating %d council-gated mechanic candidate(s) one slot at a time "
        "(model=%s, set_size=%d, mech_count=%d, floor=%d)",
        target,
        model_id,
        sp.set_size,
        sp.mechanic_count,
        floor,
    )

    # Printed-keyword set for the hard collision reject below. Built once
    # (it reads a template file) and reused across every attempt.
    known_keywords = known_keyword_set()

    accepted: list[dict] = []
    seen_names: set[str] = set()
    total_in = 0
    total_out = 0
    last_error: str | None = None
    # Per-slot bound on generation retries to get one well-formed, non-duplicate,
    # non-colliding draft before this slot is treated as ungenerable.
    gen_retries = 3
    # Output-token budget for this run's gen + reviewer calls, shared so a single
    # reasoning overrun bumps every later call to HEAVY (see _EscalatingBudget).
    budget = _EscalatingBudget()

    # Reset hook fires once before any attempt — the UI uses this to clear the
    # candidate strip when a from-scratch generation starts. Safe to fire even
    # when ``on_reset`` is None.
    if on_reset is not None:
        try:
            on_reset()
        except Exception:
            logger.exception("on_reset hook raised; continuing")

    # Fill the pool one slot at a time. Each slot: design a draft → gate it
    # through the full council (revise-in-place loop) → accept on a council pass;
    # else regenerate from scratch (threading the council's reasons) up to
    # MAX_MECHANIC_REGEN_ATTEMPTS; after the budget, accept the best-effort
    # revision flagged REVISE. A slot always fills exactly once, so the loop
    # makes progress on every iteration (no separate attempt cap needed).
    while len(accepted) < target:
        if ai_lock.is_cancelled():
            logger.info("Mechanic generation cancelled after %d candidate(s)", len(accepted))
            break

        position = len(accepted) + 1
        regen_reasons: list[str] = []
        best_effort: dict | None = None
        best_notes = ""
        slot_done = False

        for regen in range(MAX_MECHANIC_REGEN_ATTEMPTS + 1):
            if ai_lock.is_cancelled():
                break

            # On a regeneration (not the first attempt), signal the UI BEFORE the
            # slow re-draft so the card shows "Regenerating…" instead of a frozen-
            # looking "Reviewing…" badge left over from the rejected council round.
            # Reuses the council channel (no new event type); cleared when the
            # fresh draft lands.
            if regen > 0 and on_council is not None:
                try:
                    on_council(position, {"kind": "regenerating", "attempt": regen + 1})
                except Exception:
                    logger.exception("on_council hook raised; continuing")

            # --- design one valid draft for this slot (bounded retries) ---
            draft: dict | None = None
            # Targeted feedback for an in-loop re-roll (e.g. a forbidden reminder
            # placeholder); merged with the outer regen reasons so the next draft
            # within this attempt sees why the last one was rejected.
            draft_reject_reasons: list[str] = []
            for _try in range(gen_retries):
                if ai_lock.is_cancelled():
                    break
                user_prompt = build_single_mechanic_user_prompt(
                    accepted=accepted,
                    position=position,
                    target=target,
                    mechanic_count=sp.mechanic_count,
                    set_size=sp.set_size,
                    expected_density=expected_density,
                    enforce_simple_floor=enforce_simple_floor,
                    regen_reasons=regen_reasons + draft_reject_reasons,
                )
                try:
                    response = _generate_with_escalation(
                        budget,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        tool_schema=MECHANIC_TOOL_SCHEMA,
                        model=model_id,
                        temperature=MECHANIC_GEN_TEMP,
                        log_dir=log_dir,
                    )
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    logger.warning("Mechanic generation call failed: %s", last_error)
                    continue
                total_in += response.get("input_tokens", 0) or 0
                total_out += response.get("output_tokens", 0) or 0
                # The gen tool returns a list, but the prompt asks for ONE; take
                # the first valid entry. Any extras are ignored (rare for a
                # one-at-a-time ask) so each slot gets its own council gate.
                for m in (response.get("result") or {}).get("mechanics") or []:
                    if not _is_valid_candidate(m, seen_names, known_keywords):
                        nm = m.get("name") if isinstance(m, dict) else None
                        nm_clean = nm.strip() if isinstance(nm, str) else ""
                        nm_norm = nm_clean.lower()
                        # Feed the name-rejection reason back into the next retry's
                        # prompt so the model stops re-proposing the same dead name.
                        # Without this, a model can fixate on one thematically-obvious
                        # name (e.g. "Reconfigure" for a robots set) and burn every
                        # retry re-submitting it, leaving the slot unfilled.
                        if nm_norm and nm_norm in known_keywords:
                            logger.info(
                                "Rejected mechanic %r - collides with a printed keyword; "
                                "regenerating",
                                nm_clean,
                            )
                            _add_reject_reason(
                                draft_reject_reasons,
                                f"The name {nm_clean!r} is already a printed Magic keyword and "
                                "cannot be reused. Invent a brand-new mechanic with a different, "
                                "original name.",
                            )
                        elif nm_norm and nm_norm in seen_names:
                            logger.info(
                                "Rejected mechanic %r - name already used by another candidate; "
                                "regenerating",
                                nm_clean,
                            )
                            _add_reject_reason(
                                draft_reject_reasons,
                                f"The name {nm_clean!r} is already taken by another mechanic in "
                                "this set. Choose a different, original name.",
                            )
                        continue
                    # Deterministic backstop for the forbidden-placeholder defect
                    # the weak quant slips in (e.g. `[effect]`): re-roll with
                    # targeted feedback rather than letting the malformed reminder
                    # burn a council round + the spiral-prone synth downstream.
                    bad = _forbidden_placeholder(m.get("reminder_text"))
                    if bad is not None:
                        logger.info(
                            "Rejected mechanic %r - forbidden placeholder %r in reminder "
                            "text; regenerating",
                            str(m.get("name") or "").strip(),
                            bad,
                        )
                        _add_reject_reason(
                            draft_reject_reasons,
                            f"The reminder text contained the forbidden placeholder {bad!r}. "
                            "Write the concrete wording instead - for a card-defined-effect "
                            "mechanic the reminder states ONLY the shared cost/trigger and each "
                            "example card writes its own effect; never a bracket placeholder.",
                        )
                        continue
                    draft = m
                    break
                if draft is not None:
                    break

            if draft is None:
                # Couldn't produce a valid draft this round; stop trying this slot.
                break

            # --- stream the draft, then gate it through the council ---
            if on_draft is not None:
                try:
                    on_draft(position, draft)
                except Exception:
                    logger.exception("on_draft hook raised; continuing")

            council = council_review(
                draft,
                model_id=model_id,
                log_dir=log_dir,
                budget=budget,
                # A regen still to come (regen < MAX) means a still-REVISE result
                # gets re-drafted from scratch, discarding the final-round synth --
                # so skip that wasted call. On the last attempt the synth's
                # revision is kept best-effort, so let it run.
                skip_final_synth=regen < MAX_MECHANIC_REGEN_ATTEMPTS,
                on_event=(
                    # ``council_review`` invokes this synchronously within the
                    # iteration, but bind ``position`` as a default so it's a
                    # value, not a late-bound free var (B023).
                    (lambda ev, _pos=position: on_council(_pos, ev))
                    if on_council is not None
                    else None
                ),
            )
            total_in += council["input_tokens"]
            total_out += council["output_tokens"]
            mech = council["mechanic"]
            mech["_review_verdict"] = council["verdict"]
            mech["_review_notes"] = council["review_notes"]

            if council["verdict"] == "OK":
                seen_names.add(str(mech.get("name") or "").strip().lower())
                accepted.append(mech)
                if on_finalized is not None:
                    try:
                        on_finalized(position, mech, council["review_notes"])
                    except Exception:
                        logger.exception("on_finalized hook raised; continuing")
                slot_done = True
                break

            # Still REVISE after the revise loop — keep as best-effort, thread the
            # council's reasons into the next from-scratch regeneration.
            best_effort = mech
            best_notes = council["review_notes"]
            regen_reasons = council["reasons"]
            if regen < MAX_MECHANIC_REGEN_ATTEMPTS:
                logger.info(
                    "Slot %d still REVISE after council; regenerating from scratch", position
                )

        if slot_done:
            continue

        # The council never reached OK for this slot. If it produced a best-effort
        # revision, accept it flagged REVISE — the slot still fills once (the
        # theme-fit picker prefers OK, and the pool is near-all-OK by construction).
        if best_effort is not None:
            logger.info(
                "Slot %d accepted best-effort (still REVISE) after the regen budget", position
            )
            seen_names.add(str(best_effort.get("name") or "").strip().lower())
            accepted.append(best_effort)
            if on_finalized is not None:
                try:
                    on_finalized(position, best_effort, best_notes)
                except Exception:
                    logger.exception("on_finalized hook raised; continuing")
            continue

        # Couldn't even generate a valid draft for this slot. Fail fast if nothing
        # has been accepted (dead provider / unusable model); otherwise stop and
        # proceed with what we have (the floor check below is the final gate).
        if not accepted:
            raise RuntimeError(
                f"Mechanic generation produced no valid candidate after {gen_retries} "
                f"attempt(s): {last_error}. The model may be returning malformed tool "
                "output — try a different mechanics model or re-run."
            )
        logger.warning(
            "Could not generate a valid draft for slot %d; proceeding with %d candidate(s)",
            position,
            len(accepted),
        )
        break

    if len(accepted) < floor:
        raise RuntimeError(
            f"Mechanic generation produced only {len(accepted)} valid candidate(s); "
            f"need at least {floor}. The model may be returning malformed tool output — "
            "try a different mechanics model or re-run."
        )
    if len(accepted) < target:
        logger.warning(
            "Collected %d/%d mechanic candidates (>= floor of %d, proceeding)",
            len(accepted),
            target,
            floor,
        )
    return {
        "mechanics": accepted[:target],
        "input_tokens": total_in,
        "output_tokens": total_out,
        "model_id": display_model_id,
    }


def _is_filled_candidate(c: Any) -> bool:
    """A candidate is "filled" if it has a non-blank name.

    Empty ``{}`` slots show up in the candidates list whenever a refresh run
    failed below the floor (the merged pool keeps unfilled slots as ``{}``
    for the wizard to display as placeholder cards). The picker must skip
    these — picking an empty slot lands ``(unnamed)`` in the Final picks box
    and produces an obviously-broken approved.json. The "has a name" check
    is cheap and matches what the wizard's placeholder renderer keys off.
    """
    return isinstance(c, dict) and bool((c.get("name") or "").strip())


def _resolve_picks(
    selections: list[Any],
    candidate_count_total: int,
    target: int,
    valid_indices: set[int] | None = None,
) -> tuple[list[int], dict[int, str]]:
    """Turn the LLM's raw ``selections`` into exactly ``target`` valid indices.

    The model returns 1-based ``candidate_number`` values that may be
    out of range, duplicated, too few, or too many. We map them to 0-based
    indices, drop anything invalid or repeated, then **top up** with the
    first unused candidates if we came up short and **truncate** if we got
    too many. ``valid_indices`` (when given) restricts both the LLM picks
    and the top-up to candidates that actually have content — empty ``{}``
    slots get skipped instead of landing in approved.json as ``(unnamed)``.
    Returns ``(picks, reasons)`` where ``reasons`` maps a picked index to
    the model's one-line reason (topped-up picks have no reason).
    """

    # When valid_indices is None we accept everything (legacy behaviour for
    # callers that haven't computed it — tests and any older caller).
    def _ok(idx: int) -> bool:
        return valid_indices is None or idx in valid_indices

    valid_count = candidate_count_total if valid_indices is None else len(valid_indices)
    want = max(0, min(target, valid_count))
    picks: list[int] = []
    reasons: dict[int, str] = {}
    seen: set[int] = set()
    for sel in selections or []:
        if not isinstance(sel, dict):
            continue
        num = sel.get("candidate_number")
        if not isinstance(num, int):
            continue
        idx = num - 1  # 1-based in the prompt/tool, 0-based on disk
        if idx < 0 or idx >= candidate_count_total or idx in seen or not _ok(idx):
            continue
        seen.add(idx)
        picks.append(idx)
        reason = sel.get("reason")
        if isinstance(reason, str) and reason.strip():
            reasons[idx] = reason.strip()
        if len(picks) >= want:
            break
    # Top up from the front if the model under-selected (or returned junk),
    # but only from filled slots — never include an empty placeholder.
    if len(picks) < want:
        for idx in range(candidate_count_total):
            if idx not in seen and _ok(idx):
                picks.append(idx)
                seen.add(idx)
                if len(picks) >= want:
                    break
    return picks[:want], reasons


_FENCED_JSON = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_CONTROL_TOKEN = re.compile(r"<\|[^|]*\|>")


def _salvage_tool_json(text: str | None) -> dict | None:
    """Best-effort recover a tool-call JSON object from raw model ``text``.

    Local models sometimes emit the tool call as plain text instead of a
    structured call (so ``response["result"]`` comes back empty) -- occasionally
    with control-token noise (a ``<|...|>`` artifact) or the tool name jammed onto
    the payload (``select_best_mechanics{...}``). Strip the noise, then try a
    fenced ```json block, then the first balanced ``{...}``, and ``json.loads`` it.
    Returns the parsed dict, or ``None`` if nothing valid can be recovered (the
    caller then keeps its existing fallback). Strict parse only -- genuinely
    malformed pseudo-JSON (unquoted keys) is left to the fallback, never guessed.
    """
    if not text:
        return None
    s = _CONTROL_TOKEN.sub("", text)
    m = _FENCED_JSON.search(s)
    if m:
        try:
            return json.loads(m.group(1))
        except (ValueError, TypeError):
            pass
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start : i + 1])
                except (ValueError, TypeError):
                    return None
    return None


def pick_best_mechanics(
    *,
    candidates: list[dict],
    theme: dict | None = None,
    count: int | None = None,
) -> dict:
    """Ask the LLM to pick the best ``count`` mechanics from ``candidates``.

    Reads ``theme.json`` + ``set_params`` from the active project (same as
    :func:`generate_mechanic_candidates`), renders the picker prompts, and
    runs a single tool call. The selection criteria (Limited playability,
    design space, color spread, complexity mix, theme fit, non-overlap)
    live in ``mechanic_pick_system.txt``.

    Always returns a clean slate — a malformed or failed pick call degrades
    to the first ``count`` candidates rather than raising, so the stage's
    auto-continue path can never be left without an ``approved.json``::

        {
            "picks": list[int],            # 0-based indices into candidates
            "selections": list[dict],      # [{name, reason}] aligned to picks
            "overall_rationale": str,
            "model_id": str,
            "input_tokens": int,
            "output_tokens": int,
        }
    """
    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    settings = project.settings
    sp = settings.set_params
    model_id = settings.get_llm_model_id("mechanics")
    # Base id for provenance/display (model_id above is the effective ctx twin).
    display_model_id = settings.get_assigned_model_id("mechanics")
    log_dir = set_artifact_dir() / "mechanics" / "logs"

    if theme is None:
        theme_path = set_artifact_dir() / "theme.json"
        theme = json.loads(theme_path.read_text(encoding="utf-8")) if theme_path.exists() else {}
    assert theme is not None

    target = sp.mechanic_count if count is None else max(1, count)
    total = len(candidates)
    # Indices of candidates that actually carry a mechanic. Empty ``{}``
    # placeholder slots (left over from a failed refresh) get excluded
    # from both the LLM picks and the fallback top-up so the picker can
    # never land on a slot whose name is "" → ``(unnamed)`` in Final picks.
    valid_indices: set[int] = {i for i, c in enumerate(candidates) if _is_filled_candidate(c)}

    def _fallback(reason: str, model: str = display_model_id) -> dict:
        # Pick the first ``target`` *filled* candidates (skip empties).
        # If fewer filled candidates exist than the target asks for, return
        # what we have — the wizard's "Save & Continue" gate keeps the user
        # from proceeding until they refresh more candidates manually.
        ordered = sorted(valid_indices)
        picks = ordered[:target]
        logger.warning(
            "Mechanic picker falling back to first %d filled candidate(s): %s",
            len(picks),
            reason,
        )
        return {
            "picks": picks,
            "selections": [
                {"name": (candidates[i].get("name") or "?"), "reason": ""} for i in picks
            ],
            "overall_rationale": "",
            "model_id": model,
            "input_tokens": 0,
            "output_tokens": 0,
        }

    if total == 0 or not valid_indices:
        return _fallback("no filled candidates")

    system_prompt, user_prompt = build_pick_prompts(
        theme=theme,
        set_name=sp.set_name or project.set_code or "Custom Set",
        set_size=sp.set_size,
        mechanic_count=target,
        candidates=candidates,
    )

    response: dict[str, Any] | None = None
    error: str | None = None
    try:
        response = generate_with_tool(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tool_schema=MECHANIC_PICK_TOOL_SCHEMA,
            model=model_id,
            temperature=0.4,
            max_tokens=STANDARD,
            log_dir=log_dir,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    if response is None:
        return _fallback(error or "no response")

    result = response.get("result") or {}
    # Local models sometimes emit the picker tool call as raw text (control-token
    # noise, or the tool name jammed onto the payload), so `result` comes back
    # empty. Recover the real selections from the text before degrading to
    # first-N -- otherwise the LLM's actual ranking + reasons are silently lost.
    if not result.get("selections"):
        salvaged = _salvage_tool_json(response.get("text"))
        if salvaged and salvaged.get("selections"):
            result = salvaged
            logger.info(
                "Mechanic picker: recovered selections from raw text "
                "(model emitted no structured tool call)"
            )
    selections_raw = result.get("selections") or []
    picks, reasons = _resolve_picks(selections_raw, total, target, valid_indices)
    selections = [
        {"name": (candidates[i].get("name") or "?"), "reason": reasons.get(i, "")} for i in picks
    ]
    return {
        "picks": picks,
        "selections": selections,
        "overall_rationale": (result.get("overall_rationale") or "").strip(),
        "model_id": display_model_id,
        "input_tokens": response.get("input_tokens", 0) or 0,
        "output_tokens": response.get("output_tokens", 0) or 0,
    }


def persist_mechanic_selection(
    mech_dir: Path,
    candidates: list[dict],
    picks: list[int],
    *,
    source: str = "ai",
    overall_rationale: str = "",
    selections: list[dict] | None = None,
    model_id: str = "",
) -> list[dict]:
    """Write the candidates snapshot, sidecars, and ``approved.json`` for a selection.

    The single producer of a mechanics-stage selection on disk — used by the
    stage runner (AI picker), the wizard's ``/save`` (user override), and the
    re-pick endpoint, so the write order + sidecar set stay identical across
    all three.

    Order matters: ``approved.json`` is the marker downstream stages check, so
    the candidates snapshot + sidecars are written first and ``approved.json``
    last. A ``pick-rationale.json`` sidecar records who chose the slate
    (``source``: ``"ai"`` or ``"user"``) and the AI's reasons, for the wizard
    to surface. Returns the projected ``approved`` list.
    """
    mech_dir.mkdir(parents=True, exist_ok=True)

    def _write(name: str, data: Any) -> None:
        atomic_write_text(mech_dir / name, json.dumps(data, indent=2, ensure_ascii=False))

    _write("candidates.json", candidates)
    _write("evergreen-keywords.json", load_evergreen_defaults())
    approved = [candidate_to_approved(candidates[i]) for i in picks]
    _write("pointed-questions.json", render_pointed_questions(approved))
    # Empty stub — the LLM doesn't produce functional_tags; balance.py
    # tolerates the file being missing or empty.
    _write("functional-tags.json", {})
    _write(
        "pick-rationale.json",
        {
            "source": source,
            "model_id": model_id,
            "overall_rationale": overall_rationale,
            "selections": selections or [],
            "picked_at": datetime.now(UTC).isoformat(),
        },
    )
    _write("approved.json", approved)
    return approved
