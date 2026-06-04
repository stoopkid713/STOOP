"""Phase 8 — packaging path resolution (the APP_DIR trap).

A frozen build resolves two paths differently, and getting either wrong is
invisible until the exe is shipped:
  * index.html (bundled, read-only)   -> sys._MEIPASS/index.html
  * the 8 JSON state files (writable) -> sys.executable parent, NOT _MEIPASS
    (which is a temp extract dir wiped on exit)

These tests mock sys.frozen / sys._MEIPASS / sys.executable so the trap is caught
without a real PyInstaller build.
"""
from __future__ import annotations

from pathlib import Path

import main as main_mod


def _freeze(monkeypatch, exe: Path, meipass: Path) -> None:
    monkeypatch.setattr(main_mod.sys, "frozen", True, raising=False)
    monkeypatch.setattr(main_mod.sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.setattr(main_mod.sys, "executable", str(exe), raising=False)


def test_frozen_data_dir_is_localappdata_not_meipass_or_exe(monkeypatch, tmp_path):
    exe = tmp_path / "Programs" / "TL-DPS-Meter" / "TL-DPS-Meter.exe"
    meipass = tmp_path / "_MEI12345"
    local = tmp_path / "LocalAppData"
    _freeze(monkeypatch, exe, meipass)
    monkeypatch.delenv("TLDPS_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    expected = local / main_mod.APP_NAME
    assert main_mod._is_frozen() is True
    assert main_mod.app_dir() == expected
    assert main_mod.resolve_data_dir() == expected
    assert expected.is_dir()  # created on demand (works under read-only Program Files)
    # writable state must NOT land in the temp extract dir nor the read-only exe dir
    assert main_mod.resolve_data_dir() != meipass
    assert main_mod.resolve_data_dir() != exe.parent


def test_migrates_legacy_app_dir(monkeypatch, tmp_path):
    """Rebrand safety: an existing %LOCALAPPDATA%\\TL-DPS-Meter data dir is moved to
    the STOOP name on first launch, so saved runs/settings are NOT orphaned."""
    exe = tmp_path / "Programs" / "STOOP" / "STOOP.exe"
    meipass = tmp_path / "_MEI"
    local = tmp_path / "LocalAppData"
    _freeze(monkeypatch, exe, meipass)
    monkeypatch.delenv("TLDPS_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    # seed a pre-1.1.2 data dir with a user file
    legacy = local / main_mod.LEGACY_APP_NAME
    legacy.mkdir(parents=True)
    (legacy / "saved_runs.json").write_text("USER DATA", encoding="utf-8")

    new_dir = main_mod.app_dir()
    assert new_dir == local / main_mod.APP_NAME            # now resolves to STOOP
    assert (new_dir / "saved_runs.json").read_text(encoding="utf-8") == "USER DATA"
    assert not legacy.exists()                             # old dir moved, not copied


def test_legacy_migration_skipped_when_new_dir_exists(monkeypatch, tmp_path):
    """If a STOOP dir already exists, the legacy dir is left untouched (no clobber)."""
    exe = tmp_path / "Programs" / "STOOP" / "STOOP.exe"
    local = tmp_path / "LocalAppData"
    _freeze(monkeypatch, exe, tmp_path / "_MEI")
    monkeypatch.delenv("TLDPS_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    (local / main_mod.APP_NAME).mkdir(parents=True)
    (local / main_mod.APP_NAME / "keep.json").write_text("NEW", encoding="utf-8")
    legacy = local / main_mod.LEGACY_APP_NAME
    legacy.mkdir(parents=True)
    (legacy / "old.json").write_text("OLD", encoding="utf-8")

    main_mod.app_dir()
    assert (local / main_mod.APP_NAME / "keep.json").read_text(encoding="utf-8") == "NEW"
    assert legacy.exists()  # untouched


def test_frozen_index_html_is_meipass(monkeypatch, tmp_path):
    exe = tmp_path / "dist" / "TL-DPS-Meter.exe"
    meipass = tmp_path / "_MEI12345"
    _freeze(monkeypatch, exe, meipass)
    assert main_mod._index_html_path() == meipass / "index.html"


def test_frozen_env_override_still_wins(monkeypatch, tmp_path):
    exe = tmp_path / "dist" / "TL-DPS-Meter.exe"
    meipass = tmp_path / "_MEI12345"
    override = tmp_path / "custom_state"
    _freeze(monkeypatch, exe, meipass)
    monkeypatch.setenv("TLDPS_DATA_DIR", str(override))
    assert main_mod.resolve_data_dir() == override


def test_dev_paths_unfrozen(monkeypatch):
    monkeypatch.setattr(main_mod.sys, "frozen", False, raising=False)
    monkeypatch.delenv("TLDPS_DATA_DIR", raising=False)
    repo_root = Path(main_mod.__file__).resolve().parent.parent
    assert main_mod._is_frozen() is False
    assert main_mod._index_html_path() == repo_root / "index.html"
    assert main_mod.resolve_data_dir() == Path.cwd()


def test_dev_env_override(monkeypatch, tmp_path):
    monkeypatch.setattr(main_mod.sys, "frozen", False, raising=False)
    monkeypatch.setenv("TLDPS_DATA_DIR", str(tmp_path))
    assert main_mod.resolve_data_dir() == tmp_path


# --- portable vs installed (the two production packages) --------------------
def _make_portable_exe(tmp_path) -> Path:
    """A frozen exe folder that carries the portable marker beside the exe."""
    exe_dir = tmp_path / "portable" / "TL-DPS-Meter"
    exe_dir.mkdir(parents=True)
    (exe_dir / main_mod.PORTABLE_MARKER).write_text("", encoding="utf-8")
    return exe_dir / "TL-DPS-Meter.exe"


def test_is_portable_only_with_marker(monkeypatch, tmp_path):
    meipass = tmp_path / "_MEI"
    # marker present -> portable
    exe = _make_portable_exe(tmp_path)
    _freeze(monkeypatch, exe, meipass)
    assert main_mod._is_portable() is True
    # marker absent -> installed
    exe2 = tmp_path / "installed" / "TL-DPS-Meter.exe"
    exe2.parent.mkdir(parents=True)
    _freeze(monkeypatch, exe2, meipass)
    assert main_mod._is_portable() is False
    # never portable in dev, even if a marker happens to sit beside the cwd
    monkeypatch.setattr(main_mod.sys, "frozen", False, raising=False)
    assert main_mod._is_portable() is False


def test_portable_data_dir_is_exe_parent(monkeypatch, tmp_path):
    exe = _make_portable_exe(tmp_path)
    meipass = tmp_path / "_MEI"
    local = tmp_path / "LocalAppData"
    _freeze(monkeypatch, exe, meipass)
    monkeypatch.delenv("TLDPS_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    # portable -> data lives NEXT TO the exe (USB-movable), not LOCALAPPDATA/_MEIPASS
    assert main_mod.app_dir() == exe.parent
    assert main_mod.resolve_data_dir() == exe.parent
    assert main_mod.resolve_data_dir() != meipass
    assert main_mod.resolve_data_dir() != local / main_mod.APP_NAME


def test_portable_env_override_still_wins(monkeypatch, tmp_path):
    exe = _make_portable_exe(tmp_path)
    meipass = tmp_path / "_MEI"
    override = tmp_path / "custom_state"
    _freeze(monkeypatch, exe, meipass)
    monkeypatch.setenv("TLDPS_DATA_DIR", str(override))
    assert main_mod.resolve_data_dir() == override


# --- first-run preset seeding ----------------------------------------------
def _bundle_with_presets(tmp_path) -> Path:
    meipass = tmp_path / "_MEI"
    meipass.mkdir()
    (meipass / "default_target_assignments.json").write_text(
        '{"archboss": ["Test Boss"]}', encoding="utf-8")
    (meipass / "dungeons.json").write_text('{"Test Dungeon": []}', encoding="utf-8")
    return meipass


def test_seed_presets_copies_when_frozen(monkeypatch, tmp_path):
    meipass = _bundle_with_presets(tmp_path)
    _freeze(monkeypatch, tmp_path / "x.exe", meipass)
    data = tmp_path / "data"
    data.mkdir()
    main_mod.seed_presets(data)
    assert (data / "default_target_assignments.json").is_file()
    assert (data / "dungeons.json").is_file()


def test_seed_presets_does_not_overwrite_user_files(monkeypatch, tmp_path):
    meipass = _bundle_with_presets(tmp_path)
    _freeze(monkeypatch, tmp_path / "x.exe", meipass)
    data = tmp_path / "data"
    data.mkdir()
    (data / "default_target_assignments.json").write_text("USER", encoding="utf-8")
    main_mod.seed_presets(data)
    assert (data / "default_target_assignments.json").read_text(encoding="utf-8") == "USER"
    assert (data / "dungeons.json").is_file()  # the missing one is still seeded


def test_seed_presets_noop_in_dev(monkeypatch, tmp_path):
    monkeypatch.setattr(main_mod.sys, "frozen", False, raising=False)
    data = tmp_path / "data"
    data.mkdir()
    main_mod.seed_presets(data)
    assert list(data.iterdir()) == []  # dev relies on the repo files, not seeding
