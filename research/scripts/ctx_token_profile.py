"""Per-stage input-token profiler for the ctx-tier-variants investigation.

Builds the REAL prompts for the scale-sensitive pipeline stages (the ones with
no/too-thin transcript coverage) against the tracked ASD card pool, counts
tokens, and linearly extrapolates the per-gate-card component to a full set.

Run from backend/ with the venv active:
    PYTHONIOENCODING=utf-8 python ../research/scripts/ctx_token_profile.py

Reads the root checkout's gitignored ASD artifacts by absolute path (the
worktree has no output/), so it works regardless of cwd.
"""

from __future__ import annotations

import json
from pathlib import Path

from mtgai.analysis import conformance, interactions
from mtgai.analysis.gate_common import filter_gate_cards
from mtgai.generation.prompts import format_set_context
from mtgai.generation.token_utils import count_tokens
from mtgai.models.card import Card

ASD = Path("C:/Programming/MTGAI/output/sets/ASD")
FULL_SET = 277          # target premier-set size
GEMMA_ADJ = 1.25        # tiktoken undercounts Gemma by ~10-30%; conservative headroom


def load_cards() -> list[Card]:
    cards = []
    for p in sorted((ASD / "cards").glob("*.json")):
        raw = json.loads(p.read_text(encoding="utf-8"))
        try:
            cards.append(Card.model_validate(raw))
        except Exception as e:
            print(f"  skip {p.name}: {e}")
    return cards


def load_slots() -> dict[str, dict]:
    data = json.loads((ASD / "skeleton.json").read_text(encoding="utf-8"))
    slots = data["slots"] if isinstance(data, dict) else data
    return {s.get("slot_id"): s for s in slots if s.get("slot_id")}


def load_mechanics() -> list[dict]:
    p = ASD / "mechanics" / "approved.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("mechanics", data.get("approved", []))


def tok(label: str, text: str, n_cards: int | None = None) -> int:
    t = count_tokens(text)
    adj = int(t * GEMMA_ADJ)
    extra = ""
    if n_cards:
        extra = f"  ({t / n_cards:.1f} tok/card, {adj / n_cards:.1f} adj/card)"
    print(f"  {label:36} {t:>7} tok   ~{adj:>7} gemma-adj{extra}")
    return t


def main() -> None:
    cards = load_cards()
    slots = load_slots()
    mechanics = load_mechanics()
    gate_cards = filter_gate_cards(cards)
    n = len(gate_cards)
    print(f"Loaded {len(cards)} cards ({n} gate cards after basics/reprints filter), "
          f"{len(slots)} slots, {len(mechanics)} mechanics\n")

    # ---- Whole-set gate: INTERACTIONS (card pool, one line/card) ----
    print("INTERACTIONS gate (whole-set scan):")
    inter_prompt = interactions._build_interaction_prompt(gate_cards, mechanics)
    sys_inter = interactions.INTERACTION_SYSTEM_PROMPT
    schema_inter = json.dumps(interactions.INTERACTION_TOOL_SCHEMA)
    t_inter = tok("user prompt", inter_prompt, n)
    t_sys_i = count_tokens(sys_inter) + count_tokens(schema_inter)
    per_card_i = t_inter / n
    full_i = int((per_card_i * (FULL_SET * n / len(cards)) + t_sys_i) * GEMMA_ADJ)
    print(f"    + system+schema: {t_sys_i} tok")
    print(f"    -> extrapolated to ~{FULL_SET}-set (~{int(FULL_SET*n/len(cards))} gate cards): "
          f"~{full_i} gemma-adj tokens\n")

    # ---- Whole-set gate: CONFORMANCE (card + slot spec/card) ----
    print("CONFORMANCE gate (whole-set, card + slot SPEC each):")
    pairs = []
    for c in gate_cards:
        if not c.slot_id:
            continue
        spec = conformance.slot_spec_text(slots.get(c.slot_id, {}))
        if spec:
            pairs.append((c.slot_id, c, spec))
    conf_prompt = conformance._build_prompt(pairs)
    t_conf = tok("user prompt", conf_prompt, len(pairs))
    t_sys_c = count_tokens(conformance.CONFORMANCE_SYSTEM_PROMPT) + count_tokens(
        json.dumps(conformance.CONFORMANCE_TOOL_SCHEMA)
    )
    per_card_c = t_conf / max(1, len(pairs))
    full_c = int((per_card_c * (FULL_SET * n / len(cards)) + t_sys_c) * GEMMA_ADJ)
    print(f"    + system+schema: {t_sys_c} tok   ({len(pairs)} pairs with resolvable spec)")
    print(f"    -> extrapolated to ~{FULL_SET}-set: ~{full_c} gemma-adj tokens\n")

    # ---- card_gen existing-cards context (grows over the run) ----
    print("CARD_GEN existing-cards context (format_set_context grows per batch):")
    card_dicts = [c.model_dump() for c in cards]
    ctx_label = f"context @ {len(cards)} prior cards"
    t_ctx_full = tok(ctx_label, format_set_context(card_dicts), len(cards))
    per_card_ctx = t_ctx_full / len(cards)
    # Late-run batch: ~250 prior cards in context
    ctx_250 = int(per_card_ctx * 250)
    print(f"    -> at ~250 prior cards (late batch): ~{ctx_250} tok "
          f"(~{int(ctx_250*GEMMA_ADJ)} gemma-adj) for the existing-cards block alone")

    # Fixed card_gen overhead: setting prose + mechanics block (rough, from artifacts)
    theme = json.loads((ASD / "theme.json").read_text(encoding="utf-8"))
    prose = json.dumps(theme)  # upper bound on setting-prose token weight
    t_prose = count_tokens(prose)
    print(f"    theme.json total: {t_prose} tok (setting-prose block is a subset)")
    est_cardgen = int((ctx_250 + t_prose * 0.4 + 2000) * GEMMA_ADJ)
    print(f"    -> rough card_gen late-batch total: ~{est_cardgen} gemma-adj tokens "
          f"(existing-cards + ~40% of theme as prose + ~2k mechanics/specs/guidance)\n")

    print("=" * 72)
    print("SUMMARY (gemma-adjusted, full ~277-set worst case):")
    print(f"  interactions : ~{full_i:>6} tok   (MID — scales with set)")
    print(f"  conformance  : ~{full_c:>6} tok   (MID — scales with set, largest gate)")
    print(f"  card_gen     : ~{est_cardgen:>6} tok   (late batches grow with existing-cards)")
    print("  (theme_extract measured separately from transcripts: ~58.7k max)")


if __name__ == "__main__":
    main()
