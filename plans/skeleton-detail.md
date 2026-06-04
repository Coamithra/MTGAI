# Skeleton: fine-grained card subtypes

Trello: [Revisit skeleton - make more detailed](https://trello.com/c/qHGgod0O)

## Context

The skeleton's type system is coarse: every typed slot is one of 7 macro types
(`creature / instant / sorcery / enchantment / artifact / planeswalker / land`,
`SlotCardType` in `skeleton/generator.py`). It cannot say "this artifact is an
Equipment", "this enchantment is an Aura (local) not a global one", "this is a
Vehicle", "a Saga", or "an artifact creature vs a plain artifact". All that nuance
is left to the card-gen LLM, so a set's non-creature mix is unstructured and not
steerable. The card wants the skeleton to STATE a fine-grained, randomized subtype
distribution (with ranges), tweakable by the user and the AI knob-tuner.

## Research (Stage 1) - done

Fresh Scryfall pass over the last 12 premier sets (`research/scripts/subtype_analysis.py`
-> `research/subtype-distribution.md`). Classification:

- Recurring (12/12 sets) -> standing knobs: Equipment, Aura, Artifact Creature,
  Vehicle (8/12, recurring deciduous).
- Irregular/deciduous -> "irregular bucket" (pick 0-N): Saga (4/12), Enchantment
  Creature (2/12, theme-defining), Class, Shrine.
- One-set-exclusive -> exclude: Room (DSK), Case (MKM).

`instant`/`sorcery`/`planeswalker`/`land` have no meaningful subtype split.

## Design (Stage 2)

### 1. Subtype as a pure overlay (`card_subtype`)

The coarse `card_type` stays one of the 7 values - reprints, lands, the
balance/density invariants, and the relabel's count reconciliation all read it
unchanged. We add an optional refinement field on `SkeletonSlot`:

```python
class SlotCardSubtype(StrEnum):
    # recurring (standing knobs)
    EQUIPMENT = "equipment"
    VEHICLE = "vehicle"
    AURA = "aura"
    ARTIFACT_CREATURE = "artifact_creature"
    # irregular / deciduous (the bucket)
    SAGA = "saga"
    CLASS = "class"
    SHRINE = "shrine"
    ENCHANTMENT_CREATURE = "enchantment_creature"

class SkeletonSlot(BaseModel):
    ...
    card_subtype: str | None = None   # refines card_type; None = plain
```

Parent-type eligibility (enforced in code):
- `equipment`, `vehicle` -> only colorless `artifact` slots
- `aura`, `saga`, `class`, `shrine` -> only colored `enchantment` slots
- `artifact_creature`, `enchantment_creature` -> `creature` slots (any color)

`render_slot_string` shows the subtype label in the type position when present:
`"Colorless . uncommon . equipment . CMC2 . evergreen"`,
`"Black . rare . saga . CMC4 . complex"`,
`"Green . common . artifact creature . CMC3 . evergreen"`,
`"White . common . aura (local enchantment) . CMC2 . ..."`.

### 2. New knobs (group `subtype`)

Counts are per ~277-card set, scaled to `set_size` like the rarity weights. Added
to BOTH `KNOB_SPECS` and `SkeletonKnobs` (drift guard). Defaults lean; the AI tuner
bumps them for a matching theme.

| key | default | min | max | kind |
|---|---|---|---|---|
| `equipment_count` | 5 | 0 | 24 | int |
| `vehicle_count` | 2 | 0 | 12 | int |
| `aura_count` | 5 | 0 | 12 | int |
| `artifact_creature_count` | 4 | 0 | 34 | int |
| `irregular_subtype_count` | 1 | 0 | 3 | int |
| `subtype_jitter` | 0.30 | 0.0 | 0.6 | float |
| `subtype_seed` | 0 | 0 | 9999 | int |

`irregular_subtype_count` = how many deciduous specials from the bucket to include;
`subtype_jitter` = the +/- random band on each scaled count; `subtype_seed` = the
re-roll handle. All surface in the wizard + to the AI tuner automatically (schema +
listing are generated from `KNOB_SPECS`).

### 3. The irregular bucket

A curated module constant in `generator.py` of deciduous enchantment/creature
subtypes MTG reuses across sets, each with its parent + a typical count range:

```python
IRREGULAR_SUBTYPES = [
  IrregularSubtype(SAGA,                 parent="enchantment", colored=True, lo=2, hi=5),
  IrregularSubtype(CLASS,                parent="enchantment", colored=True, lo=2, hi=4),
  IrregularSubtype(SHRINE,               parent="enchantment", colored=True, lo=1, hi=5),
  IrregularSubtype(ENCHANTMENT_CREATURE, parent="creature",                  lo=4, hi=12),
]
```

The seeded RNG shuffles the bucket and takes the first `irregular_subtype_count`;
each chosen one fills `randint(lo, hi)` (scaled) eligible slots. Which ones get
picked is RNG now; theme/LLM-driven selection is explicitly deferred.

### 4. Randomization - deterministic, re-rollable

`_assign_subtypes(slots, knobs, set_size, set_code)` runs in `generate_skeleton`
after signposts are marked, before the balance report:

1. `rng = random.Random(f"{set_code}|{knobs.subtype_seed}")` - a stable string seed
   (NOT builtin `hash()`), so same project+seed -> same assignment (resume stable),
   and bumping `subtype_seed` re-rolls.
2. `center = count * set_size/277`; `realized = round(center*(1 + rng.uniform(-j,+j)))`,
   clamped >= 0.
3. Gather eligible slots per parent (rules above), EXCLUDING special slots
   (`cycle_id`, `reserved_card`, `signpost_for`, planeswalker, land) so structural
   families stay clean. Shuffle, label the first `realized` (capped at availability),
   rest stay plain. Standing subtypes are planned first, then the bucket, so the
   recurring types get their slots before the specials.

Subtypes never change `card_type`, color, rarity, or counts - it's a labelling
pass, so every existing balance/density invariant holds.

### 5. Threading

- `render_slot_string` - show the subtype label (relabel + card-gen fallback + the
  Skeleton-tab diff all read it).
- Knob tuner - auto (schema/listing from `KNOB_SPECS`); good `help` text per knob +
  a short subtype paragraph in `skeleton_knobs_context.txt`.
- Wizard `wizard_skeleton.js` - add `subtype` to `GROUP_LABELS`.

### Out of scope

- Subtypes for instants/sorceries/planeswalkers/lands.
- LLM/theme-driven selection of WHICH irregular subtype (deferred; RNG for now).
- Forcing card-gen to honor the subtype as a hard constraint (it's strong guidance
  in the descriptor; conformance already checks card-vs-slot).
- Changing the coarse type distribution or any invariant; new validators.

## Tests (`tests/test_skeleton*.py`)

- Drift guard stays green (new knobs in both lists) - existing test covers it.
- New-knob defaults/clamp/from_payload (extend `test_skeleton_knobs.py`).
- `_assign_subtypes`: jitter=0 -> exact counts; eligibility (equipment only on
  colorless artifacts, aura only on colored enchantments, never on
  land/PW/cycle/reserved/signpost); cap when too few slots; same seed -> identical,
  different seed -> differs; irregular bucket respects `irregular_subtype_count`.
- `render_slot_string` renders the subtype label.

## Verification

- `ruff check . && ruff format .`, `python -c "import mtgai"`, `pytest` from `backend/`.
- Manual: open a project, run the Skeleton stage, confirm the subtype knobs render +
  relabel descriptors show equipment/aura/vehicle/saga.
