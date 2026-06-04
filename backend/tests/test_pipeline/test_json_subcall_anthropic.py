"""Tests for the Anthropic json_mode path of theme-extraction subcalls.

Anthropic has no ``response_format`` toggle and llmfacade's Anthropic provider
treats ``output_format`` as a no-op, so Haiku used to wrap its constraints /
card-suggestion JSON in a ```json fence and our naive ``json.loads`` died at
pos 0. Two defenses are covered here:

  1. ``_strip_json_fence`` — a parse-time backstop that unwraps a fenced body.
  2. Assistant **prefill** in ``_stream_anthropic_call`` — when ``json_mode`` is
     set, a seed ``{`` assistant turn forces a bare object and structurally
     prevents a fence; the omitted ``{`` is restored onto the streamed text.
"""

from __future__ import annotations

from types import SimpleNamespace

import mtgai.generation.llm_client as llm_client
from mtgai.pipeline import theme_extractor as te
from mtgai.pipeline.theme_extractor import _strip_json_fence

# ── _strip_json_fence ────────────────────────────────────────────────


def test_strip_fence_unwraps_json_block():
    fenced = '```json\n{\n  "constraints": ["a", "b"]\n}\n```'
    assert _strip_json_fence(fenced) == '{\n  "constraints": ["a", "b"]\n}'


def test_strip_fence_unwraps_bare_fence():
    fenced = '```\n{"x": 1}\n```'
    assert _strip_json_fence(fenced) == '{"x": 1}'


def test_strip_fence_passes_through_bare_json():
    bare = '{"constraints": ["a"]}'
    assert _strip_json_fence(bare) == bare


def test_strip_fence_trims_surrounding_whitespace():
    assert _strip_json_fence('\n\n  {"x": 1}  \n') == '{"x": 1}'


# ── prefill restoration in _stream_anthropic_call ────────────────────


class _FakeStreamEvent(SimpleNamespace):
    """Mimics the llmfacade StreamEvent fields the call loop reads."""


class _FakeConversation:
    def __init__(self, deltas: list[str]):
        self._deltas = deltas
        self.history: list[tuple[str, str]] = []
        self.stream_prompt: object = "UNSET"

    def add_user_message(self, content):
        self.history.append(("user", content))

    def add_assistant_message(self, content):
        self.history.append(("assistant", content))

    def stream(self, prompt=None):
        self.stream_prompt = prompt
        for d in self._deltas:
            yield _FakeStreamEvent(text_delta=d, usage=None)


class _FakeModel:
    def __init__(self, convo: _FakeConversation):
        self._convo = convo

    def new_conversation(self, **kwargs):
        return self._convo


class _FakeProvider:
    def __init__(self, convo: _FakeConversation):
        self._convo = convo

    def new_model(self, model_id):
        return _FakeModel(self._convo)


def _run_call(monkeypatch, deltas, *, json_mode):
    convo = _FakeConversation(deltas)
    monkeypatch.setattr(llm_client, "_get_provider", lambda name: _FakeProvider(convo))
    model_info = SimpleNamespace(provider="anthropic", model_id="claude-haiku-4-5-test")
    events = list(
        te._stream_anthropic_call(
            "the user prompt",
            "the system prompt",
            model_info,
            stream_to_ui=False,
            json_mode=json_mode,
        )
    )
    complete = [e for e in events if e["type"] == "complete"]
    assert len(complete) == 1
    return convo, complete[0]["theme_text"]


def test_json_mode_prefills_brace_and_restores_it(monkeypatch):
    # Anthropic omits the prefilled `{` from the reply; the continuation starts
    # at the newline after the brace.
    convo, text = _run_call(monkeypatch, ['\n  "constraints": ["a"]\n}'], json_mode=True)
    assert text == '{\n  "constraints": ["a"]\n}'
    # The seed brace was prefilled as a trailing assistant turn, and stream()
    # was driven off history (prompt=None) rather than a fresh user prompt.
    assert ("assistant", "{") in convo.history
    assert ("user", "the user prompt") in convo.history
    assert convo.stream_prompt is None


def test_json_mode_does_not_double_brace_if_model_echoes_it(monkeypatch):
    # Defensive: if a model echoes the brace anyway, don't prepend a second one.
    _convo, text = _run_call(monkeypatch, ['{"constraints": ["a"]}'], json_mode=True)
    assert text == '{"constraints": ["a"]}'


def test_non_json_mode_streams_prompt_directly(monkeypatch):
    convo, text = _run_call(monkeypatch, ["plain prose reply"], json_mode=False)
    assert text == "plain prose reply"
    # No prefill; the user prompt drives stream() the legacy way.
    assert convo.stream_prompt == "the user prompt"
    assert all(role != "assistant" for role, _ in convo.history)
