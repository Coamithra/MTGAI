"""Benchmark Gemma 4 models on full theme extraction pipeline.

Uses the real stream_theme_extraction() function (same code the
/pipeline/theme UI calls) with the Dark Sun Campaign Setting PDF.

Measures:
- Model load time (separately - not counted in extraction metrics)
- Time to first token (TTFT) of actual extraction
- Total extraction wall clock
- Tokens/sec from Ollama's own timing stats
- Output character count for quality comparison

Usage:
    python -m scripts.benchmark_gemma4_darksun
    python -m scripts.benchmark_gemma4_darksun --models gemma4-e4b gemma4-26b
    python -m scripts.benchmark_gemma4_darksun --include-31b
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import requests

from mtgai.pipeline.theme_extractor import extract_file_content, stream_theme_extraction
from mtgai.settings.model_registry import get_registry

OLLAMA_URL = "http://localhost:11434"
PDF_PATH = Path(
    "C:/Programming/MTGAI/Inspiration/"
    "The Dark Sun Campaign Setting for Worlds Without Number.pdf"
)
RESULTS_DIR = Path("C:/Programming/MTGAI/output/benchmarks")

# Registry keys for models to benchmark
DEFAULT_MODELS = [
    "gemma4-e4b",
    "gemma4-26b-vram",
    "gemma4-26b",
]
SLOW_MODELS = ["gemma4-31b"]


def check_ollama() -> bool:
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return resp.status_code == 200
    except requests.ConnectionError:
        return False


def unload_all_models():
    """Unload any currently loaded models."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/ps", timeout=5)
        if resp.status_code == 200:
            for m in resp.json().get("models", []):
                name = m.get("name", "")
                if name:
                    print(f"  Unloading {name}...")
                    requests.post(
                        f"{OLLAMA_URL}/api/generate",
                        json={"model": name, "keep_alive": 0},
                        timeout=30,
                    )
    except Exception as e:
        print(f"  Warning: unload failed: {e}")


def load_model(model_id: str) -> float:
    """Force-load model into VRAM by making a tiny request.

    Returns elapsed seconds. This time is reported SEPARATELY from
    extraction timing - we care about tokens/sec during actual work,
    not one-time load overhead.
    """
    print(f"  Loading {model_id} into VRAM...")
    start = time.perf_counter()
    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": model_id,
            "messages": [{"role": "user", "content": "hi"}],
            "options": {"num_ctx": 2048, "num_predict": 4},
            "stream": False,
        },
        timeout=600,
    )
    resp.raise_for_status()
    elapsed = time.perf_counter() - start
    print(f"  Load time: {elapsed:.1f}s")
    return elapsed


def check_gpu_placement(model_id: str) -> str:
    """Check how Ollama placed the model (GPU/CPU split)."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/ps", timeout=5)
        for m in resp.json().get("models", []):
            if m.get("name") == model_id or m.get("model") == model_id:
                size = m.get("size", 0)
                size_vram = m.get("size_vram", 0)
                if size > 0:
                    pct_gpu = round(size_vram / size * 100)
                    pct_cpu = 100 - pct_gpu
                    return f"{pct_gpu}% GPU / {pct_cpu}% CPU ({size_vram/1e9:.1f}/{size/1e9:.1f} GB)"
        return "unknown"
    except Exception:
        return "unknown"


def run_extraction(model_key: str, text: str) -> dict:
    """Run real theme extraction pipeline, measuring timing.

    Uses stream_theme_extraction() - same code the UI calls.
    """
    first_chunk_time = None
    total_output = ""
    section_times = []
    last_status_time = None
    status_events = []

    start = time.perf_counter()

    for event in stream_theme_extraction(text, model_key):
        etype = event["type"]
        now = time.perf_counter()

        if etype == "status":
            msg = event["message"]
            if last_status_time is not None:
                section_times.append({
                    "step": status_events[-1] if status_events else "start",
                    "duration_s": round(now - last_status_time, 2),
                })
            last_status_time = now
            status_events.append(msg)
            print(f"    [{now - start:.1f}s] {msg}")
        elif etype == "theme_chunk":
            if first_chunk_time is None:
                first_chunk_time = now
                print(f"    [{now - start:.1f}s] first output chunk")
            total_output += event["text"]
        elif etype == "complete":
            # Capture final text (may differ from streamed accumulator)
            final_text = event.get("theme_text", total_output)
            if final_text and len(final_text) > len(total_output):
                total_output = final_text
            print(f"    [{now - start:.1f}s] complete")
            break
        elif etype == "error":
            raise RuntimeError(f"Extraction error: {event['message']}")

    end = time.perf_counter()
    total_wall = end - start
    ttft = (first_chunk_time - start) if first_chunk_time else total_wall

    return {
        "total_wall_s": round(total_wall, 2),
        "ttft_s": round(ttft, 2),
        "output_chars": len(total_output),
        "output_text": total_output,
        "section_times": section_times,
        "status_events": status_events,
    }


def print_summary(results: list[dict]):
    print("\n" + "=" * 100)
    print("ROUND 2 RESULTS - Dark Sun Campaign Setting (Full PDF, 128K context)")
    print("=" * 100)
    print(
        f"{'Model':<22} {'Load(s)':>8} {'Extract(s)':>11} "
        f"{'TTFT(s)':>8} {'OutChars':>9} {'Placement':<30}"
    )
    print("-" * 100)
    for r in results:
        if "error" in r:
            print(f"{r['model_key']:<22} ERROR: {r['error']}")
            continue
        print(
            f"{r['model_key']:<22} {r['load_time_s']:>8.1f} "
            f"{r['total_wall_s']:>11.1f} {r['ttft_s']:>8.1f} "
            f"{r['output_chars']:>9} {r['placement']:<30}"
        )
    print("=" * 100)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--models",
        nargs="+",
        help="Registry keys to test (default: e4b, 26b-vram, 26b)",
    )
    parser.add_argument(
        "--include-31b",
        action="store_true",
        help="Include gemma4-31b (very slow - round 1 showed 3.5 tok/s)",
    )
    args = parser.parse_args()

    if not check_ollama():
        print("ERROR: Ollama not running")
        return

    # Select models
    if args.models:
        models_to_test = args.models
    else:
        models_to_test = DEFAULT_MODELS.copy()
        if args.include_31b:
            models_to_test.extend(SLOW_MODELS)

    registry = get_registry()
    for key in models_to_test:
        if registry.get_llm(key) is None:
            print(f"ERROR: Unknown model key: {key}")
            return

    # Extract Dark Sun PDF
    print(f"Loading {PDF_PATH.name}...")
    with open(PDF_PATH, "rb") as f:
        text, images = extract_file_content(f.read(), PDF_PATH.name)
    print(f"  Text: {len(text)} chars")
    print(f"  Embedded images: {len(images)}")

    from mtgai.generation.token_utils import count_tokens
    tokens = count_tokens(text)
    print(f"  Approx tokens: {tokens}")
    print(f"\nModels to benchmark: {models_to_test}")
    print("(Using 128K context from model registry - fits single-pass)\n")

    # Prepare output
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_DIR / f"darksun_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    results = []

    for key in models_to_test:
        model_info = registry.get_llm(key)
        assert model_info is not None  # validated above
        print(f"\n{'='*60}")
        print(f"BENCHMARKING: {key} ({model_info.model_id})")
        print(f"{'='*60}")

        unload_all_models()
        time.sleep(2)

        try:
            load_time = load_model(model_info.model_id)
        except Exception as e:
            print(f"  Load failed: {e}")
            results.append({"model_key": key, "error": f"load failed: {e}"})
            continue

        placement = check_gpu_placement(model_info.model_id)
        print(f"  Placement: {placement}")

        print("  Running stream_theme_extraction()...")
        try:
            result = run_extraction(key, text)
        except Exception as e:
            print(f"  Extraction failed: {e}")
            results.append({"model_key": key, "error": f"extract failed: {e}"})
            continue

        result["model_key"] = key
        result["model_id"] = model_info.model_id
        result["load_time_s"] = round(load_time, 1)
        result["placement"] = placement
        results.append(result)

        print(f"  Extraction wall clock: {result['total_wall_s']}s")
        print(f"  Time to first token:   {result['ttft_s']}s")
        print(f"  Output chars:          {result['output_chars']}")

        # Save output
        safe_name = key.replace("/", "_").replace(":", "_")
        output_file = run_dir / f"{safe_name}_output.md"
        output_file.write_text(result["output_text"], encoding="utf-8")
        print(f"  Saved: {output_file}")

    print_summary(results)

    # Save summary JSON (without full output text)
    summary = []
    for r in results:
        entry = {k: v for k, v in r.items() if k != "output_text"}
        summary.append(entry)
    summary_file = run_dir / "results.json"
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nResults: {run_dir}")


if __name__ == "__main__":
    main()
