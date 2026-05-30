"""Pure, deterministic damage-stats aggregation core.

The single source of truth for parity is the old backend's output: feeding the
recorded ``rotation`` hits of an encounter back through these builders must
reproduce that encounter's stat block exactly (after the parity normalizer).
See ``tests/test_stats_parity.py`` and ``tools/compare_snapshots.py``.

A "hit" is a plain dict with these keys (produced by ``combat_log_parser``):
    time:str  relative_time:float  skill:str  target:str
    damage:int  is_crit:bool  is_heavy:bool  hit_type:str

Nothing here does I/O, holds wall-clock state, or imports the server — so it is
trivially unit-testable and safe to call from any thread.
"""
from __future__ import annotations

from typing import Any

from constants import (
    GAP_DEAD_THRESHOLD,
    GAP_MAJOR_THRESHOLD,
    ROUND_DEAD_TIME,
    ROUND_DPS,
    ROUND_DURATION,
    ROUND_GAP_DURATION,
    ROUND_RATE,
    SIXTY_SECOND_WINDOW,
    TOP_HITS_LIMIT,
)

Hit = dict[str, Any]


def _rate(numerator: int, hit_count: int) -> float:
    """Percentage of hits, 1 dp. 0.0 when there are no hits (no ZeroDivision)."""
    if not hit_count:
        return 0.0
    return round(numerator / hit_count * 100, ROUND_RATE)


def _skills(hits: list[Hit], total_damage: int) -> list[dict]:
    """Per-skill aggregates, sorted by total damage descending.

    Matches the old backend: skill names are aggregated then ordered by damage
    (disasm L6666: ``sorted(skill_damage.keys(), key=..., reverse=True)``).
    Insertion order (first-seen) is the stable tiebreak.
    """
    agg: dict[str, dict] = {}
    for h in hits:
        s = agg.get(h["skill"])
        if s is None:
            s = agg[h["skill"]] = {
                "name": h["skill"],
                "damage": 0,
                "hits": 0,
                "crits": 0,
                "heavies": 0,
                "crit_damage": 0,
                "heavy_damage": 0,
            }
        dmg = h["damage"]
        s["damage"] += dmg
        s["hits"] += 1
        if h["is_crit"]:
            s["crits"] += 1
            s["crit_damage"] += dmg
        if h["is_heavy"]:
            s["heavies"] += 1
            s["heavy_damage"] += dmg

    skills = list(agg.values())
    for s in skills:
        s["percent"] = round(s["damage"] / total_damage * 100, ROUND_RATE) if total_damage else 0.0
    skills.sort(key=lambda s: s["damage"], reverse=True)
    return skills


def _targets(hits: list[Hit], total_damage: int) -> list[dict]:
    """Per-target damage share, sorted by damage descending (overall block only)."""
    agg: dict[str, dict] = {}
    for h in hits:
        t = agg.get(h["target"])
        if t is None:
            t = agg[h["target"]] = {"name": h["target"], "damage": 0}
        t["damage"] += h["damage"]
    targets = list(agg.values())
    for t in targets:
        t["percent"] = round(t["damage"] / total_damage * 100, ROUND_RATE) if total_damage else 0.0
    targets.sort(key=lambda t: t["damage"], reverse=True)
    return targets


def _top_hits(hits: list[Hit]) -> list[dict]:
    """Top-N hits by damage, passed through verbatim (stable sort keeps order on ties)."""
    ordered = sorted(hits, key=lambda h: h["damage"], reverse=True)[:TOP_HITS_LIMIT]
    return [dict(h) for h in ordered]


def _gap_stats(hits: list[Hit]) -> dict:
    """Inter-hit timing analysis, reproducing the old backend's gap loop exactly.

    For every consecutive pair a gap record ``{after_index, duration, at_time}``
    is built (durations rounded to 2 dp). Derived fields:
      - total_dead_time:       sum of (gap - 1.0) over gaps longer than 1.0s, 1 dp
      - num_major_gaps:        count of gap records with duration > 2.0s
      - longest_gap:           max gap duration (0 when no gaps)
      - avg_time_between_hits: mean gap duration (0 when no gaps)
      - gaps:                  ONLY the major gap records (> 2.0s)  <- the rest are
                               folded into the aggregates, not emitted (disasm L12300-12480).
    """
    gaps: list[dict] = []
    total_gap_time = 0.0
    if len(hits) > 1:
        for i in range(1, len(hits)):
            prev_t = hits[i - 1].get("relative_time", 0)
            curr_t = hits[i].get("relative_time", 0)
            gap = curr_t - prev_t
            gaps.append(
                {
                    "after_index": i - 1,
                    "duration": round(gap, ROUND_GAP_DURATION),
                    "at_time": round(prev_t, 1),
                }
            )
            if gap > GAP_DEAD_THRESHOLD:
                total_gap_time += gap - GAP_DEAD_THRESHOLD

    major = [g for g in gaps if g["duration"] > GAP_MAJOR_THRESHOLD]
    longest = round(max((g["duration"] for g in gaps), default=0), ROUND_GAP_DURATION)
    avg = round(sum(g["duration"] for g in gaps) / len(gaps), ROUND_GAP_DURATION) if gaps else 0
    return {
        "total_dead_time": round(total_gap_time, ROUND_DEAD_TIME),
        "num_major_gaps": len(major),
        "longest_gap": longest,
        "avg_time_between_hits": avg,
        "gaps": major,
    }


def build_stat_block(
    hits: list[Hit],
    *,
    with_targets: bool = False,
    with_rotation: bool = False,
    with_gap_stats: bool = False,
) -> dict:
    """Build one stat block from a list of hits (the shared core of every view).

    ``duration`` is the span of the supplied hits (last - first relative_time);
    callers that need a fixed window must pre-slice the hits. ``dps`` is
    ``total_damage / duration`` (0 when duration is 0).
    """
    total_damage = sum(h["damage"] for h in hits)
    hit_count = len(hits)
    crit_count = sum(1 for h in hits if h["is_crit"])
    heavy_count = sum(1 for h in hits if h["is_heavy"])
    crit_heavy_count = sum(1 for h in hits if h["is_crit"] and h["is_heavy"])

    if hits:
        duration = round(hits[-1]["relative_time"] - hits[0]["relative_time"], ROUND_DURATION)
    else:
        duration = 0.0
    dps = round(total_damage / duration, ROUND_DPS) if duration > 0 else 0.0

    block: dict[str, Any] = {
        "dps": dps,
        "total_damage": total_damage,
        "duration": duration,
        "hit_count": hit_count,
        "crit_rate": _rate(crit_count, hit_count),
        "crit_damage": sum(h["damage"] for h in hits if h["is_crit"]),
        "heavy_rate": _rate(heavy_count, hit_count),
        "heavy_damage": sum(h["damage"] for h in hits if h["is_heavy"]),
        "crit_heavy_rate": _rate(crit_heavy_count, hit_count),
        "crit_heavy_damage": sum(h["damage"] for h in hits if h["is_crit"] and h["is_heavy"]),
        "skills": _skills(hits, total_damage),
        "top_hits": _top_hits(hits),
    }
    if with_targets:
        block["targets"] = _targets(hits, total_damage)
    if with_rotation:
        block["rotation"] = [dict(h) for h in hits]
    if with_gap_stats:
        block["gap_stats"] = _gap_stats(hits)
    return block


def build_overall_block(hits: list[Hit]) -> dict:
    """The encounter-wide block: includes per-target share, no rotation/gap_stats."""
    return build_stat_block(hits, with_targets=True)


def build_first_60s_block(hits: list[Hit]) -> dict:
    """The first-60-seconds block: includes rotation + gap_stats, no targets.

    The caller passes the already-windowed hits (relative_time <= 60.0); this
    matches the recorded ``first_60s.rotation`` the old backend persists.
    """
    return build_stat_block(hits, with_rotation=True, with_gap_stats=True)


def slice_first_60s(hits: list[Hit]) -> list[Hit]:
    """Hits within the first 60s window (boundary inclusive)."""
    return [h for h in hits if h["relative_time"] <= SIXTY_SECOND_WINDOW]


class CombatStats:
    """Live accumulator wrapping the pure builders (used by the server in Phase 3+)."""

    def __init__(self) -> None:
        self.hits: list[Hit] = []

    def add_hit(self, hit: Hit) -> None:
        self.hits.append(hit)

    def reset(self) -> None:
        self.hits.clear()

    def overall(self) -> dict:
        return build_overall_block(self.hits)

    def first_60s(self) -> dict:
        return build_first_60s_block(slice_first_60s(self.hits))
