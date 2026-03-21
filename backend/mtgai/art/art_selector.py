"""AI-powered art version selector.

Reviews multiple versions of generated card art and picks the best one
based on prompt adherence, visual quality, and absence of AI artifacts.

Uses Haiku vision (cheap + fast) to evaluate images.

CLI usage:
    python -m mtgai.art.art_selector --set ASD [--card W-C-01] [--dry-run]
"""

import argparse
import base64
import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path

from anthropic import Anthropic

logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path("C:/Programming/MTGAI/output")

# Load .env
_ENV_PATH = Path("C:/Programming/MTGAI/.env")
if _ENV_PATH.exists():
    for line in _ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

SYSTEM_PROMPT = """\
You are a quality assurance reviewer for card game art. You will be shown \
multiple versions of art generated for the same card, along with the original \
prompt that was used to generate them.

Your job is to pick the BEST version based on these criteria (in priority order):

1. **No AI artifacts**: Reject images with extra/missing fingers, distorted hands, \
   mangled faces, extra limbs, fused body parts, text/watermark artifacts, or any \
   obviously broken anatomy. This is the most important criterion.
2. **Prompt adherence**: The image should match what the prompt describes — correct \
   subject, pose, environment, colors, mood.
3. **Composition**: Good focal point, readable at small card size (~2.5 x 1.8 inches), \
   subject clearly visible, not too dark or washed out.
4. **Color identity**: Should feel appropriate for the card's color (white=warm/bright, \
   blue=cool/teal, black=dark/shadowy, red=warm/fiery, green=natural/lush).
5. **Style consistency**: Stylized digital illustration look, not photorealistic, \
   not overly cartoonish.

If ALL versions have serious artifacts or are unusable, say so — don't force a pick."""

TOOL_SCHEMA = {
    "name": "art_selection",
    "description": "Select the best art version for a card.",
    "input_schema": {
        "type": "object",
        "properties": {
            "pick": {
                "type": "string",
                "enum": ["v1", "v2", "v3", "none"],
                "description": "Which version to use, or 'none' if all are unusable.",
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "How confident you are in this pick.",
            },
            "reasoning": {
                "type": "string",
                "description": (
                    "2-3 sentences explaining the pick. Mention specific artifacts "
                    "found in rejected versions and what makes the pick better."
                ),
            },
            "artifacts_found": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "version": {"type": "string"},
                        "issue": {"type": "string"},
                    },
                    "required": ["version", "issue"],
                },
                "description": "List of artifact issues found in any version.",
            },
        },
        "required": ["pick", "confidence", "reasoning", "artifacts_found"],
    },
}


def _image_to_base64(path: Path) -> str:
    """Read an image file and return base64-encoded string."""
    return base64.standard_b64encode(path.read_bytes()).decode("ascii")


def _build_message_content(
    card_name: str,
    collector_number: str,
    colors: list[str],
    prompt: str,
    image_paths: list[Path],
) -> list[dict]:
    """Build multimodal message content with images and text."""
    content: list[dict] = []

    # Text context first
    color_names = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}
    color_str = "/".join(color_names.get(c, c) for c in colors) if colors else "Colorless"

    content.append(
        {
            "type": "text",
            "text": (
                f"Card: {card_name} ({collector_number})\n"
                f"Color: {color_str}\n"
                f"Art prompt: {prompt}\n\n"
                f"Below are {len(image_paths)} versions. Pick the best one."
            ),
        }
    )

    # Add images with labels
    for i, path in enumerate(image_paths, 1):
        content.append({"type": "text", "text": f"\n--- Version {i} (v{i}) ---"})
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": _image_to_base64(path),
                },
            }
        )

    return content


def select_best_version(
    card_name: str,
    collector_number: str,
    colors: list[str],
    prompt: str,
    image_paths: list[Path],
    model: str = "claude-haiku-4-5-20251001",
) -> dict:
    """Send images to Claude vision and get the best version pick.

    Returns dict with pick, confidence, reasoning, artifacts_found,
    plus token counts.
    """
    client = Anthropic()

    content = _build_message_content(card_name, collector_number, colors, prompt, image_paths)

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=0.0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
        tools=[TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": TOOL_SCHEMA["name"]},
    )

    for block in response.content:
        if block.type == "tool_use":
            return {
                **block.input,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "model": model,
            }

    raise ValueError("No tool_use block in response")


def select_art_for_set(
    set_code: str,
    card_filter: str | None = None,
    dry_run: bool = False,
    progress_callback: Callable[[str, int, int, str, float], None] | None = None,
) -> dict:
    """Run art selection for all cards with multiple versions.

    Returns summary dict.
    """
    from mtgai.io.card_io import load_card
    from mtgai.io.paths import card_slug

    cards_dir = OUTPUT_ROOT / "sets" / set_code / "cards"
    art_dir = OUTPUT_ROOT / "sets" / set_code / "art"
    log_dir = OUTPUT_ROOT / "sets" / set_code / "art-selection-logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    card_files = sorted(cards_dir.glob("*.json"))
    if card_filter:
        card_files = [f for f in card_files if f.name.startswith(card_filter)]

    total_input_tokens = 0
    total_output_tokens = 0
    results = []
    skipped = 0

    for card_file in card_files:
        card = load_card(card_file)
        cn = card.collector_number
        slug = card_slug(cn, card.name)

        # Find all versions
        versions = sorted(art_dir.glob(f"{slug}_v*.png"))
        if len(versions) < 2:
            logger.info("SKIP %s — only %d version(s)", cn, len(versions))
            skipped += 1
            continue

        if not card.art_prompt:
            logger.info("SKIP %s — no art_prompt", cn)
            skipped += 1
            continue

        logger.info("REVIEW %s: %s (%d versions)", cn, card.name, len(versions))

        if dry_run:
            results.append({"card": cn, "name": card.name, "versions": len(versions)})
            continue

        try:
            selection = select_best_version(
                card_name=card.name,
                collector_number=cn,
                colors=card.colors or [],
                prompt=card.art_prompt,
                image_paths=versions,
            )

            total_input_tokens += selection["input_tokens"]
            total_output_tokens += selection["output_tokens"]

            result = {
                "collector_number": cn,
                "name": card.name,
                "versions_reviewed": len(versions),
                "pick": selection["pick"],
                "confidence": selection["confidence"],
                "reasoning": selection["reasoning"],
                "artifacts_found": selection["artifacts_found"],
                "version_files": [v.name for v in versions],
            }
            results.append(result)

            # Save per-card log
            log_path = log_dir / f"{cn}.json"
            log_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

            logger.info(
                "  → %s (confidence: %s) — %s",
                selection["pick"],
                selection["confidence"],
                selection["reasoning"][:80] + "...",
            )

            if progress_callback is not None:
                card_cost = (selection["input_tokens"] * 0.80 / 1_000_000) + (
                    selection["output_tokens"] * 4.0 / 1_000_000
                )
                progress_callback(
                    cn,
                    len([r for r in results if "pick" in r]) + skipped,
                    len(card_files),
                    f"Selected art for {card.name}",
                    card_cost,
                )

            time.sleep(0.1)  # rate limit

        except Exception as e:
            logger.error("  ERROR on %s: %s", cn, e)
            results.append({"card": cn, "name": card.name, "error": str(e)})

    est_cost = (total_input_tokens * 0.80 / 1_000_000) + (total_output_tokens * 4.0 / 1_000_000)

    summary = {
        "set_code": set_code,
        "reviewed": len([r for r in results if "pick" in r]),
        "skipped": skipped,
        "errors": len([r for r in results if "error" in r]),
        "results": results,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "estimated_cost_usd": round(est_cost, 4),
        "dry_run": dry_run,
    }

    summary_path = log_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return summary


def generate_selection_report(set_code: str) -> Path:
    """Generate an HTML report from art selection results."""

    log_dir = OUTPUT_ROOT / "sets" / set_code / "art-selection-logs"
    report_path = OUTPUT_ROOT / "sets" / set_code / "reports" / "art-selection-report.html"

    # Load all per-card results
    results = []
    for log_file in sorted(log_dir.glob("*.json")):
        if log_file.name == "summary.json":
            continue
        results.append(json.loads(log_file.read_text(encoding="utf-8")))

    # Load prompts for display
    prompt_dir = OUTPUT_ROOT / "sets" / set_code / "art-direction" / "prompt-logs"

    # Color definitions
    color_css = {
        "W": ("#f9faf4", "#ccc"),
        "U": ("#0e68ab", "transparent"),
        "B": ("#2b2a2a", "#555"),
        "R": ("#d3202a", "transparent"),
        "G": ("#00733e", "transparent"),
    }

    cards_html = []
    for r in results:
        cn = r["collector_number"]

        # Load prompt
        prompt_file = prompt_dir / f"{cn}.json"
        prompt_text = ""
        if prompt_file.exists():
            prompt_data = json.loads(prompt_file.read_text(encoding="utf-8"))
            prompt_text = prompt_data.get("full_prompt", "")

        # Determine color pip from collector number prefix
        color_key = cn.split("-")[0]
        bg, border = color_css.get(color_key, ("#c4a24e", "transparent"))

        # Build version divs
        pick = r.get("pick", "none")
        version_files = r.get("version_files", [])
        versions_html = []
        for vf in version_files:
            # Extract version number from filename like "W-C-01_name_v1.png"
            v_num = vf.rsplit("_v", 1)[-1].replace(".png", "")
            v_label = f"v{v_num}"
            is_winner = v_label == pick
            cls = "version winner" if is_winner else "version rejected"
            label = f"&#x2714; PICK &mdash; {v_label}" if is_winner else v_label
            versions_html.append(
                f'<div class="{cls}">'
                f'<img src="../art/{vf}" alt="{v_label}">'
                f'<div class="version-label">{label}</div>'
                f"</div>"
            )

        # Artifacts list
        artifacts_html = ""
        for af in r.get("artifacts_found", []):
            artifacts_html += f'<span class="issue">[{af["version"]}] {af["issue"]}</span> '

        reasoning = r.get("reasoning", "")
        confidence = r.get("confidence", "?")

        card_html = f"""
<div class="card-section {"picked" if pick != "none" else ""}">
  <div class="card-header">
    <span class="card-name">
      <span class="color-pip" style="background:{bg}; border:1px solid {border}"></span>
      {cn}: {r["name"]}
    </span>
    <span class="card-type">Confidence: {confidence}</span>
  </div>
  <div class="prompt">{prompt_text}</div>
  <div class="versions">{"".join(versions_html)}</div>
  <div class="verdict pick">
    <strong>Pick: {pick}.</strong> {reasoning}
    {f"<br><br>Artifacts: {artifacts_html}" if artifacts_html else ""}
  </div>
</div>"""
        cards_html.append(card_html)

    # Summary table
    picks = {}
    for r in results:
        p = r.get("pick", "none")
        picks[p] = picks.get(p, 0) + 1

    summary_rows = ""
    for r in results:
        summary_rows += (
            f"<tr><td>{r['collector_number']}</td>"
            f"<td>{r['name']}</td>"
            f"<td>{r.get('pick', '?')}</td>"
            f"<td>{r.get('confidence', '?')}</td>"
            f"<td>{r.get('reasoning', '')[:60]}...</td></tr>\n"
        )

    subtitle = f"{len(results)} cards reviewed &bull; 3 versions each &bull; Haiku vision selector"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>ASD Art Selection Report — AI Review</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #1a1a2e; color: #e0e0e0;
    font-family: 'Segoe UI', Tahoma, sans-serif; padding: 2rem;
  }}
  h1 {{ color: #f0c040; margin-bottom: 0.5rem; font-size: 1.8rem; }}
  .subtitle {{ color: #888; margin-bottom: 2rem; font-size: 0.95rem; }}
  .card-section {{
    background: #16213e; border-radius: 12px;
    padding: 1.5rem; margin-bottom: 2rem;
    border: 1px solid #2a2a4a;
  }}
  .card-section.picked {{
    border-color: #4ade80;
    box-shadow: 0 0 20px rgba(74, 222, 128, 0.1);
  }}
  .card-header {{
    display: flex; justify-content: space-between;
    align-items: baseline; margin-bottom: 0.5rem;
  }}
  .card-name {{ font-size: 1.3rem; font-weight: bold; color: #e8d5b5; }}
  .card-type {{ color: #888; font-size: 0.85rem; }}
  .prompt {{
    background: #0f1629; padding: 0.75rem 1rem;
    border-radius: 6px; font-size: 0.8rem; color: #a0a0c0;
    margin-bottom: 1rem; line-height: 1.4; font-style: italic;
  }}
  .versions {{ display: flex; gap: 1rem; flex-wrap: wrap; }}
  .version {{
    flex: 1; min-width: 280px; max-width: 33%;
    border-radius: 8px; overflow: hidden;
    border: 3px solid transparent;
  }}
  .version.winner {{ border-color: #4ade80; }}
  .version.rejected {{ opacity: 0.6; }}
  .version img {{ width: 100%; display: block; }}
  .version-label {{
    padding: 0.5rem; text-align: center;
    font-size: 0.85rem; background: #0f1629;
  }}
  .version.winner .version-label {{
    background: #1a3a2a; color: #4ade80; font-weight: bold;
  }}
  .verdict {{
    margin-top: 1rem; padding: 0.75rem 1rem;
    border-radius: 6px; line-height: 1.5; font-size: 0.9rem;
  }}
  .verdict.pick {{ background: #1a3a2a; border-left: 4px solid #4ade80; }}
  .verdict strong {{ color: #4ade80; }}
  .issue {{
    color: #f87171; display: inline-block; margin-right: 0.5rem;
  }}
  .color-pip {{
    display: inline-block; width: 14px; height: 14px;
    border-radius: 50%; vertical-align: middle; margin-right: 4px;
  }}
  .summary {{
    background: #16213e; border-radius: 12px;
    padding: 1.5rem; margin-top: 2rem;
    border: 1px solid #f0c040;
  }}
  .summary h2 {{ color: #f0c040; margin-bottom: 0.75rem; }}
  .summary table {{ width: 100%; border-collapse: collapse; }}
  .summary th {{
    text-align: left; padding: 0.4rem 0.5rem; color: #888;
    border-bottom: 1px solid #2a2a4a; font-size: 0.85rem;
  }}
  .summary td {{ padding: 0.4rem 0.5rem; font-size: 0.9rem; }}
</style>
</head>
<body>

<h1>ASD Art Selection Report — AI Review</h1>
<p class="subtitle">{subtitle}</p>

{"".join(cards_html)}

<div class="summary">
  <h2>Selection Summary</h2>
  <table>
    <thead><tr><th>Card</th><th>Name</th><th>Pick</th><th>Confidence</th><th>Reasoning</th></tr></thead>
    <tbody>{summary_rows}</tbody>
  </table>
  <p style="margin-top: 1rem; color: #888; font-size: 0.85rem;">
    Pick distribution: {", ".join(f"{k}: {v}" for k, v in sorted(picks.items()))}
  </p>
</div>

</body>
</html>"""

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(html, encoding="utf-8")
    return report_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="AI-powered art version selector")
    parser.add_argument("--set", default="ASD", help="Set code (default: ASD)")
    parser.add_argument("--card", default=None, help="Single card collector number")
    parser.add_argument("--dry-run", action="store_true", help="List cards without calling API")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Generate report from existing logs",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.report_only:
        report_path = generate_selection_report(args.set)
        print(f"Report generated: {report_path}")
        return

    summary = select_art_for_set(
        set_code=args.set,
        card_filter=args.card,
        dry_run=args.dry_run,
    )

    print(f"\n{'=' * 60}")
    print(f"Art Selection — {summary['set_code']}")
    print(f"{'=' * 60}")
    print(f"Reviewed:  {summary['reviewed']}")
    print(f"Skipped:   {summary['skipped']}")
    print(f"Errors:    {summary['errors']}")
    if not summary["dry_run"]:
        print(
            f"Tokens:    {summary['total_input_tokens']:,} in / "
            f"{summary['total_output_tokens']:,} out"
        )
        print(f"Est. cost: ${summary['estimated_cost_usd']:.4f}")

    # Generate HTML report
    if not summary["dry_run"] and summary["reviewed"] > 0:
        report_path = generate_selection_report(args.set)
        print(f"\nReport: {report_path}")


if __name__ == "__main__":
    main()
