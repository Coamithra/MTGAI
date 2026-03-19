"""CLI entry point for card rendering.

Renders card images by compositing art, M15 frame templates, and text.

Usage::

    python -m mtgai.rendering --set ASD [--card W-C-01] [--dry-run] [--force]
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from mtgai.rendering.card_renderer import CardRenderer

logger = logging.getLogger(__name__)

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ASSETS_ROOT = PROJECT_ROOT / "assets"
OUTPUT_ROOT = PROJECT_ROOT / "output"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render card images from card JSON + art + M15 frames",
    )
    parser.add_argument(
        "--set",
        default="ASD",
        help="Set code (default: ASD)",
    )
    parser.add_argument(
        "--card",
        default=None,
        help=("Single card collector number or prefix (e.g. W-C-01, B-R)"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would be rendered without producing files",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-render even if output already exists",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    renderer = CardRenderer(
        assets_root=ASSETS_ROOT,
        output_root=OUTPUT_ROOT,
    )

    summary = renderer.render_set(
        set_code=args.set,
        card_filter=args.card,
        dry_run=args.dry_run,
        force=args.force,
    )

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"Card Rendering \u2014 {summary['set_code']}")
    print(f"{'=' * 60}")
    print(f"Rendered: {summary['rendered']}")
    print(f"Skipped:  {summary['skipped']}")
    print(f"Failed:   {summary['failed']}")
    print(f"Dry run:  {summary['dry_run']}")
    print(f"Elapsed:  {summary['elapsed_seconds']:.1f}s")
    if summary["errors"]:
        print("\nErrors:")
        for e in summary["errors"]:
            card_id = e.get("card", "?")
            name = e.get("name", "")
            err = e.get("error", "?")
            label = f"{card_id}: {name}" if name else card_id
            print(f"  {label} \u2014 {err}")


if __name__ == "__main__":
    main()
