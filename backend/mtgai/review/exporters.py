"""Export finished card data out of the pipeline.

Three formats, surfaced as ``review export csv|json|print``:

* **csv**   — flat spreadsheet, one row per card, key fields only.
* **json**  — single file whose top-level value is ``list[Card.model_dump()]``
  (the full, lossless card data).
* **print** — copies each card's rendered PNG into a flat directory ready to
  upload to a print service.

These are pure functions: they take an explicit ``list[Card]`` (and, for print,
an explicit renders directory) and write only the requested output. The CLI is
the only layer that resolves the active project's asset folder. Cockatrice XML
export is intentionally deferred to Phase 5.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from pydantic import BaseModel

from mtgai.io.paths import card_slug
from mtgai.models.card import Card

# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

# Flat column order for the CSV export. One row per card.
CSV_COLUMNS: list[str] = [
    "collector_number",
    "name",
    "mana_cost",
    "cmc",
    "color_identity",
    "rarity",
    "type_line",
    "power",
    "toughness",
    "loyalty",
    "oracle_text",
    "flavor_text",
    "is_reprint",
    "mechanic_tags",
    "set_code",
]

# List fields are joined with this separator so cells stay single-valued and
# never collide with CSV's comma delimiter.
_LIST_SEP = ";"


def _cell(value: object) -> str:
    """Render a scalar card field as a CSV cell string.

    ``None`` becomes an empty string, bools become ``true``/``false``, and a
    whole-number float CMC becomes an int (``3`` not ``3.0``).
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def card_to_row(card: Card) -> dict[str, str]:
    """Flatten one card into a dict of CSV cell strings keyed by ``CSV_COLUMNS``."""
    return {
        "collector_number": _cell(card.collector_number),
        "name": _cell(card.name),
        "mana_cost": _cell(card.mana_cost),
        "cmc": _cell(card.cmc),
        "color_identity": _LIST_SEP.join(c.value for c in card.color_identity),
        "rarity": _cell(card.rarity.value),
        "type_line": _cell(card.type_line),
        "power": _cell(card.power),
        "toughness": _cell(card.toughness),
        "loyalty": _cell(card.loyalty),
        "oracle_text": _cell(card.oracle_text),
        "flavor_text": _cell(card.flavor_text),
        "is_reprint": _cell(card.is_reprint),
        "mechanic_tags": _LIST_SEP.join(card.mechanic_tags),
        "set_code": _cell(card.set_code),
    }


def export_csv(cards: list[Card], out_path: Path) -> int:
    """Write ``cards`` to ``out_path`` as UTF-8 CSV. Returns the row count.

    One header row plus one row per card, in the column order of ``CSV_COLUMNS``.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for card in cards:
            writer.writerow(card_to_row(card))
    return len(cards)


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def export_json(cards: list[Card], out_path: Path) -> int:
    """Write ``cards`` to ``out_path`` as a single JSON file. Returns the count.

    The top-level value is a JSON array of ``Card.model_dump(mode="json")``
    objects (full, lossless card data). ``mode="json"`` ensures enums and
    datetimes serialize to strings.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [card.model_dump(mode="json") for card in cards]
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(cards)


# ---------------------------------------------------------------------------
# Print (copy renders to a flat dir)
# ---------------------------------------------------------------------------


class PrintExportResult(BaseModel):
    """Outcome of a print export.

    ``copied`` and ``missing`` hold collector numbers; ``out_dir`` is where the
    copied PNGs landed.
    """

    out_dir: str
    copied: list[str] = []
    missing: list[str] = []

    @property
    def copied_count(self) -> int:
        return len(self.copied)

    @property
    def missing_count(self) -> int:
        return len(self.missing)


def _resolve_render(card: Card, renders_dir: Path) -> Path | None:
    """Return the source render PNG for ``card``, or None if it can't be found.

    Prefers ``card.render_path`` when it points at an existing file (absolute,
    or relative to ``renders_dir``'s parent — the project asset folder), then
    falls back to ``renders_dir/<slug>.png``.
    """
    if card.render_path:
        candidate = Path(card.render_path)
        if not candidate.is_absolute():
            candidate = renders_dir.parent / card.render_path
        if candidate.exists():
            return candidate

    fallback = renders_dir / f"{card_slug(card.collector_number, card.name)}.png"
    if fallback.exists():
        return fallback
    return None


def export_print(cards: list[Card], renders_dir: Path, out_dir: Path) -> PrintExportResult:
    """Copy each card's rendered PNG into a flat ``out_dir``.

    Cards without a discoverable render are recorded in ``missing`` (not fatal).
    The copied file keeps its source filename (the card slug), so the directory
    is ready to upload to a print service. Re-running overwrites existing copies.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    result = PrintExportResult(out_dir=str(out_dir))
    for card in cards:
        source = _resolve_render(card, renders_dir)
        if source is None:
            result.missing.append(card.collector_number)
            continue
        shutil.copy2(source, out_dir / source.name)
        result.copied.append(card.collector_number)
    return result
