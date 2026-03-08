# Phase 0C: Project Setup - Implementation Plan

## Objective

Initialize the complete project structure for the MTG AI Set Creator. This phase produces a buildable, lintable, testable Python project skeleton with fully defined data models, state management, and tooling. Every downstream phase depends on the schema and project conventions established here.

---

## Quick Start (Context Reset)

**Prerequisites**: Python 3.12+, uv package manager installed, git.

**Read first**: This plan is self-contained. The schema defined here is the single source of truth for all downstream phases.

**Start with**: Section 11 (Implementation Order) gives the exact sequence.

**You're done when**: All items in Section 9.4 (Skeleton Verification Checklist) pass.

---

## 1. Project Structure

```
mtgai/
├── backend/
│   ├── pyproject.toml              # uv/pip project config, Ruff config, pytest config
│   ├── mtgai/                      # Main package
│   │   ├── __init__.py             # Package version, top-level exports
│   │   ├── config.py               # Shared configuration (paths, constants, model settings)
│   │   ├── models/                 # Pydantic data models
│   │   │   ├── __init__.py
│   │   │   ├── card.py             # Card, CardFace, ManaCost models
│   │   │   ├── set.py              # Set model
│   │   │   ├── mechanic.py         # Mechanic model
│   │   │   ├── pipeline.py         # PipelineStatus, GenerationAttempt models
│   │   │   └── enums.py            # Rarity, Color, CardType, CardStatus enums
│   │   ├── validation/             # Validation library (shared by Phase 1C and Phase 4)
│   │   │   ├── __init__.py
│   │   │   ├── rules_text.py       # MTG rules text grammar validation
│   │   │   ├── balance.py          # Power level / mana cost balance checks
│   │   │   ├── color_pie.py        # Color pie violation detection
│   │   │   ├── text_overflow.py    # Card text length / overflow estimation
│   │   │   ├── uniqueness.py       # Duplicate / near-duplicate detection
│   │   │   └── spelling.py         # Spell check on card text fields
│   │   ├── generation/             # Card generation (Phase 1C)
│   │   │   ├── __init__.py
│   │   │   └── (placeholder)
│   │   ├── rendering/              # Card rendering (Phase 2C)
│   │   │   ├── __init__.py
│   │   │   └── (placeholder)
│   │   ├── review/                 # CLI review tools (Phase 1A+)
│   │   │   ├── __init__.py
│   │   │   ├── __main__.py         # Entry point for `python -m mtgai.review`
│   │   │   └── (placeholder)
│   │   ├── pipeline/               # Pipeline orchestration
│   │   │   ├── __init__.py
│   │   │   └── (placeholder)
│   │   └── io/                     # JSON file I/O helpers
│   │       ├── __init__.py
│   │       ├── card_io.py          # Load/save card JSON, set JSON
│   │       └── paths.py            # Path conventions, naming helpers
│   └── tests/
│       ├── conftest.py             # Shared fixtures (sample cards, sample set)
│       ├── test_models/
│       │   ├── test_card.py        # Card model validation tests
│       │   ├── test_set.py         # Set model tests
│       │   └── test_enums.py       # Enum coverage tests
│       ├── test_validation/
│       │   └── (placeholder)       # Filled in Phase 1C
│       ├── test_io/
│       │   └── test_card_io.py     # Round-trip serialization tests
│       └── test_pipeline/
│           └── test_status.py      # Pipeline status transition tests
├── research/                       # Research outputs (Phases 0A, 0B, 0D)
│   └── .gitkeep
├── learnings/                      # Learnings from each phase
│   └── .gitkeep
├── output/                         # Generated artifacts (gitignored except structure)
│   ├── .gitkeep
│   └── sets/                       # Per-set output directories
│       └── .gitkeep
├── .github/
│   └── workflows/
│       └── ci.yml                  # GitHub Actions: lint + test
├── .gitignore
├── CLAUDE.md                       # Project conventions for AI assistants
└── README.md                       # Minimal project readme (one paragraph)
```

### Directory Explanations

| Directory | Purpose |
|-----------|---------|
| `backend/mtgai/models/` | Pydantic v2 data models. The **single source of truth** for card structure. Every other module imports from here. |
| `backend/mtgai/validation/` | Stateless validation functions. Each module exports a `validate_*()` function that takes a Card/Set and returns a list of `ValidationResult`. Built during Phase 1C, reused by Phase 4. |
| `backend/mtgai/generation/` | LLM-based card generation. Placeholder until Phase 1C. |
| `backend/mtgai/rendering/` | Card image rendering. Placeholder until Phase 2C. |
| `backend/mtgai/review/` | CLI review tools (`python -m mtgai.review`). Minimal version in Phase 1A, expanded in Phase 3A. |
| `backend/mtgai/pipeline/` | Orchestrates generation -> validation -> art -> render pipeline. Manages status transitions. |
| `backend/mtgai/io/` | File I/O helpers. Handles loading/saving JSON card data, path conventions, file naming. |
| `research/` | Markdown + JSON research outputs. Version-controlled. |
| `learnings/` | Post-phase retrospectives. Version-controlled. |
| `output/` | Binary outputs (art, renders, print files). NOT version-controlled (gitignored). |

---

## 2. Card Data Schema

### 2.1 Enums (`backend/mtgai/models/enums.py`)

```python
from enum import StrEnum

class Color(StrEnum):
    WHITE = "W"
    BLUE = "U"
    BLACK = "B"
    RED = "R"
    GREEN = "G"

class Rarity(StrEnum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    MYTHIC = "mythic"

class CardType(StrEnum):
    """Primary card types (supertypes and subtypes are separate fields)."""
    CREATURE = "Creature"
    INSTANT = "Instant"
    SORCERY = "Sorcery"
    ENCHANTMENT = "Enchantment"
    ARTIFACT = "Artifact"
    PLANESWALKER = "Planeswalker"
    LAND = "Land"
    # Battle, Kindred, etc. can be added as needed

class Supertype(StrEnum):
    LEGENDARY = "Legendary"
    BASIC = "Basic"
    SNOW = "Snow"
    WORLD = "World"

class CardStatus(StrEnum):
    """Pipeline status for a card. Transitions are forward-only (with manual override)."""
    DRAFT = "draft"                 # Just generated, not yet validated
    VALIDATED = "validated"         # Passed automated validation
    APPROVED = "approved"           # Human-approved card design
    ART_GENERATED = "art_generated" # Art has been generated
    RENDERED = "rendered"           # Card image rendered with frame + art
    PRINT_READY = "print_ready"     # Final print file exported

class CardLayout(StrEnum):
    """Card layout type. Maps to Scryfall's 'layout' field."""
    NORMAL = "normal"
    SPLIT = "split"
    MODAL_DFC = "modal_dfc"         # Modal double-faced card
    TRANSFORM = "transform"         # Transforming double-faced card
    SAGA = "saga"
    ADVENTURE = "adventure"
    # Add more as needed
```

### 2.2 Card Model (`backend/mtgai/models/card.py`)

```python
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime

class ManaCost(BaseModel):
    """Parsed representation of a mana cost string like '{2}{W}{U}'."""
    raw: str                             # e.g., "{2}{W}{U}"
    cmc: float                           # Converted mana cost (numeric)
    colors: list[Color]                  # Colors present in the cost (derived)
    generic: int = 0                     # Generic mana component
    # Individual color counts
    white: int = 0
    blue: int = 0
    black: int = 0
    red: int = 0
    green: int = 0
    colorless: int = 0                   # {C} colorless specifically
    x_count: int = 0                     # Number of {X} in cost

class GenerationAttempt(BaseModel):
    """Tracks a single generation or render attempt for a card."""
    attempt_number: int
    timestamp: datetime
    prompt_used: str | None = None       # LLM prompt (for card gen) or image prompt (for art gen)
    model_used: str | None = None        # e.g., "claude-sonnet-4-20250514", "dall-e-3"
    success: bool
    error_message: str | None = None
    validation_errors: list[str] = Field(default_factory=list)
    input_tokens: int | None = None      # Actual input tokens used (for cost tracking)
    output_tokens: int | None = None     # Actual output tokens used (for cost tracking)
    cost_usd: float | None = None        # Calculated cost for this attempt
    prompt_version: str | None = None    # Which prompt template version was used (e.g., "system-v2")

class Card(BaseModel):
    """
    Full card data model. Designed for compatibility with Scryfall's data model
    while adding pipeline-specific fields.

    Scryfall reference: https://scryfall.com/docs/api/cards
    """
    # === Identity ===
    id: str | None = None                # Internal UUID (generated on creation)
    name: str                            # Card name, e.g., "Lightning Bolt"
    layout: CardLayout = CardLayout.NORMAL

    # === Mana & Colors ===
    mana_cost: str | None = None         # Raw mana cost string: "{1}{R}"
    mana_cost_parsed: ManaCost | None = None  # Parsed mana cost (derived)
    cmc: float = 0.0                     # Converted mana cost
    colors: list[Color] = Field(default_factory=list)           # Card colors
    color_identity: list[Color] = Field(default_factory=list)   # Full color identity (includes rules text)

    # === Typeline ===
    type_line: str                       # Full type line: "Legendary Creature -- Human Wizard"
    supertypes: list[str] = Field(default_factory=list)    # ["Legendary"]
    card_types: list[str] = Field(default_factory=list)    # ["Creature"]
    subtypes: list[str] = Field(default_factory=list)      # ["Human", "Wizard"]

    # === Rules & Flavor ===
    oracle_text: str = ""                # Rules text (Scryfall calls this oracle_text)
    flavor_text: str | None = None       # Italic flavor text
    reminder_text: str | None = None     # Reminder text for keywords (usually inline in oracle_text)

    # === Stats ===
    power: str | None = None             # String because of */X values, e.g., "3", "*"
    toughness: str | None = None         # String because of */X values
    loyalty: str | None = None           # Starting loyalty for planeswalkers

    # === Set & Collector Info ===
    collector_number: str = ""           # e.g., "001", "142a"
    rarity: Rarity = Rarity.COMMON
    set_code: str = ""                   # Three-letter set code, e.g., "DSK"
    artist: str = "AI Generated"         # Artist credit

    # === Pipeline State ===
    status: CardStatus = CardStatus.DRAFT
    generation_attempts: list[GenerationAttempt] = Field(default_factory=list)
    art_generation_attempts: list[GenerationAttempt] = Field(default_factory=list)
    render_attempts: list[GenerationAttempt] = Field(default_factory=list)

    # === File Paths (relative to output/sets/<set-code>/) ===
    art_path: str | None = None          # e.g., "art/001_lightning_bolt_v2.png"
    render_path: str | None = None       # e.g., "renders/001_lightning_bolt_v1.png"
    art_prompt: str | None = None        # The image generation prompt that produced the art

    # === Design Metadata (not in Scryfall, specific to our pipeline) ===
    design_notes: str | None = None      # Free-form notes from generation or human review
    is_reprint: bool = False             # Whether this card is a reprint of an existing MTG card
    scryfall_id: str | None = None       # If reprint, the Scryfall ID of the original
    draft_archetype: str | None = None   # Which draft archetype this card supports (e.g., "WU_fliers")
    mechanic_tags: list[str] = Field(default_factory=list)  # Which set mechanics this card uses
    slot_id: str | None = None           # Reference to the skeleton slot this card fills

    # === Double-Faced / Multi-Face (for DFCs, split, adventure) ===
    card_faces: list["CardFace"] | None = None  # Non-null only for multi-face layouts

    # === Timestamps ===
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CardFace(BaseModel):
    """
    For double-faced, split, or adventure cards. Each face has its own
    name, mana cost, type line, etc. Mirrors Scryfall's card_faces structure.
    """
    name: str
    mana_cost: str | None = None
    type_line: str
    oracle_text: str = ""
    flavor_text: str | None = None
    power: str | None = None
    toughness: str | None = None
    loyalty: str | None = None
    colors: list[Color] = Field(default_factory=list)
    art_path: str | None = None
    art_prompt: str | None = None


# Resolve forward reference
Card.model_rebuild()
```

### 2.3 Mechanic Model (`backend/mtgai/models/mechanic.py`)

```python
class Mechanic(BaseModel):
    """A set-specific keyword or ability mechanic."""
    name: str                            # e.g., "Delirium"
    keyword_type: str                    # "keyword_ability", "ability_word", "keyword_action"
    reminder_text: str                   # e.g., "(As long as four or more card types are among cards in your graveyard...)"
    rules_template: str                  # Template for rules text using this mechanic
    description: str = ""               # Design intent / flavor description
    colors: list[Color] = Field(default_factory=list)         # Primary colors for this mechanic
    allowed_rarities: list[Rarity] = Field(default_factory=list)  # Which rarities can have this mechanic
    card_type_affinity: list[str] = Field(default_factory=list)   # Which card types commonly get this mechanic
    is_evergreen: bool = False           # Whether this is an evergreen keyword (flying, trample, etc.)
    example_cards: list[str] = Field(default_factory=list)  # Names of example cards using this mechanic
    design_notes: str | None = None      # How this mechanic fits the set theme
```

### 2.4 Set Model (`backend/mtgai/models/set.py`)

```python
class DraftArchetype(BaseModel):
    """One of the 10 two-color draft archetypes."""
    color_pair: str                      # e.g., "WU", "BR"
    name: str                            # e.g., "Azorius Fliers"
    description: str                     # What the archetype does
    primary_mechanics: list[str] = Field(default_factory=list)  # Mechanic names this archetype uses
    signpost_uncommon: str | None = None # Name of the signpost uncommon card

class SetSkeleton(BaseModel):
    """The structural backbone of a set before individual cards are generated."""
    total_cards: int
    commons: int
    uncommons: int
    rares: int
    mythics: int
    basic_lands: int
    # Slot allocation: how many cards per (color x rarity x type)
    slot_matrix: dict = Field(default_factory=dict)  # Flexible structure, defined in Phase 1A

class Set(BaseModel):
    """A complete MTG set."""
    name: str                            # e.g., "Duskmourn: House of Horror"
    code: str                            # Three-letter set code, e.g., "DSK"
    theme: str                           # One-line theme summary
    description: str = ""               # Longer description of the set's world/story
    cards: list[Card] = Field(default_factory=list)
    mechanics: list[Mechanic] = Field(default_factory=list)
    draft_archetypes: list[DraftArchetype] = Field(default_factory=list)
    skeleton: SetSkeleton | None = None
    # Metadata
    created_at: datetime | None = None
    updated_at: datetime | None = None
    version: str = "0.1.0"              # Set data version for schema evolution
```

### 2.5 Scryfall Compatibility Notes

The Card model intentionally mirrors Scryfall's field names where applicable:

| Our Field | Scryfall Field | Notes |
|-----------|---------------|-------|
| `name` | `name` | Identical |
| `mana_cost` | `mana_cost` | Same format: `{2}{W}{U}` |
| `cmc` | `cmc` | Identical |
| `colors` | `colors` | We use enum, Scryfall uses strings |
| `color_identity` | `color_identity` | Same semantics |
| `type_line` | `type_line` | Identical format |
| `oracle_text` | `oracle_text` | We use this name (not "rules_text") for Scryfall compat |
| `flavor_text` | `flavor_text` | Identical |
| `power`, `toughness` | `power`, `toughness` | String type to support `*` |
| `loyalty` | `loyalty` | Identical |
| `collector_number` | `collector_number` | String type |
| `rarity` | `rarity` | Same values |
| `layout` | `layout` | Same values |
| `card_faces` | `card_faces` | Same structure for multi-face |

Fields we add that Scryfall does not have: `status`, `generation_attempts`, `art_prompt`, `design_notes`, `is_reprint`, `draft_archetype`, `mechanic_tags`, `slot_id`.

---

## 3. State Management

### 3.1 Pipeline Status Transitions

```
draft --> validated --> approved --> art_generated --> rendered --> print_ready
  ^          |            |              |               |
  |          v            v              v               v
  +---- (retry) ---- (reject) ----- (reject) ------- (reject)
         back to        back to        back to         back to
         draft          draft          approved        art_generated
```

**Forward transitions** happen automatically (validation passes) or via human action (approve).
**Backward transitions** happen on rejection or regeneration (always go back to the appropriate earlier stage).

### 3.2 Resumable Pipeline Design

The pipeline must survive interruption at any point. Design principles:

1. **Each card is independent**: Cards are stored as individual JSON files. Pipeline processes one card at a time (or in small batches). Interruption loses at most the current card.
2. **Status is the resume point**: On restart, query all cards, find those not yet at the target status, and process them.
3. **Idempotent operations**: Re-running a pipeline step on an already-completed card is a no-op (check status first).
4. **Attempt tracking**: Every generation/render attempt is appended to the card's attempt list. This provides a full history for debugging and cost tracking.

### 3.3 Attempt Tracking

Each `GenerationAttempt` records:
- `attempt_number`: Sequential within the attempt list
- `timestamp`: When the attempt was made
- `prompt_used`: The full prompt sent to the LLM or image generator
- `model_used`: Model identifier (e.g., `"claude-sonnet-4-20250514"`)
- `success`: Whether the attempt produced a valid result
- `error_message`: If failed, what went wrong
- `validation_errors`: Specific validation failures that triggered a retry

### 3.4 File Naming Conventions

```
output/
└── sets/
    └── <SET_CODE>/                      # e.g., "DSK"
        ├── set.json                     # Full set metadata (Set model, without card data)
        ├── cards/
        │   ├── 001_lightning_bolt.json   # Individual card JSON files
        │   ├── 002_serra_angel.json
        │   └── ...
        ├── art/
        │   ├── 001_lightning_bolt_v1.png # Art attempts (versioned)
        │   ├── 001_lightning_bolt_v2.png
        │   └── ...
        ├── renders/
        │   ├── 001_lightning_bolt.png    # Final rendered card image
        │   └── ...
        └── print/
            ├── fronts/                  # Print-ready front images
            ├── backs/                   # Card back image(s)
            └── manifest.json            # Print order manifest
```

**Naming pattern**: `<collector_number>_<card_name_slug>[_v<attempt>].<ext>`
- `card_name_slug`: lowercase, underscores for spaces, stripped of special chars
- `_v<attempt>`: only on art files (to keep history); renders and card JSON are overwritten
- Helper function in `mtgai/io/paths.py`:
  ```python
  def card_slug(collector_number: str, card_name: str) -> str:
      slug = card_name.lower().replace(" ", "_").replace("'", "").replace(",", "")
      return f"{collector_number}_{slug}"
  ```

---

## 4. Shared Configuration System

Rather than scattering magic numbers across modules, centralize configuration in `backend/mtgai/config.py`:

```python
from pathlib import Path
from pydantic_settings import BaseSettings

class MTGAIConfig(BaseSettings):
    """
    Central configuration. Loaded from environment variables, .env file,
    or set-specific config.json. Uses pydantic-settings for validation.
    """
    # === Paths ===
    project_root: Path = Path(__file__).parent.parent.parent.parent  # mtgai/
    output_dir: Path = project_root / "output"
    research_dir: Path = project_root / "research"
    learnings_dir: Path = project_root / "learnings"

    # === LLM Settings (populated after Phase 0D) ===
    llm_provider: str = "anthropic"          # "anthropic" | "openai"
    llm_model: str = "claude-sonnet-4-20250514"
    llm_temperature: float = 0.7
    llm_max_retries: int = 3

    # === Image Generation ===
    image_provider: str = "chatgpt"          # "chatgpt" | "midjourney" | "local"
    image_model: str = "dall-e-3"

    # === Print Specs (populated after Phase 0B) ===
    print_dpi: int = 300
    print_bleed_mm: float = 3.0
    card_width_mm: float = 63.0
    card_height_mm: float = 88.0
    color_space: str = "CMYK"

    # === Pipeline ===
    max_generation_retries: int = 3
    max_art_retries: int = 2
    batch_size: int = 10                     # Cards per LLM batch call

    # === Text Overflow Constants ===
    # Maximum character counts for card text areas before font-size reduction is needed.
    # These are used by both the card generator (to constrain LLM output length) and
    # the renderer (to trigger dynamic font sizing). Values are approximate and should
    # be calibrated against actual rendered cards during Phase 2C.
    max_rules_text_chars: int = 350          # Max chars before rules text overflows at default font size
    max_flavor_text_chars: int = 150         # Max chars for flavor text
    max_combined_text_chars: int = 450       # Max combined rules + flavor text
    max_card_name_chars: int = 30            # Max chars before name font shrinks
    rules_text_font_size_default: float = 8.5  # Default rules text font size in points
    rules_text_font_size_min: float = 7.0      # Minimum before the card is considered "text overflow"

    # === API Keys (from environment / .env) ===
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    class Config:
        env_prefix = "MTGAI_"
        env_file = ".env"
        env_file_encoding = "utf-8"
```

**Why a config system instead of scattered JSON files**:
- Type-validated via Pydantic
- Environment variable overrides (12-factor app style)
- `.env` file support for API keys (never committed)
- Single import for any module that needs settings
- Print specs, LLM settings, and paths all in one place

---

## 5. Tooling Setup

### 5.1 `pyproject.toml`

```toml
[project]
name = "mtgai"
version = "0.1.0"
description = "AI-powered Magic: The Gathering custom set creator"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.7,<3",
    "pydantic-settings>=2.3,<3",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "ruff>=0.5",
]
# These groups are added in later phases:
# generation = ["anthropic>=0.30", "openai>=1.30"]
# rendering = ["Pillow>=10.0", "cairosvg>=2.7"]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # pyflakes
    "I",      # isort
    "N",      # pep8-naming
    "UP",     # pyupgrade
    "B",      # flake8-bugbear
    "SIM",    # flake8-simplify
    "TCH",    # type-checking imports
    "RUF",    # Ruff-specific rules
]

[tool.ruff.lint.isort]
known-first-party = ["mtgai"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-v --tb=short"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### 5.2 uv Setup Commands

```bash
# From backend/ directory:
uv venv                          # Create virtual environment
uv pip install -e ".[dev]"       # Install package in editable mode with dev deps
```

### 5.3 Ruff Configuration

Ruff config is embedded in `pyproject.toml` (see above). Key choices:
- **Line length 100**: Slightly wider than default 88, better for Pydantic models with long field definitions
- **Python 3.12**: Enables `X | Y` union syntax, `StrEnum`, and other modern features
- **isort integration**: Automatic import sorting via Ruff (no separate isort tool needed)

### 5.4 pytest Configuration

Also embedded in `pyproject.toml`. Key choices:
- `testpaths = ["tests"]`: Only discover tests in the `tests/` directory
- `pythonpath = ["."]`: So `import mtgai` works from the `backend/` directory
- `-v --tb=short`: Verbose test names, short tracebacks by default

---

## 6. CI Setup (GitHub Actions)

### `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3

      - name: Set up Python 3.12
        run: uv python install 3.12

      - name: Install dependencies
        run: uv pip install -e ".[dev]" --system

      - name: Lint with Ruff
        run: |
          ruff check .
          ruff format --check .

      - name: Run tests
        run: pytest --tb=short -q
```

---

## 7. CLAUDE.md

The project `CLAUDE.md` should contain:

```markdown
# MTGAI Project Conventions

## Project Structure
- Backend code lives in `backend/mtgai/`
- Tests live in `backend/tests/`, mirroring the source structure
- Research outputs go in `research/`
- Learnings go in `learnings/`
- Generated files (art, renders, print files) go in `output/` (gitignored)

## Development
- Python 3.12+, managed with uv
- Linting: `ruff check .` and `ruff format .` from `backend/`
- Tests: `pytest` from `backend/`
- All commands run from the `backend/` directory

## Code Style
- Use Pydantic v2 models for all data structures
- Use StrEnum for enumerations
- Use `X | Y` union syntax (not `Union[X, Y]`)
- Use `list[X]` (not `List[X]`)
- Line length: 100 characters
- Imports sorted by Ruff (isort rules)

## Data Models
- Card schema is the single source of truth: `mtgai/models/card.py`
- Field names match Scryfall's API where applicable (e.g., `oracle_text`, not `rules_text`)
- All models inherit from `pydantic.BaseModel`
- Card data is stored as JSON files in `output/sets/<SET_CODE>/cards/`

## Naming Conventions
- Card files: `<collector_number>_<card_name_slug>.json`
- Art files: `<collector_number>_<card_name_slug>_v<attempt>.png`
- Render files: `<collector_number>_<card_name_slug>.png`

## Pipeline
- Cards progress through statuses: draft -> validated -> approved -> art_generated -> rendered -> print_ready
- Every generation attempt is tracked (prompt, model, timestamp, success/failure)
- Pipeline is resumable: interrupted operations resume from the last incomplete card

## Testing
- Validation tests are the most important category
- Use fixtures in conftest.py for sample card data
- Test file structure mirrors source structure

## Git
- Card JSON is version-controlled
- Art and rendered images are NOT version-controlled (gitignored)
- Never commit API keys or .env files
```

---

## 8. Binary File Strategy

### `.gitignore`

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.eggs/

# Virtual environments
.venv/
venv/
env/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Environment variables / secrets
.env
.env.*
!.env.example

# Output directory (art, renders, print files are binary, not version-controlled)
output/sets/*/art/
output/sets/*/renders/
output/sets/*/print/

# Keep directory structure
!output/.gitkeep
!output/sets/.gitkeep

# OS files
.DS_Store
Thumbs.db

# Coverage
.coverage
htmlcov/
```

**Key principle**: Card JSON (`output/sets/*/cards/*.json`) IS version-controlled. It's the canonical data. Art and renders are regenerable and large, so they are gitignored.

### Output Directory Structure

```
output/
└── sets/
    └── ABC/                         # Set code
        ├── set.json                 # Set metadata
        ├── cards/                   # Version-controlled card data
        │   ├── 001_card_name.json
        │   └── ...
        ├── art/                     # Gitignored - generated art
        │   ├── 001_card_name_v1.png
        │   └── ...
        ├── renders/                 # Gitignored - rendered card images
        │   ├── 001_card_name.png
        │   └── ...
        └── print/                   # Gitignored - print-ready files
            ├── fronts/
            ├── backs/
            └── manifest.json
```

---

## 9. Verification Tests

These tests prove the skeleton works and the schema is sound. Written during Phase 0C, they become the foundation for all future tests.

### 9.1 Model Tests (`tests/test_models/test_card.py`)

```python
def test_card_creation_minimal():
    """A card can be created with just name and type_line."""
    card = Card(name="Lightning Bolt", type_line="Instant")
    assert card.name == "Lightning Bolt"
    assert card.status == CardStatus.DRAFT

def test_card_creation_full():
    """A card with all fields populated round-trips through JSON."""
    card = Card(
        name="Serra Angel",
        mana_cost="{3}{W}{W}",
        cmc=5.0,
        type_line="Creature -- Angel",
        oracle_text="Flying, vigilance",
        power="4",
        toughness="4",
        rarity=Rarity.UNCOMMON,
        colors=[Color.WHITE],
        color_identity=[Color.WHITE],
        collector_number="034",
    )
    json_str = card.model_dump_json()
    round_tripped = Card.model_validate_json(json_str)
    assert round_tripped == card

def test_card_scryfall_field_names():
    """Verify we use Scryfall-compatible field names."""
    card = Card(name="Test", type_line="Creature")
    data = card.model_dump()
    # These fields should exist with Scryfall-compatible names
    assert "oracle_text" in data
    assert "color_identity" in data
    assert "collector_number" in data
    assert "type_line" in data

def test_planeswalker_card():
    """Planeswalker cards have loyalty but no power/toughness."""
    card = Card(
        name="Test Planeswalker",
        type_line="Legendary Planeswalker -- Test",
        loyalty="4",
        oracle_text="+1: Draw a card.\n-3: Deal 3 damage.\n-7: You win.",
    )
    assert card.loyalty == "4"
    assert card.power is None

def test_double_faced_card():
    """DFC cards have card_faces."""
    card = Card(
        name="Front // Back",
        type_line="Creature // Creature",
        layout=CardLayout.TRANSFORM,
        card_faces=[
            CardFace(name="Front", type_line="Creature", oracle_text="Transform"),
            CardFace(name="Back", type_line="Creature", oracle_text="Transformed"),
        ],
    )
    assert len(card.card_faces) == 2
```

### 9.2 Status Transition Tests (`tests/test_pipeline/test_status.py`)

```python
def test_status_values():
    """All expected statuses exist."""
    assert CardStatus.DRAFT == "draft"
    assert CardStatus.PRINT_READY == "print_ready"

def test_default_status_is_draft():
    card = Card(name="Test", type_line="Instant")
    assert card.status == CardStatus.DRAFT
```

### 9.3 I/O Round-Trip Tests (`tests/test_io/test_card_io.py`)

```python
def test_save_and_load_card(tmp_path):
    """Card JSON saves to disk and loads back identically."""
    card = Card(name="Test Card", type_line="Instant", rarity=Rarity.COMMON)
    path = tmp_path / "test_card.json"
    path.write_text(card.model_dump_json(indent=2))
    loaded = Card.model_validate_json(path.read_text())
    assert loaded == card

def test_save_and_load_set(tmp_path):
    """Set with cards saves to disk and loads back."""
    card = Card(name="Test Card", type_line="Instant")
    s = Set(name="Test Set", code="TST", theme="Testing", cards=[card])
    path = tmp_path / "set.json"
    path.write_text(s.model_dump_json(indent=2))
    loaded = Set.model_validate_json(path.read_text())
    assert loaded.name == "Test Set"
    assert len(loaded.cards) == 1
```

### 9.4 Skeleton Verification Checklist

After Phase 0C is complete, run this checklist:

- [ ] `uv pip install -e ".[dev]"` succeeds
- [ ] `ruff check .` passes with no errors
- [ ] `ruff format --check .` passes
- [ ] `pytest` runs and all tests pass
- [ ] `python -c "from mtgai.models.card import Card; print(Card(name='Test', type_line='Instant').model_dump_json())"` works
- [ ] `.gitignore` correctly ignores `output/sets/*/art/` but not `output/sets/*/cards/`
- [ ] CI workflow runs on push (after first git push)

---

## 10. Cross-Cutting Concerns & Master Plan Suggestions

### 10.1 Should the Card schema include fields not in the master plan?

**Yes, and we've added them above.** Specifically:

| Field | Rationale |
|-------|-----------|
| `draft_archetype` | Essential for Phase 1A skeleton generation. Each card should know which color-pair archetype it supports (e.g., "WU_fliers"). Without this, the skeleton generator can't verify archetype coverage. |
| `mechanic_tags` | Needed for as-fan calculations (Phase 4A) and mechanic distribution validation. A card using "Delirium" should tag it so we can count as-fan across the set. |
| `slot_id` | Links a generated card back to its skeleton slot. Critical for resumable generation -- we need to know which slots are filled and which are empty. |
| `is_reprint` / `scryfall_id` | Master plan mentions reprints in Phase 1C. We need to distinguish reprints from originals and link back to the source card for data import. |
| `design_notes` | Freeform field for the LLM to explain its design choices, or for human reviewers to annotate. Useful for iterating on problem cards. |
| `art_prompt` | Master plan tracks prompts in attempts, but having the final winning prompt on the card itself is convenient for the art generation pipeline. |

### 10.2 Is the pipeline status model sufficient? Should there be sub-statuses?

The six-status model (`draft` -> `validated` -> `approved` -> `art_generated` -> `rendered` -> `print_ready`) is **sufficient for V0/V1**. However, consider these potential extensions:

**Sub-statuses that might be useful:**
- `validation_failed` -- distinct from `draft`, indicates the card was generated but failed validation (vs never generated at all). Currently we handle this via `generation_attempts[-1].success == False`, which is adequate.
- `art_review` -- between `art_generated` and `rendered`, for human art approval. Currently there's no gate here; art goes straight to rendering. Consider adding if art rejection rate is high.
- `needs_revision` -- human has reviewed and wants changes but hasn't written them yet. Currently handled by reverting to `draft`.

**Recommendation**: Keep the six statuses for now. The attempt tracking provides all the sub-status information we need. If Phase 1C reveals that we need more granular statuses, add them then. The `CardStatus` enum is easy to extend.

### 10.3 Should 0C and 0D be merged?

**No, but they should overlap.** Here's why:

- **0C can start immediately**: Project setup, tooling, CI, `.gitignore`, and the basic schema don't depend on LLM strategy decisions.
- **Schema refinement after 0D**: The LLM output format (Phase 0D) might suggest schema changes (e.g., "the LLM works best if we include a `design_intent` field alongside each card"). These are additive changes to the schema, not rewrites.
- **Practical overlap**: Start 0C, get the skeleton running. Start 0D in parallel. When 0D concludes, circle back to 0C to add any schema fields or config entries the LLM strategy requires.

The master plan already shows this: `0C + 0D (parallel)` in the execution order.

**Action**: In the schema, include placeholder fields that 0D is likely to need (e.g., `design_notes`, `art_prompt`). Mark them as `Optional` so they don't break anything if 0D decides they're unnecessary.

### 10.4 Should there be a shared config system?

**Yes, and we've defined one above** (Section 4, `MTGAIConfig`). The master plan mentions JSON files for data storage, but configuration is different from data:

| Concern | Storage | Rationale |
|---------|---------|-----------|
| Card data | JSON files | Static once generated, human-readable, git-diffable |
| Set metadata | JSON files | Same as cards |
| Print specs | Config object | Referenced by multiple modules (renderer, print export) |
| LLM settings | Config object + env vars | API keys must not be in JSON files |
| Path conventions | Config object | Avoids hardcoded paths scattered across modules |

The `pydantic-settings` approach gives us environment variable overrides, `.env` file support, and type validation -- all for free.

### 10.5 Token cost estimate: is $30 per set realistic?

**Preliminary answer (detailed analysis in Phase 0D plan):** $30 is plausible but tight for Claude/GPT-4 class models. It's realistic for Claude 3.5 Sonnet or GPT-4o, but not for Claude Opus or GPT-4 (legacy). The 0D plan includes a detailed breakdown. Key variables are batch size (single card vs 5-10 at a time), retry rate, and system prompt size.

---

## 11. Implementation Order

Within Phase 0C, execute in this order:

1. **Create directory structure** (5 min)
2. **Write `pyproject.toml`** with all tooling config (10 min)
3. **Write enums and models** -- `enums.py`, `card.py`, `mechanic.py`, `set.py`, `pipeline.py` (1 hour)
4. **Write `config.py`** with `MTGAIConfig` (15 min)
5. **Write I/O helpers** -- `card_io.py`, `paths.py` (30 min)
6. **Write `conftest.py`** with sample card fixtures (15 min)
7. **Write verification tests** -- model tests, I/O tests, status tests (45 min)
8. **Write `.gitignore`, `CLAUDE.md`** (10 min)
9. **Write CI workflow** (10 min)
10. **Run full verification checklist** (10 min)
11. **Write `learnings/phase0c.md`** with any surprises (10 min)

**Estimated total: ~3 hours**
