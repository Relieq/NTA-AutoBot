import time
import os
import cv2
import re
from paddleocr import PaddleOCR
from config.build_order import BUILD_SEQUENCE
from modules.scene import SceneManager


class BuilderManager:
    def __init__(self, device, vision, captcha_solver=None):
        self.device = device
        self.vision = vision
        self.captcha_solver = captcha_solver  # Nhận instance từ main.py
        self.assets_dir = os.path.join(os.getcwd(), "assets")
        self.ocr = PaddleOCR(use_angle_cls=True, lang='en', enable_mkldnn=False)

    def _get_path(self, filename):
        return os.path.join(self.assets_dir, filename)

    def _get_building_path(self, filename):
        # Giả sử bạn để ảnh nhà trong assets/buildings/
        return os.path.join(self.assets_dir, "buildings", filename)

    # ==========================================================
    # HÀM XỬ LÝ CAPTCHA (INTERRUPT HANDLER)
    # ==========================================================
    def safe_wait_and_check(self, wait_time=2.0):
        """
        Đợi và kiểm tra xem Captcha có xuất hiện sau một hành động không.
        Trả về:
            "OK": Không có Captcha, hành động diễn ra bình thường.
            "INTERRUPTED": Có Captcha và đã giải xong -> Cần thực hiện lại hành động từ đầu.
            "FATAL": Có Captcha nhưng giải thất bại -> Dừng bot.
        """
        # 1. Chờ xem game có ném popup Captcha ra không
        time.sleep(wait_time)

        # Nếu chưa có tính năng Captcha thì coi như OK
        if not self.captcha_solver:
            return "OK"

        screen = self.device.take_screenshot()

        # 2. Kiểm tra xem có Captcha không
        if self.captcha_solver.detect_captcha(screen):
            print("\n   [!!! BÁO ĐỘNG !!!] PHÁT HIỆN CAPTCHA TRONG LÚC XÂY DỰNG! Đang tiến hành giải mã...")

            # 3. Gọi AI giải Captcha
            success = self.captcha_solver.solve(self.device, screen)

            if success:
                print("   [INTERRUPT] Giải Captcha thành công! Popup cũ đã bị game đóng, cần thực hiện lại hành động.")
                time.sleep(2)  # Chờ game ổn định lại sau khi đóng captcha
                return "INTERRUPTED"
            else:
                print("   [FATAL] KHÔNG THỂ GIẢI CAPTCHA! Dừng Bot để bảo vệ tài khoản.")
                return "FATAL"

        return "OK"

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
    def check_upgrade_time(self, save_debug=True):
        """
        Chụp popup thông tin, crop vùng chứa thời gian tăng cấp và đọc.
        Trả về: int (số giây) hoặc None nếu không đọc được.
        """
        screen = self.device.take_screenshot()
        h, w, _ = screen.shape

        # Tính tọa độ crop cho thời gian tăng cấp
        x1 = int(w * 0.481) - 1
        x2 = int(w * 0.544) + 1
        y1 = int(h * 0.741) - 1
        y2 = int(h * 0.771) + 1

        return self._ocr_time_region(screen, x1, y1, x2, y2, "upgrade", save_debug)

    # --- HÀM: Đọc thời gian Xây mới ---
    def check_build_time(self, save_debug=True):
        """
        Chụp popup thông tin, crop vùng chứa thời gian xây mới và đọc.
        Trả về: int (số giây) hoặc None nếu không đọc được.
        """
        screen = self.device.take_screenshot()
        h, w, _ = screen.shape

        # Tính tọa độ crop cho thời gian xây mới
        x1 = int(w * 0.384) - 1
        x2 = int(w * 0.439) + 1
        y1 = int(h * 0.385) - 1
        y2 = int(h * 0.416) + 1

        return self._ocr_time_region(screen, x1, y1, x2, y2, "build", save_debug)

    def _ocr_time_region(self, screen, x1, y1, x2, y2, debug_name, save_debug=False):
        crop_img = screen[y1:y2, x1:x2]

        scale_factor = 3
        crop_enlarged = cv2.resize(crop_img, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(crop_enlarged, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        processed_img = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

        if save_debug:
            debug_img = screen.copy()
            cv2.rectangle(debug_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(debug_img, f"Time Crop: ({x1},{y1}) - ({x2},{y2})",
                        (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            debug_path = os.path.join(os.getcwd(), "debug_img", f"debug_crop_time_{debug_name}.png")
            cv2.imwrite(debug_path, debug_img)
            print(f"   [DEBUG] Đã lưu ảnh debug: {debug_path}")

        output = self.ocr.predict(processed_img)
        results = list(output)

        if not results:
            return None

        res = results[0]
        rec_texts = res.get('rec_texts', [])

        if not rec_texts:
            return None

        all_text = " ".join(rec_texts)
        return self._parse_time_string(all_text)

    def _parse_time_string(self, text):
        text = text.strip().replace(" ", "")

        match = re.search(r'(\d{1,2}):(\d{1,2}):(\d{2})', text)
        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2))
            seconds = int(match.group(3))
            total_seconds = hours * 3600 + minutes * 60 + seconds
            print(f"   [TIME] Parsed: {hours}h {minutes}m {seconds}s = {total_seconds} giây")
            return total_seconds

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
        max_retries_per_action = 2

        for attempt in range(max_retries_per_action):
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
            all_btn_xay = self.vision.find_all_templates(self.device.take_screenshot(), btn_xay_path)

            if all_btn_xay:
                btn_xay = all_btn_xay[0]
                print(
                    f"   [+] Tìm thấy {len(all_btn_xay)} nút Xây. Chọn nút trên cùng tại ({btn_xay[0]}, {btn_xay[1]})")
                self.device.tap(btn_xay[0], btn_xay[1])

                # === GỌI HÀM KIỂM TRA CAPTCHA TẠI ĐÂY ===
                status = self.safe_wait_and_check(wait_time=2.0)

                if status == "INTERRUPTED":
                    print(f"   [BUILD] Hành động bị ngắt do Captcha. Đang thử lại... (Lần {attempt + 1})")
                    time.sleep(1.5)
                    continue  # Vòng lặp sẽ chạy lại việc tìm búa -> xây
                elif status == "FATAL":
                    return False, None

                # --- KIỂM TRA HẬU QUẢ (Post-Action Check) ---
                screen_after = self.device.take_screenshot()
                is_popup_still_open = self.vision.find_template(screen_after, btn_xay_path)

                if is_popup_still_open:
                    print("   [FAIL] Nút Xây vẫn còn. (Nguyên nhân: Thiếu tài nguyên).")
                    self.device.tap(1, 1)
                    time.sleep(1)
                    return False, None
                else:
                    print("   [SUCCESS] Xây thành công (Popup đã đóng).")
                    return True, build_time
            else:
                print("   [-] Không thấy nút Xây nào trong danh sách. Có thể đã xây.")
                self.device.tap(1, 1)
                return True, 1

        return False, None

    # --- HÀM 3: Logic Nâng Cấp (Lv > 1) ---
    def upgrade_existing_structure(self, img_name, target_lv, display_name):
        """
        Nâng cấp công trình đã có.
        Trả về: (success: bool, upgrade_time: int hoặc None)
        """
        print(f"   [CHECK] Kiểm tra: {display_name} (Mục tiêu: Lv {target_lv})")

        # Tìm nhà trên map
        pos = self.vision.find_template(
            self.device.take_screenshot(),
            self._get_building_path(img_name + ".png"),
        )

        if not pos:
            print(f"   [-] Không tìm thấy {display_name} trên bản đồ. (Có thể chưa xây?)")
            return False, None

        max_retries_per_action = 2

        for attempt in range(max_retries_per_action):
            # 1. Click vào nhà
            self.device.tap(pos[0], pos[1])
            time.sleep(1.5)

            # 2. Chuyển Tab Thông Tin
            self.open_info_tab()

            # 3. Đọc Level hiện tại
            current_lv = self.check_current_level()

            if current_lv is not None:
                print(f"   [INFO] Level hiện tại: {current_lv}")
                if current_lv >= target_lv:
                    print(f"   >>> Đã đạt yêu cầu (Lv {current_lv} >= {target_lv}). BỎ QUA.")
                    self.device.tap(1, 1)
                    return True, 1
            else:
                print("   [WARN] Không đọc được level. Giả định cần nâng cấp.")

            # 4. Đọc thời gian tăng cấp
            upgrade_time = self.check_upgrade_time(save_debug=True)
            if upgrade_time:
                print(f"   [INFO] Thời gian tăng cấp dự kiến: {upgrade_time} giây")

            # 5. Tìm và bấm nút Tăng Cấp
            btn_up_path = self._get_path("btn_tang_cap_vang.png")
            btn_up = self.vision.find_template(self.device.take_screenshot(), btn_up_path)

            if btn_up:
                print("   [ACTION] Thấy nút Tăng Cấp. Đang bấm...")
                self.device.tap(btn_up[0], btn_up[1])

                # === GỌI HÀM KIỂM TRA CAPTCHA TẠI ĐÂY ===
                status = self.safe_wait_and_check(wait_time=2.0)

                if status == "INTERRUPTED":
                    print(f"   [UPGRADE] Hành động bị ngắt do Captcha. Đang thử lại... (Lần {attempt + 1})")
                    time.sleep(1.5)
                    continue  # Vòng lặp sẽ click lại vào toà nhà và tăng cấp lại
                elif status == "FATAL":
                    return False, None

                # --- KIỂM TRA HẬU QUẢ ---
                screen_after = self.device.take_screenshot()
                is_popup_still_open = self.vision.find_template(screen_after, btn_up_path)

                if is_popup_still_open:
                    print("   [FAIL] Nút Tăng Cấp vẫn còn. (Nguyên nhân: Thiếu tài nguyên hoặc Đang bận xây).")
                    self.device.tap(1, 1)
                    time.sleep(1)
                    return False, None
                else:
                    print("   [SUCCESS] Nâng cấp thành công (Popup đã đóng).")
                    return True, upgrade_time
            else:
                print("   [INFO] Không thấy nút Tăng Cấp (Có thể đang trong quá trình xây dựng).")
                self.device.tap(1, 1)
                return False, None

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
                self.build_new_structure(display)
            else:
                self.upgrade_existing_structure(name, target, display)

            # Nghỉ một chút giữa các task
            time.sleep(1)
