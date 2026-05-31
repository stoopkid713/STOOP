"""Multi-client party simulator (dev tool, gitignored).

Mimic N party members hitting the LIVE Cloudflare room from ONE machine, fed by a real
combat log — so we can test the merged board + live hydration without a second PC.

Each simulated member parses the SAME combat log (via the real parser + PartyState) into a
per-target breakdown, then posts ``post_fight`` to the room in ROUNDS — each round a bigger
slice of the fight — to mimic T&L flushing the log in bursts at combat-exit (the live
hydration cadence). Members are scaled differently so they rank distinctly.

Watch it: open the real app (or the overlay) joined to the SAME party code, and you'll see
Bot1..BotN climb the board live alongside you.

Usage (with the venv python; create/join the party code in the app first):
  backend/.venv/Scripts/python.exe backend/tools/sim_party.py <PARTY_CODE>
      [--members 4] [--log PATH] [--rounds 5] [--delay 1.5] [--host wss://...]

If --log is omitted it auto-picks the newest TLCombatLog-*.txt under
%LOCALAPPDATA%\\TL\\Saved\\CombatLogs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import websockets

# Allow running from tools/ — put backend/ on the path for the shared modules.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from combat_log_parser import parse_line  # noqa: E402
from party_state import PartyState  # noqa: E402

DEFAULT_HOST = "wss://tldps-party.kyle-526.workers.dev"
FIGHT_TS = 1_700_000_000_000  # fixed encounter id so all rounds key to one fight


def find_default_log() -> Path | None:
    base = os.environ.get("LOCALAPPDATA", "")
    if not base:
        return None
    folder = Path(base) / "TL" / "Saved" / "CombatLogs"
    if not folder.is_dir():
        return None
    logs = sorted(folder.glob("TLCombatLog-*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    return logs[0] if logs else None


def base_targets(log_path: Path) -> list[dict]:
    """Parse the whole log into the post_fight targets[] shape (real parser + PartyState)."""
    ps = PartyState()
    ps.start_recording("SIM")
    n = 0
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            p = parse_line(line)
            if p is None:
                continue
            ps.record_hit(p["target"], p["damage"], p["is_crit"], p["is_heavy"], p["_timestamp"])
            n += 1
    res = ps.stop_recording()
    print(f"  parsed {n} hits -> {len(res['targets'])} targets, total {res['total_damage']:,}")
    return res["targets"]


def scaled(targets: list[dict], frac: float, mult: float) -> list[dict]:
    """A round slice: `frac` of the fight so far, member damage `mult`. dps ~ constant."""
    out = []
    for t in targets:
        out.append({
            "target": t["target"],
            "total_damage": int(t["total_damage"] * frac * mult),
            "dps": round(t["dps"] * mult, 1),
            "duration": round(t["duration"] * frac, 1),
            "hits": int(t["hits"] * frac),
            "crit_rate": t["crit_rate"],
            "heavy_rate": t["heavy_rate"],
        })
    return out


async def member(host: str, code: str, idx: int, targets: list[dict], rounds: int, delay: float):
    uid = f"sim{idx}"
    name = f"Bot{idx}"
    mult = round(1.0 - 0.15 * (idx - 1), 3)  # Bot1 hardest, descending
    url = f"{host}/party/{code}?user_id={uid}&username={name}&leader=0"
    try:
        async with websockets.connect(url, max_size=None) as ws:
            print(f"  {name} connected (x{mult})")
            for r in range(1, rounds + 1):
                frac = r / rounds
                await ws.send(json.dumps({"type": "post_fight", "fight_ts": FIGHT_TS,
                                          "targets": scaled(targets, frac, mult)}))
                await asyncio.sleep(delay)
            await asyncio.sleep(2.0)  # linger so the final board is visible
            try:
                await ws.send(json.dumps({"type": "leave"}))
            except Exception:
                pass
            print(f"  {name} done")
    except Exception as exc:
        print(f"  {name} error: {exc}", file=sys.stderr)


async def main_async(args) -> int:
    log_path = Path(args.log) if args.log else find_default_log()
    if not log_path or not log_path.is_file():
        print("No combat log found. Pass --log <path to a TLCombatLog-*.txt>.", file=sys.stderr)
        return 2
    print(f"log: {log_path}")
    targets = base_targets(log_path)
    if not targets:
        print("No DamageDone hits parsed from that log.", file=sys.stderr)
        return 2
    print(f"driving {args.members} members -> {args.host}/party/{args.code} "
          f"({args.rounds} rounds, {args.delay}s apart)")
    await asyncio.gather(*[
        member(args.host, args.code.upper(), i, targets, args.rounds, args.delay)
        for i in range(1, args.members + 1)
    ])
    print("done.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Simulate N party members against the live room.")
    ap.add_argument("code", help="party code to join (create/join it in the app first)")
    ap.add_argument("--members", type=int, default=4)
    ap.add_argument("--log", default="")
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--host", default=DEFAULT_HOST)
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
