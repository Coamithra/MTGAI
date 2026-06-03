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


def test_build_mechanic_system_prompt_substitutes_theme_fields() -> None:
    theme = _theme_fixture()
    sys_prompt = mg.build_mechanic_system_prompt(
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
    # Excluded keywords block surfaces real printed keywords.
    assert "investigate" in sys_prompt.lower()


def test_build_mechanic_system_prompt_handles_missing_optional_blocks() -> None:
    sys_prompt = mg.build_mechanic_system_prompt(
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


def test_expected_mechanic_density_lands_in_system_prompt() -> None:
    """Density math threads into the system prompt as a min-max range string."""
    # 60 cards / (3 * 2) = 10 → "10-20"
    sys_p = mg.build_mechanic_system_prompt(
        theme={"theme": "x"}, set_name="X", set_size=60, mechanic_count=3
    )
    assert "10-20" in sys_p

    # 120 cards / (4 * 2) = 15 → "15-30"
    sys_p = mg.build_mechanic_system_prompt(
        theme={"theme": "x"}, set_name="X", set_size=120, mechanic_count=4
    )
    assert "15-30" in sys_p

    # Zero mechanic_count falls back to a default range — divide-by-zero
    # would otherwise crash the prompt template.
    sys_p = mg.build_mechanic_system_prompt(
        theme={"theme": "x"}, set_name="X", set_size=60, mechanic_count=0
    )
    assert "6-10" in sys_p


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
    # rarity_range derives from complexity (1 → spans the whole range).
    assert approved["rarity_range"] == ["common", "uncommon", "rare", "mythic"]
    # distribution was removed from the schema — it must never reach approved.json.
    assert "distribution" not in approved


def test_candidate_to_approved_rarity_range_from_complexity() -> None:
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


def test_forbidden_placeholder_flags_bracket_placeholders() -> None:
    """The deterministic gen-time guard catches the `[effect]`/`[cost]` placeholders
    the prompts forbid (and the weak quant slips in), returning the offender."""
    assert mg._forbidden_placeholder("(..., [effect].)") == "[effect]"
    assert mg._forbidden_placeholder("({T}, pay [cost]: draw.)") == "[cost]"
    assert mg._forbidden_placeholder("(Do [target] thing.)") == "[target]"
    assert mg._forbidden_placeholder("(... {cost} ...)") == "{cost}"


def test_forbidden_placeholder_ignores_real_mana_and_loyalty_symbols() -> None:
    """Genuine Magic symbols ({W}, {2}, {T}, {W/U}, {X}, {C}, {E}) are NOT
    placeholders — the brace rule only fires on a 2+-lowercase-letter word."""
    for clean in (
        "(Remove N energy counters from this creature.)",
        "({T}: Add {C}.)",
        "(Pay {2}{W/U}, {T}: scry 1.)",
        "({X}{W}: this gains +X/+0.)",
        "(You get {E}{E} (two energy counters).)",
        "(Crew 2. Equip {2}. Sacrifice this: add {C}{C}.)",
    ):
        assert mg._forbidden_placeholder(clean) is None, clean
    assert mg._forbidden_placeholder(None) is None  # non-str is harmless


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


def _reviewer_ok_response(args, kwargs) -> dict:
    """A council reviewer that passes the mechanic — verdict OK, no issues.

    With all reviewers OK the council exits round 1 without ever calling the
    synth, so the draft is accepted unchanged (the cheap, common path). Zero
    tokens so token-summation assertions stay about the generation calls.
    """
    return {
        "result": {"verdict": "OK", "issues": []},
        "input_tokens": 0,
        "output_tokens": 0,
    }


def _stub_n_per_call(n: int):
    """Return ``n`` fresh, distinct mechanics per call to the generation tool.

    Branches on tool name: the generation tool returns mechanics; every council
    reviewer passes the mechanic OK (so no synth runs and the draft is accepted
    unchanged). A counter keeps names unique across generation calls so the
    dedup loop makes progress.
    """
    counter = {"next": 0}

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "submit_mechanic_review":
            return _reviewer_ok_response(args, kwargs)
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
        if tool == "submit_mechanic_review":
            return _reviewer_ok_response(args, kwargs)
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
        if _tool_name(args, kwargs) == "submit_mechanic_review":
            return _reviewer_ok_response(args, kwargs)
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
# Per-mechanic council review (council_review)
# ---------------------------------------------------------------------------


def _reviewer(
    verdict: str,
    *,
    category: str = "wording",
    severity: str = "major",
    scope: str | None = None,
) -> dict:
    issue = {"category": category, "severity": severity, "description": f"{category} problem"}
    if scope is not None:
        issue["scope"] = scope
    issues = [] if verdict == "OK" else [issue]
    return {"result": {"verdict": verdict, "issues": issues}, "input_tokens": 1, "output_tokens": 1}


def _example_pair() -> list[dict]:
    """Two well-formed replacement example cards for the example-fix path."""
    return [
        {
            "name": "Scrap Scout",
            "mana_cost": "{G}",
            "type_line": "Creature — Beast",
            "rarity": "common",
            "oracle_text": "Ignite 1: this creature gains flying until end of turn.",
            "power": "1",
            "toughness": "1",
        },
        {
            "name": "Forge Tyrant",
            "mana_cost": "{3}{R}",
            "type_line": "Creature — Dragon",
            "rarity": "rare",
            "oracle_text": "Ignite 3: this creature deals 3 damage to any target.",
            "power": "4",
            "toughness": "4",
        },
    ]


def _examples(cards: list[dict] | None, *, notes: str = "Reworked the examples.") -> dict:
    result: dict = {"notes": notes}
    if cards is not None:
        result["example_cards"] = cards
    return {"result": result, "input_tokens": 3, "output_tokens": 3}


def _synth(revised: dict | None, *, notes: str = "Revised.", verdict: str = "OK") -> dict:
    result: dict = {
        "synthesis": "agreed",
        "consensus_issues": [],
        "verdict": verdict,
        "review_notes": notes,
    }
    if revised is not None:
        result["revised_mechanic"] = revised
    return {"result": result, "input_tokens": 5, "output_tokens": 5}


def test_council_review_all_ok_skips_synth(monkeypatch) -> None:
    """All reviewers OK → no synthesis, draft returned unchanged, verdict OK."""
    draft = _valid_mech(0)
    synth_calls = {"n": 0}

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "submit_mechanic_review":
            return _reviewer("OK")
        if tool == "submit_mechanic_synthesis":
            synth_calls["n"] += 1
            return _synth(draft)
        raise AssertionError(f"unexpected tool {tool}")

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    out = mg.council_review(draft, model_id="any-model")
    assert out["verdict"] == "OK"
    assert out["mechanic"] is draft  # unchanged
    assert out["review_notes"] == ""
    assert out["reasons"] == []
    assert synth_calls["n"] == 0
    # Three reviewers, one round, 1 in / 1 out each.
    assert out["input_tokens"] == 3
    assert out["output_tokens"] == 3


def test_council_review_lone_major_blocks_despite_majority(monkeypatch) -> None:
    """A MAJORITY of effective-OK reviewers passes round 1 — one lone REVISE
    (citing a blocking defect) was the OLD majority gate. Under the
    severity-weighted gate a lone reviewer citing a MAJOR blocking defect now
    BLOCKS even against a 2-OK majority (the Integrate fix: an objective defect
    must not lose to reviewers who missed it); the synth then runs to fix it."""
    draft = _valid_mech(0)
    revised = dict(draft)
    revised["reminder_text"] = "(fixed)"
    rcalls = {"n": 0}
    synth_calls = {"n": 0}

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "submit_mechanic_review":
            rcalls["n"] += 1
            # Round 1: members 1 & 2 OK, member 3 REVISE (MAJOR) -> blocks despite
            # the 2-of-3 majority. Round 2 (after synth): all OK -> passes.
            if rcalls["n"] == 3:
                return _reviewer("REVISE")  # default category=wording, severity=major
            return _reviewer("OK")
        if tool == "submit_mechanic_synthesis":
            synth_calls["n"] += 1
            return _synth(revised)
        raise AssertionError(f"unexpected tool {tool}")

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    out = mg.council_review(draft, model_id="any-model")
    assert synth_calls["n"] == 1  # the lone major forced a synth -- not outvoted
    assert out["verdict"] == "OK"  # round 2 cleared it
    assert out["mechanic"]["reminder_text"] == "(fixed)"


def test_council_review_minor_blocking_only_is_soft_pass(monkeypatch) -> None:
    """A REVISE citing only a MINOR blocking-category issue (a nit, e.g. a missing
    "token") is advisory and never blocks. All three reviewers nit-REVISE on
    wording/minor -> passes round 1, no synth (the Protocol wording-churn fix)."""
    draft = _valid_mech(0)
    synth_calls = {"n": 0}

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "submit_mechanic_review":
            return _reviewer("REVISE", category="wording", severity="minor")
        if tool == "submit_mechanic_synthesis":
            synth_calls["n"] += 1
            return _synth(draft)
        raise AssertionError(f"unexpected tool {tool}")

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    out = mg.council_review(draft, model_id="any-model")
    assert out["verdict"] == "OK"
    assert synth_calls["n"] == 0
    assert out["reasons"] == []  # minor nits don't become regen reasons


def test_council_review_advisory_only_revise_is_soft_pass(monkeypatch) -> None:
    """All reviewers vote REVISE but cite only an advisory (``elegant``) issue —
    no blocking defect — so the council treats every vote as effective-OK and
    passes round 1 without synthesizing. The gate is "is it broken?", not taste."""
    draft = _valid_mech(0)
    synth_calls = {"n": 0}

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "submit_mechanic_review":
            return _reviewer("REVISE", category="elegant")
        if tool == "submit_mechanic_synthesis":
            synth_calls["n"] += 1
            return _synth(draft)
        raise AssertionError(f"unexpected tool {tool}")

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    out = mg.council_review(draft, model_id="any-model")
    assert out["verdict"] == "OK"
    assert out["mechanic"] is draft
    assert synth_calls["n"] == 0
    assert out["reasons"] == []  # advisory issues don't become regen reasons


def test_council_review_skips_final_synth_when_regen_will_follow(monkeypatch) -> None:
    """With skip_final_synth=True the Phase-2 synth is skipped on the FINAL round
    (a from-scratch regen would discard it). Non-final rounds still synth; the
    result is REVISE with the round's open issues as `reasons` for the regen."""
    draft = _valid_mech(0)
    synth_calls = {"n": 0}

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "submit_mechanic_review":
            return _reviewer("REVISE")  # MAJOR -> always blocks, so it never passes
        if tool == "submit_mechanic_synthesis":
            synth_calls["n"] += 1
            # A valid revision so the loop re-reviews and runs every round.
            return _synth(dict(draft, reminder_text="(r)"))
        raise AssertionError(f"unexpected tool {tool}")

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    out = mg.council_review(draft, model_id="any-model", max_iterations=3, skip_final_synth=True)
    assert out["verdict"] == "REVISE"
    # Rounds 1 and 2 synth; the final round (3) is skipped -> 2 calls, not 3.
    assert synth_calls["n"] == 2
    assert out["reasons"]  # open issues still captured for the regen


def test_council_review_runs_final_synth_on_last_attempt(monkeypatch) -> None:
    """Default skip_final_synth=False (the last attempt, no regen left): the synth
    runs on every failing round including the final one, so its best-effort
    revision is available for the caller to keep."""
    draft = _valid_mech(0)
    synth_calls = {"n": 0}

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "submit_mechanic_review":
            return _reviewer("REVISE")
        if tool == "submit_mechanic_synthesis":
            synth_calls["n"] += 1
            return _synth(dict(draft, reminder_text="(r)"))  # valid revision each round
        raise AssertionError(f"unexpected tool {tool}")

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    out = mg.council_review(draft, model_id="any-model", max_iterations=3)
    assert out["verdict"] == "REVISE"
    assert synth_calls["n"] == 3  # all three rounds synth


def test_effective_verdict_blocks_only_on_blocking_category() -> None:
    """The taste standards are gone from the schema and only concrete defects
    gate; an empty or advisory-only REVISE is an effective OK."""
    assert "interesting" not in mg.MECHANIC_ISSUE_CATEGORIES
    assert "unique" not in mg.MECHANIC_ISSUE_CATEGORIES
    assert "elegant" not in mg.MECHANIC_BLOCKING_CATEGORIES
    block = {"category": "wording", "severity": "major", "description": "bad templating"}
    advisory = {"category": "elegant", "severity": "minor", "description": "wordy"}
    assert mg._effective_verdict({"verdict": "OK", "issues": []}) == "OK"
    assert mg._effective_verdict({"verdict": "REVISE", "issues": []}) == "OK"
    assert mg._effective_verdict({"verdict": "REVISE", "issues": [advisory]}) == "OK"
    # A MINOR-severity issue in a blocking category is a nit -> advisory, soft OK.
    minor_block = {"category": "wording", "severity": "minor", "description": "omit token"}
    assert mg._effective_verdict({"verdict": "REVISE", "issues": [minor_block]}) == "OK"
    assert mg._effective_verdict({"verdict": "REVISE", "issues": [block]}) == "REVISE"
    assert mg._effective_verdict({"verdict": "REVISE", "issues": [advisory, block]}) == "REVISE"
    # A co-cited major still gates even alongside an advisory nit.
    assert mg._effective_verdict({"verdict": "REVISE", "issues": [minor_block, block]}) == "REVISE"


def test_council_review_revises_then_passes(monkeypatch) -> None:
    """Round 1 REVISE → synth revises in place → round 2 OK → final is the revision."""
    draft = _valid_mech(0)
    revised = dict(draft)
    revised["reminder_text"] = "(tightened)"
    rcalls = {"n": 0}

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "submit_mechanic_review":
            rcalls["n"] += 1
            return _reviewer("REVISE" if rcalls["n"] <= 3 else "OK")
        if tool == "submit_mechanic_synthesis":
            return _synth(revised, notes="Tightened wording.")
        raise AssertionError(f"unexpected tool {tool}")

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    out = mg.council_review(draft, model_id="any-model")
    assert out["verdict"] == "OK"
    assert out["mechanic"]["reminder_text"] == "(tightened)"
    assert "Tightened wording." in out["review_notes"]


def test_council_review_budget_exhausted_keeps_last_revision(monkeypatch) -> None:
    """Reviewers never agree → after the iteration budget the last revision is
    kept, honestly flagged REVISE, with the round's open issues as ``reasons``."""
    draft = _valid_mech(0)

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "submit_mechanic_review":
            return _reviewer("REVISE", category="wording")
        if tool == "submit_mechanic_synthesis":
            rev = dict(draft)
            rev["reminder_text"] = "(rev)"
            return _synth(rev, verdict="REVISE")
        raise AssertionError(f"unexpected tool {tool}")

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    out = mg.council_review(draft, model_id="any-model", max_iterations=3)
    assert out["verdict"] == "REVISE"
    assert out["mechanic"]["reminder_text"] == "(rev)"
    assert out["reasons"] and "wording" in out["reasons"][0]


def test_council_review_reviewer_collapse_keeps_draft(monkeypatch) -> None:
    """Every reviewer call failing → no critiques → keep the draft (safe
    fallback), and the synth is never reached."""
    draft = _valid_mech(0)

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "submit_mechanic_review":
            raise RuntimeError("reviewer down")
        raise AssertionError("synth must not run when there are no reviews")

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    out = mg.council_review(draft, model_id="any-model")
    assert out["verdict"] == "OK"
    assert out["mechanic"] is draft
    assert out["review_notes"] == ""


def test_council_review_synth_failure_keeps_prior(monkeypatch) -> None:
    """A failing synth keeps the current mechanic, flagged REVISE for the
    caller's regenerate fallback — never crashes the council."""
    draft = _valid_mech(0)

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "submit_mechanic_review":
            return _reviewer("REVISE")
        if tool == "submit_mechanic_synthesis":
            raise RuntimeError("synth down")
        raise AssertionError(f"unexpected tool {tool}")

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    out = mg.council_review(draft, model_id="any-model")
    assert out["verdict"] == "REVISE"
    assert out["mechanic"] is draft  # unchanged on synth failure


def test_council_review_synth_retries_once_then_succeeds(monkeypatch) -> None:
    """A truncated/empty synth on the first attempt is retried once at the same
    budget; a good second attempt is taken in place (no wasted regen)."""
    draft = _valid_mech(0)
    revised = {**draft, "reminder_text": "(fixed wording)"}
    rcalls = {"n": 0}
    scalls = {"n": 0}

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "submit_mechanic_review":
            rcalls["n"] += 1
            # Round 1 (reviewers 1-3) blocks; the revision passes round 2.
            return _reviewer("REVISE" if rcalls["n"] <= 3 else "OK")
        if tool == "submit_mechanic_synthesis":
            scalls["n"] += 1
            if scalls["n"] == 1:
                raise RuntimeError("synth truncated")  # first attempt misses
            return _synth(revised)
        raise AssertionError(f"unexpected tool {tool}")

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    out = mg.council_review(draft, model_id="any-model")
    assert scalls["n"] == 2  # failed once, retried once within the same round
    assert out["mechanic"]["reminder_text"] == "(fixed wording)"
    assert out["verdict"] == "OK"


def test_council_review_reverts_synth_rename(monkeypatch) -> None:
    """The synth may not rename — enforce it in code (the prompt forbids it)."""
    draft = _valid_mech(0)  # name "Mechanic0"
    rcalls = {"n": 0}

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "submit_mechanic_review":
            rcalls["n"] += 1
            return _reviewer("REVISE" if rcalls["n"] <= 3 else "OK")
        if tool == "submit_mechanic_synthesis":
            renamed = dict(draft)
            renamed["name"] = "Totally Different Name"
            renamed["reminder_text"] = "(rev)"
            return _synth(renamed)
        raise AssertionError(f"unexpected tool {tool}")

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    out = mg.council_review(draft, model_id="any-model")
    assert out["mechanic"]["name"] == "Mechanic0"  # original wins


def test_blocking_issues_and_scope_helpers() -> None:
    """`_blocking_issues` keeps only major blocking-category issues; `_all_example_scoped`
    is True only when every such issue is explicitly example-scoped (missing scope
    defaults to mechanic)."""
    ex = {"category": "playable", "severity": "major", "scope": "example", "description": "x"}
    mech = {"category": "wording", "severity": "major", "scope": "mechanic", "description": "y"}
    no_scope = {"category": "playable", "severity": "major", "description": "z"}
    minor = {"category": "wording", "severity": "minor", "scope": "example", "description": "n"}
    advisory = {"category": "elegant", "severity": "major", "scope": "example", "description": "e"}

    reviews = [
        {"verdict": "REVISE", "issues": [ex, minor, advisory]},
        {"verdict": "REVISE", "issues": [mech]},
    ]
    # minor (not major) and advisory (elegant is not a blocking category) are excluded.
    assert mg._blocking_issues(reviews) == [ex, mech]
    assert mg._all_example_scoped([ex]) is True
    assert mg._all_example_scoped([ex, mech]) is False
    assert mg._all_example_scoped([ex, no_scope]) is False  # missing scope -> mechanic
    assert mg._all_example_scoped([]) is False


def test_blocking_issues_skips_ok_voting_reviewers() -> None:
    """`_blocking_issues` ignores issues from a reviewer whose *effective* verdict is
    OK (voted OK, or REVISE without any major blocking defect), mirroring
    `_open_issue_reasons` — a stray major issue from an OK voter must not skew scope."""
    ex = {"category": "playable", "severity": "major", "scope": "example", "description": "x"}
    stray = {"category": "wording", "severity": "major", "scope": "mechanic", "description": "y"}
    advisory = {"category": "elegant", "severity": "major", "scope": "example", "description": "e"}

    reviews = [
        {"verdict": "REVISE", "issues": [ex]},  # genuinely blocking
        {"verdict": "OK", "issues": [stray]},  # OK vote: its issue must be ignored
        {"verdict": "REVISE", "issues": [advisory]},  # REVISE but no major blocking -> OK
    ]
    # Only the truly-blocking reviewer's example-scoped issue survives, so the loop
    # routes to the example-only fix instead of a full mechanic revise.
    assert mg._blocking_issues(reviews) == [ex]
    assert mg._all_example_scoped(mg._blocking_issues(reviews)) is True


def test_council_review_example_only_routes_to_example_fix(monkeypatch) -> None:
    """When EVERY blocking issue is example-scoped the loop fixes ONLY the examples
    (submit_mechanic_examples), never the synth, and the mechanic's definition is
    spliced through byte-identical while example_cards is replaced."""
    draft = _valid_mech(0)
    draft["reminder_text"] = "(Remove N energy counters from this creature.)"
    new_examples = _example_pair()
    rcalls = {"n": 0}
    synth_calls = {"n": 0}
    fix_calls = {"n": 0}

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "submit_mechanic_review":
            rcalls["n"] += 1
            return _reviewer("REVISE" if rcalls["n"] <= 3 else "OK", scope="example")
        if tool == "submit_mechanic_examples":
            fix_calls["n"] += 1
            return _examples(new_examples, notes="Fixed the dead-on-use example.")
        if tool == "submit_mechanic_synthesis":
            synth_calls["n"] += 1
            return _synth(draft)
        raise AssertionError(f"unexpected tool {tool}")

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    out = mg.council_review(draft, model_id="any-model")
    assert out["verdict"] == "OK"
    assert fix_calls["n"] == 1
    assert synth_calls["n"] == 0  # the mechanic definition was never re-emitted
    assert out["mechanic"]["example_cards"] == new_examples
    # The reminder / name are untouched by the example-fix splice.
    assert out["mechanic"]["reminder_text"] == "(Remove N energy counters from this creature.)"
    assert out["mechanic"]["name"] == "Mechanic0"
    assert "Fixed the dead-on-use example." in out["review_notes"]


def test_council_review_mixed_scope_routes_to_synth(monkeypatch) -> None:
    """A single mechanic-scoped blocking issue alongside an example-scoped one
    implicates the keyword itself, so the full synth runs — not the example-fix."""
    draft = _valid_mech(0)
    revised = dict(draft)
    revised["reminder_text"] = "(fixed)"
    rcalls = {"n": 0}
    synth_calls = {"n": 0}

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "submit_mechanic_review":
            rcalls["n"] += 1
            if rcalls["n"] > 3:
                return _reviewer("OK")
            # Round 1: member 1 example-scoped, members 2 & 3 mechanic-scoped.
            return _reviewer("REVISE", scope="example" if rcalls["n"] == 1 else "mechanic")
        if tool == "submit_mechanic_examples":
            raise AssertionError("example-fix must not run when a mechanic issue is present")
        if tool == "submit_mechanic_synthesis":
            synth_calls["n"] += 1
            return _synth(revised)
        raise AssertionError(f"unexpected tool {tool}")

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    out = mg.council_review(draft, model_id="any-model")
    assert synth_calls["n"] == 1
    assert out["verdict"] == "OK"
    assert out["mechanic"]["reminder_text"] == "(fixed)"


def test_council_review_example_fix_failure_keeps_prior(monkeypatch) -> None:
    """A failing example-fix keeps the current mechanic, flagged REVISE — the same
    safe fallback as a failing synth."""
    draft = _valid_mech(0)

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "submit_mechanic_review":
            return _reviewer("REVISE", scope="example")
        if tool == "submit_mechanic_examples":
            raise RuntimeError("example-fix down")
        raise AssertionError(f"unexpected tool {tool}")

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    out = mg.council_review(draft, model_id="any-model")
    assert out["verdict"] == "REVISE"
    assert out["mechanic"] is draft  # unchanged on example-fix failure


def test_council_review_emits_progress_events(monkeypatch) -> None:
    """``on_event`` streams the council happening live (what the wizard's council
    panel renders): a ``round_start`` per round, a ``reviewer`` per member with its
    verdict, then ``synth_start`` / ``synth_done`` (carrying the revised mechanic)
    when a round revises. Revise-then-pass: round 1 all REVISE → synth → round 2 OK."""
    draft = _valid_mech(0)
    revised = dict(draft)
    revised["reminder_text"] = "(tightened)"
    rcalls = {"n": 0}

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "submit_mechanic_review":
            rcalls["n"] += 1
            return _reviewer("REVISE" if rcalls["n"] <= 3 else "OK")
        if tool == "submit_mechanic_synthesis":
            return _synth(revised, notes="Tightened wording.")
        raise AssertionError(f"unexpected tool {tool}")

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    events: list[dict] = []
    out = mg.council_review(draft, model_id="any-model", on_event=events.append)

    assert out["verdict"] == "OK"
    # The kind sequence the panel walks: round 1 (3 REVISE → synth) then round 2 (3 OK).
    assert [e["kind"] for e in events] == [
        "round_start",
        "reviewer",
        "reviewer",
        "reviewer",
        "synth_start",
        "synth_done",
        "round_start",
        "reviewer",
        "reviewer",
        "reviewer",
    ]
    # round_start carries the counters the panel shows (round x/max, council size).
    assert events[0] == {"kind": "round_start", "round": 1, "max_rounds": 3, "council_size": 3}
    # Each reviewer event identifies its member (the thumb slot) + its verdict.
    round1_reviewers = [e for e in events[1:4]]
    assert [e["member"] for e in round1_reviewers] == [1, 2, 3]
    assert all(e["verdict"] == "REVISE" for e in round1_reviewers)
    assert all(e["verdict"] == "OK" for e in events[7:10])
    # synth_done carries the revised mechanic so the UI can pop the new text in.
    synth_done = next(e for e in events if e["kind"] == "synth_done")
    assert synth_done["mechanic"]["reminder_text"] == "(tightened)"
    assert synth_done["review_notes"] == "Tightened wording."


def test_council_review_emits_error_verdict_on_failed_reviewer(monkeypatch) -> None:
    """A reviewer call that raises still emits a ``reviewer`` event (verdict
    ``error``) so the panel shows the slot was attempted-and-skipped, not stuck
    awaiting. With every reviewer down the council keeps the draft (safe fallback)."""
    draft = _valid_mech(0)

    def stub(*args, **kwargs):
        if _tool_name(args, kwargs) == "submit_mechanic_review":
            raise RuntimeError("reviewer down")
        raise AssertionError("synth must not run when there are no reviews")

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    events: list[dict] = []
    out = mg.council_review(draft, model_id="any-model", on_event=events.append)

    assert out["verdict"] == "OK"  # un-reviewable draft kept, not destroyed
    reviewer_events = [e for e in events if e["kind"] == "reviewer"]
    assert reviewer_events and all(e["verdict"] == "error" for e in reviewer_events)


# ---------------------------------------------------------------------------
# Reasoning-overrun budget escalation (sticky for the whole run)
# ---------------------------------------------------------------------------


def test_generate_mechanic_candidates_escalates_budget_and_sticks(_project, monkeypatch) -> None:
    """A reasoning overrun on a gen call escalates the budget to HEAVY and KEEPS
    it there for every later call in the run — we pay the fail-then-bump tax once
    for the phase, not once per candidate slot (regression for the IQ2_M
    finish_reason=length failure; see learnings/reasoning-budget-overrun.md)."""
    from mtgai.generation.token_budgets import HEAVY, STANDARD
    from mtgai.generation.token_utils import OutputTruncatedError

    gen_budgets: list[int] = []
    counter = {"next": 0}
    truncated = {"done": False}

    def stub(*args, **kwargs):
        if _tool_name(args, kwargs) == "submit_mechanic_review":
            return _reviewer_ok_response(args, kwargs)
        mt = kwargs.get("max_tokens")
        assert mt is not None  # the escalation helper always threads a budget
        if not truncated["done"]:
            # First gen call overruns at the STANDARD budget, like the 2-bit
            # quant burning the whole budget on chain-of-thought.
            truncated["done"] = True
            assert mt == STANDARD
            raise OutputTruncatedError("overran on reasoning", eval_count=mt, num_predict=mt)
        gen_budgets.append(mt)
        i = counter["next"]
        counter["next"] += 1
        return {
            "result": {"mechanics": [_valid_mech(i)]},
            "input_tokens": 10,
            "output_tokens": 20,
        }

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    result = mg.generate_mechanic_candidates()

    assert len(result["mechanics"]) == 6
    # The escalated retry AND every subsequent slot's gen call ran at HEAVY.
    assert gen_budgets
    assert all(b == HEAVY for b in gen_budgets)


def test_council_review_escalates_reviewer_budget(monkeypatch) -> None:
    """The run-shared budget threads into the council: a reviewer overrun
    escalates it, and the remaining reviewers run at HEAVY (the bump sticks
    across the council too, not just the generation loop)."""
    from mtgai.generation.token_budgets import HEAVY, STANDARD
    from mtgai.generation.token_utils import OutputTruncatedError

    draft = _valid_mech(0)
    reviewer_budgets: list[int] = []
    truncated = {"done": False}

    def stub(*args, **kwargs):
        if _tool_name(args, kwargs) != "submit_mechanic_review":
            raise AssertionError("only reviewer calls expected (all pass OK -> no synth)")
        mt = kwargs.get("max_tokens")
        assert mt is not None  # the escalation helper always threads a budget
        if not truncated["done"]:
            truncated["done"] = True
            assert mt == STANDARD
            raise OutputTruncatedError("overran on reasoning", eval_count=mt, num_predict=mt)
        reviewer_budgets.append(mt)
        return {"result": {"verdict": "OK", "issues": []}, "input_tokens": 0, "output_tokens": 0}

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    out = mg.council_review(draft, model_id="any-model")

    assert out["verdict"] == "OK"
    assert reviewer_budgets
    assert all(b == HEAVY for b in reviewer_budgets)


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


def test_generate_mechanic_candidates_stamps_ok_verdict(_project, monkeypatch) -> None:
    """A council-passing candidate is stamped ``_review_verdict='OK'`` with empty
    notes (the cheap path — all reviewers OK, no synth)."""
    monkeypatch.setattr(mg, "generate_with_tool", _stub_n_per_call(1))
    result = mg.generate_mechanic_candidates(count=2)
    assert len(result["mechanics"]) == 2
    assert all(m["_review_verdict"] == "OK" for m in result["mechanics"])
    assert all(m["_review_notes"] == "" for m in result["mechanics"])


def test_generate_mechanic_candidates_regen_fallback_accepts_best_effort(
    _project, monkeypatch
) -> None:
    """When the council never passes a slot (reviewers REVISE, synth no-ops), the
    slot is regenerated from scratch and ultimately accepted best-effort, stamped
    REVISE — the pool still fills exactly ``count`` so the picker has a slate."""
    counter = {"next": 0}

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "submit_mechanic_review":
            return {
                "result": {
                    "verdict": "REVISE",
                    "issues": [
                        {
                            "category": "wording",
                            "severity": "major",
                            "description": "invalid templating",
                        }
                    ],
                },
                "input_tokens": 1,
                "output_tokens": 1,
            }
        if tool == "submit_mechanic_synthesis":
            # No revised_mechanic → council keeps the draft, flagged REVISE.
            return {"result": {}, "input_tokens": 1, "output_tokens": 1}
        # Generation: a fresh, distinct mechanic per call (so regens don't dup).
        i = counter["next"]
        counter["next"] += 1
        return {
            "result": {"mechanics": [_valid_mech(i)]},
            "input_tokens": 1,
            "output_tokens": 1,
        }

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    drafts: list[int] = []
    finalized: list[int] = []
    result = mg.generate_mechanic_candidates(
        count=2,
        on_draft=lambda pos, mech: drafts.append(pos),
        on_finalized=lambda pos, mech, notes: finalized.append(pos),
    )
    assert len(result["mechanics"]) == 2
    assert all(m["_review_verdict"] == "REVISE" for m in result["mechanics"])
    # Each slot regenerates once (MAX_MECHANIC_REGEN_ATTEMPTS=1) — on_draft fires
    # for both the initial draft and the regen, at the same position; on_finalized
    # fires exactly once per slot when the best-effort mechanic is accepted.
    assert drafts == [1, 1, 2, 2]
    assert finalized == [1, 2]


def test_generate_mechanic_candidates_emits_regenerating_signal(_project, monkeypatch) -> None:
    """When a slot regenerates from scratch, a council 'regenerating' event fires
    for that position before the re-draft — so the UI can show "Regenerating…"
    instead of a stale "Reviewing…" badge during the (council-less) re-draft."""
    counter = {"next": 0}

    def stub(*args, **kwargs):
        tool = _tool_name(args, kwargs)
        if tool == "submit_mechanic_review":
            return _reviewer("REVISE")  # never passes -> forces a regen
        if tool == "submit_mechanic_synthesis":
            return _synth(None)  # keeps the draft, REVISE
        i = counter["next"]
        counter["next"] += 1
        return {"result": {"mechanics": [_valid_mech(i)]}, "input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(mg, "generate_with_tool", stub)
    events: list[tuple[int, str | None]] = []
    mg.generate_mechanic_candidates(
        count=1, on_council=lambda pos, ev: events.append((pos, ev.get("kind")))
    )
    # Exactly one regen attempt (MAX_MECHANIC_REGEN_ATTEMPTS=1) -> one signal, on slot 1.
    assert events.count((1, "regenerating")) == 1


def test_generate_mechanic_candidates_threads_council_events_with_position(
    _project, monkeypatch
) -> None:
    """``on_council(position, event)`` fires for each council step, tagged with the
    1-based slot ``position``. Guards the position binding (B023): each slot's events
    must carry that slot's position, not the loop's final value. All reviewers OK ⇒
    each slot is one round of round_start + 3 reviewers, no synth."""
    monkeypatch.setattr(mg, "generate_with_tool", _stub_n_per_call(1))
    councils: list[tuple[int, str]] = []

    result = mg.generate_mechanic_candidates(
        count=2,
        on_council=lambda pos, ev: councils.append((pos, ev["kind"])),
    )
    assert len(result["mechanics"]) == 2
    # Slot 1's events all carry position 1, slot 2's all carry position 2 — proof the
    # lambda bound ``position`` per-slot rather than late-binding to the final value.
    assert councils == [
        (1, "round_start"),
        (1, "reviewer"),
        (1, "reviewer"),
        (1, "reviewer"),
        (2, "round_start"),
        (2, "reviewer"),
        (2, "reviewer"),
        (2, "reviewer"),
    ]


# ---------------------------------------------------------------------------
# AI picker: prompt assembly + pick resolution
# ---------------------------------------------------------------------------


def test_salvage_tool_json_recovers_from_noisy_text() -> None:
    """`_salvage_tool_json` recovers valid JSON from raw text (a fenced block, or
    with control-token / jammed-tool-name noise) so the picker keeps the model's
    real selections; it returns None on genuinely malformed pseudo-JSON, leaving
    the first-N fallback intact rather than guessing."""
    fenced = 'pre ```json\n{"selections": [{"candidate_number": 1}]}\n``` post'
    assert mg._salvage_tool_json(fenced) == {"selections": [{"candidate_number": 1}]}
    noisy = 'select_best_mechanics<|chan|>{"a": 1, "b": [2, 3]}'
    assert mg._salvage_tool_json(noisy) == {"a": 1, "b": [2, 3]}
    # Unquoted keys (the real failure observed) -> unrecoverable -> None.
    assert mg._salvage_tool_json('select_best_mechanics{overall_rationale:<|"|>nope}') is None
    assert mg._salvage_tool_json(None) is None
    assert mg._salvage_tool_json("no json here at all") is None


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
