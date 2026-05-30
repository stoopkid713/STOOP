#!/usr/bin/env python3
"""Extract a self-contained Phase 1 parity fixture from samples/encounters_sample.json.

The sample is real OLD-backend output, so it is ground truth. encounters[0].first_60s
contains both the input (rotation[] = parsed hits) and the expected aggregates
(everything else in the block). No old .exe needed for this fixture.

Produces (in backend/fixtures/):
  sample_input_hits.json  - the rotation hits, the INPUT fed into CombatStats in Phase 1
  sample_expected.json    - the first_60s stat block with rotation removed = expected to_dict()

NOTE: damage / hit_count / crit / heavy / skills / top_hits are EXACT.
Timing-derived fields (dps, duration, gap_stats) are only as precise as rotation's
0.1s relative_time; exact-timing parity comes from the live-exe replay in Phase 3.
"""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIX = os.path.join(BASE, "backend", "fixtures")
os.makedirs(FIX, exist_ok=True)

data = json.load(open(os.path.join(BASE, "samples", "encounters_sample.json"), encoding="utf-8"))
block = data["encounters"][0]["first_60s"]

hits = block["rotation"]
expected = {k: v for k, v in block.items() if k != "rotation"}

json.dump(hits, open(os.path.join(FIX, "sample_input_hits.json"), "w", encoding="utf-8"), indent=1)
json.dump(expected, open(os.path.join(FIX, "sample_expected.json"), "w", encoding="utf-8"), indent=1)

print("wrote sample_input_hits.json:", len(hits), "hits")
print("wrote sample_expected.json: keys =", list(expected.keys()))
print("  expected.total_damage =", expected["total_damage"])
print("  expected.hit_count    =", expected["hit_count"])
print("  expected.skills       =", len(expected["skills"]), "skills")
