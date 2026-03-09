# Validation Chain Design

Design specification for the card validation pipeline that checks LLM-generated cards
for correctness. This document defines pseudocode and specifications; full implementation
is deferred to Phase 1C.

**Source schema**: `backend/mtgai/models/card.py` (Card, ManaCost, CardFace, GenerationAttempt)
**Source enums**: `backend/mtgai/models/enums.py` (Color, Rarity, CardType, Supertype, CardStatus, CardLayout)

---

## Architecture Overview

### Execution Order

Validators run in a fixed sequence, cheapest and fastest first. If a hard-fail occurs in
an early validator, later validators still run so the LLM receives all errors in a single
retry prompt (fail-fast would waste retry attempts on incomplete feedback).

```
Card JSON (from LLM)
    |
    v
[1] JSON Schema Validation ........... ~0ms, hard-fail, Pydantic parse
[2] Mana Cost / CMC Consistency ...... ~0ms, hard-fail, arithmetic
[3] Rules Text Grammar ............... ~1ms, mixed, regex patterns
[4] Color Pie Compliance ............. ~2ms, soft-fail, lookup table
[5] Power Level / Balance ............ ~1ms, soft-fail, arithmetic
[6] Text Overflow .................... ~0ms, soft-fail, char counting
[7] Uniqueness ....................... ~5ms, mixed, set-level comparison
    |
    v
Collect all errors -> classify HARD vs SOFT -> decide ACCEPT or RETRY
```

### Failure Classification

- **Hard-fail**: The card is structurally invalid or internally inconsistent. The LLM
  *must* fix these before the card can be accepted. Any hard-fail triggers a retry.
- **Soft-fail**: The card is questionable but not broken. Soft-fails are included in retry
  feedback as suggestions but do not force a retry on their own.
- **Accept threshold**: A card is accepted if it has zero hard-fails. Soft-fails are
  logged on `GenerationAttempt.validation_errors` for human review but do not block
  the card from advancing to `CardStatus.VALIDATED`.

### Error Message Type

```python
class ValidationSeverity(StrEnum):
    HARD = "HARD"
    SOFT = "SOFT"

class ValidationError(BaseModel):
    validator: str          # e.g. "mana_cost_consistency"
    severity: ValidationSeverity
    field: str              # e.g. "cmc", "oracle_text"
    message: str            # Human-readable description
    suggestion: str | None  # Actionable fix for the LLM
```

---

## Validator 1: JSON Schema Validation

### Purpose
Verify that the LLM output parses into a valid `Card` Pydantic model with all required
fields present and correctly typed.

### Input
Raw JSON string (or dict) returned by the LLM.

### Checks Performed

| Check | Example Failure | Severity |
|-------|----------------|----------|
| JSON is parseable | `{name: "Foo"}` (unquoted key) | HARD |
| Required fields present | Missing `name`, `type_line` | HARD |
| Field types correct | `cmc` is a string instead of float | HARD |
| Enum values valid | `rarity: "legendary"` (not a valid Rarity) | HARD |
| List fields are lists | `colors: "W"` instead of `["W"]` | HARD |
| Nested models valid | `mana_cost_parsed` present but missing `raw` | HARD |
| No unknown fields | Extra fields the schema doesn't define | SOFT |

### Error Message Format

```
[HARD] Field 'name' is required but missing. Fix: provide a card name as a string.
[HARD] Field 'cmc' has type str, expected float. Fix: set cmc to a number like 3.0.
[HARD] Field 'rarity' value "legendary" is not valid. Valid values: common, uncommon, rare, mythic.
[HARD] Field 'colors' must be a list of Color values ["W","U","B","R","G"], got string "W".
```

### Pseudocode

```python
def validate_schema(raw: dict) -> list[ValidationError]:
    errors = []
    try:
        card = Card.model_validate(raw)
    except PydanticValidationError as e:
        for pydantic_err in e.errors():
            field_path = ".".join(str(loc) for loc in pydantic_err["loc"])
            errors.append(ValidationError(
                validator="json_schema",
                severity=ValidationSeverity.HARD,
                field=field_path,
                message=pydantic_err["msg"],
                suggestion=_suggest_fix_for_type_error(pydantic_err),
            ))
    return errors

def _suggest_fix_for_type_error(err: dict) -> str:
    """Generate an actionable fix suggestion from a Pydantic error."""
    if err["type"] == "missing":
        return f"Provide a value for '{err['loc'][-1]}'."
    if err["type"] == "string_type":
        return f"Set '{err['loc'][-1]}' to a string value."
    if err["type"] == "float_type":
        return f"Set '{err['loc'][-1]}' to a number like 3.0."
    if err["type"] == "enum":
        # Extract valid values from the error context
        return f"Use one of the valid enum values."
    return "Check the field type and format."
```

---

## Validator 2: Mana Cost / CMC Consistency

### Purpose
Verify internal consistency between `mana_cost`, `cmc`, `colors`, `color_identity`,
and `mana_cost_parsed` fields. These fields are redundant by design (matching Scryfall),
so they must agree.

### Input
Parsed `Card` model (validator 1 must pass first, but we still run this even if
validator 1 failed -- we just skip if the Card couldn't be parsed at all).

### Checks Performed

| Check | Example Failure | Severity |
|-------|----------------|----------|
| `mana_cost` format is valid | `{2WW}` instead of `{2}{W}{W}` | HARD |
| Mana symbols are recognized | `{P}` is not a valid mana symbol | HARD |
| `cmc` matches computed CMC from `mana_cost` | `mana_cost="{2}{W}{W}"` but `cmc=3.0` (should be 4.0) | HARD |
| `colors` matches colors in `mana_cost` | `mana_cost="{1}{R}{G}"` but `colors=["R"]` (missing G) | HARD |
| `color_identity` includes `mana_cost` colors | `mana_cost="{W}"` but `color_identity=[]` | HARD |
| `color_identity` includes oracle_text mana refs | Oracle has `{B}` activation cost but `color_identity` lacks B | HARD |
| Mana cost symbol ordering follows WUBRG | `{R}{W}` should be `{W}{R}` | SOFT |
| Land cards have no mana_cost | Land with `mana_cost="{0}"` | SOFT |
| `mana_cost_parsed` agrees with `mana_cost` | Parsed says 2 white but raw says `{W}` | HARD |
| X spells have `x_count > 0` in parsed | `{X}{R}` but `x_count=0` | HARD |

### Valid Mana Symbols

```
{W}  {U}  {B}  {R}  {G}    -- colored mana
{C}                         -- colorless mana (Eldrazi style)
{X}                         -- variable mana
{0} {1} {2} ... {20}        -- generic mana (numeric)
{W/U} {W/B} {U/B} {U/R}    -- hybrid mana (future support)
  {B/R} {B/G} {R/G} {R/W}
  {G/W} {G/U}
{W/P} {U/P} {B/P} {R/P} {G/P}  -- Phyrexian mana (future support)
{T}                         -- tap symbol (not in mana_cost, but in oracle_text)
{Q}                         -- untap symbol (not in mana_cost, but in oracle_text)
```

### CMC Calculation Rules

```
{N}  -> N           (generic)
{W}  -> 1           (each colored symbol = 1)
{U}  -> 1
{B}  -> 1
{R}  -> 1
{G}  -> 1
{C}  -> 1           (colorless = 1)
{X}  -> 0           (X counts as 0 for CMC on the card)
{W/U}-> 1           (hybrid = 1)
{W/P}-> 1           (Phyrexian = 1)
```

### Error Message Format

```
[HARD] Mana cost "{2}{W}{W}" has CMC 4.0 but cmc field says 3.0. Fix: set cmc to 4.0.
[HARD] Mana cost "{1}{R}{G}" contains colors [R, G] but colors field is ["R"]. Fix: set colors to ["R", "G"].
[HARD] Mana cost "{2WW}" is malformed. Each symbol must be wrapped: "{2}{W}{W}".
[HARD] Oracle text contains "{B}" but color_identity is ["W"]. Fix: add "B" to color_identity.
[SOFT] Mana cost "{R}{W}" should follow WUBRG order: "{W}{R}".
```

### Pseudocode

```python
MANA_SYMBOL_PATTERN = re.compile(r"\{(\d+|[WUBRGCX](?:/[WUBRGP])?)\}")
WUBRG_ORDER = {"W": 0, "U": 1, "B": 2, "R": 3, "G": 4}
COLOR_SYMBOLS = {"W", "U", "B", "R", "G"}

def validate_mana_consistency(card: Card) -> list[ValidationError]:
    errors = []

    # --- Check mana_cost format ---
    if card.mana_cost is not None:
        # Verify all characters are part of valid {X} groups
        stripped = MANA_SYMBOL_PATTERN.sub("", card.mana_cost)
        if stripped.strip():
            errors.append(hard("mana_cost", f'Mana cost "{card.mana_cost}" contains '
                f'invalid characters: "{stripped}". Each symbol must be wrapped in '
                f'braces: {{2}}{{W}}{{W}}.'))

        # Parse symbols
        symbols = MANA_SYMBOL_PATTERN.findall(card.mana_cost)
        computed_cmc = 0.0
        computed_colors = set()
        generic_total = 0
        x_count = 0

        for sym in symbols:
            if sym.isdigit():
                computed_cmc += int(sym)
                generic_total += int(sym)
            elif sym == "X":
                x_count += 1
                # X contributes 0 to CMC on the card
            elif sym in COLOR_SYMBOLS:
                computed_cmc += 1
                computed_colors.add(sym)
            elif sym == "C":
                computed_cmc += 1
            elif "/" in sym:
                # Hybrid or Phyrexian: contributes 1 to CMC
                computed_cmc += 1
                parts = sym.split("/")
                for p in parts:
                    if p in COLOR_SYMBOLS:
                        computed_colors.add(p)

        # --- Check CMC ---
        if abs(card.cmc - computed_cmc) > 0.01:
            errors.append(hard("cmc",
                f'Mana cost "{card.mana_cost}" has CMC {computed_cmc} but cmc field '
                f'says {card.cmc}. Fix: set cmc to {computed_cmc}.'))

        # --- Check colors ---
        card_colors = set(c.value for c in card.colors)
        if card_colors != computed_colors:
            expected = sorted(computed_colors, key=lambda c: WUBRG_ORDER.get(c, 99))
            errors.append(hard("colors",
                f'Mana cost "{card.mana_cost}" contains colors {sorted(computed_colors)} '
                f'but colors field is {sorted(card_colors)}. Fix: set colors to '
                f'{expected}.'))

        # --- Check color_identity includes mana_cost colors ---
        ci = set(c.value for c in card.color_identity)
        if not computed_colors.issubset(ci):
            missing = computed_colors - ci
            errors.append(hard("color_identity",
                f'Color identity {sorted(ci)} is missing colors {sorted(missing)} '
                f'from mana cost. Fix: add {sorted(missing)} to color_identity.'))

        # --- Check WUBRG ordering ---
        color_syms = [s for s in symbols if s in COLOR_SYMBOLS]
        if color_syms:
            indices = [WUBRG_ORDER[s] for s in color_syms]
            if indices != sorted(indices):
                correct_order = sorted(color_syms, key=lambda c: WUBRG_ORDER[c])
                correct_cost = (
                    "".join(f"{{{s}}}" for s in symbols if s not in COLOR_SYMBOLS)
                    + "".join(f"{{{s}}}" for s in correct_order)
                )
                errors.append(soft("mana_cost",
                    f'Mana cost symbols should follow WUBRG order. '
                    f'Suggested: "{correct_cost}".'))

        # --- Check mana_cost_parsed consistency ---
        if card.mana_cost_parsed:
            p = card.mana_cost_parsed
            if p.raw != card.mana_cost:
                errors.append(hard("mana_cost_parsed.raw",
                    f'mana_cost_parsed.raw "{p.raw}" does not match '
                    f'mana_cost "{card.mana_cost}". Fix: they must be identical.'))
            if abs(p.cmc - computed_cmc) > 0.01:
                errors.append(hard("mana_cost_parsed.cmc",
                    f'mana_cost_parsed.cmc is {p.cmc} but computed CMC is '
                    f'{computed_cmc}. Fix: set to {computed_cmc}.'))
            if x_count > 0 and p.x_count != x_count:
                errors.append(hard("mana_cost_parsed.x_count",
                    f'Mana cost has {x_count} X symbol(s) but x_count is '
                    f'{p.x_count}. Fix: set x_count to {x_count}.'))

    # --- Check color_identity includes oracle_text mana refs ---
    if card.oracle_text:
        oracle_colors = set(MANA_SYMBOL_PATTERN.findall(card.oracle_text))
        oracle_colors = {c for c in oracle_colors if c in COLOR_SYMBOLS}
        ci = set(c.value for c in card.color_identity)
        if not oracle_colors.issubset(ci):
            missing = oracle_colors - ci
            errors.append(hard("color_identity",
                f'Oracle text references mana symbols {sorted(missing)} not in '
                f'color_identity {sorted(ci)}. Fix: add {sorted(missing)} to '
                f'color_identity.'))

    # --- Land checks ---
    if "Land" in card.card_types:
        if card.mana_cost and card.mana_cost not in ("", "{0}"):
            errors.append(soft("mana_cost",
                f'Land cards typically have no mana cost, but this card has '
                f'"{card.mana_cost}". Remove mana_cost or set to null.'))

    return errors
```

---

## Validator 3: Rules Text Grammar

### Purpose
Check that `oracle_text` follows MTG rules text conventions: correct self-reference,
valid keyword spelling, proper ability structure, and valid mana symbols within text.

### Input
Parsed `Card` model.

### Checks Performed

| Check | Example Failure | Severity | Rationale |
|-------|----------------|----------|-----------|
| Self-reference uses `~` not card name | `"When Serra Angel enters"` instead of `"When ~ enters"` | HARD | LLMs frequently use the card's name instead of `~` |
| No "this creature" / "this card" / "this permanent" | `"this creature gets +1/+1"` | HARD | MTG uses `~` or `it` (after initial reference) |
| Keywords are spelled correctly | `"First Strike"` (wrong casing) or `"Deathtough"` | HARD | Misspelled keywords are not real abilities |
| Triggered abilities start with When/Whenever/At | `"If ~ attacks, draw a card"` | SOFT | Some edge cases use "if" legitimately |
| Activated abilities follow `{cost}: {effect}` | `"Pay 2: Draw a card"` instead of `"{2}: Draw a card"` | HARD | Costs must use mana symbols |
| Mana symbols in text are valid | `{M}` or `{2W}` | HARD | Must use `{W}`, `{2}{W}` etc. |
| Loyalty abilities on planeswalkers follow `[+N]:` / `[-N]:` | `"+1 - Draw a card"` | HARD | Must be `+1: Draw a card.` |
| Sentences end with periods | `"Draw two cards"` (missing period) | SOFT | MTG text always ends sentences with `.` |
| Keyword list abilities are comma-separated on one line | Flying on one line, Trample on next (fine), but `"Flying Trample"` on same line without comma | SOFT | Correct: `"Flying, trample"` |
| No reminder text in oracle_text (should be in reminder_text field) | `"Flying (This creature can't be blocked...)"` | SOFT | Reminder text goes in its own field |

### Evergreen Keyword List

```python
EVERGREEN_KEYWORDS = {
    # Single-word
    "deathtouch", "defender", "double strike", "enchant", "equip",
    "first strike", "flash", "flying", "haste", "hexproof",
    "indestructible", "lifelink", "menace", "reach", "trample",
    "vigilance",
    # Parameterized (keyword {param})
    "ward",          # Ward {N} or Ward -- {cost}
    "protection",    # Protection from {quality}
    "landwalk",      # e.g., "Forestwalk" -- checked by suffix
}

# Keyword actions (appear in ability text, not as standalone)
KEYWORD_ACTIONS = {
    "attach", "cast", "counter", "create", "destroy", "discard",
    "exchange", "exile", "fight", "mill", "play", "reveal",
    "sacrifice", "scry", "search", "shuffle", "tap", "untap",
    "activate", "adapt", "amass", "bolster", "connive",
    "conjure", "discover", "explore", "investigate", "manifest",
    "proliferate", "surveil", "transform", "venture",
}
```

### Error Message Format

```
[HARD] Oracle text uses card name "Serra Angel" on line 1. Fix: replace "Serra Angel" with "~".
[HARD] Oracle text uses "this creature" on line 2. Fix: replace with "~".
[HARD] Keyword "Deathtough" is not a recognized MTG keyword. Did you mean "Deathtouch"?
[HARD] Activated ability "Pay 2: Draw a card" uses informal cost. Fix: "{2}: Draw a card."
[HARD] Mana symbol "{2W}" is malformed. Fix: use "{2}{W}".
[SOFT] Oracle text line 3 does not end with a period. MTG rules text sentences end with ".".
[SOFT] Triggered ability "If ~ attacks" uses "If" instead of "When/Whenever". Consider: "Whenever ~ attacks".
```

### Pseudocode

```python
SELF_REF_BAD = re.compile(r"\bthis (creature|card|permanent|enchantment|artifact|planeswalker)\b", re.I)
MANA_SYM_VALID = re.compile(r"\{(\d+|[WUBRGCXSTQ](?:/[WUBRGP])?)\}")
MANA_SYM_ANY = re.compile(r"\{[^}]+\}")
ACTIVATED_ABILITY = re.compile(r"^(.+): (.+)\.$", re.MULTILINE)
TRIGGERED_START = re.compile(r"^(When|Whenever|At)\b", re.I)
LOYALTY_ABILITY = re.compile(r"^[+\-−]?\d+: .+\.$", re.MULTILINE)
KEYWORD_LINE = re.compile(r"^[A-Z][a-z]+(?:,\s*[a-z][a-z ]+)*$")

def validate_rules_text(card: Card) -> list[ValidationError]:
    errors = []
    text = card.oracle_text
    if not text:
        return errors  # Vanilla creatures / lands have no oracle text

    lines = text.split("\n")

    # --- Self-reference: card name used instead of ~ ---
    if card.name in text:
        errors.append(hard("oracle_text",
            f'Oracle text uses card name "{card.name}". '
            f'Fix: replace "{card.name}" with "~".'))

    # --- "this creature/card/permanent" ---
    for match in SELF_REF_BAD.finditer(text):
        line_num = text[:match.start()].count("\n") + 1
        errors.append(hard("oracle_text",
            f'Oracle text uses "{match.group()}" on line {line_num}. '
            f'Fix: replace with "~".'))

    # --- Keyword spelling ---
    for line in lines:
        # Check if line is a keyword-only line (e.g., "Flying" or "Flying, menace")
        words = [w.strip().lower() for w in line.split(",")]
        for word in words:
            # Strip parameterized part: "Ward {2}" -> "ward"
            base = word.split("{")[0].split("from")[0].strip()
            if base and base[0].isupper() == False and _looks_like_keyword(base):
                if base not in EVERGREEN_KEYWORDS:
                    closest = _closest_keyword(base, EVERGREEN_KEYWORDS)
                    if closest and _edit_distance(base, closest) <= 2:
                        errors.append(hard("oracle_text",
                            f'Keyword "{word}" is not recognized. '
                            f'Did you mean "{closest}"?'))

    # --- Mana symbols in text ---
    for match in MANA_SYM_ANY.finditer(text):
        sym = match.group()
        if not MANA_SYM_VALID.fullmatch(sym):
            errors.append(hard("oracle_text",
                f'Mana symbol "{sym}" is malformed. Valid symbols: '
                f'{{W}}, {{U}}, {{B}}, {{R}}, {{G}}, {{C}}, {{X}}, '
                f'{{T}}, {{Q}}, or {{N}} for generic.'))

    # --- Activated abilities: cost must use mana symbols, not words ---
    for line in lines:
        if ": " in line and not TRIGGERED_START.match(line):
            cost_part = line.split(": ", 1)[0]
            # If cost mentions "pay" or uses plain numbers, it's informal
            if re.search(r"\bpay\s+\d+\b", cost_part, re.I):
                errors.append(hard("oracle_text",
                    f'Activated ability "{line}" uses informal cost. '
                    f'Fix: use mana symbols like "{{2}}: Draw a card."'))

    # --- Planeswalker loyalty abilities ---
    if "Planeswalker" in card.type_line:
        for line in lines:
            if line and (line[0] in "+-−" or line[0].isdigit()):
                if not LOYALTY_ABILITY.match(line):
                    errors.append(hard("oracle_text",
                        f'Loyalty ability "{line}" is malformed. '
                        f'Fix: format as "+N: Effect." or "−N: Effect."'))

    # --- Lines ending with periods ---
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        # Skip keyword-only lines (e.g. "Flying") -- they don't need periods
        if _is_keyword_only_line(stripped):
            continue
        if not stripped.endswith(".") and not stripped.endswith('"'):
            errors.append(soft("oracle_text",
                f'Line {i + 1} ("{stripped}") does not end with a period.'))

    # --- Reminder text in oracle_text ---
    if "(" in text and ")" in text:
        errors.append(soft("oracle_text",
            'Oracle text appears to contain reminder text in parentheses. '
            'Move reminder text to the reminder_text field.'))

    return errors

def _is_keyword_only_line(line: str) -> bool:
    """Check if a line is just keyword abilities (e.g., 'Flying, menace')."""
    words = [w.strip().lower() for w in line.rstrip(".").split(",")]
    return all(
        w.split("{")[0].split("from")[0].strip() in EVERGREEN_KEYWORDS
        for w in words if w.strip()
    )

def _looks_like_keyword(word: str) -> bool:
    """Heuristic: is this word at the start of a line and looks like it's trying
    to be a keyword? (Single or two words, no punctuation except commas.)"""
    return bool(re.match(r"^[a-z]+(?: [a-z]+)?$", word))

def _closest_keyword(word: str, keywords: set[str]) -> str | None:
    """Find the closest keyword by edit distance."""
    best = None
    best_dist = float("inf")
    for kw in keywords:
        d = _edit_distance(word, kw)
        if d < best_dist:
            best_dist = d
            best = kw
    return best if best_dist <= 3 else None

def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance."""
    # Standard DP implementation (omitted for brevity)
    ...
```

---

## Validator 4: Color Pie Compliance

### Purpose
Check that a card's abilities are consistent with what its colors are allowed to do in
MTG's color pie. This is a soft-fail validator -- color pie "bends" and "breaks" exist
in real MTG, so flagging is appropriate but auto-rejection is not.

### Input
Parsed `Card` model.

### Checks Performed

The validator scans `oracle_text` for ability patterns and maps them to allowed colors.
If the card's colors do not include any of the allowed colors for an ability, it flags
a soft-fail.

### Color Pie Ability Map

```python
COLOR_PIE_MAP: dict[str, dict] = {
    # --- Removal ---
    "direct_damage": {
        "patterns": [r"deals? \d+ damage to", r"~ deals damage equal to"],
        "primary": ["R"],
        "secondary": ["B"],  # B can damage creatures, rarely players
        "notes": "B damage usually targets creatures only",
    },
    "destroy_creature": {
        "patterns": [r"destroy target creature", r"destroy all creatures"],
        "primary": ["B"],
        "secondary": ["W"],  # W usually conditional or exile-based
        "notes": "W destruction is usually conditional ('nonblack', 'power 4+')",
    },
    "exile_creature": {
        "patterns": [r"exile target creature", r"exile target (nonland )?permanent"],
        "primary": ["W"],
        "secondary": [],
    },
    "counterspell": {
        "patterns": [r"counter target spell", r"counter target .+ spell"],
        "primary": ["U"],
        "secondary": [],
        "notes": "Counterspells are almost exclusively blue",
    },
    "bounce": {
        "patterns": [r"return target .+ to .+ hand", r"return .+ to their owners?'? hands?"],
        "primary": ["U"],
        "secondary": ["W"],  # W can bounce own permanents
    },

    # --- Card Advantage ---
    "card_draw": {
        "patterns": [r"draw (?:a|two|three|\d+) cards?", r"draws? (?:a|two|three|\d+) cards?"],
        "primary": ["U"],
        "secondary": ["B", "G"],
        "notes": "B draws with life payment; G draws based on creatures/power",
    },
    "tutor": {
        "patterns": [r"search your library for"],
        "primary": ["B"],
        "secondary": ["W", "G"],  # W tutors enchantments/small creatures; G tutors lands/creatures
    },

    # --- Mana & Resources ---
    "mana_ramp": {
        "patterns": [r"add \{[WUBRGC]\}", r"search your library for .+ land",
                     r"put .+ land .+ onto the battlefield"],
        "primary": ["G"],
        "secondary": [],
    },
    "artifact_ramp": {
        "patterns": [r"\{T\}: Add \{C\}", r"\{T\}: Add one mana of any"],
        "primary": [],  # Colorless artifacts are fine in any color
        "secondary": [],
        "notes": "Artifact mana is color-neutral",
    },

    # --- Life Manipulation ---
    "lifegain": {
        "patterns": [r"gains? \d+ life", r"you gain .+ life"],
        "primary": ["W"],
        "secondary": ["B", "G"],
        "notes": "B gains life paired with opponent losing life (drain)",
    },
    "life_drain": {
        "patterns": [r"loses? \d+ life", r"each opponent loses"],
        "primary": ["B"],
        "secondary": [],
    },

    # --- Combat Keywords ---
    "flying": {
        "patterns": [r"^Flying$", r"\bflying\b"],
        "primary": ["W", "U"],
        "secondary": ["B"],
        "notes": "B gets flying on some creatures (vampires, demons)",
    },
    "first_strike": {
        "patterns": [r"\bfirst strike\b", r"\bdouble strike\b"],
        "primary": ["W", "R"],
        "secondary": [],
    },
    "trample": {
        "patterns": [r"\btrample\b"],
        "primary": ["G"],
        "secondary": ["R"],
    },
    "deathtouch": {
        "patterns": [r"\bdeathtouch\b"],
        "primary": ["B", "G"],
        "secondary": [],
    },
    "haste": {
        "patterns": [r"\bhaste\b"],
        "primary": ["R"],
        "secondary": ["B", "G"],
    },
    "vigilance": {
        "patterns": [r"\bvigilance\b"],
        "primary": ["W", "G"],
        "secondary": [],
    },
    "lifelink": {
        "patterns": [r"\blifelink\b"],
        "primary": ["W", "B"],
        "secondary": [],
    },
    "menace": {
        "patterns": [r"\bmenace\b"],
        "primary": ["B", "R"],
        "secondary": [],
    },
    "reach": {
        "patterns": [r"\breach\b"],
        "primary": ["G"],
        "secondary": ["W", "R"],
    },
    "hexproof": {
        "patterns": [r"\bhexproof\b"],
        "primary": ["U", "G"],
        "secondary": [],
    },
    "indestructible": {
        "patterns": [r"\bindestructible\b"],
        "primary": ["W"],
        "secondary": [],
    },

    # --- Enchantment / Artifact Interaction ---
    "enchantment_removal": {
        "patterns": [r"destroy target .*(enchantment|artifact)",
                     r"exile target .*(enchantment|artifact)"],
        "primary": ["W", "G"],
        "secondary": [],
    },
    "artifact_removal": {
        "patterns": [r"destroy target artifact"],
        "primary": ["W", "G", "R"],
        "secondary": [],
    },

    # --- Graveyard ---
    "reanimation": {
        "patterns": [r"return .+ from .+ graveyard to the battlefield"],
        "primary": ["B"],
        "secondary": ["W"],  # W reanimates small creatures (CMC 3 or less)
    },

    # --- Tokens ---
    "token_creation": {
        "patterns": [r"create .+ \d+/\d+ .+ creature token"],
        "primary": ["W", "G"],
        "secondary": ["R", "B", "U"],
        "notes": "All colors make tokens; W/G are primary",
    },

    # --- Pump ---
    "pump_spell": {
        "patterns": [r"gets? \+\d+/\+\d+ until end of turn"],
        "primary": ["G", "W"],
        "secondary": ["R", "B"],
        "notes": "R pump often gives +N/+0; B pump often has a downside or -N/-N on opponents",
    },
}
```

### Error Message Format

```
[SOFT] Card is Green but has "counter target spell" which is a Blue-only ability (counterspell).
       This would be a major color pie break. Consider removing or changing the card's color.
[SOFT] Card is Red but has "draw two cards" which is primarily Blue (card_draw).
       Red card draw is usually impulsive ("exile the top card, you may play it this turn").
```

### Pseudocode

```python
def validate_color_pie(card: Card) -> list[ValidationError]:
    errors = []
    if not card.oracle_text:
        return errors

    card_colors = set(c.value for c in card.colors)

    # Colorless/artifact cards get a pass on most color pie checks
    if not card_colors and "Artifact" in card.card_types:
        return errors

    for ability_name, ability_info in COLOR_PIE_MAP.items():
        for pattern in ability_info["patterns"]:
            if re.search(pattern, card.oracle_text, re.I | re.MULTILINE):
                allowed = set(ability_info["primary"] + ability_info.get("secondary", []))
                if allowed and not card_colors.intersection(allowed):
                    primary_str = ", ".join(ability_info["primary"])
                    errors.append(soft("oracle_text",
                        f'Card is {"/".join(sorted(card_colors)) or "colorless"} but has '
                        f'"{ability_name}" ability which is primarily {primary_str}. '
                        f'{ability_info.get("notes", "")}'))
                break  # Only report once per ability category

    return errors
```

---

## Validator 5: Power Level / Balance

### Purpose
Check that a card's stats and abilities are reasonable for its rarity and CMC. Uses
heuristic guidelines, not absolute rules -- real MTG has exceptions.

### Input
Parsed `Card` model.

### Checks Performed

| Check | Guideline | Severity |
|-------|-----------|----------|
| Creature P+T vs CMC (common) | P+T <= CMC + 2 (vanilla), P+T <= CMC + 1 (with abilities) | SOFT |
| Creature P+T vs CMC (uncommon) | P+T <= CMC + 3, or CMC + 2 with strong abilities | SOFT |
| Creature P+T vs CMC (rare/mythic) | P+T <= CMC + 4 (flexible for rarity) | SOFT |
| Common NWO complexity | Max 1 keyword ability, no complex interactions | SOFT |
| Uncommon ability density | Max 2-3 abilities | SOFT |
| Removal spell efficiency | CMC 1 unconditional removal is too strong below mythic | SOFT |
| Planeswalker starting loyalty vs CMC | Loyalty should roughly equal CMC (+/- 1) | SOFT |
| Zero CMC nonland card | Cards with CMC 0 are unusual; flag for review | SOFT |
| Negative power/toughness creatures | P or T < 0 is extremely rare | SOFT |

### Creature P+T Guidelines

```
Rarity    | Vanilla (no abilities)  | With abilities         | With downside
----------|------------------------|------------------------|------------------
Common    | P+T <= CMC + 3         | P+T <= CMC + 2         | P+T <= CMC + 4
Uncommon  | P+T <= CMC + 4         | P+T <= CMC + 3         | P+T <= CMC + 5
Rare      | P+T <= CMC + 5         | P+T <= CMC + 4         | flexible
Mythic    | flexible               | flexible               | flexible
```

A "downside" is detected by patterns like: "can't block", "enters tapped",
"sacrifice", "you lose life", "defender".

### NWO (New World Order) Complexity for Commons

NWO guidelines for common cards:
- Maximum 1 keyword ability
- No abilities that reference other specific cards
- No abilities that create complex board states (e.g., "whenever any creature dies")
- No modal abilities (choose one)
- Avoid triggered abilities that trigger on opponents' actions

```python
NWO_VIOLATION_PATTERNS = [
    (r"choose (?:one|two)", "Modal abilities are too complex for common"),
    (r"whenever (?:a|an|another) creature dies", "Global death triggers are too complex for common"),
    (r"whenever (?:a|an) (?:creature|permanent) enters", "Global ETB triggers are too complex for common"),
    (r"for each", "Counting effects are too complex for common"),
    (r"search your library", "Tutoring is too complex for common"),
]
```

### Error Message Format

```
[SOFT] Power 4 + Toughness 4 = 8 on a CMC 3 common creature exceeds P+T <= CMC+2 guideline
       for commons with abilities. Consider reducing stats or increasing CMC.
[SOFT] Common creature has 3 keyword abilities (flying, lifelink, vigilance). NWO guideline
       recommends at most 1 for commons. Consider moving to uncommon.
[SOFT] CMC 1 "Destroy target creature" removal spell is very aggressive. Typical efficient
       removal is CMC 2+ or has restrictions.
```

### Pseudocode

```python
DOWNSIDE_PATTERNS = [
    r"\bcan't block\b", r"\bdefender\b", r"\benters .+ tapped\b",
    r"\bsacrifice ~\b", r"\byou lose \d+ life\b", r"\b~ doesn't untap\b",
]

def validate_power_level(card: Card) -> list[ValidationError]:
    errors = []

    # --- Creature P+T check ---
    if "Creature" in card.card_types and card.power is not None and card.toughness is not None:
        try:
            p = int(card.power)
            t = int(card.toughness)
        except ValueError:
            # Variable P/T like "*" -- skip this check
            p = None
            t = None

        if p is not None and t is not None:
            pt_sum = p + t
            cmc = card.cmc
            has_abilities = bool(card.oracle_text and card.oracle_text.strip())
            has_downside = any(
                re.search(pat, card.oracle_text or "", re.I)
                for pat in DOWNSIDE_PATTERNS
            )

            # Determine threshold based on rarity and ability presence
            if card.rarity == Rarity.COMMON:
                if has_downside:
                    threshold = cmc + 4
                elif has_abilities:
                    threshold = cmc + 2
                else:
                    threshold = cmc + 3
            elif card.rarity == Rarity.UNCOMMON:
                if has_downside:
                    threshold = cmc + 5
                elif has_abilities:
                    threshold = cmc + 3
                else:
                    threshold = cmc + 4
            elif card.rarity == Rarity.RARE:
                threshold = cmc + 5 if has_abilities else cmc + 5
            else:  # Mythic
                threshold = float("inf")  # No limit for mythics

            if pt_sum > threshold:
                errors.append(soft("power",
                    f'Power {p} + Toughness {t} = {pt_sum} on a CMC {cmc} '
                    f'{card.rarity.value} creature exceeds P+T <= CMC+{int(threshold - cmc)} '
                    f'guideline. Consider reducing stats or increasing CMC.'))

            # Negative P/T check
            if p < 0 or t < 0:
                errors.append(soft("power",
                    f'Power {p} / Toughness {t} includes a negative value, which is '
                    f'extremely rare in MTG. Verify this is intentional.'))

    # --- NWO complexity for commons ---
    if card.rarity == Rarity.COMMON and card.oracle_text:
        # Count keyword abilities
        keyword_count = sum(
            1 for kw in EVERGREEN_KEYWORDS
            if re.search(r"\b" + re.escape(kw) + r"\b", card.oracle_text, re.I)
        )
        if keyword_count > 1:
            errors.append(soft("oracle_text",
                f'Common card has {keyword_count} keyword abilities. NWO guideline '
                f'recommends at most 1 for commons. Consider moving to uncommon.'))

        # Check NWO violation patterns
        for pattern, reason in NWO_VIOLATION_PATTERNS:
            if re.search(pattern, card.oracle_text, re.I):
                errors.append(soft("oracle_text",
                    f'Common card has complexity issue: {reason}. '
                    f'Consider moving to uncommon or simplifying.'))

    # --- Removal efficiency ---
    if card.cmc <= 1 and card.oracle_text:
        if re.search(r"destroy target creature", card.oracle_text, re.I):
            if card.rarity in (Rarity.COMMON, Rarity.UNCOMMON):
                errors.append(soft("oracle_text",
                    f'CMC {card.cmc} unconditional creature removal is very pushed '
                    f'at {card.rarity.value}. Consider adding a restriction or '
                    f'increasing CMC.'))

    # --- Planeswalker loyalty ---
    if "Planeswalker" in card.card_types and card.loyalty is not None:
        try:
            loyalty = int(card.loyalty)
            if abs(loyalty - card.cmc) > 2:
                errors.append(soft("loyalty",
                    f'Planeswalker starting loyalty {loyalty} is far from CMC '
                    f'{card.cmc}. Typical loyalty is roughly CMC +/- 1.'))
        except ValueError:
            pass  # Variable loyalty -- skip

    # --- Zero CMC nonland ---
    if card.cmc == 0 and "Land" not in card.card_types:
        if card.mana_cost and card.mana_cost != "{0}":
            pass  # Already caught by mana consistency validator
        else:
            errors.append(soft("cmc",
                f'CMC 0 nonland cards are unusual. Verify this is intentional.'))

    return errors
```

---

## Validator 6: Text Overflow

### Purpose
Estimate whether the card's text will fit on a physical card. Uses character count
heuristics calibrated against real MTG cards. Exact fit is verified later against actual
renders in Phase 2C; this validator catches gross violations early.

### Input
Parsed `Card` model.

### Checks Performed

| Field | Max Characters | Notes | Severity |
|-------|---------------|-------|----------|
| `name` | 30 | Longest real MTG names are ~35 chars | SOFT |
| `type_line` | 45 | "Legendary Artifact Creature -- Human Soldier" is 45 | SOFT |
| `oracle_text` (noncreature) | 400 | Standard frame, no P/T box | SOFT |
| `oracle_text` (creature) | 300 | P/T box eats space | SOFT |
| `oracle_text` (planeswalker) | 350 | Loyalty box layout | SOFT |
| `flavor_text` | 200 | Below oracle text | SOFT |
| `oracle_text` + `flavor_text` combined | 450 (noncreature) / 350 (creature) | Total text box | SOFT |

### Error Message Format

```
[SOFT] Oracle text is 412 characters, exceeding the ~300 char guideline for creatures.
       The card may have text overflow when rendered. Consider shortening.
[SOFT] Card name "The Extremely Long and Verbose Card Name" is 42 characters.
       Names over 30 chars may not fit. Consider shortening.
```

### Pseudocode

```python
def validate_text_overflow(card: Card) -> list[ValidationError]:
    errors = []
    is_creature = "Creature" in card.card_types
    is_planeswalker = "Planeswalker" in card.card_types

    # --- Card name length ---
    if len(card.name) > 30:
        errors.append(soft("name",
            f'Card name "{card.name}" is {len(card.name)} characters. '
            f'Names over 30 chars may not fit on the card. Consider shortening.'))

    # --- Type line length ---
    if len(card.type_line) > 45:
        errors.append(soft("type_line",
            f'Type line "{card.type_line}" is {len(card.type_line)} characters. '
            f'Type lines over 45 chars may not fit. Consider shortening.'))

    # --- Oracle text length ---
    oracle_len = len(card.oracle_text) if card.oracle_text else 0
    if is_creature:
        oracle_limit = 300
    elif is_planeswalker:
        oracle_limit = 350
    else:
        oracle_limit = 400

    if oracle_len > oracle_limit:
        errors.append(soft("oracle_text",
            f'Oracle text is {oracle_len} characters, exceeding the ~{oracle_limit} '
            f'char guideline for {"creatures" if is_creature else "this card type"}. '
            f'The card may have text overflow when rendered. Consider shortening.'))

    # --- Flavor text length ---
    flavor_len = len(card.flavor_text) if card.flavor_text else 0
    if flavor_len > 200:
        errors.append(soft("flavor_text",
            f'Flavor text is {flavor_len} characters, exceeding the ~200 char '
            f'guideline. Consider shortening.'))

    # --- Combined text box ---
    combined = oracle_len + flavor_len
    combined_limit = 350 if is_creature else 450
    if combined > combined_limit and oracle_len <= oracle_limit and flavor_len <= 200:
        # Only flag combined overflow if individual checks passed
        errors.append(soft("oracle_text",
            f'Combined oracle ({oracle_len}) + flavor ({flavor_len}) = {combined} '
            f'characters exceeds the ~{combined_limit} char text box guideline. '
            f'Consider removing or shortening flavor text.'))

    return errors
```

---

## Validator 7: Uniqueness

### Purpose
Ensure the card is unique within the set -- no duplicate names and no near-duplicate
mechanics. Requires access to all previously generated/accepted cards in the set.

### Input
Parsed `Card` model, plus `list[Card]` of all existing cards in the set.

### Checks Performed

| Check | Threshold | Severity |
|-------|-----------|----------|
| Exact name match | name == existing name | HARD |
| Near-duplicate name | Levenshtein distance <= 2 | SOFT |
| Mechanical duplicate | Same CMC, same colors, same type, oracle text similarity > 80% | SOFT |
| Same collector number | collector_number already used | HARD |

### Error Message Format

```
[HARD] Card name "Lightning Bolt" already exists in the set (card #042). Fix: choose a different name.
[SOFT] Card name "Lightening Bolt" is very similar to existing "Lightning Bolt" (#042).
       Consider a more distinct name.
[SOFT] Card is mechanically similar to "Shock" (#015): same color (R), same CMC (1),
       both deal damage to target. Consider differentiating the effect.
[HARD] Collector number "042" is already assigned to "Lightning Bolt". Fix: use a unique number.
```

### Pseudocode

```python
def validate_uniqueness(card: Card, existing_cards: list[Card]) -> list[ValidationError]:
    errors = []

    for existing in existing_cards:
        # --- Exact name match ---
        if card.name.lower() == existing.name.lower():
            errors.append(hard("name",
                f'Card name "{card.name}" already exists in the set '
                f'(card #{existing.collector_number}). Fix: choose a different name.'))

        # --- Near-duplicate name ---
        elif _edit_distance(card.name.lower(), existing.name.lower()) <= 2:
            errors.append(soft("name",
                f'Card name "{card.name}" is very similar to existing '
                f'"{existing.name}" (#{existing.collector_number}). '
                f'Consider a more distinct name.'))

        # --- Mechanical similarity ---
        if (card.cmc == existing.cmc
                and set(card.colors) == set(existing.colors)
                and set(card.card_types) == set(existing.card_types)
                and card.oracle_text and existing.oracle_text):
            similarity = _text_similarity(card.oracle_text, existing.oracle_text)
            if similarity > 0.80:
                errors.append(soft("oracle_text",
                    f'Card is mechanically similar to "{existing.name}" '
                    f'(#{existing.collector_number}): same color, same CMC, '
                    f'{similarity:.0%} text similarity. Consider differentiating.'))

    # --- Collector number uniqueness ---
    if card.collector_number:
        for existing in existing_cards:
            if card.collector_number == existing.collector_number:
                errors.append(hard("collector_number",
                    f'Collector number "{card.collector_number}" is already assigned '
                    f'to "{existing.name}". Fix: use a unique collector number.'))
                break

    return errors

def _text_similarity(a: str, b: str) -> float:
    """Normalized similarity using SequenceMatcher or similar."""
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()
```

---

## Retry Feedback Format

When validation fails, errors are formatted into a structured retry prompt that is
appended to the next generation call. The format is designed to be:

1. **Specific** -- tells the LLM exactly what was wrong
2. **Actionable** -- includes a concrete fix suggestion
3. **Prioritized** -- HARD errors are listed first and marked as mandatory
4. **Bounded** -- max 10 error lines to avoid overwhelming the prompt

### Template

```
Your previous card "{card_name}" failed validation with {n_hard} error(s) and {n_soft} suggestion(s):

{errors formatted as below}

Please regenerate the card fixing all [HARD] errors. [SOFT] items are suggestions for improvement.
Do not change the card's assigned slot (color: {color}, rarity: {rarity}, type: {type}).
```

### Error Line Format

```
- [HARD] {message}. Fix: {suggestion}
- [SOFT] {message}. Suggestion: {suggestion}
```

### Full Example

```
Your previous card "Flamewing Drake" failed validation with 2 error(s) and 1 suggestion(s):

- [HARD] Mana cost "{2}{R}{R}" has CMC 4.0 but cmc field says 3.0. Fix: set cmc to 4.0.
- [HARD] Oracle text uses "this creature" on line 2. Fix: replace with "~".
- [SOFT] Power 4 + Toughness 4 = 8 on a CMC 4 common creature exceeds P+T <= CMC+2 guideline.
         Consider reducing stats or increasing CMC.

Please regenerate the card fixing all [HARD] errors. [SOFT] items are suggestions for improvement.
Do not change the card's assigned slot (color: R, rarity: common, type: Creature).
```

### Feedback Builder Pseudocode

```python
MAX_FEEDBACK_ERRORS = 10

def format_validation_feedback(
    card: Card,
    errors: list[ValidationError],
    slot: CardSlot,
) -> str:
    hard_errors = [e for e in errors if e.severity == ValidationSeverity.HARD]
    soft_errors = [e for e in errors if e.severity == ValidationSeverity.SOFT]

    # Prioritize hard errors
    selected = hard_errors[:MAX_FEEDBACK_ERRORS]
    remaining_slots = MAX_FEEDBACK_ERRORS - len(selected)
    if remaining_slots > 0:
        selected += soft_errors[:remaining_slots]

    lines = []
    for err in selected:
        tag = err.severity.value
        fix_label = "Fix" if err.severity == ValidationSeverity.HARD else "Suggestion"
        suggestion = f" {fix_label}: {err.suggestion}" if err.suggestion else ""
        lines.append(f"- [{tag}] {err.message}.{suggestion}")

    header = (
        f'Your previous card "{card.name}" failed validation with '
        f'{len(hard_errors)} error(s) and {len(soft_errors)} suggestion(s):'
    )
    footer = (
        f'Please regenerate the card fixing all [HARD] errors. '
        f'[SOFT] items are suggestions for improvement.\n'
        f'Do not change the card\'s assigned slot '
        f'(color: {slot.color}, rarity: {slot.rarity}, type: {slot.card_type}).'
    )

    return f"{header}\n\n" + "\n".join(lines) + f"\n\n{footer}"
```

---

## Pipeline Orchestration

### Validation Runner

```python
def validate_card(
    card: Card,
    existing_cards: list[Card],
) -> list[ValidationError]:
    """Run all validators in sequence and collect all errors."""
    all_errors: list[ValidationError] = []

    # Always run all validators to give complete feedback
    all_errors += validate_schema(card)          # [1]
    all_errors += validate_mana_consistency(card) # [2]
    all_errors += validate_rules_text(card)       # [3]
    all_errors += validate_color_pie(card)        # [4]
    all_errors += validate_power_level(card)      # [5]
    all_errors += validate_text_overflow(card)     # [6]
    all_errors += validate_uniqueness(card, existing_cards)  # [7]

    return all_errors

def has_hard_failures(errors: list[ValidationError]) -> bool:
    return any(e.severity == ValidationSeverity.HARD for e in errors)
```

Note: Validator 1 (schema validation) is special. If the raw JSON cannot be parsed into
a `Card` at all, validators 2-7 cannot run because they require a `Card` instance.
In that case, only schema errors are returned and the card is retried.

```python
def validate_card_from_raw(
    raw: dict,
    existing_cards: list[Card],
) -> tuple[Card | None, list[ValidationError]]:
    """Top-level validation entry point for raw LLM output."""
    schema_errors = validate_schema_raw(raw)
    if schema_errors:
        # Can't parse into Card -- return schema errors only
        return None, schema_errors

    card = Card.model_validate(raw)
    all_errors = validate_card(card, existing_cards)
    return card, all_errors
```

### Batch Generation with Partial Failures

When generating cards in batches of 5, some may pass validation while others fail.
The pipeline handles this by accepting valid cards immediately and retrying only the
failures.

```python
async def generate_batch_with_retry(
    slots: list[CardSlot],   # 5 slots
    set_context: SetContext,
    existing_cards: list[Card],
    max_retries: int = 3,
) -> list[Card]:
    results: list[Card] = []
    pending_slots = list(slots)
    feedback_map: dict[str, str] = {}  # slot_id -> feedback string

    for attempt in range(1, max_retries + 1):
        if not pending_slots:
            break

        # First attempt: batch mode (5 cards per call)
        # Retries: single-card mode for maximum quality
        if attempt == 1 and len(pending_slots) > 1:
            raw_cards = await llm_generate_batch(pending_slots, set_context, feedback_map)
        else:
            raw_cards = []
            for slot in pending_slots:
                raw = await llm_generate_single(
                    slot, set_context,
                    feedback=feedback_map.get(slot.slot_id),
                )
                raw_cards.append(raw)

        still_pending = []
        for slot, raw in zip(pending_slots, raw_cards):
            card, errors = validate_card_from_raw(raw, existing_cards + results)

            # Record the attempt
            gen_attempt = GenerationAttempt(
                attempt_number=attempt,
                timestamp=datetime.now(),
                model_used=set_context.config.llm_model,
                success=not has_hard_failures(errors),
                validation_errors=[e.message for e in errors],
            )

            if card and not has_hard_failures(errors):
                card.status = CardStatus.VALIDATED
                card.generation_attempts.append(gen_attempt)
                results.append(card)
            else:
                # Build feedback for next attempt
                feedback_map[slot.slot_id] = format_validation_feedback(
                    card or _placeholder_card(slot), errors, slot,
                )
                if card:
                    card.generation_attempts.append(gen_attempt)
                still_pending.append(slot)

        pending_slots = still_pending

    # Any remaining pending slots: flag for human review
    for slot in pending_slots:
        card = _create_draft_card(slot)
        card.status = CardStatus.DRAFT
        card.design_notes = (
            f"Failed validation after {max_retries} attempts. "
            f"Last errors: {feedback_map.get(slot.slot_id, 'unknown')}"
        )
        results.append(card)

    return results
```

### Retry Strategy

| Attempt | Mode | Model | Temperature | Notes |
|---------|------|-------|-------------|-------|
| 1 | Batch (5 cards) | Primary (Sonnet/GPT-4o) | 0.7 | Standard generation |
| 2 | Single card | Primary (Sonnet/GPT-4o) | 0.5 | Focused, with validation feedback |
| 3 | Single card | Primary (Sonnet/GPT-4o) | 0.3 | Even more focused, with accumulated feedback |
| -- | -- | -- | -- | If still failing: flag for human review |

**Escalation path after 3 retries:**
1. Card is saved with `status = CardStatus.DRAFT` and `design_notes` containing the
   last validation errors.
2. Card is added to a human review queue (a simple list in the set manifest).
3. A human can either edit the card manually or tweak the slot spec and re-run.

**Model escalation** (optional, not default): If the primary model consistently fails on
complex cards (mythics, planeswalkers), the retry loop can optionally escalate to a
stronger model (e.g., Opus). This is controlled by config:

```python
# In config
llm_escalation_model: str | None = None  # e.g., "claude-opus-4-20250514"
llm_escalate_after_attempt: int = 2       # Escalate on attempt 3+
```

### When Validators Run

| Validator | Generation Time (Phase 1C) | Render Time (Phase 2C) | Notes |
|-----------|---------------------------|------------------------|-------|
| 1. JSON Schema | Yes | No | Only relevant at generation |
| 2. Mana Cost | Yes | No | Only relevant at generation |
| 3. Rules Text | Yes | No | Only relevant at generation |
| 4. Color Pie | Yes | No | Only relevant at generation |
| 5. Power Level | Yes | No | Only relevant at generation |
| 6. Text Overflow | Yes (heuristic) | Yes (actual render) | Re-checked against real renders |
| 7. Uniqueness | Yes | No | Only relevant at generation |

Validator 6 (Text Overflow) deserves special attention: the character-count heuristic
at generation time catches gross violations (500-char oracle text on a creature), but
the actual fit depends on font metrics, text wrapping, and card frame layout. Phase 2C
renders the card and checks whether text actually fits. If it overflows, the card goes
back to a "text overflow" review queue where either:
- The card text is manually shortened, or
- The renderer adjusts font size (within limits), or
- The card is re-generated with a tighter character budget.

---

## Helper Functions

```python
def hard(field: str, message: str, suggestion: str | None = None) -> ValidationError:
    """Shorthand for creating a hard-fail ValidationError."""
    return ValidationError(
        validator="",  # Filled by caller or decorator
        severity=ValidationSeverity.HARD,
        field=field,
        message=message,
        suggestion=suggestion,
    )

def soft(field: str, message: str, suggestion: str | None = None) -> ValidationError:
    """Shorthand for creating a soft-fail ValidationError."""
    return ValidationError(
        validator="",  # Filled by caller or decorator
        severity=ValidationSeverity.SOFT,
        field=field,
        message=message,
        suggestion=suggestion,
    )
```

---

## Summary

| # | Validator | Hard Checks | Soft Checks | Approx Cost |
|---|-----------|------------|-------------|-------------|
| 1 | JSON Schema | 5+ (missing fields, wrong types, bad enums) | 1 (unknown fields) | ~0ms |
| 2 | Mana Cost / CMC | 7 (format, CMC, colors, identity, parsed) | 2 (WUBRG order, land cost) | ~0ms |
| 3 | Rules Text Grammar | 5 (self-ref, keywords, mana symbols, costs, loyalty) | 3 (periods, keyword format, reminder text) | ~1ms |
| 4 | Color Pie | 0 | Many (one per ability-color mismatch) | ~2ms |
| 5 | Power Level | 0 | 6+ (P/T, NWO, removal, loyalty, zero CMC, negative) | ~1ms |
| 6 | Text Overflow | 0 | 4 (name, type, oracle, flavor, combined) | ~0ms |
| 7 | Uniqueness | 2 (exact name, collector number) | 2 (similar name, mechanical duplicate) | ~5ms |
| **Total** | | **~19 hard checks** | **~18+ soft checks** | **<10ms per card** |

All seven validators complete in under 10ms per card. For a batch of 5, validation
adds negligible overhead compared to the LLM API call (~5-30 seconds). The chain is
designed to give the LLM maximum feedback per retry, minimizing the total number of
retries needed.
