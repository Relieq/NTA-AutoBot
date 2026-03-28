import os
import json
import time
import re
import unicodedata


class MapManager:
    DIFFICULTY_TIER_ORDER = {
        "de": 0,
        "nhap_mon": 1,
        "thuong": 2,
        "tang_bac": 3,
        "kho": 4,
        "dia_nguc": 5,
    }

    DIFFICULTY_TIER_LABELS = {
        "de": "Dễ",
        "nhap_mon": "Nhập môn",
        "thuong": "Thường",
        "tang_bac": "Tăng bậc",
        "kho": "Khó",
        "dia_nguc": "Địa ngục",
    }

    def __init__(self):
        self.data_dir = os.path.join(os.getcwd(), "data")
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

        self.map_file = os.path.join(self.data_dir, "map_data.json")

        self.main_city = (300, 300)
        self.grid = {}  # Dictionary lưu trữ: {"x,y": {"state": "...", "diff": "..."}}
        self.schema_version = 2

        # Các trạng thái có thể có:
        # OWNED (Đất mình), RESOURCE (Tài nguyên), ENEMY (Kẻ địch), OBSTACLE (Vật cản)

    def load_or_create_map(self):
        """Khởi tạo map từ file cũ hoặc tạo mới qua Terminal"""
        if os.path.exists(self.map_file):
            use_old = input(">>> Tìm thấy bản đồ cũ (map_data.json). Bạn có muốn sử dụng tiếp? (y/n): ").strip().lower()
            if use_old == 'y':
                with open(self.map_file, 'r', encoding='utf-8-sig') as f:
                    data = json.load(f)
                    # Load riêng Thành Chính và Grid
                    self.main_city = tuple(data.get("main_city", [300, 300]))
                    self.grid = data.get("grid", {})
                print(f"   [MAP] Đã tải thành công {len(self.grid)} ô đất từ bộ nhớ.")
                return

        # Nếu chọn 'n' hoặc chưa có file
        print("--- KHỞI TẠO BẢN ĐỒ SỐ MỚI ---")
        try:
            x_str = input("Nhập tọa độ X của Thành Chính (ô góc dưới bên trái): ").strip()
            y_str = input("Nhập tọa độ Y của Thành Chính (ô góc dưới bên trái): ").strip()
            base_x, base_y = int(x_str), int(y_str)
        except ValueError:
            print("Tọa độ không hợp lệ, mặc định gán X=300, Y=300.")
            base_x, base_y = 300, 300

        self.main_city = (base_x, base_y)
        self.grid = {}
        # Đánh dấu 4 ô của Thành Chính là OWNED
        # Game SLG hệ tọa độ Y tăng từ dưới lên trên, nên 4 ô là:
        # (x, y), (x+1, y), (x, y+1), (x+1, y+1)
        self.update_tile(base_x, base_y, "OWNED")
        self.update_tile(base_x + 1, base_y, "OWNED")
        self.update_tile(base_x, base_y + 1, "OWNED")
        self.update_tile(base_x + 1, base_y + 1, "OWNED")

        self.save_map()
        print("   [MAP] Đã tạo bản đồ mới thành công!")

    def save_map(self):
        data = {
            "schema_version": self.schema_version,
            "main_city": list(self.main_city),
            "grid": self.grid
        }
        with open(self.map_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def _build_tile_cache_fields(self, x, y, difficulty):
        parsed = self.parse_difficulty(difficulty)
        dist = abs(int(x) - int(self.main_city[0])) + abs(int(y) - int(self.main_city[1]))
        return {
            "distance_to_city": dist,
            "difficulty_normalized": parsed["normalized"],
            "difficulty_valid": parsed["valid"],
            "difficulty_tier_key": parsed["tier_key"],
            "difficulty_level": parsed["level"],
            "difficulty_rank": parsed["rank"],
            "difficulty_label": parsed["label"],
        }

    def _migrate_grid_cache(self):
        changed = False
        for key, data in self.grid.items():
            try:
                x, y = map(int, key.split(","))
            except Exception:
                continue

            if not isinstance(data, dict):
                continue

            difficulty = data.get("difficulty", "")
            cache = self._build_tile_cache_fields(x, y, difficulty)
            for field, value in cache.items():
                if data.get(field) != value:
                    data[field] = value
                    changed = True
        return changed

    def migrate_grid_cache(self, save_if_changed=True):
        """Migrate cache metadata cho toàn bộ grid. Dùng cho script chạy một lần."""
        changed = self._migrate_grid_cache()
        if changed and save_if_changed:
            self.save_map()
        return changed

    def update_tile(self, x, y, state, difficulty=""):
        """Cập nhật trạng thái một ô đất"""
        key = f"{x},{y}"
        tile_data = {
            "state": state,
            "difficulty": difficulty,
            "last_updated": int(time.time())
        }
        tile_data.update(self._build_tile_cache_fields(x, y, difficulty))
        self.grid[key] = tile_data
        self.save_map()

    @staticmethod
    def normalize_text(text):
        if not text:
            return ""

        text = str(text).strip().lower()
        text = unicodedata.normalize("NFD", text)
        text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
        text = text.replace("đ", "d")
        text = text.replace("v", "n")
        text = text.replace("j", "i")
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def parse_difficulty(self, text):
        normalized = self.normalize_text(text)
        compact = normalized.replace(" ", "")
        tokens = [tok for tok in normalized.split(" ") if tok]
        token_set = set(tokens)

        def has_any_token(candidates):
            return any(token in token_set for token in candidates)

        def has_any_compact(candidates):
            return any(candidate and candidate in compact for candidate in candidates)

        level_match = re.search(r"(\d+)", normalized)
        level = int(level_match.group(1)) if level_match else 999

        tier_key = None

        # Ưu tiên các tier nhiều từ trước để tránh bắt nhầm tier ngắn.
        if (
            (has_any_token({"dia", "diaa"}) and has_any_token({"nguc", "ngoc", "ngut"}))
            or has_any_compact({"dianguc", "diangoc", "diangut"})
        ):
            tier_key = "dia_nguc"
        elif (
            (has_any_token({"tang", "tag", "tangg", "tangj", "tangj"}) and has_any_token({"bac", "boc", "bae"}))
            or ("tang" in compact and "bac" in compact)
            or has_any_compact({"tangbac", "tagbac", "tangboc"})
        ):
            tier_key = "tang_bac"
        elif (
            (has_any_token({"nhap", "nhapj", "nha"}) and has_any_token({"mon", "m0n", "moi"}))
            or has_any_compact({"nhapmon", "nhapmoi"})
        ):
            tier_key = "nhap_mon"
        elif has_any_token({"thuong", "thuongg", "thuoing", "thung"}) or has_any_compact({"thuong"}):
            tier_key = "thuong"
        elif has_any_token({"kho", "khoo", "kh0"}) or has_any_compact({"kho"}):
            tier_key = "kho"
        elif has_any_token({"de", "dee", "d3"}) or has_any_compact({"de"}):
            tier_key = "de"

        if not tier_key:
            return {
                "valid": False,
                "normalized": normalized,
                "tier_key": "",
                "tier_order": 999,
                "level": level,
                "label": "",
                "rank": 999999,
            }

        tier_order = self.DIFFICULTY_TIER_ORDER[tier_key]
        label = f"{self.DIFFICULTY_TIER_LABELS[tier_key]} {level}" if level != 999 else self.DIFFICULTY_TIER_LABELS[tier_key]
        rank = tier_order * 1000 + level
        return {
            "valid": True,
            "normalized": normalized,
            "tier_key": tier_key,
            "tier_order": tier_order,
            "level": level,
            "label": label,
            "rank": rank,
        }

    def get_tile_info(self, x, y):
        return self.grid.get(f"{x},{y}", {})

    def get_tile_state(self, x, y):
        key = f"{x},{y}"
        if key in self.grid:
            return self.grid[key]["state"]
        return "UNKNOWN"

    def get_expansion_targets(self):
        """
        Thuật toán Vết Dầu Loang: Tìm các ô nằm cạnh lãnh thổ (OWNED)
        mà trạng thái là UNKNOWN (chưa quét) hoặc RESOURCE (đã quét và có thể đánh).
        """
        owned_tiles = []
        for key, data in self.grid.items():
            if data["state"] == "OWNED":
                x, y = map(int, key.split(","))
                owned_tiles.append((x, y))

        targets = []
        # Các hướng liền kề: Trên (y+1), Dưới (y-1), Trái (x-1), Phải (x+1)
        directions = [(0, 1), (0, -1), (-1, 0), (1, 0)]

        for ox, oy in owned_tiles:
            for dx, dy in directions:
                nx, ny = ox + dx, oy + dy

                # Giới hạn map 0-600
                if 0 <= nx <= 600 and 0 <= ny <= 600:
                    state = self.get_tile_state(nx, ny)
                    if state in ["UNKNOWN", "RESOURCE"]:
                        target = (nx, ny)
                        if target not in targets:
                            targets.append(target)

        def target_sort_key(target):
            tx, ty = target
            tile = self.get_tile_info(tx, ty)
            state = tile.get("state", "UNKNOWN")

            # Ưu tiên RESOURCE đã biết độ khó (theo tier + level), sau đó RESOURCE mơ hồ, cuối cùng UNKNOWN.
            if state == "RESOURCE":
                if tile.get("difficulty_valid", False):
                    return 0, int(tile.get("difficulty_rank", 999999)), int(tile.get("distance_to_city", 999999)), tx, ty
                return 1, 999, 999, tx, ty

            return 2, 999, 999, tx, ty

        return sorted(targets, key=target_sort_key)
