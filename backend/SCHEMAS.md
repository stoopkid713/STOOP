# Backend Data Schemas — Phase 0 Digest

*Authoritative, extracted from live JSON files + `samples/encounters_sample.json` (structure only, never read whole). This is the committed digest — later phases read THIS, not the 2MB disasm or 2.4MB sample. Live `stats` broadcast shape is captured empirically (see `fixtures/`), not reverse-engineered.*

> ⚠️ Corrections to `docs/` guesses are flagged **[CORRECTED]**.

---

## Stat block (the core shape — produced by `CombatStats.to_dict()`)

Used as `overall` and `first_60s` inside an encounter record, and (flattened, TBD) in the live `stats` broadcast.

```
{
  dps: float
  total_damage: int
  duration: float
  hit_count: int
  crit_rate: float          # percent, e.g. 42.7
  crit_damage: int
  heavy_rate: float
  heavy_damage: int
  crit_heavy_rate: float
  crit_heavy_damage: int
  skills:   list of SkillEntry
  top_hits: list of HitEntry        # top 10 by damage
  targets:  list of TargetEntry
  # first_60s block ALSO has:
  rotation:  list of HitEntry        # every hit, chronological
  gap_stats: GapStats
}
```

**SkillEntry:** `{ name:str, damage:int, hits:int, crits:int, heavies:int, crit_damage:int, heavy_damage:int, percent:float }`
**HitEntry:** `{ time:str, relative_time:float, skill:str, target:str, damage:int, is_crit:bool, is_heavy:bool, hit_type:str }`
**TargetEntry:** `{ name:str, damage:int, percent:float }`
**GapStats:** `{ total_dead_time:float, num_major_gaps:int, longest_gap:float, avg_time_between_hits:float, gaps:list }`

> **UNVERIFIED — capture from old `.exe`:** exact LIVE `stats` broadcast shape. Encounter records split `overall` vs `first_60s` into two blocks; the live broadcast is expected to be flatter with inline `_60s` fields (e.g. `damage_60s`, `dps_60s`). Confirm from `fixtures/gold_stats_stream.jsonl`.

---

## Encounter record (one item in `encounters.json` → `encounters[]`)

Produced by `create_encounter_record` / `build_encounter_dict`. Save/load uses this exactly.

```
{
  id: str
  timestamp: str
  build_tag: str            # default "Unnamed Build"
  notes: str
  primary_target: str
  player_class: str
  overall:   StatBlock      # full encounter (no rotation/gap_stats)
  first_60s: StatBlock      # + rotation[] + gap_stats{}
}
```

---

## The 8 JSON files (top-level shapes)

### `config.json` — 9 keys
`{ log_path:str, player_name:str, auto_detect_log:bool, broadcast_interval:float(0.5), hotkey_enabled:bool, hotkey:str("ctrl+tab"), hotkey_sound:bool, party_token:str, party_enabled:bool }`
+ `last_updated` stamped on save.

### `encounters.json`
`{ encounters: [EncounterRecord...], builds: [str...], last_updated:str|null }`

### `skill_settings.json` — **[CORRECTED: has a `skills` wrapper, NOT flat]**
`{ skills: { "<SkillName>": {cannot_crit:bool, cannot_heavy:bool}, ... }, last_updated:str }`

### `weapon_config.json` — **[CORRECTED: no `currentSkills` key — runtime-only]**
`{ skillAssignments: { "<SkillName>": "<weapon>" , ... }, last_updated:str }`
Weapon values are lowercase: `spear`, `wand`, `bow`, `staff`, `dagger`, `crossbow`, `greatsword`, `sword`, `orb`, `unassigned`.

### `dungeons.json` — **[CORRECTED: flat `{category: [names]}`, NOT `{dungeons:[...]}`]**
`{ "Co-op Dungeon":[str...], "Raid":[str...], "Field Boss":[str...], "Archboss":[str...], "Custom":[], "Guild Boss":[] }`

### `default_target_assignments.json` — **[CORRECTED: `{category: [names]}`, inverted vs user file]**
`{ archboss:[str...], field_boss:[str...], raid_boss:[str...], dungeon_boss:[str...], adds:[str...], other:[str...] }`
(293 names under `adds`.) Ships bundled, read-only.

### `target_assignments.json` — user overrides (name→category)
`{ assignments: { "<TargetName>": "<category>", ... }, last_updated:str }`

### `saved_runs.json` — empty `[]` live; item schema inferred from `save_run` payload
`{ runs: [ { id, run_name, dungeon_category, dungeon_name, dungeon_info, player_class, build_tag, contribution_percent:num|null, got_loot:bool, loot_item:str|null, encounters:[], stats:{} } ], last_updated }`
> UNVERIFIED: whether root is `{runs:[...]}` or bare `[]`. Confirm during Phase 2/3.

---

## Combat log grammar (input contract)

CSV, header line `CombatLogVersion,4` (→ skipped). Damage line, ≥10 comma fields:

| idx | field | type | notes |
|---|---|---|---|
| 0 | Timestamp | str | `YYYYMMDD-HH:MM:SS:mmm` |
| 1 | LogType | str | `DamageDone` |
| 2 | SkillName | str | may contain spaces |
| 3 | SkillId | str | numeric, not cast |
| 4 | Damage | int | |
| 5 | HitCritical | bool | `1`/`0` |
| 6 | HitDouble/Heavy | bool | `1`/`0` |
| 7 | HitType | str | `kMaxDamageByCriticalDecision` / `kNormalHit` / `kMinDamageByNormal` |
| 8 | CasterName | str | player filter |
| 9+ | TargetName | str | re-join `parts[9:]` on `,` |

<10 fields or parse error → `None`, skip. Player filter: `player_name=""` → all.

---

## Command-routing resolutions (from disasm grep)
- **`get_session_encounters`** — NO backend handler (0 disasm hits). Dead drift. New backend: alias to `get_encounters` (fix) or ignore (match-old). Decide in Phase 3.
- **`set_skill_weapon`** — NO backend handler. Real commands are `assign_skill` + `bulk_assign_skills`. Do not implement `set_skill_weapon`.
- **`merge_encounters`** — handled (dispatch @ disasm L21425). Response type confirmed in Phase 3 from handler body.

## Deferred to Phase 3 (needs the live old `.exe`, valid until 2026-06-25)
- Live `stats` broadcast exact shape → `fixtures/gold_stats_stream.jsonl`.
- The 9 init-burst response payloads → `fixtures/gold_init_responses.json`.
- Full `overall` (beyond-60s) timing parity via real-log replay (sample fixture covers first_60s exactly for damage/count/skills).
