"""JSON persistence for the TL-DPS-Meter backend (rebuild, Workstream A — Phase 2).

Eight load/save pairs, one per on-disk JSON file. Every write is **atomic**: the
payload is written to ``<file>.tmp`` and then ``os.replace``d onto the target, so a
crash mid-write can never leave a half-written file. Loads return sane defaults
when the file is absent or corrupt (the backend never crashes on a missing file).

File shapes are the authoritative ``SCHEMAS.md`` [CORRECTED] digest, cross-checked
against the live JSON files and ``server.disasm.txt``. Three quirks worth calling out:

* ``skill_settings.json`` has a ``skills`` wrapper; ``weapon_config.json`` uses
  ``skillAssignments`` (no runtime ``currentSkills`` key).
* ``dungeons.json`` and ``default_target_assignments.json`` are flat
  ``{category: [names]}`` dicts with **no** ``last_updated`` stamp.
* ``saved_runs.json`` is a **bare JSON list** (``[...]``) written with ``indent=2``
  and **no** ``last_updated`` — confirmed from the old ``save_run`` /
  ``get_saved_runs`` handlers (``runs = json.load(f)`` on load;
  ``json.dump(runs, f, indent=2)`` on save). The ``{"runs": [...]}`` envelope the
  frontend sees exists only in the WebSocket broadcast (Phase 3), never on disk.

Saves stamp ``last_updated`` (ISO-8601) for: config, encounters, skill_settings,
weapon_config, target_assignments. The other three are written verbatim.

Path resolution: every function takes an optional ``data_dir``. When omitted it
falls back to ``$TLDPS_DATA_DIR`` and then the process CWD (matching the old
backend, which used bare filenames next to the executable). The Phase 3 server
sets the directory explicitly; tests pass ``tmp_path``.
"""

from __future__ import annotations

import copy
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from constants import DEFAULT_BROADCAST_INTERVAL, DEFAULT_HOTKEY

log = logging.getLogger(__name__)

# --- File names (relative to the resolved data dir) ------------------------
CONFIG_FILE = "config.json"
ENCOUNTERS_FILE = "encounters.json"
SKILL_SETTINGS_FILE = "skill_settings.json"
WEAPON_CONFIG_FILE = "weapon_config.json"
TARGET_ASSIGNMENTS_FILE = "target_assignments.json"
DEFAULT_TARGET_ASSIGNMENTS_FILE = "default_target_assignments.json"
SAVED_RUNS_FILE = "saved_runs.json"
DUNGEONS_FILE = "dungeons.json"

# --- Structural defaults (returned when a file is absent / unreadable) ------
# These hold the structural keys only; ``last_updated`` is a save-time stamp, so
# it is intentionally absent here. Always deep-copied before handing to a caller.
DEFAULT_CONFIG: dict[str, Any] = {
    "log_path": "",
    "player_name": "",
    "auto_detect_log": True,
    "broadcast_interval": DEFAULT_BROADCAST_INTERVAL,
    "hotkey_enabled": True,
    "hotkey": DEFAULT_HOTKEY,
    "hotkey_sound": False,
    "party_token": "",
    "party_enabled": False,
}
DEFAULT_ENCOUNTERS: dict[str, Any] = {"encounters": [], "builds": []}
DEFAULT_SKILL_SETTINGS: dict[str, Any] = {"skills": {}}
DEFAULT_WEAPON_CONFIG: dict[str, Any] = {"skillAssignments": {}}
DEFAULT_TARGET_ASSIGNMENTS: dict[str, Any] = {"assignments": {}}
DEFAULT_DUNGEONS: dict[str, Any] = {}
DEFAULT_DEFAULT_TARGETS: dict[str, Any] = {}

_INDENT = 2  # matches every live JSON file + the old json.dump(..., indent=2)


# --- Path / IO primitives --------------------------------------------------
def _default_dir() -> Path:
    """Resolve the data directory when a caller doesn't pass one."""
    env = os.environ.get("TLDPS_DATA_DIR")
    return Path(env) if env else Path.cwd()


def _data_path(name: str, data_dir: str | os.PathLike[str] | None) -> Path:
    base = Path(data_dir) if data_dir is not None else _default_dir()
    return base / name


def _now_iso() -> str:
    return datetime.now().isoformat()


def _stamp(data: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy with a fresh ``last_updated`` (never mutates input)."""
    return {**data, "last_updated": _now_iso()}


def _atomic_write_json(path: Path, obj: Any) -> None:
    """Write ``obj`` as JSON to ``path`` atomically (.tmp + os.replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=_INDENT)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)  # atomic on Windows + POSIX
    finally:
        # A successful os.replace renames tmp away; if json.dump raised first,
        # tmp lingers — clean it up so no stray .tmp is left behind.
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _load_dict(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    """Load a dict-rooted file, filling missing top-level keys from ``default``."""
    if not path.exists():
        return copy.deepcopy(default)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("persistence: %s unreadable (%s); using defaults", path.name, exc)
        return copy.deepcopy(default)
    if not isinstance(data, dict):
        log.warning("persistence: %s is %s, expected object; using defaults",
                    path.name, type(data).__name__)
        return copy.deepcopy(default)
    merged = copy.deepcopy(default)
    merged.update(data)  # preserve everything on disk; default only fills gaps
    return merged


def _load_list(path: Path) -> list[Any]:
    """Load a list-rooted file (saved_runs); ``[]`` when absent/corrupt."""
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("persistence: %s unreadable (%s); using []", path.name, exc)
        return []
    if not isinstance(data, list):
        log.warning("persistence: %s is %s, expected list; using []",
                    path.name, type(data).__name__)
        return []
    return data


# --- 1. config.json --------------------------------------------------------
def load_config(data_dir=None) -> dict[str, Any]:
    return _load_dict(_data_path(CONFIG_FILE, data_dir), DEFAULT_CONFIG)


def save_config(config: dict[str, Any], data_dir=None) -> None:
    _atomic_write_json(_data_path(CONFIG_FILE, data_dir), _stamp(config))


# --- 2. encounters.json ----------------------------------------------------
def load_encounters(data_dir=None) -> dict[str, Any]:
    return _load_dict(_data_path(ENCOUNTERS_FILE, data_dir), DEFAULT_ENCOUNTERS)


def save_encounters(data: dict[str, Any], data_dir=None) -> None:
    _atomic_write_json(_data_path(ENCOUNTERS_FILE, data_dir), _stamp(data))


# --- 3. skill_settings.json ------------------------------------------------
def load_skill_settings(data_dir=None) -> dict[str, Any]:
    return _load_dict(_data_path(SKILL_SETTINGS_FILE, data_dir), DEFAULT_SKILL_SETTINGS)


def save_skill_settings(data: dict[str, Any], data_dir=None) -> None:
    _atomic_write_json(_data_path(SKILL_SETTINGS_FILE, data_dir), _stamp(data))


# --- 4. weapon_config.json -------------------------------------------------
def load_weapon_config(data_dir=None) -> dict[str, Any]:
    return _load_dict(_data_path(WEAPON_CONFIG_FILE, data_dir), DEFAULT_WEAPON_CONFIG)


def save_weapon_config(data: dict[str, Any], data_dir=None) -> None:
    _atomic_write_json(_data_path(WEAPON_CONFIG_FILE, data_dir), _stamp(data))


# --- 5. dungeons.json (flat {category: [names]}, no last_updated) -----------
def load_dungeons(data_dir=None) -> dict[str, Any]:
    return _load_dict(_data_path(DUNGEONS_FILE, data_dir), DEFAULT_DUNGEONS)


def save_dungeons(data: dict[str, Any], data_dir=None) -> None:
    _atomic_write_json(_data_path(DUNGEONS_FILE, data_dir), data)


# --- 6. default_target_assignments.json (bundled, read-only, no stamp) -----
def load_default_targets(data_dir=None) -> dict[str, Any]:
    return _load_dict(_data_path(DEFAULT_TARGET_ASSIGNMENTS_FILE, data_dir),
                      DEFAULT_DEFAULT_TARGETS)


def save_default_targets(data: dict[str, Any], data_dir=None) -> None:
    # Provided for round-trip symmetry; the app treats this file as read-only.
    _atomic_write_json(_data_path(DEFAULT_TARGET_ASSIGNMENTS_FILE, data_dir), data)


# --- 7. target_assignments.json (user overrides, name -> category) ---------
def load_target_assignments(data_dir=None) -> dict[str, Any]:
    return _load_dict(_data_path(TARGET_ASSIGNMENTS_FILE, data_dir),
                      DEFAULT_TARGET_ASSIGNMENTS)


def save_target_assignments(data: dict[str, Any], data_dir=None) -> None:
    _atomic_write_json(_data_path(TARGET_ASSIGNMENTS_FILE, data_dir), _stamp(data))


# --- 8. saved_runs.json (BARE LIST, no wrapper, no last_updated) -----------
def load_saved_runs(data_dir=None) -> list[Any]:
    return _load_list(_data_path(SAVED_RUNS_FILE, data_dir))


def save_saved_runs(runs: list[Any], data_dir=None) -> None:
    _atomic_write_json(_data_path(SAVED_RUNS_FILE, data_dir), runs)
