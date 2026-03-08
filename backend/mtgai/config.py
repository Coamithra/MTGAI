"""Central configuration using pydantic-settings.

Loaded from environment variables, .env file, or defaults.
"""

from pathlib import Path

from pydantic_settings import BaseSettings


class MTGAIConfig(BaseSettings):
    """Central configuration for the MTG AI Set Creator."""

    # === Paths ===
    project_root: Path = Path(__file__).parent.parent.parent.parent
    output_dir: Path = Path(__file__).parent.parent.parent.parent / "output"
    research_dir: Path = Path(__file__).parent.parent.parent.parent / "research"
    learnings_dir: Path = Path(__file__).parent.parent.parent.parent / "learnings"

    # === LLM Settings (populated after Phase 0D) ===
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-20250514"
    llm_temperature: float = 0.7
    llm_max_retries: int = 3

    # === Image Generation ===
    image_provider: str = "chatgpt"
    image_model: str = "dall-e-3"

    # === Print Specs (populated after Phase 0B) ===
    print_dpi: int = 300
    print_bleed_mm: float = 3.0
    card_width_mm: float = 63.0
    card_height_mm: float = 88.0
    color_space: str = "sRGB"

    # === Pipeline ===
    max_generation_retries: int = 3
    max_art_retries: int = 2
    batch_size: int = 10

    # === Text Overflow Constants ===
    max_rules_text_chars: int = 350
    max_flavor_text_chars: int = 150
    max_combined_text_chars: int = 450
    max_card_name_chars: int = 30
    rules_text_font_size_default: float = 8.5
    rules_text_font_size_min: float = 7.0

    # === API Keys (from environment / .env) ===
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    model_config = {
        "env_prefix": "MTGAI_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }
