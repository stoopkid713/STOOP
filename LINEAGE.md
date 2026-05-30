# Lineage

## Upstream

The original is [mjb6967/CKdpsApp](https://github.com/mjb6967/CKdpsApp) by
**SirPHz** — a Python (PyInstaller-bundled) WebSocket server that tails the combat
logs Throne and Liberty writes to `%LOCALAPPDATA%\TL\Saved\CombatLogs\` and serves
a browser dashboard. This project began as a fork of it in early April 2026.

## This project

The frontend (`index.html`) was extended directly — Run Lab, the stacked DPS
timeline, Cross-Skill Matrix, Compare key findings, Session Queue, and more.

The original fork's Python backend was only ever a compiled `.exe` (its source was
lost), which meant it couldn't be maintained or extended — only worked around from
the frontend. So the backend was **rebuilt from scratch as fresh, owned code**
(`backend/`): a clean Python implementation behind the same WebSocket contract, then
wrapped in a single native window (pywebview) and packaged as a portable build and a
per-user installer. The frontend is unchanged in spirit; the engine underneath is now
ours, tested, and buildable from source.

See [LICENSE](LICENSE) and [NOTICE](NOTICE) for attribution.

## Sibling project

[TL-DPS-Auto](https://github.com/stoopkid713/TL-DPS-Auto) explores a more
automation-focused design. It is a separate codebase, not a successor, and coexists
on different ports (8766/8767) so both can run at once.
