"""Combat-log line parser: raw Throne-and-Liberty CSV rows -> hit dicts.

Pure and deterministic. The grammar is documented in ``SCHEMAS.md`` and the
field indices live in ``constants.py``. ``relative_time`` is assigned by
``parse_log`` relative to the first accepted hit, matching the old backend.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from constants import (
    IDX_CASTER,
    IDX_CRIT,
    IDX_DAMAGE,
    IDX_HEAVY,
    IDX_HIT_TYPE,
    IDX_LOG_TYPE,
    IDX_SKILL,
    IDX_TARGET,
    IDX_TIMESTAMP,
    LOG_TYPE_DAMAGE,
    MIN_DAMAGE_FIELDS,
    ROUND_REL_TIME,
)

Hit = dict[str, Any]


def parse_timestamp(ts: str) -> datetime:
    """Parse ``YYYYMMDD-HH:MM:SS:mmm`` into a datetime (millis -> microseconds)."""
    date_part, time_part = ts.split("-", 1)
    year, month, day = int(date_part[0:4]), int(date_part[4:6]), int(date_part[6:8])
    hh, mm, ss, millis = time_part.split(":")
    return datetime(year, month, day, int(hh), int(mm), int(ss), int(millis) * 1000)


def _clock(ts: str) -> str:
    """Wall-clock ``HH:MM:SS`` portion of a timestamp (drops date + millis)."""
    time_part = ts.split("-", 1)[1]
    hh, mm, ss = time_part.split(":")[:3]
    return f"{hh}:{mm}:{ss}"


def parse_line(
    line: str,
    *,
    player_name: str = "",
    skill_settings: Optional[dict] = None,
) -> Optional[Hit]:
    """Parse a single log line into a partial hit (no ``relative_time`` yet).

    Returns ``None`` for: header/version lines, non-``DamageDone`` rows, rows with
    fewer than 10 fields, non-integer damage, or a caster that fails the
    ``player_name`` filter (empty filter accepts every caster).

    ``skill_settings`` applies the old backend's damage correction: a skill flagged
    ``cannot_crit`` / ``cannot_heavy`` has that flag forced False even if the log
    set it. The returned dict carries ``_timestamp`` (datetime) for the caller to
    compute ``relative_time``; ``parse_log`` strips it.
    """
    parts = line.rstrip("\n").rstrip("\r").split(",")
    if len(parts) < MIN_DAMAGE_FIELDS:
        return None
    if parts[IDX_LOG_TYPE] != LOG_TYPE_DAMAGE:
        return None

    try:
        damage = int(parts[IDX_DAMAGE])
    except (ValueError, IndexError):
        return None

    if player_name and parts[IDX_CASTER] != player_name:
        return None

    skill = parts[IDX_SKILL]
    is_crit = parts[IDX_CRIT] == "1"
    is_heavy = parts[IDX_HEAVY] == "1"

    if skill_settings:
        settings = skill_settings.get(skill)
        if settings:
            if settings.get("cannot_crit"):
                is_crit = False
            if settings.get("cannot_heavy"):
                is_heavy = False

    try:
        ts = parse_timestamp(parts[IDX_TIMESTAMP])
        clock = _clock(parts[IDX_TIMESTAMP])
    except (ValueError, IndexError):
        return None

    return {
        "_timestamp": ts,
        "time": clock,
        "skill": skill,
        "target": ",".join(parts[IDX_TARGET:]),
        "damage": damage,
        "is_crit": is_crit,
        "is_heavy": is_heavy,
        "hit_type": parts[IDX_HIT_TYPE],
    }


def relative_time(ts: datetime, start: datetime) -> float:
    """Seconds from ``start`` to ``ts``, rounded to 1 dp."""
    return round((ts - start).total_seconds(), ROUND_REL_TIME)


def finalize_hit(partial: Hit, start: datetime) -> Hit:
    """Turn a ``parse_line`` partial into a canonical hit: add relative_time, drop _timestamp."""
    return {
        "time": partial["time"],
        "relative_time": relative_time(partial["_timestamp"], start),
        "skill": partial["skill"],
        "target": partial["target"],
        "damage": partial["damage"],
        "is_crit": partial["is_crit"],
        "is_heavy": partial["is_heavy"],
        "hit_type": partial["hit_type"],
    }


def parse_log(
    lines,
    *,
    player_name: str = "",
    skill_settings: Optional[dict] = None,
) -> list[Hit]:
    """Parse an iterable of log lines into canonical hits with relative_time.

    The first accepted hit defines t=0; every hit's ``relative_time`` is measured
    from it. Returns hits in input (chronological) order.
    """
    hits: list[Hit] = []
    start: Optional[datetime] = None
    for line in lines:
        partial = parse_line(line, player_name=player_name, skill_settings=skill_settings)
        if partial is None:
            continue
        if start is None:
            start = partial["_timestamp"]
        hits.append(finalize_hit(partial, start))
    return hits
