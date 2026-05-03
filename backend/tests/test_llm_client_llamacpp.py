"""Tests for llm_client (Anthropic + llamacpp paths, llmfacade-backed)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from mtgai.generation.llm_client import (
    _llamacpp_extract_json,
    _llamacpp_new_model,
    calc_cost,
    generate_with_tool,
)

# ── Sample tool schema (Anthropic format) ────────────────────────────

SAMPLE_TOOL = {
    "name": "generate_card",
    "description": "Generate a Magic card",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "mana_cost": {"type": "string"},
            "type_line": {"type": "string"},
            "oracle_text": {"type": "string"},
        },
        "required": ["name", "mana_cost", "type_line"],
    },
}

SAMPLE_CARD = {
    "name": "Test Creature",
    "mana_cost": "{1}{W}",
    "type_line": "Creature - Human",
    "oracle_text": "Vigilance",
}


# ── JSON extraction from text ────────────────────────────────────────


class TestJsonExtraction:
    def test_fenced_json_block(self):
        text = 'Here is the card:\n```json\n{"name": "Foo", "mana_cost": "{W}"}\n```'
        result = _llamacpp_extract_json(text, "generate_card")
        assert result == {"name": "Foo", "mana_cost": "{W}"}

    def test_fenced_block_no_json_tag(self):
        text = 'Result:\n```\n{"name": "Foo"}\n```'
        result = _llamacpp_extract_json(text, "generate_card")
        assert result == {"name": "Foo"}

    def test_qwen_style_tool_call(self):
        text = '{"name": "generate_card", "arguments": {"name": "Bar", "mana_cost": "{R}"}}'
        result = _llamacpp_extract_json(text, "generate_card")
        assert result == {"name": "Bar", "mana_cost": "{R}"}

    def test_bare_json_object(self):
        text = 'I will generate the card.\n{"name": "Baz", "type_line": "Instant"}\nDone.'
        result = _llamacpp_extract_json(text, "generate_card")
        assert result == {"name": "Baz", "type_line": "Instant"}

    def test_nested_json(self):
        text = '{"outer": {"inner": "value"}, "key": "val"}'
        result = _llamacpp_extract_json(text, "tool")
        assert result == {"outer": {"inner": "value"}, "key": "val"}

    def test_no_json_found(self):
        text = "I cannot generate a card right now."
        result = _llamacpp_extract_json(text, "generate_card")
        assert result is None

    def test_malformed_json(self):
        text = '{"name": "broken'
        result = _llamacpp_extract_json(text, "generate_card")
        assert result is None

    def test_fenced_block_preferred_over_bare(self):
        """Fenced block should be tried first."""
        text = 'Bad: {"wrong": true}\n```json\n{"correct": true}\n```'
        result = _llamacpp_extract_json(text, "tool")
        assert result == {"correct": True}


# ── Cost calculation for local models ────────────────────────────────


class TestLocalCost:
    def test_local_model_is_free(self):
        # qwen2.5-14b is registered with input_price=0.0; the registry path
        # resolves it correctly and the cost is zero.
        cost = calc_cost("qwen2.5-14b", input_tokens=10000, output_tokens=5000)
        assert cost == 0.0

    def test_unregistered_model_is_free(self):
        cost = calc_cost("not-in-registry", input_tokens=50000, output_tokens=20000)
        assert cost == 0.0


# ── _llamacpp_new_model registry dispatch ────────────────────────────


class TestLlamaCppNewModel:
    def test_unregistered_model_raises(self):
        provider = MagicMock()
        with pytest.raises(ValueError, match="not in the registry"):
            _llamacpp_new_model(provider, "definitely-not-a-real-model-xyz")
        provider.new_model.assert_not_called()

    def test_missing_gguf_path_raises(self):
        """A registry entry without gguf_path must raise rather than launch
        llama-server with a missing path."""
        provider = MagicMock()
        fake_info = MagicMock()
        fake_info.gguf_path = None
        with (
            patch(
                "mtgai.settings.model_registry.ModelRegistry.get_llm_by_model_id",
                return_value=fake_info,
            ),
            pytest.raises(ValueError, match="missing gguf_path"),
        ):
            _llamacpp_new_model(provider, "fake-model")
        provider.new_model.assert_not_called()

    def test_threads_launch_kwargs_from_registry(self):
        """Registry knobs (gguf, context_size, cache_type_k/_v, n_gpu_layers)
        must be forwarded to provider.new_model(...)."""
        provider = MagicMock()
        fake_info = MagicMock()
        fake_info.model_id = "vlad-gemma4-26b-dynamic"
        fake_info.gguf_path = "C:/Models/vlad-gemma4-26b-dynamic.gguf"
        fake_info.context_window = 128000
        fake_info.cache_type_k = "q8_0"
        fake_info.cache_type_v = "q8_0"
        fake_info.n_gpu_layers = -1
        with patch(
            "mtgai.settings.model_registry.ModelRegistry.get_llm_by_model_id",
            return_value=fake_info,
        ):
            _llamacpp_new_model(provider, "vlad-gemma4-26b-dynamic")
        provider.new_model.assert_called_once_with(
            name="vlad-gemma4-26b-dynamic",
            gguf="C:/Models/vlad-gemma4-26b-dynamic.gguf",
            context_size=128000,
            cache_type_k="q8_0",
            cache_type_v="q8_0",
            n_gpu_layers=-1,
        )

    def test_omits_optional_kwargs_when_unset(self):
        """cache_type_k/_v and n_gpu_layers are llamacpp-server flags whose
        absence should be passed as 'don't set this flag', not as None."""
        provider = MagicMock()
        fake_info = MagicMock()
        fake_info.model_id = "qwen2.5-14b"
        fake_info.gguf_path = "C:/Models/qwen2.5-14b.gguf"
        fake_info.context_window = 32768
        fake_info.cache_type_k = None
        fake_info.cache_type_v = None
        fake_info.n_gpu_layers = None
        with patch(
            "mtgai.settings.model_registry.ModelRegistry.get_llm_by_model_id",
            return_value=fake_info,
        ):
            _llamacpp_new_model(provider, "qwen2.5-14b")
        kwargs = provider.new_model.call_args.kwargs
        assert kwargs == {
            "name": "qwen2.5-14b",
            "gguf": "C:/Models/qwen2.5-14b.gguf",
            "context_size": 32768,
        }


# ── llmfacade Response/Usage/ToolCall stubs ──────────────────────────


def _make_usage(prompt_tokens=100, completion_tokens=50, cache_creation=0, cache_read=0):
    """Build a mock llmfacade.Usage."""
    u = MagicMock()
    u.prompt_tokens = prompt_tokens
    u.completion_tokens = completion_tokens
    u.cache_creation_tokens = cache_creation
    u.cache_read_tokens = cache_read
    u.total_tokens = prompt_tokens + completion_tokens
    return u


def _make_tool_call(name: str, input_dict: dict):
    """Build a mock llmfacade.ToolCall."""
    tc = MagicMock()
    tc.id = "call-test"
    tc.name = name
    tc.input = input_dict
    return tc


def _make_response(*, tool_calls=None, text="", finish_reason="end_turn", usage=None):
    """Build a mock llmfacade.Response."""
    r = MagicMock()
    r.tool_calls = tool_calls or []
    r.text = text
    r.finish_reason = finish_reason
    r.usage = usage or _make_usage()
    return r


def _build_facade_provider_mock(send_returns):
    """Build a mock provider where new_model().new_conversation().send() returns
    each item from `send_returns` in order. send_returns can be:
      - a single Response (used for every send call), or
      - a list (consumed one per send).
    """
    convo = MagicMock()
    if isinstance(send_returns, list):
        convo.send.side_effect = send_returns
    else:
        convo.send.return_value = send_returns
    model = MagicMock()
    model.new_conversation.return_value = convo
    provider = MagicMock()
    provider.new_model.return_value = model
    return provider, convo


# ── Anthropic path ───────────────────────────────────────────────────


class TestAnthropicGenerateWithTool:
    """Cover the _generate_anthropic path with a stubbed llmfacade provider."""

    def test_basic_call_returns_expected_dict_shape(self, monkeypatch):
        # Disable MTGAI_MAX_MODEL so the test doesn't get downgraded.
        monkeypatch.delenv("MTGAI_MAX_MODEL", raising=False)
        usage = _make_usage(
            prompt_tokens=120, completion_tokens=80, cache_creation=20, cache_read=10
        )
        resp = _make_response(
            tool_calls=[_make_tool_call("generate_card", SAMPLE_CARD)],
            finish_reason="tool_use",
            usage=usage,
        )
        provider, convo = _build_facade_provider_mock(resp)

        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="anthropic"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            result = generate_with_tool(
                system_prompt="You are a card designer.",
                user_prompt="Make a card.",
                tool_schema=SAMPLE_TOOL,
                model="claude-sonnet-4-6",
            )

        assert result["result"] == SAMPLE_CARD
        assert result["input_tokens"] == 120
        assert result["output_tokens"] == 80
        assert result["cache_creation_input_tokens"] == 20
        assert result["cache_read_input_tokens"] == 10
        assert result["stop_reason"] == "tool_use"
        assert result["model"] == "claude-sonnet-4-6"
        # Conversation should have been built once and send called once.
        provider.new_model.assert_called_once_with("claude-sonnet-4-6")
        convo.send.assert_called_once()

    def test_max_tokens_truncation_raises(self):
        resp = _make_response(
            tool_calls=[_make_tool_call("generate_card", SAMPLE_CARD)],
            finish_reason="max_tokens",
        )
        provider, _ = _build_facade_provider_mock(resp)

        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="anthropic"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            with pytest.raises(ValueError, match="max_tokens"):
                generate_with_tool(
                    system_prompt="Sys",
                    user_prompt="User",
                    tool_schema=SAMPLE_TOOL,
                )

    def test_no_tool_call_raises(self):
        resp = _make_response(tool_calls=[], finish_reason="end_turn")
        provider, _ = _build_facade_provider_mock(resp)

        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="anthropic"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            with pytest.raises(ValueError, match="No tool_use block"):
                generate_with_tool(
                    system_prompt="Sys",
                    user_prompt="User",
                    tool_schema=SAMPLE_TOOL,
                )


# ── llamacpp path ────────────────────────────────────────────────────


class TestLlamaCppGenerateWithTool:
    """Cover the _generate_llamacpp path with a stubbed llmfacade provider."""

    def test_native_tool_calling(self):
        """Model uses native function calling properly."""
        resp = _make_response(
            tool_calls=[_make_tool_call("generate_card", SAMPLE_CARD)],
            usage=_make_usage(prompt_tokens=100, completion_tokens=50),
        )
        provider, _convo = _build_facade_provider_mock(resp)

        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="llamacpp"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            result = generate_with_tool(
                system_prompt="You are a card designer.",
                user_prompt="Make a card.",
                tool_schema=SAMPLE_TOOL,
                model="qwen2.5-14b",
            )

        assert result["result"] == SAMPLE_CARD
        assert result["stop_reason"] == "tool_use"
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50
        assert result["cache_creation_input_tokens"] == 0
        assert result["cache_read_input_tokens"] == 0

    def test_text_extraction_fallback(self):
        """Model outputs JSON as text instead of using function calling."""
        text = f"Here is the card:\n```json\n{json.dumps(SAMPLE_CARD)}\n```"
        resp = _make_response(text=text, tool_calls=[])
        provider, _ = _build_facade_provider_mock(resp)

        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="llamacpp"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            result = generate_with_tool(
                system_prompt="Sys",
                user_prompt="User",
                tool_schema=SAMPLE_TOOL,
                model="qwen2.5-14b",
            )

        assert result["result"] == SAMPLE_CARD

    def test_retry_on_garbage(self):
        """Model produces garbage, retries, then succeeds."""
        bad = _make_response(text="I don't know how to do that.", tool_calls=[])
        good = _make_response(text=json.dumps(SAMPLE_CARD), tool_calls=[])
        provider, convo = _build_facade_provider_mock([bad, good])

        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="llamacpp"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            result = generate_with_tool(
                system_prompt="Sys",
                user_prompt="User",
                tool_schema=SAMPLE_TOOL,
                model="qwen2.5-14b",
            )

        assert result["result"] == SAMPLE_CARD
        assert convo.send.call_count == 2

    def test_all_retries_exhausted(self, monkeypatch):
        """Raises ValueError after all retries fail."""
        # Pin MAX_RETRIES so this test isn't dependent on env / .env.
        monkeypatch.setattr("mtgai.generation.llm_client.MAX_RETRIES", 3)
        bad = _make_response(text="no json here", tool_calls=[])
        provider, _ = _build_facade_provider_mock([bad, bad, bad])

        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="llamacpp"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            with pytest.raises(ValueError, match="failed to produce valid tool output"):
                generate_with_tool(
                    system_prompt="Sys",
                    user_prompt="User",
                    tool_schema=SAMPLE_TOOL,
                    model="qwen2.5-14b",
                )

    def test_wrong_named_tool_call_is_not_accepted(self, monkeypatch):
        """A tool_call whose name doesn't match the requested tool must NOT
        be returned as success - local models occasionally emit wrong-named
        calls and treating those as success returns garbage-shaped data."""
        monkeypatch.setattr("mtgai.generation.llm_client.MAX_RETRIES", 2)
        wrong = _make_response(
            tool_calls=[_make_tool_call("some_other_tool", {"junk": True})],
            text="",
        )
        # 2 attempts both producing a wrong-named tool call -> must raise,
        # not return the wrong-shape data.
        provider, _ = _build_facade_provider_mock([wrong, wrong])

        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="llamacpp"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            with pytest.raises(ValueError, match="failed to produce valid tool output"):
                generate_with_tool(
                    system_prompt="Sys",
                    user_prompt="User",
                    tool_schema=SAMPLE_TOOL,
                    model="qwen2.5-14b",
                )
