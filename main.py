from core.device import DeviceManager
from core.vision import VisionManager
from modules.builder import BuilderManager
from modules.daily_task import DailyTaskManager
import time


def main():
    # 1. Khởi tạo các bộ phận
    print("--- KHỞI ĐỘNG BOT ---")
    bot_device = DeviceManager()  # Cánh tay (Kết nối ADB)
    bot_eyes = VisionManager()  # Đôi mắt (Xử lý ảnh)

    # 2. Nạp module nghiệp vụ
    # Truyền tay và mắt vào cho module này sử dụng
    # daily = DailyTaskManager(bot_device, bot_eyes)

    # Chờ một chút cho mọi thứ ổn định
    # time.sleep(2)

    # 3. Chạy thử
    # Đảm bảo game đang ở màn hình chính
    # Test chức năng 1
    # daily.do_lucky_wheel()

    # Test chức năng 2
    # daily.claim_free_gold()

    # print("=== FINISHED ===")

    # Khởi tạo Builder
    builder = BuilderManager(bot_device, bot_eyes)

    # Trong vòng lặp chính (sau này):
    # builder.execute_upgrade_sequence()

    # Test thử ngay:
    builder.execute_sequence()


if __name__ == "__main__":
    main()