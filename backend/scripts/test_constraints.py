"""Quick-and-dirty harness for reproducing and debugging constraints-extraction loops.

Feeds a saved theme text into the constraints_system.txt prompt and hits
Ollama directly with whatever sampling params you want. Streams to stdout so
you can watch a loop form in real time. A full transcript (params, prompts,
streamed response, exceptions, parse result, repetition check) lands in
tmp/constraints_tests/ - written even on crash.

Usage:
  python -m scripts.test_constraints --model vlad-gemma4-26b-dynamic
  python -m scripts.test_constraints --model vlad-gemma4-26b-dynamic --repeat-penalty 1.2
  python -m scripts.test_constraints --model unsloth-gemma4-26b-q4kxl --no-json-mode
  python -m scripts.test_constraints --theme-file path/to/theme.txt --seed 42
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
DEFAULT_THEME = ROOT / "output/sets/DARKSUN/athas_theme.txt"
CONSTRAINTS_PROMPT = ROOT / "backend/mtgai/pipeline/prompts/constraints_system.txt"
OUT_DIR = ROOT / "tmp/constraints_tests"
OLLAMA_URL = "http://localhost:11434"


def detect_repetition(text: str, min_repeats: int = 10) -> str | None:
    """Return a short description if the output tail is a repeated-token loop."""
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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--theme-file", type=Path, default=DEFAULT_THEME)
    p.add_argument("--model", default="vlad-gemma4-26b-dynamic",
                   help="Ollama model_id (not registry key)")
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--repeat-penalty", type=float, default=None,
                   help="Ollama repeat_penalty; omit for Ollama default (1.1)")
    p.add_argument("--repeat-last-n", type=int, default=None,
                   help="Ollama repeat_last_n (tokens considered for penalty)")
    p.add_argument("--num-predict", type=int, default=-1,
                   help="Max output tokens; -1 = unlimited (matches pipeline default)")
    p.add_argument("--num-ctx", type=int, default=32768)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--top-p", type=float, default=None)
    p.add_argument("--top-k", type=int, default=None)
    p.add_argument("--min-p", type=float, default=None)
    p.add_argument("--no-json-mode", action="store_true",
                   help="Disable Ollama format=json (matches pipeline behavior when off)")
    p.add_argument("--run-name", default=None,
                   help="Override output filename; default is timestamp+model")
    p.add_argument("--prompt-file", type=Path, default=CONSTRAINTS_PROMPT,
                   help="System prompt file (default: constraints_system.txt)")
    p.add_argument("--truncate-user-prompt", type=int, default=0,
                   help="Truncate user-prompt section in the log file (0 = full)")
    args = p.parse_args()

    theme_text = args.theme_file.read_text(encoding="utf-8")
    system_prompt = args.prompt_file.read_text(encoding="utf-8")
    user_msg = f"Setting:\n\n{theme_text}"

    options: dict = {
        "num_ctx": args.num_ctx,
        "temperature": args.temperature,
        "num_predict": args.num_predict,
    }
    for key, val in [
        ("repeat_penalty", args.repeat_penalty),
        ("repeat_last_n", args.repeat_last_n),
        ("seed", args.seed),
        ("top_p", args.top_p),
        ("top_k", args.top_k),
        ("min_p", args.min_p),
    ]:
        if val is not None:
            options[key] = val

    body: dict = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "options": options,
        "stream": True,
    }
    if not args.no_json_mode:
        body["format"] = "json"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_model = args.model.replace("/", "_").replace(":", "_")
    name = args.run_name or f"{stamp}_{safe_model}"
    out_path = OUT_DIR / f"{name}.txt"

    print(f"Model: {args.model}")
    print(f"Options: {json.dumps(options)}")
    print(f"JSON mode: {not args.no_json_mode}")
    print(f"Prompt: {args.prompt_file.name} ({len(system_prompt)} chars)")
    print(f"Theme:  {args.theme_file} ({len(theme_text)} chars)")
    print(f"Output: {out_path}\n---")
    sys.stdout.flush()

    chunks: list[str] = []
    final_meta: dict = {}
    exception_text: str | None = None
    http_status: int | None = None
    aborted_reason: str | None = None
    start = time.perf_counter()

    # Streaming loop detection: track the last N tokens of tail text.
    # If the tail collapses to a single repeated word for >= LOOP_THRESHOLD
    # occurrences, abort the HTTP stream early.
    LOOP_THRESHOLD = 25
    TAIL_BUDGET_CHARS = 500
    tokens_since_check: int = 0

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
                    exception_text = f"Ollama error event: {evt['error']}"
                    break
                delta = evt.get("message", {}).get("content", "")
                if delta:
                    chunks.append(delta)
                    print(delta, end="", flush=True)
                    tokens_since_check += 1
                    if tokens_since_check >= 10:
                        tokens_since_check = 0
                        tail = "".join(chunks)[-TAIL_BUDGET_CHARS:]
                        finding = detect_repetition(tail, min_repeats=LOOP_THRESHOLD)
                        if finding:
                            aborted_reason = f"Streaming loop detected: {finding}"
                            print(f"\n[aborting: {aborted_reason}]", flush=True)
                            resp.close()
                            break
                if evt.get("done"):
                    final_meta = {k: evt.get(k) for k in (
                        "total_duration", "load_duration", "prompt_eval_count",
                        "prompt_eval_duration", "eval_count", "eval_duration",
                        "done_reason",
                    )}
                    break
    except KeyboardInterrupt:
        exception_text = "KeyboardInterrupt (user cancelled)"
        print("\n[interrupted by user]")
    except Exception:
        exception_text = traceback.format_exc()
        print("\n[exception - see log file]")

    elapsed = time.perf_counter() - start
    full_output = "".join(chunks)

    # --- Post-run analysis ---
    loop_finding = detect_repetition(full_output)
    parse_status: str
    parsed_summary: str = ""
    if args.no_json_mode:
        parse_status = "skipped (JSON mode off)"
    else:
        try:
            parsed = json.loads(full_output)
            constraints = parsed.get("constraints", [])
            parse_status = f"OK - {len(constraints)} constraints"
            parsed_summary = json.dumps(parsed, indent=2, ensure_ascii=False)
        except json.JSONDecodeError as e:
            parse_status = f"FAIL - {e.msg} at line {e.lineno} col {e.colno} (pos {e.pos})"

    # --- Write full transcript ---
    user_prompt_for_log = user_msg
    if args.truncate_user_prompt and len(user_msg) > args.truncate_user_prompt:
        user_prompt_for_log = (
            user_msg[: args.truncate_user_prompt]
            + f"\n\n...[truncated {len(user_msg) - args.truncate_user_prompt} chars]"
        )

    sections: list[str] = [
        "# Constraints extraction test run",
        "",
        "## Parameters",
        "",
        f"- timestamp: {stamp}",
        f"- model: {args.model}",
        f"- prompt_file: {args.prompt_file}",
        f"- theme_file: {args.theme_file}",
        f"- theme_chars: {len(theme_text)}",
        f"- system_prompt_chars: {len(system_prompt)}",
        f"- user_prompt_chars: {len(user_msg)}",
        f"- json_mode: {not args.no_json_mode}",
        f"- options: {json.dumps(options)}",
        f"- http_status: {http_status}",
        f"- wall_time_s: {elapsed:.2f}",
        f"- output_chars: {len(full_output)}",
        f"- done_reason: {final_meta.get('done_reason')}",
        f"- ollama_meta: {json.dumps(final_meta)}",
        "",
        "## Analysis",
        "",
        f"- parse_result: {parse_status}",
        f"- repetition_loop: {loop_finding or 'not detected'}",
        f"- aborted_reason: {aborted_reason or 'none'}",
        f"- exception: {'yes (see section)' if exception_text else 'none'}",
        "",
        "## System prompt",
        "",
        "```",
        system_prompt.rstrip(),
        "```",
        "",
        "## User prompt",
        "",
        "```",
        user_prompt_for_log.rstrip(),
        "```",
        "",
        "## Raw response",
        "",
        "```",
        full_output if full_output else "(empty)",
        "```",
        "",
    ]
    if parsed_summary:
        sections += [
            "## Parsed JSON",
            "",
            "```json",
            parsed_summary,
            "```",
            "",
        ]
    if exception_text:
        sections += [
            "## Exception",
            "",
            "```",
            exception_text.rstrip(),
            "```",
            "",
        ]

    out_path.write_text("\n".join(sections), encoding="utf-8")

    print(f"\n---\nWall time: {elapsed:.2f}s")
    if final_meta:
        print(f"Meta: {json.dumps(final_meta)}")
    print(f"Parse: {parse_status}")
    if loop_finding:
        print(f"Loop:  {loop_finding}")
    if aborted_reason:
        print(f"Aborted: {aborted_reason}")
    if exception_text:
        print(f"Exception: {exception_text.splitlines()[-1] if exception_text else ''}")
    print(f"Saved: {out_path}")
    ok = exception_text is None and "FAIL" not in parse_status and aborted_reason is None
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
