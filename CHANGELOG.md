# Changelog

All notable changes to this fork are documented here. Format loosely based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

States are tagged in git as `state-<name>` and can be inspected with
`git checkout state-<name>` or `git diff state-runlab state-current`.

---

## [state-current] - 2026-05-19

The active production state. Tag `state-current` points at this commit on `main`.

### Added
- **Cross-Skill Matrix** in Compare view — side-by-side per-skill breakdown across two runs
- **Compare Key Findings** insights — auto-computed observations about run differences
- **Sidebar toggle** — collapsible navigation
- **Weapon group toggles** — filter the Weapons tab by weapon group
- `samples/encounters_sample.json` — 2.4 MB real-data fixture (sourced from the
  former `CKDPS - Copy` folder, the richest captured session) for development
  and regression testing
- `server.disasm.txt` — `pydisasm` output of `server.pyc` for backend
  reference (the only readable record — see [docs/disasm-notes.md](docs/disasm-notes.md))

### Notes
- Backend (`server.pyc`) remains binary-only. Compiled with Python 3.14;
  no automated decompiler supports that version. `server.disasm.txt` is the
  authoritative reference for backend behavior.
- Local Beta - Copy folder (the source of this state) was never pushed before
  this recovery — features above existed only on the developer's machine since
  ~mid-April.

---

## [snapshot-pre-recovery-2026-05-19] - 2026-04-08

Tag pointing at the previous `main` HEAD (commit `32b122d`), preserved before
the May 2026 recovery and reorganization. Functionally equivalent to
`state-runlab` plus minor README/HOW-TO-USE wording.

---

## [state-runlab] - 2026-04-08

### Added
- **Run Lab UI** — purpose-built side-by-side run comparison tool with skill
  matrix, cast timeline, and cast drilldown
- **Stacked DPS chart** — per-second damage broken down by skill, color-coded

---

## [state-session-queue] - 2026-04-08

### Added
- **Session Queue** — between-run workflow that auto-saves completed 60-second
  tests with placeholder tags (`__sq_*__`), inline tagging, A/B slot
  assignment for Run Lab, and bulk Save All

---

## [state-baseline] - 2026-04-07

Initial fork from [mjb6967/CKdpsApp](https://github.com/mjb6967/CKdpsApp) by SirPHz.

### Added
- Forked the v1.0 SirPHz release as-is
- Personal build tag list seeded (`4 Piece Blood`, `4 Piece Veiled`,
  `Guild Raids`, `World Boss`, `4 Piece Blood CDR`, etc.)

---

## Lineage notes

Earlier states (`state-baseline`, `state-session-queue`, `state-runlab`) are
preserved as orphan-branch commits — they're not part of `main`'s linear
history but are reachable via their tags. The `archive/` directory in the
working tree mirrors these same states folder-by-folder for offline
inspection. See [LINEAGE.md](LINEAGE.md) for the full narrative.

The sibling project [TL-DPS-Auto](https://github.com/stoopkid713/TL-DPS-Auto)
is a separate codebase — not a successor to this tool.
