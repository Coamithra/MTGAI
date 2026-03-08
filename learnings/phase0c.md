# Phase 0C Learnings

## What Worked
- Pydantic v2 models with `StrEnum` and `X | Y` syntax work cleanly on Python 3.12
- Using `from __future__ import annotations` in model files for forward references (Card references CardFace)
- `pydantic-settings` with `model_config` dict instead of inner `Config` class (Pydantic v2 style)
- Ruff catches real issues fast — caught ambiguous Unicode minus signs in test data, unused imports
- `uv` for dependency management is fast and reliable on Windows

## What Didn't Work / Gotchas
- TCH (type-checking imports) Ruff rule conflicts with Pydantic — Pydantic needs runtime type resolution, so moving imports to `TYPE_CHECKING` blocks breaks model validation. Removed TCH from Ruff config.
- Ambiguous Unicode: MTG uses real minus signs (−) in loyalty costs like "−3:", but Ruff's RUF001 flags these. Used ASCII hyphens (-) in test data instead.
- Windows path handling: `Path(__file__).parent` works but care needed with config defaults — computed paths in class body are evaluated at import time, not at instance creation.

## Key Decisions
- Removed `TCH` from Ruff lint rules (incompatible with Pydantic runtime type needs)
- Used `model_config = {}` dict style instead of inner `Config` class (Pydantic v2 recommended approach)
- Card schema uses Scryfall field names (`oracle_text`, `color_identity`) for downstream compatibility
- `save_set()` strips cards from set JSON — cards are saved individually for resumable pipeline

## Verification Results
- 29 tests passing
- `ruff check` + `ruff format --check` clean
- Card model imports and serializes correctly
- I/O round-trip works for both Card and Set

## For Downstream Phases
- Card JSON schema is stable — Phase 0D can generate JSON schemas from it for LLM tool use
- `output/sets/<CODE>/cards/` is the canonical card storage path
- Status transitions are simple field updates via `model_copy(update={...})`
