import os
import cv2
import numpy as np
import onnxruntime as ort
import easyocr
import time
import unicodedata


class CaptchaSolver:
    def __init__(self, assets_dir="assets", dataset_dir="dataset"):
        model_path = os.path.join(assets_dir, "captcha_model.onnx")
        # Khởi tạo phiên ONNX Runtime (Chạy bằng CPU rất nhanh)
        self.session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
        self.group_session = None
        self.assets_dir = assets_dir
        self.dataset_dir = dataset_dir

        self.ocr = easyocr.Reader(['vi'], gpu=False, verbose=False)

        self.labels = self._load_labels(assets_dir)

        # Knowledge Base ánh xạ Câu hỏi -> Label của Model
        self.knowledge_base = {
            "Lính Thương": ["linh_mach_dao", "linh_song_thuong", "linh_truong_giao", "linh_truong_kiem",
                            "linh_truong_mau", "linh_truong_thuong"],
            "Lính Khiên": ["linh_bua_khien", "linh_dao_khien", "linh_kiem_khien", "linh_khien_lon", "linh_riu_khien",
                           "linh_thuong_khien"],
            "Lính Cung": ["linh_cung_doc", "linh_cung_lua", "linh_cuong_no", "linh_lien_no", "linh_truong_cung",
                          "tho_san"],
            "Lính Kỵ": ["linh_cung_ky", "linh_dao_ky", "linh_kiem_ky", "linh_riu_ky", "linh_thuong_ky",
                        "linh_trong_ky"],
            "Khí Giới": ["xe_nem_da", "xe_no_lon"],
            "Dã Thú": ["chon_hoi", "gau", "nhim", "voi", "soi_hoang", "bao_san", "heo_rung", "bumblebee", "than_lan",
                       "lao_ho", "bo_rung"]
        }

        # Alias để bắt lỗi OCR câu hỏi tốt hơn (không dấu + biến thể).
        self.prompt_aliases = {
            "Lính Thương": ["linh thuong"],
            "Lính Khiên": ["linh khien"],
            "Lính Cung": ["linh cung"],
            "Lính Kỵ": ["linh ky", "linh ki"],
            "Khí Giới": ["khi gioi", "khi gio"],
            "Dã Thú": ["da thu", "thu", "thu hoang"],
        }

        self.input_name = self.session.get_inputs()[0].name
        self.group_labels = self._load_group_labels()
        self.group_to_idx = {name: i for i, name in enumerate(self.group_labels)}
        self.group_to_idx_norm = {self._normalize_text(name): i for i, name in enumerate(self.group_labels)}
        self._load_group_session()
        self.label_to_idx = {label: i for i, label in enumerate(self.labels)}
        self._validate_knowledge_base()
        self.prototype_bank = self._build_prototype_bank()
        self.group_prototype_bank = self._build_group_prototype_bank()

    def _load_group_labels(self):
        default_groups = [
            "Lính Thương",
            "Lính Khiên",
            "Lính Cung",
            "Lính Kỵ",
            "Khí Giới",
            "Dã Thú",
        ]

        path = os.path.join(self.assets_dir, "captcha_group_labels.json")
        if os.path.exists(path):
            try:
                import json
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, list) and all(isinstance(x, str) for x in loaded):
                    print(f"   [CAPTCHA] Đã load group labels từ: {path}")
                    return loaded
            except Exception as exc:
                print(f"   [CAPTCHA-WARN] Không đọc được captcha_group_labels.json: {exc}")

        return default_groups

    def _load_group_session(self):
        group_model_path = os.path.join(self.assets_dir, "captcha_group_model.onnx")
        if not os.path.exists(group_model_path):
            print("   [CAPTCHA] Chưa có captcha_group_model.onnx, dùng class-hybrid hiện tại.")
            return

        try:
            self.group_session = ort.InferenceSession(group_model_path, providers=['CPUExecutionProvider'])
            self.group_input_name = self.group_session.get_inputs()[0].name
            print(f"   [CAPTCHA] Đã load group model: {group_model_path}")
        except Exception as exc:
            print(f"   [CAPTCHA-WARN] Không load được group model: {exc}")
            self.group_session = None

    def _load_labels(self, assets_dir):
        labels_path = os.path.join(assets_dir, "captcha_labels.json")
        if os.path.exists(labels_path):
            try:
                import json
                with open(labels_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, list) and all(isinstance(x, str) for x in loaded):
                    print(f"   [CAPTCHA] Đã load labels từ: {labels_path}")
                    return loaded
            except Exception as exc:
                print(f"   [CAPTCHA-WARN] Không đọc được captcha_labels.json: {exc}")

        # Fallback để tương thích ngược.
        print("   [CAPTCHA-WARN] Dùng labels hardcode (chưa có captcha_labels.json).")
        return [
            "bao_san", "bo_rung", "bumblebee", "chon_hoi", "gau", "heo_rung",
            "lao_ho", "linh_bua_khien", "linh_cung_doc", "linh_cung_ky",
            "linh_cung_lua", "linh_cuong_no", "linh_dao_khien", "linh_dao_ky",
            "linh_khien_lon", "linh_kiem_khien", "linh_kiem_ky", "linh_lien_no",
            "linh_mach_dao", "linh_riu_khien", "linh_riu_ky", "linh_song_thuong",
            "linh_thuong_khien", "linh_thuong_ky", "linh_trong_ky", "linh_truong_cung",
            "linh_truong_giao", "linh_truong_kiem", "linh_truong_mau", "linh_truong_thuong",
            "nhim", "soi_hoang", "than_lan", "tho_san", "voi", "xe_nem_da", "xe_no_lon"
        ]

    def _validate_knowledge_base(self):
        """Kiểm tra mapping nhóm mục tiêu có khớp label model hay không."""
        label_set = set(self.labels)
        missing = []
        for group_name, group_labels in self.knowledge_base.items():
            for label in group_labels:
                if label not in label_set:
                    missing.append((group_name, label))

        if missing:
            print("   [CAPTCHA-WARN] Knowledge base có label không tồn tại trong model labels:")
            for group_name, label in missing:
                print(f"   - {group_name}: {label}")

    def _normalize_text(self, text):
        if not text:
            return ""
        text = str(text).strip().lower()
        text = unicodedata.normalize("NFD", text)
        text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
        text = text.replace("đ", "d")
        text = " ".join(text.split())
        return text

    def _preprocess_icon(self, icon_img):
        img_resized = cv2.resize(icon_img, (64, 64))
        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        img_normalized = img_rgb.astype(np.float32) / 255.0

        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        img_normalized = (img_normalized - mean) / std

        input_tensor = np.transpose(img_normalized, (2, 0, 1))
        input_tensor = np.expand_dims(input_tensor, axis=0)
        return input_tensor

    def _infer_logits(self, icon_img):
        input_tensor = self._preprocess_icon(icon_img)
        outputs = self.session.run(None, {self.input_name: input_tensor})[0]
        logits = outputs[0].astype(np.float32)
        return logits

    def _infer_group_logits(self, icon_img):
        if self.group_session is None:
            return None
        input_tensor = self._preprocess_icon(icon_img)
        outputs = self.group_session.run(None, {self.group_input_name: input_tensor})[0]
        return outputs[0].astype(np.float32)

    def _extract_icon_core(self, screen_img, bbox):
        """Crop vùng lõi của icon để giảm nhiễu từ viền khung captcha."""
        x1, y1, x2, y2 = bbox
        h, w, _ = screen_img.shape

        # Trim viền: khung icon captcha thường gây nhiễu lớn hơn phần object ở giữa.
        margin_x = max(6, int((x2 - x1) * 0.12))
        margin_y = max(6, int((y2 - y1) * 0.10))

        cx1 = max(0, x1 + margin_x)
        cy1 = max(0, y1 + margin_y)
        cx2 = min(w, x2 - margin_x)
        cy2 = min(h, y2 - margin_y)

        if cx2 <= cx1 or cy2 <= cy1:
            return screen_img[y1:y2, x1:x2]

        return screen_img[cy1:cy2, cx1:cx2]

    def _l2_normalize(self, vector):
        norm = float(np.linalg.norm(vector))
        if norm < 1e-8:
            return vector
        return vector / norm

    def _build_prototype_bank(self):
        """Tạo prototype feature cho từng class từ ảnh trong dataset/ để so similarity."""
        bank = {}
        if not os.path.isdir(self.dataset_dir):
            print(f"   [CAPTCHA-WARN] Không thấy dataset tại: {self.dataset_dir}.")
            return bank

        for label in self.labels:
            class_dir = os.path.join(self.dataset_dir, label)
            if not os.path.isdir(class_dir):
                continue

            vectors = []
            for file_name in sorted(os.listdir(class_dir)):
                if not file_name.lower().endswith((".png", ".jpg", ".jpeg")):
                    continue
                img_path = os.path.join(class_dir, file_name)
                img = cv2.imread(img_path)
                if img is None:
                    continue
                # Cả ảnh gốc + ảnh lật ngang vào prototype để tăng độ bền với captcha đảo trái-phải.
                logits_orig = self._infer_logits(img)
                vectors.append(self._l2_normalize(logits_orig))

                img_flip = cv2.flip(img, 1)
                logits_flip = self._infer_logits(img_flip)
                vectors.append(self._l2_normalize(logits_flip))

            if vectors:
                centroid = np.mean(np.stack(vectors, axis=0), axis=0)
                bank[label] = self._l2_normalize(centroid)

        print(f"   [CAPTCHA] Prototype bank: {len(bank)}/{len(self.labels)} class.")
        return bank

    def _build_group_prototype_bank(self):
        """Tạo prototype theo GROUP (6 nhóm) từ prototype class để bám mục tiêu captcha."""
        group_bank = {}
        for group_name, group_labels in self.knowledge_base.items():
            vectors = []
            for label in group_labels:
                proto = self.prototype_bank.get(label)
                if proto is not None:
                    vectors.append(proto)
            if vectors:
                centroid = np.mean(np.stack(vectors, axis=0), axis=0)
                group_bank[group_name] = self._l2_normalize(centroid)

        print(f"   [CAPTCHA] Group prototype bank: {len(group_bank)}/{len(self.knowledge_base)} group.")
        return group_bank

    def _detect_target_group(self, question_text):
        question_norm = self._normalize_text(question_text)
        for group_name, labels in self.knowledge_base.items():
            aliases = [self._normalize_text(group_name)] + [self._normalize_text(a) for a in self.prompt_aliases.get(group_name, [])]
            for alias in aliases:
                if alias and alias in question_norm:
                    return group_name, labels
        return None, None

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

    def _score_icon_similarity(self, icon_logits, target_group_name, target_group):
        """Tính similarity target/non-target và trả score hybrid để chọn 1/4 ổn định hơn."""
        target_set = set(target_group)
        non_target_group = [label for label in self.labels if label not in target_set]

        feat = self._l2_normalize(icon_logits)
        probs = self._softmax(icon_logits)

        target_best_score, target_best_label, target_details = self._score_similarity_for_labels(feat, target_group)
        non_target_best_score, non_target_best_label, non_target_details = self._score_similarity_for_labels(feat, non_target_group)

        target_prob = self._max_prob_for_labels(probs, target_group)
        non_target_prob = self._max_prob_for_labels(probs, non_target_group)
        target_group_prob = self._sum_prob_for_labels(probs, target_group)

        target_group_proto = self.group_prototype_bank.get(target_group_name)
        target_group_sim = float(np.dot(feat, target_group_proto)) if target_group_proto is not None else 0.0

        best_other_group_sim = -1.0
        best_other_group_name = ""
        best_other_group_prob = 0.0
        for group_name, group_labels in self.knowledge_base.items():
            if group_name == target_group_name:
                continue
            group_proto = self.group_prototype_bank.get(group_name)
            if group_proto is None:
                continue

            sim = float(np.dot(feat, group_proto))
            prob = self._sum_prob_for_labels(probs, group_labels)
            if sim > best_other_group_sim:
                best_other_group_sim = sim
                best_other_group_name = group_name
            if prob > best_other_group_prob:
                best_other_group_prob = prob

        pred_idx = int(np.argmax(icon_logits))
        pred_label = self.labels[pred_idx]
        pred_in_target = pred_label in target_set

        hybrid = (
            0.8 * target_best_score
            - 0.6 * non_target_best_score
            + 0.9 * target_prob
            - 0.8 * non_target_prob
            + 1.3 * target_group_sim
            - 1.1 * max(best_other_group_sim, -1.0)
            + 1.4 * target_group_prob
            - 1.3 * best_other_group_prob
            + (0.10 if pred_in_target else -0.10)
        )

        return {
            "selected_variant": "orig",
            "hybrid_score": float(hybrid),
            "target_best_score": float(target_best_score),
            "target_best_label": target_best_label,
            "target_details": target_details,
            "non_target_best_score": float(non_target_best_score),
            "non_target_best_label": non_target_best_label,
            "non_target_details": non_target_details,
            "target_prob": float(target_prob),
            "non_target_prob": float(non_target_prob),
            "target_group_prob": float(target_group_prob),
            "target_group_sim": float(target_group_sim),
            "best_other_group_name": best_other_group_name,
            "best_other_group_sim": float(best_other_group_sim),
            "best_other_group_prob": float(best_other_group_prob),
            "pred_in_target": pred_in_target,
            "pred_label": pred_label,
            "pred_logit": float(icon_logits[pred_idx]),
        }

    def _softmax(self, logits):
        shifted = logits - np.max(logits)
        exp = np.exp(shifted)
        denom = np.sum(exp)
        if denom <= 0:
            return np.zeros_like(logits, dtype=np.float32)
        return (exp / denom).astype(np.float32)

    def _max_prob_for_labels(self, probs, label_list):
        best = 0.0
        for label in label_list:
            idx = self.label_to_idx.get(label)
            if idx is not None:
                best = max(best, float(probs[idx]))
        return best

    def _sum_prob_for_labels(self, probs, label_list):
        total = 0.0
        for label in label_list:
            idx = self.label_to_idx.get(label)
            if idx is not None:
                total += float(probs[idx])
        return total

    def _score_group_model(self, group_logits, target_group_name):
        if group_logits is None:
            return {
                "target_group_prob_model": 0.0,
                "best_other_group_name_model": "",
                "best_other_group_prob_model": 0.0,
                "group_model_score": 0.0,
            }

        probs = self._softmax(group_logits)
        target_key = self._normalize_text(target_group_name)
        target_idx = self.group_to_idx_norm.get(target_key)
        target_prob = float(probs[target_idx]) if target_idx is not None and target_idx < len(probs) else 0.0

        best_other_name = ""
        best_other_prob = 0.0
        for group_name, idx in self.group_to_idx.items():
            if self._normalize_text(group_name) == target_key:
                continue
            if idx < len(probs) and float(probs[idx]) > best_other_prob:
                best_other_prob = float(probs[idx])
                best_other_name = group_name

        # Ưu tiên mạnh theo objective thật của captcha: đúng group 6 lớp.
        group_score = 2.6 * target_prob - 2.0 * best_other_prob
        return {
            "target_group_prob_model": target_prob,
            "best_other_group_name_model": best_other_name,
            "best_other_group_prob_model": best_other_prob,
            "group_model_score": float(group_score),
        }

    def _score_similarity_for_labels(self, normalized_feature, label_list):
        best_label = None
        best_score = -1.0
        details = []

        for label in label_list:
            proto = self.prototype_bank.get(label)
            if proto is None:
                continue
            score = float(np.dot(normalized_feature, proto))
            details.append((label, score))
            if score > best_score:
                best_score = score
                best_label = label

        details.sort(key=lambda item: item[1], reverse=True)
        return best_score, best_label, details

    def analyze_captcha(self, screen_img):
        """Phân tích captcha từ ảnh màn hình và trả kết quả lựa chọn 1/4 icon."""
        h, w, _ = screen_img.shape

        y1_text, y2_text = int(h * 0.35), int(h * 0.43)
        x1_text, x2_text = int(w * 0.3), int(w * 0.7)
        crop_text = screen_img[y1_text:y2_text, x1_text:x2_text]

        crop_enlarged = cv2.resize(crop_text, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        results = self.ocr.readtext(crop_enlarged)
        question_text = " ".join([res[1] for res in results])
        print(f"   [CAPTCHA] Câu hỏi đọc được: {question_text}")

        target_group_name, target_group = self._detect_target_group(question_text)
        if not target_group:
            print("   [CAPTCHA-ERR] Không hiểu câu hỏi OCR.")
            return {
                "ok": False,
                "question_text": question_text,
                "target_group_name": "",
                "target_group": [],
                "icons": [],
                "selected_index": -1,
                "selected_click": None,
            }

        print(f"   [CAPTCHA] Phát hiện loại mục tiêu cần tìm: {target_group_name}")

        icon_infos = []
        boxes = self._icon_boxes()
        selected_index = -1
        selected_score = -1e9
        selected_click = None

        for i, (x1, y1, x2, y2) in enumerate(boxes):
            icon_img = self._extract_icon_core(screen_img, (x1, y1, x2, y2))
            logits_orig = self._infer_logits(icon_img)
            predicted_idx = int(np.argmax(logits_orig))
            predicted_label = self.labels[predicted_idx]
            pred_conf = float(logits_orig[predicted_idx])

            scoring = self._score_icon_similarity(logits_orig, target_group_name, target_group)
            group_logits = self._infer_group_logits(icon_img)
            group_scoring = self._score_group_model(group_logits, target_group_name)

            # Nếu có group model: chọn theo objective thật của captcha (6 nhóm).
            # Class-hybrid chỉ dùng tie-break khi group_score quá sát nhau.
            if self.group_session is not None:
                final_score = group_scoring["group_model_score"]
            else:
                final_score = scoring["hybrid_score"]

            top3_target = ", ".join([f"{label}:{score:.4f}" for label, score in scoring["target_details"][:3]])
            top2_non_target = ", ".join([f"{label}:{score:.4f}" for label, score in scoring["non_target_details"][:2]])

            print(
                f"   [CAPTCHA] Icon {i + 1} -> pred={predicted_label} (logit={pred_conf:.2f}) "
                f"| variant={scoring['selected_variant']} "
                f"| pred_variant={scoring['pred_label']} ({scoring['pred_logit']:.2f}) "
                f"| final={final_score:.4f} "
                f"| hybrid={scoring['hybrid_score']:.4f} "
                f"| g_model={group_scoring['group_model_score']:.4f} "
                f"(p_tgt={group_scoring['target_group_prob_model']:.4f}, "
                f"p_other={group_scoring['best_other_group_name_model']}:{group_scoring['best_other_group_prob_model']:.4f}) "
                f"| tgt={scoring['target_best_label']}:{scoring['target_best_score']:.4f} "
                f"| non={scoring['non_target_best_label']}:{scoring['non_target_best_score']:.4f} "
                f"| g_tgt={scoring['target_group_sim']:.4f} g_other={scoring['best_other_group_name']}:{scoring['best_other_group_sim']:.4f} "
                f"| p_tgt={scoring['target_prob']:.4f} p_non={scoring['non_target_prob']:.4f} "
                f"| pg_tgt={scoring['target_group_prob']:.4f} pg_other={scoring['best_other_group_prob']:.4f} "
                f"| top3_tgt=[{top3_target}] top2_non=[{top2_non_target}]"
            )

            icon_infos.append(
                {
                    "index": i,
                    "bbox": (x1, y1, x2, y2),
                    "predicted_label": scoring["pred_label"],
                    "predicted_logit": scoring["pred_logit"],
                    "predicted_label_orig": predicted_label,
                    "predicted_logit_orig": pred_conf,
                    "selected_variant": scoring["selected_variant"],
                    "best_target_label": scoring["target_best_label"],
                    "similarity": scoring["target_best_score"],
                    "target_group_scores": scoring["target_details"],
                    "best_non_target_label": scoring["non_target_best_label"],
                    "non_target_similarity": scoring["non_target_best_score"],
                    "non_target_scores": scoring["non_target_details"],
                    "target_prob": scoring["target_prob"],
                    "non_target_prob": scoring["non_target_prob"],
                    "target_group_prob": scoring["target_group_prob"],
                    "target_group_sim": scoring["target_group_sim"],
                    "best_other_group_name": scoring["best_other_group_name"],
                    "best_other_group_sim": scoring["best_other_group_sim"],
                    "best_other_group_prob": scoring["best_other_group_prob"],
                    "target_group_prob_model": group_scoring["target_group_prob_model"],
                    "best_other_group_name_model": group_scoring["best_other_group_name_model"],
                    "best_other_group_prob_model": group_scoring["best_other_group_prob_model"],
                    "group_model_score": group_scoring["group_model_score"],
                    "pred_in_target": scoring["pred_in_target"],
                    "hybrid_score": scoring["hybrid_score"],
                    "final_score": float(final_score),
                }
            )

            if final_score > selected_score:
                selected_score = final_score
                selected_index = i
                selected_click = (int((x1 + x2) / 2), int((y1 + y2) / 2))
            elif self.group_session is not None and abs(final_score - selected_score) <= 0.02:
                # Tie-break nhỏ: ưu tiên icon có class-hybrid tốt hơn.
                current_best_hybrid = icon_infos[selected_index]["hybrid_score"] if selected_index != -1 else -1e9
                if scoring["hybrid_score"] > current_best_hybrid:
                    selected_score = final_score
                    selected_index = i
                    selected_click = (int((x1 + x2) / 2), int((y1 + y2) / 2))

        # Theo rule captcha mới: luôn có 1 đáp án đúng trong 4.
        return {
            "ok": selected_index != -1,
            "question_text": question_text,
            "target_group_name": target_group_name,
            "target_group": target_group,
            "icons": icon_infos,
            "selected_index": selected_index,
            "selected_click": selected_click,
        }

    def detect_captcha(self, screen_img):
        """
        Dùng OpenCV Template Matching tìm tiêu đề "Kiểm tra ngẫu nhiên"
        Bạn cần chụp ảnh chữ này lưu thành 'title_captcha.png' trong assets
        """
        title = cv2.imread(os.path.join(self.assets_dir, "title_captcha.png"))
        if title is None:
            return False

        res = cv2.matchTemplate(screen_img, title, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        return max_val > 0.7

    def solve(self, device, screen_img):
        print("   [CAPTCHA] Phát hiện Captcha. Đang phân tích...")
        analysis = self.analyze_captcha(screen_img)

        # 3. Thực thi hành động
        if analysis["ok"] and analysis["selected_click"] is not None:
            selected_idx = analysis["selected_index"]
            click_x, click_y = analysis["selected_click"]

            print(f"   [CAPTCHA] => CHỌN ICON SỐ {selected_idx + 1}")
            device.tap(click_x, click_y)
            time.sleep(1)

            # Bấm nút OK ở dưới (Cần cắt ảnh btn_ok_captcha.png)
            btn_ok = cv2.imread(os.path.join(self.assets_dir, "btn_ok_captcha.png"))
            if btn_ok is not None:
                screen_after_click = device.take_screenshot()
                res_ok = cv2.matchTemplate(screen_after_click, btn_ok, cv2.TM_CCOEFF_NORMED)
                _, max_val_ok, _, max_loc_ok = cv2.minMaxLoc(res_ok)
                if max_val_ok > 0.7:
                    device.tap(max_loc_ok[0] + btn_ok.shape[1] // 2, max_loc_ok[1] + btn_ok.shape[0] // 2)

            print("   [CAPTCHA] Đã giải xong!")
            return True

        return False
