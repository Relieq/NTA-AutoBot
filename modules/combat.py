import time
import os
import sys
import json
import re
from datetime import datetime
import cv2
import easyocr
try:
    from paddleocr import PaddleOCR
except Exception:
    PaddleOCR = None


class CombatManager:
    def __init__(self, device, vision, map_manager, captcha_solver=None, debug_enabled=None, debug_dir="debug_img/combat"):
        self.device = device
        self.vision = vision
        self.map = map_manager
        self.captcha_solver = captcha_solver  # Nhận instance từ main.py
        self.assets_dir = self._resolve_resource_dir("assets")
        env_debug = os.getenv("COMBAT_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
        self.debug_enabled = env_debug if debug_enabled is None else bool(debug_enabled)
        self.debug_dir = os.path.abspath(debug_dir)
        self._easyocr_unavailable_logged = False

        # Khởi tạo EasyOCR - hỗ trợ tiếng Việt
        # gpu=False để dùng CPU, đổi thành True nếu có GPU NVIDIA
        self.ocr = self._init_easyocr_reader(['vi'], "combat")
        # OCR thời gian hành quân dùng PaddleOCR (ổn định hơn cho chuỗi thời gian ngắn).
        self.time_ocr = None
        if PaddleOCR is not None:
            try:
                self.time_ocr = PaddleOCR(use_angle_cls=True, lang='en', enable_mkldnn=False)
                print("   [COMBAT] PaddleOCR (time) init thành công.")
            except Exception as exc:
                print(f"   [COMBAT-WARN] PaddleOCR (time) init lỗi, fallback EasyOCR: {exc}")
        else:
            print("   [COMBAT-WARN] Không import được PaddleOCR, fallback EasyOCR cho time OCR.")

        # Cấu hình danh sách đen (Blacklist độ khó)
        self.combat_timing = self._load_json_config(
            os.path.join("config", "combat_timing.json"),
            {
                "default_battle_duration_seconds": 150,
                "max_scout_targets_per_cycle": 10,
                "battle_duration_seconds": {
                    "de": 20,
                    "nhap_mon": 80,
                    "thuong": 150,
                    "tang_bac": 240,
                    "kho": 420,
                    "dia_nguc": 480,
                },
            },
        )
        self.difficulty_blacklist = self._load_json_config(
            os.path.join("config", "combat_difficulty_blacklist.json"),
            {
                "enabled": True,
                "tiers": {
                    "de": {"default": False, "levels": {}},
                    "nhap_mon": {"default": False, "levels": {}},
                    "thuong": {"default": False, "levels": {}},
                    "tang_bac": {"default": False, "levels": {"2": True, "3": True}},
                    "kho": {"default": False, "levels": {"1": True, "2": True, "3": True}},
                    "dia_nguc": {"default": True, "levels": {}},
                },
            },
        )
        self.first_dispatch_status_path = os.path.join("config", "combat_first_dispatch_status.json")
        self.first_dispatch_status = self._load_json_config(
            self.first_dispatch_status_path,
            {
                "enabled": True,
                "tiers": {
                    "de": False,
                    "nhap_mon": False,
                    "thuong": False,
                    "tang_bac": False,
                    "kho": False,
                    "dia_nguc": False,
                },
            },
        )
        self._normalize_first_dispatch_status()

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

    def _resolve_resource_dir(self, name):
        candidates = [
            os.path.abspath(os.path.join(os.getcwd(), name)),
            os.path.abspath(os.path.join(os.getcwd(), "_internal", name)),
        ]
        for p in candidates:
            if os.path.isdir(p):
                return p
        return candidates[0]

    def _resolve_easyocr_model_dir(self):
        candidates = [
            os.path.abspath(os.path.join(os.getcwd(), "third_party", "easyocr", "model")),
            os.path.abspath(os.path.join(os.getcwd(), "_internal", "third_party", "easyocr", "model")),
        ]

        if getattr(sys, "frozen", False):
            exe_root = os.path.dirname(sys.executable)
            candidates.append(os.path.abspath(os.path.join(exe_root, "third_party", "easyocr", "model")))
            candidates.append(os.path.abspath(os.path.join(exe_root, "_internal", "third_party", "easyocr", "model")))
            meipass = getattr(sys, "_MEIPASS", "")
            if meipass:
                candidates.append(os.path.abspath(os.path.join(meipass, "third_party", "easyocr", "model")))

        for path in candidates:
            if not os.path.isdir(path):
                continue
            has_model = any(name.lower().endswith(".pth") for name in os.listdir(path))
            if has_model:
                return path
        return None

    def _init_easyocr_reader(self, languages, label):
        model_dir = self._resolve_easyocr_model_dir()

        if model_dir:
            try:
                reader = easyocr.Reader(
                    languages,
                    gpu=False,
                    verbose=False,
                    model_storage_directory=model_dir,
                    download_enabled=False,
                )
                print(f"   [COMBAT] EasyOCR ({label}) init thành công với model bundled: {model_dir}")
                return reader
            except Exception as exc:
                print(f"   [COMBAT-WARN] EasyOCR ({label}) init từ model bundled lỗi: {exc}")

        if getattr(sys, "frozen", False):
            print(
                f"   [COMBAT-WARN] EasyOCR ({label}) không có model bundled trong bản .exe. "
                f"Bỏ qua EasyOCR để tránh tự tải model runtime."
            )
            return None

        try:
            reader = easyocr.Reader(languages, gpu=False, verbose=False)
            print(f"   [COMBAT] EasyOCR ({label}) init thành công (source mode).")
            return reader
        except Exception as exc:
            print(f"   [COMBAT-WARN] EasyOCR ({label}) init lỗi: {exc}")
            return None

    def _resolve_config_path(self, relative_path):
        candidates = [
            os.path.abspath(os.path.join(os.getcwd(), relative_path)),
            os.path.abspath(os.path.join(os.getcwd(), "_internal", relative_path)),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return candidates[0]

    def _ocr_time_text(self, processed_img):
        if processed_img is None:
            return ""

        if self.time_ocr is not None:
            try:
                output = self.time_ocr.predict(processed_img)
                results = list(output)
                if results:
                    rec_texts = results[0].get("rec_texts", [])
                    return " ".join(rec_texts) if rec_texts else ""
            except Exception as exc:
                print(f"   [OCR-ERR] PaddleOCR time lỗi, fallback EasyOCR: {exc}")

        if self.ocr is None:
            if not self._easyocr_unavailable_logged:
                print("   [OCR-ERR] EasyOCR không khả dụng cho fallback OCR thời gian.")
                self._easyocr_unavailable_logged = True
            return ""

        try:
            rgb = cv2.cvtColor(processed_img, cv2.COLOR_BGR2RGB)
            results = self.ocr.readtext(rgb)
            rec_texts = [item[1] for item in results] if results else []
            return " ".join(rec_texts) if rec_texts else ""
        except Exception as exc:
            print(f"   [OCR-ERR] EasyOCR time fallback lỗi: {exc}")
            return ""

    def _get_path(self, filename):
        return os.path.join(self.assets_dir, filename)

    def _should_debug(self, debug_override):
        if debug_override is None:
            return self.debug_enabled
        return bool(debug_override)

    def _load_json_config(self, relative_path, default_value):
        full_path = self._resolve_config_path(relative_path)
        if not os.path.exists(full_path):
            print(f"   [COMBAT] Không thấy '{relative_path}', dùng cấu hình mặc định.")
            return default_value

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as exc:
            print(f"   [COMBAT-WARN] Lỗi đọc '{relative_path}': {exc}. Dùng mặc định.")
        return default_value

    def _save_json_config(self, relative_path, data):
        full_path = os.path.join(os.getcwd(), relative_path)
        try:
            parent = os.path.dirname(full_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as exc:
            print(f"   [COMBAT-WARN] Không thể ghi '{relative_path}': {exc}")
            return False

    def _normalize_first_dispatch_status(self):
        expected_tiers = ["de", "nhap_mon", "thuong", "tang_bac", "kho", "dia_nguc"]
        changed = False

        if not isinstance(self.first_dispatch_status, dict):
            self.first_dispatch_status = {"enabled": True, "tiers": {}}
            changed = True

        if "enabled" not in self.first_dispatch_status:
            self.first_dispatch_status["enabled"] = True
            changed = True

        tiers = self.first_dispatch_status.get("tiers", {})
        if not isinstance(tiers, dict):
            tiers = {}
            self.first_dispatch_status["tiers"] = tiers
            changed = True

        for tier in expected_tiers:
            if tier not in tiers:
                tiers[tier] = False
                changed = True
            else:
                tiers[tier] = bool(tiers[tier])

        if changed:
            self._save_json_config(self.first_dispatch_status_path, self.first_dispatch_status)

    def _should_handle_first_dispatch_warning(self, tier_key):
        if not self.first_dispatch_status.get("enabled", True):
            return True
        if not tier_key:
            return True
        tiers = self.first_dispatch_status.get("tiers", {})
        return not bool(tiers.get(tier_key, False))

    def _mark_first_dispatch_done(self, tier_key):
        if not tier_key:
            return
        tiers = self.first_dispatch_status.get("tiers", {})
        if not isinstance(tiers, dict):
            tiers = {}
            self.first_dispatch_status["tiers"] = tiers
        if bool(tiers.get(tier_key, False)):
            return
        tiers[tier_key] = True
        if self._save_json_config(self.first_dispatch_status_path, self.first_dispatch_status):
            print(f"   [COMBAT] Đánh dấu đã xử lý lần đầu cho dải độ khó: {tier_key}")

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

    def _is_blacklisted_difficulty(self, tier_key, level):
        if not self.difficulty_blacklist.get("enabled", True):
            return False

        tiers = self.difficulty_blacklist.get("tiers", {})
        tier_cfg = tiers.get(tier_key, {})
        if not isinstance(tier_cfg, dict):
            return False

        levels = tier_cfg.get("levels", {}) if isinstance(tier_cfg.get("levels", {}), dict) else {}
        level_key = str(level)
        if level_key in levels:
            return bool(levels[level_key])

        return bool(tier_cfg.get("default", False))

    def _get_battle_duration_seconds(self, tier_key):
        durations = self.combat_timing.get("battle_duration_seconds", {})
        if tier_key in durations:
            return int(durations[tier_key])
        return int(self.combat_timing.get("default_battle_duration_seconds", 150))

    def _normalize_time_text(self, text):
        if not text:
            return ""
        text = str(text).strip().lower()
        # Chuẩn hóa OCR dễ nhầm ký tự
        text = text.replace("o", "0")
        text = text.replace("l", "1")
        text = text.replace("i", "1")
        text = text.replace(" ", "")
        # Chuẩn hóa các loại dấu ngăn cách về ':' để parse thống nhất.
        text = re.sub(r"[.,;-]", ":", text)
        text = re.sub(r":+", ":", text)
        return text

    def _parse_time_seconds(self, text):
        normalized = self._normalize_time_text(text)
        if not normalized:
            return None

        match_hms = re.search(r"(\d{1,2}):(\d{2}):(\d{2})", normalized)
        if match_hms:
            hh = int(match_hms.group(1))
            mm = int(match_hms.group(2))
            ss = int(match_hms.group(3))
            return hh * 3600 + mm * 60 + ss

        match_ms = re.search(r"(\d{1,2}):(\d{2})", normalized)
        if match_ms:
            mm = int(match_ms.group(1))
            ss = int(match_ms.group(2))
            return mm * 60 + ss

        return None

    def _extract_travel_time_seconds(self, screen_img, checkbox_center, debug_prefix="travel"):
        """OCR vùng dòng quân tương ứng checkbox, trả về số giây hành quân nếu parse được."""
        h, w = screen_img.shape[:2]
        cx, cy = checkbox_center

        x1 = max(0, cx + 30)
        x2 = min(w, cx + 250)
        y1 = max(0, cy)
        y2 = min(h, cy + 100)

        if x2 <= x1 or y2 <= y1:
            self._save_travel_time_debug(
                screen_img,
                checkbox_center,
                (x1, y1, x2, y2),
                "",
                None,
                debug_prefix,
                None,
            )
            return None

        crop = screen_img[y1:y2, x1:x2]
        enlarged = cv2.resize(crop, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        processed_img = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

        try:
            text = self._ocr_time_text(processed_img)
        except Exception as exc:
            print(f"   [OCR-ERR] Lỗi OCR thời gian hành quân: {exc}")
            self._save_travel_time_debug(
                screen_img,
                checkbox_center,
                (x1, y1, x2, y2),
                "",
                None,
                debug_prefix,
                processed_img,
            )
            return None

        seconds = self._parse_time_seconds(text)
        normalized = self._normalize_time_text(text)
        if seconds is not None:
            hh = seconds // 3600
            mm = (seconds % 3600) // 60
            ss = seconds % 60
            print(
                f"   [OCR-TIME] Checkbox ({cx},{cy}) => {hh:02d}:{mm:02d}:{ss:02d} ({seconds}s) "
                f"| raw='{text}' norm='{normalized}'"
            )
            self._save_travel_time_debug(
                screen_img,
                checkbox_center,
                (x1, y1, x2, y2),
                f"raw={text} | norm={normalized}",
                seconds,
                debug_prefix,
                processed_img,
            )
            return seconds

        self._save_travel_time_debug(
            screen_img,
            checkbox_center,
            (x1, y1, x2, y2),
            f"raw={text} | norm={normalized}",
            None,
            debug_prefix,
            processed_img,
        )
        return None

    def _save_travel_time_debug(self, screen_img, checkbox_center, roi, ocr_text, parsed_seconds, debug_prefix, processed_img):
        """Lưu ảnh debug OCR thời gian: 2 nhóm ảnh (overlay + processed)."""
        if not self.debug_enabled:
            return

        debug_dir = self.debug_dir
        overlay_dir = os.path.join(debug_dir, "time_overlay")
        processed_dir = os.path.join(debug_dir, "time_processed")
        os.makedirs(overlay_dir, exist_ok=True)
        os.makedirs(processed_dir, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        cx, cy = checkbox_center
        x1, y1, x2, y2 = roi

        full_debug = screen_img.copy()
        cv2.circle(full_debug, (int(cx), int(cy)), 8, (255, 0, 0), -1)
        cv2.putText(full_debug, "checkbox", (int(cx) + 10, int(cy) - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
        cv2.rectangle(full_debug, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)
        cv2.putText(full_debug, "OCR_TIME_ROI", (int(x1), max(20, int(y1) - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        parsed_text = f"{parsed_seconds}s" if parsed_seconds is not None else "PARSE_FAIL"
        cv2.putText(full_debug, f"OCR Text: {ocr_text if ocr_text else '(empty)'}", (10, self.screen_h - 45),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(full_debug, f"Parsed: {parsed_text}", (10, self.screen_h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        full_path = os.path.join(overlay_dir, f"debug_travel_time_{debug_prefix}_{ts}_{int(cx)}_{int(cy)}.png")
        cv2.imwrite(full_path, full_debug)

        if processed_img is not None and processed_img.size > 0:
            processed_out = processed_img.copy()
            cv2.putText(processed_out, f"OCR: {ocr_text if ocr_text else '(empty)'}", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(processed_out, f"Parsed: {parsed_text}", (10, 55),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            processed_path = os.path.join(processed_dir, f"debug_travel_time_processed_{debug_prefix}_{ts}_{int(cx)}_{int(cy)}.png")
            cv2.imwrite(processed_path, processed_out)

    def _get_center_roi(self, width_ratio=0.5, height_ratio=0.5):
        """ROI trung tâm màn hình để lọc checkbox của popup cảnh báo, tránh quét nhầm vùng UI khác."""
        rw = int(self.screen_w * width_ratio)
        rh = int(self.screen_h * height_ratio)
        x1 = max(0, (self.screen_w - rw) // 2)
        y1 = max(0, (self.screen_h - rh) // 2)
        x2 = min(self.screen_w, x1 + rw)
        y2 = min(self.screen_h, y1 + rh)
        return x1, y1, x2, y2

    def _save_warning_popup_debug(self, screen_img, roi, checkbox_pos, btn_tiep_tuc_pos, note, debug_override=None):
        if not self._should_debug(debug_override):
            return

        out_dir = os.path.join(self.debug_dir, "warning_popup")
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        x1, y1, x2, y2 = roi
        debug_img = screen_img.copy()
        cv2.rectangle(debug_img, (x1, y1), (x2, y2), (0, 165, 255), 2)
        cv2.putText(debug_img, "CENTER ROI", (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 165, 255), 2)

        if btn_tiep_tuc_pos:
            cv2.circle(debug_img, btn_tiep_tuc_pos, 8, (0, 255, 0), -1)
            cv2.putText(debug_img, "btn_tiep_tuc", (btn_tiep_tuc_pos[0] + 10, btn_tiep_tuc_pos[1] - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        if checkbox_pos:
            cv2.circle(debug_img, checkbox_pos, 8, (255, 0, 255), -1)
            cv2.putText(debug_img, "checkbox_khong_nhac", (checkbox_pos[0] + 10, checkbox_pos[1] - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 1)

        cv2.putText(debug_img, note, (10, self.screen_h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

        out_path = os.path.join(out_dir, f"debug_warning_popup_{ts}.png")
        cv2.imwrite(out_path, debug_img)

    def _find_warning_checkbox_in_center_roi(self, screen_img, roi):
        """Tìm checkbox chưa tick trong ROI trung tâm popup cảnh báo, trả về điểm gần tâm ROI nhất."""
        x1, y1, x2, y2 = roi
        if x2 <= x1 or y2 <= y1:
            return None

        crop = screen_img[y1:y2, x1:x2]
        hits = self.vision.find_all_templates(crop, self._get_path("checkbox_unchecked.png"))
        if not hits:
            return None

        roi_cx = (x2 - x1) // 2
        roi_cy = (y2 - y1) // 2
        best = min(hits, key=lambda p: (p[0] - roi_cx) ** 2 + (p[1] - roi_cy) ** 2)
        return x1 + int(best[0]), y1 + int(best[1])

    def _handle_difficulty_warning_after_dispatch_ok(self, debug=None, max_checks=4):
        """
        Xử lý popup cảnh báo độ khó lần đầu (nếu có) sau khi bấm OK xuất chiến.
        Trả về:
            "NOT_FOUND": không có popup (luồng bình thường)
            "HANDLED": đã tick "Không nhắc lại" + bấm "Tiếp tục" thành công
            "FAILED": phát hiện popup nhưng xử lý không xong
        """
        roi = self._get_center_roi(width_ratio=0.2, height_ratio=0.3)
        btn_tiep_tuc_tpl = self._get_path("btn_tiep_tuc.png")
        popup_seen = False

        for attempt in range(max_checks):
            # Popup có thể xuất hiện trễ sau animation UI.
            time.sleep(2)
            screen = self.device.take_screenshot()

            btn_tiep_tuc = self.vision.find_template(screen, btn_tiep_tuc_tpl)

            if not btn_tiep_tuc:
                # Debug tạm: lưu ảnh mỗi lần quét để kiểm tra ROI có khoanh đúng vùng popup không.
                self._save_warning_popup_debug(
                    screen,
                    roi,
                    None,
                    None,
                    f"warning_popup_attempt_{attempt + 1}_btn_tiep_tuc_not_found",
                    debug_override=debug,
                )
                continue

            popup_seen = True

            checkbox_pos = self._find_warning_checkbox_in_center_roi(screen, roi)
            if checkbox_pos:
                self.device.tap(checkbox_pos[0], checkbox_pos[1])
                time.sleep(0.25)
                print(f"   [COMBAT] Đã tick 'Không nhắc lại' tại ({checkbox_pos[0]}, {checkbox_pos[1]}).")
            else:
                print("   [COMBAT-WARN] Có popup cảnh báo nhưng chưa tìm thấy checkbox trong ROI trung tâm.")

            self.device.tap(btn_tiep_tuc[0], btn_tiep_tuc[1])
            print("   [COMBAT] Đã bấm 'Tiếp tục' để đóng cảnh báo độ khó lần đầu.")
            time.sleep(1.0)
            after = self.device.take_screenshot()
            still_visible = self.vision.find_template(after, btn_tiep_tuc_tpl)
            self._save_warning_popup_debug(
                after,
                roi,
                checkbox_pos,
                still_visible,
                "warning_popup_handled" if not still_visible else "warning_popup_still_visible",
                debug_override=debug,
            )
            if still_visible:
                print("   [COMBAT-WARN] Popup cảnh báo vẫn còn sau khi bấm 'Tiếp tục'.")
                return "FAILED"
            return "HANDLED"

        return "FAILED" if popup_seen else "NOT_FOUND"

    def _save_retreat_entry_debug(self, screen_img, btn_hanh_quan_pos, checkbox_pos, btn_ok_pos, note, debug_override=None):
        if not self._should_debug(debug_override):
            return

        out_dir = os.path.join(self.debug_dir, "retreat_entry")
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        debug_img = screen_img.copy()

        self._draw_detection_box(debug_img, btn_hanh_quan_pos, "btn_hanh_quan_map.png", "btn_hanh_quan", (0, 255, 255))
        self._draw_detection_box(debug_img, checkbox_pos, "checkbox_unchecked.png", "checkbox", (0, 255, 0))
        self._draw_detection_box(debug_img, btn_ok_pos, "btn_ok_xuat_chien.png", "btn_ok", (255, 0, 0))

        cv2.putText(debug_img, note, (10, self.screen_h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

        out_path = os.path.join(out_dir, f"debug_retreat_entry_{ts}.png")
        cv2.imwrite(out_path, debug_img)

    def _open_retreat_troops_panel(self, btn_hanh_quan_pos, debug=None, max_attempts=3):
        """Tap nút Hành Quân với verify hậu-tap để tránh false-positive hoặc tap hụt."""
        current_btn = btn_hanh_quan_pos

        for attempt in range(1, max_attempts + 1):
            if not current_btn:
                break

            print(f"   [RETREAT] Mở panel rút quân - thử lần {attempt}/{max_attempts} tại {current_btn}...")
            self.device.tap(current_btn[0], current_btn[1])
            time.sleep(2)

            post_tap_screen = self.device.take_screenshot()
            checkbox_pos = self.vision.find_template(post_tap_screen, self._get_path("checkbox_unchecked.png"))
            btn_ok_pos = self.vision.find_template(post_tap_screen, self._get_path("btn_ok_xuat_chien.png"))
            btn_hanh_quan2 = self.vision.find_template(post_tap_screen, self._get_path("btn_hanh_quan_map.png"))

            if not btn_hanh_quan2:
                self._save_retreat_entry_debug(
                    post_tap_screen,
                    current_btn,
                    checkbox_pos,
                    btn_ok_pos,
                    f"RETREAT ENTRY SUCCESS attempt={attempt}",
                    debug_override=debug,
                )
                return True

            self._save_retreat_entry_debug(
                post_tap_screen,
                btn_hanh_quan2,
                checkbox_pos,
                btn_ok_pos,
                f"RETREAT ENTRY RETRY attempt={attempt}",
                debug_override=debug,
            )

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

    def analyze_tile_state(self, x, y, debug=None):
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
        if self._should_debug(debug):
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

    def analyze_difficulty(self, screen_img, btn_chiem_pos, debug=None):
        """
        OCR vùng popup để đọc độ khó sử dụng EasyOCR.
        debug: Nếu True, sẽ lưu ảnh debug để kiểm tra vùng OCR.
        """
        # Crop vùng chứa text độ khó (Bạn cần tinh chỉnh tọa độ này chính xác)
        # Giả sử popup hiện ngay trên nút chiếm
        # Tọa độ ước lượng:
        x1, y1 = btn_chiem_pos[0] - 220, btn_chiem_pos[1] - 57
        x2, y2 = x1 + 90, y1 + 30

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
            if self.ocr is None:
                full_text = ""
            else:
                # EasyOCR trả về list các tuple: (bbox, text, confidence)
                results = self.ocr.readtext(crop_rgb)
                # Ghép tất cả text lại
                full_text = " ".join([item[1] for item in results]) if results else ""
        except Exception as e:
            print(f"   [OCR-ERR] Lỗi OCR: {e}")
            full_text = ""

        parsed = self.map.parse_difficulty(full_text)
        normalized_text = parsed["normalized"]
        is_blacklisted = parsed["valid"] and self._is_blacklisted_difficulty(parsed["tier_key"], parsed["level"])

        if parsed["valid"]:
            print(f"   [OCR-DIG] Đọc được: {full_text} | Chuẩn hóa: {parsed['label']}")
        else:
            print(f"   [OCR-DIG] Đọc được: {full_text} | Không parse được độ khó")

        # [DEBUG] Vẽ debug cho OCR
        if self._should_debug(debug):
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
            cv2.putText(debug_img, "- Blacklist: config/combat_difficulty_blacklist.json", (10, legend_y + 75),
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

    def dispatch_troops(self, btn_chiem_pos, tier_key="", debug=None):
        """Quy trình xuất quân. Tick hợp lệ khi OCR được thời gian hành quân của dòng quân đó."""
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
            return {"status": "FAILED", "max_travel_time": 0, "selected_count": 0}

        # Click tối đa 5 đạo (có swipe để cuộn danh sách nếu cần)
        count = 0
        max_troops = 5
        max_swipe_rounds = 3  # Giới hạn số lần swipe để tránh loop vô hạn
        selected_travel_times = []

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
            if self._should_debug(debug):
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

                # Theo rule mới: chỉ tính tick thành công khi OCR được thời gian hành quân.
                travel_seconds = self._extract_travel_time_seconds(current_screen, pt, debug_prefix="dispatch")
                if travel_seconds is None:
                    print(f"   [ACT] Bỏ qua checkbox ({pt[0]},{pt[1]}) vì không OCR được TG hành quân.")
                    continue

                self.device.tap(pt[0], pt[1])
                time.sleep(0.2)
                count += 1
                selected_travel_times.append(travel_seconds)

            # Nếu chưa đủ 5 quân, swipe để cuộn danh sách xuống
            if count < max_troops:
                print(f"   [ACT] Đã tick {count}/{max_troops}. Swipe để tìm thêm quân...")
                # Swipe từ dưới lên trên (kéo danh sách xuống) trong vùng cửa sổ chọn quân
                # Giả định vùng checkbox ở giữa màn hình
                swipe_x = self.screen_w // 2
                swipe_start_y = self.screen_h // 2 + 115
                swipe_end_y = self.screen_h // 2 - 115
                self.device.precise_drag(swipe_x, swipe_start_y, swipe_x, swipe_end_y, duration=2000)
                time.sleep(1.0)

        print(f"   [ACT] Đã tick tổng cộng {count} checkbox.")
        if not selected_travel_times:
            print("   [ERR] Không có checkbox hợp lệ (OCR thời gian hành quân thất bại toàn bộ).")
            self.device.tap(2, 2)
            return {"status": "FAILED", "max_travel_time": 0, "selected_count": 0}

        max_travel_time = max(selected_travel_times)
        print(f"   [ACT] TG hành quân lớn nhất của đội đã tick: {max_travel_time}s")
        time.sleep(2)

        # Bấm OK Xuất Chiến (chụp màn hình mới sau khi tick)
        screen_after_tick = self.device.take_screenshot()
        btn_ok = self.vision.find_template(screen_after_tick, self._get_path("btn_ok_xuat_chien.png"))
        if btn_ok:
            self.device.tap(btn_ok[0], btn_ok[1])

            if self._should_handle_first_dispatch_warning(tier_key):
                warning_status = self._handle_difficulty_warning_after_dispatch_ok(debug=debug)
                if warning_status == "FAILED":
                    print("   [ERR] Không xử lý được popup cảnh báo độ khó sau khi bấm OK xuất chiến.")
                    return {"status": "FAILED", "max_travel_time": max_travel_time, "selected_count": count}
                if warning_status == "HANDLED":
                    print("   [COMBAT] Popup cảnh báo độ khó đã được xử lý, tiếp tục kiểm tra Captcha.")
                elif warning_status == "NOT_FOUND":
                    print("   [COMBAT] Không thấy popup cảnh báo; tiếp tục luồng xuất quân bình thường.")
                self._mark_first_dispatch_done(tier_key)
            else:
                if tier_key:
                    print(f"   [COMBAT] Bỏ qua check popup cảnh báo cho dải '{tier_key}' (đã xử lý trước đó).")
                else:
                    print("   [COMBAT] Không xác định được tier_key, vẫn xử lý như luồng thường.")

            # === GỌI HÀM KIỂM TRA CAPTCHA SAU KHI BẤM OK ===
            status = self.safe_wait_and_check(wait_time=1.5)

            if status == "INTERRUPTED":
                print("   [ACT] Bị ngắt bởi Captcha. Yêu cầu thử lại lệnh xuất chiến.")
                return {"status": "INTERRUPTED", "max_travel_time": max_travel_time, "selected_count": count}
            elif status == "FATAL":
                return {"status": "FATAL", "max_travel_time": max_travel_time, "selected_count": count}

            print("   [ACT] Đã xuất quân thành công!")
            return {"status": "SUCCESS", "max_travel_time": max_travel_time, "selected_count": count}

        print("   [ERR] Không tìm thấy nút OK sau khi tick quân! Có thể bị click trượt hoặc popup chưa hiện đủ. "
              "Bỏ qua điểm này.")

        return {"status": "FAILED", "max_travel_time": max_travel_time, "selected_count": count}

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
        city_x, city_y = getattr(self.map, "main_city", (300, 300))

        def distance_to_city(tx, ty):
            # Dùng Manhattan distance để ưu tiên ô gần thành trên lưới tọa độ map.
            return abs(int(tx) - int(city_x)) + abs(int(ty) - int(city_y))

        for target_x, target_y in targets:
            tile = self.map.get_tile_info(target_x, target_y)
            state = tile.get("state", "")

            # Tile đã có trong map và còn là RESOURCE => dùng cache, không OCR lại.
            if state == "RESOURCE":
                valid = bool(tile.get("difficulty_valid", False))
                tier_key = tile.get("difficulty_tier_key", "") if valid else ""
                level = int(tile.get("difficulty_level", 999)) if valid else 999
                rank = int(tile.get("difficulty_rank", 999999)) if valid else 999999
                dist = int(tile.get("distance_to_city", distance_to_city(target_x, target_y)))
                label = tile.get("difficulty_label", "") if valid else ""

                # Fallback cho dữ liệu cũ chưa migrate cache.
                if not valid and tile.get("difficulty", ""):
                    parsed = self.map.parse_difficulty(tile.get("difficulty", ""))
                    valid = parsed["valid"]
                    tier_key = parsed["tier_key"] if valid else ""
                    level = parsed["level"] if valid else 999
                    rank = parsed["rank"] if valid else 999999
                    label = parsed["label"] if valid else ""

                if valid and self._is_blacklisted_difficulty(tier_key, level):
                    continue
                diff_label = label if valid else tile.get("difficulty", "") or "UNKNOWN"
                candidates.append(
                    {
                        "x": target_x,
                        "y": target_y,
                        "rank": rank,
                        "distance_to_city": dist,
                        "tier_key": tier_key if valid else "",
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
                valid = bool(tile.get("difficulty_valid", False))
                tier_key = tile.get("difficulty_tier_key", "") if valid else ""
                level = int(tile.get("difficulty_level", 999)) if valid else 999
                rank = int(tile.get("difficulty_rank", 999999)) if valid else 999999
                dist = int(tile.get("distance_to_city", distance_to_city(target_x, target_y)))
                label = tile.get("difficulty_label", "") if valid else ""

                if not valid and tile.get("difficulty", ""):
                    parsed = self.map.parse_difficulty(tile.get("difficulty", ""))
                    valid = parsed["valid"]
                    tier_key = parsed["tier_key"] if valid else ""
                    level = parsed["level"] if valid else 999
                    rank = parsed["rank"] if valid else 999999
                    label = parsed["label"] if valid else ""

                if valid and self._is_blacklisted_difficulty(tier_key, level):
                    self._close_tile_popup()
                    continue
                diff_label = label if valid else tile.get("difficulty", "") or "UNKNOWN"
                candidates.append(
                    {
                        "x": target_x,
                        "y": target_y,
                        "rank": rank,
                        "distance_to_city": dist,
                        "tier_key": tier_key if valid else "",
                        "label": diff_label,
                    }
                )
                # analyze_tile_state trả về sớm khi attackable nên popup vẫn còn mở.
                self._close_tile_popup()

        print(f"   [COMBAT] Reuse map cache: {cache_hits} ô | OCR mới: {scanned} ô")

        # Ưu tiên theo độ khó trước, nếu cùng độ khó thì chọn ô gần thành chính hơn.
        candidates.sort(key=lambda c: (c["rank"], c.get("distance_to_city", 999999), c["x"], c["y"]))
        return candidates

    def prepare_hard_dig_targets(self, start_tile, targets):
        """
        Chuẩn hóa và sắp xếp target Hard-Dig theo chiến lược lân cận gần nhất:
        bắt đầu từ ô khởi đầu, sau đó luôn chọn ô gần ô vừa chiếm xong nhất.
        """
        try:
            sx, sy = int(start_tile[0]), int(start_tile[1])
        except Exception:
            return {"status": "INVALID", "ordered_targets": [], "reason": "start_tile_invalid"}

        dedup = set()
        normalized = []
        for item in targets or []:
            try:
                tx, ty = int(item[0]), int(item[1])
            except Exception:
                continue
            if tx < 0 or tx > 600 or ty < 0 or ty > 600:
                continue
            key = (tx, ty)
            if key in dedup:
                continue
            dedup.add(key)
            normalized.append(key)

        start_key = (sx, sy)
        if 0 <= sx <= 600 and 0 <= sy <= 600 and start_key not in dedup:
            # Đảm bảo đúng yêu cầu: luôn bắt đầu chiếm từ ô khởi đầu.
            dedup.add(start_key)
            normalized.append(start_key)

        if not normalized:
            return {"status": "INVALID", "ordered_targets": [], "reason": "targets_empty"}

        remaining = set(normalized)
        if start_key in remaining:
            current = start_key
        else:
            # Fallback: nếu start không hợp lệ/ngoài map thì lấy điểm gần start nhất để khởi hành.
            current = min(remaining, key=lambda p: (abs(p[0] - sx) + abs(p[1] - sy), p[0], p[1]))

        ordered_points = [current]
        remaining.remove(current)

        while remaining:
            nxt = min(
                remaining,
                key=lambda p: (abs(p[0] - current[0]) + abs(p[1] - current[1]), p[0], p[1]),
            )
            ordered_points.append(nxt)
            remaining.remove(nxt)
            current = nxt

        ordered = [{"x": int(x), "y": int(y)} for x, y in ordered_points]
        return {
            "status": "READY",
            "start_tile": [sx, sy],
            "ordered_targets": ordered,
        }

    def dispatch_hard_dig_target(self, target, debug=None):
        """
        Hard-Dig: đánh thẳng vào target do người dùng chọn.
        Bỏ qua scan_and_dig/OCR độ khó, chỉ cần thấy nút Chiếm là xuất quân.
        """
        try:
            target_x, target_y = int(target["x"]), int(target["y"])
        except Exception:
            return {"status": "FAILED", "reason": "invalid_target"}

        print(f"   [HARD-DIG] Đang xử lý target ({target_x}, {target_y})...")
        self.jump_to_coordinate(target_x, target_y)

        cx, cy = self.screen_w // 2, self.screen_h // 2
        self.device.tap(cx, cy)
        time.sleep(1.5)
        screen = self.device.take_screenshot()
        btn_chiem_pos = self.vision.find_template(screen, self._get_path("btn_chiem.png"))

        if self._should_debug(debug):
            debug_img = screen.copy()
            cv2.circle(debug_img, (cx, cy), 8, (255, 255, 255), -1)
            cv2.putText(debug_img, "HARD-DIG TAP", (cx + 12, cy - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            self._draw_detection_box(debug_img, btn_chiem_pos, "btn_chiem.png", "btn_chiem", (0, 255, 0))
            out_path = os.path.join(os.getcwd(), "debug_img", "debug_hard_dig_target.png")
            cv2.imwrite(out_path, debug_img)

        if not btn_chiem_pos:
            print("   [HARD-DIG] Không thấy nút Chiếm tại target. Bỏ qua target này.")
            self.device.tap(cx, cy)
            return {"status": "NO_TARGET", "target": (target_x, target_y)}

        # Hard-Dig vẫn OCR độ khó để dự đoán battle duration chính xác hơn.
        # Chỉ dùng cho timing/cảnh báo lần đầu theo tier, không dùng để blacklist/skip target.
        diff_info = self.analyze_difficulty(screen, btn_chiem_pos, debug=False)
        hard_tier_key = diff_info.get("tier_key", "") if isinstance(diff_info, dict) else ""
        hard_label = diff_info.get("label", "") if isinstance(diff_info, dict) else ""
        if hard_label:
            print(f"   [HARD-DIG] Độ khó OCR: {hard_label} (tier_key={hard_tier_key or 'unknown'})")
        else:
            print("   [HARD-DIG] Không parse được độ khó, fallback battle duration mặc định.")

        dispatch_status = self.dispatch_troops(btn_chiem_pos, tier_key=hard_tier_key, debug=debug)
        dispatch_result = dispatch_status if isinstance(dispatch_status, dict) else {
            "status": "SUCCESS" if dispatch_status is True else str(dispatch_status),
            "max_travel_time": 0,
            "selected_count": 0,
        }
        dispatch_key = dispatch_result.get("status", "FAILED")

        if dispatch_key == "SUCCESS":
            self.map.update_tile(target_x, target_y, "OWNED")
            battle_seconds = self._get_battle_duration_seconds(hard_tier_key)
            predicted_wait = int(dispatch_result.get("max_travel_time", 0)) + battle_seconds
            print(
                f"   [HARD-DIG] Dự đoán chờ trận: {dispatch_result.get('max_travel_time', 0)}s hành quân + "
                f"{battle_seconds}s chiến đấu = {predicted_wait}s"
            )
            return {
                "status": "SUCCESS",
                "target": (target_x, target_y),
                "difficulty": hard_label,
                "tier_key": hard_tier_key,
                "max_travel_time": int(dispatch_result.get("max_travel_time", 0)),
                "battle_duration": battle_seconds,
                "predicted_wait": predicted_wait,
            }

        if dispatch_key in {"INTERRUPTED", "FATAL"}:
            return {
                "status": dispatch_key,
                "target": (target_x, target_y),
                "max_travel_time": int(dispatch_result.get("max_travel_time", 0)),
            }

        self.device.tap(cx, cy)
        return {
            "status": "FAILED",
            "target": (target_x, target_y),
            "max_travel_time": int(dispatch_result.get("max_travel_time", 0)),
        }

    def scan_and_dig(self):
        """Luồng Dig 2 pha: trinh sát -> chọn target -> xuất quân và trả về thời gian chờ dự đoán."""

        # 1. Lấy danh sách ô mục tiêu từ thuật toán vết dầu loang
        targets = self.map.get_expansion_targets()

        if not targets:
            print("   [COMBAT] Lãnh thổ đang bị bao vây hoặc chưa có dữ liệu. Không tìm thấy ô để mở rộng.")
            return {"status": "NO_TARGET"}

        print(f"   [COMBAT] Tìm thấy {len(targets)} ô liền kề có thể mở rộng.")
        preview = []
        for tx, ty in targets[:8]:
            tile = self.map.get_tile_info(tx, ty)
            if tile.get("difficulty_valid", False):
                diff_label = tile.get("difficulty_label", "") or tile.get("difficulty", "?") or "UNKNOWN"
            else:
                parsed = self.map.parse_difficulty(tile.get("difficulty", ""))
                diff_label = parsed["label"] if parsed["valid"] else tile.get("difficulty", "?") or "UNKNOWN"
            preview.append(f"({tx},{ty})={diff_label}")
        if preview:
            print("   [COMBAT] Ưu tiên target: " + " | ".join(preview))

        # 2. Pha trinh sát: OCR nhiều target để biết độ khó thực trước khi chọn.
        scan_budget = min(len(targets), int(self.combat_timing.get("max_scout_targets_per_cycle", 10)))
        candidates = self._collect_attackable_targets(targets, max_scan=scan_budget)

        if not candidates:
            print("   [COMBAT] Không có target hợp lệ sau khi trinh sát.")
            return {"status": "NO_TARGET"}

        top_preview = [f"({c['x']},{c['y']})={c['label']},d={c.get('distance_to_city', '?')}" for c in candidates[:8]]
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
                    dispatch_status = self.dispatch_troops(btn_chiem_pos, tier_key=candidate.get("tier_key", ""))
                    dispatch_result = dispatch_status if isinstance(dispatch_status, dict) else {
                        "status": "SUCCESS" if dispatch_status is True else str(dispatch_status),
                        "max_travel_time": 0,
                        "selected_count": 0,
                    }
                    dispatch_key = dispatch_result.get("status", "FAILED")

                    if dispatch_key == "SUCCESS":
                        # Đã xuất quân, cập nhật ô này thành OWNED trong map ảo
                        self.map.update_tile(target_x, target_y, "OWNED")
                        battle_seconds = self._get_battle_duration_seconds(candidate.get("tier_key", ""))
                        predicted_wait = int(dispatch_result.get("max_travel_time", 0)) + battle_seconds
                        print(
                            f"   [COMBAT] Dự đoán chờ trận: {dispatch_result.get('max_travel_time', 0)}s hành quân + "
                            f"{battle_seconds}s chiến đấu = {predicted_wait}s"
                        )
                        return {
                            "status": "SUCCESS",
                            "target": (target_x, target_y),
                            "difficulty": candidate.get("label", ""),
                            "tier_key": candidate.get("tier_key", ""),
                            "max_travel_time": int(dispatch_result.get("max_travel_time", 0)),
                            "battle_duration": battle_seconds,
                            "predicted_wait": predicted_wait,
                        }
                    elif dispatch_key == "INTERRUPTED":
                        print("   [COMBAT] Bị ngắt do Captcha. Thử lại ô đất này...")
                        continue
                    elif dispatch_key == "FATAL":
                        return {"status": "FATAL"}
                    else:
                        # Lỗi kẹt UI, tap đóng popup
                        self.device.tap(self.screen_w // 2, self.screen_h // 2)
                        break
                else:
                    # Không đánh được (là núi, sông, người khác...) -> Đã phân tích xong
                    break

        return {"status": "NO_TARGET"}

    def retreat_troops_logic(self, debug=None):
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
        if self._should_debug(debug):
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

        if btn_hanh_quan and self._open_retreat_troops_panel(btn_hanh_quan, debug=debug, max_attempts=3):
            time.sleep(1)

            # 4. Chọn tất cả quân (có swipe để cuộn danh sách nếu cần)
            count = 0
            max_troops = 5
            max_swipe_rounds = 3  # Giới hạn số lần swipe để tránh loop vô hạn
            selected_travel_times = []

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
                if self._should_debug(debug):
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

                    # Rule mới: chỉ tick thành công khi OCR được TG hành quân của dòng quân đó.
                    travel_seconds = self._extract_travel_time_seconds(current_screen, pt, debug_prefix="retreat")
                    if travel_seconds is None:
                        print(f"   [ACT] Bỏ qua checkbox rút quân ({pt[0]},{pt[1]}) vì OCR TG hành quân thất bại.")
                        continue

                    self.device.tap(pt[0], pt[1])
                    time.sleep(0.2)
                    count += 1
                    selected_travel_times.append(travel_seconds)

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
            if not selected_travel_times:
                print("   [ERR] Không có checkbox rút quân hợp lệ (OCR thời gian thất bại toàn bộ).")
                self.device.tap(2, 2)
                self.device.tap(cx, cy)
                return {"status": "FAILED", "max_travel_time": 0, "selected_count": 0}

            max_travel_time = max(selected_travel_times)
            print(f"   [RETREAT] TG hành quân lớn nhất khi rút quân: {max_travel_time}s")
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
                    return {"status": "INTERRUPTED", "max_travel_time": max_travel_time, "selected_count": count}
                elif status == "FATAL":
                    return {"status": "FATAL", "max_travel_time": max_travel_time, "selected_count": count}

                time.sleep(3)

                # Chụp màn hình mới để kiểm tra btn_ok2
                screen_after_ok = self.device.take_screenshot()
                btn_ok2 = self.vision.find_template(screen_after_ok, self._get_path("btn_ok_xuat_chien.png"))

                # [DEBUG] Vẽ debug cho btn_ok2
                if self._should_debug(debug):
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
                    return {"status": "FAILED", "max_travel_time": max_travel_time, "selected_count": count}
                else:
                    print("   [DONE] Đã ra lệnh rút quân thành công.")
                    return {"status": "SUCCESS", "max_travel_time": max_travel_time, "selected_count": count}

        print("   [FAIL] Lỗi khi rút quân (Không thấy nút hành quân).")
        # Tap ra ngoài để đóng popup
        self.device.tap(2, 2)
        return {"status": "FAILED", "max_travel_time": 0, "selected_count": 0}
