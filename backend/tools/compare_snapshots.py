#!/usr/bin/env python3
"""Parity comparison harness for the TL-DPS-Meter rebuild.

Normalizes two JSON snapshots (old vs new backend output) and prints PASS or a
minimal diff. The big data stays inside this process — only the ~1KB verdict is
printed, so it never bloats an agent's context (token-optimization rule #3).

Usage:
    python compare_snapshots.py <expected.json> <actual.json> [--label NAME] [--round N]

Normalization (per the rebuild plan's table):
  - drop volatile keys: last_updated, time, first_hit, last_hit, timestamp, id
  - round all floats to N decimals (default 4) to absorb FP noise
  - sort lists of dicts that carry a 'name' key (skills, targets) before compare
  - ordered lists (rotation, top_hits) compared in place (deterministic order)
Exit code 0 = PASS, 1 = FAIL.
"""
import json
import sys
import argparse

VOLATILE = {"last_updated", "time", "first_hit", "last_hit", "timestamp", "id"}


def norm(o, rnd):
    if isinstance(o, bool):
        return o
    if isinstance(o, dict):
        return {k: norm(v, rnd) for k, v in o.items() if k not in VOLATILE}
    if isinstance(o, list):
        items = [norm(x, rnd) for x in o]
        if items and isinstance(items[0], dict) and "name" in items[0]:
            items = sorted(items, key=lambda d: str(d.get("name", "")))
        return items
    if isinstance(o, float):
        return round(o, rnd)
    return o


def diffs(a, b, path="", out=None, cap=40):
    if out is None:
        out = []
    if len(out) >= cap:
        return out
    if type(a) != type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        out.append(f"{path}: type {type(a).__name__} != {type(b).__name__} ({a!r} vs {b!r})")
        return out
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"{path}.{k}: missing in EXPECTED")
            elif k not in b:
                out.append(f"{path}.{k}: missing in ACTUAL")
            else:
                diffs(a[k], b[k], f"{path}.{k}", out, cap)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} != {len(b)}")
        for i in range(min(len(a), len(b))):
            diffs(a[i], b[i], f"{path}[{i}]", out, cap)
    else:
        if a != b:
            out.append(f"{path}: {a!r} != {b!r}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("expected")
    ap.add_argument("actual")
    ap.add_argument("--label", default="snapshot")
    ap.add_argument("--round", type=int, default=4)
    a = ap.parse_args()
    exp = norm(json.load(open(a.expected, encoding="utf-8")), a.round)
    act = norm(json.load(open(a.actual, encoding="utf-8")), a.round)
    d = diffs(exp, act)
    if not d:
        print(f"PASS [{a.label}] - normalized snapshots match")
        sys.exit(0)
    print(f"FAIL [{a.label}] - {len(d)} difference(s):")
    for line in d[:40]:
        print("  " + line)
    if len(d) > 40:
        print(f"  ...(+{len(d) - 40} more)")
    sys.exit(1)


if __name__ == "__main__":
    main()
