"""Fix 2 — STATS PARITY test.

Feeds a deterministic synthetic hit-set (matching the sim_party crit-heavy-parity
scenario: 100 hits — 50 crits, 50 heavies, 25 crit-AND-heavy, 25 normal) through
the party recording path (PartyEncounter.record + results) and asserts the emitted
crit_rate / heavy_rate / crit_heavy_rate / crit_heavy_count MATCH the values that
combat_stats.build_stat_block produces on the same hit list.

Design notes:
- Deterministic: the hit list is built with an explicit pattern, no randomness.
- Minimal: only the stat-parity contract is tested — the rest of party_state is
  already covered by test_party_state.py.
- The hit dicts include a ``relative_time`` so build_stat_block can compute
  duration (though we only assert on the rate/count fields, not duration/dps).
- ``skill`` is required because build_stat_block calls _skills (and _adjusted uses
  it for skill-settings lookup). We use a single "Skill" name with no settings, so
  adjusted == raw and the test matches the no-settings party path.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from combat_stats import build_stat_block
from party_state import PartyEncounter


def _make_hits() -> list[dict]:
    """Build 100 hits with a repeating 4-cycle:
      idx % 4 == 0 → crit only          (25 total)
      idx % 4 == 1 → heavy only         (25 total)
      idx % 4 == 2 → crit AND heavy     (25 total)
      idx % 4 == 3 → normal             (25 total)

    This gives crit_count=50, heavy_count=50, crit_heavy_count=25 out of 100 hits
    → crit_rate=50.0, heavy_rate=50.0, crit_heavy_rate=25.0.
    """
    hits = []
    for i in range(100):
        r = i % 4
        is_crit = r in (0, 2)
        is_heavy = r in (1, 2)
        hits.append({
            "time": f"00:{i // 60:02d}:{i % 60:02d}",
            "relative_time": float(i),
            "skill": "Skill",
            "target": "Boss",
            "damage": 1000,
            "is_crit": is_crit,
            "is_heavy": is_heavy,
        })
    return hits


def _record_into_encounter(hits: list[dict]) -> PartyEncounter:
    """Feed hits into a fresh PartyEncounter using record() directly."""
    enc = PartyEncounter(encounter_id="test")
    base_time = datetime(2024, 1, 1, 0, 0, 0)
    for i, h in enumerate(hits):
        enc.record(
            target=h["target"],
            damage=h["damage"],
            is_crit=h["is_crit"],
            is_heavy=h["is_heavy"],
            hit_time=base_time + timedelta(seconds=i),
            skill=h["skill"],
            time=h["time"],
        )
    return enc


class TestPartyStatsParity:
    """Party scoreboard == solo meter for crit/heavy/crit-heavy stats."""

    def setup_method(self):
        self.hits = _make_hits()
        self.enc = _record_into_encounter(self.hits)
        self.results = self.enc.results()
        self.sb = build_stat_block(self.hits)
        # build_stat_block exposes crit_heavy_rate but not the raw count; compute it
        # directly (the same formula used in combat_stats.build_stat_block line 161).
        self.expected_crit_heavy_count = sum(
            1 for h in self.hits if h["is_crit"] and h["is_heavy"]
        )

    def test_single_target_in_results(self):
        """One target row for 'Boss'."""
        assert len(self.results["targets"]) == 1
        assert self.results["targets"][0]["target"] == "Boss"

    def test_crit_rate_matches_build_stat_block(self):
        row = self.results["targets"][0]
        assert row["crit_rate"] == self.sb["crit_rate"], (
            f"party crit_rate={row['crit_rate']} != solo {self.sb['crit_rate']}"
        )

    def test_heavy_rate_matches_build_stat_block(self):
        row = self.results["targets"][0]
        assert row["heavy_rate"] == self.sb["heavy_rate"], (
            f"party heavy_rate={row['heavy_rate']} != solo {self.sb['heavy_rate']}"
        )

    def test_crit_heavy_rate_present_and_correct(self):
        row = self.results["targets"][0]
        assert "crit_heavy_rate" in row, "crit_heavy_rate missing from party results"
        assert row["crit_heavy_rate"] == self.sb["crit_heavy_rate"], (
            f"party crit_heavy_rate={row['crit_heavy_rate']} != solo {self.sb['crit_heavy_rate']}"
        )

    def test_crit_heavy_count_present_and_correct(self):
        row = self.results["targets"][0]
        assert "crit_heavy_count" in row, "crit_heavy_count missing from party results"
        assert row["crit_heavy_count"] == self.expected_crit_heavy_count, (
            f"party crit_heavy_count={row['crit_heavy_count']} != expected {self.expected_crit_heavy_count}"
        )

    def test_absolute_values_match_scenario(self):
        """Validate the scenario produces the expected 50/50/25 rates."""
        row = self.results["targets"][0]
        assert row["crit_rate"] == 50.0
        assert row["heavy_rate"] == 50.0
        assert row["crit_heavy_rate"] == 25.0
        assert row["crit_heavy_count"] == 25

    def test_existing_fields_preserved(self):
        """Ensure the existing contract fields (total_damage, dps, duration, hits) are intact."""
        row = self.results["targets"][0]
        assert row["total_damage"] == 100_000
        assert row["hits"] == 100
        assert "dps" in row
        assert "duration" in row

    def test_parity_with_party_state(self):
        """End-to-end: feed through PartyState.record_hit and assert parity."""
        from party_state import PartyState

        ps = PartyState()
        ps.start_recording(party_code="test")
        base_time = datetime(2024, 1, 1, 0, 0, 0)
        for i, h in enumerate(self.hits):
            ps.record_hit(
                target=h["target"],
                damage=h["damage"],
                is_crit=h["is_crit"],
                is_heavy=h["is_heavy"],
                hit_time=base_time + timedelta(seconds=i),
                skill=h["skill"],
                time=h["time"],
            )
        results = ps.get_results()
        row = results["targets"][0]
        assert row["crit_rate"] == self.sb["crit_rate"]
        assert row["heavy_rate"] == self.sb["heavy_rate"]
        assert row["crit_heavy_rate"] == self.sb["crit_heavy_rate"]
        assert row["crit_heavy_count"] == self.expected_crit_heavy_count
