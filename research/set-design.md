# MTG Set Design Reference

## 1. Executive Summary

This document synthesizes quantitative analysis of five recent premier Magic: The Gathering sets with established design philosophy to define the structural profile of a modern MTG set. The five sets analyzed are **Duskmourn: House of Horror** (DSK, Sep 2024), **Bloomburrow** (BLB, Aug 2024), **Outlaws of Thunder Junction** (OTJ, Apr 2024), **Murders at Karlov Manor** (MKM, Feb 2024), and **The Lost Caverns of Ixalan** (LCI, Nov 2023). All data was collected from Scryfall and filtered to booster-eligible cards only.

**Key findings that define a modern standard set:**

- **Set size averages 277 cards** (range 266-291), with a consistent rarity breakdown of roughly 95 commons, 98 uncommons, 63 rares, and 20 mythics, plus 5 basic lands.
- **Creatures comprise approximately 55% of non-land cards**, with the remainder split among instants (~11%), sorceries (~10%), enchantments, artifacts, and a handful of planeswalkers.
- **Color distribution is remarkably balanced**: each mono-color represents 14-16% of non-land cards. Multicolor density varies dramatically (10-26%) based on set theme, making it the single largest theme-dependent structural variable.
- **The mana curve peaks at CMC 2-3**, with an average CMC of 3.1 across all non-land cards. The curve drops sharply above CMC 5.
- **Every set supports all 10 two-color draft archetypes** via signpost uncommons (9-10 pairs covered per set). Draft infrastructure is non-negotiable in modern set design.
- **Flying is the dominant evergreen keyword** (~26 cards/set), followed by trample, vigilance, flash, and reach. Removal density is high (~78 cards/set by a broad regex count), ensuring interactive limited environments.
- **Sets carry 15-24 non-evergreen mechanic keywords**, though this count is inflated by auxiliary mechanics (equip, crew, cycling variants). Core named mechanics per set number 3-5, appearing on 15-40 cards each.

These patterns are consistent across sets with wildly different themes (horror, animal fables, westerns, mystery, adventure), confirming they represent structural invariants of modern MTG design rather than theme-specific choices.

---

## 2. Set Structure

### 2.1 Card Counts

| Set | Code | Commons | Uncommons | Rares | Mythics | Basic Lands | Total |
|-----|------|---------|-----------|-------|---------|-------------|-------|
| Duskmourn | DSK | 96 | 100 | 60 | 20 | 5 | 276 |
| Bloomburrow | BLB | 86 | 100 | 60 | 20 | 5 | 266 |
| Outlaws of Thunder Junction | OTJ | 96 | 100 | 60 | 20 | 5 | 276 |
| Murders at Karlov Manor | MKM | 86 | 100 | 70 | 20 | 5 | 276 |
| Lost Caverns of Ixalan | LCI | 113 | 92 | 64 | 22 | 5 | 291 |
| **Average** | | **95.4** | **98.4** | **62.8** | **20.4** | **5** | **277** |
| **Std Dev** | | **11.0** | **3.6** | **4.4** | **0.9** | **0** | **8.9** |
| **Range** | | **86-113** | **92-100** | **60-70** | **20-22** | **5** | **266-291** |

**Analysis:**

- Uncommons and mythics are the most stable counts across sets. Uncommons hover at 92-100 and mythics are nearly always exactly 20.
- Commons show the most variance (86-113), largely driven by LCI which had a high artifact/transform card count inflating the common slot.
- Rares are typically 60, with MKM as an outlier at 70 (likely due to its multicolor-heavy design needing more gold rares).
- Basic lands are always exactly 5 (one per color).
- **Total minus basic lands** ranges from 261-286, averaging 272.

**Decision:** Our set should target **~275 cards total** (270 non-basic + 5 basic lands), with a rarity split of **95 commons, 100 uncommons, 60 rares, 20 mythics**.

### 2.2 Color Distribution

#### Mono-Color Percentages (of total non-land cards)

| Color | DSK | BLB | OTJ | MKM | LCI | Average |
|-------|-----|-----|-----|-----|-----|---------|
| White (W) | 16.1% | 15.9% | 15.1% | 14.0% | 15.1% | 15.2% |
| Blue (U) | 16.1% | 16.3% | 15.5% | 14.4% | 14.3% | 15.3% |
| Black (B) | 16.5% | 15.9% | 15.1% | 14.0% | 15.5% | 15.4% |
| Red (R) | 16.1% | 16.3% | 14.7% | 14.4% | 14.7% | 15.2% |
| Green (G) | 16.5% | 16.3% | 14.7% | 14.0% | 15.5% | 15.4% |
| **Multicolor** | **13.4%** | **15.5%** | **20.3%** | **26.1%** | **9.9%** | **17.0%** |
| **Colorless** | **5.1%** | **3.6%** | **4.4%** | **3.1%** | **15.1%** | **6.3%** |

#### Mono-Color Card Counts

| Color | DSK | BLB | OTJ | MKM | LCI | Average |
|-------|-----|-----|-----|-----|-----|---------|
| W | 41 | 40 | 38 | 36 | 38 | 38.6 |
| U | 41 | 41 | 39 | 37 | 36 | 38.8 |
| B | 42 | 40 | 38 | 36 | 39 | 39.0 |
| R | 41 | 41 | 37 | 37 | 37 | 38.6 |
| G | 42 | 41 | 37 | 36 | 39 | 39.0 |
| Multicolor | 34 | 39 | 51 | 67 | 25 | 43.2 |
| Colorless | 13 | 9 | 11 | 8 | 38 | 15.8 |

**Analysis:**

- Mono-color balance is extraordinarily tight. Each color accounts for 14-16.5% of non-land cards in every set, with average variance under 1 percentage point between colors within a set.
- **Multicolor is the most variable structural element**, ranging from 9.9% (LCI, artifact-heavy) to 26.1% (MKM, gold-heavy detective theme). Sets with strong multicolor themes (MKM, OTJ) push above 20%; sets emphasizing artifacts or mono-color themes stay below 15%.
- **Colorless** is similarly variable: LCI at 15.1% (artifact theme) versus MKM at 3.1%.
- The multicolor/colorless trade-off is clear: sets need to "spend" their non-mono-color budget on either multicolor or colorless, with the theme determining the split.

#### Per-Rarity Color Distribution (Average Mono-Color Cards per Rarity)

| Rarity | Per Color (avg) | Multicolor (avg) | Colorless (avg) | Total (avg) |
|--------|----------------|-------------------|-----------------|-------------|
| Common | 14.8 | 4.0 | 5.6 | 83.6 |
| Uncommon | 14.6 | 16.8 | 7.2 | 95.0 |
| Rare | 7.4 | 15.6 | 2.2 | 55.2 |
| Mythic | 2.4 | 6.8 | 0.8 | 19.2 |

**Key finding:** Commons are almost always mono-colored or colorless (BLB and MKM are exceptions with 10 multicolor commons each). Multicolor cards concentrate at uncommon and rare, where they signal draft archetypes and serve as compelling build-arounds.

**Decision:** Target ~15% per mono-color, ~15% multicolor, ~5% colorless for a balanced set. Adjust multicolor up or down based on theme.

### 2.3 Card Type Spread

#### Card Type Counts

| Type | DSK | BLB | OTJ | MKM | LCI | Average |
|------|-----|-----|-----|-----|-----|---------|
| Creature (total) | 142 | 159 | 158 | 139 | 159 | 151.4 |
| Instant | 23 | 34 | 35 | 42 | 23 | 31.4 |
| Sorcery | 25 | 27 | 29 | 30 | 24 | 27.0 |
| Enchantment (non-creature) | 47 | 19 | 18 | 36 | 17 | 27.4 |
| Artifact (non-creature) | 17 | 11 | 9 | 15 | 44 | 19.2 |
| Non-basic Land | 17 | 10 | 20 | 14 | 34 | 19.0 |
| Planeswalker | 1 | 1 | 2 | 1 | 1 | 1.2 |

*Note: "Creature (total)" includes enchantment creatures and artifact creatures. DSK had 31 enchantment creatures and 17 artifact creatures; LCI had 27 artifact creatures.*

#### Card Type Percentages (of non-basic-land total)

| Type | DSK | BLB | OTJ | MKM | LCI | Average |
|------|-----|-----|-----|-----|-----|---------|
| Creature % | 51.4% | 59.8% | 57.2% | 50.4% | 54.6% | 54.7% |
| Instant % | 8.3% | 12.8% | 12.7% | 15.2% | 7.9% | 11.4% |
| Sorcery % | 9.1% | 10.2% | 10.5% | 10.9% | 8.2% | 9.8% |

**Analysis:**

- Creature percentage (including creature subtypes like enchantment creatures and artifact creatures) averages 54.7% with a range of 50.4-59.8%. This is a fundamental design constraint: limited formats need enough creatures to build functional decks.
- Instants and sorceries together average ~21% of cards. MKM had the highest instant density (15.2%), consistent with its investigation/clue theme needing more spell interaction.
- Non-creature enchantments and artifacts vary wildly based on theme. DSK had 47 non-creature enchantments (horror/eerie theme); LCI had 44 non-creature artifacts (craft/treasure theme).
- Planeswalkers are rare: 1-2 per set, almost always at mythic.

#### Per-Rarity Type Distribution (Average Creature Count per Rarity)

| Rarity | Creatures | Instants | Sorceries | Ench. | Artifacts | Lands | PWs |
|--------|-----------|----------|-----------|-------|-----------|-------|-----|
| Common | 50.8 | 16.2 | 7.2 | 5.0 | 4.4 | 6.8 | 0 |
| Uncommon | 52.8 | 12.0 | 11.4 | 11.6 | 8.8 | 3.4 | 0 |
| Rare | 33.6 | 2.6 | 7.4 | 8.8 | 4.8 | 7.6 | 0 |
| Mythic | 14.2 | 0.6 | 1.0 | 2.0 | 1.2 | 1.2 | 1.2 |

**Key patterns:**
- Commons are creature-heavy (~53% creatures, ~17% instants, ~8% sorceries). This is by design per New World Order: simple creatures drive common gameplay.
- Uncommons have the most even type distribution, serving as the rarity where complex non-creature spells and enchantment/artifact build-arounds live.
- Rares have proportionally fewer instants (only ~2.6 per set) but more sorceries, enchantments, and lands. Splashy rares tend to be permanents, not spells.
- Mythics are dominated by creatures (~71% on average), with planeswalkers as the main non-creature mythic type.

**Decision:** Target 50-55% creatures, 10-13% instants, 8-11% sorceries, with remaining slots for enchantments/artifacts (themed to our set) and 10-15 non-basic lands.

### 2.4 Mana Curve

#### CMC Distribution (Counts)

| CMC | DSK | BLB | OTJ | MKM | LCI | Average |
|-----|-----|-----|-----|-----|-----|---------|
| 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 1 | 26 | 30 | 32 | 31 | 36 | 31.0 |
| 2 | 66 | 82 | 77 | 76 | 77 | 75.6 |
| 3 | 57 | 65 | 69 | 50 | 60 | 60.2 |
| 4 | 41 | 38 | 39 | 46 | 34 | 39.6 |
| 5 | 27 | 26 | 25 | 31 | 23 | 26.4 |
| 6 | 15 | 8 | 8 | 12 | 13 | 11.2 |
| 7+ | 22 | 2 | 1 | 11 | 9 | 9.0 |

#### CMC Distribution (Percentages)

| CMC | DSK | BLB | OTJ | MKM | LCI | Average |
|-----|-----|-----|-----|-----|-----|---------|
| 0 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| 1 | 10.2% | 12.0% | 12.7% | 12.1% | 14.3% | 12.3% |
| 2 | 26.0% | 32.7% | 30.7% | 29.6% | 30.6% | 29.9% |
| 3 | 22.4% | 25.9% | 27.5% | 19.5% | 23.8% | 23.8% |
| 4 | 16.1% | 15.1% | 15.5% | 17.9% | 13.5% | 15.6% |
| 5 | 10.6% | 10.4% | 10.0% | 12.1% | 9.1% | 10.4% |
| 6 | 5.9% | 3.2% | 3.2% | 4.7% | 5.2% | 4.4% |
| 7+ | 8.7% | 0.8% | 0.4% | 4.3% | 3.6% | 3.6% |

#### Average CMC

| Metric | DSK | BLB | OTJ | MKM | LCI | Average |
|--------|-----|-----|-----|-----|-----|---------|
| Average CMC | 3.53 | 2.92 | 2.90 | 3.23 | 3.04 | **3.12** |
| Median CMC | 3.0 | 3.0 | 3.0 | 3.0 | 3.0 | **3.0** |

**Curve shape analysis:**

The mana curve follows a consistent bell shape peaking at CMC 2-3:
- **CMC 1-2** collectively represent ~42% of non-land cards -- nearly half the set's spells cost 2 or less.
- **CMC 3** is the second-largest bucket at ~24%.
- **CMC 4** drops to ~16%.
- **CMC 5+** cards collectively represent only ~18% of the set, dropping off sharply with each additional mana.
- DSK is an outlier with average CMC of 3.53 and 8.7% at CMC 7+ (due to impending creatures and high-cost enchantments in the horror theme). BLB and OTJ are the leanest at ~2.9.

#### Per-Color Average CMC

| Color | DSK | BLB | OTJ | MKM | LCI | Average |
|-------|-----|-----|-----|-----|-----|---------|
| W | 3.46 | 2.80 | 2.71 | 2.75 | 2.61 | 2.87 |
| U | 3.63 | 3.02 | 2.87 | 3.00 | 3.03 | 3.11 |
| B | 3.90 | 3.10 | 2.66 | 3.17 | 3.31 | 3.23 |
| R | 3.54 | 2.83 | 2.76 | 2.86 | 3.19 | 3.04 |
| G | 3.45 | 2.66 | 2.95 | 3.19 | 3.23 | 3.10 |

**Color curve patterns:**
- **White** consistently has the lowest or second-lowest average CMC (~2.87), reflecting its weenie/aggro tendencies.
- **Black** tends toward the highest average CMC (~3.23), consistent with its expensive removal and large demons.
- **Red** and **Green** cluster near the middle (~3.0-3.1), though Red often curves lower due to aggressive creatures and burn.
- **Blue** varies but trends toward a middle-to-high CMC due to expensive fliers and card-draw effects.

#### Per-Rarity Average CMC

| Rarity | DSK | BLB | OTJ | MKM | LCI | Average |
|--------|-----|-----|-----|-----|-----|---------|
| Common | 3.39 | 2.84 | 2.76 | 3.08 | 2.96 | 3.01 |
| Uncommon | 3.04 | 2.83 | 2.91 | 3.12 | 2.82 | 2.94 |
| Rare | 3.81 | 2.67 | 2.91 | 3.20 | 3.22 | 3.16 |
| Mythic | 5.80 | 4.45 | 3.45 | 4.45 | 4.19 | 4.47 |

**Key pattern:** Mythics have dramatically higher CMC (4.47 average, ranging from 3.45 to 5.80) -- they are the splashy, expensive finishers. Commons and uncommons cluster around CMC 2.9-3.0, appropriate for the backbone of limited play. Rares sit slightly above at 3.16.

**Decision:** Target an average CMC of ~3.0-3.2. The curve should peak at CMC 2 (~30%) and CMC 3 (~24%), with less than 20% of cards costing 5+.

### 2.5 Creature Statistics

#### Average Power/Toughness by CMC (Cross-Set Average)

| CMC | Avg Power | Avg Toughness | Avg Creatures/Set |
|-----|-----------|---------------|-------------------|
| 1 | 1.02 | 1.44 | 10.8 |
| 2 | 1.85 | 2.08 | 40.0 |
| 3 | 2.51 | 2.66 | 40.6 |
| 4 | 3.22 | 3.48 | 26.2 |
| 5 | 4.07 | 4.30 | 17.0 |
| 6 | 5.14 | 5.02 | 8.6 |
| 7+ | ~5.0 | ~5.0 | ~3.0 |

**Vanilla test benchmarks (what you expect for a creature with no abilities at each CMC):**

- **CMC 1:** 1/1 is baseline. A 2/1 or 1/2 with no abilities is acceptable. Anything with power 2+ and an ability is pushed.
- **CMC 2:** 2/2 is the benchmark. A vanilla 2/3 or 3/1 is above-curve. Creatures with abilities are typically 1/3 or 2/1.
- **CMC 3:** 3/3 is the vanilla rate. Average creatures with abilities are 2-3/2-3.
- **CMC 4:** 3/3 to 4/4 with an ability. Vanilla 4/4 is unexciting. The data shows 3.2/3.5 average, indicating most 4-drops trade raw stats for abilities.
- **CMC 5:** 4/4 with a strong ability or 5/5 vanilla. Data shows 4.1/4.3, consistent with ability-bearing 5-drops.
- **CMC 6+:** 5/5 or larger with significant abilities. These are meant to end games.

**Notable creature subtype patterns across sets:**

- Every set has a dominant "people" type (Human in DSK/OTJ/LCI, various animal folk in BLB, Detective in MKM).
- Sets carry 2-4 heavily-featured creature subtypes that align with mechanics (e.g., BLB: Mouse, Frog, Rat, Bird; OTJ: Rogue, Mount, Mercenary).
- Common creature subtypes across multiple sets include Human, Warrior, Wizard, Soldier, and Scout.

---

## 3. Mechanics & Balance

### 3.1 Evergreen Keywords

#### Evergreen Keyword Frequency (Cards per Set)

| Keyword | DSK | BLB | OTJ | MKM | LCI | Average | Primary Colors |
|---------|-----|-----|-----|-----|-----|---------|----------------|
| Flying | 19 | 25 | 28 | 32 | 25 | **25.8** | W, U |
| Vigilance | 8 | 13 | 12 | 11 | 10 | **10.8** | W, G |
| Trample | 6 | 11 | 11 | 5 | 14 | **9.4** | G, R |
| Flash | 11 | 9 | 10 | 7 | 12 | **9.8** | U, (G, W) |
| Reach | 4 | 13 | 10 | 6 | 4 | **7.4** | G |
| Haste | 9 | 6 | 9 | 8 | 4 | **7.2** | R |
| Menace | 5 | 10 | 4 | 5 | 6 | **6.0** | B, R |
| Lifelink | 5 | 1 | 8 | 4 | 5 | **4.6** | W, B |
| Ward | 5 | 5 | 6 | 4 | 9 | **5.8** | U, W |
| Deathtouch | 4 | 5 | 5 | 4 | 4 | **4.4** | B, (G) |
| Double Strike | 2 | 1 | 0 | 3 | 1 | **1.4** | R, W |
| First Strike | 0 | 2 | 2 | 0 | 2 | **1.2** | R, W |
| Defender | 1 | 0 | 2 | 3 | 1 | **1.4** | Any |
| Hexproof | 1 | 0 | 0 | 2 | 1 | **0.8** | U, G |
| Indestructible | 0 | 0 | 0 | 1 | 1 | **0.4** | W |

**Tier analysis:**

- **Tier 1 (20+ per set):** Flying dominates at ~26 cards/set. It is the primary evasion mechanic and the single most impactful keyword for limited play.
- **Tier 2 (7-12 per set):** Vigilance, trample, flash, reach, and haste. These are the "workhorse" keywords that appear on 7-13 cards per set and define creature combat dynamics.
- **Tier 3 (4-6 per set):** Menace, lifelink, ward, deathtouch. Important but less frequent. Often concentrated in specific colors.
- **Tier 4 (0-3 per set):** Double strike, first strike, defender, hexproof, indestructible. Used sparingly for balance reasons (first strike/double strike distort combat; hexproof limits interaction; indestructible is pushed).

#### Color Assignment Patterns

The data confirms well-established color pie assignments:

| Keyword | Primary | Secondary | Tertiary |
|---------|---------|-----------|----------|
| Flying | W, U | B | R (rare) |
| Vigilance | W | G, U | R (rare) |
| Trample | G | R | B (rare) |
| Flash | U | G, W | B |
| Reach | G | R | U (rare) |
| Haste | R | G | (rare in others) |
| Menace | B | R | U (rare) |
| Lifelink | W, B | (rare in G) | -- |
| Ward | U, W | B, G | R (rare) |
| Deathtouch | B | G | -- |
| First Strike | R | W | -- |
| Double Strike | R, W | -- | -- |
| Defender | Any | -- | -- |

### 3.2 Set-Specific Mechanics

#### Core Named Mechanics per Set

| Set | Core Mechanics | Cards with Mechanic | Keyword Count |
|-----|----------------|--------------------|----|
| DSK | Manifest Dread, Survival, Eerie, Delirium, Impending | ~88 (core 5) | 24 total |
| BLB | Offspring, Gift, Valiant, Forage, Threshold | ~62 (core 5) | 18 total |
| OTJ | Plot, Spree, Saddle, Treasure (featured) | ~90 (core 4) | 15 total |
| MKM | Disguise, Investigate, Collect Evidence, Suspect, Cloak | ~121 (core 5) | 17 total |
| LCI | Discover, Explore, Descend, Craft, Transform (featured) | ~116 (core 5) | 24 total |

**Notes on keyword counts:** The raw `num_set_mechanics` counts (15-24) are inflated by auxiliary keywords like equip, crew, cycling variants, enchant, mill, surveil, and scry, which are returning/deciduous mechanics rather than true set-specific designs. The actual number of **new or featured named mechanics** per set is consistently **3-5**.

**Mechanic distribution patterns:**

- **Spread across colors:** Core mechanics are typically distributed across 2-4 colors each. No set has a mechanic limited to a single color at all rarities. Example: MKM's Disguise appears on 8-10 cards in each color; Investigate is heaviest in U (20) but present in all five.
- **Spread across rarities:** Mechanics appear at all rarities, with the heaviest concentration at common and uncommon to ensure draft visibility. Example: OTJ's Plot has 9 commons, 15 uncommons, 11 rares, 2 mythics.
- **Total cards with any set mechanic:** 115-210 per set (average ~158). This means roughly 40-75% of a set's cards reference at least one set mechanic, though many cards carry auxiliary keywords rather than the headline mechanics.
- **Individual mechanic saturation:** A single mechanic typically appears on 10-40 cards. MKM's Investigate (38) and Disguise (36) are at the high end; most mechanics land in the 15-25 range.

**Decision:** Plan for 3-5 named mechanics, each appearing on 12-30 cards. Ensure every mechanic appears at common (for draft visibility) and in at least 2-3 colors.

### 3.3 Legendary & Planeswalker Distribution

#### Legendary Creatures

| Metric | DSK | BLB | OTJ | MKM | LCI | Average |
|--------|-----|-----|-----|-----|-----|---------|
| Total Legendaries | 19 | 23 | 43 | 22 | 31 | **27.6** |
| At Uncommon | 3 | 0 | 10 | 0 | 9 | 4.4 |
| At Rare | 12 | 12 | 22 | 12 | 9 | 13.4 |
| At Mythic | 4 | 11 | 11 | 10 | 13 | 9.8 |

**Analysis:**

- Legendary creature count varies widely (19-43), strongly influenced by theme. OTJ (western outlaw theme) and LCI (adventure/gods theme) both featured many named characters.
- Uncommon legendaries are present in 3 of 5 sets. When present, they typically number 3-10. These serve both as draft signposts and as budget Commander options, a trend Wizards has embraced since 2022.
- Rares carry the bulk of legendaries (~13 per set), providing the main legendary density for Commander and casual play.
- Mythic legendaries average ~10, often serving as the set's story characters and marquee cards.

#### Planeswalkers

| Metric | DSK | BLB | OTJ | MKM | LCI | Average |
|--------|-----|-----|-----|-----|-----|---------|
| Total | 1 | 1 | 2 | 1 | 1 | **1.2** |
| Rarity | Mythic | Mythic | Mythic (2) | Mythic | Mythic | Always Mythic |

Planeswalker density has dropped significantly in recent sets (down from 3-5 in earlier eras). The current norm is **1-2 planeswalkers per set, always at mythic**.

**Decision:** Include 1-2 planeswalkers at mythic. Target 20-30 legendary creatures spread across uncommon (if desired), rare, and mythic.

### 3.4 Removal Density

#### Total Removal Count

| Metric | DSK | BLB | OTJ | MKM | LCI | Average |
|--------|-----|-----|-----|-----|-----|---------|
| Total Removal | 75 | 90 | 82 | 76 | 69 | **78.4** |
| Common Removal | 27 | 34 | 39 | 24 | 33 | **31.4** |
| Uncommon Removal | 34 | 36 | 31 | 38 | 19 | **31.6** |
| Rare Removal | 11 | 14 | 9 | 12 | 15 | **12.2** |
| Mythic Removal | 3 | 6 | 3 | 2 | 2 | **3.2** |

*Note: "Removal" is counted using a broad regex matching "destroy target", "exile target", "deals X damage", "-X/-X", etc. This counts combat tricks, sweepers, and conditional removal alongside premium single-target removal. The actual count of premium removal spells (unconditional creature removal at instant speed) is much lower.*

#### Removal by Color

| Color | DSK | BLB | OTJ | MKM | LCI | Average |
|-------|-----|-----|-----|-----|-----|---------|
| White | 19 | 25 | 19 | 23 | 14 | 20.0 |
| Blue | 7 | 12 | 6 | 10 | 5 | 8.0 |
| Black | 16 | 14 | 16 | 22 | 15 | 16.6 |
| Red | 25 | 27 | 28 | 24 | 19 | 24.6 |
| Green | 9 | 15 | 12 | 15 | 9 | 12.0 |
| Colorless | 7 | 5 | 13 | 2 | 12 | 7.8 |

#### Counterspells and Combat Tricks

| Metric | DSK | BLB | OTJ | MKM | LCI | Average |
|--------|-----|-----|-----|-----|-----|---------|
| Counterspells | 3 | 3 | 2 | 2 | 2 | **2.4** |
| Combat Tricks | 4 | 11 | 7 | 8 | 6 | **7.2** |

**Analysis:**

- **Red** has the most removal (~25/set) due to burn spells and damage-based removal counting heavily in the regex.
- **White** is second (~20/set) with exile effects and conditional removal (e.g., "exile target tapped creature").
- **Black** is third (~17/set) with destroy effects and -X/-X.
- **Green** has moderate removal (~12/set) via fight effects and bite effects (which match "deals damage equal to").
- **Blue** has the least hard removal (~8/set), relying instead on bounce, counterspells, and tempo plays.
- **Common removal (~31/set)** is critical for limited. This translates to roughly 6 common removal spells per color, ensuring every drafter has access to interaction.
- **Counterspells** average only 2-3 per set, always in Blue. This is deliberate: too many counterspells create feel-bad limited experiences.

**Decision:** Ensure at least 25-30 removal-adjacent effects at common. Every color should have at least 4-5 common cards that interact with creatures. Include 2-3 counterspells in Blue.

### 3.5 Draft Archetype Structure

#### Signpost Coverage

| Set | Color Pairs Covered | Uncommon Multicolor Cards | Rare Multicolor Cards |
|-----|--------------------:|-------------------------:|---------------------:|
| DSK | 10/10 | 20 | 14 |
| BLB | 10/10 | 10 | 19 |
| OTJ | 10/10 | 20 | 31 |
| MKM | 10/10 | 25 | 32 |
| LCI | 9/10 | 9 | 16 |

**Key finding:** Every set covers 9-10 of the 10 two-color pairs with at least one uncommon multicolor signpost card. This is a hard design rule in modern MTG. LCI missed UW at uncommon (covering only 9 pairs), which is the only exception across all five sets.

**Signpost examples from the data:**

- **BLB** used a clean "Mentor" cycle: one uncommon Mentor per color pair (e.g., Burrowguard Mentor for GW, Fireglass Mentor for BR).
- **DSK** and **OTJ** had 2 signpost uncommons per pair (20 total multicolor uncommons), giving each archetype two clear build-around signals.
- **MKM** had the most multicolor uncommons (25), reflecting its gold-heavy theme with multiple cards per pair.

**Archetype themes across sets:**

Draft archetypes are typically defined by a mechanical theme that maps to the color pair. The signpost uncommon card embodies this theme. For example:
- **WU (Azorius):** Often tempo or fliers-based. BLB: Plumecreed Mentor; MKM: No More Lies / Private Eye.
- **BR (Rakdos):** Aggressive or sacrifice-based. BLB: Fireglass Mentor; OTJ: At Knifepoint / Vial Smasher.
- **GW (Selesnya):** Go-wide tokens or +1/+1 counters. BLB: Burrowguard Mentor; OTJ: Congregation Gryff / Miriam.

**Decision:** Our set must have exactly 10 two-color draft archetypes with at least 1 multicolor uncommon signpost per pair (2 per pair is ideal). Plan for 10-20 multicolor uncommons and 10-20 multicolor rares.

---

## 4. Design Philosophy

### 4.1 New World Order

New World Order (NWO) is a set of design principles established by Mark Rosewater in 2011 that govern complexity distribution across rarities. The core principle: **commons must be simple** because they are the cards that players encounter most frequently (especially in limited), and excessive common complexity creates overwhelming board states.

**NWO principles observed in the data:**

1. **Common creatures are straightforward.** Most common creatures have 0-1 keywords. The average common CMC across sets is ~3.0, with simple stat-based designs (a 2/2 for 2, a 3/3 for 3 with one keyword).

2. **Common spells do one thing.** Common instants and sorceries typically have a single effect (deal damage, destroy a creature with a condition, draw a card). Complex modal or scaling effects are pushed to uncommon+.

3. **Mechanics at common are simple to execute.** When set mechanics appear at common, they use the mechanic's simplest mode. Example: MKM's Disguise appears on 18 commons (the most of any rarity), but common Disguise cards have straightforward trigger effects. Complex Disguise interactions (like additional on-reveal abilities) are at uncommon and rare.

4. **Board complexity at common is limited.** Common permanents avoid creating complex on-board interactions. Triggered abilities at common are typically simple (ETB effects, attack triggers) rather than complex state-tracking.

5. **Keywords per common card:** The data shows commons average fewer keyword mechanics than uncommons/rares. Flying is the most common keyword at common (~7.6 commons with flying per set), followed by flash (~4), reach (~3.2), and vigilance (~3.2). These are all simple, easily-understood keywords.

**Complexity budget by rarity:**

| Rarity | Complexity Level | Keywords/Card | Typical Ability Count |
|--------|-----------------|---------------|----------------------|
| Common | Low | 0-1 | 0-1 simple abilities |
| Uncommon | Medium | 0-2 | 1-2 abilities, can combine keywords |
| Rare | High | 0-3 | 2-3 abilities, complex interactions OK |
| Mythic | Very High | 0-4 | Splashy, unique effects, multiple abilities |

### 4.2 As-Fan Calculations

As-fan measures the expected number of cards with a given property that a player will see in a single booster pack. For a standard draft booster (10 commons, 3 uncommons, 1 rare/mythic, 1 basic land):

**Formula:** As-fan = (count at common / total commons) x 10 + (count at uncommon / total uncommons) x 3 + (count at rare / total rares + mythics) x 1

#### Evergreen Keyword As-Fan (Cross-Set Averages)

| Keyword | DSK | BLB | OTJ | MKM | LCI | Average |
|---------|-----|-----|-----|-----|-----|---------|
| Flying | 0.81 | 1.39 | 1.28 | 1.34 | 0.93 | **1.15** |
| Vigilance | 0.52 | 0.45 | 0.56 | 0.36 | 0.41 | **0.46** |
| Flash | 0.50 | 0.24 | 0.69 | 0.25 | 0.62 | **0.46** |
| Reach | 0.34 | 0.65 | 0.47 | 0.44 | 0.30 | **0.44** |
| Trample | 0.23 | 0.42 | 0.32 | 0.16 | 0.43 | **0.31** |
| Menace | 0.21 | 0.40 | 0.15 | 0.16 | 0.27 | **0.24** |
| Haste | 0.27 | 0.12 | 0.21 | 0.25 | 0.15 | **0.20** |
| Deathtouch | 0.26 | 0.19 | 0.16 | 0.15 | 0.17 | **0.19** |
| Ward | 0.26 | 0.06 | 0.21 | 0.03 | 0.23 | **0.16** |
| Lifelink | 0.09 | 0.03 | 0.41 | 0.16 | 0.11 | **0.16** |
| Defender | 0.10 | -- | 0.13 | 0.15 | 0.09 | **0.09** |
| First Strike | -- | 0.06 | 0.12 | -- | 0.02 | **0.04** |
| Double Strike | 0.03 | 0.03 | -- | 0.06 | 0.03 | **0.03** |

**Interpretation:**

- **Flying has an as-fan of ~1.15**, meaning a drafter can expect to see roughly 1 flier per pack. This is critical: flying is the primary evasion mechanic and needs to be present at a rate that makes it a real draft consideration without being overwhelming.
- **Vigilance, flash, and reach** cluster around 0.4-0.5 as-fan, meaning they appear roughly every 2-3 packs. This is the sweet spot for secondary keywords: common enough to be relevant, rare enough to feel meaningful.
- **Trample, menace, haste, deathtouch** at 0.2-0.3 as-fan appear every 3-5 packs. These are "spice" keywords that add variety without saturating the format.
- **Ward, lifelink, defender** at 0.1-0.2 are uncommon enough that they feel special when they appear.
- **Double strike and first strike** are very rare (0.03-0.04 as-fan) because they have outsized impact on combat math.

**Target as-fan ranges for our set's mechanics:**

| Mechanic Type | Target As-Fan | Rationale |
|---------------|-------------|-----------|
| Primary set mechanic | 0.8-1.5 | Should appear ~1x per pack to define the draft environment |
| Secondary set mechanic | 0.4-0.8 | Appears every 1-2 packs; supports the primary theme |
| Tertiary set mechanic | 0.2-0.4 | Appears every 3-5 packs; adds texture |

### 4.3 Color Pie Reference

The color pie defines which effects and abilities belong to which colors. This is one of Magic's most fundamental design rules. Below is a reference table for the most common card effects, compiled from observed patterns and established design rules.

#### Primary Effect Assignment by Color

| Effect Category | Primary Color(s) | Secondary | Notes |
|----------------|-------------------|-----------|-------|
| **Creature removal (destroy)** | B | W (conditional) | B gets unconditional "destroy target creature"; W gets conditional ("tapped", "power 4+") |
| **Creature removal (exile)** | W | B (rare) | W is the premier exile color |
| **Creature removal (damage)** | R | -- | "Deals N damage" is Red's primary removal |
| **Creature removal (fight)** | G | R (bite) | G gets fight ("each deals damage to other"); R gets bite ("yours deals damage to target") |
| **Creature removal (-X/-X)** | B | -- | B's alternative to destroy |
| **Counterspells** | U | -- | Exclusively Blue (2-3 per set) |
| **Card draw** | U | B (with cost) | U draws freely; B draws with life payment |
| **Direct damage (to players)** | R | B (life loss) | "Deals damage to any target" is R; "loses life" is B |
| **Lifegain** | W | B, G | W gains life most; B drains (gains + opponent loses); G incidental lifegain |
| **Enchantment removal** | W, G | -- | Primary in both colors |
| **Artifact removal** | G, R, W | -- | G and R destroy artifacts; W exiles |
| **Flying** | W, U | B | Green and Red almost never get flying |
| **Trample** | G | R | B gets trample rarely |
| **Haste** | R | G (rare), B (rare) | Overwhelmingly Red |
| **Deathtouch** | B | G | Sometimes in G for defensive creatures |
| **Reach** | G | R (rare) | Green's answer to fliers |
| **Tokens (small)** | W | G, R | W makes 1/1 tokens; G makes varied; R makes goblins/elementals |
| **Tokens (large)** | G | -- | G makes the biggest tokens (beasts, wurms) |
| **+1/+1 counters** | G, W | -- | Both get counter-based growth |
| **Ramp / mana acceleration** | G | -- | G is the only color that accelerates mana on a regular basis |
| **Land destruction** | R | -- | Extremely rare in modern sets; almost never at common |
| **Graveyard recursion** | B | G, W | B returns creatures; G returns to hand; W returns small creatures |
| **Bounce (return to hand)** | U | W (own creatures) | U bounces opponents' creatures; W flickers own |
| **Mill** | U | B | U mills opponent; B self-mills for value |
| **Pump (temporary P/T boost)** | R, G, W | -- | R: power boost; G: both stats; W: toughness-heavy |
| **Evasion (unblockable/skulk)** | U | B | U makes things unblockable; B uses menace/fear |
| **Vigilance** | W | G, U | W is primary; G secondary |
| **Flash** | U | G | U is primary; G secondary (often on creatures only) |

### 4.4 Theme-Mechanic Connection

Each analyzed set demonstrates how to connect a narrative theme to mechanical identity through named mechanics. Understanding these patterns helps design coherent mechanics for our own set.

**Duskmourn (DSK) -- Horror Theme:**
- **Manifest Dread** (face-down creatures) evokes unknown horrors lurking beneath the surface.
- **Survival** (triggers when no creatures died) captures the "final girl" horror trope.
- **Eerie** (triggers on enchantments entering or being put in graveyard) connects to the haunted house theme where enchantments represent curses, rooms, and hauntings.
- **Delirium** (card types in graveyard matter) reflects the madness and desperation of survival horror.
- The enchantment-creature dual type proliferated throughout the set (31 enchantment creatures) to support Eerie triggers.

**Bloomburrow (BLB) -- Animal Fable Theme:**
- **Offspring** (pay extra to make a small token copy) represents parent animals producing young.
- **Gift** (give an opponent something to get a bonus) captures the generous, communal nature of the woodland setting.
- **Valiant** (triggers when targeted by your spells) represents brave small creatures punching above their weight.
- **Forage** (exile 3 cards from graveyard or sacrifice a Food) represents animals gathering resources.
- Creature types are all animals (Mouse, Frog, Raccoon, etc.), with each color pair having a signature animal type.

**Outlaws of Thunder Junction (OTJ) -- Western/Heist Theme:**
- **Plot** (exile and cast later for free) represents outlaws scheming and planning heists.
- **Spree** (modal spell with additional costs per mode chosen) represents elaborate, multi-step heist operations.
- **Saddle** (tap creatures to activate mount abilities) represents the western riding/cavalry aesthetic.
- **Treasure** (heavily featured as a theme) represents the gold and loot at the heart of heist stories.
- The Outlaw creature types (Assassin, Mercenary, Pirate, Rogue, Warlock) were mechanically connected.

**Murders at Karlov Manor (MKM) -- Mystery/Detective Theme:**
- **Disguise** (face-down creatures with ward 2) represents hidden identities and suspects.
- **Investigate** (create Clue tokens) represents detective work and evidence gathering.
- **Collect Evidence** (exile cards from graveyard with total mana value >= N) represents building a case.
- **Suspect** (gains menace and can't block) represents identifying and pursuing suspects.
- This set had the highest multicolor density (26.1%), reflecting the guild-heavy Ravnica setting.

**The Lost Caverns of Ixalan (LCI) -- Adventure/Exploration Theme:**
- **Discover** (like cascade but with a mana value limit) represents finding treasures and artifacts.
- **Explore** (reveal top card, put on top or in graveyard, +1/+1 counter if land) represents scouting terrain.
- **Descend** (cards entering graveyard matters) represents delving deeper into caverns.
- **Craft** (exile this + other cards, transform) represents building artifacts from found materials.
- **Transform** was heavily featured (35 DFCs) with cards representing the duality of the surface world and the underground.

**Pattern for our set:** The best mechanics feel like the theme expressed as gameplay. They should:
1. Use a single evocative verb or noun (Plot, Discover, Investigate, Manifest).
2. Map to an intuitive action within the theme's fiction.
3. Create gameplay patterns that reinforce the emotional experience of the theme.
4. Interact with other mechanics in the set synergistically.

### 4.5 Storytelling Through Cards

Modern MTG sets tell stories through several structural elements, all visible in our data.

**Named legendary characters:** Each set features 19-43 legendary creatures representing key story characters. These appear at rare and mythic (and sometimes uncommon) and carry the narrative weight. OTJ had the most (43), reflecting its large cast of outlaws and allies. The protagonist, antagonist, and supporting cast are all represented as legendary creatures or planeswalkers.

**Signpost uncommons as archetype narrators:** The multicolor signpost uncommons often represent supporting characters or character relationships. BLB's Mentor cycle (10 cards) depicted animal mentors training apprentices, simultaneously telling stories and signaling draft archetypes.

**Location and event cards:** Non-creature permanents often represent locations (enchantments, artifacts, lands) or events (instants, sorceries) from the story. DSK had enchantment "rooms" representing areas of the haunted house. LCI had artifacts representing ancient relics. The non-basic land cycle in each set often depicts key story locations.

**Creature subtypes as worldbuilding:** The dominant creature subtypes define the world. MKM's Detective subtype (46 cards) established Ravnica as a city of investigators. BLB's animal types (Frog, Mouse, Rat, Bird) built a world of anthropomorphic animals. LCI's Dinosaur and Pirate types rooted the set in Ixalan's identity.

**Flavor text and naming conventions:** While not captured in our quantitative data, card names and flavor text carry enormous narrative weight. Sets use consistent naming conventions (MKM cards reference cases, evidence, clues; DSK cards reference fear, nightmares, survival).

**Decision:** Our set should have a clear story with:
- 3-5 main characters as mythic/rare legendaries
- 10+ supporting characters at rare/uncommon
- Location-representing permanents (lands, enchantments, or artifacts)
- A signature creature type or types that define the world
- Mechanics whose names evoke the theme's core fantasy

---

## 5. Recommendations for Our Set

Based on the comprehensive data analysis above, here are concrete targets for our custom set.

### 5.1 Total Card Count

| Parameter | Target | Acceptable Range |
|-----------|--------|-----------------|
| Total cards (with basics) | 275 | 265-290 |
| Commons | 95 | 86-110 |
| Uncommons | 100 | 92-100 |
| Rares | 60 | 60-70 |
| Mythics | 20 | 20-22 |
| Basic Lands | 5 | 5 |

### 5.2 Color Distribution Targets

| Parameter | Target | Acceptable Range |
|-----------|--------|-----------------|
| Per mono-color (% of non-land) | 15% | 14-17% |
| Per mono-color (count, ~250 non-land) | 38 | 36-42 |
| Multicolor (%) | 15% | 10-22% |
| Colorless (%) | 5% | 3-15% |

**Per-rarity mono-color targets (per color):**

| Rarity | Per Color | Multicolor Total | Colorless |
|--------|-----------|-----------------|-----------|
| Common | 15 | 0-10 | 4-6 |
| Uncommon | 14-16 | 10-20 | 3-7 |
| Rare | 7-8 | 10-20 | 0-5 |
| Mythic | 2-3 | 2-10 | 0-3 |

### 5.3 Card Type Spread Targets

| Type | Target % | Target Count (for 270 non-basic) | Range |
|------|----------|----------------------------------|-------|
| Creature (all) | 53% | 143 | 136-162 |
| Instant | 11% | 30 | 23-42 |
| Sorcery | 10% | 27 | 24-30 |
| Enchantment (non-creature) | 7-12% | 20-32 | Theme-dependent |
| Artifact (non-creature) | 5-10% | 14-27 | Theme-dependent |
| Non-basic Land | 7% | 19 | 10-34 |
| Planeswalker | <1% | 1-2 | 1-2 |

### 5.4 Mana Curve Targets

| CMC | Target % | Target Count (for ~252 non-land) |
|-----|----------|----------------------------------|
| 0 | 0% | 0-1 |
| 1 | 12% | 30 |
| 2 | 30% | 76 |
| 3 | 24% | 60 |
| 4 | 16% | 40 |
| 5 | 10% | 25 |
| 6 | 5% | 13 |
| 7+ | 3% | 8 |

| Metric | Target | Range |
|--------|--------|-------|
| Average CMC (all non-land) | 3.1 | 2.9-3.3 |
| Common average CMC | 3.0 | 2.8-3.2 |
| Mythic average CMC | 4.5 | 3.5-5.5 |

### 5.5 Keyword Budget

#### Evergreen Keywords

| Keyword | Target Count | Range | Required Colors |
|---------|-------------|-------|-----------------|
| Flying | 25 | 19-32 | W, U primary; B secondary |
| Vigilance | 11 | 8-13 | W primary; G, U secondary |
| Trample | 9 | 5-14 | G, R primary |
| Flash | 10 | 7-12 | U primary; G, W secondary |
| Reach | 7 | 4-13 | G primary |
| Haste | 7 | 4-9 | R primary |
| Menace | 6 | 4-10 | B, R primary |
| Ward | 6 | 4-9 | U, W primary |
| Lifelink | 5 | 1-8 | W, B primary |
| Deathtouch | 4 | 4-5 | B primary; G secondary |
| First Strike | 2 | 0-2 | R, W |
| Double Strike | 1 | 0-3 | R, W |
| Defender | 2 | 0-3 | Any |
| Hexproof | 1 | 0-2 | U, G |

#### Set-Specific Mechanics

| Parameter | Target | Range |
|-----------|--------|-------|
| Number of named mechanics | 4 | 3-5 |
| Cards per primary mechanic | 20-30 | 15-40 |
| Cards per secondary mechanic | 10-15 | 7-20 |
| Total cards with any set mechanic | 80-120 | 60-150 |
| As-fan per primary mechanic | 1.0-1.5 | 0.8-2.0 |
| As-fan per secondary mechanic | 0.4-0.8 | 0.2-1.0 |

### 5.6 Special Card Targets

| Card Type | Target | Range |
|-----------|--------|-------|
| Legendary creatures | 25 | 19-35 |
| Planeswalkers | 1 | 1-2 |
| Non-basic lands | 15 | 10-20 |
| Equipment | 5 | 2-12 |
| Auras | 7 | 3-10 |
| Vehicles | 2 | 0-6 |
| Sagas | 0-1 | 0-1 |

### 5.7 Removal Density Minimums

| Parameter | Target | Minimum |
|-----------|--------|---------|
| Total removal (broad count) | 75 | 65 |
| Common removal | 30 | 24 |
| Per-color removal at common | 5-6 | 4 |
| Counterspells (Blue) | 2-3 | 2 |
| Combat tricks | 7 | 4 |

**Per-color removal expectations:**
| Color | Target Total | Removal Style |
|-------|-------------|---------------|
| Red | 24 | Damage-based (burn, fight/bite) |
| White | 20 | Exile-based, conditional destroy |
| Black | 17 | Destroy, -X/-X |
| Green | 12 | Fight, bite, non-creature removal |
| Blue | 8 | Bounce, counterspells, -X/-0 |
| Colorless | 5-8 | Equipment, artifacts with removal |

### 5.8 Draft Archetype Guidelines

| Requirement | Target |
|-------------|--------|
| Two-color archetypes | 10 (all pairs) |
| Signpost uncommons per pair | 1-2 |
| Total multicolor uncommons | 10-20 |
| Total multicolor rares | 10-20 |
| Uncommon multicolor commons | 0 (unless theme demands it) |

Each archetype should have:
- 1-2 multicolor uncommon signpost cards that telegraph the theme
- 5-8 mono-color commons in each of the pair's colors that support the theme
- 2-4 uncommon/rare payoffs in each of the pair's colors
- A mechanical identity tied to the set's named mechanics

---

## Appendix A: Raw Data Summary Tables

### A.1 Complete Per-Set Creature Stats (Power/Toughness by CMC)

#### DSK (Duskmourn)

| CMC | Avg Power | Avg Toughness | Count |
|-----|-----------|---------------|-------|
| 1 | 1.30 | 1.50 | 10 |
| 2 | 1.95 | 2.08 | 39 |
| 3 | 2.82 | 2.58 | 38 |
| 4 | 3.09 | 3.48 | 23 |
| 5 | 3.88 | 4.56 | 16 |
| 6 | 5.09 | 5.18 | 11 |
| 7 | 6.50 | 6.25 | 4 |
| 9 | 9.00 | 9.00 | 1 |

#### BLB (Bloomburrow)

| CMC | Avg Power | Avg Toughness | Count |
|-----|-----------|---------------|-------|
| 1 | 1.08 | 1.46 | 13 |
| 2 | 1.84 | 1.93 | 45 |
| 3 | 2.35 | 2.75 | 48 |
| 4 | 3.15 | 3.63 | 27 |
| 5 | 4.00 | 4.35 | 17 |
| 6 | 5.25 | 4.75 | 4 |
| 7 | 5.00 | 5.00 | 1 |
| 8 | 6.00 | 6.00 | 1 |

#### OTJ (Outlaws of Thunder Junction)

| CMC | Avg Power | Avg Toughness | Count |
|-----|-----------|---------------|-------|
| 1 | 0.89 | 1.44 | 9 |
| 2 | 1.79 | 2.24 | 42 |
| 3 | 2.55 | 2.64 | 53 |
| 4 | 3.43 | 3.79 | 28 |
| 5 | 4.24 | 4.18 | 17 |
| 6 | 5.29 | 5.29 | 7 |
| 7 | 4.00 | 2.00 | 1 |

#### MKM (Murders at Karlov Manor)

| CMC | Avg Power | Avg Toughness | Count |
|-----|-----------|---------------|-------|
| 1 | 0.89 | 1.44 | 9 |
| 2 | 1.67 | 1.94 | 36 |
| 3 | 2.33 | 2.74 | 27 |
| 4 | 3.21 | 3.04 | 28 |
| 5 | 3.91 | 4.55 | 22 |
| 6 | 4.75 | 4.42 | 12 |
| 7 | 4.75 | 5.00 | 4 |
| 11 | 2.00 | 15.00 | 1 |

#### LCI (Lost Caverns of Ixalan)

| CMC | Avg Power | Avg Toughness | Count |
|-----|-----------|---------------|-------|
| 1 | 0.92 | 1.38 | 13 |
| 2 | 2.00 | 2.21 | 38 |
| 3 | 2.51 | 2.59 | 37 |
| 4 | 3.24 | 3.48 | 25 |
| 5 | 4.31 | 3.85 | 13 |
| 6 | 5.33 | 5.44 | 9 |
| 7 | 3.67 | 4.00 | 3 |
| 8 | 7.50 | 7.25 | 4 |

### A.2 Top Creature Subtypes per Set

| Rank | DSK | BLB | OTJ | MKM | LCI |
|------|-----|-----|-----|-----|-----|
| 1 | Human (44) | Frog (19) | Human (52) | Detective (46) | Human (27) |
| 2 | Nightmare (15) | Wizard (17) | Rogue (32) | Human (27) | Dinosaur (27) |
| 3 | Survivor (13) | Warrior (17) | Mount (17) | Elf (10) | Pirate (15) |
| 4 | Toy (11) | Warlock (17) | Mercenary (17) | Vampire (9) | Vampire (13) |
| 5 | Spirit (10) | Lizard (16) | Warlock (12) | Rogue (8) | Scout (13) |

### A.3 Special Cards Summary

| Metric | DSK | BLB | OTJ | MKM | LCI | Average |
|--------|-----|-----|-----|-----|-----|---------|
| Legendary Creatures | 19 | 23 | 43 | 22 | 31 | 27.6 |
| Planeswalkers | 1 | 1 | 2 | 1 | 1 | 1.2 |
| Sagas | 1 | 0 | 0 | 0 | 1 | 0.4 |
| Modal DFCs | 0 | 0 | 0 | 0 | 0 | 0 |
| Transform DFCs | 0 | 0 | 0 | 0 | 35 | 7.0 |
| Equipment | 8 | 2 | 5 | 9 | 12 | 7.2 |
| Auras | 10 | 4 | 3 | 9 | 7 | 6.6 |
| Vehicles | 2 | 1 | 2 | 1 | 6 | 2.4 |

### A.4 Draft Signpost Uncommon Names

#### DSK (Duskmourn) -- 2 per pair

| Pair | Signpost Cards |
|------|---------------|
| WU | Gremlin Tamer, Inquisitive Glimmer |
| WB | Rite of the Moth, Shroudstomper |
| WR | Arabella Abandoned Doll, Midnight Mayhem |
| WG | Baseball Bat, Shrewd Storyteller |
| UB | Fear of Infinity, Skullsnap Nuisance |
| UR | Intruding Soulrager, Smoky Lounge // Misty Salon |
| UG | Growing Dread, Oblivious Bookworm |
| BR | Disturbing Mirth, Sawblade Skinripper |
| BG | Broodspinner, Drag to the Roots |
| RG | Beastie Beatdown, Wildfire Wickerfolk |

#### BLB (Bloomburrow) -- 1 per pair (Mentor cycle)

| Pair | Signpost Card |
|------|--------------|
| WU | Plumecreed Mentor |
| WB | Starseer Mentor |
| WR | Seedglaive Mentor |
| WG | Burrowguard Mentor |
| UB | Tidecaller Mentor |
| UR | Stormcatch Mentor |
| UG | Lilysplash Mentor |
| BR | Fireglass Mentor |
| BG | Vinereap Mentor |
| RG | Wandertale Mentor |

#### OTJ (Outlaws of Thunder Junction) -- 2 per pair

| Pair | Signpost Cards |
|------|---------------|
| WU | Jem Lightfoote Sky Explorer, Wrangler of the Damned |
| WB | Baron Bertram Graywater, Ruthless Lawbringer |
| WR | Ertha Jo Frontier Mentor, Form a Posse |
| WG | Congregation Gryff, Miriam Herd Whisperer |
| UB | Intimidation Campaign, Lazav Familiar Stranger |
| UR | Kraum Violent Cacophony, Slick Sequence |
| UG | Doc Aurlock Grizzled Genius, Make Your Own Luck |
| BR | At Knifepoint, Vial Smasher Gleeful Grenadier |
| BG | Badlands Revival, Honest Rutstein |
| RG | Cactusfolk Sureshot, Jolene Plundering Pugilist |

#### MKM (Murders at Karlov Manor) -- 2 per pair

| Pair | Signpost Cards |
|------|---------------|
| WU | No More Lies, Private Eye |
| WB | Soul Search, Wispdrinker Vampire |
| WR | Lightning Helix, Meddling Youths |
| WG | Buried in the Garden, Sumala Sentry |
| UB | Coerced to Kill, Curious Cadaver |
| UR | Detective's Satchel, Gleaming Geardrake |
| UG | Evidence Examiner, Repulsive Mutation |
| BR | Deadly Complication, Rune-Brand Juggler |
| BG | Insidious Roots, Kraul Whipcracker |
| RG | Break Out, Tin Street Gossip |

#### LCI (Lost Caverns of Ixalan) -- 1 per pair (9 covered)

| Pair | Signpost Card |
|------|--------------|
| WB | Bartolome del Presidio |
| WR | Caparocti Sunborn |
| WG | Kutzil Malamet Exemplar |
| UB | Uchbenbak the Great Mistake |
| UR | Captain Storm Cosmium Raider |
| UG | Nicanzil Current Conductor |
| BR | Zoyowa Lava-Tongue |
| BG | Akawalli the Seething Tower |
| RG | Itzquinth Firstborn of Gishath |
| WU | *(none at uncommon)* |

---

## Appendix B: Methodology Notes

### Data Collection

- **Source:** All card data was pulled from the Scryfall API (`https://api.scryfall.com`) using the `is:booster` filter to include only cards that appear in draft/play booster packs.
- **Sets analyzed:** DSK, BLB, OTJ, MKM, LCI (5 most recent premier Standard sets as of data collection).
- **Filtering:** Tokens, art cards, emblems, and non-playable extras were excluded. Only cards with `games` containing `"paper"` and standard card layouts were included.
- **Pagination:** Scryfall returns max 175 cards per page; the pull script followed `next_page` URLs until all cards were retrieved.

### Known Limitations

1. **Removal counting is approximate.** The regex used (`"destroy target"`, `"exile target"`, `"deals .* damage"`, `"-X/-X"`, `"target creature gets -"`) is intentionally broad. It counts combat tricks, conditional removal, sweepers, and premium removal alike. The true count of premium, maindeckable single-target removal spells is roughly 40-60% of the broad count.

2. **Set mechanic keyword counting is noisy.** Scryfall's `keywords` array includes returning mechanics (surveil, explore), deciduous mechanics (equip, crew, scry, mill), and cycling variants alongside true set-specific mechanics. The `num_set_mechanics` count (15-24) should not be taken as the number of "new" mechanics -- the true number of new named mechanics per set is 3-5.

3. **Multicolor counting includes 3+ color cards.** Cards with 3+ colors (e.g., GRW, BGU) are counted in the multicolor total but don't map neatly to a single color pair. These typically number 3-8 per set and are mostly at rare/mythic.

4. **Creature count includes all creature subtypes.** A card with type "Enchantment Creature" counts as both a creature and an enchantment. The creature percentage (54.7% average) counts all cards with "Creature" in the type line, including enchantment creatures and artifact creatures. The "enchantment_only" and "artifact_only" counts exclude creatures.

5. **As-fan calculations use a simplified formula** based on a 10C/3U/1R draft booster model. Real Play Boosters have variable commons (6-7) and a wildcard slot, making actual as-fan slightly different. The draft booster model is used as the standard for our purposes.

6. **DFC handling:** LCI had 35 transform DFCs. These cards have two faces, and the analysis uses the front face for type, color, CMC, and keyword data. The back face (often a different permanent type, like a land or artifact) is not separately analyzed in the current data.

### Edge Cases Encountered

- **DSK's impending mythics** (5 cards) had high CMC values (listed as their full mana value despite the impending cost being lower), which inflated DSK's average CMC (3.53 vs. the 2.9-3.2 range of other sets) and the mythic average CMC (5.80).
- **LCI's UW draft pair** did not have a multicolor uncommon signpost, relying instead on mono-colored uncommons in both colors to signal the archetype. This is the only missing signpost in the entire dataset.
- **MKM's disguise mechanic** contributes face-down 2/2 creatures to the board which are not reflected in the power/toughness data (which measures the card's printed stats, not its face-down stats).
- **BLB had multicolor commons** (10 cards), which is unusual. Most sets keep commons mono-colored. This was a deliberate choice to support BLB's two-color animal tribes at the common level.

---

## Appendix C: Sources

### Data Sources

- **Scryfall API:** `https://api.scryfall.com` -- All card data retrieved via search endpoint with `set:<code> is:booster` queries.
- **Raw data location:** `research/raw-data/<set-code>/cards.json` for each of the 5 sets.
- **Analysis output:** `research/raw-data/analysis.json` containing all computed metrics.

### Design Philosophy References

- Mark Rosewater, "New World Order" (Making Magic, 2011) -- Complexity distribution by rarity.
- Mark Rosewater, "State of Design" articles (2019-2024) -- Annual set design retrospectives.
- Mark Rosewater, "Mechanical Color Pie" (2021 update) -- Official color pie assignments for all effects.
- Great Designer Search 3 essays (2018) -- Set design theory and practice.
- MTG Wiki: Set structure, booster composition, and card count references.

### Scryfall Queries Used

```
set:dsk is:booster
set:blb is:booster
set:otj is:booster
set:mkm is:booster
set:lci is:booster
```

Each query was paginated to retrieve all matching cards, then filtered locally to exclude non-standard layouts (tokens, art series, emblems).
