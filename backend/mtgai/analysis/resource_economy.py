"""Resource-economy / enablement-coverage analysis — the algorithmic economy step.

Sits beside the functional-duplicate scan in the merged ``conformance`` gate as a
**third analysis surface**. Like the duplicate scan it makes **no LLM call**: it is
a pure, deterministic pass that, for each consumable resource the set's cards
reference (Food, Treasure, custom set tokens like a mechanic's "Cloud tokens"),
counts **makers vs consumers** and cross-checks coverage.

Motivation: conformance hunts *excess* synergy and the council checks
rules-soundness, but nobody counts **enablement**. The user's "does anything even
create Food tokens?" had no automated answer — a draft archetype that consumes a
resource is dead if nothing in its colors produces it, and no existing gate would
catch that gap.

Three discovery sources for the resource vocabulary:
  1. ``PREDEFINED_TOKENS`` — the curated predefined MTG token nouns.
  2. Set-custom token types parsed from the approved mechanics' ``reminder_text``
     (e.g. Squall's "Cloud tokens").
  3. ``create ... <Name> token`` patterns mined from the pool's own oracle text.

Per-card extraction is conservative regex over ``oracle_text`` with reminder
(parenthesized) text stripped — matching the duplicate scan's convention.
Mechanic-driven consumption (a Provision carrier that "sacrifices a Food token"
*because* it has Provision) is joined via the separate mechanic-coverage channel,
not double-counted from the injected reminder text.

V1 is **advisory only** — it produces an always-on economy report plus WARN-level
findings for critical coverage gaps, but does NOT flag cards for regeneration and
does NOT bounce the pipeline (a coverage gap is set-level; a per-card regen can't
fix it). It is the analytic twin of the skeleton ``knob_warnings``: a visible
report the user acts on.

Usage::

    from mtgai.analysis.resource_economy import analyze_resource_economy

    report, warnings = analyze_resource_economy(cards, mechanics)
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict

from mtgai.analysis.gate_common import filter_gate_cards
from mtgai.models.card import Card

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Resource vocabulary
# ---------------------------------------------------------------------------

# Curated predefined MTG token-resource nouns (the consumable "artifact/enchant
# token" families that have a maker/consumer economy). Stored canonical-cased; the
# scan is case-insensitive. Deliberately excludes generic creature tokens
# (Soldier, Zombie, …) — those aren't a sacrificed/consumed resource economy.
PREDEFINED_TOKENS: tuple[str, ...] = (
    "Food",
    "Treasure",
    "Clue",
    "Blood",
    "Map",
    "Gold",
    "Powerstone",
    "Incubator",
    "Junk",
    "Shard",
    "Role",
)

# A `create ... <Name> token` clause — captures the token's proper noun. The token
# name is one or more Capitalized words right before "token(s)"; intervening
# lowercase adjectives ("colorless enchantment") are skipped by anchoring on the
# Capitalized run. Used for both mechanic-reminder discovery and pool mining.
_CREATE_TOKEN_RE = re.compile(
    r"\bcreate\b[^.;\n]*?\b((?:[A-Z][a-z]+\s+){0,3}[A-Z][a-z]+)\s+tokens?\b"
)

# Lowercase noise words that can lead a Capitalized-looking run at a sentence start
# but are not part of a token name (e.g. "Create a Food token" — "Create" itself).
_TOKEN_NAME_STOPWORDS = frozenset({"create", "a", "an", "the", "two", "three", "target", "another"})

# Colour codes a card maker/consumer is tallied under; a colourless card → "C".
COLORLESS = "C"


def _canonical_token_name(raw: str) -> str | None:
    """Reduce a captured ``create ... X token`` phrase to the token's proper noun.

    The capture may include leading adjectives; keep only the trailing run of
    Capitalized words and drop a leading stop-word. Returns ``None`` when nothing
    usable remains.
    """
    words = [w for w in raw.split() if w]
    while words and words[0].lower() in _TOKEN_NAME_STOPWORDS:
        words.pop(0)
    # Keep only the trailing contiguous Capitalized run (the proper noun).
    capitalized = [w for w in words if w[:1].isupper()]
    if not capitalized:
        return None
    name = " ".join(capitalized).strip()
    return name or None


def strip_reminder(text: str) -> str:
    """Drop parenthesized reminder text — matches the duplicate scan's convention.

    Reminder text is injected programmatically from a mechanic's definition, so a
    Provision card's reminder "(Whenever you sacrifice a Food token, …)" would
    otherwise double-count Food consumption that the mechanic-coverage join
    already attributes.
    """
    return re.sub(r"\([^)]*\)", " ", text or "")


def discover_resources(cards: list[Card], mechanics: list[dict] | None) -> list[str]:
    """Build the case-insensitive resource vocabulary for this set.

    Union of ``PREDEFINED_TOKENS``, the token nouns named in the approved
    mechanics' ``reminder_text`` (a ``create ... X token`` clause), and the token
    nouns the pool's own oracle text creates. Returned canonical-cased, sorted,
    deduped case-insensitively (first-seen casing wins).
    """
    found: dict[str, str] = {}  # lower -> canonical

    def add(name: str | None) -> None:
        if not name:
            return
        found.setdefault(name.lower(), name)

    for tok in PREDEFINED_TOKENS:
        add(tok)
    for mech in mechanics or []:
        reminder = strip_paren_outer(mech.get("reminder_text") or "")
        for m in _CREATE_TOKEN_RE.finditer(reminder):
            add(_canonical_token_name(m.group(1)))
    for card in filter_gate_cards(cards):
        oracle = strip_reminder((card.oracle_text or "").replace("\\n", "\n"))
        for m in _CREATE_TOKEN_RE.finditer(oracle):
            add(_canonical_token_name(m.group(1)))

    return sorted(found.values(), key=str.lower)


def strip_paren_outer(text: str) -> str:
    """Strip a single enclosing pair of parentheses from reminder text.

    A mechanic's ``reminder_text`` is stored wrapped in parens
    ("(Whenever you sacrifice a Food token, …)"); the token clause we want to mine
    lives *inside* them, so unlike :func:`strip_reminder` (which drops the whole
    parenthetical) we only peel the outer wrapper.
    """
    t = (text or "").strip()
    if t.startswith("(") and t.endswith(")"):
        return t[1:-1]
    # An unbalanced leading "(" still carries the clause — drop just the leading paren.
    return t.lstrip("(").rstrip(")")


# ---------------------------------------------------------------------------
# Per-card maker / consumer extraction
# ---------------------------------------------------------------------------


def _maker_re(resource: str) -> re.Pattern[str]:
    """``create [count] [adjectives] <Resource> token(s)`` for one resource."""
    return re.compile(rf"\bcreate\b[^.;\n]*?\b{re.escape(resource)}\s+tokens?\b", re.IGNORECASE)


def _consumer_re(resource: str) -> re.Pattern[str]:
    """``sacrifice [count] [adjectives] <Resource>`` (the trailing "token" optional).

    Catches both the explicit "Sacrifice a Food token" and the bare "Sacrifice a
    Food" some cards use. Conservative: keyed on an explicit *sacrifice* of the
    named resource, not every mention.
    """
    return re.compile(rf"\bsacrifices?\b[^.;\n]*?\b{re.escape(resource)}\b", re.IGNORECASE)


def card_colors(card: Card) -> list[str]:
    """The colour buckets a card's makers/consumers tally under — ``["C"]`` if colourless."""
    cols = [str(c) for c in (card.colors or [])]
    return cols if cols else [COLORLESS]


def scan_card(card: Card, resources: list[str]) -> tuple[set[str], set[str]]:
    """Return ``(makes, consumes)`` — the resources this card makes / consumes.

    A card can be in both sets (e.g. Applejack creates Food and sacrifices it for
    mana). Reminder text is stripped first.
    """
    oracle = strip_reminder((card.oracle_text or "").replace("\\n", "\n"))
    makes: set[str] = set()
    consumes: set[str] = set()
    for res in resources:
        if _maker_re(res).search(oracle):
            makes.add(res)
        if _consumer_re(res).search(oracle):
            consumes.add(res)
    return makes, consumes


# ---------------------------------------------------------------------------
# Mechanic coverage
# ---------------------------------------------------------------------------


def _mechanic_resource_roles(mechanic: dict, resources: list[str]) -> tuple[set[str], set[str]]:
    """Resources a mechanic's reminder text makes / consumes (its economy role)."""
    reminder = strip_paren_outer(mechanic.get("reminder_text") or "")
    makes: set[str] = set()
    consumes: set[str] = set()
    for res in resources:
        if _maker_re(res).search(reminder):
            makes.add(res)
        if _consumer_re(res).search(reminder):
            consumes.add(res)
    return makes, consumes


def _mechanic_carrier_count(mechanic: dict, cards: list[Card]) -> int:
    """How many gate cards carry this mechanic (its keyword appears in oracle text)."""
    name = (mechanic.get("name") or "").strip()
    if not name:
        return 0
    pattern = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
    count = 0
    for card in filter_gate_cards(cards):
        oracle = strip_reminder((card.oracle_text or "").replace("\\n", "\n"))
        if pattern.search(oracle):
            count += 1
    return count


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

# A resource is critically under-supplied when this many cards consume it but
# (almost) nothing makes it — the headline coverage gap the check exists to catch.
MIN_CONSUMERS_TO_WARN = 3
MAX_MAKERS_FOR_GAP = 1

# A colour-mismatch warning only fires when both sides are non-trivial, so a lone
# off-colour maker for a single consumer isn't noise.
MIN_CONSUMERS_FOR_COLOR_WARN = 2


def _dominant_colors(color_counts: dict[str, int]) -> set[str]:
    """The set of colours (excluding ``C``) that carry the most weight.

    Used for the maker/consumer colour-overlap test. Colourless ("C") is dropped:
    a colourless maker fixes any colour's gap, so it never causes a mismatch.
    """
    colored = {c: n for c, n in color_counts.items() if c != COLORLESS and n}
    return set(colored)


def analyze_resource_economy(
    cards: list[Card], mechanics: list[dict] | None = None
) -> tuple[dict, list[str]]:
    """Compute the per-resource maker/consumer economy + coverage warnings.

    Skips basic lands + reprints (shared :func:`filter_gate_cards`). Returns
    ``(report, warnings)``:

    - ``report`` — ``{"resources": [ {name, makers, consumers, makers_by_color,
      consumers_by_color, makers_by_rarity, consumers_by_rarity, mechanics} ],
      "warnings": [...]}``: every discovered resource that has any maker OR
      consumer, sorted by total activity. ``mechanics`` lists each approved
      mechanic joined to the resource (carrier count + role).
    - ``warnings`` — human-readable WARN strings (also copied into ``report``).

    Purely algorithmic — no LLM call, instant.
    """
    gate_cards = filter_gate_cards(cards)
    resources = discover_resources(cards, mechanics)

    makers: dict[str, list[Card]] = defaultdict(list)
    consumers: dict[str, list[Card]] = defaultdict(list)
    makers_by_color: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    consumers_by_color: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    makers_by_rarity: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    consumers_by_rarity: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for card in gate_cards:
        makes, uses = scan_card(card, resources)
        colors = card_colors(card)
        rarity = str(card.rarity)
        for res in makes:
            makers[res].append(card)
            makers_by_rarity[res][rarity] += 1
            for col in colors:
                makers_by_color[res][col] += 1
        for res in uses:
            consumers[res].append(card)
            consumers_by_rarity[res][rarity] += 1
            for col in colors:
                consumers_by_color[res][col] += 1

    # Mechanic coverage: join each approved mechanic that names a resource in its
    # reminder text to that resource's tally (Provision → Food, Squall → Cloud).
    mechanics_by_resource: dict[str, list[dict]] = defaultdict(list)
    for mech in mechanics or []:
        mech_makes, mech_uses = _mechanic_resource_roles(mech, resources)
        if not mech_makes and not mech_uses:
            continue
        carriers = _mechanic_carrier_count(mech, cards)
        for res in mech_makes | mech_uses:
            role = []
            if res in mech_makes:
                role.append("maker")
            if res in mech_uses:
                role.append("consumer")
            mechanics_by_resource[res].append(
                {
                    "name": mech.get("name") or "",
                    "carriers": carriers,
                    "role": "/".join(role),
                }
            )

    warnings = _build_warnings(
        resources, makers, consumers, makers_by_color, consumers_by_color, mechanics_by_resource
    )

    resource_rows: list[dict] = []
    for res in resources:
        n_make = len(makers[res])
        n_use = len(consumers[res])
        joined = mechanics_by_resource.get(res, [])
        if not n_make and not n_use and not joined:
            continue  # a predefined token the set never touches — don't clutter the report
        resource_rows.append(
            {
                "name": res,
                "makers": n_make,
                "consumers": n_use,
                "makers_by_color": dict(makers_by_color[res]),
                "consumers_by_color": dict(consumers_by_color[res]),
                "makers_by_rarity": dict(makers_by_rarity[res]),
                "consumers_by_rarity": dict(consumers_by_rarity[res]),
                "mechanics": joined,
            }
        )
    resource_rows.sort(key=lambda r: (-(r["makers"] + r["consumers"]), r["name"].lower()))

    report = {"resources": resource_rows, "warnings": warnings}
    logger.info(
        "Resource economy: %d resource(s) in play, %d warning(s)",
        len(resource_rows),
        len(warnings),
    )
    return report, warnings


def _build_warnings(
    resources: list[str],
    makers: dict[str, list[Card]],
    consumers: dict[str, list[Card]],
    makers_by_color: dict[str, dict[str, int]],
    consumers_by_color: dict[str, dict[str, int]],
    mechanics_by_resource: dict[str, list[dict]],
) -> list[str]:
    """Coverage-gap WARN strings — under-supplied + colour-mismatch resources.

    A mechanic joined as a *maker* counts toward supply (a Squall carrier makes
    Cloud tokens even if no card body literally says "create … Cloud token"), so a
    resource enabled purely by a keyword mechanic isn't falsely flagged dry.
    """
    out: list[str] = []
    for res in resources:
        n_use = len(consumers[res])
        if not n_use:
            continue  # nothing consumes it — no enablement gap to warn about
        # Maker supply = card makers + mechanics that act as makers.
        mech_maker = any(
            "maker" in (m.get("role") or "") for m in mechanics_by_resource.get(res, [])
        )
        n_make = len(makers[res])

        if n_use >= MIN_CONSUMERS_TO_WARN and n_make <= MAX_MAKERS_FOR_GAP and not mech_maker:
            out.append(
                f"{res}: {n_use} card(s) consume it but only {n_make} make it — "
                f"a draft archetype leaning on {res} may be starved. "
                f"Add more {res} makers (ideally at common/uncommon, in the "
                f"consumers' colors)."
            )
            continue

        # Colour-mismatch: consumers concentrated in colours no maker covers (and
        # no colourless / mechanic maker fills the gap).
        if n_use >= MIN_CONSUMERS_FOR_COLOR_WARN and n_make >= 1 and not mech_maker:
            consume_cols = _dominant_colors(consumers_by_color[res])
            make_cols = _dominant_colors(makers_by_color[res])
            colorless_maker = makers_by_color[res].get(COLORLESS, 0) > 0
            disjoint = not (consume_cols & make_cols)
            if consume_cols and make_cols and not colorless_maker and disjoint:
                out.append(
                    f"{res}: every maker is outside the consumers' colors "
                    f"(makers in {', '.join(sorted(make_cols))}; "
                    f"consumers in {', '.join(sorted(consume_cols))}) — "
                    f"the resource is produced where it can't be used. "
                    f"Add a {res} maker in {', '.join(sorted(consume_cols))} "
                    f"(or a colorless one)."
                )

    return out
