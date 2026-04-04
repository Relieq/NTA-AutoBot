# NTA-AutoBot

Bot tự động cho game Android chạy qua BlueStacks + ADB + nhận diện ảnh (OpenCV/OCR), không dùng API game.

## 1) Tổng quan
- Entrypoint: `main.py`
- Vòng lặp ưu tiên: `Combat -> DailyTask -> Builder`
- Tác vụ dựa trên nhận diện UI trong `assets/`
- Captcha dùng chiến lược thực dụng: **spam chọn icon #1**, bấm `btn_ok_captcha`, kiểm tra captcha đã biến mất chưa

## 2) Kiến trúc chính
- `core/device.py`: ADB (`tap`, `swipe`, `precise_drag`, screenshot)
- `core/vision.py`: template matching đa scale + profile riêng từng template
- `core/map_core.py`: dữ liệu map + cache metadata (`difficulty_rank`, `distance_to_city`)
- `modules/scene.py`: chuyển map/city với verify sau thao tác
- `modules/combat.py`: scan mục tiêu, OCR độ khó, dispatch/retreat, xử lý popup độ khó
- `modules/builder.py`: build/upgrade theo `BUILD_SEQUENCE`, OCR level/time, OCR tên công trình
- `modules/captcha.py`: detect captcha + solve theo spam strategy

## 3) Yêu cầu môi trường
- Windows + BlueStacks
- Python 3.12+
- Có `adb` trong PATH (hoặc cài Android Platform Tools)

## 4) Cài đặt
```powershell
cd D:\PyCharm\Project\NTA-AutoBot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 5) Chạy bot
```powershell
cd D:\PyCharm\Project\NTA-AutoBot
.\.venv\Scripts\Activate.ps1
python main.py
```

`main.py` sẽ khởi tạo map/device/vision/captcha rồi chạy vòng lặp vô hạn.

## 5.1) Chạy GUI Phase 1
GUI desktop (PySide6) cho phép Start / Pause / Resume / Stop bot và xem log runtime trực tiếp.

```powershell
cd D:\PyCharm\Project\NTA-AutoBot
.\.venv\Scripts\Activate.ps1
python gui_app.py
```

Ghi chú:
- Nút `Start` sẽ chạy bot ở process riêng để UI không bị treo.
- `Pause` tạm dừng vòng lặp chính của bot; `Resume` tiếp tục.
- `Stop` ưu tiên dừng mềm, quá timeout sẽ terminate process.
- Trong lúc bot chạy qua GUI, map/config vẫn dùng cùng file như chạy `main.py`.

## 6) Cấu hình quan trọng
### Build order
Sửa `config/build_order.py` (`BUILD_SEQUENCE`):
- `name`: template building (không cần `.png`)
- `target_lv`: level mục tiêu
- `type_name`: tên hiển thị log

### Template profile theo từng nút
Sửa `config/template_profiles.json` để tune threshold/scales/weights cho từng template.

Ví dụ:
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

### Combat timing + blacklist
- `config/combat_timing.json`: thời gian chiến đấu theo tier
- `config/combat_difficulty_blacklist.json`: bật/tắt theo tier và level
- `config/combat_first_dispatch_status.json`: trạng thái đã gặp popup cảnh báo lần đầu theo từng dải độ khó

### Runtime housekeeping
Sửa `config/runtime.json`:
- `terminal_auto_clear_enabled`, `terminal_auto_clear_interval_seconds`
- `debug_auto_cleanup_enabled`, `debug_auto_cleanup_interval_seconds`, `debug_auto_cleanup_keep_hours`

## 7) Captcha (chiến lược hiện tại)
`modules/captcha.py` không còn dùng model. Luồng xử lý:
1. Detect captcha bằng `assets/title_captcha.png`
2. Trong lúc captcha còn mở (còn thấy `btn_ok_captcha`):
   - tap icon #1
   - tap nút OK
3. Sau mỗi vòng, chụp lại màn hình và kiểm tra `btn_ok_captcha` còn hay không

Các file asset bắt buộc:
- `assets/title_captcha.png`
- `assets/btn_ok_captcha.png`

## 8) Debug
### Vision
```powershell
$env:VISION_DEBUG = "1"
python main.py
```
Ảnh debug ở `debug_img/vision`.

### Combat
```powershell
$env:COMBAT_DEBUG = "1"
python main.py
```
Ảnh debug ở `debug_img/combat` (overlay OCR time, processed OCR, checkbox rounds, retreat checks).

### Builder
```powershell
$env:BUILDER_DEBUG = "1"
python main.py
```
Ảnh debug ở `debug_img/builder`.

### Captcha
```powershell
$env:CAPTCHA_DEBUG = "1"
python main.py
```
Ảnh debug ở `debug_img/captcha/spam` theo từng attempt (`before`, `after_pick`, `after_ok`).

## 9) Công cụ tiện ích
### Migrate cache map một lần (khi đổi schema/cache)
```powershell
python migrate_map_cache.py
```
Kiểm tra trước (không ghi file):
```powershell
python migrate_map_cache.py --dry-run
```

### Test captcha offline từ ảnh chụp
```powershell
python test_captcha_solver.py --image "debug_img\your_captcha_screen.png"
```
Lưu ảnh preview riêng:
```powershell
python test_captcha_solver.py --image "debug_img\your_captcha_screen.png" --save-debug "debug_img\captcha_spam_preview.png"
```

## 10) Pattern phát triển nên giữ
- Sau mỗi action quan trọng phải verify UI hậu thao tác.
- Reuse helper hiện có thay vì viết flow one-off.
- Mọi chỉnh threshold/toạ độ nên có ảnh debug đi kèm để tune nhanh.
- Với map/combat: ưu tiên dữ liệu cache (`difficulty_*`, `distance_to_city`) trước khi OCR lại.

## 11) Troubleshooting nhanh
- Không kết nối ADB: kiểm tra BlueStacks, `adb devices`, host/port trong `DeviceManager`.
- OCR sai: xem ảnh trong `debug_img/`, chỉnh ROI hoặc tiền xử lý OCR.
- Tap sai: tune profile trong `config/template_profiles.json` trước khi sửa logic lớn.
- Captcha chưa qua: kiểm tra 2 template `title_captcha.png` và `btn_ok_captcha.png`.
