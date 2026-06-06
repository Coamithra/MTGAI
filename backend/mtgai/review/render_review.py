"""Final-review behaviors for the merged ``rendering`` stage.

The terminal ``rendering`` stage renders every card to a print-ready image and
surfaces a final-review gallery. The user has exactly two actions there, and the
non-trivial logic for both lives here as pure (IO-free) functions so it is unit-
testable in isolation from FastAPI / the renderer:

1. **Manual field edit** — :func:`finalize_one_card` runs the lightweight per-card
   finalize pass (reminder-text re-injection + validation + auto-fix), reusing
   :func:`mtgai.review.finalize.finalize_card` scoped to a single card. The caller
   then re-renders just that card.

2. **Remove a card** — :func:`plan_renumber` computes how the remaining cards'
   collector numbers must shift so numbering stays contiguous (no gaps) within the
   removed card's collector-number group. The caller hard-deletes the card, applies
   the remap (rename files + rewrite ``collector_number``), and re-renders any card
   whose number changed.

Collector-number shape: ``<prefix>-<NN>`` where the trailing ``-<digits>`` run is
a zero-padded index and the prefix is the group key (``B-C-01`` → group ``B-C``,
index ``1``; ``L-03`` → group ``L``; ``BLOG-01`` → group ``BLOG``). Renumbering is
**per group**: removing ``B-C-02`` shifts ``B-C-03`` → ``B-C-02``, ``B-C-04`` →
``B-C-03``; cards in other groups are untouched. A collector number that doesn't
match the ``<prefix>-<NN>`` shape is left exactly as-is (its own group of one).

What renumbering touches vs. deliberately leaves alone:
- ``collector_number`` (the printed identity) + the card's on-disk filename
  (``<cn>_<slug>.json``): rewritten.
- ``slot_id`` and ``skeleton.json``: **left untouched** — ``slot_id`` is the
  card's immutable link back to the skeleton slot it was generated from, an
  upstream structural identity the terminal render stage has no business
  rewriting. (``slot_id`` starts equal to ``collector_number`` at card-gen time;
  after a removal they may diverge for shifted cards, which is fine — nothing
  downstream of rendering reads ``slot_id``, and the rendering tab keys its
  context lookup by ``slot_id``, not the renumbered ``collector_number``.)
- ``generation_progress.json`` (keyed by ``slot_id``, the stable key): the caller
  drops the removed card's entry and repoints renamed cards' path values, but the
  keys stay stable because ``slot_id`` doesn't change.
- ``history/<instance>/`` snapshots: **never** retroactively renumbered — they are
  write-once historical records of what each completed loop instance produced.
"""

from __future__ import annotations

import re

from mtgai.models.card import Card
from mtgai.review.finalize import finalize_card
from mtgai.validation import ValidationError

# A collector number ends in a ``-<digits>`` index; everything before is the group.
# The ``-<prefix>`` part is optional so a bare zero-padded number (``002``) parses as
# the prefixless group — that's the shape the skeleton generator stamps onto every
# ordinary card (``001``, ``002``, …); only land/special ids carry a dashed prefix.
_CN_RE = re.compile(r"^(?:(?P<prefix>.+)-)?(?P<index>\d+)$")


def parse_collector_number(cn: str) -> tuple[str, int, int] | None:
    """Split ``<prefix>-<NN>`` into ``(prefix, index, pad_width)``.

    ``B-C-02`` -> ``("B-C", 2, 2)``; ``L-3`` -> ``("L", 3, 1)``. A bare numeric
    collector number (no dashed prefix) parses as the prefixless group:
    ``002`` -> ``("", 2, 3)`` — this is the form every ordinary card carries
    (the skeleton stamps plain zero-padded slot ids). Returns ``None`` for a
    collector number with no trailing ``<digits>`` run at all (e.g. ``PROMO``);
    it's then its own ungrouped singleton — never renumbered.
    """
    m = _CN_RE.match(cn or "")
    if not m:
        return None
    index_str = m.group("index")
    return m.group("prefix") or "", int(index_str), len(index_str)


def format_collector_number(prefix: str, index: int, pad_width: int) -> str:
    """Inverse of :func:`parse_collector_number`.

    ``("B-C", 2, 2)`` -> ``B-C-02``; the prefixless group emits just the
    zero-padded number: ``("", 2, 3)`` -> ``002``.
    """
    if not prefix:
        return f"{index:0{pad_width}d}"
    return f"{prefix}-{index:0{pad_width}d}"


def plan_renumber(collector_numbers: list[str], removed_cn: str) -> dict[str, str]:
    """Compute the contiguous-renumber remap after removing ``removed_cn``.

    ``collector_numbers`` is the set of collector numbers that REMAIN (the removed
    one already excluded). Returns ``{old_cn: new_cn}`` containing **only** the
    cards whose number actually changes — a card that keeps its number is omitted,
    so the caller's re-render set is exactly ``remap.keys()``.

    Only the removed card's group is renumbered, and only its *trailing* members
    (cards in the same group with a higher index) shift down by one to close the
    gap. Lower-indexed siblings and every other group keep their numbers. A removed
    card whose number doesn't parse (no ``-<NN>`` suffix) leaves an empty remap.
    """
    removed = parse_collector_number(removed_cn)
    if removed is None:
        return {}
    removed_prefix, _removed_index, _ = removed

    # Group the survivors that share the removed card's prefix, by ascending index.
    siblings: list[tuple[int, int, str]] = []  # (index, pad_width, old_cn)
    for cn in collector_numbers:
        parsed = parse_collector_number(cn)
        if parsed is None:
            continue
        prefix, index, pad = parsed
        if prefix == removed_prefix:
            siblings.append((index, pad, cn))
    siblings.sort()

    # Renumber the whole group densely from 1 so any pre-existing gaps also close
    # (defensive — normally only the trailing run after the removed index shifts).
    remap: dict[str, str] = {}
    for new_index, (_old_index, pad, old_cn) in enumerate(siblings, start=1):
        new_cn = format_collector_number(removed_prefix, new_index, pad)
        if new_cn != old_cn:
            remap[old_cn] = new_cn
    return remap


def finalize_one_card(
    card: Card,
    mechanics: list[dict],
    existing_cards: list[Card] | None = None,
) -> tuple[Card, list[str], list[ValidationError]]:
    """Run the lightweight per-card finalize pass on a single edited card.

    Thin wrapper over :func:`mtgai.review.finalize.finalize_card` so the rendering
    stage's on-edit behavior names its intent ("finalize just this one card") and
    has a single seam the endpoint + tests share. Returns
    ``(finalized_card, applied_fixes, remaining_manual_errors)`` — the caller
    re-injects reminder text via the reminder injector (inside ``finalize_card``),
    validates, auto-fixes, and then re-renders the returned card.
    """
    return finalize_card(card, mechanics, existing_cards)
