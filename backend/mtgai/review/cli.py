"""Typer CLI app for reviewing skeleton slots and generated cards.

Commands:
  list   — Filter and list skeleton slots
  show   — Show detail for a single slot/card
  stats  — Set-level statistics dashboard
  export — Export finished cards (csv / json / print)

Phase 3A stubs:
  approve, reject, flag, compare, art, gallery
"""

import logging
from typing import Annotated

import typer
from rich.console import Console

from mtgai.review.formatters import (
    build_archetype_table,
    build_cmc_chart,
    build_color_table,
    build_constraints_table,
    build_rarity_table,
    build_slot_panel,
    build_slot_table,
    build_stats_header,
    build_type_table,
)
from mtgai.review.loaders import load_cards_raw, load_skeleton, load_theme
from mtgai.skeleton.generator import SkeletonResult

app = typer.Typer(
    name="review",
    help="MTG AI Set Review CLI -- inspect skeleton slots, cards, and set statistics.",
    no_args_is_help=True,
)

console = Console()

# The review CLI is set-agnostic: artifact paths resolve through the active
# project's asset_folder (``set_artifact_dir``), so ``--set`` is only the
# display label. When omitted it falls back to the active project's set_code,
# then to a neutral placeholder — never a hardcoded example set.
SetOption = Annotated[
    str | None,
    typer.Option("--set", "-s", help="Set code label (defaults to the active project)."),
]


def _resolve_set_code(set_code: str | None) -> str:
    """Resolve the display set code from the flag, the active project, or a placeholder."""
    if set_code:
        return set_code
    from mtgai.runtime.runtime_state import resolve_active_set_code

    return resolve_active_set_code() or "SET"


# ---------------------------------------------------------------------------
# review list
# ---------------------------------------------------------------------------


@app.command("list")
def list_slots(
    set_code: SetOption = None,
    color: Annotated[
        str | None,
        typer.Option(
            "--color",
            "-c",
            help="Filter by color (W/U/B/R/G/multicolor/colorless).",
        ),
    ] = None,
    rarity: Annotated[
        str | None,
        typer.Option(
            "--rarity",
            "-r",
            help="Filter by rarity (common/uncommon/rare/mythic).",
        ),
    ] = None,
    card_type: Annotated[
        str | None,
        typer.Option(
            "--type",
            "-t",
            help="Filter by card type (creature/instant/sorcery/enchantment/artifact).",
        ),
    ] = None,
    cmc: Annotated[
        str | None,
        typer.Option(help="Filter by CMC (exact number or '4+' for >= 4)."),
    ] = None,
    mechanic: Annotated[
        str | None,
        typer.Option(
            "--mechanic",
            "-m",
            help="Filter by mechanic tag (vanilla/french_vanilla/evergreen/complex).",
        ),
    ] = None,
    archetype: Annotated[
        str | None,
        typer.Option(
            "--archetype",
            "-a",
            help="Filter by archetype tag (e.g., WU, BR).",
        ),
    ] = None,
    sort_by: Annotated[
        str,
        typer.Option(
            "--sort",
            help="Sort by field (slot_id/color/cmc/rarity/type).",
        ),
    ] = "slot_id",
) -> None:
    """Filter and list skeleton slots (and generated cards when available)."""
    try:
        result = load_skeleton(set_code)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    slots = list(result.slots)

    # --- Filters ---
    if color is not None:
        color_val = color.strip()
        slots = [s for s in slots if s.color == color_val]

    if rarity is not None:
        rarity_val = rarity.strip().lower()
        slots = [s for s in slots if s.rarity == rarity_val]

    if card_type is not None:
        type_val = card_type.strip().lower()
        slots = [s for s in slots if s.card_type == type_val]

    if cmc is not None:
        cmc_str = cmc.strip()
        if cmc_str.endswith("+"):
            cmc_min = int(cmc_str[:-1])
            slots = [s for s in slots if s.cmc_target >= cmc_min]
        else:
            cmc_exact = int(cmc_str)
            slots = [s for s in slots if s.cmc_target == cmc_exact]

    if mechanic is not None:
        mech_val = mechanic.strip().lower()
        slots = [s for s in slots if s.mechanic_tag == mech_val]

    if archetype is not None:
        arch_val = archetype.strip().upper()
        slots = [s for s in slots if arch_val in s.archetype_tags]

    # --- Sort ---
    rarity_order = {"common": 0, "uncommon": 1, "rare": 2, "mythic": 3}
    sort_keys = {
        "slot_id": lambda s: s.slot_id,
        "color": lambda s: s.color,
        "cmc": lambda s: s.cmc_target,
        "rarity": lambda s: rarity_order.get(s.rarity, 99),
        "type": lambda s: s.card_type,
    }
    key_fn = sort_keys.get(sort_by, sort_keys["slot_id"])
    slots.sort(key=key_fn)

    # --- Display ---
    if not slots:
        console.print("[yellow]No slots match the given filters.[/yellow]")
        raise typer.Exit(0)

    table = build_slot_table(slots)
    console.print(table)
    console.print(f"\n[bold]{len(slots)}[/bold] slot(s) shown.")


# ---------------------------------------------------------------------------
# review show
# ---------------------------------------------------------------------------


@app.command("show")
def show_slot(
    slot_id: Annotated[str, typer.Argument(help="Slot ID to show (e.g., W-C-01).")],
    set_code: SetOption = None,
) -> None:
    """Show detail for a single skeleton slot or generated card."""
    set_code = _resolve_set_code(set_code)
    try:
        result = load_skeleton(set_code)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    # Find the slot
    target_id = slot_id.strip().upper()
    match = None
    for s in result.slots:
        if s.slot_id.upper() == target_id:
            match = s
            break

    if match is None:
        console.print(f"[red]Error:[/red] Slot '{slot_id}' not found in set {set_code}.")
        # Suggest similar slots
        prefix = target_id.split("-")[0] if "-" in target_id else ""
        similar = [s.slot_id for s in result.slots if s.slot_id.startswith(prefix)][:5]
        if similar:
            console.print(f"  Did you mean: {', '.join(similar)}?")
        raise typer.Exit(1)

    # Try to find a generated card for this slot
    card_data: dict | None = None
    if match.card_id:
        cards = load_cards_raw(set_code)
        for card in cards:
            if card.get("slot_id") == match.slot_id or card.get("id") == match.card_id:
                card_data = card
                break

    panel = build_slot_panel(match, card_data)
    console.print(panel)


# ---------------------------------------------------------------------------
# review stats
# ---------------------------------------------------------------------------


@app.command("stats")
def show_stats(
    set_code: SetOption = None,
    detailed: Annotated[
        bool, typer.Option("--detailed", "-d", help="Show per-color breakdown.")
    ] = False,
) -> None:
    """Show set-level statistics dashboard."""
    set_code = _resolve_set_code(set_code)
    try:
        result = load_skeleton(set_code)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    theme_data = load_theme(set_code)
    report = result.balance_report

    # Header
    header = build_stats_header(result.config, result.total_slots, theme_data)
    console.print()
    console.print(header)
    console.print()

    # Rarity distribution
    console.print(build_rarity_table(report))
    console.print()

    # Color distribution
    console.print(build_color_table(report))
    console.print()

    # Type distribution
    console.print(build_type_table(report))
    console.print()

    # CMC curve
    console.print(build_cmc_chart(report))
    console.print()

    # Archetype coverage
    console.print(build_archetype_table(result.archetype_slots, theme_data))
    console.print()

    # Constraint checks
    console.print(build_constraints_table(report.constraints))
    console.print()

    all_hard = report.all_hard_passed
    status = "[bold green]PASS[/bold green]" if all_hard else "[bold red]FAIL[/bold red]"
    console.print(f"All hard constraints: {status}")
    console.print(
        f"Creature %: [bold]{report.creature_pct:.1f}%[/bold]  |  "
        f"Average CMC: [bold]{report.average_cmc:.2f}[/bold]"
    )

    # Detailed per-color breakdown
    if detailed:
        console.print()
        _print_per_color_breakdown(result)


def _print_per_color_breakdown(result: SkeletonResult) -> None:
    """Print per-color slot details."""
    from rich.table import Table

    from mtgai.skeleton.generator import COLORS

    colors = [*COLORS, "multicolor", "colorless"]

    for color in colors:
        color_slots = [s for s in result.slots if s.color == color]
        if not color_slots:
            continue

        table = Table(
            title=f"[bold]{color}[/bold] ({len(color_slots)} slots)",
            expand=False,
        )
        table.add_column("Rarity")
        table.add_column("Type")
        table.add_column("CMC", justify="right")
        table.add_column("Mechanic")

        # Count by rarity
        rarity_counts: dict[str, int] = {}
        type_counts: dict[str, int] = {}
        for s in color_slots:
            rarity_counts[s.rarity] = rarity_counts.get(s.rarity, 0) + 1
            type_counts[s.card_type] = type_counts.get(s.card_type, 0) + 1

        for s in sorted(color_slots, key=lambda x: x.slot_id):
            table.add_row(s.rarity, s.card_type, str(s.cmc_target), s.mechanic_tag)

        console.print(table)
        console.print(f"  Rarity: {rarity_counts}  |  Types: {type_counts}")
        console.print()


# ---------------------------------------------------------------------------
# review ai-review (Phase 4B)
# ---------------------------------------------------------------------------


@app.command("ai-review")
def ai_review(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show plan without calling LLM.")
    ] = False,
    card: Annotated[
        str | None,
        typer.Option("--card", "-c", help="Review only this collector number (e.g. W-C-01)."),
    ] = None,
    include_lands: Annotated[
        bool, typer.Option("--include-lands", help="Include basic lands in review.")
    ] = False,
    include_reprints: Annotated[
        bool, typer.Option("--include-reprints", help="Include reprints in review.")
    ] = False,
) -> None:
    """Run AI design review on generated cards (Phase 4B)."""
    from mtgai.review.ai_review import review_set

    review_set(
        dry_run=dry_run,
        card_filter=card,
        skip_lands=not include_lands,
        skip_reprints=not include_reprints,
    )


# ---------------------------------------------------------------------------
# review finalize (post-review)
# ---------------------------------------------------------------------------


@app.command("finalize")
def finalize(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show what would change without saving.")
    ] = False,
    card: Annotated[
        str | None,
        typer.Option("--card", "-c", help="Finalize only this card (e.g. W-C-01)."),
    ] = None,
) -> None:
    """Post-review finalization: inject reminder text, re-validate, auto-fix."""
    import logging

    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.review.finalize import finalize_set

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    summary = finalize_set(dry_run=dry_run, card_filter=card)

    # Rich summary
    console.print()
    console.print(f"[bold]Finalization {'(dry run) ' if dry_run else ''}complete[/bold]")
    console.print(
        f"  Cards processed: {summary['total_cards']}  |  Modified: {summary['cards_modified']}"
    )
    console.print(
        f"  Auto-fixes: [green]{summary['total_auto_fixes']}[/green]  |  "
        f"MANUAL errors: [yellow]{summary['total_manual_errors']}[/yellow]"
    )

    if summary["total_manual_errors"] > 0:
        console.print()
        console.print(
            f"[yellow]MANUAL errors found — see "
            f"{set_artifact_dir() / 'reports' / 'finalize-report.md'}[/yellow]"
        )


# ---------------------------------------------------------------------------
# review serve (Phase 3B — review server)
# ---------------------------------------------------------------------------


@app.command("serve")
def serve(
    port: Annotated[int, typer.Option("--port", "-p", help="Server port.")] = 8080,
    open_browser: Annotated[bool, typer.Option("--open", help="Open browser on startup.")] = False,
) -> None:
    """Start the local review server (FastAPI + uvicorn).

    The active project is chosen in the wizard (New / Open), not on the CLI;
    artifact paths resolve from the open project's asset folder.
    """
    import threading
    import webbrowser

    import uvicorn

    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    console.print(f"[bold]Starting MTGAI server on port {port}...[/bold]")
    console.print(f"  Wizard:   http://localhost:{port}/pipeline")
    console.print(f"  Settings: http://localhost:{port}/settings")
    console.print("[dim]Press Ctrl+C to stop.[/dim]")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    uvicorn.run("mtgai.review.server:app", host="127.0.0.1", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# review export (CSV / JSON / print)
# ---------------------------------------------------------------------------

export_app = typer.Typer(
    name="export",
    help="Export finished cards to CSV, JSON, or a flat directory of renders.",
    no_args_is_help=True,
)
app.add_typer(export_app, name="export")


def _load_cards_for_export(set_code: str):
    """Load cards for export, surfacing path errors as a clean CLI exit.

    Returns the loaded cards. Exits 1 if no project/asset folder is open.
    """
    from mtgai.io.asset_paths import NoAssetFolderError
    from mtgai.review.loaders import load_cards

    try:
        return load_cards(set_code)
    except NoAssetFolderError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


@export_app.command("csv")
def export_csv_cmd(
    set_code: SetOption = None,
    out: Annotated[str, typer.Option("--out", "-o", help="Output CSV file path.")] = "cards.csv",
) -> None:
    """Export cards to a flat CSV spreadsheet (one row per card, key fields)."""
    from pathlib import Path

    from mtgai.review.exporters import export_csv

    set_code = _resolve_set_code(set_code)
    cards = _load_cards_for_export(set_code)
    if not cards:
        console.print(f"[yellow]No cards found for set {set_code}; nothing to export.[/yellow]")
        raise typer.Exit(0)

    out_path = Path(out)
    count = export_csv(cards, out_path)
    console.print(f"[green]Exported {count} card(s)[/green] to {out_path}")


@export_app.command("json")
def export_json_cmd(
    set_code: SetOption = None,
    out: Annotated[str, typer.Option("--out", "-o", help="Output JSON file path.")] = "cards.json",
) -> None:
    """Export full card data to a single JSON file (list of card objects)."""
    from pathlib import Path

    from mtgai.review.exporters import export_json

    set_code = _resolve_set_code(set_code)
    cards = _load_cards_for_export(set_code)
    if not cards:
        console.print(f"[yellow]No cards found for set {set_code}; nothing to export.[/yellow]")
        raise typer.Exit(0)

    out_path = Path(out)
    count = export_json(cards, out_path)
    console.print(f"[green]Exported {count} card(s)[/green] to {out_path}")


@export_app.command("print")
def export_print_cmd(
    set_code: SetOption = None,
    out: Annotated[
        str, typer.Option("--out", "-o", help="Output directory for copied renders.")
    ] = "print/",
) -> None:
    """Copy all rendered card PNGs into a flat directory for print upload."""
    from pathlib import Path

    from mtgai.io.asset_paths import NoAssetFolderError, set_artifact_dir
    from mtgai.review.exporters import export_print

    set_code = _resolve_set_code(set_code)
    cards = _load_cards_for_export(set_code)
    if not cards:
        console.print(f"[yellow]No cards found for set {set_code}; nothing to export.[/yellow]")
        raise typer.Exit(0)

    try:
        renders_dir = set_artifact_dir() / "renders"
    except NoAssetFolderError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    out_dir = Path(out)
    result = export_print(cards, renders_dir, out_dir)
    console.print(
        f"[green]Copied {result.copied_count} render(s)[/green] to {out_dir}"
        f"  |  [yellow]Missing: {result.missing_count}[/yellow]"
    )
    if result.missing:
        preview = ", ".join(result.missing[:10])
        more = "" if result.missing_count <= 10 else f" (+{result.missing_count - 10} more)"
        console.print(f"[dim]No render for:[/dim] {preview}{more}")


# ---------------------------------------------------------------------------
# Phase 3A stubs
# ---------------------------------------------------------------------------


@app.command("approve")
def approve() -> None:
    """Approve a generated card. (Phase 3A)"""
    console.print("[yellow]Not yet implemented -- Phase 3A[/yellow]")


@app.command("reject")
def reject() -> None:
    """Reject a generated card with feedback. (Phase 3A)"""
    console.print("[yellow]Not yet implemented -- Phase 3A[/yellow]")


@app.command("flag")
def flag() -> None:
    """Flag a card for further review. (Phase 3A)"""
    console.print("[yellow]Not yet implemented -- Phase 3A[/yellow]")


@app.command("compare")
def compare() -> None:
    """Compare multiple generation attempts for a card. (Phase 3A)"""
    console.print("[yellow]Not yet implemented -- Phase 3A[/yellow]")


@app.command("art")
def art() -> None:
    """View or regenerate art for a card. (Phase 3A)"""
    console.print("[yellow]Not yet implemented -- Phase 3A[/yellow]")


@app.command("gallery")
def gallery() -> None:
    """View a gallery of generated cards. (Phase 3A)"""
    console.print("[yellow]Not yet implemented -- Phase 3A[/yellow]")
