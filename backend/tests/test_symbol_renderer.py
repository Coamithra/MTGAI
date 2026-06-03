"""Tests for SVG path tracing in symbol_renderer.

``_draw_svg_path_data`` imports ``svg.path`` lazily inside the function, so the
tests inject a lightweight fake ``svg.path`` module and a recording Cairo
context. This lets us assert the emitted Cairo operations without pycairo or
svg.path installed.
"""

import sys
import types

import pytest

# symbol_renderer (via mtgai.rendering.__init__ -> fonts) imports Pillow at
# module load; skip the whole module where Pillow is unavailable.
pytest.importorskip("PIL")

from mtgai.rendering import symbol_renderer


class _RecordingCtx:
    """Records Cairo path ops as ``(op, *args)`` tuples."""

    def __init__(self) -> None:
        self.ops: list[tuple] = []

    def move_to(self, x, y):
        self.ops.append(("move_to", x, y))

    def line_to(self, x, y):
        self.ops.append(("line_to", x, y))

    def curve_to(self, *args):
        self.ops.append(("curve_to", *args))

    def close_path(self):
        self.ops.append(("close_path",))


class _Pt:
    def __init__(self, real, imag):
        self.real = real
        self.imag = imag


class _FakeArc:
    """An Arc segment with a fixed start and a linear point sampler."""

    def __init__(self, start, end):
        self.start = start
        self.end = end

    def point(self, t):
        return _Pt(self.start.real + t, self.start.imag + t)


class _FakeMove:
    def __init__(self, end):
        self.end = end


@pytest.fixture
def fake_svg_path(monkeypatch):
    """Install a fake ``svg.path`` module yielding caller-supplied segments."""
    segments: list = []

    fake = types.ModuleType("svg.path")
    fake.Arc = _FakeArc
    fake.Move = _FakeMove
    # Distinct sentinel classes so isinstance checks never accidentally match.
    fake.Close = type("Close", (), {})
    fake.CubicBezier = type("CubicBezier", (), {})
    fake.Line = type("Line", (), {})
    fake.QuadraticBezier = type("QuadraticBezier", (), {})
    fake.parse_path = lambda d: list(segments)

    parent = types.ModuleType("svg")
    parent.path = fake
    monkeypatch.setitem(sys.modules, "svg", parent)
    monkeypatch.setitem(sys.modules, "svg.path", fake)
    return segments


def test_arc_emits_move_to_before_sampling(fake_svg_path):
    """An Arc opening a subpath must start with move_to(seg.start), not just
    line_to from the previous position (regression: distorted geometry)."""
    fake_svg_path.append(_FakeArc(_Pt(5.0, 7.0), _Pt(25.0, 27.0)))

    ctx = _RecordingCtx()
    symbol_renderer._draw_svg_path_data(ctx, "ignored")

    assert ctx.ops[0] == ("move_to", 5.0, 7.0)
    # Followed by the 20 sampled line_to points.
    assert all(op[0] == "line_to" for op in ctx.ops[1:])
    assert len(ctx.ops) == 1 + 20


def test_arc_following_other_segment_still_moves_to_its_start(fake_svg_path):
    """Even mid-path, the Arc re-anchors at its own start so it can't inherit a
    stale pen position from a preceding Move/Close."""
    fake_svg_path.extend(
        [
            _FakeMove(_Pt(0.0, 0.0)),
            _FakeArc(_Pt(10.0, 10.0), _Pt(30.0, 30.0)),
        ]
    )

    ctx = _RecordingCtx()
    symbol_renderer._draw_svg_path_data(ctx, "ignored")

    assert ctx.ops[0] == ("move_to", 0.0, 0.0)  # the Move
    assert ctx.ops[1] == ("move_to", 10.0, 10.0)  # the Arc re-anchors
    assert ctx.ops[2][0] == "line_to"
