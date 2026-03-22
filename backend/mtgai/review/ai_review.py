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

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from mtgai.generation.llm_client import cost_from_result, generate_with_tool
from mtgai.generation.prompts import format_mechanic_block
from mtgai.io.card_io import load_card, save_card
from mtgai.models.card import Card

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SET_CODE = "ASD"
OUTPUT_ROOT = Path("C:/Programming/MTGAI/output")
MECHANICS_PATH = OUTPUT_ROOT / "sets" / DEFAULT_SET_CODE / "mechanics" / "approved.json"
POINTED_Q_PATH = OUTPUT_ROOT / "sets" / DEFAULT_SET_CODE / "mechanics" / "pointed-questions.json"
THEME_PATH = OUTPUT_ROOT / "sets" / DEFAULT_SET_CODE / "theme.json"
REVIEWS_DIR = OUTPUT_ROOT / "sets" / DEFAULT_SET_CODE / "reviews"
REPORTS_DIR = OUTPUT_ROOT / "sets" / DEFAULT_SET_CODE / "reports"

# LLM settings — defaults (active values come from model_settings at runtime)
MODEL = "claude-opus-4-6"
EFFORT = "max"
TEMPERATURE = 1.0
MAX_ITERATIONS = 5


def _review_model() -> str:
    """Get the review model from settings."""
    from mtgai.settings.model_settings import get_llm_model

    return get_llm_model("ai_review")


def _review_effort() -> str | None:
    """Get the review effort from settings."""
    from mtgai.settings.model_settings import get_effort

    return get_effort("ai_review")


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
reviewing custom cards for a set called "Anomalous Descent" (set code ASD), a \
60-card dev set with a post-apocalyptic megadungeon theme.

Your job is to review each card for design quality and correctness. Be thorough \
but fair. Focus on real issues, not nitpicks.

Focus on:
- Oracle text correctness and MTG templating (use modern templating conventions)
- Balance relative to comparable printed cards at the same rarity
- Design quality (focused purpose, no kitchen sink, real variability)
- Keyword interactions and nonbos
- Color pie adherence
Do NOT flag:
- JSON metadata issues (e.g., keywords field) -- that's a data format concern
- Missing reminder text -- it is added programmatically after review
- Balance concerns where the card has a meaningful drawback that compensates
- Malfunction cards being above-rate -- malfunction IS the drawback, the delay is the point
- Vanilla/french vanilla creatures being simple -- that's intentional at common"""


def _format_card_for_review(card: dict) -> str:
    """Format a card dict into a readable text block."""
    lines = [
        f"Name: {card['name']}",
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
        lines.append(f"P/T: {card['power']}/{card['toughness']}")
    if card.get("loyalty") is not None:
        lines.append(f"Loyalty: {card['loyalty']}")
    notes = card.get("design_notes")
    if notes:
        lines.append(f"Design Notes: {notes}")
    # Include heuristic validation warnings from generation (MANUAL errors)
    val_errors: list[str] = []
    for attempt in card.get("generation_attempts", []):
        val_errors.extend(attempt.get("validation_errors", []))
    if val_errors:
        lines.append("Validation Warnings (from auto-validator):")
        for err in dict.fromkeys(val_errors):  # dedupe, preserve order
            lines.append(f"  - {err}")
    return "\n".join(lines)


def _build_review_prompt(
    card: dict,
    mechanics: list[dict],
    pointed_questions: list[dict],
) -> str:
    """Build the user prompt for a single-reviewer review."""
    card_text = _format_card_for_review(card)

    # Only include mechanics relevant to this card's colors
    card_colors = set(card.get("colors", []))
    if not card_colors:
        # Colorless/land — include all mechanics
        card_colors = {"W", "U", "B", "R", "G"}
    mech_block = format_mechanic_block(mechanics, card_colors)

    # Build pointed questions section
    pq_lines = []
    for i, pq in enumerate(pointed_questions, 1):
        pq_lines.append(f"{i}. {pq['question']}")
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


def _build_iteration_prompt(previous_verdict: dict) -> str:
    """Build the follow-up prompt for an iteration after a REVISE verdict."""
    issues_text = ""
    for issue in previous_verdict.get("issues", []):
        issues_text += f"- [{issue['severity']}] {issue['category']}: {issue['description']}\n"

    revised = previous_verdict.get("revised_card")
    card_text = _format_card_for_review(revised) if revised else "(no revised card provided)"

    return (
        f"You revised the card. Here is your revision:\n\n{card_text}\n\n"
        f"Issues you identified:\n{issues_text}\n"
        f"Now review YOUR REVISION with the same rigor. Does the revised card "
        f"fix all the issues without introducing new ones? Check templating, "
        f"balance, design, color pie, and the pointed questions again.\n\n"
        f"If the revised card is now good, verdict is OK. If it still needs "
        f"changes, verdict is REVISE with a new revision."
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
# Single-reviewer review (C/U tier)
# ---------------------------------------------------------------------------


def _review_single(
    card: dict,
    mechanics: list[dict],
    pointed_questions: list[dict],
    max_iterations: int = MAX_ITERATIONS,
) -> CardReviewResult:
    """Single Opus reviewer + iteration loop for C/U cards."""
    collector_number = card.get("collector_number", card.get("slot_id", "???"))
    card_name = card.get("name", "???")
    rarity = card.get("rarity", "???")

    logger.info("  [%s] Single review: %s (%s)", collector_number, card_name, rarity)

    iterations: list[ReviewIteration] = []
    total_in = 0
    total_out = 0
    total_cost = 0.0
    total_latency = 0.0

    # First iteration
    user_prompt = _build_review_prompt(card, mechanics, pointed_questions)

    for iteration in range(1, max_iterations + 1):
        logger.info("    Iteration %d/%d...", iteration, max_iterations)

        t0 = time.time()
        try:
            result = generate_with_tool(
                system_prompt=REVIEW_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                tool_schema=REVIEW_TOOL_SCHEMA,
                model=_review_model(),
                temperature=TEMPERATURE,
                max_tokens=8192,
                effort=_review_effort(),
            )
        except Exception:
            logger.exception("    API call failed on iteration %d", iteration)
            break

        latency = time.time() - t0
        effective_model = result.get("model", _review_model())
        cost = cost_from_result(result)
        total_in += (
            result["input_tokens"]
            + result.get("cache_creation_input_tokens", 0)
            + result.get("cache_read_input_tokens", 0)
        )
        total_out += result["output_tokens"]
        total_cost += cost
        total_latency += latency

        verdict_data = result["result"]
        verdict = verdict_data.get("verdict", "OK")
        issues = [ReviewIssue(**i) for i in verdict_data.get("issues", [])]

        logger.info(
            "    Verdict: %s (%d issues), $%.4f, %.1fs",
            verdict,
            len(issues),
            cost,
            latency,
        )

        iterations.append(
            ReviewIteration(
                iteration=iteration,
                prompt=user_prompt,
                response=verdict_data,
                verdict=verdict,
                issues=issues,
                model=effective_model,
                input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"],
                cost_usd=cost,
                latency_s=latency,
            )
        )

        if verdict == "OK":
            break

        # Card was revised — iterate on the revision
        if iteration < max_iterations:
            user_prompt = _build_iteration_prompt(verdict_data)
        # else: loop ends, we keep the last REVISE verdict

    # Final result
    last = iterations[-1] if iterations else None
    final_verdict = last.verdict if last else "OK"
    final_issues = last.issues if last else []
    revised_card = last.response.get("revised_card") if last and final_verdict == "OK" else None

    # If the last iteration was REVISE, we accept the revision
    if final_verdict == "REVISE" and last:
        revised_card = last.response.get("revised_card")

    # Check if any iteration produced a revision (even if final is OK,
    # the OK might be approving a previously revised card)
    card_was_changed = False
    for it in iterations:
        if it.response.get("revised_card") is not None:
            card_was_changed = True
            # Track the latest revision
            revised_card = it.response.get("revised_card")

    effective_model = iterations[0].model if iterations else _review_model()

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
# Council review (R/M tier)
# ---------------------------------------------------------------------------


def _review_council(
    card: dict,
    mechanics: list[dict],
    pointed_questions: list[dict],
    num_reviewers: int = 3,
    max_iterations: int = MAX_ITERATIONS,
) -> CardReviewResult:
    """Full council (3 independent reviewers + synthesizer) + iteration for R/M cards."""
    collector_number = card.get("collector_number", card.get("slot_id", "???"))
    card_name = card.get("name", "???")
    rarity = card.get("rarity", "???")

    logger.info(
        "  [%s] Council review (%d reviewers): %s (%s)",
        collector_number,
        num_reviewers,
        card_name,
        rarity,
    )

    council_reviews: list[CouncilMemberReview] = []
    effective_model = _review_model()
    total_in = 0
    total_out = 0
    total_cost = 0.0
    total_latency = 0.0

    user_prompt = _build_review_prompt(card, mechanics, pointed_questions)

    # Phase 1: Independent reviews
    all_ok = True
    for member_id in range(1, num_reviewers + 1):
        logger.info("    Reviewer %d/%d...", member_id, num_reviewers)

        t0 = time.time()
        try:
            result = generate_with_tool(
                system_prompt=REVIEW_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                tool_schema=REVIEW_TOOL_SCHEMA,
                model=_review_model(),
                temperature=TEMPERATURE,
                max_tokens=8192,
                effort=_review_effort(),
            )
        except Exception:
            logger.exception("    Reviewer %d API call failed", member_id)
            continue

        latency = time.time() - t0
        effective_model = result.get("model", _review_model())
        cost = cost_from_result(result)
        total_in += (
            result["input_tokens"]
            + result.get("cache_creation_input_tokens", 0)
            + result.get("cache_read_input_tokens", 0)
        )
        total_out += result["output_tokens"]
        total_cost += cost
        total_latency += latency

        verdict_data = result["result"]
        verdict = verdict_data.get("verdict", "OK")
        verdict_data["verdict"] = verdict  # ensure key exists for synthesis prompt
        issues = [ReviewIssue(**i) for i in verdict_data.get("issues", [])]

        logger.info(
            "    Reviewer %d: %s (%d issues), $%.4f",
            member_id,
            verdict,
            len(issues),
            cost,
        )

        if verdict != "OK":
            all_ok = False

        council_reviews.append(
            CouncilMemberReview(
                member_id=member_id,
                verdict=verdict,
                issues=issues,
                response=verdict_data,
                input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"],
                cost_usd=cost,
            )
        )

    # Skip synthesis if all reviewers say OK
    if all_ok and len(council_reviews) == num_reviewers:
        logger.info("    All %d reviewers say OK -- skipping synthesis", num_reviewers)
        return CardReviewResult(
            collector_number=collector_number,
            card_name=card_name,
            rarity=rarity,
            review_tier="council",
            model=effective_model,
            original_card=card,
            final_verdict="OK",
            final_issues=[],
            revised_card=None,
            card_was_changed=False,
            iterations=[],
            council_reviews=council_reviews,
            total_input_tokens=total_in,
            total_output_tokens=total_out,
            total_cost_usd=total_cost,
            total_latency_s=total_latency,
            timestamp=datetime.now(UTC).isoformat(),
        )

    # Phase 2: Synthesis
    logger.info("    Synthesizing %d reviews...", len(council_reviews))
    synthesis_prompt = _build_council_synthesis_prompt(
        card,
        [r.response for r in council_reviews],
    )

    # Include mechanic defs in synthesis context
    card_colors = set(card.get("colors", []))
    if not card_colors:
        card_colors = {"W", "U", "B", "R", "G"}
    mech_block = format_mechanic_block(mechanics, card_colors)
    synthesis_prompt = f"## Custom Mechanics\n\n{mech_block}\n\n---\n\n{synthesis_prompt}"

    iterations: list[ReviewIteration] = []

    for iteration in range(1, max_iterations + 1):
        logger.info("    Synthesis iteration %d/%d...", iteration, max_iterations)

        t0 = time.time()
        try:
            if iteration == 1:
                tool = COUNCIL_SYNTHESIS_TOOL_SCHEMA
                prompt = synthesis_prompt
            else:
                tool = REVIEW_TOOL_SCHEMA
                prompt = _build_iteration_prompt(iterations[-1].response)

            result = generate_with_tool(
                system_prompt=REVIEW_SYSTEM_PROMPT,
                user_prompt=prompt,
                tool_schema=tool,
                model=_review_model(),
                temperature=TEMPERATURE,
                max_tokens=8192,
                effort=_review_effort(),
            )
        except Exception:
            logger.exception("    Synthesis API call failed on iteration %d", iteration)
            break

        latency = time.time() - t0
        effective_model = result.get("model", _review_model())
        cost = cost_from_result(result)
        total_in += (
            result["input_tokens"]
            + result.get("cache_creation_input_tokens", 0)
            + result.get("cache_read_input_tokens", 0)
        )
        total_out += result["output_tokens"]
        total_cost += cost
        total_latency += latency

        verdict_data = result["result"]
        verdict = verdict_data.get("verdict", "OK")
        issues = [ReviewIssue(**i) for i in verdict_data.get("issues", [])]

        logger.info(
            "    Synthesis verdict: %s (%d issues), $%.4f, %.1fs",
            verdict,
            len(issues),
            cost,
            latency,
        )

        iterations.append(
            ReviewIteration(
                iteration=iteration,
                prompt=prompt,
                response=verdict_data,
                verdict=verdict,
                issues=issues,
                model=effective_model,
                input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"],
                cost_usd=cost,
                latency_s=latency,
            )
        )

        if verdict == "OK":
            break

        if iteration >= max_iterations:
            break

    # Final result
    last = iterations[-1] if iterations else None
    final_verdict = last.verdict if last else "OK"
    final_issues = last.issues if last else []

    card_was_changed = False
    revised_card = None
    for it in iterations:
        if it.response.get("revised_card") is not None:
            card_was_changed = True
            revised_card = it.response.get("revised_card")

    # Use model from synthesis iterations if available, else from council reviews
    if iterations:
        effective_model = iterations[0].model

    return CardReviewResult(
        collector_number=collector_number,
        card_name=card_name,
        rarity=rarity,
        review_tier="council",
        model=effective_model,
        original_card=card,
        final_verdict=final_verdict,
        final_issues=final_issues,
        revised_card=revised_card if card_was_changed else None,
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


def _apply_revision(original_card: Card, revised_data: dict) -> Card:
    """Apply a revision from the AI review to the original Card model.

    Only updates fields that the AI review is allowed to change (game data,
    not pipeline metadata).
    """
    update: dict = {}
    for field in (
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
    ):
        if field in revised_data:
            update[field] = revised_data[field]
    update["updated_at"] = datetime.now(UTC)
    return original_card.model_copy(update=update)


# ---------------------------------------------------------------------------
# Review logging
# ---------------------------------------------------------------------------


def _save_review_log(
    review: CardReviewResult,
    reviews_dir: Path = REVIEWS_DIR,
) -> Path:
    """Save per-card review as JSON (machine) + markdown (human-readable)."""
    reviews_dir.mkdir(parents=True, exist_ok=True)

    # JSON for resumability + summary report
    json_path = reviews_dir / f"{review.collector_number}.json"
    json_path.write_text(
        review.model_dump_json(indent=2),
        encoding="utf-8",
    )

    # Markdown for human reading
    md_path = reviews_dir / f"{review.collector_number}.md"
    md_path.write_text(_review_to_markdown(review), encoding="utf-8")

    return json_path


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
    for line in _format_card_for_review(r.original_card).splitlines():
        lines.append(f"> {line}")
    lines.append("")

    # Council reviews (if any)
    if r.council_reviews:
        lines.append("## Council Reviews")
        lines.append("")
        for cr in r.council_reviews:
            lines.append(f"### Reviewer {cr.member_id}")
            lines.append("")
            lines.append(f"**Verdict:** {cr.verdict} ({len(cr.issues)} issues)  ")
            lines.append(
                f"**Cost:** ${cr.cost_usd:.4f} ({cr.input_tokens:,} in / {cr.output_tokens:,} out)"
            )
            lines.append("")
            analysis = cr.response.get("analysis", "")
            if analysis:
                lines.append(analysis)
                lines.append("")
            for issue in cr.issues:
                lines.append(f"- **[{issue.severity}] {issue.category}:** {issue.description}")
            if cr.response.get("revised_card"):
                lines.append("")
                lines.append("**Proposed revision:**")
                lines.append("")
                for line in _format_card_for_review(cr.response["revised_card"]).splitlines():
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
                lines.append(analysis)
                lines.append("")

            for issue in it.issues:
                lines.append(f"- **[{issue.severity}] {issue.category}:** {issue.description}")

            if it.response.get("revised_card"):
                lines.append("")
                lines.append("**Revised card:**")
                lines.append("")
                for line in _format_card_for_review(it.response["revised_card"]).splitlines():
                    lines.append(f"> {line}")
            lines.append("")

    # Final revised card
    if r.card_was_changed and r.revised_card:
        lines.append("## Final Revised Card")
        lines.append("")
        for line in _format_card_for_review(r.revised_card).splitlines():
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
    set_code: str = DEFAULT_SET_CODE,
    dry_run: bool = False,
    card_filter: str | None = None,
    skip_lands: bool = True,
    skip_reprints: bool = True,
    progress_callback: Callable[[str, int, int, str, float], None] | None = None,
) -> list[CardReviewResult]:
    """Run AI design review on all cards in a set.

    Args:
        set_code: Set code to review.
        dry_run: If True, show plan without calling LLM.
        card_filter: If set, only review cards matching this collector number.
        skip_lands: Skip basic land cards (no design review needed).
        skip_reprints: Skip reprint cards (already designed).
        progress_callback: Optional callback(slot_id, completed, total, message, cost)
            invoked after each card is reviewed.

    Returns list of CardReviewResult.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Derive paths from set_code
    set_dir = OUTPUT_ROOT / "sets" / set_code
    mechanics_path = set_dir / "mechanics" / "approved.json"
    pointed_q_path = set_dir / "mechanics" / "pointed-questions.json"
    reviews_dir = set_dir / "reviews"
    reports_dir = set_dir / "reports"

    logger.info("=" * 70)
    logger.info("MTGAI AI Design Review Pipeline -- Phase 4B")
    logger.info("=" * 70)
    logger.info(
        "Model: %s | Effort: %s | Max iterations: %d",
        _review_model(),
        _review_effort() or "default",
        MAX_ITERATIONS,
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
    cards_dir = OUTPUT_ROOT / "sets" / set_code / "cards"
    if not cards_dir.exists():
        logger.error("No cards directory found at %s", cards_dir)
        return []

    card_paths = sorted(cards_dir.glob("*.json"))
    cards: list[dict] = []
    for p in card_paths:
        raw = json.loads(p.read_text(encoding="utf-8"))
        # Filter
        if card_filter and raw.get("collector_number") != card_filter:
            continue
        if skip_lands and raw.get("type_line", "").startswith("Basic Land"):
            continue
        if skip_reprints and raw.get("is_reprint"):
            continue
        cards.append(raw)

    logger.info("Cards to review: %d (filtered from %d files)", len(cards), len(card_paths))

    # Check for existing review progress
    completed: set[str] = set()
    if reviews_dir.exists() and not card_filter:
        for rp in reviews_dir.glob("*.json"):
            completed.add(rp.stem)
    if completed:
        logger.info("Found %d existing reviews -- will skip those", len(completed))
        cards = [c for c in cards if c.get("collector_number") not in completed]
        logger.info("Cards remaining: %d", len(cards))

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

    for i, card in enumerate(cards, 1):
        tier = _select_tier(card)
        cn = card.get("collector_number", "?")
        logger.info(
            "--- Card %d/%d: %s [%s] ---",
            i,
            len(cards),
            cn,
            tier,
        )

        if tier == "council":
            result = _review_council(card, mechanics, pointed_questions)
        else:
            result = _review_single(card, mechanics, pointed_questions)

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

        # Apply revision to card JSON if changed
        if result.card_was_changed and result.revised_card:
            try:
                # Find the original card file
                original_path = None
                for p in card_paths:
                    if p.stem.startswith(cn):
                        original_path = p
                        break
                if original_path:
                    original_card = load_card(original_path)
                    updated_card = _apply_revision(original_card, result.revised_card)
                    save_card(updated_card, OUTPUT_ROOT)
                    logger.info("  [%s] Card JSON updated: %s", cn, original_path.name)
            except Exception:
                logger.exception("  [%s] Failed to apply revision to card JSON", cn)

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
    report_path.write_text(report, encoding="utf-8")
    logger.info("Summary report:  %s", report_path)
    logger.info("Review logs:     %s", reviews_dir)

    return reviews


def review_all_cards(
    *,
    set_code: str = DEFAULT_SET_CODE,
    progress_callback: Callable[[str, int, int, str, float], None] | None = None,
) -> dict:
    """Run AI design review on all cards, returning a summary dict.

    This is the pipeline orchestration entry point. It delegates to ``review_set``
    and returns a dict with keys ``reviewed``, ``revised``, ``cost_usd``, and
    ``summary``.

    Args:
        set_code: Set code to review.
        progress_callback: Optional callback(slot_id, completed, total, message, cost)
            invoked after each card is reviewed.
    """
    reviews = review_set(
        set_code=set_code,
        progress_callback=progress_callback,
    )
    reviewed = len(reviews)
    revised = sum(1 for r in reviews if r.card_was_changed)
    cost_usd = sum(r.total_cost_usd for r in reviews)
    ok_count = sum(1 for r in reviews if r.final_verdict == "OK")
    summary = (
        f"AI review complete: {reviewed} cards reviewed, {revised} revised, "
        f"{ok_count} OK, ${cost_usd:.2f} total cost"
    )
    return {
        "reviewed": reviewed,
        "revised": revised,
        "cost_usd": cost_usd,
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
