"""Global hotkey listener (rebuild, Workstream A — Phase 5).

Registers a system-wide hotkey (default ``ctrl+tab``) that triggers a stats reset
+ broadcast, exactly like the old backend's ``hotkey_callback`` (disasm L1856).

Two backends, in priority order (matching ``setup_hotkey`` / ``_win32_hotkey_thread``
/ ``_keyboard_lib_setup``):

  1. **Win32 ``RegisterHotKey``** (preferred, no admin, no extra dependency — pure
     ``ctypes``): a daemon thread registers the hotkey on its own message queue and
     pumps ``WM_HOTKEY`` (786) messages, calling the trigger on each press.
  2. **``keyboard`` library fallback** (optional, lazily imported): used only if the
     Win32 registration fails (e.g. the combo is held by another app).

Thread-safety: the listener runs on its own thread; the press handler does NOT
touch shared state directly — it invokes the injected ``on_trigger`` callback,
which (in the app) is ``DPSMeterServer.request_reset`` and marshals onto the
asyncio loop via ``run_coroutine_threadsafe``.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

log = logging.getLogger(__name__)


class HotkeyManager:
    """Register a global hotkey and fire ``on_trigger`` (off the main thread) on press."""

    # Modifier flags (RegisterHotKey fsModifiers) — disasm VK/MOD table L1815-1824.
    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_NOREPEAT = 0x4000  # 16384 — suppress auto-repeat while the key is held

    HOTKEY_ID = 1
    WM_HOTKEY = 0x0312  # 786
    _PM_REMOVE = 0x0001

    # Named keys -> Windows virtual-key codes (disasm VK_CODES).
    VK_CODES = {"tab": 9, "r": 82, "f9": 120, "f10": 121, "f11": 122, "f12": 123}

    def __init__(self, on_trigger: Callable[[], None], hotkey: str = "ctrl+tab") -> None:
        self.on_trigger = on_trigger
        self.hotkey = hotkey
        self.running = False
        self.registered = False
        self.method: Optional[str] = None  # "win32" | "keyboard" | None
        self._thread: Optional[threading.Thread] = None

    # --- parsing -----------------------------------------------------------
    def parse_hotkey(self, hotkey_str: Optional[str] = None) -> tuple[int, int]:
        """Parse ``"ctrl+tab"`` -> ``(modifiers, vk)`` (disasm ``_parse_hotkey``).

        ``modifiers`` always includes ``MOD_NOREPEAT``; ``vk`` is 0 when no known
        key token is present (an invalid hotkey).
        """
        parts = (hotkey_str if hotkey_str is not None else self.hotkey).lower().split("+")
        modifiers = self.MOD_NOREPEAT
        vk = 0
        for part in parts:
            part = part.strip()
            if part == "ctrl":
                modifiers |= self.MOD_CONTROL
            elif part == "alt":
                modifiers |= self.MOD_ALT
            elif part == "shift":
                modifiers |= self.MOD_SHIFT
            elif part in self.VK_CODES:
                vk = self.VK_CODES[part]
        return modifiers, vk

    # --- lifecycle ---------------------------------------------------------
    def start(self) -> bool:
        """Start listening. Returns True if a backend registered the hotkey."""
        modifiers, vk = self.parse_hotkey()
        if vk == 0:
            log.error("hotkey: unknown key in %r", self.hotkey)
            return False
        self.running = True
        self._thread = threading.Thread(
            target=self._win32_thread, args=(modifiers, vk), daemon=True)
        self._thread.start()
        time.sleep(0.1)  # give RegisterHotKey a moment (matches old setup_hotkey)
        if not self.registered:
            return self._keyboard_fallback()
        return True

    def stop(self) -> None:
        self.running = False
        if self.method == "keyboard":
            try:
                import keyboard
                keyboard.remove_hotkey(self.hotkey)
            except Exception:  # noqa: BLE001 - best effort
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    # --- press handler (runs on the listener thread) -----------------------
    def _trigger(self) -> None:
        log.info("hotkey pressed (%s) -> reset", self.hotkey)
        try:
            self.on_trigger()
        except Exception:  # noqa: BLE001 - never kill the listener thread
            log.exception("hotkey on_trigger failed")

    # --- Win32 backend -----------------------------------------------------
    def _win32_thread(self, modifiers: int, vk: int) -> None:
        """Register the hotkey on this thread and pump WM_HOTKEY messages."""
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            if not user32.RegisterHotKey(None, self.HOTKEY_ID, modifiers, vk):
                log.warning("RegisterHotKey failed (err %s); will try fallback",
                            ctypes.get_last_error())
                return
            self.registered = True
            self.method = "win32"
            log.info("hotkey registered via Win32: %s", self.hotkey)
            msg = wintypes.MSG()
            while self.running:
                # Filter to WM_HOTKEY only; PM_REMOVE pops it off the queue.
                if user32.PeekMessageW(ctypes.byref(msg), None,
                                       self.WM_HOTKEY, self.WM_HOTKEY, self._PM_REMOVE):
                    if msg.message == self.WM_HOTKEY and msg.wParam == self.HOTKEY_ID:
                        self._trigger()
                time.sleep(0.05)
            user32.UnregisterHotKey(None, self.HOTKEY_ID)
            log.info("hotkey unregistered")
        except Exception:  # noqa: BLE001
            log.exception("Win32 hotkey thread error")

    # --- keyboard library fallback ----------------------------------------
    def _keyboard_fallback(self) -> bool:
        try:
            import keyboard
        except ImportError:
            log.warning("no hotkey backend available (Win32 failed, `keyboard` not installed)")
            return False
        try:
            keyboard.add_hotkey(self.hotkey, self._trigger)
        except Exception:  # noqa: BLE001
            log.exception("keyboard fallback failed for %s", self.hotkey)
            return False
        self.registered = True
        self.method = "keyboard"
        log.info("hotkey registered via keyboard lib: %s", self.hotkey)
        return True
