import time
import os


class DailyTaskManager:
    def __init__(self, device_manager, vision_manager):
        self.device = device_manager
        self.vision = vision_manager
        self.assets_dir = os.path.join(os.getcwd(), "assets")

    def _get_path(self, filename):
        return os.path.join(self.assets_dir, filename)

    # --- HÀM HỖ TRỢ MỚI (Giúp code ngắn gọn hơn) ---
    def find_and_tap(self, image_name, wait_after=1, retries=1, threshold=None):
        """
        Tìm ảnh -> Nếu thấy thì Tap -> Chờ một chút.
        Trả về True nếu tap thành công, False nếu không tìm thấy.

        Args:
            image_name: Tên file ảnh trong thư mục assets
            wait_after: Thời gian chờ sau khi tap (giây)
            retries: Số lần thử lại nếu không tìm thấy
            threshold: Ngưỡng nhận diện (0.0 - 1.0). Nếu None, sử dụng giá trị mặc định
        """
        path = self._get_path(image_name)

        for i in range(retries):
            screen = self.device.take_screenshot()
            if screen is None:
                return False

            pos = self.vision.find_template(screen, path, threshold=threshold)

            if pos:
                print(f"   [+] Tim thay '{image_name}'. Tap vao {pos}...")
                self.device.tap(pos[0], pos[1])
                time.sleep(wait_after)
                return True

            if i < retries - 1:
                time.sleep(1)  # Chờ 1s trước khi thử lại

        print(f"   [-] Không tìm thấy '{image_name}'")
        return False

    # --- CHỨC NĂNG 1: VÒNG QUAY ---
    def do_lucky_wheel(self):
        print("\n--- ACTION: Vòng Quay May Mắn ---")
        # 1. Tìm icon ngoài map
        if self.find_and_tap("icon_vong_quay.png", wait_after=3, threshold=0.6):
            # 2. Tìm nút Quay bên trong
            if self.find_and_tap("btn_quay.png", wait_after=4, threshold=0.6):
                print("   > Đã quay xong.")
            else:
                print("   > Không tháy nút quay (Hết lượt?).")

            # 3. Thoát ra (Tap vào vùng an toàn)
            self.device.tap(1, 1)
            time.sleep(1)
        else:
            print("   > Không thấy icon Vòng Quay ở màn hình chính.")

    # --- CHỨC NĂNG 2: NHẬN VÀNG FREE ---
    def claim_free_gold(self):
        print("\n--- ACTION: Nhận 3 Vàng Free ---")

        # 1. Tìm và bấm vào Cửa Tiệm
        # (Thử 2 lần cho chắc, lỡ game lag chưa load kịp map)
        if self.find_and_tap("icon_cua_tiem.png", wait_after=3, retries=2, threshold=0.55):

            # 2. Tìm nút 3 Vàng bên trong
            if self.find_and_tap("btn_3_vang.png", wait_after=3, threshold=0.65):
                print("   > Đã nhận 3 vàng thành công!")
                # Có thể cần bấm OK nếu game hiện popup "Nhận thành công"
                # Nhưng thường tap ra ngoài là tắt hết.
            else:
                print("   > Không thấy gói 3 vàng có thể nhận (Đã nhận rồi?).")

            # 3. Thoát ra màn hình chính
            print("   > Thoát cửa tiệm...")
            self.device.tap(1, 1)
            time.sleep(1)
        else:
            print("   > Không tìm thấy Cửa Tiệm.")
