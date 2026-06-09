"""AI-powered art version selector.

Reviews multiple versions of generated card art and picks the best one
based on prompt adherence, visual quality, and absence of AI artifacts.

Uses Haiku vision (cheap + fast) to evaluate images.

CLI usage:
    python -m mtgai.art.art_selector --mtg path/to/project.mtg [--card W-C-01] [--dry-run]
"""

import argparse
import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path

from llmfacade import ImageBlock, TextBlock

from mtgai.generation import temperatures as temps
from mtgai.io.atomic import atomic_write_text
from mtgai.io.paths import repo_root

logger = logging.getLogger(__name__)

# Load .env
_ENV_PATH = repo_root() / ".env"
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


# ---------------------------------------------------------------------------
# Art-pick decisions store (merged Art Generation stage)
# ---------------------------------------------------------------------------
#
# ``<asset>/art_gen/decisions.json`` records, per collector number, which art
# version is the chosen one and where the choice came from. Mirrors ai_review's
# ``reviews/decisions.json``: the LLM judge writes ``source="auto"`` picks, and
# the merged Art Generation tab writes ``source="user"`` overrides (re-pick /
# upload) over the top. The picked filename is also stamped onto the card's
# ``art_path`` so the renderer + gallery resolve it.


def _decisions_path(set_dir):
    return set_dir / "art_gen" / "decisions.json"


def load_art_decisions(set_dir) -> dict:
    """Load the per-card art-pick decisions for the active project."""
    path = _decisions_path(set_dir)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Could not parse %s; starting fresh", path)
    return {}


def save_art_decisions(set_dir, decisions: dict) -> None:
    """Persist the per-card art-pick decisions store."""
    path = _decisions_path(set_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(decisions, indent=2))


def _build_tool_schema(version_count: int) -> dict:
    """Build the art-selection tool schema with a ``pick`` enum sized to the
    number of versions actually shown to the model.

    Hardcoding ``v1``-``v3`` would make a ``v4`` (or higher) pick fail Anthropic
    tool-use validation whenever a card has 4+ versions, all of which are sent
    to the model. The enum is derived per-call so the schema and the images
    shown always stay in sync.
    """
    versions = [f"v{i}" for i in range(1, version_count + 1)]
    return {
        "name": "art_selection",
        "description": "Select the best art version for a card.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pick": {
                    "type": "string",
                    "enum": [*versions, "none"],
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


def _build_message_content(
    card_name: str,
    collector_number: str,
    colors: list[str],
    prompt: str,
    image_paths: list[Path],
) -> list:
    """Build multimodal message content with text + image blocks."""
    color_names = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}
    color_str = "/".join(color_names.get(c, c) for c in colors) if colors else "Colorless"

    content: list = [
        TextBlock(
            f"Card: {card_name} ({collector_number})\n"
            f"Color: {color_str}\n"
            f"Art prompt: {prompt}\n\n"
            f"Below are {len(image_paths)} versions. Pick the best one."
        )
    ]
    for i, path in enumerate(image_paths, 1):
        content.append(TextBlock(f"\n--- Version {i} (v{i}) ---"))
        content.append(ImageBlock.from_path(path))
    return content


def _judge_is_vision_capable(model_id: str) -> bool:
    """Whether the resolved ``art_select`` model can perform the vision judge.

    Reads ``supports_vision`` off the model's registry entry (a context-tier twin
    inherits its base's flag). An unknown id is treated as NOT vision-capable so an
    unrecognized assignment skips the judge loudly rather than wasting one image
    request per card on a model that can't see them.
    """
    try:
        from mtgai.settings.model_registry import get_registry

        info = get_registry().get_llm_by_model_id(model_id)
        return bool(info and info.supports_vision)
    except Exception:
        return False


def select_best_version(
    card_name: str,
    collector_number: str,
    colors: list[str],
    prompt: str,
    image_paths: list[Path],
    model: str | None = None,
    log_dir: Path | bool = True,
) -> dict:
    """Send images to Claude vision and get the best version pick.

    Returns dict with pick, confidence, reasoning, artifacts_found,
    plus token counts.

    ``log_dir`` routes the llmfacade HTML/JSONL transcript: a ``Path`` writes it
    flat into that dir, ``True`` falls back to llmfacade's session dirs, ``False``
    disables it. ``select_art_for_set`` passes its ``art-selection-logs`` dir so the
    judge transcript (named ``art_selection-*`` via :func:`_convo_name`, like the
    ``generate_with_tool`` callers) sits beside the custom per-card JSON log.
    """
    from mtgai.generation.llm_client import (
        _convo_name,
        _get_provider,
        _make_tool,
        _resolve_provider,
    )
    from mtgai.runtime.active_project import require_active_project

    if model is None:
        model = require_active_project().settings.get_llm_model_id("art_select")

    tool_schema = _build_tool_schema(len(image_paths))
    # The best-of-N judge is a VISION call. The provider is resolved from the
    # model's registry entry (``_resolve_provider``) rather than hard-pinned, so
    # a vision-capable model on any provider routes correctly. Today every
    # vision-capable LLM entry is Anthropic, so this resolves to "anthropic" for
    # the working case — but it's correct-by-construction the day a non-Anthropic
    # (or local) vision judge lands. ``select_art_for_set`` pre-flights the
    # model's ``supports_vision`` flag and skips this call entirely for a
    # text-only model, so by the time we get here the model can judge images (or
    # the call raises in a keyless / out-of-credits env, caught + fallen back to
    # v1 there).
    provider = _get_provider(_resolve_provider(model))
    facade_model = provider.new_model(model)
    convo = facade_model.new_conversation(
        name=_convo_name(tool_schema),
        system_blocks=[SYSTEM_PROMPT],
        tools=[_make_tool(tool_schema)],
        tool_choice=tool_schema["name"],
        log_dir=log_dir,
    )
    convo.add_user_message(
        content=_build_message_content(card_name, collector_number, colors, prompt, image_paths)
    )
    # GREEDY is safe here: Haiku vision is a cloud model, so there's no local
    # sampler to bypass and no repetition-loop pathology (see temperatures.py).
    resp = convo.send(max_tokens=1024, temperature=temps.GREEDY)

    if not resp.tool_calls:
        raise ValueError("No tool_use block in response")

    usage = resp.usage
    return {
        **resp.tool_calls[0].input,
        "input_tokens": usage.prompt_tokens if usage else 0,
        "output_tokens": usage.completion_tokens if usage else 0,
        "model": model,
    }


def _pick_to_filename(pick: str, version_files: list[str]) -> str | None:
    """Map a judge pick ('v2') to its filename in ``version_files``.

    Returns None for 'none' / an out-of-range pick. ``version_files`` is the
    sorted list shown to the judge (index i == v{i+1}).
    """
    if not pick or pick == "none":
        return None
    try:
        idx = int(pick.lstrip("v")) - 1
    except ValueError:
        return None
    if 0 <= idx < len(version_files):
        return version_files[idx]
    return None


def _stamp_art_path(card, set_dir, filename: str | None):
    """Persist the picked version's filename onto ``card.art_path``.

    ``art_path`` is relative to the asset folder (``art/<file>``) so the renderer
    + gallery resolve it the same way they resolve a render path. A None filename
    (no usable version) leaves the card's existing art_path untouched.
    """
    if not filename:
        return
    from mtgai.io.card_io import save_card

    updated = card.model_copy(update={"art_path": f"art/{filename}"})
    save_card(updated, set_dir=set_dir)


def select_art_for_set(
    card_filter: str | None = None,
    dry_run: bool = False,
    progress_callback: Callable[[str, int, int, str, float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict:
    """Judge the best-of-N art versions per card and stamp the pick.

    For each card with >= 2 versions, the LLM judge (the ``art_select`` model
    assignment, which must be vision-capable) picks the best version; with exactly
    one version it is auto-picked (no LLM call). The pick is written to
    ``art_path`` and recorded in ``art_gen/decisions.json`` so the merged Art
    Generation tab can show + override it.

    The judge model is pre-flighted: if it is NOT vision-capable (e.g. the
    local-by-default text-only Gemma) the best-of-N judge is skipped for the whole
    run — every multi-version card auto-picks v1 with an ``auto_fallback`` decision
    and a ``judge_skipped`` summary signal — rather than wasting one (failing) image
    request per card. Assign a vision-capable model to enable best-of-N.

    ``should_cancel`` is an optional predicate polled at each card boundary; when
    it returns True the loop stops early (decisions written so far are kept, so a
    resume skips them) and ``summary["cancelled"]`` is set.

    Returns summary dict.
    """
    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.io.card_io import load_card
    from mtgai.io.paths import card_slug
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    set_code = project.set_code
    set_dir = set_artifact_dir()
    cards_dir = set_dir / "cards"
    art_dir = set_dir / "art"
    log_dir = set_dir / "art-selection-logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Pre-flight: the best-of-N judge is a VISION call, but the default-by-policy
    # ``art_select`` assignment is a text-only local model. Resolve the judge model
    # ONCE and, if it can't do vision, skip the judge for the whole run — auto-pick
    # v1 per card with a clear ``auto_fallback`` reason instead of attempting (and
    # silently failing) one image request per card. Surfaced loudly via the summary
    # + a single WARN rather than per-card error spam.
    judge_model = project.settings.get_llm_model_id("art_select")
    judge_capable = _judge_is_vision_capable(judge_model)
    judge_skipped_reason: str | None = None
    if not judge_capable:
        judge_skipped_reason = (
            f"art_select model {judge_model!r} is not vision-capable; best-of-N "
            "judge skipped (auto-picked v1). Assign a vision-capable model to "
            "art_select (e.g. apply the 'recommended' preset) to enable best-of-N."
        )
        logger.warning("Best-of-N art judge disabled: %s", judge_skipped_reason)

    decisions = load_art_decisions(set_dir)

    card_files = sorted(cards_dir.glob("*.json"))
    if card_filter:
        card_files = [f for f in card_files if f.name.startswith(card_filter)]

    total_input_tokens = 0
    total_output_tokens = 0
    results = []
    skipped = 0
    judge_failed = 0
    judge_skipped = 0

    cancelled = False
    for card_file in card_files:
        if should_cancel is not None and should_cancel():
            logger.info("Art selection cancelled by user after %d card(s)", len(results))
            cancelled = True
            break

        card = load_card(card_file)
        cn = card.collector_number
        slug = card_slug(cn, card.name)

        # Find all versions
        versions = sorted(art_dir.glob(f"{slug}_v*.png"))
        if len(versions) == 0:
            logger.info("SKIP %s — no versions", cn)
            skipped += 1
            continue

        if not card.art_prompt:
            logger.info("SKIP %s — no art_prompt", cn)
            skipped += 1
            continue

        version_files = [v.name for v in versions]

        # Single version: auto-pick v1, no LLM judge call needed.
        if len(versions) == 1:
            pick = "v1"
            _stamp_art_path(card, set_dir, version_files[0])
            decisions[cn] = {
                "pick": pick,
                "source": "auto_single",
                "reasoning": "Only one version generated.",
                "version_files": version_files,
            }
            save_art_decisions(set_dir, decisions)
            result = {
                "collector_number": cn,
                "name": card.name,
                "versions_reviewed": 1,
                "pick": pick,
                "confidence": "high",
                "reasoning": "Only one version generated.",
                "artifacts_found": [],
                "version_files": version_files,
            }
            results.append(result)
            atomic_write_text(log_dir / f"{cn}.json", json.dumps(result, indent=2))
            continue

        if dry_run:
            results.append({"card": cn, "name": card.name, "versions": len(versions)})
            continue

        # Judge model can't do vision: skip the LLM call, auto-pick v1. Same
        # ``auto_fallback`` decision shape as the exception path so the tab treats
        # it identically; ``judge_skipped`` (vs ``judge_failed``) distinguishes
        # "never attempted because text-only" from "attempted and the call raised".
        if not judge_capable:
            judge_skipped += 1
            _stamp_art_path(card, set_dir, version_files[0])
            decisions[cn] = {
                "pick": "v1",
                "source": "auto_fallback",
                "reasoning": judge_skipped_reason,
                "version_files": version_files,
            }
            save_art_decisions(set_dir, decisions)
            result = {
                "collector_number": cn,
                "name": card.name,
                "versions_reviewed": len(versions),
                "pick": "v1",
                "confidence": "low",
                "reasoning": judge_skipped_reason,
                "artifacts_found": [],
                "version_files": version_files,
                "judge_skipped": True,
            }
            results.append(result)
            atomic_write_text(log_dir / f"{cn}.json", json.dumps(result, indent=2))
            continue

        logger.info("REVIEW %s: %s (%d versions)", cn, card.name, len(versions))

        try:
            selection = select_best_version(
                card_name=card.name,
                collector_number=cn,
                colors=card.colors or [],
                prompt=card.art_prompt,
                image_paths=versions,
                model=judge_model,
                log_dir=log_dir,
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
                "version_files": version_files,
            }
            results.append(result)

            # Stamp the chosen version onto the card + record the auto-pick. A
            # user override (re-pick in the tab) writes the same decisions store
            # with source="user", which the tab merges over this.
            picked_file = _pick_to_filename(selection["pick"], version_files)
            _stamp_art_path(card, set_dir, picked_file)
            decisions[cn] = {
                "pick": selection["pick"],
                "source": "auto",
                "confidence": selection["confidence"],
                "reasoning": selection["reasoning"],
                "artifacts_found": selection["artifacts_found"],
                "version_files": version_files,
            }
            save_art_decisions(set_dir, decisions)

            # Save per-card log
            log_path = log_dir / f"{cn}.json"
            atomic_write_text(log_path, json.dumps(result, indent=2))

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
            # Judge unavailable (e.g. no Anthropic credits, keyless env, or the
            # assigned vision model can't run): DON'T leave the card with no art.
            # Fall back to auto-picking v1 — stamp art_path + record a distinct
            # ``auto_fallback`` decision — exactly like the single-version path,
            # so every card always ends with selected art and rendering has
            # something to render. The user can still re-pick in the tab.
            judge_failed += 1
            short_err = str(e).splitlines()[0][:120] if str(e) else type(e).__name__
            logger.error("  ERROR on %s: %s — defaulting to v1 (judge unavailable)", cn, e)
            pick = "v1"
            reasoning = f"Judge unavailable ({short_err}) — defaulted to v1."
            _stamp_art_path(card, set_dir, version_files[0])
            decisions[cn] = {
                "pick": pick,
                "source": "auto_fallback",
                "reasoning": reasoning,
                "error": str(e),
                "version_files": version_files,
            }
            save_art_decisions(set_dir, decisions)
            result = {
                "collector_number": cn,
                "name": card.name,
                "versions_reviewed": len(versions),
                "pick": pick,
                "confidence": "low",
                "reasoning": reasoning,
                "artifacts_found": [],
                "version_files": version_files,
                "judge_failed": True,
            }
            results.append(result)
            atomic_write_text(log_dir / f"{cn}.json", json.dumps(result, indent=2))

    est_cost = (total_input_tokens * 0.80 / 1_000_000) + (total_output_tokens * 4.0 / 1_000_000)

    summary = {
        "set_code": set_code,
        "reviewed": len([r for r in results if "pick" in r]),
        "skipped": skipped,
        # ``errors`` counts only results with NO pick (hard failures). A judge
        # failure that fell back to v1 has a pick + ``judge_failed`` flag, so it
        # is a successful selection, not an error — surfaced via ``judge_failed``.
        "errors": len([r for r in results if "pick" not in r and "error" in r]),
        "judge_failed": judge_failed,
        "judge_skipped": judge_skipped,
        "judge_skipped_reason": judge_skipped_reason,
        "art_select_model": judge_model,
        "results": results,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "estimated_cost_usd": round(est_cost, 4),
        "dry_run": dry_run,
        "cancelled": cancelled,
    }

    summary_path = log_dir / "summary.json"
    atomic_write_text(summary_path, json.dumps(summary, indent=2))

    return summary


def generate_selection_report() -> Path:
    """Generate an HTML report from art selection results for the active project."""

    from mtgai.io.asset_paths import set_artifact_dir

    set_dir = set_artifact_dir()
    log_dir = set_dir / "art-selection-logs"
    report_path = set_dir / "reports" / "art-selection-report.html"

    # Load all per-card results
    results = []
    for log_file in sorted(log_dir.glob("*.json")):
        if log_file.name == "summary.json":
            continue
        results.append(json.loads(log_file.read_text(encoding="utf-8")))

    # Load prompts for display
    prompt_dir = set_dir / "art-direction" / "prompt-logs"

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
<title>Art Selection Report — AI Review</title>
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

<h1>Art Selection Report — AI Review</h1>
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
    atomic_write_text(report_path, html)
    return report_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="AI-powered art version selector")
    parser.add_argument(
        "--mtg",
        required=True,
        help="Path to a .mtg project file (the project's asset_folder must be set)",
    )
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

    from mtgai.runtime.cli_shim import activate_from_mtg

    activate_from_mtg(args.mtg)

    if args.report_only:
        report_path = generate_selection_report()
        print(f"Report generated: {report_path}")
        return

    summary = select_art_for_set(
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
        report_path = generate_selection_report()
        print(f"\nReport: {report_path}")


if __name__ == "__main__":
    main()
