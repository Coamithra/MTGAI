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
    "type_line": "Creature — Human",
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
        text = (
            'Bad: {"wrong": true}\n'
            '```json\n{"correct": true}\n```'
        )
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


# ── End-to-end Ollama generate_with_tool ─────────────────────────────


def _make_ollama_response(content: str = "", tool_calls=None):
    """Build a mock OpenAI-compatible response."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls

    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "tool_calls" if tool_calls else "stop"

    usage = MagicMock()
    usage.prompt_tokens = 100
    usage.completion_tokens = 50

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


class TestOllamaGenerateWithTool:
    """Test generate_with_tool with MTGAI_PROVIDER=ollama."""

    @patch.dict("os.environ", {"MTGAI_PROVIDER": "ollama"})
    @patch("mtgai.generation.llm_client.PROVIDER", "ollama")
    @patch("mtgai.generation.llm_client.OLLAMA_MODEL", "qwen2.5:14b")
    def test_native_tool_calling(self):
        """Model uses OpenAI function calling properly."""
        tc = MagicMock()
        tc.function.name = "generate_card"
        tc.function.arguments = json.dumps(SAMPLE_CARD)
        tc.id = "call_123"

        response = _make_ollama_response(tool_calls=[tc])

        with patch("openai.OpenAI") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = response

            result = generate_with_tool(
                system_prompt="You are a card designer.",
                user_prompt="Make a card.",
                tool_schema=SAMPLE_TOOL,
            )

        assert result["result"] == SAMPLE_CARD
        assert result["model"] == "qwen2.5:14b"
        assert result["stop_reason"] == "tool_use"
        assert result["cache_creation_input_tokens"] == 0
        assert result["cache_read_input_tokens"] == 0

    @patch.dict("os.environ", {"MTGAI_PROVIDER": "ollama"})
    @patch("mtgai.generation.llm_client.PROVIDER", "ollama")
    @patch("mtgai.generation.llm_client.OLLAMA_MODEL", "qwen2.5:14b")
    def test_text_extraction_fallback(self):
        """Model outputs JSON as text instead of using function calling."""
        text = f"Here is the card:\n```json\n{json.dumps(SAMPLE_CARD)}\n```"
        response = _make_ollama_response(content=text)

        with patch("openai.OpenAI") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = response

            result = generate_with_tool(
                system_prompt="You are a card designer.",
                user_prompt="Make a card.",
                tool_schema=SAMPLE_TOOL,
            )

        assert result["result"] == SAMPLE_CARD
        assert result["model"] == "qwen2.5:14b"

    @patch.dict("os.environ", {"MTGAI_PROVIDER": "ollama"})
    @patch("mtgai.generation.llm_client.PROVIDER", "ollama")
    @patch("mtgai.generation.llm_client.OLLAMA_MODEL", "qwen2.5:14b")
    def test_retry_on_garbage(self):
        """Model produces garbage, retries, then succeeds."""
        bad_response = _make_ollama_response(content="I don't know how to do that.")
        good_response = _make_ollama_response(content=json.dumps(SAMPLE_CARD))

        with patch("openai.OpenAI") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.chat.completions.create.side_effect = [bad_response, good_response]

            result = generate_with_tool(
                system_prompt="You are a card designer.",
                user_prompt="Make a card.",
                tool_schema=SAMPLE_TOOL,
            )

        assert result["result"] == SAMPLE_CARD
        assert mock_client.chat.completions.create.call_count == 2

    @patch.dict("os.environ", {"MTGAI_PROVIDER": "ollama"})
    @patch("mtgai.generation.llm_client.PROVIDER", "ollama")
    @patch("mtgai.generation.llm_client.OLLAMA_MODEL", "qwen2.5:14b")
    def test_all_retries_exhausted(self):
        """Raises ValueError after all retries fail."""
        bad_response = _make_ollama_response(content="no json here")

        with patch("openai.OpenAI") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = bad_response

            with pytest.raises(ValueError, match="failed to produce valid tool output"):
                generate_with_tool(
                    system_prompt="System",
                    user_prompt="User",
                    tool_schema=SAMPLE_TOOL,
                )

        # 1 initial + 2 retries = 3
        assert mock_client.chat.completions.create.call_count == 3

    @patch.dict("os.environ", {"MTGAI_PROVIDER": "ollama"})
    @patch("mtgai.generation.llm_client.PROVIDER", "ollama")
    @patch("mtgai.generation.llm_client.OLLAMA_MODEL", "qwen2.5:14b")
    def test_ollama_url_and_model_used(self):
        """Verify the OpenAI client is configured with the right URL."""
        tc = MagicMock()
        tc.function.name = "generate_card"
        tc.function.arguments = json.dumps(SAMPLE_CARD)
        response = _make_ollama_response(tool_calls=[tc])

        with patch("openai.OpenAI") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = response

            generate_with_tool(
                system_prompt="Sys",
                user_prompt="User",
                tool_schema=SAMPLE_TOOL,
            )

            # Check OpenAI client was created with Ollama URL
            mock_cls.assert_called_once()
            call_kwargs = mock_cls.call_args
            assert "/v1" in call_kwargs.kwargs.get("base_url", call_kwargs[1].get("base_url", ""))

    @patch("mtgai.generation.llm_client.PROVIDER", "anthropic")
    def test_anthropic_path_unchanged(self):
        """When PROVIDER=anthropic, the old code path is used (no OpenAI import)."""
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
