from core.device import DeviceManager
from core.debug_cleaner import DebugImageCleaner
from core.hard_dig import HardDigManager
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
import queue
from typing import Callable, Optional


def run_bot_loop(
    stop_event=None,
    pause_event=None,
    state_callback: Optional[Callable[[dict], None]] = None,
    map_prefer_existing=None,
    map_new_city_xy=None,
    command_queue=None,
):
    def _is_stopped():
        return stop_event is not None and stop_event.is_set()

    def _pause_gate():
        """Chặn vòng lặp khi pause được bật; trả True nếu nhận stop trong lúc pause."""
        while pause_event is not None and pause_event.is_set():
            if state_callback:
                state_callback({
                    **bot_state,
                    "engine_paused": True,
                    "ts": time.time(),
                })
            if _is_stopped():
                return True
            time.sleep(0.2)
        return False

    def _controlled_sleep(seconds):
        """Sleep có thể bị ngắt bởi pause/stop để phản hồi UI nhanh hơn."""
        end_ts = time.time() + max(0.0, float(seconds))
        while time.time() < end_ts:
            if _is_stopped():
                return True
            if _pause_gate():
                return True
            remain = end_ts - time.time()
            if remain <= 0:
                break
            time.sleep(min(0.2, remain))
        return _is_stopped()

    print("--- KHỞI ĐỘNG SUPER BOT NTA ---")
    # 1. Khởi tạo Bản đồ số ngay từ đầu (Tương tác qua Terminal)
    map_manager = MapManager()
    is_gui_mode = state_callback is not None
    prefer_existing = map_prefer_existing if map_prefer_existing is not None else (True if is_gui_mode else None)
    map_manager.load_or_create_map(
        interactive=not is_gui_mode,
        prefer_existing=prefer_existing,
        new_city_coords=map_new_city_xy,
    )

    device = DeviceManager()
    vision = VisionManager()
    terminal_cleaner = TerminalCleaner()
    debug_cleaner = DebugImageCleaner()
    hard_dig = HardDigManager()

    # Khởi tạo CaptchaSolver (template-driven spam strategy)
    print("--- KHỞI TẠO CAPTCHA SOLVER (SPAM ICON #1) ---")
    captcha_solver = CaptchaSolver()

    # Khởi tạo các module
    builder = BuilderManager(device, vision, captcha_solver)
    daily = DailyTaskManager(device, vision)
    scene = SceneManager(device, vision)
    combat = CombatManager(device, vision, map_manager, captcha_solver)
    hard_dig.consume_auto_start_request()

    # === BỘ NHỚ TRẠNG THÁI (STATE MEMORY) ===
    bot_state = {
        # Builder States
        "build_index": 0,
        "builder_free_time": .0,

        # Daily States
        "next_spin_time": .0,
        "next_gold_time": .0,

        # Combat States
        "combat_mode": "NORMAL",  # NORMAL | HARD_DIG
        "combat_status": "IDLE",  # IDLE, WAITING_RESULT, RETREATING
        "battle_finish_time": .0,
        "combat_cooldown": .0,  # Thời gian nghỉ sau mỗi trận
        "next_retreat_retry_time": .0,

        # Hard-Dig States
        "hard_dig_pending_activation": False,
        "hard_dig_inflight_target": None,
        "hard_dig_waiting_final_retreat": False,
        "hard_dig_retry_count": 0,
    }

    # === VÒNG LẶP VÔ TẬN (GAME LOOP) ===
    while True:
        if _is_stopped():
            print("[BOT] Nhận yêu cầu dừng từ GUI. Kết thúc vòng lặp chính.")
            break

        if _pause_gate():
            print("[BOT] Nhận yêu cầu dừng trong lúc pause. Kết thúc vòng lặp chính.")
            break

        if command_queue is not None:
            for _ in range(32):
                try:
                    cmd = command_queue.get_nowait()
                except queue.Empty:
                    break

                if not isinstance(cmd, dict):
                    continue

                ctype = str(cmd.get("type", "")).strip().upper()
                if ctype == "ACTIVATE_HARD_DIG":
                    hard_dig.request_activation("gui_button")
                    bot_state["hard_dig_pending_activation"] = True
                    print("[GUI-CMD] Đã nhận lệnh ACTIVATE_HARD_DIG.")
                elif ctype == "UPDATE_HARD_DIG_PLAN":
                    start_tile = cmd.get("start_tile", [300, 300])
                    targets = cmd.get("targets", [])
                    ok = hard_dig.update_plan(start_tile=start_tile, targets=targets, enabled=True)
                    if ok:
                        print(f"[GUI-CMD] Đã cập nhật hard-dig plan ({len(targets)} ô).")
                    else:
                        print("[GUI-CMD] Cập nhật hard-dig plan thất bại.")

        now = time.time()
        terminal_cleaner.maybe_clear(now)
        debug_cleaner.maybe_cleanup(now)
        if hard_dig.poll_hotkey_activation():
            bot_state["hard_dig_pending_activation"] = True

        if state_callback:
            state_callback({
                **bot_state,
                "engine_paused": False,
                "ts": now,
            })

        print("\n--- CHECKING TASKS ---")

        if hard_dig.has_activation_request():
            bot_state["hard_dig_pending_activation"] = True

        # Hard-Dig chỉ takeover sau khi combat thường hoàn tất vòng hiện tại và trở về IDLE.
        if bot_state["hard_dig_pending_activation"] and bot_state["combat_mode"] == "NORMAL":
            if bot_state["combat_status"] == "IDLE":
                prepared = hard_dig.prepare_run(combat)
                if prepared.get("status") == "READY":
                    bot_state["combat_mode"] = "HARD_DIG"
                    bot_state["hard_dig_pending_activation"] = False
                    bot_state["hard_dig_inflight_target"] = None
                    bot_state["hard_dig_waiting_final_retreat"] = False
                    print(f"> [HARD-DIG] Kích hoạt thành công. Tiến độ: {hard_dig.progress_text()}")
                else:
                    bot_state["hard_dig_pending_activation"] = False
                    hard_dig.clear_activation_request()
                    print(f"> [HARD-DIG] Không thể kích hoạt: {prepared.get('reason', 'prepare_failed')}")
            else:
                print(
                    f"> [HARD-DIG] Đang chờ combat thường hoàn tất (status={bot_state['combat_status']}) trước khi takeover."
                )

        # =========================================================
        # ƯU TIÊN 1: CHIẾN ĐẤU (DIG) - LOGIC PHỨC TẠP NHẤT
        # =========================================================
        if _pause_gate():
            print("[BOT] Dừng trong lúc chờ trước task combat.")
            break


        # Case 1: Đang rảnh và hết thời gian hồi chiêu -> Đi tìm đất
        if bot_state["combat_status"] == "IDLE":
            if time.time() >= bot_state["combat_cooldown"]:
                if bot_state["combat_mode"] == "HARD_DIG":
                    current_target = hard_dig.current_target()
                    if not current_target:
                        print("> [HARD-DIG] Đã xử lý hết danh sách target. Chuyển sang rút quân về thành chính...")
                        bot_state["combat_status"] = "RETREATING"
                        bot_state["hard_dig_waiting_final_retreat"] = True
                        bot_state["next_retreat_retry_time"] = time.time()
                        dig_result = {"status": "NO_TARGET"}
                    else:
                        print(
                            f"> [HARD-DIG] Đánh target {hard_dig.progress_text()} -> "
                            f"({current_target['x']},{current_target['y']})"
                        )
                        dig_result = combat.dispatch_hard_dig_target(current_target)
                        bot_state["hard_dig_inflight_target"] = current_target
                else:
                    print("> [COMBAT] Đang rảnh. Ra map tìm đất hoang...")
                    dig_result = combat.scan_and_dig()
                dig_status = dig_result.get("status") if isinstance(dig_result, dict) else ("SUCCESS" if dig_result else "NO_TARGET")

                if dig_status == "SUCCESS":
                    predicted_wait = int(dig_result.get("predicted_wait", 0))
                    print("   > Đã xuất quân! Chuyển trạng thái: CHỜ KẾT QUẢ")
                    bot_state["combat_status"] = "WAITING_RESULT"
                    bot_state["battle_finish_time"] = time.time() + predicted_wait
                    if bot_state["combat_mode"] == "HARD_DIG":
                        bot_state["hard_dig_retry_count"] = 0
                    print(f"   > Thời gian chờ dự đoán trận đánh: {predicted_wait}s")
                elif dig_status == "FATAL":
                    print("   > [COMBAT] Gặp lỗi nghiêm trọng khi xử lý combat. Nghỉ 60s rồi thử lại.")
                    bot_state["combat_cooldown"] = time.time() + 60
                    if bot_state["combat_mode"] == "HARD_DIG":
                        hard_dig.mark_error("fatal_dispatch")
                elif dig_status == "INTERRUPTED":
                    print("   > [COMBAT] Bị ngắt bởi Captcha. Thử lại sớm.")
                    bot_state["combat_cooldown"] = time.time() + 3
                else:
                    if bot_state["combat_mode"] == "HARD_DIG":
                        bot_state["hard_dig_inflight_target"] = None

                        # Hard-Dig: không bỏ qua ô khi dispatch/tick lỗi, luôn retry sau một khoảng nghỉ.
                        bot_state["hard_dig_retry_count"] = int(bot_state.get("hard_dig_retry_count", 0)) + 1
                        retry_idx = bot_state["hard_dig_retry_count"]
                        retry_wait = min(60, 5 + retry_idx * 5)
                        bot_state["combat_cooldown"] = time.time() + retry_wait

                        target = hard_dig.current_target()
                        if target:
                            print(
                                f"   > [HARD-DIG] Dispatch lỗi ({dig_status}) tại ({target['x']},{target['y']}). "
                                f"Sẽ thử lại sau {retry_wait}s (retry #{retry_idx})."
                            )
                        else:
                            print(
                                f"   > [HARD-DIG] Dispatch lỗi ({dig_status}). "
                                f"Sẽ thử lại sau {retry_wait}s (retry #{retry_idx})."
                            )
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
                if bot_state["combat_mode"] == "HARD_DIG":
                    inflight = bot_state.get("hard_dig_inflight_target")
                    if inflight:
                        hard_dig.mark_target_completed(inflight)
                        bot_state["hard_dig_inflight_target"] = None

                    if hard_dig.is_finished():
                        print("   [HARD-DIG] Đã xong toàn bộ target. Chuyển sang rút quân về thành chính.")
                        bot_state["combat_status"] = "RETREATING"
                        bot_state["hard_dig_waiting_final_retreat"] = True
                        bot_state["next_retreat_retry_time"] = time.time()
                    else:
                        print(f"   [HARD-DIG] Hoàn thành 1 target. Tiếp tục target kế tiếp ({hard_dig.progress_text()}).")
                        bot_state["hard_dig_retry_count"] = 0
                        bot_state["combat_status"] = "IDLE"
                        bot_state["combat_cooldown"] = time.time()
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

                    if bot_state["combat_mode"] == "HARD_DIG" and bot_state["hard_dig_waiting_final_retreat"]:
                        hard_dig.finish_run()
                        bot_state["combat_mode"] = "NORMAL"
                        bot_state["hard_dig_waiting_final_retreat"] = False
                        bot_state["hard_dig_inflight_target"] = None
                        bot_state["hard_dig_retry_count"] = 0
                        print("> [HARD-DIG] Hoàn tất phiên hard-dig. Combat-dig thường đã được bật lại.")
                elif retreat_status == "INTERRUPTED":
                    print("   [RETRY] Retreat bị ngắt do Captcha. Thử lại sau 5s.")
                    bot_state["next_retreat_retry_time"] = time.time() + 5
                elif retreat_status == "FATAL":
                    print("   [FATAL] Retreat gặp lỗi nghiêm trọng. Lùi 60s trước khi thử lại.")
                    bot_state["next_retreat_retry_time"] = time.time() + 60
                    if bot_state["combat_mode"] == "HARD_DIG":
                        hard_dig.mark_error("fatal_retreat")
                else:
                    print("   [RETRY] Rút quân lỗi. Thử lại sau 10s.")
                    bot_state["next_retreat_retry_time"] = time.time() + 10
            else:
                wait_retreat = int(bot_state["next_retreat_retry_time"] - time.time())
                print(f"> [RETREAT] Đang chờ retry rút quân ({wait_retreat}s)")

        # =========================================================
        # ƯU TIÊN 2: DAILY TASK (Cho phép chạy cả khi đang chờ combat/retreat)
        # =========================================================
        if _pause_gate():
            print("[BOT] Dừng trong lúc chờ trước task daily.")
            break

        # 1. Vòng quay
        if time.time() >= bot_state["next_spin_time"]:
            daily.do_lucky_wheel()
            bot_state["next_spin_time"] = time.time() + 600
            if state_callback:
                state_callback({**bot_state, "engine_paused": False, "ts": time.time()})
            continue

        # 2. Nhận vàng
        if time.time() >= bot_state["next_gold_time"]:
            daily.claim_free_gold()
            bot_state["next_gold_time"] = time.time() + 3600
            if state_callback:
                state_callback({**bot_state, "engine_paused": False, "ts": time.time()})
            continue

        # =========================================================
        # ƯU TIÊN 3: XÂY DỰNG (BUILDER)
        # =========================================================
        if _pause_gate():
            print("[BOT] Dừng trong lúc chờ trước task builder.")
            break

        # Theo logic mới: Build có thể chạy song song khi đang chờ combat/retreat
        if time.time() >= bot_state["builder_free_time"]:
            if bot_state["build_index"] < len(BUILD_SEQUENCE):
                # Vào thành
                scene.go_to_city()

                # Chỉ rời thành khi đã tìm được tác vụ build/upgrade thực sự hoặc gặp lỗi.
                while bot_state["build_index"] < len(BUILD_SEQUENCE):
                    if _pause_gate():
                        print("[BOT] Dừng trong lúc pause ở vòng builder.")
                        break

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
        if _controlled_sleep(5):
            print("[BOT] Kết thúc vòng lặp do stop trong lúc sleep.")
            break


def main():
    run_bot_loop()


if __name__ == "__main__":
    main()
