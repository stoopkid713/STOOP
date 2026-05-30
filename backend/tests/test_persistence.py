"""Phase 2 gate tests for persistence.py.

DoD covered here:
  * defaults returned when a file is absent (no crash);
  * round-trip identical minus ``last_updated`` for all 8 files;
  * ``samples/encounters_sample.json`` round-trips losslessly through the
    encounters load/save (strict, plus a normalized check via compare_snapshots);
  * atomic writes leave no ``.tmp`` behind and never partial-write;
  * ``saved_runs.json`` is a bare list on disk (no wrapper, no stamp).

All write tests use ``tmp_path`` — the real repo JSON files are only ever read.
"""

import json
from pathlib import Path

import pytest

import persistence as P
from compare_snapshots import norm, diffs  # reuse the gate's parity harness

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "samples" / "encounters_sample.json"

# (label, load, save, default, payload, stamps_last_updated, is_list)
CASES = [
    ("config", P.load_config, P.save_config, P.DEFAULT_CONFIG,
     {**P.DEFAULT_CONFIG, "player_name": "Tester", "log_path": "C:/logs"}, True, False),
    ("encounters", P.load_encounters, P.save_encounters, P.DEFAULT_ENCOUNTERS,
     {"encounters": [{"id": "e1", "timestamp": "2026-01-01T00:00:00",
                      "build_tag": "X", "notes": "n", "primary_target": "Boss",
                      "player_class": "Mage", "overall": {"dps": 1.5, "total_damage": 3},
                      "first_60s": {"dps": 1.5, "gap_stats": {"gaps": []}}}],
      "builds": ["X"]}, True, False),
    ("skill_settings", P.load_skill_settings, P.save_skill_settings, P.DEFAULT_SKILL_SETTINGS,
     {"skills": {"Abyssal Burst": {"cannot_crit": True, "cannot_heavy": True}}}, True, False),
    ("weapon_config", P.load_weapon_config, P.save_weapon_config, P.DEFAULT_WEAPON_CONFIG,
     {"skillAssignments": {"Abyssal Cleave": "spear", "Manaball": "wand"}}, True, False),
    ("dungeons", P.load_dungeons, P.save_dungeons, P.DEFAULT_DUNGEONS,
     {"Co-op Dungeon": ["A", "B"], "Raid": ["C"], "Custom": [], "Guild Boss": []}, False, False),
    ("default_targets", P.load_default_targets, P.save_default_targets, P.DEFAULT_DEFAULT_TARGETS,
     {"archboss": ["Tevent"], "adds": ["Goblin", "Orc"], "other": []}, False, False),
    ("target_assignments", P.load_target_assignments, P.save_target_assignments,
     P.DEFAULT_TARGET_ASSIGNMENTS,
     {"assignments": {"Goblin": "adds", "Tevent": "archboss"}}, True, False),
    ("saved_runs", P.load_saved_runs, P.save_saved_runs, [],
     [{"id": "r1", "run_name": "Run 1", "encounters": [], "stats": {},
       "got_loot": False, "loot_item": None}], False, True),
]
IDS = [c[0] for c in CASES]


def _strip_lu(obj):
    """Drop only the top-level ``last_updated`` (preserve nested id/timestamp)."""
    if isinstance(obj, dict):
        return {k: v for k, v in obj.items() if k != "last_updated"}
    return obj


# --- defaults when absent --------------------------------------------------
@pytest.mark.parametrize("label,load,save,default,payload,stamps,is_list", CASES, ids=IDS)
def test_default_when_file_absent(label, load, save, default, payload, stamps, is_list, tmp_path):
    got = load(tmp_path)  # nothing on disk
    assert got == default
    # returned default must be a fresh copy — mutating it must not poison the module
    if isinstance(got, dict):
        got["__scratch__"] = 1
    else:
        got.append("__scratch__")
    assert "__scratch__" not in load(tmp_path)


# --- round-trip identical minus last_updated -------------------------------
@pytest.mark.parametrize("label,load,save,default,payload,stamps,is_list", CASES, ids=IDS)
def test_round_trip_minus_last_updated(label, load, save, default, payload, stamps, is_list, tmp_path):
    save(payload, tmp_path)
    reloaded = load(tmp_path)
    assert _strip_lu(reloaded) == _strip_lu(payload)


# --- last_updated stamping policy -----------------------------------------
@pytest.mark.parametrize("label,load,save,default,payload,stamps,is_list", CASES, ids=IDS)
def test_stamp_policy(label, load, save, default, payload, stamps, is_list, tmp_path):
    save(payload, tmp_path)
    reloaded = load(tmp_path)
    if is_list:
        assert isinstance(reloaded, list)
        assert all("last_updated" not in r for r in reloaded if isinstance(r, dict))
    elif stamps:
        assert "last_updated" in reloaded and reloaded["last_updated"]
    else:
        assert "last_updated" not in reloaded


# --- input is never mutated by save ---------------------------------------
@pytest.mark.parametrize("label,load,save,default,payload,stamps,is_list", CASES, ids=IDS)
def test_save_does_not_mutate_input(label, load, save, default, payload, stamps, is_list, tmp_path):
    import copy
    snapshot = copy.deepcopy(payload)
    save(payload, tmp_path)
    assert payload == snapshot


# --- atomic write hygiene --------------------------------------------------
@pytest.mark.parametrize("label,load,save,default,payload,stamps,is_list", CASES, ids=IDS)
def test_atomic_no_tmp_left(label, load, save, default, payload, stamps, is_list, tmp_path):
    save(payload, tmp_path)
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == [], f"stray temp files: {leftovers}"
    # exactly one real json file, and it parses
    jsons = list(tmp_path.glob("*.json"))
    assert len(jsons) == 1
    json.loads(jsons[0].read_text(encoding="utf-8"))  # raises if partial-written


def test_atomic_overwrite_preserves_old_on_garbage(tmp_path):
    """A second save replaces the file wholesale, never appends/corrupts."""
    P.save_saved_runs([{"id": "a"}], tmp_path)
    P.save_saved_runs([{"id": "b"}, {"id": "c"}], tmp_path)
    assert P.load_saved_runs(tmp_path) == [{"id": "b"}, {"id": "c"}]


# --- corrupt file falls back to default (don't crash) ---------------------
def test_corrupt_dict_file_returns_default(tmp_path):
    (tmp_path / P.CONFIG_FILE).write_text("{ not json", encoding="utf-8")
    assert P.load_config(tmp_path) == P.DEFAULT_CONFIG


def test_corrupt_list_file_returns_empty(tmp_path):
    (tmp_path / P.SAVED_RUNS_FILE).write_text("not a list", encoding="utf-8")
    assert P.load_saved_runs(tmp_path) == []


def test_dict_where_list_expected_returns_empty(tmp_path):
    (tmp_path / P.SAVED_RUNS_FILE).write_text('{"runs": []}', encoding="utf-8")
    # the {runs:[]} envelope is WS-only; on disk a non-list means "use default"
    assert P.load_saved_runs(tmp_path) == []


# --- saved_runs is a BARE LIST on disk ------------------------------------
def test_saved_runs_written_as_bare_list(tmp_path):
    P.save_saved_runs([{"id": "r1"}], tmp_path)
    on_disk = json.loads((tmp_path / P.SAVED_RUNS_FILE).read_text(encoding="utf-8"))
    assert isinstance(on_disk, list)  # not {"runs": [...]}, not stamped
    assert on_disk == [{"id": "r1"}]


def test_empty_saved_runs_round_trips(tmp_path):
    P.save_saved_runs([], tmp_path)
    assert (tmp_path / P.SAVED_RUNS_FILE).read_text(encoding="utf-8").strip() == "[]"
    assert P.load_saved_runs(tmp_path) == []


# --- the DoD headline: encounters_sample.json lossless round-trip ----------
def test_encounters_sample_round_trips_losslessly(tmp_path):
    assert SAMPLE.exists(), f"missing fixture: {SAMPLE}"
    original = json.loads(SAMPLE.read_text(encoding="utf-8"))

    # seed the sample as the live encounters.json, load it, save it back out
    (tmp_path / P.ENCOUNTERS_FILE).write_text(SAMPLE.read_text(encoding="utf-8"),
                                              encoding="utf-8")
    loaded = P.load_encounters(tmp_path)

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    P.save_encounters(loaded, out_dir)
    reloaded = json.loads((out_dir / P.ENCOUNTERS_FILE).read_text(encoding="utf-8"))

    # strict: identical except the freshly stamped last_updated
    assert _strip_lu(reloaded) == _strip_lu(original)

    # and normalized, via the gate's own parity harness (reuse, not reimplement)
    assert diffs(norm(original, 4), norm(reloaded, 4)) == []


# --- every live repo file round-trips through its own pair -----------------
LIVE_FILES = [
    (P.CONFIG_FILE, P.load_config, P.save_config),
    (P.ENCOUNTERS_FILE, P.load_encounters, P.save_encounters),
    (P.SKILL_SETTINGS_FILE, P.load_skill_settings, P.save_skill_settings),
    (P.WEAPON_CONFIG_FILE, P.load_weapon_config, P.save_weapon_config),
    (P.DUNGEONS_FILE, P.load_dungeons, P.save_dungeons),
    (P.DEFAULT_TARGET_ASSIGNMENTS_FILE, P.load_default_targets, P.save_default_targets),
    (P.SAVED_RUNS_FILE, P.load_saved_runs, P.save_saved_runs),
]


@pytest.mark.parametrize("fname,load,save", LIVE_FILES, ids=[f[0] for f in LIVE_FILES])
def test_live_file_round_trips(fname, load, save, tmp_path):
    src = REPO_ROOT / fname
    if not src.exists():
        pytest.skip(f"live file not present: {fname}")
    (tmp_path / fname).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    loaded = load(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    save(loaded, out)
    reloaded = load(out)
    assert _strip_lu(reloaded) == _strip_lu(loaded)
