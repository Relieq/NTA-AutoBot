import subprocess
import time
import os
import sys
from ppadb.client import Client as AdbClient
import cv2
import numpy as np
import io
from PIL import Image


class DeviceManager:
    def __init__(self, host="127.0.0.1", port=5555):
        self.host = host
        self.port = port
        self.adb_cmd = self._resolve_adb_command()
        self.start_adb_server()
        self.client = AdbClient(host="127.0.0.1", port=5037)  # Default ADB server port
        self.device = None
        self.connect()

    def _resolve_adb_command(self):
        """Ưu tiên adb bundled (source / dist root / PyInstaller _internal), fallback về PATH."""
        return self.resolve_adb_command_for_current_process()

    @staticmethod
    def resolve_adb_command_for_current_process():
        """Resolve adb path cho process hiện tại (dùng được cả khi chưa tạo DeviceManager instance)."""
        candidates = []

        cwd_root = os.getcwd()
        candidates.append(os.path.abspath(os.path.join(cwd_root, "third_party", "platform-tools", "adb.exe")))
        candidates.append(os.path.abspath(os.path.join(cwd_root, "_internal", "third_party", "platform-tools", "adb.exe")))

        if getattr(sys, "frozen", False):
            exe_root = os.path.dirname(sys.executable)
            candidates.append(os.path.abspath(os.path.join(exe_root, "third_party", "platform-tools", "adb.exe")))
            candidates.append(os.path.abspath(os.path.join(exe_root, "_internal", "third_party", "platform-tools", "adb.exe")))
            meipass = getattr(sys, "_MEIPASS", "")
            if meipass:
                candidates.append(os.path.abspath(os.path.join(meipass, "third_party", "platform-tools", "adb.exe")))

        for bundled in candidates:
            if os.path.exists(bundled):
                print(f"[ADB] Dùng adb bundled: {bundled}")
                return bundled

        print("[ADB] Không thấy adb bundled, fallback dùng adb từ PATH.")
        return "adb"

    def start_adb_server(self):
        try:
            # Gọi lệnh start-server bằng adb bundled/PATH đã resolve
            subprocess.run([self.adb_cmd, "start-server"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            print(f"Loi start server: {e}")

    @staticmethod
    def stop_adb_server_global():
        """Dừng adb server theo cùng cơ chế resolve path, dùng cho cleanup khi thoát/terminate."""
        adb_cmd = DeviceManager.resolve_adb_command_for_current_process()
        try:
            subprocess.run([adb_cmd, "kill-server"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"[ADB] Đã dừng adb server bằng: {adb_cmd}")
        except Exception as e:
            print(f"[ADB-WARN] Không thể dừng adb server: {e}")

    def stop_adb_server(self):
        self.stop_adb_server_global()

    def connect(self):
        try:
            # Thử kết nối tới giả lập
            print(f"Đang kết nối tới BlueStacks {self.host}:{self.port}...")
            self.client.remote_connect(self.host, self.port)
            self.device = self.client.device(f"{self.host}:{self.port}")

            if self.device:
                print(">>> Kết nối thành công!")
            else:
                print("!!! Không tìm thấy thiết bị. Hãy kiểm tra, mở lại BlueStacks.")
        except Exception as e:
            print(f"Lỗi kết nối: {e}")

    def tap(self, x, y):
        """Gửi lệnh chạm vào tọa độ (x, y)"""
        if self.device:
            self.device.shell(f"input tap {x} {y}")
            time.sleep(0.5)  # Delay nhỏ để game kịp phản hồi

    def swipe(self, x1, y1, x2, y2, duration=500):
        """Vuốt từ (x1, y1) đến (x2, y2)"""
        if self.device:
            self.device.shell(f"input swipe {x1} {y1} {x2} {y2} {duration}")
            time.sleep(1)

    def precise_drag(self, start_x, start_y, end_x, end_y, duration = 1500):
        """
        Kéo thả chậm để không gây ra quán tính (Inertia).
        Giúp map dừng lại chính xác tại điểm thả tay.
        """
        # Thời gian kéo dài (ví dụ 1000ms - 2000ms) giúp loại bỏ đà trôi
        cmd = f"input swipe {start_x} {start_y} {end_x} {end_y} {duration}"
        if self.device:
            self.device.shell(cmd)
            # Chờ thêm chút xíu cho game render lại khung hình
            time.sleep(0.5)

    def send_keyevent(self, keycode):
        """Gửi phím cứng Android (vd: 67 là Backspace, 66 là Enter)"""
        if self.device:
            self.device.shell(f"input keyevent {keycode}")

    def input_text(self, text):
        """Nhập văn bản"""
        if self.device:
            self.device.shell(f"input text {text}")

    def take_screenshot(self):
        """Chụp màn hình và trả về định dạng ảnh OpenCV (numpy array)"""
        if self.device:
            try:
                result = self.device.screencap()
                image = Image.open(io.BytesIO(result))
                opencv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
                return opencv_image
            except Exception as e:
                print(f"[ADB-WARN] Screencap lỗi: {e}. Đang thử reconnect 1 lần...")
                try:
                    self.connect()
                except Exception:
                    pass

                if self.device:
                    try:
                        result = self.device.screencap()
                        image = Image.open(io.BytesIO(result))
                        opencv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
                        return opencv_image
                    except Exception as e2:
                        print(f"[ADB-ERR] Screencap thất bại sau reconnect: {e2}")
        return None

    def save_screenshot(self, filename="debug.png"):
        """Chụp và lưu file để kiểm tra"""
        img = self.take_screenshot()
        if img is not None:
            cv2.imwrite(filename, img)
            print(f"Đã lưu ảnh chụp màn hình tại: {filename}")