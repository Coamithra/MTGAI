"""AI design review pipeline — Phase 4B.

Implements the **tiered council+iteration hybrid** proven in Phase 1B A/B test:

- **C/U cards**: Single Opus reviewer + iteration (loop until OK or max N).
- **R/M cards**: Full council (3 independent Opus reviewers + consensus
  synthesizer, 2-of-3 filter) + iteration.
- **Planeswalkers/sagas**: Always use council tier regardless of rarity.

Every review produces a per-card log (prompt, full response, cost, verdict)
saved as JSON for diagnosis.

Usage:
    python -m mtgai.review.ai_review                # review all cards
    python -m mtgai.review.ai_review --dry-run       # show plan without API calls
    python -m mtgai.review.ai_review --card W-C-01   # review a single card
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from mtgai.generation import temperatures as temps
from mtgai.generation.llm_client import cost_from_result, generate_with_tool
from mtgai.generation.prompts import format_mechanic_block
from mtgai.generation.token_budgets import HEAVY
from mtgai.io.atomic import atomic_write_text
from mtgai.io.card_io import load_card, save_card
from mtgai.models.card import Card

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Artifact dirs are resolved per-call from the active project's asset folder
# (``set_artifact_dir``); there are no module-level per-set path constants.

# LLM settings — model + effort come from per-set model_settings at runtime.
TEMPERATURE = temps.CREATIVE  # open design-council review (see temperatures.py)
MAX_ITERATIONS = 5  # single-reviewer (C/U) self-iteration budget — unchanged

# Per-call transient-failure retries inside ONE review/synth call. A local model
# routinely returns prose instead of a parseable tool call (every retry inside
# llm_client exhausted → ``generate_with_tool`` raises), or the transport blips —
# both transient. Without an outer retry a single such failure dropped the card
# out of review entirely (the "Skyguard Sentinel: every LLM review call failed"
# bug). We re-attempt the SAME call up to this many times, only flagging the card
# for manual attention once genuine retries are exhausted.
MAX_CALL_ATTEMPTS = 3

# Council tier (R/M + planeswalkers/sagas): after the initial independent panel, the
# synthesizer revises in place and a FRESH full council re-judges the revision. This
# is the number of fresh-council *review* rounds after the initial panel — so a
# persistently problematic card is judged by at most ``1 + MAX_COUNCIL_ROUNDS`` panels
# and revised at most ``MAX_COUNCIL_ROUNDS`` times before being flagged for a
# from-scratch regen. Mirrors ``mechanic_generator.MAX_MECHANIC_REVIEW_ITERATIONS``.
MAX_COUNCIL_ROUNDS = 3


def _safe_council(on_council, event):
    """Emit a live-council event for the wizard, swallowing hook errors."""
    if on_council is None:
        return
    try:
        on_council(event)
    except Exception:
        logger.exception("ai_review on_council hook raised; continuing")


def _verdict_glyph(verdict):
    """Map an LLM verdict string to the council slot state the wizard renders."""
    return "ok" if verdict == "OK" else "revise"


def _coerce_verdict_data(result: object) -> dict:
    """Normalize a ``generate_with_tool`` ``result["result"]`` into a usable dict.

    A local model occasionally returns the tool payload in the wrong shape — a bare
    string, a list, ``None`` — or a dict with malformed keys. Everything downstream
    (``verdict_data.get("verdict")``, ``verdict_data["verdict"] = …``) assumes a dict,
    so a non-dict here is what produced the ``string indices must be integers`` crash.
    Coerce to ``{}`` when it isn't a dict so the caller falls back to a safe default
    verdict instead of raising.
    """
    return result if isinstance(result, dict) else {}


def _coerce_issues(raw: object) -> list[ReviewIssue]:
    """Parse an LLM ``issues`` array into ``ReviewIssue`` models, dropping junk.

    A local model can return ``issues`` items that aren't well-formed dicts (a bare
    string, a dict missing the required ``severity``/``category``/``description``
    keys). ``ReviewIssue(**i)`` then raises (``TypeError`` for a string,
    ``ValidationError`` for a missing key) and crashes the whole review. We instead
    fill sane defaults for missing keys and skip anything that still can't be parsed,
    so one bad issue never sinks the card's review.
    """
    if not isinstance(raw, list):
        return []
    out: list[ReviewIssue] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            out.append(
                ReviewIssue(
                    severity=str(item.get("severity") or "WARN"),
                    category=str(item.get("category") or "other"),
                    description=str(item.get("description") or ""),
                )
            )
        except Exception:
            logger.debug("Dropping unparseable review issue: %r", item)
    return out


def _review_call(
    *,
    user_prompt: str,
    tool_schema: dict,
    review_model: str,
    review_effort: str | None,
    review_thinking: str | None,
    label: str,
    should_cancel: Callable[[], bool] | None = None,
    log_dir: Path | None = None,
) -> dict | None:
    """One review/synth ``generate_with_tool`` call with transient-failure retries.

    A local model often fails to emit a parseable tool call (so ``generate_with_tool``
    raises after exhausting its own internal retries) or the transport blips — both
    transient. We retry the SAME call up to :data:`MAX_CALL_ATTEMPTS` times before
    giving up. The review temperature is already ``CREATIVE`` (1.0), so each retry
    re-rolls non-deterministically without a temperature bump. Returns the
    ``generate_with_tool`` result dict, or ``None`` when every attempt failed (the
    caller then records an error slot / flags the card — the existing contract).

    ``should_cancel`` is polled before each attempt so a Cancel doesn't burn the
    remaining retries on a card the user is abandoning.
    """
    for attempt in range(1, MAX_CALL_ATTEMPTS + 1):
        if should_cancel is not None and should_cancel():
            return None
        try:
            return generate_with_tool(
                system_prompt=REVIEW_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                tool_schema=tool_schema,
                model=review_model,
                temperature=TEMPERATURE,
                max_tokens=HEAVY,
                effort=review_effort,
                thinking=review_thinking,
                log_dir=log_dir,
            )
        except Exception:
            logger.exception(
                "    %s call failed (attempt %d/%d)", label, attempt, MAX_CALL_ATTEMPTS
            )
    return None


def _review_model() -> str:
    """Get the review model from the active project's settings."""
    from mtgai.runtime.active_project import require_active_project

    return require_active_project().settings.get_llm_model_id("ai_review")


def _review_effort() -> str | None:
    """Get the review effort from the active project's settings."""
    from mtgai.runtime.active_project import require_active_project

    return require_active_project().settings.get_effort("ai_review")


def _review_thinking() -> str | None:
    """Get the per-stage thinking override ("disabled" or None) from settings."""
    from mtgai.runtime.active_project import require_active_project

    return require_active_project().settings.get_thinking("ai_review")


# ---------------------------------------------------------------------------
# Pydantic models for review results
# ---------------------------------------------------------------------------


class ReviewIssue(BaseModel):
    severity: str  # "FAIL" or "WARN"
    category: str
    description: str


class ReviewVerdict(BaseModel):
    verdict: str  # "PASS", "WARN", "FAIL"
    issues: list[ReviewIssue] = Field(default_factory=list)
    revised_card: dict | None = None


class ReviewIteration(BaseModel):
    iteration: int
    prompt: str
    response: dict  # raw tool output from LLM
    verdict: str
    issues: list[ReviewIssue] = Field(default_factory=list)
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0


class CouncilMemberReview(BaseModel):
    member_id: int
    # Which fresh-council round this review belongs to: 1 = the initial panel,
    # 2.. = the panels that re-judge each synthesizer revision. Defaults to 1 so
    # pre-existing reviews/<cn>.json logs still load.
    round: int = 1
    verdict: str
    issues: list[ReviewIssue] = Field(default_factory=list)
    response: dict
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class CardReviewResult(BaseModel):
    """Complete review result for a single card."""

    collector_number: str
    card_name: str
    rarity: str
    review_tier: str  # "single" or "council"
    model: str = ""  # effective model after MTGAI_MAX_MODEL capping
    original_card: dict
    final_verdict: str
    final_issues: list[ReviewIssue] = Field(default_factory=list)
    revised_card: dict | None = None
    card_was_changed: bool = False
    iterations: list[ReviewIteration] = Field(default_factory=list)
    council_reviews: list[CouncilMemberReview] = Field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    total_latency_s: float = 0.0
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

REVIEW_TOOL_SCHEMA = {
    "name": "submit_review",
    "description": "Submit a structured review verdict for an MTG card.",
    "input_schema": {
        "type": "object",
        "required": ["analysis", "verdict", "issues"],
        "properties": {
            "analysis": {
                "type": "string",
                "description": (
                    "Your detailed analysis of the card covering templating, "
                    "mechanics, balance, design, and color pie."
                ),
            },
            "verdict": {
                "type": "string",
                "enum": ["OK", "REVISE"],
                "description": (
                    "OK = card is good as-is, no changes needed. "
                    "REVISE = card has issues that should be fixed."
                ),
            },
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "severity": {
                            "type": "string",
                            "enum": ["FAIL", "WARN"],
                        },
                        "category": {
                            "type": "string",
                            "description": (
                                "Issue category: keyword_negated, "
                                "redundant_conditional, above_rate_balance, kitchen_sink, "
                                "false_variability, keyword_collision, enters_tapped_irrelevant, "
                                "templating, color_pie, design, balance, other"
                            ),
                        },
                        "description": {
                            "type": "string",
                            "description": "One-sentence description of the issue.",
                        },
                    },
                    "required": ["severity", "category", "description"],
                },
                "description": "List of issues found. Empty array if OK.",
            },
            "revised_card": {
                "type": ["object", "null"],
                "description": (
                    "If verdict is REVISE, provide the complete revised card with "
                    "all fields (name, mana_cost, type_line, oracle_text, flavor_text, "
                    "power, toughness, loyalty, rarity, colors, color_identity, cmc, "
                    "design_notes). Null if verdict is OK."
                ),
                "properties": {
                    "name": {"type": "string"},
                    "mana_cost": {"type": "string"},
                    "type_line": {"type": "string"},
                    "oracle_text": {"type": "string"},
                    "flavor_text": {"type": ["string", "null"]},
                    "power": {"type": ["string", "null"]},
                    "toughness": {"type": ["string", "null"]},
                    "loyalty": {"type": ["string", "null"]},
                    "rarity": {"type": "string"},
                    "colors": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "color_identity": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "cmc": {"type": "number"},
                    "design_notes": {"type": "string"},
                },
            },
        },
    },
}

# Single-reviewer JUDGE schema: judge ONLY (no ``revised_card``). The single tier
# splits judging from revising — the reviewer decides OK/REVISE + issues, and a
# REVISE triggers a separate dedicated revise call (``REVISE_TOOL_SCHEMA``). This
# avoids the failure mode where a local model voted REVISE but omitted the revised
# card, leaving the loop to churn on a non-existent revision. (The council tier
# keeps ``REVIEW_TOOL_SCHEMA`` — its reviewers' proposed revisions feed the synth.)
JUDGE_TOOL_SCHEMA = {
    "name": "submit_review",
    "description": "Submit a structured review verdict for an MTG card.",
    "input_schema": {
        "type": "object",
        "required": ["analysis", "verdict", "issues"],
        "properties": {
            "analysis": {
                "type": "string",
                "description": (
                    "Your detailed analysis of the card covering templating, "
                    "mechanics, balance, design, and color pie."
                ),
            },
            "verdict": {
                "type": "string",
                "enum": ["OK", "REVISE"],
                "description": (
                    "OK = card is good as-is, no changes needed. "
                    "REVISE = card has issues that should be fixed."
                ),
            },
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "severity": {
                            "type": "string",
                            "enum": ["FAIL", "WARN"],
                        },
                        "category": {
                            "type": "string",
                            "description": (
                                "Issue category: keyword_negated, "
                                "redundant_conditional, above_rate_balance, kitchen_sink, "
                                "false_variability, keyword_collision, enters_tapped_irrelevant, "
                                "templating, color_pie, design, balance, other"
                            ),
                        },
                        "description": {
                            "type": "string",
                            "description": "One-sentence description of the issue.",
                        },
                    },
                    "required": ["severity", "category", "description"],
                },
                "description": "List of issues found. Empty array if OK.",
            },
        },
    },
}

# Single-reviewer REVISE schema: produce the fixed card ONLY (paired with
# ``JUDGE_TOOL_SCHEMA`` above and used by the manual ``revise_card_in_place``).
REVISE_TOOL_SCHEMA = {
    "name": "submit_revision",
    "description": "Return a complete revised MTG card that fixes the noted issues.",
    "input_schema": {
        "type": "object",
        "required": ["revised_card"],
        "properties": {
            "notes": {
                "type": "string",
                "description": "Brief note on what you changed and why.",
            },
            "revised_card": {
                "type": "object",
                "description": (
                    "The complete revised card with ALL fields (name, mana_cost, "
                    "type_line, oracle_text, flavor_text, power, toughness, loyalty, "
                    "rarity, colors, color_identity, cmc, design_notes)."
                ),
                "properties": {
                    "name": {"type": "string"},
                    "mana_cost": {"type": "string"},
                    "type_line": {"type": "string"},
                    "oracle_text": {"type": "string"},
                    "flavor_text": {"type": ["string", "null"]},
                    "power": {"type": ["string", "null"]},
                    "toughness": {"type": ["string", "null"]},
                    "loyalty": {"type": ["string", "null"]},
                    "rarity": {"type": "string"},
                    "colors": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "color_identity": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "cmc": {"type": "number"},
                    "design_notes": {"type": "string"},
                },
            },
        },
    },
}

COUNCIL_SYNTHESIS_TOOL_SCHEMA = {
    "name": "submit_synthesis",
    "description": "Synthesize council reviews into a final verdict.",
    "input_schema": {
        "type": "object",
        "required": ["synthesis", "verdict", "issues"],
        "properties": {
            "synthesis": {
                "type": "string",
                "description": (
                    "Summary of where reviewers agreed/disagreed and your "
                    "reasoning for the final verdict."
                ),
            },
            "verdict": {
                "type": "string",
                "enum": ["OK", "REVISE"],
            },
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "severity": {"type": "string", "enum": ["FAIL", "WARN"]},
                        "category": {"type": "string"},
                        "description": {"type": "string"},
                        "agreement": {
                            "type": "string",
                            "description": "How many reviewers flagged this (e.g. '2/3', '3/3').",
                        },
                    },
                    "required": ["severity", "category", "description", "agreement"],
                },
            },
            "revised_card": {
                "type": ["object", "null"],
                "description": (
                    "If verdict is REVISE, provide the complete revised card. "
                    "Null if verdict is OK."
                ),
                "properties": {
                    "name": {"type": "string"},
                    "mana_cost": {"type": "string"},
                    "type_line": {"type": "string"},
                    "oracle_text": {"type": "string"},
                    "flavor_text": {"type": ["string", "null"]},
                    "power": {"type": ["string", "null"]},
                    "toughness": {"type": ["string", "null"]},
                    "loyalty": {"type": ["string", "null"]},
                    "rarity": {"type": "string"},
                    "colors": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "color_identity": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "cmc": {"type": "number"},
                    "design_notes": {"type": "string"},
                },
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

REVIEW_SYSTEM_PROMPT = """\
You are a senior Magic: The Gathering card designer and rules expert. You are \
reviewing custom cards for a Magic set. The set's custom mechanics are supplied \
with each card; treat those definitions as authoritative.

Your job is to review each card for design quality and correctness. Be thorough \
but fair. Focus on real issues, not nitpicks.

Focus on:
- Oracle text correctness and MTG templating (use modern templating conventions)
- Balance relative to comparable printed cards at the same rarity
- Design quality (focused purpose, no kitchen sink, real variability)
- Keyword interactions and nonbos
- Color pie adherence
- A Vehicle (any card whose type line includes "Vehicle") MUST have printed \
power/toughness -- it is a non-creature that fights when crewed, and a Vehicle with \
no P/T is non-functional. This is a HARD REVISE, never something to rationalize or \
pass: if a Vehicle is missing P/T, set REVISE and give it stats. Do NOT treat a \
"non-creatures have no P/T" rule of thumb as a reason to accept a P/T-less Vehicle.
Do NOT flag:
- JSON metadata issues (e.g., keywords field) -- that's a data format concern
- Missing reminder text -- it is added programmatically after review
- Balance concerns where the card has a meaningful drawback that compensates
- A card being above-rate when a custom mechanic embeds an inherent drawback that \
compensates -- the drawback IS the cost
- Vanilla/french vanilla creatures being simple -- that's intentional at common

Power/Toughness hints. The card data may carry an auto-generated power/toughness \
hint, derived purely from statistics of printed vanilla creatures at the same mana \
value. Treat it as a loose sanity check, never a rule. Fair stats legitimately swing \
with factors the hint cannot see: color intensity (a {G}{G}{G}{G}{G} cost supports far \
bigger stats than {4}{G} at the same mana value), downsides or drawbacks on the card, \
and pushed rares/mythics that are deliberately above the vanilla curve. A vanilla \
creature's large body IS its compensation for having no abilities -- a big "dumb" \
beater (e.g. a 7/7 for 7) is fair, not overstatted. Only act on a P/T hint if, after \
weighing these, you independently agree the stats are genuinely off. Never set REVISE \
on a card solely because the hint fired.

When you REVISE a card, write its ``oracle_text`` WITHOUT any parenthetical \
reminder text. Reminder text (the italicized "(To energize, ...)" explanations in \
parentheses) is added programmatically after review -- never write it yourself. Keep \
custom-mechanic keywords bare (e.g. "When this enters, energize." not "When this \
enters, energize. (To energize, ...)"). Do not flag a card for missing reminder text, \
and do not add reminder text to fix it."""


def _format_card_for_review(
    card: dict,
    *,
    include_design_notes: bool = False,
    existing_cards: list[Card] | None = None,
) -> str:
    """Format a card dict into a readable text block.

    Heuristic design-judgment warnings (power level, color pie) are computed
    **fresh** against the supplied card via
    :func:`mtgai.analysis.heuristic_checks.check_card_heuristics` rather than
    read from ``generation_attempts[].validation_errors`` — so a revision
    produced mid-review sees warnings about its own current state, not the
    original gen-time draft. When ``existing_cards`` (the rest of the set pool)
    is supplied, the duplicate-name / mechanical-similarity detector also rides in
    as a prior so the reviewer sees a name collision with a sibling card — the
    documented intent of ``validate_mechanical_similarity``.

    ``design_notes`` are **excluded by default** (``include_design_notes=False``).
    They are card_gen's generation rationale describing the ORIGINAL slot intent
    (a specific CMC, a ``-2/-2``, french-vanilla simplicity), NOT a spec the
    design-review council should enforce. The council's job is precisely to
    rebalance (cost / P-T / effect magnitude); feeding it the stale notes makes
    reviewers flag every rebalance as "contradicts the design notes" and loop
    REVISE until the budget is exhausted, with the card never converging. Slot
    conformance is already enforced upstream by the conformance gate, so the notes
    add nothing to review but the self-inflicted contradiction. The human-readable
    markdown report passes ``include_design_notes=True`` to keep its transcript
    complete.
    """
    # ``card`` may be an LLM-produced ``revised_card`` (e.g. an iteration / council
    # revision), which a local model sometimes returns malformed — a missing ``name``
    # key, a non-dict, etc. Read every field with ``.get`` (never ``card['name']``)
    # so a bad revision can't crash the prompt builder with ``KeyError: 'name'``.
    if not isinstance(card, dict):
        return ""
    lines = [
        f"Name: {card.get('name', '???')}",
        f"Mana Cost: {card.get('mana_cost', '')}",
        f"Type: {card.get('type_line', '')}",
        f"Rarity: {card.get('rarity', '')}",
    ]
    oracle = card.get("oracle_text", "")
    if oracle:
        lines.append(f"Oracle Text: {oracle}")
    flavor = card.get("flavor_text")
    if flavor:
        lines.append(f"Flavor Text: {flavor}")
    if card.get("power") is not None:
        lines.append(f"P/T: {card.get('power')}/{card.get('toughness')}")
    if card.get("loyalty") is not None:
        lines.append(f"Loyalty: {card.get('loyalty')}")
    if include_design_notes:
        notes = card.get("design_notes")
        if notes:
            lines.append(f"Design Notes: {notes}")

    # Fresh heuristic checks — power level, color pie. Wrapped so a card dict
    # that can't be parsed (e.g. a malformed mid-review revision) doesn't
    # crash the prompt builder; the warnings are advisory.
    heuristic_block = _heuristic_warnings_for_card_dict(card, existing_cards)
    if heuristic_block:
        lines.append(heuristic_block)
    return "\n".join(lines)


def _heuristic_warnings_for_card_dict(card: dict, existing_cards: list[Card] | None = None) -> str:
    """Run check_card_heuristics against ``card`` and format findings for the prompt.

    ``existing_cards`` (the rest of the set pool) lets the mechanical-similarity /
    duplicate-name detector ride in the reviewer's prompt as a prior — the
    documented intent of ``validate_mechanical_similarity``. The card under review
    is excluded by collector number so it never matches itself. When ``None`` (the
    default, used by the markdown-transcript call sites) those priors are skipped.

    Returns an empty string if the card can't be parsed or has no findings.
    """
    from mtgai.analysis.heuristic_checks import check_card_heuristics, format_findings_for_prompt
    from mtgai.validation.mana import derive_mana_fields

    try:
        # Saved cards have derived mana fields; in-flight revisions might not.
        # Re-derive defensively so the validators see consistent input.
        enriched = {**card}
        enriched.update(derive_mana_fields(enriched.get("mana_cost"), enriched.get("oracle_text")))
        parsed = Card.model_validate(enriched)
    except Exception:
        return ""
    pool = None
    if existing_cards:
        own_cn = parsed.collector_number
        pool = [c for c in existing_cards if c.collector_number != own_cn]
    findings = check_card_heuristics(parsed, existing_cards=pool)
    return format_findings_for_prompt(findings)


def _build_review_prompt(
    card: dict,
    mechanics: list[dict],
    pointed_questions: list[dict],
    existing_cards: list[Card] | None = None,
) -> str:
    """Build the user prompt for a single-reviewer review.

    ``existing_cards`` (the set pool) threads through to the heuristic block so a
    duplicate-name / mechanical-similarity prior reaches the reviewer.
    """
    card_text = _format_card_for_review(card, existing_cards=existing_cards)

    # Only include mechanics relevant to this card's colors
    card_colors = set(card.get("colors", []))
    if not card_colors:
        # Colorless/land — include all mechanics
        card_colors = {"W", "U", "B", "R", "G"}
    mech_block = format_mechanic_block(mechanics, card_colors)

    # Build pointed questions section. A pointed question is normally a dict with a
    # ``question`` key, but tolerate a malformed entry (a bare string, a missing key)
    # so a bad pointed-questions.json can't crash review with ``string indices``.
    pq_lines = []
    for i, pq in enumerate(pointed_questions, 1):
        if isinstance(pq, dict):
            question = pq.get("question")
        elif isinstance(pq, str):
            question = pq
        else:
            question = None
        if question:
            pq_lines.append(f"{i}. {question}")
    pq_text = "\n".join(pq_lines)

    return (
        f"## Custom Mechanics\n\n{mech_block}\n\n"
        f"---\n\n"
        f"## Card to Review\n\n{card_text}\n\n"
        f"---\n\n"
        f"## Review Checklist\n\n"
        f"List any issues with templating, mechanics, balance, design, or color pie.\n\n"
        f"Additionally, consider these specific questions:\n\n{pq_text}\n\n"
        f"If the card is good as-is, verdict is OK with an empty issues list. "
        f"If the card needs changes, verdict is REVISE and provide the complete "
        f"revised card with ALL fields."
    )


def _build_single_revise_prompt(
    card: dict,
    issues: list[ReviewIssue],
    mechanics: list[dict],
    pointed_questions: list[dict],
) -> str:
    """Build the dedicated revise prompt for the single tier (judge → revise).

    Given the current card plus the issues the judge raised, ask for the complete
    fixed card via ``REVISE_TOOL_SCHEMA``. Mirrors the council synthesizer's
    revise-in-place: the model only revises here — judging is a separate call.
    """
    base_prompt = _build_review_prompt(card, mechanics, pointed_questions)
    issues_text = "".join(f"- [{i.severity}] {i.category}: {i.description}\n" for i in issues)
    return (
        f"{base_prompt}\n\n---\n\n"
        f"## Fix Required\n\n"
        f"A reviewer rated this card REVISE for the following issues:\n\n"
        f"{issues_text or '(no specific issues listed)'}\n"
        f"Produce the COMPLETE revised card that fixes these issues without "
        f"introducing new ones, keeping everything else intact and templating clean. "
        f"Return all fields."
    )


def _build_council_synthesis_prompt(
    card: dict,
    council_reviews: list[dict],
) -> str:
    """Build the prompt for the council synthesizer."""
    card_text = _format_card_for_review(card)

    reviews_text = ""
    for i, review in enumerate(council_reviews, 1):
        reviews_text += f"\n### Reviewer {i}\n"
        reviews_text += f"Verdict: {review.get('verdict', 'UNKNOWN')}\n"
        analysis = review.get("analysis", "")
        if analysis:
            reviews_text += f"Analysis: {analysis}\n"
        for issue in review.get("issues", []):
            sev = issue.get("severity", "?")
            cat = issue.get("category", "?")
            desc = issue.get("description", "?")
            reviews_text += f"- [{sev}] {cat}: {desc}\n"
        revised = review.get("revised_card")
        if revised:
            reviews_text += f"\nProposed revision:\n{_format_card_for_review(revised)}\n"

    return (
        f"## Original Card\n\n{card_text}\n\n"
        f"---\n\n"
        f"## Independent Reviewer Assessments\n\n"
        f"Three independent reviewers assessed this card. Their reviews follow.\n"
        f"{reviews_text}\n\n"
        f"---\n\n"
        f"## Your Task: Synthesize\n\n"
        f"Apply a **2-of-3 consensus filter**: only flag issues that at least 2 "
        f"of 3 reviewers agree on. Discard issues raised by only 1 reviewer "
        f"(likely a false positive).\n\n"
        f"If the consensus is that the card is fine (all 3 say OK, or only 1 "
        f"flags issues), verdict is OK.\n\n"
        f"If 2+ reviewers flag real issues, verdict is REVISE. Produce the best "
        f"revised card by combining the strongest elements from the reviewers' "
        f"suggestions. The revised card must include ALL fields."
    )


# ---------------------------------------------------------------------------
# Empty-iterations error result
# ---------------------------------------------------------------------------

# Verdict used when a card could not be reviewed at all (every LLM call errored).
# It rides the existing "REVISE" channel so ``review_all_cards`` collects the card
# into ``unfixable`` and the runner flags it for human attention / regen, rather
# than the card silently passing as OK.
_REVIEW_FAILED_VERDICT = "REVISE"
_REVIEW_FAILED_ISSUE = ReviewIssue(
    severity="FAIL",
    category="review_error",
    description=(
        "Card could not be reviewed: every LLM review call failed. Flagged for "
        "manual attention instead of being accepted as OK."
    ),
)


def _error_review_result(
    card: dict,
    review_tier: str,
    review_model: str,
    collector_number: str,
    card_name: str,
    rarity: str,
    *,
    council_reviews: list[CouncilMemberReview] | None = None,
    total_input_tokens: int = 0,
    total_output_tokens: int = 0,
    total_cost_usd: float = 0.0,
    total_latency_s: float = 0.0,
) -> CardReviewResult:
    """Build a non-OK review result for a card that could not be reviewed.

    Used when the review loop produced zero iterations because every LLM call
    raised. The card is **not** changed (no trustworthy revision exists) but its
    verdict is REVISE with an explanatory ``review_error`` issue, so the caller's
    flagging contract treats it like an unfixable card.
    """
    return CardReviewResult(
        collector_number=collector_number,
        card_name=card_name,
        rarity=rarity,
        review_tier=review_tier,
        model=review_model,
        original_card=card,
        final_verdict=_REVIEW_FAILED_VERDICT,
        final_issues=[_REVIEW_FAILED_ISSUE],
        revised_card=None,
        card_was_changed=False,
        iterations=[],
        council_reviews=council_reviews or [],
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_cost_usd=total_cost_usd,
        total_latency_s=total_latency_s,
        timestamp=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# Single-reviewer review (C/U tier)
# ---------------------------------------------------------------------------


def _review_single(
    card: dict,
    mechanics: list[dict],
    pointed_questions: list[dict],
    review_model: str,
    review_effort: str | None,
    max_iterations: int = MAX_ITERATIONS,
    on_council: Callable[[dict], None] | None = None,
    review_thinking: str | None = None,
    existing_cards: list[Card] | None = None,
    log_dir: Path | None = None,
) -> CardReviewResult:
    """Judge → revise → re-judge loop for C/U cards (judge split from revise).

    Each round the reviewer JUDGES the current card (``JUDGE_TOOL_SCHEMA`` — verdict
    + issues, no revised card). On REVISE a SEPARATE dedicated call produces the fixed
    card (``REVISE_TOOL_SCHEMA``); the next round judges that revision. This avoids the
    old failure where one call had to both judge and revise: a local model that voted
    REVISE but returned no ``revised_card`` made the loop churn on a phantom revision
    for the whole budget. Now a revise that yields no card stops the loop and leaves
    the card REVISE → flagged for a from-scratch regen (mirrors the council's "synth
    produced no revision" guard).

    ``review_model`` / ``review_effort`` are resolved once by the caller
    (``review_set``) before the per-card loop starts so a mid-run settings
    change can't swap the model between cards.

    ``on_council`` (optional) reports live progress for the wizard tab: each round is
    a one-reviewer panel with a single verdict slot (plus a ``synth`` slot while the
    revise call runs), so the tab shows the same 👍/👎 timeline the council tier does.
    Best-effort — a hook raising never breaks the review. Cancellation
    (``ai_lock.is_cancelled``) is polled at each round/call boundary.
    """
    from mtgai.runtime import ai_lock

    collector_number = card.get("collector_number", card.get("slot_id", "???"))
    card_name = card.get("name", "???")
    rarity = card.get("rarity", "???")

    logger.info("  [%s] Single review: %s (%s)", collector_number, card_name, rarity)

    iterations: list[ReviewIteration] = []
    total_in = 0
    total_out = 0
    total_cost = 0.0
    total_latency = 0.0
    effective_model = review_model
    current_card = card
    revised_card: dict | None = None
    card_was_changed = False
    final_verdict: str | None = None
    final_issues: list[ReviewIssue] = []

    def _fold(result: dict, latency: float) -> float:
        nonlocal total_in, total_out, total_cost, total_latency, effective_model
        effective_model = result.get("model", effective_model)
        cost = cost_from_result(result)
        total_in += (
            result["input_tokens"]
            + result.get("cache_creation_input_tokens", 0)
            + result.get("cache_read_input_tokens", 0)
        )
        total_out += result["output_tokens"]
        total_cost += cost
        total_latency += latency
        return cost

    for round_no in range(1, max_iterations + 1):
        if ai_lock.is_cancelled():
            break
        logger.info("    Round %d/%d: judge...", round_no, max_iterations)
        _safe_council(on_council, {"kind": "round", "round": round_no, "verdicts": []})

        judge_prompt = _build_review_prompt(
            current_card, mechanics, pointed_questions, existing_cards
        )
        t0 = time.time()
        result = _review_call(
            user_prompt=judge_prompt,
            tool_schema=JUDGE_TOOL_SCHEMA,
            review_model=review_model,
            review_effort=review_effort,
            review_thinking=review_thinking,
            label=f"Judge {round_no}",
            should_cancel=ai_lock.is_cancelled,
            log_dir=log_dir,
        )
        if result is None:
            logger.error("    Judge call failed on round %d (retries exhausted)", round_no)
            _safe_council(on_council, {"kind": "round", "round": round_no, "verdicts": ["error"]})
            break
        elapsed = time.time() - t0
        cost = _fold(result, elapsed)
        verdict_data = _coerce_verdict_data(result["result"])
        verdict = verdict_data.get("verdict", "OK")
        issues = _coerce_issues(verdict_data.get("issues"))
        _safe_council(
            on_council,
            {"kind": "round", "round": round_no, "verdicts": [_verdict_glyph(verdict)]},
        )
        logger.info(
            "    Round %d verdict: %s (%d issues), $%.4f", round_no, verdict, len(issues), cost
        )
        iteration = ReviewIteration(
            iteration=round_no,
            prompt=judge_prompt,
            response=verdict_data,
            verdict=verdict,
            issues=issues,
            model=effective_model,
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            cost_usd=cost,
            latency_s=elapsed,
        )
        iterations.append(iteration)

        if verdict == "OK":
            final_verdict = "OK"
            final_issues = []
            break

        # REVISE. After the final round there's no budget left to fix it; flag it.
        if round_no == max_iterations:
            final_verdict = "REVISE"
            final_issues = issues
            break
        if ai_lock.is_cancelled():
            final_verdict = "REVISE"
            final_issues = issues
            break

        # Dedicated revise call (judging is done — this only produces the fixed card).
        _safe_council(
            on_council,
            {
                "kind": "round",
                "round": round_no,
                "verdicts": [_verdict_glyph(verdict)],
                "synth": "running",
            },
        )
        rt0 = time.time()
        rresult = _review_call(
            user_prompt=_build_single_revise_prompt(
                current_card, issues, mechanics, pointed_questions
            ),
            tool_schema=REVISE_TOOL_SCHEMA,
            review_model=review_model,
            review_effort=review_effort,
            review_thinking=review_thinking,
            label=f"Revise {round_no}",
            should_cancel=ai_lock.is_cancelled,
            log_dir=log_dir,
        )
        _safe_council(
            on_council,
            {
                "kind": "round",
                "round": round_no,
                "verdicts": [_verdict_glyph(verdict)],
                "synth": "done",
            },
        )
        if rresult is None:
            logger.error("    Revise call failed on round %d — flagging for regen", round_no)
            final_verdict = "REVISE"
            final_issues = issues
            break
        _fold(rresult, time.time() - rt0)
        revised = _coerce_verdict_data(rresult["result"]).get("revised_card")
        if not isinstance(revised, dict):
            logger.info("    Round %d revise produced no card — flagging for regen", round_no)
            final_verdict = "REVISE"
            final_issues = issues
            break
        # Record the revision on this round's iteration log (so the markdown shows the
        # raw model output) and judge it next round. Accumulate the revision onto the
        # current card rather than feeding the raw partial dict forward: a model that
        # omits a field (e.g. mana_cost) must not blank it for the next round's judge.
        iteration.response["revised_card"] = revised
        current_card = _merge_revision_into_dict(current_card, revised)
        revised_card = current_card
        card_was_changed = True
        # Live: push the in-progress revised body so the tab's tile updates mid-loop.
        _safe_council(on_council, {"kind": "card", "card": _live_tile_fields(current_card)})

    # Every judge call failed → the card was never reviewed; flag REVISE/error so the
    # runner doesn't silently pass it as OK (mirrors the council empty-panel guard).
    if not iterations:
        logger.error(
            "  [%s] Review produced no iterations (all judge calls failed) — "
            "flagging REVISE instead of defaulting OK",
            collector_number,
        )
        return _error_review_result(
            card,
            "single",
            review_model,
            collector_number,
            card_name,
            rarity,
            total_input_tokens=total_in,
            total_output_tokens=total_out,
            total_cost_usd=total_cost,
            total_latency_s=total_latency,
        )

    # Cancelled mid-loop before a verdict was decided: keep partial, don't claim OK.
    if final_verdict is None:
        final_verdict = "REVISE"
        final_issues = iterations[-1].issues

    return CardReviewResult(
        collector_number=collector_number,
        card_name=card_name,
        rarity=rarity,
        review_tier="single",
        model=effective_model,
        original_card=card,
        final_verdict=final_verdict,
        final_issues=final_issues,
        revised_card=revised_card if card_was_changed else None,
        card_was_changed=card_was_changed,
        iterations=iterations,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        total_cost_usd=total_cost,
        total_latency_s=total_latency,
        timestamp=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# Council review (R/M tier) — fresh council per revision, regen after the budget
# ---------------------------------------------------------------------------


class _CostAcc:
    """Accumulate token/cost/latency/model across one or more LLM calls.

    Dedups the bookkeeping repeated for every reviewer + synth call. ``input_tokens``
    counts cache-creation/read tokens too (the basis for ``total_input_tokens``); a
    caller reads the raw ``result["input_tokens"]`` separately for the per-call record.
    """

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0
        self.latency_s = 0.0
        self.model = ""

    def record(self, result: dict, latency: float) -> float:
        """Fold one ``generate_with_tool`` result in; return its dollar cost."""
        self.model = result.get("model", self.model)
        cost = cost_from_result(result)
        self.input_tokens += (
            result["input_tokens"]
            + result.get("cache_creation_input_tokens", 0)
            + result.get("cache_read_input_tokens", 0)
        )
        self.output_tokens += result["output_tokens"]
        self.cost_usd += cost
        self.latency_s += latency
        return cost


def _council_consensus_ok(reviews: list[CouncilMemberReview], num_reviewers: int) -> bool:
    """2-of-3 consensus filter: a round passes iff a strict majority of the FULL
    panel voted OK (``ok * 2 > num_reviewers`` → 2 of 3). A collapsed panel (no
    reviewer returned) never passes — an un-judgeable card is not silently approved.
    """
    if not reviews:
        return False
    ok = sum(1 for r in reviews if r.verdict == "OK")
    return ok * 2 > num_reviewers


def _dedup_issues(reviews: list[CouncilMemberReview]) -> list[ReviewIssue]:
    """Flatten + dedup (by category+description) the surviving issues of a panel.

    Used as the ``final_issues`` of a flagged card — these descriptions become the
    regen reason the runner threads back into ``card_gen``.
    """
    out: list[ReviewIssue] = []
    seen: set[tuple[str, str]] = set()
    for r in reviews:
        for issue in r.issues:
            key = (issue.category, issue.description)
            if key in seen:
                continue
            seen.add(key)
            out.append(issue)
    return out


def _run_council_panel(
    card: dict,
    mechanics: list[dict],
    pointed_questions: list[dict],
    review_model: str,
    review_effort: str | None,
    num_reviewers: int,
    round_no: int,
    on_council: Callable[[dict], None] | None,
    should_cancel: Callable[[], bool] | None,
    review_thinking: str | None = None,
    existing_cards: list[Card] | None = None,
    log_dir: Path | None = None,
) -> tuple[list[CouncilMemberReview], _CostAcc, list[str]]:
    """Run one fresh independent panel on ``card`` and stream it as council ``round``.

    Each of ``num_reviewers`` reviewers judges ``card`` independently (an errored one
    gets an "error" slot so the panel still resolves). Returns the completed reviews
    (tagged with ``round_no``), a ``_CostAcc`` for the caller to fold into the totals,
    and the live verdict-glyph list. Polls ``should_cancel`` between reviewers so a
    Cancel halts the (potentially long) panel mid-round.
    """
    acc = _CostAcc()
    reviews: list[CouncilMemberReview] = []
    panel_verdicts: list[str] = []
    user_prompt = _build_review_prompt(card, mechanics, pointed_questions, existing_cards)
    _safe_council(on_council, {"kind": "round", "round": round_no, "verdicts": []})
    for member_id in range(1, num_reviewers + 1):
        if should_cancel is not None and should_cancel():
            break
        logger.info("    Round %d reviewer %d/%d...", round_no, member_id, num_reviewers)
        t0 = time.time()
        result = _review_call(
            user_prompt=user_prompt,
            tool_schema=REVIEW_TOOL_SCHEMA,
            review_model=review_model,
            review_effort=review_effort,
            review_thinking=review_thinking,
            label=f"Round {round_no} reviewer {member_id}",
            should_cancel=should_cancel,
            log_dir=log_dir,
        )
        if result is None:
            logger.error(
                "    Round %d reviewer %d API call failed (retries exhausted)",
                round_no,
                member_id,
            )
            panel_verdicts.append("error")
            _safe_council(
                on_council,
                {"kind": "round", "round": round_no, "verdicts": list(panel_verdicts)},
            )
            continue
        latency = time.time() - t0
        cost = acc.record(result, latency)
        verdict_data = _coerce_verdict_data(result["result"])
        verdict = verdict_data.get("verdict", "OK")
        verdict_data["verdict"] = verdict  # ensure key exists for the synthesis prompt
        issues = _coerce_issues(verdict_data.get("issues"))
        logger.info(
            "    Round %d reviewer %d: %s (%d issues), $%.4f",
            round_no,
            member_id,
            verdict,
            len(issues),
            cost,
        )
        panel_verdicts.append(_verdict_glyph(verdict))
        _safe_council(
            on_council,
            {"kind": "round", "round": round_no, "verdicts": list(panel_verdicts)},
        )
        reviews.append(
            CouncilMemberReview(
                member_id=member_id,
                round=round_no,
                verdict=verdict,
                issues=issues,
                response=verdict_data,
                input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"],
                cost_usd=cost,
            )
        )
    return reviews, acc, panel_verdicts


def _run_synth(
    card: dict,
    reviews: list[CouncilMemberReview],
    mechanics: list[dict],
    review_model: str,
    review_effort: str | None,
    round_no: int,
    on_council: Callable[[dict], None] | None,
    panel_verdicts: list[str],
    review_thinking: str | None = None,
    log_dir: Path | None = None,
) -> tuple[ReviewIteration | None, _CostAcc, dict | None]:
    """One synthesizer revise-in-place call against ``reviews`` of ``card``.

    The synthesizer combines the panel's consensus feedback into a single revised
    card. Its OWN verdict is ignored by the caller (it over-claims) — only its
    ``revised_card`` is used; a FRESH council re-judges next round. Returns the
    iteration record (``None`` if the call failed), a ``_CostAcc``, and the revised
    card dict (``None`` if the synth produced none). Streams the round's synth slot
    ``running → done``.
    """
    acc = _CostAcc()
    synthesis_prompt = _build_council_synthesis_prompt(card, [r.response for r in reviews])
    card_colors = set(card.get("colors", [])) or {"W", "U", "B", "R", "G"}
    mech_block = format_mechanic_block(mechanics, card_colors)
    synthesis_prompt = f"## Custom Mechanics\n\n{mech_block}\n\n---\n\n{synthesis_prompt}"
    _safe_council(
        on_council,
        {
            "kind": "round",
            "round": round_no,
            "verdicts": list(panel_verdicts),
            "synth": "running",
        },
    )
    t0 = time.time()
    result = _review_call(
        user_prompt=synthesis_prompt,
        tool_schema=COUNCIL_SYNTHESIS_TOOL_SCHEMA,
        review_model=review_model,
        review_effort=review_effort,
        review_thinking=review_thinking,
        label=f"Round {round_no} synthesis (revise)",
        log_dir=log_dir,
    )
    if result is None:
        logger.error("    Round %d synthesis (revise) call failed (retries exhausted)", round_no)
        return None, acc, None
    latency = time.time() - t0
    cost = acc.record(result, latency)
    verdict_data = _coerce_verdict_data(result["result"])
    issues = _coerce_issues(verdict_data.get("issues"))
    _safe_council(
        on_council,
        {
            "kind": "round",
            "round": round_no,
            "verdicts": list(panel_verdicts),
            "synth": "done",
        },
    )
    logger.info("    Round %d synthesis revised the card, $%.4f, %.1fs", round_no, cost, latency)
    revised = verdict_data.get("revised_card")
    # ``iteration`` is the round whose panel this synth revised (synth N revises the
    # card the round-N panel just flagged), so in a saved log iteration N sits between
    # the round-N and round-(N+1) panels.
    iteration = ReviewIteration(
        iteration=round_no,
        prompt=synthesis_prompt,
        response=verdict_data,
        verdict=verdict_data.get("verdict", "REVISE"),
        issues=issues,
        model=acc.model or review_model,
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        cost_usd=cost,
        latency_s=latency,
    )
    return iteration, acc, (revised if isinstance(revised, dict) else None)


def _review_council(
    card: dict,
    mechanics: list[dict],
    pointed_questions: list[dict],
    review_model: str,
    review_effort: str | None,
    num_reviewers: int = 3,
    max_rounds: int = MAX_COUNCIL_ROUNDS,
    on_council: Callable[[dict], None] | None = None,
    review_thinking: str | None = None,
    existing_cards: list[Card] | None = None,
    log_dir: Path | None = None,
) -> CardReviewResult:
    """Fresh-council-per-revision loop for R/M + planeswalker/saga cards.

    An independent panel (round 1) judges the original card. While the panel lacks a
    2-of-3 OK consensus, the synthesizer revises the card in place and a FRESH full
    council re-judges the revision — up to ``max_rounds`` review rounds. The synth's
    own verdict is never trusted (it over-claims); only the independent panels decide.
    A card still problematic after the final fresh council is left ``REVISE`` so the
    runner flags it (``flagged_by="ai_review"``) for a from-scratch ``card_gen`` regen
    — the best in-place revision stays saved and is archived+replaced by the regen.

    ``review_model`` / ``review_effort`` are resolved once by the caller
    (``review_set``) before the per-card loop starts so a mid-run settings change
    can't swap the model between cards.

    ``on_council`` (optional) streams each round as a full ``num_reviewers``-slot
    panel (plus the round's synth slot while it revises). Best-effort — a hook raising
    never breaks the review. Cancellation (``ai_lock.is_cancelled``) is polled at
    every round/reviewer/synth boundary so the Cancel button halts mid-card.
    """
    from mtgai.runtime import ai_lock

    collector_number = card.get("collector_number", card.get("slot_id", "???"))
    card_name = card.get("name", "???")
    rarity = card.get("rarity", "???")

    logger.info(
        "  [%s] Council review (%d reviewers, %d max rounds): %s (%s)",
        collector_number,
        num_reviewers,
        max_rounds,
        card_name,
        rarity,
    )

    council_reviews: list[CouncilMemberReview] = []
    iterations: list[ReviewIteration] = []
    total_in = 0
    total_out = 0
    total_cost = 0.0
    total_latency = 0.0
    effective_model = review_model
    current_card = card
    card_was_changed = False
    final_verdict: str | None = None
    final_issues: list[ReviewIssue] = []
    last_reviews: list[CouncilMemberReview] = []

    def _fold(acc: _CostAcc) -> None:
        nonlocal total_in, total_out, total_cost, total_latency, effective_model
        total_in += acc.input_tokens
        total_out += acc.output_tokens
        total_cost += acc.cost_usd
        total_latency += acc.latency_s
        if acc.model:
            effective_model = acc.model

    # Round 1 is the initial panel; rounds 2..max_rounds+1 re-judge each revision.
    total_panels = max_rounds + 1
    for round_no in range(1, total_panels + 1):
        if ai_lock.is_cancelled():
            break

        reviews, acc, panel_verdicts = _run_council_panel(
            current_card,
            mechanics,
            pointed_questions,
            review_model,
            review_effort,
            num_reviewers,
            round_no,
            on_council,
            ai_lock.is_cancelled,
            review_thinking=review_thinking,
            existing_cards=existing_cards,
            log_dir=log_dir,
        )
        _fold(acc)
        council_reviews.extend(reviews)
        if reviews:
            last_reviews = reviews

        # A fully collapsed INITIAL panel (every reviewer errored) leaves the card
        # un-judged — flag REVISE/error rather than risk a vacuous pass, mirroring
        # the empty-iterations guard.
        if not council_reviews:
            logger.error(
                "  [%s] All %d council reviewers failed on the initial panel — flagging "
                "REVISE instead of trusting a review-less verdict",
                collector_number,
                num_reviewers,
            )
            return _error_review_result(
                card,
                "council",
                review_model,
                collector_number,
                card_name,
                rarity,
                total_input_tokens=total_in,
                total_output_tokens=total_out,
                total_cost_usd=total_cost,
                total_latency_s=total_latency,
            )

        # A *later* round's panel fully collapsed (every reviewer errored) while an
        # earlier round succeeded: don't synthesize against zero feedback or flag with
        # an empty reason. Stop and let the post-loop fallback flag REVISE carrying the
        # last real panel's issues.
        if not reviews:
            logger.error(
                "  [%s] Round %d panel fully collapsed — flagging from the last real panel",
                collector_number,
                round_no,
            )
            break

        if ai_lock.is_cancelled():
            break

        if _council_consensus_ok(reviews, num_reviewers):
            logger.info(
                "    Round %d: 2-of-%d OK consensus — card approved", round_no, num_reviewers
            )
            final_verdict = "OK"
            final_issues = []
            break

        # Problematic. After the final fresh council, flag for a from-scratch regen.
        if round_no == total_panels:
            logger.info(
                "    Round %d still problematic after %d fresh-council round(s) — "
                "flagging for regen",
                round_no,
                max_rounds,
            )
            final_verdict = "REVISE"
            final_issues = _dedup_issues(reviews)
            break

        if ai_lock.is_cancelled():
            break

        # Synthesizer revises in place; a fresh council re-judges next round. Its own
        # verdict is ignored — only the revised card is taken.
        iteration, sacc, revised = _run_synth(
            current_card,
            reviews,
            mechanics,
            review_model,
            review_effort,
            round_no,
            on_council,
            panel_verdicts,
            review_thinking=review_thinking,
            log_dir=log_dir,
        )
        _fold(sacc)
        if iteration is None:
            # The reviser call failed — can't improve a consensus-flagged card; flag it.
            final_verdict = "REVISE"
            final_issues = _dedup_issues(reviews)
            break
        iterations.append(iteration)
        if revised is None:
            # Synth declined to revise a consensus-flagged card — nothing changed, so a
            # fresh council would only re-flag it. Flag for regen now.
            logger.info("    Round %d synth produced no revision — flagging for regen", round_no)
            final_verdict = "REVISE"
            final_issues = _dedup_issues(reviews)
            break
        # Accumulate onto the current card (not the raw partial synth dict) so an
        # omitted field can't blank the card for the next fresh council, and the final
        # save keeps every round's edit. Push the in-progress body to the tab's tile.
        current_card = _merge_revision_into_dict(current_card, revised)
        card_was_changed = True
        _safe_council(on_council, {"kind": "card", "card": _live_tile_fields(current_card)})

    # Cancelled before a verdict was decided: don't claim OK. Keep whatever was
    # reviewed (the runner skips flagging on a cancelled run anyway). A cancel before
    # any reviewer returned leaves nothing to judge — surface the error verdict.
    if final_verdict is None:
        if not council_reviews:
            return _error_review_result(
                card,
                "council",
                review_model,
                collector_number,
                card_name,
                rarity,
                total_input_tokens=total_in,
                total_output_tokens=total_out,
                total_cost_usd=total_cost,
                total_latency_s=total_latency,
            )
        final_verdict = "REVISE"
        final_issues = _dedup_issues(last_reviews)

    return CardReviewResult(
        collector_number=collector_number,
        card_name=card_name,
        rarity=rarity,
        review_tier="council",
        model=effective_model,
        original_card=card,
        final_verdict=final_verdict,
        final_issues=final_issues,
        revised_card=current_card if card_was_changed else None,
        card_was_changed=card_was_changed,
        iterations=iterations,
        council_reviews=council_reviews,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        total_cost_usd=total_cost,
        total_latency_s=total_latency,
        timestamp=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# Tier selection
# ---------------------------------------------------------------------------


def _select_tier(card: dict) -> str:
    """Choose review tier based on rarity and card type.

    - Planeswalkers and sagas: always council
    - Rare/mythic: council
    - Common/uncommon: single reviewer
    """
    rarity = card.get("rarity", "common")
    type_line = card.get("type_line", "").lower()

    if "planeswalker" in type_line or "saga" in type_line:
        return "council"
    if rarity in ("rare", "mythic"):
        return "council"
    return "single"


# ---------------------------------------------------------------------------
# Card JSON update
# ---------------------------------------------------------------------------


# Whitelisted design fields a review revision may change (game data, not pipeline
# metadata). Single source for both the Card-level apply (final save) and the
# dict-level in-loop merge below.
_REVISION_ALLOWED_FIELDS: tuple[str, ...] = (
    "name",
    "mana_cost",
    "type_line",
    "oracle_text",
    "flavor_text",
    "power",
    "toughness",
    "loyalty",
    "rarity",
    "colors",
    "color_identity",
    "cmc",
    "design_notes",
)


def _revision_field_updates(revised_data: dict) -> dict:
    """The whitelisted ``{field: value}`` updates an AI revision carries.

    Only fields present in ``revised_data`` are returned (a missing field means
    "not changed"). Reminder text is stripped from a revised ``oracle_text`` —
    reminder text is **never** LLM-authored (CLAUDE.md: it's stripped + injected
    programmatically by ``reminder_injector`` at ``finalize``); baking parenthetical
    reminder text into ``oracle_text`` before finalize would write un-canonical text
    finalize then has to re-strip. Shared by :func:`_apply_revision` (Card copy) and
    :func:`_merge_revision_into_dict` (in-loop dict merge) so the two never drift.
    """
    from mtgai.generation.reminder_injector import strip_reminder_text

    update: dict = {}
    for field in _REVISION_ALLOWED_FIELDS:
        if field in revised_data:
            value = revised_data[field]
            if field == "oracle_text" and isinstance(value, str):
                value = strip_reminder_text(value)
            update[field] = value
    return update


def _merge_revision_into_dict(current: dict, revised: dict) -> dict:
    """Accumulate an AI revision onto the current card dict for in-loop re-judging.

    The dict-level analogue of :func:`_apply_revision`: whitelisted design fields
    are taken from ``revised`` and **every field the model omitted keeps its current
    value**. A local model routinely returns a *partial* ``revised_card`` (e.g.
    dropping ``mana_cost`` while only changing ``cmc``); feeding that raw dict forward
    as the next round's card blanks the omitted fields and provokes phantom regressions
    (a dropped mana cost reads as a colorless, 0-CMC card and draws a bogus color-pie
    REVISE). Merging keeps the card whole and makes the result the running accumulation
    of every round's edits, so the final save can't lose an earlier round's change to a
    later partial revision.
    """
    merged = dict(current)
    merged.update(_revision_field_updates(revised))
    return merged


def _apply_revision(original_card: Card, revised_data: dict) -> Card:
    """Apply a revision from the AI review to the original Card model.

    Only updates fields that the AI review is allowed to change (game data,
    not pipeline metadata); see :func:`_revision_field_updates` for the whitelist
    and the reminder-text stripping rationale.
    """
    update = _revision_field_updates(revised_data)
    update["updated_at"] = datetime.now(UTC)
    return original_card.model_copy(update=update)


# ---------------------------------------------------------------------------
# Wizard review tile + live-stream hooks
# ---------------------------------------------------------------------------

# Fields the AI Design Review tab renders per card. Built from the live (post-
# revision) card so the tile reflects what's on disk, merged with the AI verdict.
_TILE_CARD_FIELDS = (
    "name",
    "mana_cost",
    "type_line",
    "oracle_text",
    "flavor_text",
    "rarity",
    "power",
    "toughness",
    "loyalty",
    "colors",
    "collector_number",
)


def _live_tile_fields(card: dict) -> dict:
    """Display-only card fields for an in-loop tile update (mirrors ``review_tile``'s
    body). Streamed mid-loop via the council ``{"kind": "card"}`` event so the tab's
    tile shows each round's revision while the card is still "Reviewing…"; the final,
    verdict-stamped tile still lands on ``card_done``.
    """
    return {f: card.get(f) for f in _TILE_CARD_FIELDS}


# Design fields a review may change (mirrors ``_apply_revision``), each with a
# human label for the "what changed" box. Order = display order in the tab.
_REVISION_FIELD_LABELS: tuple[tuple[str, str], ...] = (
    ("name", "Name"),
    ("mana_cost", "Mana cost"),
    ("type_line", "Type"),
    ("oracle_text", "Rules text"),
    ("flavor_text", "Flavor"),
    ("power", "Power"),
    ("toughness", "Toughness"),
    ("loyalty", "Loyalty"),
    ("rarity", "Rarity"),
    ("colors", "Colors"),
    ("color_identity", "Color identity"),
    ("cmc", "Mana value"),
    ("design_notes", "Design notes"),
)


def _render_field_value(value: object) -> str:
    """Display string for a card field (lists joined, None/empty → em dash)."""
    if value is None:
        return "—"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "—"
    text = str(value).strip()
    return text if text else "—"


def _norm_field_value(value: object) -> object:
    """Comparison key that ignores cosmetic differences (list order, None vs ''/[])."""
    if value is None:
        return ""
    if isinstance(value, list):
        return sorted(str(v) for v in value) if value else ""
    return str(value).strip()


def summarize_revision(original: dict, revised: dict) -> list[dict]:
    """Field-level before/after diff of the design fields a review changed.

    ``original`` is the card as it entered review (``CardReviewResult.original_card``);
    ``revised`` is the review's ``revised_card`` (the AI's applied revision — the
    fields it actually returned). Returns one ``{field, label, before, after}``
    entry per design field the revision changed, in display order — the data behind
    the tab's "what changed" box. A field the revision did not return is skipped
    (``_apply_revision`` only applies provided fields, so its absence means "not
    changed"); diffing the AI's revision rather than the live card keeps the diff
    AI-attributed even after a later manual edit. Cosmetic-only differences (colour
    list reordering, ``None`` vs ``""``/``[]``) are not reported. Empty list when
    nothing design-relevant differs, in which case the tab shows a bare "tweaked"
    mark.
    """
    changes: list[dict] = []
    for field, label in _REVISION_FIELD_LABELS:
        if field not in revised:
            continue
        before = original.get(field)
        after = revised.get(field)
        if _norm_field_value(before) == _norm_field_value(after):
            continue
        changes.append(
            {
                "field": field,
                "label": label,
                "before": _render_field_value(before),
                "after": _render_field_value(after),
            }
        )
    return changes


def review_tile(card: dict, review: CardReviewResult | None) -> dict:
    """Build the AI Design Review tab's per-card tile.

    ``card`` is the current on-disk card dict (post-revision — the council saves
    revisions in place). ``review`` is the card's ``CardReviewResult`` (the AI
    verdict), or ``None`` when the card hasn't been reviewed yet. The tile merges
    the card's display fields with a compact view of the verdict + council so the
    tab renders the stamp, the issues, and the council summary without re-loading
    the full review JSON.

    Single source of the tile shape so the per-card SSE stream and the ``/state``
    endpoint emit byte-identical payloads.
    """
    tile: dict = {f: card.get(f) for f in _TILE_CARD_FIELDS}
    cn = card.get("collector_number") or (review.collector_number if review else "") or ""
    tile["collector_number"] = cn
    tile["reviewed"] = review is not None
    if review is None:
        tile["verdict"] = None
        tile["issues"] = []
        tile["card_was_changed"] = False
        tile["changes"] = []
        tile["review_tier"] = ""
        tile["council"] = []
        return tile
    tile["verdict"] = review.final_verdict
    tile["issues"] = [i.model_dump() for i in review.final_issues]
    tile["card_was_changed"] = review.card_was_changed
    # What the review changed: diff the pre-review snapshot against the review's own
    # revised_card (the AI's applied revision), not the live card — so a later manual
    # edit can't masquerade as an AI tweak. Only computed when the review revised the
    # card (the council saves revisions in place).
    tile["changes"] = (
        summarize_revision(review.original_card, review.revised_card)
        if review.card_was_changed and review.revised_card
        else []
    )
    tile["review_tier"] = review.review_tier
    # Compact per-reviewer summary for the (resolved) council panel: verdict +
    # issue count, no full transcript (that stays in reviews/<cn>.json). With the
    # fresh-council-per-revision loop a card can carry several rounds of reviews;
    # the resolved tile shows the *deciding* (last) panel — the one whose consensus
    # set the final verdict.
    last_round = max((cr.round for cr in review.council_reviews), default=0)
    tile["council"] = [
        {"member_id": cr.member_id, "verdict": cr.verdict, "issues": len(cr.issues)}
        for cr in review.council_reviews
        if cr.round == last_round
    ]
    return tile


def _safe_hook(hooks: object | None, name: str, *args: object) -> None:
    """Call ``hooks.<name>(*args)`` if present, swallowing errors (best-effort)."""
    if hooks is None:
        return
    fn = getattr(hooks, name, None)
    if fn is None:
        return
    try:
        fn(*args)
    except Exception:
        logger.exception("ai_review %s hook raised; continuing", name)


def _emit_card_start(hooks: object | None, card: dict, tier: str) -> None:
    """Tell the tab a card has entered review (tile shows a 'reviewing' badge)."""
    _safe_hook(
        hooks,
        "on_card_start",
        {
            "collector_number": card.get("collector_number") or card.get("slot_id") or "",
            "card_name": card.get("name") or "",
            "rarity": card.get("rarity") or "",
            "review_tier": tier,
        },
    )


def _card_council_emitter(
    hooks: object | None, collector_number: str
) -> Callable[[dict], None] | None:
    """An ``on_council(event)`` callable bound to one card's stream, or None.

    Adapts the per-card ``_review_single`` / ``_review_council`` council callback
    (which only knows the round event) to the card-scoped ``on_council(cn, event)``
    stream hook by closing over the collector number.
    """
    if hooks is None or getattr(hooks, "on_council", None) is None:
        return None

    def emit(event: dict) -> None:
        _safe_hook(hooks, "on_council", collector_number, event)

    return emit


def _emit_card_done(hooks: object | None, review: CardReviewResult, card: dict) -> None:
    """Push the resolved per-card review tile so the tab stamps the card."""
    _safe_hook(hooks, "on_card_done", review_tile(card, review))


# ---------------------------------------------------------------------------
# "Already reviewed" tracking — review only cards unseen at their current content
# ---------------------------------------------------------------------------

# Sidecar recording which cards this stage has already reviewed, keyed by
# collector_number -> a content signature of the card *as the stage last left it*.
# A later review instance reviews a card only when its current signature differs
# from the recorded one (i.e. card_gen regenerated it since), and skips cards
# already reviewed at their current content. This is tracked SEPARATELY from the
# per-card ``reviews/<cn>.json`` logs (which are collector-number-keyed and
# content-blind) because several card_gen/conformance regen passes can happen
# before the first review pass even starts — so "what's changed since the last
# instance" is not enough; the stage must remember which exact card versions it
# has personally seen.
REVIEWED_FILENAME = "reviewed.json"

# Design-relevant fields the review judges — the signature basis. Excludes
# volatile pipeline metadata (status, flags, timestamps, generation_attempts) so
# only a real design change (a regen, a manual edit) shifts the signature. Mirrors
# the fields ``_apply_revision`` is allowed to change.
_SIGNATURE_FIELDS = (
    "name",
    "mana_cost",
    "type_line",
    "oracle_text",
    "flavor_text",
    "power",
    "toughness",
    "loyalty",
    "rarity",
    "colors",
    "color_identity",
    "cmc",
    "design_notes",
)


def card_signature(card: dict) -> str:
    """A stable content hash of a card's design-relevant fields.

    Two card dicts with the same design content hash equal regardless of volatile
    metadata; a regenerated/edited card hashes differently. Lists are sorted so a
    cosmetic colour reordering doesn't read as a change.
    """
    payload = {}
    for f in _SIGNATURE_FIELDS:
        v = card.get(f)
        payload[f] = sorted(v) if isinstance(v, list) else v
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def reviewed_path(set_dir: Path) -> Path:
    """Path to the reviewed-signatures sidecar under a set's ``reviews/`` dir."""
    return set_dir / "reviews" / REVIEWED_FILENAME


def load_reviewed(set_dir: Path) -> dict[str, str]:
    """Load the reviewed-signatures sidecar (empty dict if missing / malformed)."""
    path = reviewed_path(set_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read reviewed-signatures sidecar %s", path)
        return {}
    return data if isinstance(data, dict) else {}


def save_reviewed(set_dir: Path, reviewed: dict[str, str]) -> None:
    """Persist the full reviewed-signatures map."""
    path = reviewed_path(set_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(reviewed, indent=2, ensure_ascii=False))


def record_reviewed(set_dir: Path, collector_number: str, signature: str) -> None:
    """Mark one card as reviewed at ``signature``, merging into the sidecar.

    Called per card the moment its review finishes (after any in-place revision is
    saved), so a cancelled/partial run still records exactly the cards it actually
    reviewed — a resume re-reviews only the rest.
    """
    reviewed = load_reviewed(set_dir)
    if reviewed.get(collector_number) == signature:
        return
    reviewed[collector_number] = signature
    save_reviewed(set_dir, reviewed)


# ---------------------------------------------------------------------------
# User review decisions (manual approve / revise / regenerate)
# ---------------------------------------------------------------------------

# Sidecar holding the user's manual review decisions, keyed by collector_number.
# Each value is {verdict: "approved"|"rejected", reason: str, source: "user",
# signature: str}. ``signature`` is the ``card_signature`` of the card the
# decision was made AGAINST, so a later regen/edit that changes the card body
# (same collector number, different content) makes the decision stale: the
# /state endpoint ignores a decision whose recorded signature no longer matches
# the live card and falls through to the fresh flagged/AI verdict. The AI verdict
# alone lives in reviews/<cn>.json.
DECISIONS_FILENAME = "decisions.json"


def decisions_path(set_dir: Path) -> Path:
    """Path to the user-decisions sidecar under a set's ``reviews/`` dir."""
    return set_dir / "reviews" / DECISIONS_FILENAME


def load_decisions(set_dir: Path) -> dict[str, dict]:
    """Load the user-decisions sidecar (empty dict if missing / malformed)."""
    path = decisions_path(set_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read review decisions sidecar %s", path)
        return {}
    return data if isinstance(data, dict) else {}


def save_decision(
    set_dir: Path,
    collector_number: str,
    decision: dict,
    *,
    card: dict | None = None,
) -> None:
    """Record one card's user review decision, merging into the sidecar.

    When ``card`` (the card the decision was made against) is given, its
    :func:`card_signature` is stamped onto the decision so a later regen/edit that
    rewrites the card body invalidates the decision (see :func:`decision_is_stale`).
    """
    if card is not None and "signature" not in decision:
        decision = {**decision, "signature": card_signature(card)}
    decisions = load_decisions(set_dir)
    decisions[collector_number] = decision
    path = decisions_path(set_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(decisions, indent=2, ensure_ascii=False))


def decision_is_stale(decision: dict | None, card: dict | None) -> bool:
    """True when a recorded decision's card signature no longer matches the card.

    A decision carries the ``card_signature`` of the body it was made against; a
    regen/edit changes the body (same collector number) and so the signature. A
    decision recorded WITHOUT a signature (legacy, pre-staleness) is never treated
    as stale — there's nothing to compare, so it keeps its old absolute precedence.
    """
    if not isinstance(decision, dict):
        return False
    recorded = decision.get("signature")
    if not recorded or card is None:
        return False
    return recorded != card_signature(card)


def review_is_stale(reviewed_sig: str | None, card: dict | None) -> bool:
    """True when a card's persisted AI verdict was made against a now-stale body.

    ``reviews/<cn>.json`` is keyed by collector number and merged content-blind,
    so after a regen bounce rewrites the slot's body the persisted verdict (red-X
    rejection, "tweaked by AI" diff, …) still belongs to the *archived* old card.
    The ``reviewed.json`` sidecar records the ``card_signature`` each card was
    reviewed under (see :func:`record_reviewed`), so a recorded signature that no
    longer matches the live card means the verdict is stale and the card should
    read as not-yet-reviewed until the new round verdicts the new body.

    The AI-verdict twin of :func:`decision_is_stale`. A card with NO recorded
    signature (legacy / pre-tracking project) is never treated as stale — there's
    nothing to compare, so the persisted verdict keeps its old precedence.
    """
    if not reviewed_sig or card is None:
        return False
    return reviewed_sig != card_signature(card)


def clear_decision(set_dir: Path, collector_number: str) -> None:
    """Drop a card's user decision (e.g. it was re-flagged), if present."""
    decisions = load_decisions(set_dir)
    if decisions.pop(collector_number, None) is None:
        return
    atomic_write_text(decisions_path(set_dir), json.dumps(decisions, indent=2, ensure_ascii=False))


def revise_card_in_place(
    card: dict,
    instructions: str,
    mechanics: list[dict],
    pointed_questions: list[dict],
    review_model: str,
    review_effort: str | None,
    *,
    log_dir: Path | None = None,
    review_thinking: str | None = None,
) -> dict | None:
    """Run a single user-directed revision of ``card`` (mirrors council revise-in-place).

    Builds a revise prompt from the current card plus the user's free-text
    ``instructions``, runs ONE ``generate_with_tool`` call with the revise tool
    schema (``REVISE_TOOL_SCHEMA``), and returns the revised-card dict the LLM
    produced (or ``None`` if it returned none / the call failed). The caller applies
    it via :func:`_apply_revision` and saves. This is the manual-review analogue of
    the council's in-place revision — one targeted call, no iteration loop.
    """
    base_prompt = _build_review_prompt(card, mechanics, pointed_questions)
    user_prompt = (
        f"{base_prompt}\n\n---\n\n"
        f"## Reviewer's Requested Change\n\n"
        f"A human reviewer asked for this specific change:\n\n{instructions.strip()}\n\n"
        f"Apply it and return the COMPLETE revised card with ALL fields, keeping "
        f"everything else intact and templating clean. If the request is already "
        f"satisfied or cannot be applied without breaking the card, return the card "
        f"unchanged."
    )
    try:
        result = generate_with_tool(
            system_prompt=REVIEW_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            tool_schema=REVISE_TOOL_SCHEMA,
            model=review_model,
            temperature=TEMPERATURE,
            max_tokens=HEAVY,
            effort=review_effort,
            thinking=review_thinking,
            log_dir=log_dir,
        )
    except Exception:
        logger.exception("Manual revise-in-place call failed")
        return None
    verdict_data = _coerce_verdict_data(result.get("result"))
    revised = verdict_data.get("revised_card")
    if not isinstance(revised, dict):
        return None
    # The revise schema requires a card, so the model echoes it unchanged when the
    # request is already satisfied or can't be applied. Treat a no-op revision as
    # "nothing changed" (None) so the endpoint surfaces that instead of recording a
    # vacuous approval (the old REVIEW_TOOL_SCHEMA signalled this with verdict=OK).
    if not summarize_revision(card, revised):
        return None
    return revised


# ---------------------------------------------------------------------------
# Review logging
# ---------------------------------------------------------------------------


def _save_review_log(
    review: CardReviewResult,
    reviews_dir: Path,
) -> Path:
    """Save per-card review as JSON (machine) + markdown (human-readable)."""
    reviews_dir.mkdir(parents=True, exist_ok=True)

    # JSON for resumability + summary report
    json_path = reviews_dir / f"{review.collector_number}.json"
    atomic_write_text(
        json_path,
        review.model_dump_json(indent=2),
    )

    # Markdown for human reading
    md_path = reviews_dir / f"{review.collector_number}.md"
    atomic_write_text(md_path, _review_to_markdown(review))

    return json_path


def _as_markdown_text(value: object) -> str:
    """Coerce an LLM-produced field into a markdown-safe string.

    A reviewer/synth ``analysis`` (or ``synthesis``) is *supposed* to be a string,
    but a local model sometimes returns a nested dict/list there. Appending that
    raw into the markdown ``lines`` list makes ``"\\n".join(lines)`` crash with
    ``sequence item N: expected str instance, dict found``, taking the whole
    AI-review stage down. Stringify defensively (JSON for dict/list, ``str`` for
    everything else) so a malformed payload degrades to readable text instead.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _review_to_markdown(r: CardReviewResult) -> str:
    """Render a CardReviewResult as readable markdown."""
    lines = [
        f"# Review: {r.collector_number} — {r.card_name}",
        "",
        f"- **Rarity:** {r.rarity}",
        f"- **Tier:** {r.review_tier}",
        f"- **Model:** {r.model}",
        f"- **Verdict:** {r.final_verdict}",
        f"- **Changed:** {'yes' if r.card_was_changed else 'no'}",
        f"- **Cost:** ${r.total_cost_usd:.4f}",
        f"- **Tokens:** {r.total_input_tokens:,} in / {r.total_output_tokens:,} out",
        f"- **Latency:** {r.total_latency_s:.1f}s",
        f"- **Timestamp:** {r.timestamp}",
        "",
    ]

    # Original card
    lines.append("## Original Card")
    lines.append("")
    for line in _format_card_for_review(r.original_card, include_design_notes=True).splitlines():
        lines.append(f"> {line}")
    lines.append("")

    # Council reviews (if any)
    if r.council_reviews:
        lines.append("## Council Reviews")
        lines.append("")
        for cr in r.council_reviews:
            lines.append(f"### Round {cr.round} — Reviewer {cr.member_id}")
            lines.append("")
            lines.append(f"**Verdict:** {cr.verdict} ({len(cr.issues)} issues)  ")
            lines.append(
                f"**Cost:** ${cr.cost_usd:.4f} ({cr.input_tokens:,} in / {cr.output_tokens:,} out)"
            )
            lines.append("")
            analysis = cr.response.get("analysis", "")
            if analysis:
                lines.append(_as_markdown_text(analysis))
                lines.append("")
            for issue in cr.issues:
                lines.append(f"- **[{issue.severity}] {issue.category}:** {issue.description}")
            if cr.response.get("revised_card"):
                lines.append("")
                lines.append("**Proposed revision:**")
                lines.append("")
                for line in _format_card_for_review(
                    cr.response["revised_card"], include_design_notes=True
                ).splitlines():
                    lines.append(f"> {line}")
            lines.append("")

    # Iterations (single review or synthesis)
    if r.iterations:
        label = "Synthesis Iterations" if r.council_reviews else "Review Iterations"
        lines.append(f"## {label}")
        lines.append("")
        for it in r.iterations:
            lines.append(f"### Iteration {it.iteration}")
            lines.append("")
            lines.append(f"**Verdict:** {it.verdict} ({len(it.issues)} issues)  ")
            lines.append(
                f"**Cost:** ${it.cost_usd:.4f} "
                f"({it.input_tokens:,} in / {it.output_tokens:,} out)  "
            )
            lines.append(f"**Latency:** {it.latency_s:.1f}s  ")
            lines.append(f"**Model:** {it.model}")
            lines.append("")

            # Prompt (collapsed for readability)
            lines.append("<details>")
            lines.append("<summary>Prompt</summary>")
            lines.append("")
            lines.append(it.prompt)
            lines.append("")
            lines.append("</details>")
            lines.append("")

            # Analysis
            analysis = it.response.get("analysis") or it.response.get("synthesis", "")
            if analysis:
                lines.append("**Analysis:**")
                lines.append("")
                lines.append(_as_markdown_text(analysis))
                lines.append("")

            for issue in it.issues:
                lines.append(f"- **[{issue.severity}] {issue.category}:** {issue.description}")

            if it.response.get("revised_card"):
                lines.append("")
                lines.append("**Revised card:**")
                lines.append("")
                for line in _format_card_for_review(
                    it.response["revised_card"], include_design_notes=True
                ).splitlines():
                    lines.append(f"> {line}")
            lines.append("")

    # Final revised card
    if r.card_was_changed and r.revised_card:
        lines.append("## Final Revised Card")
        lines.append("")
        for line in _format_card_for_review(r.revised_card, include_design_notes=True).splitlines():
            lines.append(f"> {line}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------


def _generate_summary_report(reviews: list[CardReviewResult]) -> str:
    """Generate a markdown summary report of all reviews."""
    total_cost = sum(r.total_cost_usd for r in reviews)
    total_in = sum(r.total_input_tokens for r in reviews)
    total_out = sum(r.total_output_tokens for r in reviews)
    changed = sum(1 for r in reviews if r.card_was_changed)
    ok_count = sum(1 for r in reviews if r.final_verdict == "OK")
    revise_count = sum(1 for r in reviews if r.final_verdict == "REVISE")

    # Determine actual model used from review results
    effective_models = {r.model for r in reviews if r.model}
    model_str = ", ".join(sorted(effective_models)) if effective_models else _review_model()

    lines = [
        "# AI Design Review Summary -- Phase 4B",
        "",
        f"Date: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Model: {model_str} (effort={_review_effort() or 'default'})",
        f"Cards reviewed: {len(reviews)}",
        f"Cards changed: {changed}",
        f"Final OK: {ok_count} | Final REVISE: {revise_count}",
        f"Total cost: ${total_cost:.2f}",
        f"Total tokens: {total_in:,} input + {total_out:,} output",
        "",
        "---",
        "",
        "## Per-Card Results",
        "",
        "| # | Card | Rarity | Tier | Verdict | Issues | Changed | Cost |",
        "|---|------|--------|------|---------|--------|---------|------|",
    ]

    for r in sorted(reviews, key=lambda x: x.collector_number):
        issue_count = len(r.final_issues)
        changed_str = "YES" if r.card_was_changed else ""
        lines.append(
            f"| {r.collector_number} | {r.card_name} | {r.rarity} | "
            f"{r.review_tier} | {r.final_verdict} | {issue_count} | "
            f"{changed_str} | ${r.total_cost_usd:.3f} |"
        )

    # Cards that were changed
    changed_reviews = [r for r in reviews if r.card_was_changed]
    if changed_reviews:
        lines.extend(
            [
                "",
                "---",
                "",
                "## Cards Changed",
                "",
            ]
        )
        for r in sorted(changed_reviews, key=lambda x: x.collector_number):
            lines.append(f"### {r.collector_number}: {r.card_name}")
            lines.append("")
            lines.append("**Issues found:**")
            all_issues: list[ReviewIssue] = []
            for it in r.iterations:
                all_issues.extend(it.issues)
            for cr in r.council_reviews:
                all_issues.extend(cr.issues)
            seen: set[str] = set()
            for issue in all_issues:
                key = f"{issue.category}:{issue.description}"
                if key not in seen:
                    seen.add(key)
                    lines.append(f"- [{issue.severity}] {issue.category}: {issue.description}")
            if r.revised_card:
                lines.append("")
                lines.append("**Revised card:**")
                lines.append(f"- Name: {r.revised_card.get('name', '?')}")
                lines.append(f"- Cost: {r.revised_card.get('mana_cost', '?')}")
                lines.append(f"- Type: {r.revised_card.get('type_line', '?')}")
                oracle = r.revised_card.get("oracle_text", "")
                if oracle:
                    lines.append(f"- Oracle: {oracle[:200]}")
            lines.append("")

    # Issue category summary
    category_counts: dict[str, int] = {}
    for r in reviews:
        for it in r.iterations:
            for issue in it.issues:
                category_counts[issue.category] = category_counts.get(issue.category, 0) + 1
        for cr in r.council_reviews:
            for issue in cr.issues:
                category_counts[issue.category] = category_counts.get(issue.category, 0) + 1

    if category_counts:
        lines.extend(
            [
                "---",
                "",
                "## Issue Categories (all iterations, including duplicates)",
                "",
                "| Category | Count |",
                "|----------|-------|",
            ]
        )
        for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
            lines.append(f"| {cat} | {count} |")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Cost Breakdown",
            "",
            "| Tier | Cards | Cost | Avg/card |",
            "|------|-------|------|----------|",
        ]
    )
    single_reviews = [r for r in reviews if r.review_tier == "single"]
    council_reviews_list = [r for r in reviews if r.review_tier == "council"]
    if single_reviews:
        s_cost = sum(r.total_cost_usd for r in single_reviews)
        lines.append(
            f"| Single (C/U) | {len(single_reviews)} | "
            f"${s_cost:.2f} | ${s_cost / len(single_reviews):.3f} |"
        )
    if council_reviews_list:
        c_cost = sum(r.total_cost_usd for r in council_reviews_list)
        lines.append(
            f"| Council (R/M) | {len(council_reviews_list)} | "
            f"${c_cost:.2f} | ${c_cost / len(council_reviews_list):.3f} |"
        )
    lines.append(
        f"| **Total** | {len(reviews)} | ${total_cost:.2f} | "
        f"${total_cost / max(len(reviews), 1):.3f} |"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def review_set(
    *,
    dry_run: bool = False,
    card_filter: str | None = None,
    skip_lands: bool = True,
    skip_reprints: bool = True,
    progress_callback: Callable[[str, int, int, str, float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    hooks: object | None = None,
) -> list[CardReviewResult]:
    """Run AI design review on all cards in the active project.

    Args:
        dry_run: If True, show plan without calling LLM.
        card_filter: If set, only review cards matching this collector number.
        skip_lands: Skip basic land cards (no design review needed).
        skip_reprints: Skip reprint cards (already designed).
        progress_callback: Optional callback(slot_id, completed, total, message, cost)
            invoked after each card is reviewed.
        should_cancel: Optional predicate polled at each card boundary; when it
            returns True the loop stops early and returns the reviews completed
            so far (each already saved to ``reviews/``, so a resume skips them).
        hooks: Optional live-review stream hooks (an ``AiReviewStreamHooks`` from
            ``pipeline.stage_hooks``, or any duck-typed object exposing
            ``on_card_start(meta)`` / ``on_council(cn, event)`` /
            ``on_card_done(tile)``). Drives the wizard tab's live council + stamps.
            Every call is best-effort — a hook raising never aborts a review.

    Returns list of CardReviewResult.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    set_code = project.set_code
    set_dir = set_artifact_dir()
    mechanics_path = set_dir / "mechanics" / "approved.json"
    pointed_q_path = set_dir / "mechanics" / "pointed-questions.json"
    reviews_dir = set_dir / "reviews"
    reports_dir = set_dir / "reports"
    # Route every reviewer/synth llmfacade transcript to the set folder, the
    # documented "<asset>/<stage>/logs" convention (mechanics -> mechanics/logs,
    # card_gen -> card_gen/logs, ...). Without this the heavy ai_review stage
    # leaves no transcript in the project — they land in llmfacade's default
    # session dirs under backend/logs/ instead.
    log_dir = set_dir / "ai_review" / "logs"

    # Resolve once for the whole stage so a mid-run settings change can't
    # swap the model between cards. Matches the "no mid-stage swap"
    # guarantee in CLAUDE.md (`Model Settings`).
    review_model = _review_model()
    review_effort = _review_effort()
    review_thinking = _review_thinking()

    logger.info("=" * 70)
    logger.info("MTGAI AI Design Review Pipeline -- Phase 4B")
    logger.info("=" * 70)
    logger.info(
        "Model: %s | Effort: %s | Thinking: %s | C/U iterations: %d | council rounds: %d",
        review_model,
        review_effort or "default",
        review_thinking or "default",
        MAX_ITERATIONS,
        MAX_COUNCIL_ROUNDS,
    )
    logger.info("Set: %s", set_code)
    logger.info("")

    # Load inputs
    mechanics = json.loads(mechanics_path.read_text(encoding="utf-8"))
    pointed_questions = json.loads(pointed_q_path.read_text(encoding="utf-8"))
    logger.info(
        "Loaded: %d mechanics, %d pointed questions",
        len(mechanics),
        len(pointed_questions),
    )

    # Load cards
    cards_dir = set_dir / "cards"
    if not cards_dir.exists():
        logger.error("No cards directory found at %s", cards_dir)
        return []

    card_paths = sorted(cards_dir.glob("*.json"))
    cards: list[dict] = []
    load_failures: list[str] = []
    for p in card_paths:
        # Parse defensively: a single corrupt/unparseable card file is skipped +
        # recorded rather than aborting the whole stage (mirrors finalize_set's
        # per-card load resilience + the card_pool builder a few lines below).
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Skipping unparseable card file for review: %s (%s)", p.name, exc)
            load_failures.append(p.name)
            continue
        # Filter
        if card_filter and raw.get("collector_number") != card_filter:
            continue
        if skip_lands and raw.get("type_line", "").startswith("Basic Land"):
            continue
        if skip_reprints and raw.get("is_reprint"):
            continue
        cards.append(raw)

    logger.info("Cards to review: %d (filtered from %d files)", len(cards), len(card_paths))
    if load_failures:
        logger.warning(
            "Skipped %d unparseable card file(s): %s",
            len(load_failures),
            ", ".join(load_failures),
        )

    # Build the full on-disk pool once so each reviewer sees a duplicate-name /
    # mechanical-similarity prior against the whole set (the documented intent of
    # validate_mechanical_similarity). Parsed defensively — a malformed card file
    # is skipped rather than aborting review. Includes lands/reprints so a
    # generated card colliding with one of those names still surfaces as a prior;
    # the per-card heuristic excludes the card under review by collector number.
    card_pool: list[Card] = []
    for p in card_paths:
        try:
            card_pool.append(load_card(p))
        except Exception:
            logger.warning("Skipping unparseable card file for review pool: %s", p.name)

    # Review only cards this stage hasn't already seen *at their current content*.
    # The reviewed-signatures sidecar persists across review instances and the
    # card_gen/conformance regen passes between them, so a card regenerated after
    # an earlier review (new content -> new signature) is re-reviewed while an
    # untouched already-reviewed card is skipped. A ``card_filter`` (explicit
    # single-card review) always runs regardless. See ``card_signature`` /
    # ``load_reviewed`` for why this is tracked separately from reviews/<cn>.json.
    if not card_filter:
        # No migration seeding from the content-blind reviews/<cn>.json logs: a
        # stale log can't tell an already-reviewed card from one regenerated since
        # it was written, so seeding from current content would wrongly skip a
        # card that changed before the first signature-tracked pass. A pre-
        # signature project therefore re-reviews its pool once, which re-establishes
        # accurate signatures; every pass after that is correctly scoped.
        reviewed = load_reviewed(set_dir)
        before = len(cards)
        cards = [
            c for c in cards if reviewed.get(c.get("collector_number") or "") != card_signature(c)
        ]
        skipped = before - len(cards)
        if skipped:
            logger.info(
                "Skipping %d card(s) already reviewed at their current content; %d to review",
                skipped,
                len(cards),
            )

    if not cards:
        logger.info("Nothing to review.")
        return []

    # Plan
    single_cards = [c for c in cards if _select_tier(c) == "single"]
    council_cards = [c for c in cards if _select_tier(c) == "council"]

    logger.info("")
    logger.info("Review plan:")
    logger.info("  Single reviewer (C/U): %d cards", len(single_cards))
    for c in single_cards:
        cn = c.get("collector_number", "?")
        logger.info("    %s: %s (%s)", cn, c["name"], c["rarity"])
    logger.info("  Council (R/M+PW/saga): %d cards", len(council_cards))
    for c in council_cards:
        cn = c.get("collector_number", "?")
        logger.info("    %s: %s (%s)", cn, c["name"], c["rarity"])
    logger.info("")

    if dry_run:
        logger.info("DRY RUN -- no API calls made.")
        return []

    # Review!
    reviews: list[CardReviewResult] = []
    start_time = time.time()

    # Tell the tab a fresh review run is starting (clears any prior live council
    # state). Resumes (which skip already-reviewed cards above) still reset — the
    # tab re-hydrates completed verdicts from /state on its next paint.
    _safe_hook(hooks, "on_reset")

    for i, card in enumerate(cards, 1):
        # Poll at the card boundary so the progress strip's Cancel button halts
        # the (potentially long) council loop between cards. Reviews completed so
        # far are already saved to reviews_dir, so the partial output is kept and
        # a resume skips them.
        if should_cancel is not None and should_cancel():
            logger.info("Review cancelled by user after %d card(s)", len(reviews))
            break

        tier = _select_tier(card)
        cn = card.get("collector_number", "?")
        logger.info(
            "--- Card %d/%d: %s [%s] ---",
            i,
            len(cards),
            cn,
            tier,
        )

        # Live council: announce this card entering review (the tab marks its
        # tile "reviewing" + readies the council panel), and route the per-round
        # council events into the card-scoped stream.
        _emit_card_start(hooks, card, tier)
        card_council = _card_council_emitter(hooks, cn)

        if tier == "council":
            result = _review_council(
                card,
                mechanics,
                pointed_questions,
                review_model,
                review_effort,
                on_council=card_council,
                review_thinking=review_thinking,
                existing_cards=card_pool,
                log_dir=log_dir,
            )
        else:
            result = _review_single(
                card,
                mechanics,
                pointed_questions,
                review_model,
                review_effort,
                on_council=card_council,
                review_thinking=review_thinking,
                existing_cards=card_pool,
                log_dir=log_dir,
            )

        reviews.append(result)

        # Save per-card log
        log_path = _save_review_log(result, reviews_dir=reviews_dir)
        logger.info(
            "  [%s] Done: %s, %d issues, changed=%s, $%.4f -> %s",
            cn,
            result.final_verdict,
            len(result.final_issues),
            result.card_was_changed,
            result.total_cost_usd,
            log_path.name,
        )

        # Apply revision to card JSON if changed. ``current_card`` tracks the
        # on-disk card the tile should reflect (the revision when one was saved,
        # else the original input dict) so the wizard tile shows the live card.
        current_card: dict = card
        if result.card_was_changed and result.revised_card:
            try:
                # Find the original card file
                original_path = None
                for p in card_paths:
                    # Match the exact stem or the ``<cn>_<slug>`` prefix — never a
                    # bare prefix, which mis-matches e.g. ``W-C-01`` against a
                    # ``W-C-011_...`` file (sorted before it), corrupting the wrong
                    # card. Same idiom as server.py:_ai_review_card_path.
                    if p.stem == cn or p.stem.startswith(cn + "_"):
                        original_path = p
                        break
                if original_path:
                    original_card = load_card(original_path)
                    updated_card = _apply_revision(original_card, result.revised_card)
                    save_card(updated_card, set_dir=set_dir)
                    current_card = updated_card.model_dump(mode="json")
                    logger.info("  [%s] Card JSON updated: %s", cn, original_path.name)
            except Exception:
                logger.exception("  [%s] Failed to apply revision to card JSON", cn)

        # Mark this card seen at its current (post-revision) content, so a later
        # review instance skips it unless card_gen regenerates it again. Recorded
        # per card (not at stage end) so a cancel/resume re-reviews only the rest.
        # Skip recording when a Cancel landed: the council loop now polls cancellation
        # mid-card, so this card's review may have been cut short — leave it unrecorded
        # so a resume re-reviews it fully rather than treating the partial pass as done.
        if not (should_cancel is not None and should_cancel()):
            record_reviewed(set_dir, cn, card_signature(current_card))

        # Live council: the verdict is in — push the per-card result tile so the
        # tab stamps the card approved / rejected (rejected = flagged for regen,
        # decided by the runner; the tile carries the AI verdict + issues).
        _emit_card_done(hooks, result, current_card)

        # Notify progress callback
        if progress_callback is not None:
            card_name = card.get("name", "???")
            progress_callback(
                cn,
                i,
                len(cards),
                f"Reviewed {card_name}: {result.final_verdict}",
                result.total_cost_usd,
            )

        logger.info("")

    elapsed = time.time() - start_time
    total_cost = sum(r.total_cost_usd for r in reviews)
    changed = sum(1 for r in reviews if r.card_was_changed)

    logger.info("=" * 70)
    logger.info("REVIEW COMPLETE")
    logger.info("=" * 70)
    logger.info("Cards reviewed:  %d", len(reviews))
    logger.info("Cards changed:   %d", changed)
    logger.info("Total cost:      $%.4f", total_cost)
    logger.info("Wall time:       %.1fs (%.1f min)", elapsed, elapsed / 60)
    logger.info("Avg cost/card:   $%.4f", total_cost / max(len(reviews), 1))

    # Load any previously completed reviews for the full summary
    all_reviews = list(reviews)
    if reviews_dir.exists():
        for rp in reviews_dir.glob("*.json"):
            cn_stem = rp.stem
            if cn_stem not in {r.collector_number for r in reviews}:
                try:
                    existing = CardReviewResult.model_validate_json(rp.read_text(encoding="utf-8"))
                    all_reviews.append(existing)
                except Exception:
                    pass

    # Generate summary report
    report = _generate_summary_report(all_reviews)
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "ai-review-summary.md"
    atomic_write_text(report_path, report)
    logger.info("Summary report:  %s", report_path)
    logger.info("Review logs:     %s", reviews_dir)

    return reviews


def _unfixable_reason(issues: list[ReviewIssue]) -> str:
    """The regen reason for a card left REVISE after the iteration budget.

    Shared by the in-run path and the resume-recovery path below so a flagged
    card carries the same reason whether its REVISE verdict was produced this run
    or read back from a persisted ``reviews/<cn>.json``.
    """
    problems = "; ".join(i.description for i in issues if i.description)
    return "Design review could not fix this card after revising: " + (
        problems or "still rated REVISE after the iteration budget."
    )


def _persisted_revise_unfixable(set_dir: Path, reviewed_this_run: set[str]) -> list[dict]:
    """Recover persisted-REVISE cards the resume filter skipped this run.

    ``review_set`` records every reviewed card's content signature regardless of
    verdict, and a resume skips any card still present at that signature — so a
    card the *earlier* (cancelled/crashed) partial run rated final REVISE never
    re-enters the current run's ``reviews`` and would otherwise never be flagged
    for regen, silently shipping as if approved. This reads back each such card's
    persisted verdict and re-surfaces it as unfixable.

    A persisted REVISE is only re-surfaced when (a) the current run did NOT review
    that card, and (b) the card is still present on disk *at the signature it was
    reviewed under* — the same gate that caused the resume to skip it. That gate
    guarantees the persisted verdict is not stale: if the card had been
    regenerated since, its signature would differ and the current run would have
    re-reviewed it (overwriting the persisted json).
    """
    reviews_dir = set_dir / "reviews"
    if not reviews_dir.exists():
        return []
    reviewed_sigs = load_reviewed(set_dir)
    cards_dir = set_dir / "cards"
    recovered: list[dict] = []
    for rp in sorted(reviews_dir.glob("*.json")):
        cn = rp.stem
        if cn in reviewed_this_run:
            continue
        try:
            result = CardReviewResult.model_validate_json(rp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if result.final_verdict != "REVISE":
            continue
        # Confirm the card is still on disk at the signature it was reviewed under
        # (the resume-skip gate), so we never flag a stale persisted verdict for a
        # card that was edited/regenerated but not yet re-reviewed.
        recorded_sig = reviewed_sigs.get(cn)
        if not recorded_sig:
            continue
        live_sig = None
        if cards_dir.exists():
            for cp in sorted(cards_dir.glob(f"{cn}_*.json")):
                try:
                    live_sig = card_signature(json.loads(cp.read_text(encoding="utf-8")))
                except (OSError, json.JSONDecodeError):
                    live_sig = None
                break
        if live_sig != recorded_sig:
            continue
        recovered.append({"slot_id": cn, "reason": _unfixable_reason(result.final_issues)})
    return recovered


def review_all_cards(
    *,
    progress_callback: Callable[[str, int, int, str, float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    hooks: object | None = None,
) -> dict:
    """Run AI design review on all cards in the active project, returning a summary dict.

    This is the pipeline orchestration entry point. It delegates to ``review_set``
    and returns a dict with keys ``reviewed``, ``revised``, ``cost_usd``,
    ``unfixable``, ``cancelled``, and ``summary``.

    Args:
        progress_callback: Optional callback(slot_id, completed, total, message, cost)
            invoked after each card is reviewed.
        should_cancel: Optional predicate threaded into ``review_set`` and polled
            at each card boundary so the AI-lock Cancel button halts the loop.
        hooks: Optional live-review stream hooks threaded into ``review_set`` to
            drive the wizard tab's live council + per-card stamps.
    """
    reviews = review_set(
        progress_callback=progress_callback, should_cancel=should_cancel, hooks=hooks
    )
    cancelled = should_cancel is not None and should_cancel()
    reviewed = len(reviews)
    revised = sum(1 for r in reviews if r.card_was_changed)
    cost_usd = sum(r.total_cost_usd for r in reviews)
    ok_count = sum(1 for r in reviews if r.final_verdict == "OK")

    # Hybrid escape hatch: in-place council revision is the primary action (applied +
    # saved above), but a card still rated REVISE after the council-round budget
    # (MAX_COUNCIL_ROUNDS fresh councils for the council tier, MAX_ITERATIONS for the
    # C/U single-reviewer tier) is *unfixable in place* — surface it so the runner can
    # flag it for a from-scratch regen via the loop. The best in-place attempt stays
    # saved; the regen archives + replaces it.
    unfixable: list[dict] = []
    for r in reviews:
        if r.final_verdict != "REVISE":
            continue
        unfixable.append(
            {"slot_id": r.collector_number, "reason": _unfixable_reason(r.final_issues)}
        )

    # Recover persisted-REVISE cards a resume skipped: an earlier cancelled/crashed
    # partial run can have rated a card final REVISE and recorded its signature, so
    # the resume filter skips it and it never re-enters ``reviews`` above — without
    # this it would never be flagged for regen and would ship as if approved.
    # Skipped on a cancelled run: the unfixable list is treated as partial by the
    # runner and not flagged from at all (see run_ai_review).
    if not cancelled:
        reviewed_cns = {r.collector_number for r in reviews}
        try:
            from mtgai.io.asset_paths import set_artifact_dir

            recovered = _persisted_revise_unfixable(set_artifact_dir(), reviewed_cns)
        except Exception:
            logger.exception("Failed to recover persisted-REVISE cards for flagging")
            recovered = []
        if recovered:
            logger.info(
                "Recovered %d resume-skipped REVISE card(s) for regen flagging: %s",
                len(recovered),
                ", ".join(u["slot_id"] for u in recovered),
            )
            unfixable.extend(recovered)

    summary = (
        f"AI review complete: {reviewed} cards reviewed, {revised} revised, "
        f"{ok_count} OK, {len(unfixable)} unfixable, ${cost_usd:.2f} total cost"
    )
    return {
        "reviewed": reviewed,
        "revised": revised,
        "cost_usd": cost_usd,
        "unfixable": unfixable,
        "cancelled": cancelled,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run AI design review on generated MTG cards",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show review plan without calling LLM",
    )
    parser.add_argument(
        "--card",
        type=str,
        default=None,
        help="Review only this collector number (e.g. W-C-01)",
    )
    parser.add_argument(
        "--include-lands",
        action="store_true",
        help="Include basic land cards in review",
    )
    parser.add_argument(
        "--include-reprints",
        action="store_true",
        help="Include reprint cards in review",
    )
    args = parser.parse_args()

    review_set(
        dry_run=args.dry_run,
        card_filter=args.card,
        skip_lands=not args.include_lands,
        skip_reprints=not args.include_reprints,
    )
