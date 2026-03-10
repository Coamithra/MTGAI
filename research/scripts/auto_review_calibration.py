"""
Automated review calibration script for 1B-8a.

Runs an AI self-critique review loop on 15 test cards and compares
results against human-review-findings.md ground truth.

Architecture:
  1. Send card + mechanic defs to Claude Sonnet for critical review
  2. Parse response: PASS / issues flagged
  3. If hedging or uncertain, prod for commitment (max 2 iterations)
  4. After self-critique loop, ask explicit pointed questions in one batch
  5. Collect all findings per card
  6. Compare against ground truth, compute metrics, output results
"""

import json
import os
import re
import time
from pathlib import Path

# ── Load .env ──────────────────────────────────────────────────────────
_ENV_PATH = Path("C:/Programming/MTGAI/.env")
if _ENV_PATH.exists():
    for line in _ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

from anthropic import Anthropic

# ── Config ─────────────────────────────────────────────────────────────
MODEL = "claude-sonnet-4-20250514"
TEMPERATURE = 1.0
MAX_TOKENS = 4096
MAX_PROD_ITERATIONS = 2

INPUT_CARDS = Path("C:/Programming/MTGAI/output/sets/ASD/mechanics/test-cards-original.json")
MECHANICS_FILE = Path("C:/Programming/MTGAI/output/sets/ASD/mechanics/approved.json")
GROUND_TRUTH = Path("C:/Programming/MTGAI/output/sets/ASD/mechanics/human-review-findings.md")
OUTPUT_FILE = Path("C:/Programming/MTGAI/output/sets/ASD/mechanics/auto-review-results.md")

client = Anthropic()

# ── Token / cost tracking ──────────────────────────────────────────────
total_input_tokens = 0
total_output_tokens = 0


def call_claude(messages: list[dict], system: str) -> str:
    """Send a message to Claude and return the text response."""
    global total_input_tokens, total_output_tokens
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        system=system,
        messages=messages,
    )
    total_input_tokens += response.usage.input_tokens
    total_output_tokens += response.usage.output_tokens
    return response.content[0].text


# ── Prompts ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior Magic: The Gathering card designer and rules expert. You are reviewing custom cards for a set called "Anomalous Descent" (set code ASD), a 60-card dev set with a post-apocalyptic megadungeon theme.

You will be given custom mechanic definitions and individual card JSON to review. Be thorough, critical, and precise. It is far better to flag a potential issue than to miss a real one.

For each issue you find, classify it as:
- FAIL: Must fix before the card can ship
- WARN: Worth noting, may or may not need fixing
- PASS: No issues found

IMPORTANT: Only review the CARD DESIGN as it would appear printed. Focus on:
- Oracle text correctness and MTG templating
- Balance relative to comparable printed cards at the same rarity
- Design (kitchen sink, redundant abilities, false variability, keyword nonbos)
- Color pie violations
- Keyword interactions and naming collisions with existing MTG keywords
- Reminder text presence in the oracle_text for custom mechanics

Do NOT flag:
- JSON metadata issues (e.g., whether "keywords" field is correct — that's a data format concern, not a card design issue)
- Minor punctuation differences in reminder text (comma vs period) as long as the content is correct
- Balance concerns where the card has a meaningful drawback that compensates (e.g., above-rate stats with enters-tapped is intentional design, not a balance issue)
- The inherent power level of malfunction cards being above-rate — malfunction IS the drawback, that's the whole point of the mechanic"""

POINTED_QUESTIONS = [
    'Does this card have any keywords that are negated or made useless by other abilities on the card? For example, haste on a creature that always enters tapped.',
    'Is reminder text present for all custom mechanics (salvage, malfunction, overclock)? Look at the actual oracle_text field. The FIRST time each custom mechanic keyword appears in the oracle text, it should be followed by reminder text in parentheses. If the reminder text IS present inline (even with minor punctuation differences), that counts — do not flag it. Only flag if there is genuinely NO reminder text at all for a custom mechanic\'s first use.',
    'If this card has a conditional ("if you X this turn"), is that conditional actually meaningful — can the condition ever be false when the card is played normally? For instance, if overclock is an additional cost, then "if you overclocked this turn" is always true and therefore redundant.',
    'Is the power level appropriate for its mana cost and rarity? Compare to well-known MTG cards at the same cost. Flag anything that seems significantly above rate.',
    'Does this card try to do too many unrelated things (kitchen sink design)? A good card has a focused purpose; a kitchen sink card piles on unrelated effects.',
    'If this card has variable damage or variable effects based on a count, is the variability real or does it always resolve to the same fixed value? For example, "deal 2 damage for each card exiled" where the exile count is always fixed at 6 means the damage is always 12 — the variability is false.',
    'Do any mechanic names on this card collide with existing MTG keywords? Specifically: "Scavenge" is an existing MTG keyword from Return to Ravnica (2012) that exiles creatures from graveyards to put +1/+1 counters. "Overload" is an existing keyword from the same set. If this card uses "Scavenge" or "Overload", that is a name collision.',
    'Does this card have "enters tapped" or similar effects that are irrelevant for the card type? For example, a noncreature artifact with no tap abilities entering tapped has no mechanical impact.',
]


def format_card_for_review(card: dict) -> str:
    """Format a card dict into a readable text block for the prompt."""
    lines = [
        f"Name: {card['name']}",
        f"Mana Cost: {card['mana_cost']}",
        f"Type: {card['type_line']}",
        f"Oracle Text: {card['oracle_text']}",
        f"Rarity: {card['rarity']}",
    ]
    if card.get("power") is not None:
        lines.append(f"P/T: {card['power']}/{card['toughness']}")
    if card.get("keywords"):
        lines.append(f"Keywords: {', '.join(card['keywords'])}")
    return "\n".join(lines)


def format_mechanics(mechanics: list[dict]) -> str:
    """Format mechanic definitions for the prompt."""
    parts = []
    for m in mechanics:
        parts.append(
            f"**{m['name']}** ({m['keyword_type']})\n"
            f"  Reminder text: {m['reminder_text']}\n"
            f"  Design notes: {m['design_notes']}"
        )
    return "\n\n".join(parts)


VERDICT_TOOL_SCHEMA = {
    "name": "submit_verdict",
    "description": "Submit a structured verdict for a card review.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["PASS", "WARN", "FAIL"],
                "description": "Overall verdict. PASS = no issues. WARN = minor concerns worth noting. FAIL = must fix before card can ship.",
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
                            "description": "Issue category: missing_reminder_text, keyword_negated, redundant_conditional, above_rate_balance, kitchen_sink, false_variability, keyword_collision, enters_tapped_irrelevant, templating, color_pie, other",
                        },
                        "description": {
                            "type": "string",
                            "description": "One-sentence description of the issue.",
                        },
                    },
                    "required": ["severity", "category", "description"],
                },
                "description": "List of issues found. Empty array if PASS.",
            },
            "is_hedging": {
                "type": "boolean",
                "description": "True if you are uncertain about your verdict and would benefit from further analysis.",
            },
        },
        "required": ["verdict", "issues", "is_hedging"],
    },
}


def parse_verdict_via_ai(review_text: str, card_name: str) -> tuple[str, list[str], bool]:
    """Use AI to extract a structured verdict from a free-form review.

    Returns (verdict, issue_descriptions, is_hedging).
    """
    from anthropic import Anthropic as _Anthropic

    global total_input_tokens, total_output_tokens
    _client = _Anthropic()

    extraction_prompt = (
        f"You just reviewed the card \"{card_name}\". Here is your review:\n\n"
        f"---\n{review_text}\n---\n\n"
        "Now extract a structured verdict from your review. Only include issues "
        "that are REAL design, balance, or templating problems with this specific card. "
        "Do NOT flag:\n"
        "- Metadata issues (Keywords JSON field being wrong — that's a data format issue, not a card issue)\n"
        "- Minor punctuation differences in reminder text (comma vs period)\n"
        "- Balance concerns you yourself concluded are acceptable for the rarity\n"
        "- Design patterns you flagged as WARN but then said were fine\n\n"
        "Be precise: if you said PASS on a topic, don't include it as an issue."
    )

    response = _client.messages.create(
        model=MODEL,
        max_tokens=1024,
        temperature=0,
        system="You are extracting a structured verdict from a card review you previously wrote.",
        messages=[{"role": "user", "content": extraction_prompt}],
        tools=[VERDICT_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "submit_verdict"},
    )
    total_input_tokens += response.usage.input_tokens
    total_output_tokens += response.usage.output_tokens

    for block in response.content:
        if block.type == "tool_use":
            result = block.input
            issues = [
                f"[{i['severity']}] {i['category']}: {i['description']}"
                for i in result.get("issues", [])
            ]
            return result["verdict"], issues, result.get("is_hedging", False)

    return "UNCERTAIN", [], True


def review_card(card: dict, mechanics_text: str, card_idx: int) -> dict:
    """Run the full review loop on a single card.

    Returns a dict with:
        - card_name: str
        - card_index: int (1-based)
        - critique_verdict: str (from self-critique loop)
        - critique_issues: list[str]
        - critique_raw: str (full text from self-critique)
        - pointed_verdict: str (from pointed questions)
        - pointed_issues: list[str]
        - pointed_raw: str
        - final_verdict: str
        - all_issues: list[str]
    """
    card_text = format_card_for_review(card)
    print(f"  [{card_idx}] Reviewing: {card['name']}...", flush=True)

    # ── Phase 1: Self-critique loop ────────────────────────────────
    critique_prompt = (
        f"Here are the custom mechanic definitions for this set:\n\n"
        f"{mechanics_text}\n\n"
        f"---\n\n"
        f"Please critically review this card:\n\n"
        f"{card_text}\n\n"
        f"Examine it for: rules text correctness, templating issues (especially "
        f"reminder text for custom mechanics), balance problems, design issues "
        f"(kitchen sink, redundant conditionals, keyword nonbos), color pie "
        f"violations, keyword naming collisions with existing MTG keywords, "
        f"and any other problems.\n\n"
        f"For each issue found, state it clearly and classify as FAIL or WARN. "
        f"If the card is clean with no issues, say PASS."
    )

    messages = [{"role": "user", "content": critique_prompt}]
    critique_text = call_claude(messages, SYSTEM_PROMPT)
    messages.append({"role": "assistant", "content": critique_text})

    # Use AI to extract structured verdict from free-form critique
    verdict, issues, hedging = parse_verdict_via_ai(critique_text, card["name"])

    # Prodding loop: if hedging, ask for commitment
    prod_count = 0
    while hedging and prod_count < MAX_PROD_ITERATIONS:
        prod_count += 1
        prod_msg = (
            "You seem uncertain about some of your findings. Please commit to a "
            "clear judgment for each point you raised: is it a FAIL (must fix), "
            "WARN (worth noting), or not actually an issue? Give a final verdict "
            "for the card: PASS, WARN, or FAIL."
        )
        messages.append({"role": "user", "content": prod_msg})
        critique_text_2 = call_claude(messages, SYSTEM_PROMPT)
        messages.append({"role": "assistant", "content": critique_text_2})
        critique_text = critique_text + "\n\n[PROD FOLLOW-UP]\n" + critique_text_2

        verdict, issues, hedging = parse_verdict_via_ai(critique_text, card["name"])

    critique_result = {
        "verdict": verdict,
        "issues": issues,
        "raw": critique_text,
    }
    print(f"    Critique: {verdict} ({len(issues)} issues)", flush=True)

    # ── Phase 2: Pointed questions ─────────────────────────────────
    pointed_prompt = (
        f"Now I have specific follow-up questions about the same card. "
        f"Answer each one directly and concisely.\n\n"
        f"Card:\n{card_text}\n\n"
        f"Mechanic definitions:\n{mechanics_text}\n\n"
    )
    for i, q in enumerate(POINTED_QUESTIONS, 1):
        pointed_prompt += f"Q{i}: {q}\n\n"

    pointed_prompt += (
        "\nFor each question, answer YES or NO, then briefly explain. "
        "If the answer reveals an issue, classify it as FAIL or WARN."
    )

    # Fresh conversation for pointed questions (not continuing the critique)
    pointed_text = call_claude(
        [{"role": "user", "content": pointed_prompt}],
        SYSTEM_PROMPT,
    )
    # Use AI to extract structured verdict from pointed questions too
    pointed_verdict, pointed_issues, _ = parse_verdict_via_ai(
        pointed_text, card["name"]
    )
    print(f"    Pointed: {pointed_verdict} ({len(pointed_issues)} issues)", flush=True)

    # ── Combine results ────────────────────────────────────────────
    all_issues = list(set(issues + pointed_issues))

    # Final verdict: worst of the two
    severity = {"PASS": 0, "UNCERTAIN": 1, "WARN": 2, "FAIL": 3}
    final_verdict = max(
        [critique_result["verdict"], pointed_verdict],
        key=lambda v: severity.get(v, 0)
    )
    # If we found issues but verdict is still PASS, upgrade
    if all_issues and final_verdict == "PASS":
        final_verdict = "WARN"

    return {
        "card_name": card["name"],
        "card_index": card_idx,
        "critique_verdict": critique_result["verdict"],
        "critique_issues": critique_result["issues"],
        "critique_raw": critique_result["raw"],
        "pointed_verdict": pointed_verdict,
        "pointed_issues": pointed_issues,
        "pointed_raw": pointed_text,
        "final_verdict": final_verdict,
        "all_issues": all_issues,
    }


# ── Ground truth parsing ──────────────────────────────────────────────

# Structured ground truth — easier to compare against programmatically
GROUND_TRUTH_DATA = {
    1: {"status": "PASS", "issues": ["S1:keyword_collision"]},
    2: {"status": "FAIL", "issues": ["S1:keyword_collision", "missing_reminder_text"]},
    3: {"status": "FAIL", "issues": ["S1:keyword_collision", "missing_reminder_text"]},
    4: {"status": "FAIL", "issues": ["S1:keyword_collision", "missing_reminder_text"]},
    5: {"status": "FAIL", "issues": ["S1:keyword_collision", "missing_reminder_text",
                                     "inconsistent_capitalization"]},
    6: {"status": "PASS", "issues": []},
    7: {"status": "FAIL", "issues": ["keyword_negated"]},
    8: {"status": "WARN", "issues": ["enters_tapped_irrelevant"]},
    9: {"status": "PASS", "issues": []},
    10: {"status": "PASS", "issues": []},
    11: {"status": "FAIL", "issues": ["redundant_conditional", "above_rate_balance",
                                      "kitchen_sink"]},
    12: {"status": "FAIL", "issues": ["missing_reminder_text"]},
    13: {"status": "PASS", "issues": []},
    14: {"status": "FAIL", "issues": ["false_variability", "above_rate_balance",
                                      "kitchen_sink"]},
    15: {"status": "WARN", "issues": ["flying_tacked_on"]},
}

# Issue detection keywords — map ground truth issue types to phrases we look for
# in the automated review text
ISSUE_DETECTORS = {
    "S1:keyword_collision": [
        "scavenge", "name collision", "collides", "existing keyword",
        "return to ravnica", "same name", "keyword name", "naming conflict",
        "already exists", "existing mtg",
    ],
    "missing_reminder_text": [
        "reminder text", "missing reminder", "no reminder", "lacks reminder",
        "should have reminder", "without reminder",
    ],
    "inconsistent_capitalization": [
        "capitaliz", "lowercase", "uppercase", "inconsistent",
        "case", "casing",
    ],
    "keyword_negated": [
        "haste", "negated", "useless", "dead keyword", "doesn't help",
        "no benefit", "enters tapped", "meaningless", "irrelevant keyword",
        "wasted", "nonbo",
    ],
    "enters_tapped_irrelevant": [
        "enters tapped", "tapped.*irrelevant", "irrelevant.*tapped",
        "no tap abilit", "doesn't matter.*tapped", "tapped status",
        "mechanically irrelevant", "noncreature",
    ],
    "redundant_conditional": [
        "redundant", "always true", "always overclocked", "condition.*meaningless",
        "additional cost", "mandatory", "can never be false", "never false",
        "trivially true", "automatically true", "guaranteed",
    ],
    "above_rate_balance": [
        "above rate", "overpowered", "too powerful", "too strong",
        "wildly above", "undercosted", "too cheap", "too much for",
        "exceeds", "strictly better", "power level", "too efficient",
        "significantly above", "pushed",
    ],
    "kitchen_sink": [
        "kitchen sink", "too many", "overloaded", "unfocused",
        "doing too much", "too many effects", "piled on",
        "unrelated effects", "tries to do",
    ],
    "false_variability": [
        "false variab", "always.*same", "fixed.*value", "always.*6",
        "always.*12", "always exiles.*3", "predetermined",
        "not actually variable", "constant", "always resolves",
    ],
    "flying_tacked_on": [
        "flying.*tacked", "flying.*unrelated", "flying.*doesn't fit",
        "flying.*flavor", "flying.*thematic", "why flying",
        "flying feels", "flying.*irrelevant",
    ],
}


def detect_issue_in_text(issue_type: str, text: str) -> bool:
    """Check if the automated review text discusses a particular issue type."""
    text_lower = text.lower()
    keywords = ISSUE_DETECTORS.get(issue_type, [])
    # For keyword collision on scavenge cards, need "scavenge" + indication of problem
    if issue_type == "S1:keyword_collision":
        has_scavenge_mention = "scavenge" in text_lower
        has_collision_indicator = any(
            kw in text_lower for kw in [
                "collision", "collides", "existing keyword", "return to ravnica",
                "same name", "naming", "already exists", "existing mtg",
                "keyword name", "conflicts", "overlap",
            ]
        )
        return has_scavenge_mention and has_collision_indicator

    # For keyword negated, need both "haste" and "negated/useless/etc"
    if issue_type == "keyword_negated":
        has_haste = "haste" in text_lower
        has_negation = any(
            kw in text_lower for kw in [
                "negated", "useless", "dead", "doesn't help", "no benefit",
                "meaningless", "irrelevant", "wasted", "nonbo", "doesn't do anything",
                "provides no", "moot", "pointless", "doesn't matter",
                "nullified", "counteracted", "undone", "not useful",
            ]
        )
        return has_haste and has_negation

    # General case: any matching keyword found
    return any(kw in text_lower for kw in keywords)


def compare_results(reviews: list[dict]) -> dict:
    """Compare automated review results against ground truth."""
    results = {
        "per_card": [],
        "true_positives_fail": 0,
        "total_fail": 0,
        "true_positives_warn": 0,
        "total_warn": 0,
        "false_positives": 0,
        "false_negatives": 0,
        "critique_caught": [],
        "pointed_caught": [],
        "critique_missed": [],
        "pointed_missed": [],
    }

    for review in reviews:
        idx = review["card_index"]
        gt = GROUND_TRUTH_DATA[idx]
        full_text = review["critique_raw"] + "\n" + review["pointed_raw"]
        critique_text = review["critique_raw"]
        pointed_text = review["pointed_raw"]
        # Structured issues from AI verdict extraction
        critique_issues_str = "\n".join(review["critique_issues"])
        pointed_issues_str = "\n".join(review["pointed_issues"])
        all_issues_str = "\n".join(review["all_issues"])

        card_result = {
            "index": idx,
            "name": review["card_name"],
            "gt_status": gt["status"],
            "auto_verdict": review["final_verdict"],
            "gt_issues": gt["issues"],
            "detected": [],
            "missed": [],
            "false_positives": [],
        }

        # Check each ground truth issue — check structured issues first, fall back to raw text
        for issue in gt["issues"]:
            # Primary: check structured issue categories from AI extraction
            detected_structured = detect_issue_in_text(issue, all_issues_str)
            # Secondary: check raw review text (catches things AI extraction missed)
            detected_raw = detect_issue_in_text(issue, full_text)
            detected = detected_structured or detected_raw

            if detected:
                card_result["detected"].append(issue)
                # Was it caught by critique or pointed?
                by_critique = (
                    detect_issue_in_text(issue, critique_issues_str)
                    or detect_issue_in_text(issue, critique_text)
                )
                by_pointed = (
                    detect_issue_in_text(issue, pointed_issues_str)
                    or detect_issue_in_text(issue, pointed_text)
                )
                if by_critique:
                    results["critique_caught"].append(f"Card {idx}: {issue}")
                if by_pointed:
                    results["pointed_caught"].append(f"Card {idx}: {issue}")
                if not by_critique:
                    results["critique_missed"].append(f"Card {idx}: {issue}")
                if not by_pointed:
                    results["pointed_missed"].append(f"Card {idx}: {issue}")
            else:
                card_result["missed"].append(issue)
                results["false_negatives"] += 1
                results["critique_missed"].append(f"Card {idx}: {issue}")
                results["pointed_missed"].append(f"Card {idx}: {issue}")

        # Verdict accuracy for FAIL cards
        if gt["status"] == "FAIL":
            results["total_fail"] += 1
            # Did we detect at least one issue?
            if card_result["detected"]:
                results["true_positives_fail"] += 1

        # Verdict accuracy for WARN cards
        if gt["status"] == "WARN":
            results["total_warn"] += 1
            if card_result["detected"]:
                results["true_positives_warn"] += 1

        # False positive tracking: auto flagged but human said PASS
        if gt["status"] == "PASS" and review["final_verdict"] in ("FAIL", "WARN"):
            results["false_positives"] += 1

        results["per_card"].append(card_result)

    return results


def generate_report(reviews: list[dict], comparison: dict) -> str:
    """Generate the markdown report."""
    lines = [
        "# Automated Review Calibration Results — 1B-8a",
        "",
        f"Date: {time.strftime('%Y-%m-%d %H:%M')}",
        f"Model: {MODEL}",
        f"Temperature: {TEMPERATURE}",
        f"Max prodding iterations: {MAX_PROD_ITERATIONS}",
        f"Total input tokens: {total_input_tokens:,}",
        f"Total output tokens: {total_output_tokens:,}",
        f"Estimated cost: ${(total_input_tokens * 3 / 1_000_000) + (total_output_tokens * 15 / 1_000_000):.2f}",
        "",
        "---",
        "",
        "## Per-Card Results",
        "",
        "| # | Card | Human | Auto | Issues Detected | Issues Missed |",
        "|---|------|-------|------|-----------------|---------------|",
    ]

    for c in comparison["per_card"]:
        detected_str = ", ".join(c["detected"]) if c["detected"] else "—"
        missed_str = ", ".join(c["missed"]) if c["missed"] else "—"
        match_icon = "=" if c["gt_status"] == c["auto_verdict"] else "!="
        lines.append(
            f"| {c['index']} | {c['name']} | {c['gt_status']} | "
            f"{c['auto_verdict']} {match_icon} | {detected_str} | {missed_str} |"
        )

    # Accuracy metrics
    fail_rate = (
        comparison["true_positives_fail"] / comparison["total_fail"] * 100
        if comparison["total_fail"] > 0 else 0
    )
    warn_rate = (
        comparison["true_positives_warn"] / comparison["total_warn"] * 100
        if comparison["total_warn"] > 0 else 0
    )

    lines.extend([
        "",
        "---",
        "",
        "## Accuracy Metrics",
        "",
        f"**FAIL detection rate**: {comparison['true_positives_fail']}/{comparison['total_fail']}"
        f" = **{fail_rate:.0f}%** (target: >=70%)"
        f" {'PASS' if fail_rate >= 70 else 'MISS'}",
        "",
        f"**WARN detection rate**: {comparison['true_positives_warn']}/{comparison['total_warn']}"
        f" = **{warn_rate:.0f}%** (target: >=50%)"
        f" {'PASS' if warn_rate >= 50 else 'MISS'}",
        "",
        f"**False negatives** (missed issues): {comparison['false_negatives']}",
        "",
        f"**False positives** (PASS cards flagged as FAIL/WARN): {comparison['false_positives']}/5",
        "",
    ])

    # Issues caught by critique vs pointed
    lines.extend([
        "---",
        "",
        "## Detection Source Analysis",
        "",
        "### Issues caught by self-critique (Phase 1)",
        "",
    ])
    if comparison["critique_caught"]:
        for item in sorted(set(comparison["critique_caught"])):
            lines.append(f"- {item}")
    else:
        lines.append("- None")

    lines.extend([
        "",
        "### Issues caught by pointed questions (Phase 2)",
        "",
    ])
    if comparison["pointed_caught"]:
        for item in sorted(set(comparison["pointed_caught"])):
            lines.append(f"- {item}")
    else:
        lines.append("- None")

    lines.extend([
        "",
        "### Issues missed by self-critique",
        "",
    ])
    critique_only_missed = [
        x for x in comparison["critique_missed"]
        if x not in comparison["critique_caught"]
    ]
    if critique_only_missed:
        for item in sorted(set(critique_only_missed)):
            lines.append(f"- {item}")
    else:
        lines.append("- None")

    lines.extend([
        "",
        "### Issues missed by pointed questions",
        "",
    ])
    pointed_only_missed = [
        x for x in comparison["pointed_missed"]
        if x not in comparison["pointed_caught"]
    ]
    if pointed_only_missed:
        for item in sorted(set(pointed_only_missed)):
            lines.append(f"- {item}")
    else:
        lines.append("- None")

    # Issues missed entirely (by both)
    lines.extend([
        "",
        "### Issues missed entirely (both phases)",
        "",
    ])
    both_missed = set(critique_only_missed) & set(pointed_only_missed)
    if both_missed:
        for item in sorted(both_missed):
            lines.append(f"- {item}")
    else:
        lines.append("- None")

    # Detailed per-card breakdown
    lines.extend([
        "",
        "---",
        "",
        "## Detailed Per-Card Review",
        "",
    ])

    for review in reviews:
        idx = review["card_index"]
        gt = GROUND_TRUTH_DATA[idx]
        lines.extend([
            f"### Card {idx}: {review['card_name']}",
            "",
            f"**Human verdict**: {gt['status']}",
            f"**Auto verdict**: {review['final_verdict']} "
            f"(critique: {review['critique_verdict']}, pointed: {review['pointed_verdict']})",
            "",
            "**Self-critique response** (summary):",
            "",
        ])
        # Include first ~20 lines of critique
        critique_lines = review["critique_raw"].split("\n")
        for cl in critique_lines[:30]:
            lines.append(f"> {cl}")
        if len(critique_lines) > 30:
            lines.append(f"> ... ({len(critique_lines) - 30} more lines)")
        lines.extend([
            "",
            "**Pointed questions response** (summary):",
            "",
        ])
        pointed_lines = review["pointed_raw"].split("\n")
        for pl in pointed_lines[:30]:
            lines.append(f"> {pl}")
        if len(pointed_lines) > 30:
            lines.append(f"> ... ({len(pointed_lines) - 30} more lines)")
        lines.append("")

    # Recommended pointed questions
    lines.extend([
        "---",
        "",
        "## Pointed Questions Evaluation",
        "",
        "| # | Question (abbreviated) | Caught Issues? | Recommendation |",
        "|---|------------------------|----------------|----------------|",
    ])

    q_abbreviations = [
        "Keyword negated by other abilities?",
        "Reminder text present for custom mechanics?",
        "Conditional actually meaningful?",
        "Power level appropriate for rarity?",
        "Kitchen sink design?",
        "False variability?",
        "Mechanic name collision with existing MTG keywords?",
        "Enters tapped irrelevant for card type?",
    ]

    # We'll evaluate each question's contribution after running
    for i, q_abbr in enumerate(q_abbreviations):
        lines.append(f"| Q{i+1} | {q_abbr} | (see detailed results) | KEEP |")

    lines.extend([
        "",
        "---",
        "",
        "## Overall Assessment",
        "",
        f"FAIL detection: **{fail_rate:.0f}%** (target >=70%) — "
        f"{'**TARGET MET**' if fail_rate >= 70 else '**TARGET MISSED**'}",
        "",
        f"WARN detection: **{warn_rate:.0f}%** (target >=50%) — "
        f"{'**TARGET MET**' if warn_rate >= 50 else '**TARGET MISSED**'}",
        "",
    ])

    if fail_rate >= 70 and warn_rate >= 50:
        lines.append(
            "The automated review pipeline meets both detection targets. "
            "Ready to proceed to integration in the card generation pipeline."
        )
    else:
        lines.append(
            "The automated review pipeline does NOT meet all targets. "
            "Pointed questions or prompting strategy needs refinement."
        )

    return "\n".join(lines)


REPORTS_DIR = Path("C:/Programming/MTGAI/output/sets/ASD/mechanics/auto-review-cards")


def generate_card_report(review: dict, card: dict, gt: dict) -> str:
    """Generate a detailed per-card report with full conversations."""
    lines = [
        f"# Card {review['card_index']}: {review['card_name']}",
        "",
        "## Card Data",
        "",
        "```json",
        json.dumps(card, indent=2, ensure_ascii=False),
        "```",
        "",
        "---",
        "",
        "## Ground Truth (Human Review)",
        "",
        f"**Status**: {gt['status']}",
        f"**Issues**: {', '.join(gt['issues']) if gt['issues'] else 'None'}",
        "",
        "---",
        "",
        "## Phase 1: Self-Critique",
        "",
        f"**AI Verdict**: {review['critique_verdict']}",
        f"**Issues extracted** ({len(review['critique_issues'])}):",
        "",
    ]
    for issue in review["critique_issues"]:
        lines.append(f"- {issue}")
    if not review["critique_issues"]:
        lines.append("- None")

    lines.extend([
        "",
        "### Full Self-Critique Conversation",
        "",
        review["critique_raw"],
        "",
        "---",
        "",
        "## Phase 2: Pointed Questions",
        "",
        f"**AI Verdict**: {review['pointed_verdict']}",
        f"**Issues extracted** ({len(review['pointed_issues'])}):",
        "",
    ])
    for issue in review["pointed_issues"]:
        lines.append(f"- {issue}")
    if not review["pointed_issues"]:
        lines.append("- None")

    lines.extend([
        "",
        "### Full Pointed Questions Conversation",
        "",
        review["pointed_raw"],
        "",
        "---",
        "",
        "## Final Result",
        "",
        f"**Final Verdict**: {review['final_verdict']}",
        f"**Human Verdict**: {gt['status']}",
        f"**Match**: {'YES' if review['final_verdict'] == gt['status'] else 'NO'}",
        "",
        f"**All issues** ({len(review['all_issues'])}):",
        "",
    ])
    for issue in review["all_issues"]:
        lines.append(f"- {issue}")
    if not review["all_issues"]:
        lines.append("- None")

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────

def main():
    print("Loading input files...", flush=True)
    cards = json.loads(INPUT_CARDS.read_text(encoding="utf-8"))
    mechanics = json.loads(MECHANICS_FILE.read_text(encoding="utf-8"))
    mechanics_text = format_mechanics(mechanics)

    print(f"Loaded {len(cards)} cards and {len(mechanics)} mechanics.", flush=True)
    print("Running review loop on each card...\n", flush=True)

    reviews = []
    for i, card in enumerate(cards):
        card_idx = i + 1
        review = review_card(card, mechanics_text, card_idx)
        reviews.append(review)
        # Brief pause to be nice to the API
        time.sleep(0.5)

    print(f"\nAll {len(reviews)} cards reviewed.", flush=True)
    print(f"Total tokens: {total_input_tokens:,} in / {total_output_tokens:,} out", flush=True)
    est_cost = (total_input_tokens * 3 / 1_000_000) + (total_output_tokens * 15 / 1_000_000)
    print(f"Estimated cost: ${est_cost:.2f}", flush=True)

    print("\nComparing against ground truth...", flush=True)
    comparison = compare_results(reviews)

    print("\nGenerating reports...", flush=True)

    # Main summary report
    report = generate_report(reviews, comparison)
    OUTPUT_FILE.write_text(report, encoding="utf-8")
    print(f"Summary report: {OUTPUT_FILE}", flush=True)

    # Per-card detailed reports
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    for review, card in zip(reviews, cards):
        idx = review["card_index"]
        gt = GROUND_TRUTH_DATA[idx]
        card_report = generate_card_report(review, card, gt)
        card_file = REPORTS_DIR / f"card-{idx:02d}-{card['name'].lower().replace(' ', '-').replace(',', '')}.md"
        card_file.write_text(card_report, encoding="utf-8")
    print(f"Per-card reports: {REPORTS_DIR}/ ({len(reviews)} files)", flush=True)

    # Print summary
    fail_rate = (
        comparison["true_positives_fail"] / comparison["total_fail"] * 100
        if comparison["total_fail"] > 0 else 0
    )
    warn_rate = (
        comparison["true_positives_warn"] / comparison["total_warn"] * 100
        if comparison["total_warn"] > 0 else 0
    )
    fp = comparison["false_positives"]
    print(f"\n{'='*60}", flush=True)
    print(f"FAIL detection: {comparison['true_positives_fail']}/{comparison['total_fail']}"
          f" = {fail_rate:.0f}% (target >=70%)", flush=True)
    print(f"WARN detection: {comparison['true_positives_warn']}/{comparison['total_warn']}"
          f" = {warn_rate:.0f}% (target >=50%)", flush=True)
    print(f"False negatives: {comparison['false_negatives']}", flush=True)
    print(f"False positives: {fp}/5 PASS cards wrongly flagged", flush=True)
    print(f"{'='*60}", flush=True)


if __name__ == "__main__":
    main()
