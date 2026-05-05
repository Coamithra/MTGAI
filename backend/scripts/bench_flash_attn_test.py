"""One-off: spawn llama-server directly with --flash-attn on and run the
same Dark Sun extraction we use in TC-2 Phase B q8_0. No llmfacade, no
llama-swap — direct subprocess.

Goal: confirm or refute the hypothesis that the TC-2 numbers were measured
with flash attention OFF (because llama-server's `auto` heuristic decided
"no" for Gemma 4) and that forcing it on collapses TTFT and trims wall.

Compare against TC-2 Phase B q8_0 baseline:
    Wall   105.5 s
    TTFT    42.1 s
    Out    11,306 chars

Usage:
    python -m scripts.bench_flash_attn_test                  # Vlad q8_0
    python -m scripts.bench_flash_attn_test --flash-attn off # control
    python -m scripts.bench_flash_attn_test --gguf C:/Models/gemma-4-E4B-it-Q4_K_M.gguf
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

import httpx

from mtgai.generation.token_utils import count_tokens
from mtgai.pipeline.theme_extractor import extract_file_content

PDF_PATH = Path(
    "C:/Programming/MTGAI/Inspiration/"
    "The Dark Sun Campaign Setting for Worlds Without Number.pdf"
)
PROMPTS_DIR = Path("C:/Programming/MTGAI/backend/mtgai/pipeline/prompts")
LLAMA_SERVER = Path("C:/Tools/llama.cpp/llama-server.exe")
PORT = 5801  # offset from llmfacade's typical 5800 to avoid collision


def wait_for_ready(base: str, timeout_s: float = 120.0) -> float:
    """Poll /health until 200, return elapsed seconds."""
    start = time.perf_counter()
    while time.perf_counter() - start < timeout_s:
        try:
            r = httpx.get(f"{base}/health", timeout=2.0)
            if r.status_code == 200:
                return time.perf_counter() - start
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise TimeoutError(f"server not ready after {timeout_s}s")


def run_extraction(base: str, system_prompt: str, user_msg: str) -> dict:
    """Stream one chat-completion, return timing stats."""
    payload = {
        "model": "test",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": 16384,
        "temperature": 0.7,
        "stream": True,
    }

    first_chunk_time: float | None = None
    total_text = ""
    start = time.perf_counter()

    with httpx.stream(
        "POST",
        f"{base}/v1/chat/completions",
        json=payload,
        timeout=httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0),
    ) as resp:
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:].strip()
            if data == "[DONE]":
                break
            try:
                ev = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = ev.get("choices", [])
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            content = delta.get("content")
            if content:
                if first_chunk_time is None:
                    first_chunk_time = time.perf_counter()
                    print(
                        f"  [{first_chunk_time - start:7.1f}s] first content chunk"
                    )
                total_text += content

    end = time.perf_counter()
    return {
        "wall_s": round(end - start, 2),
        "ttft_s": round((first_chunk_time or end) - start, 2),
        "output_chars": len(total_text),
        "output_text": total_text,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--gguf",
        default="C:/Models/vlad-gemma4-26b-dynamic.gguf",
        help="Path to GGUF file to test",
    )
    parser.add_argument(
        "--ctx",
        type=int,
        default=128000,
        help="Context size",
    )
    parser.add_argument(
        "--ngl",
        type=int,
        default=-1,
        help="n-gpu-layers (-1 = all)",
    )
    parser.add_argument(
        "--cache-k",
        default="q8_0",
        help="cache-type-k",
    )
    parser.add_argument(
        "--cache-v",
        default="q8_0",
        help="cache-type-v",
    )
    parser.add_argument(
        "--flash-attn",
        choices=["on", "off", "auto"],
        default="on",
        help="Flash attention mode (default: on)",
    )
    args = parser.parse_args()

    # Load prompts
    system_prompt = (PROMPTS_DIR / "theme_extraction.txt").read_text(encoding="utf-8")
    user_template = (PROMPTS_DIR / "theme_chunk_single.txt").read_text(encoding="utf-8")

    # Load corpus
    print(f"Loading {PDF_PATH.name}...")
    with open(PDF_PATH, "rb") as f:
        text = extract_file_content(f.read(), PDF_PATH.name)
    print(f"  Text: {len(text)} chars, ~{count_tokens(text)} tokens")
    user_msg = user_template.format(text=text)

    # Build llama-server cmd
    cmd = [
        str(LLAMA_SERVER),
        "--model", args.gguf,
        "--port", str(PORT),
        "--ctx-size", str(args.ctx),
        "--cache-type-k", args.cache_k,
        "--cache-type-v", args.cache_v,
        "--n-gpu-layers", str(args.ngl),
        "--flash-attn", args.flash_attn,
        "--parallel", "1",
        "--no-webui",
    ]
    print(f"\nSpawning: {' '.join(cmd)}\n")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    base = f"http://127.0.0.1:{PORT}"
    try:
        # Wait for ready (also captures startup logs that might mention flash attn)
        print("Waiting for server ready...")
        load_s = wait_for_ready(base, timeout_s=180)
        print(f"  Ready in {load_s:.1f}s")

        # Run extraction
        print("\nRunning extraction...")
        r = run_extraction(base, system_prompt, user_msg)

        print(f"\n{'='*70}")
        print(f"RESULT (flash_attn={args.flash_attn}, ngl={args.ngl}, cache={args.cache_k})")
        print(f"{'='*70}")
        print(f"  Load time      {load_s:>8.1f} s")
        print(f"  Wall (extract) {r['wall_s']:>8.1f} s")
        print(f"  TTFT           {r['ttft_s']:>8.1f} s")
        print(f"  Output chars   {r['output_chars']:>8}")
        print(f"{'='*70}")
    finally:
        # Drain stdout and look for flash-attn evidence
        proc.terminate()
        try:
            stdout, _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, _ = proc.communicate()

        # Print any line that mentions flash / fa / attn
        flash_lines = [
            ln for ln in stdout.splitlines()
            if any(kw in ln.lower() for kw in ("flash", "fa = ", "fa:"))
        ]
        if flash_lines:
            print("\nFlash-attention evidence from llama-server log:")
            for ln in flash_lines[:10]:
                print(f"  {ln}")


if __name__ == "__main__":
    main()
