import os
import time
from datetime import datetime

import cv2


class CaptchaSolver:
    def __init__(self, assets_dir="assets", debug_enabled=None, debug_dir="debug_img/captcha"):
        self.assets_dir = self._resolve_assets_dir(assets_dir)
        env_debug = os.getenv("CAPTCHA_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
        self.debug_enabled = env_debug if debug_enabled is None else bool(debug_enabled)
        self.debug_dir = os.path.abspath(debug_dir)

    def _resolve_assets_dir(self, assets_dir):
        candidates = [
            os.path.abspath(assets_dir),
            os.path.abspath(os.path.join(os.getcwd(), assets_dir)),
            os.path.abspath(os.path.join(os.getcwd(), "_internal", assets_dir)),
        ]
        for p in candidates:
            if os.path.isdir(p):
                return p
        return candidates[0]

    def _debug_subdir(self, subdir):
        path = os.path.join(self.debug_dir, subdir)
        os.makedirs(path, exist_ok=True)
        return path

    def _debug_save(self, img, subdir, filename):
        if img is None or not self.debug_enabled:
            return
        path = os.path.join(self._debug_subdir(subdir), filename)
        cv2.imwrite(path, img)

    def _debug_draw_multiline(self, canvas, lines, origin=(10, 25), color=(255, 255, 255), scale=0.6, thickness=1):
        x, y = origin
        step = int(26 * max(scale, 0.5))
        for line in lines:
            cv2.putText(canvas, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness + 2)
            cv2.putText(canvas, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness)
            y += step

    def _icon_boxes(self):
        """Tọa độ ước lượng của 4 icon captcha trên màn hình 1600x900."""
        icon_y_start = 368
        icon_y_end = 511
        box_width = 112
        spacing = 0
        start_x = 578

        boxes = []
        for i in range(4):
            x1 = start_x + int(i * (box_width + spacing))
            x2 = x1 + int(box_width)
            boxes.append((x1, icon_y_start, x2, icon_y_end))
        return boxes

    def _find_btn_ok_captcha(self, screen_img, btn_ok_template=None, threshold=0.7):
        if screen_img is None:
            return False, 0.0, None, None

        template = btn_ok_template
        if template is None:
            template = cv2.imread(os.path.join(self.assets_dir, "btn_ok_captcha.png"))
        if template is None:
            return False, 0.0, None, None

        res = cv2.matchTemplate(screen_img, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        found = max_val >= float(threshold)
        return found, float(max_val), max_loc, template

    def _debug_capture_spam_attempt(self, screen_img, attempt_idx, phase, ok_found, ok_score, ok_loc, template, stamp):
        if not self.debug_enabled or screen_img is None:
            return

        overlay = screen_img.copy()
        lines = [
            "CAPTCHA SPAM MODE",
            f"attempt={attempt_idx}",
            f"phase={phase}",
            f"btn_ok_found={ok_found}",
            f"btn_ok_score={ok_score:.4f}",
        ]

        if ok_loc is not None and template is not None:
            h, w = template.shape[:2]
            x1, y1 = ok_loc
            x2, y2 = x1 + w, y1 + h
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (255, 200, 0), 2)
            lines.append(f"btn_ok_loc=({x1},{y1})")

        fx1, fy1, fx2, fy2 = self._icon_boxes()[0]
        cv2.rectangle(overlay, (fx1, fy1), (fx2, fy2), (0, 255, 0), 2)
        lines.append("first_icon=#1")

        self._debug_draw_multiline(overlay, lines, origin=(10, 30), color=(255, 255, 255), scale=0.6, thickness=1)
        self._debug_save(overlay, "spam", f"{stamp}_attempt_{attempt_idx:02d}_{phase}.png")

    def detect_captcha(self, screen_img):
        title = cv2.imread(os.path.join(self.assets_dir, "title_captcha.png"))
        if title is None or screen_img is None:
            return False

        res = cv2.matchTemplate(screen_img, title, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        return max_val > 0.7

    def solve(self, device, screen_img):
        print("   [CAPTCHA] Phát hiện Captcha. Chuyển sang chế độ spam chọn icon #1...")
        debug_stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        max_attempts = 10
        ok_threshold = 0.7
        wait_after_icon_tap = 0.25
        wait_after_ok_tap = 0.9

        btn_ok_template = cv2.imread(os.path.join(self.assets_dir, "btn_ok_captcha.png"))
        if btn_ok_template is None:
            print("   [CAPTCHA-ERR] Thiếu template btn_ok_captcha.png")
            return False

        x1, y1, x2, y2 = self._icon_boxes()[0]
        first_icon_click = (int((x1 + x2) / 2), int((y1 + y2) / 2))

        current_screen = screen_img
        for attempt in range(1, max_attempts + 1):
            if current_screen is None:
                current_screen = device.take_screenshot()
                if current_screen is None:
                    continue

            ok_found_before, ok_score_before, ok_loc_before, _ = self._find_btn_ok_captcha(
                current_screen,
                btn_ok_template=btn_ok_template,
                threshold=ok_threshold,
            )
            self._debug_capture_spam_attempt(
                current_screen,
                attempt,
                "before",
                ok_found_before,
                ok_score_before,
                ok_loc_before,
                btn_ok_template,
                debug_stamp,
            )

            if not ok_found_before:
                print(f"   [CAPTCHA] Không còn btn_ok_captcha (attempt {attempt}) -> captcha đã hết.")
                return True

            print(f"   [CAPTCHA] Attempt {attempt}/{max_attempts}: chọn icon #1 và bấm OK.")
            device.tap(first_icon_click[0], first_icon_click[1])
            time.sleep(wait_after_icon_tap)

            # Chụp lại để định vị nút OK chính xác rồi bấm.
            screen_after_pick = device.take_screenshot()
            ok_found_pick, ok_score_pick, ok_loc_pick, _ = self._find_btn_ok_captcha(
                screen_after_pick,
                btn_ok_template=btn_ok_template,
                threshold=ok_threshold,
            )
            self._debug_capture_spam_attempt(
                screen_after_pick,
                attempt,
                "after_pick",
                ok_found_pick,
                ok_score_pick,
                ok_loc_pick,
                btn_ok_template,
                debug_stamp,
            )

            if ok_found_pick and ok_loc_pick is not None:
                ok_x = ok_loc_pick[0] + btn_ok_template.shape[1] // 2
                ok_y = ok_loc_pick[1] + btn_ok_template.shape[0] // 2
                device.tap(ok_x, ok_y)
                time.sleep(wait_after_ok_tap)
            else:
                # Không thấy OK ngay sau khi chọn, có thể popup đã đổi trạng thái; kiểm tra lại ở vòng sau.
                time.sleep(0.5)

            current_screen = device.take_screenshot()
            ok_found_after, ok_score_after, ok_loc_after, _ = self._find_btn_ok_captcha(
                current_screen,
                btn_ok_template=btn_ok_template,
                threshold=ok_threshold,
            )
            self._debug_capture_spam_attempt(
                current_screen,
                attempt,
                "after_ok",
                ok_found_after,
                ok_score_after,
                ok_loc_after,
                btn_ok_template,
                debug_stamp,
            )

            if not ok_found_after:
                print(f"   [CAPTCHA] Đã qua captcha sau attempt {attempt}.")
                return True

        print("   [CAPTCHA-WARN] Hết số lần spam captcha nhưng vẫn còn captcha.")
        return False
