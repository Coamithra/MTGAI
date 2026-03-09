# Symbol Assets

## Mana Symbols (`mana/`)

SVG mana, tap, and loyalty symbols sourced from the
[Mana](https://github.com/andrewgioia/mana) project by Andrew Gioia.

**License:** MIT (see `mana/LICENSE`)

### Files included

| Category       | Files                                                       |
|----------------|-------------------------------------------------------------|
| Basic mana     | `w.svg`, `u.svg`, `b.svg`, `r.svg`, `g.svg`, `c.svg`      |
| Generic mana   | `0.svg` through `20.svg`, `x.svg`, `y.svg`, `z.svg`        |
| Phyrexian      | `p.svg`                                                     |
| Snow           | `s.svg`                                                     |
| Tap / Untap    | `tap.svg`, `untap.svg`                                      |
| Energy         | `e.svg`                                                     |
| Loyalty        | `loyalty-up.svg`, `loyalty-down.svg`, `loyalty-zero.svg`, `loyalty-start.svg` |
| Other          | `half.svg`, `infinity.svg`                                  |

### Naming convention

Single-letter filenames match MTG mana symbol codes:
- `w` = White, `u` = Blue, `b` = Black, `r` = Red, `g` = Green, `c` = Colorless
- `p` = Phyrexian, `s` = Snow, `e` = Energy
- `x`, `y`, `z` = Variable generic mana
- Numeric filenames (`0.svg`-`20.svg`) = fixed generic mana costs

### Hybrid and Phyrexian colored mana

The Mana project handles hybrid mana (e.g., W/U) and colored Phyrexian mana
(e.g., W/P) through CSS class layering rather than individual SVG files. For
card rendering, these will need to be composited at render time by overlaying
the base color symbol with the split/Phyrexian indicator.

## Keyrune (Set Symbols)

The [Keyrune](https://github.com/andrewgioia/keyrune) project by Andrew Gioia
provides MTG expansion/set symbol glyphs. We keep only the license reference
here; set symbols will be pulled as needed in Phase 2A.

**License:** GPL 3.0 (icons/code), SIL OFL 1.1 (fonts) -- see `keyrune-LICENSE`

Note: Set symbol glyphs are based on trademarks of Wizards of the Coast and are
used for the purpose of identifying card sets, per the WPN Marketing Materials
Policy.

## Placeholder Set Symbol

Temporary geometric shield/chevron shape used until a custom set symbol is
designed in Phase 2A.

| File                          | Rarity  | Fill Color               |
|-------------------------------|---------|--------------------------|
| `set-symbol-placeholder.svg`  | Generic | Gray (#666666)           |
| `set-symbol-common.svg`       | Common  | Black (#000000)          |
| `set-symbol-uncommon.svg`     | Uncommon| Silver gradient (#A0A0A0)|
| `set-symbol-rare.svg`         | Rare    | Gold gradient (#C8A200)  |
| `set-symbol-mythic.svg`       | Mythic  | Orange gradient (#D35400)|

All placeholder symbols use a 100x100 viewBox with the same shield path.
These will be replaced with final art in Phase 2A.
