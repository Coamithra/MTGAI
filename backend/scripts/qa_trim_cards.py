"""QA scaffolding: trim a project's card pool to a handful for fast art-tail runs.

The art tail (char_portraits, art_gen) generates Flux images at ~60s each, so a
full 66-card golden takes hours. For QA we only need a few cards to exercise the
*plumbing* (generate → judge → review grid → approve). This script trims the
active/given project's ``cards/`` to the first N card-gen cards (lowest collector
numbers) — keeping real, credited cards so artist assignment + art-prompt
authoring still apply — and prunes ``generation_progress.json`` + stale renders to
match, so downstream tabs stay internally consistent.

It does NOT touch skeleton/reprint/theme artifacts (the art tail reads cards +
theme + art-direction, not skeleton slot consistency), and it leaves basic lands
(``L-*``) out of the count by default since they carry no art_prompt.

Usage::

    # operate on a specific cloned QA project folder
    python scripts/qa_trim_cards.py --asset "C:\\path\\to\\output\\qa-runs\\foo" --keep 3

    # or resolve the active project's asset folder automatically (server-independent)
    python scripts/qa_trim_cards.py --keep 3

``--keep`` is the number of card-gen cards to KEEP (default 3). ``--include-lands``
also keeps that many ``L-*`` basics. Idempotent-ish: re-running with the same
--keep is a no-op once the pool is already trimmed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Standalone script (not on the package path): resolve repo root by walking up.
REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_asset(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    # Fall back to the active project's asset folder via the package API.
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from mtgai.runtime import active_project

    proj = active_project.read_active_project()
    if proj is None:
        raise SystemExit("No --asset given and no active project is open.")
    return Path(proj.settings.asset_folder)


def _is_land(cn: str) -> bool:
    return cn.upper().startswith("L-") or cn.upper().startswith("L")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--asset", default=None, help="project asset folder (default: active project)")
    ap.add_argument("--keep", type=int, default=3, help="card-gen cards to keep (default 3)")
    ap.add_argument("--include-lands", type=int, default=0, help="also keep this many L-* basics")
    args = ap.parse_args()

    asset = _resolve_asset(args.asset)
    cards_dir = asset / "cards"
    if not cards_dir.is_dir():
        raise SystemExit(f"No cards/ dir at {cards_dir}")

    # Partition by (is_land, collector_number).
    files = sorted(cards_dir.glob("*.json"))
    cardgen: list[tuple[str, Path]] = []
    lands: list[tuple[str, Path]] = []
    for p in files:
        try:
            cn = json.loads(p.read_text(encoding="utf-8")).get("collector_number") or p.stem
        except Exception:
            cn = p.stem
        (lands if _is_land(cn) else cardgen).append((cn, p))

    cardgen.sort(key=lambda t: t[0])
    lands.sort(key=lambda t: t[0])
    keep_cardgen = cardgen[: args.keep]
    keep_lands = lands[: args.include_lands]
    keep_cns = {cn for cn, _ in keep_cardgen + keep_lands}
    keep_paths = {p for _, p in keep_cardgen + keep_lands}

    removed = 0
    for _, p in cardgen + lands:
        if p not in keep_paths:
            p.unlink()
            removed += 1

    # Prune renders/ of removed cards (best-effort; keep ones we kept).
    renders = asset / "renders"
    if renders.is_dir():
        for r in renders.glob("*.png"):
            stem_cn = r.stem.split("_", 1)[0]
            if stem_cn not in keep_cns:
                r.unlink()

    # Rewrite generation_progress.json filled_slots to only the kept cards'
    # slots, so downstream stage state stays consistent.
    gp_path = asset / "generation_progress.json"
    if gp_path.is_file():
        gp = json.loads(gp_path.read_text(encoding="utf-8"))
        filled = gp.get("filled_slots")
        if isinstance(filled, dict):
            kept_slots = {}
            for _, p in keep_cardgen + keep_lands:
                try:
                    card = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    continue
                slot = card.get("slot_id") or card.get("collector_number")
                if slot in filled:
                    kept_slots[slot] = filled[slot]
            gp["filled_slots"] = kept_slots
            gp_path.write_text(json.dumps(gp, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        f"Trimmed {asset.name}: kept {len(keep_paths)} cards "
        f"({len(keep_cardgen)} card-gen + {len(keep_lands)} lands), removed {removed}."
    )
    print("Kept:", ", ".join(sorted(keep_cns)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
