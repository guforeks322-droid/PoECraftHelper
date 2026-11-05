# PoE Craft Helper

**A crafting helper for Path of Exile 1**: an overlay on top of the game, plus a desktop workshop where you can plan a craft and try it out. No browser needed.

Copy an item in game and the overlay shows which mods are missing, the **next step** and the chance it works. The workshop has:
- the mod pool;
- a craft cost calculator using poe.ninja prices;
- a full crafting emulator, so you can spend virtual currency before you spend real currency.

> 🇷🇺 Russian version: [README.md](README.md)

---

## Features

### In-game overlay
- Hover an item and press **Ctrl+Alt+C**. A card appears showing:
  - the mods, split into prefixes and suffixes;
  - each mod's tier and roll quality;
  - the free slots.
- The **next step** comes with its currency icon, the chance per try and the average number of tries, for example Exalt, a bench craft or an essence.
- The card can open next to the cursor and hide itself after N seconds.
- Works with both **English and Russian** game clients.

### Start window (hub)
- Four tiles: Workshop, My crafts, Import code, Settings.
- Shows the active goal and recent items with their progress, for example 2/3 wanted mods.
- A craft library with search and a filter by item class.

### Workshop
| Tab | What it does |
|---|---|
| **Mod pool** | Every prefix and suffix of the base, with tiers, weights, roll % and weight bars. Covers influences (Shaper, Elder, the conquerors), clusters and catalysts. **Right click a mod to block it.** |
| **Calculator** | Alt+Aug, Alt→Regal, Chaos, essences, fossils and Harvest. Shows the chance and the **average cost** in chaos and divine at poe.ninja prices. The cheapest method is highlighted. |
| **Essences & fossils** | Pick by icon and see how the odds shift: before → after, which mods get more or less common, and which disappear. |
| **Emulator** | A game-like item card with roll quality and a log of what each action added or removed. You can rewind to any step. See below. |
| **Recipes** | A step-by-step craft plan with branches: "if…", "repeat until…", "else → step N". Running N items shows the success rate and the **real cost of the whole path**. Templates: Alt+Aug→Regal→Exalt, Chaos, essence, fossils, essence→block→Exalt. |
| **Sockets** | Chromatics and bench recipes, using the Siveran calculator formula and the 3.29 white sockets. |

### Crafting emulator
- **Currency:** Transmutation, Alteration, Augmentation, Regal, Alchemy, Chaos, Exalted, Annulment, Scouring, Divine.
- **Essences** and every **fossil**, including the special ones: Fractured, Glyphic, Tangled, Sanctified, Bloodstained, Hollow, Gilded.
- **Crafting bench** and metacrafts: Prefixes/Suffixes Cannot Be Changed, Cannot roll Attack/Caster, Can have up to 3 Crafted.
- **Influence:** conqueror exalts, Awakener's Orb, Orb of Dominance (Maven), Craicic Maw.
- **Eldritch:** Ember, Ichor, Eldritch Chaos/Exalt/Annul, Orb of Conflict.
- **Harvest** reforges, **Veiled** Chaos/Exalt, and the unveil choice at Jun.
- **Beast crafts:** Farric Wolf/Lynx Alpha, Split, imprint (Craicic Chimeral), aspects.
- **Vaal Orb**, **Tainted** currency, **catalysts** with quality, and **Hinekora's Lock** (preview the result).
- To craft, pick a method and click the item. Two automatic modes:
  - **"Spam until goal"** rolls until you have the wanted mods.
  - **"Run N items"** reports the average, the median, the 90th percentile of tries and the cost per item.
- **Ctrl+Shift+E** sends the item under your cursor straight into the emulator, with its mods and values.

### Buy or craft
- **"⌕ buy base"** and **"⌕ finished item"** open the official trade site with the base or the wanted mods filled in. Compare the craft cost with the price of a finished item.
- **"⌕ this on trade"** in the emulator searches for an item with the same mods.

### Crafts and sharing
- A craft goal is a set of wanted mods, each with the worst tier you accept. 13 starter crafts are included.
- A recipe is saved together with its craft.
- A craft code looks like `PCH1:…`. Paste it into Discord or Telegram, and another player can add it with "Import code".

### Comfort
- Frameless windows in one dark-gold style, on top of the game.
- Configurable global hotkeys. The interface is in Russian or English (Settings → Language).
- Currency icons and item art download from the game CDN on first launch. After that everything works offline.
- Update checks through GitHub releases.

---

## Installation

1. From [Releases](../../releases), download either:
   - the installer `PoECraftHelper-Setup-vX.Y.exe`, which needs no admin rights and creates a shortcut, **or**
   - the archive `PoECraftHelper-vX.Y-win64.zip`.
2. If you use the archive, unpack **all of it**. `PoECraftHelper.exe` must sit next to the `data` and `goals` folders.
3. Set the game to **Windowed Fullscreen**. Otherwise Windows won't show windows on top of the game.
4. Run `PoECraftHelper.exe`. To switch the interface to English, go to Settings → Language and restart the app.

### Default hotkeys
| Combo | Action |
|---|---|
| `Ctrl+Alt+C` (game) | copy an item → advice in the overlay |
| `Ctrl+Shift+E` | item under cursor → emulator |
| `Ctrl+Shift+O` | show/hide the overlay |
| `Ctrl+Shift+M` | show/hide the workshop |
| `Ctrl+Shift+H` | show/hide the hub |

---

## Is it safe?

The app **reads the clipboard** and does nothing in the game by itself.

The one exception is `Ctrl+Shift+E`: it sends exactly one copy keypress per press of yours, and you can turn it off in the settings.

The app doesn't read game memory and doesn't touch game files.

---

## Running from source

```bash
pip install -r requirements.txt
python overlay.py
```

Mod data (RePoE) downloads on first launch.

Tests:
```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

## Building and releases

`.github/workflows/build.yml` runs on `windows-latest`. It:
- downloads the data and runs the tests;
- builds `PoECraftHelper.exe` with PyInstaller and checks that it starts;
- packs the zip and builds the Inno Setup installer (`installer.iss`).

Pushing a `v*` tag creates a release.

## Credits

- [RePoE](https://repoe-fork.github.io) for mod and base data
- [poe.ninja](https://poe.ninja) for prices and icons
- [Craft of Exile](https://www.craftofexile.com) and [Awakened PoE Trade](https://github.com/SnosMe/awakened-poe-trade) for inspiration
- the Siveran socket calculator for the color formula

---

Path of Exile is a trademark of Grinding Gear Games. This is a fan project. It is not affiliated with or endorsed by GGG. Game data and images belong to Grinding Gear Games.
