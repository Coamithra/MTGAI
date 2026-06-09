"""Tests for the interaction-scan context projection (Project Settings warning).

``project_largest_batch_tokens`` estimates the interaction step's largest
cumulative-context batch prompt for a set of ~set_size cards, before any real
card exists, so the picker can warn when the conformance model's window is too
small. It must be 0 for an empty set and grow with set size.
"""

from __future__ import annotations

from itertools import pairwise

from mtgai.analysis.interactions import (
    BATCH_SIZE,
    INTERACTION_SYSTEM_PROMPT,
    project_largest_batch_tokens,
)
from mtgai.generation.token_utils import count_tokens


def test_zero_set_size_is_zero():
    assert project_largest_batch_tokens(0) == 0
    assert project_largest_batch_tokens(-5) == 0


def test_grows_monotonically_with_set_size():
    vals = [project_largest_batch_tokens(n) for n in range(0, 600, 20)]
    assert all(a <= b for a, b in pairwise(vals))
    # A large set is materially bigger than a small one.
    assert project_largest_batch_tokens(600) > project_largest_batch_tokens(40) * 3


def test_at_least_system_prompt_for_a_nonempty_set():
    # The largest batch always includes the system prompt + at least one batch of
    # new cards, so the projection can't undercut the system prompt alone.
    one_batch = project_largest_batch_tokens(BATCH_SIZE)
    assert one_batch > count_tokens(INTERACTION_SYSTEM_PROMPT)


def test_mechanic_count_adds_tokens():
    without = project_largest_batch_tokens(100, mechanic_count=0)
    with_mechs = project_largest_batch_tokens(100, mechanic_count=5)
    assert with_mechs > without
