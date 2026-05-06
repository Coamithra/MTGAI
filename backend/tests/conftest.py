"""Shared test fixtures for sample cards and sets."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from mtgai.models.card import Card, CardFace
from mtgai.models.enums import CardLayout, Color, Rarity
from mtgai.models.mechanic import Mechanic
from mtgai.models.set import DraftArchetype, Set, SetSkeleton


@pytest.fixture
def isolated_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect every output-touching module at a tmp tree.

    Many modules capture ``OUTPUT_ROOT`` / ``SETS_ROOT`` at import time
    (the resolution chain ``set_artifact_dir`` walks AND every
    independent stage runner / server module that derives a path from
    them). Patching only one breaks subtly: a test seeds files in
    tmp_path but the request handler reads from the developer's real
    ``output/sets/`` because *its* OUTPUT_ROOT was never patched.

    This fixture patches the full set so any test that just wants
    "isolation from the real output dir" can declare ``isolated_output``
    and stop guessing which constants matter. The model_settings cache
    is invalidated so each test sees a fresh seed.

    Yields the ``tmp_path / "sets"`` root so test fixtures can keep
    seeding ``sets_root / code / "theme.json"`` etc. directly.
    """
    from mtgai.io import asset_paths
    from mtgai.pipeline import engine, stages
    from mtgai.pipeline import server as pipeline_server
    from mtgai.runtime import active_set, runtime_state
    from mtgai.settings import model_settings as ms

    sets_root = tmp_path / "sets"
    settings_dir = tmp_path / "settings"
    sets_root.mkdir(parents=True, exist_ok=True)
    settings_dir.mkdir(parents=True, exist_ok=True)

    # Resolution chain: asset_paths is what set_artifact_dir consults.
    monkeypatch.setattr(asset_paths, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(asset_paths, "SETS_ROOT", sets_root)
    monkeypatch.setattr(ms, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(ms, "SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(ms, "SETS_DIR", sets_root)
    monkeypatch.setattr(ms, "GLOBAL_TOML", settings_dir / "global.toml")
    monkeypatch.setattr(ms, "LEGACY_CURRENT_TOML", settings_dir / "current.toml")

    # Modules that hold their own legacy OUTPUT_ROOT/SETS_ROOT bindings.
    # Any of these can leak into real output/sets/ if missed (server's
    # _get_current_state was the canary for this whole class of bug).
    monkeypatch.setattr(engine, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(pipeline_server, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(stages, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(runtime_state, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(runtime_state, "SETS_ROOT", sets_root)
    monkeypatch.setattr(active_set, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(active_set, "SETS_ROOT", sets_root)
    monkeypatch.setattr(active_set, "_SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(active_set, "_LAST_SET_PATH", settings_dir / "last_set.toml")

    ms.invalidate_cache()
    yield sets_root
    ms.invalidate_cache()


@pytest.fixture
def sample_creature() -> Card:
    """A standard creature card (Serra Angel)."""
    return Card(
        name="Serra Angel",
        mana_cost="{3}{W}{W}",
        cmc=5.0,
        type_line="Creature — Angel",
        oracle_text="Flying, vigilance",
        power="4",
        toughness="4",
        rarity=Rarity.UNCOMMON,
        colors=[Color.WHITE],
        color_identity=[Color.WHITE],
        collector_number="034",
        set_code="TST",
        supertypes=[],
        card_types=["Creature"],
        subtypes=["Angel"],
    )


@pytest.fixture
def sample_instant() -> Card:
    """A simple instant card (Lightning Bolt)."""
    return Card(
        name="Lightning Bolt",
        mana_cost="{R}",
        cmc=1.0,
        type_line="Instant",
        oracle_text="Lightning Bolt deals 3 damage to any target.",
        rarity=Rarity.COMMON,
        colors=[Color.RED],
        color_identity=[Color.RED],
        collector_number="141",
        set_code="TST",
        card_types=["Instant"],
    )


@pytest.fixture
def sample_planeswalker() -> Card:
    """A planeswalker card."""
    return Card(
        name="Jace, Test Subject",
        mana_cost="{1}{U}{U}",
        cmc=3.0,
        type_line="Legendary Planeswalker — Jace",
        oracle_text=(
            "+1: Draw a card.\n"
            "-3: Return target creature to its owner's hand.\n"
            "-7: You draw seven cards."
        ),
        loyalty="3",
        rarity=Rarity.MYTHIC,
        colors=[Color.BLUE],
        color_identity=[Color.BLUE],
        collector_number="058",
        set_code="TST",
        supertypes=["Legendary"],
        card_types=["Planeswalker"],
        subtypes=["Jace"],
    )


@pytest.fixture
def sample_dfc() -> Card:
    """A double-faced (transform) card."""
    return Card(
        name="Daybound Wolf // Nightbound Terror",
        type_line="Creature — Wolf // Creature — Werewolf",
        layout=CardLayout.TRANSFORM,
        rarity=Rarity.UNCOMMON,
        set_code="TST",
        collector_number="200",
        card_faces=[
            CardFace(
                name="Daybound Wolf",
                mana_cost="{1}{G}",
                type_line="Creature — Wolf",
                oracle_text="Daybound",
                power="2",
                toughness="2",
                colors=[Color.GREEN],
            ),
            CardFace(
                name="Nightbound Terror",
                type_line="Creature — Werewolf",
                oracle_text="Nightbound",
                power="4",
                toughness="4",
                colors=[Color.GREEN],
            ),
        ],
    )


@pytest.fixture
def sample_mechanic() -> Mechanic:
    """A set-specific mechanic."""
    return Mechanic(
        name="Investigate",
        keyword_type="keyword_action",
        reminder_text=(
            "(Create a Clue token. It's an artifact with "
            '"{2}, Sacrifice this artifact: Draw a card.")'
        ),
        rules_template="Investigate",
        description="Create Clue tokens for card advantage",
        colors=[Color.WHITE, Color.BLUE, Color.GREEN],
        allowed_rarities=[Rarity.COMMON, Rarity.UNCOMMON, Rarity.RARE],
    )


@pytest.fixture
def sample_set(sample_creature: Card, sample_instant: Card) -> Set:
    """A minimal test set."""
    return Set(
        name="Test Set",
        code="TST",
        theme="Testing",
        description="A set used for unit testing.",
        cards=[sample_creature, sample_instant],
        skeleton=SetSkeleton(
            total_cards=280,
            commons=101,
            uncommons=80,
            rares=60,
            mythics=20,
            basic_lands=5,
        ),
        draft_archetypes=[
            DraftArchetype(
                color_pair="WU",
                name="Azorius Fliers",
                description="Evasive creatures with tempo support",
            ),
        ],
    )
