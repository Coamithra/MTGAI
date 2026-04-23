"""TC-1f benchmark: Unsloth Q4_K_XL + KV cache quantization.

Runs stream_theme_extraction() on the Dark Sun PDF at a forced 64K
context, for two models:
    - gemma4-26b-unsloth-q4kxl  (new, TC-1f candidate)
    - gemma4-26b-vram           (VladimirGav IQ4_XS, TC-1e winner at 128K)

Intended to be run twice: once with Ollama's default fp16 KV cache and
once with OLLAMA_KV_CACHE_TYPE=q4_0 set. Each run writes results tagged
with the observed KV cache mode so the two runs combine into a 2x2
matrix (model x kv_cache_mode).

Usage:
    python -m scripts.benchmark_gemma4_tc1f
    python -m scripts.benchmark_gemma4_tc1f --models gemma4-26b-unsloth-q4kxl
    python -m scripts.benchmark_gemma4_tc1f --num-ctx 32768
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
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

DEFAULT_MODELS = [
    "gemma4-26b-unsloth-q4kxl",
    "gemma4-26b-vram",
]


def check_ollama() -> bool:
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return resp.status_code == 200
    except requests.ConnectionError:
        return False


def detect_kv_cache_mode() -> str:
    """Detect Ollama's current KV cache mode.

    Ollama does not expose this via API. We read the env var that the
    benchmark process inherits (Ollama must have been started from the
    same env, or the user tells us via MTGAI_KV_CACHE override).
    """
    override = os.environ.get("MTGAI_KV_CACHE_OBSERVED")
    if override:
        return override
    return os.environ.get("OLLAMA_KV_CACHE_TYPE", "default")


def unload_all_models():
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
    """Force-load the model into VRAM with a tiny probe request."""
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
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/ps", timeout=5)
        for m in resp.json().get("models", []):
            if m.get("name") == model_id or m.get("model") == model_id:
                size = m.get("size", 0)
                size_vram = m.get("size_vram", 0)
                if size > 0:
                    pct_gpu = round(size_vram / size * 100)
                    pct_cpu = 100 - pct_gpu
                    return (
                        f"{pct_gpu}% GPU / {pct_cpu}% CPU "
                        f"({size_vram/1e9:.1f}/{size/1e9:.1f} GB)"
                    )
        return "unknown"
    except Exception:
        return "unknown"


def force_num_ctx(model_key: str, num_ctx: int) -> None:
    """Replace the registry's LLMModel with a copy capped at num_ctx.

    LLMModel is frozen, so we use dataclasses.replace and re-insert.
    This affects theme_extractor's inner registry.get_llm() lookup.
    """
    registry = get_registry()
    original = registry.get_llm(model_key)
    assert original is not None
    if original.context_window != num_ctx:
        patched = dataclasses.replace(original, context_window=num_ctx)
        registry.llm_models[model_key] = patched
        print(f"  Capped {model_key} context_window to {num_ctx}")


def run_extraction(model_key: str, text: str) -> dict:
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
                section_times.append(
                    {
                        "step": status_events[-1] if status_events else "start",
                        "duration_s": round(now - last_status_time, 2),
                    }
                )
            last_status_time = now
            status_events.append(msg)
            print(f"    [{now - start:.1f}s] {msg}")
        elif etype == "theme_chunk":
            if first_chunk_time is None:
                first_chunk_time = now
                print(f"    [{now - start:.1f}s] first output chunk")
            total_output += event["text"]
        elif etype == "complete":
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


def print_summary(results: list[dict], kv_mode: str, num_ctx: int):
    print("\n" + "=" * 100)
    print(
        f"TC-1f RESULTS - Dark Sun PDF, num_ctx={num_ctx}, "
        f"OLLAMA_KV_CACHE_TYPE={kv_mode}"
    )
    print("=" * 100)
    print(
        f"{'Model':<30} {'Load(s)':>8} {'Extract(s)':>11} "
        f"{'TTFT(s)':>8} {'OutChars':>9} {'Placement':<30}"
    )
    print("-" * 100)
    for r in results:
        if "error" in r:
            print(f"{r['model_key']:<30} ERROR: {r['error']}")
            continue
        print(
            f"{r['model_key']:<30} {r['load_time_s']:>8.1f} "
            f"{r['total_wall_s']:>11.1f} {r['ttft_s']:>8.1f} "
            f"{r['output_chars']:>9} {r['placement']:<30}"
        )
    print("=" * 100)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", help="Registry keys (default: all TC-1f models)")
    parser.add_argument("--num-ctx", type=int, default=65536, help="Forced context window (default: 64K)")
    parser.add_argument(
        "--tag",
        default=None,
        help="Override result-dir KV cache tag (e.g. 'default' or 'q4_0'). Defaults to env detection.",
    )
    args = parser.parse_args()

    if not check_ollama():
        print("ERROR: Ollama not running")
        return

    kv_mode = args.tag or detect_kv_cache_mode()
    models_to_test = args.models or DEFAULT_MODELS
    registry = get_registry()
    for key in models_to_test:
        if registry.get_llm(key) is None:
            print(f"ERROR: Unknown model key: {key}")
            return

    print(f"Loading {PDF_PATH.name}...")
    with open(PDF_PATH, "rb") as f:
        text, images = extract_file_content(f.read(), PDF_PATH.name)
    print(f"  Text: {len(text)} chars")
    print(f"  Embedded images: {len(images)}")

    from mtgai.generation.token_utils import count_tokens

    tokens = count_tokens(text)
    print(f"  Approx tokens: {tokens}")
    print(f"\nModels: {models_to_test}")
    print(f"num_ctx: {args.num_ctx}")
    print(f"KV cache mode (tagged as): {kv_mode}")
    print()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_DIR / f"tc1f_{kv_mode}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    results = []

    for key in models_to_test:
        model_info = registry.get_llm(key)
        assert model_info is not None
        print(f"\n{'='*60}")
        print(f"BENCHMARKING: {key} ({model_info.model_id})")
        print(f"{'='*60}")

        force_num_ctx(key, args.num_ctx)

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
        result["kv_cache_mode"] = kv_mode
        result["num_ctx"] = args.num_ctx
        results.append(result)

        print(f"  Extraction wall clock: {result['total_wall_s']}s")
        print(f"  Time to first token:   {result['ttft_s']}s")
        print(f"  Output chars:          {result['output_chars']}")

        safe_name = key.replace("/", "_").replace(":", "_")
        output_file = run_dir / f"{safe_name}_output.md"
        output_file.write_text(result["output_text"], encoding="utf-8")
        print(f"  Saved: {output_file}")

    print_summary(results, kv_mode, args.num_ctx)

    summary = []
    for r in results:
        entry = {k: v for k, v in r.items() if k != "output_text"}
        summary.append(entry)
    summary_file = run_dir / "results.json"
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nResults: {run_dir}")


if __name__ == "__main__":
    main()
