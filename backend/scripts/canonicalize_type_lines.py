"""One-shot sweep: rewrite stored card ``type_line`` strings into canonical order.

Background: the ``type_line`` string is authored by the LLM and rendered verbatim.
A card type written after the dash ("Creature -- Artifact Peacekeeper") or main
types in the wrong order ("Creature Artifact") used to survive to the card face,
because the schema parser fixed only the *structured* fields and left the raw
string alone. That's now AUTO-fixed in the validation pass
(``type_check.type_line_order``), so cards re-validated through gen / finalize
self-heal — but already-written card files on disk are not touched until they
pass back through validation. This script applies the same canonicalization to
existing files in one pass.

It is **surgical**: it loads each card, derives the canonical line via the SAME
package function the validator uses (``type_check.canonical_type_line`` over the
schema parser's structured parts), and rewrites ONLY the ``type_line`` value when
it differs — preserving the card's existing dash style (``--`` vs ``—``), every
other field, key order, encoding (raw UTF-8), and newline style. Unchanged cards
are not rewritten at all. Idempotent: a second run is a no-op.

Usage::

    # a specific set's tracked cards
    python scripts/canonicalize_type_lines.py output/sets/ASD/cards

    # an asset folder (its cards/ subdir is found automatically), or a single file
    python scripts/canonicalize_type_lines.py "C:\\path\\to\\output\\qa-runs\\foo"

    # default: the active project's asset folder
    python scripts/canonicalize_type_lines.py

    # preview without writing
    python scripts/canonicalize_type_lines.py output/sets/ASD/cards --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Standalone script (not on the package path): resolve repo root by walking up,
# then make the backend package importable.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from mtgai.models.card import Card  # noqa: E402
from mtgai.validation.schema import _parse_type_line  # noqa: E402
from mtgai.validation.type_check import canonical_type_line  # noqa: E402


def _resolve_cards_dirs(explicit: str | None) -> list[Path]:
    """Return the card directory/-ies (or single files) to operate on.

    A path may be a ``cards/`` dir, an asset folder (its ``cards/`` is used), or a
    single ``.json`` file. With no path, fall back to the active project's asset
    folder via the package API (server-independent).
    """
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return [p]
        if (p / "cards").is_dir():
            return [p / "cards"]
        if p.is_dir():
            return [p]
        raise SystemExit(f"Path not found or has no cards/: {p}")

    from mtgai.runtime import active_project

    proj = active_project.read_active_project()
    if proj is None:
        raise SystemExit("No path given and no active project is open.")
    cards = Path(proj.settings.asset_folder) / "cards"
    if not cards.is_dir():
        raise SystemExit(f"Active project has no cards/ dir at {cards}")
    return [cards]


def _iter_json(targets: list[Path]):
    for t in targets:
        if t.is_file():
            yield t
        else:
            yield from sorted(t.glob("*.json"))


def _canonical_for(raw: dict) -> str | None:
    """Return the canonical type_line for ``raw``, or None if it can't be parsed.

    Mirrors the validator's ``fix_type_line_order``: build a Card, derive the
    structured parts from the current line, then rebuild the string.
    """
    try:
        card = Card.model_validate(raw)
    except Exception:
        return None
    parsed = _parse_type_line(card)
    return canonical_type_line(parsed)


def _detect_newline(data: bytes) -> str:
    return "\r\n" if b"\r\n" in data else "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "path",
        nargs="?",
        default=None,
        help="cards/ dir, asset folder, or single .json (default: active project)",
    )
    ap.add_argument("--dry-run", action="store_true", help="report changes without writing")
    args = ap.parse_args()

    targets = _resolve_cards_dirs(args.path)

    changed = 0
    scanned = 0
    skipped = 0
    for p in _iter_json(targets):
        scanned += 1
        original = p.read_bytes()
        try:
            raw = json.loads(original.decode("utf-8"))
        except Exception:
            skipped += 1
            print(f"  skip (unparseable JSON): {p.name}")
            continue
        if not isinstance(raw, dict) or "type_line" not in raw:
            continue
        old = raw["type_line"]
        new = _canonical_for(raw)
        if new is None:
            skipped += 1
            print(f"  skip (not a valid Card): {p.name}")
            continue
        if new == old:
            continue

        changed += 1
        print(f"  {p.name}: {old!r} -> {new!r}")
        if not args.dry_run:
            raw["type_line"] = new
            nl = _detect_newline(original)
            text = json.dumps(raw, indent=2, ensure_ascii=False)
            with open(p, "w", encoding="utf-8", newline=nl) as fh:
                fh.write(text)

    verb = "would rewrite" if args.dry_run else "rewrote"
    print(
        f"\nScanned {scanned} file(s) across {len(targets)} target(s): "
        f"{verb} {changed}, skipped {skipped}, unchanged {scanned - changed - skipped}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
