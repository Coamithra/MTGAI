"""Per-stage input-token audit from a REAL pipeline run's llmfacade transcripts.

Point this at a project asset folder after a full local run. Each stage routes its
transcript to ``<asset>/<stage>/logs/*.jsonl`` (theme_extract also writes
``output/extraction_logs/``), and every response line records
``usage.prompt_tokens`` — the real input-token count from the model. This walks those
logs, reports the measured max / p95 / median input per stage, and recommends a
context-length tier per stage. It's the tool for the "run the full pipeline and read
the logs to determine ideal sizes" step (card 6a1c1940).

Usage (from anywhere, with backend on PYTHONPATH or just plain python):
    python ctx_log_audit.py <asset_folder> [<asset_folder> ...]
    python ctx_log_audit.py            # scans default repo locations

Stage attribution: for asset-folder logs the stage is the path component right before
``logs`` (robust, no tool->stage map needed). For the flat ``backend/logs/`` session
dirs (no stage structure) calls are grouped by the tool/convo name instead.
"""

from __future__ import annotations

import glob
import json
import math
import os
import re
import sys
from collections import defaultdict

# Candidate llama-server --ctx-size tiers to recommend from (round values).
TIERS = [16000, 24000, 32000, 48000, 64000, 96000, 128000]
GEMMA_ADJ = 1.25      # the model tokenizer runs ~10-30% over tiktoken; headroom factor
OUTPUT_RESERVE = 6000  # leave room for the stage's own output within --ctx-size
DOWNSTREAM_TIER = 48000  # the shipped DOWNSTREAM tier — flag any stage that exceeds it

REPO = "C:/Programming/MTGAI"


def _percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(math.ceil(p / 100 * len(s)) - 1)))
    return s[k]


def _toolname(convo: str | None) -> str:
    return re.sub(r"-[0-9a-f]{6,8}$", "", convo or "") or "?"


def _stage_from_path(path: str) -> str | None:
    """Stage id = the dir right before a ``logs`` component, if any."""
    parts = re.split(r"[\\/]+", path)
    if "logs" in parts:
        i = parts.index("logs")
        if i >= 1:
            cand = parts[i - 1]
            if cand not in ("backend", "."):
                return cand
    if "extraction_logs" in parts:
        return "theme_extract"
    return None


def collect(roots: list[str]) -> dict[str, list[int]]:
    by_stage: dict[str, list[int]] = defaultdict(list)
    files: list[str] = []
    for r in roots:
        files += glob.glob(os.path.join(r, "**", "*.jsonl"), recursive=True)
    for f in files:
        stage = _stage_from_path(f)
        try:
            lines = open(f, encoding="utf-8").read().splitlines()
        except OSError:
            continue
        convo = None
        for ln in lines:
            try:
                o = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if o.get("type") == "settings":
                convo = o.get("convo")
            if o.get("type") == "response":
                pt = (o.get("usage") or {}).get("prompt_tokens")
                if not pt:
                    continue
                key = stage or _toolname(o.get("convo") or convo)
                by_stage[key].append(pt)
    return by_stage


def recommend_tier(max_tok: int) -> int:
    need = int(max_tok * GEMMA_ADJ) + OUTPUT_RESERVE
    for t in TIERS:
        if t >= need:
            return t
    return TIERS[-1]


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        roots = args
    else:
        roots = [
            f"{REPO}/output",        # asset-folder + extraction logs under the repo
            f"{REPO}/backend/logs",  # flat session-dir fallback
            f"{REPO}/research",
        ]
    print("Scanning:", *roots, sep="\n  ")
    by_stage = collect(roots)
    if not by_stage:
        print("\nNo transcripts with usage.prompt_tokens found.")
        return

    print(f"\n{'stage / tool':30} {'n':>4} {'max':>8} {'p95':>8} {'median':>8}  "
          f"{'rec. ctx':>9}")
    print("-" * 78)
    flagged: list[tuple[str, int]] = []
    for stage in sorted(by_stage, key=lambda k: -max(by_stage[k])):
        v = by_stage[stage]
        mx = max(v)
        rec = recommend_tier(mx)
        note = ""
        if stage != "theme_extract" and mx * GEMMA_ADJ + OUTPUT_RESERVE > DOWNSTREAM_TIER:
            note = "  <-- exceeds 48k DOWNSTREAM tier!"
            flagged.append((stage, mx))
        print(f"{stage:30} {len(v):>4} {mx:>8} {_percentile(v,95):>8} "
              f"{_percentile(v,50):>8}  {rec:>9}{note}")

    print("\nVerdict (2-tier design: theme_extract=128k, everything else=48k):")
    if flagged:
        print("  Some downstream stage's real input exceeds the 48k tier — bump it:")
        for s, mx in flagged:
            print(f"    {s}: max {mx} tok (gemma-adj ~{int(mx*GEMMA_ADJ)}) -> "
                  f"recommend {recommend_tier(mx)}")
    else:
        downstream = [k for k in by_stage if k != "theme_extract"]
        worst = max((max(by_stage[k]) for k in downstream), default=0)
        print(f"  OK — worst downstream input {worst} tok "
              f"(gemma-adj ~{int(worst * GEMMA_ADJ)}) fits the 48k tier with headroom.")


if __name__ == "__main__":
    main()
