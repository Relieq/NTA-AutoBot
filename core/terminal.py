import json
import os
from typing import Any, Dict


class TerminalCleaner:
    def __init__(self, config_path="config/runtime.json", on_clear=None):
        self.config_path = os.path.abspath(config_path)
        self.config = self._load_config()
        self.on_clear = on_clear
        self.enabled = bool(self.config.get("terminal_auto_clear_enabled", True))
        self.interval_seconds = int(self.config.get("terminal_auto_clear_interval_seconds", 300))
        if self.interval_seconds < 10:
            self.interval_seconds = 10
        self._next_clear_at = 0.0

    def _load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            return {
                "terminal_auto_clear_enabled": True,
                "terminal_auto_clear_interval_seconds": 300,
            }

        # runtime.json có thể được ghi bởi PowerShell UTF-8 with BOM -> dùng utf-8-sig để nuốt BOM.
        last_exc = None
        for encoding in ("utf-8-sig", "utf-8"):
            try:
                with open(self.config_path, "r", encoding=encoding) as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception as exc:
                last_exc = exc

        if last_exc is not None:
            print(f"[TERMINAL] Không đọc được config '{self.config_path}': {last_exc}")

        return {
            "terminal_auto_clear_enabled": True,
            "terminal_auto_clear_interval_seconds": 300,
        }

    def force_clear(self):
        self._clear_terminal()
        self._emit_clear_event("force")

    def maybe_clear(self, now_ts):
        if not self.enabled:
            return False

        if self._next_clear_at <= 0:
            self._next_clear_at = now_ts + self.interval_seconds
            return False

        if now_ts < self._next_clear_at:
            return False

        self._clear_terminal()
        self._emit_clear_event("auto")
        self._next_clear_at = now_ts + self.interval_seconds
        return True

    def _emit_clear_event(self, mode):
        if not callable(self.on_clear):
            return
        try:
            self.on_clear({"type": "TERMINAL_CLEARED", "mode": mode})
        except Exception:
            pass

    @staticmethod
    def _clear_terminal():
        cmd = "cls" if os.name == "nt" else "clear"
        os.system(cmd)
