"""Tests for llm_client (Anthropic + llamacpp paths, llmfacade-backed)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from mtgai.generation import llm_client
from mtgai.generation.llm_client import (
    _llamacpp_extract_json,
    _llamacpp_new_model,
    calc_cost,
    generate_text,
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
        # vlad-gemma4-26b-dynamic is registered with input_price=0.0; the registry path
        # resolves it correctly and the cost is zero.
        cost = calc_cost("vlad-gemma4-26b-dynamic", input_tokens=10000, output_tokens=5000)
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
        """Registry knobs (gguf, context_size, cache_type_k/_v, n_gpu_layers,
        fit) must be forwarded to provider.new_model(...)."""
        provider = MagicMock()
        fake_info = MagicMock()
        fake_info.model_id = "vlad-gemma4-26b-dynamic"
        fake_info.gguf_path = "C:/Models/vlad-gemma4-26b-dynamic.gguf"
        fake_info.context_window = 128000
        fake_info.cache_type_k = "q8_0"
        fake_info.cache_type_v = "q8_0"
        fake_info.n_gpu_layers = -1
        fake_info.fit = True
        # No thinking on this entry — bare MagicMock attrs would otherwise be
        # truthy and leak thinking=/thinking_style= into the call.
        fake_info.thinking = None
        fake_info.thinking_style = None
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
            fit=True,
        )

    def test_omits_optional_kwargs_when_unset(self):
        """cache_type_k/_v and n_gpu_layers are llamacpp-server flags whose
        absence should be passed as 'don't set this flag', not as None. fit is a
        real bool (default True) so it's always forwarded."""
        provider = MagicMock()
        fake_info = MagicMock()
        fake_info.model_id = "vlad-gemma4-26b-dynamic"
        fake_info.gguf_path = "C:/Models/vlad-gemma4-26b-dynamic.gguf"
        fake_info.context_window = 32768
        fake_info.cache_type_k = None
        fake_info.cache_type_v = None
        fake_info.n_gpu_layers = None
        fake_info.fit = True
        fake_info.thinking = None
        fake_info.thinking_style = None
        with patch(
            "mtgai.settings.model_registry.ModelRegistry.get_llm_by_model_id",
            return_value=fake_info,
        ):
            _llamacpp_new_model(provider, "vlad-gemma4-26b-dynamic")
        kwargs = provider.new_model.call_args.kwargs
        assert kwargs == {
            "name": "vlad-gemma4-26b-dynamic",
            "gguf": "C:/Models/vlad-gemma4-26b-dynamic.gguf",
            "context_size": 32768,
            "fit": True,
        }

    def test_threads_fit_false_from_registry(self):
        """fit=false in the registry must reach provider.new_model as fit=False
        so llama-server launches --fit off (the registry, not llmfacade's
        provider default, is the source of truth for the fit flag)."""
        provider = MagicMock()
        fake_info = MagicMock()
        fake_info.model_id = "m"
        fake_info.gguf_path = "C:/Models/m.gguf"
        fake_info.context_window = 8192
        fake_info.cache_type_k = None
        fake_info.cache_type_v = None
        fake_info.n_gpu_layers = None
        fake_info.fit = False
        fake_info.thinking = None
        fake_info.thinking_style = None
        with patch(
            "mtgai.settings.model_registry.ModelRegistry.get_llm_by_model_id",
            return_value=fake_info,
        ):
            _llamacpp_new_model(provider, "m")
        assert provider.new_model.call_args.kwargs["fit"] is False

    def test_threads_thinking_knobs_from_registry(self):
        """thinking / thinking_style from the registry must reach
        provider.new_model so llama-server gets the enable_thinking template
        kwarg (the vlad-updated local default sets thinking="adaptive").
        thinking_style left unset is omitted so llmfacade auto-detects it."""
        provider = MagicMock()
        fake_info = MagicMock()
        fake_info.model_id = "gemma4-26b-vlad-updated"
        fake_info.gguf_path = "C:/Models/vlad-updated-gemma4-26b.gguf"
        fake_info.context_window = 128000
        fake_info.cache_type_k = "q8_0"
        fake_info.cache_type_v = "q8_0"
        fake_info.n_gpu_layers = -1
        fake_info.fit = True
        fake_info.thinking = "adaptive"
        fake_info.thinking_style = None
        with patch(
            "mtgai.settings.model_registry.ModelRegistry.get_llm_by_model_id",
            return_value=fake_info,
        ):
            _llamacpp_new_model(provider, "gemma4-26b-vlad-updated")
        kwargs = provider.new_model.call_args.kwargs
        assert kwargs["thinking"] == "adaptive"
        assert "thinking_style" not in kwargs
        assert kwargs["n_gpu_layers"] == -1

    def test_threads_thinking_style_override_from_registry(self):
        """An explicit thinking_style override must reach provider.new_model
        (covers the set-branch; auto-detection is bypassed when it's given)."""
        provider = MagicMock()
        fake_info = MagicMock()
        fake_info.model_id = "m"
        fake_info.gguf_path = "C:/Models/m.gguf"
        fake_info.context_window = 8192
        fake_info.cache_type_k = None
        fake_info.cache_type_v = None
        fake_info.n_gpu_layers = None
        fake_info.fit = True
        fake_info.thinking = "adaptive"
        fake_info.thinking_style = "template_kwarg"
        with patch(
            "mtgai.settings.model_registry.ModelRegistry.get_llm_by_model_id",
            return_value=fake_info,
        ):
            _llamacpp_new_model(provider, "m")
        kwargs = provider.new_model.call_args.kwargs
        assert kwargs["thinking_style"] == "template_kwarg"


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
            pytest.raises(ValueError, match="max_tokens"),
        ):
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
            pytest.raises(ValueError, match="No tool_use block"),
        ):
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
                model="vlad-gemma4-26b-dynamic",
            )

        assert result["result"] == SAMPLE_CARD
        assert result["stop_reason"] == "tool_use"
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50
        assert result["cache_creation_input_tokens"] == 0
        assert result["cache_read_input_tokens"] == 0

    def test_repeat_penalty_forwarded_to_conversation(self):
        """A per-call repeat_penalty must reach new_conversation(); omitting it
        leaves the provider default untouched (no kwarg passed)."""
        resp = _make_response(
            tool_calls=[_make_tool_call("generate_card", SAMPLE_CARD)],
            usage=_make_usage(),
        )
        provider, _ = _build_facade_provider_mock(resp)
        model = provider.new_model.return_value
        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="llamacpp"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            generate_with_tool(
                system_prompt="Sys",
                user_prompt="User",
                tool_schema=SAMPLE_TOOL,
                model="vlad-gemma4-26b-dynamic",
                repeat_penalty=1.0,
            )
        assert model.new_conversation.call_args.kwargs.get("repeat_penalty") == 1.0

        # Default path: no repeat_penalty kwarg (provider default stays in force).
        provider2, _ = _build_facade_provider_mock(resp)
        model2 = provider2.new_model.return_value
        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="llamacpp"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider2),
        ):
            generate_with_tool(
                system_prompt="Sys",
                user_prompt="User",
                tool_schema=SAMPLE_TOOL,
                model="vlad-gemma4-26b-dynamic",
            )
        assert "repeat_penalty" not in model2.new_conversation.call_args.kwargs

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
                model="vlad-gemma4-26b-dynamic",
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
                model="vlad-gemma4-26b-dynamic",
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
            pytest.raises(ValueError, match="failed to produce valid tool output"),
        ):
            generate_with_tool(
                system_prompt="Sys",
                user_prompt="User",
                tool_schema=SAMPLE_TOOL,
                model="vlad-gemma4-26b-dynamic",
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
            pytest.raises(ValueError, match="failed to produce valid tool output"),
        ):
            generate_with_tool(
                system_prompt="Sys",
                user_prompt="User",
                tool_schema=SAMPLE_TOOL,
                model="vlad-gemma4-26b-dynamic",
            )


# ── Free-text generation (generate_text) ─────────────────────────────


class TestGenerateText:
    """Cover the no-tool free-text path for both providers."""

    def test_llamacpp_returns_text_and_usage(self):
        resp = _make_response(text="line one\nline two", usage=_make_usage(100, 50))
        provider, _ = _build_facade_provider_mock(resp)
        model = provider.new_model.return_value
        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="llamacpp"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            result = generate_text(
                system_prompt="Sys",
                user_prompt="User",
                model="vlad-gemma4-26b-dynamic",
                repeat_penalty=1.0,
            )
        assert result["text"] == "line one\nline two"
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50
        assert "result" not in result  # free-text path returns text, not a tool result
        # No tools are attached, and the repeat_penalty is forwarded.
        kwargs = model.new_conversation.call_args.kwargs
        assert "tools" not in kwargs
        assert kwargs.get("repeat_penalty") == 1.0

    def test_llamacpp_does_not_raise_on_truncation(self):
        """A truncated free-text reply is still useful — return it, don't raise."""
        resp = _make_response(text="partial output", finish_reason="length")
        provider, _ = _build_facade_provider_mock(resp)
        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="llamacpp"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            result = generate_text(
                system_prompt="Sys", user_prompt="User", model="vlad-gemma4-26b-dynamic"
            )
        assert result["text"] == "partial output"
        assert result["stop_reason"] == "length"

    def test_anthropic_returns_text(self, monkeypatch):
        monkeypatch.delenv("MTGAI_MAX_MODEL", raising=False)
        resp = _make_response(text="hello", finish_reason="end_turn", usage=_make_usage(10, 5))
        provider, convo = _build_facade_provider_mock(resp)
        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="anthropic"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            result = generate_text(
                system_prompt="Sys", user_prompt="User", model="claude-sonnet-4-6"
            )
        assert result["text"] == "hello"
        assert result["input_tokens"] == 10
        convo.send.assert_called_once()


# ── Responsive cancel: interrupt the in-flight local server ──────────


class TestInterruptLocalInference:
    """``interrupt_local_inference`` kills the local server only when a local
    call is actually in flight, and degrades gracefully until llmfacade ships
    ``provider.interrupt()``."""

    @pytest.fixture(autouse=True)
    def _isolate_module_state(self):
        # Snapshot + restore the module-level in-flight counter and provider
        # cache so these tests don't leak into each other or the wider suite.
        saved_inflight = llm_client._local_inflight
        saved_providers = dict(llm_client._PROVIDERS)
        llm_client._local_inflight = 0
        yield
        llm_client._local_inflight = saved_inflight
        with llm_client._PROVIDERS_LOCK:
            llm_client._PROVIDERS.clear()
            llm_client._PROVIDERS.update(saved_providers)

    def _set_provider(self, prov):
        with llm_client._PROVIDERS_LOCK:
            llm_client._PROVIDERS["llamacpp"] = prov

    def test_noop_when_nothing_in_flight(self):
        prov = MagicMock()
        prov.interrupt.return_value = True
        self._set_provider(prov)
        # _local_inflight == 0 → no local call to abort.
        assert llm_client.interrupt_local_inference() is False
        prov.interrupt.assert_not_called()

    def test_noop_when_no_provider_cached(self):
        llm_client._local_inflight = 1
        with llm_client._PROVIDERS_LOCK:
            llm_client._PROVIDERS.pop("llamacpp", None)
        assert llm_client.interrupt_local_inference() is False

    def test_kills_when_in_flight(self):
        prov = MagicMock()
        prov.interrupt.return_value = True
        self._set_provider(prov)
        llm_client._local_inflight = 1
        assert llm_client.interrupt_local_inference() is True
        prov.interrupt.assert_called_once_with()

    def test_missing_interrupt_method_degrades(self):
        # A provider without interrupt() (today's llmfacade): warn + False, no crash.
        class NoInterrupt:
            pass

        self._set_provider(NoInterrupt())
        llm_client._local_inflight = 1
        assert llm_client.interrupt_local_inference() is False

    def test_interrupt_exception_is_swallowed(self):
        prov = MagicMock()
        prov.interrupt.side_effect = RuntimeError("kaboom")
        self._set_provider(prov)
        llm_client._local_inflight = 1
        assert llm_client.interrupt_local_inference() is False

    def test_marker_increments_and_clears(self):
        assert llm_client._local_inflight == 0
        with llm_client._local_call_marker():
            assert llm_client._local_inflight == 1
        assert llm_client._local_inflight == 0

    def test_marker_clears_on_exception(self):
        with pytest.raises(ValueError), llm_client._local_call_marker():
            assert llm_client._local_inflight == 1
            raise ValueError("x")
        assert llm_client._local_inflight == 0

    def test_interrupt_hook_registered_with_ai_lock(self):
        # Importing llm_client must have wired the interrupt as a cancel hook.
        from mtgai.runtime import ai_lock

        assert llm_client.interrupt_local_inference in ai_lock._cancel_hooks


# Multi-block system + cached-user prefix (system_blocks / cache_user primitive)


class TestSystemBlocks:
    """Cover the ``system_blocks`` / ``cache_user`` transport primitive."""

    def test_anthropic_builds_one_block_per_item_with_cache_flags(self):
        resp = _make_response(
            tool_calls=[_make_tool_call("generate_card", SAMPLE_CARD)],
            finish_reason="tool_use",
        )
        provider, _ = _build_facade_provider_mock(resp)
        model = provider.new_model.return_value
        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="anthropic"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            generate_with_tool(
                user_prompt="Make a card.",
                tool_schema=SAMPLE_TOOL,
                model="claude-sonnet-4-6",
                system_blocks=[("base instructions", True), ("static set context", True)],
            )
        blocks = model.new_conversation.call_args.kwargs["system_blocks"]
        assert [b.text for b in blocks] == ["base instructions", "static set context"]
        assert [b.cache for b in blocks] == [True, True]
        # No cache_user requested -> the last user block stays uncached.
        assert model.new_conversation.call_args.kwargs["auto_cache_last_user"] is False

    def test_anthropic_cache_false_disables_block_cache(self):
        """A bare str item is uncached; cache=False also forces every block off."""
        resp = _make_response(tool_calls=[_make_tool_call("generate_card", SAMPLE_CARD)])
        provider, _ = _build_facade_provider_mock(resp)
        model = provider.new_model.return_value
        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="anthropic"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            generate_with_tool(
                user_prompt="u",
                tool_schema=SAMPLE_TOOL,
                system_blocks=["plain", ("cached", True)],
                cache=False,
            )
        blocks = model.new_conversation.call_args.kwargs["system_blocks"]
        assert [b.cache for b in blocks] == [False, False]

    def test_anthropic_cache_user_threads_auto_cache_last_user(self):
        resp = _make_response(tool_calls=[_make_tool_call("generate_card", SAMPLE_CARD)])
        provider, _ = _build_facade_provider_mock(resp)
        model = provider.new_model.return_value
        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="anthropic"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            generate_with_tool(
                system_prompt="Sys",
                user_prompt="User",
                tool_schema=SAMPLE_TOOL,
                cache_user=True,
            )
        assert model.new_conversation.call_args.kwargs["auto_cache_last_user"] is True

    def test_llamacpp_flattens_system_blocks_to_one_string(self):
        """Caching is Anthropic-only: blocks join to one system string and the
        cache flags are dropped (cache stats stay 0)."""
        resp = _make_response(
            tool_calls=[_make_tool_call("generate_card", SAMPLE_CARD)],
            usage=_make_usage(),
        )
        provider, _ = _build_facade_provider_mock(resp)
        model = provider.new_model.return_value
        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="llamacpp"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            result = generate_with_tool(
                user_prompt="Make a card.",
                tool_schema=SAMPLE_TOOL,
                model="vlad-gemma4-26b-dynamic",
                system_blocks=[("base", True), ("static", True)],
            )
        blocks = model.new_conversation.call_args.kwargs["system_blocks"]
        assert len(blocks) == 1
        assert blocks[0].text == "base\n\nstatic"
        assert result["cache_creation_input_tokens"] == 0
        assert result["cache_read_input_tokens"] == 0

    def test_system_prompt_and_system_blocks_together_raises(self):
        with pytest.raises(ValueError, match="either system_prompt or system_blocks"):
            generate_with_tool(
                system_prompt="Sys",
                user_prompt="User",
                tool_schema=SAMPLE_TOOL,
                system_blocks=["x"],
            )

    def test_missing_tool_schema_raises(self):
        with pytest.raises(ValueError, match="requires a tool_schema"):
            generate_with_tool(system_prompt="Sys", user_prompt="User")

    def test_card_gen_shape_stays_within_four_marker_cap(self):
        """The production card_gen call shape (two cached system blocks, default
        cache=True, no cache_user) must yield exactly 2 cached system blocks +
        auto_cache_tools=True + auto_cache_last_user=False = 3 cache_control
        markers, comfortably under Anthropic's cap of 4."""
        resp = _make_response(tool_calls=[_make_tool_call("generate_card", SAMPLE_CARD)])
        provider, _ = _build_facade_provider_mock(resp)
        model = provider.new_model.return_value
        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="anthropic"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            generate_with_tool(
                user_prompt="dynamic batch content",
                tool_schema=SAMPLE_TOOL,
                model="claude-sonnet-4-6",
                system_blocks=[("base instructions", True), ("static set context", True)],
            )
        kwargs = model.new_conversation.call_args.kwargs
        blocks = kwargs["system_blocks"]
        cached_blocks = sum(1 for b in blocks if b.cache)
        markers = (
            cached_blocks + int(kwargs["auto_cache_tools"]) + int(kwargs["auto_cache_last_user"])
        )
        assert cached_blocks == 2
        assert kwargs["auto_cache_tools"] is True
        assert kwargs["auto_cache_last_user"] is False
        assert markers <= 4

    def test_empty_system_block_is_dropped(self):
        """An empty / whitespace-only block must not reach the provider as a
        cached SystemBlock (the Anthropic API rejects empty text content)."""
        resp = _make_response(tool_calls=[_make_tool_call("generate_card", SAMPLE_CARD)])
        provider, _ = _build_facade_provider_mock(resp)
        model = provider.new_model.return_value
        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="anthropic"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            generate_with_tool(
                user_prompt="u",
                tool_schema=SAMPLE_TOOL,
                system_blocks=[("kept", True), ("", True), ("   ", False)],
            )
        blocks = model.new_conversation.call_args.kwargs["system_blocks"]
        assert [b.text for b in blocks] == ["kept"]


# ── Repetition guard wiring (llmfacade RepetitionGuard adoption) ──────


class TestRepetitionGuard:
    """The local-call repetition guard is configured + wired, and an
    unrecoverable loop on a tool call surfaces as a truncation so the existing
    truncation-retry handlers absorb it. Detection itself lives in (and is tested
    by) llmfacade; here we only pin MTGAI's adoption contract."""

    def test_module_guards_are_configured(self):
        from llmfacade import RepetitionGuard

        assert isinstance(llm_client._LLAMACPP_REP_GUARD, RepetitionGuard)
        assert isinstance(llm_client._LLAMACPP_REP_GUARD_TEXT, RepetitionGuard)
        # Free-text returns the last attempt rather than raising (preserves the
        # "a partial reply is still useful" contract of generate_text).
        assert llm_client._LLAMACPP_REP_GUARD_TEXT.on_exhausted == "return_last"

    def test_llamacpp_tool_call_forwards_guard(self):
        """The llamacpp tool path sets repetition_detection on the convo; the
        Anthropic path never does (cloud models don't loop)."""
        resp = _make_response(tool_calls=[_make_tool_call("generate_card", SAMPLE_CARD)])
        provider, _ = _build_facade_provider_mock(resp)
        model = provider.new_model.return_value
        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="llamacpp"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            generate_with_tool(
                system_prompt="Sys",
                user_prompt="User",
                tool_schema=SAMPLE_TOOL,
                model="vlad-gemma4-26b-dynamic",
            )
        kwargs = model.new_conversation.call_args.kwargs
        assert kwargs.get("repetition_detection") is llm_client._LLAMACPP_REP_GUARD

    def test_llamacpp_text_call_forwards_return_last_guard(self):
        """The free-text path uses the return_last guard (no raise on a loop)."""
        resp = _make_response(text="ok", usage=_make_usage(10, 5))
        provider, _ = _build_facade_provider_mock(resp)
        model = provider.new_model.return_value
        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="llamacpp"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            generate_text(system_prompt="Sys", user_prompt="User", model="vlad-gemma4-26b-dynamic")
        kwargs = model.new_conversation.call_args.kwargs
        assert kwargs.get("repetition_detection") is llm_client._LLAMACPP_REP_GUARD_TEXT

    def test_llamacpp_stream_call_forwards_guard(self):
        """stream_text sets the guard on the convo (abort+raise on a loop)."""
        delta = MagicMock(text_delta="hello", usage=None, finish_reason=None)
        end = MagicMock(text_delta="", usage=_make_usage(10, 5), finish_reason="stop")
        provider, convo = _build_facade_provider_mock(_make_response())
        convo.stream.return_value = [delta, end]
        model = provider.new_model.return_value
        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="llamacpp"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            list(
                llm_client.stream_text(
                    system_prompt="Sys", user_prompt="User", model="vlad-gemma4-26b-dynamic"
                )
            )
        kwargs = model.new_conversation.call_args.kwargs
        assert kwargs.get("repetition_detection") is llm_client._LLAMACPP_REP_GUARD

    def test_anthropic_tool_call_has_no_guard(self):
        resp = _make_response(
            tool_calls=[_make_tool_call("generate_card", SAMPLE_CARD)],
            finish_reason="tool_use",
        )
        provider, _ = _build_facade_provider_mock(resp)
        model = provider.new_model.return_value
        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="anthropic"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
        ):
            generate_with_tool(
                system_prompt="Sys",
                user_prompt="User",
                tool_schema=SAMPLE_TOOL,
                model="claude-sonnet-4-6",
            )
        assert "repetition_detection" not in model.new_conversation.call_args.kwargs

    def test_repetition_loop_becomes_output_truncated(self):
        """A RepetitionLoopError the guard couldn't shake is re-raised as an
        OutputTruncatedError so generate_gate_tool / reprint / slot_grouper /
        mechanic-escalation handlers treat a loop exactly like a real truncation."""
        from llmfacade.exceptions import RepetitionLoopError

        from mtgai.generation.token_utils import OutputTruncatedError

        loop = RepetitionLoopError(
            "Period 'spam ' (len=5) repeated 10+ times at tail",
            attempts=3,
            partial_text="spam spam spam ",
        )
        # A list with an exception member → MagicMock raises it on send().
        provider, _ = _build_facade_provider_mock([loop])
        with (
            patch("mtgai.generation.llm_client._resolve_provider", return_value="llamacpp"),
            patch("mtgai.generation.llm_client._get_provider", return_value=provider),
            pytest.raises(OutputTruncatedError, match="repetition loop"),
        ):
            generate_with_tool(
                system_prompt="Sys",
                user_prompt="User",
                tool_schema=SAMPLE_TOOL,
                model="vlad-gemma4-26b-dynamic",
            )
