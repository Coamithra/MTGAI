# ASD Art Prompt Templates

## Architecture

Every art prompt is assembled from layers:

```
[STYLE PERSONA PREFIX]  ←  from card colors (style-guide.md §Artist Style Personas)
[UNIVERSAL PREFIX]      ←  shared across all cards
[TYPE-SPECIFIC BODY]    ←  one of the templates below, filled from card data
[RARITY MODIFIER]       ←  scales detail/drama by rarity
[MECHANIC VISUAL]       ←  if card uses Salvage/Malfunction/Overclock
[UNIVERSAL SUFFIX]      ←  shared across all cards
```

The prompt builder reads card JSON fields and selects/fills the appropriate layers.

---

## Universal Prefix

```
Stylized digital fantasy card game illustration. Bold shapes, strong silhouettes,
painterly texture. Post-apocalyptic science-fantasy setting: far-future Earth where
medieval civilization is built atop ancient mega-technology ruins. The sky has a faint
amber-red cast from a dying sun. Deadpan serious tone — bizarre subjects rendered with
complete compositional gravitas, no humor in the rendering.
```

## Universal Suffix

```
No text, no title, no card frame, no border, no watermark, no signature, no logo,
no UI elements. No letters or words anywhere in the image. High detail, clean
composition readable at small size. Strong focal silhouette against background.
Aspect ratio approximately 4:3 landscape.
```

---

## Style Persona Prefixes

Applied based on `card.colors`. For multicolor, use the first listed color as dominant, blend in secondary.

**White (W):**
```
Classical authority composition. Structured, balanced framing with strong vertical
lines. Warm sandstone and ivory tones, golden-hour lighting, long sharp shadows.
Propaganda-poster dignity — subjects centered and imposing.
```

**Blue (U):**
```
Clinical futurism composition. Geometric framing, cool steel-blue and teal palette.
Screen-glow and holographic lighting, reflective surfaces. Flat color with sharp
value contrasts, the most graphic style.
```

**Black (B):**
```
Dark grotesque composition. Heavy shadow covering 60%+ of the frame. Minimal light
sources — torchlight, dying machinery glow. Organic textures, wet surfaces, unsettling
asymmetry. Visible painterly brushwork in shadow areas.
```

**Red (R):**
```
Dynamic action composition. Tilted angles, diagonal lines, implied motion. High
contrast with warm fire-tones — rust orange, furnace red, spark-white. Saturated
and kinetic, everything feels mid-explosion.
```

**Green (G):**
```
Naturalist exploration composition. Wide vista with environmental context, dappled
light through canopy. Rich earth tones — deep emerald, moss, amber-green. Layered
depth with foreground foliage framing. The most painterly and atmospheric style.
```

**Colorless / Artifact:**
```
Technical precision composition. Centered, object-focused against dark neutral
background. Self-illuminated subject with internal glow — protonium gold, circuitry
green. Clean negative space. Archaeological illustration meets product photography.
```

---

## Rarity Modifiers

Appended after the type-specific body.

**Common:**
```
Grounded, everyday composition. Moderate detail. Slice-of-life in a strange world.
```

**Uncommon:**
```
Heightened tension or wonder. More atmospheric detail. Something slightly remarkable
about the scene.
```

**Rare:**
```
Dramatic set-piece. Rich detail, strong atmosphere. A defining moment. More saturated
color, more dramatic lighting than common/uncommon.
```

**Mythic:**
```
Maximum drama, awe, or dread. Cinematic scale and lighting. The subject commands the
entire frame. Hyper-detailed, the most polished rendering in the set.
```

---

## Mechanic Visual Modifiers

Appended if `oracle_text` contains the relevant mechanic keyword.

**Salvage:**
```
Scene includes the moment of discovery — hands reaching into wreckage, a panel pried
open, glowing circuitry revealed. Warm metallic tones (bronze, copper, gold) on the
salvaged element, contrasting with surrounding decay.
```

**Malfunction:**
```
The subject shows signs of unreliable technology — visible sparks, flickering indicator
lights, cracked glass, exposed wiring, status lights glowing amber/red. Powerful but
not fully functional.
```

**Overclock:**
```
The subject is pushed beyond safe limits — glowing cherry-red with heat, steam venting,
containment fields flickering. More saturated and contrasty than normal. Dangerous
exhilaration, briefly magnificent.
```

---

## Type-Specific Templates

### Creature

**Fields used**: `name`, `type_line`, `subtypes`, `oracle_text`, `flavor_text`, `power`, `toughness`, `colors`, `rarity`, `supertypes`

```
A {size_descriptor} {creature_type} {action_pose}.
{physical_description}.
{environment_context}.
The creature is the clear focal point, occupying 60-70% of the frame.
{legendary_modifier}
```

**Size descriptor** derived from power/toughness:
- P/T sum <= 3: "small" (camera slightly above)
- P/T sum 4-6: "medium-sized" (eye-level camera)
- P/T sum 7-9: "large" (camera slightly low, conveys power)
- P/T sum 10+: "massive" (low camera angle looking up, dwarfs surroundings)

**Legendary modifier** (if "Legendary" in supertypes):
```
Legendary character — unique distinguishing features, regal or imposing framing,
more individual detail than a generic creature. This is a named, important figure.
```

**Physical description**: Derived from creature subtypes + oracle_text + flavor_text by the LLM prompt builder. The LLM reads all three and writes a 1-2 sentence visual description.

**Environment context**: Inferred from color identity + flavor_text. Surface (warm, dusty) vs. dungeon (cool, eerie) decided by LLM based on card context.

**Action/pose**: Inferred from oracle_text keywords:
- Combat keywords (first strike, trample, menace) → aggressive action pose
- Defensive keywords (vigilance, lifelink, ward) → alert/guarding stance
- Utility keywords (salvage, ETB triggers) → interacting with environment
- Vanilla (no oracle text) → natural idle pose in environment

#### Example: Denethix Watchguard (W-C-01)
```
[White persona prefix]
[Universal prefix]
A small human soldier standing guard at a sandstone gate.
Practical leather armor with a polished bronze badge, hand resting on a simple
sword. Young face, alert but slightly bored. Ancient mega-structure wall looms
behind, its surface too smooth and regular for medieval stonework.
Warm golden light, dust motes in a shaft of sunlight through the gate arch.
The creature is the clear focal point, occupying 60-70% of the frame.
Grounded, everyday composition. Moderate detail. Slice-of-life in a strange world.
[Universal suffix]
```

#### Example: Feretha, the Hollow Founder (W-M-01)
```
[White persona prefix]
[Universal prefix]
A medium-sized spectral human figure seated on an ancient technological throne.
Translucent, ghostly form with faint golden light emanating from within. Cables
and fluid tubes connect the throne to the figure. The throne is a server rack
repurposed as a seat of power — blinking lights, humming machinery. Eyes open
but empty. A crown that is also a neural interface.
Grand throne room built inside an ancient data center — rows of humming machines
stretching into shadow behind, medieval tapestries hung over circuit-covered walls.
The creature is the clear focal point, occupying 60-70% of the frame.
Legendary character — unique distinguishing features, regal or imposing framing,
more individual detail than a generic creature. This is a named, important figure.
Maximum drama, awe, or dread. Cinematic scale and lighting. The subject commands
the entire frame. Hyper-detailed, the most polished rendering in the set.
Scene includes the moment of discovery — hands reaching into wreckage, a panel pried
open, glowing circuitry revealed. Warm metallic tones (bronze, copper, gold) on the
salvaged element, contrasting with surrounding decay.
[Universal suffix]
```

---

### Instant

**Fields used**: `name`, `oracle_text`, `flavor_text`, `colors`, `rarity`

```
A sudden, frozen-moment scene depicting {spell_effect_in_action}.
{who_or_what_is_affected}.
{energy_visual} matching {color} magical energy.
Tight crop, high energy. The moment feels instantaneous — caught mid-action.
```

**Key rule**: Show the EFFECT happening, not before or after. Instants are a single frozen frame of something dramatic.

#### Example: Scorched Passage (R-C-03)
```
[Red persona prefix]
[Universal prefix]
A sudden, frozen-moment scene depicting a blast of searing energy tearing through
a narrow dungeon corridor. Stone walls glow orange-white from the heat, debris
suspended mid-air. A silhouette at the far end of the tunnel is caught in the
blast wave.
Bright orange-red energy erupting from the near end of the frame, washing over
everything. Sparks and molten stone fragments frozen in flight.
Tight crop, high energy. The moment feels instantaneous — caught mid-action.
Grounded, everyday composition. Moderate detail. Slice-of-life in a strange world.
[Universal suffix]
```

---

### Sorcery

**Fields used**: `name`, `oracle_text`, `flavor_text`, `colors`, `rarity`

```
A sweeping scene depicting {spell_effect_in_action}.
{who_or_what_is_casting_or_affected}.
{energy_visual} matching {color} magical energy.
Wide-angle composition showing the full scope of the effect. Sorceries feel
deliberate and powerful — this took time and intention.
```

**Key difference from instant**: Wider framing, more environmental context. Sorceries are planned, not reactive.

---

### Enchantment

**Fields used**: `name`, `oracle_text`, `flavor_text`, `colors`, `rarity`

```
{enchantment_scene_description}.
An ethereal, persistent quality to the scene — something ongoing, not momentary.
Soft luminous edges, subtle glow, a sense of permanence and inevitability.
{aura_or_global_modifier}
```

**Aura modifier** (if oracle_text contains "enchant" or "attached"):
```
A subject visibly affected by the enchantment — the magical effect is ON them,
changing or augmenting them. The enchantment and the subject are one composition.
```

**Global modifier** (non-aura enchantments):
```
A scene or environment transformed by a persistent magical law or force.
The enchantment affects the whole frame, not a single subject.
```

#### Example: Edict of Continuity (W-U-03)
```
[White persona prefix]
[Universal prefix]
A scene in a Denethix government hall. A fallen soldier dissolves into golden
light while a new recruit steps forward from the ranks behind, identical armor
already donned. On a nearby workbench, a broken automaton's parts float gently
back together, reassembling themselves.
An ethereal, persistent quality to the scene — something ongoing, not momentary.
Soft luminous edges, subtle glow, a sense of permanence and inevitability.
A scene or environment transformed by a persistent magical law or force.
The enchantment affects the whole frame, not a single subject.
Heightened tension or wonder. More atmospheric detail. Something slightly
remarkable about the scene.
[Universal suffix]
```

---

### Artifact

**Fields used**: `name`, `type_line`, `oracle_text`, `flavor_text`, `rarity`

```
A {material_description} {object_type} {display_context}.
{intricate_detail_on_the_object}.
{material_quality}: ancient mega-technology, degraded but functional.
The artifact is the clear focal point, rendered with fine mechanical detail.
Muted background to emphasize the object.
```

**Equipment subtype**: If type_line contains "Equipment":
```
The equipment is shown being worn or wielded by a figure, but the ITEM is the
focal point — the figure is secondary, partially cropped or in shadow.
```

**Artifact Creature**: Uses the **Creature** template instead, but adds:
```
Clearly mechanical or constructed — visible joints, panels, internal mechanisms.
The boundary between creature and machine is blurred.
```

#### Example: Subsurface Signal Lamp (X-C-01)
```
[Colorless persona prefix]
[Universal prefix]
A cylindrical metal device sitting on a rough stone ledge in a dark underground
chamber. Tarnished bronze casing with a single glass lens at the top, emitting
a flickering beam of warm amber light. Exposed wiring along one side, a cracked
dial showing unknown symbols. Three small indicator lights — two dead, one
pulsing weakly.
Ancient mega-technology, thousands of years old. Dented, scratched, but still
functional. Fine mechanical detail on the casing — rivets, seams, a hinged
maintenance panel.
The artifact is the clear focal point, rendered with fine mechanical detail.
Muted background to emphasize the object.
Grounded, everyday composition. Moderate detail. Slice-of-life in a strange world.
The subject shows signs of unreliable technology — visible sparks, flickering
indicator lights, cracked glass, exposed wiring, status lights glowing amber/red.
Powerful but not fully functional.
[Universal suffix]
```

---

### Basic Land

**Fields used**: `name`, `subtypes` (Plains/Island/Swamp/Mountain/Forest), `flavor_text`, `color_identity`

```
A panoramic {landscape_type} in a post-apocalyptic science-fantasy world.
{time_of_day_and_atmosphere}.
{world_building_elements}: ancient mega-structures visible in the distance or
integrated into the natural landscape. Ruins of a hyper-advanced civilization
being slowly reclaimed by nature.
{color_specific_environment}.
Wide-angle landscape, deep atmospheric perspective. No figures or creatures.
A sense of vastness, beauty, and deep time.
```

**Per-subtype environments**:
- **Plains**: Open golden grasslands stretching to the horizon. Denethix's walls as a dark line in the distance. Ancient highway pylons standing in the grass like monuments. Warm amber light.
- **Island**: Coastal ruins — a flooded ancient facility, water lapping at corroded steel and cracked concrete. Mist rising. Cool blue-teal tones. Exposed submarine cables draped like kelp.
- **Swamp**: A murky lowland where ancient drainage infrastructure has failed. Dark stagnant water pooling around half-submerged machinery. Sickly green-purple bioluminescence. Fog.
- **Mountain**: Rocky highlands with exposed bunker entrances and ventilation shafts jutting from bare rock. Harsh orange-red light, dramatic shadows. Ancient antenna arrays on the peaks like skeletal trees.
- **Forest**: Dense canopy growing over and through ancient structures. Trees whose roots crack through concrete floors. Dappled green light. Steel girders used as trellises by climbing vines. Deep emerald and amber.

#### Example: Plains (L-01)
```
[Land persona prefix]
[Universal prefix]
A panoramic golden grassland stretching to the horizon under a faintly amber sky.
Late afternoon light, long shadows from structures in the middle distance. Dust
haze softening the horizon.
Ancient highway pylons stand in the grass like weathered monuments, their original
purpose forgotten. In the far distance, the dark walls of Denethix are barely
visible as a line between earth and sky. A cracked, overgrown road cuts through
the grass, leading toward the city.
Wide-angle landscape, deep atmospheric perspective. No figures or creatures.
A sense of vastness, beauty, and deep time.
Grounded, everyday composition. Moderate detail. Slice-of-life in a strange world.
[Universal suffix]
```

---

### Nonbasic Land

**Fields used**: `name`, `oracle_text`, `flavor_text`, `color_identity`

```
A panoramic scene of {location_description}.
{atmosphere_blending_color_identities}.
{world_building_elements}: a specific, named place in the world — more identity
than a basic land, less generic.
Wide-angle landscape with a sense of place. No prominent figures.
```

**Color identity blending**: If `color_identity` has two colors, blend the corresponding basic land environments. E.g., W/U = open grasslands meeting coastal ruins, or an ancient facility on the plains.

#### Example: Descent Waypoint (L-06, W/U)
```
[Land persona prefix]
[Universal prefix]
A panoramic view of a carved stone staircase descending into the earth, lit by
ancient blue-white guide lights embedded in the walls. The entrance is on a
sunlit plateau (warm amber light above) transitioning to cool blue-teal light
below. Crude rope markers and chalk arrows left by previous expeditions.
The opening is clearly ancient — too precise, too smooth — but the markings
around it are recent and human. A threshold between the known world and the
Anomalous Subsurface Environment.
Wide-angle landscape with a sense of place. No prominent figures.
Heightened tension or wonder. More atmospheric detail. Something slightly
remarkable about the scene.
[Universal suffix]
```

---

## Prompt Assembly Algorithm

```python
def build_art_prompt(card, style_guide, mechanics) -> str:
    layers = []

    # 1. Style persona from card colors
    layers.append(get_style_persona(card.colors))

    # 2. Universal prefix
    layers.append(UNIVERSAL_PREFIX)

    # 3. Type-specific body (LLM generates this from card data + template)
    template = get_template_for_type(card.type_line)
    body = llm_fill_template(template, card, style_guide)
    layers.append(body)

    # 4. Rarity modifier
    layers.append(get_rarity_modifier(card.rarity))

    # 5. Mechanic visual (if applicable)
    for mechanic in ["Salvage", "Malfunction", "Overclock"]:
        if mechanic.lower() in card.oracle_text.lower():
            layers.append(get_mechanic_visual(mechanic))

    # 6. Universal suffix
    layers.append(UNIVERSAL_SUFFIX)

    return "\n".join(layers)
```

**The LLM step** (`llm_fill_template`): A cheap model (Haiku) reads the card's `name`, `type_line`, `oracle_text`, `flavor_text`, `design_notes`, and the type-specific template, then writes 2-4 sentences of concrete visual description. This is the creative step — everything else is mechanical assembly.
