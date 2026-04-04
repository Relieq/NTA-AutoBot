import json
import os
from datetime import datetime

try:
    import msvcrt  # Windows console hotkey polling
except Exception:  # pragma: no cover - non-Windows fallback
    msvcrt = None


class HardDigManager:
    def __init__(self, plan_path="config/hard_dig_plan.json"):
        self.plan_path = os.path.abspath(plan_path)
        self.data = self._load_plan()
        self._normalize_schema()
        self._save_plan()

    def _load_plan(self):
        if not os.path.exists(self.plan_path):
            return self._default_plan()

        last_exc = None
        for encoding in ("utf-8-sig", "utf-8"):
            try:
                with open(self.plan_path, "r", encoding=encoding) as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception as exc:
                last_exc = exc

        if last_exc is not None:
            print(f"[HARD-DIG] Không đọc được file plan '{self.plan_path}': {last_exc}")
        return self._default_plan()

    @staticmethod
    def _default_plan():
        return {
            "enabled": False,
            "activate_hotkey": "h",
            "auto_start_on_boot": False,
            "start_tile": [300, 300],
            "targets": [],
            "runtime": {
                "activation_requested": False,
                "active": False,
                "current_index": 0,
                "ordered_targets": [],
                "completed_targets": [],
                "skipped_targets": [],
                "last_error": "",
                "updated_at": "",
            },
        }

    def _normalize_schema(self):
        defaults = self._default_plan()
        for key in ("enabled", "activate_hotkey", "auto_start_on_boot", "start_tile", "targets", "runtime"):
            if key not in self.data:
                self.data[key] = defaults[key]

        runtime = self.data.get("runtime")
        if not isinstance(runtime, dict):
            runtime = defaults["runtime"].copy()
            self.data["runtime"] = runtime

        for key, value in defaults["runtime"].items():
            if key not in runtime:
                runtime[key] = value if not isinstance(value, list) else []

        if not isinstance(self.data.get("targets"), list):
            self.data["targets"] = []
        if not isinstance(self.data.get("start_tile"), list) or len(self.data["start_tile"]) != 2:
            self.data["start_tile"] = [300, 300]

        hotkey = str(self.data.get("activate_hotkey", "h")).strip().lower()
        self.data["activate_hotkey"] = hotkey[0] if hotkey else "h"
        self.data["enabled"] = bool(self.data.get("enabled", False))
        self.data["auto_start_on_boot"] = bool(self.data.get("auto_start_on_boot", False))

    def _save_plan(self):
        try:
            os.makedirs(os.path.dirname(self.plan_path), exist_ok=True)
            with open(self.plan_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as exc:
            print(f"[HARD-DIG] Không thể ghi file plan '{self.plan_path}': {exc}")
            return False

    def poll_hotkey_activation(self):
        if not self.data.get("enabled", False) or msvcrt is None:
            return False

        pressed = False
        hotkey = self.data.get("activate_hotkey", "h")
        while msvcrt.kbhit():
            raw = msvcrt.getwch()
            key = str(raw).strip().lower()
            if key == hotkey:
                pressed = True

        if pressed:
            self.request_activation("hotkey")
        return pressed

    def request_activation(self, source="manual"):
        runtime = self.data["runtime"]
        runtime["activation_requested"] = True
        runtime["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._save_plan()
        print(f"[HARD-DIG] Đã nhận yêu cầu kích hoạt ({source}).")

    def update_plan(self, start_tile, targets, enabled=True):
        """Cập nhật plan hard-dig từ GUI/runtime command."""
        normalized_targets = []
        dedup = set()

        for item in targets or []:
            try:
                x, y = int(item[0]), int(item[1])
            except Exception:
                continue
            if not (0 <= x <= 600 and 0 <= y <= 600):
                continue
            key = (x, y)
            if key in dedup:
                continue
            dedup.add(key)
            normalized_targets.append([x, y])

        try:
            sx, sy = int(start_tile[0]), int(start_tile[1])
            start_valid = 0 <= sx <= 600 and 0 <= sy <= 600
        except Exception:
            sx, sy = 300, 300
            start_valid = False

        if not start_valid:
            return False

        if [sx, sy] not in normalized_targets:
            normalized_targets.append([sx, sy])

        self.data["enabled"] = bool(enabled)
        self.data["start_tile"] = [sx, sy]
        self.data["targets"] = normalized_targets

        runtime = self.data.get("runtime", {})
        runtime["ordered_targets"] = []
        runtime["completed_targets"] = []
        runtime["skipped_targets"] = []
        runtime["current_index"] = 0
        runtime["last_error"] = ""
        runtime["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.data["runtime"] = runtime

        return self._save_plan()

    def consume_auto_start_request(self):
        if not self.data.get("auto_start_on_boot", False):
            return False
        self.request_activation("auto_start_on_boot")
        self.data["auto_start_on_boot"] = False
        self._save_plan()
        return True

    def has_activation_request(self):
        return bool(self.data.get("runtime", {}).get("activation_requested", False))

    def clear_activation_request(self):
        runtime = self.data["runtime"]
        runtime["activation_requested"] = False
        runtime["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._save_plan()

    def prepare_run(self, combat_manager):
        prepared = combat_manager.prepare_hard_dig_targets(self.data.get("start_tile", [300, 300]), self.data.get("targets", []))
        if prepared.get("status") != "READY":
            self.mark_error(f"prepare_failed:{prepared.get('reason', 'unknown')}")
            return prepared

        runtime = self.data["runtime"]
        runtime["active"] = True
        runtime["current_index"] = 0
        runtime["ordered_targets"] = prepared.get("ordered_targets", [])
        runtime["completed_targets"] = []
        runtime["skipped_targets"] = []
        runtime["last_error"] = ""
        runtime["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.clear_activation_request()
        self._save_plan()
        return prepared

    def current_target(self):
        runtime = self.data.get("runtime", {})
        ordered = runtime.get("ordered_targets", [])
        idx = int(runtime.get("current_index", 0))
        if idx < 0 or idx >= len(ordered):
            return None
        target = ordered[idx]
        if not isinstance(target, dict):
            return None
        if "x" not in target or "y" not in target:
            return None
        return {"x": int(target["x"]), "y": int(target["y"])}

    def mark_target_completed(self, target):
        runtime = self.data["runtime"]
        runtime["completed_targets"].append({"x": int(target["x"]), "y": int(target["y"])})
        runtime["current_index"] = int(runtime.get("current_index", 0)) + 1
        runtime["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._save_plan()

    def mark_target_skipped(self, target, reason):
        runtime = self.data["runtime"]
        runtime["skipped_targets"].append({"x": int(target["x"]), "y": int(target["y"]), "reason": str(reason)})
        runtime["current_index"] = int(runtime.get("current_index", 0)) + 1
        runtime["last_error"] = str(reason)
        runtime["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._save_plan()

    def mark_error(self, reason):
        runtime = self.data["runtime"]
        runtime["last_error"] = str(reason)
        runtime["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._save_plan()

    def is_finished(self):
        runtime = self.data.get("runtime", {})
        ordered = runtime.get("ordered_targets", [])
        idx = int(runtime.get("current_index", 0))
        return idx >= len(ordered)

    def finish_run(self):
        runtime = self.data["runtime"]
        runtime["active"] = False
        runtime["activation_requested"] = False
        runtime["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._save_plan()

    def abort_run(self, reason):
        runtime = self.data["runtime"]
        runtime["active"] = False
        runtime["last_error"] = str(reason)
        runtime["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._save_plan()

    def active(self):
        return bool(self.data.get("runtime", {}).get("active", False))

    def progress_text(self):
        runtime = self.data.get("runtime", {})
        ordered = runtime.get("ordered_targets", [])
        idx = int(runtime.get("current_index", 0))
        return f"{idx}/{len(ordered)}"

