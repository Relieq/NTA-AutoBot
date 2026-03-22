import random
import time
import os
import cv2
import numpy as np
import math
import easyocr

from modules.captcha import CaptchaSolver


class CombatManager:
    def __init__(self, device, vision, map_manager, captcha_solver=None):
        self.device = device
        self.vision = vision
        self.map = map_manager
        self.captcha_solver = captcha_solver  # Nhận instance từ main.py
        self.assets_dir = os.path.join(os.getcwd(), "assets")

        # Khởi tạo EasyOCR - hỗ trợ tiếng Việt
        # gpu=False để dùng CPU, đổi thành True nếu có GPU NVIDIA
        self.ocr = easyocr.Reader(['vi'], gpu=False, verbose=False)

        # Cấu hình danh sách đen (Blacklist độ khó)
        # Nếu gặp các từ này trong tên đất thì bỏ qua
        self.blacklist_difficulty = ["Tăng bậc 2", "Tăng bậc 3", "Địa ngục", "Khó 1", "Khó 2", "Khó 3"]
        self.blacklist_difficulty_norm = [self.map.normalize_text(item) for item in self.blacklist_difficulty]

        # [CẤU HÌNH MÀU SẮC]
        # Màu viền xanh lá cây của lãnh thổ (Hệ màu BGR của OpenCV)
        # RGB(58, 133, 74) -> BGR(74, 133, 58)
        # Dung sai +/- 15
        # self.lower_green = np.array([60, 118, 43])
        # self.upper_green = np.array([90, 148, 73])

        # [HỆ THỐNG DẪN ĐƯỜNG]
        # camera_offset: Lưu tổng vector đã kéo map để biết đường quay về
        # self.camera_offset = [0, 0]

        # Kích thước màn hình giả lập (1600x900)
        self.screen_w = 1600
        self.screen_h = 900

    def _get_path(self, filename):
        return os.path.join(self.assets_dir, filename)

    def _draw_detection_box(self, debug_img, center_pos, template_name, label, color):
        """Vẽ khung khoanh vùng dựa trên kích thước template đã match."""
        if not center_pos:
            return False

        template = cv2.imread(self._get_path(template_name))
        if template is None:
            print(f"   [DEBUG-WARN] Không đọc được template để vẽ box: {template_name}")
            return False

        h, w = template.shape[:2]
        x1 = max(0, center_pos[0] - w // 2)
        y1 = max(0, center_pos[1] - h // 2)
        x2 = min(self.screen_w - 1, x1 + w)
        y2 = min(self.screen_h - 1, y1 + h)

        cv2.rectangle(debug_img, (x1, y1), (x2, y2), color, 2)
        cv2.circle(debug_img, (center_pos[0], center_pos[1]), 5, color, -1)
        cv2.putText(debug_img, label, (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
        return True

    def _is_blacklisted_difficulty(self, normalized_text):
        for bad in self.blacklist_difficulty_norm:
            if bad and bad in normalized_text:
                return True
        return False

    def safe_wait_and_check(self, wait_time=1.5):
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
            print("\n   [!!! BÁO ĐỘNG !!!] PHÁT HIỆN CAPTCHA! Đang tiến hành giải mã...")

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

    def jump_to_coordinate(self, x, y):
        """Mở map, nhập tọa độ X, Y và bấm Xem để dịch chuyển"""
        print(f"   [NAV] Dịch chuyển đến tọa độ ({x}, {y})...")

        # 1. Bấm mở bản đồ (cần chuẩn bị ảnh btn_map.png)
        # Hoặc dùng tọa độ cứng nếu nó luôn cố định ở góc
        btn_map_pos = self.vision.find_template(self.device.take_screenshot(), self._get_path("btn_map.png"))
        if btn_map_pos:
            self.device.tap(btn_map_pos[0], btn_map_pos[1])
        else:
            # Fallback nếu không thấy ảnh (tùy chỉnh theo máy bạn)
            self.device.tap(1500, 850)

        time.sleep(1.5)  # Chờ map mở

        # Tọa độ cứng trên màn hình 1600x900 (theo bạn cung cấp)
        box_x = (815, 705)
        box_y = (890, 705)
        btn_xem = (990, 705)
        center_screen = (self.screen_w // 2, self.screen_h // 2 - 100)  # Lệch lên trên chút để tránh bấm trúng UI

        # 2. Nhập X
        self.device.tap(box_x[0], box_x[1])
        time.sleep(0.5)
        for _ in range(4): self.device.send_keyevent(67)  # Xóa 4 lần
        self.device.input_text(str(x))
        time.sleep(0.5)
        self.device.tap(center_screen[0], center_screen[1])  # Bấm ra ngoài để đóng bàn phím ảo
        time.sleep(0.5)

        # 3. Nhập Y
        self.device.tap(box_y[0], box_y[1])
        time.sleep(0.5)
        for _ in range(4): self.device.send_keyevent(67)  # Xóa 4 lần
        self.device.input_text(str(y))
        time.sleep(0.5)
        self.device.tap(center_screen[0], center_screen[1])  # Đóng bàn phím
        time.sleep(0.5)

        # 4. Bấm Xem
        self.device.tap(btn_xem[0], btn_xem[1])
        time.sleep(2)  # Chờ camera dịch chuyển và đóng map

    def analyze_tile_state(self, x, y, debug=True):
        """
        Bấm vào ô trung tâm màn hình, phân tích các nút hiện ra
        để đánh giá trạng thái ô đất.
        """
        print(f"   [ANALYZE] Đang phân tích ô đất ({x}, {y})...")

        # Tap trung tâm màn hình (sau khi jump, ô cần tìm sẽ ở giữa)
        cx, cy = self.screen_w // 2, self.screen_h // 2
        self.device.tap(cx, cy)
        time.sleep(1.5)  # Chờ popup thông tin

        screen = self.device.take_screenshot()

        # Nhận diện các thành phần
        btn_chiem = self.vision.find_template(screen, self._get_path("btn_chiem.png"))
        btn_vao = self.vision.find_template(screen, self._get_path("btn_vao.png"))
        btn_hanh_quan = self.vision.find_template(screen, self._get_path("btn_hanh_quan_map.png"))

        state = "UNKNOWN"
        difficulty = ""

        if btn_chiem:
            if btn_vao:
                state = "RESOURCE"
                # Nếu là RESOURCE, OCR đọc độ khó
                diff_info = self.analyze_difficulty(screen, btn_chiem, debug=False)
                difficulty = diff_info["label"] or diff_info["raw_text"]

                if diff_info["attackable"]:
                    print("   => Đất tài nguyên hợp lệ. Đánh được!")
                else:
                    state = "OBSTACLE"  # Coi như chướng ngại vật để lần sau không check lại
                    print("   => Đất quá khó/Blacklist. Bỏ qua.")
            else:
                state = "ENEMY"
                print("   => Lãnh thổ người chơi khác. Bỏ qua.")
        elif btn_hanh_quan:
            state = "OWNED"
            print("   => Lãnh thổ của mình.")
        else:
            state = "OBSTACLE"
            print("   => Chướng ngại vật (Núi, sông, v.v...).")

        # [DEBUG] Khoanh vùng các nút đã nhận diện để dễ hiệu chỉnh threshold/template
        if debug:
            debug_img = screen.copy()
            cv2.circle(debug_img, (cx, cy), 8, (255, 255, 255), -1)
            cv2.putText(debug_img, "TAP CENTER", (cx + 12, cy - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            found_count = 0
            found_count += int(self._draw_detection_box(debug_img, btn_chiem, "btn_chiem.png", "btn_chiem", (0, 255, 0)))
            found_count += int(self._draw_detection_box(debug_img, btn_vao, "btn_vao.png", "btn_vao", (255, 200, 0)))
            found_count += int(self._draw_detection_box(debug_img, btn_hanh_quan, "btn_hanh_quan_map.png", "btn_hanh_quan", (0, 140, 255)))

            cv2.putText(debug_img, f"ANALYZE TILE ({x}, {y})", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(debug_img, f"STATE: {state} | DETECTED: {found_count}/3", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            debug_path = os.path.join(os.getcwd(), "debug_img", "debug_analyze_tile_state.png")
            cv2.imwrite(debug_path, debug_img)
            print(f"   [DEBUG] Đã lưu ảnh khoanh vùng nút: {debug_path}")

        # Cập nhật vào bản đồ số
        self.map.update_tile(x, y, state, difficulty)

        # Trả về tọa độ nút Chiếm nếu có thể đánh
        if state == "RESOURCE":
            return btn_chiem
        else:
            # Bấm lại vào tâm để tắt popup
            self.device.tap(cx, cy)
            return None

    # ==========================================================
    # LOGIC XUẤT QUÂN VÀ OCR CŨ (GIỮ NGUYÊN)
    # ==========================================================

    def analyze_difficulty(self, screen_img, btn_chiem_pos, debug=True):
        """
        OCR vùng popup để đọc độ khó sử dụng EasyOCR.
        debug: Nếu True, sẽ lưu ảnh debug để kiểm tra vùng OCR.
        """
        # Crop vùng chứa text độ khó (Bạn cần tinh chỉnh tọa độ này chính xác)
        # Giả sử popup hiện ngay trên nút chiếm
        # Tọa độ ước lượng:
        x1, y1 = btn_chiem_pos[0] - 200, btn_chiem_pos[1] - 57
        x2, y2 = x1 + 80, y1 + 30

        # Đảm bảo tọa độ không vượt quá kích thước ảnh
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(screen_img.shape[1], x2)
        y2 = min(screen_img.shape[0], y2)

        crop = screen_img[y1:y2, x1:x2]

        # Tiền xử lý ảnh cho EasyOCR
        # [BƯỚC 1] Upscale 4x - Giúp mô hình nhận diện text nhỏ tốt hơn
        scale_factor = 4
        crop_enlarged = cv2.resize(crop, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)

        # [BƯỚC 2] Chuyển từ BGR sang RGB (EasyOCR dùng RGB)
        crop_rgb = cv2.cvtColor(crop_enlarged, cv2.COLOR_BGR2RGB)

        # OCR với EasyOCR
        try:
            # EasyOCR trả về list các tuple: (bbox, text, confidence)
            results = self.ocr.readtext(crop_rgb)
            # Ghép tất cả text lại
            full_text = " ".join([item[1] for item in results]) if results else ""
        except Exception as e:
            print(f"   [OCR-ERR] Lỗi OCR: {e}")
            full_text = ""

        parsed = self.map.parse_difficulty(full_text)
        normalized_text = parsed["normalized"]
        is_blacklisted = self._is_blacklisted_difficulty(normalized_text)

        if parsed["valid"]:
            print(f"   [OCR-DIG] Đọc được: {full_text} | Chuẩn hóa: {parsed['label']}")
        else:
            print(f"   [OCR-DIG] Đọc được: {full_text} | Không parse được độ khó")

        # [DEBUG] Vẽ debug cho OCR
        if debug:
            debug_img = screen_img.copy()

            # Vẽ vị trí nút Chiếm (chấm xanh dương)
            cv2.circle(debug_img, (btn_chiem_pos[0], btn_chiem_pos[1]), 10, (255, 0, 0), -1)
            cv2.putText(debug_img, "btn_chiem", (btn_chiem_pos[0] + 15, btn_chiem_pos[1] - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

            # Vẽ vùng OCR (hình chữ nhật đỏ)
            cv2.rectangle(debug_img, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(debug_img, "OCR REGION", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

            # Vẽ đường nối từ nút Chiếm đến vùng OCR
            cv2.line(debug_img, (btn_chiem_pos[0], btn_chiem_pos[1]), (x1 + (x2 - x1) // 2, y2),
                     (0, 165, 255), 1)

            # Hiển thị nội dung OCR đọc được (ở góc dưới màn hình)
            if full_text:
                text_color = (0, 0, 255) if is_blacklisted else (0, 255, 0)
                status = "BLACKLISTED - SKIP" if is_blacklisted else "OK - ATTACK"

                cv2.putText(debug_img, f"OCR Result: {full_text}", (10, self.screen_h - 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, text_color, 2)
                cv2.putText(debug_img, f"Normalized: {normalized_text}", (10, self.screen_h - 35),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2)
                parsed_text = parsed["label"] if parsed["valid"] else "(unknown)"
                cv2.putText(debug_img, f"Status: {status}", (10, self.screen_h - 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, text_color, 2)
                cv2.putText(debug_img, f"Parsed: {parsed_text}", (10, self.screen_h - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2)
            else:
                cv2.putText(debug_img, "OCR Result: (empty - no text detected)", (10, self.screen_h - 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
                cv2.putText(debug_img, "Status: NO TEXT - SKIP", (10, self.screen_h - 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)

            # Vẽ legend
            legend_y = 30
            cv2.putText(debug_img, "OCR-DIG DEBUG (EasyOCR)", (10, legend_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(debug_img, "- Blue dot: btn_chiem position", (10, legend_y + 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
            cv2.putText(debug_img, "- Red rect: OCR region", (10, legend_y + 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            cv2.putText(debug_img, f"- Blacklist: {self.blacklist_difficulty}", (10, legend_y + 75),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

            # Lưu ảnh debug tổng thể
            debug_path = os.path.join(os.getcwd(), "debug_img", "debug_ocr_difficulty.png")
            cv2.imwrite(debug_path, debug_img)
            print(f"   [DEBUG] Đã lưu ảnh debug OCR: {debug_path}")

            # Lưu thêm ảnh crop gốc
            crop_path = os.path.join(os.getcwd(), "debug_img", "debug_ocr_crop_only.png")
            cv2.imwrite(crop_path, crop)
            print(f"   [DEBUG] Đã lưu ảnh crop gốc: {crop_path}")

        # Nếu không có text hoặc không parse được thì bỏ qua để tránh đánh nhầm.
        if not full_text or not parsed["valid"]:
            return {
                "attackable": False,
                "raw_text": full_text,
                "normalized_text": normalized_text,
                "label": parsed["label"],
                "tier_key": parsed["tier_key"],
                "level": parsed["level"],
                "rank": parsed["rank"],
            }

        if is_blacklisted:
            print(f"   [SKIP] Gặp độ khó trong blacklist: {parsed['label']}")
            return {
                "attackable": False,
                "raw_text": full_text,
                "normalized_text": normalized_text,
                "label": parsed["label"],
                "tier_key": parsed["tier_key"],
                "level": parsed["level"],
                "rank": parsed["rank"],
            }

        return {
            "attackable": True,
            "raw_text": full_text,
            "normalized_text": normalized_text,
            "label": parsed["label"],
            "tier_key": parsed["tier_key"],
            "level": parsed["level"],
            "rank": parsed["rank"],
        }

    def dispatch_troops(self, btn_chiem_pos, debug=True):
        """Quy trình xuất quân"""
        print("   [ACT] Bấm Chiếm...")
        self.device.tap(btn_chiem_pos[0], btn_chiem_pos[1])
        time.sleep(4)

        # Kiểm tra nút Chiếm có còn không
        screen_check = self.device.take_screenshot()
        btn_chiem_check = self.vision.find_template(screen_check, self._get_path("btn_chiem.png"))
        if btn_chiem_check:
            print("   [ERR] Vẫn thấy nút Chiếm sau khi bấm! Có thể bị click trượt hoặc popup chưa hiện đủ. "
                  "Bỏ qua điểm này.")
            self.device.tap(2, 2)
            return False

        # Click tối đa 5 đạo (có swipe để cuộn danh sách nếu cần)
        count = 0
        max_troops = 5
        max_swipe_rounds = 3  # Giới hạn số lần swipe để tránh loop vô hạn

        for swipe_round in range(max_swipe_rounds):
            if count >= max_troops:
                break

            # Tìm checkbox trong màn hình hiện tại
            current_screen = self.device.take_screenshot()
            unchecked = self.vision.find_all_templates(current_screen, self._get_path("checkbox_unchecked.png"))

            if not unchecked:
                print(f"   [ACT] Vòng {swipe_round + 1}: Không còn checkbox nào.")
                break

            print(f"   [ACT] Vòng {swipe_round + 1}: Tìm thấy {len(unchecked)} checkbox.")

            # [DEBUG] Vẽ debug cho checkbox (mỗi vòng swipe)
            if debug:
                debug_img = current_screen.copy()
                remaining = max_troops - count  # Số checkbox còn có thể click
                for idx, pt in enumerate(unchecked):
                    x1, y1 = pt[0] - 20, pt[1] - 20
                    x2, y2 = pt[0] + 20, pt[1] + 20
                    color = (0, 255, 0) if idx < remaining else (0, 165, 255)
                    cv2.rectangle(debug_img, (x1, y1), (x2, y2), color, 2)
                    cv2.circle(debug_img, (pt[0], pt[1]), 5, color, -1)
                    cv2.putText(debug_img, str(idx + 1), (pt[0] + 25, pt[1] + 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                legend_y = 30
                cv2.putText(debug_img, f"DISPATCH - Round {swipe_round + 1}: {len(unchecked)} checkbox, already ticked: {count}/{max_troops}",
                            (10, legend_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                cv2.putText(debug_img, "- Green: Will click this round", (10, legend_y + 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                cv2.putText(debug_img, "- Orange: Skipped (over limit)", (10, legend_y + 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)

                debug_path = os.path.join(os.getcwd(), "debug_img", f"debug_dispatch_checkbox_round{swipe_round + 1}.png")
                cv2.imwrite(debug_path, debug_img)
                print(f"   [DEBUG] Đã lưu ảnh debug checkbox vòng {swipe_round + 1}: {debug_path}")

            # Tick các checkbox tìm được (tối đa còn lại)
            for pt in unchecked:
                if count >= max_troops:
                    break
                self.device.tap(pt[0], pt[1])
                time.sleep(0.2)
                count += 1

            # Nếu chưa đủ 5 quân, swipe để cuộn danh sách xuống
            if count < max_troops:
                print(f"   [ACT] Đã tick {count}/{max_troops}. Swipe để tìm thêm quân...")
                # Swipe từ dưới lên trên (kéo danh sách xuống) trong vùng cửa sổ chọn quân
                # Giả định vùng checkbox ở giữa màn hình
                swipe_x = self.screen_w // 2
                swipe_start_y = self.screen_h // 2 + 125
                swipe_end_y = self.screen_h // 2 - 125
                self.device.precise_drag(swipe_x, swipe_start_y, swipe_x, swipe_end_y, duration=2000)
                time.sleep(1.0)

        print(f"   [ACT] Đã tick tổng cộng {count} checkbox.")
        time.sleep(2)

        # Bấm OK Xuất Chiến (chụp màn hình mới sau khi tick)
        screen_after_tick = self.device.take_screenshot()
        btn_ok = self.vision.find_template(screen_after_tick, self._get_path("btn_ok_xuat_chien.png"))
        if btn_ok:
            self.device.tap(btn_ok[0], btn_ok[1])

            # === GỌI HÀM KIỂM TRA CAPTCHA SAU KHI BẤM OK ===
            status = self.safe_wait_and_check(wait_time=1.5)

            if status == "INTERRUPTED":
                print("   [ACT] Bị ngắt bởi Captcha. Yêu cầu thử lại lệnh xuất chiến.")
                return "INTERRUPTED"  # Trả về tín hiệu ngắt
            elif status == "FATAL":
                return "FATAL"

            print("   [ACT] Đã xuất quân thành công!")
            return True

        print("   [ERR] Không tìm thấy nút OK sau khi tick quân! Có thể bị click trượt hoặc popup chưa hiện đủ. "
              "Bỏ qua điểm này.")

        return False

    # ==========================================================
    # PHẦN 3: LOGIC CHÍNH (MAIN COMBAT LOOP)
    # ==========================================================

    def _close_tile_popup(self):
        """Đóng popup ô đất sau khi trinh sát để tiếp tục quét target khác."""
        self.device.tap(self.screen_w // 2, self.screen_h // 2)
        time.sleep(0.3)

    def _collect_attackable_targets(self, targets, max_scan=10):
        """
        Ưu tiên dùng dữ liệu đã có trong map; chỉ OCR lại các ô chưa có profile độ khó.
        Trả về danh sách candidate có thể đánh, đã sắp theo rank tăng dần.
        """
        candidates = []
        need_ocr = []
        cache_hits = 0

        for target_x, target_y in targets:
            tile = self.map.get_tile_info(target_x, target_y)
            state = tile.get("state", "")

            # Tile đã có trong map và còn là RESOURCE => dùng cache, không OCR lại.
            if state == "RESOURCE":
                parsed = self.map.parse_difficulty(tile.get("difficulty", ""))
                diff_label = parsed["label"] if parsed["valid"] else tile.get("difficulty", "") or "UNKNOWN"
                candidates.append(
                    {
                        "x": target_x,
                        "y": target_y,
                        "rank": parsed["rank"] if parsed["valid"] else 999999,
                        "label": diff_label,
                    }
                )
                cache_hits += 1
            else:
                need_ocr.append((target_x, target_y))

        scanned = 0
        for target_x, target_y in need_ocr:
            if scanned >= max_scan:
                break

            self.jump_to_coordinate(target_x, target_y)
            btn_chiem_pos = self.analyze_tile_state(target_x, target_y, debug=False)
            scanned += 1

            if btn_chiem_pos:
                tile = self.map.get_tile_info(target_x, target_y)
                parsed = self.map.parse_difficulty(tile.get("difficulty", ""))
                diff_label = parsed["label"] if parsed["valid"] else tile.get("difficulty", "") or "UNKNOWN"
                candidates.append(
                    {
                        "x": target_x,
                        "y": target_y,
                        "rank": parsed["rank"] if parsed["valid"] else 999999,
                        "label": diff_label,
                    }
                )
                # analyze_tile_state trả về sớm khi attackable nên popup vẫn còn mở.
                self._close_tile_popup()

        print(f"   [COMBAT] Reuse map cache: {cache_hits} ô | OCR mới: {scanned} ô")

        candidates.sort(key=lambda c: (c["rank"], c["x"], c["y"]))
        return candidates

    def scan_and_dig(self):
        """Luồng Dig 2 pha: trinh sát OCR độ khó nhiều ô trước, rồi mới đánh ô dễ nhất."""

        # 1. Lấy danh sách ô mục tiêu từ thuật toán vết dầu loang
        targets = self.map.get_expansion_targets()

        if not targets:
            print("   [COMBAT] Lãnh thổ đang bị bao vây hoặc chưa có dữ liệu. Không tìm thấy ô để mở rộng.")
            return False

        print(f"   [COMBAT] Tìm thấy {len(targets)} ô liền kề có thể mở rộng.")
        preview = []
        for tx, ty in targets[:8]:
            tile = self.map.get_tile_info(tx, ty)
            parsed = self.map.parse_difficulty(tile.get("difficulty", ""))
            diff_label = parsed["label"] if parsed["valid"] else tile.get("difficulty", "?") or "UNKNOWN"
            preview.append(f"({tx},{ty})={diff_label}")
        if preview:
            print("   [COMBAT] Ưu tiên target: " + " | ".join(preview))

        # 2. Pha trinh sát: OCR nhiều target để biết độ khó thực trước khi chọn.
        scan_budget = min(len(targets), 10)
        candidates = self._collect_attackable_targets(targets, max_scan=scan_budget)

        if not candidates:
            print("   [COMBAT] Không có target hợp lệ sau khi trinh sát.")
            return False

        top_preview = [f"({c['x']},{c['y']})={c['label']}" for c in candidates[:8]]
        print("   [COMBAT] Candidate ưu tiên (cache + OCR): " + " | ".join(top_preview))

        # 3. Pha tấn công: duyệt từ dễ đến khó theo rank đã parse.
        for candidate in candidates:
            target_x, target_y = candidate["x"], candidate["y"]
            max_retries = 2
            for attempt in range(max_retries):

                # --- DỊCH CHUYỂN BẰNG TỌA ĐỘ TUYỆT ĐỐI ---
                self.jump_to_coordinate(target_x, target_y)

                # --- PHÂN TÍCH & ĐÁNH ---
                btn_chiem_pos = self.analyze_tile_state(target_x, target_y)

                if btn_chiem_pos:
                    dispatch_status = self.dispatch_troops(btn_chiem_pos)

                    if dispatch_status == True:
                        # Đã xuất quân, cập nhật ô này thành OWNED trong map ảo
                        self.map.update_tile(target_x, target_y, "OWNED")
                        return True
                    elif dispatch_status == "INTERRUPTED":
                        print("   [COMBAT] Bị ngắt do Captcha. Thử lại ô đất này...")
                        continue
                    elif dispatch_status == "FATAL":
                        return False
                    else:
                        # Lỗi kẹt UI, tap đóng popup
                        self.device.tap(self.screen_w // 2, self.screen_h // 2)
                        break
                else:
                    # Không đánh được (là núi, sông, người khác...) -> Đã phân tích xong
                    break

        return False

    def retreat_troops_logic(self, debug=True):
        """
        Quy trình rút quân về thành.
        debug: Nếu True, sẽ lưu ảnh debug để kiểm tra.
        """
        print("   [RETREAT] Bắt đầu quy trình rút quân...")

        # 1. Lấy trực tiếp tọa độ Thành Chính từ MapManager
        if hasattr(self, 'map') and self.map:
            city_x, city_y = self.map.main_city
        else:
            city_x, city_y = 300, 300

        print(f"   [RETREAT] Dịch chuyển về Thành Chính tại ({city_x}, {city_y})...")

        # 2. Dịch chuyển bằng tọa độ tuyệt đối
        self.jump_to_coordinate(city_x, city_y)
        cx, cy = self.screen_w // 2 + 1, self.screen_h // 2 + 1
        # DEBUG: Vẽ điểm tap vào thành chính
        if debug:
            screen = self.device.take_screenshot()
            debug_img = screen.copy()
            cv2.circle(debug_img, (cx, cy), 10, (255, 0, 0), -1)
            cv2.putText(debug_img, "TAP CITY CENTER", (cx + 15, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
            debug_path = os.path.join(os.getcwd(), "debug_img", "debug_retreat_tap_city.png")
            cv2.imwrite(debug_path, debug_img)
            print(f"   [DEBUG] Đã lưu ảnh debug tap thành chính: {debug_path}")
        self.device.tap(cx, cy)
        time.sleep(1.5)

        # 3. Tìm nút Hành Quân
        screen = self.device.take_screenshot()
        btn_hanh_quan = self.vision.find_template(screen, self._get_path("btn_hanh_quan_map.png"))

        if btn_hanh_quan:
            self.device.tap(btn_hanh_quan[0], btn_hanh_quan[1])
            time.sleep(2)

            # 4. Chọn tất cả quân (có swipe để cuộn danh sách nếu cần)
            count = 0
            max_troops = 5
            max_swipe_rounds = 3  # Giới hạn số lần swipe để tránh loop vô hạn

            for swipe_round in range(max_swipe_rounds):
                if count >= max_troops:
                    break

                # Tìm checkbox trong màn hình hiện tại
                current_screen = self.device.take_screenshot()
                unchecked = self.vision.find_all_templates(current_screen, self._get_path("checkbox_unchecked.png"))

                if not unchecked:
                    print(f"   [ACT] Vòng {swipe_round + 1}: Không còn checkbox nào (rút quân).")
                    break

                print(f"   [ACT] Vòng {swipe_round + 1}: Tìm thấy {len(unchecked)} checkbox (rút quân).")

                # [DEBUG] Vẽ debug cho checkbox rút quân (mỗi vòng swipe)
                if debug:
                    debug_img = current_screen.copy()
                    remaining = max_troops - count  # Số checkbox còn có thể click
                    for idx, pt in enumerate(unchecked):
                        x1, y1 = pt[0] - 20, pt[1] - 20
                        x2, y2 = pt[0] + 20, pt[1] + 20
                        color = (0, 255, 0) if idx < remaining else (0, 165, 255)
                        cv2.rectangle(debug_img, (x1, y1), (x2, y2), color, 2)
                        cv2.circle(debug_img, (pt[0], pt[1]), 5, color, -1)
                        cv2.putText(debug_img, str(idx + 1), (pt[0] + 25, pt[1] + 5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                    legend_y = 30
                    cv2.putText(debug_img, f"RETREAT - Round {swipe_round + 1}: {len(unchecked)} checkbox, already ticked: {count}/{max_troops}",
                                (10, legend_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                    cv2.putText(debug_img, "- Green: Will click this round", (10, legend_y + 25),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                    cv2.putText(debug_img, "- Orange: Skipped (over limit)", (10, legend_y + 50),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)

                    debug_path = os.path.join(os.getcwd(), "debug_img", f"debug_retreat_checkbox_round{swipe_round + 1}.png")
                    cv2.imwrite(debug_path, debug_img)
                    print(f"   [DEBUG] Đã lưu ảnh debug checkbox rút quân vòng {swipe_round + 1}: {debug_path}")

                # Tick các checkbox tìm được (tối đa còn lại)
                for pt in unchecked:
                    if count >= max_troops:
                        break
                    self.device.tap(pt[0], pt[1])
                    time.sleep(0.2)
                    count += 1

                # Nếu chưa đủ 5 quân, swipe để cuộn danh sách xuống
                if count < max_troops:
                    print(f"   [ACT] Đã tick {count}/{max_troops}. Swipe để tìm thêm quân...")
                    # Swipe từ dưới lên trên (kéo danh sách xuống) trong vùng cửa sổ chọn quân
                    swipe_x = self.screen_w // 2
                    swipe_start_y = self.screen_h // 2 + 125
                    swipe_end_y = self.screen_h // 2 - 125
                    self.device.swipe(swipe_x, swipe_start_y, swipe_x, swipe_end_y, duration=300)
                    time.sleep(1.0)

            print(f"   [ACT] Đã tick tổng cộng {count} checkbox (rút quân).")
            time.sleep(2)

            # 5. OK (chụp màn hình mới sau khi tick)
            screen_after_tick = self.device.take_screenshot()
            btn_ok = self.vision.find_template(screen_after_tick, self._get_path("btn_ok_xuat_chien.png"))
            if btn_ok:
                self.device.tap(btn_ok[0], btn_ok[1])

                # === GỌI HÀM KIỂM TRA CAPTCHA SAU KHI BẤM OK ===
                status = self.safe_wait_and_check(wait_time=1.5)

                if status == "INTERRUPTED":
                    print("   [ACT] Bị ngắt bởi Captcha. Yêu cầu thử lại lệnh xuất chiến.")
                    return "INTERRUPTED"  # Trả về tín hiệu ngắt
                elif status == "FATAL":
                    return "FATAL"

                time.sleep(3)

                # Chụp màn hình mới để kiểm tra btn_ok2
                screen_after_ok = self.device.take_screenshot()
                btn_ok2 = self.vision.find_template(screen_after_ok, self._get_path("btn_ok_xuat_chien.png"))

                # [DEBUG] Vẽ debug cho btn_ok2
                if debug:
                    debug_img = screen_after_ok.copy()

                    # Vẽ vị trí btn_ok đã bấm trước đó (màu xanh dương)
                    cv2.circle(debug_img, (btn_ok[0], btn_ok[1]), 15, (255, 0, 0), 2)
                    cv2.putText(debug_img, "btn_ok (clicked)", (btn_ok[0] + 20, btn_ok[1] - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

                    if btn_ok2:
                        # Nếu tìm thấy btn_ok2 -> Vẽ màu đỏ (lỗi - nút vẫn còn)
                        cv2.circle(debug_img, (btn_ok2[0], btn_ok2[1]), 20, (0, 0, 255), 3)
                        cv2.rectangle(debug_img, (btn_ok2[0] - 50, btn_ok2[1] - 25),
                                      (btn_ok2[0] + 50, btn_ok2[1] + 25), (0, 0, 255), 2)
                        cv2.putText(debug_img, "btn_ok2 FOUND (ERROR!)", (btn_ok2[0] + 25, btn_ok2[1] + 40),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                        status_text = "STATUS: btn_ok2 FOUND - Retreat FAILED"
                        status_color = (0, 0, 255)
                    else:
                        # Nếu không tìm thấy btn_ok2 -> Thành công (màu xanh lá)
                        status_text = "STATUS: btn_ok2 NOT FOUND - Retreat SUCCESS"
                        status_color = (0, 255, 0)

                    # Vẽ status ở góc dưới
                    cv2.putText(debug_img, status_text, (10, self.screen_h - 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)

                    # Vẽ legend
                    legend_y = 30
                    cv2.putText(debug_img, "RETREAT - btn_ok2 CHECK", (10, legend_y),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    cv2.putText(debug_img, "- Blue circle: btn_ok position (already clicked)", (10, legend_y + 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
                    cv2.putText(debug_img, "- Red circle/rect: btn_ok2 if found (error)", (10, legend_y + 55),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

                    # Lưu ảnh debug
                    debug_path = os.path.join(os.getcwd(), "debug_img", "debug_retreat_btn_ok2.png")
                    cv2.imwrite(debug_path, debug_img)
                    print(f"   [DEBUG] Đã lưu ảnh debug btn_ok2: {debug_path}")

                if btn_ok2:  # Nếu vẫn còn nút OK thì có lỗi
                    print("   [FAIL] Lỗi khi rút quân (Nút OK vẫn còn sau khi bấm).")
                    self.device.tap(2, 2)
                    self.device.tap(cx, cy)  # Tap lại vào thành chính để tắt popup thông tin
                    return False
                else:
                    print("   [DONE] Đã ra lệnh rút quân thành công.")
                    return True

        print("   [FAIL] Lỗi khi rút quân (Không thấy nút hành quân).")
        # Tap ra ngoài để đóng popup
        self.device.tap(2, 2)
        return False
