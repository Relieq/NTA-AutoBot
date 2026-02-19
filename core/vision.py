import cv2
import numpy as np


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
        threshold = threshold if threshold is not None else self.threshold
        print(f'Threshold: {threshold}')

        # 1. Đọc ảnh mẫu
        template = cv2.imread(template_path)
        if template is None:
            print(f"!!! Lỗi Vision: Không đọc được file ảnh mẫu tại: {template_path}")
            return []

        # 2. Lấy kích thước ảnh mẫu
        h, w = template.shape[:2]

        # 3. So sánh ảnh mẫu với màn hình
        result = cv2.matchTemplate(screen_img, template, cv2.TM_CCOEFF_NORMED)

        # 4. Tìm TẤT CẢ các điểm vượt ngưỡng
        locations = np.where(result >= threshold)

        # 5. Chuyển đổi thành danh sách tọa độ (x, y) và tính tâm
        points = []
        # locations trả về (rows, cols) = (y_coords, x_coords)
        y_coords, x_coords = locations
        for x, y in zip(x_coords, y_coords):
            center_x = int(x) + w // 2
            center_y = int(y) + h // 2
            points.append((center_x, center_y))

        if not points:
            return []

        # 6. Loại bỏ các điểm quá gần nhau (Non-Maximum Suppression đơn giản)
        filtered_points = []
        for pt in points:
            is_duplicate = False
            for existing_pt in filtered_points:
                distance = ((pt[0] - existing_pt[0]) ** 2 + (pt[1] - existing_pt[1]) ** 2) ** 0.5
                if distance < min_distance:
                    is_duplicate = True
                    break
            if not is_duplicate:
                filtered_points.append(pt)

        # 7. Sắp xếp theo tọa độ y tăng dần (trên cùng trước)
        filtered_points.sort(key=lambda p: p[1])

        print(f"> Vision: Tìm thấy {len(filtered_points)} vị trí của '{template_path}'")
        for i, pt in enumerate(filtered_points):
            print(f"   [{i + 1}] Tọa độ: ({pt[0]}, {pt[1]})")

        return filtered_points

