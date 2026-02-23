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
            debug_path = os.path.join(os.getcwd(), "debug_img", "debug_crop_level.png")
            cv2.imwrite(debug_path, debug_img)
            print(f"   [DEBUG] Đã lưu ảnh debug: {debug_path}")

            # Lưu ảnh crop gốc
            crop_debug_path = os.path.join(os.getcwd(), "debug_img", "debug_crop_only.png")
            cv2.imwrite(crop_debug_path, crop_img)
            print(f"   [DEBUG] Đã lưu ảnh crop gốc: {crop_debug_path}")

            # Lưu ảnh đã xử lý (ảnh mà OCR sẽ đọc)
            processed_debug_path = os.path.join(os.getcwd(), "debug_img", "debug_crop_processed.png")
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

    # --- HÀM: Đọc thời gian Tăng cấp ---
    def check_upgrade_time(self, save_debug=False):
        """
        Chụp popup thông tin, crop vùng chứa thời gian tăng cấp và đọc.
        Tọa độ: (0.462W, 0.741H) -> (0.544W, 0.771H)
        Trả về: int (số giây) hoặc None nếu không đọc được.
        """
        screen = self.device.take_screenshot()
        h, w, _ = screen.shape

        # Tính tọa độ crop cho thời gian tăng cấp
        x1 = int(w * 0.462) - 1
        x2 = int(w * 0.544) + 1
        y1 = int(h * 0.741) - 1
        y2 = int(h * 0.771) + 1

        return self._ocr_time_region(screen, x1, y1, x2, y2, "upgrade", save_debug)

    # --- HÀM: Đọc thời gian Xây mới ---
    def check_build_time(self, save_debug=False):
        """
        Chụp popup thông tin, crop vùng chứa thời gian xây mới và đọc.
        Tọa độ: (0.365W, 0.385H) -> (0.439W, 0.416H)
        Trả về: int (số giây) hoặc None nếu không đọc được.
        """
        screen = self.device.take_screenshot()
        h, w, _ = screen.shape

        # Tính tọa độ crop cho thời gian xây mới
        x1 = int(w * 0.365) - 1
        x2 = int(w * 0.439) + 1
        y1 = int(h * 0.385) - 1
        y2 = int(h * 0.416) + 1

        return self._ocr_time_region(screen, x1, y1, x2, y2, "build", save_debug)

    def _ocr_time_region(self, screen, x1, y1, x2, y2, debug_name, save_debug=False):
        """
        Hàm helper để OCR vùng chứa thời gian.
        Định dạng thời gian: "H:MM:SS" hoặc "MM:SS" hoặc "M:SS"
        Trả về: int (số giây) hoặc None nếu không đọc được.
        """
        crop_img = screen[y1:y2, x1:x2]

        # === TIỀN XỬ LÝ ẢNH CHO OCR ===
        # 1. Phóng to ảnh 3x để OCR đọc tốt hơn
        scale_factor = 3
        crop_enlarged = cv2.resize(crop_img, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)

        # 2. Chuyển sang grayscale
        gray = cv2.cvtColor(crop_enlarged, cv2.COLOR_BGR2GRAY)

        # 3. Tăng contrast bằng CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # 4. Chuyển lại sang BGR (PaddleOCR cần 3 channel)
        processed_img = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

        # [DEBUG] Vẽ khung crop lên ảnh gốc và lưu lại
        if save_debug:
            debug_img = screen.copy()
            cv2.rectangle(debug_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(debug_img, f"Time Crop: ({x1},{y1}) - ({x2},{y2})",
                        (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            debug_path = os.path.join(os.getcwd(), f"debug_crop_time_{debug_name}.png")
            cv2.imwrite(debug_path, debug_img)
            print(f"   [DEBUG] Đã lưu ảnh debug: {debug_path}")

            crop_debug_path = os.path.join(os.getcwd(), f"debug_crop_time_{debug_name}_only.png")
            cv2.imwrite(crop_debug_path, crop_img)
            print(f"   [DEBUG] Đã lưu ảnh crop: {crop_debug_path}")

            processed_debug_path = os.path.join(os.getcwd(), f"debug_crop_time_{debug_name}_processed.png")
            cv2.imwrite(processed_debug_path, processed_img)
            print(f"   [DEBUG] Đã lưu ảnh đã xử lý: {processed_debug_path}")

        # OCR đọc chữ
        output = self.ocr.predict(processed_img)
        results = list(output)

        if not results:
            print(f"   [OCR-TIME] Không có kết quả OCR cho {debug_name}.")
            return None

        res = results[0]
        rec_texts = res.get('rec_texts', [])
        rec_scores = res.get('rec_scores', [])

        if not rec_texts:
            print(f"   [OCR-TIME] Không phát hiện text nào cho {debug_name}.")
            return None

        all_text = " ".join(rec_texts)
        print(f"   [OCR-TIME] Toàn bộ text ({debug_name}): '{all_text.strip()}'")

        for i, text in enumerate(rec_texts):
            confidence = rec_scores[i] if i < len(rec_scores) else None
            conf_str = f"{confidence:.2f}" if confidence is not None else "N/A"
            print(f"   [OCR-TIME] Đọc được: '{text}' (confidence: {conf_str})")

        # Parse thời gian từ chuỗi
        return self._parse_time_string(all_text)

    def _parse_time_string(self, text):
        """
        Parse chuỗi thời gian dạng "H:MM:SS", "MM:SS", "M:SS" thành số giây.
        Trả về: int (số giây) hoặc None nếu không parse được.
        """
        # Loại bỏ khoảng trắng và ký tự lạ
        text = text.strip().replace(" ", "")

        # Pattern cho H:MM:SS hoặc HH:MM:SS
        match = re.search(r'(\d{1,2}):(\d{1,2}):(\d{2})', text)
        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2))
            seconds = int(match.group(3))
            total_seconds = hours * 3600 + minutes * 60 + seconds
            print(f"   [TIME] Parsed: {hours}h {minutes}m {seconds}s = {total_seconds} giây")
            return total_seconds

        # Pattern cho MM:SS hoặc M:SS (không có giờ)
        match = re.search(r'(\d{1,2}):(\d{2})', text)
        if match:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            total_seconds = minutes * 60 + seconds
            print(f"   [TIME] Parsed: {minutes}m {seconds}s = {total_seconds} giây")
            return total_seconds

        print(f"   [TIME] Không thể parse thời gian từ: '{text}'")
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
        """
        Xây mới công trình.
        Trả về: (success: bool, build_time: int hoặc None)
        """
        print(f"   [ACTION] Xây mới: {building_name_display}")

        # 1. Bấm nút Búa (Menu Xây dựng)
        btn_bua = self.vision.find_template(self.device.take_screenshot(), self._get_path("btn_xay_dung_menu.png"))
        if not btn_bua:
            print("   [-] Không thấy nút Menu Xây dựng.")
            return False, None

        self.device.tap(btn_bua[0], btn_bua[1])
        time.sleep(2)  # Chờ menu trượt lên

        # 2. Đọc thời gian xây TRƯỚC KHI bấm nút Xây
        build_time = self.check_build_time(save_debug=True)
        if build_time:
            print(f"   [INFO] Thời gian xây dự kiến: {build_time} giây")

        # 3. Tìm TẤT CẢ các nút 'Xây' và chọn nút TRÊN CÙNG (y nhỏ nhất)
        btn_xay_path = self._get_path("btn_xay_confirm.png")
        all_btn_xay = self.vision.find_all_templates(self.device.take_screenshot(), btn_xay_path, threshold=0.45)

        if all_btn_xay:
            # Danh sách đã được sắp xếp theo y tăng dần, nên [0] là nút trên cùng
            btn_xay = all_btn_xay[0]
            print(f"   [+] Tìm thấy {len(all_btn_xay)} nút Xây. Chọn nút trên cùng tại ({btn_xay[0]}, {btn_xay[1]})")
            self.device.tap(btn_xay[0], btn_xay[1])

            # --- KIỂM TRA HẬU QUẢ (Post-Action Check) ---
            time.sleep(2)  # Chờ 2s để game phản hồi

            # Chụp lại màn hình xem nút còn đó không
            screen_after = self.device.take_screenshot()
            is_popup_still_open = self.vision.find_template(screen_after, btn_xay_path, threshold=0.45)

            if is_popup_still_open:
                print("   [FAIL] Nút Xây vẫn còn. (Nguyên nhân: Thiếu tài nguyên).")
                # QUAN TRỌNG: Phải đóng popup lại để không kẹt bot
                print("   > Đang đóng popup để thử việc khác...")

                # Tap vào vùng tối để đóng (Góc trên trái hoặc phải)
                self.device.tap(1, 1)
                time.sleep(1)
                return False, None  # Báo hiệu thất bại để chuyển task khác
            else:
                print("   [SUCCESS] Xây thành công (Popup đã đóng).")
                return True, build_time
        else:
            print("   [-] Không thấy nút Xây nào trong danh sách. Có thể đã xây.")
            self.device.tap(1, 1)
            return True, 1

    # --- HÀM 3: Logic Nâng Cấp (Lv > 1) ---
    def upgrade_existing_structure(self, img_name, target_lv, display_name):
        """
        Nâng cấp công trình đã có.
        Trả về: (success: bool, upgrade_time: int hoặc None)
        """
        print(f"   [CHECK] Kiểm tra: {display_name} (Mục tiêu: Lv {target_lv})")

        # 1. Tìm nhà trên map
        pos = self.vision.find_template(self.device.take_screenshot(), self._get_building_path(img_name + ".png"),
                                        threshold=0.45)

        if not pos:
            print(f"   [-] Không tìm thấy {display_name} trên bản đồ. (Có thể chưa xây?)")
            # Nếu mục tiêu > 1 mà không thấy nhà -> Có thể lỗi hoặc chưa xây
            return False, None

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
                self.device.tap(1, 1)
                return True, 1  # Coi như đã xong, không cần chờ
        else:
            print("   [WARN] Không đọc được level. Giả định cần nâng cấp.")

        # 5. Đọc thời gian tăng cấp TRƯỚC KHI bấm nút
        upgrade_time = self.check_upgrade_time(save_debug=True)
        if upgrade_time:
            print(f"   [INFO] Thời gian tăng cấp dự kiến: {upgrade_time} giây")

        # 6. Tìm nút Tăng Cấp
        btn_up_path = self._get_path("btn_tang_cap_vang.png")
        btn_up = self.vision.find_template(self.device.take_screenshot(), btn_up_path, threshold=0.45)  # Threshold cao chút cho chắc

        if btn_up:
            print("   [ACTION] Thấy nút Tăng Cấp. Đang bấm...")
            self.device.tap(btn_up[0], btn_up[1])

            # --- KIỂM TRA HẬU QUẢ (Post-Action Check) ---
            time.sleep(2)  # Chờ 2s để game phản hồi

            # Chụp lại màn hình xem nút còn đó không
            screen_after = self.device.take_screenshot()
            is_popup_still_open = self.vision.find_template(screen_after, btn_up_path, threshold=0.45)

            if is_popup_still_open:
                print("   [FAIL] Nút Tăng Cấp vẫn còn. (Nguyên nhân: Thiếu tài nguyên hoặc Đang bận xây).")
                # QUAN TRỌNG: Phải đóng popup lại để không kẹt bot
                print("   > Đang đóng popup để thử việc khác...")

                # Tap vào vùng tối để đóng (Góc trên trái hoặc phải)
                self.device.tap(1, 1)
                time.sleep(1)
                return False, None  # Báo hiệu thất bại để chuyển task khác
            else:
                print("   [SUCCESS] Nâng cấp thành công (Popup đã đóng).")
                return True, upgrade_time
        else:
            # Trường hợp vào popup mà không thấy nút Tăng cấp (VD: Đang xây dở, có nút Speedup)
            print("   [INFO] Không thấy nút Tăng Cấp (Có thể đang trong quá trình xây dựng).")
            self.device.tap(1, 1)
            return False, None

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
