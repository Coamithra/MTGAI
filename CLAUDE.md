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
