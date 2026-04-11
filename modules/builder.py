import time
import os
import sys
import cv2
import re
import unicodedata
from datetime import datetime
import easyocr
try:
    from paddleocr import PaddleOCR
except Exception:
    PaddleOCR = None
from config.build_order import resolve_build_sequence
from modules.scene import SceneManager


class BuilderManager:
    def __init__(self, device, vision, captcha_solver=None, debug_enabled=None, debug_dir="debug_img/builder"):
        self.device = device
        self.vision = vision
        self.captcha_solver = captcha_solver  # Nhận instance từ main.py
        self.assets_dir = self._resolve_assets_dir()
        env_debug = os.getenv("BUILDER_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
        self.debug_enabled = env_debug if debug_enabled is None else bool(debug_enabled)
        self.debug_dir = os.path.abspath(debug_dir)
        self._easyocr_unavailable_logged = False
        self.ocr = None
        if PaddleOCR is not None:
            try:
                self.ocr = PaddleOCR(use_angle_cls=True, lang='en', enable_mkldnn=False)
                print("   [BUILDER] PaddleOCR init thành công.")
            except Exception as exc:
                print(f"   [BUILDER-WARN] PaddleOCR init lỗi, fallback EasyOCR: {exc}")
        else:
            print("   [BUILDER-WARN] Không import được PaddleOCR, fallback EasyOCR.")
        # OCR tên công trình tiếng Việt dùng EasyOCR để ổn định hơn với dấu.
        self.name_ocr = self._init_easyocr_reader(['vi'], "builder-name")

    def _resolve_assets_dir(self):
        candidates = [
            os.path.abspath(os.path.join(os.getcwd(), "assets")),
            os.path.abspath(os.path.join(os.getcwd(), "_internal", "assets")),
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
                print(f"   [BUILDER] EasyOCR ({label}) init thành công với model bundled: {model_dir}")
                return reader
            except Exception as exc:
                print(f"   [BUILDER-WARN] EasyOCR ({label}) init từ model bundled lỗi: {exc}")

        if getattr(sys, "frozen", False):
            print(
                f"   [BUILDER-WARN] EasyOCR ({label}) không có model bundled trong bản .exe. "
                f"Bỏ qua EasyOCR để tránh tự tải model runtime."
            )
            return None

        try:
            reader = easyocr.Reader(languages, gpu=False, verbose=False)
            print(f"   [BUILDER] EasyOCR ({label}) init thành công (source mode).")
            return reader
        except Exception as exc:
            print(f"   [BUILDER-WARN] EasyOCR ({label}) init lỗi: {exc}")
            return None

    def _ocr_predict_texts(self, image_bgr):
        if image_bgr is None:
            return []

        if self.ocr is not None:
            try:
                output = self.ocr.predict(image_bgr)
                results = list(output)
                if results:
                    return results[0].get('rec_texts', []) or []
            except Exception as exc:
                print(f"   [BUILDER-WARN] PaddleOCR predict lỗi, fallback EasyOCR: {exc}")

        if self.name_ocr is None:
            if not self._easyocr_unavailable_logged:
                print("   [BUILDER-WARN] EasyOCR không khả dụng, bỏ qua fallback OCR.")
                self._easyocr_unavailable_logged = True
            return []

        try:
            rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            results = self.name_ocr.readtext(rgb)
            return [item[1] for item in results] if results else []
        except Exception as exc:
            print(f"   [BUILDER-ERR] EasyOCR predict lỗi: {exc}")
            return []

    def _get_path(self, filename):
        return os.path.join(self.assets_dir, filename)

    def _get_building_path(self, filename):
        # Giả sử bạn để ảnh nhà trong assets/buildings/
        return os.path.join(self.assets_dir, "buildings", filename)

    def _should_debug(self, debug_override):
        if debug_override is None:
            return self.debug_enabled
        return bool(debug_override)

    def _debug_subdir(self, subdir):
        path = os.path.join(self.debug_dir, subdir)
        os.makedirs(path, exist_ok=True)
        return path

    def _normalize_text(self, text):
        if not text:
            return ""
        text = str(text).strip().lower()
        text = unicodedata.normalize("NFD", text)
        text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
        text = text.replace("đ", "d")
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _is_building_name_match(self, target_name, ocr_text):
        target_norm = self._normalize_text(target_name)
        ocr_norm = self._normalize_text(ocr_text)

        if not target_norm or not ocr_norm:
            return False

        if target_norm in ocr_norm or ocr_norm in target_norm:
            return True

        target_tokens = [t for t in target_norm.split(" ") if len(t) >= 2]
        ocr_tokens = set([t for t in ocr_norm.split(" ") if len(t) >= 2])
        if not target_tokens:
            return False

        overlap = sum(1 for t in target_tokens if t in ocr_tokens)
        return (overlap / len(target_tokens)) >= 0.6

    def _ocr_building_name_region(self, screen_img, x1, y1, x2, y2):
        crop = screen_img[y1:y2, x1:x2]
        if crop.size == 0:
            return {"raw": "", "norm": "", "processed": None}

        enlarged = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        processed = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

        results = []
        if self.name_ocr is not None:
            try:
                rgb = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB)
                results = self.name_ocr.readtext(rgb)
            except Exception as exc:
                print(f"   [BUILD-OCR-ERR] EasyOCR lỗi: {exc}")

        rec_texts = [item[1] for item in results] if results else []
        raw_text = " ".join(rec_texts).strip()
        norm_text = self._normalize_text(raw_text)

        return {
            "raw": raw_text,
            "norm": norm_text,
            "processed": processed,
        }

    def _draw_build_list_debug(self, screen_img, rows, round_idx, target_name):
        if not self.debug_enabled:
            return

        overlay_dir = self._debug_subdir("build_list_overlay")
        processed_dir = self._debug_subdir("build_list_processed")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        img = screen_img.copy()
        target_norm = self._normalize_text(target_name)
        cv2.putText(img, f"BUILD LIST ROUND {round_idx} | TARGET: {target_name}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(img, f"TARGET_NORM: {target_norm}", (10, 58),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

        for idx, row in enumerate(rows):
            bx, by = row["btn"]
            x1, y1, x2, y2 = row["roi"]
            color = (0, 255, 0) if row["matched"] else (0, 165, 255)

            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            cv2.circle(img, (bx, by), 5, color, -1)
            cv2.putText(img, f"#{idx + 1} RAW:{row['raw_text']}", (x1, max(20, y1 - 24)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1)
            cv2.putText(img, f"NORM:{row['norm_text']}", (x1, max(20, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

            processed = row.get("processed")
            if processed is not None and processed.size > 0:
                processed_vis = processed.copy()
                cv2.putText(processed_vis, f"RAW: {row['raw_text']}", (8, 22),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
                cv2.putText(processed_vis, f"NORM: {row['norm_text']}", (8, 48),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
                cv2.putText(processed_vis, f"MATCH: {row['matched']}", (8, 74),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
                processed_path = os.path.join(
                    processed_dir,
                    f"debug_build_list_processed_round{round_idx}_row{idx + 1}_{stamp}.png",
                )
                cv2.imwrite(processed_path, processed_vis)

        debug_path = os.path.join(overlay_dir, f"debug_build_list_round{round_idx}_{stamp}.png")
        cv2.imwrite(debug_path, img)
        print(f"   [DEBUG] Đã lưu build-list debug: {debug_path}")

    def _find_target_build_button(self, target_name, btn_xay_path, max_swipe_rounds=5):
        target_norm = self._normalize_text(target_name)
        print(f"   [BUILD-OCR] Target raw='{target_name}' | norm='{target_norm}'")

        for swipe_round in range(max_swipe_rounds):
            screen = self.device.take_screenshot()
            all_btn_xay = self.vision.find_all_templates(screen, btn_xay_path)

            if not all_btn_xay:
                print(f"   [BUILD] Vòng {swipe_round + 1}: Không thấy nút Xây nào.")
                return None, False

            rows = []
            matched_btn = None
            h, w, _ = screen.shape

            for idx, btn in enumerate(all_btn_xay):
                bx, by = btn
                # Vùng tên công trình nằm bên trái nút Xây theo từng dòng.
                x1 = max(0, bx - int(w * 0.2))
                x2 = max(x1 + 1, bx)
                y1 = max(0, by - int(h * 0.17))
                y2 = max(y1 + 1, by - int(h * 0.14))

                ocr_info = self._ocr_building_name_region(screen, x1, y1, x2, y2)
                raw_text = ocr_info["raw"]
                norm_text = ocr_info["norm"]
                matched = self._is_building_name_match(target_name, raw_text)

                print(
                    f"   [BUILD-OCR] Round {swipe_round + 1} Row {idx + 1}: "
                    f"raw='{raw_text}' | norm='{norm_text}' | matched={matched}"
                )

                rows.append({
                    "btn": (bx, by),
                    "roi": (x1, y1, x2, y2),
                    "raw_text": raw_text,
                    "norm_text": norm_text,
                    "processed": ocr_info.get("processed"),
                    "matched": matched,
                })

                if matched and matched_btn is None:
                    matched_btn = (bx, by)

            self._draw_build_list_debug(screen, rows, swipe_round + 1, target_name)

            if matched_btn:
                print(f"   [BUILD] Match công trình '{target_name}' tại nút {matched_btn} (vòng {swipe_round + 1}).")
                return matched_btn, True

            # Lăn danh sách để tìm tiếp.
            print(f"   [BUILD] Chưa thấy '{target_name}' ở vòng {swipe_round + 1}. Lăn danh sách...")
            swipe_x = w // 2
            swipe_start_y = h // 2 + 100
            swipe_end_y = h // 2 - 100
            self.device.precise_drag(swipe_x, swipe_start_y, swipe_x, swipe_end_y, duration=1800)
            time.sleep(1.0)

        return None, True

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
    def check_current_level(self, save_debug=None):
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
        if self._should_debug(save_debug):
            level_dir = self._debug_subdir("level_ocr")
            debug_img = screen.copy()
            # Vẽ hình chữ nhật màu xanh lá (BGR: 0, 255, 0), độ dày 2px
            cv2.rectangle(debug_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            # Thêm text hiển thị tọa độ
            cv2.putText(debug_img, f"Crop: ({x1},{y1}) - ({x2},{y2})",
                        (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            # Lưu ảnh debug
            debug_path = os.path.join(level_dir, "debug_crop_level.png")
            cv2.imwrite(debug_path, debug_img)
            print(f"   [DEBUG] Đã lưu ảnh debug: {debug_path}")

            # Lưu ảnh crop gốc
            crop_debug_path = os.path.join(level_dir, "debug_crop_only.png")
            cv2.imwrite(crop_debug_path, crop_img)
            print(f"   [DEBUG] Đã lưu ảnh crop gốc: {crop_debug_path}")

            # Lưu ảnh đã xử lý (ảnh mà OCR sẽ đọc)
            processed_debug_path = os.path.join(level_dir, "debug_crop_processed.png")
            cv2.imwrite(processed_debug_path, processed_img)
            print(f"   [DEBUG] Đã lưu ảnh đã xử lý: {processed_debug_path}")

        # OCR đọc chữ
        rec_texts = self._ocr_predict_texts(processed_img)
        rec_scores = []

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
    def check_upgrade_time(self, save_debug=None):
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
        y2 = int(h * 0.791) + 1

        return self._ocr_time_region(screen, x1, y1, x2, y2, "upgrade", save_debug)

    # --- HÀM: Đọc thời gian Xây mới ---
    def check_build_time(self, save_debug=None):
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

    def _ocr_time_region(self, screen, x1, y1, x2, y2, debug_name, save_debug=None):
        crop_img = screen[y1:y2, x1:x2]

        scale_factor = 3
        crop_enlarged = cv2.resize(crop_img, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(crop_enlarged, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        processed_img = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

        if self._should_debug(save_debug):
            time_dir = self._debug_subdir("time_ocr")
            debug_img = screen.copy()
            cv2.rectangle(debug_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(debug_img, f"Time Crop: ({x1},{y1}) - ({x2},{y2})",
                        (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            debug_path = os.path.join(time_dir, f"debug_crop_time_{debug_name}.png")
            cv2.imwrite(debug_path, debug_img)
            print(f"   [DEBUG] Đã lưu ảnh debug: {debug_path}")

        rec_texts = self._ocr_predict_texts(processed_img)

        if not rec_texts:
            return None

        all_text = " ".join(rec_texts)
        return self._parse_time_string(all_text)

    def _parse_time_string(self, text):
        raw_text = str(text or "").strip()
        compact = raw_text.replace(" ", "")
        if not compact:
            print("   [TIME] Không thể parse thời gian: OCR rỗng")
            return None

        # Sửa các ký tự OCR hay nhầm trong vùng thời gian.
        trans = str.maketrans({
            "O": "0", "o": "0",
            "I": "1", "l": "1", "|": "1",
            ",": ":", ".": ":", "-": ":", ";": ":", "_": ":",
        })
        normalized = compact.translate(trans)
        normalized = re.sub(r":+", ":", normalized).strip(":")

        def _log_and_return(total_seconds, detail):
            print(f"   [TIME] Parsed ({detail}): {total_seconds} giây | raw='{raw_text}' | norm='{normalized}'")
            return total_seconds

        # Ưu tiên format HH:MM:SS (hoặc MM:SS nếu OCR mất 1 cụm).
        m3 = re.search(r'(\d{1,2}):(\d{1,2}):(\d{1,2})', normalized)
        if m3:
            a, b, c = int(m3.group(1)), int(m3.group(2)), int(m3.group(3))
            if a <= 23 and b <= 59 and c <= 59:
                return _log_and_return(a * 3600 + b * 60 + c, f"h:m:s={a}:{b}:{c}")
            if a <= 59 and b <= 59 and c == 0:
                # OCR hay thêm cụm "0" ở cuối: ví dụ 09-09.0 -> hiểu là 09:09
                return _log_and_return(a * 60 + b, f"m:s (drop tail 0)={a}:{b}")

        m2 = re.search(r'(\d{1,2}):(\d{1,2})', normalized)
        if m2:
            mm, ss = int(m2.group(1)), int(m2.group(2))
            if mm <= 59 and ss <= 59:
                return _log_and_return(mm * 60 + ss, f"m:s={mm}:{ss}")

        # Fallback cuối: tách theo cụm số để cứu các trường hợp OCR bể định dạng.
        nums = [int(n) for n in re.findall(r'\d{1,2}', normalized)]
        if len(nums) >= 3:
            a, b, c = nums[0], nums[1], nums[2]
            if a <= 23 and b <= 59 and c <= 59:
                return _log_and_return(a * 3600 + b * 60 + c, f"fallback h:m:s={a}:{b}:{c}")
            if a <= 59 and b <= 59:
                return _log_and_return(a * 60 + b, f"fallback m:s={a}:{b}")
        elif len(nums) >= 2:
            mm, ss = nums[0], nums[1]
            if mm <= 59 and ss <= 59:
                return _log_and_return(mm * 60 + ss, f"fallback m:s={mm}:{ss}")

        print(f"   [TIME] Không thể parse thời gian từ: raw='{raw_text}' | norm='{normalized}'")
        return None

    def open_info_tab(self):
        screen = self.device.take_screenshot()
        h, w, _ = screen.shape
        y, x = int(h * 0.15), int(w * 0.43)
        self.device.tap(x, y)
        time.sleep(1)
        return True

    def _result(self, status, wait_time=None):
        return {"status": status, "wait_time": wait_time}

    # --- HÀM 2: Logic Xây Mới (Lv 1) ---
    def build_new_structure(self, building_name_display):
        """
        Xây mới công trình.
        Trả về dict:
            - SUCCESS: đã bấm xây thành công, wait_time là thời gian xây (nếu OCR được)
            - SKIPPED_ALREADY_DONE: công trình không còn trong danh sách build (xem như đã xây)
            - FAILED: lỗi thao tác/thiếu tài nguyên
            - FATAL: lỗi nghiêm trọng (captcha không giải được)
        """
        print(f"   [ACTION] Xây mới: {building_name_display}")
        max_retries_per_action = 2

        for attempt in range(max_retries_per_action):
            # 1. Bấm nút Búa (Menu Xây dựng)
            btn_bua = self.vision.find_template(self.device.take_screenshot(), self._get_path("btn_xay_dung_menu.png"))
            if not btn_bua:
                print("   [-] Không thấy nút Menu Xây dựng.")
                return self._result("FAILED")

            self.device.tap(btn_bua[0], btn_bua[1])
            time.sleep(2)  # Chờ menu trượt lên

            # 2. Đọc thời gian xây TRƯỚC KHI bấm nút Xây
            build_time = self.check_build_time()
            if build_time:
                print(f"   [INFO] Thời gian xây dự kiến: {build_time} giây")

            # 3. OCR tên công trình theo từng dòng và chọn đúng nút Xây tương ứng
            btn_xay_path = self._get_path("btn_xay_confirm.png")
            btn_xay, has_list = self._find_target_build_button(building_name_display, btn_xay_path, max_swipe_rounds=5)

            if btn_xay:
                print(f"   [+] Chọn đúng nút Xây của '{building_name_display}' tại ({btn_xay[0]}, {btn_xay[1]})")
                self.device.tap(btn_xay[0], btn_xay[1])

                # === GỌI HÀM KIỂM TRA CAPTCHA TẠI ĐÂY ===
                status = self.safe_wait_and_check(wait_time=2.0)

                if status == "INTERRUPTED":
                    print(f"   [BUILD] Hành động bị ngắt do Captcha. Đang thử lại... (Lần {attempt + 1})")
                    time.sleep(1.5)
                    continue  # Vòng lặp sẽ chạy lại việc tìm búa -> xây
                elif status == "FATAL":
                    return self._result("FATAL")

                # --- KIỂM TRA HẬU QUẢ (Post-Action Check) ---
                screen_after = self.device.take_screenshot()
                is_popup_still_open = self.vision.find_template(screen_after, btn_xay_path)

                if is_popup_still_open:
                    print("   [FAIL] Nút Xây vẫn còn. (Nguyên nhân: Thiếu tài nguyên).")
                    self.device.tap(1, 1)
                    time.sleep(1)
                    return self._result("FAILED")
                else:
                    print("   [SUCCESS] Xây thành công (Popup đã đóng).")
                    return self._result("SUCCESS", build_time)
            else:
                if has_list:
                    print(f"   [INFO] Không thấy '{building_name_display}' trong danh sách build. Xem như đã xây.")
                else:
                    print("   [-] Không thấy nút Xây nào trong danh sách. Có thể đã xây hết.")
                self.device.tap(1, 1)
                return self._result("SKIPPED_ALREADY_DONE")

        return self._result("FAILED")

    # --- HÀM 3: Logic Nâng Cấp (Lv > 1) ---
    def upgrade_existing_structure(self, img_name, target_lv, display_name):
        """
        Nâng cấp công trình đã có.
        Trả về dict:
            - SUCCESS: đã bấm nâng cấp thành công, wait_time là thời gian nâng cấp (nếu OCR được)
            - SKIPPED_ALREADY_DONE: level hiện tại đã đạt mục tiêu
            - FAILED: lỗi thao tác/không tìm thấy nút
            - FATAL: lỗi nghiêm trọng (captcha không giải được)
        """
        print(f"   [CHECK] Kiểm tra: {display_name} (Mục tiêu: Lv {target_lv})")

        # Tìm nhà trên map
        pos = self.vision.find_template(
            self.device.take_screenshot(),
            self._get_building_path(img_name + ".png"),
        )

        if not pos:
            print(f"   [-] Không tìm thấy {display_name} trên bản đồ. (Có thể chưa xây?)")
            return self._result("FAILED")

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
                    return self._result("SKIPPED_ALREADY_DONE")
            else:
                print("   [WARN] Không đọc được level. Giả định cần nâng cấp.")

            # 4. Đọc thời gian tăng cấp
            upgrade_time = self.check_upgrade_time()
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
                    return self._result("FATAL")

                # --- KIỂM TRA HẬU QUẢ ---
                screen_after = self.device.take_screenshot()
                is_popup_still_open = self.vision.find_template(screen_after, btn_up_path)

                if is_popup_still_open:
                    print("   [FAIL] Nút Tăng Cấp vẫn còn. (Nguyên nhân: Thiếu tài nguyên hoặc Đang bận xây).")
                    self.device.tap(1, 1)
                    time.sleep(1)
                    return self._result("FAILED")
                else:
                    print("   [SUCCESS] Nâng cấp thành công (Popup đã đóng).")
                    return self._result("SUCCESS", upgrade_time)
            else:
                print("   [INFO] Không thấy nút Tăng Cấp (Có thể đang trong quá trình xây dựng).")
                self.device.tap(1, 1)
                return self._result("FAILED")

        return self._result("FAILED")

    # --- MAIN LOOP ---
    def execute_sequence(self):
        print("\n=== BẮT ĐẦU CHUỖI XÂY DỰNG ===")

        build_sequence, start_index, _ = resolve_build_sequence()
        if start_index > 0:
            print(f"[BUILD-ORDER] Builder execute_sequence bat dau tu index {start_index}/{len(build_sequence)}")

        # Khởi tạo Scene Manager
        scene = SceneManager(self.device, self.vision)
        scene.go_to_city()

        for task in build_sequence[start_index:]:
            target = task["target_lv"]
            name = task["name"]
            display = task["type_name"]

            if target == 1:
                self.build_new_structure(display)
            else:
                self.upgrade_existing_structure(name, target, display)

            # Nghỉ một chút giữa các task
            time.sleep(1)
