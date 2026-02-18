from core.device import DeviceManager
from core.vision import VisionManager
from modules.builder import BuilderManager
from modules.daily_task import DailyTaskManager
from modules.scene import SceneManager
from config.build_order import BUILD_SEQUENCE
import time


def main():
    print("--- KHỞI ĐỘNG SUPER BOT ---")
    device = DeviceManager()
    vision = VisionManager()

    # Khởi tạo các module
    builder = BuilderManager(device, vision)
    daily = DailyTaskManager(device, vision)
    scene = SceneManager(device, vision)

    # === BỘ NHỚ TRẠNG THÁI (STATE MEMORY) ===
    bot_state = {
        "build_index": 0,  # Đang xây đến công trình thứ mấy trong list
        "builder_free_time": .0,  # Thời điểm thợ xây sẽ rảnh (Unix timestamp)
        "next_spin_time": .0,  # Thời điểm được quay số tiếp theo
        "next_gold_time": .0,  # Thời điểm được nhận vàng tiếp theo
    }

    # === VÒNG LẶP VÔ TẬN (GAME LOOP) ===
    while True:
        print("\n--- CHECKING TASKS ---")

        # ---------------------------------------------------------
        # ƯU TIÊN 1: DAILY TASK (Làm nhanh rồi té)
        # ---------------------------------------------------------

        # 1. Vòng quay may mắn (10 phút 1 lần)
        if time.time() >= bot_state["next_spin_time"]:
            daily.do_lucky_wheel()
            # Cập nhật thời gian lần tới (10 phút = 600s)
            bot_state["next_spin_time"] = time.time() + 600
            print("   > Đã xong Spin. Hẹn gặp lại sau 10p.")
            continue  # Quay lại đầu vòng lặp để check ưu tiên lại

        # 2. Nhận vàng (24h 1 lần - demo để 1h)
        if time.time() >= bot_state["next_gold_time"]:
            daily.claim_free_gold()
            bot_state["next_gold_time"] = time.time() + 86400
            continue

        # ---------------------------------------------------------
        # ƯU TIÊN 2: XÂY DỰNG (BUILDER)
        # ---------------------------------------------------------
        # Chỉ làm nếu thợ đang rảnh
        if time.time() >= bot_state["builder_free_time"]:
            print(f"> Thợ đang rảnh. Kiểm tra mục tiêu số {bot_state['build_index']} trong list...")

            # Kiểm tra xem đã xây hết list chưa
            if bot_state["build_index"] < len(BUILD_SEQUENCE):
                task = BUILD_SEQUENCE[bot_state["build_index"]]

                # Vào thành để xây
                scene.go_to_city()

                # Gọi hàm xây dựng
                # Lưu ý: Hàm này cần trả về (True/False, build_time)
                target = task["target_lv"]
                name = task["name"]
                display = task["type_name"]

                if target == 1:
                    success, build_time = builder.build_new_structure(display)
                else:
                    success, build_time = builder.upgrade_existing_structure(name, target, display)

                if success:
                    print(f"   [DONE] Đã hoàn thành lệnh cho {display}. Chuyển sang mục tiêu tiếp theo.")
                    bot_state["build_index"] += 1  # Tăng index lên

                    # Sử dụng thời gian OCR được nếu có, nếu không thì dùng mặc định 300s
                    if build_time:
                        print(f"   [TIME] Thợ sẽ bận trong {build_time} giây (từ OCR)")
                        bot_state["builder_free_time"] = time.time() + build_time
                    else:
                        print(f"   [TIME] Không OCR được thời gian, dùng mặc định 300 giây")
                        bot_state["builder_free_time"] = time.time() + 300
                else:
                    print(f"   [SKIP/FAIL] Không thể nâng {display} (Thiếu tài nguyên hoặc đang xây/tăng cấp). "
                          f"Sẽ thử lại sau.")
                    # Nếu fail, ta chờ ngắn hơn (ví dụ 1 phút) rồi thử lại hoặc thử cái tiếp theo
                    bot_state["builder_free_time"] = time.time() + 60

                scene.leave_the_city()
            else:
                print(">>> ĐÃ XÂY HẾT DANH SÁCH BUILD_SEQUENCE!")

        else:
            wait_sec = int(bot_state["builder_free_time"] - time.time())
            print(f"> Thợ đang bận xây. Còn {wait_sec} giây nữa mới xong.")

        # ---------------------------------------------------------
        # IDLE: NGHỈ NGƠI
        # ---------------------------------------------------------
        print("> Không có việc gì làm. Ngủ 10 giây...")
        time.sleep(10)


if __name__ == "__main__":
    main()
