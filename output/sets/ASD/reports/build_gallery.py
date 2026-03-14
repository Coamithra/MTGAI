"""
Build a self-contained HTML gallery for all ASD set cards with review annotations.

Reads card JSONs from output/sets/ASD/cards/ and review JSONs from output/sets/ASD/reviews/,
plus the finalize-report.md for auto-fix/MANUAL error data.  Produces a single HTML file
with inline CSS/JS that renders each card in an MTG-style frame with reviewer comments below.

Usage:
    python build_gallery.py
"""

from __future__ import annotations

import json
import re
import html
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent.parent  # output/sets/ASD
CARDS_DIR = BASE / "cards"
REVIEWS_DIR = BASE / "reviews"
FINALIZE_REPORT = BASE / "reports" / "finalize-report.md"
OUTPUT_HTML = BASE / "reports" / "card-review-gallery.html"

# ---------------------------------------------------------------------------
# Color ordering helpers
# ---------------------------------------------------------------------------
COLOR_ORDER = ["W", "U", "B", "R", "G"]
RARITY_ORDER = {"mythic": 0, "rare": 1, "uncommon": 2, "common": 3}


def color_sort_key(card: dict) -> tuple:
    """Sort key: mono colors in WUBRG, then multi (by first color), then colorless, then land."""
    colors = card.get("colors") or []
    cn = card.get("collector_number", "")
    rarity_rank = RARITY_ORDER.get(card.get("rarity", "common"), 9)

    if cn.startswith("L-"):
        return (7, 0, rarity_rank, cn)
    if not colors:
        # Colorless / artifact
        return (6, 0, rarity_rank, cn)
    if len(colors) == 1:
        idx = COLOR_ORDER.index(colors[0]) if colors[0] in COLOR_ORDER else 5
        return (idx, 0, rarity_rank, cn)
    # Multicolor – sort by first color index
    first = min(COLOR_ORDER.index(c) for c in colors if c in COLOR_ORDER) if colors else 5
    return (5, first, rarity_rank, cn)


def color_group(card: dict) -> str:
    """Return a group label for nav/filtering."""
    colors = card.get("colors") or []
    cn = card.get("collector_number", "")
    tl = card.get("type_line", "")
    if cn.startswith("L-") or "Land" in tl and not colors:
        return "Land"
    if not colors:
        return "Colorless"
    if len(colors) > 1:
        return "Multi"
    return {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}.get(
        colors[0], "Colorless"
    )


# ---------------------------------------------------------------------------
# Parse finalize report
# ---------------------------------------------------------------------------
def parse_finalize_report(path: Path) -> dict:
    """Return {collector_number: {auto_fixes: [...], manual_errors: [...]}}."""
    result: dict[str, dict] = {}
    if not path.exists():
        return result

    text = path.read_text(encoding="utf-8")
    current_section = None  # "auto" or "manual"
    current_cn = None

    for line in text.splitlines():
        if line.startswith("## Auto-Fixes Applied"):
            current_section = "auto"
            continue
        if line.startswith("## MANUAL Errors"):
            current_section = "manual"
            continue
        if line.startswith("## ") and current_section:
            current_section = None
            continue

        m = re.match(r"^### (\S+)\s+", line)
        if m:
            current_cn = m.group(1)
            if current_cn not in result:
                result[current_cn] = {"auto_fixes": [], "manual_errors": []}
            continue

        if current_cn and line.startswith("- ") and current_section:
            text_content = line[2:].strip()
            if current_section == "auto":
                result[current_cn]["auto_fixes"].append(text_content)
            elif current_section == "manual":
                result[current_cn]["manual_errors"].append(text_content)

    return result


# ---------------------------------------------------------------------------
# Mana symbol rendering
# ---------------------------------------------------------------------------
MANA_COLORS = {
    "W": "#F9FAF4",
    "U": "#0E68AB",
    "B": "#150B00",
    "R": "#D3202A",
    "G": "#00733E",
    "C": "#A8A8A8",
    "X": "#A8A8A8",
    "T": "#6B6B6B",
}


def mana_symbol_html(symbol: str) -> str:
    """Convert a single mana symbol like W, U, 2, X, T to an HTML span."""
    s = symbol.strip()
    if s == "T":
        return (
            '<span class="mana-sym mana-tap" title="Tap">'
            '<span class="tap-arrow">&#8634;</span></span>'
        )
    if s.isdigit():
        return f'<span class="mana-sym mana-generic" title="{s}">{s}</span>'
    bg = MANA_COLORS.get(s, "#A8A8A8")
    text_color = "#000" if s in ("W",) else "#fff" if s in ("U", "B", "R", "G") else "#000"
    return (
        f'<span class="mana-sym" style="background:{bg};color:{text_color}" '
        f'title="{s}">{s}</span>'
    )


def render_mana_cost(mana_cost: str | None) -> str:
    """Render a mana cost string like {2}{W}{U} into HTML spans."""
    if not mana_cost:
        return ""
    symbols = re.findall(r"\{([^}]+)\}", mana_cost)
    return "".join(mana_symbol_html(s) for s in symbols)


def render_text_with_mana(text: str, card_name: str = "") -> str:
    """Render oracle/flavor text, replacing mana symbols and ~ with card name."""
    if not text:
        return ""
    # Replace ~ with card name
    text = text.replace("~", card_name)
    # Escape HTML
    text = html.escape(text)
    # Replace mana symbols
    def mana_repl(m):
        return mana_symbol_html(m.group(1))
    text = re.sub(r"\{([^}]+)\}", mana_repl, text)
    # Replace \n with <br>
    text = text.replace("\\n", "<br>")
    text = text.replace("\n", "<br>")
    return text


# ---------------------------------------------------------------------------
# Card frame color
# ---------------------------------------------------------------------------
FRAME_COLORS = {
    "W": {"border": "#C5B678", "bg": "#F8F4E8", "title_bg": "#ECDFA0", "text_bg": "#F5F0E0"},
    "U": {"border": "#0E68AB", "bg": "#C4DBEF", "title_bg": "#5B9BD5", "text_bg": "#D6E6F5"},
    "B": {"border": "#3D3229", "bg": "#B8A99A", "title_bg": "#6B5C4F", "text_bg": "#C9BEB0"},
    "R": {"border": "#D3202A", "bg": "#E8C4A8", "title_bg": "#D4715C", "text_bg": "#F0D6C4"},
    "G": {"border": "#00733E", "bg": "#C4D8B8", "title_bg": "#5BA05A", "text_bg": "#D4E4CC"},
    "Multi": {"border": "#C9A652", "bg": "#E8D9A0", "title_bg": "#C9A652", "text_bg": "#F0E6C0"},
    "Colorless": {
        "border": "#A8A8A8",
        "bg": "#D8D8D8",
        "title_bg": "#B0B0B0",
        "text_bg": "#E0E0E0",
    },
    "Land": {"border": "#A67C52", "bg": "#D4C4A0", "title_bg": "#A67C52", "text_bg": "#E0D8C0"},
}


def get_frame_colors(card: dict) -> dict:
    group = color_group(card)
    mapping = {
        "White": "W",
        "Blue": "U",
        "Black": "B",
        "Red": "R",
        "Green": "G",
        "Multi": "Multi",
        "Colorless": "Colorless",
        "Land": "Land",
    }
    return FRAME_COLORS.get(mapping.get(group, "Colorless"), FRAME_COLORS["Colorless"])


# ---------------------------------------------------------------------------
# Art placeholder gradient
# ---------------------------------------------------------------------------
ART_GRADIENTS = {
    "W": "linear-gradient(135deg, #faf5e4 0%, #e8d9a0 40%, #f5edd5 100%)",
    "U": "linear-gradient(135deg, #1a4a7a 0%, #2980b9 40%, #5dade2 100%)",
    "B": "linear-gradient(135deg, #1a1a2e 0%, #3d3229 40%, #2c2c2c 100%)",
    "R": "linear-gradient(135deg, #922b21 0%, #d35400 40%, #e74c3c 100%)",
    "G": "linear-gradient(135deg, #1e5631 0%, #27ae60 40%, #2ecc71 100%)",
    "Multi": "linear-gradient(135deg, #c9a652 0%, #d4a843 30%, #a67c52 60%, #c9a652 100%)",
    "Colorless": "linear-gradient(135deg, #7f8c8d 0%, #bdc3c7 40%, #95a5a6 100%)",
    "Land": "linear-gradient(135deg, #6d4c2e 0%, #a67c52 40%, #c9a06a 100%)",
}


def get_art_gradient(card: dict) -> str:
    group = color_group(card)
    mapping = {
        "White": "W",
        "Blue": "U",
        "Black": "B",
        "Red": "R",
        "Green": "G",
        "Multi": "Multi",
        "Colorless": "Colorless",
        "Land": "Land",
    }
    return ART_GRADIENTS.get(mapping.get(group, "Colorless"), ART_GRADIENTS["Colorless"])


# ---------------------------------------------------------------------------
# Rarity colors
# ---------------------------------------------------------------------------
RARITY_COLORS = {
    "common": "#1a1a1a",
    "uncommon": "#9CA5AE",
    "rare": "#C9A652",
    "mythic": "#D45A28",
}

RARITY_LABELS = {
    "common": "Common",
    "uncommon": "Uncommon",
    "rare": "Rare",
    "mythic": "Mythic Rare",
}


# ---------------------------------------------------------------------------
# Build single card HTML
# ---------------------------------------------------------------------------
def build_card_html(card: dict, review: dict | None, finalize_info: dict | None) -> str:
    """Generate the HTML for one card + review section."""
    cn = card.get("collector_number", "???")
    name = card.get("name", "Unknown")
    mana_cost = card.get("mana_cost")
    type_line = (card.get("type_line") or "").replace(" -- ", " \u2014 ")
    oracle = card.get("oracle_text") or ""
    flavor = card.get("flavor_text") or ""
    power = card.get("power")
    toughness = card.get("toughness")
    loyalty = card.get("loyalty")
    rarity = card.get("rarity", "common")
    is_reprint = card.get("is_reprint", False)
    design_notes = card.get("design_notes") or ""
    group = color_group(card)

    frame = get_frame_colors(card)
    art_grad = get_art_gradient(card)
    rarity_color = RARITY_COLORS.get(rarity, "#1a1a1a")
    rarity_label = RARITY_LABELS.get(rarity, rarity)

    # Mana cost HTML
    mana_html = render_mana_cost(mana_cost)

    # Oracle text: split into lines, render reminder text in italics
    oracle_html = ""
    if oracle:
        rendered = render_text_with_mana(oracle, name)
        # Make parenthesized text italic (reminder text)
        rendered = re.sub(
            r"\(([^)]{15,})\)", r'<span class="reminder-text">(\1)</span>', rendered
        )
        oracle_html = f'<div class="card-oracle">{rendered}</div>'

    # Flavor text
    flavor_html = ""
    if flavor:
        escaped_flavor = html.escape(flavor)
        flavor_html = f'<div class="card-flavor">{escaped_flavor}</div>'

    # P/T or Loyalty box
    pt_html = ""
    if power is not None and toughness is not None:
        pt_html = f'<div class="card-pt">{html.escape(str(power))}/{html.escape(str(toughness))}</div>'
    elif loyalty is not None:
        pt_html = f'<div class="card-pt card-loyalty">{html.escape(str(loyalty))}</div>'

    # --- Review section ---
    review_html = build_review_html(cn, name, review, finalize_info, is_reprint)

    # Data attributes for filtering
    colors_data = ",".join(card.get("colors") or [])
    filter_group = group.lower()

    card_id = cn.replace("-", "_")

    return f"""
    <div class="card-entry" id="card-{card_id}"
         data-group="{filter_group}" data-rarity="{rarity}"
         data-colors="{colors_data}" data-cn="{html.escape(cn)}"
         data-changed="{'true' if review and review.get('card_was_changed') else 'false'}"
         data-has-issues="{'true' if (review and (review.get('final_issues') or (finalize_info and (finalize_info.get('manual_errors') or finalize_info.get('auto_fixes'))))) else 'false'}">
      <div class="card-anchor-target"></div>

      <!-- MTG Card Frame -->
      <div class="mtg-card" style="border-color: {frame['border']}; background: {frame['bg']}">
        <div class="card-inner" style="border-color: {frame['border']}">
          <!-- Title Bar -->
          <div class="card-title-bar" style="background: {frame['title_bg']}">
            <span class="card-name">{html.escape(name)}</span>
            <span class="card-mana-cost">{mana_html}</span>
          </div>

          <!-- Art Box -->
          <div class="card-art-box" style="background: {art_grad}">
            <div class="art-placeholder-text">{html.escape(cn)}</div>
          </div>

          <!-- Type Line -->
          <div class="card-type-bar" style="background: {frame['title_bg']}">
            <span class="card-type">{html.escape(type_line)}</span>
            <span class="card-rarity-gem" style="background: {rarity_color}"
                  title="{rarity_label}"></span>
          </div>

          <!-- Text Box -->
          <div class="card-text-box" style="background: {frame['text_bg']}">
            {oracle_html}
            {('<div class="flavor-separator"></div>' + flavor_html) if flavor else ""}
            {('<div class="card-text-empty">&#8203;</div>' if not oracle and not flavor else "")}
          </div>

          <!-- P/T Box -->
          {pt_html}
        </div>
      </div>

      <!-- Review Section -->
      {review_html}

      <!-- Design Notes (collapsible) -->
      {build_design_notes_html(design_notes) if design_notes else ""}
    </div>
    """


def build_review_html(
    cn: str,
    card_name: str,
    review: dict | None,
    finalize_info: dict | None,
    is_reprint: bool,
) -> str:
    """Build the review annotations below a card."""
    parts = []

    # Badges row
    badges = []
    if review:
        verdict = review.get("final_verdict", "OK")
        if verdict == "OK":
            badges.append('<span class="badge badge-ok">OK</span>')
        else:
            badges.append(f'<span class="badge badge-revise">{html.escape(verdict)}</span>')

        tier = review.get("review_tier", "single")
        if tier == "council":
            badges.append('<span class="badge badge-tier">Council (3 Reviewers)</span>')
        else:
            badges.append('<span class="badge badge-tier">Single Reviewer</span>')

        if review.get("card_was_changed"):
            badges.append('<span class="badge badge-changed">MODIFIED BY REVIEW</span>')

        cost = review.get("total_cost_usd", 0)
        if cost:
            badges.append(f'<span class="badge badge-cost">${cost:.4f}</span>')
    else:
        if is_reprint:
            badges.append('<span class="badge badge-not-reviewed">REPRINT</span>')
        else:
            badges.append('<span class="badge badge-not-reviewed">NOT REVIEWED</span>')

    parts.append(f'<div class="review-badges">{"".join(badges)}</div>')

    # Auto-fixes
    if finalize_info and finalize_info.get("auto_fixes"):
        fixes_list = "".join(
            f"<li>{html.escape(f)}</li>" for f in finalize_info["auto_fixes"]
        )
        parts.append(
            f'<div class="review-box review-autofix">'
            f"<strong>Auto-Fixes Applied:</strong><ul>{fixes_list}</ul></div>"
        )

    # MANUAL errors
    if finalize_info and finalize_info.get("manual_errors"):
        errs_list = "".join(
            f"<li>{html.escape(e)}</li>" for e in finalize_info["manual_errors"]
        )
        parts.append(
            f'<div class="review-box review-manual">'
            f"<strong>MANUAL Errors (Human Review Required):</strong><ul>{errs_list}</ul></div>"
        )

    # Issues from review
    if review and review.get("final_issues"):
        chips = []
        for issue in review["final_issues"]:
            sev = issue.get("severity", "WARN")
            cat = issue.get("category", "")
            desc = issue.get("description", "")
            cls = "issue-fail" if sev == "FAIL" else "issue-warn"
            chips.append(
                f'<div class="issue-chip {cls}">'
                f'<span class="issue-sev">{html.escape(sev)}</span> '
                f'<span class="issue-cat">{html.escape(cat)}</span>: '
                f"{html.escape(desc)}</div>"
            )
        parts.append(f'<div class="review-issues">{"".join(chips)}</div>')

    # Reviewer analysis (collapsible)
    if review:
        analyses = _build_analyses(review)
        if analyses:
            parts.append(
                f'<details class="review-analysis-details">'
                f"<summary>Reviewer Analysis</summary>"
                f'<div class="review-analysis-content">{analyses}</div></details>'
            )

    return f'<div class="review-section">{"".join(parts)}</div>'


def _build_analyses(review: dict) -> str:
    """Extract analysis text from iterations and council reviews."""
    sections = []

    # Council reviews
    council = review.get("council_reviews") or []
    if council:
        for cr in council:
            mid = cr.get("member_id", "?")
            resp = cr.get("response", {})
            analysis = resp.get("analysis", "")
            verdict = resp.get("verdict", "")
            if analysis:
                escaped = html.escape(analysis).replace("\n", "<br>")
                badge = (
                    '<span class="badge badge-ok">OK</span>'
                    if verdict == "OK"
                    else f'<span class="badge badge-revise">{html.escape(verdict)}</span>'
                )
                sections.append(
                    f'<div class="analysis-block">'
                    f"<h4>Reviewer {mid} {badge}</h4>"
                    f"<p>{escaped}</p></div>"
                )

    # Iterations
    iterations = review.get("iterations") or []
    for it in iterations:
        idx = it.get("iteration", "?")
        resp = it.get("response", {})
        analysis = resp.get("analysis", "")
        verdict = resp.get("verdict", "")
        if analysis:
            escaped = html.escape(analysis).replace("\n", "<br>")
            label = f"Iteration {idx}" if len(iterations) > 1 or council else "Reviewer Analysis"
            badge = (
                '<span class="badge badge-ok">OK</span>'
                if verdict == "OK"
                else f'<span class="badge badge-revise">{html.escape(verdict)}</span>'
            )
            sections.append(
                f'<div class="analysis-block">'
                f"<h4>{label} {badge}</h4>"
                f"<p>{escaped}</p></div>"
            )

    return "".join(sections)


def build_design_notes_html(notes: str) -> str:
    escaped = html.escape(notes)
    return (
        f'<details class="design-notes-details">'
        f"<summary>Design Notes</summary>"
        f'<div class="design-notes-content"><p>{escaped}</p></div></details>'
    )


# ---------------------------------------------------------------------------
# Navigation builder
# ---------------------------------------------------------------------------
GROUP_ORDER = ["White", "Blue", "Black", "Red", "Green", "Multi", "Colorless", "Land"]
GROUP_ABBREV = {
    "White": "W",
    "Blue": "U",
    "Black": "B",
    "Red": "R",
    "Green": "G",
    "Multi": "M",
    "Colorless": "X",
    "Land": "L",
}


def build_nav_html(cards: list[dict]) -> str:
    """Build sidebar navigation grouped by color."""
    groups: dict[str, list[dict]] = {g: [] for g in GROUP_ORDER}
    for c in cards:
        g = color_group(c)
        if g in groups:
            groups[g].append(c)

    nav_parts = []
    for g in GROUP_ORDER:
        if not groups[g]:
            continue
        abbr = GROUP_ABBREV[g]
        nav_parts.append(f'<div class="nav-group"><div class="nav-group-title">{g} ({len(groups[g])})</div>')
        for c in groups[g]:
            cn = c["collector_number"]
            name = c["name"]
            card_id = cn.replace("-", "_")
            rarity = c.get("rarity", "common")
            rarity_color = RARITY_COLORS.get(rarity, "#1a1a1a")
            nav_parts.append(
                f'<a class="nav-card" href="#card-{card_id}" title="{html.escape(name)}">'
                f'<span class="nav-cn">{html.escape(cn)}</span> '
                f'<span class="nav-rarity-dot" style="background:{rarity_color}"></span> '
                f'<span class="nav-name">{html.escape(name)}</span></a>'
            )
        nav_parts.append("</div>")

    return "\n".join(nav_parts)


# ---------------------------------------------------------------------------
# Main HTML template
# ---------------------------------------------------------------------------
def build_full_html(cards: list[dict], reviews: dict, finalize_data: dict) -> str:
    # Stats
    total = len(cards)
    reviewed = sum(1 for c in cards if c["collector_number"] in reviews)
    changed = sum(
        1 for c in cards if reviews.get(c["collector_number"], {}).get("card_was_changed")
    )
    with_issues = sum(
        1
        for c in cards
        if reviews.get(c["collector_number"], {}).get("final_issues")
        or (
            c["collector_number"] in finalize_data
            and (
                finalize_data[c["collector_number"]].get("manual_errors")
                or finalize_data[c["collector_number"]].get("auto_fixes")
            )
        )
    )
    reprints = sum(1 for c in cards if c.get("is_reprint"))

    # Build card HTML
    card_htmls = []
    for c in cards:
        cn = c["collector_number"]
        rev = reviews.get(cn)
        fin = finalize_data.get(cn)
        card_htmls.append(build_card_html(c, rev, fin))

    cards_html = "\n".join(card_htmls)
    nav_html = build_nav_html(cards)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Anomalous Descent (ASD) - Card Review Gallery</title>
<style>
/* ================================================================
   ROOT & RESET
   ================================================================ */
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
:root {{
  --bg-dark: #1a1a2e;
  --bg-darker: #0f0f23;
  --bg-card-area: #16213e;
  --text-primary: #e0e0e0;
  --text-secondary: #a0a0a0;
  --text-bright: #ffffff;
  --accent-gold: #C9A652;
  --accent-blue: #5dade2;
  --sidebar-width: 280px;
}}
html {{ scroll-behavior: smooth; }}
body {{
  font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
  background: var(--bg-darker);
  color: var(--text-primary);
  line-height: 1.5;
}}

/* ================================================================
   STICKY HEADER
   ================================================================ */
.top-header {{
  position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
  background: linear-gradient(180deg, #0f0f23 0%, #1a1a2e 100%);
  border-bottom: 2px solid var(--accent-gold);
  padding: 10px 20px;
  display: flex; flex-wrap: wrap; align-items: center; gap: 12px;
}}
.header-title {{
  font-size: 1.3rem; font-weight: 700; color: var(--accent-gold);
  margin-right: 20px; white-space: nowrap;
}}
.header-stats {{
  display: flex; gap: 16px; font-size: 0.85rem; color: var(--text-secondary);
  flex-wrap: wrap;
}}
.header-stats span {{ white-space: nowrap; }}
.header-stats .stat-val {{ color: var(--text-bright); font-weight: 600; }}

/* ================================================================
   FILTER BAR
   ================================================================ */
.filter-bar {{
  position: fixed; top: 52px; left: 0; right: 0; z-index: 999;
  background: #16213e; border-bottom: 1px solid #2a2a4a;
  padding: 8px 20px; display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
}}
.filter-group {{ display: flex; gap: 4px; align-items: center; }}
.filter-group-label {{
  font-size: 0.75rem; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: 0.05em; margin-right: 4px;
}}
.filter-btn {{
  padding: 4px 10px; border-radius: 4px; border: 1px solid #3a3a5a;
  background: #1a1a2e; color: var(--text-primary); cursor: pointer;
  font-size: 0.8rem; transition: all 0.15s;
}}
.filter-btn:hover {{ border-color: var(--accent-gold); }}
.filter-btn.active {{ background: var(--accent-gold); color: #000; border-color: var(--accent-gold); font-weight: 600; }}
.filter-btn-w.active {{ background: #F9FAF4; color: #333; }}
.filter-btn-u.active {{ background: #0E68AB; color: #fff; }}
.filter-btn-b.active {{ background: #3D3229; color: #fff; }}
.filter-btn-r.active {{ background: #D3202A; color: #fff; }}
.filter-btn-g.active {{ background: #00733E; color: #fff; }}
.filter-separator {{ width: 1px; height: 24px; background: #3a3a5a; margin: 0 4px; }}
.filter-count {{ font-size: 0.8rem; color: var(--text-secondary); margin-left: 12px; }}
.filter-count .count-val {{ color: var(--accent-gold); font-weight: 600; }}

/* ================================================================
   SIDEBAR NAV
   ================================================================ */
.sidebar {{
  position: fixed; top: 100px; left: 0; bottom: 0; width: var(--sidebar-width);
  background: #0f0f23; border-right: 1px solid #2a2a4a;
  overflow-y: auto; z-index: 998; padding: 12px 0;
}}
.sidebar::-webkit-scrollbar {{ width: 6px; }}
.sidebar::-webkit-scrollbar-thumb {{ background: #3a3a5a; border-radius: 3px; }}
.nav-group {{ margin-bottom: 8px; }}
.nav-group-title {{
  padding: 6px 16px; font-size: 0.8rem; font-weight: 700;
  color: var(--accent-gold); text-transform: uppercase; letter-spacing: 0.05em;
}}
.nav-card {{
  display: flex; align-items: center; gap: 6px;
  padding: 3px 16px 3px 24px; font-size: 0.78rem; color: var(--text-secondary);
  text-decoration: none; transition: background 0.1s;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.nav-card:hover {{ background: #1a1a2e; color: var(--text-bright); }}
.nav-cn {{ color: var(--text-secondary); font-family: monospace; font-size: 0.72rem; min-width: 58px; }}
.nav-rarity-dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
.nav-name {{ overflow: hidden; text-overflow: ellipsis; }}

/* ================================================================
   MAIN CONTENT
   ================================================================ */
.main-content {{
  margin-left: var(--sidebar-width);
  margin-top: 100px;
  padding: 24px 32px 60px;
  display: flex; flex-direction: column; align-items: center;
}}

/* ================================================================
   CARD ENTRY
   ================================================================ */
.card-entry {{
  margin-bottom: 40px; width: 100%; max-width: 700px;
  display: flex; flex-direction: column; align-items: center;
}}
.card-entry.hidden {{ display: none; }}
.card-anchor-target {{ scroll-margin-top: 110px; }}

/* ================================================================
   MTG CARD FRAME
   ================================================================ */
.mtg-card {{
  width: 375px; border-radius: 18px; border: 6px solid;
  padding: 6px; position: relative;
  box-shadow: 0 4px 20px rgba(0,0,0,0.6), 0 0 2px rgba(0,0,0,0.4);
}}
.card-inner {{
  border: 2px solid; border-radius: 12px; overflow: hidden;
  position: relative;
}}

/* Title bar */
.card-title-bar {{
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 10px; min-height: 32px;
  border-bottom: 1px solid rgba(0,0,0,0.15);
}}
.card-name {{
  font-weight: 700; font-size: 0.92rem; color: #111;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  max-width: 230px;
}}
.card-mana-cost {{ display: flex; gap: 2px; flex-shrink: 0; }}

/* Mana symbols */
.mana-sym {{
  display: inline-flex; align-items: center; justify-content: center;
  width: 20px; height: 20px; border-radius: 50%;
  font-size: 0.7rem; font-weight: 700;
  box-shadow: 0 1px 2px rgba(0,0,0,0.3);
  border: 1px solid rgba(0,0,0,0.2);
  vertical-align: middle;
}}
.mana-generic {{ background: #CAC5C0; color: #111; }}
.mana-tap {{ background: #CAC5C0; width: 20px; height: 20px; }}
.tap-arrow {{ font-size: 14px; color: #333; }}
.card-text-box .mana-sym {{ width: 16px; height: 16px; font-size: 0.6rem; }}
.card-text-box .mana-tap {{ width: 16px; height: 16px; }}
.card-text-box .tap-arrow {{ font-size: 11px; }}

/* Art box */
.card-art-box {{
  height: 160px; display: flex; align-items: center; justify-content: center;
  position: relative; overflow: hidden;
  border-top: 1px solid rgba(0,0,0,0.1);
  border-bottom: 1px solid rgba(0,0,0,0.1);
}}
.art-placeholder-text {{
  font-size: 1.4rem; font-weight: 700; color: rgba(255,255,255,0.25);
  letter-spacing: 0.1em; text-transform: uppercase;
  text-shadow: 0 2px 4px rgba(0,0,0,0.3);
}}

/* Type bar */
.card-type-bar {{
  display: flex; justify-content: space-between; align-items: center;
  padding: 4px 10px; min-height: 26px;
  border-bottom: 1px solid rgba(0,0,0,0.1);
}}
.card-type {{ font-size: 0.82rem; font-weight: 600; color: #111; }}
.card-rarity-gem {{
  width: 14px; height: 14px; border-radius: 50%;
  border: 1px solid rgba(0,0,0,0.3); flex-shrink: 0;
  box-shadow: inset 0 -2px 3px rgba(0,0,0,0.2), 0 1px 2px rgba(0,0,0,0.3);
}}

/* Text box */
.card-text-box {{
  padding: 10px 12px; min-height: 80px;
  font-size: 0.82rem; color: #111; line-height: 1.45;
}}
.card-oracle {{ margin-bottom: 4px; }}
.card-text-empty {{ min-height: 30px; }}
.reminder-text {{ font-style: italic; color: #444; }}
.flavor-separator {{ border-top: 1px solid rgba(0,0,0,0.15); margin: 6px 0; }}
.card-flavor {{ font-style: italic; color: #444; font-size: 0.8rem; }}

/* P/T box */
.card-pt {{
  position: absolute; bottom: 0; right: 0;
  background: linear-gradient(135deg, #e0d8c0, #c8c0a8);
  border: 2px solid rgba(0,0,0,0.3); border-radius: 8px 0 12px 0;
  padding: 2px 12px; font-size: 0.95rem; font-weight: 700; color: #111;
  box-shadow: -2px -2px 4px rgba(0,0,0,0.15);
}}
.card-loyalty {{
  background: linear-gradient(135deg, #4a4a4a, #2a2a2a);
  color: #fff; border-color: #666;
}}

/* ================================================================
   REVIEW SECTION
   ================================================================ */
.review-section {{
  width: 375px; margin-top: 12px;
}}
.review-badges {{
  display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px;
}}
.badge {{
  padding: 3px 10px; border-radius: 4px; font-size: 0.75rem; font-weight: 600;
  display: inline-block;
}}
.badge-ok {{ background: #27ae60; color: #fff; }}
.badge-revise {{ background: #e74c3c; color: #fff; }}
.badge-not-reviewed {{ background: #555; color: #ccc; }}
.badge-tier {{ background: #2c3e50; color: #bbb; border: 1px solid #444; }}
.badge-changed {{ background: #f39c12; color: #000; }}
.badge-cost {{ background: #1a1a2e; color: #7f8c8d; border: 1px solid #333; }}

/* Review boxes */
.review-box {{
  padding: 8px 12px; border-radius: 6px; margin-bottom: 8px;
  font-size: 0.8rem;
}}
.review-box ul {{ margin: 4px 0 0 16px; }}
.review-box li {{ margin-bottom: 2px; }}
.review-autofix {{ background: rgba(243,156,18,0.15); border: 1px solid #f39c12; color: #f5c66d; }}
.review-manual {{ background: rgba(231,76,60,0.15); border: 1px solid #e74c3c; color: #f0a8a0; }}

/* Issue chips */
.review-issues {{ display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; }}
.issue-chip {{
  padding: 6px 10px; border-radius: 4px; font-size: 0.78rem; line-height: 1.3;
}}
.issue-fail {{ background: rgba(231,76,60,0.15); border: 1px solid #c0392b; color: #f0a8a0; }}
.issue-warn {{ background: rgba(243,156,18,0.15); border: 1px solid #d4a017; color: #f5c66d; }}
.issue-sev {{ font-weight: 700; }}
.issue-cat {{ font-weight: 600; }}

/* Analysis details */
.review-analysis-details, .design-notes-details {{
  width: 375px; margin-top: 6px;
}}
.review-analysis-details summary, .design-notes-details summary {{
  cursor: pointer; font-size: 0.82rem; color: var(--accent-blue);
  padding: 4px 0; user-select: none;
}}
.review-analysis-details summary:hover, .design-notes-details summary:hover {{
  color: var(--text-bright);
}}
.review-analysis-content, .design-notes-content {{
  background: #16213e; border: 1px solid #2a2a4a; border-radius: 6px;
  padding: 12px; margin-top: 6px; font-size: 0.78rem;
  color: var(--text-secondary); line-height: 1.5;
  max-height: 400px; overflow-y: auto;
}}
.review-analysis-content::-webkit-scrollbar, .design-notes-content::-webkit-scrollbar {{
  width: 5px;
}}
.review-analysis-content::-webkit-scrollbar-thumb, .design-notes-content::-webkit-scrollbar-thumb {{
  background: #3a3a5a; border-radius: 3px;
}}
.analysis-block {{ margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #2a2a4a; }}
.analysis-block:last-child {{ border-bottom: none; margin-bottom: 0; padding-bottom: 0; }}
.analysis-block h4 {{ font-size: 0.82rem; color: var(--text-bright); margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }}
.analysis-block .badge {{ font-size: 0.65rem; padding: 1px 6px; }}

/* ================================================================
   RESPONSIVE
   ================================================================ */
@media (max-width: 900px) {{
  .sidebar {{ display: none; }}
  .main-content {{ margin-left: 0; }}
  :root {{ --sidebar-width: 0px; }}
}}
</style>
</head>
<body>

<!-- ============================================================
     STICKY HEADER
     ============================================================ -->
<div class="top-header">
  <div class="header-title">Anomalous Descent (ASD)</div>
  <div class="header-stats">
    <span><span class="stat-val">{total}</span> cards</span>
    <span><span class="stat-val">{reviewed}</span> reviewed</span>
    <span><span class="stat-val">{changed}</span> changed</span>
    <span><span class="stat-val">{with_issues}</span> with issues</span>
    <span><span class="stat-val">{reprints}</span> reprints</span>
  </div>
</div>

<!-- ============================================================
     FILTER BAR
     ============================================================ -->
<div class="filter-bar">
  <div class="filter-group">
    <span class="filter-group-label">Color</span>
    <button class="filter-btn filter-btn-w active" data-filter="color" data-value="white">W</button>
    <button class="filter-btn filter-btn-u active" data-filter="color" data-value="blue">U</button>
    <button class="filter-btn filter-btn-b active" data-filter="color" data-value="black">B</button>
    <button class="filter-btn filter-btn-r active" data-filter="color" data-value="red">R</button>
    <button class="filter-btn filter-btn-g active" data-filter="color" data-value="green">G</button>
    <button class="filter-btn active" data-filter="color" data-value="multi">Multi</button>
    <button class="filter-btn active" data-filter="color" data-value="colorless">X</button>
    <button class="filter-btn active" data-filter="color" data-value="land">Land</button>
  </div>
  <div class="filter-separator"></div>
  <div class="filter-group">
    <span class="filter-group-label">Rarity</span>
    <button class="filter-btn active" data-filter="rarity" data-value="mythic" style="color:#D45A28">M</button>
    <button class="filter-btn active" data-filter="rarity" data-value="rare" style="color:#C9A652">R</button>
    <button class="filter-btn active" data-filter="rarity" data-value="uncommon" style="color:#9CA5AE">U</button>
    <button class="filter-btn active" data-filter="rarity" data-value="common">C</button>
  </div>
  <div class="filter-separator"></div>
  <div class="filter-group">
    <button class="filter-btn" data-filter="toggle" data-value="changed">Changed Only</button>
    <button class="filter-btn" data-filter="toggle" data-value="issues">With Issues</button>
  </div>
  <div class="filter-count">Showing <span class="count-val" id="visible-count">{total}</span> of {total}</div>
</div>

<!-- ============================================================
     SIDEBAR
     ============================================================ -->
<div class="sidebar" id="sidebar">
{nav_html}
</div>

<!-- ============================================================
     MAIN CONTENT
     ============================================================ -->
<div class="main-content" id="main-content">
{cards_html}
</div>

<script>
(function() {{
  // ---- Filter logic ----
  const entries = document.querySelectorAll('.card-entry');
  const countEl = document.getElementById('visible-count');

  // Track active filters
  const activeColors = new Set(['white','blue','black','red','green','multi','colorless','land']);
  const activeRarities = new Set(['mythic','rare','uncommon','common']);
  let showChangedOnly = false;
  let showIssuesOnly = false;

  function applyFilters() {{
    let count = 0;
    entries.forEach(el => {{
      const group = el.dataset.group;
      const rarity = el.dataset.rarity;
      const changed = el.dataset.changed === 'true';
      const hasIssues = el.dataset.hasIssues === 'true';

      let visible = activeColors.has(group) && activeRarities.has(rarity);
      if (showChangedOnly && !changed) visible = false;
      if (showIssuesOnly && !hasIssues) visible = false;

      el.classList.toggle('hidden', !visible);
      if (visible) count++;
    }});
    countEl.textContent = count;
  }}

  // Button click handlers
  document.querySelectorAll('.filter-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
      const filterType = btn.dataset.filter;
      const value = btn.dataset.value;

      if (filterType === 'color') {{
        btn.classList.toggle('active');
        if (activeColors.has(value)) activeColors.delete(value);
        else activeColors.add(value);
      }} else if (filterType === 'rarity') {{
        btn.classList.toggle('active');
        if (activeRarities.has(value)) activeRarities.delete(value);
        else activeRarities.add(value);
      }} else if (filterType === 'toggle') {{
        btn.classList.toggle('active');
        if (value === 'changed') showChangedOnly = !showChangedOnly;
        if (value === 'issues') showIssuesOnly = !showIssuesOnly;
      }}
      applyFilters();
    }});
  }});

  // Smooth scroll for nav links
  document.querySelectorAll('.nav-card').forEach(link => {{
    link.addEventListener('click', (e) => {{
      e.preventDefault();
      const targetId = link.getAttribute('href').slice(1);
      const target = document.getElementById(targetId);
      if (target) {{
        const anchor = target.querySelector('.card-anchor-target');
        if (anchor) anchor.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
        else target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      }}
    }});
  }});
}})();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    # Load all cards
    cards = []
    for f in sorted(CARDS_DIR.glob("*.json")):
        with open(f, encoding="utf-8") as fh:
            cards.append(json.load(fh))

    # Sort cards
    cards.sort(key=color_sort_key)

    # Load reviews
    reviews = {}
    for f in sorted(REVIEWS_DIR.glob("*.json")):
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        cn = data.get("collector_number")
        if cn:
            reviews[cn] = data

    # Load finalize report
    finalize_data = parse_finalize_report(FINALIZE_REPORT)

    # Build HTML
    html_content = build_full_html(cards, reviews, finalize_data)

    # Write output
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(html_content, encoding="utf-8")
    print(f"Gallery written to {OUTPUT_HTML}")
    print(f"  Cards: {len(cards)}")
    print(f"  Reviews: {len(reviews)}")
    print(f"  Finalize entries: {len(finalize_data)}")


if __name__ == "__main__":
    main()
