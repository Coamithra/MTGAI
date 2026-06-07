"""QA scaffolding: seed a rendering project in the UN-approved (paused) state.

The debug ``seed-stage`` endpoint marks the target stage **COMPLETED**, so seeding
``rendering`` always lands the wizard on an *already-approved* set ("Set approved
for print. 🎉") with no Approve button — there is no in-app way to un-approve.
That makes the approve-for-print *click gate* impossible to exercise from a seed.

This script closes that gap for the QA bot: it seeds ``rendering`` via the running
debug server, then patches the cloned ``pipeline-state.json`` so the rendering
backbone stage is ``paused_for_review`` (pipeline ``paused``) — exactly the state
a real run with the rendering break-point ON would pause in. Reload
``/pipeline/rendering`` and the "Approve for print" button is now present + live.

Usage (server must be running with ``serve --debug``)::

    python scripts/qa_seed_rendering_unapproved.py [--port 8080] [--source DIR]

Prints the asset folder + the navigate URL. Pure stdlib (urllib/json), no deps.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--source", default=None, help="golden source_dir (default: newest)")
    args = ap.parse_args()

    base = f"http://localhost:{args.port}"
    seed_body: dict = {"target_stage": "rendering"}
    if args.source:
        seed_body["source_dir"] = args.source

    try:
        res = _post(f"{base}/api/debug/seed-stage", seed_body)
    except urllib.error.URLError as exc:
        print(f"ERROR: could not reach debug server at {base}: {exc}", file=sys.stderr)
        print("Is the server running with `serve --debug`?", file=sys.stderr)
        return 2

    asset = res.get("asset_folder")
    if not asset:
        print(f"ERROR: seed-stage returned no asset_folder: {res}", file=sys.stderr)
        return 1

    state_path = Path(asset) / "pipeline-state.json"
    if not state_path.is_file():
        print(f"ERROR: no pipeline-state.json at {state_path}", file=sys.stderr)
        return 1

    state = json.loads(state_path.read_text(encoding="utf-8"))
    flipped = False
    for stage in state.get("stages", []):
        # Backbone rendering instance only (instance_id == stage_id).
        if stage.get("stage_id") == "rendering" and stage.get("instance_id") == "rendering":
            stage["status"] = "paused_for_review"
            flipped = True
    if not flipped:
        print("ERROR: no backbone rendering stage found in cloned state", file=sys.stderr)
        return 1
    state["overall_status"] = "paused"
    state["current_instance_id"] = "rendering"

    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Seeded UN-approved rendering project:")
    print(f"  asset_folder : {asset}")
    print(f"  state        : {state_path}")
    print(f"  navigate     : {base}/pipeline/rendering")
    print("Rendering stage is now paused_for_review — the 'Approve for print' button is live.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
