"""Mirror the real app flow: theme extraction -> constraints -> card suggestions.

Tests whether sequential separate /api/chat calls against the same Ollama
instance degrade reliably after a long prior call (KV-cache leak hypothesis
from production reports).

Each trial runs three independent /api/chat calls in order (matching
`extract_constraints` / `stream_theme_extraction` in `theme_extractor.py`):
  1. Theme extraction     (source doc -> theme prose)      system=theme_extraction.txt
  2. Constraints (JSON)   (theme -> {"constraints": [...]}) system=constraints_system.txt
  3. Card suggestions     (theme -> {"card_suggestions": [...]}) system=card_suggestions_system.txt

Usage:
  python -m scripts.test_long_context --trials 3
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path("C:/Programming/MTGAI")
PROMPTS_DIR = ROOT / "backend/mtgai/pipeline/prompts"
DEFAULT_SOURCE = ROOT / "output/sets/DARKSUN/darksun_source.txt"
DEFAULT_THEME = ROOT / "output/sets/DARKSUN/athas_theme.txt"
OUT_DIR = ROOT / "tmp/constraints_tests"
OLLAMA_URL = "http://localhost:11434"


def detect_repetition(text: str, min_repeats: int = 15) -> str | None:
    if not text:
        return None
    tail = text[-4000:]
    words = tail.split()
    if len(words) < min_repeats:
        return None
    last = words[-1].strip(".,;:!?\"'")
    if not last:
        return None
    streak = 0
    for w in reversed(words):
        if w.strip(".,;:!?\"'") == last:
            streak += 1
        else:
            break
    if streak >= min_repeats:
        return f"Token '{last}' repeated {streak} times in a row at end of output"
    return None


def run_call(
    label: str,
    model: str,
    system_prompt: str,
    user_msg: str,
    options: dict,
    json_mode: bool,
) -> dict:
    body: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "options": options,
        "stream": True,
    }
    if json_mode:
        body["format"] = "json"

    chunks: list[str] = []
    meta: dict = {}
    exc_text: str | None = None
    aborted_reason: str | None = None
    http_status: int | None = None
    start = time.perf_counter()

    LOOP_THRESHOLD = 25
    TAIL_BUDGET_CHARS = 500
    tokens_since_check = 0

    try:
        with requests.post(
            f"{OLLAMA_URL}/api/chat",
            json=body,
            stream=True,
            timeout=1800,
        ) as resp:
            http_status = resp.status_code
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    evt = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                if "error" in evt:
                    exc_text = f"Ollama error event: {evt['error']}"
                    break
                delta = evt.get("message", {}).get("content", "")
                if delta:
                    chunks.append(delta)
                    tokens_since_check += 1
                    if tokens_since_check >= 10:
                        tokens_since_check = 0
                        tail = "".join(chunks)[-TAIL_BUDGET_CHARS:]
                        finding = detect_repetition(tail, min_repeats=LOOP_THRESHOLD)
                        if finding:
                            aborted_reason = f"Streaming loop detected: {finding}"
                            resp.close()
                            break
                if evt.get("done"):
                    meta = {k: evt.get(k) for k in (
                        "total_duration", "load_duration", "prompt_eval_count",
                        "prompt_eval_duration", "eval_count", "eval_duration",
                        "done_reason",
                    )}
                    break
    except Exception:
        exc_text = traceback.format_exc()

    return {
        "label": label,
        "raw": "".join(chunks),
        "meta": meta,
        "wall_s": time.perf_counter() - start,
        "http_status": http_status,
        "exception": exc_text,
        "aborted_reason": aborted_reason,
    }


def analyze_json_call(result: dict, json_key: str) -> tuple[str, str]:
    """Return (parse_status, parsed_summary)."""
    raw = result["raw"]
    try:
        parsed = json.loads(raw)
        items = parsed.get(json_key, [])
        if isinstance(items, list):
            return f"OK - {len(items)} {json_key}", json.dumps(parsed, indent=2, ensure_ascii=False)
        return f"FAIL - '{json_key}' not a list", ""
    except json.JSONDecodeError as e:
        return f"FAIL - {e.msg} at pos {e.pos}", ""


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="vlad-gemma4-26b-dynamic")
    p.add_argument("--num-ctx", type=int, default=128000)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--num-predict", type=int, default=-1)
    p.add_argument("--repeat-penalty", type=float, default=None)
    p.add_argument("--trials", type=int, default=3)
    p.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    p.add_argument("--theme", type=Path, default=DEFAULT_THEME,
                   help="Pre-extracted theme (fed to constraints + suggestions)")
    p.add_argument("--run-name-prefix", default="longctx")
    args = p.parse_args()

    theme_extraction_system = (PROMPTS_DIR / "theme_extraction.txt").read_text(encoding="utf-8")
    theme_extraction_user_tpl = (PROMPTS_DIR / "theme_chunk_single.txt").read_text(encoding="utf-8")
    constraints_system = (PROMPTS_DIR / "constraints_system.txt").read_text(encoding="utf-8")
    suggestions_system = (PROMPTS_DIR / "card_suggestions_system.txt").read_text(encoding="utf-8")

    source_text = args.source.read_text(encoding="utf-8")
    theme_text = args.theme.read_text(encoding="utf-8")

    theme_user = theme_extraction_user_tpl.replace("{text}", source_text)
    constraints_user = f"Setting:\n\n{theme_text}"
    suggestions_user = f"Setting:\n\n{theme_text}"

    base_options: dict = {
        "num_ctx": args.num_ctx,
        "temperature": args.temperature,
        "num_predict": args.num_predict,
    }
    if args.repeat_penalty is not None:
        base_options["repeat_penalty"] = args.repeat_penalty

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Model: {args.model}")
    print(f"Options: {json.dumps(base_options)}")
    print(f"Source: {args.source} ({len(source_text)} chars)")
    print(f"Theme:  {args.theme} ({len(theme_text)} chars)")
    print(f"Trials: {args.trials}")
    sys.stdout.flush()

    summary: list[dict] = []

    for trial in range(1, args.trials + 1):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_model = args.model.replace("/", "_").replace(":", "_")
        name = f"{args.run_name_prefix}_trial{trial}_{safe_model}_{stamp}"
        out_path = OUT_DIR / f"{name}.txt"

        print(f"\n=== Trial {trial}/{args.trials} ===")
        print(f"Output: {out_path}")
        sys.stdout.flush()

        # --- Call 1: theme extraction ---
        print("[1/3] Theme extraction...")
        sys.stdout.flush()
        theme_result = run_call(
            "theme_extraction",
            args.model,
            theme_extraction_system,
            theme_user,
            dict(base_options),
            json_mode=False,
        )
        theme_loop = detect_repetition(theme_result["raw"])
        print(f"  wall={theme_result['wall_s']:.1f}s  chars={len(theme_result['raw'])}  "
              f"loop={'YES' if theme_loop else 'no'}  meta={json.dumps(theme_result['meta'])}")
        if theme_loop:
            print(f"  LOOP: {theme_loop}")
        if theme_result["exception"]:
            print(f"  EXCEPTION: {theme_result['exception'].splitlines()[-1]}")

        # --- Call 2: constraints ---
        print("[2/3] Constraints extraction...")
        sys.stdout.flush()
        constraints_result = run_call(
            "constraints_extraction",
            args.model,
            constraints_system,
            constraints_user,
            dict(base_options),
            json_mode=True,
        )
        c_status, c_parsed = analyze_json_call(constraints_result, "constraints")
        c_loop = detect_repetition(constraints_result["raw"])
        print(f"  wall={constraints_result['wall_s']:.1f}s  chars={len(constraints_result['raw'])}  "
              f"parse={c_status}  loop={'YES' if c_loop else 'no'}")
        if c_loop:
            print(f"  LOOP: {c_loop}")

        # --- Call 3: card suggestions ---
        print("[3/3] Card suggestions extraction...")
        sys.stdout.flush()
        suggestions_result = run_call(
            "card_suggestions_extraction",
            args.model,
            suggestions_system,
            suggestions_user,
            dict(base_options),
            json_mode=True,
        )
        s_status, s_parsed = analyze_json_call(suggestions_result, "card_suggestions")
        s_loop = detect_repetition(suggestions_result["raw"])
        print(f"  wall={suggestions_result['wall_s']:.1f}s  chars={len(suggestions_result['raw'])}  "
              f"parse={s_status}  loop={'YES' if s_loop else 'no'}")
        if s_loop:
            print(f"  LOOP: {s_loop}")

        # --- Write log ---
        lines: list[str] = [
            "# Long-context sequence test (mirrors real app flow)",
            "",
            "## Parameters",
            "",
            f"- timestamp: {stamp}",
            f"- trial: {trial}/{args.trials}",
            f"- model: {args.model}",
            f"- options: {json.dumps(base_options)}",
            f"- num_ctx: {args.num_ctx}",
            f"- source: {args.source}",
            f"- theme: {args.theme}",
            "",
            "## Per-call summary",
            "",
            f"- theme: wall={theme_result['wall_s']:.1f}s  chars={len(theme_result['raw'])}  "
            f"loop={'YES' if theme_loop else 'no'}",
            f"- constraints: wall={constraints_result['wall_s']:.1f}s  "
            f"chars={len(constraints_result['raw'])}  parse={c_status}  "
            f"loop={'YES' if c_loop else 'no'}",
            f"- suggestions: wall={suggestions_result['wall_s']:.1f}s  "
            f"chars={len(suggestions_result['raw'])}  parse={s_status}  "
            f"loop={'YES' if s_loop else 'no'}",
            "",
        ]

        def _dump(section_title: str, result: dict, loop_reason: str | None,
                  parsed: str | None = None) -> list[str]:
            out = [
                f"## {section_title}",
                "",
                f"- wall_s: {result['wall_s']:.2f}",
                f"- http_status: {result['http_status']}",
                f"- output_chars: {len(result['raw'])}",
                f"- meta: {json.dumps(result['meta'])}",
                f"- exception: {'yes (see below)' if result['exception'] else 'none'}",
                f"- aborted_reason: {result['aborted_reason'] or 'none'}",
                f"- loop: {loop_reason or 'not detected'}",
                "",
                "### Raw response",
                "",
                "```",
                result["raw"] if result["raw"] else "(empty)",
                "```",
                "",
            ]
            if parsed:
                out += ["### Parsed JSON", "", "```json", parsed, "```", ""]
            if result["exception"]:
                out += ["### Exception", "", "```", result["exception"].rstrip(), "```", ""]
            return out

        lines += _dump("[1/3] Theme extraction", theme_result, theme_loop)
        lines += _dump("[2/3] Constraints", constraints_result, c_loop, c_parsed)
        lines += _dump("[3/3] Card suggestions", suggestions_result, s_loop, s_parsed)

        out_path.write_text("\n".join(lines), encoding="utf-8")

        summary.append({
            "trial": trial,
            "theme_wall": theme_result["wall_s"],
            "theme_chars": len(theme_result["raw"]),
            "theme_loop": bool(theme_loop),
            "constraints_wall": constraints_result["wall_s"],
            "constraints_chars": len(constraints_result["raw"]),
            "constraints_status": c_status,
            "constraints_loop": bool(c_loop),
            "suggestions_wall": suggestions_result["wall_s"],
            "suggestions_chars": len(suggestions_result["raw"]),
            "suggestions_status": s_status,
            "suggestions_loop": bool(s_loop),
            "file": str(out_path),
        })

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    n_loop = sum(1 for s in summary
                 if s["theme_loop"] or s["constraints_loop"] or s["suggestions_loop"])
    n_fail = sum(1 for s in summary
                 if "FAIL" in s["constraints_status"] or "FAIL" in s["suggestions_status"])
    print(f"Trials: {len(summary)}")
    print(f"Any-loop trials: {n_loop}")
    print(f"Parse-failure trials: {n_fail}")
    for s in summary:
        print(f"  trial {s['trial']}:")
        print(f"    theme:       wall={s['theme_wall']:.1f}s  chars={s['theme_chars']}  "
              f"loop={'YES' if s['theme_loop'] else 'no'}")
        print(f"    constraints: wall={s['constraints_wall']:.1f}s  chars={s['constraints_chars']}  "
              f"parse={s['constraints_status']}  loop={'YES' if s['constraints_loop'] else 'no'}")
        print(f"    suggestions: wall={s['suggestions_wall']:.1f}s  chars={s['suggestions_chars']}  "
              f"parse={s['suggestions_status']}  loop={'YES' if s['suggestions_loop'] else 'no'}")
    return 1 if (n_loop > 0 or n_fail > 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
