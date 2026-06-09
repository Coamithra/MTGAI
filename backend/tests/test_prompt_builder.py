"""Tests for artist-driven, LLM-authored art prompt generation.

Covers:
* Card immutability — ``generate_prompts_for_set`` persists a *copy* with
  ``art_prompt`` (and the credited artist) set, never mutating the loaded Card.
* Dry-run never saves.
* Artist-assignment distribution (grouped, contiguous, near-equal).
* Cameo-probability gating (0 → never, 1 → always, deterministic per card).
* User-message assembly (reference-caveat material + cameo instruction).
"""

import json

import pytest

import mtgai.art.artist_assignment as aa
import mtgai.art.prompt_builder as pb
from mtgai.art.artist_assignment import ArtPromptKnobs, assign_artists
from mtgai.models.card import Card, Color, Rarity


def _make_card(**overrides) -> Card:
    base = dict(
        name="Test Bear",
        mana_cost="{1}{G}",
        cmc=2.0,
        type_line="Creature — Bear",
        oracle_text="",
        power="2",
        toughness="2",
        rarity=Rarity.COMMON,
        colors=[Color.GREEN],
        color_identity=[Color.GREEN],
        collector_number="001",
        set_code="TST",
        card_types=["Creature"],
        subtypes=["Bear"],
    )
    base.update(overrides)
    return Card(**base)


@pytest.fixture
def loaded_card() -> Card:
    return _make_card()


def _patch_stage_inputs(monkeypatch, set_dir, *, artists=None, cameo_entities=None):
    """Patch the active project + the stage's data-loading seams on ``pb``."""
    import mtgai.io.asset_paths as asset_paths
    import mtgai.runtime.active_project as active_project

    settings = type(
        "S",
        (),
        {"get_llm_model_id": lambda self, _s: "m", "get_thinking": lambda self, _s: "disabled"},
    )()

    monkeypatch.setattr(asset_paths, "set_artifact_dir", lambda: set_dir)
    monkeypatch.setattr(
        active_project,
        "require_active_project",
        lambda: type("P", (), {"set_code": "TST", "settings": settings})(),
    )
    monkeypatch.setattr(pb, "get_artists", lambda: artists or [])
    monkeypatch.setattr(pb, "get_set_art_direction", lambda: "")
    monkeypatch.setattr(pb, "get_cameo_entities", lambda: cameo_entities or [])
    monkeypatch.setattr(pb, "get_visual_references", lambda *a, **k: "")
    # Unified entity-tagging seams: no LLM in unit tests.
    monkeypatch.setattr(pb, "get_refs", lambda: {})
    monkeypatch.setattr(
        pb, "ensure_entity_tags", lambda *a, **k: ({"cards": {}, "entities_meta": {}}, 0.0)
    )
    monkeypatch.setattr(pb, "effective_card_tags", lambda _data, _cn: [])
    monkeypatch.setattr(pb, "get_visual_references_for_keys", lambda _keys: "")
    monkeypatch.setattr(pb, "_sanitize_for_flux", lambda t: t)
    monkeypatch.setattr(
        pb, "load_art_prompt_knobs", lambda _d: ArtPromptKnobs(cameo_probability=0.0)
    )
    monkeypatch.setattr(pb.time, "sleep", lambda _s: None)


# ---------------------------------------------------------------------------
# generate_prompts_for_set — immutability + dry-run
# ---------------------------------------------------------------------------


def test_generate_prompts_persists_copy_without_mutating_original(
    monkeypatch, tmp_path, loaded_card
):
    set_dir = tmp_path / "set"
    (set_dir / "cards").mkdir(parents=True)
    (set_dir / "cards" / "001_test-bear.json").write_text(
        json.dumps({"stub": True}), encoding="utf-8"
    )

    saved: list[Card] = []
    monkeypatch.setattr(pb, "load_card", lambda _p: loaded_card)
    monkeypatch.setattr(pb, "save_card", lambda card, set_dir=None: saved.append(card))
    monkeypatch.setattr(pb, "generate_art_prompt", lambda _c, **k: ("FULL PROMPT", 10, 20))
    _patch_stage_inputs(monkeypatch, set_dir)

    summary = pb.generate_prompts_for_set()

    assert summary["processed"] == 1
    assert loaded_card.art_prompt is None  # original untouched
    assert len(saved) == 1
    assert saved[0] is not loaded_card
    assert saved[0].art_prompt == "FULL PROMPT"
    assert saved[0].name == loaded_card.name
    assert saved[0].collector_number == loaded_card.collector_number


def test_dry_run_does_not_save(monkeypatch, tmp_path, loaded_card):
    set_dir = tmp_path / "set"
    (set_dir / "cards").mkdir(parents=True)
    (set_dir / "cards" / "001_test-bear.json").write_text("{}", encoding="utf-8")

    saved: list[Card] = []
    monkeypatch.setattr(pb, "load_card", lambda _p: loaded_card)
    monkeypatch.setattr(pb, "save_card", lambda card, set_dir=None: saved.append(card))
    monkeypatch.setattr(pb, "generate_art_prompt", lambda _c, **k: ("FULL PROMPT", 10, 20))
    _patch_stage_inputs(monkeypatch, set_dir)

    pb.generate_prompts_for_set(dry_run=True)

    assert saved == []
    assert loaded_card.art_prompt is None


def test_credited_card_gets_directory_artist(monkeypatch, tmp_path, loaded_card):
    set_dir = tmp_path / "set"
    (set_dir / "cards").mkdir(parents=True)
    (set_dir / "cards" / "001_test-bear.json").write_text("{}", encoding="utf-8")

    saved: list[Card] = []
    monkeypatch.setattr(pb, "load_card", lambda _p: loaded_card)
    monkeypatch.setattr(pb, "save_card", lambda card, set_dir=None: saved.append(card))
    monkeypatch.setattr(pb, "generate_art_prompt", lambda _c, **k: ("P", 1, 1))
    _patch_stage_inputs(
        monkeypatch,
        set_dir,
        artists=[{"name": "Jane Painter", "style_prompt": "bold inks"}],
    )

    pb.generate_prompts_for_set()
    assert saved[0].artist == "Jane Painter"


def test_card_saved_callback_streams_each_card(monkeypatch, tmp_path, loaded_card):
    set_dir = tmp_path / "set"
    (set_dir / "cards").mkdir(parents=True)
    (set_dir / "cards" / "001_test-bear.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(pb, "load_card", lambda _p: loaded_card)
    monkeypatch.setattr(pb, "save_card", lambda card, set_dir=None: None)
    monkeypatch.setattr(pb, "generate_art_prompt", lambda _c, **k: ("P", 1, 1))
    _patch_stage_inputs(monkeypatch, set_dir)

    streamed: list[Card] = []
    pb.generate_prompts_for_set(card_saved_callback=streamed.append)
    assert len(streamed) == 1
    assert streamed[0].art_prompt == "P"


# ---------------------------------------------------------------------------
# Artist assignment distribution
# ---------------------------------------------------------------------------


def _pool(n: int) -> list[dict]:
    return [{"collector_number": f"{i:03d}", "rarity": "common", "colors": ["G"]} for i in range(n)]


def test_assign_artists_no_artists_returns_empty():
    assert assign_artists(_pool(5), []) == {}


def test_assign_artists_no_cards_returns_empty():
    assert assign_artists([], [{"name": "A"}]) == {}


def test_assign_artists_every_card_assigned():
    cards = _pool(25)
    artists = [{"name": "A"}, {"name": "B"}]
    out = assign_artists(cards, artists)
    assert len(out) == 25
    assert all(cn in out for cn in (c["collector_number"] for c in cards))


def test_assign_artists_slices_near_equal_and_contiguous():
    # 25 cards / 2 artists → sizes 13 + 12, contiguous in sorted order.
    cards = _pool(25)
    artists = [{"name": "A"}, {"name": "B"}]
    out = assign_artists(cards, artists)
    counts = {"A": 0, "B": 0}
    for name in out.values():
        counts[name] += 1
    assert sorted(counts.values()) == [12, 13]
    # Contiguity: with a uniform pool the sort is by collector number, so the
    # first 13 go to A, the rest to B.
    ordered_cns = [c["collector_number"] for c in cards]
    a_cns = [cn for cn in ordered_cns if out[cn] == "A"]
    assert a_cns == ordered_cns[:13]


def test_assign_artists_groups_by_rarity_then_color():
    # A mythic and a common; with 2 artists each rarity band lands on its own
    # painter (the grouped policy's whole point).
    cards = [
        {"collector_number": "010", "rarity": "common", "colors": ["G"]},
        {"collector_number": "001", "rarity": "mythic", "colors": ["R"]},
    ]
    out = assign_artists(cards, [{"name": "A"}, {"name": "B"}])
    # mythic sorts first → artist A; common → artist B.
    assert out["001"] == "A"
    assert out["010"] == "B"


def test_assign_artists_deterministic():
    cards = _pool(17)
    artists = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
    assert assign_artists(cards, artists) == assign_artists(list(reversed(cards)), artists)


# ---------------------------------------------------------------------------
# Cameo-probability gating
# ---------------------------------------------------------------------------


def test_roll_cameo_zero_probability_never_fires(monkeypatch):
    monkeypatch.setattr(
        pb, "get_cameo_entities", lambda: [{"key": "x", "kind": "character", "description": "d"}]
    )
    assert pb._roll_cameo(_make_card(), 0.0) is None


def test_roll_cameo_full_probability_always_fires(monkeypatch):
    entities = [{"key": "queen", "kind": "character", "description": "a tall queen"}]
    monkeypatch.setattr(pb, "get_cameo_entities", lambda: entities)
    out = pb._roll_cameo(_make_card(), 1.0)
    assert out is not None
    assert out["key"] == "queen"


def test_roll_cameo_empty_style_guide_never_fires(monkeypatch):
    monkeypatch.setattr(pb, "get_cameo_entities", lambda: [])
    assert pb._roll_cameo(_make_card(), 1.0) is None


def test_roll_cameo_deterministic_per_card(monkeypatch):
    entities = [
        {"key": "a", "kind": "character", "description": "one"},
        {"key": "b", "kind": "location", "description": "two"},
    ]
    monkeypatch.setattr(pb, "get_cameo_entities", lambda: entities)
    card = _make_card(collector_number="042")
    first = pb._roll_cameo(card, 0.5)
    second = pb._roll_cameo(card, 0.5)
    assert first == second  # same collector number → same decision


def test_roll_cameo_distribution_roughly_matches_probability(monkeypatch):
    entities = [{"key": "x", "kind": "character", "description": "d"}]
    monkeypatch.setattr(pb, "get_cameo_entities", lambda: entities)
    hits = sum(1 for i in range(400) if pb._roll_cameo(_make_card(collector_number=str(i)), 0.25))
    # Seeded per card; expect ~100/400. Allow a wide band so it's not flaky.
    assert 50 <= hits <= 160


# ---------------------------------------------------------------------------
# User-message assembly
# ---------------------------------------------------------------------------


def test_user_message_includes_reference_caveats_and_card():
    msg = pb.build_art_prompt_user_message(
        _make_card(name="Court Assassin", flavor_text="A blade in the dark."),
        artist_style="moody chiaroscuro",
        set_art_direction="gothic spires under perpetual dusk",
        setting_prose="## Setting\nA decaying royal court.",
        visual_refs="",
        cameo=None,
    )
    assert "moody chiaroscuro" in msg
    assert "reference" in msg.lower()
    assert "Court Assassin" in msg
    assert "A blade in the dark." in msg
    # Oracle text is labelled context-only, mechanics must not be depicted.
    assert "Author ONE finished Flux prompt" in msg


def test_user_message_includes_cameo_instruction():
    msg = pb.build_art_prompt_user_message(
        _make_card(),
        artist_style="",
        set_art_direction="",
        setting_prose="",
        visual_refs="",
        cameo={"key": "the-queen", "kind": "character", "description": "a tall crowned figure"},
    )
    assert "CAMEO REQUEST" in msg
    assert "a tall crowned figure" in msg
    assert "by appearance, not name" in msg


def test_user_message_omits_empty_sections():
    msg = pb.build_art_prompt_user_message(
        _make_card(),
        artist_style="",
        set_art_direction="",
        setting_prose="",
        visual_refs="",
        cameo=None,
    )
    assert "ARTIST STYLE" not in msg
    assert "SET ART DIRECTION" not in msg
    assert "SETTING" not in msg
    assert "CAMEO REQUEST" not in msg
    assert "CARD:" in msg  # the card block is always present


# ---------------------------------------------------------------------------
# Defensive art_prompt extraction (local-model malformed tool-call keys)
# ---------------------------------------------------------------------------


def test_extract_art_prompt_exact_key():
    assert pb._extract_art_prompt({"art_prompt": "A battered knight."}) == "A battered knight."


def test_extract_art_prompt_corrupted_duplicated_key():
    # card 001 from the QA repro: the value is fine, the key is corrupted.
    assert pb._extract_art_prompt({"art_prompt{art_prompt": "A small fox."}) == "A small fox."


def test_extract_art_prompt_corrupted_key_with_stray_char():
    # card 003: corrupted key with a stray Japanese 'ri' char (り).
    assert pb._extract_art_prompt({"art_promptり{art_prompt": "A bulky ogre."}) == "A bulky ogre."


def test_extract_art_prompt_lone_string_value_fallback():
    # No key contains 'art_prompt' at all — fall back to the single string value.
    assert pb._extract_art_prompt({"prmpt": "A glowing rune."}) == "A glowing rune."


def test_extract_art_prompt_strips_whitespace():
    assert pb._extract_art_prompt({"art_prompt": "  spaced  "}) == "spaced"


def test_extract_art_prompt_bare_string():
    assert pb._extract_art_prompt("A direct string.") == "A direct string."


def test_extract_art_prompt_none_when_no_usable_string():
    assert pb._extract_art_prompt({}) is None
    assert pb._extract_art_prompt({"art_prompt": ""}) is None
    assert pb._extract_art_prompt(None) is None
    assert pb._extract_art_prompt({"a": 1, "b": 2}) is None
    # Ambiguous: two unrelated string values, neither key matches → no guess.
    assert pb._extract_art_prompt({"x": "one", "y": "two"}) is None


def _patch_generate_art_prompt_deps(monkeypatch):
    import mtgai.runtime.active_project as active_project

    monkeypatch.setattr(pb, "get_visual_references", lambda *a, **k: "")
    settings = type(
        "S",
        (),
        {"get_llm_model_id": lambda self, _s: "m", "get_thinking": lambda self, _s: "disabled"},
    )()
    monkeypatch.setattr(
        active_project,
        "require_active_project",
        lambda: type("P", (), {"settings": settings})(),
    )


def test_generate_art_prompt_recovers_malformed_key_no_retry(monkeypatch):
    """A good-value / malformed-key payload is extracted on the first call (no retry)."""
    _patch_generate_art_prompt_deps(monkeypatch)
    calls: list[float] = []

    def fake_generate(**kwargs):
        calls.append(kwargs["temperature"])
        return {
            "result": {"art_prompt{art_prompt": "A small fox."},
            "input_tokens": 5,
            "output_tokens": 9,
        }

    monkeypatch.setattr(pb, "generate_with_tool", fake_generate)
    prompt, in_tok, out_tok = pb.generate_art_prompt(
        _make_card(),
        artist_style="",
        set_art_direction="",
        setting_prose="",
        cameo=None,
    )
    assert prompt == "A small fox."
    assert (in_tok, out_tok) == (5, 9)
    assert len(calls) == 1  # extraction succeeded, no retry


def test_generate_art_prompt_retries_at_bumped_temp_then_succeeds(monkeypatch):
    """A genuinely-unusable payload is retried at a higher temperature."""
    _patch_generate_art_prompt_deps(monkeypatch)
    temps_seen: list[float] = []
    results = [
        {"result": {}, "input_tokens": 1, "output_tokens": 1},
        {"result": {"art_prompt": "A bulky ogre."}, "input_tokens": 2, "output_tokens": 3},
    ]

    def fake_generate(**kwargs):
        temps_seen.append(kwargs["temperature"])
        return results.pop(0)

    monkeypatch.setattr(pb, "generate_with_tool", fake_generate)
    prompt, _i, _o = pb.generate_art_prompt(
        _make_card(),
        artist_style="",
        set_art_direction="",
        setting_prose="",
        cameo=None,
    )
    assert prompt == "A bulky ogre."
    assert len(temps_seen) == 2
    assert temps_seen[1] > temps_seen[0]  # second attempt bumped the temperature


def test_generate_art_prompt_raises_after_exhausted_retries(monkeypatch):
    _patch_generate_art_prompt_deps(monkeypatch)
    n_calls: list[int] = []

    def fake_generate(**kwargs):
        n_calls.append(1)
        return {"result": {}, "input_tokens": 0, "output_tokens": 0}

    monkeypatch.setattr(pb, "generate_with_tool", fake_generate)
    with pytest.raises(ValueError):
        pb.generate_art_prompt(
            _make_card(),
            artist_style="",
            set_art_direction="",
            setting_prose="",
            cameo=None,
        )
    assert len(n_calls) == pb._MAX_PROMPT_ATTEMPTS


# ---------------------------------------------------------------------------
# Knobs round-trip
# ---------------------------------------------------------------------------


def test_art_prompt_knobs_round_trip(tmp_path):
    asset = tmp_path / "asset"
    asset.mkdir()
    aa.save_art_prompt_knobs(asset, ArtPromptKnobs(cameo_probability=0.4))
    assert aa.load_art_prompt_knobs(asset).cameo_probability == pytest.approx(0.4)


def test_art_prompt_knobs_default_when_missing(tmp_path):
    asset = tmp_path / "asset"
    asset.mkdir()
    assert aa.load_art_prompt_knobs(asset).cameo_probability == pytest.approx(
        aa.DEFAULT_CAMEO_PROBABILITY
    )


def test_art_prompt_knobs_clamps_out_of_range():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ArtPromptKnobs(cameo_probability=1.5)
