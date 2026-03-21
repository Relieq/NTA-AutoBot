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

    # ==========================================================
    # PHẦN 1: HỆ THỐNG NAVIGATION (DI CHUYỂN & NEO)
    # ==========================================================

    # def reset_camera_to_city(self, max_retries=3):
    #     """
    #     Tìm Thành Chính và kéo nó về giữa màn hình để làm mốc tọa độ (0,0).
    #     Sẽ thử lại tối đa max_retries lần nếu không tìm thấy.
    #     """
    #     print("   [NAV] Đang Reset Camera về Thành Chính (Neo)...")
    #     center_x, center_y = self.screen_w // 2, self.screen_h // 2
    #
    #     for attempt in range(1, max_retries + 1):
    #         screen = self.device.take_screenshot()
    #
    #         # Tìm ảnh thành chính trên map
    #         # Lưu ý: threshold thấp một chút vì map có thể bị zoom hoặc đổi màu nhẹ
    #         city_pos = self.vision.find_template(screen, self._get_path("thanh_chinh_map.png"), threshold=0.45)
    #
    #         if city_pos:
    #             # Tính độ lệch so với tâm màn hình
    #             dx = center_x - city_pos[0]
    #             dy = center_y - city_pos[1]
    #
    #             # Nếu lệch quá 50px thì kéo về giữa
    #             if abs(dx) > 50 or abs(dy) > 50:
    #                 print(f"   [NAV] Thành lệch ({dx}, {dy}). Đang kéo về giữa...")
    #                 # Kéo map: Swipe từ vị trí thành về tâm
    #                 self.device.precise_drag(city_pos[0], city_pos[1], center_x, center_y)
    #                 time.sleep(1.5)
    #
    #             # Reset biến nhớ
    #             self.camera_offset = [0, 0]
    #             print("   [NAV] Đã Neo thành công. Offset = [0, 0]")
    #             return True
    #         else:
    #             print(f"   [NAV-WARN] Lần {attempt}/{max_retries}: Không tìm thấy Thành Chính. Đang thử lại...")
    #             if attempt < max_retries:
    #                 # Chờ một chút và thử zoom out hoặc kéo ngẫu nhiên để tìm lại
    #                 time.sleep(1.0)
    #                 # Kéo map một chút về hướng trung tâm (giả định thành có thể ở gần)
    #                 self.device.precise_drag(center_x + 100, center_y + 100, center_x, center_y)
    #                 time.sleep(1.0)
    #
    #     print("   [NAV-ERR] Không tìm thấy Thành Chính sau nhiều lần thử! (Có thể đang ở quá xa)")
    #     return False
    #
    # def ensure_target_safe(self, target_x, target_y, debug=True):
    #     """
    #     [QUAN TRỌNG] Kiểm tra mục tiêu có nằm trong Vùng An Toàn không.
    #     Nếu không, thực hiện kéo map để đưa mục tiêu vào vùng an toàn.
    #     Mục đích: Đảm bảo popup thông tin hiện đủ để game KHÔNG tự cuộn map.
    #     debug: Nếu True, sẽ lưu ảnh debug để kiểm tra.
    #     """
    #     # Cấu hình Vùng An Toàn (Safe Zone)
    #     # Popup cao khoảng 360px -> Chừa lề trên 420px
    #     SAFE_TOP = 150
    #     SAFE_BOTTOM = self.screen_h - 150  # Tránh UI bên dưới
    #     SAFE_LEFT = 150  # Tránh UI bên trái
    #     SAFE_RIGHT = self.screen_w - 150  # Tránh UI bên phải
    #
    #     drag_x = 0
    #     drag_y = 0
    #
    #     # Tính toán cần kéo bao nhiêu (Drag Vector)
    #     # Nguyên tắc: Kéo map đi đâu thì mục tiêu sẽ trôi theo đó
    #
    #     # Nếu mục tiêu quá cao -> Kéo map xuống (drag_y > 0)
    #     if target_y < SAFE_TOP:
    #         drag_y = SAFE_TOP - target_y
    #     # Nếu mục tiêu quá thấp -> Kéo map lên (drag_y < 0)
    #     elif target_y > SAFE_BOTTOM:
    #         drag_y = SAFE_BOTTOM - target_y
    #
    #     # Nếu mục tiêu quá trái -> Kéo map sang phải (drag_x > 0)
    #     if target_x < SAFE_LEFT:
    #         drag_x = SAFE_LEFT - target_x
    #     # Nếu mục tiêu quá phải -> Kéo map sang trái (drag_x < 0)
    #     elif target_x > SAFE_RIGHT:
    #         drag_x = SAFE_RIGHT - target_x
    #
    #     # [DEBUG] Vẽ ảnh debug nếu được yêu cầu
    #     if debug:
    #         screen = self.device.take_screenshot()
    #         debug_img = screen.copy()
    #
    #         # Vẽ Safe Zone (hình chữ nhật xanh dương)
    #         cv2.rectangle(debug_img, (SAFE_LEFT, SAFE_TOP), (SAFE_RIGHT, SAFE_BOTTOM), (255, 200, 0), 2)
    #         cv2.putText(debug_img, "SAFE ZONE", (SAFE_LEFT + 10, SAFE_TOP + 30),
    #                     cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 200, 0), 2)
    #
    #         # Vẽ tâm màn hình
    #         cx, cy = self.screen_w // 2, self.screen_h // 2
    #         cv2.circle(debug_img, (cx, cy), 8, (255, 255, 255), -1)
    #         cv2.putText(debug_img, "CENTER", (cx + 10, cy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    #
    #         # Vẽ vị trí mục tiêu ban đầu (chấm đỏ)
    #         cv2.circle(debug_img, (int(target_x), int(target_y)), 12, (0, 0, 255), -1)
    #         cv2.putText(debug_img, f"TARGET ({target_x}, {target_y})", (int(target_x) + 15, int(target_y) - 10),
    #                     cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    #
    #         # Tính vị trí mục tiêu mới
    #         new_x = int(target_x + drag_x)
    #         new_y = int(target_y + drag_y)
    #
    #         # Nếu có drag thì vẽ thêm
    #         if drag_x != 0 or drag_y != 0:
    #             # Vẽ vị trí mục tiêu mới (chấm xanh lá)
    #             cv2.circle(debug_img, (new_x, new_y), 12, (0, 255, 0), -1)
    #             cv2.putText(debug_img, f"NEW ({new_x}, {new_y})", (new_x + 15, new_y + 20),
    #                         cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    #
    #             # Vẽ đường nối từ target cũ sang target mới (mũi tên cam)
    #             cv2.arrowedLine(debug_img, (int(target_x), int(target_y)), (new_x, new_y),
    #                             (0, 165, 255), 3, tipLength=0.2)
    #
    #             # Vẽ vector drag từ tâm (mũi tên tím)
    #             end_drag_x = cx + drag_x
    #             end_drag_y = cy + drag_y
    #             cv2.arrowedLine(debug_img, (cx, cy), (int(end_drag_x), int(end_drag_y)),
    #                             (255, 0, 255), 2, tipLength=0.15)
    #             cv2.putText(debug_img, f"DRAG ({drag_x}, {drag_y})", (cx + 10, cy + 30),
    #                         cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 2)
    #
    #             status_text = "UNSAFE - NEED DRAG"
    #             status_color = (0, 0, 255)
    #         else:
    #             status_text = "SAFE - NO DRAG NEEDED"
    #             status_color = (0, 255, 0)
    #
    #         # Vẽ status
    #         cv2.putText(debug_img, status_text, (10, self.screen_h - 20),
    #                     cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)
    #
    #         # Vẽ legend
    #         legend_y = 30
    #         cv2.putText(debug_img, "LEGEND:", (10, legend_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
    #                     (255, 255, 255), 2)
    #         cv2.putText(debug_img, "- Cyan rect: Safe Zone", (10, legend_y + 25), cv2.FONT_HERSHEY_SIMPLEX,
    #                     0.5, (255, 200, 0), 1)
    #         cv2.putText(debug_img, "- Red dot: Original target", (10, legend_y + 50), cv2.FONT_HERSHEY_SIMPLEX,
    #                     0.5, (0, 0, 255), 1)
    #         cv2.putText(debug_img, "- Green dot: New target", (10, legend_y + 75), cv2.FONT_HERSHEY_SIMPLEX,
    #                     0.5, (0, 255, 0), 1)
    #         cv2.putText(debug_img, "- Orange arrow: Target move", (10, legend_y + 100), cv2.FONT_HERSHEY_SIMPLEX,
    #                     0.5, (0, 165, 255), 1)
    #         cv2.putText(debug_img, "- Purple arrow: Drag vector", (10, legend_y + 125), cv2.FONT_HERSHEY_SIMPLEX,
    #                     0.5, (255, 0, 255), 1)
    #
    #         # Lưu ảnh debug
    #         debug_path = os.path.join(os.getcwd(), "debug_img", "debug_safe_zone.png")
    #         cv2.imwrite(debug_path, debug_img)
    #         print(f"   [DEBUG] Đã lưu ảnh debug Safe Zone: {debug_path}")
    #
    #     # Thực hiện Drag nếu cần
    #     if drag_x != 0 or drag_y != 0:
    #         print(f"   [SAFE-GUARD] Mục tiêu ({target_x}, {target_y}) gần rìa. Drag map: ({drag_x}, {drag_y})")
    #
    #         # Thực hiện Swipe từ giữa màn hình
    #         start_sw_x, start_sw_y = self.screen_w // 2, self.screen_h // 2
    #         end_sw_x = start_sw_x + drag_x
    #         end_sw_y = start_sw_y + drag_y
    #
    #         # Dùng precise_drag (kéo chậm) để tránh quán tính
    #         self.device.precise_drag(start_sw_x, start_sw_y, end_sw_x, end_sw_y)
    #
    #         # Cập nhật bộ nhớ đường đi (Dead Reckoning)
    #         self.camera_offset[0] += drag_x
    #         self.camera_offset[1] += drag_y
    #
    #         # Tính toán tọa độ MỚI của mục tiêu trên màn hình sau khi kéo
    #         new_x = int(target_x + drag_x)
    #         new_y = int(target_y + drag_y)
    #         return new_x, new_y
    #
    #     # Nếu đã an toàn thì trả về tọa độ cũ
    #     return target_x, target_y
    #
    # def return_to_base(self):
    #     """
    #     Sử dụng trí nhớ (camera_offset) để cuộn ngược về nhà.
    #     """
    #     print(f"   [RETREAT] Đang quay về thành. Offset cần bù: {self.camera_offset}")
    #
    #     # Lặp lại cho đến khi về gần gốc (sai số < 50px)
    #     while abs(self.camera_offset[0]) > 50 or abs(self.camera_offset[1]) > 50:
    #         # Vector quay về là NGƯỢC LẠI với offset (-offset)
    #         back_x = -self.camera_offset[0]
    #         back_y = -self.camera_offset[1]
    #
    #         # Cắt ngắn mỗi bước đi tối đa 300px để game load kịp
    #         step_x = int(np.clip(back_x, -400, 400))
    #         step_y = int(np.clip(back_y, -400, 400))
    #
    #         # Swipe
    #         cx, cy = self.screen_w // 2, self.screen_h // 2
    #         self.device.precise_drag(cx, cy, cx + step_x, cy + step_y)
    #
    #         # Trừ dần offset
    #         self.camera_offset[0] += step_x
    #         self.camera_offset[1] += step_y
    #
    #     print("   [RETREAT] Đã về khu vực thành. Căn chỉnh tinh lần cuối...")
    #     self.reset_camera_to_city()

    # ==========================================================
    # PHẦN 2: LOGIC TÌM MỤC TIÊU & PHÂN TÍCH
    # ==========================================================

    # def find_border_targets(self, debug=True):
    #     """
    #     Tìm viền xanh -> Lấy contour -> Tính điểm liền kề (4 hướng) thay vì chéo.
    #     debug: Nếu True, sẽ lưu ảnh debug để kiểm tra.
    #     """
    #     screen = self.device.take_screenshot()
    #     # Lọc màu
    #     mask = cv2.inRange(screen, self.lower_green, self.upper_green)
    #
    #     # Tìm đường viền
    #     contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    #
    #     # [DEBUG] Tạo bản sao để vẽ debug
    #     if debug:
    #         debug_img = screen.copy()
    #         # Vẽ tất cả contours màu vàng
    #         cv2.drawContours(debug_img, contours, -1, (0, 255, 255), 2)
    #
    #     targets = []
    #     if contours:
    #         # Lấy contour lớn nhất
    #         largest_contour = max(contours, key=cv2.contourArea)
    #
    #         # [DEBUG] Vẽ contour lớn nhất màu xanh dương đậm
    #         if debug:
    #             cv2.drawContours(debug_img, [largest_contour], -1, (255, 0, 0), 3)
    #
    #         # Làm mượt contour
    #         epsilon = 0.005 * cv2.arcLength(largest_contour, True)
    #         approx = cv2.approxPolyDP(largest_contour, epsilon, True)
    #
    #         # [DEBUG] Vẽ contour đã làm mượt màu tím
    #         if debug:
    #             cv2.drawContours(debug_img, [approx], -1, (255, 0, 255), 2)
    #
    #         # Lấy tâm màn hình (Thành chính)
    #         cx, cy = self.screen_w // 2, self.screen_h // 2
    #
    #         # [DEBUG] Vẽ tâm màn hình
    #         if debug:
    #             cv2.circle(debug_img, (cx, cy), 10, (0, 0, 255), -1)  # Chấm đỏ tâm
    #             cv2.putText(debug_img, "CENTER", (cx + 15, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    #
    #         # Duyệt qua các điểm trên viền
    #         for i in range(0, len(approx)):  # Step để không quá dày
    #             pt = approx[i][0]
    #
    #             # [DEBUG] Vẽ điểm trên viền gốc màu xanh lá
    #             if debug:
    #                 cv2.circle(debug_img, (pt[0], pt[1]), 5, (0, 255, 0), -1)
    #
    #             # Tính vector từ Tâm -> Điểm Viền
    #             vec_x = pt[0] - cx
    #             vec_y = pt[1] - cy
    #
    #             # --- LOGIC MỚI: DOMINANT AXIS ---
    #             # Offset cần phải đủ lớn để nhảy sang ô bên cạnh (khoảng 1/2 đến 1 ô)
    #             # Bạn cần chỉnh số này cho khớp kích thước ô đất
    #             offset = 30
    #
    #             target_x = pt[0]
    #             target_y = pt[1]
    #
    #             # Kiểm tra trục nào lớn hơn thì đi theo trục đó
    #             if abs(vec_x) > abs(vec_y):
    #                 # Ưu tiên trục Ngang (Left/Right)
    #                 if vec_x > 0:
    #                     target_x += offset  # Đi sang Phải
    #                 else:
    #                     target_x -= offset  # Đi sang Trái
    #                 target_y += random.Random(i).randint(-15, 15)  # Thêm nhiễu ngẫu nhiên trên trục phụ
    #             else:
    #                 # Ưu tiên trục Dọc (Up/Down)
    #                 if vec_y > 0:
    #                     target_y += offset  # Đi xuống Dưới
    #                 else:
    #                     target_y -= offset  # Đi lên Trên
    #                 target_x += random.Random(i).randint(-15, 15)  # Thêm nhiễu ngẫu nhiên trên trục phụ
    #
    #             # Làm tròn thành số nguyên
    #             target_x = int(target_x)
    #             target_y = int(target_y)
    #
    #             # Chỉ lấy điểm nằm trong màn hình
    #             margin = 30
    #             if margin < target_x < self.screen_w - margin and margin < target_y < self.screen_h - margin:
    #                 targets.append((target_x, target_y))
    #
    #                 # [DEBUG] Vẽ điểm target màu cam và đường nối
    #                 if debug:
    #                     cv2.circle(debug_img, (target_x, target_y), 7, (0, 165, 255), -1)  # Cam
    #                     cv2.line(debug_img, (pt[0], pt[1]), (target_x, target_y), (0, 165, 255), 1)
    #
    #     # Sắp xếp: Ưu tiên điểm gần tâm nhất
    #     targets.sort(key=lambda p: math.hypot(p[0] - self.screen_w // 2, p[1] - self.screen_h // 2))
    #
    #     # Lọc bớt các điểm trùng nhau hoặc quá gần nhau (để tránh click lại cùng 1 ô)
    #     unique_targets = []
    #     for idx, t in enumerate(targets):
    #         # Nếu điểm t cách tất cả điểm đã chọn > 40px thì mới lấy
    #         if all(math.hypot(t[0] - u[0], t[1] - u[1]) > 40 for u in unique_targets):
    #             unique_targets.append(t)
    #
    #     # [DEBUG] Vẽ các điểm unique_targets cuối cùng với số thứ tự
    #     if debug:
    #         for idx, t in enumerate(unique_targets):
    #             # Vẽ vòng tròn đỏ lớn hơn
    #             cv2.circle(debug_img, t, 12, (0, 0, 255), 2)
    #             # Đánh số thứ tự
    #             cv2.putText(debug_img, str(idx + 1), (t[0] + 15, t[1] + 5),
    #                         cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    #
    #         # Vẽ legend (chú thích)
    #         legend_y = 30
    #         cv2.putText(debug_img, "LEGEND:", (10, legend_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
    #                     (255, 255, 255), 2)
    #         cv2.putText(debug_img, "- Yellow: All contours", (10, legend_y + 25), cv2.FONT_HERSHEY_SIMPLEX,
    #                     0.5, (0, 255, 255), 1)
    #         cv2.putText(debug_img, "- Blue: Largest contour", (10, legend_y + 50), cv2.FONT_HERSHEY_SIMPLEX,
    #                     0.5, (255, 0, 0), 1)
    #         cv2.putText(debug_img, "- Purple: Smoothed contour", (10, legend_y + 75), cv2.FONT_HERSHEY_SIMPLEX,
    #                     0.5, (255, 0, 255), 1)
    #         cv2.putText(debug_img, "- Green: Border points", (10, legend_y + 100), cv2.FONT_HERSHEY_SIMPLEX,
    #                     0.5, (0, 255, 0), 1)
    #         cv2.putText(debug_img, "- Orange: Target offset", (10, legend_y + 125), cv2.FONT_HERSHEY_SIMPLEX,
    #                     0.5, (0, 165, 255), 1)
    #         cv2.putText(debug_img, "- Red circle: Final targets", (10, legend_y + 150), cv2.FONT_HERSHEY_SIMPLEX,
    #                     0.5, (0, 0, 255), 1)
    #
    #         # Lưu ảnh debug
    #         debug_path = os.path.join(os.getcwd(), "debug_img", "debug_border_targets.png")
    #         cv2.imwrite(debug_path, debug_img)
    #         print(f"   [DEBUG] Đã lưu ảnh debug viền: {debug_path}")
    #
    #         # Lưu thêm mask để kiểm tra lọc màu
    #         mask_path = os.path.join(os.getcwd(), "debug_img", "debug_border_mask.png")
    #         cv2.imwrite(mask_path, mask)
    #         print(f"   [DEBUG] Đã lưu mask lọc màu: {mask_path}")
    #
    #     return unique_targets

    # ==========================================================
    # LOGIC ĐIỀU HƯỚNG THEO TỌA ĐỘ (ABSOLUTE NAVIGATION)
    # ==========================================================

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
                if self.analyze_difficulty(screen, btn_chiem, debug=False):
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

        print(f"   [OCR-DIG] Đọc được: {full_text}")

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
                # Kiểm tra blacklist để đổi màu
                is_blacklisted = any(bad.lower() in full_text.lower() for bad in self.blacklist_difficulty)
                text_color = (0, 0, 255) if is_blacklisted else (0, 255, 0)
                status = "BLACKLISTED - SKIP" if is_blacklisted else "OK - ATTACK"

                cv2.putText(debug_img, f"OCR Result: {full_text}", (10, self.screen_h - 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, text_color, 2)
                cv2.putText(debug_img, f"Status: {status}", (10, self.screen_h - 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, text_color, 2)
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

        # Nếu không có text thì bỏ qua
        if not full_text:
            return False

        # Check Blacklist
        for bad in self.blacklist_difficulty:
            if bad.lower() in full_text.lower():
                print(f"   [SKIP] Gặp độ khó trong blacklist: {bad}")
                return False

        return True

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

    def scan_and_dig(self):
        """Luồng xử lý Dig mới dựa trên Bản đồ số"""

        # 1. Lấy danh sách ô mục tiêu từ thuật toán vết dầu loang
        targets = self.map.get_expansion_targets()

        if not targets:
            print("   [COMBAT] Lãnh thổ đang bị bao vây hoặc chưa có dữ liệu. Không tìm thấy ô để mở rộng.")
            return False

        print(f"   [COMBAT] Tìm thấy {len(targets)} ô liền kề có thể mở rộng.")

        # 2. Duyệt từng mục tiêu
        for target_x, target_y in targets:
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
