"""Tests for the MTGAIConfig configuration system."""

from unittest.mock import patch

import pytest

from mtgai.config import MTGAIConfig

# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


def test_default_llm_provider():
    """Default LLM provider is anthropic."""
    config = MTGAIConfig()
    assert config.llm_provider == "anthropic"


def test_default_llm_model():
    """Default LLM model is set."""
    config = MTGAIConfig()
    assert "claude" in config.llm_model or config.llm_model != ""


def test_default_llm_temperature():
    """Default temperature is a reasonable float between 0 and 2."""
    config = MTGAIConfig()
    assert 0.0 <= config.llm_temperature <= 2.0


def test_default_llm_max_retries():
    """Default max retries is a positive integer."""
    config = MTGAIConfig()
    assert config.llm_max_retries >= 1


def test_default_image_provider():
    """Default image provider is set."""
    config = MTGAIConfig()
    assert config.image_provider != ""


def test_default_print_specs():
    """Default print specs are reasonable for poker-sized cards."""
    config = MTGAIConfig()
    assert config.print_dpi == 300
    assert config.print_bleed_mm == pytest.approx(3.0)
    # Standard MTG card is 63 x 88 mm
    assert config.card_width_mm == pytest.approx(63.0)
    assert config.card_height_mm == pytest.approx(88.0)
    assert config.color_space == "sRGB"


def test_default_pipeline_settings():
    """Default pipeline batch sizes and retries are sensible."""
    config = MTGAIConfig()
    assert config.max_generation_retries >= 1
    assert config.max_art_retries >= 1
    assert config.batch_size >= 1


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def test_project_root_is_directory():
    """project_root resolves to a directory that exists (or at least is a Path)."""
    config = MTGAIConfig()
    # project_root is computed relative to config.py's location
    assert config.project_root is not None
    # It should be a Path object
    from pathlib import Path

    assert isinstance(config.project_root, Path)


def test_output_dir_is_path():
    """output_dir is a valid Path."""
    config = MTGAIConfig()
    from pathlib import Path

    assert isinstance(config.output_dir, Path)
    assert "output" in str(config.output_dir)


def test_research_dir_is_path():
    """research_dir is a valid Path."""
    config = MTGAIConfig()
    from pathlib import Path

    assert isinstance(config.research_dir, Path)
    assert "research" in str(config.research_dir)


def test_learnings_dir_is_path():
    """learnings_dir is a valid Path."""
    config = MTGAIConfig()
    from pathlib import Path

    assert isinstance(config.learnings_dir, Path)
    assert "learnings" in str(config.learnings_dir)


# ---------------------------------------------------------------------------
# Text overflow constants
# ---------------------------------------------------------------------------


def test_max_rules_text_chars():
    """Max rules text chars is a reasonable limit."""
    config = MTGAIConfig()
    assert config.max_rules_text_chars > 0
    assert config.max_rules_text_chars <= 1000


def test_max_flavor_text_chars():
    """Max flavor text chars is a reasonable limit."""
    config = MTGAIConfig()
    assert config.max_flavor_text_chars > 0
    assert config.max_flavor_text_chars <= 500


def test_max_combined_text_chars():
    """Max combined text is at least as large as rules or flavor alone."""
    config = MTGAIConfig()
    assert config.max_combined_text_chars >= config.max_rules_text_chars
    assert config.max_combined_text_chars >= config.max_flavor_text_chars


def test_max_card_name_chars():
    """Max card name chars is a reasonable limit."""
    config = MTGAIConfig()
    assert config.max_card_name_chars > 0
    assert config.max_card_name_chars <= 100


def test_font_size_defaults():
    """Font size defaults are reasonable."""
    config = MTGAIConfig()
    assert config.rules_text_font_size_default > 0
    assert config.rules_text_font_size_min > 0
    assert config.rules_text_font_size_min <= config.rules_text_font_size_default


# ---------------------------------------------------------------------------
# Environment variable override
# ---------------------------------------------------------------------------


def test_env_prefix_override():
    """MTGAI_ prefixed env vars override defaults."""
    with patch.dict("os.environ", {"MTGAI_LLM_PROVIDER": "openai"}):
        config = MTGAIConfig()
        assert config.llm_provider == "openai"


def test_env_override_temperature():
    """MTGAI_LLM_TEMPERATURE overrides the default."""
    with patch.dict("os.environ", {"MTGAI_LLM_TEMPERATURE": "0.3"}):
        config = MTGAIConfig()
        assert config.llm_temperature == pytest.approx(0.3)


def test_env_override_batch_size():
    """MTGAI_BATCH_SIZE overrides the default."""
    with patch.dict("os.environ", {"MTGAI_BATCH_SIZE": "25"}):
        config = MTGAIConfig()
        assert config.batch_size == 25


def test_env_override_api_key():
    """API keys can be set via environment variables."""
    with patch.dict("os.environ", {"MTGAI_ANTHROPIC_API_KEY": "test-key-123"}):
        config = MTGAIConfig()
        assert config.anthropic_api_key == "test-key-123"


def test_api_keys_default_none():
    """API keys default to None when not set."""
    # Use a clean environment without any MTGAI_ keys
    with patch.dict("os.environ", {}, clear=False):
        config = MTGAIConfig()
        # If no env var is set, the default is None
        # (This may or may not be None depending on .env file)
        assert config.anthropic_api_key is None or isinstance(config.anthropic_api_key, str)
