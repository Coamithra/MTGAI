"""TC-2 benchmark: llama.cpp via llmfacade.

Re-baselines the post-Ollama→llama.cpp transport on the established Dark Sun
PDF corpus. Default matrix: Vlad Gemma 4 26B at 128K context across f16, q8_0,
and q4_0 KV cache modes. KV cache mode is now per-model in models.toml, so
each variant is a synthetic registry entry pointing at the same GGUF with
different launch knobs (and a unique model_id so llama-swap creates a
separate server per variant).

Flare-probe load/extraction split: each variant first sends a 4-token "hi"
to force llama-swap to spawn llama-server and load weights into VRAM
(measured as load_time_s), then the real extraction begins (measured as
extraction_time_s). Restores the load/extraction split that the TC-1f
script got from Ollama's /api/ps unload + warmup pattern.

Usage:
    python -m scripts.benchmark_llamacpp_tc2
    python -m scripts.benchmark_llamacpp_tc2 --variants vlad-gemma4-26b-dynamic-q4_0
    python -m scripts.benchmark_llamacpp_tc2 --num-ctx 32768 --corpus asd
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path

from mtgai.generation.llm_client import _get_provider, _llamacpp_new_model
from mtgai.generation.token_utils import count_tokens
from mtgai.pipeline.theme_extractor import (
    extract_file_content,
    request_cancel,
    stream_theme_extraction,
)
from mtgai.settings.model_registry import LLMModel, get_registry

PDF_PATH = Path(
    "C:/Programming/MTGAI/Inspiration/"
    "The Dark Sun Campaign Setting for Worlds Without Number.pdf"
)
ASD_THEME_PATH = Path("C:/Programming/MTGAI/output/sets/ASD/theme.txt")
RESULTS_DIR = Path("C:/Programming/MTGAI/output/benchmarks")


@dataclasses.dataclass(frozen=True)
class Variant:
    """A synthetic registry entry for benchmarking. Each variant spawns a
    distinct llama-server because model_id is suffixed with the cache mode."""

    key: str  # registry key the benchmark uses to refer to the variant
    base_key: str  # registry key to clone GGUF / context_window from
    cache_type_k: str | None
    cache_type_v: str | None
    n_gpu_layers: int | None = -1


# f16 KV cache at 128K context is ~3.4 GB. With Vlad weights also targeting
# all-GPU (n_gpu_layers=-1), the total exceeds 12 GB VRAM and llama-server
# OOMs mid-extraction (same trap as TC-1f's `num_gpu=99` upstream Vlad
# Modelfile). Cap GPU layers manually for f16. q8_0 (~1.7 GB) and q4_0
# (~0.8 GB) caches leave room for the all-GPU production config.
VLAD_VARIANTS: list[Variant] = [
    Variant(
        key="vlad-gemma4-26b-dynamic-f16",
        base_key="gemma4-26b-vram-dynamic",
        cache_type_k="f16",
        cache_type_v="f16",
        n_gpu_layers=35,
    ),
    Variant(
        key="vlad-gemma4-26b-dynamic-q8_0",
        base_key="gemma4-26b-vram-dynamic",
        cache_type_k="q8_0",
        cache_type_v="q8_0",
        n_gpu_layers=-1,
    ),
    Variant(
        key="vlad-gemma4-26b-dynamic-q4_0",
        base_key="gemma4-26b-vram-dynamic",
        cache_type_k="q4_0",
        cache_type_v="q4_0",
        n_gpu_layers=-1,
    ),
]


def register_variant(v: Variant, num_ctx: int | None = None) -> LLMModel:
    """Inject a synthetic LLMModel into the registry and return it."""
    registry = get_registry()
    base = registry.get_llm(v.base_key)
    if base is None:
        raise ValueError(f"Base model {v.base_key!r} not in registry")

    overrides: dict = {
        "key": v.key,
        # Unique model_id per variant → distinct llama-swap YAML entry,
        # distinct llama-server process, per-server cache_type_k actually
        # honoured (rather than reusing a previously-launched server).
        "model_id": f"{base.model_id}-bench-{v.cache_type_k or 'default'}",
        "cache_type_k": v.cache_type_k,
        "cache_type_v": v.cache_type_v,
    }
    if v.n_gpu_layers is not None:
        overrides["n_gpu_layers"] = v.n_gpu_layers
    if num_ctx is not None:
        overrides["context_window"] = num_ctx

    patched = dataclasses.replace(base, **overrides)
    registry.llm_models[v.key] = patched
    registry._model_id_to_key[patched.model_id] = v.key
    return patched


def query_gpu_placement() -> str:
    """Best-effort runtime VRAM usage from nvidia-smi."""
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0:
            line = out.stdout.strip().splitlines()[0]
            used, total = (int(x.strip()) for x in line.split(","))
            return f"{used}/{total} MiB ({100*used/total:.0f}%)"
    except Exception:
        pass
    return "unknown"


def flare_probe(model_info: LLMModel) -> float:
    """Force llama-swap to spawn llama-server + load weights into VRAM.

    Returns wall time in seconds. The Conversation send is intentionally
    tiny (max_tokens=4) so the cost is dominated by model load, not
    inference.
    """
    provider = _get_provider("llamacpp")
    facade_model = _llamacpp_new_model(provider, model_info.model_id)
    convo = facade_model.new_conversation(log_dir=False)
    start = time.perf_counter()
    convo.send("hi", max_tokens=4)
    return time.perf_counter() - start


def run_extraction(model_key: str, text: str) -> dict:
    """Run stream_theme_extraction and capture timing + output stats."""
    first_chunk_time: float | None = None
    total_output = ""
    section_times: list[dict] = []
    last_status_time: float | None = None
    status_events: list[str] = []

    start = time.perf_counter()

    for event in stream_theme_extraction(text, model_key):
        etype = event["type"]
        now = time.perf_counter()

        if etype == "status":
            msg = event.get("message", "")
            if last_status_time is not None:
                section_times.append(
                    {
                        "step": status_events[-1] if status_events else "start",
                        "duration_s": round(now - last_status_time, 2),
                    }
                )
            last_status_time = now
            status_events.append(msg)
            print(f"    [{now - start:7.1f}s] {msg}")
        elif etype == "theme_chunk":
            if first_chunk_time is None:
                first_chunk_time = now
                print(f"    [{now - start:7.1f}s] first output chunk")
            total_output += event.get("text", "")
        elif etype == "complete":
            final = event.get("theme_text", total_output)
            if final and len(final) > len(total_output):
                total_output = final
            print(f"    [{now - start:7.1f}s] complete")
            break
        elif etype == "error":
            raise RuntimeError(f"Extraction error: {event.get('message')}")
        elif etype == "cancelled":
            print(f"    [{now - start:7.1f}s] cancelled")
            break

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


def print_summary(results: list[dict], num_ctx: int):
    print("\n" + "=" * 110)
    print(f"TC-2 RESULTS — num_ctx={num_ctx}, transport=llamacpp")
    print("=" * 110)
    print(
        f"{'Variant':<40} {'Load(s)':>8} {'Extract(s)':>11} "
        f"{'TTFT(s)':>9} {'OutChars':>9} {'GPU':<24}"
    )
    print("-" * 110)
    for r in results:
        if "error" in r:
            print(f"{r['variant']:<40} ERROR: {r['error']}")
            continue
        print(
            f"{r['variant']:<40} {r['load_time_s']:>8.1f} "
            f"{r['extraction_time_s']:>11.1f} {r['ttft_s']:>9.1f} "
            f"{r['output_chars']:>9} {r['placement']:<24}"
        )
    print("=" * 110)


def install_sigint_handler():
    """Wire Ctrl+C → request_cancel() so we abort cleanly mid-stream."""

    def handler(_signum, _frame):
        print("\n^C received — requesting cancel...")
        request_cancel()

    signal.signal(signal.SIGINT, handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variants",
        nargs="+",
        help="Synthetic variant keys to run (default: all Vlad variants)",
    )
    parser.add_argument(
        "--registry-key",
        help=(
            "Bench a single registry entry as-is (no synthetic-variant "
            "machinery). Mutually exclusive with --variants. The model's "
            "cache_type_k/v + n_gpu_layers come straight from models.toml."
        ),
    )
    parser.add_argument(
        "--num-ctx",
        type=int,
        default=128000,
        help="Force context window (default: 128000)",
    )
    parser.add_argument(
        "--corpus",
        choices=["darksun", "asd"],
        default="darksun",
        help="Corpus to extract (default: darksun)",
    )
    parser.add_argument(
        "--tag",
        default="vlad-rebaseline",
        help="Result-dir tag (default: vlad-rebaseline)",
    )
    args = parser.parse_args()

    if args.variants and args.registry_key:
        parser.error("--variants and --registry-key are mutually exclusive")

    install_sigint_handler()

    # Pick corpus
    if args.corpus == "darksun":
        path = PDF_PATH
        print(f"Loading {path.name}...")
        with open(path, "rb") as f:
            text = extract_file_content(f.read(), path.name)
    else:
        path = ASD_THEME_PATH
        print(f"Loading {path.name}...")
        text = path.read_text(encoding="utf-8")

    print(f"  Text: {len(text)} chars")
    approx = count_tokens(text)
    print(f"  Approx tokens (tiktoken cl100k): {approx}")

    # Resolve what to run. --registry-key takes a model_key from models.toml
    # and overrides the num_ctx; everything else (cache_type_k, n_gpu_layers)
    # comes from the registry entry as written. --variants uses the synthetic
    # Vlad-cache-sweep machinery.
    if args.registry_key:
        variants_to_run = [args.registry_key]
        registry = get_registry()
        base = registry.get_llm(args.registry_key)
        if base is None:
            print(f"ERROR: registry key {args.registry_key!r} not found")
            return
        # Synthesize a Variant from the registry entry, preserving its launch
        # knobs verbatim. register_variant still suffixes the model_id with
        # the cache mode, which is fine — gives us clean per-run isolation.
        passthrough = Variant(
            key=args.registry_key,
            base_key=args.registry_key,
            cache_type_k=base.cache_type_k,
            cache_type_v=base.cache_type_v,
            n_gpu_layers=base.n_gpu_layers,
        )
        by_key = {args.registry_key: passthrough}
    else:
        variants_to_run = args.variants or [v.key for v in VLAD_VARIANTS]
        by_key = {v.key: v for v in VLAD_VARIANTS}

    print(f"\nVariants: {variants_to_run}")
    print(f"num_ctx: {args.num_ctx}\n")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_DIR / f"tc2_{args.tag}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []

    for vk in variants_to_run:
        if vk not in by_key:
            print(f"ERROR: unknown variant {vk!r}")
            continue
        v = by_key[vk]
        print(f"\n{'='*70}")
        print(f"BENCHMARKING: {vk}")
        print(f"  cache_type_k={v.cache_type_k}, cache_type_v={v.cache_type_v}")
        print(f"  n_gpu_layers={v.n_gpu_layers}, num_ctx={args.num_ctx}")
        print(f"{'='*70}")

        try:
            model_info = register_variant(v, num_ctx=args.num_ctx)
        except Exception as e:
            print(f"  Variant registration failed: {e}")
            results.append({"variant": vk, "error": f"register: {e}"})
            continue

        print("  Flare probe (force-load via 4-token 'hi')...")
        try:
            load_s = flare_probe(model_info)
            print(f"  Load time: {load_s:.1f}s")
        except Exception as e:
            print(f"  Flare probe failed: {e}")
            results.append({"variant": vk, "error": f"load: {e}"})
            continue

        placement = query_gpu_placement()
        print(f"  Placement (post-load): {placement}")

        print("  Running stream_theme_extraction()...")
        try:
            r = run_extraction(vk, text)
        except Exception as e:
            print(f"  Extraction failed: {e}")
            results.append({"variant": vk, "error": f"extract: {e}"})
            continue

        r["variant"] = vk
        r["model_id"] = model_info.model_id
        r["gguf_path"] = model_info.gguf_path
        r["cache_type_k"] = v.cache_type_k
        r["cache_type_v"] = v.cache_type_v
        r["n_gpu_layers"] = v.n_gpu_layers
        r["context_window"] = args.num_ctx
        r["load_time_s"] = round(load_s, 1)
        r["extraction_time_s"] = r["total_wall_s"]
        r["placement"] = placement
        results.append(r)

        # Save per-variant output and a running summary so a mid-run abort
        # still leaves usable artifacts on disk.
        safe = vk.replace("/", "_").replace(":", "_")
        (run_dir / f"{safe}_output.md").write_text(r["output_text"], encoding="utf-8")
        (run_dir / "results.json").write_text(
            json.dumps(
                [{k: v for k, v in res.items() if k != "output_text"} for res in results],
                indent=2,
            ),
            encoding="utf-8",
        )

    print_summary(results, args.num_ctx)
    print(f"\nResults: {run_dir}")


if __name__ == "__main__":
    main()
