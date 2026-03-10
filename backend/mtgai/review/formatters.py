"""Rich formatting helpers for the review CLI.

Provides table builders, panel renderers, and color-coding utilities
for displaying skeleton slots, cards, and set statistics.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from mtgai.skeleton.generator import (
    COLOR_PAIRS,
    BalanceReport,
    ConstraintResult,
    SetConfig,
    SkeletonSlot,
)

console = Console()

# ---------------------------------------------------------------------------
# Color styling
# ---------------------------------------------------------------------------

COLOR_STYLES: dict[str, str] = {
    "W": "yellow",
    "U": "blue",
    "B": "magenta",
    "R": "red",
    "G": "green",
    "multicolor": "bright_yellow",
    "colorless": "white",
}


def styled_color(color: str) -> Text:
    """Return a Rich Text with the color name styled appropriately."""
    style = COLOR_STYLES.get(color, "white")
    return Text(color, style=style)


# ---------------------------------------------------------------------------
# Slot list table
# ---------------------------------------------------------------------------


def build_slot_table(slots: list[SkeletonSlot]) -> Table:
    """Build a Rich Table showing skeleton slot rows."""
    table = Table(
        title="Skeleton Slots",
        show_lines=False,
        expand=False,
    )
    table.add_column("Slot ID", style="bold cyan", no_wrap=True)
    table.add_column("Color", no_wrap=True)
    table.add_column("Rarity", no_wrap=True)
    table.add_column("Type", no_wrap=True)
    table.add_column("CMC", justify="right", no_wrap=True)
    table.add_column("Mechanic", no_wrap=True)
    table.add_column("Archetypes", no_wrap=False)

    for slot in slots:
        arch_str = ", ".join(slot.archetype_tags) if slot.archetype_tags else "-"
        table.add_row(
            slot.slot_id,
            styled_color(slot.color),
            slot.rarity,
            slot.card_type,
            str(slot.cmc_target),
            slot.mechanic_tag,
            arch_str,
        )

    return table


# ---------------------------------------------------------------------------
# Slot detail panel
# ---------------------------------------------------------------------------


def build_slot_panel(slot: SkeletonSlot, card_data: dict | None = None) -> Panel:
    """Build a Rich Panel showing full detail for a single slot."""
    lines: list[str] = [
        f"[bold]Slot ID:[/bold]     {slot.slot_id}",
        f"[bold]Color:[/bold]       {slot.color}",
        f"[bold]Rarity:[/bold]      {slot.rarity}",
        f"[bold]Card Type:[/bold]   {slot.card_type}",
        f"[bold]CMC Target:[/bold]  {slot.cmc_target}",
        f"[bold]Mechanic:[/bold]    {slot.mechanic_tag}",
        f"[bold]Archetypes:[/bold]  {', '.join(slot.archetype_tags) or '-'}",
    ]

    if slot.color_pair:
        lines.append(f"[bold]Color Pair:[/bold]  {slot.color_pair}")

    if slot.is_reprint_slot:
        lines.append("[bold]Reprint:[/bold]     Yes")

    if slot.notes:
        lines.append(f"[bold]Notes:[/bold]       {slot.notes}")

    if slot.card_id:
        lines.append(f"\n[bold]Card ID:[/bold]     {slot.card_id}")

    if card_data:
        lines.append("")
        lines.append("[bold underline]Generated Card[/bold underline]")
        lines.append(f"  [bold]Name:[/bold]       {card_data.get('name', 'N/A')}")
        lines.append(f"  [bold]Mana Cost:[/bold]  {card_data.get('mana_cost', 'N/A')}")
        lines.append(f"  [bold]Type Line:[/bold]  {card_data.get('type_line', 'N/A')}")
        if card_data.get("oracle_text"):
            lines.append("  [bold]Oracle Text:[/bold]")
            lines.append(f"    {card_data['oracle_text']}")
        if card_data.get("flavor_text"):
            lines.append("  [bold]Flavor:[/bold]")
            lines.append(f"    [italic]{card_data['flavor_text']}[/italic]")
        if card_data.get("power") is not None:
            lines.append(
                f"  [bold]P/T:[/bold]        {card_data.get('power')}/{card_data.get('toughness')}"
            )
        lines.append(f"  [bold]Status:[/bold]     {card_data.get('status', 'N/A')}")

    body = "\n".join(lines)
    style = COLOR_STYLES.get(slot.color, "white")
    return Panel(body, title=f"Slot {slot.slot_id}", border_style=style, expand=False)


# ---------------------------------------------------------------------------
# Stats dashboard
# ---------------------------------------------------------------------------


def build_rarity_table(report: BalanceReport) -> Table:
    """Rarity distribution table."""
    table = Table(title="Rarity Distribution", expand=False)
    table.add_column("Rarity", style="bold")
    table.add_column("Count", justify="right")
    table.add_column("Pct", justify="right")

    total = sum(report.rarity_counts.values()) or 1
    for rarity in ["common", "uncommon", "rare", "mythic"]:
        count = report.rarity_counts.get(rarity, 0)
        pct = count / total * 100
        table.add_row(rarity, str(count), f"{pct:.1f}%")
    table.add_row("[bold]Total[/bold]", f"[bold]{total}[/bold]", "")
    return table


def build_color_table(report: BalanceReport) -> Table:
    """Color distribution table."""
    table = Table(title="Color Distribution", expand=False)
    table.add_column("Color", style="bold")
    table.add_column("Count", justify="right")
    table.add_column("Pct", justify="right")

    total = sum(report.color_counts.values()) or 1
    for color in ["W", "U", "B", "R", "G", "multicolor", "colorless"]:
        count = report.color_counts.get(color, 0)
        pct = count / total * 100
        style = COLOR_STYLES.get(color, "white")
        table.add_row(Text(color, style=style), str(count), f"{pct:.1f}%")
    return table


def build_type_table(report: BalanceReport) -> Table:
    """Type distribution table."""
    table = Table(title="Type Distribution", expand=False)
    table.add_column("Type", style="bold")
    table.add_column("Count", justify="right")
    table.add_column("Pct", justify="right")

    total = sum(report.type_counts.values()) or 1
    for card_type in [
        "creature",
        "instant",
        "sorcery",
        "enchantment",
        "artifact",
        "planeswalker",
        "land",
    ]:
        count = report.type_counts.get(card_type, 0)
        if count:
            pct = count / total * 100
            table.add_row(card_type, str(count), f"{pct:.1f}%")
    return table


def build_cmc_chart(report: BalanceReport) -> Table:
    """ASCII bar chart for CMC distribution using a Rich Table."""
    table = Table(title="CMC Curve", expand=False, show_header=True)
    table.add_column("CMC", justify="right", style="bold", no_wrap=True)
    table.add_column("Count", justify="right", no_wrap=True)
    table.add_column("Distribution", no_wrap=False)

    max_count = max(report.cmc_distribution.values()) if report.cmc_distribution else 1
    bar_width = 40

    for cmc in sorted(report.cmc_distribution):
        count = report.cmc_distribution[cmc]
        bar_len = int(count / max_count * bar_width) if max_count > 0 else 0
        bar = Text("=" * bar_len, style="green")
        table.add_row(str(cmc), str(count), bar)

    return table


def build_archetype_table(
    archetype_slots: dict[str, list[str]],
    theme_data: dict | None = None,
) -> Table:
    """Archetype coverage table."""
    table = Table(title="Archetype Coverage", expand=False)
    table.add_column("Pair", style="bold", no_wrap=True)
    table.add_column("Name", no_wrap=True)
    table.add_column("Slots", justify="right", no_wrap=True)

    # Build lookup for archetype names from theme data
    arch_names: dict[str, str] = {}
    if theme_data and "draft_archetypes" in theme_data:
        for arch in theme_data["draft_archetypes"]:
            arch_names[arch["color_pair"]] = arch["name"]

    for pair in COLOR_PAIRS:
        slot_ids = archetype_slots.get(pair, [])
        name = arch_names.get(pair, "")
        table.add_row(pair, name, str(len(slot_ids)))

    return table


def build_constraints_table(constraints: list[ConstraintResult]) -> Table:
    """Constraint check summary table."""
    table = Table(title="Constraint Checks", expand=False)
    table.add_column("Status", no_wrap=True, justify="center")
    table.add_column("Type", no_wrap=True)
    table.add_column("Name", no_wrap=True)
    table.add_column("Message", no_wrap=False)

    for c in constraints:
        status = Text("PASS", style="bold green") if c.passed else Text("FAIL", style="bold red")
        kind = "HARD" if c.is_hard else "SOFT"
        table.add_row(status, kind, c.name, c.message)

    return table


def build_stats_header(config: SetConfig, total_slots: int, theme_data: dict | None = None) -> str:
    """Build a header string for the stats dashboard."""
    lines = [
        f"[bold]{config.name}[/bold] [{config.code}]",
        f"Theme: {config.theme}",
        f"Total slots: {total_slots}",
    ]
    if theme_data and "flavor_description" in theme_data:
        desc = theme_data["flavor_description"]
        # Truncate long descriptions
        if len(desc) > 200:
            desc = desc[:200] + "..."
        lines.append(f"Flavor: [italic]{desc}[/italic]")
    return "\n".join(lines)
