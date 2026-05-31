#!/usr/bin/env python
"""One-shot: carve index.html's single 14k-line <script> into source modules under src/js/,
wrapping each carved range in @inject:NAME / @end:NAME markers (same pattern as party_render.js).

SAFETY: this does NOT change any code. It copies contiguous line ranges into module files and
inserts marker COMMENT lines around those same ranges in index.html. The build's inliner later
replaces each region with its module's content — which is an exact copy, so a no-op. The script
asserts that (new index.html, with all inserted marker lines removed) == (original index.html),
byte for byte, and refuses to write anything if that invariant fails.

Run from backend/:  .venv/Scripts/python.exe tools/split_index.py [--apply]
Without --apply it's a dry run (reports + verifies, writes nothing).
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent      # repo root
INDEX = ROOT / "index.html"
JS_DIR = ROOT / "src" / "js"

# (module_name, start_line, end_line) — 1-based inclusive. Cut points are top-level `function`
# starts (verified clean boundaries); the party_render region (24434-24686) is deliberately
# skipped so its existing @inject markers stay untouched.
MODULES = [
    ("core-init",          11827, 12195),
    ("encounter-stats",    12196, 13137),
    ("log-export",         13138, 14242),
    ("targets-assign",     14243, 16038),
    ("saved-runs",         16039, 16940),
    ("run-builder",        16941, 18678),
    ("run-types-skills",   18679, 20361),
    ("class-insights",     20362, 22021),
    ("encounter-edit",     22022, 23223),
    ("party",              23224, 24433),
    # 24434-24686 = @inject:party_render region — left as-is
    ("member-detail-tabs", 24687, 25504),
    ("rotation-oracle",    25505, 26162),
]


def main(argv):
    apply = "--apply" in argv
    with open(INDEX, "r", encoding="utf-8", newline="") as fh:
        raw = fh.read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.splitlines(keepends=True)           # preserve exact endings
    n = len(lines)
    print(f"index.html: {n} lines, newline={'CRLF' if nl == chr(13)+chr(10) else 'LF'}")

    # sanity: boundaries must be clean (function start, body start, or post-party_render)
    for name, s, e in MODULES:
        first = lines[s - 1]
        ok = first.startswith("        function ") or s in (11827, 24687)
        print(f"  {name:20s} {s}-{e}  start={'OK' if ok else 'CHECK'}: {first.rstrip()[:60]}")

    # Build the new file. Walk original lines; when we enter a module's start, emit the
    # inject marker, the module body, the end marker; copy everything else verbatim.
    starts = {s: (name, e) for (name, s, e) in MODULES}
    ends = {e for (_, _, e) in MODULES}
    out = []
    modules_text = {}
    i = 1  # 1-based
    while i <= n:
        if i in starts:
            name, e = starts[i]
            inject = f"        /* @inject:{name} — GENERATED from /src/js/{name}.js by build.py; edit the SOURCE, not here */{nl}"
            endm = f"        /* @end:{name} */{nl}"
            body = lines[i - 1:e]                   # the module's exact lines
            modules_text[name] = "".join(body)
            out.append(inject)
            out.extend(body)
            out.append(endm)
            i = e + 1
        else:
            out.append(lines[i - 1])
            i += 1

    new_text = "".join(out)

    # SAFETY INVARIANT: strip every inserted marker line -> must equal the original byte-for-byte.
    marker_lines = set()
    for name, _, _ in MODULES:
        marker_lines.add(f"        /* @inject:{name} — GENERATED from /src/js/{name}.js by build.py; edit the SOURCE, not here */")
        marker_lines.add(f"        /* @end:{name} */")
    stripped = "".join(l for l in new_text.splitlines(keepends=True)
                       if l.rstrip("\r\n") not in marker_lines)
    if stripped != raw:
        print("\nABORT: reassembly is NOT byte-identical to the original. Writing nothing.", file=sys.stderr)
        # find first diff for diagnostics
        a, b = stripped, raw
        for k in range(min(len(a), len(b))):
            if a[k] != b[k]:
                print(f"  first diff at char {k}: {a[k-20:k+20]!r} vs {b[k-20:k+20]!r}", file=sys.stderr)
                break
        return 1
    print("\nVERIFY: strip-markers == original  -> byte-identical OK")
    print(f"modules: {len(modules_text)}  |  index.html {len(raw)} -> {len(new_text)} bytes (+markers only)")

    if not apply:
        print("\n(dry run) re-run with --apply to write src/js/*.js + rewrite index.html")
        return 0

    JS_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in modules_text.items():
        with open(JS_DIR / f"{name}.js", "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    with open(INDEX, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_text)
    print(f"\nWROTE {len(modules_text)} modules -> {JS_DIR}")
    print("REWROTE index.html with @inject markers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
