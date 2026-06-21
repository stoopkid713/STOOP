"""Whole-folder combat-log ingest (#43) — captures historical/rolled logs, not just
the newest file. Self-contained (no gold fixtures), so it always runs."""
from __future__ import annotations

from pathlib import Path

import encounter_scan
import dps_meter_server as srv

_HDR = "CombatLogVersion,4\n"
_ASSIGNS = {"assignments": {}}


def _line(ts: str, dmg: int, target: str) -> str:
    # timestamp,DamageDone,skill,skillId,damage,is_crit,is_heavy,hit_type,caster,target
    return f"20260101-{ts},DamageDone,Slash,1,{dmg},0,0,kNormalHit,Hero,{target}"


def _write_log(path: Path, target: str, hour: str, dmg: int = 5000) -> None:
    path.write_text(
        _HDR + "\n".join(_line(f"{hour}:00:0{i}:000", dmg, target) for i in range(3)) + "\n",
        encoding="utf-8")


def test_folder_ingest_captures_all_files(tmp_path):
    """Two rolled logs, each a distinct boss — both surface (the latest-file-only path
    would miss the older one)."""
    _write_log(tmp_path / "CombatLog_a.txt", "BossA", "10")
    _write_log(tmp_path / "CombatLog_b.txt", "BossB", "11")

    folder = encounter_scan.parse_encounters_from_folder(tmp_path, _ASSIGNS)
    names = {e["target_name"] for e in folder}
    assert "BossA" in names and "BossB" in names            # both rolled logs captured

    single = encounter_scan.parse_encounters_from_log(tmp_path / "CombatLog_a.txt", _ASSIGNS)
    assert {e["target_name"] for e in single} == {"BossA"}  # baseline: one file = one boss


def test_folder_ingest_sorted_recent_first(tmp_path):
    _write_log(tmp_path / "CombatLog_a.txt", "BossA", "10")
    _write_log(tmp_path / "CombatLog_b.txt", "BossB", "11")  # later end_time
    folder = encounter_scan.parse_encounters_from_folder(tmp_path, _ASSIGNS)
    assert folder[0]["target_name"] == "BossB"              # most recent first


def test_folder_ingest_missing_dir(tmp_path):
    assert encounter_scan.parse_encounters_from_folder(tmp_path / "nope", _ASSIGNS) == []


def test_encounter_history_whole_folder_is_optin(tmp_path):
    """Default is unchanged (newest file only); whole_folder=True opts into the folder."""
    _write_log(tmp_path / "CombatLog_a.txt", "BossA", "10")
    _write_log(tmp_path / "CombatLog_b.txt", "BossB", "11")
    server = srv.DPSMeterServer(tmp_path, port=0)
    server.config = {**server.config, "log_path": str(tmp_path)}

    default = {e["target_name"] for e in server._encounter_history()}
    full = {e["target_name"] for e in server._encounter_history(whole_folder=True)}
    assert default == {"BossB"}                              # active (newest) file only
    assert {"BossA", "BossB"} <= full                        # opt-in captures both
