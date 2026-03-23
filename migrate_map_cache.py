import argparse
import json
import os
import shutil
from datetime import datetime

from core.map_core import MapManager


def main():
    parser = argparse.ArgumentParser(description="Migrate cache metadata cho data/map_data.json (chạy một lần khi cần).")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ kiểm tra có thay đổi hay không, không ghi file")
    parser.add_argument("--no-backup", action="store_true", help="Không tạo file backup trước khi migrate")
    args = parser.parse_args()

    mgr = MapManager()
    map_path = mgr.map_file
    if not os.path.exists(map_path):
        print(f"[MAP-MIGRATE] Không tìm thấy file map: {map_path}")
        return

    with open(map_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    mgr.main_city = tuple(data.get("main_city", [300, 300]))
    mgr.grid = data.get("grid", {})

    if args.dry_run:
        changed = mgr.migrate_grid_cache(save_if_changed=False)
        print(f"[MAP-MIGRATE] dry-run | changed={changed} | tiles={len(mgr.grid)}")
        return

    if not args.no_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{map_path}.bak_{ts}"
        shutil.copy2(map_path, backup_path)
        print(f"[MAP-MIGRATE] Đã tạo backup: {backup_path}")

    changed = mgr.migrate_grid_cache(save_if_changed=True)
    print(f"[MAP-MIGRATE] done | changed={changed} | tiles={len(mgr.grid)} | path={map_path}")


if __name__ == "__main__":
    main()

