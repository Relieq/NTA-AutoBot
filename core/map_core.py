import os
import json
import time


class MapManager:
    def __init__(self):
        self.data_dir = os.path.join(os.getcwd(), "data")
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

        self.map_file = os.path.join(self.data_dir, "map_data.json")

        self.main_city = (300, 300)
        self.grid = {}  # Dictionary lưu trữ: {"x,y": {"state": "...", "diff": "..."}}

        # Các trạng thái có thể có:
        # OWNED (Đất mình), RESOURCE (Tài nguyên), ENEMY (Kẻ địch), OBSTACLE (Vật cản)

    def load_or_create_map(self):
        """Khởi tạo map từ file cũ hoặc tạo mới qua Terminal"""
        if os.path.exists(self.map_file):
            use_old = input(">>> Tìm thấy bản đồ cũ (map_data.json). Bạn có muốn sử dụng tiếp? (y/n): ").strip().lower()
            if use_old == 'y':
                with open(self.map_file, 'r', encoding='utf-8') as f:
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
            "main_city": list(self.main_city),
            "grid": self.grid
        }
        with open(self.map_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def update_tile(self, x, y, state, difficulty=""):
        """Cập nhật trạng thái một ô đất"""
        key = f"{x},{y}"
        self.grid[key] = {
            "state": state,
            "difficulty": difficulty,
            "last_updated": int(time.time())
        }
        self.save_map()

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

        return targets