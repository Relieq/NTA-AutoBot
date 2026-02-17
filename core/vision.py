import cv2


class VisionManager:
    def __init__(self):
        # Ngưỡng nhận diện mặc định (0.8 = chính xác 80%)
        # Nếu bot không tìm thấy, hãy giảm xuống 0.7 hoặc 0.6
        # Nếu bot bấm nhầm chỗ, hãy tăng lên 0.9
        self.threshold = 0.6

    def find_template(self, screen_img, template_path, threshold=None):
        """
        Tìm vị trí ảnh mẫu (template) trên ảnh màn hình lớn.
        Trả về tọa độ tâm (center_x, center_y) để click.

        Args:
            screen_img: Ảnh màn hình để tìm kiếm
            template_path: Đường dẫn đến ảnh mẫu
            threshold: Ngưỡng nhận diện (0.0 - 1.0). Nếu None, sử dụng self.threshold
        """
        # Sử dụng threshold truyền vào, nếu không có thì dùng giá trị mặc định
        threshold = threshold if threshold is not None else self.threshold
        print(f'Threshold: {threshold}')

        # 1. Đọc ảnh mẫu từ đường dẫn assets
        template = cv2.imread(template_path)
        if template is None:
            print(f"!!! Lỗi Vision: Không đọc được file ảnh mẫu tại: {template_path}")
            return None

        # 2. Lấy kích thước ảnh mẫu (chiều cao h, chiều rộng w)
        h, w = template.shape[:2]

        # 3. So sánh ảnh mẫu với màn hình bằng phương pháp TM_CCOEFF_NORMED
        # (Đây là phương pháp phổ biến và chính xác nhất cho dạng này)
        result = cv2.matchTemplate(screen_img, template, cv2.TM_CCOEFF_NORMED)

        # 4. Tìm điểm có độ trùng khớp cao nhất
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        # 5. Kiểm tra xem độ trùng khớp có vượt qua ngưỡng không
        if max_val >= threshold:
            # max_loc là tọa độ góc trên-trái của vùng tìm thấy.
            # Ta cần tính tọa độ tâm để click vào giữa nút cho chắc ăn.
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            print(f"> Vision: Tìm thấy '{template_path}' - Độ chính xác: {max_val:.2f}")
            return center_x, center_y

        # Không tìm thấy hoặc độ chính xác thấp hơn ngưỡng
        return None
