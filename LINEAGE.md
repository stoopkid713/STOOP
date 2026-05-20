# Lineage

How this codebase came to exist, in narrative form.

## Upstream

The original is [mjb6967/CKdpsApp](https://github.com/mjb6967/CKdpsApp) by
SirPHz — a Python (PyInstaller-bundled) WebSocket server that tails the
combat log files Throne and Liberty writes to
`%LOCALAPPDATA%\TL\Saved\CombatLogs\` and serves a browser dashboard at
`http://localhost`.

## This fork

Forked at SirPHz v1.0 in early April 2026. Frontend (`index.html`) and a
handful of data files were modified directly in-place; the Python backend
(`server.py` → `server.pyc` inside `TL-DPS-Meter.exe`) was never modified
in this fork and remains the upstream binary.

### Feature evolution

Each step below corresponds to a `state-*` tag in this repo. Tags are
orphan-branch commits — they don't appear in `main`'s linear history.

1. **state-baseline** (Apr 7) — clean fork. Added personal build tags
   (`4 Piece Blood`, `World Boss`, etc.) to seed the build-tag dropdown.
2. **state-session-queue** (Apr 8) — added the Session Queue feature so
   60-second tests auto-save with placeholder tags and can be tagged
   inline / assigned to Run Lab slots later.
3. **state-runlab** (Apr 8) — added the Run Lab UI and Stacked DPS chart.
   This is roughly the state that was pushed to GitHub on Apr 8 and stayed
   there until the May 2026 recovery — see tag
   `snapshot-pre-recovery-2026-05-19` for the exact published HEAD.
4. **state-current** (May 19) — added Cross-Skill Matrix, Compare Key
   Findings, Sidebar toggle, and Weapon group toggles. **This is the
   active production state on `main`.**

The progression from `state-baseline` → `state-current` is monotonic — each
state adds features without removing any.

### Why orphan-branch tags instead of linear commits

The original 5 commits on `main` (from the Apr 8 push) reflect a single
publish event, not the actual development history. Rather than rewrite or
duplicate those commits, the historical states are preserved as orphan
commits referenced only by their tags. The `archive/` directory in the
working tree provides folder-level access to the same content for direct
inspection.

### Backend recovery situation

The fork's `server.py` source was lost — the developer only ever had the
PyInstaller-bundled `.exe` and the upstream's source was not vendored. When
the May 2026 recovery surfaced this gap, `pyinstxtractor` was used to pull
`server.pyc` out of the `.exe`, but the `.pyc` was compiled with **Python
3.14**. No automated decompiler (`uncompyle6`, `decompyle3`) supports that
version. The only readable record of the backend is
[`server.disasm.txt`](server.disasm.txt) — a 28,526-line `pydisasm`
disassembly with named opcodes, constant pools, and variable names intact.
Manual reconstruction is the only path back to `.py` source; for now, the
backend stays binary.

For more context see [docs/disasm-notes.md](docs/disasm-notes.md).

## Sibling project

A separate experiment — [TL-DPS-Auto](https://github.com/stoopkid713/TL-DPS-Auto) —
explores an automation-focused design using conceptual ideas borrowed from
this tool. It is **not** a v2 or a successor; it is a different codebase
with a different design philosophy. It coexists with this tool on ports
8766/8767 so both can run simultaneously.

## Recovery & reorganization (May 2026)

Prior to May 2026 the codebase was sprawled across 5 folders on the
developer's Desktop (CKDPS, CKDPS - Copy, CKDPS - StoopKid Alpha, CKDPS -
StoopKid Beta, CKDPS - StoopKid Beta - Copy) with no git history beyond
the initial Apr 8 push. The May 2026 cleanup:

- Consolidated all 5 folders into `archive/` (gitignored) of this repo
- Tagged the 5 distinct frontend states for restorability
- Caught GitHub up to the most recent local work (`state-current`)
- Split the Alpha sibling project out into its own repo
- Established forward discipline: single `main` branch, `feat/*` branches
  for new work, no more folder-as-branch duplication

Backups from this transition live at `C:\Users\Admin\Desktop-backup-2026-05-19\`
on the developer's machine until verification confirms the recovery held up.
