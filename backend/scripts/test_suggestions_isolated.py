"""Test card_suggestions extraction in isolation (no precursor calls).

If the failure rate drops vs. test_long_context.py, the failure is driven by
prior-call state (KV leak / accumulation). If it stays high, the failure is
driven by the prompt + grammar combination itself.

Usage:
  python -m scripts.test_suggestions_isolated --trials 6
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


def detect_phrase_repetition(text: str, max_phrase_len: int = 60, min_repeats: int = 6) -> str | None:
    """Detect repetition of multi-token phrases at the tail of the stream.

    Looks for any short suffix (1..max_phrase_len chars) that is repeated
    consecutively at the end of `text` at least `min_repeats` times.
    Catches non-trivial loops (whole-line, short-phrase, JSON-fragment cycles)
    that single-token detection misses.
    """
    if not text:
        return None
    n = len(text)
    for plen in range(2, max_phrase_len + 1):
        if plen * min_repeats > n:
            break
        phrase = text[n - plen:]
        ok = True
        for i in range(1, min_repeats):
            if text[n - plen * (i + 1):n - plen * i] != phrase:
                ok = False
                break
        if ok:
            display = phrase if len(phrase) <= 40 else phrase[:37] + "..."
            return f"Phrase {display!r} (len={plen}) repeated {min_repeats}+ times at end"
    return None


def run_call(
    model: str,
    system_prompt: str,
    user_msg: str,
    options: dict,
    stream_log_path: Path | None = None,
    max_call_seconds: float = 600.0,
) -> dict:
    body: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "options": options,
        "stream": True,
        "format": "json",
    }

    chunks: list[str] = []
    meta: dict = {}
    exc_text: str | None = None
    aborted_reason: str | None = None
    http_status: int | None = None
    start = time.perf_counter()

    LOOP_THRESHOLD = 25
    TAIL_BUDGET_CHARS = 1500
    tokens_since_check = 0
    last_progress = time.perf_counter()
    PROGRESS_INTERVAL_S = 15.0

    log_fp = open(stream_log_path, "w", encoding="utf-8") if stream_log_path else None

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
                    if log_fp:
                        log_fp.write(delta)
                        log_fp.flush()
                    tokens_since_check += 1
                    now = time.perf_counter()
                    elapsed = now - start
                    if elapsed > max_call_seconds:
                        aborted_reason = (
                            f"Wall-clock timeout: {elapsed:.0f}s > "
                            f"max_call_seconds={max_call_seconds:.0f}s "
                            f"(generated {len(chunks)} tokens)"
                        )
                        print(f"    [ABORT: {aborted_reason}]", flush=True)
                        resp.close()
                        break
                    if now - last_progress >= PROGRESS_INTERVAL_S:
                        last_progress = now
                        total_chars = sum(len(c) for c in chunks)
                        print(f"    [progress {elapsed:.0f}s tokens={len(chunks)} chars={total_chars}]",
                              flush=True)
                    if tokens_since_check >= 10:
                        tokens_since_check = 0
                        tail = "".join(chunks)[-TAIL_BUDGET_CHARS:]
                        finding = (detect_repetition(tail, min_repeats=LOOP_THRESHOLD)
                                   or detect_phrase_repetition(tail))
                        if finding:
                            aborted_reason = f"Streaming loop detected: {finding}"
                            print(f"    [ABORT: {aborted_reason}]", flush=True)
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
    finally:
        if log_fp:
            log_fp.close()

    return {
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
    p.add_argument("--trials", type=int, default=6)
    p.add_argument("--theme", type=Path, default=DEFAULT_THEME)
    p.add_argument("--run-name-prefix", default="suggonly")
    p.add_argument("--max-call-seconds", type=float, default=600.0,
                   help="Abort a single call after this wall-clock budget")
    args = p.parse_args()

    suggestions_system = (PROMPTS_DIR / "card_suggestions_system.txt").read_text(encoding="utf-8")
    theme_text = args.theme.read_text(encoding="utf-8")
    user_msg = f"Setting:\n\n{theme_text}"

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
        sys.stdout.flush()

        stream_path = OUT_DIR / f"{name}.stream.txt"
        result = run_call(args.model, suggestions_system, user_msg, dict(base_options),
                          stream_log_path=stream_path,
                          max_call_seconds=args.max_call_seconds)
        raw = result["raw"]
        loop = detect_repetition(raw)
        try:
            parsed = json.loads(raw)
            items = parsed.get("card_suggestions", [])
            if isinstance(items, list):
                parse_status = f"OK - {len(items)} card_suggestions"
                parsed_summary = json.dumps(parsed, indent=2, ensure_ascii=False)
            else:
                parse_status = "FAIL - 'card_suggestions' not a list"
                parsed_summary = ""
        except json.JSONDecodeError as e:
            parse_status = f"FAIL - {e.msg} at pos {e.pos}"
            parsed_summary = ""

        print(f"  wall={result['wall_s']:.1f}s  chars={len(raw)}  parse={parse_status}  "
              f"loop={'YES' if loop else 'no'}  meta={json.dumps(result['meta'])}")
        if loop:
            print(f"  LOOP: {loop}")
        if result["aborted_reason"]:
            print(f"  ABORTED: {result['aborted_reason']}")
        if result["exception"]:
            print(f"  EXCEPTION: {result['exception'].splitlines()[-1]}")

        lines: list[str] = [
            "# Card-suggestions isolation test",
            "",
            "## Parameters",
            "",
            f"- timestamp: {stamp}",
            f"- trial: {trial}/{args.trials}",
            f"- model: {args.model}",
            f"- options: {json.dumps(base_options)}",
            f"- num_ctx: {args.num_ctx}",
            f"- theme: {args.theme}",
            "",
            "## Result",
            "",
            f"- wall_s: {result['wall_s']:.2f}",
            f"- http_status: {result['http_status']}",
            f"- output_chars: {len(raw)}",
            f"- parse: {parse_status}",
            f"- loop: {loop or 'not detected'}",
            f"- aborted_reason: {result['aborted_reason'] or 'none'}",
            f"- meta: {json.dumps(result['meta'])}",
            f"- exception: {'yes (see below)' if result['exception'] else 'none'}",
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
        if result["exception"]:
            lines += ["### Exception", "", "```", result["exception"].rstrip(), "```", ""]

        out_path.write_text("\n".join(lines), encoding="utf-8")

        summary.append({
            "trial": trial,
            "wall_s": result["wall_s"],
            "chars": len(raw),
            "parse_status": parse_status,
            "loop": bool(loop),
            "meta": result["meta"],
        })

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    n_loop = sum(1 for s in summary if s["loop"])
    n_fail = sum(1 for s in summary if "FAIL" in s["parse_status"])
    print(f"Trials: {len(summary)}")
    print(f"Loops detected: {n_loop}")
    print(f"Parse failures: {n_fail}")
    for s in summary:
        prompt_eval = s["meta"].get("prompt_eval_count", "?") if s["meta"] else "?"
        print(f"  trial {s['trial']}: wall={s['wall_s']:.1f}s  chars={s['chars']}  "
              f"prompt_tokens={prompt_eval}  parse={s['parse_status']}  "
              f"loop={'YES' if s['loop'] else 'no'}")
    return 1 if (n_loop > 0 or n_fail > 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
