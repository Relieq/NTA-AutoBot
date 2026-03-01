from core.device import DeviceManager
from core.vision import VisionManager
from modules.builder import BuilderManager
from modules.captcha import CaptchaSolver
from modules.daily_task import DailyTaskManager
from modules.scene import SceneManager
from modules.combat import CombatManager
from config.build_order import BUILD_SEQUENCE
import time


def main():
    print("--- KHỞI ĐỘNG SUPER BOT NTA ---")
    device = DeviceManager()
    vision = VisionManager()

    # Khởi tạo CaptchaSolver (Load model ONNX vào RAM 1 lần duy nhất)
    print("--- ĐANG TẢI MODEL AI GIẢI CAPTCHA ---")
    captcha_solver = CaptchaSolver()

    # Khởi tạo các module
    builder = BuilderManager(device, vision, captcha_solver)
    daily = DailyTaskManager(device, vision)
    scene = SceneManager(device, vision)
    combat = CombatManager(device, vision, captcha_solver)

    # === BỘ NHỚ TRẠNG THÁI (STATE MEMORY) ===
    bot_state = {
        # Builder States
        "build_index": 0,
        "builder_free_time": .0,

        # Daily States
        "next_spin_time": .0,
        "next_gold_time": .0,

        # Combat States
        "combat_status": "IDLE",  # IDLE, WAITING_RESULT, RETREATING
        "battle_start_time": .0,
        "combat_cooldown": .0,  # Thời gian nghỉ sau mỗi trận
    }

    # === VÒNG LẶP VÔ TẬN (GAME LOOP) ===
    while True:
        print("\n--- CHECKING TASKS ---")

        # =========================================================
        # ƯU TIÊN 1: CHIẾN ĐẤU (DIG) - LOGIC PHỨC TẠP NHẤT
        # =========================================================

        # Case 1: Đang rảnh và hết thời gian hồi chiêu -> Đi tìm đất
        if bot_state["combat_status"] == "IDLE":
            if time.time() >= bot_state["combat_cooldown"]:
                print("> [COMBAT] Đang rảnh. Ra map tìm đất hoang...")

                # Gọi hàm tấn công
                has_attacked = combat.scan_and_dig()

                if has_attacked:
                    print("   > Đã xuất quân! Chuyển trạng thái: CHỜ KẾT QUẢ")
                    bot_state["combat_status"] = "WAITING_RESULT"
                    bot_state["battle_start_time"] = time.time()
                else:
                    print("   > Không tìm thấy đất ngon. Nghỉ 5 phút.")
                    bot_state["combat_cooldown"] = time.time() + 300
            else:
                wait = int(bot_state["combat_cooldown"] - time.time())
                print(f"> [COMBAT] Đang nghỉ ngơi hồi sức (Còn {wait}s)")

        # Case 2: Đang chờ kết quả chiến đấu (Max 12 phút)
        elif bot_state["combat_status"] == "WAITING_RESULT":
            elapsed = time.time() - bot_state["battle_start_time"]
            print(f"> [COMBAT] Đang chờ quân đánh... ({int(elapsed)}s)")

            # Logic kiểm tra chiến thắng:
            # Vì ta không lưu tọa độ đất (do map trôi), ta dùng cơ chế timeout
            # Hoặc quét toàn màn hình tìm icon Mũ Giáp (nếu camera chưa di chuyển)

            # Ở đây dùng logic đơn giản như bạn yêu cầu:
            # Chờ 10 phút (600s) cho chắc chắn thắng
            if elapsed > 180:
                print("   [INFO] Đã hết thời gian chờ (10p). Giả định đã thắng/thua xong.")
                bot_state["combat_status"] = "RETREATING"

            # Trong lúc chờ đánh nhau, bot có thể làm việc khác (như check daily) 
            # nhưng hạn chế chuyển cảnh để tránh lỗi map. Tạm thời cho bot đứng im chờ.
            # time.sleep(10)
            # continue

            # Case 3: Rút quân về hồi máu
        elif bot_state["combat_status"] == "RETREATING":
            if combat.retreat_troops_logic():
                print("   [FINISH] Hoàn thành quy trình Dig.")
                bot_state["combat_status"] = "IDLE"
                # Nghỉ 5 phút để hồi máu lính
                bot_state["combat_cooldown"] = time.time() + 300
            else:
                print("   [RETRY] Rút quân lỗi. Thử lại sau 10s.")
                time.sleep(10)

        # =========================================================
        # ƯU TIÊN 2: DAILY TASK (Chỉ làm khi Combat đang IDLE hoặc Cooldown)
        # =========================================================

        if bot_state["combat_status"] == "IDLE":
            # 1. Vòng quay
            if time.time() >= bot_state["next_spin_time"]:
                daily.do_lucky_wheel()
                bot_state["next_spin_time"] = time.time() + 600
                continue

            # 2. Nhận vàng
            if time.time() >= bot_state["next_gold_time"]:
                daily.claim_free_gold()
                bot_state["next_gold_time"] = time.time() + 3600
                continue

        # =========================================================
        # ƯU TIÊN 3: XÂY DỰNG (BUILDER)
        # =========================================================

        # Chỉ xây khi Combat IDLE (để tránh xung đột màn hình Thành/Map)
        if bot_state["combat_status"] == "IDLE" and time.time() >= bot_state["builder_free_time"]:
            if bot_state["build_index"] < len(BUILD_SEQUENCE):
                task = BUILD_SEQUENCE[bot_state["build_index"]]

                # Vào thành
                scene.go_to_city()

                # Thực hiện xây
                target = task["target_lv"]
                name = task["name"]
                display = task["type_name"]

                if target == 1:
                    success, b_time = builder.build_new_structure(display)
                else:
                    success, b_time = builder.upgrade_existing_structure(name, target, display)

                if success:
                    bot_state["build_index"] += 1
                    wait_time = b_time if b_time else 300
                    bot_state["builder_free_time"] = time.time() + wait_time
                else:
                    # Fail thì thử lại sau 60s
                    bot_state["builder_free_time"] = time.time() + 60

                # Xây xong ra map đứng cho tiện combat
                scene.leave_the_city()
            else:
                print(">>> ĐÃ XÂY HẾT LIST.")

        # Nghỉ ngơi chung
        print("> Bot ngủ 5 giây...")
        time.sleep(5)


if __name__ == "__main__":
    main()
