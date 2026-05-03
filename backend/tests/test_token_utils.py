"""Tests for token counting and truncation detection utilities."""

import pytest

from mtgai.generation.token_utils import (
    ContextOverflowError,
    InputTruncatedError,
    OutputTruncatedError,
    available_for_input,
    check_post_call,
    check_pre_call,
    count_messages_tokens,
    count_tokens,
)


# ── Basic token counting ────────────────────────────────────────────


class TestCountTokens:
    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_short_text(self):
        tokens = count_tokens("Hello world")
        assert 1 <= tokens <= 5

    def test_longer_text(self):
        text = "The quick brown fox jumps over the lazy dog. " * 100
        tokens = count_tokens(text)
        assert tokens > 100

    def test_json_text(self):
        """JSON content should be countable."""
        text = '{"name": "Test Card", "mana_cost": "{1}{W}", "type_line": "Creature"}'
        tokens = count_tokens(text)
        assert tokens > 5


class TestCountMessagesTokens:
    def test_simple_messages(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        tokens = count_messages_tokens(messages)
        assert tokens > 0

    def test_with_tools(self):
        messages = [{"role": "user", "content": "Hello"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test",
                    "description": "A test tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        with_tools = count_messages_tokens(messages, tools=tools)
        without_tools = count_messages_tokens(messages)
        assert with_tools > without_tools

    def test_empty_messages(self):
        assert count_messages_tokens([]) == 0


# ── Pre-call check ──────────────────────────────────────────────────


class TestCheckPreCall:
    def test_small_input_passes(self):
        """Short messages should not raise."""
        messages = [
            {"role": "system", "content": "Be helpful."},
            {"role": "user", "content": "Hi"},
        ]
        # Should not raise - tiny input vs 32k default context
        check_pre_call("unknown-model", messages)

    def test_huge_input_raises(self):
        """Input exceeding context window should raise ContextOverflowError."""
        # Create a message that's way bigger than any context window
        huge_text = "word " * 200_000  # ~200k tokens
        messages = [{"role": "user", "content": huge_text}]

        with pytest.raises(ContextOverflowError) as exc_info:
            check_pre_call("unknown-model", messages, output_reserve=4096)

        assert exc_info.value.estimated_tokens > 0
        assert exc_info.value.available_tokens > 0


# ── Post-call check ─────────────────────────────────────────────────


class TestCheckPostCall:
    def test_normal_response_passes(self):
        """Normal response with reasonable token counts should not raise."""
        data = {
            "prompt_tokens": 500,
            "completion_tokens": 200,
            "finish_reason": "stop",
        }
        # Estimated ~500 tokens, got 500 back - fine
        check_post_call(data, estimated_input_tokens=500, model="test")

    def test_input_truncation_detected(self):
        """Should raise when the backend processed far fewer tokens than sent."""
        data = {
            "prompt_tokens": 1000,
            "completion_tokens": 200,
            "finish_reason": "stop",
        }
        # We estimated 5000 tokens but the backend only processed 1000
        with pytest.raises(InputTruncatedError) as exc_info:
            check_post_call(data, estimated_input_tokens=5000, model="test")

        assert exc_info.value.expected_tokens == 5000
        assert exc_info.value.actual_tokens == 1000

    def test_output_truncation_finish_reason_length(self):
        """Should raise when finish_reason is 'length'."""
        data = {
            "prompt_tokens": 500,
            "completion_tokens": 8192,
            "finish_reason": "length",
        }
        with pytest.raises(OutputTruncatedError):
            check_post_call(data, estimated_input_tokens=500, model="test")

    def test_output_truncation_hit_num_predict(self):
        """Should raise when completion_tokens hits num_predict exactly."""
        data = {
            "prompt_tokens": 500,
            "completion_tokens": 4096,
            "finish_reason": "stop",
        }
        with pytest.raises(OutputTruncatedError):
            check_post_call(
                data, estimated_input_tokens=500, model="test", num_predict=4096
            )

    def test_tokenizer_mismatch_tolerance(self):
        """Should allow ~30% difference due to tokenizer mismatch."""
        data = {
            "prompt_tokens": 800,
            "completion_tokens": 200,
            "finish_reason": "stop",
        }
        # Estimated 1000, got 800 back - within tolerance (ratio 0.8)
        check_post_call(data, estimated_input_tokens=1000, model="test")

    def test_zero_prompt_eval_skips_check(self):
        """If prompt_tokens is 0, skip input truncation check."""
        data = {
            "prompt_tokens": 0,
            "completion_tokens": 200,
            "finish_reason": "stop",
        }
        # Should not raise even with high estimate
        check_post_call(data, estimated_input_tokens=50000, model="test")

    def test_num_predict_negative_skips_check(self):
        """num_predict=-1 (unlimited) should not trigger output truncation."""
        data = {
            "prompt_tokens": 500,
            "completion_tokens": 50000,
            "finish_reason": "stop",
        }
        check_post_call(
            data, estimated_input_tokens=500, model="test", num_predict=-1
        )


# ── Available for input ──────────────────────────────────────────────


class TestAvailableForInput:
    def test_basic_budget(self):
        """Should return positive budget for small system prompt."""
        budget = available_for_input(
            "unknown-model",
            system_prompt="Be helpful.",
            output_reserve=4096,
        )
        # Default 32k context - small prompt - 4k reserve = ~27k available
        assert budget > 20000

    def test_large_prompt_reduces_budget(self):
        big_prompt = "You are an expert. " * 5000
        budget = available_for_input(
            "unknown-model",
            system_prompt=big_prompt,
            output_reserve=4096,
        )
        small_budget = available_for_input(
            "unknown-model",
            system_prompt="Be helpful.",
            output_reserve=4096,
        )
        assert budget < small_budget
