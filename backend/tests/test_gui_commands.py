"""GUI / system commands restored in the Phase-8 interactive pass.

`open_logs_folder` and `purge_log` were mis-bucketed as silent GUI no-ops in
Phase 3, but the old exe actually handled both (disasm L18610-18729). The
"Open Logs Folder" button doing nothing surfaced the regression. These tests
exercise the handlers directly (they are pure ``(server, msg) -> dict|None``
functions) with a tiny stub standing in for the server's ``_log_dir``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import dps_meter_server as srv


class _Stub:
    """Minimal stand-in: the two handlers only touch ``_log_dir()``."""

    def __init__(self, log_dir):
        self._dir = Path(log_dir) if log_dir is not None else None

    def _log_dir(self):
        return self._dir


# --- parity: no longer silently dropped ------------------------------------
def test_commands_are_registered_not_ignored():
    assert "open_logs_folder" in srv.HANDLERS
    assert "purge_log" in srv.HANDLERS
    assert "open_logs_folder" not in srv.SILENTLY_IGNORED
    assert "purge_log" not in srv.SILENTLY_IGNORED


# --- open_logs_folder ------------------------------------------------------
def test_open_logs_folder_opens_existing_dir(tmp_path, monkeypatch):
    calls = []
    # The handler imports `os`/`subprocess` locally, but they are the same module
    # objects, so patching them here intercepts the real call (no Explorer window).
    if sys.platform.startswith("win"):
        monkeypatch.setattr(os, "startfile", lambda p: calls.append(p),
                            raising=False)
    else:
        import subprocess
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a))

    result = srv._h_open_logs_folder(_Stub(tmp_path), {})
    assert result is None              # old exe sends NO reply on success
    assert len(calls) == 1            # platform open invoked exactly once


def test_open_logs_folder_missing_dir_errors(tmp_path):
    missing = tmp_path / "does_not_exist"
    result = srv._h_open_logs_folder(_Stub(missing), {})
    assert result == {"type": "error", "message": "Logs folder not found"}


def test_open_logs_folder_none_dir_errors():
    result = srv._h_open_logs_folder(_Stub(None), {})
    assert result == {"type": "error", "message": "Logs folder not found"}


# --- purge_log -------------------------------------------------------------
def test_purge_log_truncates_active_file(tmp_path):
    older = tmp_path / "CombatLog_2026-01-01.txt"
    active = tmp_path / "CombatLog_2026-01-02.txt"  # newest by name = active
    older.write_text("old data\n", encoding="utf-8")
    active.write_text("line1\nline2\nline3\n", encoding="utf-8")

    result = srv._h_purge_log(_Stub(tmp_path), {})
    assert result == {"type": "log_purged"}
    # Only the active (newest) file is cleared; the older one is untouched.
    assert active.read_text(encoding="utf-8") == ""
    assert older.read_text(encoding="utf-8") == "old data\n"


def test_purge_log_no_files_errors(tmp_path):
    result = srv._h_purge_log(_Stub(tmp_path), {})
    assert result == {"type": "error", "message": "No log file found to purge"}


def test_purge_log_missing_dir_errors(tmp_path):
    result = srv._h_purge_log(_Stub(tmp_path / "nope"), {})
    assert result == {"type": "error", "message": "No log file found to purge"}


# --- data lifecycle: open_data_folder / reset_data -------------------------
class _DataStub:
    """Stand-in exposing only ``data_dir`` (what the data commands touch)."""

    def __init__(self, data_dir):
        self.data_dir = str(data_dir)


def test_data_commands_registered():
    assert "open_data_folder" in srv.HANDLERS
    assert "reset_data" in srv.HANDLERS
    assert "open_data_folder" not in srv.SILENTLY_IGNORED
    assert "reset_data" not in srv.SILENTLY_IGNORED


def test_open_data_folder_opens_dir(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(srv, "_open_in_file_browser", lambda p: calls.append(p))
    result = srv._h_open_data_folder(_DataStub(tmp_path), {})
    assert result is None                     # no reply on success
    assert calls == [str(tmp_path)]


def test_open_data_folder_missing_dir_errors(tmp_path):
    result = srv._h_open_data_folder(_DataStub(tmp_path / "nope"), {})
    assert result == {"type": "error", "message": "Data folder not found"}


def test_reset_data_clears_encounters_and_runs(tmp_path):
    import persistence as p

    p.save_encounters({"encounters": [{"id": "x"}], "builds": ["B"]}, str(tmp_path))
    p.save_saved_runs([{"run_id": "r"}], str(tmp_path))
    # a preset/setting that must SURVIVE the reset
    p.save_skill_settings({"skills": {"Fireball": {"cannot_crit": True}}}, str(tmp_path))

    result = srv._h_reset_data(_DataStub(tmp_path), {})
    assert result == {"type": "data_reset"}
    enc = p.load_encounters(str(tmp_path))
    assert enc["encounters"] == [] and enc["builds"] == []  # cleared (last_updated stamp ok)
    assert p.load_saved_runs(str(tmp_path)) == []
    # settings are intentionally preserved (reset only clears fight data)
    assert p.load_skill_settings(str(tmp_path))["skills"] == {"Fireball": {"cannot_crit": True}}


# --- save_encounter duplicate guard (double-connected frontend) -------------
from datetime import datetime  # noqa: E402


def _mk_partial(dmg, skill="Star Destroyer", target="Practice Dummy"):
    return {"_timestamp": datetime(2026, 5, 30, 17, 0, 0), "time": "17:00:00",
            "skill": skill, "target": target, "damage": dmg,
            "is_crit": False, "is_heavy": False, "hit_type": "normal"}


def test_double_save_encounter_is_deduped(tmp_path):
    """Two save_encounter calls for the same buffer moments apart (the twin-runs
    bug) collapse to ONE stored encounter; the second reuses the first."""
    import persistence as p

    server = srv.DPSMeterServer(tmp_path, port=0)
    for d in (100, 200, 300):
        server.stats.add_partial(_mk_partial(d))

    r1 = srv._h_save_encounter(server, {"build_tag": "__sq_a__"})
    r2 = srv._h_save_encounter(server, {"build_tag": "__sq_b__"})  # twin, ms later

    encs = p.load_encounters(str(tmp_path)).get("encounters", [])
    assert len(encs) == 1                                   # second deduped
    assert r2["encounter"]["id"] == r1["encounter"]["id"]   # reused the first


def test_distinct_saves_are_not_deduped(tmp_path):
    """A genuinely different result (buffer changed) still saves separately."""
    import persistence as p

    server = srv.DPSMeterServer(tmp_path, port=0)
    server.stats.add_partial(_mk_partial(100))
    srv._h_save_encounter(server, {"build_tag": "A"})
    server.stats.add_partial(_mk_partial(999))              # buffer changed
    srv._h_save_encounter(server, {"build_tag": "B"})

    encs = p.load_encounters(str(tmp_path)).get("encounters", [])
    assert len(encs) == 2


# --- get_suggested_names (F4) ----------------------------------------------
class _NameStub:
    """Stand-in exposing the two attributes _h_get_suggested_names touches."""

    def __init__(self, player_name="", log_dir=None):
        self.config = {"player_name": player_name}
        self._dir = Path(log_dir) if log_dir is not None else None

    def _log_dir(self):
        return self._dir


def test_get_suggested_names_registered():
    assert "get_suggested_names" in srv.HANDLERS


def test_get_suggested_names_prefers_configured_name(tmp_path):
    res = srv._h_get_suggested_names(_NameStub(player_name="Hero", log_dir=tmp_path), {})
    assert res["type"] == "suggested_names"
    assert res["names"][0] == "Hero"   # configured name is the primary candidate


def test_get_suggested_names_dominant_caster_from_log(tmp_path):
    fmt = "20260104-01:00:46:100,DamageDone,Void Slash,123,{dmg},0,0,kNormalHit,{caster},Dummy"
    rows = [fmt.format(dmg=10000, caster="BigDPS") for _ in range(5)]
    rows.append(fmt.format(dmg=100, caster="Tinydps"))
    (tmp_path / "CombatLog_2026-01-04.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
    res = srv._h_get_suggested_names(_NameStub(player_name="", log_dir=tmp_path), {})
    assert res["names"], "expected a suggested name from the log"
    assert res["names"][0] == "BigDPS"  # highest total-damage caster wins


# --- saved-run IDs are unique (#22) ----------------------------------------
def test_save_run_ids_are_unique(tmp_path):
    """Two runs saved in the same wall-clock second must get distinct ids.

    Regression (#22): run_id was strftime('%Y%m%d_%H%M%S') at 1s resolution with
    no dedup, so back-to-back saves collided on one id.
    """
    import persistence as p

    server = srv.DPSMeterServer(tmp_path, port=0)
    r1 = srv._h_save_run(server, {"run_name": "A"})
    r2 = srv._h_save_run(server, {"run_name": "B"})
    assert r1["run_id"] != r2["run_id"]

    ids = [r["id"] for r in p.load_saved_runs(str(tmp_path))]
    assert len(ids) == len(set(ids)) == 2  # both persisted, no collision


# --- update_encounter on a bad id errors, no phantom write (#27) ------------
def test_update_encounter_bad_id_errors_without_save(tmp_path, monkeypatch):
    """Updating a non-existent encounter id returns an error and does NOT write.

    Regression (#27): the handler returned ``encounter: null`` (looks like a
    success) AND still re-saved the file even though nothing matched.
    """
    import persistence as p

    server = srv.DPSMeterServer(tmp_path, port=0)
    saved = {"n": 0}
    real_save = p.save_encounters
    def _counting_save(data, data_dir):
        saved["n"] += 1
        return real_save(data, data_dir)
    monkeypatch.setattr(p, "save_encounters", _counting_save)

    res = srv._h_update_encounter(server, {"encounter_id": "does-not-exist", "notes": "x"})
    assert res["type"] == "error"          # not a phantom "encounter_updated"
    assert res.get("encounter") is None
    assert saved["n"] == 0                  # no no-op write on a miss


# --- load_encounter_data freezes the live merge (#20) ----------------------
def test_load_encounter_data_freezes_live_buffer(tmp_path, monkeypatch):
    """Loading a saved encounter must STOP the watcher from merging new live hits into the
    loaded historical buffer.

    Regression (#20): the handler replaced s.stats with the viewed encounter's hits but never
    updated reset_after_timestamp, so the watcher kept folding live combat into that buffer —
    corrupting the live view (and any follow-up save). The fix mirrors _h_reset: set the cutoff
    to now and skip the file backlog.
    """
    server = srv.DPSMeterServer(tmp_path, port=0)
    assert server.reset_after_timestamp is None          # nothing frozen yet

    monkeypatch.setattr(server, "_active_log_file", lambda: tmp_path / "log.txt")
    monkeypatch.setattr(srv.encounter_scan, "parse_encounter_details",
                        lambda *a, **k: {"dps": 1, "total_damage": 30})
    monkeypatch.setattr(srv.encounter_scan, "parse_encounter_hits", lambda *a, **k: [])

    class _FakeWatcher:
        def __init__(self): self.skipped = False
        def skip_to_end(self): self.skipped = True
    server.watcher = _FakeWatcher()

    res = srv._h_load_encounter_data(
        server, {"target_name": "Boss", "start_time": "2026-05-30T17:00:00"})

    assert res["type"] == "encounter_loaded"
    assert server.reset_after_timestamp is not None       # cutoff now set -> live merge frozen
    assert server.watcher.skipped is True                 # file backlog skipped, like _h_reset
