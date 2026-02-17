import time
import os
import cv2
import re
from paddleocr import PaddleOCR
from config.build_order import BUILD_SEQUENCE
from modules.scene import SceneManager


class BuilderManager:
    def __init__(self, device, vision):
        self.device = device
        self.vision = vision
        self.assets_dir = os.path.join(os.getcwd(), "assets")
        self.ocr = PaddleOCR(use_angle_cls=True, lang='en', enable_mkldnn=False)

    def _get_path(self, filename):
        return os.path.join(self.assets_dir, filename)

    def _get_building_path(self, filename):
        # Giả sử bạn để ảnh nhà trong assets/buildings/
        return os.path.join(self.assets_dir, "buildings", filename)

    # --- HÀM 1: Đọc Level hiện tại (Quan trọng nhất để Skip) ---
    def check_current_level(self, save_debug=False):
        """
        Chụp popup thông tin, crop vùng chứa chữ 'Cấp X' và đọc số.
        Trả về: int (level) hoặc None nếu không đọc được.
        """
        screen = self.device.take_screenshot()

        # [CẤU HÌNH TỌA ĐỘ] - Bạn cần chỉnh số này theo máy của bạn!
        h, w, _ = screen.shape

        # Tính tọa độ crop
        y1 = int(h * 0.260) - 1
        y2 = int(h * 0.3) + 1
        x1 = int(w * 0.4125) - 1
        x2 = int(w * 0.475) + 1

        crop_img = screen[y1:y2, x1:x2]

        # === TIỀN XỬ LÝ ẢNH CHO OCR ===
        # 1. Phóng to ảnh 3x để OCR đọc tốt hơn
        scale_factor = 3
        crop_enlarged = cv2.resize(crop_img, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)

        # 2. Chuyển sang grayscale
        gray = cv2.cvtColor(crop_enlarged, cv2.COLOR_BGR2GRAY)

        # 3. Tăng contrast bằng CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # 4. Chuyển lại sang BGR (PaddleOCR cần 3 channel)
        processed_img = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

        # [DEBUG] Vẽ khung crop lên ảnh gốc và lưu lại
        if save_debug:
            debug_img = screen.copy()
            # Vẽ hình chữ nhật màu xanh lá (BGR: 0, 255, 0), độ dày 2px
            cv2.rectangle(debug_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            # Thêm text hiển thị tọa độ
            cv2.putText(debug_img, f"Crop: ({x1},{y1}) - ({x2},{y2})",
                        (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            # Lưu ảnh debug
            debug_path = os.path.join(os.getcwd(), "debug_crop_level.png")
            cv2.imwrite(debug_path, debug_img)
            print(f"   [DEBUG] Đã lưu ảnh debug: {debug_path}")

            # Lưu ảnh crop gốc
            crop_debug_path = os.path.join(os.getcwd(), "debug_crop_only.png")
            cv2.imwrite(crop_debug_path, crop_img)
            print(f"   [DEBUG] Đã lưu ảnh crop gốc: {crop_debug_path}")

            # Lưu ảnh đã xử lý (ảnh mà OCR sẽ đọc)
            processed_debug_path = os.path.join(os.getcwd(), "debug_crop_processed.png")
            cv2.imwrite(processed_debug_path, processed_img)
            print(f"   [DEBUG] Đã lưu ảnh đã xử lý: {processed_debug_path}")

        # OCR đọc chữ
        output = self.ocr.predict(processed_img)  # Đây là generator
        results = list(output)  # Chuyển thành list để dễ handle (thường chỉ 1 result cho single image)

        if not results:
            print("   [OCR] Không có kết quả OCR.")
            return None

        res = results[0]  # Lấy result đầu tiên (cho single crop_img)

        rec_texts = res.get('rec_texts', [])
        rec_scores = res.get('rec_scores', [])

        if not rec_texts:
            print("   [OCR] Không phát hiện text nào.")
            return None

        # Gom tất cả text thành 1 chuỗi để tìm số
        all_text = " ".join(rec_texts)
        print(f"   [OCR] Toàn bộ text: '{all_text.strip()}'")

        # In chi tiết từng line (với confidence nếu có)
        for i, text in enumerate(rec_texts):
            confidence = rec_scores[i] if i < len(rec_scores) else None
            conf_str = f"{confidence:.2f}" if confidence is not None else "N/A"
            print(f"   [OCR] Đọc được: '{text}' (confidence: {conf_str})")

        # Tìm số trong chuỗi - ưu tiên pattern "Cấp X" hoặc "Level X"
        match = re.search(r'(?:Cấp|Cap|Level|Lv|cấp|cap)\s*(\d+)', all_text, re.IGNORECASE)
        if match:
            return int(match.group(1))

        # Nếu không có pattern, tìm số đứng riêng (1-30)
        numbers = re.findall(r'\b(\d{1,2})\b', all_text)
        for num_str in numbers:
            num = int(num_str)
            if 1 <= num <= 20:  # Level hợp lệ trong game
                return num

        return None

    def open_info_tab(self):
        """Chuyển sang tab Thông Tin Kiến Trúc nếu đang ở tab khác"""
        # Tìm tab thông tin (dạng chưa active hoặc active đều được)
        # Nếu game mặc định mở tab này rồi thì hàm này sẽ pass
        # tab_thong_tin = self.vision.find_template(self.device.take_screenshot(), self._get_path("tab_thong_tin.png"),
        #                                           threshold=0.75)
        # if not tab_thong_tin:
        #     print("   [-] Không thấy tab thông tin kiến trúc thông thường. Thử tìm dạng bị che")
        #     tab_thong_tin = self.vision.find_template(self.device.take_screenshot(),
        #                                               self._get_path("tab_thong_tin_bi_che1.png"),
        #                                               threshold=0.95)
        #     if not tab_thong_tin:
        #         print("   [-] Không thấy tab thông tin kiến trúc bị che đen.")
        #         return False
        # self.device.tap(tab_thong_tin[0], tab_thong_tin[1])
        screen = self.device.take_screenshot()
        h, w, _ = screen.shape
        y, x = int(h * 0.15), int(w * 0.43)
        self.device.tap(x, y)
        time.sleep(1)
        return True

    # --- HÀM 2: Logic Xây Mới (Lv 1) ---
    def build_new_structure(self, building_name_display):
        print(f"   [ACTION] Xây mới: {building_name_display}")

        # 1. Bấm nút Búa (Menu Xây dựng)
        btn_bua = self.vision.find_template(self.device.take_screenshot(), self._get_path("btn_xay_dung_menu.png"))
        if not btn_bua:
            print("   [-] Không thấy nút Menu Xây dựng.")
            return False

        self.device.tap(btn_bua[0], btn_bua[1])
        time.sleep(2)  # Chờ menu trượt lên

        # 2. Bấm nút 'Xây' ĐẦU TIÊN trong danh sách (Theo yêu cầu của bạn)
        # Ta tìm ảnh nút "Xây" (btn_xay_confirm.png)
        # Vì hàm find_template trả về vị trí khớp NHẤT, ta cần logic lấy vị trí CAO NHẤT (y nhỏ nhất)
        # Nhưng để đơn giản, ta giả định nút đầu tiên sẽ được detect.
        # [Mẹo] Bạn có thể fix cứng tọa độ nút xây đầu tiên nếu danh sách không đổi vị trí.

        btn_xay = self.vision.find_template(self.device.take_screenshot(), self._get_path("btn_xay_confirm.png"))
        if btn_xay:
            print("   [+] Bấm nút Xây đầu tiên.")
            self.device.tap(btn_xay[0], btn_xay[1])
            time.sleep(2)
            return True
        else:
            print("   [-] Không thấy nút Xây nào trong danh sách.")
            self.device.tap(0, 0)
            return False

    # --- HÀM 3: Logic Nâng Cấp (Lv > 1) ---
    def upgrade_existing_structure(self, img_name, target_lv, display_name):
        print(f"   [CHECK] Kiểm tra: {display_name} (Mục tiêu: Lv {target_lv})")

        # 1. Tìm nhà trên map
        pos = self.vision.find_template(self.device.take_screenshot(), self._get_building_path(img_name + ".png"),
                                        threshold=0.45)

        if not pos:
            print(f"   [-] Không tìm thấy {display_name} trên bản đồ. (Có thể chưa xây?)")
            # Nếu mục tiêu > 1 mà không thấy nhà -> Có thể lỗi hoặc chưa xây
            return False

        # 2. Click vào nhà
        self.device.tap(pos[0], pos[1])
        time.sleep(1.5)  # Chờ popup hiện

        # 3. Chuyển Tab Thông Tin (Quan trọng)
        self.open_info_tab()

        # 4. Đọc Level hiện tại (OCR)
        current_lv = self.check_current_level()

        if current_lv is not None:
            print(f"   [INFO] Level hiện tại: {current_lv}")
            if current_lv >= target_lv:
                print(f"   >>> Đã đạt yêu cầu (Lv {current_lv} >= {target_lv}). BỎ QUA.")
                # Đóng popup
                self.device.tap(0, 0)
                return True  # Coi như đã xong
        else:
            print("   [WARN] Không đọc được level. Giả định cần nâng cấp.")

        # 5. Bấm nút Tăng Cấp
        btn_up = self.vision.find_template(self.device.take_screenshot(), self._get_path("btn_tang_cap_vang.png"),
                                           threshold=0.5)
        if btn_up:
            print("   [+] Bấm Tăng Cấp.")
            self.device.tap(btn_up[0], btn_up[1])
            time.sleep(3)  # Chờ server

            # Check xem có nâng được không (hay thiếu tài nguyên)
            # Nếu popup vẫn còn -> Thiếu tài nguyên
            # Nếu popup mất -> Đang xây
            # Tạm thời return True
            return True
        else:
            print("   [-] Không thấy nút Tăng Cấp (Đang xây hoặc Max cấp?).")
            self.device.tap(0, 0)
            return False

    # --- MAIN LOOP ---
    def execute_sequence(self):
        print("\n=== BẮT ĐẦU CHUỖI XÂY DỰNG ===")

        # Khởi tạo Scene Manager
        scene = SceneManager(self.device, self.vision)
        scene.go_to_city()

        for task in BUILD_SEQUENCE:
            target = task["target_lv"]
            name = task["name"]
            display = task["type_name"]

            if target == 1:
                # Logic Xây Mới
                # Trước khi xây mới, nên check xem trên map có nhà đó chưa (tránh xây trùng nếu game cho phép)
                # Nhưng theo yêu cầu của bạn: Lv1 -> Gọi lệnh Xây
                self.build_new_structure(display)
            else:
                # Logic Nâng Cấp
                self.upgrade_existing_structure(name, target, display)

            # Nghỉ một chút giữa các task
            time.sleep(1)
