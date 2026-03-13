# Anomalous Descent (ASD) -- Card Gallery

**60 cards** | Generated 2026-03-12 | Opus 4.6, effort=max | Cost: $2.78

**Validation:** 42 clean, 18 with flagged issues

---

## White (10 cards)

### W-C-01: Denethix Watchguard

**{W}** | Creature -- Human Soldier | 1/2 | *Common*

*The Unyielding Fist posts sentries at every gate. Most of them even stay awake.*

**Design notes:** Clean white 1-drop vanilla. 1/2 for {W} is a standard common statline (P+T=3, CMC+3=4, well within budget). White gets small defensive creatures at common. The 1/2 body is useful for blocking early aggression, fitting white's protective role in the set. Flavor ties to Denethix's Unyielding Fist military force.

---

### W-C-02: Fist Patrol Rider

**{1}{W}** | Creature -- Human Soldier | 2/2 | *Common*

> Vigilance

*"Sleep is a luxury. Alertness is a duty."
--Unyielding Fist field manual*

**Design notes:** French vanilla 2-drop with vigilance, white's signature evergreen keyword. 2/2 vigilance for 2 is a well-established common statline (P+T=4, CMC+3=5, within budget). Vigilance is the quintessential white keyword and plays well at common -- simple to track and rewards both attacking and defending. Flavor connects to the Unyielding Fist enforcers of Denethix.

---

### W-C-03: Sanctioned Exile

**{2}{W}** | Instant | *Common*

> Exile target creature with power 4 or greater.

*"By order of the Vizier, you are remanded to the subsurface. Permanently."
--Fist Commandant Drel*

**Design notes:** Conditional exile-based removal, squarely in white's color pie. At 3 mana and restricted to power 4+, this is appropriately costed for common -- it handles big threats but can't answer small utility creatures or tokens. Comparable to Angelic Purge or Reprisal variants. The 'power 4 or greater' restriction keeps it conditional per NWO common removal guidelines. Instant speed is a slight premium but justified by the narrow targeting. Flavor ties to Denethix's authoritarian government exiling undesirables into the megadungeon.

---

### W-C-04: Salvage the Gatehouse

**{3}{W}** | Sorcery | *Common*

> Create two 1/1 white Human Soldier creature tokens.
> Salvage 3. (Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)

*Every ruin holds something worth defending -- and something worth taking.*

**Design notes:** White common sorcery combining token creation (white's bread and butter) with the set's Salvage mechanic. Two 1/1 tokens for 4 mana is below rate, but Salvage 3 adds meaningful value by filtering for artifacts. This is the first white card with Salvage so it includes reminder text. The sorcery speed and CMC 4 keep power level appropriate for common. Salvage 3 is within the common range (2-3). White is a primary Salvage color per the set's mechanic definition. The two effects are thematically linked -- you're reclaiming a defensive position and recovering relics from it.

**Validation issues:**
- `rules_text.reminder_in_oracle`: Oracle text contains what looks like reminder text: "(Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"

---

### W-M-01: Feretha, the Hollow Founder

**{W}{W}** | Legendary Creature -- Human Spirit | 2/3 | *Mythic*

> Vigilance, lifelink
> ~ can't attack or block unless you control an artifact.
> Whenever an artifact enters under your control, put a +1/+1 counter on ~.
> When ~ dies, salvage 4. (Look at the top four cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.).

*His body sits the throne. His mind turns the gears.*

**Design notes:** White mythic at CMC 2. A 2/3 with vigilance and lifelink for WW is pushed stats, but the restriction that it can't attack or block without an artifact is a meaningful deckbuilding constraint -- Feretha is literally a puppet without the machines sustaining him. The +1/+1 counter growth rewards artifact-heavy strategies and makes him scale into the late game. The death trigger salvage 4 ensures you recoup value if removed, fitting the lore of his brain being hooked to machinery. The flavor captures the tragedy of Denethix's hollow figurehead perfectly. Mythic-appropriate as a build-around legendary that demands artifact support but rewards it generously.

**Validation issues:**
- `rules_text.reminder_in_oracle`: Oracle text contains what looks like reminder text: "(Look at the top four cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"
- `text_overflow.oracle`: Oracle text is 338 characters, exceeding the 300-char limit for this card type

---

### W-R-01: Cult Relic-Bearer

**{W}** | Creature -- Human Cleric | 1/2 | *Rare*

> Whenever you cast an artifact spell, ~ gets +1/+0 and gains vigilance until end of turn.
> {2}{W}, {T}, Sacrifice ~: Salvage 5. (Look at the top five cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.).

*"Every relic is a prayer answered by the ancients."*

**Design notes:** White rare at CMC 1. A 1/2 for W is fair baseline. The artifact-cast trigger gives it early relevance in artifact-heavy decks as an aggressive body that gains vigilance. The sacrifice ability provides a late-game option -- pay 3 total mana, tap and sac to salvage 5, which is deep digging for a 1-drop. The sacrifice cost ensures it's a one-shot effect and creates tension between keeping the body and cashing it in. Salvage 5 at rare is within the scaling guidelines. Supports WU artifacts archetype.

**Validation issues:**
- `rules_text.reminder_in_oracle`: Oracle text contains what looks like reminder text: "(Look at the top five cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"

---

### W-R-02: The Vizier's Decree

**{2}{W}{W}** | Enchantment | *Rare*

> When ~ enters, exile target creature an opponent controls until ~ leaves the battlefield.
> Whenever a creature enters under an opponent's control, that creature doesn't untap during its controller's next untap step unless that player pays {2}.

*"Feretha's will is absolute. His voice is mine. His law is everything."
--Koyl Yrenum*

**Design notes:** White rare enchantment at CMC 4. Combines two white effects -- Oblivion Ring-style conditional removal and a taxing effect on opponent's new creatures. The Banishing Light effect ties removal to the enchantment's survival, giving opponents counterplay. The tax effect slows opponents deploying threats but doesn't prevent them -- pay 2 or your creature enters effectively tapped. This captures the Vizier's authoritarian control of Denethix. Both abilities are firmly in white's color pie (removal via exile, taxing effects). Strong but answerable -- destroying the enchantment frees the exiled creature and ends the tax.

---

### W-U-01: Cult Archivist

**{W}** | Creature -- Human Cleric | 1/1 | *Uncommon*

> Whenever an artifact enters under your control, you gain 1 life.

*"Each relic recovered is a verse of the Builders' gospel restored."*

**Design notes:** A 1-mana uncommon build-around that rewards the artifact subtheme with incremental lifegain -- firmly in white's slice of the color pie. The 1/1 body is fragile and the effect is small, so at uncommon this provides a useful synergy piece without being overpowered. Parallels Spore-Nest Forager (green, +1/+1 counters) and Spark Detonator (red, 1 damage) as artifact-entry payoffs in other colors, giving white its own angle on the same trigger. Lifegain is white's version of this effect -- defensive and incremental. The Cult of Science flavor ties the mechanical artifact caring to the set's world.

---

### W-U-02: Fist Supply Marshal

**{2}{W}** | Creature -- Human Soldier | 2/2 | *Uncommon*

> When ~ enters, salvage 3. (Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.).
> Whenever an artifact enters under your control, ~ gets +1/+1 until end of turn.

*"Requisition Form 7-C. Approved. Don't ask where it came from."*

**Design notes:** White uncommon at CMC 3. A 2/2 body is below rate for 3 mana, but the ETB salvage 3 provides card selection and the artifact-trigger pump gives it relevance in artifact-heavy decks. Supports the WU (Ancient Technology) and WG (Salvage) draft archetypes. The pump is temporary, keeping it from snowballing too hard. P+T base of 4 is well within CMC+3=6 budget. Two abilities is appropriate for uncommon.

**Validation issues:**
- `rules_text.reminder_in_oracle`: Oracle text contains what looks like reminder text: "(Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"

---

### W-U-03: Edict of Continuity

**{2}{W}{W}** | Enchantment | *Uncommon*

> Whenever one or more creatures you control die, create a 1/1 white Human Soldier creature token.
> Whenever an artifact you control is put into a graveyard from the battlefield, you may return it to its owner's hand.

*Denethix endures. Its people are replaced. Its machines, repaired.*

**Design notes:** White uncommon enchantment at CMC 4. Two related triggered abilities that reward attrition strategies -- creatures dying make tokens (white's bread and butter), and artifacts going to the graveyard can be recouped. The creature trigger only makes one token regardless of how many die at once, preventing combo abuse with board wipes. The artifact recursion requires the artifact to actually hit the graveyard (not exile), keeping it fair. Both halves support white's role as the 'civilization endures' color in this set. Complex enough for uncommon but each piece is individually simple.

---

## Blue (10 cards)

### U-C-01: Subsurface Surveyor

**{U}** | Creature -- Human Scout | 1/2 | *Common*

*"The first rule of the descent: count your steps. The second rule: count them again when nothing adds up."*

**Design notes:** Blue common vanilla at CMC 1. A 1/2 for {U} is a clean, on-rate defensive body -- comparable to Merfolk of the Pearl Trident's 1/1 but shifted to favor toughness, which fits blue's defensive common creature profile. P+T = 3 = CMC(1)+2, well within the CMC+3 budget. The Scout type fits the dungeon-exploration theme. No abilities keeps it NWO-clean at common.

---

### U-C-02: Glintscale Flyer

**{1}{U}** | Creature -- Drake | 1/2 | *Common*

> Flying

*They nest in the upper shafts of the megadungeon, drawn by thermals from machinery that hasn't cooled in ten thousand years.*

**Design notes:** Blue common french vanilla with flying -- blue's signature evergreen keyword. A 1/2 flyer for {1}{U} is a conservative, format-staple statline (compare to Welkin Tern at 2/1 flying). P+T = 3 = CMC(2)+1, very safe under the CMC+3 budget. Drake is a classic blue creature type. The slightly higher toughness makes it a reliable early blocker in the air, fitting blue's tempo-defensive role at common.

---

### U-C-03: Redirect Pulse

**{2}{U}** | Instant | *Common*

> Return target creature to its owner's hand.
> Draw a card.

*The ancient defense grid doesn't distinguish between intruders and residents. It simply insists that everyone leave.*

**Design notes:** Blue common instant -- bounce + cantrip at 3 mana. This is a well-established common template (compare to Blink of an Eye without kicker, or Repulse). Bounce is core blue removal that doesn't destroy permanents, respecting the color pie. The cantrip replaces itself, making it a solid tempo play. At {2}{U} it's fairly costed -- not as efficient as pure 2-mana bounce, but the card draw compensates. Fits the set by evoking ancient automated defense systems.

---

### U-C-04: Excavate the Archives

**{4}{U}** | Sorcery | *Common*

> Draw three cards, then discard a card.
> Salvage 3. (Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)

*"Most of what we find is junk. But junk from before the collapse is still worth a fortune."*

**Design notes:** Blue common sorcery at CMC 5 -- the 'complex common' slot. Draw 3 discard 1 is a classic blue common effect at 5 mana (Tidings draws 4 for 5, so draw 3 loot 1 is weaker on raw cards but adds selection). The Salvage 3 rider adds set-mechanic relevance and artifact synergy without adding meaningful complexity -- it's a clean additional look that happens after the draw/discard. Salvage at 3 is within the common range (2-3). The two effects are thematically unified: you're digging through ancient archives and pulling out useful relics. Sorcery speed keeps it from being too flexible.

**Validation issues:**
- `rules_text.reminder_in_oracle`: Oracle text contains what looks like reminder text: "(Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"

---

### U-M-01: The Head Scientist

**{1}{U}{U}** | Legendary Creature -- Human Artificer | 1/3 | *Mythic*

> Flash
> When ~ enters, salvage 5. (Look at the top five cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.).
> Artifact spells you cast cost {1} less to cast.
> Whenever you cast an artifact spell, you may tap or untap target permanent.

*He surveys his domain from twelve feet up. The stilts are load-bearing. So is the ego.*

**Design notes:** Blue mythic legendary creature at CMC 3. The Head Scientist is a key lore figure -- the leader of the Cult of Science, famous for his 12-foot stilts. Mechanically, he's a mythic build-around for artifact strategies. Flash lets you deploy him reactively (appropriate for blue). Salvage 5 on entry provides immediate value, digging deep for an artifact. The cost reduction enables explosive artifact chains, and the tap/untap trigger provides flexible interaction -- tap down blockers, untap your own mana rocks for more casts, or untap creatures for defense. A 1/3 body is deliberately fragile for a mythic, reflecting that he's a scientist, not a warrior. The power comes from the artifact synergy engine, not raw stats. Multiple abilities are appropriate at mythic rarity.

**Validation issues:**
- `rules_text.reminder_in_oracle`: Oracle text contains what looks like reminder text: "(Look at the top five cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"
- `text_overflow.oracle`: Oracle text is 320 characters, exceeding the 300-char limit for this card type

---

### U-R-01: Cult Savant

**{U}** | Creature -- Human Artificer | 1/1 | *Rare*

> Whenever you cast an artifact spell, draw a card, then discard a card.
> {3}{U}, {T}, Sacrifice ~: Return target artifact card from your graveyard to the battlefield. It gains malfunction 2. (It enters tapped with two malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.).

*"I understand this device completely. The runes mean 'warranty void if opened.'"*

**Design notes:** Blue rare creature at CMC 1. A build-around 1-drop for the Cult of Science archetype. The loot-on-artifact-cast ability is efficient card filtering that rewards artifact-heavy builds without raw card advantage -- you always discard. The activated ability is a powerful late-game reanimation effect for artifacts, gated behind significant costs (4 mana, tap, sacrifice) and the malfunction 2 tempo penalty. Malfunction is in-color for blue and creates meaningful delay. The sacrifice cost prevents repeatable abuse. A 1/1 for {U} is fragile enough to be answered easily. This is a Johnny/Jenny rare that rewards careful deckbuilding.

**Validation issues:**
- `rules_text.reminder_in_oracle`: Oracle text contains what looks like reminder text: "(It enters tapped with two malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.)"
- `rules_text.malfunction_enters_tapped`: Malfunction already causes the permanent to enter tapped -- explicit 'enters tapped' is redundant
- `color_pie.reanimation`: Card is U but has "reanimation" which is primarily B
- `text_overflow.oracle`: Oracle text is 316 characters, exceeding the 300-char limit for this card type

---

### U-R-02: The Cartography Engine

**{2}{U}{U}** | Legendary Enchantment -- Artifact | *Rare*

> At the beginning of your upkeep, salvage 4. (Look at the top four cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.).
> Whenever an artifact enters under your control, you may pay {1}. If you do, draw a card.

**Design notes:** Blue rare enchantment-artifact at CMC 4. A powerful engine card that defines the Cult of Science archetype. Salvage 4 every upkeep digs deep for artifacts, and the second ability converts those found artifacts into card advantage -- but requires mana investment ({1} per draw), preventing it from being free value. The two abilities create a virtuous loop: salvage finds artifacts, playing artifacts draws cards, drawing cards finds more fuel. At 4 mana with no immediate board impact, it's vulnerable to aggressive strategies. The legendary supertype prevents stacking. Enchantment-Artifact typing is flavorful (ancient technology) and makes it vulnerable to both enchantment and artifact removal, providing counterplay.

**Validation issues:**
- `rules_text.reminder_in_oracle`: Oracle text contains what looks like reminder text: "(Look at the top four cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"

---

### U-U-01: Cult Initiate

**{U}** | Creature -- Human Artificer | 1/1 | *Uncommon*

> When ~ enters, scry 1.
> Whenever you cast an artifact spell, ~ gets +1/+0 until end of turn.

*"The ancients didn't pray to their machines. They understood them. We'll get there eventually."*

**Design notes:** Blue uncommon creature at CMC 1 -- an early artifact-matters enabler for the Cult of Science (UR) and Ancient Technology (WU) draft archetypes. A 1/1 for {U} with scry 1 ETB is a fair floor (comparable to Faerie Seer). The artifact-cast trigger gives it scaling relevance without being oppressive -- it becomes a 2/1 attacker when you're casting artifacts, rewarding the set's artifact subtheme. P+T = 2 = CMC(1)+1, well within budget. Two abilities is appropriate at uncommon. The Artificer type supports tribal synergies. The Cult of Science flavor is a perfect home for this card.

---

### U-U-02: Subsurface Cartographer

**{2}{U}** | Creature -- Human Wizard | 2/2 | *Uncommon*

> Flying
> Whenever ~ deals combat damage to a player, salvage 3. (Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.).

*"Level four is plasma conduits. Level five is the screaming. I haven't mapped level six. Nobody maps level six."*

**Design notes:** Blue uncommon creature at CMC 3. A 2/2 flyer for 3 is a clean Limited body -- slightly below rate to account for the salvage trigger. Flying ensures it can connect for the combat damage trigger, making salvage 3 a meaningful reward for attacking. Supports both the UW Ancient Technology and UG Dinosaur/Artifact archetypes by filtering for artifacts. P+T (4) = CMC+1, well within budget. Two abilities (flying + triggered salvage) is appropriate uncommon complexity.

**Validation issues:**
- `rules_text.reminder_in_oracle`: Oracle text contains what looks like reminder text: "(Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"

---

### U-U-03: Automated Sentry Grid

**{3}{U}{U}** | Enchantment | *Uncommon*

> Whenever a creature an opponent controls attacks, tap it. It doesn't untap during its controller's next untap step unless its controller pays {2}.
> Whenever an artifact enters under your control, scry 1.

*The grid was designed to protect something. After ten thousand years, it no longer remembers what.*

**Design notes:** Blue uncommon enchantment at CMC 5. A defensive pillow-fort effect that feels like ancient security technology. The tap-and-freeze effect is a blue staple (Frost Titan, Dungeon Geists lineage) but spread across all attackers at a steep 5-mana investment. The {2} opt-out prevents total lockdown and gives opponents meaningful choices. The artifact-scry rider ties it into the set's artifact subtheme without being too powerful -- scry 1 is minor enough to not dominate. At 5 mana, this is a late-game stabilizer, not an oppressive lock piece.

---

## Black (10 cards)

### B-C-01: Subsurface Scavenger

**{B}** | Creature -- Human Rogue | 1/1 | *Common*

*The first level of the dungeon is picked clean. The second level picks back.*

**Design notes:** Black 1-mana vanilla creature. A 1/1 for B is the standard baseline -- clean, simple, fills the curve for limited. P+T=2, well within CMC+3=4 budget. The flavor captures a Denethix dungeon-diver scraping by on the megadungeon's upper levels.

---

### B-C-02: Fist Enforcer

**{1}{B}** | Creature -- Human Soldier | 2/1 | *Common*

> Menace

*The Unyielding Fist doesn't ask questions. The laser rifles discourage them.*

**Design notes:** French vanilla black common at CMC 2. A 2/1 menace for 1B is a solid aggressive two-drop -- P+T=3, within the CMC+3=5 budget. Menace is a primary black keyword and fits the Unyielding Fist thematically: enforcers that are hard to block because nobody wants to stand in front of them. The fragile toughness balances the evasion.

---

### B-C-03: Dungeon Rot

**{2}{B}** | Instant | *Common*

> Target creature gets -3/-3 until end of turn.

*The deeper halls breathe something that isn't air. Exposed flesh darkens, softens, and sloughs away in minutes.*

**Design notes:** Black common conditional removal. -3/-3 at instant speed for 3 mana is a clean, well-established rate for common removal -- it kills most small and midsize creatures but can't touch the biggest threats, keeping it appropriately conditional for common. Comparable to Disfigure's bigger sibling or Grasp of Darkness at a fairer cost. Straightforward, one-line rules text per NWO common guidelines.

---

### B-C-04: Plunder the Catacombs

**{4}{B}** | Sorcery | *Common*

> Return up to two target creature cards from your graveyard to your hand. Each opponent loses 2 life.

*"Loot the dead, sell what you can, and pray whatever killed them moved on." --Denethix Descent Guild handbook*

**Design notes:** Black common sorcery at CMC 5 with a more complex effect per the brief. This combines two core black effects -- raise dead (returning creatures from graveyard) and life drain -- into a single coherent card about plundering the dungeon's depths. Returning two creatures at sorcery speed for 5 mana is fair; the 2 life loss to each opponent adds value without being the primary mode. The two effects are thematically unified (descending into the catacombs and returning with spoils, leaving death in your wake) rather than being a kitchen-sink design. Appropriate complexity for a common sorcery -- two related effects, no tracking or board complexity.

---

### B-M-01: Apex of the Subsurface

**{2}{B}{B}** | Legendary Creature -- Horror | 4/4 | *Mythic*

> Deathtouch
> Whenever a creature dealt damage by ~ this turn dies, exile it. You may cast creature spells from among cards exiled with ~ by paying life equal to their mana value rather than paying their mana cost.
> Whenever you cast a spell this way, each opponent loses 2 life.

*It was here before Mount Rendon. Before humanity. It will be here after.*

**Design notes:** The mythic horror lurking at the bottom of the Anomalous Subsurface Environment. A 4/4 deathtouch for 4 is already a strong creature, but the real power is the reanimation-from-exile ability. Deathtouch ensures any creature it fights or blocks dies, feeding the exile zone. Then you can cast those exiled creatures by paying life -- deeply black, reminiscent of Bolas's Citadel and Reanimate. The 2-life drain on each cast offsets some of the life payment and pressures opponents. This creates a mythic play pattern: it kills things, eats them, and lets you deploy them. Life payment creates meaningful tension -- you can't recklessly cast everything. The 'dealt damage by ~' clause means it needs to be in combat or fighting, not just existing. Powerful, splashy, and quintessentially black.

---

### B-R-01: Koyl Yrenum, the Vizier

**{1}{B}** | Legendary Creature -- Human Advisor | 1/3 | *Rare*

> Whenever another creature dies, you may pay {1}. If you do, look at the top two cards of target opponent's library. Put one into their graveyard and the other back on top.
> hexproof, indestructible

*Feretha still rules Denethix. Everyone knows this. Everyone.*

**Design notes:** The Vizier who rules through deception -- mechanically, he manipulates information (opponents' libraries) and protects himself by sacrificing others. A 1/3 for 2 is defensive, fitting an advisor who hides behind others. The first ability is a repeatable Surveil-for-opponents on death triggers, costing {1} each time to prevent it from being free -- it fuels mill strategies and gives information advantage. The sacrifice ability is flavorful self-preservation: Koyl will always throw someone else under the bus. Both abilities together create tension: you want creatures to die (for value) but also need them alive (for protection). Complex but cohesive at rare.

**Validation issues:**
- `color_pie.hexproof`: Card is B but has "hexproof" which is primarily U/G
- `color_pie.indestructible`: Card is B but has "indestructible" which is primarily W

---

### B-R-02: The Brain Engine

**{3}{B}{B}** | Legendary Enchantment -- Artifact | *Rare*

> Whenever a nontoken creature you control dies, exile it with a charge counter on ~.
> {2}{B}, {T}, Remove three charge counters from ~: Return target creature card from exile to the battlefield under your control. It's a black Zombie in addition to its other colors and types.

*Feretha's body sat on the throne. His brain hung in the basement, dreaming of a city it no longer controlled.*

**Design notes:** A legendary enchantment artifact representing the machine keeping Feretha's brain alive -- and the broader super-science of brain extraction in the setting. It stockpiles dead creatures (exiling them to track via charge counters) then reanimates from exile, not graveyard, which is a distinctive twist. Requiring 3 charge counters means you need three creatures to die before you get one back -- this is a slow engine, not a combo piece. The Zombie typing adds black flavor. The tap requirement means one activation per turn. At 5 mana with a 3-death investment before payoff, this is powerful but appropriately slow for a rare build-around. Raise dead from exile is black's reanimation wheelhouse.

---

### B-U-01: Toothwork Familiar

**{B}** | Creature -- Construct | 1/1 | *Uncommon*

> When ~ dies, each opponent loses 1 life and you gain 1 life.

*Forty-seven teeth, none of them from the same mouth. It chittered when it walked and screamed when it broke.*

**Design notes:** Black uncommon 1-drop with a death trigger. A 1/1 for B that drains 1 on death is a useful role-player -- it trades profitably, discourages attacks, and synergizes with sacrifice themes (common in black). The drain-on-death is a classic black effect that rewards the creature dying, fitting the dungeon's attrition theme. P+T=2, well under budget. At uncommon it's a clean build-around piece for sacrifice or aristocrats strategies without being oppressive. The flavor references the set's clockwork dolls made of human teeth -- a perfectly normal thing to find in the Anomalous Subsurface Environment.

---

### B-U-02: Luminous Spark Extractor

**{2}{B}** | Creature -- Human Assassin | 2/2 | *Uncommon*

> When ~ enters, target opponent discards a card. If that card was a creature card, create a 1/1 colorless Construct artifact creature token.

*"We don't kill slavers. We simply... repurpose them."
--Kessa, Spark operative*

**Design notes:** Black uncommon at CMC 3. A 2/2 for 3 with a discard ETB is a solid but fair uncommon -- compare Burglar Rat (common, weaker) and Raider's Wake (uncommon, stronger). The conditional token creation adds value without being too complex. The Construct token ties into the set's super-science theme and the Society of the Luminous Spark's brain-extraction lore. P+T=4 <= 3+3=6, well within budget. Discard is core black, token creation is secondary.

---

### B-U-03: Subsurface Harvest

**{3}{B}{B}** | Enchantment | *Uncommon*

> Whenever a creature you control dies, you may pay 1 life. If you do, draw a card.
> At the beginning of your end step, if three or more creatures died this turn, create a 4/4 black Horror creature token.

*The dungeon feeds on the dead. It always has.*

**Design notes:** Black uncommon enchantment at CMC 5. The first ability is a classic black sacrifice-for-value engine -- paying life to draw cards is deeply black (compare Phyrexian Arena, Dark Prophecy). The life cost prevents it from being free card draw. The second ability rewards sacrifice-heavy strategies with a big payoff token, but requires real setup: three creatures dying in one turn demands either a board wipe or dedicated sacrifice outlets. At 5 mana, it's a midgame engine that asks you to build around it. The Horror token ties into the megadungeon's eldritch spawning theme.

---

## Red (9 cards)

### R-C-01: Moktar Raider

**{1}{R}** | Creature -- Moktar Warrior | 2/2 | *Common*

*The moktars don't raid Denethix because they hate civilization. They raid it because the granaries are right there.*

**Design notes:** Clean red common vanilla. A 2/2 for 2 is the baseline for a common creature -- no frills, just a solid body. P+T=4, CMC+3=5, well within budget. Moktars are a key creature type in the setting as wilderness raiders, making this a natural flavor fit for red's aggressive identity.

---

### R-C-02: Wasteland Raptor

**{2}{R}** | Creature -- Dinosaur | 3/1 | *Common*

> Haste

*The Fist's perimeter scouts learned to identify its hunting cry. By then, of course, it was already too late.*

**Design notes:** French vanilla red common with haste. A 3/1 haste for 3 is a clean aggressive creature -- hits hard but trades down easily. P+T=4, CMC+3=6, well within budget. The glass cannon statline is quintessentially red. Dinosaurs are a major creature type in the wilderness around Denethix, and haste captures the ambush predator feel.

---

### R-C-03: Scorched Passage

**{3}{R}** | Instant | *Common*

> ~ deals 4 damage to target creature.

*"Tunnel B-7 is clear."
"What was in it?"
"Doesn't matter now."*

**Design notes:** Conditional removal at common -- 4 damage for 4 mana at instant speed is a solid rate that kills most creatures but not everything. This is red's primary removal mode (burn) at an appropriate common power level. Comparable to Flame Javelin or similar burn spells, but at a fair rate. Doesn't hit players, keeping it as creature removal rather than a reach spell.

---

### R-C-04: Ransack the Storeroom

**{5}{R}** | Sorcery | *Common*

> ~ deals 5 damage divided as you choose among any number of target creatures.
> Create two Treasure tokens.

*The first adventurers down took notes and drew maps. The later ones just brought bigger bags.*

**Design notes:** A top-end common sorcery with two related effects -- board-clearing burn plus treasure generation. At 6 mana sorcery speed, 5 divided damage is a powerful but fair board wipe effect for limited (comparable to Pyrotechnics at 5 mana). The two Treasure tokens represent the loot you grab in the chaos, tying gameplay to the dungeon-raiding flavor. Both effects are squarely red. The complexity comes from dividing damage among targets, which is an established common-level complex effect (seen on cards like Fireball variants), making this appropriate as the 'complex' common slot.

---

### R-R-01: Spark Detonator

**{1}{R}** | Creature -- Human Rebel Artificer | 2/1 | *Rare*

> Whenever an artifact enters under your control, ~ deals 1 damage to each opponent.
> {1}{R}, Sacrifice an artifact: ~ deals 3 damage to any target.

*The Society of the Luminous Spark learned that ancient weapons are useful twice -- once when fired, once when they explode.*

**Design notes:** A 2 CMC red rare build-around that turns artifacts into damage. The triggered ability pings opponents whenever artifacts arrive (tokens count!), while the activated ability lets you sacrifice artifacts for significant targeted damage. At 2/1 it's fragile and demands protection. The two abilities are tightly linked -- both care about artifacts -- avoiding kitchen-sink design. This is a Spark Rebellion payoff card that also bridges into the UR artifacts-matter space. The 1-damage ping is incremental, while the 3-damage sac ability provides meaningful reach. Compares to Reckless Fireweaver but adds the sacrifice outlet at rare power level.

---

### R-R-02: The Burning Descent

**{4}{R}{R}** | Enchantment | *Rare*

> At the beginning of your upkeep, overclock. (Exile the top three cards of your library. You may play them until end of turn.).
> Whenever you play a card exiled with ~, ~ deals 2 damage to each opponent.

*The deeper you go, the hotter it gets. Most explorers assume that's geology.*

**Design notes:** A red rare enchantment showcasing the Overclock mechanic. Every upkeep you exile 3 cards and get to play them that turn -- a relentless engine that churns through your library. The 2-damage trigger per card played from exile rewards you for actually casting what you find, turning the overclock into a damage clock. At 6 CMC this is a late-game inevitability engine: 3 cards per turn with up to 6 damage if you play them all. The risk is real -- you're exiling cards permanently, and anything you can't play is lost forever. This creates genuine tension around deck construction (low curve helps) and mana management. Overclock's first appearance in the set, so reminder text is included.

**Validation issues:**
- `rules_text.reminder_in_oracle`: Oracle text contains what looks like reminder text: "(Exile the top three cards of your library. You may play them until end of turn.)"

---

### R-U-01: Spark Saboteur

**{1}{R}** | Creature -- Human Rebel | 2/1 | *Uncommon*

> When ~ enters, it deals 1 damage to target creature or planeswalker.
> Sacrifice ~: Destroy target artifact.

*The Luminous Spark lights fires. The Saboteurs make sure the right things burn.*

**Design notes:** A flexible utility creature for red at uncommon. The ETB ping is a classic red effect that's useful for picking off small creatures or finishing off damaged ones. The sacrifice-to-destroy-artifact ability gives it late-game relevance in a set full of ancient technology and constructs. Both abilities are firmly in red's color pie (direct damage and artifact destruction). P+T=3, CMC+3=5, within budget. Two abilities is appropriate for uncommon complexity. The Human Rebel type ties into the Society of the Luminous Spark rebellion flavor.

---

### R-U-02: Moktar War-Screamer

**{2}{R}{R}** | Creature -- Moktar Berserker | 3/2 | *Uncommon*

> Haste
> Whenever ~ attacks, it gets +1/+0 until end of turn for each other attacking creature.

*The moktars have no word for "retreat." They also have no word for "planning," "subtlety," or "indoors."*

**Design notes:** Red uncommon attacker that rewards going wide. 4 CMC for a 3/2 haste is below rate on its own (P+T = 5, CMC+3 = 7, well within budget), but the scaling attack bonus makes it a legitimate threat in aggressive decks. The bonus is genuinely variable -- depends on board state and attack decisions. Fits the Moktar Raider/warband flavor. Haste is fine here since no Malfunction. Two abilities (haste + triggered) is appropriate for uncommon.

---

### R-U-03: Raider's Bounty

**{4}{R}{R}** | Enchantment | *Uncommon*

> Whenever a creature you control deals combat damage to a player, exile the top card of your library. You may play it until end of turn.
> At the beginning of your end step, ~ deals 2 damage to you for each card exiled with ~ that wasn't played this turn. Then remove all cards exiled with ~ from the game.

*"Take everything. Carry what you can. Burn the rest."*

**Design notes:** A red uncommon enchantment that creates impulsive draw off combat damage -- core red mechanic. The complexity comes from the risk/reward tension: each connecting creature gives you a card to play, but unplayed cards punish you with 2 damage each at end step. This encourages careful sequencing -- attack with only as many creatures as you can use cards for. At 6 CMC it's a late-game value engine that demands an aggressive board to function. The self-damage prevents it from being free value and keeps it firmly in red's 'reckless impulse' space. 'Remove from the game' clause prevents tracking nightmares across multiple turns.

---

## Green (9 cards)

### G-C-01: Wilderness Tracker

**{1}{G}** | Creature -- Human Scout | 3/2 | *Common*

*The trails beyond Denethix don't stay in one place. Neither does she.*

**Design notes:** Green common vanilla at CMC 2. A 3/2 for {1}{G} is a clean, efficient baseline -- P+T = 5, which equals CMC+3. This is a standard green common beater comparable to Grizzly Bears variants with one extra power. No abilities keeps it at the simplest possible complexity for common. The Human Scout type fits the setting's wilderness exploration theme.

---

### G-C-02: Rendon Ceratops

**{2}{G}** | Creature -- Dinosaur | 3/3 | *Common*

> Trample

*Denethix's outer walls were built tall enough to discourage most predators. Most.*

**Design notes:** Green common french vanilla at CMC 3. A 3/3 trample for {2}{G} is a solid but fair limited creature -- P+T = 6 = CMC+3 exactly. Trample is the most iconic green evergreen keyword and plays perfectly on a dinosaur. The Dinosaur type ties into the set's wilderness teeming with dinosaurs. Clean, simple, does one thing well.

**Validation issues:**
- `power_level.overstatted`: Power 3 + Toughness 3 = 6 on a CMC 3.0 common creature exceeds P+T <= CMC+2 guideline

---

### G-C-03: Overgrown Ambush

**{3}{G}** | Instant | *Common*

> Target creature you control gets +3/+3 and gains trample until end of turn.

*"The jungle doesn't attack you. It just stops letting you leave."
--Denethix ranger's proverb*

**Design notes:** Green common combat trick at CMC 4. At 4 mana this is appropriately costed for a common -- it's a sizable pump but at instant speed it serves as green's version of removal (winning combats). +3/+3 with trample is a clean, single-purpose effect that green gets naturally. Comparable to cards like Titanic Growth but at one more mana for the added trample. Being an instant at 4 mana means it's a real mana investment to hold up, which is a natural balancing factor.

---

### G-C-04: Reclaim the Surface

**{5}{G}{G}** | Sorcery | *Common*

> Destroy target artifact and target enchantment.
> Create two 4/4 green Dinosaur creature tokens with trample.

*Nature does not reclaim. It was never gone.*

**Design notes:** Green common sorcery at CMC 7 with a complex effect for common. At 7 mana this is a top-end common that does something splashy -- destroying an artifact and an enchantment (both firmly in green's color pie) while also creating two 4/4 tramplers. The dual removal plus token creation is complex for common but justified at this high mana cost, where it serves as a big payoff in limited. Each target is required, so it's dead without both an artifact and enchantment target, which is a real deckbuilding/timing constraint that balances the power. Fits the theme of the wilderness overtaking ancient technology.

**Validation issues:**
- `power_level.nwo_multiple_keywords`: Common has 2 keyword abilities; NWO suggests at most 1

---

### G-R-01: Spore-Nest Forager

**{1}{G}** | Creature -- Fungus Scout | 1/2 | *Rare*

> Whenever an artifact enters under your control, put a +1/+1 counter on ~.
> {G}, Remove two +1/+1 counters from ~: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.

*It catalogues the dungeon's relics by taste.*

**Design notes:** A 2-CMC rare build-around that ties the set's artifact theme to green's ramp identity. P+T=3 (CMC+1) is modest, reflecting its value engine role. The first ability rewards playing artifacts -- synergizing with Salvage cards that find artifacts -- by growing the creature. The second ability converts accumulated counters into ramp, green's signature effect. Requiring two counters means you need multiple artifact triggers before each activation, creating real deckbuilding tension and preventing degenerate loops. The land enters tapped to prevent too-fast mana acceleration.

---

### G-R-02: The Subsurface Reclaims

**{5}{G}{G}** | Enchantment | *Rare*

> Whenever a nontoken creature you control dies, you may exile it. If you do, create a token that's a copy of that creature, except it's a Plant creature in addition to its other types and has "When this creature dies, salvage 5. (Look at the top five cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"

*"The dungeon doesn't kill you. It replants you."
-- Moktar proverb*

**Design notes:** A rare enchantment that creates a recursive value engine themed around the dungeon's alien ecosystem reclaiming the dead. Each nontoken creature gets one 'regrowth' as a Plant copy, but the copy is a token so it won't re-trigger the enchantment -- preventing infinite loops naturally. The added Salvage 5 on the token's death means each regrown creature leaves behind one last gift of artifact-finding, tying into the set's core mechanic at the rare-appropriate power level of 5. The exile clause is a real cost that prevents graveyard synergy overlap with black's recursion theme (e.g., The Brain Engine, Plunder the Catacombs), giving each color a distinct angle on death triggers.

**Validation issues:**
- `rules_text.this_creature`: Line 1: "this creature" should use "~" or "this" only in specific MTG contexts
- `rules_text.reminder_in_oracle`: Oracle text contains what looks like reminder text: "(Look at the top five cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"
- `text_overflow.combined`: Combined oracle + flavor text is 458 characters, exceeding the 450-char limit for this card type

---

### G-U-01: Moktar Salvager

**{1}{G}** | Creature -- Moktar Warrior | 2/1 | *Uncommon*

> When ~ enters, salvage 3. (Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.).

*"Shiny thing good. Shiny thing mine."
--Moktar creed, loosely translated*

**Design notes:** Green uncommon creature at CMC 2 featuring the set's Salvage mechanic. A 2/1 for {1}{G} with an ETB salvage 3 is a clean two-drop that supports the artifact subtheme. The body is intentionally undersized (P+T = 3, well under CMC+3=5) to account for the card selection. Salvage is in green's slice of the mechanic, and filtering for artifacts from the top of your library is a light form of card advantage appropriate for uncommon. The Moktar creature type ties into the setting's wilderness-dwelling moktars. First use of Salvage in the set, so reminder text is included.

**Validation issues:**
- `rules_text.reminder_in_oracle`: Oracle text contains what looks like reminder text: "(Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"

---

### G-U-02: Rendon Packleader

**{2}{G}{G}** | Creature -- Dinosaur | 4/3 | *Uncommon*

> Trample
> Whenever ~ deals combat damage to a player, salvage 4. (Look at the top four cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.).

*The herd moves as one. The earth moves with them.*

**Design notes:** Green uncommon at CMC 4 with P+T=7 (CMC+3, on budget). Trample helps connect for the salvage trigger, creating a natural synergy -- the keyword enables the ability rather than being stapled on. Salvage 4 at uncommon is in the 4-5 range specified for that rarity. Rewards attacking, which green wants to do with beefy creatures. The combat damage trigger means the salvage isn't guaranteed, adding meaningful gameplay tension.

**Validation issues:**
- `rules_text.reminder_in_oracle`: Oracle text contains what looks like reminder text: "(Look at the top four cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"

---

### G-U-03: Law of the Wilderness

**{5}{G}{G}** | Enchantment | *Uncommon*

> When ~ enters, destroy all artifacts and enchantments other than ~.
> Creatures you control get +2/+2 and have trample.
> Whenever an artifact or enchantment an opponent controls is put into a graveyard from the battlefield, create a 3/3 green Dinosaur creature token.

*Civilization is a brief interruption.*

**Design notes:** A splashy uncommon finisher at CMC 7 that captures green's philosophy of nature reclaiming technology. The ETB is a green-appropriate Shatterstorm/Tranquility hybrid. The anthem + trample is a classic green payoff for going wide. The token creation punishes opponents who try to rebuild with artifacts/enchantments after the sweep. At 7 mana this is a draft-viable top-end bomb that's powerful but appropriately costed. All three abilities are thematically unified: nature destroys civilization, empowers creatures, and grows from the ruins.

---

## White-Blue (3 cards)

### WU-M-01: The Custodian Eternal

**{3}{W}{U}** | Legendary Artifact Creature -- Construct | 4/5 | *Mythic*

> Flying, vigilance
> Whenever ~ or another artifact enters under your control, exile target nonland permanent an opponent controls until ~ leaves the battlefield.
> When ~ dies, salvage 6. (Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.).

*It was old when the world was young.*

**Design notes:** Mythic capstone for the WU Ancient Technology archetype. A 4/5 flying vigilance for 5 is a strong but fair body. The core ability is an Oblivion Ring-style repeatable exile tied to artifact ETBs -- each artifact you play temporarily removes a nonland permanent. This is white's exile-based removal married to blue's artifact affinity, creating a powerful board-control engine that rewards artifact-dense decks. The exile is tied to the Custodian leaving, so all exiled cards return if it's removed -- a meaningful counterplay window that prevents it from being oppressive. The death trigger (salvage 6) ensures you recover momentum if your opponent does answer it, finding another artifact threat to continue your gameplan. Flying + vigilance means it attacks and defends simultaneously, befitting an ancient guardian. P+T of 9 at CMC 5 is within mythic budget. The card is spectacular but answerable -- removal returns all exiled permanents, creating dramatic swings in both directions.

**Validation issues:**
- `rules_text.reminder_in_oracle`: Oracle text contains what looks like reminder text: "(Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"
- `text_overflow.oracle`: Oracle text is 347 characters, exceeding the 300-char limit for this card type

---

### WU-R-01: Protonium Curator

**{W}{U}** | Legendary Creature -- Human Artificer | 1/3 | *Rare*

> Whenever an artifact enters under your control, you may tap or untap target artifact.
> Artifacts you control have "Malfunction 1" instead of "Malfunction 2" or "Malfunction 3."

*"Every relic tells me its name. Most of them are screaming it."*

**Design notes:** Rare legendary for the WU Ancient Technology archetype. The first ability -- tapping or untapping an artifact when one enters -- is a flexible control tool. It can lock down an opponent's artifact or untap your own for repeated use, creating interesting board puzzles. The second ability is a build-around that reduces Malfunction counters on your permanents, making your degraded automatons come online faster. This directly supports the WU archetype's theme of mastering ancient technology. A 1/3 body is defensive and appropriate for a 2-mana utility legend -- it survives common removal like Spark Saboteur's ping. White gets the tap/untap-artifact space, blue gets artifact affinity, and the Malfunction reduction is a set-specific synergy payoff. The Malfunction reduction is a static replacement effect that's clean to parse.

---

### WU-U-01: Relic Warden Automaton

**{W}{U}** | Artifact Creature -- Construct | 2/2 | *Uncommon*

> Vigilance
> Whenever another artifact enters under your control, scry 1.

*Its patrol routes haven't changed in ten thousand years. Neither has its enthusiasm.*

**Design notes:** WU signpost uncommon for the Ancient Technology draft archetype. A 2/2 vigilance for 2 is a clean, efficient body. The artifact-trigger scry ability rewards the deck's natural artifact density without generating raw card advantage -- it smooths draws incrementally, which is the WU sweet spot. Vigilance is white, scry is blue, and the artifact-matters trigger ties into the archetype's core gameplan. Being an artifact creature itself means it can trigger other artifact-matters cards in the set (Cult Archivist, Spore-Nest Forager, Spark Detonator). Two abilities is appropriate for uncommon signpost. P+T = 4 = CMC+2, well within budget.

---

## White-Black (2 cards)

### WB-R-01: Proclamation Enforcer

**{1}{W}{B}** | Legendary Creature -- Human Soldier | 2/3 | *Rare*

> Whenever you gain life, create a 1/1 white Human Soldier creature token. This ability triggers only once each turn.
> Whenever another creature you control dies, each opponent loses 1 life.

*She ensures the city mourns on schedule and celebrates on command.*

**Design notes:** Rare WB legend for the Vizier's Regime archetype that creates a self-reinforcing engine. The lifegain-to-tokens ability is white (tokens, lifegain triggers seen on cards like Attended Healer), while the death-trigger drain is black. Together they form a loop: tokens die, opponents lose life, and any incidental lifegain (from the uncommon signpost Fist Tax Collector, Cult Archivist triggers, lifelink from Feretha, etc.) creates more tokens to sacrifice. The 'once each turn' clause on token creation prevents infinite loops and keeps it from spiraling out of control with repeated drain triggers. A 2/3 legendary for 3 mana is modestly statted -- the value is in the engine, not the body. As a build-around rare, it ties together the archetype's lifegain, token, and sacrifice themes without being a one-card combo.

---

### WB-U-01: Fist Tax Collector

**{W}{B}** | Creature -- Human Advisor | 2/1 | *Uncommon*

> Whenever another creature you control dies, each opponent loses 1 life and you gain 1 life.

*"The Vizier requires a contribution from every citizen. The dead are no exception."*

**Design notes:** WB signpost uncommon for the Vizier's Regime archetype. A 2/1 for 2 is clean at uncommon. The death-trigger drain effect is the core payoff for the sacrifice-and-taxation theme -- it rewards you for trading creatures, tokens dying in combat, or deliberate sacrifice outlets. White gets lifegain, black gets life drain, and both colors care about creatures dying. The effect is incremental rather than explosive, giving the archetype inevitability without being oppressive. Pairs naturally with token generators like Edict of Continuity and sacrifice outlets like Koyl Yrenum. P+T of 3 at CMC 2 is within budget, and the 2/1 stat line makes it fragile enough that opponents can answer it before it accumulates too much value.

---

## White-Red (2 cards)

### WR-R-01: Kethra, Spark Commander

**{1}{W}{R}** | Legendary Creature -- Human Rebel | 2/2 | *Rare*

> Haste
> Whenever ~ attacks, create a 1/1 white Human Rebel creature token that's tapped and attacking.
> Equipment you control have equip {1}.

*She freed a hundred slaves in a single night. By dawn, she had an army.*

**Design notes:** Rare WR legendary that leads the Spark Rebellion archetype. A 2/2 haste for 3 is below-rate on stats alone, justified by three synergistic abilities. Haste lets her attack immediately, triggering the token generation right away for immediate board impact. The token enters tapped and attacking -- go-wide aggression that's flavorful for a rebel commander rallying fighters. The equip cost reduction to {1} ties the go-wide token strategy to the equipment subtheme: you generate bodies and cheaply arm them. This creates a powerful engine in dedicated builds but she's fragile at 2/2 and needs equipment and combat to generate value. White gets tokens and equipment synergy; red gets haste and aggressive combat triggers. The combination of abilities tells a cohesive story without being a kitchen sink -- every line feeds into 'make rebels, arm rebels, attack.'

---

### WR-U-01: Spark Rallier

**{W}{R}** | Creature -- Human Rebel | 2/2 | *Uncommon*

> Whenever ~ or another creature you control becomes equipped, target creature you control gains first strike until end of turn.

*"They gave us slave collars. We made them into shields."*

**Design notes:** WR signpost uncommon for the Spark Rebellion archetype. A 2/2 for 2 is a clean, fair statline at uncommon. The triggered ability rewards the equipment subtheme by granting first strike whenever any creature you control becomes equipped -- this encourages moving equipment around in combat for aggressive trades. First strike is shared by white and red, and the equipment-matters trigger ties into the archetype's 'weapons to overwhelm' identity. The ability is strong in the right deck but does nothing without equipment, keeping it balanced as an archetype payoff rather than a generically powerful card.

---

## White-Green (2 cards)

### WG-R-01: Sura, Rendon Ranchmaster

**{1}{W}{G}** | Legendary Creature -- Human Settler | 2/3 | *Rare*

> Whenever you create one or more tokens, put a +1/+1 counter on each of them.
> {3}{G}{W}, {T}: Create two 1/1 white Human Soldier creature tokens and a 3/3 green Dinosaur creature token.

*"The beasts don't need taming. They need purpose."*

**Design notes:** Rare legendary for the WG Frontier Settlers archetype. The static ability rewards the entire token strategy by buffing every token you create across all sources -- Human Soldiers from Edict of Continuity arrive as 2/2s, Dinosaur tokens from Reclaim the Surface arrive as 5/5s. This is a powerful build-around that demands an answer. The activated ability is expensive at 5 mana + tap, providing a self-contained token engine that doesn't come online until later turns, generating 7 power across 3 bodies (boosted to 9 power with the counters). The 2/3 body for 3 is modest, keeping the card honest when you don't have token support. Green gets creature tokens and +1/+1 counters; white gets soldier tokens and anthem-adjacent effects. The legendary status prevents doubling up in limited.

---

### WG-U-01: Frontier Homesteader

**{W}{G}** | Creature -- Human Settler | 1/1 | *Uncommon*

> Whenever another creature enters under your control, put a +1/+1 counter on ~.

*"Forty acres, a ceratops, and a laser fence. That's all anyone needs."*

**Design notes:** WG signpost uncommon for the Frontier Settlers archetype. A simple, clean payoff for the go-wide token strategy -- every token or creature you add makes this bigger. At 1/1 for 2 mana, it's underwhelming on its own and demands you commit to the board-building plan. Compares favorably to cards like Luminarch Aspirant but requires more setup since it only triggers on OTHER creatures entering. Works with the token generation from white (Salvage the Gatehouse, Edict of Continuity) and green's creature-heavy gameplan. The +1/+1 counter theme ties into the archetype's counter subtheme. Single ability keeps it at uncommon complexity while being a meaningful build-around in draft.

---

## Blue-Black (1 cards)

### UB-U-01: Depth Crawler Archivist

**{1}{U}{B}** | Creature -- Human Rogue | 2/2 | *Uncommon*

> When ~ enters, mill three cards.
> Whenever one or more creature cards are put into your graveyard from your library, draw a card and you lose 1 life.

*"Level four had a library once. Now it has teeth. I took notes on both."*

**Design notes:** UB signpost uncommon for the Deep Descent archetype. The ETB mill 3 immediately fuels graveyard strategies and has a good chance of triggering the draw ability on entry. The triggered ability rewards continued milling from any source -- self-mill spells, other creatures, etc. -- creating a payoff engine for the archetype. The 'one or more' batching prevents it from drawing multiple cards off a single mill effect, keeping it fair. The life loss is the 'greater risk' the archetype promises and is squarely in black's color pie (paying life for cards). A 2/2 for 3 is below rate on stats, justified by the card advantage potential. Mill is shared UB territory, draw-for-life is black, making this a clean color pie fit. At uncommon, two abilities are appropriate and the interaction between them is the kind of synergy signpost uncommons should telegraph.

---

## Colorless (2 cards)

### X-C-01: Corroded Exo-Frame

**{2}** | Artifact -- Equipment | *Common*

> Equipped creature gets +1/+1.
> Equip {1}

*"It's missing an arm, the power cell is cracked, and something nested in the helmet. Still better than leather." --Moktar salvage report*

**Design notes:** A clean, simple common equipment for the set. +1/+1 for equip 1 at CMC 2 is a well-established rate (comparable to Short Sword at CMC 1 with equip 1 for +1/+1, but this costs 1 more to cast -- slightly below rate, which is fine for a colorless common). As a vanilla-equivalent, it has no special abilities beyond the baseline equipment function. Supports the artifact-matters subthemes across WU, WR, and UR archetypes by being a cheap artifact that naturally wants to be played. The flavor evokes degraded super-science gear repurposed by dungeon delvers.

---

### X-U-01: Flickering Relay Node

**{3}** | Artifact | *Uncommon*

> Malfunction 2 (This permanent enters tapped with two malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.).
> {T}: Add two mana of any one color.
> When the last malfunction counter is removed from ~, scry 2.

*It hummed, sputtered, hummed again, then settled into a frequency that made everyone's teeth itch.*

**Design notes:** A mana rock that showcases the Malfunction mechanic at uncommon complexity. With Malfunction 2, it enters tapped and can't be used for 2 full turns (counters removed at your upkeep turns 2 and 3, first tap available turn 3 after the last counter comes off). This is a significant tempo cost for a mana rock -- you're paying 3 mana now for 2-mana-per-turn payoff starting much later. Compare to Worn Powerstone (3 mana, enters tapped, taps for {C}{C} -- available next turn). This is stronger when online (colored mana) but dramatically slower. The scry 2 trigger when the last counter is removed rewards patience and creates a satisfying 'boot-up complete' moment. The tap ability produces colored mana, making enters-tapped meaningful per the design checklist. Malfunction 2 is the expected scaling for uncommon. Supports Cult of Science (UR) counter-manipulation themes.

**Validation issues:**
- `rules_text.this_creature`: Line 1: "This permanent" should use "~" or "this" only in specific MTG contexts
- `rules_text.reminder_in_oracle`: Oracle text contains what looks like reminder text: "(This permanent enters tapped with two malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.)"
- `rules_text.malfunction_enters_tapped`: Malfunction already causes the permanent to enter tapped -- explicit 'enters tapped' is redundant

---
