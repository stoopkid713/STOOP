# 05 — Data Contracts

[← Wiki home](README.md)

Authoritative shapes live in [`backend/SCHEMAS.md`](../../backend/SCHEMAS.md) (the committed
"Phase 0 digest", with `[CORRECTED]` flags where the original docs guessed wrong). This page
summarizes the three contracts that bound everything: the **combat-log grammar** (input), the
**8 JSON files** (state), and the **WebSocket protocol** (transport).

## 1. Combat-log grammar (the input contract)

CSV. Header line `CombatLogVersion,4` (skipped). A damage line has **≥10 comma fields**:

| idx | field | type | notes |
|---|---|---|---|
| 0 | Timestamp | str | `YYYYMMDD-HH:MM:SS:mmm` |
| 1 | LogType | str | always `DamageDone` |
| 2 | SkillName | str | may contain spaces |
| 3 | SkillId | str | numeric |
| 4 | Damage | int | |
| 5 | HitCritical | bool | `1`/`0` |
| 6 | HitHeavy | bool | `1`/`0` |
| 7 | HitType | str | `kMiss` / `kMinDamageByNormal` / `kNormalHit` / `kMaxDamageByNormal` / `kMaxDamageByCriticalDecision` |
| 8 | CasterName | str | player filter |
| 9+ | TargetName | str | re-join `parts[9:]` on `,` |

`<10` fields or a parse error → skipped. Player filter: empty player name → accept all. Parsed by
[`combat_log_parser.py`](../../backend/combat_log_parser.py); indices in
[`constants.py`](../../backend/constants.py).

> **⛔ Hard limit (verified):** the T&L log is **self-only and outgoing-damage only** — every row
> is `DamageDone`, the caster is always the player, the player never appears as a target. There are
> **no** incoming-damage, death, boss-HP, healing, or buff/debuff rows. So death/defensive timelines,
> buff-uptime, and boss-HP phase-splitting are **not buildable** from the log (they'd need
> memory/packet capture, which the architecture refuses). Underused-but-present: per-**target**
> damage and **`hit_type`** (a free accuracy/hit-quality stat).

## 2. The stat block (computed core)

Produced by `CombatStats.to_dict()` ([`combat_stats.py`](../../backend/combat_stats.py)); used as
`overall` and `first_60s` inside an encounter record:

```
{ dps, total_damage, duration, hit_count,
  crit_rate, crit_damage, heavy_rate, heavy_damage, crit_heavy_rate, crit_heavy_damage,
  skills: [SkillEntry], top_hits: [HitEntry] (top 10), targets: [TargetEntry],
  # first_60s ALSO has:
  rotation: [HitEntry] (every hit, chronological), gap_stats: GapStats }
```

- **SkillEntry** `{name, damage, hits, crits, heavies, crit_damage, heavy_damage, percent}`
- **HitEntry** `{time, relative_time, skill, target, damage, is_crit, is_heavy, hit_type}`
- **TargetEntry** `{name, damage, percent}`
- **GapStats** `{total_dead_time, num_major_gaps, longest_gap, avg_time_between_hits, gaps}`

## 3. The 8 JSON files (on-disk state)

Managed atomically by [`persistence.py`](../../backend/persistence.py). Shapes per
[`SCHEMAS.md`](../../backend/SCHEMAS.md):

| File | Shape (top level) | Notes |
|---|---|---|
| `config.json` | `{log_path, player_name, auto_detect_log, broadcast_interval, hotkey_enabled, hotkey, hotkey_sound, party_token, party_enabled}` | + `last_updated` on save |
| `encounters.json` | `{encounters: [EncounterRecord], builds: [str], last_updated}` | |
| `saved_runs.json` | **bare list** `[ {…13 keys} ]` | no wrapper, no `last_updated`; `{runs:[…]}` is WS-only |
| `skill_settings.json` | `{skills: {name: {cannot_crit, cannot_heavy}}, last_updated}` | has a `skills` wrapper |
| `weapon_config.json` | `{skillAssignments: {name: weapon}, last_updated}` | weapons lowercase |
| `default_target_assignments.json` | `{category: [names]}` | bundled, read-only (293 `adds`) |
| `target_assignments.json` | `{assignments: {name: category}, last_updated}` | user overrides |
| `dungeons.json` | `{category: [names]}` | flat, no `last_updated` |

**EncounterRecord** = `{id, timestamp, build_tag, notes, primary_target, player_class, overall:
StatBlock, first_60s: StatBlock}`.

> Presets (`default_target_assignments.json`, `dungeons.json`, `skill_settings.json`,
> `weapon_config.json`) ship bundled and are seeded into the data dir on first run — see
> [`backend/main.py:180`](../../backend/main.py) (`seed_presets`). User fight data starts empty.

## 4. WebSocket protocol (transport)

`ws://localhost:8765`. Frontend → backend: `{"command": <name>, ...}`. Backend → frontend:
`{"type": <name>, ...}`. Dispatch table + handlers in
[`dps_meter_server.py`](../../backend/dps_meter_server.py).

- **Init burst (9, on connect):** `get_config`, `get_encounters`, `get_saved_runs`,
  `get_skill_settings`, `get_weapon_config`, `get_target_assignments`, `get_default_targets`,
  `get_dungeons`, `get_encounter_history` — all must answer before tabs render.
- **Live broadcast:** a `stats` message every 0.5 s (interval from `config.broadcast_interval`),
  carrying the flattened stat shape + `party_status`.
- **Quirks:** `get_session_encounters` → aliased to `get_encounters`; `set_skill_weapon` → ignored
  (use `assign_skill` / `bulk_assign_skills`); `saved_runs` replies wrap the bare list as
  `{"type":"saved_runs_list","runs":[…]}`; an `error` type lets the frontend tell "thinking" from "dead".

The **party** wire protocol (member → room `post_fight`, room → members merged board) is documented
in [`workers/party/README.md`](../../workers/party/README.md) — see [04 — Party Worker](04-party-worker.md).
