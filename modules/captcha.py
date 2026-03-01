import os
import cv2
import numpy as np
import onnxruntime as ort
import easyocr
import time


class CaptchaSolver:
    def __init__(self, assets_dir="assets"):
        model_path = os.path.join(assets_dir, "captcha_model.onnx")
        # Khởi tạo phiên ONNX Runtime (Chạy bằng CPU rất nhanh)
        self.session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])

        self.ocr = easyocr.Reader(['vi'], gpu=False, verbose=False)

        # Danh sách label (BẮT BUỘC PHẢI KHỚP THỨ TỰ VỚI LÚC TRAIN)
        # Bạn copy từ mảng in ra lúc chạy file train_captcha.py dán vào đây
        self.labels = [
            "bao_san", "bo_rung", "bumblebee", "chon_hoi", "gau", "heo_rung",
            "lao_ho", "linh_bua_khien", "linh_cung_doc", "linh_cung_ky",
            "linh_cung_lua", "linh_cuong_no", "linh_dao_khien", "linh_dao_ky",
            "linh_khien_lon", "linh_kiem_khien", "linh_kiem_ky", "linh_lien_no",
            "linh_mach_dao", "linh_riu_khien", "linh_riu_ky", "linh_song_thuong",
            "linh_thuong_khien", "linh_thuong_ky", "linh_trong_ky", "linh_truong_cung",
            "linh_truong_giao", "linh_truong_kiem", "linh_truong_mau", "linh_truong_thuong",
            "nhim", "soi_hoang", "than_lan", "tho_san", "voi", "xe_nem_da", "xe_no_lon"
        ]

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

    def detect_captcha(self, screen_img):
        """
        Dùng OpenCV Template Matching tìm tiêu đề "Kiểm tra ngẫu nhiên"
        Bạn cần chụp ảnh chữ này lưu thành 'title_captcha.png' trong assets
        """
        title = cv2.imread(os.path.join("assets", "title_captcha.png"))
        if title is None:
            return False

        res = cv2.matchTemplate(screen_img, title, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        return max_val > 0.7

    def solve(self, device, screen_img):
        print("   [CAPTCHA] Phát hiện Captcha. Đang phân tích...")
        h, w, _ = screen_img.shape

        # 1. OCR Tìm câu hỏi (Vùng text thường nằm giữa màn hình phía trên các icon)
        y1_text, y2_text = int(h * 0.35), int(h * 0.43)
        x1_text, x2_text = int(w * 0.3), int(w * 0.7)
        crop_text = screen_img[y1_text:y2_text, x1_text:x2_text]

        # Phóng to và OCR
        crop_enlarged = cv2.resize(crop_text, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        results = self.ocr.readtext(crop_enlarged)
        question_text = " ".join([res[1] for res in results])
        print(f"   [CAPTCHA] Câu hỏi đọc được: {question_text}")

        # Tìm Target Group trong Knowledge Base
        target_group = None
        for key in self.knowledge_base.keys():
            if key.lower() in question_text.lower():
                target_group = self.knowledge_base[key]
                print(f"   [CAPTCHA] Phát hiện loại mục tiêu cần tìm: {key}")
                break

        if not target_group:
            print("   [CAPTCHA-ERR] Không hiểu câu hỏi OCR.")
            return False

        # 2. Cắt 4 icon và Phân loại
        # Tọa độ ước lượng của 4 icon (Dựa vào captcha.png)
        # Bạn sẽ phải mở MS Paint lên đo lại tọa độ x,y chuẩn xác nhé
        icon_y_start = 368
        icon_y_end = 511
        box_width = 112.25  # Cỡ mỗi icon
        spacing = 0  # Khoảng cách giữa các icon (Nếu có) - Ở đây là sát nhau nên để 0
        start_x = 578

        best_icon_idx = -1
        best_confidence = -1

        for i in range(4):
            x1 = start_x + int(i * (box_width + spacing))
            x2 = x1 + int(box_width)

            icon_img = screen_img[icon_y_start:icon_y_end, x1:x2]

            # --- Tiền xử lý cho Model ONNX ---
            # Resize về 64x64, BGR -> RGB, Normalize
            img_resized = cv2.resize(icon_img, (64, 64))
            img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
            img_normalized = img_rgb.astype(np.float32) / 255.0

            # Tương đương với transforms.Normalize của PyTorch
            mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
            std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
            img_normalized = (img_normalized - mean) / std

            # Đổi shape từ (H, W, C) sang (1, C, H, W)
            input_tensor = np.transpose(img_normalized, (2, 0, 1))
            input_tensor = np.expand_dims(input_tensor, axis=0)

            # --- Chạy Model ---
            outputs = self.session.run(None, {'input': input_tensor})[0]

            # Lấy top 1 predict
            predicted_idx = np.argmax(outputs[0])
            confidence = outputs[0][predicted_idx]
            predicted_label = self.labels[predicted_idx]

            print(f"   [CAPTCHA] Icon {i + 1} -> {predicted_label} (Conf: {confidence:.2f})")

            # Nếu nhãn dự đoán nằm trong nhóm cần tìm
            if predicted_label in target_group:
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_icon_idx = i
                    # Tọa độ tâm để click
                    target_click_x = x1 + box_width // 2
                    target_click_y = icon_y_start + (icon_y_end - icon_y_start) // 2

        # 3. Thực thi hành động
        if best_icon_idx != -1:
            print(f"   [CAPTCHA] => CHỌN ICON SỐ {best_icon_idx + 1}")
            device.tap(target_click_x, target_click_y)
            time.sleep(1)

            # Bấm nút OK ở dưới (Cần cắt ảnh btn_ok_captcha.png)
            btn_ok = cv2.imread(os.path.join("assets", "btn_ok_captcha.png"))
            res_ok = cv2.matchTemplate(screen_img, btn_ok, cv2.TM_CCOEFF_NORMED)
            _, max_val_ok, _, max_loc_ok = cv2.minMaxLoc(res_ok)
            if max_val_ok > 0.7:
                device.tap(max_loc_ok[0] + btn_ok.shape[1] // 2, max_loc_ok[1] + btn_ok.shape[0] // 2)

            print("   [CAPTCHA] Đã giải xong!")
            return True

        return False
