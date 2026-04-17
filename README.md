# NTA-AutoBot

<center>

![mô tả ảnh](images/NTA_logo.jpg)

</center>

Bot tự động cho game Android theo hướng nhận diện ảnh (OpenCV + OCR), chạy qua BlueStacks + ADB, không dùng API game.

## 1) Tổng quan nhanh
- Luồng chính: `Combat -> DailyTask -> Builder` (vòng lặp vô tận trong `main.py`).
- Có GUI desktop (`gui_app.py`) để chạy bot, theo dõi log/state, cấu hình, và lập kế hoạch Hard-Dig.
- Captcha dùng chiến lược thực dụng: spam chọn icon #1 + kiểm tra captcha còn hay không.
- Hệ thống template matching đã có profile theo từng nút (`config/template_profiles.json`).
- Builder hỗ trợ danh sách build động với điểm bắt đầu cấu hình bằng `start_index` (không cần comment thủ công).

## 2) Kiến trúc project
- `main.py`: khởi tạo manager, chạy state machine task, hỗ trợ pause/resume/stop từ GUI.
- `core/device.py`: quản lý ADB, tap/swipe/drag/screenshot, ưu tiên dùng adb bundled.
- `core/vision.py`: template matching đa scale, đa kênh (color/gray/edge), nạp profile threshold.
- `core/map_core.py`: bản đồ số, cache tile info (state, difficulty, distance...), lưu `data/map_data.json`.
- `core/hard_dig.py`: trạng thái và kế hoạch hard-dig runtime.
- `core/gui_app.py`: giao diện chính + cửa sổ Hard-Dig Planner + cửa sổ Config Editor.
- `core/gui_bridge.py`: chạy bot ở process riêng và stream log/state về GUI.
- `modules/combat.py`: scan target, OCR độ khó, dispatch/retreat, timing combat, hard-dig dispatch.
- `modules/builder.py`: build/upgrade, OCR level/time/tên công trình, bỏ qua tác vụ đã hoàn thành.
- `modules/daily_task.py`: vòng quay may mắn định kỳ.
- `modules/captcha.py`: detect captcha và giải theo luồng spam icon #1.

## 3) Yêu cầu môi trường
- Windows (PowerShell), BlueStacks đang chạy.
- Python 3.12+.
- Đủ CPU/RAM cho OpenCV + OCR (PaddleOCR/EasyOCR/Torch).
- Nếu đóng gói: có `third_party/platform-tools/adb.exe` để bundle ADB.

<center>

![Android_Debug_Bridge.jpg](images/Android_Debug_Bridge.jpg)
*Bật Android Debug Bridge*

</center>

## 4) Cài đặt từ source
```powershell
cd "D:\PyCharm\Project\NTA-AutoBot"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 5) Cách chạy bot

### 5.1 Chạy bằng GUI (khuyến nghị)
```powershell
cd "D:\PyCharm\Project\NTA-AutoBot"
.\.venv\Scripts\Activate.ps1
python gui_app.py
```

### 5.2 Chạy bằng CLI
```powershell
cd "D:\PyCharm\Project\NTA-AutoBot"
.\.venv\Scripts\Activate.ps1
python main.py
```

## 6) Hướng dẫn sử dụng GUI

### 6.1 Cửa sổ chính

<center>

![GUI_main.png](images/GUI_main.png)

</center>

- Chọn `Dùng map cũ` hoặc `Tạo map mới` + nhập `X/Y`.
- Thiết lập bắt buộc lần đầu: trước khi chạy bot, cần cấu hình `build_order_runtime.json` trong Config Editor và bấm `Save`.
- `Start`: chạy bot process.
- `Pause` / `Resume`: tạm dừng / tiếp tục theo cơ chế cooperative.
- `Stop`: dừng mềm, quá timeout sẽ terminate process.
- `Live Log`: hiển thị stdout/stderr/runtime state.
- Nút `?` góc trên phải: xem hướng dẫn nhanh của cửa sổ chính.

### 6.2 Hard-Dig Planner (cửa sổ riêng)

<center>

![GUI_hard_dig.png](images/GUI_hard_dig.png)

</center>

- Mở bằng `Open Hard-Dig Planner`.
- Chế độ thao tác:
  - `Tô màu`: chọn ô mục tiêu.
  - `Xóa`: bỏ chọn.
  - `Chọn ô bắt đầu`: chọn ô đầu tiên trong chuỗi hard-dig.
- Hỗ trợ map:
  - Zoom +/-.
  - Trục tọa độ + tooltip tọa độ.
  - Overlay trạng thái từ `data/map_data.json` (`Reload map_data`).
- Lưu và kích hoạt:
  - `Lưu plan Hard-Dig` -> ghi `config/hard_dig_plan.json`.
  - `Kích hoạt Hard-Dig` -> gửi command runtime.
- Nút `?` góc trên phải: xem hướng dẫn riêng cho Hard-Dig Planner.

### 6.3 Config Editor (cửa sổ riêng)

<center>

![GUI_config_editor.png](images/GUI_config_editor.png)

</center>

- Mở bằng `Open Config Editor`.
- Chọn file config trong dropdown, bấm `Load`.
- Có 2 chế độ:
  - Friendly (form): chỉnh nhanh các trường phổ biến.
  - Advanced JSON: chỉnh trực tiếp file JSON.
- `Save`: ghi file an toàn + backup `.bak_YYYYMMDD_HHMMSS`.
- Nút `?` góc trên phải: xem hướng dẫn riêng cho Config Editor.

## 7) Cấu hình quan trọng
- `config/runtime.json`: dọn terminal và ảnh debug theo chu kỳ.
- `config/template_profiles.json`: threshold/scale/weights theo từng template.
- `config/combat_timing.json`: thời gian chiến đấu theo từng dải độ khó.
- `config/combat_difficulty_blacklist.json`: bật/tắt blacklist theo tier/level.
- `config/combat_first_dispatch_status.json`: đánh dấu popup cảnh báo độ khó lần đầu theo tier.
- `config/hard_dig_plan.json`: kế hoạch hard-dig.
- `config/build_order.py`: danh sách gốc `BUILD_SEQUENCE`.
- `config/build_order_runtime.json`: điểm bắt đầu builder (`start_index`).

Khi bot khởi động, log sẽ in mục `[CONFIG] Runtime config paths` để bạn kiểm tra chính xác file config nào đang được load (rất hữu ích khi chạy bản đóng gói `.exe`).

`runtime.json` cũng hỗ trợ dọn file backup config `.bak`:
- `config_backup_enabled`: bật/tắt dọn backup tự động.
- `config_backup_keep_count`: giữ tối đa N bản backup mới nhất cho mỗi file config.
- `config_backup_keep_days`: chỉ giữ backup cũ trong tối đa X ngày.

### 7.1 Chọn điểm bắt đầu Builder
- Trong Config Editor, chọn `build_order_runtime.json`.
- Dùng Step Picker (danh sách nút “Bước X: ...”) để bấm chọn điểm bắt đầu.
- Giá trị lưu dưới dạng `start_index` (0-based).

Từ bản `v1.1.1`, GUI áp dụng cơ chế bảo vệ khởi tạo:
- `Start` sẽ bị khóa cho đến khi file `build_order_runtime.json` có `initial_setup_done = true`.
- Khi mở tool lần đầu và chưa setup, GUI sẽ tự mở `Config Editor` đúng file `build_order_runtime.json`.
- Sau khi bấm `Save` trong Config Editor, hệ thống tự ghi `initial_setup_done = true` và mở khóa `Start`.

Lưu ý bản đóng gói (`.exe`): bot ưu tiên đọc file runtime người dùng chỉnh ở `config/build_order_runtime.json` (ngoài thư mục bundle nội bộ), nên thay đổi `start_index` sẽ có hiệu lực đúng như khi chạy source.

## 8) Captcha (trạng thái hiện tại)
- Không dùng model phân loại captcha.
- Luồng xử lý:
  1) Detect captcha bằng `assets/title_captcha.png`.
  2) Nếu còn `btn_ok_captcha`, bot chọn icon #1 rồi bấm OK.
  3) Kiểm tra lại, lặp đến khi captcha biến mất hoặc hết lượt thử.

<center>

![captcha_test_assets_captcha.png](images/captcha_test_assets_captcha.png)

</center>

## 9) Debug và hiệu chỉnh

### 9.1 Vision
```powershell
$env:VISION_DEBUG = "1"
python main.py
```
Ảnh ở `debug_img/vision`.

### 9.2 Combat
```powershell
$env:COMBAT_DEBUG = "1"
python main.py
```
Ảnh ở `debug_img/combat`.

### 9.3 Builder
```powershell
$env:BUILDER_DEBUG = "1"
python main.py
```
Ảnh ở `debug_img/builder`.

### 9.4 Captcha
```powershell
$env:CAPTCHA_DEBUG = "1"
python main.py
```
Ảnh ở `debug_img/captcha/spam`.

## 10) Đóng gói ứng dụng

### 10.1 Build bằng PyInstaller
Project đã có script `build.ps1`:

```powershell
cd "D:\PyCharm\Project\NTA-AutoBot"
.\build.ps1
```

Lệnh trong script:
```powershell
cd "D:\PyCharm\Project\NTA-AutoBot"
Remove-Item -Recurse -Force "build","dist" -ErrorAction SilentlyContinue
python.exe -m PyInstaller --noconfirm --clean "NTA-AutoBot.spec"
```

### 10.2 Test bản dist
```powershell
cd "D:\PyCharm\Project\NTA-AutoBot\dist\NTA-AutoBot"
.\NTA-AutoBot.exe
```

Checklist test nhanh:
- GUI mở bình thường.
- Bấm Start bot chạy được.
- Log có dòng dùng adb bundled (nếu đã bundle `third_party/platform-tools`).

### 10.3 Build installer bằng Inno Setup
Script installer: `installer/NTA-AutoBot.iss`

```powershell
cd "D:\PyCharm\Project\NTA-AutoBot"
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" ".\installer\NTA-AutoBot.iss"
```

Output mặc định: `installer/installer_output/NTA-AutoBot-Setup.exe`

## 11) Troubleshooting nhanh
- Không kết nối ADB:
  - kiểm tra BlueStacks và endpoint `127.0.0.1:5555`;
  - kiểm tra có `adb.exe` bundled hoặc `adb` trong PATH.
- OCR sai hoặc detect thiếu:
  - bật debug tương ứng và xem ảnh trong `debug_img/`;
  - tune `config/template_profiles.json` và ROI.
- Hard-Dig không takeover:
  - kiểm tra `hard_dig_plan.json` có `targets` + `start_tile` hợp lệ;
  - kiểm tra log combat đang ở trạng thái nào.
- Builder chạy sai điểm bắt đầu:
  - kiểm tra `config/build_order_runtime.json` (`start_index`) hoặc chọn lại trong Step Picker GUI.
- Không bấm được `Start` ngay khi mở app:
  - đây là hành vi đúng từ `v1.1.1` để ép setup ban đầu Builder;
  - mở `Config Editor` -> `build_order_runtime.json` -> chọn bước bắt đầu -> `Save`.
- Log không tự clear trên GUI:
  - tính năng auto-clear phụ thuộc `config/runtime.json`:
    - `terminal_auto_clear_enabled`
    - `terminal_auto_clear_interval_seconds`
  - khi auto-clear kích hoạt, `Live Log` trên GUI cũng sẽ được xóa đồng bộ.
- File `.bak` tăng dần dung lượng:
  - chỉnh trong `config/runtime.json` bằng 3 tham số backup ở trên;
  - bot sẽ tự dọn các file backup quá cũ khi bạn bấm Save config trong Config Editor.
- Bot crash khi ADB chập chờn/mất kết nối tạm thời:
  - bot đã thêm cơ chế retry reconnect khi `screencap` lỗi;
  - Vision cũng bỏ qua an toàn khi frame `None`/rỗng thay vì crash;
  - nếu vẫn lỗi liên tục, kiểm tra BlueStacks + cổng ADB và thử Start lại bot.

## 12) Công cụ phụ trợ
- Migrate map cache một lần:
```powershell
python migrate_map_cache.py
```

- Dry run migrate:
```powershell
python migrate_map_cache.py --dry-run
```

- Test captcha offline từ ảnh:
```powershell
python test_captcha_solver.py --image "debug_img\your_captcha_screen.png"
```

