"""Unified per-card entity tagging (the single source of truth for "which
style-guide entities does this card feature").

Both the appearance-TEXT path (``art_prompts`` → ``prompt_builder``) and the
reference-IMAGE path (``char_portraits``) used to decide a card's entities
independently — a brittle substring match for text, a separate LLM pass for
images — so they routinely disagreed (card 6a27581d). This module is the one
LLM detection pass both consume:

* It runs at ``art_prompts`` time (``ensure_entity_tags``), persisting a sidecar
  ``art-direction/entity-tags.json`` mapping every card to the dictionary
  entities it features (1-card entities included).
* ``art_prompts`` reads each card's tags and injects the matching appearance
  prose (``visual_reference.get_visual_references_for_keys``).
* ``char_portraits`` reads the SAME sidecar (no second LLM pass), derives the
  recurring (2+ card) entities via ``recurring_from_tags``, and generates +
  attaches their reference images.

Detection is dictionary-anchored and deliberately ignores ``art_prompt`` text
(which is authored downstream), so the result is stable whether prompts exist
yet or not.

Sidecar shape::

    {
      "cards": {"<cn>": {"tags": [{"entity_key", "kind"}], "source": "ai"|"manual"}},
      "entities_meta": {"<entity_key>": {"name", "kind", "note"}}
    }

A card whose ``source`` is ``"manual"`` (the user edited its tags in the Art
Prompts tab) is preserved verbatim across an AI re-detection.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from mtgai.art.visual_reference import normalize_entity_key
from mtgai.generation import temperatures as temps
from mtgai.generation.llm_client import cost_from_result, generate_with_tool
from mtgai.generation.token_budgets import STANDARD
from mtgai.io.atomic import atomic_write_text

logger = logging.getLogger(__name__)

ENTITY_TAGS_FILENAME = "entity-tags.json"

# The art-direction dictionary's keyed sub-dicts that hold appearance prose, in
# priority order (mirrors character_portraits._REF_CATEGORIES).
_REF_CATEGORIES = ("legendary_characters", "creature_types", "factions", "landmarks")


def entity_tags_path(set_dir: Path) -> Path:
    """Sidecar path for a project's per-card entity tags."""
    return set_dir / "art-direction" / ENTITY_TAGS_FILENAME


def load_entity_tags(set_dir: Path) -> dict:
    """Load the entity-tags sidecar, returning an empty skeleton on absence/error."""
    path = entity_tags_path(set_dir)
    if not path.exists():
        return {"cards": {}, "entities_meta": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # a corrupt sidecar must not abort the stage
        logger.warning("Could not parse %s (%s); starting from empty tags", path, e)
        return {"cards": {}, "entities_meta": {}}
    if not isinstance(data, dict):
        return {"cards": {}, "entities_meta": {}}
    cards = data.get("cards")
    meta = data.get("entities_meta")
    out = {
        "cards": cards if isinstance(cards, dict) else {},
        "entities_meta": meta if isinstance(meta, dict) else {},
    }
    # Carry the diagnostic flag through so a failed prior run is re-detected
    # (_sidecar_is_vacuous reads it; card 6a29a6eb).
    if data.get("detection_failed"):
        out["detection_failed"] = True
    return out


def save_entity_tags(set_dir: Path, data: dict) -> None:
    """Persist the entity-tags sidecar atomically."""
    path = entity_tags_path(set_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# LLM detection
# ---------------------------------------------------------------------------


def _card_summary_line(card: dict) -> str:
    """One compact line per card for detection: the fields an entity name surfaces
    in (name / type / oracle / flavor). Deliberately excludes ``art_prompt`` —
    detection must not depend on downstream-authored prompt text."""
    cn = str(card.get("collector_number") or "?")
    name = str(card.get("name") or "")
    type_line = str(card.get("type_line") or "")
    oracle = str(card.get("oracle_text") or "").replace("\n", " ")
    flavor = str(card.get("flavor_text") or "").replace("\n", " ")
    parts = [f"[{cn}] {name} — {type_line}"]
    if oracle:
        parts.append(f"text: {oracle}")
    if flavor:
        parts.append(f"flavor: {flavor}")
    return " | ".join(parts)


def _build_detection_tool_schema() -> dict:
    return {
        "name": "report_card_entities",
        "description": (
            "Report which named style-guide entities (characters, locations, "
            "factions, creatures, elements) each card features, and the cards "
            "each appears on."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "description": (
                        "One entry per distinct entity that appears on one or more "
                        "cards (single-card entities INCLUDED)."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "entity_key": {
                                "type": "string",
                                "description": (
                                    "Lowercase snake_case slug. Prefer the slug from "
                                    "the art-direction dictionary when the entity "
                                    "matches one of its keys."
                                ),
                            },
                            "name": {"type": "string", "description": "Display name."},
                            "kind": {
                                "type": "string",
                                "description": (
                                    "'character', 'location', 'faction', 'creature', or 'element'."
                                ),
                            },
                            "cards": {
                                "type": "array",
                                "description": (
                                    "Collector-number STRINGS of the cards this entity "
                                    "appears on — copy the bracketed [..] ids from the "
                                    'card list VERBATIM (e.g. "041", "L-01a"). These are '
                                    "string labels, NOT numbers: never emit a bare number "
                                    "like 41 or 0."
                                ),
                                "items": {
                                    "type": "string",
                                    "description": (
                                        "A collector-number string exactly as bracketed, "
                                        'e.g. "041" or "L-01a".'
                                    ),
                                },
                            },
                            "note": {
                                "type": "string",
                                "description": "Optional one-line note on what it is.",
                            },
                        },
                        "required": ["entity_key", "name", "kind", "cards"],
                    },
                }
            },
            "required": ["entities"],
        },
    }


def _build_detection_prompt(
    cards: list[dict], visual_refs: dict, *, corrective: str | None = None
) -> tuple[str, str, str]:
    """Return (system, context_block, user) for per-card entity detection.

    ``corrective`` is an optional feedback line prepended to the user turn on a
    validate-and-retry attempt (e.g. after the model emitted numeric card refs).
    """
    system = (
        "You are a Magic: The Gathering set continuity editor. You scan a whole "
        "card set and tag each card with the named characters, locations, factions, "
        "creatures, and other concrete visual entities it FEATURES — whether by "
        "name in its title, in its rules text, or in its flavor.\n\n"
        "Report every entity that appears on one or more cards (do NOT drop "
        "single-card entities — they still need consistent appearance text). For "
        "each entity, list the collector numbers it appears on. Each card line "
        "starts with its collector number in square brackets, e.g. [041] or "
        "[L-01a]; copy that bracketed id VERBATIM as a STRING into the entity's "
        '"cards" array (never a bare number like 41 or 0). Use the art-direction '
        "dictionary's existing slug as the entity_key whenever the entity matches "
        "one of its keys, so the tag links back to the dictionary's appearance "
        "prose. Return your findings through the report_card_entities tool."
    )

    dict_keys: list[str] = []
    for category in _REF_CATEGORIES:
        sub = visual_refs.get(category, {})
        if isinstance(sub, dict):
            dict_keys.extend(f"- {key} ({category})" for key in sub)
    keys_block = "\n".join(dict_keys) if dict_keys else "(the dictionary is empty)"
    context_block = (
        "## Art-direction dictionary keys\n"
        "These are the known entities with appearance prose. Prefer these slugs as "
        "entity_key when an entity matches one:\n"
        f"{keys_block}"
    )

    card_lines = "\n".join(_card_summary_line(c) for c in cards) or "(no cards)"
    correction = f"{corrective}\n\n" if corrective else ""
    user = (
        f"{correction}"
        f"# Card pool ({len(cards)} cards)\n"
        "Each line: [collector_number] name — type | text | flavor.\n\n"
        f"{card_lines}\n\n"
        "Tag every card with the entities it features and report them."
    )
    return system, context_block, user


# A retry fires when MORE than this fraction of detected entities lose ALL their
# card refs to validation — the signature of the local-model bug where the tool
# call emitted numeric refs (cards: [0.0]) for every entity (card 6a29a6eb).
_REF_LOSS_RETRY_THRESHOLD = 0.5

_RETRY_CORRECTIVE = (
    'Your previous response emitted invalid card references: the "cards" arrays '
    "did not match any real collector number, so every entity was discarded. The "
    "card references MUST be the collector-number STRINGS exactly as they appear in "
    'square brackets at the start of each card line (e.g. "041", "L-01a") — never a '
    "bare number like 41 or 0, and never an index. Re-report now using the bracketed "
    "collector numbers verbatim."
)


def _parse_detection_entities(
    raw: list, valid_cards: set[str]
) -> tuple[list[dict], int, int, list]:
    """Validate one detection tool result against the real collector numbers.

    Returns ``(entities, detected_count, dropped_count, sample_bad_refs)`` where:

    * ``entities`` is the accepted, deduped list (entries with no valid ref dropped);
    * ``detected_count`` is the number of distinct (non-dup) entities the model named;
    * ``dropped_count`` is how many of those lost ALL their refs to validation;
    * ``sample_bad_refs`` is a small sample of the raw refs that failed to match,
      for the diagnostic WARN.
    """
    entities: list[dict] = []
    seen_keys: set[str] = set()
    detected = 0
    dropped = 0
    bad_refs: list = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = normalize_entity_key(str(item.get("entity_key") or item.get("name") or ""))
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        detected += 1
        raw_refs = list(dict.fromkeys(str(c) for c in (item.get("cards") or [])))
        cns = [cn for cn in raw_refs if cn in valid_cards]
        if not cns:
            dropped += 1
            for ref in raw_refs:
                if len(bad_refs) < 5 and ref not in bad_refs:
                    bad_refs.append(ref)
            continue
        entities.append(
            {
                "entity_key": key,
                "name": str(item.get("name") or key.replace("_", " ").title()),
                "kind": str(item.get("kind") or "entity"),
                "cards": cns,
                "note": str(item.get("note") or ""),
            }
        )
    return entities, detected, dropped, bad_refs


def _detection_call(
    cards: list[dict],
    visual_refs: dict,
    valid_cards: set[str],
    *,
    model_id: str,
    log_dir: Path | None,
    thinking: str | None,
    temperature: float,
    corrective: str | None = None,
) -> tuple[list[dict], float, int, int, list]:
    """One LLM detection call + validation. Returns
    ``(entities, cost, detected_count, dropped_count, sample_bad_refs)``."""
    system, context_block, user = _build_detection_prompt(cards, visual_refs, corrective=corrective)
    response = generate_with_tool(
        system_blocks=[(system, True), (context_block, True)],
        user_prompt=user,
        tool_schema=_build_detection_tool_schema(),
        model=model_id,
        thinking=thinking,
        temperature=temperature,
        max_tokens=STANDARD,
        log_dir=log_dir,
    )
    cost = cost_from_result(response)
    raw = response.get("result", {}).get("entities", []) or []
    entities, detected, dropped, bad_refs = _parse_detection_entities(raw, valid_cards)
    return entities, cost, detected, dropped, bad_refs


def detect_entity_tags(
    cards: list[dict],
    visual_refs: dict,
    *,
    model_id: str,
    log_dir: Path | None = None,
    thinking: str | None = None,
    diagnostics: dict | None = None,
) -> tuple[list[dict], float]:
    """LLM-detect which entities each card features.

    Returns ``(entities, cost_usd)`` where each entity is
    ``{entity_key, name, kind, cards: [collector_number], note}``. Unlike the old
    recurring-entity detector this keeps single-card entities (the text path needs
    their appearance prose); the recurrence (2+) filter is applied later, only
    where reference IMAGES are decided (:func:`recurring_from_tags`).

    **Validate-and-retry** (card 6a29a6eb): the local model occasionally emits
    invalid ``cards`` refs (numeric ``[0.0]`` instead of collector-number strings)
    for the entities it correctly named, so every entity loses all its refs to
    validation and the result silently collapses to ``[]``. When the model named
    entities but MORE than :data:`_REF_LOSS_RETRY_THRESHOLD` of them lost ALL refs,
    the call retries ONCE with a temp bump (:data:`temperatures.RETRY_TEMP_STEP`)
    and corrective feedback naming the format error. The better of the two attempts
    (more accepted entities) is kept.

    When a mutable ``diagnostics`` dict is passed it is populated with
    ``detected``, ``accepted``, ``dropped``, ``attempts``, ``sample_bad_refs`` and a
    ``detection_failed`` bool (True when entities were detected but ALL were dropped
    even after the retry) so the caller can mark the sidecar diagnosably and WARN.
    """
    if not cards:
        return [], 0.0

    valid_cards = {str(c.get("collector_number") or "") for c in cards}
    # Floored off the near-greedy base for a local reasoning model so the whole-pool
    # scan terminates instead of looping (temperatures.floor_for_local).
    base_temp = temps.floor_for_local(temps.ANALYTICAL, model_id)
    entities, cost, detected, dropped, bad_refs = _detection_call(
        cards,
        visual_refs,
        valid_cards,
        model_id=model_id,
        log_dir=log_dir,
        thinking=thinking,
        temperature=base_temp,
    )
    attempts = 1

    # Validate: if the model named entities but >50% lost all refs, the refs were
    # malformed (the numeric-ref bug). Retry once, temp-bumped, with feedback.
    if detected and dropped > detected * _REF_LOSS_RETRY_THRESHOLD:
        logger.warning(
            "Entity detection lost %d/%d entities to invalid card refs "
            "(sample: %s); retrying with corrective feedback.",
            dropped,
            detected,
            bad_refs,
        )
        r_entities, r_cost, r_detected, r_dropped, r_bad = _detection_call(
            cards,
            visual_refs,
            valid_cards,
            model_id=model_id,
            log_dir=log_dir,
            thinking=thinking,
            temperature=base_temp + temps.RETRY_TEMP_STEP,
            corrective=_RETRY_CORRECTIVE,
        )
        attempts = 2
        cost += r_cost
        # Keep the better attempt (more accepted entities).
        if len(r_entities) >= len(entities):
            entities, detected, dropped, bad_refs = r_entities, r_detected, r_dropped, r_bad

    if diagnostics is not None:
        diagnostics["detected"] = detected
        diagnostics["accepted"] = len(entities)
        diagnostics["dropped"] = dropped
        diagnostics["attempts"] = attempts
        diagnostics["sample_bad_refs"] = bad_refs
        diagnostics["detection_failed"] = bool(detected) and not entities

    return entities, cost


# ---------------------------------------------------------------------------
# Sidecar derivation helpers
# ---------------------------------------------------------------------------


def _entities_to_card_tags(entities: list[dict]) -> dict[str, list[dict]]:
    """Invert the entity-centric detection list into ``{cn: [{entity_key, kind}]}``."""
    by_card: dict[str, list[dict]] = {}
    for entity in entities:
        key = entity["entity_key"]
        kind = entity.get("kind") or "entity"
        for cn in entity.get("cards") or []:
            tags = by_card.setdefault(cn, [])
            if not any(t["entity_key"] == key for t in tags):
                tags.append({"entity_key": key, "kind": kind})
    return by_card


def _entities_meta(entities: list[dict]) -> dict[str, dict]:
    """Build the ``entity_key -> {name, kind, note}`` lookup for tab labels and the
    char_portraits recurrence reconstruction."""
    return {
        e["entity_key"]: {
            "name": e.get("name") or e["entity_key"].replace("_", " ").title(),
            "kind": e.get("kind") or "entity",
            "note": e.get("note") or "",
        }
        for e in entities
    }


def effective_card_tags(data: dict, cn: str) -> list[dict]:
    """Return a card's effective tag list ``[{entity_key, kind}]`` (AI or manual)."""
    entry = (data.get("cards") or {}).get(cn)
    if not isinstance(entry, dict):
        return []
    tags = entry.get("tags")
    if not isinstance(tags, list):
        return []
    out: list[dict] = []
    for t in tags:
        if isinstance(t, dict) and t.get("entity_key"):
            out.append({"entity_key": str(t["entity_key"]), "kind": str(t.get("kind") or "entity")})
    return out


def recurring_from_tags(data: dict, min_cards: int = 2) -> list[dict]:
    """Derive the recurring (``>= min_cards``) entities from the per-card tags.

    Inverts the effective tags into ``entity_key -> [cn]`` and keeps entities that
    feature on at least ``min_cards`` cards — the ones that warrant a shared
    reference image. Name/kind/note come from ``entities_meta`` (the AI detection
    cache), falling back to the slug. This is what ``char_portraits`` feeds to
    image generation + ``entities.json`` instead of running its own LLM pass.
    """
    cards = data.get("cards") or {}
    meta = data.get("entities_meta") or {}
    by_entity: dict[str, list[str]] = {}
    for cn, entry in cards.items():
        if not isinstance(entry, dict):
            continue
        for t in entry.get("tags") or []:
            if isinstance(t, dict) and t.get("entity_key"):
                by_entity.setdefault(str(t["entity_key"]), [])
                if cn not in by_entity[str(t["entity_key"])]:
                    by_entity[str(t["entity_key"])].append(cn)

    out: list[dict] = []
    for key, cns in by_entity.items():
        if len(cns) < min_cards:
            continue
        m_raw = meta.get(key)
        m = m_raw if isinstance(m_raw, dict) else {}
        out.append(
            {
                "entity_key": key,
                "name": str(m.get("name") or key.replace("_", " ").title()),
                "kind": str(m.get("kind") or "entity"),
                "cards": sorted(cns),
                "note": str(m.get("note") or ""),
            }
        )
    out.sort(key=lambda e: e["entity_key"])
    return out


# ---------------------------------------------------------------------------
# Detect-or-reuse entry point
# ---------------------------------------------------------------------------


def _sidecar_is_vacuous(data: dict) -> bool:
    """True when an existing sidecar carries NO usable detection result.

    A sidecar is vacuous when a prior detection failed (``detection_failed``) OR
    every per-card record has empty tags AND ``entities_meta`` is empty — the
    indistinguishable-empty shape the numeric-card-ref bug wrote (card 6a29a6eb).
    Such a sidecar is treated as ABSENT so :func:`ensure_entity_tags` re-detects
    instead of trusting it (any ``source="manual"`` record is still preserved by
    the merge below). A sidecar with at least one non-empty tag list or a
    populated ``entities_meta`` is a real result and is trusted.
    """
    if data.get("detection_failed"):
        return True
    if data.get("entities_meta"):
        return False
    cards = data.get("cards") or {}
    return not any(isinstance(entry, dict) and entry.get("tags") for entry in cards.values())


def ensure_entity_tags(
    set_dir: Path,
    cards: list[dict],
    visual_refs: dict,
    *,
    model_id: str,
    log_dir: Path | None = None,
    thinking: str | None = None,
    force: bool = False,
) -> tuple[dict, float]:
    """Return the per-card entity-tags sidecar, detecting only when needed.

    When the sidecar already exists and ``force`` is False it is returned as-is
    (no LLM call) — a resume / a downstream stage reuses the prior decision. With
    ``force`` (the Art Prompts "Refresh AI" re-roll) the detection re-runs but
    **manual-source** per-card tags are preserved verbatim.

    Returns ``(data, cost_usd)``; ``cost_usd`` is 0.0 when the cached sidecar was
    reused.

    A sidecar that exists but carries no usable result (``detection_failed`` set,
    or every record empty + empty ``entities_meta`` — the shape the numeric-ref bug
    wrote, card 6a29a6eb) is treated as ABSENT and re-detected, so a single bad run
    no longer poisons every downstream consumer (``recurring_from_tags`` →
    char_portraits). ``source="manual"`` records survive the re-detection.
    """
    existing = load_entity_tags(set_dir)
    if existing.get("cards") and not force and not _sidecar_is_vacuous(existing):
        return existing, 0.0

    diagnostics: dict = {}
    entities, cost = detect_entity_tags(
        cards,
        visual_refs,
        model_id=model_id,
        log_dir=log_dir,
        thinking=thinking,
        diagnostics=diagnostics,
    )
    ai_card_tags = _entities_to_card_tags(entities)

    prev_cards = existing.get("cards") or {}
    merged_cards: dict[str, dict] = {}
    all_cns = {str(c.get("collector_number") or "") for c in cards if c.get("collector_number")}
    for cn in all_cns:
        prev = prev_cards.get(cn)
        # Preserve a card the user manually tagged; re-detect everything else.
        if isinstance(prev, dict) and prev.get("source") == "manual":
            merged_cards[cn] = prev
        else:
            merged_cards[cn] = {"tags": ai_card_tags.get(cn, []), "source": "ai"}

    # Refresh entity metadata from the AI pass, keeping meta for entities that
    # only survive on manual cards (so their labels don't go blank).
    merged_meta = dict(existing.get("entities_meta") or {})
    merged_meta.update(_entities_meta(entities))

    data = {"cards": merged_cards, "entities_meta": merged_meta}

    # Loud failure: entities were detected but ALL dropped by ref-validation, even
    # after the retry. Mark the sidecar diagnosably (and WARN) instead of writing an
    # indistinguishable empty result — both so a human notices and so a later
    # ensure_entity_tags re-detects it via _sidecar_is_vacuous (card 6a29a6eb).
    if diagnostics.get("detection_failed"):
        logger.warning(
            "Entity detection failed: %d entities detected but ALL were dropped by "
            "card-ref validation after %d attempt(s) (sample bad refs: %s). The "
            "sidecar %s is marked detection_failed and will be re-detected next run.",
            diagnostics.get("detected", 0),
            diagnostics.get("attempts", 1),
            diagnostics.get("sample_bad_refs", []),
            entity_tags_path(set_dir),
        )
        data["detection_failed"] = True

    save_entity_tags(set_dir, data)
    return data, cost


def set_card_tags(set_dir: Path, cn: str, tags: list[dict]) -> dict:
    """Persist a manual per-card tag override (source=manual) and return the sidecar.

    Each tag is ``{entity_key, kind}``; the entry is marked ``manual`` so a later
    AI re-detection (``ensure_entity_tags(force=True)``) preserves it. Unknown
    entity metadata is filled into ``entities_meta`` so the tab can label it.
    """
    data = load_entity_tags(set_dir)
    cards = data.setdefault("cards", {})
    meta = data.setdefault("entities_meta", {})
    clean: list[dict] = []
    for t in tags:
        if not isinstance(t, dict):
            continue
        key = normalize_entity_key(str(t.get("entity_key") or ""))
        if not key or any(c["entity_key"] == key for c in clean):
            continue
        kind = str(t.get("kind") or "entity")
        clean.append({"entity_key": key, "kind": kind})
        meta.setdefault(key, {"name": key.replace("_", " ").title(), "kind": kind, "note": ""})
    cards[cn] = {"tags": clean, "source": "manual"}
    save_entity_tags(set_dir, data)
    return data
