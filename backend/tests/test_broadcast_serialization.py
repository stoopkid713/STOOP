"""Regression: WS serialization must tolerate a stray ``datetime``.

The debug trace sink broadcasts trace records that can carry raw ``datetime``
fields (e.g. the ``server.ingest`` trace's ``stats.first_ts``/``last_ts``). Before
the fix, ``_broadcast``/``_send`` used a bare ``json.dumps`` → the broadcast raised
``TypeError('Object of type datetime is not JSON serializable')`` inside a
fire-and-forget Task and the frame was **silently dropped** (recurring once per
combat-flush during party recording, only with ``TLDPS_DEBUG=1``).

Both serializers now pass ``default=str`` — mirroring ``debug._write`` — so any
stray datetime renders to its string form instead of crashing the send. See
``TL-DPS-Meter-oracle/docs/BUG-datetime-broadcast.md``.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

from dps_meter_server import DPSMeterServer


class _CaptureWS:
    """Minimal stand-in for a connected websocket: records the frames sent."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, data: str) -> None:
        self.sent.append(data)


def _run(coro):
    return asyncio.run(coro)


def test_broadcast_tolerates_datetime(tmp_path):
    """A debug-shaped payload carrying a raw datetime broadcasts without raising."""
    async def go():
        s = DPSMeterServer(tmp_path)
        ws = _CaptureWS()
        s.clients.add(ws)
        payload = {
            "type": "debug",
            "data": {"event": "server.ingest",
                     "first_ts": datetime(2026, 5, 31, 1, 2, 3),
                     "last_ts": datetime(2026, 5, 31, 1, 3, 4)},
        }
        await s._broadcast(payload)  # must not raise
        assert ws.sent, "broadcast produced no frame (was it dropped?)"
        decoded = json.loads(ws.sent[0])
        # The datetime survived as a (string) value rather than aborting the send.
        assert decoded["data"]["first_ts"]
        assert isinstance(decoded["data"]["first_ts"], str)

    _run(go())


def test_send_tolerates_datetime(tmp_path):
    """The single-client _send path is guarded the same way."""
    async def go():
        s = DPSMeterServer(tmp_path)
        ws = _CaptureWS()
        await s._send(ws, {"type": "x", "ts": datetime(2026, 5, 31)})  # must not raise
        assert ws.sent
        json.loads(ws.sent[0])  # valid JSON

    _run(go())
