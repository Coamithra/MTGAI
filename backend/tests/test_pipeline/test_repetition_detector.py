"""Tests for the suffix-tandem-repeat detector used by theme extraction.

The detector scans the tail of a streaming buffer for periodic repetition.
These tests cover the user-reported failure modes (hyphen-glued token loops,
verbatim phrase loops), threshold behavior, and the false-positive guard
that suppresses ASCII-art / markdown-separator hits.
"""

from mtgai.pipeline.theme_extractor import _detect_tandem_repeat


def test_user_failure_dash_loop():
    """The original bug: 'the-the-the-...' with no whitespace separators."""
    text = "control the " + "the-" * 30
    hit = _detect_tandem_repeat(text)
    assert hit is not None
    assert "len=4" in hit


def test_user_failure_phrase_loop():
    """Verbatim phrase loop with mid-range period."""
    phrase = "absolute authority and "
    text = "context " + phrase * 5
    hit = _detect_tandem_repeat(text)
    assert hit is not None
    assert f"len={len(phrase)}" in hit


def test_single_char_loop():
    """Single alnum character repeated 20+ times triggers p=1."""
    text = "a" * 25
    hit = _detect_tandem_repeat(text)
    assert hit is not None
    assert "len=1" in hit


def test_canonical_period_preferred():
    """'abc' * 5 reports p=3 not p=6 or p=9."""
    text = "abc" * 8
    hit = _detect_tandem_repeat(text)
    assert hit is not None
    assert "len=3" in hit


def test_below_threshold_no_hit():
    """Period 4, 3 reps, total 12 chars - under both reps and total thresholds."""
    text = "prefix the-the-the-"
    assert _detect_tandem_repeat(text) is None


def test_long_phrase_two_reps_hit():
    """80-char sentence repeated twice fires the long-period band (p>=61, k>=2)."""
    sentence = "The wandering scholar reached the temple gates at dawn, alone. 0123456789abcdef"
    assert len(sentence) >= 61
    text = "intro " + sentence * 2
    hit = _detect_tandem_repeat(text)
    assert hit is not None


def test_parallel_structure_no_false_positive():
    """Legitimate parallel-structure prose has distinct content between matches."""
    text = "Red mana, blue mana, green mana, white mana, black mana, colorless mana."
    assert _detect_tandem_repeat(text) is None


def test_ascii_separators_no_false_positive():
    """Pure non-alnum periodic patterns are suppressed by the alnum guard."""
    cases = [
        "-" * 80,
        "=" * 50,
        "*" * 30,
        "|---|" * 12,
        "_" * 60,
        " " * 40,
        "***",
        "~~~~~~~~~~~~~~~~",
        ". . . . . . . . . . . . . . . . . . . . ",
    ]
    for s in cases:
        assert _detect_tandem_repeat(s) is None, f"false positive on: {s!r}"


def test_streaming_simulation():
    """Feed the bug-report string char-by-char; detector fires soon after the loop starts."""
    prefix = "control the "
    loop_unit = "the-"
    full = prefix + loop_unit * 40
    fired_at = None
    for i in range(1, len(full) + 1):
        if _detect_tandem_repeat(full[:i]) is not None:
            fired_at = i
            break
    assert fired_at is not None, "detector never fired on the bug-report string"
    chars_after_loop_start = fired_at - len(prefix)
    assert chars_after_loop_start <= 70, (
        f"detector fired {chars_after_loop_start} chars into the loop; expected <=70"
    )


def test_empty_and_short():
    """Empty / very short inputs return None instead of erroring."""
    assert _detect_tandem_repeat("") is None
    assert _detect_tandem_repeat("a") is None
    assert _detect_tandem_repeat("hello") is None
    assert _detect_tandem_repeat("a" * 10) is None  # below 20-rep threshold


def test_normal_prose_no_false_positive():
    """A multi-paragraph chunk of legitimate prose should not trigger."""
    prose = (
        "The seven sun-blasted city-states of Athas sit in uneasy balance, "
        "each ruled by an immortal sorcerer-king who has bent the bones of "
        "the world to a private ambition. In Tyr the slaves rose, killing "
        "Kalak as he reached for dragonhood; in Urik the half-mad Hamanu "
        "still grinds his templars against every neighbor; in Raam the "
        "Great Vizier Abalach-Re plays at piety while her secret war-bands "
        "prowl the shifting Sandwastes. Beyond the cities the wastes are "
        "ruled by their own predators - silt drakes, thri-kreen war-clutches, "
        "the tireless caravans of the merchant houses. Magic is the slow "
        "murder of the world: each spell drinks the life from grass and "
        "scrub, leaving sterile ash where rain once fell. Preservers steal "
        "only what the land can spare; defilers take everything and call it "
        "a fair price. The Veiled Alliance hides the preservers from the "
        "templars, the templars hide the truth of the sorcerer-kings from "
        "the people, and the sorcerer-kings hide the price of their power "
        "from themselves. Heroes here are smaller than legends - a "
        "gladiator who survives the arena, a mul who refuses to be sold, "
        "a half-elf scout who finds water on a route everyone said was dry. "
        "Each city-state has its own currency of cruelty, its own ration "
        "of hope, its own short list of names that everyone knows but "
        "nobody speaks aloud after dark."
    )
    assert len(prose) >= 1000
    assert _detect_tandem_repeat(prose) is None


def test_punctuation_period_with_alnum_still_caught():
    """A period containing both punctuation AND alnum chars should still fire."""
    text = "preserver of life. " * 6
    hit = _detect_tandem_repeat(text)
    assert hit is not None
