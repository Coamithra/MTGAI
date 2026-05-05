"""Phase C: raw llama-bench.exe sanity for all on-disk GGUFs.

Bypasses MTGAI / llmfacade entirely - shells out to ``llama-bench.exe`` for
pp512 (prompt eval throughput) and tg128 (generation throughput) numbers.
The point is to spot regressions caused by llmfacade's wrapping overhead
vs. raw llama.cpp performance.

Default model list reflects the post-Ollama→llama.cpp migration registry
plus any blobs hard-linked from Ollama's cache (see scripts.link_ollama_blobs).
``llama-bench`` is single-pass-deterministic enough that we run each
combination once - if a row looks weird, rerun manually.

Usage:
    python -m scripts.benchmark_llama_bench
    python -m scripts.benchmark_llama_bench --models C:/Models/qwen2.5-3b.gguf
    python -m scripts.benchmark_llama_bench --ngl 35       # custom GPU layer cap
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

LLAMA_BENCH = Path("C:/Tools/llama.cpp/llama-bench.exe")
RESULTS_DIR = Path("C:/Programming/MTGAI/output/benchmarks")

# Curated default list - small, fast models first so failures show early.
DEFAULT_GGUFS: list[Path] = [
    Path("C:/Models/llama3.2-3b.gguf"),
    Path("C:/Models/qwen2.5-3b.gguf"),
    Path("C:/Models/phi4-mini.gguf"),
    Path("C:/Models/qwen3.5-4b.gguf"),
    Path("C:/Models/qwen2.5-14b.gguf"),
    Path("C:/Models/vlad-gemma4-26b-dynamic.gguf"),
]


def run_one(gguf: Path, ngl: int, pp: int, tg: int, timeout_s: int) -> dict:
    """Run llama-bench against one GGUF and return parsed JSON."""
    if not gguf.is_file():
        return {"gguf": str(gguf), "error": "file not found"}

    cmd = [
        str(LLAMA_BENCH),
        "-m", str(gguf),
        "-p", str(pp),
        "-n", str(tg),
        "-ngl", str(ngl),
        "-o", "json",
    ]
    print(f"  $ {' '.join(cmd)}")
    start = time.perf_counter()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return {"gguf": str(gguf), "error": f"timeout after {timeout_s}s"}
    elapsed = time.perf_counter() - start

    if proc.returncode != 0:
        return {
            "gguf": str(gguf),
            "error": f"rc={proc.returncode}",
            "stderr_tail": proc.stderr[-500:],
            "wall_s": round(elapsed, 1),
        }

    try:
        rows = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "gguf": str(gguf),
            "error": "json parse failed",
            "stdout_tail": proc.stdout[-500:],
            "wall_s": round(elapsed, 1),
        }

    return {
        "gguf": str(gguf),
        "wall_s": round(elapsed, 1),
        "rows": rows,
    }


def fmt_summary(results: list[dict]) -> None:
    print("\n" + "=" * 100)
    print("Phase C — llama-bench.exe raw tok/s")
    print("=" * 100)
    print(f"{'Model':<40} {'pp512 tok/s':>14} {'tg128 tok/s':>14} {'Wall(s)':>8}")
    print("-" * 100)
    for r in results:
        name = Path(r["gguf"]).stem
        if "error" in r:
            print(f"{name:<40}  ERROR: {r['error']}")
            continue
        # Each row has avg_ts (avg tokens/sec) and n_prompt / n_gen tags.
        pp = next((row for row in r["rows"] if row.get("n_prompt", 0) > 0), {})
        tg = next((row for row in r["rows"] if row.get("n_gen", 0) > 0), {})
        pp_ts = pp.get("avg_ts", 0)
        tg_ts = tg.get("avg_ts", 0)
        print(
            f"{name:<40} {pp_ts:>14.1f} {tg_ts:>14.1f} {r['wall_s']:>8.1f}"
        )
    print("=" * 100)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--models",
        nargs="+",
        help="GGUF paths to test (default: curated list of on-disk models)",
    )
    parser.add_argument(
        "--ngl",
        type=int,
        default=999,
        help="-ngl flag for llama-bench (default: 999 = all GPU layers)",
    )
    parser.add_argument("--pp", type=int, default=512, help="Prompt eval token count")
    parser.add_argument("--tg", type=int, default=128, help="Generation token count")
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Per-model timeout in seconds (default: 600)",
    )
    parser.add_argument(
        "--tag", default="phase-c-raw", help="Result-dir tag"
    )
    args = parser.parse_args()

    if not LLAMA_BENCH.is_file():
        print(f"ERROR: llama-bench.exe not found at {LLAMA_BENCH}")
        return

    ggufs = [Path(p) for p in args.models] if args.models else DEFAULT_GGUFS
    print(f"Phase C: {len(ggufs)} model(s), -ngl={args.ngl}, pp={args.pp}, tg={args.tg}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_DIR / f"phase_c_{args.tag}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for gguf in ggufs:
        print(f"\n{Path(gguf).stem}")
        r = run_one(gguf, args.ngl, args.pp, args.tg, args.timeout)
        results.append(r)
        # Persist running summary
        (run_dir / "results.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )

    fmt_summary(results)
    print(f"\nResults: {run_dir}")


if __name__ == "__main__":
    main()
