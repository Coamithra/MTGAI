"""mtg-mech-lab — a standalone prototype for honing the mechanic generation +
council-review prompts before porting them into the real MTGAI pipeline.

It reuses MTGAI's ``generate_with_tool`` transport (Anthropic + local models,
the model registry, and ``.env`` key loading) so any prompt we tune here
transfers 1:1 to the real pipeline. The *prose* prompts live in
``prompts/*.txt`` so we can hack them and re-run instantly; the JSON tool
schemas and the orchestration loop live in this file.

Run with the MTGAI venv python (it already has llmfacade installed):

    & C:/Programming/MTGAI/backend/.venv/Scripts/python.exe mech_lab.py --count 4

Iterate on the REVIEW prompts against a FIXED set of drafts (so output changes
reflect prompt edits, not generation randomness): generate once, then replay.

    ... mech_lab.py --count 4                        # writes runs/<ts>.drafts.json
    ... mech_lab.py --drafts runs/<ts>.drafts.json   # review-only, same drafts

Each run writes a readable Markdown report + a full JSON dump under runs/.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ── bootstrap: make MTGAI's llm_client importable ──────────────────────────
# This folder lives inside the MTGAI repo as a sibling of backend/. Prefer the
# repo-relative path (survives the repo being moved/cloned elsewhere); fall back
# to the absolute path if run from some detached copy.
_HERE = Path(__file__).resolve().parent
MTGAI_BACKEND = _HERE.parent / "backend"
if not (MTGAI_BACKEND / "mtgai").exists():
    MTGAI_BACKEND = Path(r"C:\Programming\MTGAI\backend")
if str(MTGAI_BACKEND) not in sys.path:
    sys.path.insert(0, str(MTGAI_BACKEND))

try:  # Windows cp1252 guard — the global rule: keep stdout UTF-8.
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mtgai.generation.llm_client import cost_from_result, generate_with_tool  # noqa: E402

HERE = Path(__file__).resolve().parent
PROMPTS = HERE / "prompts"
RUNS = HERE / "runs"

# Short stand-in for the real mtg_known_keywords.json collision list. The
# generator is told to avoid these; the reviewer judges "is this a reskin?"
# from its own knowledge, so this list only needs to steer generation.
EXCLUDED_KEYWORDS = [
    "Flying", "Trample", "Vigilance", "Haste", "Deathtouch", "Lifelink",
    "First strike", "Double strike", "Menace", "Reach", "Defender", "Flash",
    "Hexproof", "Indestructible", "Ward", "Convoke", "Cascade", "Flashback",
    "Kicker", "Cycling", "Scry", "Surveil", "Explore", "Adapt", "Proliferate",
    "Landfall", "Prowess", "Delirium", "Threshold", "Morph", "Ninjutsu",
    "Embalm", "Eternalize", "Exploit", "Afflict", "Mentor", "Riot", "Adventure",
]

# ── JSON tool schemas (the structural contract; mirror the real pipeline) ──

COLOR_ENUM = ["W", "U", "B", "R", "G"]
KEYWORD_TYPES = ["keyword_ability", "ability_word", "keyword_action"]
RARITIES = ["common", "uncommon", "rare", "mythic"]
ISSUE_CATEGORIES = [
    "playable", "wording", "interesting", "self_consistent", "unique", "elegant", "other",
]

EXAMPLE_CARD_SCHEMA: dict = {
    "type": "object",
    "required": ["name", "mana_cost", "type_line", "rarity", "oracle_text"],
    "properties": {
        "name": {"type": "string"},
        "mana_cost": {"type": "string", "description": "e.g. {2}{U} or {G} or '' for lands"},
        "type_line": {"type": "string"},
        "rarity": {"type": "string", "enum": RARITIES},
        "oracle_text": {
            "type": "string",
            "description": "No parenthetical reminder text (injected downstream).",
        },
        "power": {"type": "string", "description": "Creatures only."},
        "toughness": {"type": "string", "description": "Creatures only."},
    },
}

MECHANIC_ITEM_SCHEMA: dict = {
    "type": "object",
    "required": [
        "name", "keyword_type", "reminder_text", "colors", "complexity",
        "design_rationale", "distribution", "example_cards",
    ],
    "properties": {
        "name": {"type": "string", "description": "One or two words; no printed-keyword collision."},
        "keyword_type": {"type": "string", "enum": KEYWORD_TYPES},
        "reminder_text": {"type": "string", "description": "Under 100 characters."},
        "colors": {
            "type": "array",
            "items": {"type": "string", "enum": COLOR_ENUM},
            "description": "1-3 colors.",
        },
        "complexity": {"type": "integer", "enum": [1, 2, 3]},
        "design_rationale": {"type": "string"},
        "distribution": {
            "type": "object",
            "properties": {r: {"type": "integer"} for r in RARITIES},
        },
        "example_cards": {
            "type": "array",
            "items": EXAMPLE_CARD_SCHEMA,
            "minItems": 2,
            "maxItems": 2,
            "description": "Exactly two cards that use the mechanic, at contrasting rarities.",
        },
    },
}

GEN_TOOL: dict = {
    "name": "submit_mechanic",
    "description": "Submit one freshly designed set mechanic with two example cards.",
    "input_schema": MECHANIC_ITEM_SCHEMA,
}

ISSUE_SCHEMA: dict = {
    "type": "object",
    "required": ["category", "severity", "description"],
    "properties": {
        "category": {"type": "string", "enum": ISSUE_CATEGORIES},
        "severity": {"type": "string", "enum": ["minor", "major"]},
        "description": {"type": "string", "description": "One sentence: the problem, concretely."},
    },
}

REVIEW_TOOL: dict = {
    "name": "submit_review",
    "description": "Submit your independent critique of one mechanic.",
    "input_schema": {
        "type": "object",
        "required": ["verdict", "issues"],
        "properties": {
            "verdict": {"type": "string", "enum": ["OK", "REVISE"]},
            "issues": {"type": "array", "items": ISSUE_SCHEMA},
        },
    },
}

SYNTH_ISSUE_SCHEMA: dict = {
    "type": "object",
    "required": ["category", "agreement", "description"],
    "properties": {
        "category": {"type": "string", "enum": ISSUE_CATEGORIES},
        "agreement": {
            "type": "integer",
            "description": "How many of the council's reviewers raised this issue.",
        },
        "description": {"type": "string"},
    },
}

SYNTH_TOOL: dict = {
    "name": "submit_synthesis",
    "description": (
        "Synthesize the council's reviews into one consensus decision and an "
        "improved mechanic."
    ),
    "input_schema": {
        "type": "object",
        "required": ["synthesis", "consensus_issues", "revised_mechanic", "verdict", "review_notes"],
        "properties": {
            "synthesis": {"type": "string", "description": "Brief: what the council agreed on."},
            "consensus_issues": {"type": "array", "items": SYNTH_ISSUE_SCHEMA},
            "revised_mechanic": MECHANIC_ITEM_SCHEMA,
            "verdict": {
                "type": "string",
                "enum": ["OK", "REVISE"],
                "description": "Is the REVISED mechanic now excellent (OK) or still wanting (REVISE)?",
            },
            "review_notes": {
                "type": "string",
                "description": "One or two sentences: what you changed and why. Empty if unchanged.",
            },
        },
    },
}


# ── prompt loading + safe substitution ─────────────────────────────────────


def load_prompt(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def render(template: str, mapping: dict[str, Any]) -> str:
    """Literal ``{key}`` substitution (NOT str.format) so values containing
    braces — mana symbols like ``{T}``/``{2}{U}`` — never blow up."""
    out = template
    for key, val in mapping.items():
        out = out.replace("{" + key + "}", str(val))
    return out


# ── theme + mechanic rendering ─────────────────────────────────────────────


def format_setting_block(theme: dict) -> str:
    one = (theme.get("theme") or "").strip()
    prose = (theme.get("setting") or theme.get("flavor_description") or "").strip()
    parts = [p for p in (one, prose) if p]
    return "\n\n".join(parts) if parts else "(no setting provided)"


def format_constraints_block(theme: dict) -> str:
    cons = theme.get("constraints") or theme.get("special_constraints") or []
    lines = []
    for c in cons:
        text = c.get("text") if isinstance(c, dict) else c
        if text:
            lines.append(f"- {text}")
    return "\n".join(lines) if lines else "(no special constraints)"


def format_already_designed(accepted: list[dict]) -> str:
    if not accepted:
        return "No mechanics designed yet — this is the first."
    lines = []
    for i, m in enumerate(accepted, 1):
        colors = "".join(m.get("colors") or []) or "colorless"
        lines.append(
            f"{i}. {m.get('name', '?')} — {colors}, complexity {m.get('complexity', '?')}, "
            f"{m.get('keyword_type', '?')}"
        )
        rem = (m.get("reminder_text") or "").strip()
        if rem:
            lines.append(f"   text: {rem}")
    return "\n".join(lines)


def format_mechanic_block(m: dict) -> str:
    """Verbose, player's-eye rendering — including full example-card text."""
    m = m or {}
    colors = "".join(m.get("colors") or []) or "(colorless)"
    dist = m.get("distribution") or {}
    dist_line = ", ".join(f"{r} {dist.get(r, 0)}" for r in RARITIES)
    lines = [
        f"Name: {m.get('name', '?')}",
        f"Keyword type: {m.get('keyword_type', '?')}",
        f"Colors: {colors}",
        f"Complexity: {m.get('complexity', '?')}",
        f"Reminder text: {(m.get('reminder_text') or '').strip() or '(none)'}",
        f"Rarity distribution: {dist_line}",
        f"Design rationale: {(m.get('design_rationale') or '').strip() or '(none)'}",
        "",
        "Example cards:",
    ]
    examples = m.get("example_cards") or []
    if not examples:
        lines.append("  (none provided)")
    for i, e in enumerate(examples, 1):
        e = e or {}
        cost = e.get("mana_cost") or ""
        pt = ""
        if e.get("power") not in (None, "") and e.get("toughness") not in (None, ""):
            pt = f" {e.get('power')}/{e.get('toughness')}"
        head = f"  {i}. {e.get('name', '(unnamed)')}"
        if cost:
            head += f" {cost}"
        head += f"  —  {e.get('type_line', '?')}{pt}  ({e.get('rarity', '?')})"
        lines.append(head)
        for ln in (e.get("oracle_text") or "(empty)").splitlines() or ["(empty)"]:
            lines.append(f"     {ln}")
    return "\n".join(lines)


def format_reviews_block(reviews: list[dict]) -> str:
    lines = []
    for i, r in enumerate(reviews, 1):
        lines.append(f"### Reviewer {i} — verdict: {r['verdict']}")
        issues = r.get("issues") or []
        if not issues:
            lines.append("  (no issues raised)")
        for iss in issues:
            lines.append(
                f"  - [{iss.get('category', '?')}/{iss.get('severity', '?')}] "
                f"{iss.get('description', '')}"
            )
    return "\n".join(lines)


# ── LLM calls (each wrapped by caller in try/except; safe fallback) ────────


def call_generate(theme: dict, accepted: list[dict], position: int, target: int,
                  set_size: int, mechanic_count: int, model: str, temp: float,
                  log_dir: Path, repeat_penalty: float | None) -> dict:
    sys_p = render(load_prompt("gen_system.txt"), {
        "set_name": theme.get("name") or "(unnamed set)",
        "set_size": set_size,
        "mechanic_count": mechanic_count,
        "setting_block": format_setting_block(theme),
        "constraints_block": format_constraints_block(theme),
        "excluded_keywords": ", ".join(EXCLUDED_KEYWORDS),
    })
    user_p = render(load_prompt("gen_user.txt"), {
        "position": position,
        "target": target,
        "already_block": format_already_designed(accepted),
    })
    return generate_with_tool(
        system_prompt=sys_p, user_prompt=user_p, tool_schema=GEN_TOOL,
        model=model, temperature=temp, max_tokens=2048, log_dir=log_dir,
        repeat_penalty=repeat_penalty,
    )


def call_reviewer(mech: dict, model: str, temp: float, log_dir: Path,
                  repeat_penalty: float | None) -> dict:
    sys_p = load_prompt("review_system.txt")
    user_p = render(load_prompt("review_user.txt"), {"mechanic_block": format_mechanic_block(mech)})
    return generate_with_tool(
        system_prompt=sys_p, user_prompt=user_p, tool_schema=REVIEW_TOOL,
        model=model, temperature=temp, max_tokens=3072, log_dir=log_dir,
        repeat_penalty=repeat_penalty,
    )


def call_synth(mech: dict, reviews: list[dict], model: str, temp: float, log_dir: Path,
               repeat_penalty: float | None) -> dict:
    sys_p = load_prompt("review_system.txt")  # shared standards
    user_p = render(load_prompt("synth_user.txt"), {
        "mechanic_block": format_mechanic_block(mech),
        "reviews_block": format_reviews_block(reviews),
        "council_size": len(reviews),
    })
    # Synth re-emits the full mechanic (2 example cards) + consensus prose; local
    # models are verbose, so give it real headroom or it truncates mid-JSON.
    return generate_with_tool(
        system_prompt=sys_p, user_prompt=user_p, tool_schema=SYNTH_TOOL,
        model=model, temperature=temp, max_tokens=8192, log_dir=log_dir,
        repeat_penalty=repeat_penalty,
    )


# Escalating repeat_penalty rungs for retrying a synth that looped/truncated.
# Mirrors the real app's theme_extractor JSON-subcall loop-breaker: on llama.cpp
# repeat_penalty actually moves the sampler, and >1.20 noticeably degrades JSON
# output, so 1.20 is the ceiling. Attempt 1 uses the run's base --repeat-penalty;
# these are the higher rungs tried only after a failure.
SYNTH_RETRY_PENALTIES = (1.15, 1.20)


def call_synth_escalating(mech: dict, reviews: list[dict], model: str, temp: float,
                          log_dir: Path, base_penalty: float | None) -> dict | None:
    """Call the synth, escalating repeat_penalty on a looped/truncated reply.

    The synth is the one call that reliably trips Gemma's constrained-JSON
    repetition collapse — it re-emits the whole mechanic (2 example cards) plus
    consensus prose, fed all the reviews, so it generates far past where a
    correct answer would close and ``check_post_call_response`` raises on the
    ``length`` finish. On llama.cpp a higher repeat_penalty breaks those loops in
    practice, so on failure we retry at progressively higher penalties up to the
    1.20 JSON-safe ceiling. Returns the first response carrying a usable
    ``revised_mechanic``, or ``None`` if every rung failed.
    """
    rungs = [base_penalty] + [
        p for p in SYNTH_RETRY_PENALTIES if base_penalty is None or p > base_penalty
    ]
    last_exc: Exception | None = None
    for i, rp in enumerate(rungs, 1):
        tag = f"repeat_penalty={rp}" if rp is not None else "default repeat_penalty"
        try:
            resp = call_synth(mech, reviews, model, temp, log_dir, rp)
        except Exception as exc:  # truncation guard raises here on a loop
            last_exc = exc
            print(f"      synth attempt {i}/{len(rungs)} ({tag}) failed: "
                  f"{type(exc).__name__}: {exc}")
            continue
        if (resp.get("result") or {}).get("revised_mechanic"):
            if i > 1:
                print(f"      synth recovered on attempt {i} ({tag})")
            return resp
        print(f"      synth attempt {i}/{len(rungs)} ({tag}) parsed but emitted no "
              f"revised_mechanic; escalating")
    if last_exc:
        print(f"      synth exhausted all {len(rungs)} attempt(s) — keeping current mechanic")
    return None


# ── council review of one mechanic (the heart of the prototype) ────────────


def review_one(draft: dict, *, model: str, council_size: int, max_iterations: int,
               review_temp: float, synth_temp: float, log_dir: Path,
               repeat_penalty: float | None) -> dict:
    """Council + iteration loop. Mirrors the planned production design:

      1. ``council_size`` independent reviewers critique the current mechanic.
      2. If all say OK → done (mechanic stands).
      3. Else a synthesizer applies a >=2/council consensus filter and emits an
         improved mechanic + verdict + changelog.
      4. Re-review the revision; repeat until OK or the iteration budget runs out.

    Every call is best-effort: a failed reviewer is skipped; a failed synth keeps
    the current mechanic. A bad review pass never destroys a good draft. The
    mechanic name is never allowed to change (anti-rename guard).
    """
    original_name = (draft.get("name") or "").strip()
    mechanic = draft
    notes: list[str] = []
    rounds: list[dict] = []
    tok_in = tok_out = 0
    cost = 0.0
    final_verdict = "OK"

    for rnd in range(1, max_iterations + 1):
        # Phase 1 — independent reviewers
        reviews: list[dict] = []
        for member in range(1, council_size + 1):
            try:
                resp = call_reviewer(mechanic, model, review_temp, log_dir, repeat_penalty)
            except Exception as exc:  # skip a failed reviewer, don't abort
                print(f"      reviewer {member} failed: {type(exc).__name__}: {exc}")
                continue
            r = resp.get("result") or {}
            reviews.append({
                "member": member,
                "verdict": r.get("verdict", "OK"),
                "issues": r.get("issues") or [],
            })
            tok_in += resp.get("input_tokens", 0) or 0
            tok_out += resp.get("output_tokens", 0) or 0
            cost += cost_from_result(resp)

        all_ok = bool(reviews) and all(r["verdict"] == "OK" for r in reviews)
        round_rec: dict = {
            "round": rnd,
            "mechanic": mechanic,
            "reviews": reviews,
            "all_ok": all_ok,
            "synth": None,
        }

        if all_ok or not reviews:
            rounds.append(round_rec)
            final_verdict = "OK"
            break

        # Phase 2 — synthesis (consensus filter + revision). The synth is the call
        # that trips Gemma's constrained-JSON repetition collapse, so retry it with
        # escalating repeat_penalty (the real app's theme_extractor loop-breaker).
        sresp = call_synth_escalating(mechanic, reviews, model, synth_temp, log_dir, repeat_penalty)
        if sresp is None:
            rounds.append(round_rec)
            final_verdict = "REVISE"
            break
        s = sresp.get("result") or {}
        tok_in += sresp.get("input_tokens", 0) or 0
        tok_out += sresp.get("output_tokens", 0) or 0
        cost += cost_from_result(sresp)

        revised = s.get("revised_mechanic")
        if isinstance(revised, dict) and revised:
            # Anti-rename guard.
            rev_name = (revised.get("name") or "").strip()
            if original_name and rev_name and rev_name.lower() != original_name.lower():
                revised["name"] = original_name
            mechanic = revised
        note = (s.get("review_notes") or "").strip()
        if note:
            notes.append(note)
        round_rec["synth"] = {
            "synthesis": s.get("synthesis", ""),
            "verdict": s.get("verdict", "REVISE"),
            "consensus_issues": s.get("consensus_issues") or [],
            "review_notes": note,
        }
        rounds.append(round_rec)
        final_verdict = s.get("verdict", "REVISE")

        if final_verdict == "OK":
            break  # synthesizer is confident the revision is now clean

    return {
        "draft": draft,
        "final": mechanic,
        "final_verdict": final_verdict,
        "review_notes": " ".join(notes),
        "rounds": rounds,
        "tokens": {"in": tok_in, "out": tok_out},
        "cost": cost,
    }


# ── field-level diff (draft vs final) for the report ───────────────────────


def diff_mechanic(draft: dict, final: dict) -> list[str]:
    out = []
    for field in ("reminder_text", "complexity", "keyword_type"):
        a, b = draft.get(field), final.get(field)
        if a != b:
            out.append(f"- {field}: {a!r} → {b!r}")
    if (draft.get("colors") or []) != (final.get("colors") or []):
        out.append(f"- colors: {draft.get('colors')} → {final.get('colors')}")
    da, db = draft.get("example_cards") or [], final.get("example_cards") or []
    for i in range(max(len(da), len(db))):
        ca = da[i] if i < len(da) else {}
        cb = db[i] if i < len(db) else {}
        if (ca.get("oracle_text"), ca.get("name"), ca.get("type_line")) != (
            cb.get("oracle_text"), cb.get("name"), cb.get("type_line")
        ):
            out.append(f"- example {i + 1} rewritten: {ca.get('name', '?')} → {cb.get('name', '?')}")
    return out


# ── report writers ─────────────────────────────────────────────────────────


def build_report(results: list[dict], meta: dict) -> str:
    lines = [
        f"# Mechanic lab run — {meta['timestamp']}",
        "",
        f"- model: `{meta['model']}`  ·  council: {meta['council']}  ·  "
        f"max iterations: {meta['iterations']}",
        f"- theme: **{meta['theme_name']}**",
        f"- generated: {meta['generated']}  ·  reviewed: {len(results)}",
        f"- total cost: ${meta['cost']:.4f}  ·  tokens: "
        f"{meta['tokens']['in']:,} in / {meta['tokens']['out']:,} out",
        "",
        "---",
        "",
    ]
    for idx, res in enumerate(results, 1):
        final = res["final"]
        changed = res["review_notes"] != "" or diff_mechanic(res["draft"], final)
        flag = "REVISED" if changed else "unchanged"
        lines += [
            f"## {idx}. {final.get('name', '?')}  ·  final verdict: "
            f"{res['final_verdict']}  ·  {flag}",
            "",
            "### Draft",
            "```",
            format_mechanic_block(res["draft"]),
            "```",
            "",
        ]
        for rrec in res["rounds"]:
            lines.append(f"### Round {rrec['round']} — reviewers")
            lines.append("```")
            lines.append(format_reviews_block(rrec["reviews"]))
            lines.append("```")
            if rrec["all_ok"]:
                lines.append("_All reviewers OK._")
                lines.append("")
                continue
            syn = rrec["synth"]
            if syn:
                lines.append(f"**Synthesis** (verdict: {syn['verdict']}): {syn['synthesis']}")
                if syn["consensus_issues"]:
                    lines.append("")
                    lines.append("Consensus issues acted on:")
                    for ci in syn["consensus_issues"]:
                        lines.append(
                            f"- [{ci.get('category', '?')}] (agree {ci.get('agreement', '?')}) "
                            f"{ci.get('description', '')}"
                        )
                if syn["review_notes"]:
                    lines.append("")
                    lines.append(f"Changelog: {syn['review_notes']}")
            lines.append("")
        d = diff_mechanic(res["draft"], final)
        lines += ["### Final", "```", format_mechanic_block(final), "```", ""]
        if d:
            lines += ["**What changed:**", *d, ""]
        lines += ["---", ""]
    return "\n".join(lines)


def print_console_summary(results: list[dict], meta: dict) -> None:
    print("\n" + "=" * 70)
    print(f"RUN SUMMARY — model {meta['model']} · council {meta['council']} · "
          f"theme {meta['theme_name']}")
    print("=" * 70)
    for idx, res in enumerate(results, 1):
        final = res["final"]
        d = diff_mechanic(res["draft"], final)
        flag = "REVISED" if (res["review_notes"] or d) else "unchanged"
        print(f"\n{idx}. {final.get('name', '?')}  [{flag}, final verdict "
              f"{res['final_verdict']}, {len(res['rounds'])} round(s)]")
        print(f"   {(final.get('reminder_text') or '').strip()}")
        if res["review_notes"]:
            print(f"   notes: {res['review_notes']}")
        for line in d:
            print(f"   {line}")
    print(f"\nTotal: ${meta['cost']:.4f} · "
          f"{meta['tokens']['in']:,} in / {meta['tokens']['out']:,} out tokens")


# ── orchestration ──────────────────────────────────────────────────────────


def generate_drafts(theme: dict, count: int, set_size: int, mechanic_count: int,
                    model: str, temp: float, log_dir: Path,
                    repeat_penalty: float | None) -> tuple[list[dict], dict, float]:
    accepted: list[dict] = []
    tok_in = tok_out = 0
    cost = 0.0
    for i in range(count):
        print(f"  generating draft {i + 1}/{count} ...")
        try:
            resp = call_generate(theme, accepted, i + 1, count, set_size, mechanic_count,
                                 model, temp, log_dir, repeat_penalty)
        except Exception as exc:
            print(f"    generation failed: {type(exc).__name__}: {exc}")
            continue
        mech = resp.get("result") or {}
        if not mech.get("name"):
            print("    generation returned no usable mechanic; skipping")
            continue
        accepted.append(mech)
        tok_in += resp.get("input_tokens", 0) or 0
        tok_out += resp.get("output_tokens", 0) or 0
        cost += cost_from_result(resp)
        print(f"    -> {mech.get('name')} ({''.join(mech.get('colors') or []) or 'colorless'}, "
              f"cx{mech.get('complexity', '?')})")
    return accepted, {"in": tok_in, "out": tok_out}, cost


def main() -> int:
    ap = argparse.ArgumentParser(description="Prototype mechanic generation + council review.")
    ap.add_argument("--theme", default=str(HERE / "themes" / "sample.json"),
                    help="Path to a theme JSON file.")
    ap.add_argument("--count", type=int, default=3, help="How many mechanics to generate.")
    ap.add_argument("--drafts", default=None,
                    help="Skip generation; load drafts from this JSON file (replay the review).")
    # Default to the SAME local model the real `mechanics` stage uses
    # (registry key gemma4-26b-vram-dynamic -> model_id vlad-gemma4-26b-dynamic).
    # Pass --model claude-sonnet-4-6 / claude-opus-4-6 for the API ceiling
    # (needs ANTHROPIC_API_KEY in C:/Programming/MTGAI/.env).
    ap.add_argument("--model", default="vlad-gemma4-26b-dynamic", help="Model id (any registry entry).")
    ap.add_argument("--review-model", default=None, help="Override model for review (default = --model).")
    ap.add_argument("--council", type=int, default=3, help="Reviewers per round.")
    ap.add_argument("--iterations", type=int, default=3, help="Max review rounds.")
    ap.add_argument("--gen-temp", type=float, default=0.9)
    ap.add_argument("--review-temp", type=float, default=0.4)
    ap.add_argument("--synth-temp", type=float, default=0.2)
    # 1.1 is the provider default (LLAMACPP_REPEAT_PENALTY) the real app uses for
    # ALL structured tool-use — the mechanics stage included — and on llama.cpp it
    # actually moves the sampler, breaking Gemma's constrained-JSON repetition
    # collapse. The synth call escalates further (1.15 → 1.20) on a looped/truncated
    # reply; >1.20 degrades JSON output, so that's the ceiling. Ignored on Anthropic.
    ap.add_argument("--repeat-penalty", type=float, default=1.1,
                    help="llamacpp only; provider default 1.1. Synth retries escalate to 1.20. "
                         "Ignored on Anthropic.")
    ap.add_argument("--no-review", action="store_true", help="Only generate; skip the review.")
    ap.add_argument("--set-size", type=int, default=250)
    ap.add_argument("--mechanic-count", type=int, default=None,
                    help="Target keep-count for the gen prompt's density math (default = --count).")
    args = ap.parse_args()

    review_model = args.review_model or args.model
    mechanic_count = args.mechanic_count or args.count

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    RUNS.mkdir(parents=True, exist_ok=True)
    log_dir = RUNS / stamp / "llm-logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    gen_tokens = {"in": 0, "out": 0}
    gen_cost = 0.0

    if args.drafts:
        theme = {"name": "(replay)"}
        drafts = json.loads(Path(args.drafts).read_text(encoding="utf-8"))
        print(f"Loaded {len(drafts)} draft(s) from {args.drafts} — review-only replay.")
    else:
        theme = json.loads(Path(args.theme).read_text(encoding="utf-8"))
        print(f"Theme: {theme.get('name', '(unnamed)')}  ·  generating {args.count} mechanic(s) "
              f"with {args.model} ...")
        drafts, gen_tokens, gen_cost = generate_drafts(
            theme, args.count, args.set_size, mechanic_count, args.model, args.gen_temp,
            log_dir, args.repeat_penalty,
        )
        # Always persist drafts so a future run can replay the review against them.
        (RUNS / f"{stamp}.drafts.json").write_text(
            json.dumps(drafts, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    if not drafts:
        print("No drafts to work with — aborting.")
        return 1

    results: list[dict] = []
    if args.no_review:
        results = [{"draft": d, "final": d, "final_verdict": "OK", "review_notes": "",
                    "rounds": [], "tokens": {"in": 0, "out": 0}, "cost": 0.0} for d in drafts]
    else:
        for i, draft in enumerate(drafts, 1):
            print(f"\nReviewing {i}/{len(drafts)}: {draft.get('name', '?')} "
                  f"(council {args.council}, model {review_model}) ...")
            t0 = time.time()
            res = review_one(
                draft, model=review_model, council_size=args.council,
                max_iterations=args.iterations, review_temp=args.review_temp,
                synth_temp=args.synth_temp, log_dir=log_dir, repeat_penalty=args.repeat_penalty,
            )
            print(f"   done in {time.time() - t0:.1f}s — final verdict {res['final_verdict']}")
            results.append(res)

    tot_in = gen_tokens["in"] + sum(r["tokens"]["in"] for r in results)
    tot_out = gen_tokens["out"] + sum(r["tokens"]["out"] for r in results)
    tot_cost = gen_cost + sum(r["cost"] for r in results)
    meta = {
        "timestamp": stamp,
        "model": review_model,
        "council": args.council,
        "iterations": args.iterations,
        "theme_name": theme.get("name", "(unnamed)"),
        "generated": "(replay)" if args.drafts else len(drafts),
        "cost": tot_cost,
        "tokens": {"in": tot_in, "out": tot_out},
    }

    report_md = build_report(results, meta)
    (RUNS / f"{stamp}.md").write_text(report_md, encoding="utf-8")
    (RUNS / f"{stamp}.json").write_text(
        json.dumps({"meta": meta, "results": results}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print_console_summary(results, meta)
    print(f"\nFull report:  {RUNS / (stamp + '.md')}")
    print(f"Raw JSON:     {RUNS / (stamp + '.json')}")
    if not args.drafts:
        print(f"Drafts:       {RUNS / (stamp + '.drafts.json')}  (replay with --drafts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
