"""Phase 5 gate: global reset hotkey.

Covers ``parse_hotkey`` (the modifier/VK math, disasm-faithful) and the press
-> reset-broadcast path end-to-end over a real WebSocket. The actual Win32
``RegisterHotKey`` + message pump can't be driven without a synthetic keypress,
so the press is simulated by invoking the listener's trigger from a WORKER thread
(exercising the real cross-thread ``run_coroutine_threadsafe`` marshal into the
asyncio loop).
"""
from __future__ import annotations

import asyncio
import json
import pathlib

import websockets

from dps_meter_server import DPSMeterServer
from hotkey import HotkeyManager

HEADER = "CombatLogVersion,4\n"
M = HotkeyManager  # for the modifier constants


def _dmg(i: int, dmg: int) -> str:
    return (f"20260530-01:00:{i % 60:02d}:000,DamageDone,Star Destroyer,123,{dmg},"
            f"1,0,kMaxDamageByCriticalDecision,Player,Practice Dummy")


# ===========================================================================
# parse_hotkey — modifiers always carry MOD_NOREPEAT; vk from VK_CODES.
# ===========================================================================
def test_parse_hotkey_ctrl_tab():
    mgr = HotkeyManager(lambda: None, hotkey="ctrl+tab")
    mods, vk = mgr.parse_hotkey()
    assert (mods, vk) == (M.MOD_NOREPEAT | M.MOD_CONTROL, 9)
    assert (mods, vk) == (16386, 9)  # explicit numeric check


def test_parse_hotkey_variants():
    mgr = HotkeyManager(lambda: None)
    assert mgr.parse_hotkey("alt+f9") == (M.MOD_NOREPEAT | M.MOD_ALT, 120)
    assert mgr.parse_hotkey("ctrl+shift+r") == (
        M.MOD_NOREPEAT | M.MOD_CONTROL | M.MOD_SHIFT, 82)
    assert mgr.parse_hotkey("CTRL+TAB") == (16386, 9)  # case-insensitive


def test_parse_hotkey_unknown_key_is_invalid():
    mgr = HotkeyManager(lambda: None)
    mods, vk = mgr.parse_hotkey("ctrl+nope")
    assert vk == 0  # no usable key -> start() will refuse it
    assert mods == M.MOD_NOREPEAT | M.MOD_CONTROL


def test_start_refuses_unknown_key():
    mgr = HotkeyManager(lambda: None, hotkey="ctrl+nope")
    assert mgr.start() is False
    assert mgr.registered is False


# ===========================================================================
# Press -> reset broadcast over WS (the DoD).
# ===========================================================================
def test_hotkey_trigger_broadcasts_reset(tmp_path):
    asyncio.run(_trigger_resets(tmp_path))


async def _trigger_resets(tmp_path):
    server = DPSMeterServer(tmp_path, port=0, broadcast_interval=0.1)
    await server.start()
    server.ingest_lines([_dmg(1, 1000), _dmg(2, 2000)])  # total_damage 3000
    mgr = HotkeyManager(server.request_reset, hotkey="ctrl+tab")
    try:
        async with websockets.connect(f"ws://localhost:{server.port}", max_size=None) as ws:
            # confirm non-zero stats are flowing first
            pre = await _wait_for(ws, lambda m: m.get("type") == "stats", timeout=1.0)
            assert pre["data"]["total_damage"] == 3000

            # simulate a key press from a worker thread (real cross-thread marshal)
            await asyncio.to_thread(mgr._trigger)

            reset = await _wait_for(ws, lambda m: m.get("type") == "reset", timeout=2.0)
            assert reset == {"type": "reset"}
            zeroed = await _wait_for(
                ws, lambda m: m.get("type") == "stats" and m["data"]["total_damage"] == 0,
                timeout=2.0)
            assert zeroed["data"]["hit_count"] == 0
            assert server.stats.hits == []
    finally:
        await server.stop()


# ===========================================================================
# test_hotkey command still answers hotkey_test (wired in Phase 3, re-verified).
# ===========================================================================
def test_test_hotkey_command(tmp_path):
    asyncio.run(_test_hotkey_cmd(tmp_path))


async def _test_hotkey_cmd(tmp_path):
    server = DPSMeterServer(tmp_path, port=0, broadcast_interval=0.1)
    await server.start()
    try:
        async with websockets.connect(f"ws://localhost:{server.port}", max_size=None) as ws:
            await ws.send(json.dumps({"command": "test_hotkey"}))
            resp = await _wait_for(ws, lambda m: m.get("type") != "stats", timeout=2.0)
            assert resp == {"type": "hotkey_test", "success": True}
    finally:
        await server.stop()


async def _wait_for(ws, pred, *, timeout):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), deadline - loop.time())
        except asyncio.TimeoutError:
            break
        msg = json.loads(raw)
        if pred(msg):
            return msg
    raise AssertionError("predicate not satisfied before timeout")
