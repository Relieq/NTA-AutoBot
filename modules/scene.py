import time
import os


class SceneManager:
    def __init__(self, device, vision):
        self.device = device
        self.vision = vision
        self.assets_dir = os.path.join(os.getcwd(), "assets")

    def _get_path(self, filename):
        return os.path.join(self.assets_dir, filename)

    def go_to_city(self):
        """Vào màn hình thành chính"""
        print("   > Đang kiểm tra vị trí: Cần vào Thành Chính...")
        # Tìm nút Vào Thành
        if self.vision.find_template(self.device.take_screenshot(), self._get_path("btn_vao_thanh.png")):
            print("   > Phát hiện nút Vào Thành. Click ngay.")
            # Tìm và click
            pos = self.vision.find_template(self.device.take_screenshot(), self._get_path("btn_vao_thanh.png"))
            if pos:
                self.device.tap(pos[0], pos[1])
                time.sleep(4)  # Chờ load cảnh trong thành
        else:
            print("   > (Giả định) Đã ở trong thành hoặc không thấy nút.")

    def leave_the_city(self):
        """Ra khỏi thành chính"""
        print("   > Đang kiểm tra vị trí: Cần ra khỏi Thành Chính...")
        # Tìm nút Ra Thành
        if self.vision.find_template(self.device.take_screenshot(), self._get_path("btn_ra_thanh.png")):
            print("   > Phát hiện nút Ra Thành. Click ngay.")
            # Tìm và click
            pos = self.vision.find_template(self.device.take_screenshot(), self._get_path("btn_ra_thanh.png"))
            if pos:
                self.device.tap(pos[0], pos[1])
                time.sleep(4)  # Chờ load cảnh ngoài thành
        else:
            print("   > (Giả định) Đã ở ngoài thành hoặc không thấy nút.")

