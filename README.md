# NTA-AutoBot

Bot tự động cho game Android chạy qua BlueStacks + ADB + nhận diện ảnh (OpenCV/OCR), không sử dụng API game.

## 1) Tổng quan nhanh
- Entry point: `main.py`
- Vòng lặp ưu tiên cố định: `Combat -> DailyTask -> Builder`
- Bot duy trì trạng thái trong `bot_state` (cooldown, phase chiến đấu, tiến độ xây)
- Mọi thao tác đều dựa trên template image trong `assets/` (cố gắng phóng to màn hình game đến tối đa để dễ nhận diện).
- Captcha được xử lý tự động bằng `modules/captcha.py` (ONNX + EasyOCR)

## 2) Kiến trúc project
- `core/device.py`
  - `DeviceManager`: kết nối ADB, `tap`, `swipe`, `precise_drag`, chụp màn hình.
- `core/vision.py`
  - `VisionManager`: `find_template(...)`, `find_all_templates(...)` với OpenCV template matching.
- `modules/scene.py`
  - Chuyển cảnh thành/map (`go_to_city`, `leave_the_city`) theo kiểu double-check.
- `modules/daily_task.py`
  - Nhiệm vụ đơn giản hằng ngày (vòng quay, vàng free), dùng helper `find_and_tap(...)`.
- `modules/builder.py`
  - Luồng xây/nâng cấp công trình, OCR level/time, skip idempotent khi đã đủ level.
- `modules/combat.py`
  - Tìm mục tiêu trên map, OCR độ khó, xuất quân, rút quân, dead-reckoning camera.
- `modules/captcha.py`
  - Nhận captcha, OCR câu hỏi, classifier ONNX cho icon, bấm đáp án.
- `config/build_order.py`
  - Danh sách lệnh xây/nâng cấp (`BUILD_SEQUENCE`).

## 3) Yêu cầu môi trường
- Windows + BlueStacks (khuyến nghị dùng đúng tỉ lệ màn hình ổn định)
- Python 3.12+ (tôi dùng 3.12)
- Có sẵn `adb` trong PATH (hoặc cài [Android Platform Tools](https://developer.android.com/tools/releases/platform-tools?hl=vi))
- Đã cài các gói trong `requirements.txt`

## 4) Cài đặt
```powershell
cd D:\PyCharm\Project\NTA-AutoBot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Nếu gặp lỗi PaddleOCR/PaddlePaddle, thử cài riêng theo CPU wheel phù hợp bản Python của bạn.

## 5) Chạy bot
```powershell
cd D:\PyCharm\Project\NTA-AutoBot
.\.venv\Scripts\Activate.ps1
python main.py
```

`main.py` sẽ:
1. Tạo `DeviceManager` + `VisionManager`
2. Load `CaptchaSolver` (ONNX) 1 lần
3. Tạo `BuilderManager`, `DailyTaskManager`, `SceneManager`, `CombatManager`
4. Chạy vòng lặp vô tận theo thứ tự ưu tiên

## 6) Cấu hình quan trọng
### Build order
Sửa `config/build_order.py` trong `BUILD_SEQUENCE`:
- `name`: tên file template building (không cần `.png`)
- `target_lv`: level mục tiêu
- `type_name`: tên hiển thị log

### Vision threshold
- Mặc định toàn cục: `VisionManager.threshold` trong `core/vision.py` (hiện là `0.6`)
- Có thể cấu hình theo từng template trong `config/template_profiles.json`
- Thứ tự ưu tiên khi resolve ngưỡng: `threshold truyền trực tiếp` -> `profile của template` -> `default trong profile` -> `VisionManager.threshold`

Ví dụ profile theo từng nút:
```json
{
  "default": {
    "threshold": 0.6,
    "scales": [1.0, 0.95, 1.05],
    "weights": { "color": 1.0, "gray": 1.0, "edge": 0.98 }
  },
  "templates": {
    "btn_chiem.png": { "threshold": 0.67 },
    "checkbox_unchecked.png": {
      "find_all": { "threshold": 0.75, "min_distance": 18 }
    }
  }
}
```

### Combat tuning
Trong `modules/combat.py`:
- `screen_w`, `screen_h` đang giả định `1600x900`
- Rule tick checkbox: chỉ tính thành công khi OCR được `TG hành quân` của dòng quân đó
- Cấu hình thời gian combat nằm trong `config/combat_timing.json`
- Cấu hình blacklist độ khó theo từng tier/level nằm trong `config/combat_difficulty_blacklist.json`
- Màu viền xanh map (`lower_green`/`upper_green`) để tìm border target

### Runtime terminal
- Cấu hình tự clear terminal định kỳ nằm trong `config/runtime.json`
- `terminal_auto_clear_enabled`: bật/tắt tự clear terminal
- `terminal_auto_clear_interval_seconds`: chu kỳ clear (giây), tối thiểu 10 giây
- `runtime.json` được đọc bằng `utf-8-sig` để tương thích file có BOM (thường gặp khi lưu bằng PowerShell/Windows tools)

### Runtime debug cleanup
- `debug_auto_cleanup_enabled`: bật/tắt tự dọn ảnh debug
- `debug_auto_cleanup_interval_seconds`: chu kỳ quét dọn (giây)
- `debug_auto_cleanup_keep_hours`: giữ lại ảnh mới hơn số giờ này
- `debug_auto_cleanup_root_dir`: thư mục gốc cần dọn (mặc định `debug_img`)
- `debug_auto_cleanup_max_delete_per_cycle`: giới hạn số file xóa mỗi chu kỳ
- `debug_auto_cleanup_extensions`: chỉ xóa các đuôi ảnh trong danh sách

Trong `core/map_core.py`:
- Target `RESOURCE` đã có độ khó sẽ được ưu tiên theo thứ tự tăng dần:
  `Dễ X` -> `Nhập môn X` -> `Thường X` -> `Tăng bậc X` -> `Khó X` -> `Địa ngục X`.
- `UNKNOWN` hoặc không parse được độ khó sẽ đứng sau nhóm có độ khó parse được.

### Captcha model + labels
Trong `modules/captcha.py`:
- `assets/captcha_model.onnx` phải tồn tại
- Ưu tiên đọc `assets/captcha_labels.json` để đồng bộ thứ tự labels theo model
- Nếu thiếu file labels json, solver mới fallback sang danh sách hardcode
- Nếu có `assets/captcha_group_model.onnx`, solver sẽ ưu tiên score theo model 6 nhóm (đúng objective captcha)

## 7) Retrain model captcha
Dữ liệu nằm trong `dataset/` (mỗi class là 1 folder).

```powershell
cd D:\PyCharm\Project\NTA-AutoBot
.\.venv\Scripts\Activate.ps1
python train_captcha.py
```

Sau khi train, file mới được export vào:
- `assets/captcha_model.onnx`
- `assets/captcha_labels.json`

Train thêm model captcha theo 6 nhóm (khuyến nghị):
```powershell
python train_captcha_group.py
```

File export của group model:
- `assets/captcha_group_model.onnx`
- `assets/captcha_group_labels.json`

## 8) Assets là hợp đồng bắt buộc
Bot chỉ hành động được nếu template đúng và khớp UI game:
- Nút scene/task/combat/captcha nằm trong `assets/`
- Building template nằm trong `assets/buildings/`

Khi thêm hành động mới:
1. Thêm template image tương ứng
2. Viết flow tap + post-action verification
3. Thêm debug capture để dễ calib

## 9) Debug và calibration
Thư mục `debug_img/` được dùng để lưu ảnh phân tích:
- Border target + safe zone combat
- OCR crop cho level/time/difficulty
- Checkbox rounds khi dispatch/retreat
- Kiểm tra nút OK sau retreat

### Debug khoanh vùng template matching
`VisionManager` hỗ trợ lưu ảnh khoanh vùng cho `find_template`/`find_all_templates` vào `debug_img/vision`.

Bật nhanh bằng biến môi trường:
```powershell
$env:VISION_DEBUG = "1"
python main.py
```

Tắt debug:
```powershell
$env:VISION_DEBUG = "0"
```

### Debug ảnh combat (OCR thời gian hành quân, checkbox, retreat)
`CombatManager` hỗ trợ bật/tắt debug toàn cục bằng biến môi trường `COMBAT_DEBUG`.

OCR thời gian hành quân dùng `PaddleOCR` (pipeline giống builder) để ổn định hơn với chuỗi dạng thời gian.

Ảnh debug OCR thời gian được tách thành 2 nhóm:
- `debug_img/combat/time_overlay/`: ảnh full màn hình có khoanh ROI + kết quả parse
- `debug_img/combat/time_processed/`: ảnh vùng đã tiền xử lý OCR + text/parse

Bật debug combat:
```powershell
$env:COMBAT_DEBUG = "1"
python main.py
```

Tắt debug combat:
```powershell
$env:COMBAT_DEBUG = "0"
```

### Debug ảnh builder
`BuilderManager` hỗ trợ bật/tắt debug toàn cục bằng biến môi trường `BUILDER_DEBUG`.

Builder debug hiện tách theo nhóm thư mục:
- `debug_img/builder/build_list_overlay/`: ảnh overlay danh sách build từng vòng lăn
- `debug_img/builder/build_list_processed/`: ảnh ROI đã xử lý OCR theo từng dòng
- `debug_img/builder/level_ocr/`: debug OCR level công trình
- `debug_img/builder/time_ocr/`: debug OCR thời gian build/upgrade

Khi OCR tên công trình, log console sẽ in cả `raw` và `norm` để đối chiếu kết quả match.

Bật debug builder:
```powershell
$env:BUILDER_DEBUG = "1"
python main.py
```

Tắt debug builder:
```powershell
$env:BUILDER_DEBUG = "0"
```

Khi bot click sai/không tìm thấy UI:
1. Giảm/tăng threshold tại call đó
2. Kiểm tra lại template screenshot
3. Kiểm tra crop tọa độ OCR theo đúng độ phân giải

## 10) Pattern quan trọng khi phát triển
- Giữ boundary manager rõ ràng: low-level ADB ở `core/device.py`, logic nghiệp vụ ở `modules/*`.
- Sau mỗi action quan trọng, luôn check hậu quả bằng UI (nút còn hiện = fail).
- Tại builder/combat, xử lý captcha theo trạng thái: `OK`, `INTERRUPTED`, `FATAL`.
- Builder ưu tiên idempotent: đọc level hiện tại trước, đạt rồi thì skip.
- Combat dùng `camera_offset` + `reset_camera_to_city()` để tránh lạc neo tọa độ.

## 11) Troubleshooting nhanh
### Không kết nối được emulator
- Mở BlueStacks trước
- Kiểm tra `adb devices`
- Kiểm tra host/port trong `DeviceManager` (mặc định `127.0.0.1:5555`)

### OCR đọc sai level/time
- Kiểm tra ảnh trong `debug_img/`
- Điều chỉnh crop tọa độ trong `modules/builder.py`
- Đảm bảo scale màn hình không đổi so với lúc calib

### Combat không tìm thấy mục tiêu
- Kiểm tra biên màu xanh (`lower_green`, `upper_green`)
- Kiểm tra `thanh_chinh_map.png` có còn khớp map hiện tại
- Kiểm tra `screen_w/screen_h` có đúng với emulator

### Captcha fail
- Kiểm tra `assets/title_captcha.png`, `assets/btn_ok_captcha.png`
- Retrain lại model và đồng bộ thứ tự `labels`

### Test captcha offline từ ảnh chụp
Bạn có thể test solver mà không cần chờ captcha xuất hiện trong game:

```powershell
python test_captcha_solver.py --image "debug_img\your_captcha_screen.png"
```

Nếu muốn chỉ định đường dẫn ảnh debug output:

```powershell
python test_captcha_solver.py --image "debug_img\your_captcha_screen.png" --save-debug "debug_img\captcha_test_result.png"
```

## 12) Lưu ý an toàn vận hành
- Đây là bot tự động thao tác game, có rủi ro account tùy theo chính sách game.
- Nên test trên account phụ trước khi chạy dài hạn.
- Luôn theo dõi log khi thay đổi threshold/tọa độ/template.

