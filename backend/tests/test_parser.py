"""Unit tests for the combat-log parser: line grammar, hit-type flags, filtering,
target re-join, and relative_time assignment."""
from datetime import datetime

from combat_log_parser import parse_line, parse_log, parse_timestamp

# A well-formed damage row template; index map (SCHEMAS.md):
# 0 ts | 1 type | 2 skill | 3 skillId | 4 dmg | 5 crit | 6 heavy | 7 hitType | 8 caster | 9+ target
CRIT = "kMaxDamageByCriticalDecision"
NORMAL = "kNormalHit"


def row(ts="20260104-01:00:46:100", skill="Void Slash", dmg="1000", crit="0",
        heavy="0", hit_type=NORMAL, caster="Hero", target="Practice Dummy"):
    return f"{ts},DamageDone,{skill},123,{dmg},{crit},{heavy},{hit_type},{caster},{target}"


def test_parse_timestamp():
    ts = parse_timestamp("20260104-01:02:03:456")
    assert ts == datetime(2026, 1, 4, 1, 2, 3, 456000)


def test_normal_hit():
    h = parse_line(row())
    assert h["skill"] == "Void Slash"
    assert h["damage"] == 1000
    assert h["is_crit"] is False
    assert h["is_heavy"] is False
    assert h["hit_type"] == NORMAL
    assert h["time"] == "01:00:46"
    assert h["target"] == "Practice Dummy"


def test_crit_heavy_flags():
    crit = parse_line(row(crit="1", hit_type=CRIT))
    assert crit["is_crit"] is True and crit["is_heavy"] is False
    heavy = parse_line(row(heavy="1"))
    assert heavy["is_crit"] is False and heavy["is_heavy"] is True
    both = parse_line(row(crit="1", heavy="1", hit_type=CRIT))
    assert both["is_crit"] is True and both["is_heavy"] is True


def test_header_and_short_lines_skipped():
    assert parse_line("CombatLogVersion,4") is None
    assert parse_line("") is None
    assert parse_line("20260104-01:00:46:100,DamageDone,Skill,1,5") is None  # <10 fields


def test_non_damage_row_skipped():
    assert parse_line("20260104-01:00:46:100,BuffApplied,Haste,1,0,0,0,kNormalHit,Hero,Self") is None


def test_non_integer_damage_skipped():
    assert parse_line(row(dmg="NaN")) is None


def test_player_filter():
    assert parse_line(row(caster="Hero"), player_name="Hero") is not None
    assert parse_line(row(caster="Someone"), player_name="Hero") is None
    # empty filter accepts any caster
    assert parse_line(row(caster="Anyone"), player_name="") is not None


def test_target_with_comma_is_rejoined():
    h = parse_line(row(target="Big, Scary Boss"))
    assert h["target"] == "Big, Scary Boss"


def test_skill_settings_correction():
    settings = {"Void Slash": {"cannot_crit": True, "cannot_heavy": False}}
    h = parse_line(row(crit="1", heavy="1", hit_type=CRIT), skill_settings=settings)
    assert h["is_crit"] is False  # forced off
    assert h["is_heavy"] is True  # untouched


def test_parse_log_assigns_relative_time():
    lines = [
        "CombatLogVersion,4",
        row(ts="20260104-01:00:46:000", dmg="100"),
        row(ts="20260104-01:00:46:500", dmg="200"),
        row(ts="20260104-01:00:48:000", dmg="300"),
    ]
    hits = parse_log(lines)
    assert [h["relative_time"] for h in hits] == [0.0, 0.5, 2.0]
    assert [h["damage"] for h in hits] == [100, 200, 300]
    assert all("_timestamp" not in h for h in hits)
