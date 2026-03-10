"""Typer CLI app for reviewing skeleton slots and generated cards.

Commands:
  list   — Filter and list skeleton slots
  show   — Show detail for a single slot/card
  stats  — Set-level statistics dashboard

Phase 3A stubs:
  approve, reject, flag, compare, export, art, gallery
"""

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
from mtgai.review.loaders import load_cards, load_skeleton, load_theme
from mtgai.skeleton.generator import SkeletonResult

app = typer.Typer(
    name="review",
    help="MTG AI Set Review CLI -- inspect skeleton slots, cards, and set statistics.",
    no_args_is_help=True,
)

console = Console()


# ---------------------------------------------------------------------------
# review list
# ---------------------------------------------------------------------------


@app.command("list")
def list_slots(
    set_code: Annotated[str, typer.Option("--set", "-s", help="Set code to review.")] = "ASD",
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
    set_code: Annotated[str, typer.Option("--set", "-s", help="Set code to review.")] = "ASD",
) -> None:
    """Show detail for a single skeleton slot or generated card."""
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
        cards = load_cards(set_code)
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
    set_code: Annotated[str, typer.Option("--set", "-s", help="Set code to review.")] = "ASD",
    detailed: Annotated[
        bool, typer.Option("--detailed", "-d", help="Show per-color breakdown.")
    ] = False,
) -> None:
    """Show set-level statistics dashboard."""
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


@app.command("export")
def export() -> None:
    """Export cards for print or Tabletop Simulator. (Phase 3A)"""
    console.print("[yellow]Not yet implemented -- Phase 3A[/yellow]")


@app.command("art")
def art() -> None:
    """View or regenerate art for a card. (Phase 3A)"""
    console.print("[yellow]Not yet implemented -- Phase 3A[/yellow]")


@app.command("gallery")
def gallery() -> None:
    """View a gallery of generated cards. (Phase 3A)"""
    console.print("[yellow]Not yet implemented -- Phase 3A[/yellow]")
