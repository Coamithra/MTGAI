"""Tests for Ollama provider support in llm_client."""

import json
from unittest.mock import MagicMock, patch

import pytest

from mtgai.generation.llm_client import (
    _ollama_extract_json,
    _ollama_translate_tool,
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


# ── Tool schema translation ──────────────────────────────────────────


class TestToolTranslation:
    def test_basic_translation(self):
        result = _ollama_translate_tool(SAMPLE_TOOL)
        assert result["type"] == "function"
        assert result["function"]["name"] == "generate_card"
        assert result["function"]["description"] == "Generate a Magic card"
        assert result["function"]["parameters"] == SAMPLE_TOOL["input_schema"]

    def test_missing_description(self):
        tool = {"name": "foo", "input_schema": {"type": "object", "properties": {}}}
        result = _ollama_translate_tool(tool)
        assert result["function"]["description"] == ""

    def test_missing_input_schema(self):
        tool = {"name": "foo", "description": "bar"}
        result = _ollama_translate_tool(tool)
        assert result["function"]["parameters"] == {"type": "object", "properties": {}}


# ── JSON extraction from text ────────────────────────────────────────


class TestJsonExtraction:
    def test_fenced_json_block(self):
        text = 'Here is the card:\n```json\n{"name": "Foo", "mana_cost": "{W}"}\n```'
        result = _ollama_extract_json(text, "generate_card")
        assert result == {"name": "Foo", "mana_cost": "{W}"}

    def test_fenced_block_no_json_tag(self):
        text = 'Result:\n```\n{"name": "Foo"}\n```'
        result = _ollama_extract_json(text, "generate_card")
        assert result == {"name": "Foo"}

    def test_qwen_style_tool_call(self):
        text = '{"name": "generate_card", "arguments": {"name": "Bar", "mana_cost": "{R}"}}'
        result = _ollama_extract_json(text, "generate_card")
        assert result == {"name": "Bar", "mana_cost": "{R}"}

    def test_bare_json_object(self):
        text = 'I will generate the card.\n{"name": "Baz", "type_line": "Instant"}\nDone.'
        result = _ollama_extract_json(text, "generate_card")
        assert result == {"name": "Baz", "type_line": "Instant"}

    def test_nested_json(self):
        text = '{"outer": {"inner": "value"}, "key": "val"}'
        result = _ollama_extract_json(text, "tool")
        assert result == {"outer": {"inner": "value"}, "key": "val"}

    def test_no_json_found(self):
        text = "I cannot generate a card right now."
        result = _ollama_extract_json(text, "generate_card")
        assert result is None

    def test_malformed_json(self):
        text = '{"name": "broken'
        result = _ollama_extract_json(text, "generate_card")
        assert result is None

    def test_fenced_block_preferred_over_bare(self):
        """Fenced block should be tried first."""
        text = 'Bad: {"wrong": true}\n' '```json\n{"correct": true}\n```'
        result = _ollama_extract_json(text, "tool")
        assert result == {"correct": True}


# ── Cost calculation for local models ────────────────────────────────


class TestLocalCost:
    def test_unknown_model_is_free(self):
        cost = calc_cost("qwen2.5:14b", input_tokens=10000, output_tokens=5000)
        assert cost == 0.0

    def test_ollama_model_is_free(self):
        cost = calc_cost("llama3:8b", input_tokens=50000, output_tokens=20000)
        assert cost == 0.0


# ── Helpers for native API responses ─────────────────────────────────


def _make_ollama_response(
    content: str = "",
    tool_calls: list | None = None,
    prompt_eval_count: int = 100,
    eval_count: int = 50,
) -> dict:
    """Build a mock Ollama native API response dict."""
    msg: dict = {"role": "assistant", "content": content}
    if tool_calls is not None:
        msg["tool_calls"] = tool_calls
    return {
        "message": msg,
        "done": True,
        "prompt_eval_count": prompt_eval_count,
        "eval_count": eval_count,
    }


def _make_native_tool_call(name: str, arguments: dict) -> dict:
    """Build a tool_call entry for the native API format."""
    return {"function": {"name": name, "arguments": arguments}}


# ── End-to-end Ollama generate_with_tool ─────────────────────────────


class TestOllamaGenerateWithTool:
    """Test generate_with_tool routed to Ollama via _resolve_provider."""

    def _patch_ollama(self):
        """Patch _resolve_provider to route to Ollama regardless of model name."""
        return patch("mtgai.generation.llm_client._resolve_provider", return_value="ollama")

    def test_native_tool_calling(self):
        """Model uses native function calling properly."""
        tc = _make_native_tool_call("generate_card", SAMPLE_CARD)
        response = _make_ollama_response(tool_calls=[tc])

        with (
            self._patch_ollama(),
            patch("mtgai.generation.llm_client._ollama_post", return_value=response) as mock_post,
        ):
            result = generate_with_tool(
                system_prompt="You are a card designer.",
                user_prompt="Make a card.",
                tool_schema=SAMPLE_TOOL,
            )

        assert result["result"] == SAMPLE_CARD
        assert result["stop_reason"] == "tool_use"
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50
        assert result["cache_creation_input_tokens"] == 0
        assert result["cache_read_input_tokens"] == 0
        mock_post.assert_called_once()

    def test_tool_args_as_string(self):
        """Ollama may return tool arguments as a JSON string instead of dict."""
        tc = {"function": {"name": "generate_card", "arguments": json.dumps(SAMPLE_CARD)}}
        response = _make_ollama_response(tool_calls=[tc])

        with (
            self._patch_ollama(),
            patch("mtgai.generation.llm_client._ollama_post", return_value=response),
        ):
            result = generate_with_tool(
                system_prompt="Sys",
                user_prompt="User",
                tool_schema=SAMPLE_TOOL,
            )

        assert result["result"] == SAMPLE_CARD

    def test_text_extraction_fallback(self):
        """Model outputs JSON as text instead of using function calling."""
        text = f"Here is the card:\n```json\n{json.dumps(SAMPLE_CARD)}\n```"
        response = _make_ollama_response(content=text)

        with (
            self._patch_ollama(),
            patch("mtgai.generation.llm_client._ollama_post", return_value=response),
        ):
            result = generate_with_tool(
                system_prompt="You are a card designer.",
                user_prompt="Make a card.",
                tool_schema=SAMPLE_TOOL,
            )

        assert result["result"] == SAMPLE_CARD

    def test_retry_on_garbage(self):
        """Model produces garbage, retries, then succeeds."""
        bad_response = _make_ollama_response(content="I don't know how to do that.")
        good_response = _make_ollama_response(content=json.dumps(SAMPLE_CARD))

        with (
            self._patch_ollama(),
            patch(
                "mtgai.generation.llm_client._ollama_post",
                side_effect=[bad_response, good_response],
            ),
        ):
            result = generate_with_tool(
                system_prompt="You are a card designer.",
                user_prompt="Make a card.",
                tool_schema=SAMPLE_TOOL,
            )

        assert result["result"] == SAMPLE_CARD

    def test_all_retries_exhausted(self):
        """Raises ValueError after all retries fail."""
        bad_response = _make_ollama_response(content="no json here")

        with (
            self._patch_ollama(),
            patch("mtgai.generation.llm_client._ollama_post", return_value=bad_response),
        ):
            with pytest.raises(ValueError, match="failed to produce valid tool output"):
                generate_with_tool(
                    system_prompt="System",
                    user_prompt="User",
                    tool_schema=SAMPLE_TOOL,
                )

    def test_native_api_url_used(self):
        """Verify calls go to /api/chat, not /v1."""
        tc = _make_native_tool_call("generate_card", SAMPLE_CARD)
        response = _make_ollama_response(tool_calls=[tc])

        with (
            self._patch_ollama(),
            patch("mtgai.generation.llm_client._ollama_post", return_value=response) as mock_post,
        ):
            generate_with_tool(
                system_prompt="Sys",
                user_prompt="User",
                tool_schema=SAMPLE_TOOL,
            )

            call_args = mock_post.call_args
            assert "/api/chat" in call_args[0][0]

    def test_num_ctx_passed(self):
        """Verify num_ctx is included in the request body."""
        tc = _make_native_tool_call("generate_card", SAMPLE_CARD)
        response = _make_ollama_response(tool_calls=[tc])

        with (
            self._patch_ollama(),
            patch("mtgai.generation.llm_client._ollama_post", return_value=response) as mock_post,
            patch(
                "mtgai.generation.llm_client._ollama_get_context_window", return_value=128000
            ),
        ):
            generate_with_tool(
                system_prompt="Sys",
                user_prompt="User",
                tool_schema=SAMPLE_TOOL,
            )

            call_body = mock_post.call_args[0][1]
            assert call_body["options"]["num_ctx"] == 128000
            assert call_body["options"]["num_predict"] == 8192  # default max_tokens

    @patch("mtgai.generation.llm_client.PROVIDER", "anthropic")
    def test_anthropic_path_unchanged(self):
        """When PROVIDER=anthropic, the old code path is used."""
        with patch("mtgai.generation.llm_client._generate_anthropic") as mock_anth:
            mock_anth.return_value = {
                "result": SAMPLE_CARD,
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "stop_reason": "end_turn",
                "model": "claude-sonnet-4-6",
            }
            result = generate_with_tool(
                system_prompt="Sys",
                user_prompt="User",
                tool_schema=SAMPLE_TOOL,
            )
            assert result["model"] == "claude-sonnet-4-6"
            mock_anth.assert_called_once()


# ── Connection retry tests ───────────────────────────────────────────


class TestOllamaRetry:
    def test_retries_on_connection_error(self):
        """_ollama_post retries on connection errors."""
        import requests

        with patch("mtgai.generation.llm_client.time.sleep"):
            with patch("requests.post") as mock_post:
                mock_post.side_effect = [
                    requests.ConnectionError("refused"),
                    MagicMock(
                        status_code=200,
                        raise_for_status=lambda: None,
                        json=lambda: {"message": {}, "done": True},
                    ),
                ]

                from mtgai.generation.llm_client import _ollama_post

                result = _ollama_post("http://localhost:11434/api/chat", {})
                assert result["done"] is True
                assert mock_post.call_count == 2

    def test_raises_after_max_retries(self):
        """_ollama_post raises after exhausting retries."""
        import requests

        with patch("mtgai.generation.llm_client.time.sleep"):
            with patch("requests.post") as mock_post:
                mock_post.side_effect = requests.ConnectionError("refused")

                from mtgai.generation.llm_client import _ollama_post

                with pytest.raises(requests.ConnectionError):
                    _ollama_post("http://localhost:11434/api/chat", {})

                assert mock_post.call_count == 3
