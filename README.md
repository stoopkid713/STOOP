# ツCKヤ DPS Meter

A combat-log analyzer for **Throne and Liberty** — real-time DPS, crit/heavy
tracking, per-skill rotation analysis, and side-by-side build comparison, in a
single native window. It reads the log files the game writes; it never touches the
game process.

> Backend rebuilt from scratch as owned, open code. Original concept by
> **SirPHz** ([mjb6967/CKdpsApp](https://github.com/mjb6967/CKdpsApp)) — see
> [LICENSE](LICENSE) / [NOTICE](NOTICE) and [LINEAGE.md](LINEAGE.md).

---

## ⬇️ Download & Run

Two ways to get it — pick one:

| | **Installer** | **Portable** |
|---|---|---|
| File | `TL-DPS-Meter-Setup.exe` | `TL-DPS-Meter-portable.zip` |
| Installs to | `%LOCALAPPDATA%\Programs` (per-user, no admin) | nowhere — runs from the folder |
| Start Menu / uninstaller | yes | no |
| Your data lives | `%LOCALAPPDATA%\TL-DPS-Meter` | **next to the exe** (USB-movable) |
| Best for | "set it and forget it" | a portable / USB setup, or trying it out |

**[⬇ Latest release →](https://github.com/stoopkid713/TL-DPS-Meter/releases/latest)**

- **Installer:** download `TL-DPS-Meter-Setup.exe`, run it, launch from the Start Menu.
- **Portable:** download `TL-DPS-Meter-portable.zip`, unzip anywhere (keep the files
  together), double-click `TL-DPS-Meter.exe`. The app *is* the window — no browser tab.

**Windows 10/11.** First launch shows a SmartScreen "unknown publisher" warning
(unsigned build) — click **More info → Run anyway**.

Then in Throne & Liberty, enable Combat Logging *(Settings → Shortcuts → Ring Menu →
add **"Combat Meter"**)* and activate it from the Ring Menu. T&L writes logs *after*
you leave combat, so stats populate when a fight ends, not during.

---

## Features

### 📊 Build Testing
60-second standardized tests for fair build comparison — real-time DPS, crit, heavy,
and crit+heavy rates, per-skill damage breakdown, weapon-specific DPS splits.

### 🎯 Rotation Analysis
- Stacked DPS timeline (per-second damage colored by skill — see which skills drove each burst)
- Piano-roll per-skill cast timeline
- Gap detection + segment analysis (0-15s, 15-30s, 30-45s, 45-60s)
- Skill-aware performance insights: weak-window cause, dropped-cast detection,
  DPS consistency (coefficient of variation), damage concentration

### ⚔️ Build Comparison
Compare up to 3 saved builds side-by-side — per-skill matrix, rotation timing,
segment DPS, and auto-computed key findings that name exactly which skills drove the delta.

### 🔬 Run Lab
Back-to-back build-testing without saving — Session Queue (runs auto-queue, tag/assign
inline), Skill Matrix, Cast Timeline, and Cast Drilldown (every cast: timestamp, damage,
hit type, interval chart).

### 💾 Build Management & 🏰 Dungeon Runs
Save encounters with build tags + class, load any for full review, combine encounters
into full dungeon runs with boss detection and run summaries.

### 👥 Party DPS (Beta)
Post-pull damage leaderboard shared across a party (all members run the app).

---

## Enable Combat Logging

1. **Settings → Shortcuts → Ring Menu Settings**
2. Add **"Combat Meter"** to your Ring Menu
3. In-game, open the Ring Menu and activate **Combat Meter**

Logs save to `%LOCALAPPDATA%\TL\Saved\CombatLogs`.

---

## Global Hotkey

| Hotkey | Action |
|--------|--------|
| `Ctrl+Tab` | Reset encounter (works while in-game) |

---

## Build from source

The app is Python + a single-file HTML frontend, packaged with PyInstaller.
[`uv`](https://github.com/astral-sh/uv) drives a reproducible build.

```powershell
cd backend
uv run pytest                 # run the test suite
uv run python build.py        # -> dist/TL-DPS-Meter.exe + portable.zip + Setup.exe
```

`build.py --no-installer` skips the Inno Setup step. The installer needs
[Inno Setup 6](https://jrsoftware.org/isdl.php) (`winget install -e --id JRSoftware.InnoSetup`).
Run the app in dev (no packaging) with `uv run python main.py`.

---

## Data files

The app seeds functional presets on first run; your fight data starts empty.

| File | Purpose |
|------|---------|
| `config.json` | Settings (log path, player name, hotkey) |
| `encounters.json` | Saved encounters + build-tag history |
| `saved_runs.json` | Saved dungeon runs |
| `skill_settings.json` | Skills marked as cannot-crit / cannot-heavy |
| `weapon_config.json` | Skill→weapon assignments |
| `default_target_assignments.json` | Target categorization |
| `dungeons.json` | Dungeon definitions |

Reveal the folder from the app's sidebar ("🗃️ App Data"); reset fight data with
"♻️ Reset Data" (keeps presets).

---

## FAQ

**Why don't I see damage during combat?** T&L writes logs when you leave combat, not
during. Stats appear after each fight.

**Can I get banned?** The tool only reads log files the game generates. It does not
inject into, modify, or interact with the game process.

**Why does antivirus / SmartScreen flag the exe?** False positive from unsigned
PyInstaller packaging. The source is in this repo — build it yourself if you prefer.

**How do I filter to only my damage?** Settings → Player Name → your character name.

---

## Credits

- Original concept: **SirPHz** — [mjb6967/CKdpsApp](https://github.com/mjb6967/CKdpsApp)
- This build: **stoopkid4529**

Made for the Throne and Liberty community ☕
