"""Unit tests for the TC-2 mechanic-generator pure functions.

The LLM round-trip (``generate_mechanic_candidates``) is exercised by the
endpoint tests in ``test_pipeline/test_wizard_mechanics.py`` with a
monkeypatched ``generate_with_tool``. This module covers the helpers
that don't touch the network: prompt assembly, schema projection,
collision detection, and template loaders.
"""

from __future__ import annotations

import pytest

from mtgai.generation import mechanic_generator as mg


def _theme_fixture() -> dict:
    return {
        "code": "TST",
        "name": "Test Set",
        "theme": "Steampunk dragons in a clockwork sky.",
        "flavor_description": (
            "Floating cities tethered by brass chains. Dragons roost in steeple-spires "
            "and are courted by tinker-knights. Beneath the cloud line lies the wreck "
            "of an older world."
        ),
        "draft_archetypes": [
            {"color_pair": "WU", "name": "Aether Knights", "description": "skies-matter tempo"},
            {"color_pair": "BR", "name": "Boilerworks", "description": "discard + fling aggro"},
        ],
        "creature_types": ["Dragon", "Tinker-Knight", "Squire"],
        "constraints": [
            {"text": "At least 6 artifact creatures."},
            {"text": "No graveyard recursion."},
        ],
        "legendary_characters": [
            {"name": "Yenna of Ten Spires"},
            {"name": "Maglith the Boilermaker"},
        ],
        "notable_cards": [{"name": "Yenna's Boilerplate"}],
    }


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


def test_build_mechanic_prompts_substitutes_theme_fields() -> None:
    theme = _theme_fixture()
    sys_prompt, user_prompt = mg.build_mechanic_prompts(
        theme=theme,
        set_name="Brass Sky",
        set_size=120,
        mechanic_count=3,
    )

    assert "Brass Sky" in sys_prompt
    assert "Steampunk dragons" in sys_prompt
    assert "Floating cities" in sys_prompt
    assert "Aether Knights" in sys_prompt and "Boilerworks" in sys_prompt
    assert "At least 6 artifact creatures" in sys_prompt
    # Mechanic count threads through.
    assert "3" in sys_prompt
    assert "3" in user_prompt
    # Excluded keywords block surfaces real printed keywords.
    assert "investigate" in sys_prompt.lower()


def test_build_mechanic_prompts_handles_missing_optional_blocks() -> None:
    sys_prompt, _user_prompt = mg.build_mechanic_prompts(
        theme={"theme": "Bare bones theme."},
        set_name="",
        set_size=60,
        mechanic_count=2,
    )

    assert "Bare bones theme." in sys_prompt
    # Empty set_name still renders something rather than KeyError.
    assert "(unnamed set)" in sys_prompt or "set_name" not in sys_prompt
    # The Draft-archetypes section is omitted entirely when there are none
    # (mechanics are designed before archetypes exist) — no dead placeholder.
    assert "## Draft archetypes" not in sys_prompt
    # Other optional blocks still fall back to placeholder strings, not KeyError.
    assert "no special constraints" in sys_prompt


def test_expected_mechanic_density_lands_in_prompts() -> None:
    """Density math threads into both prompts as a min-max range string."""
    # 60 cards / (3 * 2) = 10 → "10-20"
    sys_p, user_p = mg.build_mechanic_prompts(
        theme={"theme": "x"}, set_name="X", set_size=60, mechanic_count=3
    )
    assert "10-20" in sys_p and "10-20" in user_p

    # 120 cards / (4 * 2) = 15 → "15-30"
    sys_p, user_p = mg.build_mechanic_prompts(
        theme={"theme": "x"}, set_name="X", set_size=120, mechanic_count=4
    )
    assert "15-30" in sys_p and "15-30" in user_p

    # Zero mechanic_count falls back to a default range — divide-by-zero
    # would otherwise crash the user prompt template.
    sys_p, user_p = mg.build_mechanic_prompts(
        theme={"theme": "x"}, set_name="X", set_size=60, mechanic_count=0
    )
    assert "6-10" in sys_p and "6-10" in user_p


# ---------------------------------------------------------------------------
# Sidecar template loaders
# ---------------------------------------------------------------------------


def test_load_evergreen_defaults_has_all_five_colors() -> None:
    defaults = mg.load_evergreen_defaults()
    assert set(defaults) == {"W", "U", "B", "R", "G"}
    for color, kws in defaults.items():
        assert isinstance(kws, list) and kws, f"{color} should have at least one keyword"


def test_load_pointed_questions_template_has_canonical_set() -> None:
    qs = mg.load_pointed_questions_template()
    # Every entry has the four expected fields.
    for q in qs:
        assert "id" in q and "question" in q and "category" in q and "source" in q
    # The two questions that should carry the placeholder.
    by_id = {q["id"]: q for q in qs}
    assert "{mechanic_names}" in by_id["reminder_text"]["question"]
    assert "{mechanic_names}" in by_id["keyword_collision"]["question"]


def test_render_pointed_questions_substitutes_mechanic_names() -> None:
    approved = [
        {"name": "Salvage"},
        {"name": "Malfunction"},
        {"name": "Overclock"},
    ]
    rendered = mg.render_pointed_questions(approved)
    by_id = {q["id"]: q for q in rendered}
    rendered_text = by_id["reminder_text"]["question"]
    collision_text = by_id["keyword_collision"]["question"]
    assert "Salvage, Malfunction, Overclock" in rendered_text
    assert "{mechanic_names}" not in rendered_text
    assert "Salvage, Malfunction, Overclock" in collision_text
    assert "{mechanic_names}" not in collision_text
    # Non-placeholder questions pass through untouched.
    assert by_id["keyword_nonbo"]["question"].startswith("Does this card")


def test_known_keyword_set_is_lowercase_and_includes_evergreens() -> None:
    kws = mg.known_keyword_set()
    assert "flying" in kws and "vigilance" in kws and "deathtouch" in kws
    assert "scavenge" in kws and "overload" in kws  # ASD's ground-truth collisions.
    # Lowercased, no leading/trailing whitespace.
    for k in kws:
        assert k == k.strip().lower()


# ---------------------------------------------------------------------------
# candidate_to_approved projection
# ---------------------------------------------------------------------------


def test_candidate_to_approved_renames_design_rationale_and_keeps_examples() -> None:
    candidate = {
        "name": "Test",
        "keyword_type": "keyword_ability",
        "reminder_text": "(test)",
        "colors": ["W"],
        "complexity": 1,
        "flavor_connection": "fits the world",
        "design_rationale": "rationale goes here",
        "common_patterns": ["pattern A"],
        "uncommon_patterns": [],
        "rare_patterns": [],
        "example_cards": [
            {
                "name": "Wee Tinkerer",
                "mana_cost": "{W}",
                "type_line": "Creature — Human Artificer",
                "rarity": "common",
                "oracle_text": "Test 1.",
                "power": "1",
                "toughness": "1",
            },
            {
                "name": "Grand Engineer",
                "mana_cost": "{3}{W}",
                "type_line": "Creature — Human Artificer",
                "rarity": "rare",
                "oracle_text": "Test 3.",
                "power": "3",
                "toughness": "3",
            },
        ],
        "distribution": {"common": 3, "uncommon": 2, "rare": 1, "mythic": 0},
    }
    approved = mg.candidate_to_approved(candidate)
    assert approved["design_notes"] == "rationale goes here"
    assert "design_rationale" not in approved
    # Trimmed fields never reach approved.json (whitelist projection).
    for trimmed in (
        "flavor_connection",
        "common_patterns",
        "uncommon_patterns",
        "rare_patterns",
    ):
        assert trimmed not in approved
    # example_cards propagate so card-gen can use them as concrete reference
    # designs (rendered by ``format_mechanic_block``).
    assert len(approved["example_cards"]) == 2
    assert approved["example_cards"][0]["name"] == "Wee Tinkerer"
    assert approved["example_cards"][1]["rarity"] == "rare"
    # rarity_range derives from non-zero distribution rarities.
    assert approved["rarity_range"] == ["common", "uncommon", "rare"]
    # Distribution survives.
    assert approved["distribution"]["common"] == 3


def test_candidate_to_approved_falls_back_when_distribution_is_empty() -> None:
    candidate = {
        "name": "Test",
        "complexity": 3,
        "design_rationale": "x",
    }
    approved = mg.candidate_to_approved(candidate)
    # Complexity 3 → no common (rare+ only).
    assert approved["rarity_range"] == ["uncommon", "rare", "mythic"]


# ---------------------------------------------------------------------------
# Collision detection
# ---------------------------------------------------------------------------


def test_detect_keyword_collisions_flags_printed_keywords() -> None:
    candidates = [
        {"name": "Salvage"},  # custom — ok
        {"name": "Scavenge"},  # printed — flag
        {"name": "Flying"},  # evergreen — flag
        {"name": ""},  # no name — skip
    ]
    collisions = mg.detect_keyword_collisions(candidates)
    assert collisions == {1: "Scavenge", 2: "Flying"}


def test_detect_keyword_collisions_is_case_insensitive() -> None:
    collisions = mg.detect_keyword_collisions([{"name": "scavenge"}])
    assert collisions == {0: "scavenge"}


def test_is_valid_candidate_rejects_printed_keyword_collision() -> None:
    """A name matching a printed keyword is a hard reject, so the generation
    loop regenerates rather than keeping an unrenameable colliding candidate."""
    known = mg.known_keyword_set()
    assert "reconfigure" in known  # guards the fixture: Reconfigure is printed.
    colliding = {"name": "Reconfigure", "reminder_text": "Transform this card."}
    custom = {"name": "Weaponize", "reminder_text": "Transform this card."}
    assert mg._is_valid_candidate(colliding, set(), known) is False
    # Case-insensitive, same as the display-path collision check.
    assert mg._is_valid_candidate({**colliding, "name": "reCONFIGURE"}, set(), known) is False
    # A non-colliding, well-formed candidate still passes.
    assert mg._is_valid_candidate(custom, set(), known) is True


def test_is_valid_candidate_still_rejects_dupes_and_malformed() -> None:
    """The collision check is additive — existing dupe/malformed guards hold."""
    known = mg.known_keyword_set()
    assert mg._is_valid_candidate({"name": "Weaponize"}, set(), known) is False  # no metadata
    assert mg._is_valid_candidate({"name": ""}, set(), known) is False  # blank name
    assert (
        mg._is_valid_candidate({"name": "Weaponize", "reminder_text": "x"}, {"weaponize"}, known)
        is False  # duplicate of an already-accepted name
    )


# ---------------------------------------------------------------------------
# generate_mechanic_candidates contract: count enforcement
# ---------------------------------------------------------------------------


@pytest.fixture
def _project(isolated_output, monkeypatch) -> None:
    """Pin a minimal active project + write a theme.json under its asset folder."""
    import json

    from mtgai.runtime import active_project
    from mtgai.settings import model_settings as ms

    asset = isolated_output / "sets" / "TST"
    asset.mkdir(parents=True, exist_ok=True)
    (asset / "theme.json").write_text(
        json.dumps(_theme_fixture(), indent=2),
        encoding="utf-8",
    )

    settings = ms.ModelSettings(
        asset_folder=str(asset),
        set_params=ms.SetParams(set_name="Brass Sky", set_size=120, mechanic_count=3),
    )
    active_project.write_active_project(
        active_project.ProjectState(set_code="TST", settings=settings)
    )


def _valid_mech(i: int) -> dict:
    return {
        "name": f"Mechanic{i}",
        "keyword_type": "keyword_ability",
        "reminder_text": "(...)",
        "colors": ["W"],
        "complexity": 1,
        "flavor_connection": "fits",
        "design_rationale": "good",
        "common_patterns": ["x"],
        "uncommon_patterns": [],
        "rare_patterns": [],
        "example_cards": [],
        "distribution": {"common": 1, "uncommon": 0, "rare": 0, "mythic": 0},
    }


def _tool_name(args, kwargs) -> str:
    """Extract the ``tool_schema`` name from the call args/kwargs.

    ``generate_with_tool`` is called positionally in some places and by
    keyword in others; pick the schema out of wherever it lives so the
    stubs can branch on tool name (generation vs review vs picker).
    """
    schema = kwargs.get("tool_schema")
    # Positional fallback: the schema sits after system_prompt + user_prompt.
    if schema is None and len(args) >= 3:
        schema = args[2]
    return (schema or {}).get("name", "")


def _review_passthrough_response(args, kwargs) -> dict:
    """Echo the mechanic from the review prompt back unchanged, no notes.

    The user prompt's ``mechanic_block`` carries the draft's name on the
    first line ("Name: <name>"), so we don't need to reconstruct the full
    object — the generator only requires the review tool to return
    *something dict-shaped under "mechanic"*. We return the bare minimum
    that survives the generator's defensive checks: keep the original draft
    intact by re-using ``_valid_mech`` keyed on the parsed name.
    """
    user_prompt = ""
    if "user_prompt" in kwargs:
        user_prompt = kwargs["user_prompt"]
    elif len(args) >= 2:
        user_prompt = args[1]
    name = ""
    for line in (user_prompt or "").splitlines():
        if line.startswith("Name:"):
            name = line.split(":", 1)[1].strip()
            break
    # The reviewer needs the mechanic in its original schema shape (so the
    # name+metadata survives), but the loop doesn't care about anything
    # beyond ``mechanic`` being a dict — _valid_mech(0) is enough to keep
    # the structure valid.
    mech = _valid_mech(0)
    if name:
        mech["name"] = name
    return {
        "result": {"mechanic": mech, "review_notes": ""},
        "input_tokens": 0,
        "output_tokens": 0,
    }


def _stub_n_per_call(n: int):
    """Return ``n`` fresh, distinct mechanics per call to the generation tool.

    Branches on tool name: generation tool returns mechanics; review tool
    passes through unchanged (no notes). A counter keeps names unique across
    generation calls so the dedup loop makes progress.
    """
    counter = {"next": 0}

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "review_mechanic":
            return _review_passthrough_response(args, kwargs)
        start = counter["next"]
        counter["next"] += n
        return {
            "result": {"mechanics": [_valid_mech(j) for j in range(start, start + n)]},
            "input_tokens": 10,
            "output_tokens": 20,
        }

    return stub


def _stub_distinct_then_dupes(distinct: int):
    """Yield ``distinct`` unique mechanics from the generation tool, then keep
    returning a duplicate so the loop can't make further progress (exercises
    the floor / cap). Review tool passes through unchanged."""
    counter = {"call": 0}

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "review_mechanic":
            return _review_passthrough_response(args, kwargs)
        i = counter["call"]
        counter["call"] += 1
        idx = i if i < distinct else 0  # repeats Mechanic0 once exhausted
        return {
            "result": {"mechanics": [_valid_mech(idx)]},
            "input_tokens": 10,
            "output_tokens": 20,
        }

    return stub


def test_generate_mechanic_candidates_loops_one_at_a_time(_project, monkeypatch) -> None:
    # One fresh mechanic per call -> six calls to reach the target of six.
    monkeypatch.setattr(mg, "generate_with_tool", _stub_n_per_call(1))
    result = mg.generate_mechanic_candidates()
    names = [m["name"] for m in result["mechanics"]]
    assert len(names) == 6
    assert len(set(names)) == 6  # all distinct
    # Tokens are summed across the six calls.
    assert result["input_tokens"] == 60
    assert result["output_tokens"] == 120


def test_generate_mechanic_candidates_caps_at_target(_project, monkeypatch) -> None:
    # A call returning more than needed is truncated to the target.
    monkeypatch.setattr(mg, "generate_with_tool", _stub_n_per_call(8))
    result = mg.generate_mechanic_candidates()
    assert len(result["mechanics"]) == 6


def test_generate_mechanic_candidates_honours_count_arg(_project, monkeypatch) -> None:
    # The refresh-one path asks for a single candidate.
    monkeypatch.setattr(mg, "generate_with_tool", _stub_n_per_call(1))
    result = mg.generate_mechanic_candidates(count=1)
    assert len(result["mechanics"]) == 1


def test_generate_mechanic_candidates_accepts_floor_when_stuck(_project, monkeypatch) -> None:
    # mechanic_count == 3 (fixture); the model yields only 3 distinct ones
    # then loops on a duplicate. We accept the floor rather than failing.
    monkeypatch.setattr(mg, "generate_with_tool", _stub_distinct_then_dupes(3))
    result = mg.generate_mechanic_candidates()
    assert len(result["mechanics"]) == 3


def test_generate_mechanic_candidates_raises_below_floor(_project, monkeypatch) -> None:
    # Only 2 distinct ever produced — below the floor of 3 -> failure.
    monkeypatch.setattr(mg, "generate_with_tool", _stub_distinct_then_dupes(2))
    with pytest.raises(RuntimeError, match="at least 3"):
        mg.generate_mechanic_candidates()


def test_generate_mechanic_candidates_drops_malformed_entries(_project, monkeypatch) -> None:
    # Debris (null name, or example-card-shaped objects lacking mechanic
    # metadata) is dropped; only the well-formed mechanic survives.
    def stub(*args, **kwargs):
        if _tool_name(args, kwargs) == "review_mechanic":
            return _review_passthrough_response(args, kwargs)
        return {
            "result": {
                "mechanics": [
                    {"name": None, "reminder_text": "(x)"},  # null name
                    {"mana_cost": "1R", "oracle_text": "deal 1"},  # example-card debris
                    _valid_mech(0),  # the real one
                ]
            },
            "input_tokens": 5,
            "output_tokens": 5,
        }

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    result = mg.generate_mechanic_candidates(count=1)
    assert len(result["mechanics"]) == 1
    assert result["mechanics"][0]["name"] == "Mechanic0"


# ---------------------------------------------------------------------------
# Per-mechanic review pass
# ---------------------------------------------------------------------------


def test_review_mechanic_returns_revised_with_notes(monkeypatch) -> None:
    """Happy path: reviewer tweaks the draft and returns notes; the helper
    threads the revised mechanic + notes + token totals through."""
    draft = _valid_mech(0)
    revised = dict(draft)
    revised["reminder_text"] = "(tighter rewrite under 100 chars.)"

    def stub(*args, **kwargs):
        assert _tool_name(args, kwargs) == "review_mechanic"
        return {
            "result": {
                "mechanic": revised,
                "review_notes": "Tightened reminder text from 110 → 30 chars.",
            },
            "input_tokens": 7,
            "output_tokens": 12,
        }

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    out = mg.review_mechanic(draft, model_id="any-model")
    assert out["mechanic"]["reminder_text"] == "(tighter rewrite under 100 chars.)"
    assert "Tightened" in out["review_notes"]
    assert out["input_tokens"] == 7
    assert out["output_tokens"] == 12


def test_review_mechanic_keeps_draft_on_llm_failure(monkeypatch) -> None:
    """A bad review pass must never destroy a good draft."""
    draft = _valid_mech(0)

    def boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(mg, "generate_with_tool", boom)
    out = mg.review_mechanic(draft, model_id="any-model")
    assert out["mechanic"] is draft  # exact same object — no copy
    assert out["review_notes"] == ""
    assert out["input_tokens"] == 0


def test_review_mechanic_keeps_draft_on_malformed_response(monkeypatch) -> None:
    """``mechanic`` missing → fall back to the draft so the loop can proceed."""
    draft = _valid_mech(0)
    monkeypatch.setattr(
        mg,
        "generate_with_tool",
        lambda *a, **k: {"result": {"review_notes": "n/a"}, "input_tokens": 3, "output_tokens": 4},
    )
    out = mg.review_mechanic(draft, model_id="any-model")
    assert out["mechanic"] is draft
    # Tokens still roll up so the cost surfaces accurately even on fallback.
    assert out["input_tokens"] == 3
    assert out["output_tokens"] == 4


def test_review_mechanic_reverts_rename(monkeypatch) -> None:
    """The prompt forbids renames; enforce it in code too — a misbehaving local
    model can't strand the user with a silently-renamed candidate."""
    draft = _valid_mech(0)
    renamed = dict(draft)
    renamed["name"] = "Totally Different Name"
    monkeypatch.setattr(
        mg,
        "generate_with_tool",
        lambda *a, **k: {
            "result": {"mechanic": renamed, "review_notes": "Renamed for clarity."},
            "input_tokens": 1,
            "output_tokens": 1,
        },
    )
    out = mg.review_mechanic(draft, model_id="any-model")
    assert out["mechanic"]["name"] == "Mechanic0"  # original wins


# ---------------------------------------------------------------------------
# Streaming hooks on generate_mechanic_candidates
# ---------------------------------------------------------------------------


def test_generate_mechanic_candidates_fires_streaming_hooks(_project, monkeypatch) -> None:
    """Streaming contract: on_reset fires once at start; on_draft + on_finalized
    fire in pairs per accepted candidate, in order, with the same position."""
    monkeypatch.setattr(mg, "generate_with_tool", _stub_n_per_call(1))
    events: list[tuple[str, int]] = []

    def reset_hook() -> None:
        events.append(("reset", 0))

    def draft_hook(pos: int, mech: dict) -> None:
        events.append(("draft", pos))

    def finalized_hook(pos: int, mech: dict, notes: str) -> None:
        events.append(("finalized", pos))

    result = mg.generate_mechanic_candidates(
        count=3,
        on_reset=reset_hook,
        on_draft=draft_hook,
        on_finalized=finalized_hook,
    )
    assert len(result["mechanics"]) == 3
    # One reset, then drafted/finalized in order for positions 1, 2, 3.
    assert events == [
        ("reset", 0),
        ("draft", 1),
        ("finalized", 1),
        ("draft", 2),
        ("finalized", 2),
        ("draft", 3),
        ("finalized", 3),
    ]


def test_generate_mechanic_candidates_stamps_review_notes(_project, monkeypatch) -> None:
    """The reviewer's notes (or empty string on no-op) ride on the mechanic
    so the wizard can surface what was fixed."""
    counter = {"call": 0}

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "review_mechanic":
            counter["call"] += 1
            # First review tweaks; second is a no-op (empty notes).
            notes = "Fixed example card 2." if counter["call"] == 1 else ""
            user_prompt = kwargs.get("user_prompt", "")
            name = ""
            for line in user_prompt.splitlines():
                if line.startswith("Name:"):
                    name = line.split(":", 1)[1].strip()
                    break
            mech = _valid_mech(0)
            if name:
                mech["name"] = name
            return {
                "result": {"mechanic": mech, "review_notes": notes},
                "input_tokens": 0,
                "output_tokens": 0,
            }
        # Generation path: one fresh mechanic per call.
        idx = counter["call"]  # any unique-enough seed; review counter is separate
        return {
            "result": {"mechanics": [_valid_mech(idx + 100)]},
            "input_tokens": 1,
            "output_tokens": 1,
        }

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    result = mg.generate_mechanic_candidates(count=2)
    assert len(result["mechanics"]) == 2
    assert result["mechanics"][0]["_review_notes"] == "Fixed example card 2."
    assert result["mechanics"][1]["_review_notes"] == ""


# ---------------------------------------------------------------------------
# AI picker: prompt assembly + pick resolution
# ---------------------------------------------------------------------------


def test_build_pick_prompts_numbers_candidates_and_threads_context() -> None:
    theme = _theme_fixture()
    candidates = [_valid_mech(0), _valid_mech(1), _valid_mech(2)]
    candidates[1]["name"] = "Boilerplate"
    sys_prompt, user_prompt = mg.build_pick_prompts(
        theme=theme,
        set_name="Brass Sky",
        set_size=120,
        mechanic_count=2,
        candidates=candidates,
    )
    # Set context threads into the system prompt.
    assert "Brass Sky" in sys_prompt
    assert "Steampunk dragons" in sys_prompt
    assert "Aether Knights" in sys_prompt
    assert "At least 6 artifact creatures" in sys_prompt
    assert "select" in sys_prompt.lower()
    assert "2" in sys_prompt  # mechanic_count
    # User prompt carries the numbered digest.
    assert "1. Mechanic0" in user_prompt
    assert "2. Boilerplate" in user_prompt
    assert "3. Mechanic2" in user_prompt


def test_resolve_picks_maps_1_based_and_dedupes() -> None:
    selections = [
        {"candidate_number": 2, "reason": "spread"},
        {"candidate_number": 2, "reason": "dup ignored"},  # duplicate
        {"candidate_number": 99, "reason": "out of range"},  # dropped
        {"candidate_number": 5, "reason": "complex"},
    ]
    picks, reasons = mg._resolve_picks(selections, candidate_count_total=6, target=3)
    # 1-based 2,5 -> 0-based 1,4; topped up with the first unused index (0).
    assert picks == [1, 4, 0]
    assert reasons[1] == "spread"
    assert reasons[4] == "complex"
    assert 0 not in reasons  # topped-up pick has no model reason


def test_resolve_picks_tops_up_when_too_few() -> None:
    picks, reasons = mg._resolve_picks([], candidate_count_total=6, target=3)
    assert picks == [0, 1, 2]
    assert reasons == {}


def test_resolve_picks_truncates_when_too_many() -> None:
    selections = [{"candidate_number": n, "reason": "r"} for n in range(1, 6)]
    picks, _ = mg._resolve_picks(selections, candidate_count_total=6, target=3)
    assert picks == [0, 1, 2]


def test_pick_best_mechanics_uses_llm_selection(_project, monkeypatch) -> None:
    candidates = [_valid_mech(i) for i in range(6)]

    def stub(*args, **kwargs):
        return {
            "result": {
                "selections": [
                    {"candidate_number": 2, "reason": "great in Limited"},
                    {"candidate_number": 4, "reason": "fills a color gap"},
                    {"candidate_number": 6, "reason": "deep design space"},
                ],
                "overall_rationale": "balanced color + complexity spread",
            },
            "input_tokens": 11,
            "output_tokens": 7,
        }

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    result = mg.pick_best_mechanics(candidates=candidates)
    assert result["picks"] == [1, 3, 5]  # 1-based -> 0-based
    assert [s["name"] for s in result["selections"]] == ["Mechanic1", "Mechanic3", "Mechanic5"]
    assert result["selections"][0]["reason"] == "great in Limited"
    assert result["overall_rationale"] == "balanced color + complexity spread"
    assert result["input_tokens"] == 11


def test_pick_best_mechanics_falls_back_on_error(_project, monkeypatch) -> None:
    candidates = [_valid_mech(i) for i in range(6)]

    def boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(mg, "generate_with_tool", boom)
    result = mg.pick_best_mechanics(candidates=candidates)
    # Degrades to the first N (mechanic_count=3 from the fixture).
    assert result["picks"] == [0, 1, 2]
    assert result["overall_rationale"] == ""


def test_pick_best_mechanics_skips_empty_slots(_project, monkeypatch) -> None:
    """Empty ``{}`` slots (left over from a failed refresh run) must never end
    up in the picker's output — picking them lands ``(unnamed)`` in Final picks
    and produces a junk approved.json. Both the LLM-pick path and the fallback
    top-up must skip them."""
    # Pool of 6 with empties at indices 1, 2, 4. Filled at 0, 3, 5.
    candidates: list[dict] = [
        _valid_mech(0),
        {},
        {},
        _valid_mech(3),
        {},
        _valid_mech(5),
    ]
    candidates[0]["name"] = "Alpha"
    candidates[3]["name"] = "Delta"
    candidates[5]["name"] = "Foxtrot"

    # LLM picks a mix including an empty (index 2 → candidate_number 3 in
    # 1-based) — that pick must be dropped and topped up from filled-only.
    def stub(*args, **kwargs):
        return {
            "result": {
                "selections": [
                    {"candidate_number": 1, "reason": "alpha"},
                    {"candidate_number": 3, "reason": "empty pick — invalid"},
                    {"candidate_number": 4, "reason": "delta"},
                ],
                "overall_rationale": "ok",
            },
            "input_tokens": 1,
            "output_tokens": 1,
        }

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    result = mg.pick_best_mechanics(candidates=candidates)
    # mechanic_count=3 from fixture; the empty-slot pick was dropped and
    # the top-up grabbed the next filled slot (index 5 / Foxtrot).
    assert result["picks"] == [0, 3, 5]
    assert [s["name"] for s in result["selections"]] == ["Alpha", "Delta", "Foxtrot"]


def test_pick_best_mechanics_fallback_skips_empty_slots(_project, monkeypatch) -> None:
    """When the LLM call itself fails, the fallback also picks only filled
    candidates (not the first N regardless of content)."""
    candidates: list[dict] = [
        {},
        _valid_mech(1),
        {},
        _valid_mech(3),
        _valid_mech(5),
        {},
    ]
    candidates[1]["name"] = "Bravo"
    candidates[3]["name"] = "Delta"
    candidates[4]["name"] = "Echo"

    def boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(mg, "generate_with_tool", boom)
    result = mg.pick_best_mechanics(candidates=candidates)
    # Fallback picks the first 3 *filled* slots, skipping empties.
    assert result["picks"] == [1, 3, 4]
    assert [s["name"] for s in result["selections"]] == ["Bravo", "Delta", "Echo"]


def test_pick_best_mechanics_falls_back_when_no_selections(_project, monkeypatch) -> None:
    candidates = [_valid_mech(i) for i in range(6)]
    monkeypatch.setattr(mg, "generate_with_tool", lambda *a, **k: {"result": {}})
    result = mg.pick_best_mechanics(candidates=candidates)
    assert result["picks"] == [0, 1, 2]


# ---------------------------------------------------------------------------
# persist_mechanic_selection
# ---------------------------------------------------------------------------


def test_persist_mechanic_selection_writes_all_files(tmp_path) -> None:
    import json

    candidates = [_valid_mech(i) for i in range(6)]
    mech_dir = tmp_path / "mechanics"
    approved = mg.persist_mechanic_selection(
        mech_dir,
        candidates,
        [0, 2],
        source="ai",
        overall_rationale="why these two",
        selections=[{"name": "Mechanic0", "reason": "a"}, {"name": "Mechanic2", "reason": "b"}],
        model_id="sonnet-test",
    )
    # Returns the projected approved list.
    assert [a["name"] for a in approved] == ["Mechanic0", "Mechanic2"]
    assert "design_notes" in approved[0] and "design_rationale" not in approved[0]

    # All sidecars + approved + rationale written.
    for name in (
        "candidates.json",
        "evergreen-keywords.json",
        "pointed-questions.json",
        "functional-tags.json",
        "pick-rationale.json",
        "approved.json",
    ):
        assert (mech_dir / name).exists(), name

    rationale = json.loads((mech_dir / "pick-rationale.json").read_text(encoding="utf-8"))
    assert rationale["source"] == "ai"
    assert rationale["model_id"] == "sonnet-test"
    assert rationale["overall_rationale"] == "why these two"
    assert len(rationale["selections"]) == 2
    assert "picked_at" in rationale
    on_disk_approved = json.loads((mech_dir / "approved.json").read_text(encoding="utf-8"))
    assert [a["name"] for a in on_disk_approved] == ["Mechanic0", "Mechanic2"]
