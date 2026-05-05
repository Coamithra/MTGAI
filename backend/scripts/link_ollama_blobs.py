"""Hard-link Ollama-cached GGUF blobs into C:\\Models\\ with friendly names.

Ollama stores GGUF files as content-addressed blobs under
``~/.ollama/models/blobs/sha256-<hash>``. The manifests under
``~/.ollama/models/manifests/`` map model tags to blob hashes.

This helper resolves named tags (or explicit blob-hash overrides) to GGUF
files in ``C:\\Models\\`` via NTFS hard links. Hard links don't duplicate
disk usage, but unlike symlinks they don't break if Ollama rotates the
manifest pointer (the link's target is the blob inode).

Caveat: if Ollama runs ``ollama rm <model>`` and garbage-collects the blob,
our hard link becomes the sole reference, so the disk space stays held.
That's fine for a benchmarking workflow.

Usage:
    python -m scripts.link_ollama_blobs --plan      # show what would be linked
    python -m scripts.link_ollama_blobs --execute   # actually create links
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path

OLLAMA_ROOT = Path("C:/Users/coami/.ollama/models")
MODELS_DIR = Path("C:/Models")


@dataclass(frozen=True)
class LinkSpec:
    """Maps an Ollama tag to a destination filename in C:\\Models\\."""

    ollama_tag: str  # e.g. "library/gemma4/26b"
    dest_filename: str  # e.g. "gemma4-26b-stock-q4_K_M.gguf"
    purpose: str  # human-readable note for logging


# Phase-D candidates already cached by Ollama (verified via manifest scan).
#
# Stock Google GGUFs (gemma4:26b, gemma4:e4b, gemma4:31b) are NOT included
# here because they fail to load in llama.cpp: their architecture metadata
# expects multimodal tensors (vision + audio) that aren't shipped in the
# text-only blob, and the loader's tensor-count assertion rejects them.
# Only Unsloth's text-only repacks (and VladimirGav's, used elsewhere) are
# llama.cpp-compatible. See learnings/llamacpp-tc2-benchmark.md for detail.
DEFAULT_LINKS: list[LinkSpec] = [
    LinkSpec(
        ollama_tag="library/unsloth-gemma4-26b-q4kxl/latest",
        dest_filename="gemma4-26b-unsloth-q4kxl.gguf",
        purpose="D2: Unsloth UD-Q4_K_XL backup (~17 GB) — confirmed loadable",
    ),
]


def resolve_blob(tag: str) -> tuple[Path, int]:
    """Return (blob_path, expected_size) for an Ollama tag."""
    parts = tag.split("/")
    manifest = OLLAMA_ROOT / "manifests" / "registry.ollama.ai" / Path(*parts)
    if not manifest.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest}")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    # The first layer of mediaType ending in ".image.model" is the GGUF.
    for layer in data.get("layers", []):
        if layer.get("mediaType", "").endswith(".image.model"):
            digest = layer["digest"]  # "sha256:abc..."
            algo, h = digest.split(":")
            blob = OLLAMA_ROOT / "blobs" / f"{algo}-{h}"
            if not blob.is_file():
                raise FileNotFoundError(f"Blob missing: {blob}")
            return blob, int(layer.get("size", 0))
    raise RuntimeError(f"No model layer in manifest for {tag}")


def main():
    parser = argparse.ArgumentParser()
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--plan", action="store_true", help="Show what would happen")
    grp.add_argument("--execute", action="store_true", help="Actually create links")
    parser.add_argument(
        "--specs",
        nargs="+",
        help="Subset of dest_filename values to link (default: all)",
    )
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    selected = DEFAULT_LINKS
    if args.specs:
        selected = [s for s in DEFAULT_LINKS if s.dest_filename in set(args.specs)]
        if not selected:
            print(f"ERROR: no specs match {args.specs}")
            print(f"Available: {[s.dest_filename for s in DEFAULT_LINKS]}")
            return

    print(f"Plan: link {len(selected)} blob(s) into {MODELS_DIR}")
    print("-" * 80)

    for spec in selected:
        dest = MODELS_DIR / spec.dest_filename
        try:
            blob, size = resolve_blob(spec.ollama_tag)
        except Exception as e:
            print(f"  [SKIP] {spec.dest_filename}: {e}")
            continue

        size_gb = size / (1024**3)
        if dest.exists():
            existing_size = dest.stat().st_size
            if existing_size == size:
                print(
                    f"  [OK   ] {spec.dest_filename}  "
                    f"already exists, {size_gb:.2f} GB matches"
                )
                continue
            print(
                f"  [WARN ] {spec.dest_filename}  exists with different size "
                f"({existing_size:,} vs blob {size:,}) — leaving alone"
            )
            continue

        print(f"  [LINK ] {spec.dest_filename}  ({size_gb:.2f} GB)  ← {blob.name}")
        print(f"          purpose: {spec.purpose}")
        if args.execute:
            try:
                os.link(str(blob), str(dest))
                actual = dest.stat().st_size
                if actual != size:
                    print(
                        f"          [WARN] post-link size mismatch: "
                        f"{actual:,} vs {size:,}"
                    )
                else:
                    print("          [OK] hard link created")
            except OSError as e:
                print(f"          [FAIL] os.link failed: {e}")

    if args.plan:
        print("\n(plan-only — re-run with --execute to actually link)")


if __name__ == "__main__":
    main()
