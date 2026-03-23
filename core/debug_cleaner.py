import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Set


class DebugImageCleaner:
    def __init__(self, config_path="config/runtime.json"):
        self.config_path = os.path.abspath(config_path)
        self.config = self._load_config()

        self.enabled = bool(self.config.get("debug_auto_cleanup_enabled", False))
        self.interval_seconds = int(self.config.get("debug_auto_cleanup_interval_seconds", 900))
        self.keep_hours = float(self.config.get("debug_auto_cleanup_keep_hours", 24))
        self.root_dir = os.path.abspath(self.config.get("debug_auto_cleanup_root_dir", "debug_img"))
        self.max_delete_per_cycle = int(self.config.get("debug_auto_cleanup_max_delete_per_cycle", 500))

        exts = self.config.get("debug_auto_cleanup_extensions", [".png", ".jpg", ".jpeg", ".bmp", ".webp"])
        self.extensions = self._normalize_extensions(exts)

        if self.interval_seconds < 30:
            self.interval_seconds = 30
        if self.keep_hours < 0.1:
            self.keep_hours = 0.1
        if self.max_delete_per_cycle < 10:
            self.max_delete_per_cycle = 10

        self._next_cleanup_at = 0.0

    def _load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            return {}

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
            print(f"[DEBUG-CLEANUP] Không đọc được config '{self.config_path}': {last_exc}")
        return {}

    @staticmethod
    def _normalize_extensions(exts: Any) -> Set[str]:
        if isinstance(exts, str) or not isinstance(exts, Iterable):
            return {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

        normalized = set()
        for item in exts:
            if not isinstance(item, str):
                continue
            ext = item.strip().lower()
            if not ext:
                continue
            if not ext.startswith("."):
                ext = "." + ext
            normalized.add(ext)

        return normalized or {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

    def maybe_cleanup(self, now_ts: float) -> int:
        if not self.enabled:
            return 0

        if self._next_cleanup_at <= 0:
            self._next_cleanup_at = now_ts + self.interval_seconds
            return 0

        if now_ts < self._next_cleanup_at:
            return 0

        deleted = self._cleanup_old_images(now_ts)
        self._next_cleanup_at = now_ts + self.interval_seconds
        return deleted

    def _cleanup_old_images(self, now_ts: float) -> int:
        root = Path(self.root_dir)
        if not root.exists() or not root.is_dir():
            return 0

        cutoff_ts = now_ts - (self.keep_hours * 3600.0)
        deleted_count = 0

        try:
            candidates = sorted(root.rglob("*"), key=lambda p: p.stat().st_mtime)
        except Exception as exc:
            print(f"[DEBUG-CLEANUP] Không duyệt được '{root}': {exc}")
            return 0

        for path in candidates:
            if deleted_count >= self.max_delete_per_cycle:
                break
            if not path.is_file():
                continue
            if path.suffix.lower() not in self.extensions:
                continue

            try:
                mtime = path.stat().st_mtime
            except Exception:
                continue

            if mtime >= cutoff_ts:
                continue

            try:
                path.unlink()
                deleted_count += 1
            except Exception as exc:
                print(f"[DEBUG-CLEANUP] Không xóa được '{path}': {exc}")

        if deleted_count > 0:
            keep_seconds = int(self.keep_hours * 3600)
            print(f"[DEBUG-CLEANUP] Đã xóa {deleted_count} ảnh debug cũ hơn {keep_seconds}s")

        return deleted_count

