import subprocess
import time
from ppadb.client import Client as AdbClient
import cv2
import numpy as np
import io
from PIL import Image


class DeviceManager:
    def __init__(self, host="127.0.0.1", port=5555):
        self.host = host
        self.port = port
        self.start_adb_server()
        self.client = AdbClient(host="127.0.0.1", port=5037)  # Default ADB server port
        self.device = None
        self.connect()

    def start_adb_server(self):
        try:
            # Gọi lệnh start-server bằng đường dẫn tuyệt đối
            subprocess.run([self.adb_path, "start-server"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            print(f"Loi start server: {e}")

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

    def take_screenshot(self):
        """Chụp màn hình và trả về định dạng ảnh OpenCV (numpy array)"""
        if self.device:
            result = self.device.screencap()

            # Convert raw bytes thành ảnh
            image = Image.open(io.BytesIO(result))

            # Convert sang định dạng OpenCV (BGR) để xử lý sau này
            opencv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            return opencv_image
        return None

    def save_screenshot(self, filename="debug.png"):
        """Chụp và lưu file để kiểm tra"""
        img = self.take_screenshot()
        if img is not None:
            cv2.imwrite(filename, img)
            print(f"Đã lưu ảnh chụp màn hình tại: {filename}")