"""Phase 1 parity gate: feeding an encounter's recorded rotation back through the
stats core must reproduce the old backend's persisted first_60s block exactly.

Ground truth comes from ``samples/encounters_sample.json`` (real old-backend
output), split by ``tools/build_sample_fixture.py`` into:
    fixtures/sample_input_hits.json  -> the rotation (INPUT)
    fixtures/sample_expected.json    -> first_60s minus rotation (EXPECTED)

Comparison uses the project's own parity normalizer (drop volatile keys, round
floats, sort name-keyed lists) so this test and ``compare_snapshots.py`` agree.
"""
import json
import os

from combat_stats import build_first_60s_block
from compare_snapshots import diffs, norm

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(BACKEND, "fixtures")


def _load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


def test_first_60s_block_matches_old_backend():
    hits = _load("sample_input_hits.json")
    expected = _load("sample_expected.json")

    block = build_first_60s_block(hits)
    # The expected fixture has rotation stripped (it is the INPUT); strip ours to match.
    block.pop("rotation", None)

    d = diffs(norm(expected, 4), norm(block, 4))
    assert not d, "first_60s parity diffs:\n  " + "\n  ".join(d[:40])


def test_headline_numbers_are_exact():
    """Spot-check the high-value aggregates independently of the normalizer."""
    hits = _load("sample_input_hits.json")
    block = build_first_60s_block(hits)
    assert block["total_damage"] == 11773741
    assert block["hit_count"] == 1763
    assert block["crit_damage"] == 4586052
    assert block["duration"] == 60.0
    assert block["dps"] == 196229.0
    assert block["crit_rate"] == 34.4
    assert block["heavy_rate"] == 27.5
    assert block["gap_stats"]["longest_gap"] == 0.6
    assert block["gap_stats"]["num_major_gaps"] == 0
    assert block["gap_stats"]["gaps"] == []


def test_skills_sorted_by_damage_desc():
    hits = _load("sample_input_hits.json")
    skills = build_first_60s_block(hits)["skills"]
    damages = [s["damage"] for s in skills]
    assert damages == sorted(damages, reverse=True)
    assert skills[0]["name"] == "Curse Explosion"
