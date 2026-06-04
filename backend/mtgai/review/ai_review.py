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


def _review_model() -> str:
    """Get the review model from the active project's settings."""
    from mtgai.runtime.active_project import require_active_project

    return require_active_project().settings.get_llm_model_id("ai_review")


def _review_effort() -> str | None:
    """Get the review effort from the active project's settings."""
    from mtgai.runtime.active_project import require_active_project

    return require_active_project().settings.get_effort("ai_review")


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
Do NOT flag:
- JSON metadata issues (e.g., keywords field) -- that's a data format concern
- Missing reminder text -- it is added programmatically after review
- Balance concerns where the card has a meaningful drawback that compensates
- A card being above-rate when a custom mechanic embeds an inherent drawback that \
compensates -- the drawback IS the cost
- Vanilla/french vanilla creatures being simple -- that's intentional at common"""


def _format_card_for_review(card: dict) -> str:
    """Format a card dict into a readable text block.

    Heuristic design-judgment warnings (power level, color pie) are computed
    **fresh** against the supplied card via
    :func:`mtgai.analysis.heuristic_checks.check_card_heuristics` rather than
    read from ``generation_attempts[].validation_errors`` — so a revision
    produced mid-review sees warnings about its own current state, not the
    original gen-time draft. Mechanical similarity (cross-set) is intentionally
    skipped here; it's a set-level concern (the old render_qa stage that
    surfaced it was dropped in the art/render topology reorg).
    """
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

    # Fresh heuristic checks — power level, color pie. Wrapped so a card dict
    # that can't be parsed (e.g. a malformed mid-review revision) doesn't
    # crash the prompt builder; the warnings are advisory.
    heuristic_block = _heuristic_warnings_for_card_dict(card)
    if heuristic_block:
        lines.append(heuristic_block)
    return "\n".join(lines)


def _heuristic_warnings_for_card_dict(card: dict) -> str:
    """Run check_card_heuristics against ``card`` and format findings for the prompt.

    Returns an empty string if the card can't be parsed or has no findings.
    """
    from mtgai.analysis.heuristic_checks import check_card_heuristics, format_findings_for_prompt
    from mtgai.models.card import Card
    from mtgai.validation.mana import derive_mana_fields

    try:
        # Saved cards have derived mana fields; in-flight revisions might not.
        # Re-derive defensively so the validators see consistent input.
        enriched = {**card}
        enriched.update(derive_mana_fields(enriched.get("mana_cost"), enriched.get("oracle_text")))
        parsed = Card.model_validate(enriched)
    except Exception:
        return ""
    findings = check_card_heuristics(parsed, existing_cards=None)
    return format_findings_for_prompt(findings)


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
) -> CardReviewResult:
    """Single Opus reviewer + iteration loop for C/U cards.

    ``review_model`` / ``review_effort`` are resolved once by the caller
    (``review_set``) before the per-card loop starts so a mid-run settings
    change can't swap the model between cards.

    ``on_council`` (optional) reports live progress for the wizard tab: each
    iteration is a one-reviewer "round" with a single verdict slot, so a card
    being reviewed shows the same 👍/👎 timeline the council tier does. It is
    best-effort — a hook raising never breaks the review.
    """
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

        # Live council: a single-reviewer iteration is one "round" with one
        # verdict slot. Announce the reviewer reading (no verdict yet) so the
        # tab's spinner shows, then fill the slot once the verdict lands.
        _safe_council(on_council, {"kind": "round", "round": iteration, "verdicts": []})

        t0 = time.time()
        try:
            result = generate_with_tool(
                system_prompt=REVIEW_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                tool_schema=REVIEW_TOOL_SCHEMA,
                model=review_model,
                temperature=TEMPERATURE,
                max_tokens=HEAVY,
                effort=review_effort,
            )
        except Exception:
            logger.exception("    API call failed on iteration %d", iteration)
            _safe_council(on_council, {"kind": "round", "round": iteration, "verdicts": ["error"]})
            break

        latency = time.time() - t0
        effective_model = result.get("model", review_model)
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

        _safe_council(
            on_council,
            {"kind": "round", "round": iteration, "verdicts": [_verdict_glyph(verdict)]},
        )

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

    # Final result. If every LLM call failed (``iterations`` empty), the card was
    # never actually reviewed — surface a REVISE/error verdict so the runner flags
    # it for human attention rather than silently passing it as OK (the bug this
    # guards against). The exception itself was already logged via
    # ``logger.exception`` above; log the empty-iterations outcome explicitly so
    # the silent-pass cause is observable in the review log.
    if not iterations:
        logger.error(
            "  [%s] Review produced no iterations (all LLM calls failed) — "
            "flagging REVISE instead of defaulting OK",
            collector_number,
        )
        return _error_review_result(
            card, "single", review_model, collector_number, card_name, rarity
        )

    last = iterations[-1]
    final_verdict = last.verdict
    final_issues = last.issues
    revised_card = last.response.get("revised_card") if final_verdict == "OK" else None

    # If the last iteration was REVISE, we accept the revision
    if final_verdict == "REVISE":
        revised_card = last.response.get("revised_card")

    # Check if any iteration produced a revision (even if final is OK,
    # the OK might be approving a previously revised card)
    card_was_changed = False
    for it in iterations:
        if it.response.get("revised_card") is not None:
            card_was_changed = True
            # Track the latest revision
            revised_card = it.response.get("revised_card")

    effective_model = iterations[0].model

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
    user_prompt = _build_review_prompt(card, mechanics, pointed_questions)
    _safe_council(on_council, {"kind": "round", "round": round_no, "verdicts": []})
    for member_id in range(1, num_reviewers + 1):
        if should_cancel is not None and should_cancel():
            break
        logger.info("    Round %d reviewer %d/%d...", round_no, member_id, num_reviewers)
        t0 = time.time()
        try:
            result = generate_with_tool(
                system_prompt=REVIEW_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                tool_schema=REVIEW_TOOL_SCHEMA,
                model=review_model,
                temperature=TEMPERATURE,
                max_tokens=HEAVY,
                effort=review_effort,
            )
        except Exception:
            logger.exception("    Round %d reviewer %d API call failed", round_no, member_id)
            panel_verdicts.append("error")
            _safe_council(
                on_council,
                {"kind": "round", "round": round_no, "verdicts": list(panel_verdicts)},
            )
            continue
        latency = time.time() - t0
        cost = acc.record(result, latency)
        verdict_data = result["result"]
        verdict = verdict_data.get("verdict", "OK")
        verdict_data["verdict"] = verdict  # ensure key exists for the synthesis prompt
        issues = [ReviewIssue(**i) for i in verdict_data.get("issues", [])]
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
    try:
        result = generate_with_tool(
            system_prompt=REVIEW_SYSTEM_PROMPT,
            user_prompt=synthesis_prompt,
            tool_schema=COUNCIL_SYNTHESIS_TOOL_SCHEMA,
            model=review_model,
            temperature=TEMPERATURE,
            max_tokens=HEAVY,
            effort=review_effort,
        )
    except Exception:
        logger.exception("    Round %d synthesis (revise) call failed", round_no)
        return None, acc, None
    latency = time.time() - t0
    cost = acc.record(result, latency)
    verdict_data = result["result"]
    issues = [ReviewIssue(**i) for i in verdict_data.get("issues", [])]
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
        current_card = revised
        card_was_changed = True

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
        tile["review_tier"] = ""
        tile["council"] = []
        return tile
    tile["verdict"] = review.final_verdict
    tile["issues"] = [i.model_dump() for i in review.final_issues]
    tile["card_was_changed"] = review.card_was_changed
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
# Each value is {verdict: "approved"|"rejected", reason: str, source: "user"}.
# The /state endpoint merges this over the AI verdict so a reload keeps the
# user's call (the AI verdict alone lives in reviews/<cn>.json).
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


def save_decision(set_dir: Path, collector_number: str, decision: dict) -> None:
    """Record one card's user review decision, merging into the sidecar."""
    decisions = load_decisions(set_dir)
    decisions[collector_number] = decision
    path = decisions_path(set_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(decisions, indent=2, ensure_ascii=False))


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
) -> dict | None:
    """Run a single user-directed revision of ``card`` (mirrors council revise-in-place).

    Builds a review prompt from the current card plus the user's free-text
    ``instructions``, runs ONE ``generate_with_tool`` call with the review tool
    schema, and returns the revised-card dict the LLM produced (or ``None`` if it
    declined to change anything / the call failed). The caller applies it via
    :func:`_apply_revision` and saves. This is the manual-review analogue of the
    council's in-place revision — one targeted call, no iteration loop.
    """
    base_prompt = _build_review_prompt(card, mechanics, pointed_questions)
    user_prompt = (
        f"{base_prompt}\n\n---\n\n"
        f"## Reviewer's Requested Change\n\n"
        f"A human reviewer asked for this specific change:\n\n{instructions.strip()}\n\n"
        f"Apply it. Set verdict to REVISE and return the COMPLETE revised card with "
        f"ALL fields, keeping everything else intact and templating clean. Only set "
        f"verdict OK (with no revised_card) if the request is already satisfied or "
        f"cannot be applied without breaking the card."
    )
    try:
        result = generate_with_tool(
            system_prompt=REVIEW_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            tool_schema=REVIEW_TOOL_SCHEMA,
            model=review_model,
            temperature=TEMPERATURE,
            max_tokens=HEAVY,
            effort=review_effort,
            log_dir=log_dir,
        )
    except Exception:
        logger.exception("Manual revise-in-place call failed")
        return None
    verdict_data = result.get("result", {})
    revised = verdict_data.get("revised_card")
    return revised if isinstance(revised, dict) else None


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
            lines.append(f"### Round {cr.round} — Reviewer {cr.member_id}")
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

    # Resolve once for the whole stage so a mid-run settings change can't
    # swap the model between cards. Matches the "no mid-stage swap"
    # guarantee in CLAUDE.md (`Model Settings`).
    review_model = _review_model()
    review_effort = _review_effort()

    logger.info("=" * 70)
    logger.info("MTGAI AI Design Review Pipeline -- Phase 4B")
    logger.info("=" * 70)
    logger.info(
        "Model: %s | Effort: %s | C/U iterations: %d | council rounds: %d",
        review_model,
        review_effort or "default",
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
            )
        else:
            result = _review_single(
                card,
                mechanics,
                pointed_questions,
                review_model,
                review_effort,
                on_council=card_council,
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
                    if p.stem.startswith(cn):
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

    # Hybrid escape hatch: in-place council
    # revision is the primary action (applied + saved above), but a card the
    # council still rated REVISE after MAX_ITERATIONS is *unfixable in place* —
    # surface it so the runner can flag it for a from-scratch regen via the loop.
    # The best in-place attempt stays saved; the regen archives + replaces it.
    unfixable: list[dict] = []
    for r in reviews:
        if r.final_verdict != "REVISE":
            continue
        problems = "; ".join(i.description for i in r.final_issues if i.description)
        reason = "Design review could not fix this card after revising: " + (
            problems or "still rated REVISE after the iteration budget."
        )
        unfixable.append({"slot_id": r.collector_number, "reason": reason})

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
