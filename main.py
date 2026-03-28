from core.device import DeviceManager
from core.debug_cleaner import DebugImageCleaner
from core.map_core import MapManager
from core.terminal import TerminalCleaner
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
    # 1. Khởi tạo Bản đồ số ngay từ đầu (Tương tác qua Terminal)
    map_manager = MapManager()
    map_manager.load_or_create_map()

    device = DeviceManager()
    vision = VisionManager()
    terminal_cleaner = TerminalCleaner()
    debug_cleaner = DebugImageCleaner()

    # Khởi tạo CaptchaSolver (template-driven spam strategy)
    print("--- KHỞI TẠO CAPTCHA SOLVER (SPAM ICON #1) ---")
    captcha_solver = CaptchaSolver()

    # Khởi tạo các module
    builder = BuilderManager(device, vision, captcha_solver)
    daily = DailyTaskManager(device, vision)
    scene = SceneManager(device, vision)
    combat = CombatManager(device, vision, map_manager, captcha_solver)

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
        "battle_finish_time": .0,
        "combat_cooldown": .0,  # Thời gian nghỉ sau mỗi trận
        "next_retreat_retry_time": .0,
    }

    # === VÒNG LẶP VÔ TẬN (GAME LOOP) ===
    while True:
        now = time.time()
        terminal_cleaner.maybe_clear(now)
        debug_cleaner.maybe_cleanup(now)
        print("\n--- CHECKING TASKS ---")

        # =========================================================
        # ƯU TIÊN 1: CHIẾN ĐẤU (DIG) - LOGIC PHỨC TẠP NHẤT
        # =========================================================


        # Case 1: Đang rảnh và hết thời gian hồi chiêu -> Đi tìm đất
        if bot_state["combat_status"] == "IDLE":
            if time.time() >= bot_state["combat_cooldown"]:
                print("> [COMBAT] Đang rảnh. Ra map tìm đất hoang...")

                # Gọi hàm tấn công
                dig_result = combat.scan_and_dig()
                dig_status = dig_result.get("status") if isinstance(dig_result, dict) else ("SUCCESS" if dig_result else "NO_TARGET")

                if dig_status == "SUCCESS":
                    predicted_wait = int(dig_result.get("predicted_wait", 0))
                    print("   > Đã xuất quân! Chuyển trạng thái: CHỜ KẾT QUẢ")
                    bot_state["combat_status"] = "WAITING_RESULT"
                    bot_state["battle_finish_time"] = time.time() + predicted_wait
                    print(f"   > Thời gian chờ dự đoán trận đánh: {predicted_wait}s")
                elif dig_status == "FATAL":
                    print("   > [COMBAT] Gặp lỗi nghiêm trọng khi xử lý combat. Nghỉ 60s rồi thử lại.")
                    bot_state["combat_cooldown"] = time.time() + 60
                else:
                    print("   > Không tìm thấy đất ngon. Nghỉ 5 phút.")
                    bot_state["combat_cooldown"] = time.time() + 300
            else:
                wait = int(bot_state["combat_cooldown"] - time.time())
                print(f"> [COMBAT] Đang nghỉ ngơi hồi sức (Còn {wait}s)")

        # Case 2: Đang chờ kết quả chiến đấu theo thời gian dự đoán
        elif bot_state["combat_status"] == "WAITING_RESULT":
            remain = int(bot_state["battle_finish_time"] - time.time())
            if remain > 0:
                print(f"> [COMBAT] Đang chờ quân đánh... (Còn {remain}s)")
            else:
                print("   [INFO] Hết thời gian chờ dự đoán. Chuyển sang rút quân.")
                bot_state["combat_status"] = "RETREATING"
                bot_state["next_retreat_retry_time"] = time.time()

        # Case 3: Rút quân về thành chính
        elif bot_state["combat_status"] == "RETREATING":
            if time.time() >= bot_state["next_retreat_retry_time"]:
                retreat_result = combat.retreat_troops_logic()
                retreat_status = retreat_result.get("status") if isinstance(retreat_result, dict) else ("SUCCESS" if retreat_result else "FAILED")

                if retreat_status == "SUCCESS":
                    print("   [FINISH] Hoàn thành quy trình Dig.")
                    bot_state["combat_status"] = "IDLE"
                    # Theo logic mới: chờ đúng bằng TG hành quân lớn nhất khi rút quân (không cộng hồi máu)
                    retreat_wait = int(retreat_result.get("max_travel_time", 0)) if isinstance(retreat_result, dict) else 0
                    bot_state["combat_cooldown"] = time.time() + retreat_wait
                    print(f"   [COMBAT] Cooldown sau retreat: {retreat_wait}s")
                elif retreat_status == "INTERRUPTED":
                    print("   [RETRY] Retreat bị ngắt do Captcha. Thử lại sau 5s.")
                    bot_state["next_retreat_retry_time"] = time.time() + 5
                elif retreat_status == "FATAL":
                    print("   [FATAL] Retreat gặp lỗi nghiêm trọng. Lùi 60s trước khi thử lại.")
                    bot_state["next_retreat_retry_time"] = time.time() + 60
                else:
                    print("   [RETRY] Rút quân lỗi. Thử lại sau 10s.")
                    bot_state["next_retreat_retry_time"] = time.time() + 10
            else:
                wait_retreat = int(bot_state["next_retreat_retry_time"] - time.time())
                print(f"> [RETREAT] Đang chờ retry rút quân ({wait_retreat}s)")

        # =========================================================
        # ƯU TIÊN 2: DAILY TASK (Cho phép chạy cả khi đang chờ combat/retreat)
        # =========================================================

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

        # Theo logic mới: Build có thể chạy song song khi đang chờ combat/retreat
        if time.time() >= bot_state["builder_free_time"]:
            if bot_state["build_index"] < len(BUILD_SEQUENCE):
                # Vào thành
                scene.go_to_city()

                # Chỉ rời thành khi đã tìm được tác vụ build/upgrade thực sự hoặc gặp lỗi.
                while bot_state["build_index"] < len(BUILD_SEQUENCE):
                    task = BUILD_SEQUENCE[bot_state["build_index"]]

                    target = task["target_lv"]
                    name = task["name"]
                    display = task["type_name"]

                    if target == 1:
                        result = builder.build_new_structure(display)
                    else:
                        result = builder.upgrade_existing_structure(name, target, display)

                    status = result.get("status", "FAILED") if isinstance(result, dict) else "FAILED"
                    wait_time = result.get("wait_time") if isinstance(result, dict) else None

                    if status == "SUCCESS":
                        bot_state["build_index"] += 1
                        bot_state["builder_free_time"] = time.time() + (wait_time if wait_time else 300)
                        break

                    if status == "SKIPPED_ALREADY_DONE":
                        bot_state["build_index"] += 1
                        # Không set cooldown giả; tiếp tục ngay task kế tiếp trong thành.
                        continue

                    # FAILED/FATAL thì lùi 60s rồi thử lại từ task hiện tại.
                    bot_state["builder_free_time"] = time.time() + 60
                    break

                # Xây xong ra map đứng cho tiện combat
                scene.leave_the_city()
            else:
                print(">>> ĐÃ XÂY HẾT LIST.")

        # Nghỉ ngơi chung
        print("> Bot ngủ 5 giây...")
        time.sleep(5)


if __name__ == "__main__":
    main()
