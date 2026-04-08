import cv2
import numpy as np
import json
import os
import sys
from datetime import datetime
from typing import cast


class VisionManager:
    def __init__(self, profile_path="config/template_profiles.json", debug_enabled=None, debug_dir="debug_img/vision"):
        # Ngưỡng nhận diện mặc định (0.8 = chính xác 80%)
        # Nếu bot không tìm thấy, hãy giảm xuống 0.7 hoặc 0.6
        # Nếu bot bấm nhầm chỗ, hãy tăng lên 0.9
        self.threshold = 0.6
        # Scale mặc định để giảm lỗi do UI bị thay đổi kích thước nhẹ theo emulator/device.
        self.scales = (1.0, 0.95, 1.05, 0.9, 1.1)
        self.method_weights = {
            "color": 1.0,
            "gray": 1.0,
            "edge": 0.98,
        }
        self._template_cache = {}
        self.profile_path = self._resolve_profile_path(profile_path)
        self.template_profiles = self._load_profiles(self.profile_path)
        env_debug = os.getenv("VISION_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
        self.debug_enabled = env_debug if debug_enabled is None else bool(debug_enabled)
        self.debug_dir = os.path.abspath(debug_dir)

    def _resolve_profile_path(self, profile_path):
        candidates = [os.path.abspath(profile_path)]

        if getattr(sys, "frozen", False):
            exe_root = os.path.dirname(sys.executable)
            candidates.append(os.path.abspath(os.path.join(exe_root, profile_path)))
            candidates.append(os.path.abspath(os.path.join(exe_root, "_internal", profile_path)))
            meipass = getattr(sys, "_MEIPASS", "")
            if meipass:
                candidates.append(os.path.abspath(os.path.join(meipass, profile_path)))

        for p in candidates:
            if os.path.exists(p):
                return p

        # fallback để message log hiển thị đường dẫn dễ hiểu
        return candidates[0]

    def _load_profiles(self, profile_path):
        if not os.path.exists(profile_path):
            print(f"> Vision: Không thấy profile config tại '{profile_path}', dùng cấu hình mặc định.")
            return {}

        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                print(f"!!! Vision: Profile config không hợp lệ: {profile_path}")
                return {}
            return data
        except Exception as exc:
            print(f"!!! Vision: Không đọc được profile config '{profile_path}': {exc}")
            return {}

    def _template_keys(self, template_path):
        keys = []
        abs_path = os.path.abspath(template_path)
        base = os.path.basename(template_path)
        if base:
            keys.append(base)
        try:
            rel = os.path.relpath(abs_path, os.getcwd()).replace("\\", "/")
            keys.append(rel)
        except ValueError:
            pass
        keys.append(abs_path.replace("\\", "/"))
        return keys

    def _resolve_profile(self, template_path):
        templates = self.template_profiles.get("templates", {})
        if not isinstance(templates, dict):
            return {}

        for key in self._template_keys(template_path):
            profile = templates.get(key)
            if isinstance(profile, dict):
                return profile
        return {}

    def _resolve_threshold(self, explicit_threshold, profile, mode):
        if explicit_threshold is not None:
            return explicit_threshold

        mode_cfg = profile.get(mode, {}) if isinstance(profile, dict) else {}
        if isinstance(mode_cfg, dict) and "threshold" in mode_cfg:
            return float(mode_cfg["threshold"])

        if isinstance(profile, dict) and "threshold" in profile:
            return float(profile["threshold"])

        default_cfg = self.template_profiles.get("default", {})
        if isinstance(default_cfg, dict) and "threshold" in default_cfg:
            return float(default_cfg["threshold"])

        return self.threshold

    def _resolve_scales(self, profile):
        if isinstance(profile, dict) and isinstance(profile.get("scales"), list) and profile.get("scales"):
            return tuple(float(v) for v in profile["scales"])

        default_cfg = self.template_profiles.get("default", {})
        if isinstance(default_cfg, dict) and isinstance(default_cfg.get("scales"), list) and default_cfg.get("scales"):
            return tuple(float(v) for v in default_cfg["scales"])

        return self.scales

    def _resolve_weights(self, profile):
        resolved = dict(self.method_weights)

        default_cfg = self.template_profiles.get("default", {})
        if isinstance(default_cfg, dict) and isinstance(default_cfg.get("weights"), dict):
            for key, value in default_cfg["weights"].items():
                if key in resolved:
                    resolved[key] = float(value)

        if isinstance(profile, dict) and isinstance(profile.get("weights"), dict):
            for key, value in profile["weights"].items():
                if key in resolved:
                    resolved[key] = float(value)

        return resolved

    def _resolve_min_distance(self, explicit_min_distance, profile):
        mode_cfg = profile.get("find_all", {}) if isinstance(profile, dict) else {}
        if isinstance(mode_cfg, dict) and "min_distance" in mode_cfg:
            return int(mode_cfg["min_distance"])

        if isinstance(profile, dict) and "min_distance" in profile:
            return int(profile["min_distance"])

        default_cfg = self.template_profiles.get("default", {})
        if isinstance(default_cfg, dict) and "min_distance" in default_cfg:
            return int(default_cfg["min_distance"])

        return explicit_min_distance

    def _debug_write_overlay(self, screen_img, template_path, detections, title, template_wh):
        if not self.debug_enabled:
            return

        os.makedirs(self.debug_dir, exist_ok=True)
        output = self._to_bgr(screen_img).copy()
        tw, th = template_wh
        cv2.putText(output, title, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

        for idx, det in enumerate(detections):
            cx, cy, score = det
            x1 = max(0, int(cx - tw // 2))
            y1 = max(0, int(cy - th // 2))
            x2 = min(output.shape[1] - 1, x1 + tw)
            y2 = min(output.shape[0] - 1, y1 + th)
            cv2.rectangle(output, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.circle(output, (int(cx), int(cy)), 4, (0, 255, 0), -1)
            cv2.putText(output, f"#{idx + 1}:{score:.2f}", (x1, max(12, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        file_name = f"vision_debug_{ts}_{os.path.basename(template_path)}"
        out_path = os.path.join(self.debug_dir, file_name)
        cv2.imwrite(out_path, output)
        print(f"> Vision Debug: {out_path}")

    def _to_gray(self, img):
        if img is None:
            return None
        if len(img.shape) == 2:
            return img
        if img.shape[2] == 4:
            return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    def _to_bgr(self, img):
        if img is None:
            return None
        if len(img.shape) == 2:
            return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        if img.shape[2] == 4:
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        return img

    def _preprocess_gray(self, gray):
        # CLAHE giúp ổn định hơn khi brightness/contrast trên màn hình thay đổi.
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(gray)

    def _edge_map(self, gray):
        return cv2.Canny(gray, 60, 180)

    def _load_template_bundle(self, template_path):
        cached = self._template_cache.get(template_path)
        if cached is not None:
            return cached

        template = cv2.imread(template_path, cv2.IMREAD_UNCHANGED)
        if template is None:
            return None

        template_color = self._to_bgr(template)
        gray = self._to_gray(template_color)
        gray = self._preprocess_gray(gray)
        edge = self._edge_map(gray)

        bundle = {
            "color": template_color,
            "gray": gray,
            "edge": edge,
            "h": template_color.shape[0],
            "w": template_color.shape[1],
        }
        self._template_cache[template_path] = bundle
        return bundle

    def _resize_template(self, template, scale):
        if abs(scale - 1.0) < 1e-6:
            return template

        h, w = template.shape[:2]
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
        return cv2.resize(template, (nw, nh), interpolation=interp)

    def _result_to_detections(self, result, threshold, tw, th, min_distance):
        y_coords, x_coords = np.where(result >= threshold)
        raw = []
        for x, y in zip(x_coords, y_coords):
            center_x = int(x + tw // 2)
            center_y = int(y + th // 2)
            raw.append((center_x, center_y, float(result[y, x])))

        # Giữ điểm có score cao trước, rồi lọc theo khoảng cách để tránh trùng lặp.
        raw.sort(key=lambda p: p[2], reverse=True)
        picked = []
        for cx, cy, score in raw:
            duplicate = False
            for ex, ey, _ in picked:
                distance = ((cx - ex) ** 2 + (cy - ey) ** 2) ** 0.5
                if distance < min_distance:
                    duplicate = True
                    break
            if not duplicate:
                picked.append((cx, cy, score))

        return picked

    def find_template(self, screen_img, template_path, threshold=None, max_retries=1):
        """
        Tìm vị trí ảnh mẫu (template) trên ảnh màn hình lớn.
        Trả về tọa độ tâm (center_x, center_y) để click.

        Args:
            screen_img: Ảnh màn hình để tìm kiếm
            template_path: Đường dẫn đến ảnh mẫu
            threshold: Ngưỡng nhận diện (0.0 - 1.0). Nếu None, sử dụng self.threshold
            max_retries: Số lần thử tìm kiếm (mặc định 1)
        """
        profile = self._resolve_profile(template_path)
        threshold = self._resolve_threshold(threshold, profile, "find_template")
        scales = self._resolve_scales(profile)
        weights = self._resolve_weights(profile)
        print(f'Threshold: {threshold}')

        template_bundle = self._load_template_bundle(template_path)
        if template_bundle is None:
            print(f"!!! Lỗi Vision: Không đọc được file ảnh mẫu tại: {template_path}")
            return None

        screen_color = self._to_bgr(screen_img)
        screen_gray = self._preprocess_gray(self._to_gray(screen_color))
        screen_edge = self._edge_map(screen_gray)

        methods = [
            ("color", screen_color, template_bundle["color"], weights["color"]),
            ("gray", screen_gray, template_bundle["gray"], weights["gray"]),
            ("edge", screen_edge, template_bundle["edge"], weights["edge"]),
        ]

        # 3. Thử tìm kiếm với số lần thử được chỉ định
        for attempt in range(max_retries):
            best_score = -1.0
            best_raw_score = -1.0
            best_loc = None
            best_tw = 0
            best_th = 0
            best_method = ""
            best_scale = 1.0
            for scale in scales:
                for method_name, source, tpl_base, score_weight in methods:
                    tpl = self._resize_template(tpl_base, scale)
                    th, tw = tpl.shape[:2]

                    if source.shape[0] < th or source.shape[1] < tw:
                        continue

                    result = cv2.matchTemplate(source, tpl, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(result)
                    weighted_score = float(max_val) * score_weight

                    if weighted_score > best_score:
                        best_score = weighted_score
                        best_raw_score = float(max_val)
                        best_loc = max_loc
                        best_tw = tw
                        best_th = th
                        best_method = method_name
                        best_scale = scale

            if best_loc is not None and best_score >= threshold:
                loc_x, loc_y = cast(tuple[int, int], best_loc)
                center_x = loc_x + best_tw // 2
                center_y = loc_y + best_th // 2
                self._debug_write_overlay(
                    screen_color,
                    template_path,
                    [(center_x, center_y, best_score)],
                    f"find_template | {best_method} | scale={best_scale:.2f} | thr={threshold:.2f}",
                    (best_tw, best_th),
                )
                print(
                    f"> Vision: Tìm thấy '{template_path}' - score: {best_score:.2f} "
                    f"(raw={best_raw_score:.2f}, method={best_method}, scale={best_scale:.2f})"
                )
                return center_x, center_y

            # Nếu chưa tìm thấy và còn lần thử
            if attempt < max_retries - 1:
                print(f"> Vision: Lần {attempt + 1}/{max_retries} - Chưa tìm thấy, thử lại...")

        # Không tìm thấy sau tất cả các lần thử
        return None

    def find_all_templates(self, screen_img, template_path, threshold=None, min_distance=20):
        """
        Tìm TẤT CẢ các vị trí ảnh mẫu (template) trên ảnh màn hình.
        Trả về danh sách các tọa độ tâm [(x1, y1), (x2, y2), ...] sắp xếp theo y tăng dần.

        Args:
            screen_img: Ảnh màn hình để tìm kiếm
            template_path: Đường dẫn đến ảnh mẫu
            threshold: Ngưỡng nhận diện (0.0 - 1.0). Nếu None, sử dụng self.threshold
            min_distance: Khoảng cách tối thiểu giữa 2 điểm tìm được (tránh trùng lặp)

        Returns:
            List các tuple (center_x, center_y) sắp xếp theo y tăng dần, hoặc [] nếu không tìm thấy
        """
        profile = self._resolve_profile(template_path)
        threshold = self._resolve_threshold(threshold, profile, "find_all")
        min_distance = self._resolve_min_distance(min_distance, profile)
        scales = self._resolve_scales(profile)
        weights = self._resolve_weights(profile)
        print(f'Threshold: {threshold}')

        template_bundle = self._load_template_bundle(template_path)
        if template_bundle is None:
            print(f"!!! Lỗi Vision: Không đọc được file ảnh mẫu tại: {template_path}")
            return []

        screen_color = self._to_bgr(screen_img)
        screen_gray = self._preprocess_gray(self._to_gray(screen_color))
        screen_edge = self._edge_map(screen_gray)
        methods = [
            (screen_color, template_bundle["color"], weights["color"]),
            (screen_gray, template_bundle["gray"], weights["gray"]),
            (screen_edge, template_bundle["edge"], weights["edge"]),
        ]

        all_candidates = []
        for scale in scales:
            for source, tpl_base, score_weight in methods:
                tpl = self._resize_template(tpl_base, scale)
                th, tw = tpl.shape[:2]
                if source.shape[0] < th or source.shape[1] < tw:
                    continue

                result = cv2.matchTemplate(source, tpl, cv2.TM_CCOEFF_NORMED)
                detections = self._result_to_detections(result, threshold / score_weight, tw, th, min_distance)
                for cx, cy, score in detections:
                    all_candidates.append((cx, cy, score * score_weight))

        if not all_candidates:
            return []

        all_candidates.sort(key=lambda p: p[2], reverse=True)
        filtered_points = []
        for cx, cy, _ in all_candidates:
            is_duplicate = False
            for ex, ey in filtered_points:
                distance = ((cx - ex) ** 2 + (cy - ey) ** 2) ** 0.5
                if distance < min_distance:
                    is_duplicate = True
                    break
            if not is_duplicate:
                filtered_points.append((cx, cy))

        # 7. Sắp xếp theo tọa độ y tăng dần (trên cùng trước)
        filtered_points.sort(key=lambda p: p[1])

        print(f"> Vision: Tìm thấy {len(filtered_points)} vị trí của '{template_path}'")
        for i, pt in enumerate(filtered_points):
            print(f"   [{i + 1}] Tọa độ: ({pt[0]}, {pt[1]})")

        top_debug = []
        for cx, cy in filtered_points[:15]:
            top_debug.append((cx, cy, threshold))
        if top_debug:
            base_tw = template_bundle["w"]
            base_th = template_bundle["h"]
            self._debug_write_overlay(
                screen_color,
                template_path,
                top_debug,
                f"find_all | hits={len(filtered_points)} | thr={threshold:.2f}",
                (base_tw, base_th),
            )

        return filtered_points

