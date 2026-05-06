"""Benchmark Gemma 4 models on theme extraction.

Runs the same theme extraction task on each Gemma 4 model variant,
measuring wall-clock time, token throughput, and saving outputs for
human quality comparison.

Usage:
    python -m scripts.benchmark_gemma4 [--models gemma4:e4b gemma4:26b]
    python -m scripts.benchmark_gemma4 --skip-warmup
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import requests

OLLAMA_URL = "http://localhost:11434"
RESULTS_DIR = Path("C:/Programming/MTGAI/output/benchmarks")

# Models to benchmark (registry key -> ollama model_id)
MODELS = {
    "gemma4-e4b": "gemma4:e4b",
    "gemma4-26b-vram": "VladimirGav/gemma4-26b-16GB-VRAM",
    "gemma4-26b": "gemma4:26b",
    "gemma4-31b": "gemma4:31b",
}

# Source document
THEME_FILE = Path("C:/Programming/MTGAI/output/sets/ASD/theme.txt")
PROMPTS_DIR = Path("C:/Programming/MTGAI/backend/mtgai/pipeline/prompts")


def load_prompts() -> tuple[str, str]:
    """Load system prompt and build user prompt from theme.txt."""
    system_prompt = (PROMPTS_DIR / "theme_extraction.txt").read_text(encoding="utf-8")
    template = (PROMPTS_DIR / "theme_chunk_single.txt").read_text(encoding="utf-8")
    source_text = THEME_FILE.read_text(encoding="utf-8")
    user_prompt = template.format(text=source_text)
    return system_prompt, user_prompt


def check_ollama() -> bool:
    """Verify Ollama is running."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return resp.status_code == 200
    except requests.ConnectionError:
        return False


def unload_all_models():
    """Unload any currently loaded models to get clean VRAM state."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/ps", timeout=5)
        if resp.status_code == 200:
            loaded = resp.json().get("models", [])
            for m in loaded:
                name = m.get("name", "")
                if name:
                    print(f"  Unloading {name}...")
                    requests.post(
                        f"{OLLAMA_URL}/api/generate",
                        json={"model": name, "keep_alive": 0},
                        timeout=30,
                    )
    except Exception as e:
        print(f"  Warning: could not unload models: {e}")


def warmup_model(model_id: str):
    """Send a tiny prompt to warm up the model (load weights into VRAM)."""
    print(f"  Warming up {model_id}...")
    start = time.perf_counter()
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": "Say hello."}],
                "options": {"num_ctx": 2048, "num_predict": 16},
                "stream": False,
            },
            timeout=300,
        )
        resp.raise_for_status()
        elapsed = time.perf_counter() - start
        print(f"  Warmup done in {elapsed:.1f}s")
    except Exception as e:
        print(f"  Warmup failed: {e}")
        raise


def run_benchmark(
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    num_ctx: int = 32768,
) -> dict:
    """Run theme extraction on a single model, streaming response.

    Returns dict with timing, token counts, and output text.
    """
    body = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "options": {
            "num_ctx": num_ctx,
            "temperature": 0.7,
            "num_predict": -1,
        },
        "stream": True,
    }

    output_text = ""
    first_token_time = None
    token_count = 0
    total_duration_ns = 0
    eval_count = 0
    eval_duration_ns = 0
    prompt_eval_count = 0
    prompt_eval_duration_ns = 0

    start = time.perf_counter()

    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json=body,
        stream=True,
        timeout=600,
    )
    resp.raise_for_status()

    for line in resp.iter_lines():
        if not line:
            continue
        data = json.loads(line)

        if data.get("done"):
            # Final message has timing stats
            total_duration_ns = data.get("total_duration", 0)
            eval_count = data.get("eval_count", 0)
            eval_duration_ns = data.get("eval_duration", 0)
            prompt_eval_count = data.get("prompt_eval_count", 0)
            prompt_eval_duration_ns = data.get("prompt_eval_duration", 0)
            break

        content = data.get("message", {}).get("content", "")
        if content:
            if first_token_time is None:
                first_token_time = time.perf_counter()
            output_text += content
            token_count += 1  # approximate (streaming chunks != tokens)

    end = time.perf_counter()
    wall_clock = end - start
    ttft = (first_token_time - start) if first_token_time else wall_clock

    # Ollama provides precise eval stats
    eval_tok_per_sec = (
        (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns > 0 else 0
    )
    prompt_tok_per_sec = (
        (prompt_eval_count / (prompt_eval_duration_ns / 1e9))
        if prompt_eval_duration_ns > 0
        else 0
    )

    return {
        "model_id": model_id,
        "wall_clock_s": round(wall_clock, 2),
        "ttft_s": round(ttft, 2),
        "output_chars": len(output_text),
        "eval_count": eval_count,
        "eval_duration_s": round(eval_duration_ns / 1e9, 2),
        "eval_tok_per_sec": round(eval_tok_per_sec, 1),
        "prompt_eval_count": prompt_eval_count,
        "prompt_eval_duration_s": round(prompt_eval_duration_ns / 1e9, 2),
        "prompt_tok_per_sec": round(prompt_tok_per_sec, 1),
        "total_duration_s": round(total_duration_ns / 1e9, 2),
        "output_text": output_text,
    }


def print_summary(results: list[dict]):
    """Print a comparison table."""
    print("\n" + "=" * 90)
    print("BENCHMARK RESULTS")
    print("=" * 90)
    print(
        f"{'Model':<42} {'Wall(s)':>8} {'TTFT(s)':>8} "
        f"{'OutTok':>7} {'Gen t/s':>8} {'Prompt t/s':>10} {'Chars':>7}"
    )
    print("-" * 90)
    for r in results:
        print(
            f"{r['model_id']:<42} {r['wall_clock_s']:>8.1f} {r['ttft_s']:>8.1f} "
            f"{r['eval_count']:>7} {r['eval_tok_per_sec']:>8.1f} "
            f"{r['prompt_tok_per_sec']:>10.1f} {r['output_chars']:>7}"
        )
    print("=" * 90)


def main():
    parser = argparse.ArgumentParser(description="Benchmark Gemma 4 models")
    parser.add_argument(
        "--models",
        nargs="+",
        help="Ollama model IDs to test (default: all 4 Gemma 4 variants)",
    )
    parser.add_argument(
        "--skip-warmup",
        action="store_true",
        help="Skip model warmup (use if model is already loaded)",
    )
    parser.add_argument(
        "--num-ctx",
        type=int,
        default=32768,
        help="Context window size (default: 32768 - enough for theme.txt)",
    )
    args = parser.parse_args()

    if not check_ollama():
        print("ERROR: Ollama is not running. Start it first.")
        return

    system_prompt, user_prompt = load_prompts()
    print(f"Source document: {THEME_FILE}")
    print(f"Source chars: {len(THEME_FILE.read_text(encoding='utf-8'))}")
    print(f"System prompt: {len(system_prompt)} chars")
    print(f"User prompt: {len(user_prompt)} chars")
    print(f"Context window: {args.num_ctx}")

    # Select models
    if args.models:
        models_to_test = {k: v for k, v in MODELS.items() if v in args.models}
        if not models_to_test:
            # Maybe they passed registry keys
            models_to_test = {k: v for k, v in MODELS.items() if k in args.models}
        if not models_to_test:
            print(f"No matching models found. Available: {list(MODELS.values())}")
            return
    else:
        models_to_test = MODELS

    print(f"\nModels to benchmark: {list(models_to_test.values())}")

    # Prepare output directory
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_DIR / f"gemma4_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    results = []

    for key, model_id in models_to_test.items():
        print(f"\n{'='*60}")
        print(f"BENCHMARKING: {model_id} (key: {key})")
        print(f"{'='*60}")

        # Unload previous model to get clean VRAM
        unload_all_models()
        time.sleep(2)

        if not args.skip_warmup:
            try:
                warmup_model(model_id)
            except Exception:
                print(f"  SKIPPING {model_id} - failed to load")
                continue

        print("  Running theme extraction...")
        try:
            result = run_benchmark(model_id, system_prompt, user_prompt, args.num_ctx)
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append({
                "model_id": model_id,
                "error": str(e),
            })
            continue

        results.append(result)

        # Print per-model summary
        print(f"  Wall clock: {result['wall_clock_s']}s")
        print(f"  Time to first token: {result['ttft_s']}s")
        print(f"  Output tokens: {result['eval_count']}")
        print(f"  Generation speed: {result['eval_tok_per_sec']} tok/s")
        print(f"  Prompt processing: {result['prompt_tok_per_sec']} tok/s")
        print(f"  Output length: {result['output_chars']} chars")

        # Save individual output
        safe_name = key.replace("/", "_").replace(":", "_")
        output_file = run_dir / f"{safe_name}_output.md"
        output_file.write_text(result["output_text"], encoding="utf-8")
        print(f"  Output saved: {output_file}")

    # Print comparison table
    print_summary([r for r in results if "error" not in r])

    # Save structured results (without full output text)
    summary = []
    for r in results:
        entry = {k: v for k, v in r.items() if k != "output_text"}
        summary.append(entry)

    summary_file = run_dir / "benchmark_results.json"
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nResults saved to: {run_dir}")
    print(f"JSON summary: {summary_file}")
    print("\nReview outputs for quality:")
    for key in models_to_test:
        safe_name = key.replace("/", "_").replace(":", "_")
        print(f"  {run_dir / f'{safe_name}_output.md'}")


if __name__ == "__main__":
    main()
