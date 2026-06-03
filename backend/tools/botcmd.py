"""botcmd.py — Interactive commandable party-bot harness for TL-DPS-Meter testing.

Holds N persistent WebSocket bot connections to a room and executes typed
commands on demand against the live party worker.  Fire-and-forget is gone;
every action is explicit.

Usage:
  backend/.venv/Scripts/python.exe backend/tools/botcmd.py [CODE] [--members N]
      [--host wss://tldps-party.kyle-526.workers.dev]

  # Local wrangler dev:
  backend/.venv/Scripts/python.exe backend/tools/botcmd.py TESTBOT --members 3 \\
      --host wss://127.0.0.1:8787

Commands (REPL):
  room <CODE>             — set/switch room (new connections use this code)
  add <N>                 — connect N more bots (join only, no auto-post)
  drop <id|all>           — disconnect bot(s)
  dmg <id|all> [boss] [amount]   — post ONE damage fight
  final <id|all> [boss] [amount] — post final fight + final_detail
  leader <id>             — transfer leader crown to bot <id>
  kick <targetId>         — leader kicks a user_id from the room
  reset                   — leader sends reset_roster
  clear                   — leader sends clear
  list / status           — show connected bots + last room snapshot
  help                    — show commands
  quit / exit             — drop all bots and exit

Bot IDs are 1-based sequential integers shown in `list`.  user_id on the wire
is "bot<N>" so the room and obs_rooms see them as botN.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Optional

# Allow running from tools/ — put backend/ on the path for shared modules.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from combat_stats import _skills as _agg_skills, build_stat_block  # noqa: E402
    _HAS_COMBAT_STATS = True
except ImportError:
    _HAS_COMBAT_STATS = False
    print("[warn] combat_stats not available — detail blocks will be minimal", file=sys.stderr)

try:
    import websockets                                       # noqa: E402
    _HAS_WS = True
except ImportError:
    _HAS_WS = False

DEFAULT_HOST = "wss://tldps-party.kyle-526.workers.dev"
DEFAULT_BOSS = "Tevent"
DEFAULT_DAMAGE = 500_000
DEFAULT_DURATION = 60.0
DEFAULT_HITS = 300


# ---------------------------------------------------------------------------
# Protocol helpers — imported/mirrored from sim_party.py
# ---------------------------------------------------------------------------

def _post_fight_frame(
    *,
    fight_ts: int,
    targets: list[dict],
    skills: Optional[list[dict]] = None,
    rotation: Optional[list[dict]] = None,
    final: bool = False,
) -> dict:
    """v2 post_fight envelope. Mirrors sim_party._post_fight_frame (sim_party.py:96)."""
    summary = {
        "total_damage": sum(t.get("total_damage", 0) for t in targets),
        "duration": max((t.get("duration", 0) for t in targets), default=0),
    }
    return {
        "type": "post_fight",
        "v": 2,
        "fight_ts": fight_ts,
        "encounter_id": str(fight_ts),
        "targets": targets,
        "summary": summary,
        "skills": skills,
        "rotation": rotation,
        "final": final,
    }


def _final_detail_frame(*, encounter_id: str, detail: dict) -> dict:
    """final_detail frame. Mirrors sim_party._final_detail_frame (sim_party.py:138)."""
    return {
        "type": "final_detail",
        "encounter_id": encounter_id,
        "detail": detail,
    }


def _make_synthetic_hits(
    n_hits: int = 100,
    *,
    total_damage: int = DEFAULT_DAMAGE,
    skill_name: str = "Skill",
    boss_name: str = DEFAULT_BOSS,
    fight_duration_s: float = DEFAULT_DURATION,
) -> list[dict]:
    """Synthetic hit list. Mirrors sim_party._make_synthetic_hits (sim_party.py:168)."""
    hits = []
    per_hit_dmg = total_damage // n_hits
    for i in range(n_hits):
        rel_t = round(i * fight_duration_s / n_hits, 1)
        idx = i % 4
        is_crit = idx in (1, 3)
        is_heavy = idx in (2, 3)
        hits.append({
            "time": f"00:{int(rel_t // 60):02d}:{int(rel_t % 60):02d}",
            "relative_time": rel_t,
            "skill": skill_name,
            "target": boss_name,
            "damage": per_hit_dmg,
            "is_crit": is_crit,
            "is_heavy": is_heavy,
            "hit_type": "DamageDone",
        })
    return hits


def _mb_targets(boss: str, total_damage: int) -> list[dict]:
    """Build a minimal targets[] row. Mirrors sim_party._mb_targets (sim_party.py:560)."""
    return [
        {
            "target": boss,
            "total_damage": total_damage,
            "dps": round(total_damage / DEFAULT_DURATION, 1),
            "duration": DEFAULT_DURATION,
            "hits": DEFAULT_HITS,
            "crit_rate": 40.0,
            "heavy_rate": 18.0,
            "crit_heavy_rate": 8.0,
        }
    ]


def _build_detail(boss: str, total_damage: int) -> dict:
    """Build detail block for final_detail. Uses combat_stats when available."""
    hits = _make_synthetic_hits(100, total_damage=total_damage, boss_name=boss)
    if _HAS_COMBAT_STATS:
        block = build_stat_block(hits, with_rotation=True)
        skills = _agg_skills(hits, block["total_damage"])
        target_row = {
            "target": boss,
            "total_damage": block["total_damage"],
            "dps": block["dps"] if block["duration"] > 0 else round(total_damage / DEFAULT_DURATION, 1),
            "duration": DEFAULT_DURATION,
            "hits": 100,
            "crit_rate": block["crit_rate"],
            "heavy_rate": block["heavy_rate"],
            "crit_heavy_rate": block["crit_heavy_rate"],
        }
        return {
            "targets": [target_row],
            "skills": skills,
            "total_damage": block["total_damage"],
            "duration": DEFAULT_DURATION,
            "rotation": block.get("rotation"),
        }
    else:
        # Minimal detail when combat_stats unavailable
        tgt = _mb_targets(boss, total_damage)[0]
        return {
            "targets": [tgt],
            "skills": [],
            "total_damage": total_damage,
            "duration": DEFAULT_DURATION,
            "rotation": None,
        }


# ---------------------------------------------------------------------------
# Bot — one persistent WebSocket connection
# ---------------------------------------------------------------------------

class Bot:
    """Represents one persistent bot WebSocket connection."""

    def __init__(self, bot_id: int, host: str, code: str):
        self.bot_id = bot_id          # 1-based, shown in UI
        self.user_id = f"bot{bot_id}"
        self.username = f"BotCmd{bot_id}"
        self.host = host
        self.code = code
        self.ws = None                # websockets.WebSocketClientProtocol
        self.connected = False
        self.is_leader = False        # local mirror of room leader state
        self._reader_task: Optional[asyncio.Task] = None
        # Room snapshot — updated by incoming broadcasts
        self.last_roster: list[dict] = []
        self.last_encounters: list[dict] = []
        self.last_scoreboard: Optional[dict] = None
        self.last_welcome: Optional[dict] = None

    @property
    def url(self) -> str:
        leader_flag = "1" if self.is_leader else "0"
        return (
            f"{self.host}/party/{self.code}"
            f"?user_id={self.user_id}&username={self.username}&leader={leader_flag}"
        )

    async def connect(self) -> None:
        """Open the WebSocket connection and start reading."""
        if self.connected:
            return
        self.ws = await websockets.connect(self.url, max_size=None)
        self.connected = True
        self._reader_task = asyncio.create_task(self._read_loop())

    async def disconnect(self) -> None:
        """Close the connection cleanly."""
        self.connected = False
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
            self._reader_task = None
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None

    async def send(self, msg: dict) -> None:
        """Send a JSON message to the room."""
        if not self.connected or self.ws is None:
            raise RuntimeError(f"Bot {self.bot_id} is not connected")
        await self.ws.send(json.dumps(msg))

    async def _read_loop(self) -> None:
        """Background reader — handles ping/pong keepalive and updates snapshots."""
        try:
            async for raw in self.ws:
                if not self.connected:
                    break
                try:
                    m = json.loads(raw)
                except Exception:
                    continue
                t = m.get("type")
                if t == "ping":
                    # Keepalive: reply pong immediately
                    try:
                        await self.ws.send(json.dumps({"type": "pong"}))
                    except Exception:
                        pass
                elif t == "welcome":
                    self.last_welcome = m
                    you = m.get("you", {})
                    self.is_leader = bool(you.get("is_leader", False))
                    self.last_roster = m.get("roster", [])
                    encounters_raw = m.get("encounters", [])
                    self.last_encounters = encounters_raw if isinstance(encounters_raw, list) else []
                elif t == "roster":
                    self.last_roster = m.get("members", [])
                    # Update own leader flag from roster
                    for member in self.last_roster:
                        if member.get("user_id") == self.user_id:
                            self.is_leader = bool(member.get("is_leader", False))
                            break
                elif t == "encounters":
                    enc_list = m.get("list", [])
                    self.last_encounters = enc_list if isinstance(enc_list, list) else []
                elif t == "scoreboard":
                    self.last_scoreboard = m
                elif t == "leader_changed":
                    # Update own leader flag
                    new_leader_id = m.get("user_id")
                    if new_leader_id == self.user_id:
                        self.is_leader = True
                    elif self.is_leader and new_leader_id != self.user_id:
                        self.is_leader = False
        except (asyncio.CancelledError, Exception):
            pass
        finally:
            self.connected = False

    async def post_dmg(self, boss: str, amount: int) -> int:
        """Post a single non-final damage fight. Returns fight_ts used."""
        fight_ts = int(time.time() * 1000)
        targets = _mb_targets(boss, amount)
        frame = _post_fight_frame(fight_ts=fight_ts, targets=targets, final=False)
        await self.send(frame)
        return fight_ts

    async def post_final(self, boss: str, amount: int) -> int:
        """Post final post_fight then final_detail. Returns fight_ts used."""
        fight_ts = int(time.time() * 1000)
        enc_id = str(fight_ts)
        targets = _mb_targets(boss, amount)
        detail = _build_detail(boss, amount)
        final_frame = _post_fight_frame(
            fight_ts=fight_ts,
            targets=targets,
            skills=detail["skills"],
            rotation=detail.get("rotation"),
            final=True,
        )
        await self.send(final_frame)
        # Small gap so the worker writes the submission row before the detail
        await asyncio.sleep(0.1)
        fd = _final_detail_frame(encounter_id=enc_id, detail=detail)
        await self.send(fd)
        return fight_ts

    def __repr__(self) -> str:
        status = "connected" if self.connected else "disconnected"
        leader = " [LEADER]" if self.is_leader else ""
        return f"Bot#{self.bot_id} ({self.user_id}) @{self.code} {status}{leader}"


# ---------------------------------------------------------------------------
# BotHarness — manages the pool of bots + the async REPL
# ---------------------------------------------------------------------------

class BotHarness:
    """Manages the pool of bot connections and dispatches REPL commands."""

    def __init__(self, host: str):
        self.host = host
        self.room_code: str = ""
        self._bots: dict[int, Bot] = {}   # bot_id -> Bot
        self._next_id = 1

    # ------------------------------------------------------------------
    # Bot pool helpers

    def _get_bot(self, bot_id: int) -> Optional[Bot]:
        return self._bots.get(bot_id)

    def _connected_bots(self) -> list[Bot]:
        return [b for b in self._bots.values() if b.connected]

    def _leader_bot(self) -> Optional[Bot]:
        """Return the first bot that believes it is the room leader."""
        for b in self._connected_bots():
            if b.is_leader:
                return b
        return None

    async def _add_bots(self, n: int) -> None:
        """Connect N new bots to self.room_code."""
        if not self.room_code:
            print("[error] No room set. Use: room <CODE>")
            return
        if not _HAS_WS:
            print("[error] websockets not installed. pip install websockets")
            return
        added = []
        for _ in range(n):
            bid = self._next_id
            self._next_id += 1
            bot = Bot(bid, self.host, self.room_code)
            try:
                await bot.connect()
                self._bots[bid] = bot
                added.append(bot)
            except Exception as e:
                print(f"[error] Bot#{bid} connect failed: {e}")
        if added:
            print(f"[ok] Connected: {', '.join(str(b) for b in added)}")
        # Give the welcome message a moment to arrive before returning
        if added:
            await asyncio.sleep(0.3)

    async def _drop_bot(self, bot: Bot) -> None:
        await bot.disconnect()
        del self._bots[bot.bot_id]
        print(f"[ok] Dropped Bot#{bot.bot_id}")

    # ------------------------------------------------------------------
    # Command dispatch

    async def cmd_room(self, args: list[str]) -> None:
        """room <CODE>"""
        if not args:
            print(f"[info] Current room: {self.room_code or '(none)'}")
            return
        self.room_code = args[0].upper()
        print(f"[ok] Room set to: {self.room_code}")

    async def cmd_add(self, args: list[str]) -> None:
        """add <N>"""
        try:
            n = int(args[0]) if args else 1
        except ValueError:
            print("[error] Usage: add <N>")
            return
        if n < 1 or n > 20:
            print("[error] N must be 1–20")
            return
        await self._add_bots(n)

    async def cmd_drop(self, args: list[str]) -> None:
        """drop <id|all>"""
        if not args:
            print("[error] Usage: drop <id|all>")
            return
        if args[0].lower() == "all":
            targets = list(self._bots.values())
        else:
            try:
                bid = int(args[0])
            except ValueError:
                print("[error] Usage: drop <id|all>")
                return
            bot = self._get_bot(bid)
            if not bot:
                print(f"[error] No bot #{bid}")
                return
            targets = [bot]
        for b in targets:
            await self._drop_bot(b)

    async def cmd_dmg(self, args: list[str]) -> None:
        """dmg <id|all> [boss] [amount]"""
        bot_sel, boss, amount = self._parse_dmg_args(args)
        if bot_sel is None:
            return
        for bot in bot_sel:
            try:
                fts = await bot.post_dmg(boss, amount)
                print(f"[ok] Bot#{bot.bot_id} post_fight(dmg) boss={boss} dmg={amount:,} fight_ts={fts}")
            except Exception as e:
                print(f"[error] Bot#{bot.bot_id} dmg failed: {e}")

    async def cmd_final(self, args: list[str]) -> None:
        """final <id|all> [boss] [amount]"""
        bot_sel, boss, amount = self._parse_dmg_args(args)
        if bot_sel is None:
            return
        for bot in bot_sel:
            try:
                fts = await bot.post_final(boss, amount)
                print(f"[ok] Bot#{bot.bot_id} post_fight(final)+final_detail boss={boss} dmg={amount:,} fight_ts={fts}")
            except Exception as e:
                print(f"[error] Bot#{bot.bot_id} final failed: {e}")

    def _parse_dmg_args(
        self, args: list[str]
    ) -> tuple[Optional[list[Bot]], str, int]:
        """Parse <id|all> [boss] [amount] — returns (bots, boss, amount) or (None, ...) on error."""
        if not args:
            print("[error] Usage: dmg <id|all> [boss] [amount]")
            return None, DEFAULT_BOSS, DEFAULT_DAMAGE

        # First arg: id or "all"
        selector = args[0]
        if selector.lower() == "all":
            bot_sel = self._connected_bots()
            if not bot_sel:
                print("[error] No connected bots")
                return None, DEFAULT_BOSS, DEFAULT_DAMAGE
        else:
            try:
                bid = int(selector)
            except ValueError:
                print("[error] First arg must be a bot id or 'all'")
                return None, DEFAULT_BOSS, DEFAULT_DAMAGE
            bot = self._get_bot(bid)
            if not bot or not bot.connected:
                print(f"[error] Bot#{bid} not connected")
                return None, DEFAULT_BOSS, DEFAULT_DAMAGE
            bot_sel = [bot]

        boss = DEFAULT_BOSS
        amount = DEFAULT_DAMAGE
        rest = args[1:]
        if rest:
            # Heuristic: if it looks like a number → amount, else boss name (maybe followed by amount)
            if rest[0].isdigit():
                try:
                    amount = int(rest[0])
                except ValueError:
                    pass
            else:
                boss = rest[0]
                if len(rest) > 1:
                    try:
                        amount = int(rest[1])
                    except ValueError:
                        pass

        return bot_sel, boss, amount

    async def cmd_leader(self, args: list[str]) -> None:
        """leader <id> — make bot <id> the room leader."""
        if not args:
            print("[error] Usage: leader <id>")
            return
        try:
            target_bid = int(args[0])
        except ValueError:
            print("[error] Usage: leader <id>  (bot id is a number)")
            return
        current_leader = self._leader_bot()
        if current_leader is None:
            print("[warn] No bot currently believes it is the leader. "
                  "Sending make_leader from Bot#1 (or first connected). "
                  "This may be rejected by the worker if that bot isn't the leader.")
            bots = self._connected_bots()
            if not bots:
                print("[error] No connected bots")
                return
            sender = bots[0]
        else:
            sender = current_leader

        target_bot = self._get_bot(target_bid)
        if target_bot is None:
            print(f"[error] No bot #{target_bid}")
            return
        if not target_bot.connected:
            print(f"[error] Bot#{target_bid} is not connected")
            return
        if target_bot.user_id == sender.user_id:
            print(f"[info] Bot#{target_bid} is already the leader (or the sender)")
            return

        try:
            await sender.send({"type": "make_leader", "user_id": target_bot.user_id})
            print(f"[ok] Sent make_leader from Bot#{sender.bot_id} -> Bot#{target_bid} ({target_bot.user_id})")
            # Give the worker a moment to process and broadcast back
            await asyncio.sleep(0.3)
        except Exception as e:
            print(f"[error] make_leader failed: {e}")

    async def cmd_kick(self, args: list[str]) -> None:
        """kick <targetUserId> — leader bot kicks a member."""
        if not args:
            print("[error] Usage: kick <targetUserId>")
            return
        target_uid = args[0]
        leader = self._leader_bot()
        if leader is None:
            print("[warn] No bot is the current leader. Kick may be rejected by the worker.")
            bots = self._connected_bots()
            if not bots:
                print("[error] No connected bots")
                return
            leader = bots[0]
        try:
            await leader.send({"type": "kick", "user_id": target_uid})
            print(f"[ok] Sent kick({target_uid}) from Bot#{leader.bot_id}")
        except Exception as e:
            print(f"[error] kick failed: {e}")

    async def cmd_reset(self, _args: list[str]) -> None:
        """reset — leader sends reset_roster."""
        leader = self._leader_bot()
        if leader is None:
            print("[warn] No bot is the current leader. reset_roster may be rejected.")
            bots = self._connected_bots()
            if not bots:
                print("[error] No connected bots")
                return
            leader = bots[0]
        try:
            await leader.send({"type": "reset_roster"})
            print(f"[ok] Sent reset_roster from Bot#{leader.bot_id}")
        except Exception as e:
            print(f"[error] reset_roster failed: {e}")

    async def cmd_clear(self, _args: list[str]) -> None:
        """clear — leader clears the active board."""
        leader = self._leader_bot()
        if leader is None:
            print("[warn] No bot is the current leader. clear may be rejected.")
            bots = self._connected_bots()
            if not bots:
                print("[error] No connected bots")
                return
            leader = bots[0]
        try:
            await leader.send({"type": "clear"})
            print(f"[ok] Sent clear from Bot#{leader.bot_id}")
        except Exception as e:
            print(f"[error] clear failed: {e}")

    async def cmd_list(self, _args: list[str]) -> None:
        """list / status — show bots and room snapshot."""
        print(f"\n=== Room: {self.room_code or '(none set)'} ===")
        if not self._bots:
            print("  No bots connected.")
        else:
            for bid, bot in sorted(self._bots.items()):
                status = "connected" if bot.connected else "DISCONNECTED"
                leader_tag = " [LEADER]" if bot.is_leader else ""
                print(f"  Bot#{bid}  uid={bot.user_id}  name={bot.username}  {status}{leader_tag}")

        # Pull snapshot from the first connected bot
        bots = self._connected_bots()
        if bots:
            b = bots[0]
            # Roster from worker
            if b.last_roster:
                print(f"\n  Room roster ({len(b.last_roster)} members):")
                for m in b.last_roster:
                    online = "online" if m.get("online") else "offline"
                    ldr = " *leader*" if m.get("is_leader") else ""
                    print(f"    {m.get('user_id')} ({m.get('username')}) {online}{ldr}")
            else:
                print("\n  [no roster data yet]")
            # Encounters
            if b.last_encounters:
                print(f"\n  Encounters ({len(b.last_encounters)}):")
                for e in b.last_encounters:
                    ended = " [ended]" if e.get("ended") else " [active]"
                    print(f"    {e.get('encounter_id')}  boss={e.get('boss')}  "
                          f"members={e.get('entries_n', '?')}{ended}")
            else:
                print("\n  [no encounter data yet]")
            # Latest scoreboard
            sb = b.last_scoreboard
            if sb and sb.get("entries"):
                print(f"\n  Scoreboard (boss={sb.get('boss')} enc={sb.get('encounter_id')}):")
                for entry in sb["entries"]:
                    print(f"    #{entry.get('rank')} {entry.get('username')} "
                          f"dmg={entry.get('total_damage', 0):,} "
                          f"contrib={entry.get('contribution', 0):.1f}%")
        print()

    def cmd_help(self, _args: list[str]) -> None:
        """Print command reference."""
        print("""
Commands:
  room <CODE>                    — set/switch target room (new connections use it)
  add <N>                        — connect N more bots (join-only)
  drop <id|all>                  — disconnect bot(s)
  dmg <id|all> [boss] [amount]   — post one damage fight (non-final)
  final <id|all> [boss] [amount] — post final fight + final_detail
  leader <id>                    — transfer leader crown to bot <id>
  kick <targetUserId>            — leader kicks a user from the room
  reset                          — leader sends reset_roster
  clear                          — leader clears the active board
  list / status                  — show local bots + last room snapshot
  help                           — this message
  quit / exit                    — drop all bots and exit

Notes:
  • Bot IDs are 1-based integers (shown in 'list').
  • 'dmg' sends a non-final post_fight (encounter stays open).
  • 'final' sends final post_fight + final_detail (closes encounter, enables drill-down).
  • leader/kick/reset/clear require a bot to be the room leader.
    Connect with leader=1 (first bot) or use 'leader <id>' to transfer.
  • Default boss: Tevent, default damage: 500,000
""")

    # ------------------------------------------------------------------
    # REPL loop

    async def run_repl(self) -> None:
        """Main async REPL — reads stdin without blocking the socket read loops."""
        loop = asyncio.get_event_loop()
        print("botcmd ready. Type 'help' for commands.")
        if self.room_code:
            print(f"  Room: {self.room_code}  |  host: {self.host}")

        while True:
            try:
                # Offload blocking readline to executor so asyncio can still
                # service socket read tasks between prompts.
                line = await loop.run_in_executor(None, sys.stdin.readline)
            except (EOFError, KeyboardInterrupt):
                break
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            parts = line.split()
            cmd = parts[0].lower()
            args = parts[1:]

            try:
                if cmd == "quit" or cmd == "exit":
                    break
                elif cmd == "room":
                    await self.cmd_room(args)
                elif cmd == "add":
                    await self.cmd_add(args)
                elif cmd == "drop":
                    await self.cmd_drop(args)
                elif cmd == "dmg":
                    await self.cmd_dmg(args)
                elif cmd == "final":
                    await self.cmd_final(args)
                elif cmd == "leader":
                    await self.cmd_leader(args)
                elif cmd == "kick":
                    await self.cmd_kick(args)
                elif cmd == "reset":
                    await self.cmd_reset(args)
                elif cmd == "clear":
                    await self.cmd_clear(args)
                elif cmd in ("list", "status", "ls"):
                    await self.cmd_list(args)
                elif cmd == "help":
                    self.cmd_help(args)
                else:
                    print(f"[unknown] '{cmd}' — type 'help' for commands")
            except Exception as e:
                print(f"[error] Command failed: {e}")

        # Cleanup on exit
        print("\nDropping all bots...")
        for bot in list(self._bots.values()):
            await bot.disconnect()
        self._bots.clear()
        print("bye.")

    async def startup_connect(self, n: int) -> None:
        """Connect N bots at startup if a room code is already set."""
        if self.room_code and n > 0:
            print(f"Connecting {n} bot(s) to room {self.room_code}...")
            await self._add_bots(n)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main_async(args: argparse.Namespace) -> int:
    if not _HAS_WS:
        print("ERROR: websockets not installed. Run: pip install websockets", file=sys.stderr)
        return 1

    harness = BotHarness(host=args.host)
    if args.code:
        harness.room_code = args.code.upper()
    await harness.startup_connect(args.members)
    await harness.run_repl()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Interactive party-bot harness — commandable WebSocket bots for TL-DPS-Meter testing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 3 bots against prod:
  python botcmd.py TESTBOT --members 3

  # local wrangler dev:
  python botcmd.py TESTBOT --members 2 --host wss://127.0.0.1:8787

  # start with no bots (connect later in REPL):
  python botcmd.py
""")
    ap.add_argument("code", nargs="?", default="",
                    help="party code to join on startup (optional)")
    ap.add_argument("--members", type=int, default=0,
                    help="number of bots to connect on startup (default: 0)")
    ap.add_argument("--host", default=DEFAULT_HOST,
                    help=f"WebSocket host (default: {DEFAULT_HOST})")
    args = ap.parse_args()
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
