"""Test the production call sequence: theme extraction -> constraints.

Approximates the production failure condition where a big theme extraction
(long input, long output) is immediately followed by a constraints call on
the same Ollama model. Tests whether prior-state carryover contributes to
the "precious" loop.

By default uses the real pipeline prompts (theme_extraction.txt, constraints_system.txt)
and a substantial input document.

Usage:
  python -m scripts.test_sequence --model vlad-gemma4-26b-dynamic
  python -m scripts.test_sequence --model vlad-gemma4-26b-dynamic --skip-precursor  # constraints only
  python -m scripts.test_sequence --model vlad-gemma4-26b-dynamic --precursor-input path/to/bigdoc.txt
  python -m scripts.test_sequence --trials 10  # batch runs
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
DEFAULT_PRECURSOR_INPUT = ROOT / "output/sets/DARKSUN/darksun_source.txt"
DEFAULT_CONSTRAINTS_INPUT = ROOT / "output/sets/DARKSUN/athas_theme.txt"
OUT_DIR = ROOT / "tmp/constraints_tests"
OLLAMA_URL = "http://localhost:11434"


def detect_repetition(text: str, min_repeats: int = 10) -> str | None:
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
    print_stream: bool = False,
) -> dict:
    """Fire one Ollama call. Returns dict with raw, meta, wall_s, exception."""
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
                    if print_stream:
                        print(delta, end="", flush=True)
                    tokens_since_check += 1
                    if tokens_since_check >= 10:
                        tokens_since_check = 0
                        tail = "".join(chunks)[-TAIL_BUDGET_CHARS:]
                        finding = detect_repetition(tail, min_repeats=LOOP_THRESHOLD)
                        if finding:
                            aborted_reason = f"Streaming loop detected: {finding}"
                            if print_stream:
                                print(f"\n[aborting: {aborted_reason}]", flush=True)
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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="vlad-gemma4-26b-dynamic")
    p.add_argument("--num-ctx", type=int, default=128000)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--num-predict", type=int, default=-1)
    p.add_argument("--repeat-penalty", type=float, default=None)
    p.add_argument("--trials", type=int, default=1, help="Number of sequential trials")
    p.add_argument("--skip-precursor", action="store_true",
                   help="Skip the theme-extraction call (isolates constraints)")
    p.add_argument("--precursor-input", type=Path, default=DEFAULT_PRECURSOR_INPUT,
                   help="Text fed to theme_extraction prompt (big doc to load cache)")
    p.add_argument("--constraints-input", type=Path, default=DEFAULT_CONSTRAINTS_INPUT,
                   help="Theme text fed to constraints prompt")
    p.add_argument("--run-name-prefix", default="sequence")
    args = p.parse_args()

    precursor_system = (PROMPTS_DIR / "theme_extraction.txt").read_text(encoding="utf-8")
    precursor_template = (PROMPTS_DIR / "theme_chunk_single.txt").read_text(encoding="utf-8")
    precursor_text = args.precursor_input.read_text(encoding="utf-8")
    precursor_user = precursor_template.replace("{text}", precursor_text)

    constraints_system = (PROMPTS_DIR / "constraints_system.txt").read_text(encoding="utf-8")
    constraints_text = args.constraints_input.read_text(encoding="utf-8")
    constraints_user = f"Setting:\n\n{constraints_text}"

    base_options: dict = {
        "num_ctx": args.num_ctx,
        "temperature": args.temperature,
        "num_predict": args.num_predict,
    }
    if args.repeat_penalty is not None:
        base_options["repeat_penalty"] = args.repeat_penalty

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    summary: list[dict] = []

    for trial in range(1, args.trials + 1):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        trial_tag = f"trial{trial}" if args.trials > 1 else "single"
        safe_model = args.model.replace("/", "_").replace(":", "_")
        name = f"{args.run_name_prefix}_{trial_tag}_{safe_model}_{stamp}"
        out_path = OUT_DIR / f"{name}.txt"

        print(f"\n=== Trial {trial}/{args.trials} ===")
        print(f"Model: {args.model}  num_ctx={args.num_ctx}  options={json.dumps(base_options)}")
        print(f"Skip precursor: {args.skip_precursor}")
        print(f"Output: {out_path}")
        sys.stdout.flush()

        precursor_result: dict | None = None
        if not args.skip_precursor:
            print("\n[1/2] Precursor theme extraction...")
            sys.stdout.flush()
            precursor_result = run_call(
                "theme_extraction_precursor",
                args.model,
                precursor_system,
                precursor_user,
                dict(base_options),
                json_mode=False,  # theme extraction doesn't use JSON mode
                print_stream=False,
            )
            print(f"  wall={precursor_result['wall_s']:.1f}s  chars={len(precursor_result['raw'])}  meta={json.dumps(precursor_result['meta'])}")
            if precursor_result["exception"]:
                print(f"  EXCEPTION: {precursor_result['exception'].splitlines()[-1]}")

        print("\n[2/2] Constraints extraction...")
        sys.stdout.flush()
        constraints_result = run_call(
            "constraints_extraction",
            args.model,
            constraints_system,
            constraints_user,
            dict(base_options),
            json_mode=True,
            print_stream=False,
        )

        raw = constraints_result["raw"]
        loop = detect_repetition(raw)
        parse_status: str
        try:
            parsed = json.loads(raw)
            n = len(parsed.get("constraints", []))
            parse_status = f"OK - {n} constraints"
            parsed_summary = json.dumps(parsed, indent=2, ensure_ascii=False)
        except json.JSONDecodeError as e:
            parse_status = f"FAIL - {e.msg} at pos {e.pos}"
            parsed_summary = ""

        print(f"  wall={constraints_result['wall_s']:.1f}s  chars={len(raw)}  parse={parse_status}  loop={'YES' if loop else 'no'}")
        if loop:
            print(f"  LOOP: {loop}")

        # Write log file
        lines: list[str] = [
            "# Sequence test run",
            "",
            "## Parameters",
            "",
            f"- timestamp: {stamp}",
            f"- trial: {trial}/{args.trials}",
            f"- model: {args.model}",
            f"- options: {json.dumps(base_options)}",
            f"- num_ctx: {args.num_ctx}",
            f"- skip_precursor: {args.skip_precursor}",
            f"- precursor_input: {args.precursor_input if not args.skip_precursor else 'N/A'}",
            f"- constraints_input: {args.constraints_input}",
            "",
            "## Analysis",
            "",
            f"- constraints_parse: {parse_status}",
            f"- constraints_loop: {loop or 'not detected'}",
            "",
        ]

        if precursor_result is not None:
            lines += [
                "## Precursor (theme extraction)",
                "",
                f"- wall_s: {precursor_result['wall_s']:.2f}",
                f"- http_status: {precursor_result['http_status']}",
                f"- output_chars: {len(precursor_result['raw'])}",
                f"- meta: {json.dumps(precursor_result['meta'])}",
                f"- exception: {'yes (see below)' if precursor_result['exception'] else 'none'}",
                "",
                "### Raw response",
                "",
                "```",
                precursor_result["raw"] if precursor_result["raw"] else "(empty)",
                "```",
                "",
            ]
            if precursor_result["exception"]:
                lines += ["### Exception", "", "```", precursor_result["exception"].rstrip(), "```", ""]

        lines += [
            "## Constraints call",
            "",
            f"- wall_s: {constraints_result['wall_s']:.2f}",
            f"- http_status: {constraints_result['http_status']}",
            f"- output_chars: {len(raw)}",
            f"- meta: {json.dumps(constraints_result['meta'])}",
            f"- exception: {'yes (see below)' if constraints_result['exception'] else 'none'}",
            "",
            "### Raw response",
            "",
            "```",
            raw if raw else "(empty)",
            "```",
            "",
        ]
        if parsed_summary:
            lines += ["### Parsed JSON", "", "```json", parsed_summary, "```", ""]
        if constraints_result["exception"]:
            lines += ["### Exception", "", "```", constraints_result["exception"].rstrip(), "```", ""]

        out_path.write_text("\n".join(lines), encoding="utf-8")

        summary.append({
            "trial": trial,
            "precursor_wall_s": precursor_result["wall_s"] if precursor_result else None,
            "precursor_chars": len(precursor_result["raw"]) if precursor_result else None,
            "constraints_wall_s": constraints_result["wall_s"],
            "constraints_chars": len(raw),
            "parse_status": parse_status,
            "loop": bool(loop),
            "file": str(out_path),
        })

    # Final summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    n_loop = sum(1 for s in summary if s["loop"])
    n_fail = sum(1 for s in summary if "FAIL" in s["parse_status"])
    print(f"Trials: {len(summary)}")
    print(f"Loops detected: {n_loop}")
    print(f"Parse failures: {n_fail}")
    for s in summary:
        print(f"  trial {s['trial']}: constraints_wall={s['constraints_wall_s']:.1f}s  parse={s['parse_status']}  loop={'YES' if s['loop'] else 'no'}")
    return 1 if (n_loop > 0 or n_fail > 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
