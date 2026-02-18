import time
import os


class SceneManager:
    def __init__(self, device, vision):
        self.device = device
        self.vision = vision
        self.assets_dir = os.path.join(os.getcwd(), "assets")

    def _get_path(self, filename):
        return os.path.join(self.assets_dir, filename)

    def go_to_city(self, max_retries=3):
        """Vào màn hình thành chính với double check"""
        print("   > Đang kiểm tra vị trí: Cần vào Thành Chính...")

        for attempt in range(max_retries):
            # Tìm nút Vào Thành
            pos = self.vision.find_template(self.device.take_screenshot(), self._get_path("btn_vao_thanh.png"))
            if pos:
                print(f"   > Phát hiện nút Vào Thành. Click ngay. (Lần thử {attempt + 1})")
                self.device.tap(pos[0], pos[1])
                time.sleep(2)  # Chờ load cảnh trong thành

                # Double check: kiểm tra xem nút còn hiện không
                check_pos = self.vision.find_template(self.device.take_screenshot(),
                                                      self._get_path("btn_vao_thanh.png"))
                if not check_pos:
                    print("   > ✓ Đã vào thành thành công (nút Vào Thành không còn).")
                    return True
                else:
                    print("   > [!] Nút Vào Thành vẫn còn. Thử lại...")
            else:
                print("   > (Giả định) Đã ở trong thành hoặc không thấy nút.")
                return True

        print("   > [WARN] Không thể vào thành sau nhiều lần thử.")
        return False

    def leave_the_city(self, max_retries=3):
        """Ra khỏi thành chính với double check"""
        print("   > Đang kiểm tra vị trí: Cần ra khỏi Thành Chính...")

        for attempt in range(max_retries):
            # Tìm nút Ra Thành
            pos = self.vision.find_template(self.device.take_screenshot(), self._get_path("btn_ra_thanh.png"))
            if pos:
                print(f"   > Phát hiện nút Ra Thành. Click ngay. (Lần thử {attempt + 1})")
                self.device.tap(pos[0], pos[1])
                time.sleep(2)  # Chờ load cảnh ngoài thành

                # Double check: kiểm tra xem nút còn hiện không
                check_pos = self.vision.find_template(self.device.take_screenshot(), self._get_path("btn_ra_thanh.png"))
                if not check_pos:
                    print("   > ✓ Đã ra thành thành công (nút Ra Thành không còn).")
                    return True
                else:
                    print("   > [!] Nút Ra Thành vẫn còn. Thử lại...")
            else:
                print("   > (Giả định) Đã ở ngoài thành hoặc không thấy nút.")
                return True

        print("   > [WARN] Không thể ra thành sau nhiều lần thử.")
        return False
